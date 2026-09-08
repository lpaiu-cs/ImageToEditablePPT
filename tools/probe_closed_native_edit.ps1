[CmdletBinding()]
param(
    [Parameter(Mandatory=$true)][string]$InputPath,
    [Parameter(Mandatory=$true)][string]$OwnerName,
    [Parameter(Mandatory=$true)][string]$OutputDirectory
)
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
if (Get-Process POWERPNT -ErrorAction SilentlyContinue) { throw 'An existing PowerPoint session must not be disturbed.' }
$taskSource = (Resolve-Path -LiteralPath $InputPath).Path
$taskOutput = [IO.Path]::GetFullPath((Join-Path (Get-Location) $OutputDirectory))
if (Test-Path -LiteralPath $taskOutput) { throw 'Output directory already exists.' }
$taskSourceHash = (Get-FileHash -LiteralPath $taskSource -Algorithm SHA256).Hash
New-Item -ItemType Directory -Path $taskOutput | Out-Null
$taskEdited = Join-Path $taskOutput 'edited.pptx'
Copy-Item -LiteralPath $taskSource -Destination $taskEdited
$taskPowerPoint = New-Object -ComObject PowerPoint.Application
$taskDeck = $null
try {
    $taskDeck = $taskPowerPoint.Presentations.Open($taskEdited, $false, $false, $false)
    $taskSlide = $taskDeck.Slides.Item(1)
    $taskOwner = $taskSlide.Shapes.Item($OwnerName)
    $taskBefore = [ordered]@{ left=[double]$taskOwner.Left; top=[double]$taskOwner.Top; text=[string]$taskOwner.TextFrame.TextRange.Text }
    $taskConnections = @()
    foreach ($taskShape in $taskSlide.Shapes) {
        if ($taskShape.Connector -ne -1) { continue }
        $taskFormat = $taskShape.ConnectorFormat
        if ($taskFormat.BeginConnected -ne -1 -or $taskFormat.EndConnected -ne -1) { throw 'Detached native connector before edit.' }
        if ($taskFormat.BeginConnectedShape.Name -eq $OwnerName -or $taskFormat.EndConnectedShape.Name -eq $OwnerName) {
            $taskConnections += [ordered]@{ name=[string]$taskShape.Name; begin=[string]$taskFormat.BeginConnectedShape.Name; end=[string]$taskFormat.EndConnectedShape.Name; left=[double]$taskShape.Left; top=[double]$taskShape.Top; width=[double]$taskShape.Width; height=[double]$taskShape.Height }
        }
    }
    if ($taskConnections.Count -eq 0) { throw 'Choose an owner with an actual native connection.' }
    $taskOwner.Left = $taskOwner.Left + 12
    $taskOwner.Top = $taskOwner.Top + 8
    $taskOwner.TextFrame.TextRange.Text = $taskBefore.text + ' [edit probe]'
    $taskAfterConnections = @()
    foreach ($taskConnection in $taskConnections) {
        $taskShape = $taskSlide.Shapes.Item($taskConnection.name)
        $taskFormat = $taskShape.ConnectorFormat
        if ($taskFormat.BeginConnected -ne -1 -or $taskFormat.EndConnected -ne -1) { throw 'Native connection detached after owner move.' }
        if ($taskFormat.BeginConnectedShape.Name -ne $taskConnection.begin -or $taskFormat.EndConnectedShape.Name -ne $taskConnection.end) { throw 'Native connection owner changed.' }
        $taskAfterConnections += [ordered]@{ name=[string]$taskShape.Name; left=[double]$taskShape.Left; top=[double]$taskShape.Top; width=[double]$taskShape.Width; height=[double]$taskShape.Height }
    }
    $taskAfter = [ordered]@{ left=[double]$taskOwner.Left; top=[double]$taskOwner.Top; text=[string]$taskOwner.TextFrame.TextRange.Text }
    if ([Math]::Abs($taskAfter.left-$taskBefore.left-12) -gt .01 -or [Math]::Abs($taskAfter.top-$taskBefore.top-8) -gt .01) { throw 'Owner movement did not persist.' }
    $taskDeck.Save()
    $taskSlide.Export((Join-Path $taskOutput 'edited.png'),'PNG',1280,[Math]::Round(1280*$taskDeck.PageSetup.SlideHeight/$taskDeck.PageSetup.SlideWidth))
    $taskReport = [ordered]@{ scope='Automated PowerPoint editability probe on a copy; not human editing-time evidence'; source=$taskSource; source_sha256=$taskSourceHash.ToLowerInvariant(); edited=$taskEdited; owner=$OwnerName; before=$taskBefore; after=$taskAfter; connections_before=$taskConnections; connections_after=$taskAfterConnections }
    $taskReport | ConvertTo-Json -Depth 10 | Set-Content -LiteralPath (Join-Path $taskOutput 'edit-probe.json') -Encoding utf8
    $taskReport | ConvertTo-Json -Depth 10
}
finally {
    if ($null -ne $taskDeck) { $taskDeck.Close(); [Runtime.InteropServices.Marshal]::FinalReleaseComObject($taskDeck) | Out-Null }
    $taskPowerPoint.Quit()
    [Runtime.InteropServices.Marshal]::FinalReleaseComObject($taskPowerPoint) | Out-Null
}
if ((Get-FileHash -LiteralPath $taskSource -Algorithm SHA256).Hash -ne $taskSourceHash) { throw 'Frozen source deck changed.' }
