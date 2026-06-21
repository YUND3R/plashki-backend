$ErrorActionPreference = "Stop"

param(
    [Parameter(Mandatory = $true)]
    [string]$BackupDir,
    [string]$DbUser = "plashki",
    [string]$DbName = "plashki",
    [string]$DbService = "db",
    [string]$ApiService = "api"
)

$dbDumpPath = Join-Path $BackupDir "db.dump"
$uploadsPath = Join-Path $BackupDir "uploads.tar.gz"

if (!(Test-Path $dbDumpPath)) {
    throw "db.dump not found in $BackupDir"
}
if (!(Test-Path $uploadsPath)) {
    throw "uploads.tar.gz not found in $BackupDir"
}

Write-Host "Restoring from: $BackupDir"

$dbContainer = (docker compose ps -q $DbService).Trim()
$apiContainer = (docker compose ps -q $ApiService).Trim()
if ([string]::IsNullOrWhiteSpace($dbContainer)) {
    throw "DB container for service '$DbService' not found. Run docker compose up -d first."
}
if ([string]::IsNullOrWhiteSpace($apiContainer)) {
    throw "API container for service '$ApiService' not found. Run docker compose up -d first."
}

Write-Host "1/2 Restoring database..."
docker cp $dbDumpPath "$dbContainer:/tmp/db.dump"
docker compose exec -T $DbService sh -lc "dropdb -U $DbUser --if-exists $DbName && createdb -U $DbUser $DbName"
docker compose exec -T $DbService pg_restore -U $DbUser -d $DbName --clean --if-exists /tmp/db.dump
docker compose exec -T $DbService rm -f /tmp/db.dump

Write-Host "2/2 Restoring uploads..."
docker cp $uploadsPath "$apiContainer:/tmp/uploads.tar.gz"
docker compose exec -T $ApiService sh -lc "rm -rf /app/uploads/* && tar -xzf /tmp/uploads.tar.gz -C /app/uploads"
docker compose exec -T $ApiService rm -f /tmp/uploads.tar.gz

Write-Host "Restore complete."
