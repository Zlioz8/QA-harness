// Auth del target: reexporta el adaptador que elige AUTH_ADAPTER (aquí `php-form`).
//
// Es todo el coste de portar las especificaciones genéricas a un proyecto nuevo. Lo que es
// específico del stack —el formulario de ADI, su marcador de sesión iniciada— vive una sola
// vez en lib/auth/index.ts y lo hereda cualquier otro PHP de la fábrica que venga detrás.
export { loginAs, hasRole, CREDS, type Role } from '../lib/auth/index';
