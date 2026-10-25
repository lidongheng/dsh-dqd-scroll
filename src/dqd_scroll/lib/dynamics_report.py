from __future__ import annotations;

from datetime import datetime;

from ..models import TeamDynamic, TeamDynamicsFetch;


def format_team_dynamics_report(
    team_name: str,
    interests: tuple[str, ...],
    selected_dynamics: tuple[TeamDynamic, ...],
    fetch_result: TeamDynamicsFetch,
    since: datetime,
    until: datetime,
) -> str:
    # 动态只进入用户要求的 Markdown 日报，不进入数据库或其他原始响应文件。
    if not team_name.strip():
        raise ValueError('team_name 必须是非空字符串。');
    if not interests:
        raise ValueError('日报兴趣列表不能为空。');
    if since >= until:
        raise ValueError('日报开始时间必须早于结束时间。');

    lines = [
        f'# {team_name}命中兴趣的动态',
        '',
        f'- 生成时间：{until.isoformat(sep=" ")}',
        f'- 动态时间范围：{since.isoformat(sep=" ")} 至 {until.isoformat(sep=" ")}（起止均包含）',
        f'- 兴趣筛选：{"、".join(interests)}（任一兴趣词命中）',
        f'- 分页结果：请求 {fetch_result.page_count} 页；{_fetch_status(fetch_result)}',
        f'- 命中动态：{len(selected_dynamics)} 条',
        '',
    ];
    if not selected_dynamics:
        lines.append('所选时间范围内没有命中已配置兴趣的动态。');
        return '\n'.join(lines);

    for dynamic in selected_dynamics:
        title = _markdown_text(dynamic.title);
        lines.extend(
            [
                f'## {dynamic.feed_time:%Y-%m-%d %H:%M} · {title}',
                '',
                f'- 命中兴趣：{"、".join(dynamic.matched_interests)}',
            ]
        );
        if dynamic.link is not None:
            lines.append(f'- 原动态：[懂球帝]({_markdown_link(dynamic.link)})');
        lines.extend(['', _markdown_text(dynamic.content), '']);

    return '\n'.join(lines).rstrip();


def format_all_team_dynamics_report(
    team_name: str,
    dynamics: tuple[TeamDynamic, ...],
    fetch_result: TeamDynamicsFetch,
    since: datetime,
    until: datetime,
) -> str:
    # 此报告保留所选时间范围内的全部动态，不经过兴趣词筛选。
    if not team_name.strip():
        raise ValueError('team_name 必须是非空字符串。');
    if since >= until:
        raise ValueError('日报开始时间必须早于结束时间。');

    lines = [
        f'# {team_name}全部动态',
        '',
        f'- 生成时间：{until.isoformat(sep=" ")}',
        f'- 动态时间范围：{since.isoformat(sep=" ")} 至 {until.isoformat(sep=" ")}（起止均包含）',
        f'- 分页结果：请求 {fetch_result.page_count} 页；{_fetch_status(fetch_result)}',
        f'- 抓取动态：{len(dynamics)} 条',
        '',
    ];
    if not dynamics:
        lines.append('所选时间范围内没有抓取到动态。');
        return '\n'.join(lines);

    for dynamic in dynamics:
        title = _markdown_text(dynamic.title);
        lines.extend(
            [
                f'## {dynamic.feed_time:%Y-%m-%d %H:%M} · {title}',
                '',
            ]
        );
        if dynamic.link is not None:
            lines.append(f'- 原动态：[懂球帝]({_markdown_link(dynamic.link)})');
        lines.extend(['', _markdown_text(dynamic.content), '']);

    return '\n'.join(lines).rstrip();


def _fetch_status(fetch_result: TeamDynamicsFetch) -> str:
    if fetch_result.pages_reached_cutoff:
        return '已抓到所选开始时间之前的动态';
    if fetch_result.pages_reached_end:
        return '接口分页已结束';
    return '达到 50 页上限，所选开始时间尚未到达，结果不完整';


def _markdown_text(value: str) -> str:
    return value.replace('\r\n', '\n').replace('\r', '\n').strip();


def _markdown_link(value: str) -> str:
    return value.replace(' ', '%20').replace(')', '%29');
