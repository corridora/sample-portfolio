import { readFileSync } from 'node:fs';
import { spawn } from 'node:child_process';
import { dailyWindow, heartbeatCovers } from './daily-window.mjs';

const data = { ...JSON.parse(readFileSync('.sample/config.json', 'utf8')), ...JSON.parse(readFileSync('.sample/secrets.json', 'utf8')), ...process.env };
const daily = data.DEMO_DAILY_START_UTC || '14:20';
dailyWindow(new Date(), daily); // Reject invalid schedules before entering the timer loop.
let running = false;
let lastAttempt = 0;
async function tick() {
  const now = new Date();
  const window = dailyWindow(now, daily);
  if (running || Date.now() - lastAttempt < 15 * 60 * 1000) return;
  let heartbeat;
  try {
    const response = await fetch(`${data.APP_URL}/api/demo/heartbeat`, { headers: { authorization: `Bearer ${data.DEMO_CONTROL_TOKEN}` }, signal: AbortSignal.timeout(10000) });
    if (!response.ok) throw new Error(`Heartbeat ${response.status}`);
    heartbeat = await response.json();
  } catch (error) { console.error('Heartbeat unavailable:', error.message); }
  if (heartbeatCovers(heartbeat, window)) return;
  // On first daily tick and every missed-heartbeat replay, journey opens a new bounded override and exercises the real browser action.
  running = true; lastAttempt = Date.now();
  console.log('Starting daily/watchdog browser journey', window.day);
  const child = spawn(process.execPath, ['scripts/journey.mjs'], { env: data, stdio: 'inherit' });
  const timeout = setTimeout(() => child.kill('SIGKILL'), 120000);
  child.once('exit', code => { clearTimeout(timeout); running = false; if (code !== 0) console.error('Missing daily heartbeat: next watchdog tick will replay.'); });
  child.once('error', error => { clearTimeout(timeout); running = false; console.error(error.message); });
}
await tick();
setInterval(() => tick().catch(error => console.error(error.message)), 60000);
