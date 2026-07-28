import { test, expect, request as pwRequest } from '@playwright/test';
import { loginAs, CREDS } from './_auth';

const BASE = process.env.BASE_URL || 'http://localhost:8099';

// H8 — /delegados/soporte must require auth (no PII to anonymous callers).
test('delegado soporte returns no PII without a session (H8)', async () => {
  const anon = await pwRequest.newContext({ baseURL: BASE });
  const res = await anon.get('/api/delegados/soporte?dependencia_id=1');
  expect(res.status(), 'must not be a 200 with delegado data').not.toBe(200);
  const text = await res.text();
  expect(text).not.toMatch(/@sena\.edu\.co/);
});

// H10 — CORS must not reflect arbitrary origins.
test('CORS does not allow an arbitrary origin (H10)', async () => {
  const anon = await pwRequest.newContext({ baseURL: BASE });
  const res = await anon.fetch('/api/login', {
    method: 'OPTIONS',
    headers: { Origin: 'http://evil.com', 'Access-Control-Request-Method': 'POST' },
  });
  const acao = res.headers()['access-control-allow-origin'];
  expect(acao ?? '', 'evil.com must not be echoed back').not.toBe('http://evil.com');
});
