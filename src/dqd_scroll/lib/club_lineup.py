from __future__ import annotations;

import json;
from importlib.resources import files;


# 阵型、分组及位置兼容表从原 JS 原样迁移；未知阵型不推断为 442。
CONFIG = json.loads(files('dqd_scroll.shared').joinpath('clubLineup.json').read_text(encoding='utf-8'));
FORMATIONS = CONFIG['formations'];
GROUPS = CONFIG['groups'];
COMPATIBILITY = CONFIG['compatibility'];
POSITION_GROUP = {position: group for group, positions in GROUPS.items() for position in positions};


def recommend_lineup(players: list[dict], formation: str) -> list[dict]:
    if formation not in FORMATIONS:
        return [];
    positions = FORMATIONS[formation];
    ranked = [];
    for player in players:
        preferences = sorted(player['positions'], key=lambda position: -player['positions'][position]);
        # 没有实际位置记录的球员不能被默认为中场加入推荐。
        if not preferences:
            continue;
        group = POSITION_GROUP[preferences[0]];
        ranked.append({**player, 'preferences': preferences, 'group': group});
    ranked.sort(key=lambda player: -player['lineups']);
    candidates = ranked[:16];
    if len(candidates) < 11:
        return [];
    selected = [];
    for group in GROUPS:
        required = sum(POSITION_GROUP[position] == group for position in positions);
        selected.extend([player for player in candidates if player['group'] == group][:required]);
    selected_ids = {player['person_id'] for player in selected};
    selected.extend([player for player in candidates if player['person_id'] not in selected_ids][:11 - len(selected)]);

    def score(player: dict, position: str) -> float:
        group = POSITION_GROUP[position];
        player_group = player['group'];
        value = 0;
        if (group == 'GK') != (player_group == 'GK'):
            value = -1000;
        elif {group, player_group} == {'DF', 'FW'}:
            value = -800;
        elif group != player_group:
            value = -300;
        counts = player['positions'];
        if position in counts:
            value += counts[position] * 1000;
        else:
            preferences = player['preferences'];
            for index, preferred in enumerate(preferences):
                if preferred in COMPATIBILITY[position]:
                    value += counts[preferred] * (len(preferences) - index) / len(preferences) * 100;
                    break;
        return value + player['lineups'] * 5;

    assigned = set();
    lineup = [];
    # 先门将，再后卫、中场、前锋；相同评分保持原始候选顺序。
    for group in GROUPS:
        for position in positions:
            if POSITION_GROUP[position] != group:
                continue;
            choices = [player for player in selected if player['person_id'] not in assigned];
            if group == 'GK':
                choices = [player for player in choices if player['group'] == 'GK'];
            if not choices:
                return [];
            best = max(choices, key=lambda player: score(player, position));
            assigned.add(best['person_id']);
            lineup.append({**best, 'recommended_position': position});
    if len(lineup) != 11 or not any(player['group'] == 'GK' for player in lineup):
        return [];
    return lineup;
