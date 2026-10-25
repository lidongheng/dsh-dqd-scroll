from __future__ import annotations;

import re;
from urllib.parse import parse_qs, urlsplit;

from ..models import ProcessedTeamFixture, TeamSchedule, TeamScheduleMatch;


def parse_team_schedule(
    response_body: object,
    team_id: int,
    league_serial: int,
    request_url: str,
) -> TeamSchedule:
    # 解析响应前先校验传入的球队和联赛编号，避免把响应写入错误的球队。
    _require_positive_id(team_id, 'team_id');
    _require_positive_id(league_serial, 'league_serial');
    if not isinstance(response_body, dict):
        raise ValueError('赛程响应根节点必须是 JSON 对象。');

    season_name, season_sort = _parse_current_season(response_body, team_id, request_url);
    raw_matches = response_body.get('data');
    if not isinstance(raw_matches, list) or not raw_matches:
        raise ValueError('赛程响应的 data 必须是非空比赛列表。');

    matches_by_id = {};
    for index, raw_match in enumerate(raw_matches, start=1):
        if not isinstance(raw_match, dict):
            raise ValueError(f'赛程响应 data 第 {index} 条记录必须是 JSON 对象。');

        match = _parse_match(raw_match, index);
        if team_id not in (match.team_a_id, match.team_b_id):
            raise ValueError(f'赛程响应第 {index} 场比赛不包含目标球队 ID: {team_id}');

        existing_match = matches_by_id.get(match.match_id);
        if existing_match is not None and existing_match != match:
            raise ValueError(f'同一 match_id 出现内容冲突的赛程记录: {match.match_id}');
        matches_by_id[match.match_id] = match;

    ordered_matches = tuple(
        sorted(matches_by_id.values(), key=lambda match: (match.start_play, match.match_id))
    );
    return TeamSchedule(
        team_id=team_id,
        league_serial=league_serial,
        season=season_name,
        season_sort=season_sort,
        matches=ordered_matches,
    );


def process_team_schedule(schedule: TeamSchedule) -> tuple[ProcessedTeamFixture, ...]:
    # 把 A/B 两侧变成目标球队视角，供报告和 DSH 脚本直接使用。
    processed_fixtures = [];
    for match in schedule.matches:
        if match.team_a_id == schedule.team_id:
            fixture = ProcessedTeamFixture(
                match_id=match.match_id,
                competition_name=match.competition_name,
                gameweek=match.gameweek,
                round_name=match.round_name,
                match_title=match.match_title,
                start_play=match.start_play,
                team_side='A',
                opponent_id=match.team_b_id,
                opponent_name=match.team_b_name,
                team_score=match.fs_a,
                opponent_score=match.fs_b,
                team_penalty_score=match.ps_a,
                opponent_penalty_score=match.ps_b,
                status=match.status,
            );
        elif match.team_b_id == schedule.team_id:
            fixture = ProcessedTeamFixture(
                match_id=match.match_id,
                competition_name=match.competition_name,
                gameweek=match.gameweek,
                round_name=match.round_name,
                match_title=match.match_title,
                start_play=match.start_play,
                team_side='B',
                opponent_id=match.team_a_id,
                opponent_name=match.team_a_name,
                team_score=match.fs_b,
                opponent_score=match.fs_a,
                team_penalty_score=match.ps_b,
                opponent_penalty_score=match.ps_a,
                status=match.status,
            );
        else:
            raise ValueError(f'match_id={match.match_id} 不包含目标球队 ID: {schedule.team_id}');
        processed_fixtures.append(fixture);

    return tuple(processed_fixtures);


def format_team_schedule_report(team_name: str, schedule: TeamSchedule) -> str:
    # Markdown 报告读取已经入库的赛程，并用目标球队视角展示比分和对手。
    if not isinstance(team_name, str) or not team_name.strip():
        raise ValueError('team_name 必须是非空字符串。');

    lines = [
        f'# {team_name} 最新赛季赛程',
        '',
        f'赛季：{schedule.season}',
        '',
        '| 开球时间 | 赛事 | 轮次 | 比赛标题 | 对手 | 接口侧别 | 本队比分 | 对方比分 | 本队点球 | 对方点球 | 状态 |',
        '| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |',
    ];
    for fixture in process_team_schedule(schedule):
        values = (
            fixture.start_play,
            fixture.competition_name,
            fixture.gameweek,
            fixture.match_title,
            fixture.opponent_name,
            fixture.team_side,
            fixture.team_score,
            fixture.opponent_score,
            fixture.team_penalty_score,
            fixture.opponent_penalty_score,
            fixture.status,
        );
        escaped_values = [_markdown_cell(value) for value in values];
        lines.append(f"| {' | '.join(escaped_values)} |");

    return '\n'.join(lines);


def _parse_current_season(
    response_body: dict[str, object],
    team_id: int,
    request_url: str,
) -> tuple[str, int]:
    season_list = response_body.get('season_list');
    if not isinstance(season_list, list) or not season_list:
        raise ValueError('赛程响应的 season_list 必须是非空数组。');

    current_seasons = [];
    season_sorts = [];
    for index, season_item in enumerate(season_list, start=1):
        if not isinstance(season_item, dict):
            raise ValueError(f'season_list 第 {index} 项必须是 JSON 对象。');
        if 'sort' not in season_item:
            raise ValueError(f'season_list 第 {index} 项缺少 sort。');
        season_sort = season_item['sort'];
        if isinstance(season_sort, bool) or not isinstance(season_sort, int) or season_sort <= 0:
            raise ValueError(f'season_list 第 {index} 项 sort 必须是正整数。');
        season_sorts.append(season_sort);

        if 'current' in season_item and not isinstance(season_item['current'], bool):
            raise ValueError(f'season_list 第 {index} 项 current 必须是布尔值。');
        if season_item.get('current') is True:
            current_seasons.append(season_item);

    if len(current_seasons) != 1:
        raise ValueError(f'season_list 必须且只能标记一个 current 赛季，实际为 {len(current_seasons)} 个。');

    current_season = current_seasons[0];
    season_name = current_season.get('name');
    if not isinstance(season_name, str) or re.fullmatch(r'\d{4}/\d{4}', season_name) is None:
        raise ValueError('当前赛季 name 必须符合 YYYY/YYYY 格式。');
    season_sort = current_season['sort'];
    if season_sort != max(season_sorts):
        raise ValueError('标记为 current 的赛季不是 season_list 中 sort 最大的赛季。');

    season_url = current_season.get('url');
    if not isinstance(season_url, str) or not season_url:
        raise ValueError('当前赛季缺少 url。');
    current_url_season = _season_from_url(season_url, team_id, '当前赛季');
    requested_season = _season_from_url(request_url, team_id, '实际请求');
    if requested_season != current_url_season:
        raise ValueError('实际请求 URL 的 season 与响应标记的 current 赛季不一致。');
    if requested_season != season_name.replace('/', '-'):
        raise ValueError('实际请求 URL 的 season 与 season_list.name 不匹配。');

    return season_name, season_sort;


def _season_from_url(url: str, team_id: int, label: str) -> str:
    if not isinstance(url, str) or not url:
        raise ValueError(f'{label} URL 必须是非空字符串。');
    parsed_url = urlsplit(url);
    expected_path = f'/soccer/biz/dqd/team/schedule/{team_id}';
    if parsed_url.scheme != 'https' or parsed_url.netloc != 'sport-data.dongqiudi.com':
        raise ValueError(f'{label} URL 的协议或主机与懂球帝赛程接口不匹配。');
    if parsed_url.path != expected_path:
        raise ValueError(f'{label} URL 路径必须指向目标球队: {expected_path}');
    query = parse_qs(parsed_url.query, strict_parsing=True);
    season_values = query.get('season');
    if not isinstance(season_values, list) or len(season_values) != 1:
        raise ValueError(f'{label} URL 必须且只能包含一个 season 参数。');
    if re.fullmatch(r'\d{4}-\d{4}', season_values[0]) is None:
        raise ValueError(f'{label} URL 的 season 参数必须符合 YYYY-YYYY 格式。');
    return season_values[0];


def _parse_match(raw_match: dict[str, object], index: int) -> TeamScheduleMatch:
    # API 的比赛字段在样本中都是字符串；空字符串也保留原样，不填造默认内容。
    string_fields = (
        'competition_name',
        'gameweek',
        'team_A_name',
        'team_B_name',
        'team_A_logo',
        'team_B_logo',
        'fs_A',
        'fs_B',
        'ps_A',
        'ps_B',
        'start_play',
        'suretime',
        'status',
        'playing_time',
        'scheme',
        'round_name',
        'minute',
        'minute_extra',
        'score_color',
        'match_title',
    );
    values = {};
    for field_name in string_fields:
        field_value = raw_match.get(field_name);
        if not isinstance(field_value, str):
            raise ValueError(f'赛程响应第 {index} 条记录的 {field_name} 必须是字符串。');
        values[field_name] = field_value;

    return TeamScheduleMatch(
        match_id=_parse_positive_id(raw_match.get('match_id'), index, 'match_id'),
        competition_id=_parse_positive_id(raw_match.get('competition_id'), index, 'competition_id'),
        competition_name=values['competition_name'],
        gameweek=values['gameweek'],
        team_a_id=_parse_positive_id(raw_match.get('team_A_id'), index, 'team_A_id'),
        team_b_id=_parse_positive_id(raw_match.get('team_B_id'), index, 'team_B_id'),
        team_a_name=values['team_A_name'],
        team_b_name=values['team_B_name'],
        team_a_logo=values['team_A_logo'],
        team_b_logo=values['team_B_logo'],
        fs_a=values['fs_A'],
        fs_b=values['fs_B'],
        ps_a=values['ps_A'],
        ps_b=values['ps_B'],
        start_play=values['start_play'],
        suretime=values['suretime'],
        status=values['status'],
        playing_time=values['playing_time'],
        scheme=values['scheme'],
        round_name=values['round_name'],
        minute=values['minute'],
        minute_extra=values['minute_extra'],
        score_color=values['score_color'],
        match_title=values['match_title'],
    );


def _parse_positive_id(value: object, record_index: int, field_name: str) -> int:
    if not isinstance(value, str) or not value.isdecimal():
        raise ValueError(f'赛程响应第 {record_index} 条记录的 {field_name} 必须是数字字符串。');
    parsed_value = int(value);
    if parsed_value <= 0:
        raise ValueError(f'赛程响应第 {record_index} 条记录的 {field_name} 必须是正整数。');
    return parsed_value;


def _require_positive_id(value: int, field_name: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f'{field_name} 必须是正整数。');


def _markdown_cell(value: str) -> str:
    return value.replace('|', '\\|').replace('\r', ' ').replace('\n', ' ');
