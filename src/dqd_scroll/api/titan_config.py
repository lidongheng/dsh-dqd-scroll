from __future__ import annotations;


# 首版只接入英超；其他联赛必须显式配置赛程文件，不能根据编号猜测。
LEAGUES = {36: {'file_id': 's36', 'name': '英超'}};
SCHEDULE_URL = 'https://zq.titan007.com/jsData/matchResult/{season}/{file_id}.js?version={version}';
SCHEDULE_REFERER = 'https://zq.titan007.com/cn/League/{season}/{league_id}.html';
DETAIL_URL = 'http://bf.titan007.com/detail/{match_id}cn.htm';
DETAIL_REFERER = 'http://bf.titan007.com/';
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/89.0.4389.82 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8',
    'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
};
REQUEST_TIMEOUT_SECONDS = 30;
SCRIPT_HEADERS = {
    **HEADERS,
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Accept': '*/*',
    'Sec-Fetch-Dest': 'script',
    'Sec-Fetch-Mode': 'no-cors',
    'Sec-Fetch-Site': 'same-origin',
};
