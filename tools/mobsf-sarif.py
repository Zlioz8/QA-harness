#!/usr/bin/env python3
"""MobSF report_json -> SARIF.

Same reason as zap-sarif.py and qodana-sarif.py: everything downstream in this lab reads SARIF —
gate.sh counts results, dashboard.py renders them, the triage view lists them. A dimension whose
output nothing parses has not been run, whatever the log said. MobSF speaks its own JSON, with a
different shape per section (and the shapes move between MobSF releases), so the walk below is
deliberately defensive: an unknown section is skipped, never guessed at.

Sections consumed, and why each is a finding source and not decoration:

  manifest_analysis    what the shipped manifest permits (exported components, backup, cleartext)
  code_analysis        patterns found in the DECOMPILED bundle — including code no repository
                       under audit contains, because it arrived with a dependency
  network_security     the trust decisions the binary actually carries
  certificate_analysis how the artifact was signed (v1-only, debug certificate, weak digest)
  binary_analysis      native library hardening
  permissions          dangerous permissions as declared by the installed package
  trackers             third-party analytics compiled in

Usage: mobsf-sarif.py <reports_dir>/mobile [artifact_relpath]
"""
from __future__ import annotations

import json
import os
import sys

# MobSF's vocabulary -> the lab's. dashboard.severity_of reads properties.tags first, so the word
# written here is the severity MobSF assigned, not one re-derived from a score.
SEV = {
    "high": "high", "warning": "medium", "medium": "medium",
    "info": "low", "secure": "low", "good": "low", "hotspot": "medium",
}
LEVEL = {"high": "error", "medium": "warning", "low": "note"}


def norm(sev: str) -> str:
    return SEV.get(str(sev or "").strip().lower(), "medium")


def result(rule_id: str, message: str, sev: str, artifact: str, extra: str = "") -> dict:
    sev = norm(sev)
    text = message if not extra else f"{message} [{extra}]"
    return {
        "ruleId": rule_id,
        "level": LEVEL[sev],
        "message": {"text": text.strip()[:1800] or rule_id},
        "properties": {"tags": [sev]},
        "locations": [{
            "physicalLocation": {
                "artifactLocation": {"uri": artifact},
                "region": {"startLine": 1},
            }
        }],
    }


def walk(doc: dict, artifact: str) -> list[dict]:
    out: list[dict] = []

    # manifest_analysis: {"manifest_findings": [{rule, title, severity, description, name}]}
    man = doc.get("manifest_analysis") or {}
    for f in (man.get("manifest_findings") or man.get("manifest") or []):
        if not isinstance(f, dict):
            continue
        out.append(result(
            f"mobsf.manifest.{f.get('rule', 'finding')}",
            f.get("title") or f.get("desc") or f.get("description") or "manifest finding",
            f.get("severity", "warning"), artifact,
            ", ".join(f.get("component", []) if isinstance(f.get("component"), list) else []),
        ))

    # code_analysis: {"findings": {rule_id: {metadata:{severity,description,cvss,...}, files:{}}}}
    code = (doc.get("code_analysis") or {}).get("findings") or {}
    for rule_id, f in code.items() if isinstance(code, dict) else []:
        meta = (f or {}).get("metadata", {}) if isinstance(f, dict) else {}
        files = list(((f or {}).get("files") or {}).keys())[:3] if isinstance(f, dict) else []
        out.append(result(
            f"mobsf.code.{rule_id}",
            meta.get("description") or rule_id,
            meta.get("severity", "warning"), artifact,
            ", ".join(files),
        ))

    # network_security: {"network_findings": [{scope, severity, description}]}
    for f in ((doc.get("network_security") or {}).get("network_findings") or []):
        if not isinstance(f, dict):
            continue
        scope = f.get("scope")
        out.append(result(
            "mobsf.network.trust",
            f.get("description") or "network security config finding",
            f.get("severity", "warning"), artifact,
            ", ".join(scope) if isinstance(scope, list) else str(scope or ""),
        ))

    # certificate_analysis: {"certificate_findings": [[severity, description, title], ...]}
    for f in ((doc.get("certificate_analysis") or {}).get("certificate_findings") or []):
        if isinstance(f, (list, tuple)) and len(f) >= 2:
            out.append(result("mobsf.certificate", str(f[1]), str(f[0]), artifact))
        elif isinstance(f, dict):
            out.append(result("mobsf.certificate",
                              f.get("description", "certificate finding"),
                              f.get("severity", "warning"), artifact))

    # binary_analysis: [{name, nx:{severity,description}, ...}]
    for lib in (doc.get("binary_analysis") or []):
        if not isinstance(lib, dict):
            continue
        name = lib.get("name", "native library")
        for key, val in lib.items():
            if isinstance(val, dict) and "severity" in val:
                out.append(result(f"mobsf.binary.{key}",
                                  val.get("description", key), val["severity"], artifact, name))

    # permissions: {"android.permission.X": {status, info, description}}
    perms = doc.get("permissions") or {}
    for name, meta in perms.items() if isinstance(perms, dict) else []:
        if not isinstance(meta, dict):
            continue
        if str(meta.get("status", "")).lower() in ("dangerous", "signatureorsystem"):
            out.append(result("mobsf.permission.dangerous",
                              f"{name}: {meta.get('description', meta.get('info', ''))}",
                              "warning", artifact, meta.get("status", "")))

    # trackers: {"trackers": [{name, categories}]}
    for t in ((doc.get("trackers") or {}).get("trackers") or []):
        if isinstance(t, dict):
            out.append(result("mobsf.tracker",
                              f"Third-party tracker compiled into the bundle: {t.get('name')}",
                              "info", artifact, t.get("categories", "")))

    # Secrets MobSF found in the decompiled bundle. Distinct from gitleaks: this is what SHIPPED,
    # which includes strings injected at build time and never present in any repository.
    for s in (doc.get("secrets") or []):
        out.append(result("mobsf.secret", f"Possible hardcoded secret in the bundle: {s}",
                          "high", artifact))

    return out


def main() -> int:
    if len(sys.argv) < 2:
        print("usage: mobsf-sarif.py <mobile reports dir> [artifact path]", file=sys.stderr)
        return 2
    d = sys.argv[1]
    artifact = sys.argv[2] if len(sys.argv) > 2 else "artifact.apk"
    try:
        with open(os.path.join(d, "mobsf.json"), encoding="utf-8") as fh:
            doc = json.load(fh)
    except (OSError, ValueError) as exc:
        # No SARIF written when there is nothing to convert: an absent file reads as NOT RUN,
        # an empty one would claim a clean scan.
        print(f"mobsf: no report to convert ({exc})", file=sys.stderr)
        return 1

    results = walk(doc, artifact)
    sarif = {
        "version": "2.1.0",
        "$schema": "https://json.schemastore.org/sarif-2.1.0.json",
        "runs": [{
            "tool": {"driver": {
                "name": "MobSF",
                "informationUri": "https://mobsf.github.io/docs/",
                "version": str(doc.get("version", "")),
            }},
            "results": results,
        }],
    }
    out = os.path.join(d, "mobsf.sarif")
    with open(out, "w", encoding="utf-8") as fh:
        json.dump(sarif, fh, indent=1)

    app = doc.get("app_name") or doc.get("file_name") or artifact
    print(f"mobsf: {len(results)} findings -> {out}  ({app}, "
          f"{doc.get('package_name', '?')} v{doc.get('version_name', '?')})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
