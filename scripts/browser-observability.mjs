export async function assertRumReady(page, timeout = 10000) {
  if (!await page.locator('script[data-service="sample-portfolio-web"]').count()) return;
  await page.waitForFunction(() => ['ready', 'failed'].includes(window.CorridoraRum?.getInitializationStatus?.()), undefined, { timeout });
  const status = await page.evaluate(() => window.CorridoraRum?.getInitializationStatus?.());
  if (status !== 'ready') throw new Error('Configured Corridora RUM failed to initialize; journey heartbeat withheld');
}
