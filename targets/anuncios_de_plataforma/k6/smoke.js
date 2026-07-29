// Load profile for anuncios_de_plataforma — AUTHENTICATED, which is the point.
//
// `make perf-jmeter` already measures the anonymous surface of this Moodle, and every plugin
// path there answers with a redirect to the login page. That number describes Moodle's login
// screen, not the plugins. This script logs in as role A and drives the screens the plugin
// actually serves, so p95 refers to the code under audit.
//
// The endpoints exercised are read-only on purpose. insertRecord / deleteRecord / send_segmented
// are excluded: send_segmented delivers mass email to every user enrolled in the resolved
// courses, and a load test that discovers that at 10 VUs is an incident, not a measurement.
import http from 'k6/http';
import { check, group, sleep } from 'k6';
import { BASE, jar, login } from '/seclab-lib/session.js';

export const options = {
  scenarios: {
    plugin_screens: {
      executor: 'ramping-vus',
      startVUs: 1,
      stages: [
        { duration: '20s', target: 5 },
        { duration: '40s', target: 5 },
        { duration: '10s', target: 0 },
      ],
    },
  },
  // Declared here as well as in target.env so a run that breaches them is visibly failing while
  // it happens, not only afterwards in `make gate`.
  thresholds: {
    http_req_failed: ['rate<0.01'],
    http_req_duration: ['p(95)<1500'],
  },
};

// Moodle's session is per-VU: logging in inside setup() would share one session across VUs and
// measure a cache, not concurrency.
export default function () {
  if (!__ITER) login('A');

  group('plugin screens', () => {
    for (const path of [
      '/local/slider_form/index.php',
      '/local/slider_form/menu.php',
      '/local/slider_form/show_order.php',
      '/local/slider_form/table_logs.php',
    ]) {
      const res = http.get(`${BASE}${path}`, { jar, tags: { endpoint: path } });
      // Status alone is not enough: Moodle answers 200 with the LOGIN PAGE when the session has
      // gone. Without this check the run reports a fast, healthy application while measuring a
      // login form over and over.
      check(res, {
        [`${path} 200`]: (r) => r.status === 200,
        [`${path} is not the login page`]: (r) => !String(r.body).includes('name="logintoken"'),
      });
    }
  });

  group('ajax read endpoints', () => {
    const res = http.get(`${BASE}/local/slider_form/ajax/saved_filters.php?action=list`, {
      jar,
      tags: { endpoint: 'saved_filters' },
    });
    check(res, { 'saved_filters answers': (r) => r.status === 200 });
  });

  sleep(1);
}
