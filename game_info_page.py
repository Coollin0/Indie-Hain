# pages/game_info_page.py
from __future__ import annotations
from typing import Dict, Optional, Set
from distribution_client.downloader import get_manifest, install_from_manifest
from services.install_worker import start_install_thread
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QScrollArea, QFrame, QSizePolicy
)
from services.env import abs_url, install_root
from services.net_image import NetImage
from shiboken6 import isValid as qt_is_valid

class GameInfoPage(QWidget):
    """
    Detailseite für ein Spiel (vom Shop aus geöffnet).
    Zeigt: Cover, Titel, Preis, Beschreibung und Buttons (Zurück, In den Warenkorb).
    """
    add_to_cart = Signal(dict)     # {id:int, title:str, price:float}
    back_requested = Signal()

    def __init__(self):
        super().__init__()
        self._game: Optional[Dict] = None
        self._cart_ids: Set[int] = set()
        self._owned_ids: Set[int] = set()
        self._install_thread = None
        self._install_worker = None

        root = QVBoxLayout(self)
        root.setContentsMargins(40, 30, 40, 30)
        root.setSpacing(16)

        # Header
        self.title_lbl = QLabel("", alignment=Qt.AlignLeft)
        self.title_lbl.setStyleSheet("font-size:28px; font-weight:700;")
        root.addWidget(self.title_lbl)

        # Content
        content_row = QHBoxLayout()
        content_row.setSpacing(24)
        root.addLayout(content_row)

        # Cover links
        self.cover_lbl = QLabel()
        self.cover_lbl.setFixedSize(240, 320)
        self.cover_lbl.setStyleSheet("background:#222; border-radius:12px;")
        self.cover_lbl.setAlignment(Qt.AlignCenter)
        content_row.addWidget(self.cover_lbl)

        # Info rechts
        info_col = QVBoxLayout()
        info_col.setSpacing(12)
        content_row.addLayout(info_col)

        self.price_lbl = QLabel("")
        self.price_lbl.setStyleSheet("font-size:18px; font-weight:600;")
        info_col.addWidget(self.price_lbl)

        # Beschreibung (scrollbar)
        desc_scroll = QScrollArea()
        desc_scroll.setWidgetResizable(True)
        desc_scroll.setFrameShape(QFrame.NoFrame)
        info_col.addWidget(desc_scroll, 1)

        self.desc_widget = QWidget()
        self.desc_layout = QVBoxLayout(self.desc_widget)
        self.desc_layout.setContentsMargins(0, 0, 0, 0)

        self.desc_lbl = QLabel("")
        self.desc_lbl.setWordWrap(True)
        self.desc_lbl.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Maximum)
        self.desc_layout.addWidget(self.desc_lbl)
        self.desc_layout.addStretch(1)

        desc_scroll.setWidget(self.desc_widget)

        # Buttons
        btn_row = QHBoxLayout()
        btn_row.addStretch(1)
        self.back_btn = QPushButton("Zurück zum Shop")
        self.cart_btn = QPushButton("In den Warenkorb")
        self.cart_btn.setDefault(True)
        self._origin = "shop"  # default
        self.back_btn.setText("Zurück zum Shop")  # default
        btn_row.addWidget(self.back_btn)
        btn_row.addWidget(self.cart_btn)
        root.addLayout(btn_row)

        self.back_btn.clicked.connect(self.back_requested.emit)
        self.cart_btn.clicked.connect(self._emit_add_to_cart)

        self._img = NetImage(self)
        self.cover_big = QLabel(alignment=Qt.AlignCenter)
        self.cover_big.setMinimumHeight(240)

    # ---------- Public API ----------
    def set_game(self, game: Dict):
        """Spiel setzen und UI füllen. game: {id, title, price, description?, cover_path?, cover_url?}"""
        from shiboken6 import isValid as qt_is_valid
        self._game = game

        # --- Titel & Preis ---
        title = game.get("title") or "Unbenannt"
        self.title_lbl.setText(title)
        price = float(game.get("price") or 0.0)
        self.price_lbl.setText(
            f"Preis: {price:,.2f} €".replace(",", "X").replace(".", ",").replace("X", ".")
        )

        # --- Beschreibung ---
        desc = game.get("description") or "Keine Beschreibung vorhanden."
        fm = self.desc_lbl.fontMetrics()
        elided = fm.elidedText(desc, Qt.ElideRight, self.desc_lbl.width() or 360)
        self.desc_lbl.setText(elided)

        # --- Cover (lokal oder remote) ---
        cover_path = game.get("cover_path") or ""
        cover_url = game.get("cover_url") or ""

        # Lokales Cover zuerst versuchen
        pixmap_set = False
        if cover_path:
            pm = QPixmap(cover_path)
            if not pm.isNull():
                self.cover_lbl.setPixmap(
                    pm.scaled(self.cover_lbl.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation)
                )
                pixmap_set = True

        # Remote (falls vorhanden)
        if cover_url and not pixmap_set:
            url = abs_url(cover_url)
            def _on_img(pm: QPixmap):
                if not qt_is_valid(self.cover_lbl):
                    return
                if pm.isNull():
                    self.cover_lbl.setText("Kein Cover")
                else:
                    self.cover_lbl.setPixmap(
                        pm.scaled(self.cover_lbl.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation)
                    )
            self._img.load(url, _on_img, guard=self.cover_lbl)

        if not cover_url and not cover_path:
            self.cover_lbl.setText("Kein Cover")

        # --- Großes Cover (z. B. Header) ---
        if cover_url:
            url = abs_url(cover_url)
            def _on_big(pm: QPixmap):
                if not qt_is_valid(self.cover_big):
                    return
                if pm.isNull():
                    self.cover_big.setText("Kein Cover")
                else:
                    scaled = pm.scaledToHeight(240, Qt.SmoothTransformation)
                    self.cover_big.setPixmap(scaled)
            self._img.load(url, _on_big, guard=self.cover_big)
        else:
            self.cover_big.setText("Kein Cover")

        # --- Buttons aktualisieren ---
        self._sync_buttons()


    def set_cart_ids(self, ids: Set[int]):
        self._cart_ids = set(ids)
        self._sync_buttons()

    def set_owned_ids(self, ids: Set[int]):
        self._owned_ids = set(ids)
        self._sync_buttons()

    # ---------- Internals ----------
    def _sync_buttons(self):
        if not self._game:
            self.cart_btn.setEnabled(False)
            self.cart_btn.setText("In den Warenkorb")
            return
        gid = int(self._game["id"])
        if gid in self._owned_ids:
            self.cart_btn.setEnabled(False)
            self.cart_btn.setText("Bereits gekauft")
        elif gid in self._cart_ids:
            self.cart_btn.setEnabled(False)
            self.cart_btn.setText("Im Warenkorb")
        else:
            self.cart_btn.setEnabled(True)
            self.cart_btn.setText("In den Warenkorb")

    def _emit_add_to_cart(self):
        if self._game:
            self.add_to_cart.emit({
                "id": int(self._game["id"]),
                "title": self._game.get("title", ""),
                "price": float(self._game.get("price", 0.0)),
            })

    def set_origin(self, origin: str):
        """origin: 'shop' oder 'library'"""
        self._origin = "library" if origin == "library" else "shop"
        if self._origin == "library":
            self.back_btn.setText("Zurück zur Library")
        else:
            self.back_btn.setText("Zurück zum Shop")

    def on_install_clicked(self, game):
        slug = game["slug"]  # sicherstellen, dass dein game dict den slug hat
        install_dir = install_root() / slug

        self._install_thread, self._install_worker = start_install_thread(slug, install_dir, parent = self,)
        self._install_worker.progress.connect(self._on_install_progress)
        self._install_worker.finished.connect(self._on_install_finished)

        # Thread aufräumen
        self._install_worker.finished.connect(self._install_thread.quit)
        self._install_worker.finished.connect(self._install_worker.deleteLater)
        self._install_thread.finished.connect(self._install_thread.deleteLater)

        self._install_thread.start()

    def _on_install_progress(self, pct: int):
        # setze z.B. einen ProgressBar-Wert
        pass

    def _on_install_finished(self, ok: bool, msg: str):
        if ok:
            # UI: Status „Installiert“, Button deaktivieren, etc.
            pass
        else:
            # Fehlermeldung anzeigen
            pass
