import { existsSync, readFileSync, readdirSync } from 'node:fs';
import { createRequire } from 'node:module';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { registerDqdSettingsApi, migrateExecutionMethod, readDqdSettings } from './settings-api.js';
import { createDqdLogger } from './lib/logger.js';
import { createDynamicsScheduler } from './lib/scheduler.js';
import { initializeUserData } from './lib/user-data.js';

export const name = 'dqd-scroll';
export const inject = ['webServer'];

export function apply(ctx) {
  const projectDir = dirname(fileURLToPath(import.meta.url));
  const dshHomePath = ctx.get('dshHomePath');
  let stateDir = '';
  if (typeof dshHomePath === 'function') stateDir = dshHomePath('dqd-scroll');
  if (typeof dshHomePath === 'string' && dshHomePath.length > 0) stateDir = join(dshHomePath, 'dqd-scroll');
  if (typeof stateDir !== 'string' || stateDir.length === 0) {
    throw new Error('DSH 未提供有效的 dshHomePath，无法确定本机运行环境目录。');
  }

  const configPath = initializeUserData(projectDir, stateDir);
  const logger = createDqdLogger(stateDir, ctx.logger);
  if (migrateExecutionMethod(configPath)) logger.info('已将原有日报执行方式迁移为 command，保留此前的命令运行行为。');

  const scanForDsh = (directory, depth, budget) => {
    if (depth > 7 || budget.count > 4000) return '';
    let entries = [];
    try {
      entries = readdirSync(directory, { withFileTypes: true });
    } catch {
      return '';
    }
    for (const entry of entries) {
      if (!entry.isDirectory()) continue;
      budget.count += 1;
      if (budget.count > 4000) return '';
      const childDirectory = join(directory, entry.name);
      if (entry.name === 'dsh') {
        const cliPath = join(childDirectory, 'lib', 'bin.js');
        if (existsSync(cliPath)) return cliPath;
      }
      const result = scanForDsh(childDirectory, depth + 1, budget);
      if (result) return result;
    }
    return '';
  };

  const resolveDshCli = () => {
    const entryPath = process.argv[1];
    if (typeof entryPath === 'string' && existsSync(entryPath) && /[\\/]@deepseek-ai[\\/]dsh[\\/]lib[\\/]bin\.js$/i.test(entryPath)) {
      return entryPath;
    }

    const require = createRequire(import.meta.url);
    try {
      const entry = require.resolve('@deepseek-ai/dsh/lib/bin.js');
      if (existsSync(entry)) return entry;
    } catch {
      // 继续通过已安装的 DSH 包入口定位命令行文件。
    }

    try {
      let directory = dirname(require.resolve('@deepseek-ai/dsh'));
      for (let depth = 0; depth < 6; depth += 1) {
        const manifestPath = join(directory, 'package.json');
        if (existsSync(manifestPath)) {
          const manifest = JSON.parse(readFileSync(manifestPath, 'utf8'));
          if (manifest.name === '@deepseek-ai/dsh') {
            let relativeCliPath = '';
            if (typeof manifest.bin === 'string') relativeCliPath = manifest.bin;
            if (manifest.bin && typeof manifest.bin.dsh === 'string') relativeCliPath = manifest.bin.dsh;
            if (relativeCliPath.length === 0) throw new Error('DSH npm 包没有声明 dsh 命令行入口。');
            const cliPath = join(directory, relativeCliPath);
            if (existsSync(cliPath)) return cliPath;
            break;
          }
        }
        const parentDirectory = dirname(directory);
        if (parentDirectory === directory) break;
        directory = parentDirectory;
      }
    } catch {
      // 下面给出明确的 CLI 定位错误，不使用裸 dsh 命令猜测路径。
    }
    const roots = [];
    if (typeof process.resourcesPath === 'string') roots.push(process.resourcesPath);
    roots.push(join(dirname(process.execPath), 'resources'));
    const visitedRoots = new Set();
    for (const root of roots) {
      if (!existsSync(root) || visitedRoots.has(root)) continue;
      visitedRoots.add(root);
      const cliPath = scanForDsh(root, 0, { count: 0 });
      if (cliPath) return cliPath;
    }
    throw new Error('无法从当前 npm 安装位置或 DSH 应用目录解析命令行入口。');
  };

  const resolveModelSelection = () => {
    const selection = ctx.get('agentDefaultModel')?.currentSelection?.();
    if (!selection || typeof selection !== 'object') return null;
    let provider = selection.provider;
    if (typeof provider !== 'string') provider = selection.providerId;
    let model = selection.model;
    if (typeof model !== 'string') model = selection.modelId;
    if (typeof provider !== 'string' || provider.length === 0 || typeof model !== 'string' || model.length === 0) return null;
    const result = { provider, model };
    if (typeof selection.reasoningEffort === 'string') result.reasoningEffort = selection.reasoningEffort;
    return result;
  };

  const scheduler = createDynamicsScheduler({
    stateDir,
    projectDir,
    configPath,
    pythonEnvironmentPath: join(stateDir, 'python-environment.json'),
    logger,
    resolveDshCli,
    resolveModelSelection,
  });

  ctx.effect(() => registerDqdSettingsApi(ctx, projectDir, configPath, stateDir, scheduler, logger), 'dqd-scroll 设置页 API');
  ctx.effect(() => () => scheduler.dispose(), 'dqd-scroll 插件定时器');
  try {
    scheduler.sync(readDqdSettings(configPath)).catch((error) => logger.error(`初始化自动日报调度失败：${error.stack ?? error}`));
  } catch (error) {
    logger.error(`读取自动日报设置失败：${error.stack ?? error}`);
  }
}
