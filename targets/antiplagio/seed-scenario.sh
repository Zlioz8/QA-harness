#!/usr/bin/env bash
# Escenario minimo que vuelve significativa la matriz de autorizacion (M4 del informe de
# migracion, que quedo inconcluso): un curso, una tarea (assign), y los dos roles matriculados
# con privilegio DISTINTO sobre ese mismo contexto.
#
# Sin esto, ROLE_A y ROLE_B son dos usuarios de sitio sin permisos sobre nada: un 403 para el
# rol que SI deberia poder no prueba que el plugin controle acceso, solo que nadie esta
# matriculado. Un falso PASS es el peor resultado posible de una auditoria.
#
# Ejecutar despues de seed-users.sh, con Moodle respondiendo 200.
# Imprime al final los ids que las specs de Playwright necesitan.
set -euo pipefail
C=seclab_antiplagio-moodle-1

docker exec "$C" php -r '
define("CLI_SCRIPT", true);
require("/bitnami/moodle/config.php");
require_once($CFG->dirroot."/course/lib.php");
require_once($CFG->dirroot."/lib/enrollib.php");
require_once($CFG->dirroot."/lib/modinfolib.php");

// create_module() comprueba capacidades contra $USER; en CLI no hay sesion y falla por
// permisos antes de llegar a crear nada. Actuar como admin es lo que hace el propio
// admin/cli de Moodle.
\core\session\manager::set_user(get_admin());

// --- curso ---------------------------------------------------------------
$course = $DB->get_record("course", ["shortname" => "SECLAB-ANTIPLAG"]);
if (!$course) {
    $c = new stdClass();
    $c->fullname = "Curso laboratorio antiplagio";
    $c->shortname = "SECLAB-ANTIPLAG";
    $c->category = 1;
    $c->format = "topics";
    $c->visible = 1;
    $course = create_course($c);
}
echo "course_id=".$course->id."\n";

// --- tarea (assign) ------------------------------------------------------
$cm = $DB->get_record_sql(
    "SELECT cm.id AS cmid, a.id AS assignid
       FROM {course_modules} cm
       JOIN {modules} m ON m.id = cm.module AND m.name = :mod
       JOIN {assign} a ON a.id = cm.instance
      WHERE cm.course = :cid",
    ["mod" => "assign", "cid" => $course->id]
);
if (!$cm) {
    $module = $DB->get_record("modules", ["name" => "assign"], "*", MUST_EXIST);
    $a = new stdClass();
    $a->course = $course->id;
    $a->name = "Entrega laboratorio";           // sin em-dash: latin-1 rompe el pipeline
    $a->intro = "Actividad sembrada por SECURITY-LAB";
    $a->introformat = FORMAT_HTML;
    // create_module() exige introeditor cuando el modulo soporta FEATURE_MOD_INTRO
    // (course/lib.php:2959). Sin el, aborta con createmodulemissingattribut.
    $a->introeditor = ["text" => $a->intro, "format" => FORMAT_HTML, "itemid" => 0];
    $a->duedate = time() + 7 * 86400;           // duedate=0 no encola analisis
    $a->allowsubmissionsfromdate = 0;
    $a->cutoffdate = 0;
    $a->gradingduedate = 0;
    $a->grade = 100;
    $a->submissiondrafts = 0;
    $a->requiresubmissionstatement = 0;
    $a->sendnotifications = 0;
    $a->sendlatenotifications = 0;
    $a->teamsubmission = 0;
    $a->requireallteammemberssubmit = 0;
    $a->blindmarking = 0;
    $a->attemptreopenmethod = "none";
    $a->maxattempts = -1;
    $a->markingworkflow = 0;
    $a->markingallocation = 0;
    $a->assignsubmission_onlinetext_enabled = 1;
    $a->assignsubmission_file_enabled = 1;
    $a->assignsubmission_file_maxfiles = 1;
    $a->assignsubmission_file_maxsizebytes = 0;
    $a->assignfeedback_comments_enabled = 1;
    $a->module = $module->id;
    $a->modulename = "assign";
    $a->section = 0;
    $a->visible = 1;
    $a->cmidnumber = "";
    $a = create_module($a);
    // create_module() devuelve el module info, cuyo ->id es el course_module, no la instancia
    // de assign. Releer de la BD evita publicar un assign_id equivocado a las specs.
    $cm = $DB->get_record_sql(
        "SELECT cm.id AS cmid, a.id AS assignid
           FROM {course_modules} cm
           JOIN {modules} m ON m.id = cm.module AND m.name = :mod
           JOIN {assign} a ON a.id = cm.instance
          WHERE cm.course = :cid",
        ["mod" => "assign", "cid" => $course->id]
    );
}
echo "assign_id=".$cm->assignid."\ncmid=".$cm->cmid."\n";

// --- matriculas con privilegio distinto ----------------------------------
$plugin = enrol_get_plugin("manual");
$instance = $DB->get_record("enrol", ["courseid" => $course->id, "enrol" => "manual"], "*", IGNORE_MISSING);
if (!$instance) {
    $plugin->add_default_instance($course);
    $instance = $DB->get_record("enrol", ["courseid" => $course->id, "enrol" => "manual"], "*", MUST_EXIST);
}
foreach ([["instructor_lab", "editingteacher"], ["aprendiz_lab", "student"]] as $pair) {
    list($username, $shortname) = $pair;
    $u = $DB->get_record("user", ["username" => $username], "*", MUST_EXIST);
    $r = $DB->get_record("role", ["shortname" => $shortname], "*", MUST_EXIST);
    $plugin->enrol_user($instance, $u->id, $r->id);
    echo "enrolled ".$username." as ".$shortname." (userid ".$u->id.")\n";
}
'
