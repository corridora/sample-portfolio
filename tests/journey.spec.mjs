import { test, expect } from '@playwright/test';
import { readFileSync } from 'node:fs';
import { assertRumReady } from '../scripts/browser-observability.mjs';

test('HTMX positions and genuine RUM CLIENT → Laravel SERVER correlation', async ({ browser }) => {
  const base = process.env.BASE_URL || 'http://127.0.0.1:4105';
  const bundle = process.env.RUM_BUNDLE_PATH;
  test.skip(!bundle || !process.env.OTLP_CAPTURE_URL, 'Set RUM_BUNDLE_PATH and OTLP_CAPTURE_URL; use python3 tests/run_validation.py');
  const page = await browser.newPage();
  await page.route('https://rum.corridora.com/**', route => route.fulfill({ contentType: 'text/javascript', body: readFileSync(bundle) }));
  await page.goto(base);
  await assertRumReady(page);
  await expect(page.locator('tbody tr')).toHaveCount(3);
  await page.locator('#revalue').click();
  await expect(page.locator('#total')).toHaveText('$1,105.50');
  await expect(page.locator('#state')).toHaveText('Healthy · batched valuation');
  const result = await page.evaluate(() => window.portfolioLastResult);
  await page.waitForTimeout(2000);
  await page.goto('about:blank');
  await page.waitForTimeout(400);
  const records = await (await fetch(process.env.OTLP_CAPTURE_URL + '/records')).json();
  const spans = records.filter(record => record.path === '/v1/traces').flatMap(record => record.body.resourceSpans || []).flatMap(resource => resource.scopeSpans || []).flatMap(scope => scope.spans || []);
  const server = spans.find(span => span.name === 'GET api/valuation' && normalize(span.traceId) === result.trace_id);
  expect(server, 'Captured SDK SERVER span').toBeTruthy();
  const client = spans.find(span => normalize(span.spanId) === normalize(server.parentSpanId) && normalize(span.traceId) === normalize(server.traceId) && (span.kind === 3 || span.kind === 'SPAN_KIND_CLIENT'));
  expect(client, 'Actual Corridora RUM CLIENT is the SERVER parent').toBeTruthy();
  const action = spans.find(span => span.name === 'portfolio.revalue' && normalize(span.spanId) === normalize(client.parentSpanId));
  expect(action, 'Manual OTel HTMX action parents RUM CLIENT').toBeTruthy();
  console.log('Verified real browser/client and Laravel server parentage:', result.trace_id);
  await page.close();
  const broken = await browser.newPage();
  await broken.route('https://rum.corridora.com/**', route => route.abort());
  await broken.goto(base);
  await expect(assertRumReady(broken, 250)).rejects.toThrow();
  await broken.close();
});
function normalize(value) {
  if (!value) return '';
  return /^[0-9a-f]{16,32}$/i.test(value) ? value.toLowerCase() : Buffer.from(value, 'base64').toString('hex');
}
