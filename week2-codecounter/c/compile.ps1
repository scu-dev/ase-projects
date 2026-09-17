param(
    [ValidateSet('Debug', 'Release')]
    [string]$Configuration = 'Release'
)

$ErrorActionPreference = 'Stop'

# Usage: .\compile.ps1 Debug
#        .\compile.ps1 Release
$vswhere = Join-Path ${env:ProgramFiles(x86)} 'Microsoft Visual Studio\Installer\vswhere.exe'
if (!(Test-Path -LiteralPath $vswhere)) {
    throw 'Visual Studio Installer was not found. Install Visual Studio with C++ build tools.'
}
$vsPath = & $vswhere -latest -products * -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property installationPath
if (!$vsPath) {
    throw 'No Visual Studio installation with C++ build tools was found.'
}
Import-Module (Join-Path $vsPath 'Common7\Tools\Microsoft.VisualStudio.DevShell.dll')
Enter-VsDevShell -VsInstallPath $vsPath -SkipAutomaticLocation -DevCmdArguments '-arch=x64 -host_arch=x64'

Push-Location $PSScriptRoot
try {
    if ($Configuration -eq 'Debug') {
        # Disable optimization and generate debugging symbols.
        cl /nologo /W4 /utf-8 /TC /Od /Zi /D_DEBUG /MDd codecounter.c /Fe:codecounter.exe /link /DEBUG
    } else {
        # Enable optimization and use the release runtime.
        cl /nologo /W4 /utf-8 /TC /O2 /DNDEBUG /MD codecounter.c /Fe:codecounter.exe
    }
    if ($LASTEXITCODE -ne 0) {
        throw "Compilation failed with exit code $LASTEXITCODE."
    }
} finally {
    Pop-Location
}