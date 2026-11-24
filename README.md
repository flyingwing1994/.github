# .github

Standaard sjablonen, labels en checks voor alle repo's van flyingwing1994.

- [`WORKFLOW.md`](WORKFLOW.md) — de afspraken: issues, branches, PR's, checks en mergen.
- [`.github/ISSUE_TEMPLATE/`](.github/ISSUE_TEMPLATE) — issue-sjablonen (klein, bug, feature). GitHub gebruikt ze automatisch in elke repo zonder eigen sjablonen.
- [`.github/pull_request_template.md`](.github/pull_request_template.md) — PR-sjabloon.
- [`labels.yml`](labels.yml) — standaardlabels.
- [`CHECKS.md`](CHECKS.md) — centrale checks en auto-merge: hoe een repo ze aanroept.
- [`templates/pr.yml`](templates/pr.yml) — sjabloon voor de PR-workflow in een repo.
- [`skills/dev-workflow/SKILL.md`](skills/dev-workflow/SKILL.md) — de werkwijze als Claude-skill.

## Skill installeren of bijwerken (Windows, PowerShell)

```powershell
$d = "$HOME\.claude\skills\dev-workflow"; New-Item -ItemType Directory -Force $d | Out-Null
Invoke-WebRequest https://raw.githubusercontent.com/flyingwing1994/.github/main/skills/dev-workflow/SKILL.md -OutFile "$d\SKILL.md"
```

En eenmalig in de globale `CLAUDE.md` (`$HOME\.claude\CLAUDE.md`):

```text
Voor al het git- en GitHub-werk in mijn repo's: volg altijd de skill `dev-workflow`.
```
