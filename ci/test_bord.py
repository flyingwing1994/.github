"""Tests voor ci/bord.py. Draaien met: python -m unittest discover -s ci"""
import unittest

from bord import doelstatus_issue, doelstatus_pr, prioriteit, secties, triage_compleet

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


if __name__ == "__main__":
    unittest.main()
