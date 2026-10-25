from __future__ import annotations;

import tomllib;
from dataclasses import dataclass;
from datetime import datetime;
from pathlib import Path;


@dataclass(frozen=True)
class TeamConfig:
    # dqd_id 是懂球帝球队 ID；qiutan_serial 是球探球队编号；league_serial 等字段描述赛事。
    dqd_id: int;
    dqd_name: str;
    qiutan_name: str;
    qiutan_serial: str;
    league_serial: int;
    league_slug: str;
    match_league_name: str;


@dataclass(frozen=True)
class DynamicsConfig:
    # 动态日报独立于 SQLite；球队名称和兴趣项由用户在 TOML 中显式填写。
    team_names: tuple[str, ...];
    interests: tuple[str, ...];
    daily_run_time: str;
    python_path: Path;


@dataclass(frozen=True)
class ProjectConfig:
    # 项目显式配置球队映射，不从代码默认值或网络响应推断。
    teams: tuple[TeamConfig, ...];
    database_path: Path;
    dynamics: DynamicsConfig | None;


def load_config(config_path: Path) -> ProjectConfig:
    # 先解析配置文件的绝对路径，数据库相对路径就以该文件所在目录为基准。
    resolved_config_path = config_path.resolve();
    if not resolved_config_path.is_file():
        raise FileNotFoundError(f'配置文件不存在: {resolved_config_path}');

    raw_config = tomllib.loads(resolved_config_path.read_text(encoding='utf-8'));
    if 'teams' not in raw_config:
        raise ValueError('config.toml 缺少必填字段: teams');
    raw_teams = raw_config['teams'];
    if not isinstance(raw_teams, list) or not raw_teams:
        raise ValueError('config.toml 的 teams 必须是非空球队列表。');

    teams = [];
    seen_dqd_ids = set();
    required_fields = (
        'dqd_id',
        'dqd_name',
        'qiutan_name',
        'qiutan_serial',
        'league_serial',
        'league_slug',
        'match_league_name',
    );
    for team_index, raw_team in enumerate(raw_teams, start=1):
        if not isinstance(raw_team, dict):
            raise ValueError(f'config.toml 的第 {team_index} 条 teams 记录必须是表。');

        for field_name in required_fields:
            if field_name not in raw_team:
                raise ValueError(f'config.toml 的第 {team_index} 条球队记录缺少字段: {field_name}');

        dqd_id = raw_team['dqd_id'];
        if isinstance(dqd_id, bool) or not isinstance(dqd_id, int) or dqd_id <= 0:
            raise ValueError(f'config.toml 的第 {team_index} 条球队记录 dqd_id 必须是正整数。');
        if dqd_id in seen_dqd_ids:
            raise ValueError(f'config.toml 存在重复的懂球帝球队 ID: {dqd_id}');
        seen_dqd_ids.add(dqd_id);

        league_serial = raw_team['league_serial'];
        if isinstance(league_serial, bool) or not isinstance(league_serial, int) or league_serial <= 0:
            raise ValueError(f'config.toml 的第 {team_index} 条球队记录 league_serial 必须是正整数。');

        team_values = {};
        for field_name in ('dqd_name', 'qiutan_name', 'qiutan_serial', 'league_slug', 'match_league_name'):
            field_value = raw_team[field_name];
            if not isinstance(field_value, str) or not field_value.strip():
                raise ValueError(f'config.toml 的第 {team_index} 条球队记录 {field_name} 必须是非空字符串。');
            team_values[field_name] = field_value;

        teams.append(
            TeamConfig(
                dqd_id=dqd_id,
                dqd_name=team_values['dqd_name'],
                qiutan_name=team_values['qiutan_name'],
                qiutan_serial=team_values['qiutan_serial'],
                league_serial=league_serial,
                league_slug=team_values['league_slug'],
                match_league_name=team_values['match_league_name'],
            )
        );

    if 'database_path' not in raw_config:
        raise ValueError('config.toml 缺少必填字段: database_path');
    database_path_value = raw_config['database_path'];
    if not isinstance(database_path_value, str) or not database_path_value:
        raise ValueError('config.toml 的 database_path 必须是非空路径字符串。');

    database_path = Path(database_path_value);
    if not database_path.is_absolute():
        database_path = resolved_config_path.parent / database_path;

    dynamics = None;
    if 'dynamics' in raw_config:
        raw_dynamics = raw_config['dynamics'];
        if not isinstance(raw_dynamics, dict):
            raise ValueError('config.toml 的 dynamics 必须是表。');
        for field_name in ('team_names', 'interests', 'daily_run_time', 'python_path'):
            if field_name not in raw_dynamics:
                raise ValueError(f'config.toml 的 dynamics 缺少必填字段: {field_name}');

        raw_team_names = raw_dynamics['team_names'];
        if not isinstance(raw_team_names, list) or not raw_team_names:
            raise ValueError('config.toml 的 dynamics.team_names 必须是非空球队名称列表。');
        team_names = [];
        seen_team_names = set();
        for team_index, team_name in enumerate(raw_team_names, start=1):
            if not isinstance(team_name, str) or not team_name.strip():
                raise ValueError(f'config.toml 的 dynamics.team_names 第 {team_index} 项必须是非空字符串。');
            normalized_team_name = team_name.strip();
            if normalized_team_name in seen_team_names:
                raise ValueError(f'config.toml 的 dynamics.team_names 存在重复球队: {normalized_team_name}');
            # 只从 teams 中的懂球帝名称解析球队映射，不接受猜测或手动补 ID。
            matching_teams = [team for team in teams if team.dqd_name == normalized_team_name];
            if not matching_teams:
                raise ValueError(
                    f'config.toml 的 dynamics.team_names 找不到懂球帝球队名称: {normalized_team_name}；'
                    '请填写 teams 中的 dqd_name。'
                );
            if len(matching_teams) != 1:
                raise ValueError(f'config.toml 的 teams 中 dqd_name 不唯一: {normalized_team_name}');
            seen_team_names.add(normalized_team_name);
            team_names.append(normalized_team_name);

        raw_interests = raw_dynamics['interests'];
        if not isinstance(raw_interests, list):
            raise ValueError('config.toml 的 dynamics.interests 必须是字符串列表。');
        interests = [];
        for interest_index, interest in enumerate(raw_interests, start=1):
            if not isinstance(interest, str) or not interest.strip():
                raise ValueError(f'config.toml 的 dynamics.interests 第 {interest_index} 项必须是非空字符串。');
            interests.append(interest.strip());

        daily_run_time = raw_dynamics['daily_run_time'];
        if not isinstance(daily_run_time, str):
            raise ValueError('config.toml 的 dynamics.daily_run_time 必须是 HH:MM 字符串。');
        try:
            datetime.strptime(daily_run_time, '%H:%M');
        except ValueError as error:
            raise ValueError('config.toml 的 dynamics.daily_run_time 必须使用 HH:MM 格式。') from error;

        python_path_value = raw_dynamics['python_path'];
        if not isinstance(python_path_value, str) or not python_path_value.strip():
            raise ValueError('config.toml 的 dynamics.python_path 必须是非空 Python 可执行文件路径。');
        python_path = Path(python_path_value);
        if not python_path.is_absolute():
            python_path = resolved_config_path.parent / python_path;

        dynamics = DynamicsConfig(
            team_names=tuple(team_names),
            interests=tuple(interests),
            daily_run_time=daily_run_time,
            python_path=python_path.resolve(),
        );
    return ProjectConfig(teams=tuple(teams), database_path=database_path.resolve(), dynamics=dynamics);
