import assert from 'node:assert/strict';
import { spawnSync } from 'node:child_process';
import { copyFileSync, mkdirSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import test from 'node:test';
import { createDynamicsScheduler } from '../lib/scheduler.js';

const sourceDir = dirname(dirname(fileURLToPath(import.meta.url)));
const manualRange = { since: '2026-09-30T23:45', until: '2026-10-02T08:05' };

const fixture = (context, mode) => {
  const root = mkdtempSync(join(tmpdir(), 'dqd-runner-test-'));
  context.after(() => rmSync(root, { recursive: true, force: true }));
  const projectDir = join(root, 'project');
  const stateDir = join(root, 'state');
  mkdirSync(join(projectDir, 'src', 'dqd_scroll'), { recursive: true });
  mkdirSync(join(projectDir, 'lib'));
  mkdirSync(stateDir);
  writeFileSync(join(projectDir, 'teams.json'), '[]');
  writeFileSync(join(projectDir, 'src', 'dqd_scroll', '__init__.py'), '');
  writeFileSync(join(projectDir, 'src', 'dqd_scroll', '__main__.py'), [
    'import json, os, sys, time;',
    'from pathlib import Path;',
    'time.sleep(0.2);',
    'Path(__file__).resolve().parents[2].joinpath("captured.json").write_text(json.dumps(sys.argv[1:]), encoding="utf-8");',
    'print("report fixture completed");',
    'if "DQD_TEST_EXIT" in os.environ: sys.exit(int(os.environ["DQD_TEST_EXIT"]));',
  ].join('\n'));
  const result = spawnSync('python', ['-c', 'import sys; print(sys.executable)'], { encoding: 'utf8' });
  assert.equal(result.status, 0, `${result.error}\n${result.stderr}`);
  const pythonPath = result.stdout.trim();
  const modelCli = join(root, 'model.mjs');
  writeFileSync(modelCli, `import { writeFileSync } from 'node:fs';\nwriteFileSync(${JSON.stringify(join(root, 'model-args.json'))}, JSON.stringify(process.argv.slice(2)));\n`);
  const config = {
    executionMethod: mode, stateDir, projectDir, pythonPath, configPath: join(root, 'config.toml'),
    dshExecutable: process.execPath, dshCliPath: modelCli, runAsNode: false,
    promptPath: join(sourceDir, 'prompts', 'duty.md'), overlayPath: join(root, 'overlay.yml'),
  };
  for (const file of ['dynamics-scheduled-runner.js', 'dynamics-report-time.mjs']) {
    copyFileSync(join(sourceDir, 'lib', file), join(projectDir, 'lib', file));
  }
  const runnerPath = join(stateDir, 'dynamics-scheduled-runner.mjs');
  copyFileSync(join(sourceDir, 'lib', 'dynamics-scheduled-runner.js'), runnerPath);
  copyFileSync(join(sourceDir, 'lib', 'dynamics-report-time.mjs'), join(stateDir, 'dynamics-report-time.mjs'));
  writeFileSync(join(stateDir, 'dynamics-scheduled-config.json'), JSON.stringify(config));
  const statePath = join(stateDir, 'dynamics-schedule-state.json');
  const automaticState = { registered: true, daily_run_time: '21:00', last_attempt_date: '2026-10-24', last_run_date: '2026-10-24', last_status: 'succeeded', last_error: 'scheduled error', last_manual_error: 'old manual error' };
  writeFileSync(statePath, JSON.stringify(automaticState));
  const readState = () => JSON.parse(readFileSync(statePath, 'utf8'));
  const run = (args, env = process.env) => spawnSync(process.execPath, [runnerPath, ...args], {
    cwd: root, env, encoding: 'utf8', timeout: 10_000,
  });
  return { root, projectDir, stateDir, config, statePath, automaticState, readState, run };
};

for (const mode of ['command', 'model']) {
  test(`${mode}: custom range reaches the child unchanged and preserves automatic execution flags`, (context) => {
    const f = fixture(context, mode);
    const result = f.run(['--since', manualRange.since, '--until', manualRange.until]);
    assert.equal(result.status, 0, `${result.error}\n${result.stderr}`);
    const state = f.readState();
    assert.equal(state.last_manual_status, 'succeeded');
    assert.equal(state.last_manual_since, manualRange.since);
    assert.equal(state.last_manual_until, manualRange.until);
    assert.equal(state.last_run_date, f.automaticState.last_run_date);
    assert.equal(state.last_attempt_date, f.automaticState.last_attempt_date);
    assert.equal(state.last_error, 'scheduled error');
    assert.equal(state.last_manual_error, undefined);
    if (mode === 'command') {
      const args = JSON.parse(readFileSync(join(f.projectDir, 'captured.json'), 'utf8'));
      assert.equal(args[args.indexOf('--since') + 1], manualRange.since);
      assert.equal(args[args.indexOf('--until') + 1], manualRange.until);
    } else {
      const args = JSON.parse(readFileSync(join(f.root, 'model-args.json'), 'utf8'));
      assert.deepEqual(args.slice(0, 2), ['--profile', 'headless']);
      assert.ok(args.at(-1).includes(`--since ${manualRange.since} --until ${manualRange.until}`));
    }
  });

  test(`${mode}: automatic runner fixes one trailing 24-hour range before starting its child`, (context) => {
    const f = fixture(context, mode);
    const result = f.run([]);
    assert.equal(result.status, 0, `${result.error}\n${result.stderr}`);
    const state = f.readState();
    assert.equal(state.last_status, 'succeeded');
    assert.equal(Date.parse(`${state.last_until}+08:00`) - Date.parse(`${state.last_since}+08:00`), 86_400_000);
    if (mode === 'model') {
      const args = JSON.parse(readFileSync(join(f.root, 'model-args.json'), 'utf8'));
      assert.ok(args.at(-1).includes(`--since ${state.last_since} --until ${state.last_until}`));
    }
  });
}

test('manual child failure records a separate failure and leaves automatic state intact', (context) => {
  const f = fixture(context, 'command');
  const result = f.run(['--since', manualRange.since, '--until', manualRange.until], { ...process.env, DQD_TEST_EXIT: '1' });
  assert.equal(result.status, 1);
  const state = f.readState();
  assert.equal(state.last_manual_status, 'failed');
  assert.equal(state.last_manual_exit_code, 1);
  assert.equal(state.last_status, 'succeeded');
});

test('scheduler starts a manual report without registering a task and rejects duplicate clicks', async (context) => {
  const f = fixture(context, 'command');
  const environmentPath = join(f.root, 'python-environment.json');
  writeFileSync(environmentPath, JSON.stringify({ pythonPath: f.config.pythonPath }));
  const scheduler = createDynamicsScheduler({
    stateDir: f.stateDir, projectDir: f.projectDir, configPath: f.config.configPath,
    pythonEnvironmentPath: environmentPath, logger: { info() {}, error() {} },
  });
  const settings = { dailyRunTime: '21:00', executionMethod: 'command', teamNames: ['曼城'], interests: ['伤病'] };
  const first = scheduler.runNow(settings, manualRange);
  await assert.rejects(scheduler.runNow(settings, manualRange), (error) => error.statusCode === 409);
  const state = await first;
  assert.equal(state.last_manual_status, 'succeeded');
  assert.equal(state.daily_run_time, '21:00');
  assert.equal(state.last_run_date, f.automaticState.last_run_date);
});

test('a failed manual launch returns an actionable error and permits a retry', async (context) => {
  const f = fixture(context, 'command');
  const environmentPath = join(f.root, 'python-environment.json');
  writeFileSync(environmentPath, JSON.stringify({ pythonPath: f.config.pythonPath }));
  const scheduler = createDynamicsScheduler({
    stateDir: f.stateDir, projectDir: f.projectDir, configPath: f.config.configPath,
    pythonEnvironmentPath: environmentPath, logger: { info() {}, error() {} },
  });
  const settings = { dailyRunTime: '21:00', executionMethod: 'command', teamNames: ['曼城'], interests: ['伤病'] };
  writeFileSync(join(f.projectDir, 'src', 'dqd_scroll', '__main__.py'), 'raise SystemExit(1);');
  await assert.rejects(scheduler.runNow(settings, manualRange), /请查看运行日志/);
  writeFileSync(join(f.projectDir, 'src', 'dqd_scroll', '__main__.py'), 'print("recovered");');
  assert.equal((await scheduler.runNow(settings, manualRange)).last_manual_status, 'succeeded');
});
