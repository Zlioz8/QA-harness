// Project-specific: the trust boundary BETWEEN services, which no scanner models.
//
// Found by reading api_antiplagio/main.py, not by any tool: the analyzer authenticates to the
// API with a shared secret in X-Antiplag-Secret, but the check is skipped entirely when
// PROCESS_STATUS_SECRET is unset — the code logs a warning and continues. So a deployment that
// simply never set the variable exposes /process/status to anyone who can reach the API: mark
// any analysis finished, or inject the report filename.
//
// A DAST crawler cannot find this (it never guesses the header name), and a SAST rule cannot
// judge it (the code is a deliberate, commented compatibility choice). It takes a person who
// read the file — which is exactly the class of finding the migration manual says stays human.
import { test, expect, request as pwRequest } from '@playwright/test';

const API = process.env.API_URL || 'http://localhost:8030';
const SECRET = process.env.PROCESS_STATUS_SECRET || '';

// Shape of models_api/estatus_process.py — see the note in the first test.
const VALID_BODY = {
  id_process: 999999,
  final_state_process: 'finalizado',
  name_antpgl_report: 'lab-probe.pdf',
};

test.describe('service-to-service trust (antiplagio)', () => {
  test('the API is up', async () => {
    const ctx = await pwRequest.newContext({ baseURL: API });
    expect((await ctx.get('/health')).status()).toBe(200);
  });

  test('/process/status rejects a request with no shared secret', async () => {
    test.skip(!SECRET, 'PROCESS_STATUS_SECRET not set in this run — see the finding, not a pass');
    const ctx = await pwRequest.newContext({ baseURL: API });
    const res = await ctx.post('/api/process/status', {
      data: VALID_BODY,
    });
    // The body must be VALID. FastAPI validates the Pydantic model before the handler runs, and
    // the secret is checked inside the handler — so an invalid body returns 422 and never
    // reaches the authentication check. A spec that sends junk here silently tests nothing.
    // (That ordering is also a finding in itself: an unauthenticated caller can map the expected
    // schema by telling 422 from 401.)
    expect([401, 403], `unauthenticated /api/process/status answered ${res.status()}`)
      .toContain(res.status());
  });

  test('/process/status rejects a wrong shared secret', async () => {
    test.skip(!SECRET, 'PROCESS_STATUS_SECRET not set in this run');
    const ctx = await pwRequest.newContext({ baseURL: API });
    const res = await ctx.post('/api/process/status', {
      headers: { 'X-Antiplag-Secret': 'wrong-value' },
      data: VALID_BODY,
    });
    expect([401, 403], `wrong secret answered ${res.status()}`).toContain(res.status());
  });

  test('the API does not advertise an interactive schema', async () => {
    // FastAPI serves /docs and /openapi.json by default. On an internal service reachable from
    // a plugin, that hands an attacker the full request shape for free.
    const ctx = await pwRequest.newContext({ baseURL: API });
    const docs = await ctx.get('/docs');
    const schema = await ctx.get('/openapi.json');
    expect(
      [docs.status(), schema.status()],
      'interactive API documentation is exposed',
    ).toEqual([404, 404]);
  });
});
