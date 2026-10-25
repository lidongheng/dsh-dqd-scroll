import { spawnSync } from 'node:child_process';
import { existsSync, mkdtempSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { initializeUserData } from '../lib/user-data.js';
import { ensureUv } from '../lib/uvfetch.mjs';

const runProcess = (command, args, options) => {
  const result = spawnSync(command, args, {
    ...options,
    encoding: 'utf8',
    windowsHide: true,
  });
  if (result.error) throw result.error;
  if (result.status !== 0) {
    const output = [result.stdout, result.stderr].filter(Boolean).join('\n');
    throw new Error(`${command} ${args.join(' ')} 失败: ${output || `exit=${result.status}`}`);
  }
  return result.stdout;
};

const projectDir = dirname(dirname(fileURLToPath(import.meta.url)));
const stateDir = mkdtempSync(join(tmpdir(), 'dqd-scroll-python-bootstrap-'));

try {
  const configPath = initializeUserData(projectDir, stateDir);
  const pythonEnvironmentDir = join(stateDir, '.venv');
  const pythonEnvironment = {
    ...process.env,
    UV_CACHE_DIR: join(stateDir, 'uv-cache'),
    UV_PYTHON_INSTALL_DIR: join(stateDir, 'uv-python'),
    PYTHONPATH: join(projectDir, 'src'),
    PYTHONUTF8: '1',
    PYTHONIOENCODING: 'utf-8',
  };
  const uvPath = await ensureUv({ dir: join(stateDir, 'bin') });

  runProcess(uvPath, ['python', 'install', '3.11'], { cwd: stateDir, env: pythonEnvironment });
  runProcess(uvPath, ['venv', '--python', '3.11', pythonEnvironmentDir], {
    cwd: stateDir,
    env: pythonEnvironment,
  });

  const pythonPath = process.platform === 'win32'
    ? join(pythonEnvironmentDir, 'Scripts', 'python.exe')
    : join(pythonEnvironmentDir, 'bin', 'python');
  if (!existsSync(pythonPath)) throw new Error(`Python 环境创建后未找到解释器: ${pythonPath}`);

  const pythonVersion = runProcess(pythonPath, [
    '-c',
    'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}")',
  ], { cwd: stateDir, env: pythonEnvironment }).trim();
  if (!/^3\.11\.\d+$/.test(pythonVersion)) throw new Error(`创建的 Python 版本不符合要求: ${pythonVersion}`);

  runProcess(pythonPath, [
    '-m',
    'dqd_scroll',
    'db-init',
    '--config',
    configPath,
    '--teams',
    join(projectDir, 'teams.json'),
  ], { cwd: stateDir, env: pythonEnvironment });

  process.stdout.write(`Python bootstrap verified: ${pythonVersion}\n`);
} finally {
  rmSync(stateDir, { recursive: true, force: true });
}

