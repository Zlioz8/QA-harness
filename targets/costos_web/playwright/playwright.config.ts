import { defineConfig } from '@playwright/test';

// e2e/QA over the RUNNING app. These specs use Playwright's API request context
// (reliable regardless of the SPA's hardcoded origin, finding H17) plus browser
// checks where DOM rendering is what matters.
// Dos raíces: las specs propias del proyecto (tests/) y las genéricas que hereda todo perfil
// (lib/specs/, entre ellas la matriz de autorización). El servicio playwright copia ambas a /run.
export default defineConfig({
  testDir: '.',
  testMatch: ['tests/**/*.spec.ts', 'lib/specs/**/*.spec.ts'],
  timeout: 45_000,
  // Sin reintentos: un fallo intermitente de autorización es un hallazgo, no ruido que ocultar.
  retries: 0,
  // Un solo worker. Cada worker es un proceso con su propia caché de sesiones, así que N workers
  // son N inicios de sesión por rol; con el limitador del login (10/min por email+IP) la suite
  // se autodenegaba con 429 y reportaba fallos de autorización que no existían.
  workers: 1,
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
