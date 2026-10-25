from __future__ import annotations;

import sqlite3;
from collections.abc import Iterable, Iterator;
from contextlib import closing, contextmanager;
from pathlib import Path;

from .config import TeamConfig;
from .models import PlayerAbility, PlayerProfile, PlayerStatistics, RosterMember, Team, TeamSchedule, TeamScheduleMatch;


PLAYER_STATISTIC_FIELDS = ('caps', 'lineups', 'goals', 'assists', 'rescues');


class Repository:
    def __init__(self, database_path: Path) -> None:
        if not database_path.is_absolute():
            raise ValueError('database_path must be an absolute path.');
        self._database_path = database_path;

    def initialize(self, teams: Iterable[TeamConfig]) -> None:
        # 初始化前验证全部配置，避免无效或重复的球队记录进入数据库。
        team_records = list(teams);
        if not team_records:
            raise ValueError('teams cannot be empty.');
        team_ids = [team.dqd_id for team in team_records];
        for team_id in team_ids:
            _require_positive_id(team_id, 'dqd_id');
        if len(set(team_ids)) != len(team_ids):
            raise ValueError('teams contains duplicate dqd_id values.');

        self._database_path.parent.mkdir(parents=True, exist_ok=True);

        # 外键确保球员关联到已配置球队；球队表同时保存懂球帝与球探的映射。
        with self._connection() as connection:
            connection.execute('PRAGMA foreign_keys = ON;');
            connection.execute('BEGIN IMMEDIATE;');
            connection.execute(
                'CREATE TABLE IF NOT EXISTS teams ('
                'team_id INTEGER PRIMARY KEY, '
                'dqd_name TEXT NOT NULL, '
                'qiutan_name TEXT NOT NULL, '
                'qiutan_serial TEXT NOT NULL, '
                'league_serial INTEGER NOT NULL, '
                'league_slug TEXT NOT NULL, '
                'match_league_name TEXT NOT NULL'
                ');'
            );
            connection.execute(
                'CREATE TABLE IF NOT EXISTS players ('
                'person_id INTEGER PRIMARY KEY, '
                'person_name TEXT NOT NULL, '
                'attr TEXT NOT NULL, '
                'shirt_number TEXT, '
                'person_en_name TEXT, '
                'age TEXT, social_status TEXT, nationality TEXT, height INTEGER, weight INTEGER, '
                'caps INTEGER, lineups INTEGER, goals INTEGER, assists INTEGER, rescues INTEGER, '
                'ability INTEGER, position TEXT, '
                'stats_season TEXT, stats_league_serial INTEGER'
                ');'
            );
            connection.execute(
                'CREATE TABLE IF NOT EXISTS team_players ('
                'team_id INTEGER NOT NULL REFERENCES teams(team_id), '
                'person_id INTEGER NOT NULL REFERENCES players(person_id), '
                'PRIMARY KEY (team_id, person_id)'
                ');'
            );
            # 当前联赛只保留一个最新赛季映射；赛程表通过复合外键引用这条关系。
            connection.execute(
                'CREATE TABLE IF NOT EXISTS league_seasons ('
                'league_serial INTEGER NOT NULL, '
                'season TEXT NOT NULL, '
                'season_sort INTEGER NOT NULL, '
                'PRIMARY KEY (league_serial, season), '
                'UNIQUE (league_serial)'
                ');'
            );
            connection.execute(
                'CREATE TABLE IF NOT EXISTS team_schedules ('
                'team_id INTEGER NOT NULL REFERENCES teams(team_id), '
                'league_serial INTEGER NOT NULL, '
                'season TEXT NOT NULL, '
                'match_id INTEGER NOT NULL, '
                'competition_id INTEGER NOT NULL, '
                'competition_name TEXT NOT NULL, '
                'gameweek TEXT NOT NULL, '
                'team_a_id INTEGER NOT NULL, '
                'team_b_id INTEGER NOT NULL, '
                'team_a_name TEXT NOT NULL, '
                'team_b_name TEXT NOT NULL, '
                'team_a_logo TEXT NOT NULL, '
                'team_b_logo TEXT NOT NULL, '
                'fs_a TEXT NOT NULL, '
                'fs_b TEXT NOT NULL, '
                'ps_a TEXT NOT NULL, '
                'ps_b TEXT NOT NULL, '
                'start_play TEXT NOT NULL, '
                'suretime TEXT NOT NULL, '
                'status TEXT NOT NULL, '
                'playing_time TEXT NOT NULL, '
                'scheme TEXT NOT NULL, '
                'round_name TEXT NOT NULL, '
                'minute TEXT NOT NULL, '
                'minute_extra TEXT NOT NULL, '
                'score_color TEXT NOT NULL, '
                'match_title TEXT NOT NULL, '
                'PRIMARY KEY (team_id, match_id), '
                'FOREIGN KEY (league_serial, season) '
                'REFERENCES league_seasons(league_serial, season)'
                ');'
            );
            connection.execute(
                'CREATE INDEX IF NOT EXISTS team_schedules_team_kickoff_idx '
                'ON team_schedules(team_id, start_play);'
            );
            # 旧版数据库逐步增加球队映射字段；已存在的驼峰列会重命名并保留原值。
            team_columns = {row[1] for row in connection.execute('PRAGMA table_info(teams);').fetchall()};
            if 'dqd_name' not in team_columns:
                connection.execute('ALTER TABLE teams ADD COLUMN dqd_name TEXT;');
            if 'qiutan_name' not in team_columns:
                connection.execute('ALTER TABLE teams ADD COLUMN qiutan_name TEXT;');
            if 'qiutan_serial' not in team_columns:
                connection.execute('ALTER TABLE teams ADD COLUMN qiutan_serial TEXT;');
            league_column_migrations = (
                ('leagueSerial', 'league_serial', 'INTEGER'),
                ('leagueSlug', 'league_slug', 'TEXT'),
                ('matchLeagueName', 'match_league_name', 'TEXT'),
            );
            for old_name, new_name, column_type in league_column_migrations:
                if new_name not in team_columns:
                    if old_name in team_columns:
                        connection.execute(f'ALTER TABLE teams RENAME COLUMN {old_name} TO {new_name};');
                        team_columns.remove(old_name);
                    else:
                        connection.execute(f'ALTER TABLE teams ADD COLUMN {new_name} {column_type};');
                    team_columns.add(new_name);

            # 老版 players 表逐步增加姓名、位置、球衣号码和英文名列，保留已有人员 ID。
            player_columns = {row[1] for row in connection.execute('PRAGMA table_info(players);').fetchall()};
            if 'person_name' not in player_columns:
                connection.execute('ALTER TABLE players ADD COLUMN person_name TEXT;');
                player_columns.add('person_name');
            if 'attr' not in player_columns:
                connection.execute('ALTER TABLE players ADD COLUMN attr TEXT;');
                player_columns.add('attr');
            if 'shirt_number' not in player_columns:
                connection.execute('ALTER TABLE players ADD COLUMN shirt_number TEXT;');
                player_columns.add('shirt_number');
            if 'person_en_name' not in player_columns:
                connection.execute('ALTER TABLE players ADD COLUMN person_en_name TEXT;');
                player_columns.add('person_en_name');
            for column in ('age', 'social_status', 'nationality'):
                if column not in player_columns:
                    connection.execute(f'ALTER TABLE players ADD COLUMN {column} TEXT;');
            for column in PLAYER_STATISTIC_FIELDS + ('ability', 'height', 'weight'):
                if column not in player_columns:
                    connection.execute(f'ALTER TABLE players ADD COLUMN {column} INTEGER;');
            if 'position' not in player_columns:
                connection.execute('ALTER TABLE players ADD COLUMN position TEXT;');
            if 'stats_season' not in player_columns:
                connection.execute('ALTER TABLE players ADD COLUMN stats_season TEXT;');
            if 'stats_league_serial' not in player_columns:
                connection.execute('ALTER TABLE players ADD COLUMN stats_league_serial INTEGER;');
            team_player_columns = {row[1] for row in connection.execute('PRAGMA table_info(team_players);').fetchall()};
            if 'attr' in team_player_columns:
                # 从旧的球队关联表迁移 attr；同一人员在多个队有记录时按 team_id 顺序取一条旧值。
                connection.execute(
                    'UPDATE players SET attr = ('
                    'SELECT team_players.attr FROM team_players '
                    'WHERE team_players.person_id = players.person_id '
                    'AND team_players.attr IS NOT NULL '
                    'ORDER BY team_players.team_id LIMIT 1'
                    ') WHERE players.attr IS NULL;'
                );
                # 重建中间表以移除 attr，只保留球队 ID 和人员 ID 两个关联字段。
                connection.execute(
                    'CREATE TABLE team_players_new ('
                    'team_id INTEGER NOT NULL REFERENCES teams(team_id), '
                    'person_id INTEGER NOT NULL REFERENCES players(person_id), '
                    'PRIMARY KEY (team_id, person_id)'
                    ');'
                );
                connection.execute(
                    'INSERT INTO team_players_new (team_id, person_id) '
                    'SELECT team_id, person_id FROM team_players;'
                );
                connection.execute('DROP TABLE team_players;');
                connection.execute('ALTER TABLE team_players_new RENAME TO team_players;');

            # 用懂球帝 ID 做唯一键；重复初始化时更新名称和球探编号，不会重复插入。
            connection.executemany(
                'INSERT INTO teams '
                '(team_id, dqd_name, qiutan_name, qiutan_serial, league_serial, league_slug, match_league_name) '
                'VALUES (?, ?, ?, ?, ?, ?, ?) '
                'ON CONFLICT(team_id) DO UPDATE SET '
                'dqd_name = excluded.dqd_name, '
                'qiutan_name = excluded.qiutan_name, '
                'qiutan_serial = excluded.qiutan_serial, '
                'league_serial = excluded.league_serial, '
                'league_slug = excluded.league_slug, '
                'match_league_name = excluded.match_league_name;',
                [
                    (
                        team.dqd_id,
                        team.dqd_name,
                        team.qiutan_name,
                        team.qiutan_serial,
                        team.league_serial,
                        team.league_slug,
                        team.match_league_name,
                    )
                    for team in team_records
                ],
            );
            connection.execute('PRAGMA user_version = 8;');

    def get_team(self, team_id: int) -> Team:
        # 运行时从 teams 表读取名称和联赛映射，不再依赖 config.toml 的重复记录。
        _require_positive_id(team_id, 'team_id');
        with self._connection() as connection:
            row = connection.execute(
                'SELECT team_id, dqd_name, qiutan_name, qiutan_serial, league_serial, league_slug, match_league_name '
                'FROM teams WHERE team_id = ?;',
                (team_id,),
            ).fetchone();
        if row is None:
            raise ValueError(
                f'team_id={team_id} 不在 SQLite 的 teams 表中；'
                '请在项目根目录 teams.json 添加该球队的完整映射后，运行 db-init --config config.toml。'
            );
        return Team(
            team_id=row[0],
            dqd_name=row[1],
            qiutan_name=row[2],
            qiutan_serial=row[3],
            league_serial=row[4],
            league_slug=row[5],
            match_league_name=row[6],
        );

    def get_current_season(self, team_id: int) -> str:
        _require_positive_id(team_id, 'team_id');
        with self._connection() as connection:
            row = connection.execute(
                'SELECT ls.season FROM teams AS t '
                'JOIN league_seasons AS ls ON ls.league_serial = t.league_serial '
                'WHERE t.team_id = ?;',
                (team_id,),
            ).fetchone();
        if row is None:
            raise ValueError(f'team_id={team_id} 没有 league_seasons 当前赛季记录，请先导入赛程。');
        return row[0];

    def replace_team_player_details(
        self,
        team_id: int,
        season: str,
        statistics: Iterable[PlayerStatistics],
        abilities: Iterable[PlayerAbility],
        profiles: Iterable[PlayerProfile],
    ) -> None:
        _require_positive_id(team_id, 'team_id');
        records = list(statistics);
        if not records or not all(isinstance(record, PlayerStatistics) for record in records):
            raise ValueError('statistics must contain PlayerStatistics records.');
        person_ids = [record.person_id for record in records];
        if len(set(person_ids)) != len(person_ids):
            raise ValueError('statistics contains duplicate person_id values.');
        for record in records:
            _require_positive_id(record.person_id, 'person_id');
            for field in PLAYER_STATISTIC_FIELDS:
                value = getattr(record, field);
                if value is not None and (isinstance(value, bool) or not isinstance(value, int) or value < 0):
                    raise ValueError(f'{field} must be a non-negative integer or None.');
            base_values = (record.caps, record.lineups, record.goals, record.assists);
            if any(value is None for value in base_values) and not all(value is None for value in base_values):
                raise ValueError('caps, lineups, goals and assists must all be present or all be None.');

        ability_records = list(abilities);
        if not ability_records or not all(isinstance(record, PlayerAbility) for record in ability_records):
            raise ValueError('abilities must contain PlayerAbility records.');
        for record in ability_records:
            _require_positive_id(record.person_id, 'person_id');
            if (record.ability is None) != (record.position is None):
                raise ValueError('ability and position must both be present or both be None.');
            if record.ability is not None:
                if isinstance(record.ability, bool) or not isinstance(record.ability, int) or record.ability < 0:
                    raise ValueError('ability must be a non-negative integer or None.');
                if not isinstance(record.position, str) or not record.position.strip():
                    raise ValueError('position must be a non-empty string or None.');
        abilities_by_id = {record.person_id: record for record in ability_records};
        if len(abilities_by_id) != len(ability_records) or set(abilities_by_id) != set(person_ids):
            raise ValueError('能力值人员必须与统计人员完全一致且不重复。');

        profile_records = list(profiles);
        if not all(isinstance(record, PlayerProfile) for record in profile_records):
            raise ValueError('profiles must contain PlayerProfile records.');
        profiles_by_id = {record.person_id: record for record in profile_records};
        if len(profiles_by_id) != len(profile_records) or set(profiles_by_id) != set(person_ids):
            raise ValueError('个人资料人员必须与统计人员完全一致且不重复。');
        for record in profile_records:
            if not isinstance(record.nationality, str) or not record.nationality.strip():
                raise ValueError('nationality must be a non-empty string.');
            for value in (record.height, record.weight):
                if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
                    raise ValueError('height and weight must be positive integers.');

        # 提交前再次核验赛季和名单，避免抓取途中来源变化后写入过期细节。
        with self._connection() as connection:
            connection.execute('BEGIN IMMEDIATE;');
            season_row = connection.execute(
                'SELECT t.league_serial, ls.season FROM teams AS t '
                'JOIN league_seasons AS ls ON ls.league_serial = t.league_serial WHERE t.team_id = ?;',
                (team_id,),
            ).fetchone();
            if season_row is None or season_row[1] != season:
                raise ValueError('抓取期间 league_seasons 已变化，拒绝写入过期赛季统计。');
            players = dict(connection.execute(
                'SELECT p.person_id, p.attr FROM players AS p '
                'JOIN team_players AS tp ON tp.person_id = p.person_id '
                'WHERE tp.team_id = ? AND p.attr != ?;',
                (team_id, '主教练'),
            ).fetchall());
            if set(players) != set(person_ids):
                raise ValueError('统计人员与当前球队球员名单不一致，拒绝写入。');
            for record in records:
                if players[record.person_id] != '门将' and record.rescues is not None:
                    raise ValueError('非门将的 rescues 必须为 None。');
                if players[record.person_id] == '门将' and (record.caps is None) != (record.rescues is None):
                    raise ValueError('门将有联赛统计时必须同时提供 rescues。');
            connection.executemany(
                'UPDATE players SET caps = ?, lineups = ?, goals = ?, assists = ?, rescues = ?, '
                'ability = ?, position = ?, nationality = ?, height = ?, weight = ?, '
                'stats_season = ?, stats_league_serial = ? WHERE person_id = ?;',
                [
                    (record.caps, record.lineups, record.goals, record.assists, record.rescues,
                     abilities_by_id[record.person_id].ability, abilities_by_id[record.person_id].position,
                     profiles_by_id[record.person_id].nationality,
                     profiles_by_id[record.person_id].height, profiles_by_id[record.person_id].weight,
                     season, season_row[0], record.person_id)
                    for record in records
                ],
            );

    def get_club_players(self, team_id: int) -> list[dict]:
        self.get_team(team_id);
        with self._connection() as connection:
            connection.row_factory = sqlite3.Row;
            rows = connection.execute(
                'SELECT p.* FROM players p JOIN team_players tp ON tp.person_id = p.person_id '
                'WHERE tp.team_id = ? AND p.attr != ? ORDER BY tp.rowid;',
                (team_id, '主教练'),
            ).fetchall();
        if not rows:
            raise ValueError('球队没有球员名单，请先运行 roster-sync。');
        return [dict(row) for row in rows];

    def replace_team_players(self, team_id: int, members: Iterable[RosterMember]) -> int:
        # 传入的是已经校验过的名单记录；每次同步都更新人员资料和球衣号码。
        _require_positive_id(team_id, 'team_id');
        roster_members = list(members);
        if not roster_members:
            raise ValueError('members cannot be empty; refusing to clear the saved team roster.');

        player_ids = [];
        for member in roster_members:
            if not isinstance(member, RosterMember):
                raise ValueError('members must contain RosterMember records.');
            _require_positive_id(member.person_id, 'person_id');
            if not isinstance(member.person_name, str) or not member.person_name.strip():
                raise ValueError('person_name must be a non-empty string.');
            if not isinstance(member.attr, str) or not member.attr.strip():
                raise ValueError('attr must be a non-empty string.');
            if member.shirt_number is not None and not isinstance(member.shirt_number, str):
                raise ValueError('shirt_number must be a string or None.');
            if member.person_en_name is not None and not isinstance(member.person_en_name, str):
                raise ValueError('person_en_name must be a string or None.');
            if not isinstance(member.age, str) or not member.age.strip():
                raise ValueError('age must be a non-empty string.');
            if member.social_status is not None and not isinstance(member.social_status, str):
                raise ValueError('social_status must be a string or None.');
            player_ids.append(member.person_id);
        if len(set(player_ids)) != len(player_ids):
            raise ValueError('members contains duplicate person_id values.');

        # 一个事务里更新人员资料、删除旧关联并写入新关联；任一步失败都会整体回滚。
        with self._connection() as connection:
            connection.execute('PRAGMA foreign_keys = ON;');
            connection.execute('BEGIN IMMEDIATE;');
            connection.executemany(
                'INSERT INTO players '
                '(person_id, person_name, attr, shirt_number, person_en_name, age, social_status) '
                'VALUES (?, ?, ?, ?, ?, ?, ?) '
                'ON CONFLICT(person_id) DO UPDATE SET '
                'person_name = excluded.person_name, '
                'attr = excluded.attr, '
                'shirt_number = excluded.shirt_number, '
                'person_en_name = excluded.person_en_name, '
                'age = excluded.age, '
                'social_status = excluded.social_status;',
                [
                    (
                        member.person_id,
                        member.person_name,
                        member.attr,
                        member.shirt_number,
                        member.person_en_name,
                        member.age,
                        member.social_status,
                    )
                    for member in roster_members
                ],
            );
            connection.execute('DELETE FROM team_players WHERE team_id = ?;', (team_id,));
            connection.executemany(
                'INSERT INTO team_players (team_id, person_id) VALUES (?, ?);',
                [(team_id, member.person_id) for member in roster_members],
            );

        return len(player_ids);

    def replace_team_schedule(self, schedule: TeamSchedule) -> int:
        # 清洗后的赛程整批替换；赛季升级与旧赛程清理也在同一事务中完成。
        if not isinstance(schedule, TeamSchedule):
            raise ValueError('schedule must be a TeamSchedule record.');
        _require_positive_id(schedule.team_id, 'team_id');
        _require_positive_id(schedule.league_serial, 'league_serial');
        _require_positive_id(schedule.season_sort, 'season_sort');
        if not isinstance(schedule.season, str) or not schedule.season.strip():
            raise ValueError('season must be a non-empty string.');
        if not schedule.matches:
            raise ValueError('matches cannot be empty; refusing to clear the saved team schedule.');

        match_ids = [];
        for match in schedule.matches:
            if not isinstance(match, TeamScheduleMatch):
                raise ValueError('matches must contain TeamScheduleMatch records.');
            _require_positive_id(match.match_id, 'match_id');
            _require_positive_id(match.competition_id, 'competition_id');
            _require_positive_id(match.team_a_id, 'team_a_id');
            _require_positive_id(match.team_b_id, 'team_b_id');
            if schedule.team_id not in (match.team_a_id, match.team_b_id):
                raise ValueError(f'match_id={match.match_id} does not include team_id={schedule.team_id}.');
            match_ids.append(match.match_id);
        if len(set(match_ids)) != len(match_ids):
            raise ValueError('matches contains duplicate match_id values.');

        with self._connection() as connection:
            connection.execute('PRAGMA foreign_keys = ON;');
            connection.execute('BEGIN IMMEDIATE;');
            team_row = connection.execute(
                'SELECT league_serial FROM teams WHERE team_id = ?;',
                (schedule.team_id,),
            ).fetchone();
            if team_row is None:
                raise ValueError(f'team_id is not present in teams: {schedule.team_id}');
            if team_row[0] != schedule.league_serial:
                raise ValueError(
                    f'league_serial mismatch for team_id={schedule.team_id}: '
                    f'config={team_row[0]}, response={schedule.league_serial}.'
                );

            current_season = connection.execute(
                'SELECT season, season_sort FROM league_seasons WHERE league_serial = ?;',
                (schedule.league_serial,),
            ).fetchone();
            if current_season is not None and schedule.season_sort < current_season[1]:
                raise ValueError(
                    f'拒绝用旧赛季 {schedule.season} 覆盖已保存的最新赛季 {current_season[0]}。'
                );
            if current_season is not None and schedule.season_sort == current_season[1]:
                if schedule.season != current_season[0]:
                    raise ValueError('相同 season_sort 对应了不同 season，拒绝覆盖赛季映射。');
            if current_season is not None and schedule.season_sort > current_season[1]:
                # 切换联赛赛季时清除旧统计，避免 players 展示上赛季的数据。
                connection.execute(
                    'UPDATE players SET caps = NULL, lineups = NULL, goals = NULL, assists = NULL, '
                    'rescues = NULL, ability = NULL, position = NULL, stats_season = NULL, stats_league_serial = NULL '
                    'WHERE stats_league_serial = ?;',
                    (schedule.league_serial,),
                );
                # 新赛季开始时，联赛内所有球队的上一赛季赛程一并清除。
                connection.execute(
                    'DELETE FROM team_schedules WHERE league_serial = ?;',
                    (schedule.league_serial,),
                );
                connection.execute(
                    'DELETE FROM league_seasons WHERE league_serial = ?;',
                    (schedule.league_serial,),
                );

            connection.execute(
                'INSERT INTO league_seasons (league_serial, season, season_sort) VALUES (?, ?, ?) '
                'ON CONFLICT(league_serial, season) DO UPDATE SET season_sort = excluded.season_sort;',
                (schedule.league_serial, schedule.season, schedule.season_sort),
            );
            connection.execute(
                'DELETE FROM team_schedules WHERE team_id = ?;',
                (schedule.team_id,),
            );
            connection.executemany(
                'INSERT INTO team_schedules ('
                'team_id, league_serial, season, match_id, competition_id, competition_name, gameweek, '
                'team_a_id, team_b_id, team_a_name, team_b_name, team_a_logo, team_b_logo, '
                'fs_a, fs_b, ps_a, ps_b, start_play, suretime, status, playing_time, scheme, '
                'round_name, minute, minute_extra, score_color, match_title'
                ') VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);',
                [
                    (
                        schedule.team_id,
                        schedule.league_serial,
                        schedule.season,
                        match.match_id,
                        match.competition_id,
                        match.competition_name,
                        match.gameweek,
                        match.team_a_id,
                        match.team_b_id,
                        match.team_a_name,
                        match.team_b_name,
                        match.team_a_logo,
                        match.team_b_logo,
                        match.fs_a,
                        match.fs_b,
                        match.ps_a,
                        match.ps_b,
                        match.start_play,
                        match.suretime,
                        match.status,
                        match.playing_time,
                        match.scheme,
                        match.round_name,
                        match.minute,
                        match.minute_extra,
                        match.score_color,
                        match.match_title,
                    )
                    for match in schedule.matches
                ],
            );

        return len(schedule.matches);

    def get_team_schedule(self, team_id: int) -> TeamSchedule:
        # 读取联赛当前赛季关联的赛程；不存在数据时明确报错，不猜测赛季或球队。
        _require_positive_id(team_id, 'team_id');
        with self._connection() as connection:
            team_row = connection.execute(
                'SELECT league_serial FROM teams WHERE team_id = ?;',
                (team_id,),
            ).fetchone();
            if team_row is None:
                raise ValueError(f'team_id is not present in teams: {team_id}');
            league_serial = team_row[0];
            season_row = connection.execute(
                'SELECT season, season_sort FROM league_seasons WHERE league_serial = ?;',
                (league_serial,),
            ).fetchone();
            if season_row is None:
                raise ValueError(f'league_serial={league_serial} has no imported current season.');
            rows = connection.execute(
                'SELECT match_id, competition_id, competition_name, gameweek, team_a_id, team_b_id, '
                'team_a_name, team_b_name, team_a_logo, team_b_logo, fs_a, fs_b, ps_a, ps_b, '
                'start_play, suretime, status, playing_time, scheme, round_name, minute, minute_extra, '
                'score_color, match_title FROM team_schedules '
                'WHERE team_id = ? AND league_serial = ? AND season = ? '
                'ORDER BY start_play, match_id;',
                (team_id, league_serial, season_row[0]),
            ).fetchall();
        if not rows:
            raise ValueError(f'team_id={team_id} has no saved schedule for season={season_row[0]}.');

        matches = tuple(TeamScheduleMatch(*row) for row in rows);
        return TeamSchedule(
            team_id=team_id,
            league_serial=league_serial,
            season=season_row[0],
            season_sort=season_row[1],
            matches=matches,
        );

    @contextmanager
    def _connection(self) -> Iterator[sqlite3.Connection]:
        # Connection 上下文负责提交/回滚事务；closing 在结束后明确关闭文件句柄。
        with closing(sqlite3.connect(self._database_path)) as connection:
            with connection:
                yield connection;


def _require_positive_id(value: int, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f'{field_name} must be a positive integer.');
    return value;
