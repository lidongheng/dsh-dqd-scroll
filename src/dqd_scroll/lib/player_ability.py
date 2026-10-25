from collections.abc import Mapping;

from ..models import PlayerAbility;


def parse_player_ability(response_body: object, person_id: int, position_map: Mapping[str, str]) -> PlayerAbility:
    if not isinstance(response_body, dict):
        raise ValueError(f'person_id={person_id} 的能力响应必须是对象。');
    errno = response_body.get('errno');
    if isinstance(errno, bool) or not isinstance(errno, int):
        raise ValueError(f'person_id={person_id} 的能力响应缺少整数 errno。');
    if errno != 0:
        errmsg = response_body.get('errmsg');
        raise ValueError(f'person_id={person_id} 的能力接口失败: errno={errno}, errmsg={errmsg!r}');
    data = response_body.get('data');
    if not isinstance(data, dict) or not isinstance(data.get('fields'), list) or not data['fields']:
        raise ValueError(f'person_id={person_id} 的能力响应缺少非空 data.fields。');

    candidates = [];
    for field in data['fields']:
        if not isinstance(field, dict) or not isinstance(field.get('lv'), str):
            raise ValueError(f'person_id={person_id} 的能力位置项缺少字符串 lv。');
        if not field['lv'].endswith('_f'):
            continue;
        value = field.get('val');
        if isinstance(value, str) and value.isascii() and value.isdecimal():
            value = int(value);
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise ValueError(f'person_id={person_id} 的能力位置 val 必须是非负整数。');
        name = field.get('name');
        if not isinstance(name, str) or not name.strip():
            raise ValueError(f'person_id={person_id} 的能力位置项缺少非空 name。');
        candidates.append((value, name));
    if not candidates:
        raise ValueError(f'person_id={person_id} 的能力位置中没有 lv 以 _f 结尾的项目。');

    # 与 getAbilityPosition 一致：只比较 _f 项；同分时保留接口中的第一项。
    ability, name = max(candidates, key=lambda candidate: candidate[0]);
    if name not in position_map:
        raise ValueError(f'positionMap.json 未配置懂球帝位置: {name}');
    return PlayerAbility(person_id, ability, position_map[name]);
