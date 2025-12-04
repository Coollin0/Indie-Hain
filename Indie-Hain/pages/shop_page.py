# pages/shop_page.py
from __future__ import annotations
from typing import Dict, List, Set

from PySide6.QtCore import (
    Qt, QSize, Signal, QObject, QEvent, QTimer,
    QPropertyAnimation, QEasingCurve, QRect
)
from PySide6.QtGui import QIcon, QPixmap
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QScrollArea, QFrame, QGridLayout, QToolButton,
    QLabel, QHBoxLayout, QSizePolicy, QGraphicsOpacityEffect
)

from shiboken6 import isValid as qt_is_valid

from services import shop_api
from services.env import abs_url
from services.net_image import NetImage


class ShopPage(QWidget):
    add_to_cart = Signal(dict)      # {id:int, title:str, price:float}
    game_clicked = Signal(dict)     # {id, title, price, ...}

    CARD_W = 180
    COVER_H = 240
    HSPACE = 18
    VSPACE = 22

    def __init__(self):
        super().__init__()
        self._games: List[Dict] = []
        self._cart_ids: Set[int] = set()
        self._owned_ids: Set[int] = set()
        self._cards: list[QWidget] = []
        self._badge_by_id: dict[int, QLabel] = {}
        self._ph_pm: QPixmap | None = None  # placeholder cache

        # Grundlayout
        root = QVBoxLayout(self)
        root.setContentsMargins(24, 16, 24, 16)
        root.setSpacing(12)

        header = QLabel("🛒 Indie-Hain Shop", alignment=Qt.AlignHCenter)
        header.setStyleSheet("font-size:26px; font-weight:700; margin:8px 0 6px;")
        root.addWidget(header)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.NoFrame)
        root.addWidget(self.scroll, 1)

        self.grid_host = QWidget()
        self.grid = QGridLayout(self.grid_host)
        self.grid.setContentsMargins(4, 4, 4, 4)
        self.grid.setHorizontalSpacing(self.HSPACE)
        self.grid.setVerticalSpacing(self.VSPACE)
        self.scroll.setWidget(self.grid_host)

        self.empty_lbl = QLabel("Keine Spiele gefunden.")
        self.empty_lbl.setAlignment(Qt.AlignCenter)
        self.empty_lbl.setStyleSheet("color:#a8a8a8; padding:32px; font-size:14px;")
        self.empty_lbl.hide()
        root.addWidget(self.empty_lbl)

        self._img = NetImage(self)
        self.scroll.viewport().installEventFilter(self)

        QTimer.singleShot(0, self.refresh)

    # ---------- Öffentliche API ----------
    def set_games(self, games: List[Dict]):
        self._games = list(games)
        self._build_cards()
        self._relayout()

    def set_cart_ids(self, ids: Set[int]):
        self._cart_ids = set(ids)
        self._sync_badges()

    def set_owned_ids(self, ids: Set[int]):
        self._owned_ids = set(ids)
        self._sync_badges()

    def all_games(self) -> list[dict]:
        """
        Gibt eine Kopie der aktuellen Shop-Games zurück.
        Wird benutzt, um Library-Einträge mit Cover/Beschreibung
        aus dem Shop anzureichern.
        """
        return list(self._games)

    # ---------- Events ----------
    def eventFilter(self, obj: QObject, ev) -> bool:
        if obj is self.scroll.viewport() and ev.type() == QEvent.Resize:
            self._relayout()
        return super().eventFilter(obj, ev)

    # ---------- Kartenaufbau ----------
    def _build_cards(self):
        while self.grid.count():
            item = self.grid.takeAt(0)
            w = item.widget()
            if w:
                w.setParent(None)
                w.deleteLater()

        self._cards.clear()
        self._badge_by_id.clear()

        if not self._games:
            self.grid_host.hide()
            self.empty_lbl.show()
            return

        self.empty_lbl.hide()
        self.grid_host.show()

        for g in self._games:
            self._cards.append(self._create_card(g))

        self._sync_badges()

    def _relayout(self):
        if not self._cards:
            return
        vw = self.scroll.viewport().width()
        cols = max(1, int((vw + self.HSPACE) // (self.CARD_W + self.HSPACE)))
        for i, card in enumerate(self._cards):
            r = i // cols
            c = i % cols
            self.grid.addWidget(card, r, c, Qt.AlignTop)

    # ---------- Karte erzeugen ----------
    def _create_card(self, game: Dict) -> QWidget:
        gid: int = int(game.get("id", 0))
        title: str = str(game.get("title") or "Unbenannt")
        price: float = float(game.get("price") or 0.0)
        desc: str = str(game.get("description") or "")
        cover_url: str = str(game.get("cover_url") or "").strip()

        card = QFrame()
        card.setObjectName("card")
        card.setFixedWidth(self.CARD_W)
        card.setStyleSheet("""
            QFrame#card {
                background:#1e1e1e; border:1px solid rgba(255,255,255,0.07);
                border-radius:12px;
            }
            QFrame#card:hover { border-color: rgba(255,255,255,0.18); }
        """)
        lay = QVBoxLayout(card)
        lay.setContentsMargins(10, 10, 10, 10)
        lay.setSpacing(8)

        # --- Cover mit Hover-Zoom ---
        cover_btn = QToolButton()
        cover_btn.setToolButtonStyle(Qt.ToolButtonIconOnly)
        cover_btn.setIconSize(QSize(self.CARD_W - 20, self.COVER_H))
        cover_btn.setFixedSize(self.CARD_W - 20, self.COVER_H)
        cover_btn.setStyleSheet("border:0; border-radius:8px; background:#111;")
        cover_btn.setCursor(Qt.PointingHandCursor)
        cover_btn.setToolTip(title)
        cover_btn.setIcon(QIcon(self._placeholder_pm()))
        lay.addWidget(cover_btn)
        cover_btn.clicked.connect(lambda _, g=game: self.game_clicked.emit(g))

        # Hover-Animation Setup
        cover_btn._hover_anim = QPropertyAnimation(cover_btn, b"geometry", cover_btn)
        cover_btn._hover_anim.setDuration(130)
        cover_btn._hover_anim.setEasingCurve(QEasingCurve.OutQuad)
        cover_btn.installEventFilter(self)

        # Badge
        badge = QLabel("", parent=cover_btn)
        badge.setStyleSheet("""
            background: rgba(0,0,0,0.65); color:#e8e8e8; padding:2px 6px;
            border-radius:8px; font-size:11px;
        """)
        badge.move(6, 6)
        badge.hide()
        self._badge_by_id[gid] = badge

        # Start transparent, nach dem Laden einblenden
        self._attach_fader(cover_btn, start_opacity=0.0)

        if cover_url:
            url = abs_url(cover_url)
            def _on_img(pm: QPixmap, btn=cover_btn):
                if not qt_is_valid(btn) or pm.isNull():
                    return
                scaled = pm.scaled(
                    btn.iconSize().width(), btn.iconSize().height(),
                    Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation
                )
                btn.setIcon(QIcon(scaled))
                self._fade_in(btn, duration_ms=220)
            self._img.load(url, _on_img, guard=cover_btn)

        # --- Preis-Badge auf dem Cover ---
        sale = float(game.get("sale_percent") or 0.0)
        price_text = self._fmt_price(price * (100.0 - sale) / 100.0 if sale > 0 else price)
        price_lbl = QLabel(price_text, parent=cover_btn)
        price_lbl.setStyleSheet("""
            background: rgba(0,0,0,0.7);
            color: #f8f8f8;
            padding: 4px 8px;
            border-radius: 8px;
            font-size: 13px;
            font-weight: 600;
        """)
        price_lbl.adjustSize()
        price_lbl.move(cover_btn.width() - price_lbl.width() - 10, cover_btn.height() - price_lbl.height() - 10)
        if sale > 0.0:
            price_lbl.setText(f"-{int(sale)}% {price_text}")

        # Hover-Overlay mit Titel + Beschreibung
        overlay = QFrame(cover_btn)
        overlay.setObjectName("overlay")
        overlay.setStyleSheet("""
            QFrame#overlay { background: rgba(0,0,0,0.55); border-radius:8px; }
            QFrame#overlay QLabel { color: #f2f2f2; background: transparent; }
        """)
        overlay.setGeometry(0, 0, cover_btn.width(), cover_btn.height())
        overlay.hide()
        ov_lay = QVBoxLayout(overlay)
        ov_lay.setContentsMargins(10, 10, 10, 10)
        ov_lay.setSpacing(6)
        t_lbl = QLabel(title)
        t_lbl.setWordWrap(True)
        t_lbl.setStyleSheet("font-size:14px; font-weight:700; background: transparent;")
        ov_lay.addWidget(t_lbl)
        if desc:
            d_lbl = QLabel(desc)
            d_lbl.setWordWrap(True)
            d_lbl.setStyleSheet("font-size:12px; color:#d8d8d8; background: transparent;")
            d_lbl.setFixedHeight(min(120, 300))  # begrenzt die Höhe ein wenig
            d_lbl.setAlignment(Qt.AlignTop)
            d_lbl.setTextInteractionFlags(Qt.TextSelectableByMouse)
            ov_lay.addWidget(d_lbl)
        ov_lay.addStretch(1)
        cover_btn._hover_overlay = overlay
        cover_btn._price_label = price_lbl

        return card

    # ========== Effekte ==========
    def eventFilter(self, obj, ev):
        # Hover Zoom-Effekt
        if isinstance(obj, QToolButton):
            if ev.type() == QEvent.Enter:
                self._animate_hover(obj, zoom_in=True)
                ov = getattr(obj, "_hover_overlay", None)
                if ov:
                    ov.show()
            elif ev.type() == QEvent.Leave:
                self._animate_hover(obj, zoom_in=False)
                ov = getattr(obj, "_hover_overlay", None)
                if ov:
                    ov.hide()
            elif ev.type() == QEvent.Resize:
                # Preisbadge und Overlay mit dem Button mitbewegen
                ov = getattr(obj, "_hover_overlay", None)
                if ov:
                    ov.setGeometry(0, 0, obj.width(), obj.height())
                pl = getattr(obj, "_price_label", None)
                if pl:
                    pl.move(obj.width() - pl.width() - 10, obj.height() - pl.height() - 10)
        return super().eventFilter(obj, ev)

    def _animate_hover(self, btn: QToolButton, zoom_in: bool):
        """Kleine Scale-Animation beim Hovern."""
        anim: QPropertyAnimation = getattr(btn, "_hover_anim", None)
        if not anim:
            return
        rect = btn.geometry()
        if zoom_in:
            new_rect = QRect(
                rect.x() - 3, rect.y() - 3,
                rect.width() + 6, rect.height() + 6
            )
        else:
            new_rect = QRect(
                rect.x() + 3, rect.y() + 3,
                rect.width() - 6, rect.height() - 6
            )
        anim.stop()
        anim.setStartValue(rect)
        anim.setEndValue(new_rect)
        anim.start()

    # ===== Helpers =====
    def _clamp_two_lines(self, text: str, avail_px: int) -> str:
        """Schneidet Text so, dass er in ~2 Zeilen passt, mit … am Ende."""
        if not text:
            return ""
        fm = self.fontMetrics()
        # grobe Heuristik: verfügbare Breite = Kartenbreite - Padding
        max_per_line = fm.elidedText(text, Qt.ElideRight, avail_px)
        # zweite Zeile: Rest erneut eliden
        if len(text) <= len(max_per_line):
            return max_per_line
        rest = text[len(max_per_line):].lstrip()
        second = fm.elidedText(rest, Qt.ElideRight, avail_px)
        # “Zeilenumbruch” erzwingen
        return f"{max_per_line}\n{second}"
    
    def _placeholder_pm(self) -> QPixmap:
        if self._ph_pm and not self._ph_pm.isNull():
            return self._ph_pm
        pm = QPixmap(self.CARD_W - 20, self.COVER_H)
        pm.fill(Qt.black)
        self._ph_pm = pm
        return pm

    def _attach_fader(self, widget: QWidget, start_opacity: float = 0.0):
        eff = QGraphicsOpacityEffect(widget)
        eff.setOpacity(max(0.0, min(1.0, start_opacity)))
        widget.setGraphicsEffect(eff)

    def _fade_in(self, widget: QWidget, duration_ms: int = 220):
        eff = widget.graphicsEffect()
        if not isinstance(eff, QGraphicsOpacityEffect):
            eff = QGraphicsOpacityEffect(widget)
            eff.setOpacity(0.0)
            widget.setGraphicsEffect(eff)
        anim = QPropertyAnimation(eff, b"opacity", widget)
        anim.setDuration(max(60, duration_ms))
        anim.setStartValue(eff.opacity())
        anim.setEndValue(1.0)
        anim.setEasingCurve(QEasingCurve.OutCubic)
        anim.start(QPropertyAnimation.DeleteWhenStopped)

    def _fmt_price(self, price: float) -> str:
        return (f"{price:,.2f} €").replace(",", "X").replace(".", ",").replace("X", ".")

    def _sync_badges(self):
        for g in self._games:
            gid = int(g["id"])
            badge = self._badge_by_id.get(gid)
            if not badge:
                continue

            if gid in self._owned_ids:
                badge.setText("✔︎ Gekauft")
                badge.show()
            elif gid in self._cart_ids:
                badge.setText("Im Warenkorb")
                badge.show()
            else:
                # Wenn Sale aktiv ist, Rabatt anzeigen
                sale = float(g.get("sale_percent") or 0.0)
                if sale > 0.0:
                    badge.setText(f"-{int(sale)}%")
                    badge.show()
                else:
                    badge.hide()


    # ---------- Daten vom Backend ----------
    def refresh(self):
        try:
            games = shop_api.list_public_games()
            self.set_games(games or [])
            if not games:
                print("⚠️ Keine Spiele im Backend gefunden.")
        except Exception as e:
            print("❌ Konnte Spiele nicht laden:", e)
            self.set_games([])
