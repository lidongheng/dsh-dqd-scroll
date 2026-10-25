import { spawn } from 'node:child_process';
import { existsSync, mkdirSync, readFileSync, writeFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { registerDqdSettingsApi } from './settings-api.js';


export const name = 'dqd-scroll';
export const inject = ['webServer'];


export function apply(ctx) {
  const projectDir = dirname(fileURLToPath(import.meta.url));
  const configPath = join(projectDir, 'config.toml');
  const statePath = join(projectDir, 'data', 'dynamics-schedule-state.json');
  ctx.effect(() => registerDqdSettingsApi(ctx, projectDir, configPath), 'dqd-scroll 设置页 API');
  let activeChild = null;
  let missingSettingsNoticeDate = null;

  const readDynamicsSchedule = () => {
    const configText = readFileSync(configPath, 'utf8');
    const configLines = configText.split(/\r?\n/);
    const schedule = {};
    let inDynamicsSection = false;
    for (const line of configLines) {
      const sectionMatch = line.match(/^\s*\[([^\]]+)\]\s*$/);
      if (sectionMatch) {
        inDynamicsSection = sectionMatch[1] === 'dynamics';
        continue;
      }
      if (!inDynamicsSection || !line.includes('=')) continue;
      const separatorIndex = line.indexOf('=');
      const key = line.slice(0, separatorIndex).trim();
      const value = line.slice(separatorIndex + 1).trim();
      const arrayValue = value.replace(/\s+#.*$/, '').trim();
      if (key === 'team_names') schedule.team_names_configured = !/^\[\s*\]$/.test(arrayValue);
      if (key === 'interests') schedule.interests_configured = !/^\[\s*\]$/.test(arrayValue);
      if (key === 'daily_run_time' || key === 'python_path') {
        if (!value.startsWith("'") || !value.endsWith("'")) {
          throw new Error(`config.toml 的 dynamics.${key} 必须使用单引号字符串`);
        }
        schedule[key] = value.slice(1, -1);
      }
    }
    if (typeof schedule.daily_run_time !== 'string' || !/^([01]\d|2[0-3]):[0-5]\d$/.test(schedule.daily_run_time)) {
      throw new Error('config.toml 缺少有效的 dynamics.daily_run_time');
    }
    if (typeof schedule.python_path !== 'string' || schedule.python_path.length === 0) {
      throw new Error('config.toml 缺少有效的 dynamics.python_path');
    }
    return schedule;
  };

  const shanghaiDateTime = () => {
    const parts = new Intl.DateTimeFormat('en-CA', {
      timeZone: 'Asia/Shanghai',
      year: 'numeric',
      month: '2-digit',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
      hourCycle: 'h23',
    }).formatToParts(new Date());
    const values = Object.fromEntries(parts.map((part) => [part.type, part.value]));
    return {
      date: `${values.year}-${values.month}-${values.day}`,
      time: `${values.hour}:${values.minute}`,
    };
  };

  const tick = () => {
    try {
      if (activeChild) return;
      const schedule = readDynamicsSchedule();
      const now = shanghaiDateTime();
      if (now.time < schedule.daily_run_time) return;
      if (!schedule.team_names_configured || !schedule.interests_configured) {
        if (missingSettingsNoticeDate !== now.date) {
          console.warn('[dqd-scroll] 请在“刷懂球帝”设置中配置关注球队和关注内容，再生成日报。');
          missingSettingsNoticeDate = now.date;
        }
        return;
      }

      const scheduleState = existsSync(statePath)
        ? JSON.parse(readFileSync(statePath, 'utf8'))
        : {};
      if (scheduleState.last_run_date === now.date) return;

      activeChild = spawn(
        schedule.python_path,
        ['-m', 'dqd_scroll', 'dynamics-report', '--config', configPath],
        {
          cwd: projectDir,
          env: {
            ...process.env,
            PYTHONPATH: join(projectDir, 'src'),
            PYTHONUTF8: '1',
            PYTHONIOENCODING: 'utf-8',
          },
          stdio: ['ignore', 'pipe', 'pipe'],
        },
      );
      activeChild.stdout.on('data', (chunk) => console.log(`[dqd-scroll] ${chunk.toString().trimEnd()}`));
      activeChild.stderr.on('data', (chunk) => console.error(`[dqd-scroll] ${chunk.toString().trimEnd()}`));
      activeChild.on('error', (error) => {
        console.error(`[dqd-scroll] 动态日报启动失败: ${error.message}`);
        activeChild = null;
      });
      activeChild.on('close', (code) => {
        if (code === 0) {
          // 只有日报成功生成后才记录完成；失败时定时器会在下一分钟重试。
          try {
            mkdirSync(dirname(statePath), { recursive: true });
            writeFileSync(statePath, JSON.stringify({ last_run_date: now.date }, null, 2), 'utf8');
          } catch (error) {
            console.error(`[dqd-scroll] 无法保存日报完成状态: ${error.stack ?? error}`);
          }
        }
        console.log(`[dqd-scroll] 动态日报进程结束，exit=${code}`);
        activeChild = null;
      });
    } catch (error) {
      console.error(`[dqd-scroll] 每日动态调度失败: ${error.stack ?? error}`);
    }
  };

  const timer = setInterval(tick, 60_000);
  timer.unref?.();
  tick();
  ctx.effect(() => () => clearInterval(timer), 'dqd-scroll 每日动态日报调度');
}
