import { copyFileSync, existsSync, mkdirSync, readdirSync } from 'node:fs';
import { join } from 'node:path';

const copyDirectory = (sourceDir, targetDir) => {
  mkdirSync(targetDir, { recursive: true });
  for (const entry of readdirSync(sourceDir, { withFileTypes: true })) {
    const sourcePath = join(sourceDir, entry.name);
    const targetPath = join(targetDir, entry.name);
    if (entry.isDirectory()) {
      copyDirectory(sourcePath, targetPath);
      continue;
    }
    if (!entry.isFile()) throw new Error(`不支持迁移非普通文件: ${sourcePath}`);
    copyFileSync(sourcePath, targetPath);
  }
};

export function initializeUserData(projectDir, stateDir) {
  mkdirSync(stateDir, { recursive: true });

  const configPath = join(stateDir, 'config.toml');
  if (!existsSync(configPath)) copyFileSync(join(projectDir, 'config.toml'), configPath);

  const legacyDatabasePath = join(projectDir, 'data', 'dqd_scroll.sqlite3');
  const stateDatabasePath = join(stateDir, 'data', 'dqd_scroll.sqlite3');
  if (!existsSync(stateDatabasePath) && existsSync(legacyDatabasePath)) {
    mkdirSync(join(stateDir, 'data'), { recursive: true });
    copyFileSync(legacyDatabasePath, stateDatabasePath);
  }

  const legacyReportPath = join(projectDir, 'out');
  const stateReportPath = join(stateDir, 'out');
  if (!existsSync(stateReportPath) && existsSync(legacyReportPath)) {
    copyDirectory(legacyReportPath, stateReportPath);
  }

  return configPath;
}
