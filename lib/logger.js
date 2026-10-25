import { appendFileSync, existsSync, mkdirSync, readFileSync, renameSync, statSync, unlinkSync } from 'node:fs';
import { join } from 'node:path';

const MAX_LOG_BYTES = 2 * 1024 * 1024;

export function createDqdLogger(stateDir, hostLogger) {
  const logPath = join(stateDir, 'dqd-scroll.log');

  const write = (level, message) => {
    const line = `${new Date().toISOString()} [${level.toUpperCase()}] ${message}`;
    try {
      mkdirSync(stateDir, { recursive: true });
      if (existsSync(logPath) && statSync(logPath).size > MAX_LOG_BYTES) {
        const previousLogPath = `${logPath}.1`;
        if (existsSync(previousLogPath)) unlinkSync(previousLogPath);
        renameSync(logPath, previousLogPath);
      }
      appendFileSync(logPath, `${line}\n`, 'utf8');
    } catch (error) {
      try {
        hostLogger?.error?.(`[dqd-scroll] 无法写入日志 ${logPath}: ${error.message}`);
      } catch {
        // 日志落盘失败时不影响 DSH 宿主运行。
      }
    }
    try {
      hostLogger?.[level]?.(`[dqd-scroll] ${message}`);
    } catch {
      // DSH logger 不可用时仍保留运行目录日志。
    }
  };

  const readRecent = (lineLimit) => {
    if (!existsSync(logPath)) return '';
    return readFileSync(logPath, 'utf8').split(/\r?\n/).filter(Boolean).slice(-lineLimit).join('\n');
  };

  return {
    info: (message) => write('info', message),
    error: (message) => write('error', message),
    logPath,
    readRecent,
  };
}
