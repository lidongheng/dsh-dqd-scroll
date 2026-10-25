import tempfile;
import unittest;
from datetime import datetime, timedelta, timezone;
from pathlib import Path;
from types import SimpleNamespace;
from unittest.mock import patch;
from zoneinfo import ZoneInfo;

from dqd_scroll import cli;
from dqd_scroll.api.dqd_api import fetch_team_dynamics;


class FixedDateTime(datetime):
    @classmethod
    def now(cls, tz=None):
        return cls(2026, 10, 25, 0, 15, 26, tzinfo=tz);


class ReportRangeTest(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(prefix='dqd-report-range-');
        self.addCleanup(self.directory.cleanup);
        self.config_path = Path(self.directory.name) / 'config.toml';
        self.config = SimpleNamespace(
            dynamics=SimpleNamespace(team_names=('曼城',), interests=('伤病',)),
            teams=(SimpleNamespace(dqd_name='曼城', dqd_id=50000529),),
        );
        self.config_patch = patch.object(cli, 'load_config', return_value=self.config);
        self.config_patch.start();
        self.addCleanup(self.config_patch.stop);

    def test_default_range_is_24_hours_instead_of_midnight(self):
        with patch.object(cli, 'datetime', FixedDateTime), patch.object(cli, 'build_team_dynamics_reports', return_value=('all', 'interests', SimpleNamespace(page_count=1))) as build:
            self.assertEqual(cli.generate_dynamics_report(self.config_path, None, None), 0);
        since, until = build.call_args.args[-2:];
        self.assertEqual(since, datetime(2026, 10, 24, 0, 15, 26));
        self.assertEqual(until - since, timedelta(hours=24));

    def test_manual_range_is_used_exactly(self):
        since = datetime(2026, 9, 30, 23, 45);
        until = datetime(2026, 10, 2, 8, 5);
        with patch.object(cli, 'build_team_dynamics_reports', return_value=('all', 'interests', SimpleNamespace(page_count=1))) as build:
            self.assertEqual(cli.generate_dynamics_report(self.config_path, since, until), 0);
        self.assertEqual(build.call_args.args[-2:], (since, until));
        self.assertTrue((self.config_path.parent / 'out/dynamics/2026-10-02/曼城-all.md').exists());

    def test_invalid_manual_ranges_fail_before_fetch(self):
        at = datetime(2026, 10, 25, 20, 35);
        for since, until in [(at, None), (None, at), (at, at), (at, at - timedelta(minutes=1)), (at.replace(tzinfo=timezone.utc), at)]:
            with self.subTest(since=since, until=until), patch.object(cli, 'build_team_dynamics_reports') as build:
                with self.assertRaises(ValueError):
                    cli.generate_dynamics_report(self.config_path, since, until);
                build.assert_not_called();

    def test_feed_filter_includes_exact_boundaries_and_excludes_outside(self):
        since = datetime(2026, 10, 24, 20, 35);
        until = datetime(2026, 10, 25, 20, 35);
        times = [since - timedelta(seconds=1), since, until, until + timedelta(seconds=1)];
        articles = [{'id': index + 1, 'title': f'动态 {index}', 'show_time': int(at.replace(tzinfo=ZoneInfo('Asia/Shanghai')).timestamp())} for index, at in enumerate(times)];
        with patch('dqd_scroll.api.dqd_api.get_json', return_value={'code': 0, 'data': {'next': '', 'articles': articles}}):
            result = fetch_team_dynamics(50000529, since, until);
        self.assertEqual([item.dynamic_id for item in result.dynamics], [3, 2]);


if __name__ == '__main__':
    unittest.main();
