"""Motor P2P de Apex Torrent mediante libtorrent 2.0.

Las llamadas al motor se hacen desde el hilo Qt. Libtorrent utiliza sus propios
hilos internos para tráfico/red/disco. Nunca se modifica el disco de descargas
manualmente al eliminar un torrent: el motor conoce los archivos legítimos.
"""
from __future__ import annotations
import shutil
import logging
from datetime import datetime
import time
import uuid
from pathlib import Path
from urllib.parse import parse_qs, urlsplit
import libtorrent as lt
from state import Store, VERSION
from performance import profile_settings
from cyber_theme import THEMES
from scheduler import schedule_allowed
from smart_engine import effective_upload_limit_kib, smart_upload_report
from diagnosis import diagnose
from peer_intelligence import human_client, human_endpoint, peer_availability
from network_routes import detect_default_route, interface_settings, readable_route, RouteError


class EngineError(Exception):
    pass


def validate_magnet(uri: str) -> str:
    uri = uri.strip()
    parts = urlsplit(uri)
    if parts.scheme.lower() != "magnet":
        raise EngineError("Introduce un enlace magnet válido (magnet:?...).")
    xts = parse_qs(parts.query).get("xt", [])
    if not any(v.startswith("urn:btih:") or v.startswith("urn:btmh:") for v in xts):
        raise EngineError("Al enlace magnet le falta una huella BitTorrent válida (xt).")
    return uri


def explain_error(message: str) -> str:
    """Simple, conservative guidance. Never assume the underlying cause."""
    value = (message or "").casefold()
    if any(w in value for w in (
        "no space left", "not enough space", "disk full", "espacio insuficiente",
        "no hay espacio", "space on the disk", "there is not enough space"
    )):
        return "Posible falta de espacio. Revisa los GiB disponibles en la unidad de destino."
    if any(w in value for w in (
        "permission denied", "access denied", "access is denied", "acceso denegado",
        "not permitted", "operation not permitted"
    )):
        return "Posibles permisos insuficientes. Prueba una carpeta dentro de Descargas."
    if any(w in value for w in (
        "path not found", "no such file", "cannot find the path", "ruta especificada",
        "system cannot find", "file not found"
    )):
        return "Posible ruta inexistente. Comprueba la carpeta de destino."
    if any(w in value for w in (
        "filename or extension is too long", "path too long", "name too long"
    )):
        return "La ruta podría ser demasiado larga. Prueba una carpeta con un nombre corto."
    if any(w in value for w in (
        "being used by another process", "sharing violation", "used by another process"
    )):
        return "Un archivo podría estar en uso por otro programa. Cierra aplicaciones relacionadas."
    if any(w in value for w in ("i/o error", "input/output error", "error de e/s")):
        return "Posible problema de lectura o escritura. Comprueba la unidad de destino."
    return "Revisa el mensaje técnico y la ruta de destino antes de intentar otra descarga."


def _read_error_field(obj, key: str):
    """Lee propiedades y métodos del binding, sin convertir errores a punteros SWIG."""
    try:
        member = getattr(obj, key)
        return (member() if callable(member) else member), ""
    except Exception as exc:
        return None, f"{key}: {type(exc).__name__}: {exc}"


def describe_libtorrent_error(errc) -> dict:
    """Extrae mensaje, categoría y código aun si el binding no ofrece message().

    No confunde la dirección de memoria de error_code con un mensaje legible.
    """
    result = {"error": "", "error_code": None, "error_category": "",
              "error_exception": ""}
    if errc is None:
        return result
    issues = []
    code, issue = _read_error_field(errc, "value")
    if issue:
        issues.append(issue)
    if code is not None:
        try:
            result["error_code"] = int(code)
        except (TypeError, ValueError, OverflowError):
            issues.append(f"value: no se pudo convertir el valor {type(code).__name__}")
    # El código 0 significa éxito aunque el wrapper Python sea truthy.
    if result["error_code"] == 0:
        return result
    try:
        if not bool(errc) and result["error_code"] is None:
            return result
    except Exception as exc:
        issues.append(f"bool: {type(exc).__name__}: {exc}")
    message, issue = _read_error_field(errc, "message")
    if issue:
        issues.append(issue)
    category, issue = _read_error_field(errc, "category")
    if issue:
        issues.append(issue)
    if category is not None:
        name, issue = _read_error_field(category, "name")
        if issue:
            issues.append(issue)
        if isinstance(name, str):
            result["error_category"] = name
        # Recuperación: error_category.message(code) puede funcionar si
        # error_code.message() falla por una incompatibilidad del binding.
        if not isinstance(message, str) or not message.strip() or message.startswith("<libtorrent."):
            if result["error_code"] is not None:
                try:
                    category_message = getattr(category, "message")
                    message = (category_message(result["error_code"])
                               if callable(category_message) else category_message)
                except Exception as exc:
                    issues.append(f"category.message: {type(exc).__name__}: {exc}")
    if isinstance(message, str) and message.strip() and not message.startswith("<libtorrent."):
        if message.strip().casefold() not in ("success", "no error", "ningún error"):
            result["error"] = message.strip()
    if not result["error"]:
        result["error"] = "Error de libtorrent: mensaje no disponible en este binding"
    result["error_exception"] = "; ".join(issues)
    return result


def describe_error_file(status, handle) -> str:
    """Obtiene el archivo/área asociado, si libtorrent lo declara."""
    try:
        raw = getattr(status, "error_file", None)
        if raw is None:
            return ""
        file_index = int(raw)
        special = {-1: "", -3: "Contexto SSL", -4: "Metadatos",
                   -5: "Excepción interna", -6: "Archivo de piezas parciales"}
        if file_index in special:
            return special[file_index]
        if file_index < 0:
            return f"Área especial ({file_index})"
        if handle.has_metadata():
            files = handle.torrent_file().files()
            if file_index < files.num_files():
                return files.file_path(file_index)
        return f"Índice de archivo {file_index}"
    except Exception:
        return ""


def _alert_mask():
    """Incluye diagnóstico P2P cuando el binding expone las categorías.

    No modifica la configuración si el binding usa otros nombres; es más
    seguro que pasar una máscara arbitraria y producir miles de alertas.
    """
    try:
        flags = lt.alert.category_t
    except AttributeError:
        return None
    names = {
        "error": ("error_notification", "error"),
        "tracker": ("tracker_notification", "tracker"),
        "dht": ("dht_notification", "dht"),
        "status": ("status_notification", "status"),
    }
    mask = 0
    for options in names.values():
        for name in options:
            part = getattr(flags, name, None)
            if part is not None:
                try:
                    mask |= int(part)
                    break
                except (ValueError, TypeError):
                    pass
    return mask or None


def _str_field(obj, key: str, fallback: str = "") -> str:
    value, _ = _read_error_field(obj, key)
    return value.strip() if isinstance(value, str) else fallback


class TorrentEngine:
    def __init__(self, store: Store):
        self.store = store
        self.settings = store.load_settings()
        self.records: dict[str, dict] = {}
        self.handles: dict[str, object] = {}
        self.load_errors: list[str] = []
        self._resume_pending: set[str] = set()
        self._last_errors: dict[str, str] = {}
        self._error_alerts: dict[str, str] = {}
        self._tracker_health: dict[str, dict[str, dict]] = {}
        self._dht_events: dict[str, str] = {}
        self._network_events: list[str] = []
        self._idle_started: dict[str, float] = {}
        self._announce_times: dict[str, float] = {}
        self._route = detect_default_route()
        self._route_updated_at = time.monotonic()
        self.session = lt.session(self._session_settings())
        for rec in self.store.load_records():
            rid = str(rec["id"])
            if rid in self.records:
                continue
            self.records[rid] = rec
            try:
                self.handles[rid] = self._restore(rec)
                if (not self.settings.get("auto_resume", True) or rec.get("paused", False)
                        or rec.get("schedule_paused", False)):
                    self.handles[rid].pause()
                else:
                    self.handles[rid].resume()
            except Exception as exc:
                self.load_errors.append(f"{rec.get('name', 'Torrent')}: {exc}")
        self.persist()
        self.apply_schedule()

    @staticmethod
    def _listen_interfaces(port_value) -> str:
        """Binding para todas las interfaces, evitando depender de 6881.

        Puerto 0 significa asignación automática por el sistema operativo.
        No significa abrir puertos del firewall ni cambiar el router.
        """
        try:
            port = int(port_value)
        except (TypeError, ValueError, OverflowError) as exc:
            raise EngineError("El puerto de escucha debe ser un número.") from exc
        if port != 0 and not (1024 <= port <= 65535):
            raise EngineError("Usa puerto 0 (automático) o un puerto entre 1024 y 65535.")
        return f"0.0.0.0:{port},[::]:{port}"

    def _session_settings(self) -> dict:
        s = self.settings
        config = {
            "enable_dht": bool(s.get("dht", True)),
            "enable_lsd": True,
            "enable_upnp": bool(s.get("upnp", True)),
            "enable_natpmp": bool(s.get("upnp", True)),
            "download_rate_limit": int(s.get("download_limit_kib", 0)) * 1024,
            "upload_rate_limit": effective_upload_limit_kib(s) * 1024,
            "connections_limit": int(s.get("connections_limit", 200)),
            "active_downloads": int(s.get("active_downloads", 4)),
            "active_seeds": int(s.get("active_seeds", 6)),
            "active_limit": max(10, int(s.get("active_downloads", 4)) + int(s.get("active_seeds", 6))),
            # 0 permite a Windows escoger puertos disponibles. La v1.0.4
            # escuchaba implícitamente en 6881 y Windows negó ese puerto;
            # la única escucha resultante fue IPv6 loopback ::1.
            **interface_settings(s.get("network_mode", "route"), s.get("listen_port", 0), self._route),
            "user_agent": "ApexTorrent/1.4.0-alpha.1 libtorrent",
        }
        mask = _alert_mask()
        if mask is not None:
            config["alert_mask"] = mask
        return config

    def _resume_path(self, rid: str) -> Path:
        return self.store.base / "resume" / (rid + ".fastresume")

    def _prepare_params(self, rec: dict):
        resume = self._resume_path(str(rec["id"]))
        atp = None
        if resume.is_file():
            try:
                atp = lt.read_resume_data(resume.read_bytes())
            except Exception:
                atp = None  # Revisión normal de hashes si el resume está dañado.
        if atp is None:
            if rec["kind"] == "magnet":
                atp = lt.parse_magnet_uri(validate_magnet(rec["source"]))
            elif rec["kind"] == "torrent":
                ti = lt.torrent_info(rec["source"])
                atp = lt.add_torrent_params()
                atp.ti = ti
            else:
                raise EngineError("Tipo de torrent desconocido.")
        if rec["kind"] == "torrent":
            # El archivo .torrent guardado se verifica en cada inicio.
            atp.ti = lt.torrent_info(rec["source"])
        # Nunca confiar la ruta del archivo descargado a un resume externo.
        atp.save_path = str(Path(rec["save_path"]).expanduser().resolve())
        return atp

    def _restore(self, rec: dict):
        save = Path(rec["save_path"])
        save.mkdir(parents=True, exist_ok=True)
        handle = self.session.add_torrent(self._prepare_params(rec))
        # Límites personalizados guardados con la biblioteca. La API admite 0 = ilimitado.
        try:
            self._apply_torrent_limits(handle, rec)
        except Exception as exc:
            logging.warning("No se pudieron restaurar límites individuales: %s", exc)
        return handle

    def persist(self):
        self.store.save_records(self.records)

    def _torrent_key(self, handle) -> str:
        """Huella estable, no una dirección de memoria Python."""
        return self._hashes_key(handle.info_hashes())

    def _hashes_key(self, hashes) -> str:
        parts = []
        for version, size in (("v1", 20), ("v2", 32)):
            has = getattr(hashes, "has_" + version, None)
            try:
                available = has() if callable(has) else False
            except Exception:
                available = False
            if available:
                value = getattr(hashes, version, None)
                result = self._hash_hex(value, size)
                if result:
                    parts.append(f"{version}: {result}")
        if parts:
            return " · ".join(parts)
        as_text = str(hashes)
        return as_text if "object at 0x" not in as_text else "No disponible en este binding"

    @staticmethod
    def _hash_hex(value, size: int) -> str:
        if value is None:
            return ""
        for method in ("to_bytes", "to_string"):
            fn = getattr(value, method, None)
            if callable(fn):
                try:
                    data = fn()
                    if isinstance(data, (bytes, bytearray)) and len(data) == size:
                        return bytes(data).hex()
                    if isinstance(data, str) and len(data) == size * 2 and all(c in '0123456789abcdefABCDEF' for c in data):
                        return data.lower()
                except Exception:
                    pass
        try:
            data = bytes(value)
            if len(data) == size:
                return data.hex()
        except Exception:
            pass
        raw = str(value)
        if len(raw) == size * 2 and all(c in '0123456789abcdefABCDEF' for c in raw):
            return raw.lower()
        return ""

    def _assert_not_duplicate(self, params) -> None:
        target = getattr(params, "info_hashes", None)
        if getattr(params, "ti", None) is not None:
            target = params.ti.info_hashes()
        if target is None:
            return
        key = self._hashes_key(target)
        for h in self.handles.values():
            if not h.is_valid():
                continue
            existing = h.info_hashes()
            # Los wrappers info_hash_t implementan comparación de hashes.
            # Respaldamos con una clave hexadecimal para bindings distintos.
            try:
                equivalent = bool(existing == target)
            except Exception:
                equivalent = False
            existing_key = self._hashes_key(existing)
            if equivalent or (key != "No disponible en este binding" and key == existing_key):
                raise EngineError("Este torrent ya está en la biblioteca.")

    def add_magnet(self, uri: str, save_path: str | None = None) -> str:
        uri = validate_magnet(uri)
        params = lt.parse_magnet_uri(uri)
        self._assert_not_duplicate(params)
        return self._new("magnet", uri, save_path)

    def add_torrent_file(self, filename: str, save_path: str | None = None) -> str:
        source = Path(filename).expanduser().resolve()
        if source.suffix.lower() != ".torrent" or not source.is_file():
            raise EngineError("Selecciona un archivo .torrent existente.")
        ti = lt.torrent_info(str(source))  # Fallar antes de copiar un archivo no válido.
        atp = lt.add_torrent_params()
        atp.ti = ti
        self._assert_not_duplicate(atp)
        rid = uuid.uuid4().hex
        dest = self.store.base / "torrents" / f"{rid}.torrent"
        shutil.copyfile(source, dest)
        try:
            return self._new("torrent", str(dest), save_path, rid=rid)
        except Exception:
            dest.unlink(missing_ok=True)
            raise

    def _new(self, kind: str, source: str, save_path: str | None, rid: str | None = None) -> str:
        rid = rid or uuid.uuid4().hex
        download_path = str(Path(save_path or self.settings["download_dir"]).expanduser().resolve())
        rec = {
            "id": rid, "kind": kind, "source": source, "save_path": download_path,
            "paused": False, "schedule_paused": False, "name": "Obteniendo metadatos..." if kind == "magnet" else Path(source).stem,
            "created": int(time.time()),
        }
        handle = self._restore(rec)
        self.records[rid] = rec
        self.handles[rid] = handle
        self.persist()
        self.apply_schedule()
        return rid

    def pause(self, rid: str):
        self.handles[rid].pause()
        self.records[rid]["paused"] = True
        self.persist()
        self.request_resume(rid)

    def resume(self, rid: str):
        if not schedule_allowed(self.settings):
            raise EngineError("Fuera del horario programado. Desactiva el planificador o espera la siguiente ventana.")
        self.handles[rid].resume()
        self.records[rid]["schedule_paused"] = False
        self.records[rid]["paused"] = False
        self.persist()
        self.request_resume(rid)

    def apply_schedule(self, now=None) -> int:
        """Pausa solo descargas activas fuera de horario, no comparte menos ni
        revierte las pausas manuales. Reversible aun tras reiniciar Apex.
        """
        allowed = schedule_allowed(self.settings, now)
        modified = 0
        for rid, rec in self.records.items():
            handle = self.handles.get(rid)
            if handle is None or not handle.is_valid():
                continue
            if allowed:
                if rec.get("schedule_paused"):
                    if not rec.get("paused", False) and self.settings.get("auto_resume", True):
                        handle.resume()
                    rec["schedule_paused"] = False
                    modified += 1
            elif not rec.get("paused", False) and not rec.get("schedule_paused", False):
                try:
                    st = handle.status()
                    if bool(getattr(st, "is_seeding", False)) or float(getattr(st, "progress", 0)) >= 1.0:
                        continue
                except Exception:
                    continue  # No pausar sin conocer el estado.
                handle.pause()
                rec["schedule_paused"] = True
                modified += 1
        if modified:
            self.persist()
        return modified

    def recheck(self, rid: str):
        self.handles[rid].force_recheck()

    def remove(self, rid: str, delete_data: bool = False):
        rec = self.records[rid]
        h = self.handles.get(rid)
        if h and h.is_valid():
            if delete_data:
                opts = getattr(self.session, "delete_files", None)
                if opts is None:
                    opts = getattr(getattr(lt, "session", None), "delete_files", None)
                if opts is None:
                    opts = getattr(getattr(lt, "options_t", None), "delete_files", None)
                if opts is None:
                    raise EngineError("El motor no admite eliminación segura de archivos.")
                self.session.remove_torrent(h, opts)
            else:
                self.session.remove_torrent(h)
        del self.records[rid]
        self.handles.pop(rid, None)
        self._resume_pending.discard(rid)
        self._last_errors.pop(rid, None)
        self._error_alerts.pop(rid, None)
        self._tracker_health.pop(rid, None)
        self._idle_started.pop(rid, None)
        self._announce_times.pop(rid, None)
        self._dht_events.pop(rid, None)
        self._resume_path(rid).unlink(missing_ok=True)
        if rec["kind"] == "torrent":
            # Nunca borrar un archivo ajeno a nuestro almacén.
            known = self.store.base / "torrents" / (rid + ".torrent")
            known.unlink(missing_ok=True)
        self.persist()

    @staticmethod
    def _apply_torrent_limits(handle, rec: dict):
        """Solo modifica el torrent indicado; no altera los límites globales."""
        mapping = (
            ("download_limit_kib", "set_download_limit"),
            ("upload_limit_kib", "set_upload_limit"),
        )
        for key, method in mapping:
            if key in rec:
                value = max(0, int(rec[key])) * 1024
                getattr(handle, method)(value)

    def set_torrent_limits(self, rid: str, down_kib: int, up_kib: int) -> None:
        if rid not in self.handles or rid not in self.records:
            raise EngineError("Selecciona un torrent válido.")
        if min(down_kib, up_kib) < 0:
            raise EngineError("Los límites individuales no pueden ser negativos.")
        handle = self.handles[rid]
        # La validación sucede antes de persistir: no guardamos algo que el motor rechazó.
        new_record = {**self.records[rid], "download_limit_kib": int(down_kib),
                      "upload_limit_kib": int(up_kib)}
        try:
            self._apply_torrent_limits(handle, new_record)
        except Exception as exc:
            raise EngineError(f"libtorrent no pudo establecer estos límites: {exc}") from exc
        self.records[rid] = new_record
        self.persist()

    def apply_profile(self, name: str) -> dict:
        """Los perfiles son topes/conexiones, no aceleradores mágicos."""
        try:
            values = profile_settings(name)
        except ValueError as exc:
            raise EngineError(str(exc)) from exc
        self.apply_settings(values)
        return values

    def peer_details(self, rid: str) -> list[dict]:
        """Datos visibles de pares; consulta opcional, sin romper el render principal."""
        h = self.handles.get(rid)
        if not h or not h.is_valid():
            return []
        result = []
        for peer in h.get_peer_info()[:120]:
            endpoint = human_endpoint(getattr(peer, "ip", None))
            result.append({
                "endpoint": endpoint,
                "client": human_client(getattr(peer, "client", None)),
                "down": max(0, int(getattr(peer, "down_speed", 0))),
                "up": max(0, int(getattr(peer, "up_speed", 0))),
                "progress": max(0.0, min(1.0, float(getattr(peer, "progress", 0.0)))),
                "availability": peer_availability(getattr(peer, "progress", 0.0)),
            })
        return result

    def refresh_network_route(self, force: bool = False) -> bool:
        """Actualiza las IP elegidas al cambiar Wi-Fi/red. Nunca pasa a modo abierto.

        Invocación normal limitada a 30 s. Si la ruta se pierde, deshabilita
        sockets P2P nuevos para evitar continuar en un adaptador no deseado.
        """
        if self.settings.get("network_mode", "route") != "route":
            return False
        if not force and time.monotonic() - self._route_updated_at < 30:
            return False
        self._route_updated_at = time.monotonic()
        detected = detect_default_route()
        if detected == self._route:
            return False
        previous = self._route
        new_network = interface_settings("route", self.settings.get("listen_port", 0), detected)
        try:
            self.session.apply_settings(new_network)
            self._route = detected
            self._network_events.append("Ruta local actualizada: " + readable_route("route", detected))
            self._network_events = self._network_events[-12:]
            return True
        except Exception:
            self._route = previous
            raise

    def network_overview(self) -> dict:
        """Devuelve solo información observada del motor; nunca adivina NAT ni IP pública."""
        listening = [entry for entry in self._network_events if "listen_succeeded_alert:" in entry]
        failures = [entry for entry in self._network_events if "listen_failed_alert:" in entry]
        return {
            "listen": listening[-8:], "failures": failures[-8:],
            "dht_enabled": bool(self.settings.get("dht", True)),
            "upnp_enabled": bool(self.settings.get("upnp", True)),
            "connections_limit": int(self.settings.get("connections_limit", 200)),
            "requested_interfaces": interface_settings(self.settings.get("network_mode", "route"), self.settings.get("listen_port", 0), self._route)["listen_interfaces"] or "(red detenida: sin ruta)",
            "outgoing_interfaces": interface_settings(self.settings.get("network_mode", "route"), self.settings.get("listen_port", 0), self._route)["outgoing_interfaces"] or "(decide Windows)",
            "network_mode": self.settings.get("network_mode", "route"),
            "route_info": readable_route(self.settings.get("network_mode", "route"), self._route),
            "profile": self.settings.get("profile", "Equilibrado"),
            "smart": smart_upload_report(self.settings),
        }

    def apply_settings(self, new_settings: dict):
        """Valida antes de persistir y evita reajustar sockets por un cambio visual.

        Libtorrent aplica parámetros en su propio hilo; los cambios de escucha
        pueden tardar. Nunca modifica la configuración de Windows.
        """
        merged = dict(self.settings)
        merged.update(new_settings)
        for key in ("download_limit_kib", "upload_limit_kib"):
            value = int(merged[key])
            if not 0 <= value <= 1000000:
                raise EngineError("Límite de velocidad fuera de rango.")
            merged[key] = value
        connections = int(merged["connections_limit"])
        if not 10 <= connections <= 2000:
            raise EngineError("El máximo de conexiones debe estar entre 10 y 2000.")
        merged["connections_limit"] = connections
        for key in ("active_downloads", "active_seeds"):
            value = int(merged.get(key, 4 if key == "active_downloads" else 6))
            if not 1 <= value <= 50:
                raise EngineError("Los torrents activos deben estar entre 1 y 50.")
            merged[key] = value
        if merged.get("accent_theme", "Azul") not in THEMES:
            raise EngineError("Tema de apariencia desconocido.")
        try:
            merged["upload_capacity_mbps"] = int(merged.get("upload_capacity_mbps", 0))
            merged["smart_upload_percent"] = int(merged.get("smart_upload_percent", 80))
            merged["smart_engine_enabled"] = bool(merged.get("smart_engine_enabled", False))
            if not 0 <= merged["upload_capacity_mbps"] <= 1000:
                raise ValueError("La subida medida debe estar entre 0 y 1000 Mbps.")
            if not 50 <= merged["smart_upload_percent"] <= 90:
                raise ValueError("El objetivo de subida debe estar entre 50 y 90 %.")
            effective_upload_limit_kib(merged)
        except (TypeError, ValueError, OverflowError) as exc:
            raise EngineError(f"Parámetros de Smart Engine inválidos: {exc}") from exc
        for key in ("schedule_start_hour", "schedule_end_hour"):
            try:
                value = int(merged.get(key, 0))
            except (ValueError, TypeError, OverflowError) as exc:
                raise EngineError("Horas del planificador inválidas.") from exc
            if value < 0 or value > 23:
                raise EngineError("Horario válido: de 00 a 23 horas.")
            merged[key] = value
        merged["schedule_enabled"] = bool(merged.get("schedule_enabled", False))
        self._listen_interfaces(merged.get("listen_port", 0))
        if merged.get("network_mode", "route") not in ("route", "compatibility"):
            raise EngineError("Modo de red inválido.")
        interface_settings(merged.get("network_mode", "route"), merged.get("listen_port", 0), self._route)
        runtime_keys = {"download_limit_kib", "upload_limit_kib", "connections_limit",
                        "active_downloads", "active_seeds", "listen_port", "network_mode", "dht", "upnp",
                        "smart_engine_enabled", "upload_capacity_mbps", "smart_upload_percent"}
        changed_runtime = any(merged[k] != self.settings.get(k) for k in runtime_keys)
        previous = self.settings
        previous_route = self._route
        try:
            if merged.get("network_mode", "route") == "route" and (
                    merged.get("network_mode") != previous.get("network_mode")
                    or merged.get("listen_port") != previous.get("listen_port")):
                self._route = detect_default_route()
                self._route_updated_at = time.monotonic()
            self.settings = merged
            if changed_runtime:
                self.session.apply_settings(self._session_settings())
            self.store.save_json("settings.json", merged)
            self.apply_schedule()
        except Exception:
            self.settings = previous
            self._route = previous_route
            raise

    def request_resume(self, rid: str):
        h = self.handles.get(rid)
        if h and h.is_valid() and rid not in self._resume_pending:
            try:
                h.save_resume_data()
                self._resume_pending.add(rid)
            except Exception:
                pass

    def save_all_resume(self):
        for rid in list(self.handles):
            self.request_resume(rid)

    def _rid_for_alert(self, alert):
        try:
            target = alert.handle
            return next((rid for rid, h in self.handles.items() if h == target), None)
        except (AttributeError, RuntimeError):
            return None

    def process_alerts(self):
        for alert in self.session.pop_alerts():
            kind = type(alert).__name__
            if kind in ("save_resume_data_alert", "save_resume_data_failed_alert"):
                rid = self._rid_for_alert(alert)
                if rid:
                    self._resume_pending.discard(rid)
                    if kind == "save_resume_data_alert":
                        try:
                            data = bytes(lt.write_resume_data_buf(alert.params))
                            target = self._resume_path(rid)
                            tmp = target.with_suffix(".tmp")
                            tmp.write_bytes(data)
                            tmp.replace(target)
                        except Exception as exc:
                            self.load_errors.append(f"No se guardó el estado de {rid[:7]}: {exc}")
            elif kind == "metadata_received_alert":
                rid = self._rid_for_alert(alert)
                if rid:
                    self.request_resume(rid)
            elif kind in ("torrent_error_alert", "file_error_alert", "metadata_failed_alert",
                          "storage_moved_failed_alert"):
                rid = self._rid_for_alert(alert)
                if rid:
                    message = _str_field(alert, "message")
                    if message:
                        self._error_alerts[rid] = message
                        logging.error("Alerta libtorrent %s: %s", rid[:8], message)
            elif kind in ("tracker_error_alert", "tracker_reply_alert", "tracker_warning_alert",
                          "tracker_announce_alert", "dht_reply_alert"):
                rid = self._rid_for_alert(alert)
                if rid:
                    message = _str_field(alert, "message")
                    if kind == "dht_reply_alert":
                        count = getattr(alert, "num_peers", None)
                        self._dht_events[rid] = (f"DHT respondió: {count} pares" if isinstance(count, int)
                                                 else message or "Respuesta DHT recibida")
                    else:
                        url = _str_field(alert, "url", "(tracker sin dirección)")
                        status = {
                            "tracker_error_alert": "Error",
                            "tracker_reply_alert": "Respondió",
                            "tracker_warning_alert": "Advertencia",
                            "tracker_announce_alert": "Anunciando",
                        }[kind]
                        if kind == "tracker_reply_alert":
                            count = getattr(alert, "num_peers", None)
                            if isinstance(count, int):
                                message = f"Anuncio correcto · {count} pares anunciados"
                        elif kind == "tracker_error_alert":
                            why = _str_field(alert, "failure_reason")
                            if why:
                                message = (message + " · " + why).strip(" ·")
                        # Una lista no confiable puede contener miles de trackers:
                        # acotamos las estadísticas en memoria sin tocar el motor.
                        bucket = self._tracker_health.setdefault(rid, {})
                        if len(bucket) >= 512 and url not in bucket:
                            continue
                        bucket[url] = {
                            "state": status, "message": message,
                            "time": datetime.now().strftime("%H:%M:%S"),
                        }
            elif kind in ("listen_failed_alert", "listen_succeeded_alert", "dht_bootstrap_alert"):
                line = f"{datetime.now().strftime('%H:%M:%S')} · {kind}: {_str_field(alert, 'message')}"
                self._network_events.append(line)
                self._network_events = self._network_events[-12:]

    def rows(self) -> list[dict]:
        items = []
        changed = False
        for rid, rec in self.records.items():
            h = self.handles.get(rid)
            if not h or not h.is_valid():
                items.append({"id": rid, "name": rec.get("name", "Torrent"),
                              "size": 0, "done": 0, "progress": 0.0,
                              "state": "No disponible", "down": 0, "up": 0,
                              "peers": 0, "seeds": 0, "eta": -1, "ratio": 0.0,
                              "paused": True, "error": "No se pudo recuperar. Revisa el origen.",
                              "error_hint": "Prueba a agregar el torrent nuevamente.",
                              "save_path": rec.get("save_path", "")})
                continue
            try:
                st = h.status()
                has_metadata = h.has_metadata()
                name = st.name or rec.get("name", "Torrent")
                if name and name != rec.get("name"):
                    rec["name"] = name
                    changed = True
                size = int(st.total_wanted)
                done = int(st.total_wanted_done)
                rate = max(0, int(st.download_rate))
                raw_payload = getattr(st, "download_payload_rate", None)
                payload_rate = max(0, int(raw_payload)) if raw_payload is not None else None
                progress = max(0.0, min(1.0, float(st.progress)))
                if rec.get("paused") or (not self.settings.get("auto_resume", True) and st.paused):
                    state = "Pausado"
                elif rec.get("schedule_paused", False):
                    state = "Fuera de horario"
                elif st.is_seeding:
                    state = "Compartiendo"
                elif not has_metadata:
                    state = "Metadatos"
                elif progress >= 1.0:
                    state = "Completado"
                elif st.state == getattr(lt.torrent_status, "checking_files", None):
                    state = "Verificando"
                elif st.state == getattr(lt.torrent_status, "checking_resume_data", None):
                    state = "Reanudando"
                elif payload_rate is not None and payload_rate > 0:
                    state = "Descargando"
                elif payload_rate == 0 and rate > 0:
                    state = "Conectando" if int(st.num_peers) else "Buscando fuentes"
                elif rate == 0:
                    state = "Esperando pares"
                else:
                    state = "Descargando"  # binding anterior sin medición de payload
                error_detail = describe_libtorrent_error(getattr(st, "errc", None))
                error = error_detail["error"]
                if error.startswith("Error de libtorrent: mensaje no disponible"):
                    error = self._error_alerts.get(rid, "") or error
                if error:
                    state = "Error"
                else:
                    self._error_alerts.pop(rid, None)
                debug_signature = (error, error_detail["error_code"],
                                   error_detail["error_category"],
                                   error_detail["error_exception"])
                if error and self._last_errors.get(rid) != repr(debug_signature):
                    logging.error("Torrent %s (%s): %s", rid[:8], name, debug_signature)
                    self._last_errors[rid] = repr(debug_signature)
                elif not error:
                    self._last_errors.pop(rid, None)
                now = time.monotonic()
                if (rate > 0 or rec.get("paused") or rec.get("schedule_paused")
                        or progress >= 1.0 or state == "Error"):
                    self._idle_started[rid] = now
                idle_seconds = max(0, int(now - self._idle_started.setdefault(rid, now)))
                items.append({
                    "id": rid, "name": name, "size": size, "done": done, "idle_seconds": idle_seconds,
                    "progress": progress, "state": state,
                    "down": rate, "payload_down": payload_rate,
                    "up": max(0, int(st.upload_rate)),
                    "peers": int(st.num_peers), "seeds": int(getattr(st, "num_seeds", 0)),
                    "eta": int((size - done) / (payload_rate if payload_rate is not None else rate))
                    if (payload_rate if payload_rate is not None else rate) > 0 and size > done else -1,
                    "ratio": float(st.all_time_upload) / max(1, float(st.all_time_download)),
                    "paused": bool(rec.get("paused", False) or rec.get("schedule_paused", False)), "error": error,
                    "error_hint": explain_error(error) if error else "",
                    "error_code": error_detail["error_code"],
                    "error_category": error_detail["error_category"],
                    "error_exception": error_detail["error_exception"],
                    "error_file": describe_error_file(st, h) if error else "",
                    "error_alert": self._error_alerts.get(rid, "") if error else "",
                    "save_path": rec["save_path"], "hash": self._torrent_key(h),
                })
            except Exception as exc:
                items.append({"id": rid, "name": rec.get("name", "Torrent"), "size": 0,
                              "done": 0, "progress": 0, "state": "Error", "down": 0, "up": 0,
                              "peers": 0, "seeds": 0, "eta": -1, "ratio": 0, "paused": True,
                              "error": str(exc), "error_hint": explain_error(str(exc)),
                              "save_path": rec.get("save_path", "")})
        if changed:
            self.persist()
        return items

    def files(self, rid: str) -> list[dict]:
        h = self.handles.get(rid)
        if not h or not h.is_valid() or not h.has_metadata():
            return []
        ti = h.torrent_file()
        files = ti.files()
        priorities = list(h.get_file_priorities())
        try:
            downloaded = list(h.file_progress())
        except Exception:
            downloaded = []
        return [{"index": i, "path": files.file_path(i), "size": int(files.file_size(i)),
                 "downloaded": int(downloaded[i]) if i < len(downloaded) else 0,
                 "priority": int(priorities[i]) if i < len(priorities) else 4}
                for i in range(files.num_files())]

    def set_file_priority(self, rid: str, index: int, priority: int):
        if priority not in (0, 1, 4, 7):
            raise EngineError("Prioridad de archivo no admitida.")
        h = self.handles[rid]
        h.file_priority(index, priority)
        self.request_resume(rid)

    def set_file_priorities(self, rid: str, changes: dict[int, int]) -> None:
        """Cambios por lotes tras validar índices y prioridades; nunca borra archivos."""
        h = self.handles.get(rid)
        if not h or not h.is_valid() or not h.has_metadata():
            raise EngineError("No hay metadatos disponibles para seleccionar archivos.")
        total = len(h.get_file_priorities())
        for idx, value in changes.items():
            if type(idx) is not int or not 0 <= idx < total or value not in (0, 1, 4, 7):
                raise EngineError("Índice o prioridad inválidos; no se aplicó ningún cambio.")
        if not changes:
            return
        for idx, value in changes.items():
            h.file_priority(idx, value)
        self.request_resume(rid)

    def tracker_details(self, rid: str) -> list[dict]:
        """Las URLs vienen del motor, los errores del flujo de alertas.

        Un fallo leyendo archivos NO debe interferir con esta función.
        """
        h = self.handles.get(rid)
        if not h or not h.is_valid():
            return [{"url": "—", "state": "Sin conexión", "message": "Torrent no recuperado"}]
        found = []
        problems = []
        try:
            for entry in h.trackers():
                url = getattr(entry, "url", "")
                if isinstance(url, str) and url:
                    found.append(url)
        except Exception as exc:
            problems.append(f"No se pudo leer la lista activa: {type(exc).__name__}: {exc}")
        if not found and h.has_metadata():
            try:
                for entry in h.torrent_file().trackers():
                    url = getattr(entry, "url", "")
                    if isinstance(url, str) and url:
                        found.append(url)
            except Exception as exc:
                problems.append(f"No se pudo leer .torrent: {type(exc).__name__}: {exc}")
        report = self._tracker_health.get(rid, {})
        found.extend(url for url in report if url not in found)
        if not found:
            return [{"url": "(ningún tracker registrado)", "state": "Sin trackers",
                     "message": "; ".join(problems) or
                     "Puede depender de DHT. Verifica si el .torrent original tiene URLs de announce."}]
        out = []
        for url in dict.fromkeys(found):
            info = report.get(url, {})
            state = info.get("state", "Sin respuesta registrada")
            detail = info.get("message", "")
            if info.get("time"):
                detail = f"{info['time']} · {detail}".strip(" ·")
            out.append({"url": url, "state": state, "message": detail})
        if problems:
            out.append({"url": "(lectura parcial)", "state": "Aviso", "message": "; ".join(problems)})
        return out

    def trackers(self, rid: str) -> list[str]:
        return [entry["url"] for entry in self.tracker_details(rid)
                if entry["url"].startswith(("http://", "https://", "udp://"))]

    def reannounce(self, rid: str) -> None:
        h = self.handles.get(rid)
        if not h or not h.is_valid():
            raise EngineError("Selecciona un torrent válido para reanunciar.")
        now = time.monotonic()
        last = self._announce_times.get(rid)
        if last is not None and now - last < 60:
            raise EngineError("Ya se solicitó un anuncio. Espera 60 segundos para evitar saturar trackers.")
        h.force_reannounce()
        self._announce_times[rid] = now

    def attempt_recovery(self, rid: str) -> dict[str, object]:
        """Conservative retry of peer discovery; never modifies trackers or files.

        Respects manually paused/scheduled/private torrents. Unlike force
        rechecks, this cannot cause lengthy disk I/O. Cooldown shared with
        reannounce() and optional DHT announces prevents tracker flooding.
        No torrent is ever described as unavailable solely for having zero seeds.
        """
        handle = self.handles.get(rid)
        rec = self.records.get(rid)
        if not rec or handle is None or not handle.is_valid():
            raise EngineError("Selecciona una descarga válida antes de reintentar.")
        if rec.get("paused") or rec.get("schedule_paused"):
            return {"changed": False, "code": "paused",
                    "message": "Esta descarga está pausada manualmente o fuera de horario. No se cambió la pausa. Reanúdala o revisa el planificador si quieres continuar."}
        status = handle.status()
        if getattr(status, "is_seeding", False) or float(getattr(status, "progress", 0)) >= 1:
            return {"changed": False, "code": "completed",
                    "message": "El contenido ya está completo. No necesita recuperar fuentes para descargar."}
        if describe_libtorrent_error(getattr(status, "errc", None))["error"]:
            return {"changed": False, "code": "error",
                    "message": "El motor registra un error. Consulta Diagnóstico y Verificar; no se ha alterado la descarga."}
        remaining = 60 - (time.monotonic() - self._announce_times.get(rid, float('-inf')))
        if remaining > 0:
            return {"changed": False, "code": "cooldown",
                    "message": f"Ya se solicitó búsqueda recientemente. Espera {int(remaining)+1} segundos antes de repetirla."}
        commands = []
        # Do not announce a private torrent via DHT. Some bindings do not
        # expose force_dht_announce(), so skip it gracefully.
        private = False
        if handle.has_metadata():
            try:
                info = handle.torrent_file()
                private = bool(info.priv()) if info is not None else False
            except Exception:
                private = True  # fail closed if metadata cannot be inspected
        if self.settings.get("dht", True) and not private:
            dht = getattr(handle, "force_dht_announce", None)
            if callable(dht):
                try:
                    dht()
                    commands.append("DHT")
                except Exception as exc:
                    logging.warning("DHT announce opcional no disponible: %s", exc)
        force = getattr(handle, "force_reannounce", None)
        if callable(force):
            try:
                force()
                commands.append("trackers")
            except Exception as exc:
                logging.warning("No se pudo reanunciar trackers: %s", exc)
        if not commands:
            return {"changed": False, "code": "unsupported",
                    "message": "Esta versión del motor no pudo iniciar un anuncio adicional. La descarga seguirá buscando normalmente."}
        self._announce_times[rid] = time.monotonic()
        message = ("Nueva búsqueda solicitada mediante " + " y ".join(commands) +
                   ". Espera unos minutos y consulta Pares / Diagnóstico. "
                   "No se añadieron trackers ni se tocaron datos; si no hay fuentes disponibles no comenzará la descarga.")
        return {"changed": True, "code": "requested", "message": message, "via": tuple(commands)}

    def diagnose_download(self, rid: str, row: dict | None = None):
        """Aviso de causas posibles; solo consulta información observada."""
        if rid not in self.records:
            raise EngineError("No se encontró la descarga.")
        if row is None:
            row = next((item for item in self.rows() if item['id'] == rid), {})
        overview = self.network_overview()
        listen_ok = None
        if overview['listen']:
            listen_ok = True
        elif overview['failures']:
            listen_ok = False
        return diagnose(row, self.tracker_details(rid),
                        dht_enabled=bool(self.settings.get('dht', True)), listen_ok=listen_ok)


    def network_diagnostic(self, rid: str, row: dict | None = None) -> str:
        rec = self.records.get(rid)
        if not rec:
            raise EngineError("No se encontró el torrent.")
        row = row or next((r for r in self.rows() if r["id"] == rid), {})
        diagnosis = self.diagnose_download(rid, row)
        overview = self.network_overview()
        lines = [f"Apex Torrent {VERSION} — diagnóstico de conectividad", "",
                 "¿POR QUÉ NO DESCARGA?", diagnosis.report(), "",
                 "Aviso: contiene nombres, URLs de trackers y rutas de archivos locales.", "",
                 f"Torrent: {row.get('name', rec.get('name', '—'))}",
                 f"Estado: {row.get('state', '—')}",
                 f"Pares conectados: {row.get('peers', '—')}",
                 f"Semillas conectadas: {row.get('seeds', '—')}",
                 f"Velocidad: {row.get('down', '—')} bytes/s",
                 f"Progreso: {100 * row.get('progress', 0):.2f}%",
                 f"Interfaces de escucha: {overview['requested_interfaces']}",
                 f"Interfaces de salida TCP: {overview['outgoing_interfaces']}",
                 f"Selección de interfaz: {overview['route_info']}",
                 "Puerto automático: " + ("Sí (elegido por Windows)" if int(self.settings.get("listen_port", 0)) == 0 else "No"),
                 f"DHT habilitada: {self.settings.get('dht', False)}",
                 f"UPnP/NAT-PMP habilitado: {self.settings.get('upnp', False)}",
                 f"Máximo de conexiones: {self.settings.get('connections_limit', 200)}",
                 f"Hash: {row.get('hash', '—')}",
                 f"Última respuesta DHT: {self._dht_events.get(rid, 'No registrada')}",
                 f"Error de torrent: {row.get('error', '') or 'Ninguno registrado'}",
                 f"Carpeta: {rec.get('save_path', '—')}", "", "TRACKERS:"]
        for entry in self.tracker_details(rid):
            lines.append(f"• {entry['url']} | {entry['state']} | {entry['message']}")
        lines.append("\nEVENTOS GENERALES DE RED:")
        lines.extend(self._network_events or ["No registrados"])
        lines.extend(["", "INTERPRETACIÓN:",
                      "Si aparece listen_succeeded_alert en IPv4 (0.0.0.0 o 192.168.x.x), la escucha IPv4 está activa.",
                      "Si aparece listen_failed_alert, consulta el puerto y el mensaje de Windows.",
                      "Puerto automático no garantiza conectividad externa si hay restricciones de red o firewall."])
        return "\n".join(lines)

    def close(self, seconds: float = 3.0):
        self.persist()
        self.save_all_resume()
        deadline = time.monotonic() + seconds
        while self._resume_pending and time.monotonic() < deadline:
            self.process_alerts()
            if self._resume_pending:
                time.sleep(0.05)
        self.process_alerts()
