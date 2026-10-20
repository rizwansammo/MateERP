# New database per run; keeps financial fixtures away from the development installation.
param([switch]$SkipBuild, [string]$TestFile)
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$savedUrl = $env:MATEERP_BACKEND_URL
$savedDb = $env:MATEERP_E2E_DB_NAME
$savedService = $env:MATEERP_TEST_SERVICE
$env:MATEERP_E2E_DB_NAME = 'mateerp_e2e_' + [Guid]::NewGuid().ToString('N')
$env:MATEERP_BACKEND_URL = 'http://127.0.0.1:8101'
$env:MATEERP_TEST_SERVICE = 'backend-e2e'
Push-Location $root
try {
    docker compose exec -T backend python manage.py prepare_e2e_database $env:MATEERP_E2E_DB_NAME
    if ($LASTEXITCODE -ne 0) { throw 'Unable to create isolated browser-test database.' }
    docker compose --profile e2e up -d backend-e2e
    if ($LASTEXITCODE -ne 0) { throw 'Unable to start isolated browser-test backend.' }
    $ready = $false
    for ($i = 0; $i -lt 60; $i++) {
        try {
            $response = Invoke-WebRequest 'http://127.0.0.1:8101/api/v1/health/' -UseBasicParsing -TimeoutSec 2
            if ($response.StatusCode -eq 200) { $ready = $true; break }
        } catch { Start-Sleep -Seconds 1 }
    }
    if (-not $ready) { docker compose logs --tail 30 backend-e2e; throw 'Browser-test backend did not become ready.' }
    Push-Location frontend
    try {
        if (-not $SkipBuild) { npm run build; if ($LASTEXITCODE -ne 0) { throw 'Frontend build failed.' } }
        if ($TestFile) { npx playwright test $TestFile } else { npx playwright test }
        if ($LASTEXITCODE -ne 0) { throw 'Browser acceptance tests failed.' }
    } finally { Pop-Location }
    Write-Host "Browser data retained in $env:MATEERP_E2E_DB_NAME."
} finally {
    docker compose --profile e2e stop backend-e2e
    $env:MATEERP_BACKEND_URL = $savedUrl
    $env:MATEERP_E2E_DB_NAME = $savedDb
    $env:MATEERP_TEST_SERVICE = $savedService
    Pop-Location
}
