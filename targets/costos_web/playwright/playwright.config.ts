import { defineConfig } from '@playwright/test';

// e2e/QA over the RUNNING app. These specs use Playwright's API request context
// (reliable regardless of the SPA's hardcoded origin, finding H17) plus browser
// checks where DOM rendering is what matters.
export default defineConfig({
  testDir: './tests',
  timeout: 30_000,
  reporter: [
    ['line'],
    ['html', { outputFolder: '/reports/html', open: 'never' }],
    ['json', { outputFile: '/reports/results.json' }],
  ],
  use: {
    baseURL: process.env.BASE_URL || 'http://localhost:8099',
    extraHTTPHeaders: { Origin: process.env.ALLOWED_ORIGIN || 'http://localhost:5173' },
    ignoreHTTPSErrors: true,
  },
});
