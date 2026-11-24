# Centrale checks en auto-merge

Hoe de checks uit [WORKFLOW.md §4 en §5](WORKFLOW.md#4-checks-op-elke-pr) technisch werken, en hoe een repo ze aanroept.

## Aansluiten

1. Kopieer [`templates/pr.yml`](templates/pr.yml) naar `.github/workflows/pr.yml` in de repo.
2. Vul de commando's in (zie hieronder). Leeg laten wat niet van toepassing is.
3. Eigen checks van de repo (zoals de HA-checks van homelab-config) komen als extra job in hetzelfde bestand, en in de `needs` van `automerge`.
4. Zet de repo-instellingen (zie [Instellingen per repo](#instellingen-per-repo)).

De repo verwijst naar `@main`. Een wijziging aan de centrale checks geldt dus meteen overal; zo'n PR krijgt altijd het label `risico` en wordt eerst op een testbranch van yaniv-scorekeeper geprobeerd.

## Invoervelden

| Veld | Betekenis | Voorbeeld |
| --- | --- | --- |
| `node-version` | Node installeren | `"22"` |
| `python-version` | Python installeren | `"3.12"` |
| `install` | Afhankelijkheden installeren (vóór lint/build/test) | `npm ci` |
| `lint` | Lint/format-check | `npm run lint` |
| `build` | Build | `npm run build` |
| `test` | Tests | `npm test` |
| `tests-verplicht` | `true` zodra het testbasis-issue klaar is | `false` |

## Checks

Elke repo krijgt dezelfde check-namen, zodat de lijst verplichte checks overal gelijk is.

| Check | Wat | Blokkeert |
| --- | --- | --- |
| `checks / geheimen` | Gitleaks over **alle commits** van de PR; gevonden waarden worden in de log gemaskeerd | Ja |
| `checks / semgrep` | Semgrep CE, regelset `p/default`, telemetrie uit, alleen **nieuwe** bevindingen | Alleen bij ERROR |
| `checks / dependencies` | `dependency-review-action` (ernst *moderate* en hoger). Alleen openbare repo's; op privé-repo's overgeslagen | Ja |
| `checks / lint` | Altijd YAML-lint (eigen `.yamllint` van de repo, anders de ruime standaard) + het `lint`-commando | Ja |
| `checks / build` | Het `build`-commando | Ja |
| `checks / test` | Het `test`-commando. Leeg = waarschuwing, tot `tests-verplicht: true` | Ja |
| `checks / docs` | Interne links in Markdown (bestanden en ankers, geen externe sites) | Ja |
| `checks / proces` | Issue-koppeling (`Closes #nr`) en de vaste risicoregels | Alleen ontbrekende issue-koppeling |
| `review / claude` | Claude-review op vaste criteria (zie [Claude-review](#claude-review)); pas na groene checks | Bij BLOKKEREND of geen oordeel |
| `review / second-opinion` | Tweede Claude-ronde op beveiliging; alleen bij een vlag of security-gevoelige wijziging, anders overgeslagen | Bij BLOKKEREND |
| `automerge / automerge` | Merget als alles groen is en er geen `risico`-label is | — |

Dependabot-PR's hoeven geen issue te koppelen.

## Vaste risicoregels

`ci/risico.py` zet het label `risico` als de PR:

1. `.github/workflows/` raakt;
2. bestanden of mappen verwijdert;
3. geheimen, auth of login raakt (op bestandsnaam, bijv. `auth/`, `.env*`, `*secret*`, `*.key`);
4. database-schema's of migraties raakt (`migrations/`, `*.sql`, `schema.prisma`, …);
5. deploy- of infraconfig raakt (`Dockerfile`, `compose*.yml`, `*.tf`, tunnel/nginx/netwerk, …);
6. een nieuw package toevoegt of een grote versiesprong maakt (`package.json`, `requirements*.txt`, `pyproject.toml`; bij 0.x telt een minor-sprong als groot);
7. meer dan 400 regels wijzigt (lockfiles niet meegeteld).

De regels kijken naar bestandsnamen en packagelijsten. De inhoud (bijv. login-code in een gewoon bestand) beoordeelt de Claude-review. Het script zet het label alleen; weghalen doet Michiel.

## Claude-review

`review.yml` draait via het Pro-account van Michiel (secret `CLAUDE_CODE_OAUTH_TOKEN`, per repo geplaatst). Claude draait in een job met **alleen leesrechten** (`review / analyse`, `review / analyse-second`): PR, diff, gekoppeld issue, bestanden. Commentaar, label en PR-tekst zet `ci/review.py` in een aparte job zonder Claude (`review / claude`, `review / second-opinion`); alleen die twee zijn verplichte checks. Bevat Claude's uitvoer het token of iets wat op een token lijkt, dan wordt niets geplaatst en is de check rood.

Vaste criteria: correctheid (doet het wat het issue vraagt), beveiliging, tests, documentatie, scope ten opzichte van het issue, en inhoudelijk risico. Daarnaast leest Claude de `CLAUDE.md` van de repo en, als die bestaat, `.github/review.md` met extra criteria van die repo.

| Oordeel | Check | Gevolg |
| --- | --- | --- |
| OK | Groen | Auto-merge mag door |
| RISICO | Groen | Label `risico`; bovenaan de PR in gewoon Nederlands wat er verandert, het risico en het advies; second opinion; Michiel merget zelf |
| BLOKKEREND | Rood | Commentaar met wat er eerst moet gebeuren |
| Geen oordeel | Rood | Fail-closed (bijv. token ontbreekt of verlopen) |

- **Second opinion** draait bij RISICO, bij een security-gevoelige wijziging of als `proces` al `risico` zette. Hij kijkt als aanvaller en blokkeert alleen bij een concreet beveiligingsprobleem.
- **Zelfde commit** wordt niet opnieuw gereviewd (bijv. na het aanpassen van de PR-tekst): het oordeel uit het eerdere commentaar wordt hergebruikt. Opnieuw laten reviewen: verwijder het review-commentaar en draai de job opnieuw.
- **Dependabot-PR's** worden overgeslagen (Dependabot kan niet bij het token). Grote sprongen krijgen via de vaste regels toch `risico`.
- **Tegoed:** elke review gebruikt het Pro-tegoed van Michiel, gedeeld met zijn eigen gebruik van Claude. De review draait daarom pas als de checks groen zijn.

## Auto-merge

`automerge.yml` draait als laatste job, pas als alle jobs in `needs` geslaagd zijn. Hij merget **niet** bij:
het label `risico`, een draft-PR, een PR vanaf een fork, of een auteur die niet de eigenaar of Dependabot is.

| Repo | Hoe |
| --- | --- |
| Openbaar | Ingebouwde auto-merge van GitHub (`--auto`), afgedwongen door een ruleset met verplichte checks. Kan dat niet, dan direct squash. |
| Privé (geen Pro) | Direct squash-merge door de workflow. Er is geen technische blokkade op `main`; "nooit rechtstreeks naar main" is daar een afspraak. |

De merge gebeurt met het workflow-token. Let op: zo'n merge start **geen** nieuwe workflows op `main` (bijv. een deploy bij een push naar `main`). Een repo die dat nodig heeft, meldt dit in een issue.

## Instellingen per repo

**Snelst: [`scripts/repo-inrichten.ps1`](scripts/repo-inrichten.ps1)**, lokaal door Michiel gedraaid (Claude kan repo-instellingen en secrets niet wijzigen, en ziet secrets nooit). Het script zet alles hieronder in één keer, voor een of meer repo's, en vraagt de twee tokens verborgen:

```powershell
# eenmalig: winget install GitHub.cli ; gh auth login
.\scripts\repo-inrichten.ps1 -Repos yaniv-scorekeeper
.\scripts\repo-inrichten.ps1 -Repos fotospel,feest -GeenSecrets   # secrets niet opnieuw zetten
.\scripts\repo-inrichten.ps1 -Repos feest -Onthoud            # tokens versleuteld onthouden (DPAPI, buiten elke repo)
.\scripts\repo-inrichten.ps1 -Repos .github,feest -NieuweTokens   # na een nieuw token: opnieuw vragen en bewaren
```

Opnieuw draaien is veilig. Met `-Onthoud` staan de tokens versleuteld met het Windows-account van Michiel in `$HOME\.repo-inrichten\tokens.xml` (nooit in een repo, nooit als platte tekst); volgende runs vragen dan niets meer. Wat het script zet, staat hieronder (ook om met de hand te doen of na te kijken). Settings → General → Pull Requests:

- Allow merge commits: **uit**
- Allow squash merging: **aan**, standaardbericht *Pull request title and description*
- Allow rebase merging: **uit**
- Always suggest updating pull request branches: **aan**
- Allow auto-merge: **aan**
- Automatically delete head branches: **aan**

Alle repo's, Settings → Secrets and variables → Actions → New repository secret:

- `CLAUDE_CODE_OAUTH_TOKEN`: het token uit `claude setup-token` (Michiel plaatst het zelf; Claude ziet de waarde nooit)

Alle repo's, Settings → Advanced Security:

- *Dependency graph*: **aan** (nodig voor `checks / dependencies` op openbare repo's)
- *Dependabot alerts* en *Dependabot security updates*: **aan** (WORKFLOW.md §6: beveiligingsupdates direct)

Alleen openbare repo's, extra:

- Settings → Rules → Rulesets: ruleset op `main` met *Restrict deletions*, *Block force pushes*, *Require a pull request before merging* (0 goedkeuringen) en *Require status checks to pass* met de checks hierboven (zonder `automerge`).
- Settings → Advanced Security: *Secret Protection* en *Push protection* aan.

Labels: die uit [`labels.yml`](labels.yml); ongebruikte standaardlabels van GitHub worden verwijderd.

## Versies

- Externe actions zijn gepind op een commit-SHA; Dependabot houdt ze bij (`.github/dependabot.yml`).
- Semgrep en yamllint staan in `ci/requirements-*.txt`; Dependabot houdt ze bij.
- Gitleaks staat met versie en checksum in `checks.yml` en wordt **handmatig** bijgewerkt.
- Krijgt een privé-repo echte packagebestanden (lockfiles), dan voegen we daar OSV-Scanner toe, omdat `dependency-review-action` op privé-repo's niet werkt.

## Bord

Eén GitHub Project op het account van Michiel, met alle issues uit alle repo's (WORKFLOW.md §2). Elke repo roept `bord.yml` aan via [`templates/bord.yml`](templates/bord.yml); het script is `ci/bord.py`.

| Gebeurtenis | Wat het bord doet |
| --- | --- |
| Issue geopend, bewerkt of heropend | Op het bord; veld *Prioriteit* uit `### Prioriteit`. Verplichte sjabloonvelden en prioriteit ingevuld → **Gepland**, anders **Idee** + label `wacht-op-info`. Alleen zolang het kaartje in Idee of Gepland staat. |
| PR met `Closes #nr` (geopend, bewerkt, label) | Dat issue → **Bezig**; met label `risico` → **In review**. Nooit terug uit Klaar. |
| Issue gesloten of PR gemerged | → **Klaar**, via de ingebouwde workflows van het Project (geen eigen code). |

- Welke velden verplicht zijn, leest het script uit de centrale issue-sjablonen (`.github/ISSUE_TEMPLATE/`).
- PR's van Dependabot en vanaf forks worden overgeslagen (Dependabot krijgt geen secrets en sluit geen issues).
- Labels die een workflow zet (zoals `risico` door de checks of de review), starten geen nieuwe workflows. Daarom werkt de PR-workflow het bord na de review nog eens bij.
- Tokens: het bord wordt bijgewerkt met `PROJECT_TOKEN` (classic, alleen `project`-scope, door Michiel per repo als secret geplaatst). De repo zelf lezen en het label `wacht-op-info` zetten gebeurt met het gewone workflow-token.

### Bord inrichten (eenmalig, Michiel)

1. github.com → je profiel → **Projects → New project → Board**, naam bijv. `Werk`.
2. Veld **Status** (bestaat al): opties exact `Idee`, `Gepland`, `Bezig`, `In review`, `Klaar`.
3. Nieuw veld **Prioriteit**, type *Single select*: opties exact `Urgent`, `Hoog`, `Middel`, `Laag`.
4. Project → **Workflows**: *Item closed* → Status `Klaar` en *Pull request merged* → Status `Klaar` aan; *Auto-add* uit (dat doet de Action).
5. Token: Settings → Developer settings → **Tokens (classic)** → alleen scope `project`, met een vervaldatum; als secret `PROJECT_TOKEN` in elke repo.
