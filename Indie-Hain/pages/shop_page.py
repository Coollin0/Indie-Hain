# pages/shop_page.py
from __future__ import annotations
from typing import Dict, List, Set
from PySide6.QtCore import Qt, QSize, Signal, QObject, QEvent
from PySide6.QtGui import QIcon, QPixmap
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QScrollArea, QFrame, QGridLayout, QToolButton,
    QLabel, QHBoxLayout, QSizePolicy
)

class ShopPage(QWidget):
    add_to_cart = Signal(dict)      # {id:int, title:str, price:float}
    game_clicked = Signal(dict)     # {id, title, price, ...}

    # Demo-Daten – cover_path optional. Falls du Cover-Dateien hast, Pfade hier eintragen.
    DEMO_GAMES: List[Dict] = [
        {"id": 1, "title": "Hollow Knight", "price": 14.99, "description": "Metroidvania im Reich Hallownest."},
        {"id": 2, "title": "Celeste", "price": 19.99, "description": "Präzises Plattforming mit Herz."},
        {"id": 3, "title": "Stardew Valley", "price": 13.99},
        {"id": 4, "title": "Undertale", "price": 9.99},
        {"id": 5, "title": "Cuphead", "price": 19.99},
        {"id": 6, "title": "Dead Cells", "price": 24.99},
        {"id": 7, "title": "Shovel Knight", "price": 14.99},
        {"id": 8, "title": "Ori and the Blind Forest", "price": 19.99},
    ]

    CARD_W = 180
    COVER_H = 240
    HSPACE = 18
    VSPACE = 22

    def __init__(self):
        super().__init__()
        self._games: List[Dict] = list(self.DEMO_GAMES)
        self._cart_ids: Set[int] = set()
        self._owned_ids: Set[int] = set()

        self._cards: list[QWidget] = []
        self._badge_by_id: dict[int, QLabel] = {}

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

        # Relayout, wenn Viewport-Größe sich ändert
        self.scroll.viewport().installEventFilter(self)

        self._build_cards()
        self._relayout()

    # ---------- Public API ----------
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

    # ---------- Events ----------
    def eventFilter(self, obj: QObject, ev) -> bool:
        if obj is self.scroll.viewport() and ev.type() == QEvent.Resize:
            self._relayout()
        return super().eventFilter(obj, ev)

    # ---------- Build / Layout ----------
    def _build_cards(self):
        # alte Karten entfernen
        for i in reversed(range(self.grid.count())):
            item = self.grid.itemAt(i)
            w = item.widget()
            if w: w.setParent(None)
        self._cards.clear()
        self._badge_by_id.clear()

        for g in self._games:
            self._cards.append(self._create_card(g))

        self._sync_badges()

    def _relayout(self):
        if not self._cards:
            return
        vw = self.scroll.viewport().width()
        cols = max(1, int((vw + self.HSPACE) // (self.CARD_W + self.HSPACE)))
        # neu anordnen
        for i, card in enumerate(self._cards):
            r = i // cols
            c = i % cols
            self.grid.addWidget(card, r, c, Qt.AlignTop)

    # ---------- Card factory ----------
    def _create_card(self, game: Dict) -> QWidget:
        gid = int(game["id"])
        title = game.get("title", "")
        price = float(game.get("price", 0.0))

        card = QFrame()
        card.setObjectName("card")
        card.setFixedWidth(self.CARD_W)
        card.setStyleSheet("""
            QFrame#card {
                background: #1e1e1e; border: 1px solid rgba(255,255,255,0.07);
                border-radius: 12px;
            }
            QFrame#card:hover { border-color: rgba(255,255,255,0.18); }
        """)
        lay = QVBoxLayout(card)
        lay.setContentsMargins(10, 10, 10, 10)
        lay.setSpacing(8)

        # Cover als klickbarer Button
        cover_btn = QToolButton()
        cover_btn.setToolButtonStyle(Qt.ToolButtonIconOnly)
        cover_btn.setIconSize(QSize(self.CARD_W-20, self.COVER_H))
        cover_btn.setFixedSize(self.CARD_W-20, self.COVER_H)
        pm = self._load_cover(game)
        if pm.isNull():
            # Placeholder
            placeholder = QPixmap(self.CARD_W-20, self.COVER_H)
            placeholder.fill(Qt.black)
            pm = placeholder
        cover_btn.setIcon(QIcon(pm))
        cover_btn.clicked.connect(lambda _, g=game: self.game_clicked.emit(g))
        cover_btn.setStyleSheet("border: 0; border-radius: 8px;")
        lay.addWidget(cover_btn)

        # Badge oben links auf dem Cover
        badge = QLabel("", parent=cover_btn)
        badge.setStyleSheet("""
            background: rgba(0,0,0,0.65); color: #e8e8e8; padding: 2px 6px;
            border-radius: 8px; font-size: 11px;
        """)
        badge.move(6, 6)
        badge.hide()
        self._badge_by_id[gid] = badge

        # Titel + Preis Zeile
        meta_row = QHBoxLayout()
        meta_row.setContentsMargins(0, 0, 0, 0)
        meta_row.setSpacing(6)

        title_btn = QToolButton()
        title_btn.setText(title)
        title_btn.setToolButtonStyle(Qt.ToolButtonTextOnly)
        title_btn.setStyleSheet("""
            QToolButton { font-size: 14px; text-align: left; border: 0; padding: 2px 0; color: #eaeaea; }
            QToolButton:hover { text-decoration: underline; }
        """)
        title_btn.clicked.connect(lambda _, g=game: self.game_clicked.emit(g))
        title_btn.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)

        price_lbl = QLabel(self._fmt_price(price))
        price_lbl.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        price_lbl.setStyleSheet("font-size: 13px; color: #cfcfcf;")

        meta_row.addWidget(title_btn, 1)
        meta_row.addWidget(price_lbl, 0)
        lay.addLayout(meta_row)

        return card

    # ---------- Helpers ----------
    def _load_cover(self, game: Dict) -> QPixmap:
        cover = game.get("cover_path")
        if not cover:
            return QPixmap()
        pm = QPixmap(cover)
        if pm.isNull():
            return QPixmap()
        # auf Buttongröße skalieren (wird später nochmal gerendert)
        return pm.scaled(self.CARD_W-20, self.COVER_H, Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)

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
                badge.hide()
