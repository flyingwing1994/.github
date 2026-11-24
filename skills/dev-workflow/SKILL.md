---
name: dev-workflow
description: Werkwijze voor alle git- en GitHub-werk in de repo's van flyingwing1994 (Michiel). Gebruik bij elke wijziging in een repo, een nieuw project, een idee of bug van Michiel, het aanmaken van issues, branches, commits of PR's, het inrichten van een repo, en bij vragen naar het overzicht (in review, urgent, top van Gepland).
---

# dev-workflow

Bron van waarheid: [`WORKFLOW.md`](https://github.com/flyingwing1994/.github/blob/main/WORKFLOW.md) en
[`CHECKS.md`](https://github.com/flyingwing1994/.github/blob/main/CHECKS.md) in `flyingwing1994/.github`.
Lees die bij twijfel; deze skill is de samenvatting om te handelen.

Taal: Nederlands. Conventional-Commits-voorvoegsels in het Engels.

## Altijd

- **Nooit rechtstreeks naar `main`.** Elke wijziging: issue → branch → PR.
- Claude doet al het git- en GitHub-werk (issue, branch, commits, push, PR). Commando's op machines (ssh, `pct`, `qm`, Home Assistant) niet: geef die als blok aan Michiel.
- Geheimen nooit in git of chat. Michiel plaatst ze als GitHub-secret; Claude ziet de waarde nooit.
- Vragen één voor één, gesloten, met advies. Stappen voor Michiel als blok, met per stap het verwachte resultaat.
- Repo-instellingen en secrets kan Claude niet wijzigen: laat Michiel `scripts/repo-inrichten.ps1 -Repos <naam>` uit `flyingwing1994/.github` draaien (zie CHECKS.md, Instellingen per repo).
- De `CLAUDE.md` van een repo kan aanvullende afspraken hebben (bijv. homelab-config: harde kaders, schrijfroute). Volg die ook; bij tegenspraak: eerst Michiel vragen.

## 1. Idee of bug → issue

1. Triage: vraag door tot het sjabloon gevuld is: wanneer klaar (vaste datum?), gevolg als het niet gebeurt, voor wie (Michiel, Shirley, vrienden, gasten), workaround?
2. Stel een prioriteit voor met onderbouwing: Urgent (stuk of harde datum) · Hoog · Middel · Laag. Michiel bevestigt.
3. Maak het issue met de kopjes van het sjabloon (`klein`, `bug` of `feature`) en het passende label. Exact:
   `### Prioriteit` gevolgd door `Urgent`, `Hoog`, `Middel` of `Laag` (de bord-Action leest dit).
   Titel: `[Feature] …`, `[Bug] …` of `[Klein] …`.

## 2. Branch, commits, PR

- Branch: `type/issuenr-omschrijving`, bijv. `feat/12-team-codes`, `fix/15-login-crash`, `docs/18-readme-ip-plan`.
- Commits: `feat: … (#12)` — voorvoegsels `feat`, `fix`, `docs`, `chore`, `test`, `refactor`.
- PR-titel: `feat: …` **zonder** issuenummer (GitHub zet het PR-nummer erachter bij de squash).
- PR-beschrijving volgens `.github/pull_request_template.md`: `Closes #nr`, Samenvatting (gewoon Nederlands), Technische wijzigingen, Zo getest, Docs, Risico.
- Docs bijwerken in dezelfde PR (README of het juiste doc).
- Nieuwe features en bugfixes krijgen tests (verplicht zodra het testbasis-issue van de repo klaar is).
- Na het openen: vraag Michiel of Claude de PR moet volgen.

## 3. Checks, risico, mergen

- Elke PR draait de centrale checks, daarna de Claude-review. Zie CHECKS.md.
- Label `risico` (vaste regels of Claude-review) → Michiel merget zelf. Claude zet nooit zelf een uitlegblok in de PR; dat doet de review.
- Geen vlag en alles groen → automatisch gemerged (squash). **Claude merget nooit zelf.**
- Faalt een check: oorzaak zoeken en oplossen in dezelfde branch. Nooit een test overslaan of uitzetten om groen te krijgen.

## 4. Overzicht (alleen op verzoek)

Op de vraag "overzicht": in review (PR's met `risico`), Urgent, en de top van Gepland op het bord.

## 5. Nieuwe repo of project (ook bij de uitrol naar bestaande repo's)

1. Stel bij een nieuw project altijd een repo voor, met advies privé of openbaar en de reden. Michiel beslist.
2. Eerst kijken: taal, packagebestanden, tests, Dockerfile/compose, deploy, en of er al workflows of een `CLAUDE.md` zijn. Iets dat rechtstreeks naar `main` pusht (bijv. Klipper-Backup) eerst met Michiel bespreken.
3. Michiel draait het inrichtscript (merge-instellingen, beveiliging, ruleset bij openbaar, labels, secrets). Ophalen via de API, niet via raw.githubusercontent.com (cache):
   `Invoke-WebRequest -Headers @{Accept='application/vnd.github.raw'} https://api.github.com/repos/flyingwing1994/.github/contents/scripts/repo-inrichten.ps1 -OutFile "$HOME\repo-inrichten.ps1"`
   en dan `powershell -ExecutionPolicy Bypass -File "$HOME\repo-inrichten.ps1" -Repos <naam>` (tokens zijn onthouden met `-Onthoud`).
4. Eén PR "centrale workflow aansluiten" (issue → PR in die repo):
   - `.github/workflows/pr.yml` uit `templates/pr.yml`: commando's invullen; `node-version`/`python-version` **gelijk aan de Dockerfile**; job `automerge` met `issues: write`.
   - `.github/workflows/bord.yml` uit `templates/bord.yml`.
   - `.github/dependabot.yml`: wekelijks, `cooldown: default-days: 7`, gebundeld; ecosystemen van de repo + `github-actions` (+ `docker` waar van toepassing).
   - `CLAUDE.md` met de werkwijze-regel (zie WORKFLOW.md §8) en een korte beschrijving van de repo.
   - README: alinea over de werkwijze.
5. Daarna: testbasis-issue als er nog geen tests zijn; issue voor lint/format als dat ontbreekt. Pas na de testbasis `tests-verplicht: true` (aparte PR, want `pr.yml` = risico).
6. Valkuilen uit de proef:
   - Nep-sleutels en -tokens in tests **per run willekeurig** maken (bijv. `randomUUID()`); vaste waarden geven vals alarm in de geheimen-scan, en geschiedenis herschrijven kan niet.
   - Wijzigingen aan `pr.yml` krijgen altijd `risico`; houd ze apart van inhoudelijk werk, zodat dat werk automatisch kan mergen.
   - PR's die een andere PR nodig hebben: als concept openen en pas klaarzetten als de eerste gemerged is.
   - Openbare repo's: de ruleset noemt de verplichte checks; nieuwe check-namen moeten daar ook in (via het inrichtscript).
7. Privé-repo met echte packagebestanden: OSV-Scanner toevoegen (dependency-review werkt daar niet).
