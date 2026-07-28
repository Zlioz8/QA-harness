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
// A missing file means the dimension was not tested — it is reported as skipped, never as passed.
import { test, expect } from '@playwright/test';
import * as fs from 'fs';
// This file lives at lib/specs/, so the adapter is one directory up.
import { loginAs, hasRole, Role } from '../auth/index';

type Rule = { path: string; method?: string; allow: Role[]; note?: string };

const FILE = 'authz-matrix.json';
const rules: Rule[] = fs.existsSync(FILE) ? JSON.parse(fs.readFileSync(FILE, 'utf8')) : [];

test.describe('authorization matrix', () => {
  test.skip(rules.length === 0, `no ${FILE} in this target — authorization NOT tested`);
  test.skip(!hasRole('A') || !hasRole('B'), 'needs two accounts of different privilege');

  for (const rule of rules) {
    const method = (rule.method || 'GET').toUpperCase();
    for (const role of ['A', 'B'] as Role[]) {
      const should = rule.allow.includes(role);
      test(`${method} ${rule.path} — role ${role} ${should ? 'allowed' : 'denied'}${rule.note ? ` (${rule.note})` : ''}`, async () => {
        const ctx = await loginAs(role);
        const res = await ctx.fetch(rule.path, { method });
        if (should) {
          expect(res.status(), 'legitimate access must not be blocked').toBeLessThan(400);
        } else {
          // 200 here is the finding: the low-privilege account reached something it must not.
          expect([401, 403, 404], `role ${role} reached ${rule.path} with ${res.status()}`)
            .toContain(res.status());
        }
      });
    }
  }
});
