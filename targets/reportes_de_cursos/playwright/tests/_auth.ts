// Auth del target: reexporta el adaptador que elige AUTH_ADAPTER (aquí `zea-standalone`).
//
// Todo lo específico de este stack —que el login son DOS saltos (login.php -> token.php) y que la
// API acepta el JWT DE CURSO como Bearer— vive una sola vez en lib/auth/index.ts. Aquí no se
// reimplementa nada.
export { loginAs, hasRole, CREDS, type Role } from '../lib/auth/index';
