"""Planificador horario optativo y local: no cambia firewall, red ni semillas.

Una ventana [inicio, fin) se expresa en horas locales 0..23. Inicio=fin
significa día entero y el modo está apagado por defecto.
"""
from datetime import datetime


def hour_allowed(start: int, end: int, hour: int) -> bool:
    for n in (start, end, hour):
        if type(n) is not int or not 0 <= n <= 23:
            raise ValueError("El horario debe utilizar horas enteras entre 00 y 23.")
    if start == end:
        return True
    if start < end:
        return start <= hour < end
    return hour >= start or hour < end


def schedule_allowed(settings: dict, now: datetime | None = None) -> bool:
    if not settings.get("schedule_enabled", False):
        return True
    hour = (now or datetime.now().astimezone()).hour
    return hour_allowed(int(settings.get("schedule_start_hour", 0)),
                        int(settings.get("schedule_end_hour", 0)), hour)


def schedule_caption(settings: dict, now: datetime | None = None) -> str:
    if not settings.get("schedule_enabled", False):
        return "Planificador desactivado · las transferencias siguen su curso normal."
    start, end = int(settings["schedule_start_hour"]), int(settings["schedule_end_hour"])
    hours = "todo el día" if start == end else f"{start:02d}:00–{end:02d}:00 (hora local)"
    state = "Horario permitido" if schedule_allowed(settings, now) else "Fuera de horario: descargas en pausa"
    return f"{state} · Ventana {hours}. Comparticiones terminadas no se pausan."
