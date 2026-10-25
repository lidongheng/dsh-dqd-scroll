from __future__ import annotations;

from dataclasses import dataclass;
from datetime import datetime;


@dataclass(frozen=True)
class Team:
    # 球队资料已保存到 SQLite；运行时命令从 teams 表读取此记录。
    team_id: int;
    dqd_name: str;
    qiutan_name: str;
    qiutan_serial: str;
    league_serial: int;
    league_slug: str;
    match_league_name: str;


@dataclass(frozen=True)
class RosterMember:
    # person_id 在接口响应中是数字字符串；解析时会转成整数，便于 SQLite 建立关联。
    person_id: int;
    # 每次刷新球队名单时，都用接口响应中的姓名更新本地人员记录。
    person_name: str;
    # attr 表示接口返回的位置或岗位，例如“前锋”或“主教练”，会写入 players 表。
    attr: str;


@dataclass(frozen=True)
class TeamRoster:
    # 保存四种球员位置和一名主教练；教练组其他人员不会进入球队名单。
    members: tuple[RosterMember, ...];


@dataclass(frozen=True)
class TeamScheduleMatch:
    # match_id 是赛程记录的唯一标识；其余字段保留接口提供的比赛信息。
    match_id: int;
    competition_id: int;
    competition_name: str;
    gameweek: str;
    team_a_id: int;
    team_b_id: int;
    team_a_name: str;
    team_b_name: str;
    team_a_logo: str;
    team_b_logo: str;
    fs_a: str;
    fs_b: str;
    ps_a: str;
    ps_b: str;
    start_play: str;
    suretime: str;
    status: str;
    playing_time: str;
    scheme: str;
    round_name: str;
    minute: str;
    minute_extra: str;
    score_color: str;
    match_title: str;


@dataclass(frozen=True)
class TeamSchedule:
    # league_serial 与 season 来自当前赛季选项；matches 只含这支球队的当前赛季赛程。
    team_id: int;
    league_serial: int;
    season: str;
    season_sort: int;
    matches: tuple[TeamScheduleMatch, ...];


@dataclass(frozen=True)
class ProcessedTeamFixture:
    # 将原始 A/B 两侧转换为指定球队视角，同时保留接口侧别，不推断主客场。
    match_id: int;
    competition_name: str;
    gameweek: str;
    round_name: str;
    match_title: str;
    start_play: str;
    team_side: str;
    opponent_id: int;
    opponent_name: str;
    team_score: str;
    opponent_score: str;
    team_penalty_score: str;
    opponent_penalty_score: str;
    status: str;


@dataclass(frozen=True)
class TeamDynamic:
    # 动态对象仅保留日报需要的字段；不映射到 SQLite。
    dynamic_id: int;
    feed_time: datetime;
    title: str;
    content: str;
    link: str | None;
    matched_interests: tuple[str, ...];


@dataclass(frozen=True)
class TeamDynamicsFetch:
    # 未到截止时间时需结合 pages_reached_end 判断是否耗尽接口，或触发 50 页上限。
    dynamics: tuple[TeamDynamic, ...];
    page_count: int;
    pages_reached_cutoff: bool;
    pages_reached_end: bool;
