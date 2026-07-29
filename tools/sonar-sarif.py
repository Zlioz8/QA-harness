#!/usr/bin/env python3
"""SonarQube issues + hotspots -> SARIF.

Why convert instead of teaching every consumer to read Sonar's JSON: the gate, the report and
the findings view already speak SARIF, and each one that learned a sixth dialect would be a
sixth place where severity is resolved slightly differently. One translation here, and Sonar
becomes an ordinary source everywhere else.

Severity mapping keeps Sonar's own word in `properties.tags`, which is where dashboard.py looks
first — so the report shows what Sonar decided, not a re-derivation of it.

Usage: sonar-sarif.py <reports_dir>/sonar
"""
from __future__ import annotations

import json
import os
import sys

# Sonar's scale is its own; these are the names the rest of the lab uses.
SEV = {
    "BLOCKER": "critical", "CRITICAL": "critical", "HIGH": "high",
    "MAJOR": "high", "MEDIUM": "medium", "MINOR": "low", "LOW": "low", "INFO": "low",
}


def read(path: str):
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return None


def _result(rule, sev, msg, comp, line):
    # Sonar components are "projectKey:path"; the report wants the path.
    path = comp.split(":", 1)[1] if ":" in comp else comp
    return {
        "ruleId": rule,
        "level": {"critical": "error", "high": "error",
                  "medium": "warning", "low": "note"}.get(sev, "warning"),
        "message": {"text": msg},
        "locations": [{"physicalLocation": {
            "artifactLocation": {"uri": path},
            "region": {"startLine": line or 1},
        }}],
    }, {
        "id": rule,
        "name": rule,
        "shortDescription": {"text": msg[:120]},
        "properties": {"tags": [sev]},
    }


def main() -> int:
    if len(sys.argv) < 2:
        print("usage: sonar-sarif.py <sonar reports dir>", file=sys.stderr)
        return 2
    d = sys.argv[1]
    issues = read(os.path.join(d, "issues.json"))
    hotspots = read(os.path.join(d, "hotspots.json"))
    if issues is None and hotspots is None:
        print("sonar: nothing exported — not writing a SARIF "
              "(an absent file means NOT RUN; an empty one would mean 'clean')", file=sys.stderr)
        return 1

    results, rules = [], {}
    for it in (issues or {}).get("issues", []):
        sev = SEV.get(str(it.get("severity", "")).upper(), "unranked")
        res, rule = _result(it.get("rule", "sonar"), sev,
                            it.get("message", ""), it.get("component", ""), it.get("line"))
        results.append(res)
        rules[rule["id"]] = rule

    # Hotspots are Sonar's "security-sensitive, a human must look" bucket. They are NOT issues
    # and are absent from /api/issues/search — dropping them would quietly hide the security
    # half of what Sonar found in a lab whose whole point is security.
    for hs in (hotspots or {}).get("hotspots", []):
        sev = SEV.get(str(hs.get("vulnerabilityProbability", "")).upper(), "medium")
        rid = f"hotspot:{hs.get('securityCategory', 'unknown')}"
        res, rule = _result(rid, sev, hs.get("message", ""),
                            hs.get("component", ""), hs.get("line"))
        results.append(res)
        rules[rule["id"]] = rule

    sarif = {
        "version": "2.1.0",
        "$schema": "https://json.schemastore.org/sarif-2.1.0.json",
        "runs": [{
            "tool": {"driver": {"name": "SonarQube", "rules": list(rules.values())}},
            "results": results,
        }],
    }
    out = os.path.join(d, "sonar.sarif")
    with open(out, "w", encoding="utf-8") as fh:
        json.dump(sarif, fh, indent=1, ensure_ascii=False)
    print(f"sonar: {len(results)} findings -> {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
