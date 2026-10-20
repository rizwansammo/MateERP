# Runs every MateERP Phase 1 check. Requires the Docker stack to be running
# (docker compose up -d) and frontend dependencies installed (npm ci).
#   powershell -ExecutionPolicy Bypass -File scripts\verify.ps1 [-SkipE2E]
param([switch]$SkipE2E)

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$failed = @()

function Step([string]$name, [scriptblock]$block) {
    Write-Host "`n=== $name ===" -ForegroundColor Cyan
    & $block
    if ($LASTEXITCODE -ne 0) {
        Write-Host "FAILED: $name" -ForegroundColor Red
        $script:failed += $name
    } else {
        Write-Host "OK: $name" -ForegroundColor Green
    }
}

Push-Location $root
try {
    Step 'Backend: Django system check' { docker compose exec -T backend python manage.py check }
    Step 'Backend: no missing migrations' { docker compose exec -T backend python manage.py makemigrations --check --dry-run }
    Step 'Backend: ruff lint' { docker compose exec -T backend ruff check . }
    Step 'Backend: ruff format' { docker compose exec -T backend ruff format --check . }
    Step 'Backend: pytest (PostgreSQL)' { docker compose exec -T backend pytest }

    Push-Location frontend
    try {
        Step 'Frontend: ESLint' { npm run lint }
        Step 'Frontend: TypeScript' { npm run typecheck }
        Step 'Frontend: unit tests' { npm test }
        Step 'Frontend: production build' { npm run build }
        if (-not $SkipE2E) {
            Step 'Frontend: e2e against live backend' { npx playwright test }
        }
    } finally {
        Pop-Location
    }
} finally {
    Pop-Location
}

if ($failed.Count -gt 0) {
    Write-Host "`n$($failed.Count) check(s) failed: $($failed -join ', ')" -ForegroundColor Red
    exit 1
}
Write-Host "`nAll checks passed." -ForegroundColor Green
