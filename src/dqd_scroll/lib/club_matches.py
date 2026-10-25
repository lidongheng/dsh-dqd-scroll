from __future__ import annotations;

import re;
from dataclasses import dataclass;

import json5;
from bs4 import BeautifulSoup;

from .club_lineup import FORMATIONS;


@dataclass(frozen=True)
class ClubMatch:
    match_id: int;
    round: int;
    side: str;
    kickoff: str;


@dataclass(frozen=True)
class MatchPlayer:
    number: str;
    name: str;
    position: str | None;
    caps: int;
    lineups: int;
    goals: int;
    assists: int;


@dataclass(frozen=True)
class MatchLineup:
    formation: str;
    players: tuple[MatchPlayer, ...];


def _array_assignment(text: str, start: int) -> list:
    # JS 赛程包含 [a,,b] 稀疏数组；缺位表示源数据缺失，用 JSON null 表达，绝不补成 0。
    # 只扫描一个数组，保留字符串内容，不执行赋值语句或远端代码。
    output = [];
    depth = 0;
    quote = None;
    escaped = False;
    previous = None;
    for char in text[start:]:
        if quote is not None:
            output.append(char);
            if escaped:
                escaped = False;
            elif char == '\\':
                escaped = True;
            elif char == quote:
                quote = None;
                previous = 'value';
            continue;
        if char in ('\'', '"'):
            quote = char;
        elif char == '[':
            depth += 1;
        elif char == ']':
            depth -= 1;
        elif char == ',' and previous in ('[', ','):
            output.append('null');
        output.append(char);
        if not char.isspace():
            previous = char;
        if char == ']' and depth == 0:
            return json5.loads(''.join(output));
    raise ValueError('球探赛程数组未闭合。');


def parse_schedule(text: str, team_serial: str, league_id: int, season: str, before_round: int | None) -> list[ClubMatch]:
    if before_round is not None and (isinstance(before_round, bool) or before_round <= 0):
        raise ValueError('截止轮次必须是正整数。');
    if not re.fullmatch(r'\d{4}/\d{4}', season):
        raise ValueError(f'不支持的赛季格式: {season}');
    # 仅解析赋值后的 JSON5 数组；禁止执行远端 JS。
    league_match = re.search(r'\bvar\s+arrLeague\s*=\s*', text);
    if league_match is None:
        raise ValueError('球探赛程缺少 arrLeague。');
    league = _array_assignment(text, league_match.end());
    if not isinstance(league, list) or len(league) < 5 or league[0] != league_id or league[4] != season.replace('/', '-'):
        raise ValueError('球探赛程联赛或赛季与 SQLite 不一致。');
    matches = [];
    seen = set();
    round_assignments = list(re.finditer(r'\bjh\s*\[\s*[\'\"]R_(\d+)[\'\"]\s*\]\s*=\s*', text));
    if not round_assignments:
        raise ValueError('球探赛程缺少 R_* 轮次。');
    for assignment in round_assignments:
        round_number = int(assignment[1]);
        if before_round is not None and round_number >= before_round:
            continue;
        records = _array_assignment(text, assignment.end());
        if not isinstance(records, list):
            raise ValueError(f'第 {round_number} 轮不是比赛数组。');
        for record in records:
            if not isinstance(record, list) or len(record) < 7:
                raise ValueError(f'第 {round_number} 轮比赛记录不完整。');
            if record[2] != -1 or int(team_serial) not in (record[4], record[5]):
                continue;
            if record[1] != league_id or isinstance(record[0], bool) or not isinstance(record[0], int) or record[0] <= 0:
                raise ValueError('球探比赛编号或赛事编号无效。');
            if record[0] in seen:
                raise ValueError(f'球探比赛编号重复: {record[0]}');
            seen.add(record[0]);
            side = 'home' if record[4] == int(team_serial) else 'guest';
            matches.append(ClubMatch(record[0], round_number, side, record[3]));
    return sorted(matches, key=lambda match: (match.round, match.kickoff, match.match_id));


def parse_match_lineup(html: str, match: ClubMatch, team_serial: str) -> MatchLineup:
    soup = BeautifulSoup(html, 'html.parser');
    team_link = soup.select_one(f'.{match.side} a[href*="/team/"]');
    if team_link is None:
        team_link = soup.select_one(f'.{match.side} a');
    # 页面侧别必须对应目标球探球队，防止错误页面混入累计统计。
    if team_link is None or re.search(rf'/{re.escape(team_serial)}\.html(?:[?#]|$)', str(team_link.get('href'))) is None:
        raise ValueError(f'比赛 {match.match_id} 页面球队与目标球队不一致。');
    formation_node = soup.select_one(f'.content .title .{match.side}N');
    if formation_node is None:
        formation_node = soup.select_one(f'#matchBox2 > .teamNames .{match.side}');
    if formation_node is None:
        raise ValueError(f'比赛 {match.match_id} 缺少阵型。');
    formation = re.sub(r'[^0-9]', '', formation_node.get_text());
    positions = FORMATIONS[formation] if formation in FORMATIONS else None;
    if positions is not None and match.side == 'guest':
        positions = list(reversed(positions));
    starters = soup.select(f'#matchBox2 .plays .{match.side} .playBox .play');
    if len(starters) != 11:
        raise ValueError(f'比赛 {match.match_id} 首发数量为 {len(starters)}，应为 11。');
    bench = soup.select(f'#matchBox2 .backupPlay .{match.side} .play');
    players = [];
    numbers = set();
    for index, node in enumerate(starters + bench):
        starter = index < len(starters);
        if starter:
            number_node = node.select_one('span i');
            if number_node is None:
                number_node = node.select_one('.headicon .num');
        else:
            number_node = node.select_one('.name i');
        name_node = node.select_one('.name');
        if number_node is None or name_node is None:
            raise ValueError(f'比赛 {match.match_id} 球员缺少号码或姓名。');
        number = number_node.get_text(strip=True);
        # 部分青年替补没有球员详情链接，姓名直接放在 .name 文本中；排除号码节点。
        name = ''.join(text for text in name_node.find_all(string=True) if text.parent.name != 'i').strip();
        if not number.isascii() or not number.isdecimal() or not name or str(int(number)) in numbers:
            raise ValueError(f'比赛 {match.match_id} 球员号码重复或字段无效: {number}');
        number = str(int(number));
        numbers.add(number);
        selector = 'div[id^="playerTech_"] img' if starter else '.eventicon img';
        icons = [];
        for image in node.select(selector):
            src = image.get('src');
            if not isinstance(src, str):
                raise ValueError(f'比赛 {match.match_id} 事件图标缺少 src。');
            icons.append(src.rsplit('/', 1)[-1]);
        caps = 1 if starter or '4.png' in icons else 0;
        lineups = 1 if starter else 0;
        position = positions[index] if starter and positions is not None else None;
        players.append(MatchPlayer(number, name, position, caps, lineups,
                                   sum(icon in ('1.png', '7.png', '8.png') for icon in icons), icons.count('12.png')));
    return MatchLineup(formation, tuple(players));
