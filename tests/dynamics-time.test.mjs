import assert from 'node:assert/strict';
import test from 'node:test';
import { rollingReportRange, validateManualRange } from '../lib/dynamics-report-time.mjs';

test('automatic range crosses Shanghai midnight and covers the preceding 24 hours', () => {
  assert.deepEqual(rollingReportRange(new Date('2026-10-24T16:15:26Z')), {
    since: '2026-10-24T00:15:26', until: '2026-10-25T00:15:26',
  });
  assert.deepEqual(rollingReportRange(new Date('2024-02-29T16:00:00Z')), {
    since: '2024-02-29T00:00:00', until: '2024-03-01T00:00:00',
  });
});

test('custom minute range is preserved without browser-local timezone conversion', () => {
  const range = { since: '2024-02-29T08:05', until: '2024-03-01T09:06' };
  assert.deepEqual(validateManualRange(range), range);
});

test('custom ranges reject missing values, impossible dates, seconds and timezone suffixes', () => {
  for (const since of [undefined, '', '2026-02-29T12:00', '2026-02-30T12:00', '2026-13-01T12:00', '2026-10-25T24:00', '0000-01-01T00:00', '2026-10-25T12:00:01', '2026-10-25T12:00Z']) {
    assert.throws(() => validateManualRange({ since, until: '2026-12-31T23:59' }));
  }
  assert.throws(() => validateManualRange(null));
  assert.throws(() => validateManualRange({ since: '2026-10-25T12:00' }));
  for (const until of ['2026-10-25T12:00', '2026-10-24T12:00']) {
    assert.throws(() => validateManualRange({ since: '2026-10-25T12:00', until }), /开始时间必须早于结束时间/);
  }
});
