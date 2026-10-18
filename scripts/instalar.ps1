$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $root
Write-Host ''
Write-Host '==============================================' -ForegroundColor Cyan
Write-Host '      APEX TORRENT 1.3.1 - INSTALADOR' -ForegroundColor Cyan
Write-Host '==============================================' -ForegroundColor Cyan
Write-Host ''

# No se usa la version predeterminada si es incompatible (p. ej. 3.15).
$choices = @(
    @{ cmd='py'; prefix=@('-3.12') },
    @{ cmd='py'; prefix=@('-3.13') },
    @{ cmd='python'; prefix=@() }
)
$found = $false
$python = ''
$prefix = @()
foreach ($option in $choices) {
    if (-not (Get-Command ($option.cmd) -ErrorAction SilentlyContinue)) { continue }
    try {
        $candidate = [string]$option.cmd
        $candidatePrefix = @($option.prefix)
        $out = & $candidate @candidatePrefix -c 'import sys,struct;print(str(sys.version_info.major)+chr(46)+str(sys.version_info.minor)+chr(124)+str(struct.calcsize(chr(80))*8))' 2>$null
        if ($LASTEXITCODE -eq 0 -and $out -match '^(3\.(12|13))\|64$') {
            $python = $candidate
            $prefix = $candidatePrefix
            Write-Host "Python compatible detectado: $out ($python $($prefix -join ' '))" -ForegroundColor Green
            $found = $true
            break
        }
    } catch { continue }
}
if (-not $found) {
    Write-Host ''
    Write-Host 'ERROR: No se detecto Python 3.12/3.13 de 64 bits.' -ForegroundColor Red
    Write-Host 'Instala Python 3.12 x64 desde https://www.python.org/downloads/'
    Write-Host 'En la instalacion activa el Python Launcher (py) y vuelve a ejecutar este archivo.'
    exit 1
}

$venvPython = Join-Path $root '.venv\Scripts\python.exe'
$verificationScript = Join-Path $PSScriptRoot 'verificar_dependencias.py'

if (-not (Test-Path -LiteralPath $venvPython -PathType Leaf)) {
    Write-Host 'Creando entorno virtual .venv...' -ForegroundColor Yellow
    & $python @prefix -m venv .venv
    if ($LASTEXITCODE -ne 0) { throw 'No fue posible crear el entorno virtual.' }
}

# Llamar a un archivo Python, no a `python -c`: PowerShell 5.1 puede
# eliminar las comillas internas del codigo y provocar SyntaxError.
# Si ya esta completo (por ejemplo, tras el bug de 1.0), no reinstalar nada.
Write-Host 'Comprobando dependencias instaladas...' -ForegroundColor Yellow
& $venvPython $verificationScript
if ($LASTEXITCODE -eq 0) {
    Write-Host ''
    Write-Host 'DEPENDENCIAS VALIDAS. No es necesario reinstalar.' -ForegroundColor Green
} else {
    Write-Host 'Instalando PySide6 y libtorrent...' -ForegroundColor Yellow
    & $venvPython -m pip install --disable-pip-version-check --only-binary=:all: -r requirements.txt
    if ($LASTEXITCODE -ne 0) {
        Write-Host ''
        Write-Host 'ERROR: Faltan dependencias o Internet. Revisa el mensaje de pip.' -ForegroundColor Red
        exit 2
    }
    Write-Host 'Validando librerias despues de la instalacion...' -ForegroundColor Yellow
    & $venvPython $verificationScript
    if ($LASTEXITCODE -ne 0) { throw 'No se pudieron importar las dependencias despues de instalarlas.' }
}
Write-Host ''
Write-Host 'INSTALACION COMPLETADA.' -ForegroundColor Green
Write-Host 'Abre INICIAR_WINDOWS.bat para usar Apex Torrent.' -ForegroundColor Green
Write-Host 'Creando accesos directos de Windows...' -ForegroundColor Cyan
$shortcutScript = Join-Path $PSScriptRoot 'crear_acceso_directo.ps1'
& powershell.exe -NoProfile -ExecutionPolicy Bypass -File $shortcutScript
if ($LASTEXITCODE -ne 0) {
    Write-Host 'Aviso: la aplicacion esta instalada, pero no se pudo crear el acceso. Puedes usar CREAR_ACCESO_DIRECTO.bat.' -ForegroundColor Yellow
}
exit 0
