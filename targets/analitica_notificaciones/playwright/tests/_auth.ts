// Auth del target: reexporta el adaptador que elige AUTH_ADAPTER (aquí `jwt-bearer`).
//
// Es todo el coste de portar las especificaciones genéricas a este proyecto. Lo específico del
// stack —que el login es POST /api/auth/moodle-login {username,password} -> {access_token} y que
// el token viaja como Authorization: Bearer— ya vive una sola vez en lib/auth/index.ts
// (adaptador jwt-bearer), así que aquí no se reimplementa nada.
export { loginAs, hasRole, CREDS, type Role } from '../lib/auth/index';
