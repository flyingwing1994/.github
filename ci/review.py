#!/usr/bin/env python3
"""Verwerkt het oordeel van de Claude-review en de second opinion. Zie CHECKS.md en WORKFLOW.md §5.

Claude zelf kan alleen lezen. Dit script zet op basis van Claude's gestructureerde uitvoer
het PR-commentaar, het label `risico` en het uitlegblok bovenaan de PR.

Gebruik (in GitHub Actions):
    python review.py vorige  --soort review|second   # eerder oordeel voor dit commit hergebruiken?
    python review.py verwerk --soort review|second   # oordeel uit $OUTPUT verwerken

Omgeving: GH_TOKEN, REPO, PR, HEAD_SHA, en voor `verwerk` OUTPUT (JSON van claude-code-action).
Exitcode 1 bij BLOKKEREND of als er geen geldig oordeel is (fail-closed).
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys

BOT = "github-actions[bot]"
OORDELEN = {"review": {"OK", "RISICO", "BLOKKEREND"}, "second": {"OK", "BLOKKEREND"}}
TITELS = {"review": "Claude-review", "second": "Second opinion (beveiliging)"}
BLOK_START = "<!-- claude-risico:start -->"
BLOK_EIND = "<!-- claude-risico:end -->"
RE_MARKER = re.compile(r"<!-- claude-(review|second) sha=([0-9a-f]+) oordeel=([A-Z]+) tweede=(true|false) -->")


# --------------------------------------------------------------------------- GitHub
def gh(*args: str, data: dict | None = None) -> object:
    cmd = ["gh", "api", *args]
    if data is not None:
        cmd += ["--input", "-"]
    uit = subprocess.run(cmd, input=json.dumps(data) if data is not None else None,
                         check=True, capture_output=True, text=True).stdout
    return json.loads(uit) if uit.strip() else None


def commentaren(repo: str, pr: str) -> list[dict]:
    uit: list[dict] = []
    pagina = 1
    while True:
        deel = gh(f"repos/{repo}/issues/{pr}/comments?per_page=100&page={pagina}")
        uit += deel
        if len(deel) < 100:
            return uit
        pagina += 1


def eigen_commentaar(alle: list[dict], soort: str) -> tuple[dict | None, re.Match | None]:
    for c in alle:
        if (c.get("user") or {}).get("login") != BOT:
            continue
        m = RE_MARKER.search(c.get("body") or "")
        if m and m.group(1) == soort:
            return c, m
    return None, None


# --------------------------------------------------------------------------- opmaak
def schoon(tekst: object, max_len: int = 6000) -> str:
    """Claude-tekst ontdoen van HTML-commentaar (markers) en inkorten."""
    t = str(tekst or "").replace("<!--", "&lt;!--").replace("-->", "--&gt;").strip()
    return t if len(t) <= max_len else t[:max_len] + "\n\n… (ingekort)"


def citaat(tekst: str) -> str:
    return "\n".join("> " + r if r else ">" for r in tekst.splitlines())


def risicoblok(o: dict) -> str:
    regels = [
        "**Risicovlag — Michiel merget zelf.**",
        f"**Wat verandert er:** {schoon(o.get('samenvatting'), 1500)}",
        f"**Risico:** {schoon(o.get('risico'), 1500)}",
        f"**Advies:** {schoon(o.get('advies'), 1500)}",
    ]
    return BLOK_START + "\n" + citaat("\n".join(regels)) + "\n" + BLOK_EIND


def met_blok(body: str, blok: str) -> str:
    body = body or ""
    if BLOK_START in body and BLOK_EIND in body:
        voor, rest = body.split(BLOK_START, 1)
        _, na = rest.split(BLOK_EIND, 1)
        return voor + blok + na
    return blok + "\n\n" + body


def commentaar(soort: str, o: dict, sha: str, tweede: bool) -> str:
    oordeel = o["oordeel"]
    icoon = {"OK": "✅", "RISICO": "⚠️", "BLOKKEREND": "❌"}[oordeel]
    regels = [
        f"<!-- claude-{soort} sha={sha} oordeel={oordeel} tweede={'true' if tweede else 'false'} -->",
        f"## {TITELS[soort]}: {icoon} {oordeel}",
        "",
        f"_Commit `{sha[:7]}`_",
        "",
    ]
    if o.get("samenvatting"):
        regels += [schoon(o["samenvatting"], 1500), ""]
    if o.get("bevindingen"):
        regels += ["### Bevindingen", "", schoon(o["bevindingen"]), ""]
    if oordeel == "BLOKKEREND" and o.get("advies"):
        regels += ["### Wat moet er gebeuren", "", schoon(o["advies"], 1500), ""]
    if soort == "review" and tweede:
        regels += ["_Second opinion (beveiliging) volgt._", ""]
    regels += ["---", "_Automatische review door Claude via [Claude Code](https://claude.ai/code)._"]
    return "\n".join(regels)


# --------------------------------------------------------------------------- acties
def schrijf(var: str, tekst: str) -> None:
    pad = os.environ.get(var)
    if pad:
        with open(pad, "a", encoding="utf-8") as f:
            f.write(tekst)


def vorige(soort: str) -> int:
    repo, pr, sha = os.environ["REPO"], os.environ["PR"], os.environ["HEAD_SHA"]
    _, m = eigen_commentaar(commentaren(repo, pr), soort)
    if m and m.group(2) == sha:
        print(f"Dit commit is al beoordeeld: {m.group(3)}. Oordeel hergebruikt.")
        schrijf("GITHUB_OUTPUT", f"hergebruik=true\noordeel={m.group(3)}\ntweede={m.group(4)}\n")
        return 1 if m.group(3) == "BLOKKEREND" else 0
    schrijf("GITHUB_OUTPUT", "hergebruik=false\n")
    return 0


def verwerk(soort: str) -> int:
    repo, pr, sha = os.environ["REPO"], os.environ["PR"], os.environ["HEAD_SHA"]
    try:
        o = json.loads(os.environ.get("OUTPUT") or "")
    except json.JSONDecodeError:
        o = {}
    if not isinstance(o, dict) or o.get("oordeel") not in OORDELEN[soort]:
        print("::error::Geen geldig oordeel van Claude: check faalt (fail-closed).")
        return 1

    tweede = False
    if soort == "review":
        labels = {l["name"] for l in gh(f"repos/{repo}/issues/{pr}/labels")}
        tweede = o["oordeel"] == "RISICO" or bool(o.get("beveiligingsgevoelig")) or "risico" in labels
        if o["oordeel"] == "RISICO":
            gh(f"repos/{repo}/issues/{pr}/labels", data={"labels": ["risico"]})
            body = gh(f"repos/{repo}/pulls/{pr}")["body"] or ""
            gh("-X", "PATCH", f"repos/{repo}/pulls/{pr}", data={"body": met_blok(body, risicoblok(o))})

    tekst = commentaar(soort, o, sha, tweede)
    bestaand, _ = eigen_commentaar(commentaren(repo, pr), soort)
    if bestaand:
        gh("-X", "PATCH", f"repos/{repo}/issues/comments/{bestaand['id']}", data={"body": tekst})
    else:
        gh(f"repos/{repo}/issues/{pr}/comments", data={"body": tekst})

    print(tekst)
    schrijf("GITHUB_STEP_SUMMARY", tekst + "\n")
    schrijf("GITHUB_OUTPUT", f"oordeel={o['oordeel']}\ntweede={'true' if tweede else 'false'}\n")
    return 1 if o["oordeel"] == "BLOKKEREND" else 0


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("actie", choices=["vorige", "verwerk"])
    p.add_argument("--soort", choices=["review", "second"], required=True)
    a = p.parse_args()
    return vorige(a.soort) if a.actie == "vorige" else verwerk(a.soort)


if __name__ == "__main__":
    sys.exit(main())
