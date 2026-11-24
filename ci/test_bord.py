"""Tests voor ci/bord.py. Draaien met: python -m unittest discover -s ci"""
import os
import subprocess
import unittest
from unittest import mock

import bord

from bord import canoniek, doelstatus_issue, norm, doelstatus_pr, prioriteit, secties, triage_compleet

FEATURE = {
    "labels": ["feature"],
    "body": [
        {"type": "textarea", "attributes": {"label": "Doel"}, "validations": {"required": True}},
        {"type": "textarea", "attributes": {"label": "Gewenst gedrag", "value": "- [ ]\n"},
         "validations": {"required": True}},
        {"type": "input", "attributes": {"label": "Deadline"}},
        {"type": "dropdown", "attributes": {"label": "Prioriteit"}, "validations": {"required": True}},
    ],
}

COMPLEET = """### Doel

Iets oplossen.

### Gewenst gedrag

- [ ] werkt

### Deadline

_No response_

### Prioriteit

Hoog
"""


class Tekst(unittest.TestCase):
    def test_secties(self):
        s = secties(COMPLEET)
        self.assertEqual(s["Doel"], "Iets oplossen.")
        self.assertEqual(s["Deadline"], "_No response_")

    def test_prioriteit(self):
        self.assertEqual(prioriteit(secties(COMPLEET)), "Hoog")
        self.assertIsNone(prioriteit(secties("### Prioriteit\n\nheel hoog\n")))
        self.assertIsNone(prioriteit(secties("Geen koppen")))


class Triage(unittest.TestCase):
    def test_compleet(self):
        self.assertEqual(triage_compleet(COMPLEET, {"feature"}, [FEATURE]), (True, []))

    def test_standaardwaarde_telt_als_leeg(self):
        body = COMPLEET.replace("- [ ] werkt", "- [ ]")
        self.assertEqual(triage_compleet(body, {"feature"}, [FEATURE]), (False, ["Gewenst gedrag"]))

    def test_no_response_en_geen_prioriteit(self):
        body = COMPLEET.replace("Iets oplossen.", "_No response_").replace("Hoog", "")
        ok, ontbreekt = triage_compleet(body, {"feature"}, [FEATURE])
        self.assertFalse(ok)
        self.assertEqual(sorted(ontbreekt), ["Doel", "Prioriteit"])

    def test_zonder_sjabloon_alleen_prioriteit(self):
        self.assertEqual(triage_compleet("### Prioriteit\n\nLaag", {"onderhoud"}, [FEATURE]), (True, []))


class Status(unittest.TestCase):
    def test_issue(self):
        self.assertEqual(doelstatus_issue(True, None), "Gepland")
        self.assertEqual(doelstatus_issue(False, "Gepland"), "Idee")
        self.assertIsNone(doelstatus_issue(True, "Bezig"))
        self.assertIsNone(doelstatus_issue(True, "Klaar"))

    def test_pr(self):
        self.assertEqual(doelstatus_pr(False, "Gepland"), "Bezig")
        self.assertEqual(doelstatus_pr(True, "Bezig"), "In review")
        self.assertEqual(doelstatus_pr(False, "In review"), "Bezig")
        self.assertIsNone(doelstatus_pr(True, "Klaar"))


class Namen(unittest.TestCase):
    def test_hoofdletters(self):
        self.assertEqual(norm("in  Review "), norm("In review"))
        self.assertEqual(canoniek("in Review"), "In review")
        self.assertEqual(canoniek("Klaar"), "Klaar")
        self.assertIsNone(canoniek(None))


class NepBord:
    """Houdt bij wat het script op het bord zou zetten."""

    def __init__(self, huidig):
        self.huidig, self.gezet = huidig, []

    def toevoegen(self, content_id):
        return "item-" + content_id, self.huidig

    def zet(self, item, veld, waarde):
        self.gezet.append((item, veld, waarde))


PR_EVENT = {
    "repository": {"full_name": "flyingwing1994/test"},
    "pull_request": {"number": 7, "labels": [],  # labels uit het event: nog zonder risico
                     "head": {"repo": {"full_name": "flyingwing1994/test"}}},
}
GESLOTEN = {"repository": {"pullRequest": {"closingIssuesReferences": {"nodes": [
    {"id": "I_1", "number": 3, "repository": {"nameWithOwner": "flyingwing1994/test"}}]}}}}


class PullRequest(unittest.TestCase):
    def draai(self, labels, huidig="Bezig"):
        b = NepBord(huidig)
        with mock.patch.object(bord, "graphql", return_value=GESLOTEN), \
             mock.patch.object(bord, "huidige_labels", return_value=labels), \
             mock.patch.dict(os.environ, {"GH_TOKEN": "x"}):
            bord.pull_request(b, PR_EVENT)
        return b.gezet

    def test_risico_later_gezet_gaat_naar_in_review(self):
        self.assertEqual(self.draai({"risico", "feature"}), [("item-I_1", "Status", "In review")])

    def test_zonder_risico_blijft_bezig(self):
        self.assertEqual(self.draai({"feature"}), [])
        self.assertEqual(self.draai({"feature"}, huidig="Gepland"), [("item-I_1", "Status", "Bezig")])

    def test_fork_wordt_genegeerd(self):
        ev = {**PR_EVENT, "pull_request": {**PR_EVENT["pull_request"],
                                           "head": {"repo": {"full_name": "iemand/fork"}}}}
        b = NepBord("Bezig")
        bord.pull_request(b, ev)
        self.assertEqual(b.gezet, [])


class HuidigeLabels(unittest.TestCase):
    def test_leest_labels_via_api(self):
        uit = subprocess.CompletedProcess([], 0, stdout="feature\nrisico\n\n")
        with mock.patch.object(bord.subprocess, "run", return_value=uit) as run:
            self.assertEqual(bord.huidige_labels("o/r", 7), {"feature", "risico"})
        self.assertIn("repos/o/r/issues/7/labels", run.call_args.args[0])


class GraphQL(unittest.TestCase):
    def uitvoer(self, *antwoorden):
        return [subprocess.CompletedProcess([], code, stdout=tekst, stderr="fout") for code, tekst in antwoorden]

    def test_tijdelijke_fout_wordt_opnieuw_geprobeerd(self):
        antwoorden = self.uitvoer((1, "<html>502</html>"), (0, '{"data": {"ok": 1}}'))
        with mock.patch.object(bord.subprocess, "run", side_effect=antwoorden) as run, \
             mock.patch.object(bord.time, "sleep"):
            self.assertEqual(bord.graphql("t", "q"), {"ok": 1})
        self.assertEqual(run.call_count, 2)

    def test_inhoudelijke_fout_niet_opnieuw(self):
        antwoorden = self.uitvoer((1, '{"errors": [{"message": "niet gevonden"}]}'))
        with mock.patch.object(bord.subprocess, "run", side_effect=antwoorden) as run, \
             self.assertRaises(SystemExit) as fout:
            bord.graphql("t", "q")
        self.assertEqual(run.call_count, 1)
        self.assertIn("niet gevonden", str(fout.exception))

    def test_blijvende_fout_na_drie_pogingen(self):
        antwoorden = self.uitvoer(*[(1, "")] * 3)
        with mock.patch.object(bord.subprocess, "run", side_effect=antwoorden) as run, \
             mock.patch.object(bord.time, "sleep"), self.assertRaises(SystemExit) as fout:
            bord.graphql("t", "q")
        self.assertEqual(run.call_count, 3)
        self.assertIn("3 pogingen", str(fout.exception))


if __name__ == "__main__":
    unittest.main()
