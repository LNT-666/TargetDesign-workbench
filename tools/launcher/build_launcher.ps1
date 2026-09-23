# Build the double-click launcher for the local web workbench.
#
#   powershell -ExecutionPolicy Bypass -File tools\launcher\build_launcher.ps1
#
# The result is a small native WinForms exe (no .NET SDK, no PyInstaller).  It
# starts `python webapp\app.py` with the interpreter found on this machine and
# opens the browser once the server answers.
param(
    [string]$Output = "",
    [switch]$Quiet
)

$ErrorActionPreference = "Stop"

$launcherDir = $PSScriptRoot
$repoRoot = Split-Path -Parent (Split-Path -Parent $launcherDir)
$source = Join-Path $launcherDir "WorkbenchLauncher.cs"

if (-not (Test-Path $source)) {
    throw "launcher source not found: $source"
}
if (-not (Test-Path (Join-Path $repoRoot "webapp\app.py"))) {
    throw "webapp\app.py not found under $repoRoot"
}

if ([string]::IsNullOrWhiteSpace($Output)) {
    $Output = Join-Path $repoRoot "TargetDesign-workbench.exe"
}

$cscCandidates = @(
    (Join-Path $env:windir "Microsoft.NET\Framework64\v4.0.30319\csc.exe"),
    (Join-Path $env:windir "Microsoft.NET\Framework\v4.0.30319\csc.exe")
)
$csc = $cscCandidates | Where-Object { Test-Path $_ } | Select-Object -First 1
if (-not $csc) {
    throw "no C# compiler found (looked for csc.exe under $env:windir\Microsoft.NET)"
}

$arguments = @(
    "/nologo",
    "/target:winexe",
    "/optimize+",
    "/platform:anycpu",
    "/reference:System.dll",
    "/reference:System.Drawing.dll",
    "/reference:System.Windows.Forms.dll",
    "/out:$Output",
    $source
)

if (-not $Quiet) {
    Write-Host "compiler : $csc"
    Write-Host "source   : $source"
    Write-Host "output   : $Output"
}

& $csc $arguments
if ($LASTEXITCODE -ne 0) {
    throw "csc failed with exit code $LASTEXITCODE"
}

$item = Get-Item $Output
$hash = (Get-FileHash -Algorithm SHA256 $Output).Hash
if (-not $Quiet) {
    Write-Host ("built    : {0} ({1:N0} bytes)" -f $item.FullName, $item.Length)
    Write-Host "sha256   : $hash"
}