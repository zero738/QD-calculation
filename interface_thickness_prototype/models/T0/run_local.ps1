param([string]$InputFile = 'single_point.inp')
$ErrorActionPreference = 'Stop'
$cmd = $env:CP2K_CMD
if (-not $cmd) { foreach ($candidate in @('cp2k.psmp','cp2k.popt','cp2k')) { if (Get-Command $candidate -ErrorAction SilentlyContinue) { $cmd=$candidate; break } } }
if (-not $cmd) { throw 'CP2K not found. Set CP2K_CMD.' }
if (-not $env:OMP_NUM_THREADS) { $env:OMP_NUM_THREADS='4' }
$OutputFile = [IO.Path]::ChangeExtension($InputFile, '.out')
& $cmd -i $InputFile -o $OutputFile
& $env:PYTHON ../../scripts/parse_cp2k_output.py $OutputFile --input $InputFile
