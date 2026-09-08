param([string]$InputDirectory='artifacts/region-native-production/run1',[string]$OutputDirectory='artifacts/region-native-production/edit-probe-v1')
Set-StrictMode -Version Latest
$ErrorActionPreference='Stop'
if (Get-Process POWERPNT -ErrorAction SilentlyContinue) { throw 'Existing PowerPoint process' }
$output=[IO.Path]::GetFullPath((Join-Path (Get-Location) $OutputDirectory))
if (Test-Path -LiteralPath $output) { throw 'Refusing evidence overwrite' }
New-Item -ItemType Directory -Path $output | Out-Null
function Snapshot($slide) {
 $rows=@()
 foreach ($s in $slide.Shapes) {
  $r=[ordered]@{name=$s.Name; id=$s.Id; left=[double]$s.Left; top=[double]$s.Top; width=[double]$s.Width; height=[double]$s.Height}
  if ($s.Connector -eq -1) {
   $r.begin_connected=$s.ConnectorFormat.BeginConnected -eq -1; $r.end_connected=$s.ConnectorFormat.EndConnected -eq -1
   if ($r.begin_connected) { $r.begin_owner=$s.ConnectorFormat.BeginConnectedShape.Name; $r.begin_site=$s.ConnectorFormat.BeginConnectionSite }
   if ($r.end_connected) { $r.end_owner=$s.ConnectorFormat.EndConnectedShape.Name; $r.end_site=$s.ConnectorFormat.EndConnectionSite }
  }
  $rows+=$r
 }
 return $rows
}
$app=New-Object -ComObject PowerPoint.Application
$deck=$null; $records=@()
try {
 foreach ($case in @(@{sample='mixed-attention'; owner='node:region:0'},@{sample='cogbot-perceive'; owner='node:region:1'})) {
  $name=$case.sample
  $file=(Resolve-Path -LiteralPath (Join-Path $InputDirectory "$name--region_native.pptx")).Path
  $hash=(Get-FileHash -LiteralPath $file).Hash
  $deck=$app.Presentations.Open($file,$true,$true,$false)
  $slide=$deck.Slides.Item(1); $before=@(Snapshot $slide)
  $deck.SaveAs((Join-Path $output "$name--roundtrip.pptx"),24)
  $slide.Export((Join-Path $output "$name--roundtrip.png"),'PNG',1200,0)
  $owner=$slide.Shapes.Item($case.owner)
  $text=[string]$owner.TextFrame.TextRange.Text
  $owner.TextFrame.TextRange.Text='REGION EDIT PROBE'
  $textOK=[string]$owner.TextFrame.TextRange.Text -eq 'REGION EDIT PROBE'
  $owner.TextFrame.TextRange.Text=$text
  $owner.LockAspectRatio=0
  $owner.Left=[double]$owner.Left+12; $owner.Top=[double]$owner.Top+18
  $owner.Width=[double]$owner.Width*1.25; $owner.Height=[double]$owner.Height*1.20
  $edited=@(Snapshot $slide)
  $editedPath=Join-Path $output "$name--edited.pptx"
  $deck.SaveAs($editedPath,24); $slide.Export((Join-Path $output "$name--edited.png"),'PNG',1200,0)
  $deck.Close(); [Runtime.InteropServices.Marshal]::FinalReleaseComObject($deck) | Out-Null; $deck=$null
  $deck=$app.Presentations.Open($editedPath,$true,$true,$false)
  $slide=$deck.Slides.Item(1); $reopened=@(Snapshot $slide)
  $deck.SaveAs((Join-Path $output "$name--reopened.pptx"),24)
  $slide.Export((Join-Path $output "$name--reopened.png"),'PNG',1200,0)
  foreach ($s in $slide.Shapes) { if ($s.Connector -eq -1) { $s.RerouteConnections() } }
  $rerouted=@(Snapshot $slide)
  $deck.SaveAs((Join-Path $output "$name--rerouted.pptx"),24)
  $slide.Export((Join-Path $output "$name--rerouted.png"),'PNG',1200,0)
  $deck.Close(); [Runtime.InteropServices.Marshal]::FinalReleaseComObject($deck) | Out-Null; $deck=$null
  $records+=[ordered]@{sample=$name; edited_owner=$case.owner; input_sha256=$hash.ToLowerInvariant(); original_unchanged=((Get-FileHash -LiteralPath $file).Hash -eq $hash); text_edit_succeeded=$textOK; before=$before; edited=$edited; reopened=$reopened; rerouted=$rerouted}
  [ordered]@{powerpoint_version=[string]$app.Version; records=$records} | ConvertTo-Json -Depth 10 | Set-Content -LiteralPath (Join-Path $output 'probe.json') -Encoding utf8
 }
} finally {
 if ($null -ne $deck) { $deck.Saved=-1; $deck.Close(); [Runtime.InteropServices.Marshal]::FinalReleaseComObject($deck) | Out-Null }
 $app.Quit(); [Runtime.InteropServices.Marshal]::FinalReleaseComObject($app) | Out-Null
}
