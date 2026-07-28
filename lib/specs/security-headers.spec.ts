// GENERIC — runs against any project, no business knowledge required.
// Response headers are a property of the deployment, so this spec is pure reuse: a new
// target inherits it by importing it, without writing a line.
import { test, expect, request as pwRequest } from '@playwright/test';

const BASE = process.env.BASE_URL || 'http://localhost:8099';
const HEALTH = process.env.HEALTH_PATH || '/';

test.describe('security headers (generic)', () => {
  test('the app is actually up before anything else is measured', async () => {
    const ctx = await pwRequest.newContext({ baseURL: BASE, ignoreHTTPSErrors: true });
    const res = await ctx.get(HEALTH);
    // If this fails, every other dynamic result in the run is meaningless — a clean
    // ZAP report against a dead app looks exactly like a secure app.
    expect(res.status(), `${BASE}${HEALTH} must return 200 for the run to be valid`).toBe(200);
  });

  test('baseline headers are present', async () => {
    const ctx = await pwRequest.newContext({ baseURL: BASE, ignoreHTTPSErrors: true });
    const h = (await ctx.get(HEALTH)).headers();
    const missing: string[] = [];
    if (!h['content-security-policy']) missing.push('Content-Security-Policy');
    if (h['x-content-type-options'] !== 'nosniff') missing.push('X-Content-Type-Options: nosniff');
    if (!h['x-frame-options'] && !/frame-ancestors/.test(h['content-security-policy'] || ''))
      missing.push('X-Frame-Options or CSP frame-ancestors');
    expect(missing, `missing headers: ${missing.join(', ')}`).toEqual([]);
  });

  test('the server does not advertise its stack', async () => {
    const ctx = await pwRequest.newContext({ baseURL: BASE, ignoreHTTPSErrors: true });
    const h = (await ctx.get(HEALTH)).headers();
    const leaks = ['x-powered-by', 'server']
      .filter((k) => h[k] && /\d/.test(h[k]))   // a version number is the part that helps an attacker
      .map((k) => `${k}: ${h[k]}`);
    expect(leaks, `version disclosure: ${leaks.join(', ')}`).toEqual([]);
  });
});
