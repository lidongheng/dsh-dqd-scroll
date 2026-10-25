import assert from 'node:assert/strict';
import { mkdtempSync, readFileSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import test from 'node:test';
import { registerDqdSettingsApi } from '../settings-api.js';

const projectDir = dirname(dirname(fileURLToPath(import.meta.url)));
const setup = (context, runNow) => {
  const stateDir = mkdtempSync(join(tmpdir(), 'dqd-manual-api-'));
  context.after(() => rmSync(stateDir, { recursive: true, force: true }));
  const configPath = join(stateDir, 'config.toml');
  const text = readFileSync(join(projectDir, 'config.toml'), 'utf8')
    .replace('team_names = []', "team_names = ['曼城']")
    .replace('interests = []', "interests = ['伤病']");
  writeFileSync(configPath, text);
  let route;
  registerDqdSettingsApi({ webServer: { register(value) { route = value; } } }, projectDir, configPath, stateDir,
    { runNow, readState: () => ({ registered: true }) }, { logPath: join(stateDir, 'log'), readRecent: () => '' });
  const post = async (body, headers = { host: 'localhost:1234', origin: 'http://localhost:1234' }) => {
    const response = { statusCode: 0, setHeader() {}, end(value) { this.body = JSON.parse(value); } };
    await route.handler({ method: 'POST', url: '/api/dqd-scroll/run-now', headers,
      async *[Symbol.asyncIterator]() { yield Buffer.from(JSON.stringify(body)); } }, response);
    return response;
  };
  return { post, configPath, text };
};

test('run-now passes the exact range and saved settings without rewriting the schedule', async (context) => {
  let captured;
  const fixture = setup(context, async (settings, range) => {
    captured = { settings, range };
    return { last_manual_status: 'succeeded', daily_run_time: '21:00' };
  });
  const range = { since: '2026-10-24T20:35', until: '2026-10-25T20:35' };
  const result = await fixture.post(range);
  assert.equal(result.statusCode, 200);
  assert.deepEqual(captured.range, range);
  assert.deepEqual(captured.settings.teamNames, ['曼城']);
  assert.deepEqual(captured.settings.interests, ['伤病']);
  assert.equal(captured.settings.executionMethod, 'command');
  assert.equal(result.body.scheduleState.last_manual_status, 'succeeded');
  assert.equal(readFileSync(fixture.configPath, 'utf8'), fixture.text);
});

test('invalid or cross-origin manual requests never start a report', async (context) => {
  let calls = 0;
  const { post } = setup(context, async () => { calls += 1; });
  for (const body of [{}, { since: '2026-02-30T12:00', until: '2026-10-25T20:35' }, { since: '2026-10-25T21:00', until: '2026-10-25T20:35' }]) {
    assert.equal((await post(body)).statusCode, 400);
  }
  assert.equal((await post({ since: '2026-10-24T20:35', until: '2026-10-25T20:35' }, {
    host: 'localhost:1234', origin: 'https://example.com',
  })).statusCode, 403);
  assert.equal(calls, 0);
});

test('manual failures and busy responses are returned to the settings page', async (context) => {
  const range = { since: '2026-10-24T20:35', until: '2026-10-25T20:35' };
  const failure = setup(context, async () => { throw new Error('report failed'); });
  assert.equal((await failure.post(range)).statusCode, 500);
  const busy = setup(context, async () => { throw Object.assign(new Error('busy'), { statusCode: 409 }); });
  assert.equal((await busy.post(range)).statusCode, 409);
});
