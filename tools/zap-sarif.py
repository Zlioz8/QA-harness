#!/usr/bin/env python3
"""OWASP ZAP traditional-json -> SARIF.

Why this exists, and it is not a nicety: ZAP's `traditional-json` template is ZAP's own format,
not SARIF. Every consumer in this lab reads SARIF — gate.sh counts `"ruleId"`, dashboard.py and
the findings view parse `runs[].results[]`. So a completed ZAP scan holding 21 alerts was counted
as **zero**, and `make gate` printed

    PASS  DAST alerts: 0 (max 40)

over a High and six Mediums. The same failure family as the `sarif_count` bug: the lab approving
what it cannot parse. A tool whose output nothing reads has not been run, whatever the log says.

ZAP's own SARIF template would be preferable — native config over conversion is this lab's rule —
but it is not present in the zap-stable image's reports addon, and depending on a template that
may or may not ship is how a pipeline silently stops producing a file.

Usage: zap-sarif.py <reports_dir>/zap
"""
from __future__ import annotations

import html
import json
import os
import re
import sys

TAGS = ("html2text", re.compile(r"<[^>]+>"))

# ZAP risk -> the lab's vocabulary. `dashboard.severity_of` reads properties.tags first, so
# writing the word here means the report shows what ZAP decided, not a re-derivation.
RISK = {"High": "high", "Medium": "medium", "Low": "low", "Informational": "low"}
LEVEL = {"high": "error", "medium": "warning", "low": "note"}


def strip_html(text: str) -> str:
    return " ".join(html.unescape(TAGS[1].sub(" ", text or "")).split())


def main() -> int:
    if len(sys.argv) < 2:
        print("usage: zap-sarif.py <zap reports dir>", file=sys.stderr)
        return 2
    d = sys.argv[1]
    src = os.path.join(d, "zap-report.json")
    try:
        with open(src, encoding="utf-8") as fh:
            doc = json.load(fh)
    except (OSError, ValueError) as exc:
        # No SARIF is written when there is nothing to convert. An absent file means NOT RUN;
        # an empty one would claim the scan happened and found nothing.
        print(f"zap: no report to convert ({exc})", file=sys.stderr)
        return 1

    results, rules = [], {}
    for site in doc.get("site", []):
        for alert in site.get("alerts", []):
            sev = RISK.get((alert.get("riskdesc") or "").split(" ")[0], "low")
            rid = f"zap-{alert.get('pluginid', '0')}"
            rules[rid] = {
                "id": rid,
                "name": alert.get("alert", rid),
                "shortDescription": {"text": alert.get("alert", "")[:200]},
                "fullDescription": {"text": strip_html(alert.get("desc", ""))[:900]},
                "help": {"text": strip_html(alert.get("solution", ""))[:900]},
                "properties": {
                    "tags": [sev] + ([f"CWE-{alert['cweid']}"] if alert.get("cweid") else []),
                },
            }
            # One SARIF result per INSTANCE, not per alert. ZAP groups by rule; the lab triages
            # by location, and "5 instances" collapsed into one row hides four of the five URLs
            # a person has to look at.
            for inst in alert.get("instances", []) or [{}]:
                detail = " · ".join(x for x in [
                    f"param: {inst['param']}" if inst.get("param") else "",
                    f"attack: {inst['attack'][:120]}" if inst.get("attack") else "",
                    f"evidence: {inst['evidence'][:120]}" if inst.get("evidence") else "",
                ] if x)
                results.append({
                    "ruleId": rid,
                    "level": LEVEL.get(sev, "warning"),
                    "message": {"text": " — ".join(
                        x for x in [alert.get("alert", ""), detail] if x)},
                    "locations": [{"physicalLocation": {
                        # The "file" of a DAST finding is a URL. Keeping it in artifactLocation
                        # is what lets the findings view group and filter DAST alongside SAST.
                        "artifactLocation": {"uri": inst.get("uri", site.get("@name", ""))},
                        "region": {"startLine": 1},
                    }}],
                })

    sarif = {
        "version": "2.1.0",
        "$schema": "https://json.schemastore.org/sarif-2.1.0.json",
        "runs": [{
            "tool": {"driver": {"name": "OWASP ZAP", "rules": list(rules.values())}},
            "results": results,
        }],
    }
    out = os.path.join(d, "zap.sarif")
    with open(out, "w", encoding="utf-8") as fh:
        json.dump(sarif, fh, indent=1, ensure_ascii=False)
    print(f"zap: {len(results)} findings ({len(rules)} rules) -> {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
