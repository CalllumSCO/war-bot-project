# Cut Cloud Run war-bot-api over to Supabase via DATABASE_URL.
# Requires: billing enabled on war-bot-476522, gcloud auth, .env.local with pooler DATABASE_URL.
#
# IAM needed for joyfulsinger.rlw@gmail.com (Owner must grant if missing):
#   roles/storage.objectAdmin      - upload Cloud Build source
#   roles/secretmanager.admin      - create/update database_url secret
#   roles/cloudbuild.builds.editor - already present
#   roles/run.admin                - already present
#   roles/artifactregistry.writer  - already present
#
#   powershell -ExecutionPolicy Bypass -File scripts/cutover_supabase_cloudrun.ps1
#
# Optional: skip Secret Manager and set DATABASE_URL as a plain env var:
#   $env:CUTOVER_PLAIN_ENV = "1"

$Project = "war-bot-476522"
$Region = "us-east1"
$Service = "war-bot-api"
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $Root

# Avoid ErrorActionPreference=Stop: gcloud.ps1 emits NativeCommandError noise
# ("Python was not found") that would abort the script.

$envFile = Join-Path $Root ".env.local"
if (-not (Test-Path $envFile)) {
    throw "Missing .env.local - need a Session pooler DATABASE_URL."
}

$dbUrl = $null
Get-Content $envFile | ForEach-Object {
    if ($_ -match '^\s*(?:DATABASE_URL|SUPABASE_DATABASE_URL|supabase)\s*=\s*(.+)\s*$') {
        $dbUrl = $Matches[1].Trim().Trim('"').Trim("'")
    }
}
if (-not $dbUrl) {
    throw "No DATABASE_URL / SUPABASE_DATABASE_URL / supabase in .env.local"
}
if ($dbUrl -notmatch 'pooler\.supabase\.com') {
    Write-Warning "DATABASE_URL host is not Session pooler - Cloud Run (IPv4) may fail on direct db.*.supabase.co."
}

Write-Host "Building API image..."
# --async avoids failing when this account cannot stream Cloud Build logs.
gcloud builds submit --config=cloudbuild.api.yaml --project=$Project --async .
if ($LASTEXITCODE -ne 0) {
    throw "Cloud Build submit failed (exit $LASTEXITCODE). Need roles/storage.objectAdmin on the cloudbuild bucket."
}
$buildId = gcloud builds list --project=$Project --ongoing --limit=1 --format="value(id)"
if (-not $buildId) {
    # Fall back to most recent build if it already left "ongoing".
    $buildId = gcloud builds list --project=$Project --limit=1 --format="value(id)"
}
Write-Host "Waiting for build $buildId..."
do {
    Start-Sleep -Seconds 5
    $status = gcloud builds describe $buildId --project=$Project --format="value(status)"
    Write-Host "  status=$status"
} while ($status -in @("QUEUED", "WORKING", "STATUS_UNKNOWN", ""))
if ($status -ne "SUCCESS") {
    throw "Cloud Build finished with status=$status (id=$buildId)."
}
Write-Host "Build SUCCESS."

Write-Host "Upserting DB connection for Cloud Run (value not printed)..."
$plainEnv = $env:CUTOVER_PLAIN_ENV -eq "1"
$secretFlag = $null
$envFlag = "USE_JSON_STORES=0"
if ($plainEnv) {
    Write-Warning "CUTOVER_PLAIN_ENV=1 - setting DATABASE_URL as a plain Cloud Run env var (visible to project editors)."
    $envFlag = "USE_JSON_STORES=0,DATABASE_URL=$dbUrl"
} else {
    $tmp = Join-Path $env:TEMP "war-bot-database-url.txt"
    try {
        Set-Content -Path $tmp -Value $dbUrl -NoNewline -Encoding utf8
        gcloud secrets describe database_url --project=$Project 2>$null | Out-Null
        if ($LASTEXITCODE -ne 0) {
            gcloud secrets create database_url --project=$Project --replication-policy=automatic
            if ($LASTEXITCODE -ne 0) { throw "Failed to create database_url secret. Grant roles/secretmanager.admin or set CUTOVER_PLAIN_ENV=1." }
        }
        gcloud secrets versions add database_url --project=$Project --data-file=$tmp | Out-Null
        if ($LASTEXITCODE -ne 0) { throw "Failed to add database_url secret version." }
    }
    finally {
        Remove-Item -Force $tmp -ErrorAction SilentlyContinue
    }
    $secretFlag = "DATABASE_URL=database_url:latest"
}

Write-Host "Updating Cloud Run $Service..."
$updateArgs = @(
    "run", "services", "update", $Service,
    "--project=$Project",
    "--region=$Region",
    "--image=us-east1-docker.pkg.dev/$Project/cloud-run-source-deploy/war-bot-api:latest",
    "--update-env-vars=$envFlag",
    "--remove-secrets=CLOUDSQL_INSTANCE,CLOUDSQL_DB,CLOUDSQL_USER,CLOUDSQL_PASSWORD",
    "--clear-cloudsql-instances",
    "--quiet"
)
if ($secretFlag) {
    $updateArgs += "--update-secrets=$secretFlag"
}
& gcloud @updateArgs
if ($LASTEXITCODE -ne 0) {
    throw "Cloud Run update failed (exit $LASTEXITCODE)."
}

$url = gcloud run services describe $Service --project=$Project --region=$Region --format="value(status.url)"
Write-Host "Done. Service URL: $url"
Write-Host "Smoke: gcloud run services proxy $Service --region=$Region --project=$Project"
Write-Host "Then: curl http://127.0.0.1:8080/health"
