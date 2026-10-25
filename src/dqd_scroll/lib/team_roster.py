from __future__ import annotations;

from ..models import RosterMember, TeamRoster;


PLAYER_GROUP_TYPES = frozenset({'attacker', 'midfielder', 'defender', 'goalkeeper'});
STAFF_GROUP_TYPES = frozenset({'coach', 'manager'});


def parse_team_roster(response_body: object) -> TeamRoster:
    # 这里校验接口样本、筛选名单成员并清洗重复记录；字段变化时明确报错，不猜字段或补默认值。
    if not isinstance(response_body, dict):
        raise ValueError('球队名单响应根节点必须是 JSON 对象。');

    response_code = response_body.get('code');
    if isinstance(response_code, bool) or not isinstance(response_code, int):
        raise ValueError('球队名单响应缺少整数 code 字段。');
    if response_code != 0:
        raise ValueError(f'球队名单接口返回业务错误 code: {response_code}');

    response_message = response_body.get('message');
    if not isinstance(response_message, str):
        raise ValueError('球队名单响应缺少字符串 message 字段。');

    response_data = response_body.get('data');
    if not isinstance(response_data, dict):
        raise ValueError('球队名单响应的 data 字段必须是 JSON 对象。');
    groups = response_data.get('list');
    if not isinstance(groups, list):
        raise ValueError('球队名单响应缺少 data.list 分组列表。');

    roster_members_by_id = {};
    for group_index, group in enumerate(groups):
        if not isinstance(group, dict):
            raise ValueError(f'data.list[{group_index}] 必须是 JSON 对象。');

        group_type = group.get('type');
        if not isinstance(group_type, str):
            raise ValueError(f'data.list[{group_index}] 缺少字符串 type 字段。');

        members = group.get('data');
        if not isinstance(members, list):
            raise ValueError(f'data.list[{group_index}].data 必须是名单数组。');

        # 老板、主席等工作人员不进入名单；教练分组只保留主教练这一条记录。
        if group_type == 'manager':
            continue;
        if group_type not in PLAYER_GROUP_TYPES and group_type not in STAFF_GROUP_TYPES:
            raise ValueError(f'遇到未识别的球队名单分组 type: {group_type}');

        if group_type == 'coach':
            head_coaches = [
                (member_index, member)
                for member_index, member in enumerate(members)
                if isinstance(member, dict) and member.get('type') == '主教练'
            ];
            if len(head_coaches) != 1:
                raise ValueError('球队名单响应必须且只能包含一条 type 为“主教练”的记录。');
            members_to_parse = head_coaches;
            attr = '主教练';
        else:
            attr = group.get('title');
            if not isinstance(attr, str) or not attr.strip():
                raise ValueError(f'data.list[{group_index}].title 必须是非空字符串。');
            members_to_parse = list(enumerate(members));

        for member_index, member in members_to_parse:
            if not isinstance(member, dict):
                raise ValueError(f'data.list[{group_index}].data[{member_index}] 必须是 JSON 对象。');

            if group_type == 'coach' and member.get('type') != '主教练':
                continue;

            person_id_value = member.get('person_id');
            if (
                not isinstance(person_id_value, str)
                or not person_id_value.isascii()
                or not person_id_value.isdecimal()
            ):
                raise ValueError(
                    f'data.list[{group_index}].data[{member_index}].person_id 必须是数字字符串。'
                );

            person_id = int(person_id_value);
            if person_id <= 0:
                raise ValueError(f'球队名单中的 person_id 必须是正整数: {person_id_value}');
            person_name = member.get('person_name');
            if not isinstance(person_name, str) or not person_name.strip():
                raise ValueError(
                    f'data.list[{group_index}].data[{member_index}].person_name 必须是非空字符串。'
                );

            roster_member = RosterMember(person_id=person_id, person_name=person_name, attr=attr);
            existing_member = roster_members_by_id.get(person_id);
            if existing_member is not None:
                if existing_member != roster_member:
                    raise ValueError(
                        f'球队名单中 person_id={person_id} 重复且姓名或 attr 不一致。'
                    );
                continue;
            roster_members_by_id[person_id] = roster_member;

    if not roster_members_by_id:
        raise ValueError('球队名单响应中没有可保存的名单成员。');

    return TeamRoster(members=tuple(roster_members_by_id.values()));
