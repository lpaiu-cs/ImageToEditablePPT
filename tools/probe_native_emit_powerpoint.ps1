[CmdletBinding()]
param([string] $RunDirectory = 'artifacts/region-first-r1/run1',
      [string] $OutputDirectory = 'artifacts/region-first-r1/edit-probe-v1')
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
if (Get-Process POWERPNT -ErrorAction SilentlyContinue) { throw 'Existing PowerPoint: refusing application reuse.' }
$output = [IO.Path]::GetFullPath((Join-Path (Get-Location) $OutputDirectory))
if (Test-Path -LiteralPath $output) { throw 'Refusing to overwrite evidence.' }
New-Item -ItemType Directory -Path $output | Out-Null
function Snapshot($slide) {
    $records = @()
    foreach ($shape in $slide.Shapes) {
        $r = [ordered]@{name=$shape.Name; id=$shape.Id; left=[double]$shape.Left; top=[double]$shape.Top; width=[double]$shape.Width; height=[double]$shape.Height}
        if ($shape.Connector -eq -1) {
            $r.begin_connected = $shape.ConnectorFormat.BeginConnected -eq -1
            $r.end_connected = $shape.ConnectorFormat.EndConnected -eq -1
            if ($r.begin_connected) { $r.begin_owner=$shape.ConnectorFormat.BeginConnectedShape.Name; $r.begin_site=$shape.ConnectorFormat.BeginConnectionSite }
            if ($r.end_connected) { $r.end_owner=$shape.ConnectorFormat.EndConnectedShape.Name; $r.end_site=$shape.ConnectorFormat.EndConnectionSite }
        }
        $records += $r
    }
    return $records
}
$app = New-Object -ComObject PowerPoint.Application
$deck = $null
$records = @()
try {
    foreach ($arm in @('normalize_only','normalized_sites')) {
        $inputFile = (Resolve-Path -LiteralPath (Join-Path $RunDirectory "mixed-attention--$arm.pptx")).Path
        $beforeHash = (Get-FileHash -LiteralPath $inputFile).Hash
        $deck = $app.Presentations.Open($inputFile, $true, $true, $false)
        $slide = $deck.Slides.Item(1)
        $before = @(Snapshot $slide)
        $target = $slide.Shapes.Item('attention')
        $oldText = [string]$target.TextFrame.TextRange.Text
        $target.TextFrame.TextRange.Text = 'R1 EDIT PROBE'
        $textEdit = [string]$target.TextFrame.TextRange.Text -eq 'R1 EDIT PROBE'
        $target.TextFrame.TextRange.Text = $oldText
        $target.LockAspectRatio = 0
        $target.Left = [double]$target.Left + 12
        $target.Top = [double]$target.Top + 18
        $target.Width = [double]$target.Width * 1.25
        $target.Height = [double]$target.Height * 1.20
        $edited = @(Snapshot $slide)
        $editedPath = Join-Path $output "$arm--edited.pptx"
        $deck.SaveAs($editedPath,24)
        $slide.Export((Join-Path $output "$arm--edited.png"),'PNG',1200,0)
        $deck.Close()
        [Runtime.InteropServices.Marshal]::FinalReleaseComObject($deck) | Out-Null
        $deck = $null
        $deck = $app.Presentations.Open($editedPath,$true,$true,$false)
        $slide = $deck.Slides.Item(1)
        $reopened = @(Snapshot $slide)
        $deck.SaveAs((Join-Path $output "$arm--reopened.pptx"),24)
        $slide.Export((Join-Path $output "$arm--reopened.png"),'PNG',1200,0)
        foreach ($shape in $slide.Shapes) { if ($shape.Connector -eq -1) { $shape.RerouteConnections() } }
        $rerouted = @(Snapshot $slide)
        $deck.SaveAs((Join-Path $output "$arm--rerouted.pptx"),24)
        $slide.Export((Join-Path $output "$arm--rerouted.png"),'PNG',1200,0)
        $deck.Close()
        [Runtime.InteropServices.Marshal]::FinalReleaseComObject($deck) | Out-Null
        $deck = $null
        $records += [ordered]@{arm=$arm; input_path=$inputFile; input_sha256=$beforeHash.ToLowerInvariant(); original_unchanged=((Get-FileHash -LiteralPath $inputFile).Hash -eq $beforeHash); text_edit_succeeded=$textEdit; before=$before; edited=$edited; reopened=$reopened; rerouted=$rerouted}
        [ordered]@{status='automated_native_probe_not_human_timing'; powerpoint_version=[string]$app.Version; records=$records} | ConvertTo-Json -Depth 10 | Set-Content -LiteralPath (Join-Path $output 'probe.json') -Encoding utf8
    }
}
finally {
    if ($null -ne $deck) { $deck.Saved=-1; $deck.Close(); [Runtime.InteropServices.Marshal]::FinalReleaseComObject($deck) | Out-Null }
    $app.Quit()
    [Runtime.InteropServices.Marshal]::FinalReleaseComObject($app) | Out-Null
}
Write-Output "Saved native edit probe: $output"
