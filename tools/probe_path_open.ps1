param([string]$InputDirectory='artifacts/region-first-r3e/run1',[string]$OutputPath='artifacts/region-first-r3e/open_probe.json')
$ErrorActionPreference='Stop'
if (Get-Process POWERPNT -ErrorAction SilentlyContinue) { throw 'Existing PowerPoint process' }
if (Test-Path -LiteralPath $OutputPath) { throw 'Evidence already exists' }
$app=New-Object -ComObject PowerPoint.Application
$records=@()
try {
 foreach ($file in Get-ChildItem -LiteralPath $InputDirectory -Filter '*.pptx') {
  $deck=$null
  $r=[ordered]@{path=$file.FullName; sha256=(Get-FileHash -LiteralPath $file.FullName).Hash.ToLowerInvariant()}
  try { $deck=$app.Presentations.Open($file.FullName,$true,$true,$false); $r.opened=$true }
  catch { $r.opened=$false; $r.error=$_.Exception.Message; $r.hresult=$_.Exception.HResult }
  finally { if ($null -ne $deck) { $deck.Close(); [Runtime.InteropServices.Marshal]::FinalReleaseComObject($deck) | Out-Null } }
  $records+=$r
 }
 [ordered]@{powerpoint_version=[string]$app.Version; records=$records} | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath $OutputPath -Encoding utf8
 $records | ConvertTo-Json -Depth 6
} finally { $app.Quit(); [Runtime.InteropServices.Marshal]::FinalReleaseComObject($app) | Out-Null }
