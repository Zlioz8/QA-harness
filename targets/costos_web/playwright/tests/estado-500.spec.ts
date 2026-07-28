import { test, expect } from '@playwright/test';
import { loginAs, xsrfHeader, CREDS } from './_auth';

// H27 — la ruta `PUT /usuarios/{id}/estado` apuntaba a `cambiarEstado`, método
// inexistente, y devolvía 500. En ea47f371 la ruta fue ELIMINADA, por lo que ya no
// puede producir el error de servidor. Verificamos que no haya 500 ni referencia al
// método. (El cambio de estado se realiza vía `PUT /api/usuarios/{id}`.)
test('estado endpoint no longer throws a server error (H27)', async () => {
  const admin = await loginAs(CREDS.admin.email, CREDS.admin.pass);
  const res = await admin.put('/api/usuarios/2/estado', {
    headers: await xsrfHeader(admin),
    data: { estado: false },
  });
  expect(res.status(), 'no debe haber error 500').not.toBe(500);
  const text = await res.text();
  expect(text).not.toMatch(/cambiarEstado/);
});

// Control: el estado sí se puede cambiar por el endpoint de actualización.
test('estado can be updated through the user update endpoint', async () => {
  const admin = await loginAs(CREDS.admin.email, CREDS.admin.pass);
  const res = await admin.put('/api/usuarios/2', {
    headers: await xsrfHeader(admin),
    data: { estado: true },
  });
  expect([200, 201]).toContain(res.status());
});
