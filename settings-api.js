import { spawn } from 'node:child_process';
import { existsSync, mkdirSync, readFileSync, renameSync, unlinkSync, writeFileSync } from 'node:fs';
import { join } from 'node:path';
import { ensureUv } from './lib/uvfetch.mjs';

const MAX_REQUEST_BYTES = 16_384;
const MAX_TOOL_OUTPUT_CHARS = 32_768;

const httpError = (message, statusCode) => Object.assign(new Error(message), { statusCode });

const tomlCommentIndex = (value) => {
  let quote = '';
  let escaped = false;

  for (let index = 0; index < value.length; index += 1) {
    const character = value[index];
    if (quote === '"') {
      if (escaped) {
        escaped = false;
      } else if (character === '\\') {
        escaped = true;
      } else if (character === '"') {
        quote = '';
      }
      continue;
    }
    if (quote === "'") {
      if (character === "'") quote = '';
      continue;
    }
    if (character === '"' || character === "'") {
      quote = character;
      continue;
    }
    if (character === '#') return index;
  }

  return -1;
};

const withoutTomlComment = (value) => {
  const commentIndex = tomlCommentIndex(value);
  return (commentIndex === -1 ? value : value.slice(0, commentIndex)).trim();
};

const parseTomlStringArray = (source) => {
  const value = withoutTomlComment(source);
  if (!value.startsWith('[') || !value.endsWith(']')) {
    throw new Error('config.toml 的 dynamics.interests 必须是单行 TOML 字符串数组。');
  }

  const values = [];
  let cursor = 1;
  const end = value.length - 1;

  while (cursor < end) {
    while (/\s/.test(value[cursor] ?? '')) cursor += 1;
    if (cursor >= end) break;

    const quote = value[cursor];
    if (quote !== '"' && quote !== "'") {
      throw new Error('config.toml 的 dynamics.interests 只支持字符串项。');
    }

    const start = cursor;
    cursor += 1;
    let escaped = false;
    let closed = false;
    while (cursor < end) {
      const character = value[cursor];
      if (quote === '"' && escaped) {
        escaped = false;
      } else if (quote === '"' && character === '\\') {
        escaped = true;
      } else if (character === quote) {
        cursor += 1;
        closed = true;
        break;
      }
      cursor += 1;
    }
    if (!closed) throw new Error('config.toml 的 dynamics.interests 字符串没有闭合。');

    const token = value.slice(start, cursor);
    let item;
    if (quote === '"') {
      item = JSON.parse(token);
    } else {
      item = token.slice(1, -1);
    }
    if (typeof item !== 'string' || item.trim().length === 0) {
      throw new Error('config.toml 的 dynamics.interests 不能包含空字符串。');
    }
    values.push(item.trim());

    while (/\s/.test(value[cursor] ?? '')) cursor += 1;
    if (cursor < end && value[cursor] === ',') {
      cursor += 1;
      continue;
    }
    if (cursor < end) throw new Error('config.toml 的 dynamics.interests 项之间必须用逗号分隔。');
  }

  return values;
};

const readSettingsFromText = (text) => {
  const values = new Map();
  let section = '';

  for (const line of text.split(/\r?\n/)) {
    const sectionMatch = line.match(/^\s*\[([^\]]+)\]\s*$/);
    if (sectionMatch) {
      section = sectionMatch[1];
      continue;
    }
    if (section !== 'dynamics') continue;

    const assignment = line.match(/^\s*(team_names|interests|daily_run_time|execution_method)\s*=\s*(.*)$/);
    if (!assignment) continue;
    if (values.has(assignment[1])) throw new Error(`config.toml 的 dynamics.${assignment[1]} 重复定义。`);
    values.set(assignment[1], withoutTomlComment(assignment[2]));
  }

  if (!values.has('team_names')) throw new Error('config.toml 缺少 dynamics.team_names。');
  if (!values.has('interests')) throw new Error('config.toml 缺少 dynamics.interests。');
  if (!values.has('daily_run_time')) throw new Error('config.toml 缺少 dynamics.daily_run_time。');
  if (!values.has('execution_method')) throw new Error('config.toml 缺少 dynamics.execution_method。');

  const timeMatch = values.get('daily_run_time').match(/^(['"])(\d{2}:\d{2})\1$/);
  if (!timeMatch) throw new Error('config.toml 的 dynamics.daily_run_time 必须使用 HH:MM 字符串。');
  const [hour, minute] = timeMatch[2].split(':').map(Number);
  if (hour > 23 || minute > 59) throw new Error('config.toml 的 dynamics.daily_run_time 超出有效范围。');
  const methodMatch = values.get('execution_method').match(/^(['"])(command|model)\1$/);
  if (!methodMatch) throw new Error('config.toml 的 dynamics.execution_method 必须是 command 或 model。');

  return {
    dailyRunTime: timeMatch[2],
    executionMethod: methodMatch[2],
    teamNames: parseTomlStringArray(values.get('team_names')),
    interests: parseTomlStringArray(values.get('interests')),
  };
};

export function readDqdSettings(configPath) {
  return readSettingsFromText(readFileSync(configPath, 'utf8'));
}

export function migrateExecutionMethod(configPath) {
  const currentText = readFileSync(configPath, 'utf8');
  let inDynamicsSection = false;
  let hasExecutionMethod = false;
  let insertionIndex = -1;
  const lines = currentText.split(/\r?\n/);

  for (let index = 0; index < lines.length; index += 1) {
    const sectionMatch = lines[index].match(/^\s*\[([^\]]+)\]\s*$/);
    if (sectionMatch) {
      inDynamicsSection = sectionMatch[1] === 'dynamics';
      continue;
    }
    if (!inDynamicsSection) continue;
    if (/^\s*execution_method\s*=/.test(lines[index])) hasExecutionMethod = true;
    if (/^\s*daily_run_time\s*=/.test(lines[index])) insertionIndex = index + 1;
  }

  if (hasExecutionMethod) return false;
  if (insertionIndex === -1) throw new Error('config.toml 缺少 dynamics.daily_run_time，无法迁移执行方式设置。');
  lines.splice(insertionIndex, 0, "execution_method = 'command'");
  const lineEnding = currentText.includes('\r\n') ? '\r\n' : '\n';
  const temporaryPath = `${configPath}.${process.pid}.${Date.now()}.tmp`;
  writeFileSync(temporaryPath, lines.join(lineEnding), { encoding: 'utf8', flag: 'wx' });
  try {
    renameSync(temporaryPath, configPath);
  } catch (error) {
    try {
      unlinkSync(temporaryPath);
    } catch {
      // 保留原始写入错误，便于界面显示实际原因。
    }
    throw error;
  }
  return true;
}

const validateSettings = (body, availableTeamNames) => {
  if (!body || typeof body !== 'object' || Array.isArray(body)) {
    throw httpError('设置请求必须是 JSON 对象。', 400);
  }
  const allowedKeys = new Set(['dailyRunTime', 'executionMethod', 'teamNames', 'interests']);
  for (const key of Object.keys(body)) {
    if (!allowedKeys.has(key)) throw httpError(`不支持的设置字段: ${key}`, 400);
  }
  if (typeof body.dailyRunTime !== 'string' || !/^([01]\d|2[0-3]):[0-5]\d$/.test(body.dailyRunTime)) {
    throw httpError('自动运行时间必须是 00:00 至 23:59 之间的 HH:MM。', 400);
  }
  if (body.executionMethod !== 'command' && body.executionMethod !== 'model') {
    throw httpError('执行方式必须是 command 或 model。', 400);
  }
  if (!Array.isArray(body.teamNames) || body.teamNames.length === 0) {
    throw httpError('请至少填写一个关注球队名称。', 400);
  }
  const teamNames = body.teamNames.map((teamName, index) => {
    if (typeof teamName !== 'string' || teamName.trim().length === 0) {
      throw httpError(`第 ${index + 1} 个关注球队名称不能为空。`, 400);
    }
    const normalizedTeamName = teamName.trim();
    if (!availableTeamNames.has(normalizedTeamName)) {
      throw httpError(`不支持关注球队“${normalizedTeamName}”；请从设置页显示的可选球队中选择。`, 400);
    }
    return normalizedTeamName;
  });
  if (new Set(teamNames).size !== teamNames.length) throw httpError('关注球队名称不能重复。', 400);
  if (!Array.isArray(body.interests)) throw httpError('关注内容必须是字符串数组。', 400);

  const interests = body.interests.map((interest, index) => {
    if (typeof interest !== 'string' || interest.trim().length === 0) {
      throw httpError(`第 ${index + 1} 条关注内容不能为空。`, 400);
    }
    return interest.trim();
  });

  return { dailyRunTime: body.dailyRunTime, executionMethod: body.executionMethod, teamNames, interests };
};

const writeSettings = (configPath, settings) => {
  const currentText = readFileSync(configPath, 'utf8');
  readSettingsFromText(currentText);
  const replacements = new Map([
    ['team_names', JSON.stringify(settings.teamNames)],
    ['daily_run_time', `'${settings.dailyRunTime}'`],
    ['execution_method', `'${settings.executionMethod}'`],
    ['interests', JSON.stringify(settings.interests)],
  ]);
  const counts = new Map([...replacements.keys()].map((key) => [key, 0]));
  const lines = currentText.split(/\r?\n/);
  let section = '';

  for (let index = 0; index < lines.length; index += 1) {
    const line = lines[index];
    const sectionMatch = line.match(/^\s*\[([^\]]+)\]\s*$/);
    if (sectionMatch) {
      section = sectionMatch[1];
      continue;
    }
    if (section !== 'dynamics') continue;

    const assignment = line.match(/^\s*(team_names|daily_run_time|execution_method|interests)\s*=/);
    if (!assignment) continue;
    const key = assignment[1];
    if (counts.get(key) !== 0) throw new Error(`config.toml 的 dynamics.${key} 重复定义。`);

    const equalIndex = line.indexOf('=');
    const suffix = line.slice(equalIndex + 1);
    const commentIndex = tomlCommentIndex(suffix);
    let comment = '';
    if (commentIndex !== -1) comment = suffix.slice(commentIndex).trim();
    lines[index] = `${line.slice(0, equalIndex + 1)} ${replacements.get(key)}${comment ? ` ${comment}` : ''}`;
    counts.set(key, 1);
  }

  for (const [key, count] of counts) {
    if (count !== 1) throw new Error(`config.toml 的 dynamics.${key} 必须且只能定义一次。`);
  }

  const lineEnding = currentText.includes('\r\n') ? '\r\n' : '\n';
  const updatedText = lines.join(lineEnding);
  const savedSettings = readSettingsFromText(updatedText);
  const temporaryPath = `${configPath}.${process.pid}.${Date.now()}.tmp`;
  writeFileSync(temporaryPath, updatedText, { encoding: 'utf8', flag: 'wx' });
  try {
    renameSync(temporaryPath, configPath);
  } catch (error) {
    try {
      unlinkSync(temporaryPath);
    } catch {
      // 保留原始写入错误，便于界面显示实际原因。
    }
    throw error;
  }
  return savedSettings;
};

const readJsonBody = async (request) => {
  const chunks = [];
  let bytes = 0;
  for await (const chunk of request) {
    bytes += chunk.length;
    if (bytes > MAX_REQUEST_BYTES) throw httpError('设置请求超过大小限制。', 413);
    chunks.push(chunk);
  }
  try {
    return JSON.parse(Buffer.concat(chunks).toString('utf8'));
  } catch {
    throw httpError('设置请求不是有效的 JSON。', 400);
  }
};

const sendJson = (response, statusCode, body) => {
  response.statusCode = statusCode;
  response.setHeader('content-type', 'application/json; charset=utf-8');
  response.end(JSON.stringify(body));
};

const sameOriginRequest = (request) => {
  const host = String(request.headers.host ?? '').toLowerCase();
  if (!/^(127\.0\.0\.1|localhost|\[::1\])(:\d+)?$/.test(host)) return false;
  const source = String(request.headers.origin ?? request.headers.referer ?? '');
  if (!source) return true;

  let sourceHost;
  try {
    sourceHost = new URL(source).host.toLowerCase();
  } catch {
    return false;
  }
  return sourceHost === host;
};

const connectionFor = (context) => {
  const readers = [
    () => (typeof context.get === 'function' ? context.get('connection') : null),
    () => Reflect.get(context, 'connection'),
    () => (context.root && typeof context.root === 'object' ? context.root.connection : null),
  ];
  for (const read of readers) {
    try {
      const connection = read();
      if (connection && typeof connection.requestRejection === 'function') return connection;
    } catch {
      // 继续检查 DSH 暴露的其他 connection 入口。
    }
  }
  return null;
};

const rejectUntrustedRequest = (context, request, response) => {
  const connection = connectionFor(context);
  if (connection) {
    try {
      const rejection = connection.requestRejection({ headers: request.headers });
      if (rejection === undefined) return false;
      response.statusCode = typeof rejection === 'number' ? rejection : 403;
      response.end();
      return true;
    } catch {
      response.statusCode = 403;
      response.end();
      return true;
    }
  }
  if (sameOriginRequest(request)) return false;
  sendJson(response, 403, { ok: false, error: '只接受本机同源请求。' });
  return true;
};

const appendBounded = (current, chunk) => {
  const combined = current + chunk.toString('utf8');
  return combined.slice(Math.max(0, combined.length - MAX_TOOL_OUTPUT_CHARS));
};

const runProcess = (command, args, options) => new Promise((resolve, reject) => {
  let child;
  try {
    child = spawn(command, args, {
      ...options,
      windowsHide: true,
      stdio: ['ignore', 'pipe', 'pipe'],
    });
  } catch (error) {
    reject(error);
    return;
  }

  let stdout = '';
  let stderr = '';
  let settled = false;
  child.stdout.on('data', (chunk) => {
    stdout = appendBounded(stdout, chunk);
  });
  child.stderr.on('data', (chunk) => {
    stderr = appendBounded(stderr, chunk);
  });
  child.once('error', (error) => {
    if (settled) return;
    settled = true;
    reject(error);
  });
  child.once('close', (code, signal) => {
    if (settled) return;
    settled = true;
    const output = [stdout, stderr].filter(Boolean).join('\n');
    if (code !== 0) {
      reject(new Error(`${command} ${args.join(' ')} 失败: ${output || `exit=${code} signal=${signal ?? 'none'}`}`));
      return;
    }
    resolve({ code, output, stdout, stderr });
  });
});

export function registerDqdSettingsApi(context, projectDir, configPath, stateDir, scheduler, logger) {
  const pythonEnvironmentPath = join(stateDir, 'python-environment.json');
  const pythonEnvironmentDir = join(stateDir, '.venv');
  const teamData = JSON.parse(readFileSync(join(projectDir, 'teams.json'), 'utf8'));
  const availableTeamNames = new Set(teamData.map((team) => team.dqd_name));
  let pythonEnvironmentInstallRunning = false;

  const pythonEnvironmentPython = () => process.platform === 'win32'
    ? join(pythonEnvironmentDir, 'Scripts', 'python.exe')
    : join(pythonEnvironmentDir, 'bin', 'python');

  const readPythonEnvironment = () => {
    if (!existsSync(pythonEnvironmentPath)) return { ready: false, pythonPath: '' };
    const savedEnvironment = JSON.parse(readFileSync(pythonEnvironmentPath, 'utf8'));
    if (typeof savedEnvironment.pythonPath !== 'string' || savedEnvironment.pythonPath.length === 0) {
      throw new Error('本机 Python 环境记录缺少有效的 pythonPath。');
    }
    return {
      ready: existsSync(savedEnvironment.pythonPath),
      pythonPath: savedEnvironment.pythonPath,
      pythonVersion: savedEnvironment.pythonVersion,
    };
  };

  const installPythonEnvironment = async () => {
    if (pythonEnvironmentInstallRunning) throw httpError('本机运行环境正在安装。', 409);
    pythonEnvironmentInstallRunning = true;
    try {
      mkdirSync(stateDir, { recursive: true });
      const uvPath = await ensureUv({ dir: join(stateDir, 'bin') });
      const pythonEnv = {
        ...process.env,
        UV_CACHE_DIR: join(stateDir, 'uv-cache'),
        UV_PYTHON_INSTALL_DIR: join(stateDir, 'uv-python'),
        PYTHONPATH: join(projectDir, 'src'),
        PYTHONUTF8: '1',
        PYTHONIOENCODING: 'utf-8',
      };
      await runProcess(uvPath, ['python', 'install', '3.11'], { cwd: stateDir, env: pythonEnv });
      await runProcess(uvPath, ['venv', '--python', '3.11', pythonEnvironmentDir], { cwd: stateDir, env: pythonEnv });

      const pythonPath = pythonEnvironmentPython();
      if (!existsSync(pythonPath)) throw new Error(`Python 环境创建后未找到解释器: ${pythonPath}`);
      const versionResult = await runProcess(pythonPath, [
        '-c',
        'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}")',
      ], { cwd: stateDir, env: pythonEnv });
      const pythonVersion = versionResult.stdout.trim();
      if (!/^3\.11\.\d+$/.test(pythonVersion)) throw new Error(`创建的 Python 版本不符合要求: ${pythonVersion}`);

      const databaseResult = await runProcess(pythonPath, [
        '-m',
        'dqd_scroll',
        'db-init',
        '--config',
        configPath,
        '--teams',
        join(projectDir, 'teams.json'),
      ], { cwd: stateDir, env: pythonEnv });
      writeFileSync(pythonEnvironmentPath, JSON.stringify({
        pythonPath,
        pythonVersion,
      }, null, 2), 'utf8');
      return {
        ready: true,
        pythonPath,
        pythonVersion,
        output: databaseResult.output.trim(),
      };
    } finally {
      pythonEnvironmentInstallRunning = false;
    }
  };

  return context.webServer.register({
    kind: 'prefix',
    path: '/api/dqd-scroll',
    handler: async (request, response) => {
      if (rejectUntrustedRequest(context, request, response)) return;

      const url = new URL(request.url, 'http://127.0.0.1');
      try {
        if (request.method === 'GET' && url.pathname === '/api/dqd-scroll/settings') {
          const text = readFileSync(configPath, 'utf8');
          return sendJson(response, 200, {
            ok: true,
            settings: readSettingsFromText(text),
            pythonEnvironment: readPythonEnvironment(),
            availableTeamNames: [...availableTeamNames],
            scheduleState: scheduler.readState(),
            logPath: logger.logPath,
          });
        }

        if (request.method === 'GET' && url.pathname === '/api/dqd-scroll/logs') {
          return sendJson(response, 200, { ok: true, log: logger.readRecent(100), logPath: logger.logPath });
        }

        if (request.method === 'POST' && url.pathname === '/api/dqd-scroll/settings') {
          const settings = validateSettings(await readJsonBody(request), availableTeamNames);
          const savedSettings = writeSettings(configPath, settings);
          const scheduleState = await scheduler.sync(savedSettings);
          return sendJson(response, 200, { ok: true, settings: savedSettings, scheduleState });
        }

        if (request.method === 'POST' && url.pathname === '/api/dqd-scroll/python-environment/install') {
          const pythonEnvironment = await installPythonEnvironment();
          const scheduleState = await scheduler.sync(readSettingsFromText(readFileSync(configPath, 'utf8')));
          return sendJson(response, 200, { ok: true, pythonEnvironment, scheduleState });
        }

        return sendJson(response, 404, { ok: false, error: `未知请求: ${request.method} ${url.pathname}` });
      } catch (error) {
        const statusCode = Number.isInteger(error.statusCode) ? error.statusCode : 500;
        return sendJson(response, statusCode, { ok: false, error: error.message });
      }
    },
  });
}
