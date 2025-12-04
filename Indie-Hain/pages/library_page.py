# pages/library_page.py
from __future__ import annotations
from typing import Dict, List
from PySide6.QtCore import Qt, QSize, Signal, QObject, QEvent, QPropertyAnimation, QEasingCurve
from PySide6.QtGui import QIcon, QPixmap
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QScrollArea, QFrame, QGridLayout, QToolButton,
    QLabel, QHBoxLayout, QSizePolicy, QGraphicsOpacityEffect, QPushButton
)
from shiboken6 import isValid as qt_is_valid
from services.env import abs_url
from services.net_image import NetImage

class LibraryPage(QWidget):
    item_clicked = Signal(dict)
    install_requested = Signal(dict)    # <- für gui.py erwartet
    start_requested = Signal(dict)      # ruft Starten auf (wenn installiert)
    uninstall_requested = Signal(dict)  # ruft Deinstallation auf

    CARD_W = 180
    COVER_H = 240
    HSPACE = 18
    VSPACE = 22

    def __init__(self):
        super().__init__()
        self._items: List[Dict] = []
        self._cards: list[QWidget] = []
        self._ph_pm: QPixmap | None = None

        root = QVBoxLayout(self)
        root.setContentsMargins(24, 16, 24, 16)
        root.setSpacing(12)

        header = QLabel("📚 Deine Bibliothek", alignment=Qt.AlignHCenter)
        header.setStyleSheet("font-size:26px; font-weight:700; margin:8px 0 6px;")
        root.addWidget(header)

        self.scroll = QScrollArea(); self.scroll.setWidgetResizable(True); self.scroll.setFrameShape(QFrame.NoFrame)
        root.addWidget(self.scroll, 1)

        self.grid_host = QWidget()
        self.grid = QGridLayout(self.grid_host)
        self.grid.setContentsMargins(4, 4, 4, 4)
        self.grid.setHorizontalSpacing(self.HSPACE)
        self.grid.setVerticalSpacing(self.VSPACE)
        self.scroll.setWidget(self.grid_host)

        self.empty_lbl = QLabel("Noch keine Spiele in deiner Bibliothek.")
        self.empty_lbl.setAlignment(Qt.AlignCenter)
        self.empty_lbl.setStyleSheet("color:#a8a8a8; padding:32px; font-size:14px;")
        self.empty_lbl.hide()
        root.addWidget(self.empty_lbl)

        self._img = NetImage(self)
        self.scroll.viewport().installEventFilter(self)

    # API
    def set_items(self, items: List[Dict]):
        self._items = list(items or [])
        self._build_cards()
        self._relayout()

    def set_games(self, games: List[Dict]):
        self.set_items(games)

    # Build/Layout
    def _build_cards(self):
        while self.grid.count():
            it = self.grid.takeAt(0)
            w = it.widget()
            if w:
                w.setParent(None)
                w.deleteLater()
        self._cards.clear()

        if not self._items:
            self.grid_host.hide(); self.empty_lbl.show()
            return

        self.empty_lbl.hide(); self.grid_host.show()

        for g in self._items:
            self._cards.append(self._create_card(g))

    def _relayout(self):
        if not self._cards:
            return
        vw = self.scroll.viewport().width()
        cols = max(1, int((vw + self.HSPACE) // (self.CARD_W + self.HSPACE)))
        for i, card in enumerate(self._cards):
            r = i // cols
            c = i % cols
            self.grid.addWidget(card, r, c, Qt.AlignTop)

    def eventFilter(self, obj: QObject, ev) -> bool:
        if obj is self.scroll.viewport() and ev.type() == QEvent.Resize:
            self._relayout()
        return super().eventFilter(obj, ev)

    # Card
    def _create_card(self, game: Dict) -> QWidget:
        title: str = str(game.get("title") or "Unbenannt")
        cover_url: str = str(game.get("cover_url") or "").strip()

        card = QFrame()
        card.setObjectName("card")
        card.setFixedWidth(self.CARD_W)
        card.setStyleSheet("""
            QFrame#card { background:#1e1e1e; border:1px solid rgba(255,255,255,0.07); border-radius:12px; }
            QFrame#card:hover { border-color: rgba(255,255,255,0.18); }
        """)
        lay = QVBoxLayout(card); lay.setContentsMargins(10,10,10,10); lay.setSpacing(8)

        # --- COVER BUTTON ---
        cover_btn = QToolButton()
        cover_btn.setToolButtonStyle(Qt.ToolButtonIconOnly)
        cover_btn.setIconSize(QSize(self.CARD_W-20, self.COVER_H))
        cover_btn.setFixedSize(self.CARD_W-20, self.COVER_H)
        cover_btn.setStyleSheet("border:0; border-radius:8px; background:#111;")
        cover_btn.setCursor(Qt.PointingHandCursor)
        cover_btn.setToolTip(title)
        cover_btn.setIcon(QIcon(self._placeholder_pm()))
        lay.addWidget(cover_btn)
        cover_btn.clicked.connect(lambda _, g=game: self.item_clicked.emit(g))

        self._attach_fader(cover_btn, 0.0)

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
                self._fade_in(btn, 220)
            self._img.load(url, _on_img, guard=cover_btn)

        # --- TITELZEILE + INSTALL/START/DEINSTALL BUTTONS ---
        title_btn = QToolButton()
        title_btn.setText(title)
        title_btn.setToolButtonStyle(Qt.ToolButtonTextOnly)
        title_btn.setStyleSheet(
            "QToolButton{font-size:14px;text-align:left;border:0;padding:4px 0;color:#eaeaea;}"
            "QToolButton:hover{text-decoration:underline;}"
        )
        title_btn.setCursor(Qt.PointingHandCursor)
        title_btn.clicked.connect(lambda _, g=game: self.item_clicked.emit(g))
        title_btn.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        lay.addWidget(title_btn)

        installed = bool(game.get("installed"))
        btn_install = QPushButton("Starten" if installed else "Installieren")
        btn_install.setCursor(Qt.PointingHandCursor)
        if installed:
            btn_install.clicked.connect(lambda _=None, g=game: self.start_requested.emit(g))
        else:
            btn_install.clicked.connect(lambda _=None, g=game: self.install_requested.emit(g))

        btn_uninstall = QPushButton("Deinstallieren")
        btn_uninstall.setCursor(Qt.PointingHandCursor)
        btn_uninstall.setEnabled(installed)
        btn_uninstall.clicked.connect(lambda _=None, g=game: self.uninstall_requested.emit(g))

        install_row = QHBoxLayout()
        install_row.setContentsMargins(0, 0, 0, 0)
        install_row.setSpacing(0)
        install_row.addStretch()
        install_row.addWidget(btn_install)
        install_row.addSpacing(8)
        install_row.addWidget(btn_uninstall)
        install_row.addStretch()
        lay.addLayout(install_row)

        # --- KEINE DESCRIPTION MEHR IN LIBRARY! ---
        # (absichtlich entfernt)

        return card


    # Helpers
    def _placeholder_pm(self) -> QPixmap:
        if self._ph_pm and not self._ph_pm.isNull():
            return self._ph_pm
        pm = QPixmap(self.CARD_W-20, self.COVER_H); pm.fill(Qt.black)
        self._ph_pm = pm
        return pm

    def _attach_fader(self, widget, start_opacity: float):
        eff = QGraphicsOpacityEffect(widget); eff.setOpacity(max(0.0, min(1.0, start_opacity)))
        widget.setGraphicsEffect(eff)

    def _fade_in(self, widget, duration_ms: int):
        eff = widget.graphicsEffect()
        if not isinstance(eff, QGraphicsOpacityEffect):
            eff = QGraphicsOpacityEffect(widget); eff.setOpacity(0.0); widget.setGraphicsEffect(eff)
        anim = QPropertyAnimation(eff, b"opacity", widget)
        anim.setDuration(max(60, duration_ms)); anim.setStartValue(eff.opacity()); anim.setEndValue(1.0)
        anim.setEasingCurve(QEasingCurve.OutCubic); anim.start(QPropertyAnimation.DeleteWhenStopped)

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
