"""Persist the human judgement about a finding.

This is the piece that keeps the lab honest about its own limits. A scanner produces signal; only
a person can say whether a given hit is real. In the antiplagio run, thirteen apparent
authorization failures turned out to be zero real bypasses — some blocked by a missing scenario,
some because a 200 carried an error body — and that reasoning existed nowhere but in the head of
whoever did it. The next reader started from scratch.

A verdict plus a sentence, stored next to the artifacts, turns a list of raw findings into a list
of *judged* findings. Both the web UI (which writes them) and the generated report (which shows
them) use this module, so a triage note recorded in the browser appears in the report unchanged.

Keys are content-derived — tool, rule and location — rather than positional: a finding must keep
its verdict when the scan re-runs and the ordering changes. Line numbers move, so they are
deliberately left out of the key; a note may occasionally attach to a shifted line, which is far
better than silently losing every verdict on each run.
"""
from __future__ import annotations

import json
import os
import time

VERDICTS = ("confirmed", "false-positive", "inconclusive")

LABELS = {
    "confirmed": "Confirmado",
    "false-positive": "Falso positivo",
    "inconclusive": "Inconcluso",
}


def key_for(tool: str, rule: str, loc: str) -> str:
    return f"{tool}|{rule}|{loc}"


def path_for(reports_dir: str) -> str:
    return os.path.join(reports_dir, "triage.json")


def load(reports_dir: str) -> dict:
    try:
        with open(path_for(reports_dir), encoding="utf-8") as fh:
            data = json.load(fh)
            return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def save(reports_dir: str, entries: dict) -> None:
    """Merge and write atomically. An empty verdict removes the entry rather than storing a
    blank one, so clearing a mistaken judgement is possible from the same form that made it."""
    current = load(reports_dir)
    for key, entry in entries.items():
        verdict = (entry.get("verdict") or "").strip()
        note = (entry.get("note") or "").strip()
        if verdict not in VERDICTS and not note:
            current.pop(key, None)
            continue
        current[key] = {"verdict": verdict, "note": note, "at": time.time()}

    os.makedirs(reports_dir, exist_ok=True)
    tmp = path_for(reports_dir) + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(current, fh, indent=1, ensure_ascii=False)
    os.replace(tmp, path_for(reports_dir))


def summary(entries: dict) -> dict:
    out = {v: 0 for v in VERDICTS}
    for e in entries.values():
        v = e.get("verdict")
        if v in out:
            out[v] += 1
    return out
