import { APIRequestContext, request as pwRequest } from '@playwright/test';

const ORIGIN = process.env.ALLOWED_ORIGIN || 'http://localhost:5173';
const BASE = process.env.BASE_URL || 'http://localhost:8099';

// Logs in via the Sanctum SPA flow (csrf-cookie -> /api/login) and returns an
// APIRequestContext whose cookie jar holds the authenticated session.
export async function loginAs(email: string, password: string): Promise<APIRequestContext> {
  const ctx = await pwRequest.newContext({ baseURL: BASE, extraHTTPHeaders: { Origin: ORIGIN } });
  await ctx.get('/sanctum/csrf-cookie');
  const state = await ctx.storageState();
  const raw = state.cookies.find((c) => c.name === 'XSRF-TOKEN')?.value ?? '';
  const xsrf = decodeURIComponent(raw);
  const res = await ctx.post('/api/login', {
    headers: { 'X-XSRF-TOKEN': xsrf, 'Content-Type': 'application/json' },
    data: { email, password },
  });
  if (res.status() !== 200) throw new Error(`login failed for ${email}: ${res.status()}`);
  return ctx;
}

export async function xsrfHeader(ctx: APIRequestContext): Promise<Record<string, string>> {
  const state = await ctx.storageState();
  const raw = state.cookies.find((c) => c.name === 'XSRF-TOKEN')?.value ?? '';
  return { 'X-XSRF-TOKEN': decodeURIComponent(raw) };
}

export const CREDS = {
  admin: { email: process.env.ADMIN_EMAIL || 'admin@test.local', pass: process.env.ADMIN_PASS || 'secret123' },
  rep: { email: process.env.REP_EMAIL || 'rep@test.local', pass: process.env.REP_PASS || 'secret123' },
};
