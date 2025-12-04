# pages/cart_page.py
from __future__ import annotations
from typing import Dict, List
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QListWidget, QListWidgetItem, QFrame, QHBoxLayout,
    QLabel, QPushButton, QGraphicsOpacityEffect
)
from shiboken6 import isValid as qt_is_valid
from services.env import abs_url
from services.net_image import NetImage


class CartPage(QWidget):
    # neue, klare Signale
    remove_requested = Signal(int)      # game_id
    checkout_requested = Signal()
    # Kompatibilitäts-Aliase (für alte Verkabelung in gui.py)
    item_removed = Signal(int)
    checkout_clicked = Signal()

    THUMB_W = 64
    THUMB_H = 86

    def __init__(self):
        super().__init__()
        self._items: List[Dict] = []
        self._img = NetImage(self)
        self._ph: QPixmap | None = None

        root = QVBoxLayout(self)
        root.setContentsMargins(24, 16, 24, 16)
        root.setSpacing(12)

        header = QLabel("🧺 Warenkorb", alignment=Qt.AlignHCenter)
        header.setStyleSheet("font-size:26px; font-weight:700; margin:8px 0 6px;")
        root.addWidget(header)

        self.list = QListWidget()
        self.list.setStyleSheet("QListWidget{border:0;}")
        root.addWidget(self.list, 1)

        foot = QHBoxLayout()
        self.total_lbl = QLabel("Summe: 0,00 €")
        self.btn_checkout = QPushButton("Zur Kasse")
        # beide Signale abfeuern (neu + Alias)
        self.btn_checkout.clicked.connect(self.checkout_requested.emit)
        self.btn_checkout.clicked.connect(self.checkout_clicked.emit)
        foot.addWidget(self.total_lbl, 1)
        foot.addWidget(self.btn_checkout, 0)
        root.addLayout(foot)

    def set_items(self, items: List[Dict]):
        self._items = list(items or [])
        self._rebuild()
        self._update_total()

    def _rebuild(self):
        self.list.clear()
        for g in self._items:
            self._add_row(g)

    def _add_row(self, game: Dict):
        gid = int(game.get("id", 0))
        title = str(game.get("title") or "Unbenannt")
        price = float(game.get("price") or 0.0)
        sale = float(game.get("sale_percent") or 0.0)
        cover_url = str(game.get("cover_url") or "").strip()

        # effektiver Preis
        if sale > 0.0:
            eff = price * (100.0 - sale) / 100.0
            price_text = f"{self._fmt_price(price)} → {self._fmt_price(eff)}"
        else:
            price_text = self._fmt_price(price)

        row = QFrame()
        row.setStyleSheet(
            "QFrame{background:#1b1b1b;"
            "border:1px solid rgba(255,255,255,0.07);"
            "border-radius:10px;}"
        )
        lay = QHBoxLayout(row)
        lay.setContentsMargins(10, 8, 10, 8)
        lay.setSpacing(10)

        thumb = QLabel()
        thumb.setFixedSize(self.THUMB_W, self.THUMB_H)
        thumb.setStyleSheet("background:#111;border-radius:8px;")
        thumb.setPixmap(self._placeholder())
        lay.addWidget(thumb, 0)

        if cover_url:
            url = abs_url(cover_url)

            def _on_img(pm: QPixmap, lbl=thumb):
                if not qt_is_valid(lbl) or pm.isNull():
                    return
                lbl.setPixmap(
                    pm.scaled(
                        self.THUMB_W,
                        self.THUMB_H,
                        Qt.KeepAspectRatioByExpanding,
                        Qt.SmoothTransformation,
                    )
                )
                self._fade_in(lbl, 180)

            self._img.load(url, _on_img, guard=thumb)

        meta = QVBoxLayout()
        t = QLabel(title)
        t.setStyleSheet("font-size:14px;color:#eaeaea;")
        p = QLabel(price_text)
        p.setStyleSheet("font-size:13px;color:#cfcfcf;")
        meta.addWidget(t)
        meta.addWidget(p)
        lay.addLayout(meta, 1)

        btn_remove = QPushButton("Entfernen")
        btn_remove.setStyleSheet("QPushButton{padding:6px 10px;}")
        # neu + alias gleichzeitig emittieren
        btn_remove.clicked.connect(
            lambda _=None, id_=gid: (
                self.remove_requested.emit(id_),
                self.item_removed.emit(id_),
            )
        )
        lay.addWidget(btn_remove, 0)

        item = QListWidgetItem(self.list)
        item.setSizeHint(row.sizeHint())
        self.list.addItem(item)
        self.list.setItemWidget(item, row)

    def _update_total(self):
        total = 0.0
        for g in self._items:
            price = float(g.get("price") or 0.0)
            sale = float(g.get("sale_percent") or 0.0)
            if sale > 0.0:
                price = price * (100.0 - sale) / 100.0
            total += price
        self.total_lbl.setText(f"Summe: {self._fmt_price(total)}")

    def _fmt_price(self, price: float) -> str:
        return (
            f"{price:,.2f} €"
            .replace(",", "X")
            .replace(".", ",")
            .replace("X", ".")
        )

    def _placeholder(self) -> QPixmap:
        if self._ph and not self._ph.isNull():
            return self._ph
        pm = QPixmap(self.THUMB_W, self.THUMB_H)
        pm.fill(Qt.black)
        self._ph = pm
        return pm

    def _fade_in(self, widget, duration_ms: int):
        eff = QGraphicsOpacityEffect(widget)
        eff.setOpacity(0.0)
        widget.setGraphicsEffect(eff)
        from PySide6.QtCore import QPropertyAnimation, QEasingCurve

        anim = QPropertyAnimation(eff, b"opacity", widget)
        anim.setDuration(max(60, duration_ms))
        anim.setStartValue(0.0)
        anim.setEndValue(1.0)
        anim.setEasingCurve(QEasingCurve.OutCubic)
        anim.start(QPropertyAnimation.DeleteWhenStopped)
