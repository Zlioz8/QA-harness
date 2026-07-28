"""Run `make` goals as background jobs, stream their output, and keep them honest.

Three properties this file exists to guarantee:

  1. **The UI never reimplements the lab.** Every job is `make <goal> TARGET=<t>` and nothing
     else. If the interface needs something make cannot do, the fix is a new make goal — not a
     second implementation that will drift from the first and eventually contradict it.

  2. **The log lives on disk, not in memory.** A job belongs to the Docker daemon, not to this
     process. Restarting the UI mid-run must not lose the output or the run; reconnecting just
     re-reads the file. A `make up` that takes ninety seconds to install a host application would
     otherwise look like a hang with nothing to show for it.

  3. **One run per target.** Two runs of the same profile share a compose project name and a
     reports directory, so they corrupt each other. Different profiles run in parallel freely.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import threading
import time
import uuid
from dataclasses import dataclass, asdict
from typing import Iterator

ANSI = re.compile(r"\x1b\[[0-9;]*m")

LAB = os.environ.get("LAB_DIR", os.getcwd())
STATE = os.path.join(LAB, "reports", ".ui")
JOBS_DIR = os.path.join(STATE, "jobs")


def _ensure_dirs() -> None:
    os.makedirs(JOBS_DIR, exist_ok=True)


@dataclass
class Job:
    id: str
    target: str
    goal: str
    status: str            # running | done | failed
    started: float
    finished: float = 0.0
    exit_code: int | None = None

    @property
    def log_path(self) -> str:
        return os.path.join(JOBS_DIR, f"{self.id}.log")

    @property
    def meta_path(self) -> str:
        return os.path.join(JOBS_DIR, f"{self.id}.json")


class Runner:
    def __init__(self, redactor=None):
        # redactor(target) -> list[str] of secret values to scrub before anything is shown.
        self._redactor = redactor or (lambda _t: [])
        self._lock = threading.Lock()
        _ensure_dirs()
        self.reconcile()

    def reconcile(self) -> None:
        """Settle jobs left mid-flight by a UI restart.

        What actually happens when the UI dies during a run, verified rather than assumed: the
        tool container is a sibling on the host daemon, so IT KEEPS RUNNING and still writes its
        artifact. What dies is the process reading its output, so the log freezes and the job
        would otherwise stay "running" forever, blocking the target's lock and lying on screen.

        These jobs are marked `interrupted`, which is the truthful state: we no longer know how
        they ended. The artifact on disk is the authority — check reports/, not this status.
        """
        for job in self.recent(limit=200):
            if job.status != "running":
                continue
            try:
                idle = time.time() - os.path.getmtime(job.log_path)
            except OSError:
                idle = 1e9
            if idle > 120:
                job.status = "interrupted"
                job.finished = time.time()
                self._write_meta(job)
                try:
                    with open(job.log_path, "a", encoding="utf-8") as log:
                        log.write("\n[ui] la interfaz se reinició durante esta corrida. La "
                                  "herramienta siguió corriendo en su propio contenedor y pudo "
                                  "terminar bien: comprueba el artefacto en reports/.\n")
                except OSError:
                    pass

    # ---------------------------------------------------------------- state

    def _write_meta(self, job: Job) -> None:
        with open(job.meta_path, "w", encoding="utf-8") as fh:
            json.dump(asdict(job), fh)

    def get(self, job_id: str) -> Job | None:
        path = os.path.join(JOBS_DIR, f"{job_id}.json")
        if not os.path.exists(path):
            return None
        try:
            with open(path, encoding="utf-8") as fh:
                return Job(**json.load(fh))
        except Exception:
            return None

    def recent(self, target: str | None = None, limit: int = 40) -> list[Job]:
        out: list[Job] = []
        if not os.path.isdir(JOBS_DIR):
            return out
        for name in sorted(os.listdir(JOBS_DIR), reverse=True):
            if not name.endswith(".json"):
                continue
            job = self.get(name[:-5])
            if job and (target is None or job.target == target):
                out.append(job)
            if len(out) >= limit:
                break
        return sorted(out, key=lambda j: j.started, reverse=True)

    def running_for(self, target: str) -> Job | None:
        """A job whose process is genuinely still alive.

        Checked from the file, never from an in-memory table: after a UI restart the table is
        empty but the work is not, and offering to launch a duplicate would be worse than useless.
        """
        for job in self.recent(target, limit=20):
            if job.status == "running":
                # A job left "running" by a killed UI is stale once its log stops growing.
                try:
                    age = time.time() - os.path.getmtime(job.log_path)
                except OSError:
                    age = 1e9
                if age < 90:
                    return job
        return None

    # ---------------------------------------------------------------- running

    def start(self, target: str, goal: str, extra_env: dict[str, str] | None = None) -> Job:
        with self._lock:
            busy = self.running_for(target)
            if busy:
                raise RuntimeError(
                    f"'{busy.goal}' ya está corriendo sobre '{target}'. Dos corridas del mismo "
                    f"perfil comparten proyecto de compose y carpeta de reportes, así que se "
                    f"corromperían entre sí. Adjúntate a esa corrida o espera a que termine."
                )
            job = Job(id=uuid.uuid4().hex[:12], target=target, goal=goal,
                      status="running", started=time.time())
            self._write_meta(job)

        secrets = self._redactor(target)
        env = {**os.environ, **(extra_env or {})}

        def run() -> None:
            with open(job.log_path, "w", encoding="utf-8", buffering=1) as log:
                log.write(f"$ make {goal} TARGET={target}\n\n")
                try:
                    proc = subprocess.Popen(
                        ["make", goal, f"TARGET={target}"],
                        cwd=LAB, env=env, stdout=subprocess.PIPE,
                        stderr=subprocess.STDOUT, text=True, bufsize=1,
                    )
                    for line in proc.stdout:            # type: ignore[union-attr]
                        clean = ANSI.sub("", line)
                        for s in secrets:
                            if s and len(s) >= 4:
                                clean = clean.replace(s, "«redactado»")
                        log.write(clean)
                    proc.wait()
                    job.exit_code = proc.returncode
                    job.status = "done" if proc.returncode == 0 else "failed"
                except Exception as exc:                # pragma: no cover - defensive
                    log.write(f"\n[ui] no se pudo ejecutar: {exc}\n")
                    job.status = "failed"
                    job.exit_code = -1
                finally:
                    job.finished = time.time()
                    self._write_meta(job)
                    log.write(f"\n[ui] terminó con código {job.exit_code}\n")

        threading.Thread(target=run, daemon=True).start()
        return job

    # ---------------------------------------------------------------- streaming

    def stream(self, job_id: str) -> Iterator[str]:
        """Server-sent events, tailing the log file.

        Reading the file rather than holding a pipe is what makes a reconnect (or a UI restart)
        pick up mid-run instead of showing an empty pane next to a job that is clearly working.
        """
        job = self.get(job_id)
        if not job:
            yield "event: end\ndata: sin trabajo\n\n"
            return

        pos = 0
        idle = 0.0
        while True:
            try:
                with open(job.log_path, encoding="utf-8", errors="replace") as fh:
                    fh.seek(pos)
                    chunk = fh.read()
                    pos = fh.tell()
            except FileNotFoundError:
                chunk = ""

            if chunk:
                idle = 0.0
                for line in chunk.splitlines():
                    yield f"data: {line}\n\n"
            else:
                idle += 0.4

            job = self.get(job_id) or job
            if job.status != "running" and not chunk:
                yield f"event: end\ndata: {job.status}:{job.exit_code}\n\n"
                return
            if idle > 900:                       # 15 min with no output: stop holding the socket
                yield "event: end\ndata: timeout\n\n"
                return
            time.sleep(0.4)


def read_log(job_id: str, tail: int = 4000) -> str:
    path = os.path.join(JOBS_DIR, f"{job_id}.log")
    try:
        with open(path, encoding="utf-8", errors="replace") as fh:
            return fh.read()[-tail * 80:]
    except OSError:
        return ""
