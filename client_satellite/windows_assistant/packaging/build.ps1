$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

$version = (Select-String -Path "settings\paths.py" -Pattern '^VERSION = "([0-9.]+)"').Matches[0].Groups[1].Value
if (-not $version) { throw "Versione non trovata in settings\paths.py" }
Write-Host "ATENA Assistente $version"

python packaging\make_icon.py build\atena.ico
python -m PyInstaller --noconfirm --clean --distpath build\dist --workpath build\work packaging\atena_assistant.spec

$iscc = Get-Command iscc.exe -ErrorAction SilentlyContinue
$compiler = if ($iscc) { $iscc.Source } else { "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe" }
& $compiler "/DAppVersion=$version" packaging\installer.iss
if ($LASTEXITCODE -ne 0) { throw "Inno Setup non riuscito ($LASTEXITCODE)" }

python packaging\sign_manifest.py build\installer\ATENA_Assistente_Setup.exe $version build\installer
"version=$version" | Out-File -FilePath build\version.txt -Encoding ascii
