// Tráfico de FONDO: personas usando la WEB de Moodle mientras otras usan la app.
//
// La app y la web de Zajuna comparten el mismo Moodle y, con él, los mismos trabajadores de
// php-fpm. Medir la app con el Moodle para ella sola da un techo que en la plataforma real no
// existe. Este guion ocupa lo que en la realidad está ocupado: cada persona de fondo inicia sesión
// por el formulario web, abre su página principal y entra a sus cursos, con pausas de lectura.
//
// Usa las ÚLTIMAS cuentas del archivo, para no coincidir con las personas de la app (que toman las
// primeras). Sus peticiones llevan `fase: fondo` (lib/k6/carga.js): no entran en el juicio del SLO.
import http from 'k6/http';
import exec from 'k6/execution';
import { sleep } from 'k6';
import { Counter } from 'k6/metrics';
import { cuentas, FONDO } from '/seclab-lib/carga.js';

const WEB = (__ENV.MOODLE_WEB_URL || '').replace(/\/$/, '');
// En este Moodle el nombre de usuario es el documento MÁS el tipo en minúsculas («…cc»); la API lo
// compone sola (app/auth/identidad_moodle.py), el formulario web no. Sin el sufijo, el login web
// responde «Acceso inválido» y el fondo solo golpea la página de login (pasó el 2026-10-01).
const SUFIJO = __ENV.MOODLE_WEB_SUFIJO === undefined ? 'cc' : __ENV.MOODLE_WEB_SUFIJO;
const paginasWeb = new Counter('fondo_web_paginas');
const fallosWeb = new Counter('fondo_web_fallos');
const sesionesWeb = new Counter('fondo_web_sesiones');
let dentro = false;

function pagina(ruta, cuerpo) {
  const r = cuerpo ? http.post(`${WEB}${ruta}`, cuerpo, { tags: FONDO, redirects: 5 }) : http.get(`${WEB}${ruta}`, { tags: FONDO, redirects: 5 });
  paginasWeb.add(1);
  if (r.status >= 400 || r.status === 0) fallosWeb.add(1);
  return r;
}

export function navegarWeb() {
  if (!WEB) { sleep(5); return; }
  const todas = cuentas();
  const yo = todas[todas.length - 1 - ((exec.vu.idInTest - 1) % todas.length)];
  if (!dentro) {
    const formulario = pagina('/login/index.php');
    const ficha = /name="logintoken" value="([^"]+)"/.exec(formulario.body || '');
    const r = pagina('/login/index.php', { username: `${yo.usuario}${SUFIJO}`, password: yo.clave, logintoken: ficha ? ficha[1] : '' });
    dentro = r.status === 200 && !/name="logintoken"/.test(r.body || '');
    if (!dentro) { fallosWeb.add(1); sleep(10); return; }
    sesionesWeb.add(1);
  }
  pagina('/my/');
  sleep(4 + Math.random() * 8);
  const cursos = yo.cursos || [];
  if (cursos.length) pagina(`/course/view.php?id=${cursos[Math.floor(Math.random() * cursos.length)]}`);
  sleep(6 + Math.random() * 12);
}
