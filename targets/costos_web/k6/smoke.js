// SMOKE — 1 VU. Baseline latency and sanity of every endpoint under test.
// If this is not green, no other measurement is meaningful.
import { check, sleep } from 'k6';
import { login, authedGet } from './lib/session.js';

export const options = {
  vus: 1,
  duration: '30s',
  thresholds: { 'http_req_failed': ['rate<0.01'] },
};

let authed = false;

export default function () {
  if (!authed) authed = login('admin');

  const endpoints = [
    ['/api/usuarios?per_page=10', 'usuarios_pag'],
    ['/api/regionales', 'regionales'],
    ['/api/dependencias', 'dependencias'],
    ['/api/grupos', 'grupos'],
    ['/api/roles', 'roles'],
  ];

  for (const [path, tag] of endpoints) {
    const res = authedGet(path, tag);
    check(res, { [`${tag} 200`]: (r) => r.status === 200 });
  }
  sleep(1);
}
