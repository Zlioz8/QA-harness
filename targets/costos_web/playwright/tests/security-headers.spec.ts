import { test, expect, request as pwRequest } from '@playwright/test';

const BASE = process.env.BASE_URL || 'http://localhost:8099';

// Middleware SecurityHeaders (ea47f371) — responde a las alertas de OWASP ZAP.
test('security headers are present and X-Powered-By is removed', async () => {
  const ctx = await pwRequest.newContext({ baseURL: BASE });
  const res = await ctx.get('/up');
  const h = res.headers();

  expect(h['x-content-type-options']).toBe('nosniff');
  expect(h['x-frame-options']).toBe('DENY');
  expect(h['referrer-policy']).toBe('strict-origin-when-cross-origin');
  expect(h['content-security-policy'], 'debe declararse una CSP').toBeTruthy();
  expect(h['permissions-policy']).toBeTruthy();
  expect(h['x-powered-by'], 'no debe filtrar la versión del servidor').toBeUndefined();
});
