// Auth del target: reexporta el adaptador que elige AUTH_ADAPTER (aquí `encuestas-sso`).
//
// Todo lo específico del stack —el SSO de tres saltos Moodle-form -> pase HMAC del plugin ->
// token Sanctum— vive una sola vez en lib/auth/index.ts. Aquí no se reimplementa nada.
export { loginAs, hasRole, writeHeaders, CREDS, type Role } from '../lib/auth/index';
