from __future__ import annotations;

from datetime import date, datetime, timedelta, timezone;

from ..models import ProcessedTeamFixture, TeamSchedule;
from .team_schedule import process_team_schedule;


_UTC_PLUS_8 = timezone(timedelta(hours=8));


def format_daily_schedule_report(
    team_name: str,
    schedule: TeamSchedule,
    report_date: date,
    period_end: date,
) -> str:
    # 数据库存 UTC；先转换为 UTC+8，再按本地日期筛选并计算整份赛程的间隔。
    if not isinstance(team_name, str) or not team_name.strip():
        raise ValueError('team_name 必须是非空字符串。');
    if not isinstance(report_date, date) or isinstance(report_date, datetime):
        raise ValueError('report_date 必须是日期。');
    if not isinstance(period_end, date) or isinstance(period_end, datetime):
        raise ValueError('period_end 必须是日期。');
    if period_end <= report_date:
        raise ValueError('period_end 必须晚于 report_date。');

    fixtures = [];
    previous_kickoff = None;
    for fixture in process_team_schedule(schedule):
        kickoff_utc = datetime.strptime(fixture.start_play, '%Y-%m-%d %H:%M:%S').replace(
            tzinfo=timezone.utc
        );
        kickoff_local = kickoff_utc.astimezone(_UTC_PLUS_8);
        rest_interval = None;
        if previous_kickoff is not None:
            rest_interval = kickoff_local - previous_kickoff;
        if report_date <= kickoff_local.date() < period_end:
            fixtures.append((fixture, kickoff_local, rest_interval));
        previous_kickoff = kickoff_local;

    inclusive_end = period_end - timedelta(days=1);
    lines = [
        f'# {team_name}赛程日报',
        '',
        f'- 生成日期：{report_date.isoformat()}',
        f'- 赛程范围：{report_date.isoformat()} 至 {inclusive_end.isoformat()}（结束日包含在内）',
        f'- 当前赛季：{schedule.season}',
        f'- 数据来源：SQLite `team_schedules` 表',
        f'- 范围内比赛：{len(fixtures)} 场',
        '',
        '## 未来一个月赛程',
        '',
    ];
    if not fixtures:
        lines.append('这个日期范围内没有已入库的比赛。');
        return '\n'.join(lines);

    lines.extend(
        [
            '| 开球时间（UTC+8） | 星期 | 赛事 | 轮次 | 对阵 | 距上一场开球间隔 |',
            '| --- | --- | --- | --- | --- | --- |',
        ]
    );
    weekdays = ('周一', '周二', '周三', '周四', '周五', '周六', '周日');
    for fixture, kickoff_local, rest_interval in fixtures:
        rest_hours = '';
        if rest_interval is not None:
            rest_hours = _format_rest_interval(rest_interval);
        values = (
            kickoff_local.strftime('%Y-%m-%d %H:%M:%S'),
            weekdays[kickoff_local.weekday()],
            fixture.competition_name,
            _fixture_round_name(fixture),
            f'{fixture.opponent_name}vs{team_name}',
            rest_hours,
        );
        escaped_values = [_markdown_cell(value) for value in values];
        lines.append(f"| {' | '.join(escaped_values)} |");

    return '\n'.join(lines);


def _fixture_round_name(fixture: ProcessedTeamFixture) -> str:
    round_name = fixture.round_name.strip();
    if not round_name:
        title = fixture.match_title.strip();
        competition = fixture.competition_name.strip();
        if competition and title.startswith(competition):
            round_name = title[len(competition):].strip();
    if '第' in round_name:
        return round_name;
    gameweek = fixture.gameweek.strip();
    if round_name and gameweek.isdecimal():
        return f'{round_name} 第{gameweek}轮';
    if round_name:
        return round_name;
    return fixture.gameweek;


def _format_rest_interval(interval: timedelta) -> str:
    hours = interval.total_seconds() / 3600;
    if hours.is_integer():
        return f'{int(hours)}小时';
    return f'{hours:g}小时';


def _markdown_cell(value: str) -> str:
    return value.replace('|', '\\|').replace('\r', ' ').replace('\n', ' ');
