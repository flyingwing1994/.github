#!/usr/bin/env python3
"""Zet issues op het centrale GitHub Project-bord. Zie WORKFLOW.md §2 en CHECKS.md.

Gebruik (in GitHub Actions; leest het event uit $GITHUB_EVENT_PATH):
    python bord.py --eigenaar flyingwing1994 --project 1 --sjablonen <pad naar .github/ISSUE_TEMPLATE>

Omgeving:
    PROJECT_TOKEN  classic token met alleen `project`-scope (bord lezen/schrijven)
    GH_TOKEN       workflow-token (repo lezen, label `wacht-op-info` zetten)

Gedrag:
- Issue geopend/bewerkt/heropend: op het bord, veld Prioriteit uit `### Prioriteit`.
  Kolom Gepland als de verplichte sjabloonvelden en de prioriteit zijn ingevuld, anders Idee
  + label `wacht-op-info`. Alleen zolang het kaartje in Idee of Gepland (of nergens) staat.
- PR (niet vanaf een fork): elk issue dat de PR sluit (`Closes #nr`) naar Bezig, of naar
  In review als de PR het label `risico` heeft. Nooit terug uit Klaar.
- Klaar regelen de ingebouwde workflows van het Project (item closed / PR merged).
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path

PRIORITEITEN = ("Urgent", "Hoog", "Middel", "Laag")
VROEG = {None, "", "Idee", "Gepland"}
LEEG = {"", "_no response_", "none"}


# --------------------------------------------------------------------------- issuetekst
def secties(body: str) -> dict[str, str]:
    """`### Kop` + inhoud, zoals GitHub issue-formulieren en de API-sjablonen ze schrijven."""
    uit: dict[str, str] = {}
    kop = None
    regels: list[str] = []
    for regel in (body or "").splitlines():
        m = re.match(r"^###\s+(.+?)\s*$", regel)
        if m:
            if kop is not None:
                uit[kop] = "\n".join(regels).strip()
            kop, regels = m.group(1).strip(), []
        elif kop is not None:
            regels.append(regel)
    if kop is not None:
        uit[kop] = "\n".join(regels).strip()
    return uit


def prioriteit(s: dict[str, str]) -> str | None:
    waarde = (s.get("Prioriteit") or "").strip().splitlines()
    return waarde[0].strip() if waarde and waarde[0].strip() in PRIORITEITEN else None


def leeg(waarde: str, standaard: str = "") -> bool:
    w = (waarde or "").strip()
    return w.lower() in LEEG or (standaard.strip() != "" and w == standaard.strip())


def verplichte_velden(sjabloon: dict) -> list[tuple[str, str]]:
    """(label, standaardwaarde) van verplichte velden in een issue-formulier."""
    uit = []
    for veld in sjabloon.get("body") or []:
        if (veld.get("validations") or {}).get("required") and veld.get("type") != "markdown":
            attr = veld.get("attributes") or {}
            uit.append((str(attr.get("label", "")).strip(), str(attr.get("value") or "")))
    return uit


def triage_compleet(body: str, labels: set[str], sjablonen: list[dict]) -> tuple[bool, list[str]]:
    """Compleet = prioriteit geldig + alle verplichte velden van het passende sjabloon gevuld."""
    s = secties(body)
    ontbreekt = [] if prioriteit(s) else ["Prioriteit"]
    for sj in sjablonen:
        if set(sj.get("labels") or []) & labels:
            for label, standaard in verplichte_velden(sj):
                if label != "Prioriteit" and leeg(s.get(label, ""), standaard):
                    ontbreekt.append(label)
            break
    return not ontbreekt, ontbreekt


def doelstatus_pr(heeft_risico: bool, huidig: str | None) -> str | None:
    if huidig == "Klaar":
        return None
    return "In review" if heeft_risico else "Bezig"


def doelstatus_issue(compleet: bool, huidig: str | None) -> str | None:
    if huidig not in VROEG:
        return None
    return "Gepland" if compleet else "Idee"


# --------------------------------------------------------------------------- GitHub
def graphql(token: str, query: str, **variabelen) -> dict:
    payload = {"query": query, "variables": variabelen}
    env = {**os.environ, "GH_TOKEN": token}
    uit = subprocess.run(["gh", "api", "graphql", "--input", "-"], input=json.dumps(payload),
                         capture_output=True, text=True, env=env)
    data = json.loads(uit.stdout or "{}")
    if uit.returncode or data.get("errors"):
        raise SystemExit(f"GraphQL-fout: {data.get('errors') or uit.stderr.strip()}")
    return data["data"]


def rest(*args: str, data: dict | None = None) -> None:
    cmd = ["gh", "api", *args, "--silent"]
    if data is not None:
        cmd += ["--input", "-"]
    subprocess.run(cmd, input=json.dumps(data) if data is not None else None, check=True, text=True)


Q_PROJECT = """query($login:String!,$nr:Int!){ user(login:$login){ projectV2(number:$nr){ id
  fields(first:50){ nodes{ ... on ProjectV2SingleSelectField { id name options { id name } } } } } } }"""
M_ADD = """mutation($p:ID!,$c:ID!){ addProjectV2ItemById(input:{projectId:$p,contentId:$c}){ item{ id
  fieldValueByName(name:"Status"){ ... on ProjectV2ItemFieldSingleSelectValue { name } } } } }"""
M_SET = """mutation($p:ID!,$i:ID!,$f:ID!,$o:String!){ updateProjectV2ItemFieldValue(input:{projectId:$p,
  itemId:$i,fieldId:$f,value:{singleSelectOptionId:$o}}){ projectV2Item{ id } } }"""
Q_SLUIT = """query($o:String!,$r:String!,$n:Int!){ repository(owner:$o,name:$r){ pullRequest(number:$n){
  closingIssuesReferences(first:20){ nodes{ id number repository{ nameWithOwner } } } } } }"""


class Bord:
    def __init__(self, token: str, eigenaar: str, nummer: int):
        self.token = token
        p = graphql(token, Q_PROJECT, login=eigenaar, nr=nummer)["user"]["projectV2"]
        if not p:
            raise SystemExit(f"Project {nummer} van {eigenaar} niet gevonden (token of nummer?).")
        self.id = p["id"]
        self.velden = {f["name"]: f for f in p["fields"]["nodes"] if f}
        for naam in ("Status", "Prioriteit"):
            if naam not in self.velden:
                gevonden = ", ".join(repr(n) for n in self.velden) or "geen"
                raise SystemExit(f"Veld '{naam}' (single select) ontbreekt op het bord. "
                                 f"Gevonden single select-velden: {gevonden}.")

    def toevoegen(self, content_id: str) -> tuple[str, str | None]:
        item = graphql(self.token, M_ADD, p=self.id, c=content_id)["addProjectV2ItemById"]["item"]
        return item["id"], (item.get("fieldValueByName") or {}).get("name")

    def zet(self, item: str, veld: str, waarde: str) -> None:
        f = self.velden[veld]
        optie = next((o["id"] for o in f["options"] if o["name"] == waarde), None)
        if optie is None:
            opties = ", ".join(repr(o["name"]) for o in f["options"])
            raise SystemExit(f"Optie '{waarde}' ontbreekt in veld '{veld}' op het bord. Gevonden: {opties}.")
        graphql(self.token, M_SET, p=self.id, i=item, f=f["id"], o=optie)
        print(f"{veld} → {waarde}")


# --------------------------------------------------------------------------- afhandeling
def laad_sjablonen(map_: str | None) -> list[dict]:
    if not map_ or not Path(map_).is_dir():
        return []
    import yaml  # alleen hier nodig

    return [yaml.safe_load(p.read_text(encoding="utf-8")) or {}
            for p in sorted(Path(map_).glob("*.y*ml")) if p.name != "config.yml"]


def issue(bord: Bord, ev: dict, sjablonen: list[dict]) -> None:
    iss = ev["issue"]
    if iss.get("pull_request"):
        return
    labels = {l["name"] for l in iss.get("labels") or []}
    compleet, ontbreekt = triage_compleet(iss.get("body") or "", labels, sjablonen)
    item, huidig = bord.toevoegen(iss["node_id"])
    prio = prioriteit(secties(iss.get("body") or ""))
    if prio:
        bord.zet(item, "Prioriteit", prio)
    doel = doelstatus_issue(compleet, huidig)
    if doel:
        bord.zet(item, "Status", doel)
    if doel == "Idee":
        print(f"Triage onvolledig, ontbreekt: {', '.join(ontbreekt)}")
    repo, nr = ev["repository"]["full_name"], iss["number"]
    if doel == "Idee" and "wacht-op-info" not in labels:
        rest(f"repos/{repo}/issues/{nr}/labels", data={"labels": ["wacht-op-info"]})
    elif doel == "Gepland" and "wacht-op-info" in labels:
        rest("-X", "DELETE", f"repos/{repo}/issues/{nr}/labels/wacht-op-info")


def pull_request(bord: Bord, ev: dict) -> None:
    pr = ev["pull_request"]
    if pr["head"]["repo"]["full_name"] != ev["repository"]["full_name"]:
        print("PR vanaf een fork: bord niet bijgewerkt.")
        return
    eigenaar, naam = ev["repository"]["full_name"].split("/")
    refs = graphql(os.environ["GH_TOKEN"], Q_SLUIT, o=eigenaar, r=naam, n=pr["number"])
    issues = refs["repository"]["pullRequest"]["closingIssuesReferences"]["nodes"]
    risico = any(l["name"] == "risico" for l in pr.get("labels") or [])
    if not issues:
        print("PR sluit geen issues: bord niet bijgewerkt.")
    for iss in issues:
        if not iss["repository"]["nameWithOwner"].startswith(eigenaar + "/"):
            continue
        item, huidig = bord.toevoegen(iss["id"])
        doel = doelstatus_pr(risico, huidig)
        print(f"Issue {iss['repository']['nameWithOwner']}#{iss['number']}: {huidig} → {doel}")
        if doel and doel != huidig:
            bord.zet(item, "Status", doel)


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--eigenaar", required=True)
    p.add_argument("--project", type=int, required=True)
    p.add_argument("--sjablonen")
    a = p.parse_args()
    ev = json.loads(Path(os.environ["GITHUB_EVENT_PATH"]).read_text(encoding="utf-8"))
    token = os.environ.get("PROJECT_TOKEN")
    if not token:
        print("::error::Secret PROJECT_TOKEN ontbreekt.")
        return 1
    bord = Bord(token, a.eigenaar, a.project)
    if "pull_request" in ev:
        pull_request(bord, ev)
    elif "issue" in ev:
        issue(bord, ev, laad_sjablonen(a.sjablonen))
    return 0


if __name__ == "__main__":
    sys.exit(main())
