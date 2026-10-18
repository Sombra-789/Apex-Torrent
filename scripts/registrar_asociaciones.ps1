# Registra Apex Torrent como CANDIDATO de aplicación predeterminada, sin cambiar UserChoice.
# Nunca escribe en HKLM y permite revertir con quitar_asociaciones.ps1.
$ErrorActionPreference = 'Stop'
try {
    $root = (Resolve-Path -LiteralPath (Split-Path -Parent $PSScriptRoot)).Path
    $exe = Join-Path $root 'dist\ApexTorrent\ApexTorrent.exe'
    $pythonw = Join-Path $root '.venv\Scripts\pythonw.exe'
    $main = Join-Path $root 'app\main.py'
    $ico = Join-Path $root 'app\assets\apex-torrent.ico'
    if (Test-Path -LiteralPath $exe -PathType Leaf) {
        $command = '"' + $exe + '" "%1"'
    } elseif ((Test-Path -LiteralPath $pythonw -PathType Leaf) -and (Test-Path -LiteralPath $main -PathType Leaf)) {
        $command = '"' + $pythonw + '" "' + $main + '" "%1"'
    } else { throw 'Falta el EXE o .venv. Instala Apex Torrent antes de registrar.' }

    $classes = 'HKCU:\Software\Classes'
    $torrent = Join-Path $classes 'ApexTorrent.torrent'
    $magnet = Join-Path $classes 'ApexTorrent.magnet'
    foreach ($key in @($torrent, $magnet)) {
        New-Item -Path $key -Force | Out-Null
        Set-Item -Path $key -Value 'Apex Torrent 1.3'
        $icoKey = New-Item -Path (Join-Path $key 'DefaultIcon') -Force
        Set-Item -Path $icoKey.PSPath -Value ('"' + $ico + '"')
        $cmdKey = New-Item -Path (Join-Path $key 'shell\open\command') -Force
        Set-Item -Path $cmdKey.PSPath -Value $command
    }
    # ProgID de URL. La asociación magnet queda disponible en Default Apps.
    New-ItemProperty -Path $magnet -Name 'URL Protocol' -Value '' -PropertyType String -Force | Out-Null

    $caps = 'HKCU:\Software\ApexSoftware\ApexTorrent\Capabilities'
    New-Item -Path $caps -Force | Out-Null
    New-ItemProperty -Path $caps -Name ApplicationName -Value 'Apex Torrent' -PropertyType String -Force | Out-Null
    New-ItemProperty -Path $caps -Name ApplicationDescription -Value 'Cliente BitTorrent de escritorio' -PropertyType String -Force | Out-Null
    $files = New-Item -Path (Join-Path $caps 'FileAssociations') -Force
    New-ItemProperty -Path $files.PSPath -Name '.torrent' -Value 'ApexTorrent.torrent' -PropertyType String -Force | Out-Null
    $urls = New-Item -Path (Join-Path $caps 'URLAssociations') -Force
    New-ItemProperty -Path $urls.PSPath -Name 'magnet' -Value 'ApexTorrent.magnet' -PropertyType String -Force | Out-Null
    $registered = 'HKCU:\Software\RegisteredApplications'
    New-Item -Path $registered -Force | Out-Null
    New-ItemProperty -Path $registered -Name 'Apex Torrent' -Value 'Software\ApexSoftware\ApexTorrent\Capabilities' -PropertyType String -Force | Out-Null
    Write-Host 'Apex Torrent esta registrado como opcion para .torrent y magnet (sin cambiar programas predeterminados).' -ForegroundColor Green
    Write-Host 'Si deseas usarlo por defecto: Configuracion de Windows -> Aplicaciones -> Aplicaciones predeterminadas -> Apex Torrent.' -ForegroundColor Cyan
    Write-Host 'Para revertir: QUITAR_ASOCIACIONES_WINDOWS.bat' -ForegroundColor Yellow
} catch {
    Write-Host "ERROR: $($_.Exception.Message)" -ForegroundColor Red
    exit 1
}
