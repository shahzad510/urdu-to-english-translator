# Build the offline Windows x64 application folder and, when Inno Setup is
# already installed, the installer. This script does not download files.
$ErrorActionPreference = "Stop"

$Root = Resolve-Path (Join-Path $PSScriptRoot "..\..")
Set-Location $Root

function Fail([string]$Message) {
    Write-Error $Message
    exit 1
}

if (-not [Environment]::Is64BitOperatingSystem) {
    Fail "This build requires 64-bit Windows."
}

$Python = Join-Path $Root ".venv\Scripts\python.exe"

if (-not (Test-Path $Python)) {
    Fail "Project virtual environment Python was not found at $Python."
}

$Version = & $Python -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}'); print(sys.maxsize > 2**32)"
$Lines = $Version -split "`n"

if ($Lines[0].Trim() -notin @("3.11", "3.12")) {
    Fail "Python 3.11 or 3.12 is required. Found $($Lines[0])."
}

if ($Lines[1].Trim() -ne "True") {
    Fail "Python is not 64-bit."
}

& $Python -c "import PySide6, docx, PyInstaller"

if ($LASTEXITCODE -ne 0) {
    Fail "Required build packages are missing from the project virtual environment."
}

$Icon = Join-Path $PSScriptRoot "assets\UrduTranslator.ico"
if (-not (Test-Path $Icon)) {
    Fail "Missing packaging\windows\assets\UrduTranslator.ico. Generate it from the repository root icon.png before building."
}

$Runtime = Join-Path $PSScriptRoot "runtime"
$Server = Join-Path $Runtime "llama-server.exe"
if (-not (Test-Path $Server)) {
    Fail "Place a CPU-only Windows x64 llama-server.exe and every DLL it needs in packaging\windows\runtime. Do not use the Linux llama-server binary. This script will not download llama.cpp."
}

$Gguf = Get-ChildItem -Path $Runtime -Filter *.gguf -Recurse -ErrorAction SilentlyContinue
if ($Gguf) {
    Fail "A .gguf file is in the packaging tree. Remove it. The model is transferred on USB and must not be installed with the application."
}

$Dist = Join-Path $PSScriptRoot "dist"
$Work = Join-Path $PSScriptRoot "build"
if (Test-Path $Dist) { Remove-Item $Dist -Recurse -Force }
if (Test-Path $Work) { Remove-Item $Work -Recurse -Force }

& $Python -m PyInstaller --noconfirm --distpath $Dist --workpath $Work (Join-Path $PSScriptRoot "UrduTranslator.spec")
if ($LASTEXITCODE -ne 0) {
    Fail "PyInstaller did not produce the application."
}

$Exe = Join-Path $Dist "UrduTranslator\UrduTranslator.exe"
if (-not (Test-Path $Exe)) {
    Fail "UrduTranslator.exe was not created."
}
$BundledServer = Get-ChildItem -Path (Join-Path $Dist "UrduTranslator") -Filter "llama-server.exe" -File -Recurse | Select-Object -First 1
if (-not $BundledServer) {
    Fail "llama-server.exe was not copied into the application runtime folder."
}
$PackagedModel = Get-ChildItem -Path $Dist -Filter *.gguf -Recurse -ErrorAction SilentlyContinue
if ($PackagedModel) {
    Fail "The build contains a GGUF file. The installer must not include the model."
}

Write-Host "Application folder: $Dist\UrduTranslator"
Write-Host "UrduTranslator.exe and llama-server.exe are present. No GGUF file was packaged."

$Iscc = Get-Command ISCC -ErrorAction SilentlyContinue
if (-not $Iscc) {
    Write-Host "Inno Setup compiler (ISCC) was not found. The installer was not built. Compile packaging\windows\installer.iss on this machine when Inno Setup is installed. Do not download it from the offline target."
    exit 0
}

& ISCC (Join-Path $PSScriptRoot "installer.iss")
if ($LASTEXITCODE -ne 0) {
    Fail "Inno Setup did not create the installer."
}
$Setup = Join-Path $PSScriptRoot "output\UrduTranslator-Setup-1.0.0-x64.exe"
if (-not (Test-Path $Setup)) {
    Fail "The installer file was not created."
}
Write-Host "Installer: $Setup"
