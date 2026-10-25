import assert from 'node:assert/strict';
import { spawnSync } from 'node:child_process';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import test from 'node:test';

test('Python report ranges and feed boundaries', () => {
  const projectDir = dirname(dirname(fileURLToPath(import.meta.url)));
  const result = spawnSync('python', ['-m', 'unittest', 'discover', '-s', 'tests/python'], {
    cwd: projectDir, env: { ...process.env, PYTHONPATH: join(projectDir, 'src'), PYTHONUTF8: '1' }, encoding: 'utf8',
  });
  assert.equal(result.status, 0, `${result.error}\n${result.stdout}\n${result.stderr}`);
});
