param([Parameter(Mandatory=$true)][string]$ExperimentDirectory)
$ErrorActionPreference = 'Stop'
$root = (Resolve-Path -LiteralPath $ExperimentDirectory).Path
function Hash-File([string]$path) {
    $hasher = [Security.Cryptography.SHA256]::Create()
    try { return ([BitConverter]::ToString($hasher.ComputeHash([IO.File]::ReadAllBytes($path)))).Replace('-', '').ToLowerInvariant() }
    finally { $hasher.Dispose() }
}
$hadPowerPoint = @(Get-Process POWERPNT -ErrorAction SilentlyContinue).Count -gt 0
$app = New-Object -ComObject PowerPoint.Application
$records = @()
try {
    foreach ($variant in @('native-baseline', 'native-candidate')) {
        $output = Join-Path $root ($variant + '/render-v2')
        if (Test-Path -LiteralPath $output) { throw "Output already exists: $output" }
        New-Item -ItemType Directory -Path $output | Out-Null
        foreach ($file in Get-ChildItem -LiteralPath (Join-Path $root $variant) -Filter '*.pptx') {
            $presentation = $app.Presentations.Open($file.FullName, $true, $true, $false)
            try {
                $target = Join-Path $output ($file.BaseName + '.png')
                $presentation.Slides.Item(1).Export($target, 'PNG', 1280, 720)
                $records += [ordered]@{variant=$variant; name=$file.BaseName; pptx_sha256=(Hash-File $file.FullName); render=$target; render_sha256=(Hash-File $target); shapes=$presentation.Slides.Item(1).Shapes.Count}
            } finally {
                $presentation.Close()
                [void][Runtime.InteropServices.Marshal]::FinalReleaseComObject($presentation)
            }
        }
    }
} finally {
    # Never terminate a pre-existing user instance or presentations opened meanwhile.
    if (-not $hadPowerPoint -and $app.Presentations.Count -eq 0) { $app.Quit() }
    [void][Runtime.InteropServices.Marshal]::FinalReleaseComObject($app)
}
$records | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath (Join-Path $root 'native-render.json') -Encoding UTF8
Write-Output "Rendered $($records.Count) PPTX files; pre-existing PowerPoint: $hadPowerPoint"
