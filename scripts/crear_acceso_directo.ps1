$ErrorActionPreference = 'Stop'
try {
    $root = (Resolve-Path -LiteralPath (Split-Path -Parent $PSScriptRoot)).Path
    $exe = Join-Path $root 'dist\ApexTorrent\ApexTorrent.exe'
    $pythonw = Join-Path $root '.venv\Scripts\pythonw.exe'
    $main = Join-Path $root 'app\main.py'
    $icon = Join-Path $root 'app\assets\apex-torrent.ico'
    if (-not (Test-Path -LiteralPath $icon -PathType Leaf)) {
        throw 'No se encuentra el icono Apex Torrent. Reinstala el parche.'
    }
    if (Test-Path -LiteralPath $exe -PathType Leaf) {
        $target = $exe
        $args = ''
    } elseif ((Test-Path -LiteralPath $pythonw -PathType Leaf) -and (Test-Path -LiteralPath $main -PathType Leaf)) {
        $target = $pythonw
        $args = '"' + $main + '"'
    } else {
        throw 'No existe el ejecutable ni el entorno .venv. Ejecuta INSTALAR_WINDOWS.bat primero.'
    }
    $shell = New-Object -ComObject WScript.Shell
    $desktop = [string]$shell.SpecialFolders.Item('Desktop')
    if (-not $desktop -or -not (Test-Path -LiteralPath $desktop -PathType Container)) {
        throw 'No se pudo localizar el Escritorio de Windows.'
    }
    $programs = Join-Path ([Environment]::GetFolderPath('StartMenu')) 'Programs\Apex Software'
    New-Item -ItemType Directory -Path $programs -Force | Out-Null
    foreach ($path in @((Join-Path $desktop 'Apex Torrent.lnk'), (Join-Path $programs 'Apex Torrent.lnk'))) {
        $lnk = $shell.CreateShortcut($path)
        $lnk.TargetPath = $target
        $lnk.Arguments = $args
        $lnk.WorkingDirectory = $root
        $lnk.IconLocation = "$icon,0"
        $lnk.Description = 'Apex Torrent 1.3 Ultimate Edition'
        $lnk.Save()
        Write-Host "Acceso creado: $path" -ForegroundColor Green
    }
    Write-Host ''
    Write-Host 'Para anclarlo a la barra de tareas: abre Apex Torrent, clic derecho en su icono y Anclar a la barra de tareas.' -ForegroundColor Cyan
    Write-Host 'Si Windows tenia un icono antiguo anclado, desanclalo y ancla el nuevo.' -ForegroundColor Yellow
    exit 0
} catch {
    Write-Host "ERROR: $($_.Exception.Message)" -ForegroundColor Red
    exit 1
}
