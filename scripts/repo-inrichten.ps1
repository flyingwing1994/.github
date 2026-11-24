<#
.SYNOPSIS
  Richt een of meer repo's van flyingwing1994 in volgens CHECKS.md: merge-instellingen,
  beveiliging, ruleset (openbare repo's), labels en secrets.

.DESCRIPTION
  Draai dit lokaal met de GitHub CLI (gh), ingelogd als de eigenaar van de repo's.
  Opnieuw draaien is veilig: alles wordt (opnieuw) op de juiste waarde gezet.
  De secrets worden een keer verborgen gevraagd en nergens opgeslagen of getoond.

.EXAMPLE
  .\repo-inrichten.ps1 -Repos yaniv-scorekeeper

.EXAMPLE
  .\repo-inrichten.ps1 -Repos fotospel,feest,gopro-pipeline,homelab-config,klipper-config

.EXAMPLE
  .\repo-inrichten.ps1 -Repos fotospel -GeenSecrets
#>
[CmdletBinding()]
param(
  [Parameter(Mandatory = $true)] [string[]] $Repos,
  [string] $Eigenaar = 'flyingwing1994',
  [switch] $GeenSecrets,
  [switch] $GeenRuleset
)

# Fouten van gh worden via de exitcode afgevangen (PowerShell 5 ziet uitvoer op stderr anders als fout).
$ErrorActionPreference = 'Continue'
# Tekst naar gh altijd als UTF-8 (Windows PowerShell 5 gebruikt anders ASCII).
$OutputEncoding = [System.Text.UTF8Encoding]::new($false)
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)

# Verplichte checks in de ruleset (gelijk aan CHECKS.md).
$VerplichteChecks = @(
  'checks / geheimen', 'checks / semgrep', 'checks / dependencies', 'checks / lint',
  'checks / build', 'checks / test', 'checks / docs', 'checks / proces',
  'review / claude', 'review / second-opinion'
)
$StandaardLabels = @('documentation', 'duplicate', 'enhancement', 'good first issue', 'help wanted',
  'invalid', 'question', 'wontfix', 'accessibility')

# ------------------------------------------------------------------ hulpjes
function GhRun {
  # Let op: geen functie 'gh' noemen. PowerShell is hoofdletterongevoelig en functies gaan voor
  # programma's, dan roept '& gh' zichzelf aan in plaats van gh.exe.
  # Roept gh aan met alle meegegeven argumenten. Uitvoer en foutmeldingen blijven gescheiden,
  # zodat een waarschuwing nooit in een waarde terechtkomt; bij een fout volgt een duidelijke melding.
  $fout = [System.IO.Path]::GetTempFileName()
  try {
    $uit = & gh @args 2>$fout
    if ($LASTEXITCODE -ne 0) { throw "gh $($args -join ' ') mislukte: $(Get-Content $fout -Raw)" }
    return $uit
  } finally { Remove-Item $fout -ErrorAction SilentlyContinue }
}

function GhJson {
  # Stuurt JSON naar gh api (via stdin).
  param([string] $Methode, [string] $Pad, [object] $Data)
  $json = $Data | ConvertTo-Json -Depth 10 -Compress
  $fout = [System.IO.Path]::GetTempFileName()
  try {
    $uit = $json | & gh api -X $Methode $Pad --input - 2>$fout
    if ($LASTEXITCODE -ne 0) { throw "gh api -X $Methode $Pad mislukte: $(Get-Content $fout -Raw)" }
    return $uit
  } finally { Remove-Item $fout -ErrorAction SilentlyContinue }
}

function Stap([string] $Tekst) { Write-Host "    OK  $Tekst" -ForegroundColor Green }
function Bezig([string] $Tekst) { Write-Host "  ... $Tekst" -ForegroundColor DarkGray }

function LeesSecret([string] $Naam) {
  $veilig = Read-Host "Plak $Naam (Enter = overslaan)" -AsSecureString
  $ptr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($veilig)
  try { return [Runtime.InteropServices.Marshal]::PtrToStringBSTR($ptr) }
  finally { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($ptr) }
}

function LeesLabels {
  # labels.yml uit de .github-repo; eenvoudig formaat: - name / color / description.
  $tekst = GhRun api "repos/$Eigenaar/.github/contents/labels.yml" -H 'Accept: application/vnd.github.raw'
  $labels = @(); $huidig = $null
  foreach ($regel in ($tekst -split "`n")) {
    if ($regel -match '^\s*-\s*name:\s*(.+?)\s*$') {
      if ($huidig) { $labels += $huidig }
      $huidig = @{ name = $Matches[1].Trim('"'); color = ''; description = '' }
    } elseif ($huidig -and $regel -match '^\s*color:\s*"?([0-9a-fA-F]{6})"?\s*$') {
      $huidig.color = $Matches[1]
    } elseif ($huidig -and $regel -match '^\s*description:\s*(.+?)\s*$') {
      $huidig.description = $Matches[1].Trim('"')
    }
  }
  if ($huidig) { $labels += $huidig }
  if ($labels.Count -eq 0) { throw 'Geen labels gevonden in labels.yml.' }
  return $labels
}

# ------------------------------------------------------------------ onderdelen
function ZetMergeInstellingen([string] $R) {
  GhRun api -X PATCH "repos/$R" `
    -F allow_squash_merge=true -F allow_merge_commit=false -F allow_rebase_merge=false `
    -F delete_branch_on_merge=true -F allow_auto_merge=true -F allow_update_branch=true `
    -f squash_merge_commit_title=PR_TITLE -f squash_merge_commit_message=PR_BODY --silent | Out-Null
  Stap 'merge: alleen squash (titel + beschrijving), auto-merge, branch bijwerken, branches verwijderen'
}

function ZetBeveiliging([string] $R, [bool] $Openbaar) {
  # Dependabot alerts zet ook de dependency graph aan.
  GhRun api -X PUT "repos/$R/vulnerability-alerts" --silent | Out-Null
  GhRun api -X PUT "repos/$R/automated-security-fixes" --silent | Out-Null
  Stap 'beveiliging: dependency graph, Dependabot alerts en security updates'
  if ($Openbaar) {
    GhJson PATCH "repos/$R" @{ security_and_analysis = @{
        secret_scanning                 = @{ status = 'enabled' }
        secret_scanning_push_protection = @{ status = 'enabled' }
      } } | Out-Null
    Stap 'beveiliging: secret scanning en push protection'
  }
}

function ZetRuleset([string] $R) {
  $ruleset = @{
    name          = 'main'
    target        = 'branch'
    enforcement   = 'active'
    conditions    = @{ ref_name = @{ include = @('~DEFAULT_BRANCH'); exclude = @() } }
    # 5 = rol Repository admin; alleen via een PR (nood-merge als een check kapot is).
    bypass_actors = @(@{ actor_id = 5; actor_type = 'RepositoryRole'; bypass_mode = 'pull_request' })
    rules         = @(
      @{ type = 'deletion' },
      @{ type = 'non_fast_forward' },
      @{ type = 'pull_request'; parameters = @{
          required_approving_review_count   = 0
          dismiss_stale_reviews_on_push     = $false
          require_code_owner_review         = $false
          require_last_push_approval        = $false
          required_review_thread_resolution = $false
          allowed_merge_methods             = @('squash')
        } },
      @{ type = 'required_status_checks'; parameters = @{
          strict_required_status_checks_policy = $false
          required_status_checks               = @($VerplichteChecks | ForEach-Object { @{ context = $_ } })
        } }
    )
  }
  $bestaand = (GhRun api "repos/$R/rulesets" | ConvertFrom-Json) | Where-Object { $_.name -eq 'main' } | Select-Object -First 1
  if ($bestaand) {
    GhJson PUT "repos/$R/rulesets/$($bestaand.id)" $ruleset | Out-Null
    Stap "ruleset 'main' bijgewerkt ($($VerplichteChecks.Count) verplichte checks)"
  } else {
    GhJson POST "repos/$R/rulesets" $ruleset | Out-Null
    Stap "ruleset 'main' aangemaakt ($($VerplichteChecks.Count) verplichte checks)"
  }
}

function ZetLabels([string] $R, [array] $Labels) {
  foreach ($l in $Labels) {
    GhRun label create $l.name --repo $R --color $l.color --description $l.description --force | Out-Null
  }
  $weg = @()
  foreach ($naam in $StandaardLabels) {
    & gh api "repos/$R/labels/$([uri]::EscapeDataString($naam))" --silent 2>$null | Out-Null
    if ($LASTEXITCODE -ne 0) { continue }
    $gebruik = GhRun api "repos/$R/issues?state=all&per_page=1&labels=$([uri]::EscapeDataString($naam))" --jq 'length'
    if ([int]$gebruik -eq 0) {
      GhRun api -X DELETE "repos/$R/labels/$([uri]::EscapeDataString($naam))" --silent | Out-Null
      $weg += $naam
    }
  }
  Stap "labels: $($Labels.Count) uit labels.yml gezet; $($weg.Count) ongebruikte standaardlabels verwijderd"
}

function ZetSecrets([string] $R, [hashtable] $Secrets) {
  foreach ($naam in $Secrets.Keys) {
    if ([string]::IsNullOrEmpty($Secrets[$naam])) { continue }
    # Via stdin, zodat het token niet in de proceslijst staat (gh haalt de regelovergang eraf).
    $Secrets[$naam] | & gh secret set $naam --repo $R 2>&1 | Out-Null
    if ($LASTEXITCODE -ne 0) { throw "Secret $naam zetten in $R mislukte." }
    Stap "secret $naam gezet"
  }
}

# ------------------------------------------------------------------ start
if (-not (Get-Command gh -ErrorAction SilentlyContinue)) {
  throw 'GitHub CLI (gh) niet gevonden. Installeer met: winget install GitHub.cli  (daarna: gh auth login)'
}
# Inlogcontrole via een echte API-vraag (gh auth status geeft onder PowerShell 5 niet altijd exitcode 0).
Write-Host 'Inlog controleren...'
$login = & gh api user --jq '.login' 2>&1
if ($LASTEXITCODE -ne 0 -or -not $login) {
  throw "Inlogcontrole mislukt. Melding van gh: $login`nNiet ingelogd? Draai dan: gh auth login"
}
Write-Host "Ingelogd als $login."
Write-Host 'labels.yml ophalen...'


$labels = LeesLabels
$secrets = @{}
if (-not $GeenSecrets) {
  Write-Host 'Secrets worden verborgen gevraagd en in alle opgegeven repo''s gezet.'
  $secrets['CLAUDE_CODE_OAUTH_TOKEN'] = LeesSecret 'CLAUDE_CODE_OAUTH_TOKEN'
  $secrets['PROJECT_TOKEN'] = LeesSecret 'PROJECT_TOKEN'
}

$fouten = @()
foreach ($naam in $Repos) {
  $R = if ($naam -like '*/*') { $naam } else { "$Eigenaar/$naam" }
  Write-Host "`n== $R"
  try {
    $openbaar = (GhRun api "repos/$R" --jq '.visibility') -eq 'public'
    Stap ("zichtbaarheid: " + $(if ($openbaar) { 'openbaar' } else { 'prive' }))
    Bezig 'merge-instellingen'; ZetMergeInstellingen $R
    Bezig 'beveiliging'; ZetBeveiliging $R $openbaar
    if ($openbaar -and -not $GeenRuleset) { Bezig 'ruleset'; ZetRuleset $R }
    elseif (-not $openbaar) { Stap 'ruleset: overgeslagen (prive zonder Pro; zie CHECKS.md)' }
    Bezig 'labels (kan even duren)'; ZetLabels $R $labels
    if (-not $GeenSecrets) { Bezig 'secrets'; ZetSecrets $R $secrets }
    Write-Host "  Klaar met $R" -ForegroundColor Green
  } catch {
    Write-Host "  FOUT: $($_.Exception.Message)" -ForegroundColor Red
    $fouten += $R
  }
}

# Secrets uit het geheugen halen.
foreach ($k in @($secrets.Keys)) { $secrets[$k] = $null }

if ($fouten.Count) {
  Write-Host "`nMislukt voor: $($fouten -join ', '). Los de melding op en draai het script opnieuw." -ForegroundColor Red
  exit 1
}
Write-Host "`nKlaar: $($Repos.Count) repo('s) ingericht." -ForegroundColor Green
