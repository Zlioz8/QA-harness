import { test, expect } from '@playwright/test';
import { loginAs, xsrfHeader, CREDS } from './_auth';

// H5 — stored XSS in FAQ answers must be sanitized server-side.
test('stored answer strips executable HTML (H5)', async () => {
  const admin = await loginAs(CREDS.admin.email, CREDS.admin.pass);
  const payload = '<img src=x onerror=alert(1)><svg onload=alert(2)><b>ok</b>';
  const res = await admin.post('/api/preguntas', {
    headers: await xsrfHeader(admin),
    data: { pregunta: 'q', respuesta: payload },
  });
  expect(res.status()).toBe(201);
  const body = await res.json();
  expect(body.respuesta, 'onerror/onload/script must be removed').not.toMatch(/onerror|onload|<script/i);
  expect(body.respuesta, 'safe markup may remain').toContain('<b>ok</b>');
});
