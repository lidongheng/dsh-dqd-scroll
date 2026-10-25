import { copyFileSync, existsSync, mkdirSync, readFileSync, writeFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { spawn } from 'node:child_process';

const TASK_NAME = 'DSH-DQD-Scroll-Dynamics';
const TASK_STATE_FILE = 'dynamics-schedule-state.json';
const TASK_CONFIG_FILE = 'dynamics-scheduled-config.json';
const RUNNER_FILE = 'dynamics-scheduled-runner.mjs';
const RUNNER_SCRIPT_FILE = 'dynamics-scheduled-runner.ps1';
const REGISTER_SCRIPT_FILE = 'dynamics-register-schedule.ps1';

const powerShellLiteral = (value) => `'${String(value).replace(/'/g, "''")}'`;

const writePowerShellScript = (scriptPath, lines) => {
  const content = `${lines.join('\r\n')}\r\n`;
  const utf8WithBom = Buffer.concat([Buffer.from([0xef, 0xbb, 0xbf]), Buffer.from(content, 'utf8')]);
  writeFileSync(scriptPath, utf8WithBom);
};

const runProcess = (command, args, options = {}) => new Promise((resolve, reject) => {
  let child;
  try {
    child = spawn(command, args, { ...options, windowsHide: true, stdio: ['ignore', 'pipe', 'pipe'] });
  } catch (error) {
    reject(error);
    return;
  }

  let stdout = '';
  let stderr = '';
  child.stdout.on('data', (chunk) => {
    stdout += chunk.toString('utf8');
  });
  child.stderr.on('data', (chunk) => {
    stderr += chunk.toString('utf8');
  });
  child.once('error', reject);
  child.once('close', (code) => {
    if (code !== 0) {
      reject(new Error((stderr || stdout || `${command} exit=${code}`).trim()));
      return;
    }
    resolve({ stdout, stderr });
  });
});

export function createDynamicsScheduler({ stateDir, projectDir, configPath, pythonEnvironmentPath, logger, resolveDshCli, resolveModelSelection }) {
  const statePath = join(stateDir, TASK_STATE_FILE);
  const taskConfigPath = join(stateDir, TASK_CONFIG_FILE);
  const runnerPath = join(stateDir, RUNNER_FILE);
  const runnerScriptPath = join(stateDir, RUNNER_SCRIPT_FILE);
  const registerScriptPath = join(stateDir, REGISTER_SCRIPT_FILE);
  let macTimer = null;
  let macSchedule = null;
  let macRunInProgress = false;

  const readState = () => {
    if (!existsSync(statePath)) return null;
    return JSON.parse(readFileSync(statePath, 'utf8'));
  };

  const writeState = (nextState) => {
    mkdirSync(stateDir, { recursive: true });
    writeFileSync(statePath, `${JSON.stringify(nextState, null, 2)}\n`, 'utf8');
  };

  const powershellPath = () => {
    if (typeof process.env.SystemRoot !== 'string' || process.env.SystemRoot.length === 0) {
      throw new Error('Windows SystemRoot 环境变量不存在，无法注册任务计划。');
    }
    return join(process.env.SystemRoot, 'System32', 'WindowsPowerShell', 'v1.0', 'powershell.exe');
  };

  const writeRunnerFiles = (schedule, pythonPath, dshCliPath, modelSelection) => {
    const runnerSource = join(projectDir, 'lib', 'dynamics-scheduled-runner.js');
    if (!existsSync(runnerSource)) throw new Error(`找不到定时运行入口: ${runnerSource}`);
    copyFileSync(runnerSource, runnerPath);
    const runnerConfig = {
      executionMethod: schedule.executionMethod,
      dailyRunTime: schedule.dailyRunTime,
      teamNames: schedule.teamNames,
      interests: schedule.interests,
      stateDir,
      configPath,
      pythonPath,
      projectDir,
      dshExecutable: process.execPath,
      runAsNode: Boolean(process.versions.electron),
      promptPath: join(projectDir, 'prompts', 'duty.md'),
      overlayPath: join(stateDir, 'headless-overlay.yml'),
    };
    if (dshCliPath) runnerConfig.dshCliPath = dshCliPath;
    if (modelSelection) runnerConfig.modelSelection = modelSelection;
    writeFileSync(taskConfigPath, `${JSON.stringify(runnerConfig, null, 2)}\n`, 'utf8');

    const dshHome = dirname(stateDir);
    const runnerLines = [
      `$env:DSH_HOME = ${powerShellLiteral(dshHome)};`,
      `$env:ELECTRON_RUN_AS_NODE = ${powerShellLiteral(process.versions.electron ? '1' : '')};`,
      `& ${powerShellLiteral(process.execPath)} ${powerShellLiteral(runnerPath)};`,
      'exit $LASTEXITCODE;',
    ];
    writePowerShellScript(runnerScriptPath, runnerLines);
  };

  const writeOverlay = (modelSelection) => {
    const lines = [
      '- id: credentials',
      '  disabled: false',
      '- id: authorization',
      '  disabled: false',
      '- id: deepseek-account',
      '  disabled: false',
    ];
    if (modelSelection) {
      lines.push(
        '- id: agent-default-model',
        '  config:',
        `    provider: ${JSON.stringify(modelSelection.provider)}`,
        `    model: ${JSON.stringify(modelSelection.model)}`,
      );
      if (modelSelection.reasoningEffort) lines.push(`    reasoningEffort: ${JSON.stringify(modelSelection.reasoningEffort)}`);
    }
    writeFileSync(join(stateDir, 'headless-overlay.yml'), `${lines.join('\n')}\n`, 'utf8');
  };

  const writeRegisterScript = (dailyRunTime) => {
    const powershell = powershellPath();
    const registerLines = [
      `$taskName = ${powerShellLiteral(TASK_NAME)};`,
      `$runnerScript = ${powerShellLiteral(runnerScriptPath)};`,
      `$powerShell = ${powerShellLiteral(powershell)};`,
      `$runAt = [datetime]::ParseExact(${powerShellLiteral(dailyRunTime)}, 'HH:mm', [Globalization.CultureInfo]::InvariantCulture);`,
      '$actionArguments = "-NoLogo -NoProfile -NonInteractive -WindowStyle Hidden -ExecutionPolicy Bypass -File `"$runnerScript`"";',
      '$action = New-ScheduledTaskAction -Execute $powerShell -Argument $actionArguments;',
      '$trigger = New-ScheduledTaskTrigger -Daily -At $runAt;',
      '$userId = "$env:USERDOMAIN\$env:USERNAME";',
      '$principal = New-ScheduledTaskPrincipal -UserId $userId -LogonType Interactive -RunLevel Limited;',
      'Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $trigger -Principal $principal -Force | Out-Null;',
    ];
    writePowerShellScript(registerScriptPath, registerLines);
    return powershell;
  };

  const registerTask = async (dailyRunTime) => {
    const currentTimeZone = Intl.DateTimeFormat().resolvedOptions().timeZone;
    if (currentTimeZone !== 'Asia/Shanghai') {
      throw new Error(`系统时区为 ${currentTimeZone}，动态日报时间按 Asia/Shanghai 保存；请将 Windows 系统时区设为 Asia/Shanghai。`);
    }
    const powershell = writeRegisterScript(dailyRunTime);
    const result = await runProcess(powershell, ['-NoLogo', '-NoProfile', '-NonInteractive', '-ExecutionPolicy', 'Bypass', '-File', registerScriptPath]);
    if (result.stdout.trim()) logger.info(result.stdout.trim());
    if (result.stderr.trim()) logger.info(result.stderr.trim());
  };

  const removeTask = async () => {
    const powershell = powershellPath();
    const removeScriptPath = join(stateDir, 'dynamics-remove-schedule.ps1');
    const lines = [
      `$taskName = ${powerShellLiteral(TASK_NAME)};`,
      'Unregister-ScheduledTask -TaskName $taskName -Confirm:$false -ErrorAction SilentlyContinue;',
    ];
    writePowerShellScript(removeScriptPath, lines);
    await runProcess(powershell, ['-NoLogo', '-NoProfile', '-NonInteractive', '-ExecutionPolicy', 'Bypass', '-File', removeScriptPath]);
  };

  const stopMacTimer = () => {
    macSchedule = null;
    if (macTimer !== null) clearInterval(macTimer);
    macTimer = null;
  };

  const getShanghaiTime = () => {
    const parts = Object.fromEntries(new Intl.DateTimeFormat('en-CA', {
      timeZone: 'Asia/Shanghai',
      year: 'numeric',
      month: '2-digit',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
      hourCycle: 'h23',
    }).formatToParts(new Date()).map((part) => [part.type, part.value]));
    return {
      date: `${parts.year}-${parts.month}-${parts.day}`,
      time: `${parts.hour}:${parts.minute}`,
    };
  };

  const runMacSchedule = async () => {
    if (!macSchedule || macRunInProgress) return;
    const now = getShanghaiTime();
    if (now.time < macSchedule.dailyRunTime) return;
    const priorState = readState() ?? {};
    if (priorState.last_attempt_date === now.date) return;

    macRunInProgress = true;
    const startedAt = new Date().toISOString();
    try {
      writeState({
        ...priorState,
        last_attempt_at: startedAt,
        last_attempt_date: now.date,
        last_execution_method: macSchedule.executionMethod,
        last_status: 'running',
      });
      const env = {
        ...process.env,
        DSH_HOME: dirname(stateDir),
        ...(process.versions.electron ? { ELECTRON_RUN_AS_NODE: '1' } : {}),
      };
      await runProcess(process.execPath, [runnerPath], { cwd: stateDir, env });
    } catch (error) {
      logger.error(`macOS 定时日报启动失败：${error.stack ?? error}`);
      const currentState = readState() ?? {};
      writeState({
        ...currentState,
        last_finished_at: new Date().toISOString(),
        last_status: 'failed',
        last_error: error.message,
      });
    } finally {
      macRunInProgress = false;
    }
  };

  const startMacTimer = (schedule) => {
    macSchedule = schedule;
    if (macTimer !== null) return;
    // DSH 插件进程休眠或退出时，定时器会暂停；恢复后按当天是否已执行决定是否补跑。
    macTimer = setInterval(() => {
      runMacSchedule().catch((error) => logger.error(`macOS 定时日报检查失败：${error.stack ?? error}`));
    }, 30_000);
    macTimer.unref?.();
    queueMicrotask(() => {
      runMacSchedule().catch((error) => logger.error(`macOS 定时日报检查失败：${error.stack ?? error}`));
    });
  };

  const sync = async (schedule) => {
    const priorState = readState() ?? {};
    const isWindows = process.platform === 'win32';
    const isMacOS = process.platform === 'darwin';
    let schedulerName = 'unsupported';
    if (isWindows) schedulerName = 'windows-task-scheduler';
    if (isMacOS) schedulerName = 'plugin-interval';
    const state = {
      ...priorState,
      scheduler: schedulerName,
      execution_method: schedule.executionMethod,
      daily_run_time: schedule.dailyRunTime,
      time_zone: 'Asia/Shanghai',
      last_sync_at: new Date().toISOString(),
    };
    if (isWindows) state.task_name = TASK_NAME;
    else delete state.task_name;

    try {
      if (!isWindows && !isMacOS) throw new Error(`当前只支持 Windows 和 macOS，未支持系统：${process.platform}。`);
      if (isWindows) {
        const timeZone = Intl.DateTimeFormat().resolvedOptions().timeZone;
        if (timeZone !== 'Asia/Shanghai') throw new Error(`系统时区为 ${timeZone}，动态日报时间按 Asia/Shanghai 保存；请将 Windows 系统时区设为 Asia/Shanghai。`);
      }
      if (schedule.teamNames.length === 0) throw new Error('请先在设置页配置关注球队。');
      if (schedule.interests.length === 0) throw new Error('请先在设置页配置关注内容。');
      if (!existsSync(pythonEnvironmentPath)) throw new Error('本机 Python 环境尚未安装。');
      const pythonEnvironment = JSON.parse(readFileSync(pythonEnvironmentPath, 'utf8'));
      const pythonPath = pythonEnvironment.pythonPath;
      if (typeof pythonPath !== 'string' || pythonPath.length === 0 || !existsSync(pythonPath)) {
        throw new Error('本机 Python 环境路径无效，请重新安装本机环境。');
      }

      let dshCliPath = '';
      let modelSelection = null;
      if (schedule.executionMethod === 'model') {
        dshCliPath = resolveDshCli();
        modelSelection = resolveModelSelection();
        if (!modelSelection) throw new Error('无法读取 DSH 当前模型设置，模型执行任务未注册。');
        writeOverlay(modelSelection);
      }

      writeRunnerFiles(schedule, pythonPath, dshCliPath, modelSelection);
      if (isWindows) await registerTask(schedule.dailyRunTime);
      else startMacTimer(schedule);
      state.registered = true;
      delete state.error;
      logger.info(`自动日报调度已启用：每天 ${schedule.dailyRunTime}（Asia/Shanghai），执行方式=${schedule.executionMethod}，调度器=${schedulerName}。`);
    } catch (error) {
      stopMacTimer();
      if (isWindows) {
        try {
          await removeTask();
        } catch (removeError) {
          logger.error(`清理旧任务计划失败：${removeError.stack ?? removeError}`);
        }
      }
      state.registered = false;
      state.error = error.message;
      logger.error(`自动日报调度未启用：${error.stack ?? error}`);
    }

    writeState(state);
    return state;
  };

  return { readState, sync, dispose: stopMacTimer };
}
