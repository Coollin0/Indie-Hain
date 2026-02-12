# pages/library_page.py
from __future__ import annotations
from typing import Dict, List
from PySide6.QtCore import Qt, QSize, Signal, QObject, QEvent, QPropertyAnimation, QEasingCurve
from PySide6.QtGui import QIcon, QPixmap
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QScrollArea, QFrame, QGridLayout, QToolButton,
    QLabel, QHBoxLayout, QSizePolicy, QGraphicsOpacityEffect, QPushButton,
    QLineEdit, QCheckBox
)
from shiboken6 import isValid as qt_is_valid
from services.env import abs_url
from services.net_image import NetImage

class LibraryPage(QWidget):
    item_clicked = Signal(dict)
    install_requested = Signal(dict)    # <- für gui.py erwartet
    start_requested = Signal(dict)      # ruft Starten auf (wenn installiert)
    uninstall_requested = Signal(dict)  # ruft Deinstallation auf
    open_requested = Signal(dict)       # öffnet Installationsordner
    rescan_requested = Signal()         # Library/Installationen neu scannen
    legacy_path_requested = Signal()   # Legacy-Installationspfad hinzufügen

    CARD_W = 180
    COVER_H = 240
    HSPACE = 18
    VSPACE = 22

    def __init__(self):
        super().__init__()
        self._items: List[Dict] = []
        self._cards: list[QWidget] = []
        self._ph_pm: QPixmap | None = None
        self._visible_items: List[Dict] = []
        self._empty_default = "Noch keine Spiele in deiner Bibliothek."
        self._missing_count = 0

        root = QVBoxLayout(self)
        root.setContentsMargins(24, 16, 24, 16)
        root.setSpacing(12)

        header_row = QHBoxLayout()
        header_row.setContentsMargins(0, 0, 0, 0)
        header_row.setSpacing(12)

        header = QLabel("📚 Deine Bibliothek")
        header.setAlignment(Qt.AlignHCenter)
        header.setStyleSheet("font-size:26px; font-weight:700; margin:8px 0 6px;")
        header_row.addWidget(header, 1)

        self.btn_rescan = QPushButton("Rescan")
        self.btn_rescan.setCursor(Qt.PointingHandCursor)
        self.btn_rescan.setStyleSheet(
            "QPushButton{padding:6px 12px;border-radius:10px;border:1px solid rgba(255,255,255,0.12);"
            "color:#eaeaea;background:#1b1b1b;}"
            "QPushButton:hover{border-color:rgba(255,255,255,0.28);}"
        )
        self.btn_add_path = QPushButton("Pfad hinzufügen")
        self.btn_add_path.setCursor(Qt.PointingHandCursor)
        self.btn_add_path.setStyleSheet(
            "QPushButton{padding:6px 12px;border-radius:10px;border:1px solid rgba(255,255,255,0.12);"
            "color:#eaeaea;background:#1b1b1b;}"
            "QPushButton:hover{border-color:rgba(255,255,255,0.28);}"
        )
        header_row.addWidget(self.btn_add_path, alignment=Qt.AlignRight)
        header_row.addWidget(self.btn_rescan, alignment=Qt.AlignRight)
        root.addLayout(header_row)

        filter_row = QHBoxLayout()
        filter_row.setContentsMargins(0, 0, 0, 0)
        filter_row.setSpacing(12)

        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Suche nach Titel, Slug ...")
        self.search_input.setClearButtonEnabled(True)
        self.search_input.setStyleSheet(
            "QLineEdit{padding:8px 12px;border-radius:12px;border:1px solid rgba(255,255,255,0.12);"
            "color:#eaeaea;background:#151515;}"
            "QLineEdit:focus{border-color:rgba(255,255,255,0.28);}"
        )
        filter_row.addWidget(self.search_input, 1)

        self.chk_installed = QCheckBox("Nur installiert")
        self.chk_installed.setStyleSheet("QCheckBox{color:#c8c8c8;}")
        filter_row.addWidget(self.chk_installed, alignment=Qt.AlignRight)

        self.result_lbl = QLabel("")
        self.result_lbl.setStyleSheet("color:#a8a8a8; font-size:12px;")
        filter_row.addWidget(self.result_lbl, alignment=Qt.AlignRight)

        self.installed_lbl = QLabel("")
        self.installed_lbl.setStyleSheet("color:#8fd3b6; font-size:12px;")
        filter_row.addWidget(self.installed_lbl, alignment=Qt.AlignRight)

        self.missing_lbl = QLabel("")
        self.missing_lbl.setStyleSheet("color:#f0c66b; font-size:12px;")
        filter_row.addWidget(self.missing_lbl, alignment=Qt.AlignRight)

        root.addLayout(filter_row)

        self.scroll = QScrollArea(); self.scroll.setWidgetResizable(True); self.scroll.setFrameShape(QFrame.NoFrame)
        root.addWidget(self.scroll, 1)

        self.grid_host = QWidget()
        self.grid = QGridLayout(self.grid_host)
        self.grid.setContentsMargins(4, 4, 4, 4)
        self.grid.setHorizontalSpacing(self.HSPACE)
        self.grid.setVerticalSpacing(self.VSPACE)
        self.scroll.setWidget(self.grid_host)

        self.empty_lbl = QLabel(self._empty_default)
        self.empty_lbl.setAlignment(Qt.AlignCenter)
        self.empty_lbl.setStyleSheet("color:#a8a8a8; padding:32px; font-size:14px;")
        self.empty_lbl.hide()
        root.addWidget(self.empty_lbl)

        self._img = NetImage(self)
        self.scroll.viewport().installEventFilter(self)
        self.btn_rescan.clicked.connect(self.rescan_requested.emit)
        self.btn_add_path.clicked.connect(self.legacy_path_requested.emit)
        self.search_input.textChanged.connect(self._apply_filters)
        self.chk_installed.toggled.connect(self._apply_filters)

    # API
    def set_items(self, items: List[Dict]):
        self._items = list(items or [])
        self._apply_filters()

    def set_games(self, games: List[Dict]):
        self.set_items(games)

    def set_missing_count(self, count: int):
        self._missing_count = max(0, int(count))
        self._update_count()

    # Build/Layout
    def _build_cards(self):
        while self.grid.count():
            it = self.grid.takeAt(0)
            w = it.widget()
            if w:
                w.setParent(None)
                w.deleteLater()
        self._cards.clear()

        if not self._visible_items:
            self.empty_lbl.setText(
                self._empty_default if not self._items else "Keine Treffer."
            )
            self.grid_host.hide(); self.empty_lbl.show()
            return

        self.empty_lbl.hide(); self.grid_host.show()

        for g in self._visible_items:
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

    def _apply_filters(self):
        self._visible_items = self._filtered_items()
        self._build_cards()
        self._relayout()
        self._update_count()

    def _filtered_items(self) -> List[Dict]:
        query = self.search_input.text().strip().lower()
        installed_only = self.chk_installed.isChecked()
        filtered: List[Dict] = []
        for item in self._items:
            if installed_only and not item.get("installed"):
                continue
            if query:
                title = str(item.get("title") or "").lower()
                slug = str(item.get("slug") or "").lower()
                if query not in title and query not in slug:
                    continue
            filtered.append(item)
        return filtered

    def _update_count(self):
        total = len(self._items)
        visible = len(self._visible_items)
        installed = sum(1 for item in self._items if item.get("installed"))
        if total == 0:
            self.result_lbl.setText("")
            self.installed_lbl.setText("")
            self.missing_lbl.setText("")
        else:
            self.result_lbl.setText(f"{visible} von {total}")
            self.installed_lbl.setText(f"Installiert: {installed}")
            if self._missing_count:
                self.missing_lbl.setText(f"Fehlend: {self._missing_count}")
            else:
                self.missing_lbl.setText("")

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

        btn_open = QPushButton("Ordner")
        btn_open.setCursor(Qt.PointingHandCursor)
        btn_open.setEnabled(installed)
        btn_open.clicked.connect(lambda _=None, g=game: self.open_requested.emit(g))

        install_row = QHBoxLayout()
        install_row.setContentsMargins(0, 0, 0, 0)
        install_row.setSpacing(0)
        install_row.addStretch()
        install_row.addWidget(btn_install)
        install_row.addSpacing(8)
        install_row.addWidget(btn_open)
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
