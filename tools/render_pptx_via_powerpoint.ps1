[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string[]] $InputPath,

    [Parameter(Mandatory = $true)]
    [string] $OutputDirectory,

    [ValidateRange(64, 4096)]
    [int] $Width = 1200,

    [switch] $Force
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Resolve-TaskPath {
    param([Parameter(Mandatory = $true)][string] $Path)
    if ([System.IO.Path]::IsPathRooted($Path)) {
        return [System.IO.Path]::GetFullPath($Path)
    }
    return [System.IO.Path]::GetFullPath((Join-Path (Get-Location) $Path))
}

$resolvedOutput = Resolve-TaskPath -Path $OutputDirectory
if (-not (Test-Path -LiteralPath $resolvedOutput)) {
    New-Item -ItemType Directory -Path $resolvedOutput | Out-Null
}

$files = @()
foreach ($rawPath in $InputPath) {
    $resolved = Resolve-TaskPath -Path $rawPath
    if (Test-Path -LiteralPath $resolved -PathType Container) {
        $files += Get-ChildItem -LiteralPath $resolved -Filter "*.pptx" -File
    }
    elseif (Test-Path -LiteralPath $resolved -PathType Leaf) {
        $item = Get-Item -LiteralPath $resolved
        if ($item.Extension -ine ".pptx") {
            throw "Input is not a PPTX file: $resolved"
        }
        $files += $item
    }
    else {
        throw "Input path does not exist: $resolved"
    }
}
$files = @($files | Sort-Object -Property FullName -Unique)
if ($files.Count -eq 0) {
    throw "No PPTX files were found."
}

$powerPoint = New-Object -ComObject PowerPoint.Application
$records = @()
try {
    $powerPointVersion = [string] $powerPoint.Version
    foreach ($file in $files) {
        $target = Join-Path $resolvedOutput ($file.BaseName + ".png")
        if ((Test-Path -LiteralPath $target) -and -not $Force) {
            throw "Refusing to overwrite existing render: $target"
        }
        $presentation = $powerPoint.Presentations.Open($file.FullName, $true, $true, $false)
        try {
            if ($presentation.Slides.Count -ne 1) {
                throw "Expected one slide in $($file.FullName), found $($presentation.Slides.Count)"
            }
            $slideWidth = [double] $presentation.PageSetup.SlideWidth
            $slideHeight = [double] $presentation.PageSetup.SlideHeight
            $height = [Math]::Max(1, [Math]::Round($Width * $slideHeight / $slideWidth))
            $presentation.Slides.Item(1).Export($target, "PNG", $Width, $height)
        }
        finally {
            $presentation.Close()
            [System.Runtime.InteropServices.Marshal]::FinalReleaseComObject($presentation) | Out-Null
        }
        $records += [ordered]@{
            id = $file.BaseName
            pptx_path = $file.FullName
            pptx_sha256 = (Get-FileHash -LiteralPath $file.FullName -Algorithm SHA256).Hash.ToLowerInvariant()
            render_path = $target
            render_sha256 = (Get-FileHash -LiteralPath $target -Algorithm SHA256).Hash.ToLowerInvariant()
            width = $Width
            height = $height
        }
        Write-Output "[OK] $($file.Name) -> $target (${Width}x${height})"
    }
}
finally {
    $powerPoint.Quit()
    [System.Runtime.InteropServices.Marshal]::FinalReleaseComObject($powerPoint) | Out-Null
}

$manifest = [ordered]@{
    schema_version = "phase16_powerpoint_render_manifest_v1"
    generated_at = [DateTimeOffset]::UtcNow.ToString("o")
    powerpoint_version = $powerPointVersion
    export_format = "PNG"
    target_width = $Width
    records = $records
}
$manifestPath = Join-Path $resolvedOutput "powerpoint_render_manifest.json"
$manifest | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $manifestPath -Encoding utf8
Write-Output "[MANIFEST] $manifestPath"
