from __future__ import annotations
from typing import Dict, List
from pathlib import Path
from PySide6.QtCore import Qt, QSize, Signal, QObject, QEvent
from PySide6.QtGui import QIcon, QPixmap
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QScrollArea, QFrame, QGridLayout,
    QToolButton, QLabel, QHBoxLayout, QSizePolicy, QPushButton
)
INSTALL_BASE = Path("./Installed")

class LibraryPage(QWidget):
    install_requested = Signal(dict)   # emits the game dict (must include 'slug')
    """
    Grid-Ansicht wie Steam: Cover-Karten, darunter Name (kein Preis).
    - set_items(items: List[Dict])  -> baut die Karten
    - item_clicked:dict             -> Signal beim Öffnen einer Detailseite
    - refresh_gate()                -> no-op für Kompatibilität
    """
    item_clicked = Signal(dict)
    # Optional: Signal bleibt vorhanden, wird aber NICHT benutzt (damit gui.py nicht bricht)
    # remove_item = Signal(int)

    CARD_W  = 180
    COVER_H = 240
    HSPACE  = 18
    VSPACE  = 22

    def __init__(self):
        super().__init__()
        self._items: List[Dict] = []
        self._cards: list[QWidget] = []

        root = QVBoxLayout(self)
        root.setContentsMargins(24, 16, 24, 16)
        root.setSpacing(12)

        header = QLabel("🎮 Deine Library", alignment=Qt.AlignHCenter)
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

        # Re-Layout bei Größenänderung
        self.scroll.viewport().installEventFilter(self)

    # ----- Public API -----
    def set_items(self, items: List[Dict]):
        self._items = list(items)
        self._build_cards()
        self._relayout()

    def refresh_gate(self):
        pass

    # ----- Events -----
    def eventFilter(self, obj: QObject, ev) -> bool:
        if obj is self.scroll.viewport() and ev.type() == QEvent.Resize:
            self._relayout()
        return super().eventFilter(obj, ev)

    # ----- Build / Layout -----
    def _build_cards(self):
        for i in reversed(range(self.grid.count())):
            w = self.grid.itemAt(i).widget()
            if w: w.setParent(None)
        self._cards.clear()

        for g in self._items:
            self._cards.append(self._create_card(g))

    def _relayout(self):
        if not self._cards:
            return
        vw = self.scroll.viewport().width()
        cols = max(1, int((vw + self.HSPACE) // (self.CARD_W + self.HSPACE)))
        for i, card in enumerate(self._cards):
            r, c = divmod(i, cols)
            self.grid.addWidget(card, r, c, Qt.AlignTop)

    # ----- Card factory -----
    def _create_card(self, game: Dict) -> QWidget:
        title = game.get("title", "")

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
        lay.setContentsMargins(10,10,10,10)
        lay.setSpacing(8)

        # Cover (klickbar)
        cover_btn = QToolButton()
        cover_btn.setToolButtonStyle(Qt.ToolButtonIconOnly)
        cover_btn.setIconSize(QSize(self.CARD_W-20, self.COVER_H))
        cover_btn.setFixedSize(self.CARD_W-20, self.COVER_H)
        pm = self._load_cover(game)
        if pm.isNull():
            placeholder = QPixmap(self.CARD_W-20, self.COVER_H); placeholder.fill(Qt.black); pm = placeholder
        cover_btn.setIcon(QIcon(pm))
        cover_btn.setStyleSheet("border:0; border-radius:8px;")
        cover_btn.clicked.connect(lambda _, g=game: self.item_clicked.emit(g))
        lay.addWidget(cover_btn)

        # Titelzeile + Install-Button
        row = QHBoxLayout(); row.setContentsMargins(0,0,0,0); row.setSpacing(8)

        title_btn = QToolButton()
        title_btn.setText(title)
        title_btn.setToolButtonStyle(Qt.ToolButtonTextOnly)
        title_btn.setStyleSheet("""
            QToolButton { font-size:14px; text-align:left; border:0; padding:2px 0; color:#eaeaea; }
            QToolButton:hover { text-decoration: underline; }
        """)
        title_btn.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        title_btn.clicked.connect(lambda _, g=game: self.item_clicked.emit(g))
        row.addWidget(title_btn, 1)

        btn_install = QPushButton("Installieren")
        btn_install.setEnabled(not self._is_installed(game))
        btn_install.clicked.connect(lambda _, g=game: self.install_requested.emit(g))
        row.addWidget(btn_install)

        lay.addLayout(row)

        return card

    # ----- Helpers -----
    def _load_cover(self, game: Dict) -> QPixmap:
        cover = game.get("cover_path")
        if not cover: return QPixmap()
        pm = QPixmap(cover)
        if pm.isNull(): return QPixmap()
        return pm.scaled(self.CARD_W-20, self.COVER_H, Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)
    
    def _is_installed(self, game: dict) -> bool:
        slug = game.get("slug") or str(game.get("id"))
        return (INSTALL_BASE / slug).exists()
