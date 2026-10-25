import { appendFileSync, existsSync, readFileSync, renameSync, statSync, unlinkSync, writeFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { spawn } from 'node:child_process';
import { fileURLToPath } from 'node:url';

const MAX_LOG_BYTES = 2 * 1024 * 1024;
const runnerPath = fileURLToPath(import.meta.url);
const stateDir = dirname(runnerPath);
const configPath = join(stateDir, 'dynamics-scheduled-config.json');
const logPath = join(stateDir, 'dqd-scroll.log');
const statePath = join(stateDir, 'dynamics-schedule-state.json');

const log = (level, message) => {
  const line = `${new Date().toISOString()} [${level.toUpperCase()}] ${message}`;
  try {
    if (existsSync(logPath) && statSync(logPath).size > MAX_LOG_BYTES) {
      const previousLogPath = `${logPath}.1`;
      if (existsSync(previousLogPath)) unlinkSync(previousLogPath);
      renameSync(logPath, previousLogPath);
    }
    appendFileSync(logPath, `${line}\n`, 'utf8');
  } catch {
    process.stderr.write(`${line}\n`);
  }
};

const updateState = (runState) => {
  let currentState = {};
  if (existsSync(statePath)) currentState = JSON.parse(readFileSync(statePath, 'utf8'));
  const nextState = { ...currentState, ...runState };
  if (runState.last_status === 'succeeded') delete nextState.last_error;
  writeFileSync(statePath, `${JSON.stringify(nextState, null, 2)}\n`, 'utf8');
};

const runChild = (command, args, options) => new Promise((resolve, reject) => {
  let child;
  try {
    child = spawn(command, args, { windowsHide: true, stdio: ['ignore', 'pipe', 'pipe'], ...options });
  } catch (error) {
    reject(error);
    return;
  }
  child.stdout.on('data', (chunk) => {
    const output = chunk.toString('utf8').trimEnd();
    if (output) log('info', output);
  });
  child.stderr.on('data', (chunk) => {
    const output = chunk.toString('utf8').trimEnd();
    if (output) log('error', output);
  });
  child.once('error', reject);
  child.once('close', (code) => resolve(code));
});

const run = async () => {
  const settings = JSON.parse(readFileSync(configPath, 'utf8'));
  const startedAt = new Date();
  const runDate = new Intl.DateTimeFormat('en-CA', { timeZone: 'Asia/Shanghai', year: 'numeric', month: '2-digit', day: '2-digit' }).format(startedAt);
  const mode = settings.executionMethod;
  if (mode !== 'command' && mode !== 'model') throw new Error(`未知动态日报执行方式：${mode}`);
  log('info', `动态日报启动：${runDate}，执行方式=${mode}。`);
  updateState({ last_attempt_at: startedAt.toISOString(), last_attempt_date: runDate, last_execution_method: mode, last_status: 'running' });

  let command = settings.pythonPath;
  let args = [
    '-m',
    'dqd_scroll',
    'dynamics-report',
    '--config',
    settings.configPath,
    '--teams',
    join(settings.projectDir, 'teams.json'),
  ];
  let env = {
    ...process.env,
    PYTHONPATH: join(settings.projectDir, 'src'),
    PYTHONUTF8: '1',
    PYTHONIOENCODING: 'utf-8',
  };

  if (mode === 'model') {
    const dutyPrompt = readFileSync(settings.promptPath, 'utf8');
    const teamMapPath = join(settings.projectDir, 'teams.json');
    const taskPrompt = [
      dutyPrompt,
      '',
      `配置文件：${settings.configPath}`,
      `Python 可执行文件：${settings.pythonPath}`,
      `命令参数：-m dqd_scroll dynamics-report --config ${settings.configPath} --teams ${teamMapPath}`,
      `工作目录：${settings.stateDir}`,
      '请使用 headless 会话提供的命令行工具，以当前 shell 支持的语法启动上述 Python 可执行文件并传入这些参数。检查命令结果和生成的报告文件；不要自行实现接口抓取或关键词筛选，只根据命令输出和文件内容汇报执行结果。',
    ].join('\n');
    command = settings.dshExecutable;
    args = [settings.dshCliPath, '--profile', 'headless', '--patch', settings.overlayPath, taskPrompt];
    env = {
      ...process.env,
      DSH_HOME: join(settings.stateDir, '..'),
      PYTHONPATH: join(settings.projectDir, 'src'),
      PYTHONUTF8: '1',
      PYTHONIOENCODING: 'utf-8',
      ...(settings.runAsNode ? { ELECTRON_RUN_AS_NODE: '1' } : {}),
    };
  }

  try {
    const code = await runChild(command, args, { cwd: settings.stateDir, env });
    const finishedAt = new Date();
    const succeeded = code === 0;
    if (succeeded) log('info', `动态日报执行完成：exit=${code}。`);
    if (!succeeded) log('error', `动态日报执行失败：exit=${code}。`);
    updateState({
      last_finished_at: finishedAt.toISOString(),
      last_status: succeeded ? 'succeeded' : 'failed',
      last_exit_code: code,
      ...(succeeded ? { last_run_at: finishedAt.toISOString(), last_run_date: runDate } : {}),
    });
    process.exitCode = succeeded ? 0 : 1;
  } catch (error) {
    log('error', `动态日报启动失败：${error.stack ?? error}`);
    updateState({ last_finished_at: new Date().toISOString(), last_status: 'failed', last_error: error.message });
    process.exitCode = 1;
  }
};

run().catch((error) => {
  log('error', `定时运行入口异常：${error.stack ?? error}`);
  process.exitCode = 1;
});
