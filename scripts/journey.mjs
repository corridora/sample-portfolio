import { chromium, expect } from '@playwright/test';
import { readFileSync, existsSync } from 'node:fs';
import { resolve } from 'node:path';
import { assertRumReady } from './browser-observability.mjs';

const root = resolve(import.meta.dirname, '..');
const settings = {};
for (const file of ['config', 'secrets']) {
  const path = resolve(root, '.sample', `${file}.json`);
  if (existsSync(path)) Object.assign(settings, JSON.parse(readFileSync(path, 'utf8')));
}
Object.assign(settings, process.env);
const base = settings.BASE_URL || settings.APP_URL || 'http://127.0.0.1:4105';
const token = settings.DEMO_CONTROL_TOKEN;
if (!token || token.length < 16) throw new Error('DEMO_CONTROL_TOKEN (at least 16 characters) required');
const control = async phase => {
  const response = await fetch(`${base}/api/demo/scenario`, { method: 'POST', headers: { authorization: `Bearer ${token}`, 'content-type': 'application/json' }, body: JSON.stringify({ phase, duration_seconds: 600 }), signal: AbortSignal.timeout(10000) });
  if (!response.ok) throw new Error(`Scenario control returned ${response.status}`);
};
const browser = await chromium.launch({ headless: true, executablePath: settings.CHROMIUM_EXECUTABLE_PATH || undefined, args: ['--disable-dev-shm-usage', '--no-sandbox'] });
const page = await browser.newPage();
if (settings.RUM_BUNDLE_PATH) {
  const scriptOrigin = new URL(settings.CORRIDORA_RUM_SCRIPT_URL || 'https://rum.corridora.com/corridora-rum.js').origin;
  await page.route(`${scriptOrigin}/**`, route => route.fulfill({ contentType: 'text/javascript', body: readFileSync(settings.RUM_BUNDLE_PATH) }));
}
const started = Date.now();
let trace;
try {
  await control('healthy');
  await page.goto(base, { waitUntil: 'networkidle' });
  await assertRumReady(page);
  await expect(page.locator('tbody tr')).toHaveCount(3);
  await page.locator('#revalue').click();
  await expect(page.locator('#state')).toHaveText('Healthy · batched valuation');
  await control('regression');
  await page.locator('#revalue').click();
  await expect(page.locator('#state')).toHaveText('Simulated regression · sequential lookups');
  const bad = await page.evaluate(() => window.portfolioLastResult);
  if (bad.elapsed_ms < 1450 || bad.elapsed_ms > 12000 || bad.total !== 1105.5) throw new Error('Expected bounded 1.5-second regression with unchanged valuation');
  await page.locator('#control').click();
  await expect(page.locator('#state')).toHaveText('Healthy · batched valuation');
  const healthy = await page.evaluate(() => window.portfolioLastResult);
  if (healthy.elapsed_ms >= bad.elapsed_ms - 500) throw new Error('Healthy control did not avoid injected delay');
  await control('recover');
  await page.locator('#revalue').click();
  await expect(page.locator('#state')).toHaveText('Healthy · batched valuation');
  trace = await page.evaluate(() => window.portfolioLastResult.trace_id);
  // Allow RUM's batch processor to send real browser spans.
  await page.waitForTimeout(1500);
  await page.goto('about:blank');
  const heartbeat = await fetch(`${base}/api/demo/heartbeat`, { method: 'POST', headers: { authorization: `Bearer ${token}`, 'content-type': 'application/json' }, body: JSON.stringify({ result: 'passed', trace_id: trace }), signal: AbortSignal.timeout(10000) });
  if (!heartbeat.ok) throw new Error('Heartbeat rejected');
  console.log(JSON.stringify({ result: 'passed', trace_id: trace, regression_ms: Math.round(bad.elapsed_ms), healthy_ms: Math.round(healthy.elapsed_ms), duration_ms: Date.now() - started }));
} finally {
  await control('recover').catch(() => {});
  await browser.close();
}
