from __future__ import annotations;

from ..models import PlayerProfile;


def parse_player_profile(response_body: object, person_id: int) -> PlayerProfile:
    if not isinstance(response_body, dict) or not isinstance(response_body.get('base_info'), dict):
        raise ValueError(f'person_id={person_id} 个人资料缺少 base_info。');
    base_info = response_body['base_info'];
    nationality = base_info.get('nationality');
    if not isinstance(nationality, str) or not nationality.strip():
        raise ValueError(f'person_id={person_id} 国籍必须是非空字符串。');
    measurements = {};
    for field in ('height', 'weight'):
        value = base_info.get(field);
        if isinstance(value, str) and value.isascii() and value.isdecimal():
            value = int(value);
        if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
            raise ValueError(f'person_id={person_id} {field} 必须是正整数，实际为 {value!r}。');
        measurements[field] = value;
    return PlayerProfile(person_id, nationality, measurements['height'], measurements['weight']);
