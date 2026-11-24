# Syntaxcontrole van alle PowerShell-scripts in scripts/. Draait in de checks (test).
$fouten = 0
foreach ($f in Get-ChildItem -Path (Join-Path $PSScriptRoot '..' 'scripts') -Filter *.ps1) {
  $tokens = $null; $errors = $null
  [System.Management.Automation.Language.Parser]::ParseFile($f.FullName, [ref]$tokens, [ref]$errors) | Out-Null
  foreach ($e in $errors) {
    Write-Host "::error file=scripts/$($f.Name),line=$($e.Extent.StartLineNumber)::$($e.Message)"
    $fouten++
  }
  if (-not $errors) { Write-Host "OK: scripts/$($f.Name)" }
}
exit [int]($fouten -gt 0)
