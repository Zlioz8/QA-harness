import { test, expect } from '@playwright/test';
import { loginAs, xsrfHeader, CREDS } from './_auth';

// H1 / H2 — a representative (rol 4) must NOT be able to manage users or escalate.
test.describe('Authorization matrix (backend is the authority)', () => {
  test('rep cannot create an admin user (H2)', async () => {
    const rep = await loginAs(CREDS.rep.email, CREDS.rep.pass);
    const res = await rep.post('/api/usuarios', {
      headers: await xsrfHeader(rep),
      data: { nombre: 'x', email: 'evil@test.local', documento: '999', rol_id: 1, contrasena: 'x' },
    });
    expect(res.status(), 'creating rol_id=1 as rep must be forbidden').toBe(403);
  });

  test('rep cannot delete users (H1)', async () => {
    const rep = await loginAs(CREDS.rep.email, CREDS.rep.pass);
    const res = await rep.delete('/api/usuarios/1', { headers: await xsrfHeader(rep) });
    expect(res.status()).toBe(403);
  });

  // Control: admin authorization works on a lightweight admin-only endpoint.
  // (We deliberately avoid /api/usuarios here — see usuarios-oom.spec.ts, it OOMs
  // on the real dataset. Using a heavy endpoint would conflate authz with H19/H20.)
  test('admin CAN reach an admin-only endpoint (control)', async () => {
    const admin = await loginAs(CREDS.admin.email, CREDS.admin.pass);
    const res = await admin.get('/api/roles');
    expect(res.status()).toBe(200);
  });
});
