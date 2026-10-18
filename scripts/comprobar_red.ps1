$ErrorActionPreference = 'Continue'
Write-Host '================================================' -ForegroundColor Cyan
Write-Host ' APEX TORRENT 1.3.8 - FINAL POLISH' -ForegroundColor Cyan
Write-Host '================================================' -ForegroundColor Cyan
Write-Host 'Solo lectura: no modifica la red ni el firewall.'
Write-Host 'La ruta detectada es local; no confirma que un tracker tenga semillas.'
Write-Host ''
Write-Host '1) Adaptadores con ruta IPv4 predeterminada' -ForegroundColor Cyan
try {
    $routes = Get-NetRoute -DestinationPrefix '0.0.0.0/0' -AddressFamily IPv4 -ErrorAction Stop | Sort-Object RouteMetric
    if ($routes) {
        foreach ($route in $routes) {
            $iface = Get-NetIPInterface -InterfaceIndex $route.InterfaceIndex -AddressFamily IPv4 -ErrorAction SilentlyContinue
            $ip = Get-NetIPAddress -InterfaceIndex $route.InterfaceIndex -AddressFamily IPv4 -ErrorAction SilentlyContinue | Where-Object { $_.AddressState -eq 'Preferred' } | Select-Object -First 1 -ExpandProperty IPAddress
            Write-Host ('Indice {0} · {1} · IPv4 {2} · Gateway {3} · RouteMetric {4} · InterfaceMetric {5}' -f $route.InterfaceIndex, $iface.InterfaceAlias, $ip, $route.NextHop, $route.RouteMetric, $iface.InterfaceMetric)
        }
    } else { Write-Host 'No hay ruta IPv4 por defecto.' }
} catch { Write-Host "No se pudo consultar la ruta: $($_.Exception.Message)" }
Write-Host ''
Write-Host '2) Adaptadores IPv4 activos' -ForegroundColor Cyan
try {
    Get-NetAdapter -ErrorAction Stop | Where-Object {$_.Status -eq 'Up'} | Select-Object Name, InterfaceDescription, Status, ifIndex | Format-Table -AutoSize
} catch { Write-Host "No se pudo consultar adaptadores: $($_.Exception.Message)" }
Write-Host ''
Write-Host '3) Puerto 6881, solo como referencia historica' -ForegroundColor Cyan
try {
    $used = Get-NetTCPConnection -State Listen -ErrorAction Stop | Where-Object { $_.LocalPort -eq 6881 }
    if ($used) { $used | Select-Object LocalAddress, LocalPort, OwningProcess | Format-Table -AutoSize }
    else { Write-Host 'No se detectaron escuchas TCP en el puerto 6881.' }
} catch { Write-Host "No se pudieron leer puertos: $($_.Exception.Message)" }
Write-Host ''
Write-Host '4) Resolucion DNS de un tracker legal de referencia (Ubuntu)' -ForegroundColor Cyan
try {
    Resolve-DnsName torrent.ubuntu.com -ErrorAction Stop | Where-Object {$_.Type -eq 'A' -or $_.Type -eq 'AAAA'} | Select-Object -First 4 Name, Type, IPAddress | Format-Table -AutoSize
} catch { Write-Host "Consulta DNS fallida: $($_.Exception.Message)" }
Write-Host ''
Write-Host 'No es necesario modificar el firewall para realizar este diagnostico.'
