import argparse;
import json;
from calendar import monthrange;
from datetime import date, datetime, timedelta;
from pathlib import Path;
from zoneinfo import ZoneInfo;

from .config import load_config;
from .lib.report import format_daily_schedule_report;
from .lib.team_schedule import format_team_schedule_report;
from .repository import Repository;
from .workflow import build_team_dynamics_reports, save_team_roster_response, save_team_schedule_response;


def show_status() -> int:
    print('球队动态只读日报已接入；名单、赛程和球员接口的实时 HTTP 契约仍待核验。');
    return 0;


def initialize_database(config_path: Path, team_data_path: Path | None = None) -> int:
    # CLI 从 TOML 读取数据库位置、从 JSON 读取球队映射，不在代码里猜默认值。
    config = load_config(config_path, team_data_path);
    repository = Repository(config.database_path);
    repository.initialize(config.teams);
    print(f'SQLite 已初始化: {config.database_path}');
    print(f'写入球队映射: {len(config.teams)} 支');
    return 0;


def import_team_roster_response(database_path: Path, dqd_team_id: int, response_path: Path) -> int:
    # 这个命令离线读取已保存的响应样本，不会发送网络请求。
    repository = _repository_for_existing_database(database_path);
    team = repository.get_team(dqd_team_id);

    resolved_response_path = response_path.resolve();
    if not resolved_response_path.is_file():
        raise FileNotFoundError(f'响应文件不存在: {resolved_response_path}');
    response_body = json.loads(resolved_response_path.read_text(encoding='utf-8'));

    saved_count = save_team_roster_response(repository, dqd_team_id, response_body);
    print(f'从响应文件刷新人员姓名、球衣号码、英文名和 attr，并替换球队名单: {saved_count} 条');
    print(f'球队: {team.dqd_name}（懂球帝 ID {dqd_team_id}）');
    return 0;


def import_team_schedule_response(
    database_path: Path,
    dqd_team_id: int,
    response_path: Path,
    request_url: str,
) -> int:
    # 这个命令离线导入接口响应样本，不会发送网络请求。
    repository = _repository_for_existing_database(database_path);
    team = repository.get_team(dqd_team_id);
    resolved_response_path = response_path.resolve();
    if not resolved_response_path.is_file():
        raise FileNotFoundError(f'响应文件不存在: {resolved_response_path}');
    response_body = json.loads(resolved_response_path.read_text(encoding='utf-8'));

    saved_count = save_team_schedule_response(
        repository,
        dqd_team_id,
        team.league_serial,
        response_body,
        request_url,
    );
    print(f'清洗、去重并写入最新赛季赛程: {saved_count} 场');
    print(f'球队: {team.dqd_name}（懂球帝 ID {dqd_team_id}）');
    print(f'联赛: {team.match_league_name}（league_serial={team.league_serial}）');
    print('赛季: 取自响应 season_list 中唯一标记为 current 的项目');
    return 0;


def show_team_schedule_report(database_path: Path, dqd_team_id: int) -> int:
    # 报告只读取 SQLite 中当前联赛赛季的记录，不访问网络也不读取旧赛季。
    repository = _repository_for_existing_database(database_path);
    team = repository.get_team(dqd_team_id);
    schedule = repository.get_team_schedule(dqd_team_id);
    print(format_team_schedule_report(team.dqd_name, schedule));
    return 0;


def generate_daily_report(
    database_path: Path,
    dqd_team_id: int,
    report_date: date | None,
) -> int:
    # 日报从当前赛季的 SQLite 赛程生成，不发起接口请求，也不修改数据库。
    repository = _repository_for_existing_database(database_path);
    team = repository.get_team(dqd_team_id);
    if report_date is None:
        report_date = datetime.now(ZoneInfo('Asia/Shanghai')).date();
    period_end = _next_calendar_month(report_date);
    schedule = repository.get_team_schedule(dqd_team_id);
    report_markdown = format_daily_schedule_report(team.dqd_name, schedule, report_date, period_end);

    report_path = Path.cwd() / 'out' / f'{report_date.isoformat()}.md';
    report_path.parent.mkdir(parents=True, exist_ok=True);
    report_path.write_text(report_markdown + '\n', encoding='utf-8');
    print(f'日报已生成: {report_path}');
    print(f'球队: {team.dqd_name}（懂球帝 ID {dqd_team_id}）');
    print(f'赛程范围: {report_date.isoformat()} 至 {period_end.isoformat()}（结束日不含）');
    return 0;


def generate_dynamics_report(
    config_path: Path,
    since: datetime | None,
    until: datetime | None,
    team_data_path: Path | None = None,
) -> int:
    # 默认生成上海时区当前时刻往前 24 小时的报告；手动范围按传入值执行。
    config = load_config(config_path, team_data_path);
    if config.dynamics is None:
        raise ValueError('config.toml 缺少 dynamics 配置表。');
    if not config.dynamics.team_names:
        raise ValueError('请先在 config.toml 的 dynamics.team_names 中配置关注球队。');
    if not config.dynamics.interests:
        raise ValueError('请先在 config.toml 的 dynamics.interests 中配置关注内容。');
    if (since is None) != (until is None):
        raise ValueError('手动选择时间范围时，--since 和 --until 必须同时提供。');
    if since is None and until is None:
        until = datetime.now(ZoneInfo('Asia/Shanghai')).replace(tzinfo=None, microsecond=0);
        since = until - timedelta(hours=24);
    if since.tzinfo is not None or until.tzinfo is not None:
        raise ValueError('--since 和 --until 请使用上海本地时间，不要附带时区偏移。');
    if since >= until:
        raise ValueError('--since 必须早于 --until。');

    # load_config 已按懂球帝名称验证映射；这里用同一映射逐队抓取。
    teams_by_name = {team.dqd_name: team for team in config.teams};
    selected_teams = [teams_by_name[team_name] for team_name in config.dynamics.team_names];
    report_date = until.date().isoformat();
    report_directory = config_path.resolve().parent / 'out' / 'dynamics' / report_date;
    report_directory.mkdir(parents=True, exist_ok=True);
    print(f'时间范围: {since.isoformat(sep=" ")} 至 {until.isoformat(sep=" ")}');
    for team in selected_teams:
        all_report_markdown, interests_report_markdown, fetch_result = build_team_dynamics_reports(
            team.dqd_name,
            team.dqd_id,
            config.dynamics.interests,
            since,
            until,
        );
        report_team_name = _report_file_team_name(team.dqd_name);
        all_report_path = report_directory / f'{report_team_name}-all.md';
        interests_report_path = report_directory / f'{report_team_name}-interests.md';
        all_report_path.write_text(all_report_markdown + '\n', encoding='utf-8');
        interests_report_path.write_text(interests_report_markdown + '\n', encoding='utf-8');
        print(f'球队: {team.dqd_name}（懂球帝 ID {team.dqd_id}）');
        print(f'全部动态日报已生成: {all_report_path}');
        print(f'兴趣命中日报已生成: {interests_report_path}');
        print(f'已请求分页: {fetch_result.page_count} 页（上限 50 页）');
    return 0;


def _report_file_team_name(team_name: str) -> str:
    # 用懂球帝名称标识文件，同时替换 Windows 文件名不允许的字符。
    invalid_filename_characters = '<>:"/\\|?*';
    return ''.join('_' if character in invalid_filename_characters or ord(character) < 32 else character for character in team_name);


def _next_calendar_month(value: date) -> date:
    # 以日历月计算结束日期；例如 1 月 31 日对应 2 月最后一天。
    if value.month == 12:
        next_year = value.year + 1;
        next_month = 1;
    else:
        next_year = value.year;
        next_month = value.month + 1;
    next_month_last_day = monthrange(next_year, next_month)[1];
    next_day = min(value.day, next_month_last_day);
    return date(next_year, next_month, next_day);


def _repository_for_existing_database(database_path: Path) -> Repository:
    # 运行命令必须使用初始化过的 SQLite，避免路径错误时创建空数据库文件。
    resolved_database_path = database_path.resolve();
    if not resolved_database_path.is_file():
        raise FileNotFoundError(
            f'SQLite 数据库不存在: {resolved_database_path}；请先运行 db-init --config config.toml。'
        );
    return Repository(resolved_database_path);


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description='懂球帝只读阅读助手');
    parser.add_argument('--version', action='version', version='dqd-scroll 0.1.1');
    subparsers = parser.add_subparsers(dest='command', required=True);

    status_parser = subparsers.add_parser('status', help='查看项目当前阶段');
    status_parser.set_defaults(handler=show_status);

    database_parser = subparsers.add_parser('db-init', help='按配置文件初始化 SQLite');
    database_parser.add_argument('--config', type=Path, required=True, help='TOML 配置文件路径');
    database_parser.add_argument('--teams', type=Path, help='球队映射 JSON 文件路径');
    database_parser.set_defaults(handler=initialize_database);

    roster_parser = subparsers.add_parser(
        'roster-import',
        help='从响应文件刷新人员姓名、球衣号码、英文名和 attr 并替换球队名单',
    );
    roster_parser.add_argument('--database', type=Path, required=True, help='已初始化的 SQLite 数据库文件路径');
    roster_parser.add_argument('--team-id', type=int, required=True, help='懂球帝球队 ID');
    roster_parser.add_argument('--response-file', type=Path, required=True, help='球队名单 JSON 响应文件');
    roster_parser.set_defaults(handler=import_team_roster_response);

    schedule_import_parser = subparsers.add_parser(
        'schedule-import',
        help='从响应文件清洗、去重并导入球队最新赛季赛程',
    );
    schedule_import_parser.add_argument('--database', type=Path, required=True, help='已初始化的 SQLite 数据库文件路径');
    schedule_import_parser.add_argument('--team-id', type=int, required=True, help='懂球帝球队 ID');
    schedule_import_parser.add_argument('--response-file', type=Path, required=True, help='球队赛程 JSON 响应文件');
    schedule_import_parser.add_argument('--request-url', required=True, help='本次赛程响应对应的实际请求 URL，用于核对 season');
    schedule_import_parser.set_defaults(handler=import_team_schedule_response);

    schedule_report_parser = subparsers.add_parser(
        'schedule-report',
        help='从 SQLite 读取并加工输出球队最新赛季赛程 Markdown',
    );
    schedule_report_parser.add_argument('--database', type=Path, required=True, help='已初始化的 SQLite 数据库文件路径');
    schedule_report_parser.add_argument('--team-id', type=int, required=True, help='懂球帝球队 ID');
    schedule_report_parser.set_defaults(handler=show_team_schedule_report);

    daily_report_parser = subparsers.add_parser(
        'daily-report',
        help='从 SQLite 生成球队未来一个自然月的赛程 Markdown 日报',
    );
    daily_report_parser.add_argument('--database', type=Path, required=True, help='已初始化的 SQLite 数据库文件路径');
    daily_report_parser.add_argument('--team-id', type=int, required=True, help='懂球帝球队 ID');
    daily_report_parser.add_argument(
        '--as-of',
        type=date.fromisoformat,
        help='日报日期 YYYY-MM-DD；省略时使用 Asia/Shanghai 当天日期',
    );
    daily_report_parser.set_defaults(handler=generate_daily_report);

    dynamics_report_parser = subparsers.add_parser(
        'dynamics-report',
        help='读取配置球队动态并按配置兴趣生成 Markdown 日报，不写入 SQLite',
    );
    dynamics_report_parser.add_argument('--config', type=Path, required=True, help='TOML 配置文件路径');
    dynamics_report_parser.add_argument('--teams', type=Path, help='球队映射 JSON 文件路径');
    dynamics_report_parser.add_argument(
        '--since',
        type=datetime.fromisoformat,
        help='选择动态开始时间，ISO 格式，例如 2026-10-25T00:00:00；需与 --until 同时提供',
    );
    dynamics_report_parser.add_argument(
        '--until',
        type=datetime.fromisoformat,
        help='选择动态结束时间，ISO 格式，例如 2026-10-25T21:00:00；需与 --since 同时提供',
    );
    dynamics_report_parser.set_defaults(handler=generate_dynamics_report);
    return parser;


def main() -> int:
    args = build_parser().parse_args();
    if args.command == 'status':
        return args.handler();
    if args.command == 'db-init':
        return args.handler(args.config, args.teams);
    if args.command == 'schedule-report':
        return args.handler(args.database, args.team_id);
    if args.command == 'daily-report':
        return args.handler(args.database, args.team_id, args.as_of);
    if args.command == 'dynamics-report':
        return args.handler(args.config, args.since, args.until, args.teams);
    if args.command == 'schedule-import':
        return args.handler(args.database, args.team_id, args.response_file, args.request_url);
    return args.handler(args.database, args.team_id, args.response_file);
