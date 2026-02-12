# pages/dev_games_page.py
from __future__ import annotations
from typing import Dict, List

from PySide6.QtCore import Qt, QSize, Signal
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QScrollArea, QFrame, QGridLayout,
    QHBoxLayout, QPushButton, QSizePolicy
)


class DevGamesPage(QWidget):
    edit_requested = Signal(dict)       # später für Edit-Dialog
    buyers_requested = Signal(dict)     # später für Käuferliste
    unpublish_requested = Signal(dict)  # entfernt App aus dem Shop
    upload_requested = Signal()

    CARD_W = 230
    CARD_H = 180

    def __init__(self, parent=None):
        super().__init__(parent)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(32, 24, 32, 24)
        outer.setSpacing(16)

        title_row = QHBoxLayout()
        title = QLabel("🛠️  Deine Games")
        title.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        title.setStyleSheet("font-size: 26px; font-weight: 600; color: #f0f0f0;")
        title_row.addWidget(title)
        title_row.addStretch(1)

        self.btn_upload = QPushButton("Game Upload")
        self.btn_upload.setCursor(Qt.PointingHandCursor)
        self.btn_upload.clicked.connect(self.upload_requested.emit)
        title_row.addWidget(self.btn_upload)
        outer.addLayout(title_row)

        self.info_lbl = QLabel("Hier siehst du alle Games, die du als Dev hochgeladen hast.")
        self.info_lbl.setStyleSheet("font-size: 13px; color: #b0b0b0;")
        outer.addWidget(self.info_lbl)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.NoFrame)
        outer.addWidget(self.scroll, 1)

        self._host = QWidget()
        self._grid = QGridLayout(self._host)
        self._grid.setContentsMargins(0, 0, 0, 0)
        self._grid.setHorizontalSpacing(24)
        self._grid.setVerticalSpacing(24)
        self.scroll.setWidget(self._host)

        self._games: List[Dict] = []

    # ---------- Public API ----------
    def set_items(self, games: List[Dict]):
        # alte Cards entfernen
        while self._grid.count():
            item = self._grid.takeAt(0)
            w = item.widget()
            if w is not None:
                w.deleteLater()

        self._games = list(games)
        if not self._games:
            self.info_lbl.setText("Noch keine Games hochgeladen.")
        else:
            self.info_lbl.setText("")

        cols = 3
        for idx, g in enumerate(self._games):
            r, c = divmod(idx, cols)
            card = self._create_card(g)
            self._grid.addWidget(card, r, c, Qt.AlignTop)

    # ---------- intern ----------
    def _create_card(self, game: Dict) -> QWidget:
        title = str(game.get("title") or "Unbenannt")
        price = float(game.get("price") or 0.0)
        sale = float(game.get("sale_percent") or 0.0)
        purchase_count = int(game.get("purchase_count") or 0)
        approved_raw = game.get("is_approved")
        is_approved = str(approved_raw).strip().lower() in {"1", "true", "yes", "approved"}

        card = QFrame()
        card.setObjectName("devcard")
        card.setFixedWidth(self.CARD_W)
        card.setStyleSheet("""
            QFrame#devcard {
                background: #1e1e1e;
                border-radius: 12px;
                border: 1px solid rgba(255,255,255,0.07);
            }
            QFrame#devcard:hover {
                border-color: rgba(255,255,255,0.18);
            }
        """)
        lay = QVBoxLayout(card)
        lay.setContentsMargins(12, 10, 12, 10)
        lay.setSpacing(6)

        lbl_title = QLabel(title)
        lbl_title.setWordWrap(True)
        lbl_title.setStyleSheet("font-size: 14px; font-weight: 600; color: #f5f5f5;")
        title_row = QHBoxLayout()
        title_row.setContentsMargins(0, 0, 0, 0)
        title_row.setSpacing(8)
        title_row.addWidget(lbl_title, 1)

        status_dot = QFrame()
        status_dot.setFixedSize(10, 10)
        if is_approved:
            status_dot.setStyleSheet("background:#35c759; border-radius:5px;")
            status_dot.setToolTip("Approved")
        else:
            status_dot.setStyleSheet("background:#ff4d4f; border-radius:5px;")
            status_dot.setToolTip("Noch nicht approved")
        title_row.addWidget(status_dot, 0, Qt.AlignTop | Qt.AlignRight)
        lay.addLayout(title_row)

        # Preis + Rabatt
        if sale > 0:
            sale_price = price * (100.0 - sale) / 100.0
            lbl_price = QLabel(f"{price:.2f} € → {sale_price:.2f} € (-{int(sale)}%)")
            lbl_price.setStyleSheet(
                "font-size: 13px; color: #ffdf5a;"
            )
        else:
            lbl_price = QLabel(f"{price:.2f} €")
            lbl_price.setStyleSheet("font-size: 13px; color: #d0d0d0;")

        lay.addWidget(lbl_price)

        # Käufe
        lbl_stats = QLabel(f"{purchase_count} Käufe")
        lbl_stats.setStyleSheet("font-size: 12px; color: #a0a0a0;")
        lay.addWidget(lbl_stats)

        lay.addStretch()

        # Buttons unten (für später)
        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(6)

        btn_edit = QPushButton("Bearbeiten")
        btn_edit.setCursor(Qt.PointingHandCursor)
        btn_edit.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        btn_edit.clicked.connect(lambda _, g=game: self.edit_requested.emit(g))

        btn_buyers = QPushButton("Käufer")
        btn_buyers.setCursor(Qt.PointingHandCursor)
        btn_buyers.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        btn_buyers.clicked.connect(lambda _, g=game: self.buyers_requested.emit(g))

        btn_unpublish = QPushButton("Aus Shop entfernen")
        btn_unpublish.setCursor(Qt.PointingHandCursor)
        btn_unpublish.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        btn_unpublish.setEnabled(is_approved)
        btn_unpublish.clicked.connect(lambda _, g=game: self.unpublish_requested.emit(g))
        btn_unpublish.setStyleSheet(
            "QPushButton{background:#5a2a2a;color:#ffecec;border:1px solid #7a3a3a;border-radius:8px;padding:6px 8px;}"
            "QPushButton:hover{background:#6c3333;border-color:#934646;}"
            "QPushButton:pressed{background:#4a2323;}"
            "QPushButton:disabled{background:#303030;color:#8f8f8f;border-color:#3f3f3f;}"
        )
        if not is_approved:
            btn_unpublish.setToolTip("Bereits nicht im Shop")

        row.addWidget(btn_edit)
        row.addWidget(btn_buyers)
        row.addWidget(btn_unpublish)
        lay.addLayout(row)

        return card
