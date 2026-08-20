#!/usr/bin/env python3
"""Compare two runs of the same target: what got FIXED, what PERSISTS, what is NEW.

This is the piece that makes a re-audit worth running. Absolute totals cannot answer the only
question a second round exists to ask, and they actively mislead: a project that closed six
findings while introducing two regressions shows a SMALLER total and a worse state. "47
findings" is not a result; "6 closed, 39 still open since R1, 2 new" is.

Findings are matched on the triage key (tool | rule | location) — the same key tools/triage.py
uses, deliberately built WITHOUT line numbers so that a finding keeps its identity when code
moves around it. Reusing that key rather than inventing a second one is the whole reason a
verdict recorded in round 1 still applies in round 2.

Triage is respected, because a finding a human already dismissed must not be reported to the
developer as fixed work: false positives are counted apart and never inflate the "fixed" column.

  tools/diff-runs.py <target>                 last two runs
  tools/diff-runs.py <target> <run-a> <run-b> two named runs
  tools/diff-runs.py <target> --json          machine-readable, for tools/report.py
"""
from __future__ import annotations

import json
import os
import sys

LAB = os.environ.get("LAB_DIR", os.getcwd())
sys.path.insert(0, os.path.join(LAB, "ui"))
sys.path.insert(0, os.path.join(LAB, "tools"))
import findings as findlib  # noqa: E402 — the one SARIF reader; a second would drift


def runs_of(target: str) -> list[str]:
    d = os.path.join(LAB, "reports", target, "runs")
    if not os.path.isdir(d):
        return []
    return sorted(x for x in os.listdir(d) if os.path.isdir(os.path.join(d, x)))


def index(target: str, run: str) -> dict[str, dict]:
    """key -> finding, for one archived run."""
    got = findlib.collect(os.path.join(LAB, "reports", target, "runs", run))
    return {f["key"]: f for f in got["findings"]}


def diff(target: str, a: str, b: str) -> dict:
    old, new = index(target, a), index(target, b)

    def dismissed(f: dict) -> bool:
        return f.get("verdict") == "false-positive"

    fixed = [f for k, f in old.items() if k not in new and not dismissed(f)]
    persist = [f for k, f in new.items() if k in old and not dismissed(f)]
    fresh = [f for k, f in new.items() if k not in old and not dismissed(f)]
    # Kept apart on purpose: something a human already ruled out is not developer work, in
    # either direction. Counting it as "fixed" would credit a fix nobody made.
    fp = [f for f in new.values() if dismissed(f)]

    order = findlib.dashboard.SEV_ORDER
    for lst in (fixed, persist, fresh, fp):
        lst.sort(key=lambda f: (order.index(f["sev"]), f["tool"], f["loc"]))

    return {
        "target": target, "run_a": a, "run_b": b,
        "fixed": fixed, "persistent": persist, "new": fresh, "false_positives": fp,
    }


def main() -> int:
    args = [a for a in sys.argv[1:] if a != "--json"]
    as_json = "--json" in sys.argv[1:]
    if not args:
        print(__doc__.strip().splitlines()[-3].strip(), file=sys.stderr)
        return 2
    target = args[0]

    available = runs_of(target)
    if len(args) >= 3:
        a, b = args[1], args[2]
    elif len(available) >= 2:
        a, b = available[-2], available[-1]
    else:
        # Not an error. A first audit legitimately has nothing to compare against, and saying
        # so is different from reporting an empty diff — which would read as "nothing changed".
        msg = {"target": target, "run_a": None, "run_b": available[-1] if available else None,
               "fixed": [], "persistent": [], "new": [], "false_positives": [],
               "note": "primera corrida: no hay ronda anterior con la que comparar"}
        print(json.dumps(msg, ensure_ascii=False, indent=1) if as_json
              else f"{target}: primera corrida, no hay con qué comparar "
                   f"({len(available)} corrida(s) archivada(s))")
        return 0

    d = diff(target, a, b)
    if as_json:
        print(json.dumps(d, ensure_ascii=False, indent=1))
        return 0

    print(f"== diff: {target} ==")
    print(f"   antes: {a}")
    print(f"   ahora: {b}\n")
    for label, items in (("CORREGIDOS", d["fixed"]),
                         ("NUEVOS (regresiones o hallazgos nuevos)", d["new"]),
                         ("PERSISTENTES", d["persistent"])):
        print(f"-- {label}: {len(items)}")
        for f in items[:20]:
            print(f"     [{f['sev']:<8}] {f['tool']:<13} {f['path']}  {f['rule']}")
        if len(items) > 20:
            print(f"     ... y {len(items) - 20} más")
        print()
    if d["false_positives"]:
        print(f"-- descartados por triaje previo (no cuentan en ningún lado): "
              f"{len(d['false_positives'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
