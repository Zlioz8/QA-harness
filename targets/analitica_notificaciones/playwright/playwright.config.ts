import { defineConfig } from '@playwright/test';

// Dos raíces de pruebas: las propias del perfil y las genéricas de lib/specs que hereda todo
// proyecto (cabeceras y matriz de autorización). El servicio playwright las copia juntas en /run.
export default defineConfig({
  testDir: '.',
  testMatch: ['tests/**/*.spec.ts', 'lib/specs/**/*.spec.ts'],
  timeout: 45_000,
  // UN worker. El login pasa por Moodle (login/token.php) contra un Moodle de PRODUCCIÓN
  // compartido: varios workers autenticando en paralelo multiplican esa carga y arriesgan que
  // Moodle limite la emisión de tokens, lo que la suite leería como fallo de autorización.
  // Además lib/auth memoiza una sesión por rol, así que un worker basta y sobra.
  workers: 1,
  reporter: [
    ['line'],
    ['html', { outputFolder: '/reports/html', open: 'never' }],
    ['json', { outputFile: '/reports/results.json' }],
  ],
  use: {
    baseURL: process.env.BASE_URL || 'http://localhost:8089',
    ignoreHTTPSErrors: true,
  },
});
