<?php
/**
 * Usuarios sintéticos de carga en el Moodle LOCAL, por la API de Moodle.
 *
 * Una prueba de carga con dos cuentas mide la caché por persona del backend, no el sistema. Hacen
 * falta tantas personas distintas como usuarios virtuales, y no pueden ser cuentas reales.
 *
 * NO escribe tablas a mano: user_create_user(), el plugin de matrícula manual y user_delete_user()
 * mantienen coherentes contextos, cachés y eventos. NUNCA contra preprod ni producción.
 *
 * Cómo se reconocen (y se borran sin ambigüedad): correo `k6load_NNNN@carga.invalid`.
 * El usuario de Moodle es `<documento>cc`, porque el backend compone así la identidad
 * (movil_api/app/auth/identidad_moodle.py: usuario_de_moodle). Documentos: 99000NNNNN.
 *
 * Reparto, y de dónde sale cada número:
 *   - cursos por persona: 95 % uno, 4 % dos, 1 % tres. MEDIDO en este Moodle el 2026-09-30
 *     (mdl_user_enrolments: 18.407 con uno, 811 con dos, 164 con tres o más).
 *   - una persona de cada --por-curso es instructor. SUPUESTO: una ficha del SENA con un
 *     instructor. Este Moodle no sirve para medirlo (es de capacitación: más instructores que
 *     aprendices).
 *   - el fondo de cursos son los que tienen contenido de verdad (entre --min y --max módulos) y
 *     matrícula manual; el de referencia va primero. Repartir entre muchos cursos evita que una
 *     sola caché de curso caliente haga el resultado optimista.
 *
 * Uso (como el usuario del servidor web):
 *   sudo -u www-data php sembrar-usuarios.php --moodle=/var/www/zajuna --count=1000 \
 *        --fondo=40 --por-curso=25 --referencia=23542 > ../k6/datos/cuentas.json
 *   sudo -u www-data php sembrar-usuarios.php --moodle=/var/www/zajuna --delete
 *   sudo -u www-data php sembrar-usuarios.php --moodle=/var/www/zajuna --contar
 */

define('CLI_SCRIPT', true);

$o = getopt('', ['moodle:', 'count::', 'fondo::', 'por-curso::', 'referencia::', 'min::', 'max::', 'clave::', 'delete', 'contar', 'help']);
if (isset($o['help']) || !isset($o['moodle'])) {
    fwrite(STDERR, "Uso: php sembrar-usuarios.php --moodle=/ruta [--count=1000] [--fondo=40] [--por-curso=25]\n" .
                   "     [--referencia=ID] [--min=25] [--max=150] [--clave=…]   |  --delete  |  --contar\n");
    exit(1);
}
$raiz = rtrim($o['moodle'], '/');
if (!is_readable("$raiz/config.php")) {
    fwrite(STDERR, "No se puede leer $raiz/config.php\n");
    exit(1);
}
require("$raiz/config.php");
require_once($CFG->dirroot . '/user/lib.php');
require_once($CFG->libdir . '/moodlelib.php');
require_once($CFG->libdir . '/enrollib.php');

// Defensa: esto solo tiene sentido contra un Moodle propio. Un wwwroot público se rechaza.
if (!preg_match('#//(localhost|127\.|nginx\.zajuna\.com|10\.|192\.168\.)#', $CFG->wwwroot)) {
    fwrite(STDERR, "wwwroot = {$CFG->wwwroot}: no parece un Moodle local. No se siembra nada.\n");
    exit(1);
}

$sello = "email LIKE 'k6load\\_%@carga.invalid' AND deleted = 0";

if (isset($o['contar'])) {
    echo $DB->count_records_select('user', $sello) . "\n";
    exit(0);
}

if (isset($o['delete'])) {
    $n = 0;
    foreach ($DB->get_records_select('user', $sello) as $u) {
        if (strpos($u->email, 'k6load_') !== 0) {
            continue;
        }
        user_delete_user($u);
        $n++;
    }
    fwrite(STDERR, "Eliminados $n usuarios sintéticos\n");
    exit(0);
}

$cuantos = (int)($o['count'] ?? 1000);
$fondo = (int)($o['fondo'] ?? 40);
$porcurso = max(2, (int)($o['por-curso'] ?? 25));
$ref = (int)($o['referencia'] ?? 0);
$min = (int)($o['min'] ?? 25);
$max = (int)($o['max'] ?? 150);
// La clave nace aquí y solo sale por la salida estándar, hacia un archivo que no se versiona.
$clave = $o['clave'] ?? ('K6c' . bin2hex(random_bytes(6)) . '*9aZ');

$cursos = $DB->get_fieldset_sql(
    "SELECT c.id
       FROM {course} c
       JOIN (SELECT course, COUNT(*) n FROM {course_modules} WHERE deletioninprogress = 0 GROUP BY course) m ON m.course = c.id
      WHERE c.visible = 1 AND m.n BETWEEN :min AND :max
        AND EXISTS (SELECT 1 FROM {enrol} e WHERE e.courseid = c.id AND e.enrol = 'manual' AND e.status = 0)
   ORDER BY (SELECT COUNT(*) FROM {user_enrolments} ue JOIN {enrol} e2 ON e2.id = ue.enrolid WHERE e2.courseid = c.id) DESC, c.id",
    ['min' => $min, 'max' => $max], 0, $fondo);
if ($ref && !in_array($ref, $cursos)) {
    array_unshift($cursos, $ref);
    $cursos = array_slice($cursos, 0, $fondo);
}
if (!$cursos) {
    fwrite(STDERR, "Ningún curso con entre $min y $max módulos y matrícula manual\n");
    exit(1);
}
fwrite(STDERR, "Fondo de " . count($cursos) . " cursos: " . implode(',', $cursos) . "\n");

$manual = enrol_get_plugin('manual');
$rolaprendiz = $DB->get_field('role', 'id', ['shortname' => 'student'], MUST_EXIST);
$rolinstructor = $DB->get_field('role', 'id', ['shortname' => 'editingteacher'], MUST_EXIST);
$instancias = [];
foreach ($cursos as $cid) {
    foreach (enrol_get_instances($cid, true) as $inst) {
        if ($inst->enrol === 'manual') {
            $instancias[$cid] = $inst;
            break;
        }
    }
}
$cursos = array_values(array_keys($instancias));

$salida = [];
$creados = 0;
$reusados = 0;
for ($i = 1; $i <= $cuantos; $i++) {
    $doc = sprintf('99000%05d', $i);
    $username = $doc . 'cc';
    $u = $DB->get_record('user', ['username' => $username, 'mnethostid' => $CFG->mnet_localhost_id]);
    if ($u && $u->deleted == 0) {
        update_internal_user_password($u, $clave);
        $uid = $u->id;
        $reusados++;
    } else {
        $n = new stdClass();
        $n->username = $username;
        $n->auth = 'manual';
        $n->confirmed = 1;
        $n->mnethostid = $CFG->mnet_localhost_id;
        $n->email = sprintf('k6load_%05d@carga.invalid', $i);
        $n->firstname = 'Carga';
        $n->lastname = sprintf('K6 %05d', $i);
        $n->password = $clave;
        $n->policyagreed = 1;
        $n->timezone = '99';
        $n->lang = 'es';
        $uid = user_create_user($n, true, false);
        $creados++;
    }

    // Reparto: bloques de --por-curso personas por curso; la primera de cada bloque enseña.
    $bloque = intdiv($i - 1, $porcurso);
    $instructor = (($i - 1) % $porcurso) === 0;
    $mios = [$cursos[$bloque % count($cursos)]];
    if (!$instructor) {
        if ($i % 100 === 50) {                       // 1 %: tres cursos
            $mios[] = $cursos[($bloque + 1) % count($cursos)];
            $mios[] = $cursos[($bloque + 2) % count($cursos)];
        } else if ($i % 25 === 12) {                 // 4 %: dos cursos
            $mios[] = $cursos[($bloque + 1) % count($cursos)];
        }
    }
    foreach (array_unique($mios) as $cid) {
        $ctx = context_course::instance($cid);
        if (!is_enrolled($ctx, $uid)) {
            $manual->enrol_user($instancias[$cid], $uid, $instructor ? $rolinstructor : $rolaprendiz);
        }
    }
    $salida[] = ['usuario' => $doc, 'clave' => $clave, 'rol' => $instructor ? 'instructor' : 'aprendiz',
                 'id' => (int)$uid, 'cursos' => array_values(array_unique($mios))];
    if ($i % 100 === 0) {
        fwrite(STDERR, "  $i / $cuantos\n");
    }
}
fwrite(STDERR, "Usuarios: $creados creados, $reusados reutilizados\n");
echo json_encode($salida, JSON_UNESCAPED_UNICODE) . "\n";
