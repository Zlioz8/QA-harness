import { defineConfig } from '@playwright/test';

// Two test roots: the target's own specs (business logic) and the generic ones from lib/specs
// that every project inherits. Copied side by side into /run by the playwright service.
export default defineConfig({
  testDir: '.',
  testMatch: ['tests/**/*.spec.ts', 'lib/specs/**/*.spec.ts'],
  timeout: 45_000,
  reporter: [
    ['line'],
    ['html', { outputFolder: '/reports/html', open: 'never' }],
    ['json', { outputFile: '/reports/results.json' }],
  ],
  use: {
    baseURL: process.env.BASE_URL || 'http://localhost:8082',
    ignoreHTTPSErrors: true,
  },
});
