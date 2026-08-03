import { APIRequestContext, request as pwRequest } from '@playwright/test';
import { sesionDe } from './_sesion';

const ORIGIN = process.env.ALLOWED_ORIGIN || 'http://localhost:5173';
const BASE = process.env.BASE_URL || 'http://localhost:8099';

// Logs in via the Sanctum SPA flow (csrf-cookie -> /api/login) and returns an
// APIRequestContext whose cookie jar holds the authenticated session.
export async function loginAs(email: string, password: string): Promise<APIRequestContext> {
  // Delegado en _sesion.ts: una sola sesión por cuenta, compartida entre archivos, para no
  // disparar el limitador de intentos de acceso (ver la nota extensa en ese módulo).
  return sesionDe(email, password);
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
