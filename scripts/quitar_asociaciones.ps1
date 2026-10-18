# Solo elimina claves de Apex Torrent en HKCU; no altera preferencias de otras apps.
$ErrorActionPreference = 'Stop'
try {
    $reg = 'HKCU:\Software\RegisteredApplications'
    if (Test-Path $reg) {
        Remove-ItemProperty -Path $reg -Name 'Apex Torrent' -ErrorAction SilentlyContinue
    }
    foreach ($key in @('HKCU:\Software\ApexSoftware\ApexTorrent\Capabilities',
                       'HKCU:\Software\Classes\ApexTorrent.torrent',
                       'HKCU:\Software\Classes\ApexTorrent.magnet')) {
        if (Test-Path $key) { Remove-Item -LiteralPath $key -Recurse -Force }
    }
    Write-Host 'Registros de Apex Torrent retirados. Los datos descargados no se han modificado.' -ForegroundColor Green
} catch {
    Write-Host "ERROR: $($_.Exception.Message)" -ForegroundColor Red
    exit 1
}
