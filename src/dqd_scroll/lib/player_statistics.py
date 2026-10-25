from __future__ import annotations;

from ..models import PlayerStatistics;


def parse_player_statistics(
    response_body: object,
    person_id: int,
    season: str,
    league_name: str,
    is_goalkeeper: bool,
) -> PlayerStatistics:
    if not isinstance(response_body, dict) or not isinstance(response_body.get('league'), list):
        raise ValueError(f'person_id={person_id} 的统计响应必须包含 league 数组。');

    matching_rows = [];
    seen_ids = set();
    for row in response_body['league']:
        if not isinstance(row, dict):
            raise ValueError(f'person_id={person_id} 的 league 记录必须是对象。');
        row_season = row.get('season');
        competition = row.get('competition');
        if not isinstance(row_season, dict) or not isinstance(row_season.get('name'), str):
            raise ValueError(f'person_id={person_id} 的 league 记录缺少 season.name。');
        if not isinstance(competition, dict) or not isinstance(competition.get('short_name'), str):
            raise ValueError(f'person_id={person_id} 的 league 记录缺少 competition.short_name。');
        if row_season['name'] != season or competition['short_name'] != league_name:
            continue;
        row_id = row.get('id');
        if not isinstance(row_id, str) or not row_id:
            raise ValueError(f'person_id={person_id} 的本赛季联赛记录缺少 id。');
        if row_id in seen_ids:
            raise ValueError(f'person_id={person_id} 的联赛统计记录 id={row_id} 重复。');
        seen_ids.add(row_id);
        matching_rows.append(row);

    if not matching_rows:
        return PlayerStatistics(person_id, None, None, None, None, None);

    # 同赛季在同一联赛转会可能产生多条球队记录，累计该联赛的实际统计。
    totals = {};
    for output_field, source_field in (
        ('caps', 'appearances'),
        ('lineups', 'starts'),
        ('goals', 'goals'),
        ('assists', 'assists'),
    ):
        totals[output_field] = sum(_counter(row.get('base_info'), source_field, person_id) for row in matching_rows);
    rescues = None;
    if is_goalkeeper:
        rescues = sum(_counter(row.get('statistic'), 'saves', person_id) for row in matching_rows);
    return PlayerStatistics(person_id, totals['caps'], totals['lineups'], totals['goals'], totals['assists'], rescues);


def _counter(section: object, field: str, person_id: int) -> int:
    if not isinstance(section, dict):
        raise ValueError(f'person_id={person_id} 的统计 {field} 所属节点必须是对象。');
    value = section.get(field);
    if not isinstance(value, str) or not value.isascii() or not value.isdecimal():
        raise ValueError(f'person_id={person_id} 的统计 {field} 必须是非负整数字符串，实际为 {value!r}。');
    return int(value);
