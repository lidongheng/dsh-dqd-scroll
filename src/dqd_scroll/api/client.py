from __future__ import annotations;

import json;
from urllib.error import HTTPError, URLError;
from urllib.request import Request, urlopen;


def get_json(url: str, timeout_seconds: int, headers: dict[str, str]) -> object:
    # 统一通过 Request 发送配置的请求头，避免 urllib 使用默认的 Python 客户端标识。
    request = Request(url, headers=headers, method='GET');
    try:
        with urlopen(request, timeout=timeout_seconds) as response:
            if response.status != 200:
                raise RuntimeError(f'懂球帝接口返回 HTTP {response.status}: {url}');
            response_body = response.read().decode('utf-8');
    except HTTPError as error:
        raise RuntimeError(f'懂球帝接口返回 HTTP {error.code}: {url}') from error;
    except URLError as error:
        raise RuntimeError(f'懂球帝接口请求失败: {error.reason}') from error;

    try:
        return json.loads(response_body);
    except json.JSONDecodeError as error:
        raise ValueError(f'懂球帝接口响应不是有效 JSON: {url}') from error;
