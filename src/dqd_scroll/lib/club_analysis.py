from __future__ import annotations;

import json;
import logging;
import os;
import re;
from collections import Counter;
from datetime import datetime;
from pathlib import Path;
from tempfile import NamedTemporaryFile;
from time import sleep;
from zoneinfo import ZoneInfo;

from ..api.titan_api import fetch_text;
from ..api.titan_config import DETAIL_REFERER, DETAIL_URL, LEAGUES, SCHEDULE_REFERER, SCHEDULE_URL;
from ..repository import Repository;
from .club_lineup import FORMATIONS, POSITION_GROUP, recommend_lineup;
from .club_matches import ClubMatch, MatchLineup, parse_match_lineup, parse_schedule;


logger = logging.getLogger(__name__);


def roster_by_number(roster: list[dict]) -> dict[str, dict]:
    by_number = {};
    for player in roster:
        number = player['shirt_number'];
        if not isinstance(number, str) or not number.isascii() or not number.isdecimal():
            raise ValueError(f'球员 {player["person_name"]} 球衣号码无效。');
        number = str(int(number));
        if number in by_number:
            raise ValueError(f'当前名单球衣号码重复: {number}');
        for field in ('person_name', 'nationality', 'age', 'social_status'):
            if not isinstance(player[field], str) or not player[field].strip():
                raise ValueError(f'球员 {player["person_name"]} 缺少 {field}，请先同步名单及个人资料。');
        for field in ('height', 'weight'):
            if isinstance(player[field], bool) or not isinstance(player[field], int) or player[field] <= 0:
                raise ValueError(f'球员 {player["person_name"]} 缺少有效 {field}，请先同步个人资料。');
        by_number[number] = player;
    return by_number;


def aggregate_matches(roster: list[dict], matches: list[tuple[ClubMatch, MatchLineup]]) -> dict:
    by_number = roster_by_number(roster);
    totals = {};
    formations = Counter();
    unmatched = [];
    for match, lineup in matches:
        formations[lineup.formation] += 1;
        for source in lineup.players:
            if source.caps == 0:
                continue;
            if source.number not in by_number:
                unmatched.append((match.match_id, source.number, source.name));
                continue;
            member = by_number[source.number];
            person_id = member['person_id'];
            if person_id not in totals:
                totals[person_id] = {
                    **member, 'caps': 0, 'lineups': 0, 'goals': 0, 'assists': 0,
                    'positions': Counter(), 'alternative_names': [],
                };
            player = totals[person_id];
            player['caps'] += source.caps;
            player['lineups'] += source.lineups;
            player['goals'] += source.goals;
            player['assists'] += source.assists;
            if source.position is not None:
                player['positions'][source.position] += 1;
            if source.name != member['person_name'] and source.name not in player['alternative_names']:
                player['alternative_names'].append(source.name);
    # JS 的数字属性键按球衣号枚举，保留这一顺序以维持同分时的选择结果。
    players = sorted(totals.values(), key=lambda player: int(player['shirt_number']));
    most_used = None;
    if formations:
        most_used = max(formations, key=formations.__getitem__);
    lineup = [];
    if most_used in FORMATIONS:
        lineup = recommend_lineup(players, most_used);
    return {'players': players, 'formations': formations, 'most_used': most_used,
            'recommended': lineup, 'unmatched': unmatched};


def _cell(value: object) -> str:
    return str(value).replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;').replace('|', '&#124;').replace('\n', ' ').replace('\r', ' ');


def format_club_report(team_name: str, season: str, before_round: int | None,
                       matches: list[tuple[ClubMatch, MatchLineup]], analysis: dict) -> str:
    rounds = sorted({match.round for match, _ in matches});
    scope = '当前赛季全部已完赛联赛' if before_round is None else f'第 {before_round} 轮之前的已完赛联赛';
    lines = [f'# {_cell(team_name)} 国内联赛出场分析', '', f'赛季：{season}；范围：{scope}',
             f'分析轮次：{", ".join(map(str, rounds))}；比赛数量：{len(matches)}',
             f'比赛编号：{", ".join(str(match.match_id) for match, _ in matches)}',
             '球员范围：当前名单中实际上场的球员，按唯一球衣号关联；括号内为球探姓名。', '', '## 球员统计', '',
             '| 球员 | 出场 | 首发 | 进球 | 助攻 | 位置出场次数 | 国籍 | 年龄 | 身高(cm) | 体重(kg) | 身价(欧) |',
             '| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |'];
    for player in sorted(analysis['players'], key=lambda player: (-player['lineups'], -player['caps'])):
        name = f'{player["shirt_number"]}-{player["person_name"]}';
        if player['alternative_names']:
            name += f'({"、".join(player["alternative_names"])})';
        positions = dict(sorted(player['positions'].items(), key=lambda item: -item[1]));
        cells = (name, player['caps'], player['lineups'], player['goals'], player['assists'],
                 json.dumps(positions, ensure_ascii=False), player['nationality'], player['age'],
                 player['height'], player['weight'], player['social_status']);
        lines.append('| ' + ' | '.join(_cell(value) for value in cells) + ' |');
    lines.extend(['', '## 阵型与推荐首发', '']);
    lines.append('阵型使用次数：' + '，'.join(f'{formation}：{count}' for formation, count in analysis['formations'].most_common()));
    if analysis['most_used'] is None:
        lines.append('无法确定最常用阵型，无法生成推荐首发。');
    else:
        lines.append(f'最常用阵型：{analysis["most_used"]}');
        if analysis['recommended']:
            groups = [];
            for group in ('GK', 'DF', 'MF', 'FW'):
                names = [f'{player["shirt_number"]}-{player["person_name"]}' for player in analysis['recommended']
                         if POSITION_GROUP[player['recommended_position']] == group];
                groups.append('，'.join(names));
            lines.append('推荐首发阵容：' + _cell('/'.join(groups)));
        else:
            lines.append('无法生成完整推荐首发：阵型未配置或有效位置数据不足。');
    unknown = [formation for formation in analysis['formations'] if formation not in FORMATIONS];
    if unknown:
        lines.append('未配置阵型：' + '，'.join(unknown) + '；对应比赛不推断球员位置。');
    if analysis['unmatched']:
        lines.extend(['', '## 未匹配人员（已排除）', '']);
        for match_id, number, name in analysis['unmatched']:
            lines.append(f'- 比赛 {match_id}：{number}-{_cell(name)}');
    return '\n'.join(lines) + '\n';


def generate_club_report(repository: Repository, team_id: int, before_round: int | None, output_dir: Path) -> tuple[Path, str]:
    team = repository.get_team(team_id);
    if before_round is not None and (isinstance(before_round, bool) or before_round <= 0):
        raise ValueError('截止轮次必须是正整数。');
    season = repository.get_current_season(team_id);
    if team.league_serial not in LEAGUES:
        raise ValueError(f'尚未配置联赛 {team.league_serial} 的球探采集，首版支持英超。');
    roster = repository.get_club_players(team_id);
    roster_by_number(roster);
    config = LEAGUES[team.league_serial];
    url_season = season.replace('/', '-');
    version = datetime.now(ZoneInfo('Asia/Shanghai')).strftime('%Y%m%d%H');
    schedule_url = SCHEDULE_URL.format(season=url_season, file_id=config['file_id'], version=version);
    referer = SCHEDULE_REFERER.format(season=url_season, league_id=team.league_serial);
    schedule = parse_schedule(fetch_text(schedule_url, referer), team.qiutan_serial, team.league_serial, season, before_round);
    if not schedule:
        raise ValueError('没有符合范围的已完赛联赛比赛，不生成报告。');
    parsed = [];
    failures = [];
    for index, match in enumerate(schedule, start=1):
        # 赛程及每场技术统计均串行；重试另按 1、2、4 秒退避。
        sleep(1);
        logger.info('分析比赛 %s/%s：%s（第 %s 轮）', index, len(schedule), match.match_id, match.round);
        for attempt in range(4):
            try:
                html = fetch_text(DETAIL_URL.format(match_id=match.match_id), DETAIL_REFERER);
                parsed.append((match, parse_match_lineup(html, match, team.qiutan_serial)));
                break;
            except (RuntimeError, ValueError, OSError) as error:
                logger.info('比赛 %s 第 %s 次请求或解析失败：%s', match.match_id, attempt + 1, error);
                if attempt == 3:
                    failures.append(f'{match.match_id}: {error}');
                else:
                    sleep(2 ** attempt);
    if failures:
        raise RuntimeError('分析不完整，保留上次成功报告。失败比赛：' + '；'.join(failures));
    # 抓取耗时较长，输出前确认所用赛季和名单资料没有被其他命令修改。
    if repository.get_current_season(team_id) != season or repository.get_club_players(team_id) != roster:
        raise RuntimeError('分析期间赛季或球员资料已变化，拒绝发布过期报告。');
    analysis = aggregate_matches(roster, parsed);
    markdown = format_club_report(team.dqd_name, season, before_round, parsed, analysis);
    safe_team_name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', '_', team.dqd_name);
    directory = output_dir.resolve() / url_season / safe_team_name;
    directory.mkdir(parents=True, exist_ok=True);
    filename = 'all.md' if before_round is None else f'before-round-{before_round}.md';
    output_path = directory / filename;
    # 同目录临时文件替换，写入失败时保留已有成功报告。
    with NamedTemporaryFile(mode='w', encoding='utf-8', dir=directory, delete=False, suffix='.tmp') as temporary:
        temporary_path = Path(temporary.name);
        try:
            temporary.write(markdown);
        except BaseException:
            temporary.close();
            temporary_path.unlink();
            raise;
    try:
        os.replace(temporary_path, output_path);
    finally:
        temporary_path.unlink(missing_ok=True);
    return output_path, markdown;
