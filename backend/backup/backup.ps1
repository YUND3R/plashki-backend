$ErrorActionPreference = "Stop"

param(
    [string]$OutputRoot = "C:\backups\plashki",
    [string]$DbUser = "plashki",
    [string]$DbName = "plashki",
    [string]$DbService = "db",
    [string]$ApiService = "api"
)

$timestamp = Get-Date -Format "yyyyMMdd_HHmmss"
$backupDir = Join-Path $OutputRoot $timestamp
New-Item -ItemType Directory -Force -Path $backupDir | Out-Null

Write-Host "Creating backup in: $backupDir"

$dbDumpPath = Join-Path $backupDir "db.dump"
$uploadsPath = Join-Path $backupDir "uploads.tar.gz"
$checksumsPath = Join-Path $backupDir "checksums.txt"

Write-Host "1/3 Dumping database..."
docker compose exec -T $DbService pg_dump -U $DbUser -d $DbName -Fc > $dbDumpPath

Write-Host "2/3 Archiving uploads..."
docker compose exec -T $ApiService sh -lc "tar -czf - -C /app/uploads ." > $uploadsPath

Write-Host "3/3 Writing checksums..."
"# SHA256" | Out-File -FilePath $checksumsPath -Encoding utf8
Get-FileHash $dbDumpPath -Algorithm SHA256 | ForEach-Object {
    "$($_.Hash)  db.dump" | Out-File -FilePath $checksumsPath -Append -Encoding utf8
}
Get-FileHash $uploadsPath -Algorithm SHA256 | ForEach-Object {
    "$($_.Hash)  uploads.tar.gz" | Out-File -FilePath $checksumsPath -Append -Encoding utf8
}

Write-Host "Backup complete."
Write-Host " - DB: $dbDumpPath"
Write-Host " - Uploads: $uploadsPath"
Write-Host " - Checksums: $checksumsPath"
