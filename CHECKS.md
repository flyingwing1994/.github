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

## Auto-merge

`automerge.yml` draait als laatste job, pas als alle jobs in `needs` geslaagd zijn. Hij merget **niet** bij:
het label `risico`, een draft-PR, een PR vanaf een fork, of een auteur die niet de eigenaar of Dependabot is.

| Repo | Hoe |
| --- | --- |
| Openbaar | Ingebouwde auto-merge van GitHub (`--auto`), afgedwongen door een ruleset met verplichte checks. Kan dat niet, dan direct squash. |
| Privé (geen Pro) | Direct squash-merge door de workflow. Er is geen technische blokkade op `main`; "nooit rechtstreeks naar main" is daar een afspraak. |

De merge gebeurt met het workflow-token. Let op: zo'n merge start **geen** nieuwe workflows op `main` (bijv. een deploy bij een push naar `main`). Een repo die dat nodig heeft, meldt dit in een issue.

## Instellingen per repo

Handmatig, want Claude kan repo-instellingen niet wijzigen. Settings → General → Pull Requests:

- Allow merge commits: **uit**
- Allow squash merging: **aan**, standaardbericht *Pull request title and description*
- Allow rebase merging: **uit**
- Always suggest updating pull request branches: **aan**
- Allow auto-merge: **aan**
- Automatically delete head branches: **aan**

Alle repo's, Settings → Advanced Security:

- *Dependency graph*: **aan** (nodig voor `checks / dependencies` op openbare repo's)
- *Dependabot alerts* en *Dependabot security updates*: **aan** (WORKFLOW.md §6: beveiligingsupdates direct)

Alleen openbare repo's, extra:

- Settings → Rules → Rulesets: ruleset op `main` met *Restrict deletions*, *Block force pushes*, *Require a pull request before merging* (0 goedkeuringen) en *Require status checks to pass* met de checks hierboven (zonder `automerge`).
- Settings → Advanced Security: *Secret Protection* en *Push protection* aan.

## Versies

- Externe actions zijn gepind op een commit-SHA; Dependabot houdt ze bij (`.github/dependabot.yml`).
- Semgrep en yamllint staan in `ci/requirements-*.txt`; Dependabot houdt ze bij.
- Gitleaks staat met versie en checksum in `checks.yml` en wordt **handmatig** bijgewerkt.
- Krijgt een privé-repo echte packagebestanden (lockfiles), dan voegen we daar OSV-Scanner toe, omdat `dependency-review-action` op privé-repo's niet werkt.
