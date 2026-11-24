# Controle van alle PowerShell-scripts in scripts/. Draait in de checks (test).
# - syntaxfouten
# - een functie met dezelfde naam als een programma dat het script met '&' aanroept
#   (PowerShell is hoofdletterongevoelig en functies gaan voor: '& gh' roept dan de functie aan)
$fouten = 0
foreach ($f in Get-ChildItem -Path (Join-Path $PSScriptRoot '..' 'scripts') -Filter *.ps1) {
  $tokens = $null; $errors = $null
  $ast = [System.Management.Automation.Language.Parser]::ParseFile($f.FullName, [ref]$tokens, [ref]$errors)
  foreach ($e in $errors) {
    Write-Host "::error file=scripts/$($f.Name),line=$($e.Extent.StartLineNumber)::$($e.Message)"
    $fouten++
  }
  $functies = @($ast.FindAll({ $args[0] -is [System.Management.Automation.Language.FunctionDefinitionAst] }, $true) |
      ForEach-Object { $_.Name.ToLowerInvariant() })
  $aanroepen = $ast.FindAll({
      $args[0] -is [System.Management.Automation.Language.CommandAst] -and
      $args[0].InvocationOperator -eq [System.Management.Automation.Language.TokenKind]::Ampersand -and
      $args[0].CommandElements[0] -is [System.Management.Automation.Language.StringConstantExpressionAst]
    }, $true)
  foreach ($a in $aanroepen) {
    $naam = $a.CommandElements[0].Value.ToLowerInvariant()
    if ($functies -contains $naam) {
      Write-Host "::error file=scripts/$($f.Name),line=$($a.Extent.StartLineNumber)::'& $naam' roept de functie '$naam' aan in plaats van het programma. Geef de functie een andere naam."
      $fouten++
    }
  }
  if (-not $errors) { Write-Host "Gecontroleerd: scripts/$($f.Name)" }
}
exit [int]($fouten -gt 0)
