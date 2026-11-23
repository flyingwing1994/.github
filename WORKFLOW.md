# Dev-workflow

Bron van waarheid voor hoe alle projecten van flyingwing1994 via git en GitHub werken.
Geldt voor mensen én Claude. Laatst bijgewerkt: 23-11-2026.

## 1. Basis

- Geldt voor alles wat in git kan, ook nieuwe projecten. Claude stelt bij een nieuw project altijd een repo voor en adviseert privé of openbaar, met reden. Michiel beslist.
- **Nooit rechtstreeks naar `main`.** Elke wijziging gaat via een pull request. Op privé-repo's is dat een harde afspraak (geen GitHub Pro); op openbare repo's ook technisch afgeschermd.
- Claude doet al het git- en GitHub-werk: issue, branch, commits, push, PR.
- Commando's op machines (ssh, `pct`, `qm`, Home Assistant) vallen buiten deze workflow en blijven bij Michiel.

## 2. Issues = de todo-lijst

Elke wijziging begint met een issue, ook kleine.

1. Michiel meldt een idee of bug.
2. Claude vraagt door tot het sjabloon gevuld kan worden (triage):
   - Wanneer moet het idealiter klaar zijn? Vaste datum?
   - Wat gebeurt er als het niet gebeurt?
   - Voor wie: Michiel, Shirley, vrienden, gasten?
   - Is er een workaround?
3. Claude stelt een prioriteit voor met onderbouwing. Michiel bevestigt of past aan.
4. Claude maakt het issue aan. Het komt automatisch op het bord.

**Sjablonen:** `klein` (wat, waarom), `bug` en `feature` (uitgebreid, met triage). Maakt Claude een issue via de API, dan volgt de tekst dezelfde kopjes als het sjabloon, met `### Prioriteit` gevolgd door precies `Urgent`, `Hoog`, `Middel` of `Laag`. De bord-Action leest dat veld.

**Prioriteit:** Urgent (iets is stuk of er is een harde datum) · Hoog · Middel · Laag.

**Bord:** één GitHub Project over alle repo's.

| Kolom | Betekenis |
| --- | --- |
| Idee | Nog niet compleet, triage-info ontbreekt |
| Gepland | Triage klaar, prioriteit bevestigd |
| Bezig | Er is een branch/PR |
| In review | PR wacht op Michiel (risicovlag) |
| Klaar | Gemerged, issue gesloten |

Het overzicht (in review, urgent, top van Gepland) geeft Claude alleen op verzoek.

**Labels:** zie `labels.yml`.

## 3. Branches, commits en PR's

- **Branch:** `type/issuenummer-omschrijving`, bijv. `feat/12-team-codes`, `fix/15-login-crash`, `docs/18-readme-ip-plan`.
- **Taal:** Nederlands, met Engelse Conventional-Commits-voorvoegsels: `feat:`, `fix:`, `docs:`, `chore:`, `test:`, `refactor:`.
  Voorbeeld: `feat: team-codes opnieuw genereren bij laden (#12)`.
- **Merge:** altijd squash. Eén commit per PR op `main`, met het PR-nummer. Branch wordt daarna verwijderd.
- **PR-beschrijving:** volgens `pull_request_template.md`: issue-koppeling, samenvatting in gewoon Nederlands, technische wijzigingen, zo getest, docs, risico.

## 4. Checks op elke PR

| Groep | Checks |
| --- | --- |
| Veiligheid | Geheimen-scan, Semgrep, dependency-check, security-onderdeel in Claude-review |
| Kwaliteit | Lint/format, build, Claude-review |
| Documentatie | README of juiste doc bijgewerkt; inhoud gecontroleerd door Claude |
| Testen | Tests draaien; nieuwe features en bugfixes hebben tests |
| Proces | Issue-koppeling, vaste risicoregels |

- **Tests:** verplicht in code-repo's, na eenmalig een testbasis-issue per repo (tot dan alleen waarschuwing). Config/docs-repo's: automatische checks (YAML, HA-config, links) plus een verplicht "zo getest"-blok.
- Repo's roepen de centrale checks aan en kunnen eigen checks toevoegen. Technische uitwerking: [`CHECKS.md`](CHECKS.md).

## 5. Risico en mergen

Een PR krijgt het label `risico` als **een** van deze twee iets vindt:

**Vaste regels** — de PR raakt:
1. `.github/workflows/`
2. het verwijderen van bestanden of mappen
3. geheimen, auth of login
4. database-schema's of migraties
5. deploy- of infraconfig (Dockerfile, compose, tunnel, netwerk)
6. nieuwe packages of grote versiesprongen
7. meer dan 400 gewijzigde regels

**Claude-review** — inhoudelijk oordeel op vaste criteria.

| Situatie | Wat gebeurt er |
| --- | --- |
| Geen vlag, alles groen | Automatisch gemerged |
| Wel een vlag | Michiel merget zelf. Claude zet bovenaan de PR in gewoon Nederlands wat er verandert, wat het risico is en wat Claude adviseert. Code lezen is niet nodig. |

**Second opinion:** een tweede Claude-ronde gericht op beveiliging, alleen bij een vlag of een security-gevoelige wijziging. (GitHub Models, het eerdere plan, is op 30-07-2026 door GitHub gestopt.)

## 6. Dependencies

| Soort | Aanpak |
| --- | --- |
| Gewone updates | Wekelijks gebundeld, 7 dagen wachttijd, automatisch mergen bij groen |
| Beveiligingsupdates | Direct, prioriteit Urgent, automatisch mergen bij groen |
| Grote versiesprong | Vlag |

## 7. Geheimen

Tokens en wachtwoorden komen nooit in git of in een chat. Michiel plaatst ze zelf als GitHub-secret. Claude ziet de waarde nooit.
