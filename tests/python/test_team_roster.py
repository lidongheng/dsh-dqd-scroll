import json;
import sqlite3;
import tempfile;
import unittest;
from contextlib import closing;
from pathlib import Path;

from dqd_scroll.config import load_team_data;
from dqd_scroll.lib.team_roster import parse_team_roster;
from dqd_scroll.repository import Repository;


ROOT = Path(__file__).resolve().parents[2];


class TeamRosterFieldsTest(unittest.TestCase):
    def setUp(self):
        self.response = json.loads((ROOT / 'fixtures/team-roster.response.sample.json').read_text(encoding='utf-8'));
        self.player = next(group for group in self.response['data']['list'] if group['type'] == 'attacker')['data'][0];

    def test_age_and_market_value_keep_source_units_and_ignore_statistic_order(self):
        self.player['statistic'].insert(0, {'出场': '11'});
        members = {member.person_id: member for member in parse_team_roster(self.response).members};
        self.assertEqual((members[50259656].age, members[50259656].social_status), ('26岁', '2.2亿'));
        self.assertEqual((members[50002854].age, members[50002854].social_status), ('46岁', None));

    def test_missing_duplicate_or_invalid_source_values_are_rejected(self):
        for statistics in ([], [{'身价(欧)': 220000000}], [{'身价(欧)': '2.2亿'}, {'身价(欧)': '2.3亿'}]):
            with self.subTest(statistics=statistics), self.assertRaises(ValueError):
                self.player['statistic'] = statistics;
                parse_team_roster(self.response);
        self.player['statistic'] = [{'身价(欧)': '2.2亿'}];
        self.player['age'] = 26;
        with self.assertRaises(ValueError):
            parse_team_roster(self.response);

    def test_roster_refresh_updates_age_and_value_without_clearing_details(self):
        with tempfile.TemporaryDirectory(prefix='dqd-roster-fields-') as directory:
            database_path = Path(directory) / 'players.sqlite3';
            repository = Repository(database_path);
            team = next(team for team in load_team_data(ROOT / 'teams.json') if team.dqd_id == 50000529);
            repository.initialize((team,));
            repository.replace_team_players(50000529, parse_team_roster(self.response).members);
            with closing(sqlite3.connect(database_path)) as connection, connection:
                connection.execute('UPDATE players SET caps = 8, ability = 93, position = ?, nationality = ?, height = 195, weight = 94 WHERE person_id = ?;', ('ST', '挪威', 50259656));
            self.player['age'] = '27岁';
            self.player['statistic'] = [{'身价(欧)': '2.3亿'}];
            repository.replace_team_players(50000529, parse_team_roster(self.response).members);
            with closing(sqlite3.connect(database_path)) as connection:
                row = connection.execute('SELECT age, social_status, caps, ability, position, nationality, height, weight FROM players WHERE person_id = ?;', (50259656,)).fetchone();
            self.assertEqual(row, ('27岁', '2.3亿', 8, 93, 'ST', '挪威', 195, 94));


if __name__ == '__main__':
    unittest.main();
