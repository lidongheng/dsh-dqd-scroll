from __future__ import annotations;

from datetime import datetime;

from .api.dqd_api import fetch_team_dynamics;
from .lib.dynamics_report import format_all_team_dynamics_report, format_team_dynamics_report;
from .lib.team_dynamics import select_interesting_dynamics;
from .lib.team_roster import parse_team_roster;
from .lib.team_schedule import parse_team_schedule;
from .models import TeamDynamicsFetch;
from .repository import Repository;


def save_team_roster_response(
    repository: Repository,
    dqd_team_id: int,
    response_body: object,
) -> int:
    # 每次拿到新名单时，先校验人员 ID、姓名和 attr，再在同一事务中刷新人员资料与球队关联。
    roster = parse_team_roster(response_body);
    return repository.replace_team_players(dqd_team_id, roster.members);


def save_team_schedule_response(
    repository: Repository,
    dqd_team_id: int,
    league_serial: int,
    response_body: object,
    request_url: str,
) -> int:
    # 对照实际请求 URL 校验响应赛季，再将映射和去重后的赛程原子写入 SQLite。
    schedule = parse_team_schedule(response_body, dqd_team_id, league_serial, request_url);
    return repository.replace_team_schedule(schedule);


def build_team_dynamics_reports(
    team_name: str,
    team_id: int,
    interests: tuple[str, ...],
    since: datetime,
    until: datetime,
) -> tuple[str, str, TeamDynamicsFetch]:
    # 一次请求同时生成全部动态与兴趣命中报告，不调用 Repository，也不写入 SQLite。
    if since >= until:
        raise ValueError('动态日报开始时间必须早于结束时间。');
    fetch_result = fetch_team_dynamics(team_id, since, until);
    selected_dynamics = select_interesting_dynamics(fetch_result.dynamics, interests);
    all_report_markdown = format_all_team_dynamics_report(
        team_name,
        fetch_result.dynamics,
        fetch_result,
        since,
        until,
    );
    interests_report_markdown = format_team_dynamics_report(
        team_name,
        interests,
        selected_dynamics,
        fetch_result,
        since,
        until,
    );
    return all_report_markdown, interests_report_markdown, fetch_result;
