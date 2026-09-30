// Línea base: cuánto cuesta cada gesto de la app SIN compañía. Un usuario, un gesto tras otro,
// varias personas distintas (instructor y aprendiz) para no medir la caché de una sola.
//
// Responde: latencia, tamaño y llamadas a Moodle de cada petición cuando el sistema está libre.
// Todo lo que se mida después bajo carga se compara contra esto: si un endpoint ya es lento
// aquí, la carga no es su problema.
import { sleep } from 'k6';
import exec from 'k6/execution';
import { opciones, resumen, cuentaDe } from '/seclab-lib/carga.js';
import * as M from './modelo.js';

export const options = opciones(M.ENDPOINTS);

// Índices en cuentas.json (la siembra pone un instructor al principio de cada bloque de 25 y
// reparte dos cursos a una persona de cada 25): instructor, aprendiz, aprendiz con dos cursos…
const QUIEN = [1, 2, 12, 26, 27, 3];

export default function () {
  const i = exec.scenario.iterationInTest;
  const n = QUIEN[i % QUIEN.length] + 25 * Math.floor(i / QUIEN.length);
  const c = cuentaDe(n);
  if (!M.usar(c, M.entrar(c, `10.252.0.${(n % 250) + 1}`))) return;
  const pasos = [M.arranque, M.inicio, M.abrirCurso, M.calificaciones, M.cambiarAprendiz, M.calendario,
    M.notificaciones, M.buscar, M.evidencia, M.evidencia, M.evidencia, M.abrirCurso, M.inicio, M.reposo];
  for (const f of pasos) {
    f();
    sleep(1);
  }
}

export function handleSummary(data) {
  return resumen(data, { guion: 'linea-base.js' });
}
