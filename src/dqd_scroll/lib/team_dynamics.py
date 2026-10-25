from __future__ import annotations;

from datetime import datetime;
from zoneinfo import ZoneInfo;

from ..models import TeamDynamic;


def parse_team_dynamic(raw_dynamic: object) -> TeamDynamic:
    # show_time 与分页 next.after 对应，作为动态在信息流中的展示时间和截止时间依据。
    if not isinstance(raw_dynamic, dict):
        raise ValueError('data.articles 中的动态记录必须是对象。');

    dynamic_id = raw_dynamic.get('id');
    if isinstance(dynamic_id, bool) or not isinstance(dynamic_id, int) or dynamic_id <= 0:
        raise ValueError('动态 id 必须是正整数。');

    title = raw_dynamic.get('title');
    if not isinstance(title, str):
        raise ValueError(f'动态 {dynamic_id} 的 title 必须是字符串。');

    show_time = raw_dynamic.get('show_time');
    if isinstance(show_time, bool) or not isinstance(show_time, int) or show_time <= 0:
        raise ValueError(f'动态 {dynamic_id} 的 show_time 必须是正整数 Unix 时间戳。');
    feed_time = datetime.fromtimestamp(show_time, ZoneInfo('Asia/Shanghai')).replace(tzinfo=None);

    content_parts = [title];
    description = raw_dynamic.get('description');
    if description is not None:
        if not isinstance(description, str):
            raise ValueError(f'动态 {dynamic_id} 的 description 必须是字符串。');
        if description and description != title:
            content_parts.append(description);

    talk = raw_dynamic.get('talk');
    if talk is not None:
        if not isinstance(talk, dict):
            raise ValueError(f'动态 {dynamic_id} 的 talk 必须是对象。');
        talk_content = talk.get('content');
        if talk_content is not None:
            if not isinstance(talk_content, str):
                raise ValueError(f'动态 {dynamic_id} 的 talk.content 必须是字符串。');
            if talk_content and talk_content not in content_parts:
                content_parts.append(talk_content);

    link = raw_dynamic.get('share');
    if link is not None and not isinstance(link, str):
        raise ValueError(f'动态 {dynamic_id} 的 share 必须是字符串。');

    return TeamDynamic(
        dynamic_id=dynamic_id,
        feed_time=feed_time,
        title=title,
        content='\n'.join(content_parts),
        link=link,
        matched_interests=(),
    );


def select_interesting_dynamics(
    dynamics: tuple[TeamDynamic, ...],
    interests: tuple[str, ...],
) -> tuple[TeamDynamic, ...]:
    # 以用户配置兴趣词的子串命中筛选；任意一个兴趣词匹配即进入日报。
    if not interests:
        raise ValueError('config.toml 的 dynamics.interests 不能为空，请填写你关注的内容。');
    selected = [];
    for dynamic in dynamics:
        normalized_content = dynamic.content.casefold();
        matched_interests = tuple(interest for interest in interests if interest.casefold() in normalized_content);
        if matched_interests:
            selected.append(
                TeamDynamic(
                    dynamic_id=dynamic.dynamic_id,
                    feed_time=dynamic.feed_time,
                    title=dynamic.title,
                    content=dynamic.content,
                    link=dynamic.link,
                    matched_interests=matched_interests,
                )
            );
    return tuple(selected);
