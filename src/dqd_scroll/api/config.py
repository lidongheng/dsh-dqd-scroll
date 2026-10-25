from __future__ import annotations;


# 与 playerListCrawler.js 保持一致，所有懂球帝请求共用同一个客户端标识。
DQD_USER_AGENT = (
    'Mozilla/5.0 (Linux; Android 14; 2509FPN0BC Build/UQ1A.240205.08311809; wv) '
    'AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/146.0.7680.119 '
    'Mobile Safari/537.36 Package/com.dongqiudi.news News/444 Android/14 '
    'NewsApp/444 SDK/34 VERSION/8.7.4 dongqiudiClientApp HM/false privacy/64'
);
DQD_SPORT_HEADERS = {
    'Accept': 'application/json',
    'User-Agent': DQD_USER_AGENT,
};
DQD_APP_HEADERS = {
    'Accept': 'application/json, text/plain, */*',
    'User-Agent': DQD_USER_AGENT,
    'sec-ch-ua-platform': '"Android"',
    'sec-ch-ua': '"Chromium";v="146", "Not-A.Brand";v="24", "Android WebView";v="146"',
    'Origin': 'https://topic.dongqiudi.com',
    'X-Requested-With': 'com.dongqiudi.news',
    'Sec-Fetch-Site': 'same-site',
    'Sec-Fetch-Mode': 'cors',
    'Sec-Fetch-Dest': 'empty',
    'Accept-Language': 'zh-CN,zh;q=0.9,en-US;q=0.8,en;q=0.7',
};
DQD_ROSTER_REFERER = 'https://topic.dongqiudi.com/webapp/team_player/team_player.html?id={team_id}&from=wxmp';
DQD_STATISTICS_REFERER = 'https://topic.dongqiudi.com/webapp/career-stats/career-stats.html?id={person_id}';
# 当前流程不请求个人资料中的 ability_url，能力值请求明确使用专题页首页。
DQD_ABILITY_REFERER = 'https://topic.dongqiudi.com/';
DQD_DYNAMICS_REFERER = 'https://topic.dongqiudi.com/';
DQD_PROFILE_REFERER = 'https://topic.dongqiudi.com/';
