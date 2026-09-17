param(
    [ValidateSet('Debug', 'Release')]
    [string]$Configuration = 'Release'
)

$ErrorActionPreference = 'Stop'

# Usage: .\compile.ps1 Debug
#        .\compile.ps1 Release
Push-Location $PSScriptRoot
try {
    if ($Configuration -eq 'Debug') {
        cargo build --bin codecounter
    } else {
        cargo build --bin codecounter --release
    }
    if ($LASTEXITCODE -ne 0) {
        throw "Compilation failed with exit code $LASTEXITCODE."
    }
} finally {
    Pop-Location
}