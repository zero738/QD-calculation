[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
$PrototypeRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$Source = Join-Path $PrototypeRoot 'server_scnet_2024_1'
$Zip = Join-Path $PrototypeRoot 'scnet_upload_bundle.zip'
$Stage = Join-Path $PrototypeRoot '.scnet_bundle_stage'
$StagePackage = Join-Path $Stage 'server_scnet_2024_1'

if (-not (Test-Path -LiteralPath (Join-Path $Source 'submit_pipeline.sh'))) {
    throw 'Incomplete server package: submit_pipeline.sh is missing.'
}

Get-Content -LiteralPath (Join-Path $Source 'upload_manifest.txt') | ForEach-Object {
    if ($_ -match '^([0-9a-f]{64})  (.+)$') {
        $Expected = $Matches[1]
        $Path = Join-Path $Source ($Matches[2] -replace '/', '\')
        if (-not (Test-Path -LiteralPath $Path)) { throw "Manifest file missing: $Path" }
        $Actual = (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLowerInvariant()
        if ($Actual -ne $Expected) { throw "Manifest hash mismatch: $Path" }
    }
}

if (Test-Path -LiteralPath $Stage) {
    $Resolved = (Resolve-Path -LiteralPath $Stage).Path
    if (-not $Resolved.StartsWith((Resolve-Path -LiteralPath $PrototypeRoot).Path)) {
        throw 'Refusing to remove staging path outside interface_thickness_prototype.'
    }
    Remove-Item -LiteralPath $Resolved -Recurse -Force
}
New-Item -ItemType Directory -Path $StagePackage | Out-Null

$ExcludedDirectoryNames = @('runs', '__pycache__', '.git', '.venv', 'venv')
$ExcludedExtensions = @('.pyc', '.wfn', '.restart', '.cube', '.out')
Get-ChildItem -LiteralPath $Source -Recurse -File | ForEach-Object {
    $Relative = $_.FullName.Substring($Source.Length).TrimStart('\')
    $Parts = $Relative -split '\\'
    if ($Parts | Where-Object { $_ -in $ExcludedDirectoryNames }) { return }
    if ($_.Extension.ToLowerInvariant() -in $ExcludedExtensions) { return }
    if ($_.Name -eq 'scnet_results_bundle.tar.gz') { return }
    $Destination = Join-Path $StagePackage $Relative
    New-Item -ItemType Directory -Path (Split-Path -Parent $Destination) -Force | Out-Null
    Copy-Item -LiteralPath $_.FullName -Destination $Destination
}

if (Test-Path -LiteralPath $Zip) { Remove-Item -LiteralPath $Zip -Force }
Add-Type -AssemblyName System.IO.Compression
Add-Type -AssemblyName System.IO.Compression.FileSystem
$Stream = [System.IO.File]::Open($Zip, [System.IO.FileMode]::CreateNew)
$Archive = New-Object System.IO.Compression.ZipArchive($Stream, [System.IO.Compression.ZipArchiveMode]::Create)
try {
    Get-ChildItem -LiteralPath $StagePackage -Recurse -File | ForEach-Object {
        $Relative = $_.FullName.Substring($StagePackage.Length).TrimStart('\').Replace('\', '/')
        $EntryName = "server_scnet_2024_1/$Relative"
        [System.IO.Compression.ZipFileExtensions]::CreateEntryFromFile(
            $Archive, $_.FullName, $EntryName, [System.IO.Compression.CompressionLevel]::Optimal
        ) | Out-Null
    }
}
finally {
    $Archive.Dispose()
    $Stream.Dispose()
}
Remove-Item -LiteralPath $Stage -Recurse -Force
Write-Host "Created: $Zip"
