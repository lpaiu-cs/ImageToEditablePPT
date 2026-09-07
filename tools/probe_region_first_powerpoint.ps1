[CmdletBinding()]
param(
    [string] $InputPath = "artifacts/region-first-r0/run1/mixed-blip--roi_cv.pptx",
    [string] $OutputPath = "artifacts/region-first-r0/movement_probe.json"
)
Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
if (Get-Process POWERPNT -ErrorAction SilentlyContinue) {
    throw "An existing PowerPoint process is present; do not risk quitting the user's application."
}
$inputAbsolute = (Resolve-Path -LiteralPath $InputPath).Path
$outputAbsolute = [IO.Path]::GetFullPath((Join-Path (Get-Location) $OutputPath))
if (Test-Path -LiteralPath $outputAbsolute) { throw "Refusing to overwrite probe evidence." }
$powerPoint = New-Object -ComObject PowerPoint.Application
$presentation = $null
try {
    $presentation = $powerPoint.Presentations.Open($inputAbsolute, $true, $true, $false)
    $slide = $presentation.Slides.Item(1)
    $connector = $null
    foreach ($shape in $slide.Shapes) {
        if ($shape.Connector -eq -1 -and $shape.ConnectorFormat.BeginConnected -eq -1 -and $shape.ConnectorFormat.EndConnected -eq -1) {
            if ($shape.ConnectorFormat.BeginConnectedShape.Left -lt $shape.ConnectorFormat.EndConnectedShape.Left) {
                $connector = $shape
                break
            }
        }
    }
    if ($null -eq $connector) { throw "No suitable native left-to-right bound connector." }
    $source = $connector.ConnectorFormat.BeginConnectedShape
    $target = $connector.ConnectorFormat.EndConnectedShape
    $sourceId = $source.Id
    $targetId = $target.Id
    $sourceLeft = [double] $source.Left
    $targetLeft = [double] $target.Left
    $connectorLeft = [double] $connector.Left
    $originalText = [string] $source.TextFrame.TextRange.Text
    $source.Left = $sourceLeft + 12.0
    # No RerouteConnections call: measure normal bound-connector update after owner movement.
    $observedDelta = [double] $connector.Left - $connectorLeft
    $source.TextFrame.TextRange.Text = "R0 EDIT PROBE"
    $record = [ordered]@{
        status = "automated_native_behavior_probe_not_human_timing"
        powerpoint_version = [string] $powerPoint.Version
        input_path = $inputAbsolute
        input_sha256 = (Get-FileHash -LiteralPath $inputAbsolute -Algorithm SHA256).Hash.ToLowerInvariant()
        source_shape_name = $source.Name
        target_shape_name = $target.Name
        connector_name = $connector.Name
        requested_source_move_pt = 12.0
        observed_source_move_pt = [double] $source.Left - $sourceLeft
        observed_connector_left_move_pt = $observedDelta
        target_unmoved = [Math]::Abs([double] $target.Left - $targetLeft) -lt 0.01
        endpoint_binding_ids_preserved = ($connector.ConnectorFormat.BeginConnectedShape.Id -eq $sourceId -and $connector.ConnectorFormat.EndConnectedShape.Id -eq $targetId)
        owned_label_edit_succeeded = ([string] $source.TextFrame.TextRange.Text -eq "R0 EDIT PROBE")
        original_label = $originalText
        source_file_saved = $false
    }
    $record | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath $outputAbsolute -Encoding utf8
    $record | ConvertTo-Json -Depth 5
}
finally {
    if ($null -ne $presentation) {
        $presentation.Saved = -1
        $presentation.Close()
        [Runtime.InteropServices.Marshal]::FinalReleaseComObject($presentation) | Out-Null
    }
    $powerPoint.Quit()
    [Runtime.InteropServices.Marshal]::FinalReleaseComObject($powerPoint) | Out-Null
}
