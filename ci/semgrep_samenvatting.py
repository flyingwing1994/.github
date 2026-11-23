#!/usr/bin/env python3
"""Leest Semgrep-JSON en schrijft een samenvatting. Zie WORKFLOW.md §4 en CHECKS.md.

Gebruik: python semgrep_samenvatting.py semgrep.json
Exitcode 1 bij minstens één blokkerende bevinding (ERROR) of als Semgrep zelf fouten meldde
die de scan onbetrouwbaar maken (fail-closed). WARNING en INFO zijn alleen informatief.
"""
from __future__ import annotations

import json
import os
import sys

BLOKKEREND = {"ERROR", "CRITICAL", "HIGH"}


def main(pad: str) -> int:
    with open(pad, encoding="utf-8") as f:
        data = json.load(f)
    bevindingen = data.get("results") or []
    fouten = [e for e in data.get("errors") or [] if str(e.get("level", "")).lower() == "error"]

    blok = [b for b in bevindingen if str(b.get("extra", {}).get("severity", "")).upper() in BLOKKEREND]
    rest = [b for b in bevindingen if b not in blok]

    regels = ["## Semgrep (alleen nieuwe bevindingen in deze PR)", ""]
    if not bevindingen and not fouten:
        regels.append("✅ Geen nieuwe bevindingen.")
    for titel, lijst in (("❌ Blokkerend (ERROR)", blok), ("⚠️ Waarschuwing (WARNING/INFO)", rest)):
        if lijst:
            regels += [f"### {titel}: {len(lijst)}", ""]
            for b in lijst[:50]:
                extra = b.get("extra", {})
                bericht = " ".join(str(extra.get("message", "")).split())[:300]
                regels.append(f"- `{b.get('path')}:{b.get('start', {}).get('line')}` `{b.get('check_id')}`: {bericht}")
            regels.append("")
    if fouten:
        regels += [f"### ❌ Semgrep meldde {len(fouten)} fout(en); scan niet betrouwbaar", ""]
        regels += [f"- {' '.join(str(e.get('message', '')).split())[:300]}" for e in fouten[:10]]

    tekst = "\n".join(regels) + "\n"
    print(tekst)
    if os.environ.get("GITHUB_STEP_SUMMARY"):
        with open(os.environ["GITHUB_STEP_SUMMARY"], "a", encoding="utf-8") as f:
            f.write(tekst)
    for b in blok:
        print(f"::error file={b.get('path')},line={b.get('start', {}).get('line')}::{b.get('check_id')}")
    return 1 if blok or fouten else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1]))
