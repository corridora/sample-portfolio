import test from 'node:test';
import assert from 'node:assert/strict';
import { dailyWindow, heartbeatCovers } from '../scripts/daily-window.mjs';

test('late UTC schedule remains active across midnight and resets at the next start', () => {
  const window = dailyWindow(new Date('2026-10-12T00:02:00Z'), '23:55');
  assert.equal(new Date(window.start).toISOString(), '2026-10-11T23:55:00.000Z');
  assert.equal(window.day, '2026-10-11');
  assert.equal(dailyWindow(new Date('2026-10-12T23:54:59Z'), '23:55').start, window.start);
  assert.equal(dailyWindow(new Date('2026-10-12T23:55:00Z'), '23:55').start, window.end);
});

test('only a successful heartbeat within the schedule period suppresses replay', () => {
  const window = dailyWindow(new Date('2026-10-12T00:02:00Z'), '23:55');
  assert.equal(heartbeatCovers({ result: 'passed', at: window.start / 1000 - 1 }, window), false);
  assert.equal(heartbeatCovers({ result: 'passed', at: window.start / 1000 }, window), true);
  assert.equal(heartbeatCovers({ result: 'passed', at: window.end / 1000 }, window), false);
  assert.equal(heartbeatCovers({ result: 'failed', at: window.start / 1000 }, window), false);
  assert.equal(heartbeatCovers({ result: 'passed', date: '2026-10-12' }, window), false);
  assert.throws(() => dailyWindow(new Date(), '25:00'), /HH:MM/);
});
