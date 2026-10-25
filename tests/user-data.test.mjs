import assert from 'node:assert/strict';
import { mkdtempSync, mkdirSync, readFileSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import test from 'node:test';
import { initializeUserData } from '../lib/user-data.js';

const createDirectories = () => {
  const root = mkdtempSync(join(tmpdir(), 'dqd-scroll-test-'));
  const projectDir = join(root, 'project');
  const stateDir = join(root, 'dsh-home', 'dqd-scroll');
  mkdirSync(projectDir, { recursive: true });
  return { root, projectDir, stateDir };
};

test('first run copies configuration and migrates existing database and reports', (context) => {
  const { root, projectDir, stateDir } = createDirectories();
  context.after(() => rmSync(root, { recursive: true, force: true }));

  writeFileSync(join(projectDir, 'config.toml'), "database_path = 'data/dqd_scroll.sqlite3'\n", 'utf8');
  mkdirSync(join(projectDir, 'data'), { recursive: true });
  writeFileSync(join(projectDir, 'data', 'dqd_scroll.sqlite3'), 'legacy database', 'utf8');
  mkdirSync(join(projectDir, 'out', 'dynamics'), { recursive: true });
  writeFileSync(join(projectDir, 'out', 'dynamics', 'report.md'), 'legacy report', 'utf8');

  const configPath = initializeUserData(projectDir, stateDir);

  assert.equal(configPath, join(stateDir, 'config.toml'));
  assert.equal(readFileSync(configPath, 'utf8'), "database_path = 'data/dqd_scroll.sqlite3'\n");
  assert.equal(readFileSync(join(stateDir, 'data', 'dqd_scroll.sqlite3'), 'utf8'), 'legacy database');
  assert.equal(readFileSync(join(stateDir, 'out', 'dynamics', 'report.md'), 'utf8'), 'legacy report');
  assert.equal(readFileSync(join(projectDir, 'data', 'dqd_scroll.sqlite3'), 'utf8'), 'legacy database');
});

test('subsequent startup preserves configuration, database, and reports in DSH home', (context) => {
  const { root, projectDir, stateDir } = createDirectories();
  context.after(() => rmSync(root, { recursive: true, force: true }));

  writeFileSync(join(projectDir, 'config.toml'), "database_path = 'data/dqd_scroll.sqlite3'\n", 'utf8');
  mkdirSync(join(stateDir, 'data'), { recursive: true });
  mkdirSync(join(stateDir, 'out'), { recursive: true });
  writeFileSync(join(stateDir, 'config.toml'), 'user settings', 'utf8');
  writeFileSync(join(stateDir, 'data', 'dqd_scroll.sqlite3'), 'user database', 'utf8');
  writeFileSync(join(stateDir, 'out', 'report.md'), 'user report', 'utf8');
  mkdirSync(join(projectDir, 'data'), { recursive: true });
  writeFileSync(join(projectDir, 'data', 'dqd_scroll.sqlite3'), 'old database', 'utf8');

  initializeUserData(projectDir, stateDir);

  assert.equal(readFileSync(join(stateDir, 'config.toml'), 'utf8'), 'user settings');
  assert.equal(readFileSync(join(stateDir, 'data', 'dqd_scroll.sqlite3'), 'utf8'), 'user database');
  assert.equal(readFileSync(join(stateDir, 'out', 'report.md'), 'utf8'), 'user report');
});
