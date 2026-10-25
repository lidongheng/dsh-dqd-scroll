import assert from 'node:assert/strict';
import { mkdtempSync, readFileSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import test from 'node:test';
import { apply } from '../index.js';

const responseObject = () => ({
  headers: {},
  statusCode: 0,
  body: '',
  setHeader(name, value) {
    this.headers[name] = value;
  },
  end(body = '') {
    this.body = body;
  },
});

test('plugin activates against DSH services and saves settings under DSH home', async (context) => {
  const dshHome = mkdtempSync(join(tmpdir(), 'dqd-scroll-activation-'));
  const cleanups = [];
  const routes = [];
  context.after(() => {
    for (const cleanup of cleanups.reverse()) cleanup();
    rmSync(dshHome, { recursive: true, force: true });
  });

  const dshContext = {
    webServer: {
      register(route) {
        routes.push(route);
        return () => {};
      },
    },
    get(key) {
      if (key === 'dshHomePath') return (...segments) => join(dshHome, ...segments);
      return undefined;
    },
    effect(effect) {
      const cleanup = effect();
      if (typeof cleanup === 'function') cleanups.push(cleanup);
    },
  };

  const packageConfigPath = new URL('../config.toml', import.meta.url);
  const packageConfigBefore = readFileSync(packageConfigPath, 'utf8');
  apply(dshContext);

  const route = routes.find((registeredRoute) => registeredRoute.path === '/api/dqd-scroll');
  assert.ok(route);

  const getResponse = responseObject();
  await route.handler({
    method: 'GET',
    url: '/api/dqd-scroll/settings',
    headers: { host: 'localhost:8000' },
  }, getResponse);
  const initialBody = JSON.parse(getResponse.body);
  assert.equal(initialBody.ok, true);
  assert.equal(initialBody.settings.teamNames.length, 0);
  assert.ok(initialBody.availableTeamNames.length > 0);

  const teamName = initialBody.availableTeamNames[0];
  const postBody = Buffer.from(JSON.stringify({
    dailyRunTime: '21:00',
    teamNames: [teamName],
    interests: ['伤病'],
  }));
  const postResponse = responseObject();
  const postRequest = {
    method: 'POST',
    url: '/api/dqd-scroll/settings',
    headers: { host: 'localhost:8000' },
    async *[Symbol.asyncIterator]() {
      yield postBody;
    },
  };
  await route.handler(postRequest, postResponse);

  assert.equal(postResponse.statusCode, 200);
  assert.equal(JSON.parse(postResponse.body).settings.teamNames[0], teamName);
  assert.equal(readFileSync(packageConfigPath, 'utf8'), packageConfigBefore);
  assert.match(readFileSync(join(dshHome, 'dqd-scroll', 'config.toml'), 'utf8'), new RegExp(teamName));
});
