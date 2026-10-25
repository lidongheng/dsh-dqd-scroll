import json;
import logging;
import sqlite3;
import tempfile;
import unittest;
from pathlib import Path;
from contextlib import closing;
from dataclasses import replace;
from unittest.mock import Mock, call, patch;

from dqd_scroll.config import load_team_data;
from dqd_scroll.lib.player_statistics import parse_player_statistics;
from dqd_scroll.lib.team_schedule import parse_team_schedule;
from dqd_scroll.repository import Repository;
from dqd_scroll.workflow import sync_team_roster;
from dqd_scroll.models import PlayerAbility, PlayerProfile;


ROOT = Path(__file__).resolve().parents[2];


def league_row(row_id='current', season='2026/2027', league='英超'):
    return {
        'id': row_id,
        'season': {'name': season},
        'competition': {'short_name': league},
        'base_info': {'appearances': '8', 'starts': '8', 'goals': '9', 'assists': '0'},
        'statistic': {'saves': '21'},
    };


def ability_response():
    return {
        'errno': 0,
        'data': {'average': {'val': 91}, 'fields': [{'name': '中锋', 'val': 93, 'lv': 'lv1_f'}]},
    };


class PlayerStatisticsParserTest(unittest.TestCase):
    def test_selects_database_season_and_league_without_cup_totals(self):
        response = {
            'league': [league_row(), league_row('old', '2025/2026'), league_row('other', league='德甲')],
            'cup': [league_row('cup')],
            'total': [{'list': [{'title': '进球', 'value': '13'}]}],
        };
        result = parse_player_statistics(response, 50259656, '2026/2027', '英超', False);
        self.assertEqual((result.caps, result.lineups, result.goals, result.assists, result.rescues), (8, 8, 9, 0, None));

    def test_sums_same_season_same_league_transfer_records(self):
        response = {'league': [league_row('first-club'), league_row('second-club')]};
        result = parse_player_statistics(response, 50259656, '2026/2027', '英超', False);
        self.assertEqual((result.caps, result.goals), (16, 18));

    def test_goalkeeper_saves_use_statistic_saves(self):
        result = parse_player_statistics({'league': [league_row()]}, 50228675, '2026/2027', '英超', True);
        self.assertEqual(result.rescues, 21);

    def test_absent_current_season_is_unknown_instead_of_zero(self):
        result = parse_player_statistics({'league': [league_row(season='2025/2026')]}, 1, '2026/2027', '英超', True);
        self.assertEqual((result.caps, result.lineups, result.goals, result.assists, result.rescues), (None,) * 5);

    def test_invalid_or_missing_counts_and_duplicate_rows_are_rejected(self):
        for value in (None, '-', True, -1, '1.5'):
            row = league_row();
            row['base_info']['appearances'] = value;
            with self.subTest(value=value), self.assertRaises(ValueError):
                parse_player_statistics({'league': [row]}, 1, '2026/2027', '英超', False);
        with self.assertRaises(ValueError):
            parse_player_statistics({'league': [league_row(), league_row()]}, 1, '2026/2027', '英超', False);
        row = league_row();
        del row['statistic']['saves'];
        with self.assertRaises(ValueError):
            parse_player_statistics({'league': [row]}, 1, '2026/2027', '英超', True);


class PlayerStatisticsWorkflowTest(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory(prefix='dqd-player-statistics-');
        self.addCleanup(directory.cleanup);
        self.database_path = Path(directory.name) / 'players.sqlite3';
        self.repository = Repository(self.database_path);
        self.team = next(team for team in load_team_data(ROOT / 'teams.json') if team.dqd_id == 50000529);
        self.repository.initialize((self.team,));
        with closing(sqlite3.connect(self.database_path)) as connection, connection:
            connection.execute('INSERT INTO league_seasons VALUES (?, ?, ?);', (36, '2026/2027', 127));
        self.roster = json.loads((ROOT / 'fixtures/team-roster.response.sample.json').read_text(encoding='utf-8'));
        ability_patch = patch('dqd_scroll.workflow.fetch_player_ability', return_value=ability_response());
        self.fetch_ability = ability_patch.start();
        self.addCleanup(ability_patch.stop);
        profile_patch = patch('dqd_scroll.workflow.fetch_player_profile', return_value={'base_info': {'nationality': '挪威', 'height': '195', 'weight': '94'}});
        self.fetch_profile = profile_patch.start();
        self.addCleanup(profile_patch.stop);

    def test_24_requests_wait_one_second_skip_coach_and_persist_statistics(self):
        with patch('dqd_scroll.workflow.fetch_team_roster', return_value=self.roster), \
             patch('dqd_scroll.workflow.fetch_player_statistics', return_value={'league': [league_row()]}) as fetch, \
             patch('dqd_scroll.workflow.sleep') as sleep:
            events = Mock();
            events.attach_mock(sleep, 'sleep');
            events.attach_mock(fetch, 'statistics');
            events.attach_mock(self.fetch_ability, 'ability');
            events.attach_mock(self.fetch_profile, 'profile');
            result = sync_team_roster(self.repository, 50000529);
        self.assertEqual(result, (25, 24));
        self.assertEqual(len(fetch.call_args_list), 24);
        self.assertEqual(len({item.args[0] for item in fetch.call_args_list}), 24);
        self.assertNotIn(call(50002854), fetch.call_args_list);
        self.assertEqual(sleep.call_args_list, [call(1)] * 23);
        expected_events = [];
        for request in fetch.call_args_list:
            person_id = request.args[0];
            if expected_events:
                expected_events.append(call.sleep(1));
            expected_events.extend([call.statistics(person_id), call.ability(person_id), call.profile(person_id)]);
        self.assertEqual(events.mock_calls, expected_events);
        self.assertEqual(self.fetch_ability.call_count, 24);
        self.assertEqual(self.fetch_profile.call_count, 24);
        self.assertNotIn(call(50002854), self.fetch_profile.call_args_list);
        with closing(sqlite3.connect(self.database_path)) as connection, connection:
            self.assertEqual(connection.execute('SELECT COUNT(*) FROM players WHERE stats_season = ?;', ('2026/2027',)).fetchone()[0], 24);
            self.assertEqual(connection.execute('SELECT caps, lineups, goals, assists, rescues FROM players WHERE person_id = 50259656;').fetchone(), (8, 8, 9, 0, None));
            self.assertEqual(connection.execute('SELECT rescues FROM players WHERE person_id = 50228675;').fetchone()[0], 21);
            self.assertEqual(connection.execute('SELECT ability, position FROM players WHERE person_id = 50259656;').fetchone(), (93, 'ST'));
            self.assertEqual(connection.execute('SELECT nationality, height, weight FROM players WHERE person_id = 50259656;').fetchone(), ('挪威', 195, 94));
            self.assertEqual(connection.execute('SELECT nationality, height, weight FROM players WHERE person_id = 50002854;').fetchone(), (None, None, None));

    def test_profile_failure_does_not_commit_partial_profiles_or_statistics(self):
        with patch('dqd_scroll.workflow.fetch_team_roster', return_value=self.roster), \
             patch('dqd_scroll.workflow.fetch_player_statistics', return_value={'league': [league_row()]}), \
             patch('dqd_scroll.workflow.sleep'):
            sync_team_roster(self.repository, 50000529);
        self.fetch_profile.side_effect = [
            {'base_info': {'nationality': '新国籍', 'height': 200, 'weight': 95}},
            RuntimeError('HTTP 503'),
        ];
        changed = league_row();
        changed['base_info']['goals'] = '99';
        with patch('dqd_scroll.workflow.fetch_team_roster', return_value=self.roster), \
             patch('dqd_scroll.workflow.fetch_player_statistics', return_value={'league': [changed]}), \
             patch('dqd_scroll.workflow.sleep'), self.assertRaises(RuntimeError):
            sync_team_roster(self.repository, 50000529);
        with closing(sqlite3.connect(self.database_path)) as connection:
            self.assertEqual(connection.execute('SELECT nationality, height, weight, goals FROM players WHERE person_id=50259656;').fetchone(), ('挪威', 195, 94, 9));

    def test_http_failure_does_not_partially_replace_saved_statistics(self):
        with patch('dqd_scroll.workflow.fetch_team_roster', return_value=self.roster), \
             patch('dqd_scroll.workflow.fetch_player_statistics', return_value={'league': [league_row()]}), \
             patch('dqd_scroll.workflow.sleep'):
            sync_team_roster(self.repository, 50000529);
        changed_row = league_row();
        changed_row['base_info']['goals'] = '99';
        with patch('dqd_scroll.workflow.fetch_team_roster', return_value=self.roster), \
             patch('dqd_scroll.workflow.fetch_player_statistics', side_effect=[{'league': [changed_row]}, RuntimeError('HTTP 429')]), \
             patch('dqd_scroll.workflow.sleep'), self.assertRaises(RuntimeError):
            sync_team_roster(self.repository, 50000529);
        with closing(sqlite3.connect(self.database_path)) as connection, connection:
            self.assertEqual(connection.execute('SELECT goals FROM players WHERE person_id = 50259656;').fetchone()[0], 9);

    def test_database_season_change_is_rejected_before_statistics_commit(self):
        from dqd_scroll.models import PlayerStatistics;
        with self.assertRaises(ValueError):
            self.repository.replace_team_player_details(
                50000529, '2025/2026', [PlayerStatistics(1, 1, 1, 1, 1, None)], [PlayerAbility(1, 93, 'ST')], [PlayerProfile(1, '挪威', 195, 94)],
            );

    def test_ability_failure_logs_info_and_keeps_processing_statistics(self):
        with patch('dqd_scroll.workflow.fetch_team_roster', return_value=self.roster), \
             patch('dqd_scroll.workflow.fetch_player_statistics', return_value={'league': [league_row()]}), \
             patch('dqd_scroll.workflow.sleep'):
            sync_team_roster(self.repository, 50000529);
        changed_row = league_row();
        changed_row['base_info']['goals'] = '99';
        self.fetch_ability.reset_mock();
        self.fetch_ability.side_effect = RuntimeError('ability HTTP 429');
        with patch('dqd_scroll.workflow.fetch_team_roster', return_value=self.roster), \
             patch('dqd_scroll.workflow.fetch_player_statistics', return_value={'league': [changed_row]}) as fetch, \
             patch('dqd_scroll.workflow.sleep'), self.assertLogs('dqd_scroll.workflow', level='INFO') as logs:
            result = sync_team_roster(self.repository, 50000529);
        self.assertEqual(result, (25, 24));
        self.assertEqual((fetch.call_count, self.fetch_ability.call_count), (24, 24));
        self.assertEqual(len(logs.records), 24);
        self.assertTrue(all(record.levelno == logging.INFO for record in logs.records));
        with closing(sqlite3.connect(self.database_path)) as connection, connection:
            self.assertEqual(connection.execute('SELECT goals, ability, position FROM players WHERE person_id = 50259656;').fetchone(), (99, None, None));

    def test_missing_ability_saves_null_and_next_player_still_gets_ability(self):
        self.fetch_ability.side_effect = [{'errno': 0, 'data': {'fields': []}}] + [ability_response()] * 23;
        with patch('dqd_scroll.workflow.fetch_team_roster', return_value=self.roster), \
             patch('dqd_scroll.workflow.fetch_player_statistics', return_value={'league': [league_row()]}), \
             patch('dqd_scroll.workflow.sleep'), self.assertLogs('dqd_scroll.workflow', level='INFO') as logs:
            result = sync_team_roster(self.repository, 50000529);
        self.assertEqual(result, (25, 24));
        self.assertEqual(len(logs.records), 1);
        with closing(sqlite3.connect(self.database_path)) as connection, connection:
            self.assertEqual(connection.execute('SELECT ability, position FROM players WHERE person_id = 50259656;').fetchone(), (None, None));
            self.assertEqual(connection.execute('SELECT ability, position FROM players WHERE person_id = 50436685;').fetchone(), (93, 'ST'));

    def test_missing_database_season_prevents_network_calls(self):
        with closing(sqlite3.connect(self.database_path)) as connection, connection:
            connection.execute('DELETE FROM league_seasons;');
        with patch('dqd_scroll.workflow.fetch_team_roster') as fetch, self.assertRaises(ValueError):
            sync_team_roster(self.repository, 50000529);
        fetch.assert_not_called();

    def test_new_league_season_clears_old_player_statistics(self):
        with patch('dqd_scroll.workflow.fetch_team_roster', return_value=self.roster), \
             patch('dqd_scroll.workflow.fetch_player_statistics', return_value={'league': [league_row()]}), \
             patch('dqd_scroll.workflow.sleep'):
            sync_team_roster(self.repository, 50000529);
        body = json.loads((ROOT / 'fixtures/team-schedule.response.sample.json').read_text(encoding='utf-8'));
        schedule = parse_team_schedule(
            body, 50000529, 36,
            'https://sport-data.dongqiudi.com/soccer/biz/dqd/team/schedule/50000529?season=2026-2027',
        );
        self.repository.replace_team_schedule(replace(schedule, season='2027/2028', season_sort=128));
        with closing(sqlite3.connect(self.database_path)) as connection, connection:
            self.assertEqual(connection.execute('SELECT caps, rescues, stats_season, ability, position FROM players WHERE person_id = 50228675;').fetchone(), (None,) * 5);

    def test_migration_keeps_old_player_values_and_adds_nullable_statistics(self):
        old_path = self.database_path.parent / 'old.sqlite3';
        with closing(sqlite3.connect(old_path)) as connection, connection:
            connection.execute('CREATE TABLE players (person_id INTEGER PRIMARY KEY, person_name TEXT, attr TEXT, shirt_number TEXT, person_en_name TEXT);');
            connection.execute('INSERT INTO players VALUES (?, ?, ?, ?, ?);', (1, '球员', '前锋', '9', 'Player'));
        repository = Repository(old_path);
        repository.initialize((self.team,));
        repository.initialize((self.team,));
        with closing(sqlite3.connect(old_path)) as connection, connection:
            self.assertEqual(connection.execute('SELECT person_name, shirt_number, caps, rescues, stats_season, ability, position FROM players WHERE person_id = 1;').fetchone(), ('球员', '9', None, None, None, None, None));
            self.assertEqual(connection.execute('SELECT age, social_status FROM players WHERE person_id = 1;').fetchone(), (None, None));
            self.assertEqual(connection.execute('SELECT nationality, height, weight FROM players WHERE person_id = 1;').fetchone(), (None, None, None));


if __name__ == '__main__':
    unittest.main();
