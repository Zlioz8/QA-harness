// GENERIC ENGINE, PROJECT-SUPPLIED POLICY.
//
// This is the dividing line the migration manual is about: executing an authorization
// matrix is fully automatable; *knowing* the matrix never is. No scanner can tell whether
// a 200 is correct — that depends on what the institution decided this role may see.
//
// So the target supplies targets/<name>/playwright/authz-matrix.json:
//
//   [
//     { "path": "/api/users",            "method": "GET",  "allow": ["A"] },
//     { "path": "/download.php?id=999",  "method": "GET",  "allow": [],
//       "note": "another user's document — nobody may read it via a guessed id" }
//   ]
//
// "allow" lists the roles that SHOULD succeed. Every other role must be denied (401/403/404).
//
// ADVERTENCIA SOBRE ESCRITURAS. El motor ejecuta cada regla con TODOS los roles, incluido el
// permitido, porque un endpoint que deniega a quien tiene derecho también es un hallazgo. Con un
// metodo de escritura eso no es una comprobacion: es la mutacion real. En costos_web una regla
// PUT {rol_id:1} ascendio a la cuenta de menor privilegio a administradora y, con ese privilegio,
// otra spec borro la cuenta administradora del entorno de pruebas. Regla practica: en esta matriz,
// escrituras SOLO contra objetivos desechables que la propia suite cree y destruya; las que tocan
// datos del proyecto van en una spec del target, que puede restaurar lo que toca.
// A missing file means the dimension was not tested — it is reported as skipped, never as passed.
import { test, expect } from '@playwright/test';
import * as fs from 'fs';
// This file lives at lib/specs/, so the adapter is one directory up.
import { loginAs, hasRole, writeHeaders, Role, BASE } from '../auth/index';

// `body` is optional: GET rules omit it (antiplagio-style path+query); JSON APIs whose
// authorization lives on POST endpoints supply it so the request is well-formed and the
// status reflects authorization, not a 422 for a missing payload.
type Rule = { path: string; method?: string; allow: Role[]; note?: string; body?: unknown };

const FILE = 'authz-matrix.json';
const rules: Rule[] = fs.existsSync(FILE) ? JSON.parse(fs.readFileSync(FILE, 'utf8')) : [];

// Ritmo opcional entre comprobaciones. Un backend con limitador por usuario (Costos Web:
// throttle:60,1) responde 429 a una matriz que dispara decenas de peticiones seguidas, y ese
// 429 se lee como denegacion: la matriz acaba midiendo el limitador en vez de la autorizacion.
// El perfil declara E2E_PACE_MS cuando su aplicacion lo necesita; por defecto no hay espera.
const PACE = Number(process.env.E2E_PACE_MS || 0);

test.describe('authorization matrix', () => {
  test.beforeEach(async () => { if (PACE) await new Promise((r) => setTimeout(r, PACE)); });
  test.skip(rules.length === 0, `no ${FILE} in this target — authorization NOT tested`);
  test.skip(!hasRole('A') || !hasRole('B'), 'needs two accounts of different privilege');

  for (const rule of rules) {
    const method = (rule.method || 'GET').toUpperCase();
    for (const role of ['A', 'B'] as Role[]) {
      const should = rule.allow.includes(role);
      test(`${method} ${rule.path} — role ${role} ${should ? 'allowed' : 'denied'}${rule.note ? ` (${rule.note})` : ''}`, async () => {
        const ctx = await loginAs(role);
        // Build an ABSOLUTE url instead of trusting Playwright's baseURL join: an absolute
        // path ("/grades/x") resolves against the ORIGIN and silently drops a baseURL path
        // prefix (https://host/mobile/api -> https://host/grades/x -> 404). Concatenation
        // keeps the prefix, and is correct for path-less bases too (http://moodle:8080 + /x).
        const url = /^https?:\/\//.test(rule.path) ? rule.path : `${BASE}${rule.path}`;
        // maxRedirects: 0 is load-bearing, not a detail.
        //
        // Server-rendered applications deny by REDIRECTING — Moodle answers 303 to the login or
        // permission page, Laravel 302 to /login. Following that redirect lands on a page that
        // renders perfectly well and returns 200, so every correct denial was being recorded as
        // "the low-privilege account reached it": a false bypass, reported with total confidence,
        // on exactly the dimension this lab exists to measure. Verified against
        // local_slider_form, where nine screens denied role B with 303 and the suite called all
        // nine a finding.
        // Las escrituras necesitan la cabecera CSRF del adaptador. Sin ella, Laravel responde
        // 419 "CSRF token mismatch" ANTES de evaluar el rol: la regla queda medida contra el
        // guardia equivocado y un endpoint mal protegido pasaría por bien protegido.
        const esEscritura = !['GET', 'HEAD', 'OPTIONS'].includes(method);
        const csrf = esEscritura ? await writeHeaders(ctx) : {};
        const res = await ctx.fetch(url, {
          method,
          maxRedirects: 0,
          headers: { ...csrf, ...(rule.body !== undefined ? { 'Content-Type': 'application/json' } : {}) },
          ...(rule.body !== undefined ? { data: rule.body } : {}),
        });
        const status = res.status();
        // Where a 3xx GOES decides what it means: to a login or permission page it is a denial;
        // anywhere else it is ordinary navigation and the request did succeed.
        const location = res.headers()['location'] ?? '';
        const isDenialRedirect =
          status >= 300 && status < 400 &&
          /login|denied|forbidden|permission|nopermission|accessdenied/i.test(location);

        if (should) {
          expect(status, `legitimate access must not be blocked (Location: ${location || 'none'})`)
            .toBeLessThan(400);
          expect(isDenialRedirect,
            `role ${role} was redirected to a login/permission page: ${location}`).toBe(false);
        } else {
          // A denial is either an explicit refusal status or a redirect to a login/permission
          // page. Anything else means the account reached what it must not.
          expect(isDenialRedirect || [401, 403, 404].includes(status),
            `role ${role} reached ${rule.path} with ${status}` +
            (location ? ` (Location: ${location})` : '')).toBe(true);
        }
      });
    }
  }
});
