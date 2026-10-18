"""Selección conservadora de interfaces para libtorrent 2.x.

No hace peticiones HTTP/DNS. UDP connect() determina la dirección origen que
selecciona la tabla de rutas local de Windows (no envía un datagrama).
No supone que la ruta local garantice conectividad remota, NAT ni semillas.
"""
from __future__ import annotations

from dataclasses import dataclass
import ipaddress
import socket


class RouteError(ValueError):
    pass


@dataclass(frozen=True)
class RouteSnapshot:
    ipv4: str = ""
    ipv6: str = ""
    detail: str = ""

    @property
    def ready(self) -> bool:
        return bool(self.ipv4 or self.ipv6)


def _usable_address(value: str, version: int) -> str:
    try:
        ip = ipaddress.ip_address(str(value).split('%', 1)[0])
        if ip.version != version or ip.is_unspecified or ip.is_loopback or ip.is_link_local or ip.is_multicast:
            return ""
        # No aceptar direcciones reservadas de documentación o broadcast.
        if version == 4 and (ip.is_reserved or ip == ipaddress.IPv4Address('255.255.255.255')):
            return ""
        return str(ip)
    except ValueError:
        return ""


def _probe(family: int, destination: tuple, socket_factory=socket.socket) -> str:
    sock = socket_factory(family, socket.SOCK_DGRAM)
    try:
        sock.connect(destination)  # UDP connect NO envía paquetes de red.
        address = sock.getsockname()[0]
        return _usable_address(address, 4 if family == socket.AF_INET else 6)
    finally:
        sock.close()


def detect_default_route(socket_factory=socket.socket) -> RouteSnapshot:
    """Detecta IPs origen locales para IPv4/IPv6 sin salida al exterior.

    No filtra manualmente nombres como Wi-Fi: si el sistema prioriza una VPN,
    seguirá la ruta de Windows en lugar de saltársela.
    """
    ipv4 = ipv6 = ""
    problems = []
    for family, destination, label in (
        (socket.AF_INET, ("1.1.1.1", 443), "IPv4"),
        (socket.AF_INET6, ("2606:4700:4700::1111", 443, 0, 0), "IPv6"),
    ):
        try:
            result = _probe(family, destination, socket_factory)
            if not result:
                problems.append(f"{label}: dirección de salida no utilizable")
            elif family == socket.AF_INET:
                ipv4 = result
            else:
                ipv6 = result
        except (OSError, ValueError) as exc:
            problems.append(f"{label}: {type(exc).__name__}")
    return RouteSnapshot(ipv4, ipv6, "; ".join(problems))


def interface_settings(mode: str, port: int, route: RouteSnapshot) -> dict[str, str]:
    """Genera ajustes de escucha y salida; sin modo fallback implícito.

    route: exclusivamente las IP con ruta local; compatibility: comportamiento
    anterior, a petición explícita. Sin ruta válida, se bloquea nueva red P2P
    en vez de redirigir inesperadamente a otra interfaz.
    """
    try:
        port = int(port)
    except (TypeError, ValueError, OverflowError) as exc:
        raise RouteError("Puerto inválido") from exc
    if port != 0 and not (1024 <= port <= 65535):
        raise RouteError("Puerto 0 o 1024–65535")
    if mode == "compatibility":
        return {"listen_interfaces": f"0.0.0.0:{port},[::]:{port}", "outgoing_interfaces": ""}
    if mode != "route":
        raise RouteError("Modo de red desconocido")
    listen = []
    out = []
    if route.ipv4:
        addr = _usable_address(route.ipv4, 4)
        if addr:
            listen.append(f"{addr}:{port}")
            out.append(addr)
    if route.ipv6:
        addr = _usable_address(route.ipv6, 6)
        if addr:
            listen.append(f"[{addr}]:{port}")
            out.append(addr)
    if not listen:
        return {"listen_interfaces": "", "outgoing_interfaces": "127.0.0.1"}
    return {"listen_interfaces": ",".join(listen), "outgoing_interfaces": ",".join(out)}


def readable_route(mode: str, route: RouteSnapshot) -> str:
    if mode == "compatibility":
        return "Compatibilidad: todas las interfaces (incluye virtuales)."
    if route.ready:
        items = [f"IPv4 {route.ipv4}" if route.ipv4 else "", f"IPv6 {route.ipv6}" if route.ipv6 else ""]
        return "Ruta principal: " + " · ".join(item for item in items if item)
    return "Sin ruta local detectada: conexiones nuevas detenidas; comprueba Wi-Fi y vuelve a detectar."
