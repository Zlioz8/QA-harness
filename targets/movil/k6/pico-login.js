// Pico de login: muchas personas abriendo la app a la vez SIN sesión previa (primera hora de un
// lunes, o justo después de una notificación masiva). Cada usuario virtual inicia sesión él
// mismo al llegar —con su cuenta y su IP— y sigue usando la app.
//
// Se corre con CARGA_TIPO=pico (salto brusco) o con la escalera `pico`. Lo que se busca: cuántos
// logins por segundo aguanta la cadena login -> token.php de Moodle, y si el sistema se recupera.
import { opciones, resumen } from '/seclab-lib/carga.js';
import { ENDPOINTS, unGestoConLogin } from './modelo.js';

export const options = opciones(ENDPOINTS);

export default function () {
  unGestoConLogin();
}

export function handleSummary(data) {
  return resumen(data, { guion: 'pico-login.js' });
}
