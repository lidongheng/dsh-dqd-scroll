import json;
import io;
import tempfile;
import unittest;
from pathlib import Path;
from contextlib import redirect_stdout, redirect_stderr;
from types import SimpleNamespace;
from unittest.mock import Mock, call, patch;

from bs4 import BeautifulSoup;

from dqd_scroll.lib.club_analysis import aggregate_matches, format_club_report, generate_club_report, roster_by_number;
from dqd_scroll.lib.club_lineup import recommend_lineup;
from dqd_scroll.lib.club_matches import parse_match_lineup, parse_schedule;
from dqd_scroll.lib.player_profile import parse_player_profile;
from dqd_scroll.cli import analyze_club;


FIXTURES = Path(__file__).resolve().parents[2] / 'fixtures/club-analysis';


class PlayerProfileTest(unittest.TestCase):
    def test_profile_preserves_nationality_and_normalizes_measurements(self):
        profile = parse_player_profile({'base_info': {'nationality': '挪威/英格兰', 'height': '195', 'weight': 94}}, 1);
        self.assertEqual((profile.nationality, profile.height, profile.weight), ('挪威/英格兰', 195, 94));

    def test_missing_invalid_or_zero_measurements_are_rejected(self):
        for field in ('height', 'weight', 'nationality'):
            for value in (None, '', 0, True, '未知'):
                if field == 'nationality' and value == '未知':
                    continue;
                base = {'nationality': '挪威', 'height': '195', 'weight': '94'};
                base[field] = value;
                with self.subTest(field=field, value=value), self.assertRaises(ValueError):
                    parse_player_profile({'base_info': base}, 1);


class ClubAnalysisTest(unittest.TestCase):
    def setUp(self):
        self.schedule_text = (FIXTURES / 'schedule.js').read_text(encoding='utf-8');
        self.roster = json.loads((FIXTURES / 'roster.json').read_text(encoding='utf-8'));
        self.expected = json.loads((FIXTURES / 'expected.json').read_text(encoding='utf-8'));
        self.matches = parse_schedule(self.schedule_text, '26', 36, '2026/2027', None);
        self.html = {match.match_id: (FIXTURES / f'{match.match_id}.html').read_text(encoding='utf-8') for match in self.matches};
        self.parsed = [(match, parse_match_lineup(self.html[match.match_id], match, '26')) for match in self.matches];

    def test_schedule_filters_team_status_and_round_and_accepts_sparse_arrays(self):
        self.assertEqual([(match.match_id, match.side) for match in self.matches], [(3003856, 'home'), (3003863, 'guest')]);
        self.assertEqual(len(parse_schedule(self.schedule_text, '26', 36, '2026/2027', 2)), 1);
        self.assertEqual(parse_schedule(self.schedule_text, '26', 36, '2026/2027', 1), []);
        for season, round_number in (('2025/2026', None), ('2026/2027', 0)):
            with self.assertRaises(ValueError):
                parse_schedule(self.schedule_text, '26', 36, season, round_number);

    def test_home_away_events_and_position_order_match_original_js(self):
        for (_, lineup), expected in zip(self.parsed, self.expected['parsed']):
            self.assertEqual(lineup.formation, expected['formation']);
            self.assertEqual(len(lineup.players), len(expected['players']));
            for actual, source in zip(lineup.players, expected['players']):
                self.assertEqual((actual.number, actual.name, actual.caps, actual.lineups, actual.goals, actual.assists),
                                 tuple(source[key] for key in ('number', 'name', 'caps', 'lineups', 'goals', 'assists')));
                if actual.lineups:
                    self.assertEqual(actual.position, source['position']);
                else:
                    self.assertIsNone(actual.position);
        self.assertTrue(any(player.caps == 0 for _, lineup in self.parsed for player in lineup.players));

    def test_totals_formations_and_recommendation_match_original_js(self):
        analysis = aggregate_matches(self.roster, self.parsed);
        actual = {player['shirt_number']: {field: player[field] for field in ('caps', 'lineups', 'goals', 'assists', 'positions')}
                  for player in analysis['players']};
        # 原 JSON 也包含未登场替补；终端摘要和本报告只展示上场人员。
        appeared = {number: player for number, player in self.expected['players'].items() if player['caps'] > 0};
        self.assertEqual(actual, appeared);
        self.assertEqual(analysis['formations'], self.expected['formations']);
        self.assertEqual([[player['shirt_number'], player['recommended_position']] for player in analysis['recommended']], self.expected['recommended']);
        self.assertTrue(analysis['unmatched']);

    def test_unknown_formation_does_not_assign_positions_or_default_to_442(self):
        html = self.html[3003856].replace('4-2-3-1', '9-9-9');
        parsed = parse_match_lineup(html, self.matches[0], '26');
        self.assertEqual(parsed.formation, '999');
        self.assertTrue(all(player.position is None for player in parsed.players));
        analysis = aggregate_matches(self.roster, [(self.matches[0], parsed)]);
        self.assertEqual(analysis['recommended'], []);
        self.assertEqual(recommend_lineup(analysis['players'], '999'), []);
        markdown = format_club_report('曼城', '2026/2027', None, [(self.matches[0], parsed)], analysis);
        self.assertIn('未配置阵型：999', markdown);
        self.assertNotIn('最常用阵型：442', markdown);

    def test_unlinked_bench_name_is_read_from_actual_text(self):
        soup = BeautifulSoup(self.html[3003856], 'html.parser');
        link = soup.select_one('#matchBox2 .backupPlay .home .name a');
        name = link.get_text(strip=True);
        link.unwrap();
        parsed = parse_match_lineup(str(soup), self.matches[0], '26');
        self.assertIn(name, [player.name for player in parsed.players]);

    def test_missing_starter_and_duplicate_numbers_are_rejected(self):
        soup = BeautifulSoup(self.html[3003856], 'html.parser');
        soup.select_one('#matchBox2 .plays .home .play').decompose();
        with self.assertRaises(ValueError):
            parse_match_lineup(str(soup), self.matches[0], '26');
        with self.assertRaises(ValueError):
            roster_by_number(self.roster + [self.roster[0]]);

    def repository(self):
        repository = Mock();
        repository.get_team.return_value = SimpleNamespace(dqd_name='曼城', league_serial=36, qiutan_serial='26');
        repository.get_current_season.return_value = '2026/2027';
        repository.get_club_players.return_value = self.roster;
        return repository;

    def fetch(self, url, referer):
        if 's36.js' in url:
            return self.schedule_text;
        for match_id, html in self.html.items():
            if str(match_id) in url:
                return html;
        raise AssertionError(url);

    def test_atomic_report_and_same_rendered_content(self):
        with tempfile.TemporaryDirectory() as directory, patch('dqd_scroll.lib.club_analysis.fetch_text', side_effect=self.fetch), patch('dqd_scroll.lib.club_analysis.sleep'):
            output, markdown = generate_club_report(self.repository(), 50000529, None, Path(directory));
            self.assertEqual(output.read_text(encoding='utf-8'), markdown);
            self.assertEqual(output.relative_to(directory), Path('2026-2027/曼城/all.md'));
            self.assertIn('2.2亿', markdown);
            self.assertNotIn('2.2亿万欧元', markdown);
            self.assertIn('比赛数量：2', markdown);
            self.assertIn('## 未匹配人员', markdown);
            cutoff, _ = generate_club_report(self.repository(), 50000529, 2, Path(directory));
            self.assertEqual(cutoff.name, 'before-round-2.md');

    def test_failure_retries_continues_and_keeps_successful_report(self):
        def fail_first(url, referer):
            if '3003856cn' in url:
                raise RuntimeError('HTTP 503');
            return self.fetch(url, referer);
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / '2026-2027/曼城/all.md';
            output.parent.mkdir(parents=True);
            output.write_text('previous success', encoding='utf-8');
            with patch('dqd_scroll.lib.club_analysis.fetch_text', side_effect=fail_first) as fetch, patch('dqd_scroll.lib.club_analysis.sleep') as sleep:
                with self.assertRaisesRegex(RuntimeError, '3003856'):
                    generate_club_report(self.repository(), 50000529, None, Path(directory));
            self.assertEqual(len(fetch.call_args_list), 6);
            self.assertIn('3003863', fetch.call_args_list[-1].args[0]);
            self.assertEqual(sleep.call_args_list, [call(1), call(1), call(2), call(4), call(1)]);
            self.assertEqual(output.read_text(encoding='utf-8'), 'previous success');

    def test_zero_matches_does_not_create_report(self):
        with tempfile.TemporaryDirectory() as directory, patch('dqd_scroll.lib.club_analysis.fetch_text', side_effect=self.fetch):
            with self.assertRaisesRegex(ValueError, '没有符合范围'):
                generate_club_report(self.repository(), 50000529, 1, Path(directory));
            self.assertEqual(list(Path(directory).iterdir()), []);

    def test_cli_stdout_equals_saved_markdown_and_failure_returns_nonzero(self):
        with tempfile.TemporaryDirectory() as directory:
            stdout = io.StringIO();
            stderr = io.StringIO();
            with patch('dqd_scroll.cli._repository_for_existing_database', return_value=self.repository()), \
                 patch('dqd_scroll.lib.club_analysis.fetch_text', side_effect=self.fetch), \
                 patch('dqd_scroll.lib.club_analysis.sleep'), redirect_stdout(stdout), redirect_stderr(stderr):
                status = analyze_club(Path(directory) / 'players.sqlite3', 50000529, None, Path(directory));
            self.assertEqual(status, 0);
            self.assertEqual(stdout.getvalue(), (Path(directory) / '2026-2027/曼城/all.md').read_text(encoding='utf-8'));
            self.assertIn('报告已保存', stderr.getvalue());
            with patch('dqd_scroll.cli.generate_club_report', side_effect=RuntimeError('失败比赛：3003856')), \
                 patch('dqd_scroll.cli._repository_for_existing_database', return_value=self.repository()), redirect_stderr(io.StringIO()):
                self.assertEqual(analyze_club(Path(directory) / 'players.sqlite3', 50000529, None, Path(directory)), 1);

    def test_publish_error_cleans_temporary_file_and_preserves_existing_report(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / '2026-2027/曼城/all.md';
            output.parent.mkdir(parents=True);
            output.write_text('previous success', encoding='utf-8');
            with patch('dqd_scroll.lib.club_analysis.fetch_text', side_effect=self.fetch), \
                 patch('dqd_scroll.lib.club_analysis.sleep'), \
                 patch('dqd_scroll.lib.club_analysis.os.replace', side_effect=OSError('permission denied')), self.assertRaises(OSError):
                generate_club_report(self.repository(), 50000529, None, Path(directory));
            self.assertEqual(output.read_text(encoding='utf-8'), 'previous success');
            self.assertEqual(list(output.parent.glob('*.tmp')), []);


if __name__ == '__main__':
    unittest.main();
