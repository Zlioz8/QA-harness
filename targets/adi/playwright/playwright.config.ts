import { defineConfig } from '@playwright/test';

// Dos raíces de pruebas: las propias del perfil y las genéricas de lib/specs que hereda todo
// proyecto (cabeceras y matriz de autorización). El servicio playwright las copia juntas en /run.
export default defineConfig({
  testDir: '.',
  testMatch: ['tests/**/*.spec.ts', 'lib/specs/**/*.spec.ts'],
  timeout: 45_000,
  // UN worker. ADI bloquea la IP tras 5 intentos fallidos durante 15 minutos
  // ("ADI".login_attempts): varios workers autenticando en paralelo agotan ese contador y la
  // suite se autodeniega, reportando como fallo de autorización lo que solo es su propio ritmo.
  workers: 1,
  reporter: [
    ['line'],
    ['html', { outputFolder: '/reports/html', open: 'never' }],
    ['json', { outputFile: '/reports/results.json' }],
  ],
  use: {
    baseURL: process.env.BASE_URL || 'http://localhost:8090',
    ignoreHTTPSErrors: true,
  },
});
