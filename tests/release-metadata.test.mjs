import assert from 'node:assert/strict';
import { existsSync, readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import test from 'node:test';
import { fileURLToPath } from 'node:url';

const projectDir = dirname(dirname(fileURLToPath(import.meta.url)));
const packageJson = JSON.parse(readFileSync(join(projectDir, 'package.json'), 'utf8'));

test('npm manifest is publishable and declares the public repository', () => {
  assert.equal(packageJson.private, undefined);
  assert.equal(packageJson.publishConfig.access, 'public');
  assert.equal(packageJson.repository.url, 'git+https://github.com/lidongheng/dsh-dqd-scroll.git');
  assert.equal(packageJson.license, 'MIT');
});

test('release file allowlist contains every plugin runtime entry', () => {
  const runtimeFiles = [
    'index.js',
    'client.js',
    'settings-api.js',
    'cordis.patch.yml',
    'config.toml',
    'teams.json',
    'lib/user-data.js',
    'lib/uvfetch.mjs',
    'lib/scheduler.js',
    'lib/dynamics-scheduled-runner.js',
    'lib/dynamics-report-time.mjs',
    'src/dqd_scroll/__main__.py',
    'src/dqd_scroll/cli.py',
    'src/dqd_scroll/api/dqd_api.py',
  ];
  for (const file of runtimeFiles) {
    assert.ok(existsSync(join(projectDir, file)), `${file} does not exist in the source tree`);
  }
  assert.ok(packageJson.files.includes('src/dqd_scroll/*.py'), 'Python package files are missing from the package allowlist');
  assert.ok(packageJson.files.includes('src/dqd_scroll/api/*.py'), 'Python API files are missing from the package allowlist');
  assert.ok(packageJson.files.includes('src/dqd_scroll/lib/*.py'), 'Python library files are missing from the package allowlist');
  for (const file of runtimeFiles.filter((file) => !file.startsWith('src/'))) {
    assert.ok(packageJson.files.includes(file), `${file} is missing from the package allowlist`);
  }
});

test('npm and Python package versions match', () => {
  const metadata = readFileSync(join(projectDir, 'pyproject.toml'), 'utf8');
  assert.equal(metadata.match(/^version = "([^"]+)"/m)[1], packageJson.version);
});
