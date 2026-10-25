from __future__ import annotations;

import ssl;
from urllib.error import HTTPError, URLError;
from urllib.parse import urlsplit;
from urllib.request import Request, urlopen;

from .titan_config import HEADERS, REQUEST_TIMEOUT_SECONDS, SCRIPT_HEADERS;


def fetch_text(url: str, referer: str) -> str:
    headers = SCRIPT_HEADERS if '/jsData/' in urlsplit(url).path else HEADERS;
    request = Request(url, headers={**headers, 'Referer': referer}, method='GET');
    # 原项目显式限制 TLS 1.2；使用默认 TLS 协商时球探会直接断开连接。
    context = ssl.create_default_context();
    context.maximum_version = ssl.TLSVersion.TLSv1_2;
    try:
        with urlopen(request, context=context, timeout=REQUEST_TIMEOUT_SECONDS) as response:
            if response.status != 200:
                raise RuntimeError(f'球探接口 HTTP {response.status}: {url}');
            return response.read().decode('utf-8-sig');
    except (HTTPError, URLError, OSError) as error:
        raise RuntimeError(f'球探请求失败 {url}: {error}') from error;
