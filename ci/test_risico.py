"""Tests voor ci/risico.py. Draaien met: python -m unittest discover -s ci"""
import json
import unittest

from risico import Wijziging, beoordeel, heeft_issue, is_sprong


def lezer(bestanden: dict[str, str]):
    return lambda pad: bestanden.get(pad, "")


def vlag(wijzigingen, base=None, head=None):
    return beoordeel(wijzigingen, lezer(base or {}), lezer(head or {}))


class IssueKoppeling(unittest.TestCase):
    def test_varianten(self):
        for body in ("Closes #12", "fixes #3", "Resolved: #7", "closes flyingwing1994/.github#4"):
            self.assertTrue(heeft_issue(body), body)

    def test_ontbreekt(self):
        for body in ("", "Closes #", "Zie #12", "Closes\n"):
            self.assertFalse(heeft_issue(body), body)


class Regels(unittest.TestCase):
    def test_geen_vlag(self):
        self.assertEqual(vlag([Wijziging("M", "src/app.js", toegevoegd=10)]), {})

    def test_workflows(self):
        self.assertIn(1, vlag([Wijziging("M", ".github/workflows/pr.yml")]))

    def test_verwijderen(self):
        self.assertIn(2, vlag([Wijziging("D", "docs/oud.md")]))

    def test_geheimen(self):
        for pad in ("src/auth/login.js", ".env.example", "config/secrets.yaml", "certs/server.key"):
            self.assertIn(3, vlag([Wijziging("M", pad)]), pad)
        self.assertNotIn(3, vlag([Wijziging("M", "src/game.js")]))

    def test_database(self):
        for pad in ("db/migrations/001.sql", "prisma/schema.prisma"):
            self.assertIn(4, vlag([Wijziging("M", pad)]), pad)

    def test_infra(self):
        for pad in ("Dockerfile", "docker/ha-mcp/docker-compose.yml", "infra/main.tf", "fly.toml"):
            self.assertIn(5, vlag([Wijziging("M", pad)]), pad)

    def test_ai_instructies_en_scripts(self):
        for pad in ("CLAUDE.md", "web/CLAUDE.md", ".claude/settings.json", "skills/dev-workflow/SKILL.md",
                    "scripts/repo-inrichten.ps1"):
            self.assertIn(8, vlag([Wijziging("M", pad)]), pad)
        for pad in ("docs/scripts.md", "web/src/skills.ts", "README.md"):
            self.assertNotIn(8, vlag([Wijziging("M", pad)]), pad)

    def test_regels(self):
        self.assertIn(7, vlag([Wijziging("M", "a.js", toegevoegd=300, verwijderd=101)]))
        self.assertNotIn(7, vlag([Wijziging("M", "a.js", toegevoegd=300, verwijderd=100)]))
        self.assertNotIn(7, vlag([Wijziging("M", "package-lock.json", toegevoegd=5000)]))


class Packages(unittest.TestCase):
    def test_sprong(self):
        self.assertTrue(is_sprong("^4.2.0", "^5.0.0"))
        self.assertFalse(is_sprong("^4.2.0", "^4.9.1"))
        self.assertTrue(is_sprong("0.3.1", "0.4.0"))
        self.assertFalse(is_sprong("latest", "^5.0.0"))

    def test_npm(self):
        base = {"package.json": json.dumps({"dependencies": {"react": "^18.2.0"}})}
        head = {"package.json": json.dumps({"dependencies": {"react": "^19.0.0", "zod": "^3.0.0"}})}
        uit = vlag([Wijziging("M", "package.json")], base, head)
        self.assertEqual(len(uit[6]), 2)

    def test_npm_kleine_update(self):
        base = {"package.json": json.dumps({"devDependencies": {"vite": "^5.1.0"}})}
        head = {"package.json": json.dumps({"devDependencies": {"vite": "^5.4.2"}})}
        self.assertNotIn(6, vlag([Wijziging("M", "package.json")], base, head))

    def test_requirements(self):
        base = {"requirements.txt": "requests==2.31.0\n"}
        head = {"requirements.txt": "requests==2.32.0\nPyYAML>=6\n"}
        uit = vlag([Wijziging("M", "requirements.txt")], base, head)
        self.assertEqual(uit[6], ["nieuw package `pyyaml` in `requirements.txt`"])

    def test_pyproject(self):
        base = {"pyproject.toml": '[project]\ndependencies = ["httpx>=0.27"]\n'}
        head = {"pyproject.toml": '[project]\ndependencies = ["httpx>=0.28"]\n'}
        self.assertIn(6, vlag([Wijziging("M", "pyproject.toml")], base, head))


if __name__ == "__main__":
    unittest.main()
