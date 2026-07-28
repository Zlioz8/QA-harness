// Target-side auth: a two-line re-export of the shared adapter chosen by AUTH_ADAPTER.
//
// This file is the whole cost of porting the generic specs to a new project. Everything
// stack-specific (Moodle's one-shot logintoken, its per-session sesskey) lives once in
// lib/auth/index.ts and is reused by every Moodle project that follows.
export { loginAs, hasRole, sesskeyOf, CREDS, type Role } from '../lib/auth/index';
