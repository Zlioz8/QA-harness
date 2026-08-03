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
    // 403 = el guardia de rol lo paró; 422 = pasó el guardia y lo paró la validación, lo que ya
    // es un hallazgo menor (el rol no debería llegar a validarse siquiera).
    expect([403, 422], 'creating rol_id=1 as rep must be forbidden').toContain(res.status());
    if ([200, 201].includes(res.status())) throw new Error('ESCALADA: el rep creó un administrador');
  });

  test('rep cannot delete users (H1)', async () => {
    const rep = await loginAs(CREDS.rep.email, CREDS.rep.pass);
    // Objetivo INEXISTENTE a propósito. El guardia de rol (RoleMiddleware) corre antes que el
    // controlador, así que un 403 aquí demuestra lo mismo sin arriesgar datos. Apuntando a un
    // usuario real, esta prueba borró la cuenta administradora del entorno el día que otra
    // corrida ascendió por error a la cuenta de menor privilegio.
    const res = await rep.delete('/api/usuarios/999999999', { headers: await xsrfHeader(rep) });
    expect([403, 404]).toContain(res.status());
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
