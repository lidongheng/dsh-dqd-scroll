from __future__ import annotations;

from datetime import datetime;
from urllib.parse import parse_qs, urlencode, urlsplit;
from zoneinfo import ZoneInfo;

from .client import get_json;
from ..lib.team_dynamics import parse_team_dynamic;
from ..models import TeamDynamic, TeamDynamicsFetch;


DYNAMICS_ENDPOINT = 'https://api.dongqiudi.com/v3/archive/app/channel/feeds';
MAX_DYNAMICS_PAGES = 50;
REQUEST_TIMEOUT_SECONDS = 30;


def fetch_team_dynamics(team_id: int, since: datetime, until: datetime) -> TeamDynamicsFetch:
    # 每页只在内存处理；只保留时间范围内的动态供日报格式化。
    current_url = _first_page_url(team_id);
    seen_urls = set();
    dynamics_by_id = {};
    page_count = 0;
    pages_reached_cutoff = False;
    pages_reached_end = False;

    while page_count < MAX_DYNAMICS_PAGES:
        if current_url in seen_urls:
            raise ValueError(f'动态分页 next URL 重复，已停止以防无限循环: {current_url}');
        seen_urls.add(current_url);
        _validate_page_url(current_url, team_id);
        response_body = get_json(current_url, REQUEST_TIMEOUT_SECONDS);
        page_data = _parse_page_response(response_body);
        page_count += 1;

        page_dynamics = [];
        for raw_dynamic in page_data['articles']:
            dynamic = parse_team_dynamic(raw_dynamic);
            page_dynamics.append(dynamic);
            if since <= dynamic.feed_time <= until:
                previous_dynamic = dynamics_by_id.get(dynamic.dynamic_id);
                if previous_dynamic is not None and previous_dynamic != dynamic:
                    raise ValueError(f'动态 ID {dynamic.dynamic_id} 在分页响应中内容冲突。');
                dynamics_by_id[dynamic.dynamic_id] = dynamic;

        next_url = page_data['next'];
        if not next_url:
            pages_reached_end = True;
            break;
        if next_url in seen_urls:
            raise ValueError(f'动态分页 next URL 重复，已停止以防无限循环: {next_url}');
        _validate_page_url(next_url, team_id);
        next_after = _next_after_timestamp(next_url);
        page_is_before_cutoff = bool(page_dynamics) and max(dynamic.feed_time for dynamic in page_dynamics) < since;
        if next_after < _to_unix_timestamp(since) and page_is_before_cutoff:
            pages_reached_cutoff = True;
            break;
        current_url = next_url;

    ordered_dynamics = tuple(
        sorted(dynamics_by_id.values(), key=lambda dynamic: (dynamic.feed_time, dynamic.dynamic_id), reverse=True)
    );
    return TeamDynamicsFetch(
        dynamics=ordered_dynamics,
        page_count=page_count,
        pages_reached_cutoff=pages_reached_cutoff,
        pages_reached_end=pages_reached_end,
    );


def _first_page_url(team_id: int) -> str:
    query = urlencode(
        (
            ('id', str(team_id)),
            ('type', 'team'),
            ('version', '444'),
            ('platform', 'android'),
            ('isDarkMode', '0'),
            ('android-channel', 'website'),
            ('isTeenager', '0'),
            ('device_glb_type', '1'),
        )
    );
    return f'{DYNAMICS_ENDPOINT}?{query}';


def _validate_page_url(url: str, team_id: int) -> None:
    parsed_url = urlsplit(url);
    if parsed_url.scheme != 'https' or parsed_url.netloc != 'api.dongqiudi.com':
        raise ValueError(f'动态分页 next URL 不属于懂球帝 API: {url}');
    if parsed_url.path != urlsplit(DYNAMICS_ENDPOINT).path:
        raise ValueError(f'动态分页 next URL 路径与已核验接口不符: {url}');
    query = parse_qs(parsed_url.query, strict_parsing=True);
    if query.get('id') != [str(team_id)] or query.get('type') != ['team']:
        raise ValueError(f'动态分页 next URL 的球队或类型与配置不符: {url}');


def _next_after_timestamp(url: str) -> int:
    query = parse_qs(urlsplit(url).query, strict_parsing=True);
    after_values = query.get('after');
    if after_values is None or len(after_values) != 1:
        raise ValueError(f'动态分页 next URL 缺少唯一的 after 时间戳: {url}');
    try:
        after_timestamp = int(after_values[0]);
    except ValueError as error:
        raise ValueError(f'动态分页 next URL 的 after 必须是 Unix 时间戳: {url}') from error;
    if after_timestamp <= 0:
        raise ValueError(f'动态分页 next URL 的 after 必须是正整数: {url}');
    return after_timestamp;


def _to_unix_timestamp(value: datetime) -> int:
    if value.tzinfo is not None:
        raise ValueError('动态日报时间范围必须是上海本地时间，不要附带时区偏移。');
    return int(value.replace(tzinfo=ZoneInfo('Asia/Shanghai')).timestamp());


def _parse_page_response(response_body: object) -> dict[str, object]:
    if not isinstance(response_body, dict):
        raise ValueError('动态接口响应根节点必须是对象。');
    code = response_body.get('code');
    if isinstance(code, bool) or not isinstance(code, int):
        raise ValueError('动态接口响应 code 必须是整数。');
    if code != 0:
        message = response_body.get('message');
        raise RuntimeError(f'懂球帝动态接口业务错误 code={code}, message={message}');

    data = response_body.get('data');
    if not isinstance(data, dict):
        raise ValueError('动态接口响应 data 必须是对象。');
    if 'next' not in data or not isinstance(data['next'], str):
        raise ValueError('动态接口响应 data.next 必须是字符串。');
    if 'articles' not in data or not isinstance(data['articles'], list):
        raise ValueError('动态接口响应 data.articles 必须是列表。');
    return {'next': data['next'], 'articles': data['articles']};
