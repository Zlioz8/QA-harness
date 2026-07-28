import { test, expect } from '@playwright/test';
import { loginAs, CREDS } from './_auth';

// H19 / H20 — el listado de usuarios debe estar paginado en servidor.
// Antes (2f0c54be) `->get()` sobre ~20k filas agotaba la memoria (500 OOM).
// Desde ea47f371 usa `paginate()`, por lo que debe responder 200 con envoltura
// de paginación y NO devolver la tabla completa.
test('user listing is paginated and responds OK (H19/H20)', async () => {
  const admin = await loginAs(CREDS.admin.email, CREDS.admin.pass);
  const res = await admin.get('/api/usuarios?per_page=10');
  expect(res.status(), 'el listado paginado debe responder 200').toBe(200);

  const body = await res.json();
  expect(body).toHaveProperty('data');
  expect(body).toHaveProperty('total');
  expect(Array.isArray(body.data)).toBe(true);
  expect(body.data.length, 'debe respetar per_page').toBeLessThanOrEqual(10);
  expect(body.total, 'el total refleja el dataset real completo').toBeGreaterThan(1000);
});
