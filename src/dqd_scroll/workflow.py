from __future__ import annotations;

from datetime import datetime;
from time import sleep;
import logging;

from .api.dqd_api import fetch_player_ability, fetch_player_profile, fetch_player_statistics, fetch_team_dynamics, fetch_team_roster;
from .lib.player_profile import parse_player_profile;
from .lib.dynamics_report import format_all_team_dynamics_report, format_team_dynamics_report;
from .lib.team_dynamics import select_interesting_dynamics;
from .lib.team_roster import parse_team_roster;
from .lib.player_statistics import parse_player_statistics;
from .lib.player_ability import parse_player_ability;
from .lib.team_schedule import parse_team_schedule;
from .models import PlayerAbility, TeamDynamicsFetch;
from .repository import Repository;
from .shared import load_position_map;


logger = logging.getLogger(__name__);


def sync_team_roster(repository: Repository, dqd_team_id: int) -> tuple[int, int]:
    team = repository.get_team(dqd_team_id);
    season = repository.get_current_season(dqd_team_id);
    position_map = load_position_map();
    roster = parse_team_roster(fetch_team_roster(dqd_team_id));
    saved_count = repository.replace_team_players(dqd_team_id, roster.members);

    statistics = [];
    abilities = [];
    profiles = [];
    for member in roster.members:
        if member.attr == '主教练':
            continue;
        # 每名球员的三个请求连续执行；上一名的资料请求结束后才开始计时。
        if statistics:
            sleep(1);
        response_body = fetch_player_statistics(member.person_id);
        statistics.append(parse_player_statistics(
            response_body,
            member.person_id,
            season,
            team.match_league_name,
            member.attr == '门将',
        ));
        try:
            ability = parse_player_ability(fetch_player_ability(member.person_id), member.person_id, position_map);
        except (RuntimeError, ValueError, OSError) as error:
            # 单个球员能力不可用时保留 NULL，继续下一人，不丢弃已取得的联赛统计。
            logger.info('person_id=%s 能力数据不可用，ability/position 写入 NULL，继续下一名球员：%s', member.person_id, error);
            ability = PlayerAbility(member.person_id, None, None);
        abilities.append(ability);
        profiles.append(parse_player_profile(fetch_player_profile(member.person_id), member.person_id));

    # 全部球员处理结束后一起提交；无能力数据的球员保留 NULL。
    repository.replace_team_player_details(dqd_team_id, season, statistics, abilities, profiles);
    return saved_count, len(statistics);


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
