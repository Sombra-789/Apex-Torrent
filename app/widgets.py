"""Widgets gráficos de Apex Torrent 1.1; dibujo local sin QtCharts/WebEngine."""
from __future__ import annotations
from PySide6.QtCore import Qt, QPointF
from PySide6.QtGui import QColor, QPainter, QPen, QPainterPath, QLinearGradient, QFont
from PySide6.QtWidgets import QWidget, QApplication
from performance import TransferHistory

class TransferGraph(QWidget):
    """Historial real muestreado por el controlador; cero hasta recibir datos."""
    def __init__(self, parent=None, capacity=180):
        super().__init__(parent)
        self.history = TransferHistory(capacity)
        self.setMinimumHeight(145)
        self.setToolTip("Gráfica local de tráfico registrado por Apex Torrent; sin simulaciones")

    def add_sample(self, down: float, up: float):
        self.history.append(down, up)
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = self.rect().adjusted(41, 22, -17, -29)
        if rect.width() <= 10 or rect.height() <= 10:
            p.end(); return
        p.setPen(QPen(QColor("#202020"), 1))
        for i in range(5):
            y = rect.top() + rect.height() * i / 4
            p.drawLine(QPointF(rect.left(), y), QPointF(rect.right(), y))
        mx = max(128 * 1024, self.history.peak() * 1.12)
        p.setPen(QColor("#aeb0b5"))
        p.setFont(QFont("Segoe UI", 8))
        p.drawText(2, 19, f"{mx/1048576:.1f} MiB/s")
        p.drawText(9, rect.bottom(), "0")
        p.drawText(rect.left(), self.height()-9, "−3 min")
        p.drawText(rect.right()-30, self.height()-9, "Ahora")
        accent = QApplication.instance().property("apex_plot_accent") or "#35aaff"
        for samples, color in (
            (self.history.downloads, accent),
            (self.history.uploads, "#9c9fa8")):
            points = list(samples)
            if not points:
                continue
            path = QPainterPath()
            denom = max(1, self.history.capacity-1)
            x0 = rect.left() + max(0,self.history.capacity-len(points)) / denom * rect.width()
            y0 = rect.bottom() - min(mx,points[0]) / mx * rect.height()
            path.moveTo(x0, y0)
            for i, value in enumerate(points[1:], start=1):
                x = rect.left() + (max(0, self.history.capacity-len(points)) + i)/denom*rect.width()
                y = rect.bottom() - min(mx,value)/mx*rect.height()
                path.lineTo(x,y)
            p.setPen(QPen(QColor(color), 2))
            p.drawPath(path)
        p.setPen(QColor(accent)); p.drawText(rect.left()+8, 14, "●  Descarga")
        p.setPen(QColor("#9c9fa8")); p.drawText(rect.left()+110, 14, "●  Subida")
        p.end()
