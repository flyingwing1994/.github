#!/usr/bin/env python3
"""Proces-check voor PR's: issue-koppeling en de vaste risicoregels (1-8) uit WORKFLOW.md §5.

Gebruik (lokaal of in GitHub Actions, vanuit de root van de repo die de PR bevat):
    python risico.py --base BASE_SHA --head HEAD_SHA

De PR-tekst en -auteur komen uit de omgevingsvariabelen PR_BODY en PR_AUTHOR
(nooit via de opdrachtregel, zodat tekst uit de PR niet als code kan worden uitgevoerd).

Uitkomst:
- Uitleg in de log en, in Actions, in de job-samenvatting.
- GITHUB_OUTPUT krijgt `risico=true|false`.
- Exitcode 1 als de issue-koppeling ontbreekt. Een risicovlag laat de check NIET falen;
  die blokkeert alleen de auto-merge (via het label `risico`).

Alleen de standaardbibliotheek (Python 3.11+).
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import tomllib
from dataclasses import dataclass
from typing import Callable

MAX_REGELS = 400

# Lockfiles tellen niet mee voor regel 7: ze groeien mee met elke package-update.
LOCKFILES = {
    "package-lock.json", "npm-shrinkwrap.json", "yarn.lock", "pnpm-lock.yaml", "bun.lockb",
    "poetry.lock", "uv.lock", "Pipfile.lock", "Cargo.lock", "go.sum", "composer.lock", "Gemfile.lock",
}

# Bots die geen issue hoeven te koppelen.
BOTS = {"dependabot[bot]", "github-actions[bot]"}

RE_ISSUE = re.compile(
    r"\b(close[sd]?|fix(e[sd])?|resolve[sd]?)\s*:?\s+([\w.-]+/[\w.-]+)?#\d+", re.IGNORECASE
)

# Regel 3: geheimen, auth of login (op pad; de inhoud beoordeelt de Claude-review).
RE_GEHEIM = re.compile(
    r"(^|[/._-])(secrets?|geheim\w*|auth\w*|oauth\w*|login\w*|passw\w*|wachtwoord\w*|credentials?|tokens?)([/._-]|$)"
    r"|(^|/)\.env(\.[\w.-]+)?$|\.(pem|key|p12|pfx)$",
    re.IGNORECASE,
)
# Regel 4: database-schema's of migraties.
RE_DATABASE = re.compile(
    r"(^|/)(migrations?|alembic|prisma)(/|$)|(^|/)schema\.(sql|prisma|rb)$|\.sql$", re.IGNORECASE
)
# Regel 5: deploy- of infraconfig.
RE_INFRA = re.compile(
    r"(^|/)(dockerfile[^/]*|[^/]*\.dockerfile|(docker-)?compose[^/]*\.ya?ml|caddyfile|nginx[^/]*\.conf"
    r"|[^/]*\.tf|fly\.toml|wrangler\.toml|vercel\.json|netlify\.toml|cloudflared[^/]*|[^/]*tunnel[^/]*)$"
    r"|(^|/)(infra|deploy|k8s|kubernetes|cloudflared|nginx|network|netwerk)/",
    re.IGNORECASE,
)

# Regel 8: instructies voor Claude en beheerscripts.
RE_AI = re.compile(r"(^|/)(CLAUDE\.md|AGENTS\.md)$|(^|/)\.claude/|^skills/|^scripts/", re.IGNORECASE)

REGELS = {
    1: "raakt `.github/workflows/`",
    2: "verwijdert bestanden of mappen",
    3: "raakt geheimen, auth of login",
    4: "raakt database-schema's of migraties",
    5: "raakt deploy- of infraconfig",
    6: "nieuwe packages of grote versiesprongen",
    7: f"meer dan {MAX_REGELS} gewijzigde regels (lockfiles niet meegeteld)",
    8: "raakt instructies voor Claude of beheerscripts (`CLAUDE.md`, `.claude/`, `skills/`, `scripts/`)",
}


@dataclass
class Wijziging:
    status: str  # A, M, D, R, C, T
    pad: str
    oud_pad: str | None = None
    toegevoegd: int = 0
    verwijderd: int = 0


# --------------------------------------------------------------------------- versies
def major(versie: str) -> tuple[int, int] | None:
    """Geeft (major, minor) van een versiespecificatie, of None als die niet te lezen is.

    Bij 0.x telt de minor als 'major', want daar is elke minor-sprong mogelijk brekend.
    """
    m = re.search(r"(\d+)(?:\.(\d+|x|\*))?", versie or "")
    if not m:
        return None
    hoofd = int(m.group(1))
    sub = m.group(2)
    minor = int(sub) if sub and sub.isdigit() else 0
    return (hoofd, minor if hoofd == 0 else 0)


def is_sprong(oud: str, nieuw: str) -> bool:
    a, b = major(oud), major(nieuw)
    return a is not None and b is not None and a != b


def npm_deps(tekst: str) -> dict[str, str]:
    try:
        data = json.loads(tekst) if tekst.strip() else {}
    except json.JSONDecodeError:
        return {}
    deps: dict[str, str] = {}
    for sectie in ("dependencies", "devDependencies", "optionalDependencies", "peerDependencies"):
        deps.update({k: str(v) for k, v in (data.get(sectie) or {}).items()})
    return deps


RE_PEP508 = re.compile(r"^\s*([A-Za-z0-9][A-Za-z0-9._-]*)\s*(\[[^\]]*\])?\s*(.*)$")


def pep508(regel: str) -> tuple[str, str] | None:
    regel = regel.split("#", 1)[0].strip()
    if not regel or regel.startswith("-"):
        return None
    m = RE_PEP508.match(regel)
    if not m:
        return None
    naam = re.sub(r"[-_.]+", "-", m.group(1)).lower()
    return naam, m.group(3).split(";", 1)[0].strip()


def py_deps_requirements(tekst: str) -> dict[str, str]:
    return dict(filter(None, (pep508(r) for r in tekst.splitlines())))


def py_deps_pyproject(tekst: str) -> dict[str, str]:
    try:
        data = tomllib.loads(tekst) if tekst.strip() else {}
    except tomllib.TOMLDecodeError:
        return {}
    project = data.get("project") or {}
    regels = list(project.get("dependencies") or [])
    for groep in (project.get("optional-dependencies") or {}).values():
        regels.extend(groep)
    for groep in (data.get("dependency-groups") or {}).values():
        regels.extend(r for r in groep if isinstance(r, str))
    return dict(filter(None, (pep508(r) for r in regels)))


def lezer_voor(pad: str) -> Callable[[str], dict[str, str]] | None:
    naam = pad.rsplit("/", 1)[-1]
    if naam == "package.json":
        return npm_deps
    if re.fullmatch(r"requirements[\w.-]*\.(txt|in)", naam):
        return py_deps_requirements
    if naam == "pyproject.toml":
        return py_deps_pyproject
    return None


def package_bevindingen(w: Wijziging, lees_base: Callable[[str], str], lees_head: Callable[[str], str]) -> list[str]:
    lezer = lezer_voor(w.pad)
    if lezer is None or w.status == "D":
        return []
    oud = lezer(lees_base(w.oud_pad or w.pad)) if w.status != "A" else {}
    nieuw = lezer(lees_head(w.pad))
    uit: list[str] = []
    for naam, versie in sorted(nieuw.items()):
        if naam not in oud:
            uit.append(f"nieuw package `{naam}` in `{w.pad}`")
        elif is_sprong(oud[naam], versie):
            uit.append(f"versiesprong `{naam}` {oud[naam]} → {versie} in `{w.pad}`")
    return uit


# --------------------------------------------------------------------------- beoordeling
def beoordeel(
    wijzigingen: list[Wijziging],
    lees_base: Callable[[str], str],
    lees_head: Callable[[str], str],
) -> dict[int, list[str]]:
    """Past de vaste risicoregels toe. Geeft per geraakte regel de redenen."""
    vlag: dict[int, list[str]] = {}

    def zet(regel: int, reden: str) -> None:
        vlag.setdefault(regel, []).append(reden)

    totaal = 0
    for w in wijzigingen:
        paden = [w.pad] + ([w.oud_pad] if w.oud_pad else [])
        if any(p.startswith(".github/workflows/") for p in paden):
            zet(1, f"`{w.pad}`")
        if w.status == "D":
            zet(2, f"`{w.pad}`")
        if any(RE_GEHEIM.search(p) for p in paden):
            zet(3, f"`{w.pad}`")
        if any(RE_DATABASE.search(p) for p in paden):
            zet(4, f"`{w.pad}`")
        if any(RE_INFRA.search(p) for p in paden):
            zet(5, f"`{w.pad}`")
        if any(RE_AI.search(p) for p in paden):
            zet(8, f"`{w.pad}`")
        for reden in package_bevindingen(w, lees_base, lees_head):
            zet(6, reden)
        if w.pad.rsplit("/", 1)[-1] not in LOCKFILES:
            totaal += w.toegevoegd + w.verwijderd
    if totaal > MAX_REGELS:
        zet(7, f"{totaal} regels")
    return vlag


def heeft_issue(body: str) -> bool:
    return bool(RE_ISSUE.search(body or ""))


# --------------------------------------------------------------------------- git
def git(*args: str) -> str:
    return subprocess.run(["git", *args], check=True, capture_output=True, text=True).stdout


def lees(sha: str) -> Callable[[str], str]:
    def _lees(pad: str) -> str:
        try:
            return git("show", f"{sha}:{pad}")
        except subprocess.CalledProcessError:
            return ""
    return _lees


def wijzigingen(base: str, head: str) -> list[Wijziging]:
    uit: dict[str, Wijziging] = {}
    for regel in git("diff", "--name-status", "-M", f"{base}...{head}").splitlines():
        delen = regel.split("\t")
        status = delen[0][0]
        if status in "RC":
            uit[delen[2]] = Wijziging(status, delen[2], delen[1])
        else:
            uit[delen[1]] = Wijziging(status, delen[1])
    for regel in git("diff", "--numstat", "-M", f"{base}...{head}").splitlines():
        plus, min_, pad = regel.split("\t", 2)
        if " => " in pad:  # hernoemd: neem het nieuwe pad
            pad = re.sub(r"\{([^{}]*) => ([^{}]*)\}", r"\2", pad)
            pad = pad.split(" => ")[-1].replace("//", "/")
        w = uit.get(pad)
        if w and plus != "-":
            w.toegevoegd, w.verwijderd = int(plus), int(min_)
    return list(uit.values())


# --------------------------------------------------------------------------- uitvoer
def schrijf(bestand_var: str, tekst: str) -> None:
    pad = os.environ.get(bestand_var)
    if pad:
        with open(pad, "a", encoding="utf-8") as f:
            f.write(tekst)


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--base", required=True)
    p.add_argument("--head", required=True)
    args = p.parse_args()

    body = os.environ.get("PR_BODY", "")
    auteur = os.environ.get("PR_AUTHOR", "")

    vlag = beoordeel(wijzigingen(args.base, args.head), lees(args.base), lees(args.head))
    issue_ok = auteur in BOTS or heeft_issue(body)

    regels = ["## Proces-check", ""]
    if issue_ok:
        regels.append("✅ Issue-koppeling aanwezig" + (" (bot, niet nodig)" if auteur in BOTS else "") + ".")
    else:
        regels.append("❌ Geen issue-koppeling. Zet `Closes #<nr>` in de PR-beschrijving.")
    regels.append("")
    if vlag:
        regels.append("⚠️ **Risicovlag**: label `risico` gezet. Michiel merget zelf.")
        regels.append("")
        for nr in sorted(vlag):
            regels.append(f"- Regel {nr}: {REGELS[nr]}")
            for reden in vlag[nr][:20]:
                regels.append(f"  - {reden}")
            if len(vlag[nr]) > 20:
                regels.append(f"  - … en nog {len(vlag[nr]) - 20}")
    else:
        regels.append("✅ Geen van de vaste risicoregels geraakt.")
    tekst = "\n".join(regels) + "\n"

    print(tekst)
    schrijf("GITHUB_STEP_SUMMARY", tekst)
    schrijf("GITHUB_OUTPUT", f"risico={'true' if vlag else 'false'}\n")
    return 0 if issue_ok else 1


if __name__ == "__main__":
    sys.exit(main())
