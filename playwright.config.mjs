import { defineConfig } from '@playwright/test';
export default defineConfig({ testDir: './tests', testMatch: '*.spec.mjs', workers: 1, fullyParallel: false, timeout: 60000, use: { headless: true, launchOptions: { executablePath: process.env.CHROMIUM_EXECUTABLE_PATH || undefined } }, reporter: 'list' });
