import sys
import re
from pathlib import Path
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QToolBar, QLabel, QWidget,
    QSizePolicy, QStackedWidget, QVBoxLayout, QToolButton, QWidgetAction, QHBoxLayout
)
from PySide6.QtGui import QAction, QActionGroup, QIcon, QPixmap, QPainter, QPainterPath
from PySide6.QtCore import Qt, QSize, Signal

from pages.shop_page import ShopPage
from pages.cart_page import CartPage
from pages.library_page import LibraryPage
from pages.profile_page import ProfilePage
from pages.admin_page import AdminPage
from pages.game_info_page import GameInfoPage
from pages.game_upload_page import GameUploadPage
from services.install_worker import start_install_thread
from data import store


class SimplePage(QWidget):
    def __init__(self, title: str):
        super().__init__()
        lay = QVBoxLayout(self)
        lbl = QLabel(title, alignment=Qt.AlignCenter)
        lbl.setStyleSheet("font-size: 28px; font-weight: 600;")
        lay.addWidget(lbl)


# --------- Warenkorb-Button ----------
class CartButton(QWidget):
    clicked = Signal()
    def __init__(self, parent=None, icon_path: str = "assets/cart.png"):
        super().__init__(parent)
        lay = QHBoxLayout(self); lay.setContentsMargins(0,0,0,0); lay.setSpacing(6)
        abs_icon = (Path(__file__).resolve().parent / icon_path).resolve()
        self.btn = QToolButton(self)
        icon = QIcon(str(abs_icon))
        if icon.isNull(): self.btn.setText("🛒")
        else: self.btn.setIcon(icon)
        self.btn.setIconSize(QSize(24, 24))
        self.btn.setToolButtonStyle(Qt.ToolButtonIconOnly)
        self.btn.setFixedSize(32, 32)
        self.btn.clicked.connect(self.clicked.emit)
        self.label = QLabel("", self); self.label.setAlignment(Qt.AlignCenter)
        self.label.setStyleSheet("color: #e8e8e8; font-size: 12px;")
        lay.addWidget(self.btn); lay.addWidget(self.label)
        self.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
    def set_count(self, n: int):
        self.label.setText(f"({n})" if n > 0 else "")


# --------- Profil-Chip (rund maskiert) ----------
class ProfileChip(QWidget):
    clicked = Signal()
    def __init__(self):
        super().__init__()
        lay = QHBoxLayout(self); lay.setContentsMargins(6,2,6,2); lay.setSpacing(8)
        self.avatar = QLabel(); self.avatar.setFixedSize(24, 24)
        self.name = QLabel("Profile"); self.name.setStyleSheet("color: #e8e8e8; font-size: 16px;")
        lay.addWidget(self.avatar); lay.addWidget(self.name)
        self.setCursor(Qt.PointingHandCursor)
    def mouseReleaseEvent(self, e): self.clicked.emit()
    def _circle_pixmap(self, pm: QPixmap, size: QSize) -> QPixmap:
        s = min(size.width(), size.height())
        if s <= 0 or pm.isNull(): return QPixmap()
        src = pm.scaled(s, s, Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)
        out = QPixmap(s, s); out.fill(Qt.transparent)
        p = QPainter(out); p.setRenderHints(QPainter.Antialiasing | QPainter.SmoothPixmapTransform, True)
        path = QPainterPath(); path.addEllipse(0, 0, s, s)
        p.setClipPath(path); p.drawPixmap(0, 0, src); p.end()
        return out
    def set_user(self, username: str, avatar_path: str | None):
        self.name.setText(username or "Profile")
        if avatar_path and Path(avatar_path).exists():
            pm = QPixmap(avatar_path); circ = self._circle_pixmap(pm, self.avatar.size())
            if not circ.isNull(): self.avatar.setText(""); self.avatar.setPixmap(circ); return
        self.avatar.setPixmap(QPixmap()); self.avatar.setText("👤")


class Main(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Indie-Hain")
        self.resize(1000, 650)

        store.init_db()

        # Warenkorb-/State-Daten
        self.cart: list[dict] = []
        self.cart_ids: set[int] = set()
        self.guest_cart: list[dict] = []
        self.guest_cart_ids: set[int] = set()
        self.owned_ids: set[int] = set()   # ✅ Library-IDs (gekauft)

        # ----- Seiten / Stack -----
        self.stack = QStackedWidget(); self.setCentralWidget(self.stack)
        self.shop_page = ShopPage()
        self.cart_page = CartPage()
        self.library_page = LibraryPage()
        self.profile_page = ProfilePage()
        self.admin_page = AdminPage()
        self.game_info_page = GameInfoPage()
        self.game_upload_page = GameUploadPage()
        self.stack.addWidget(self.game_upload_page)
        self.game_upload_page.back_requested.connect(lambda: self.show_page("Profile"))

        # Signale
        self.shop_page.add_to_cart.connect(self.add_to_cart)
        if hasattr(self.shop_page, "remove_from_cart"):
            self.shop_page.remove_from_cart.connect(self.remove_from_cart)
        self.cart_page.item_removed.connect(self.remove_from_cart)
        self.cart_page.checkout_clicked.connect(self.checkout)
        self.profile_page.game_upload_requested.connect(lambda: self._open_upload_page())

        # Detailseite
        self.shop_page.game_clicked.connect(self.open_game_from_shop)
        self.library_page.item_clicked.connect(self.open_game_from_library)
        self.game_info_page.add_to_cart.connect(self.add_to_cart)       # ✅ richtiger Slot
        self.game_info_page.back_requested.connect(self._on_game_back)

        if hasattr(self.cart_page, "go_to_profile"):
            self.cart_page.go_to_profile.connect(lambda: (self.uncheck_nav(), self.show_page("Profile")))
        if hasattr(self.library_page, "go_to_profile"):
            self.library_page.go_to_profile.connect(lambda: (self.uncheck_nav(), self.show_page("Profile")))
        if hasattr(self.admin_page, "go_to_profile"):
            self.admin_page.go_to_profile.connect(lambda: (self.uncheck_nav(), self.show_page("Profile")))

        self.profile_page.logged_in.connect(self._on_auth_changed)
        self.profile_page.role_changed.connect(self._on_auth_changed)
        if hasattr(self.profile_page, "profile_updated"):
            self.profile_page.profile_updated.connect(self._on_auth_changed)

        # Seiten registrieren
        self.pages = {
            "Shop": self.shop_page,
            "Library": self.library_page,
            "Indie-Verse": SimplePage("🌌 Indie-Verse"),
            "Profile": self.profile_page,
            "Admin": self.admin_page,
            "Cart": self.cart_page,
        }
        for name in ("Shop", "Library", "Indie-Verse", "Profile", "Admin", "Cart"):
            self.stack.addWidget(self.pages[name])

        self.library_page.install_requested.connect(self._on_install_requested)
        self._install_thread = None
        self._install_worker = None

        # ✅ GameInfoPage auch in den Stack aufnehmen (ohne Toolbar-Button)
        self.stack.addWidget(self.game_info_page)

        # Erstes Laden
        self._refresh_library_from_db()
        if hasattr(self.shop_page, "set_cart_ids"):
            self.shop_page.set_cart_ids(self.cart_ids)
        # ✅ Detailseite initial mit States füttern
        self.game_info_page.set_cart_ids(self.cart_ids)
        self.game_info_page.set_owned_ids(self.owned_ids)

        # ----- Toolbar -----
        tb = QToolBar("Navigation")
        tb.setMovable(False); tb.setFloatable(False)
        tb.setContextMenuPolicy(Qt.PreventContextMenu)
        tb.setToolButtonStyle(Qt.ToolButtonTextOnly)
        tb.setIconSize(QSize(32, 32))
        tb.setStyleSheet("""
            QToolBar { spacing: 14px; }
            QToolButton { font-size: 16px; padding: 8px 16px; color: #e8e8e8; }
            QToolButton:hover { background: rgba(255,255,255,0.06); border-radius: 8px; }
            QToolButton:checked { background: #dcdcdc; color: #111; border-radius: 8px; }
        """)
        self.addToolBar(Qt.TopToolBarArea, tb)
        self.tb = tb

        left_spacer = QWidget(); left_spacer.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        tb.addWidget(left_spacer)

        self.group = QActionGroup(self); self.group.setExclusive(True)
        self.actions: dict[str, QAction] = {}
        for name in ("Shop", "Library", "Indie-Verse", "Profile", "Admin"):
            act = QAction(name, self); act.setCheckable(True)
            tb.addAction(act); self.group.addAction(act); self.actions[name] = act
            act.triggered.connect(lambda _, n=name: self.show_page(n))

        # Profil-Chip
        self.profile_chip = ProfileChip()
        self.profile_chip.clicked.connect(lambda: self.show_page("Profile"))
        self.profile_widget_action = QWidgetAction(self)
        self.profile_widget_action.setDefaultWidget(self.profile_chip)
        tb.insertAction(self.actions["Profile"], self.profile_widget_action)
        self.profile_widget_action.setVisible(False)

        right_spacer = QWidget(); right_spacer.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        tb.addWidget(right_spacer)

        self.cart_btn = CartButton(icon_path="assets/cart.png")
        cart_widget_action = QWidgetAction(self); cart_widget_action.setDefaultWidget(self.cart_btn)
        tb.addAction(cart_widget_action)
        end_spacer = QWidget(); end_spacer.setFixedWidth(12); tb.addWidget(end_spacer)
        self.cart_btn.clicked.connect(lambda: (self.uncheck_nav(), self.show_page("Cart")))
        self.cart_btn.set_count(0)

        # Sichtbarkeit Admin-Tab initial
        self._sync_admin_tab_visibility()

        self.statusBar().showMessage("Bereit")
        self.actions["Shop"].setChecked(True)
        self.show_page("Shop")

        # Auto-Login (falls session.json vorhanden)
        if store.load_session():
            self._on_auth_changed()

        # Toolbar initial
        self._sync_profile_chip()

    @staticmethod
    def _slugify(s: str) -> str:
        s = s.lower()
        s = re.sub(r'[^a-z0-9]+', '-', s).strip('-')
        return s

    # --- Helpers ---
    def uncheck_nav(self):
        self.group.setExclusive(False)
        for act in self.actions.values(): act.setChecked(False)
        self.group.setExclusive(True)

    def _refresh_library_from_db(self):
        items = store.get_library_items()
        self.library_page.set_items(items)
        for g in items:
            if not g.get("slug"):
                g["slug"] = self._slugify(g.get("title", ""))   # <-- self._slugify


        # ✅ IDs merken & verteilen
        self.owned_ids = {int(x["id"]) for x in items}
        if hasattr(self.shop_page, "set_owned_ids"):
            self.shop_page.set_owned_ids(self.owned_ids)

        # ✅ Detailseite mit aktuellem State füttern
        self.game_info_page.set_cart_ids(self.cart_ids)
        self.game_info_page.set_owned_ids(self.owned_ids)

    def _on_auth_changed(self):
        # Library ggf. migrieren
        if store.is_logged_in():
            try:
                store.ensure_user_scoped_library(store.session.current_user.id)
            except Exception as e:
                self.statusBar().showMessage(f"Library-Migration fehlgeschlagen: {e}", 4000)

            # OPTION A: Guest-Cart NICHT mergen
            db_cart = store.cart_get_items()
            self.guest_cart.clear()
            self.guest_cart_ids.clear()
            self.cart = db_cart
            self.cart_ids = {int(g["id"]) for g in self.cart}
        else:
            # Logout -> Guest-Ansicht
            self.cart = list(self.guest_cart)
            self.cart_ids = set(self.guest_cart_ids)

        # Gates & Seiten
        if hasattr(self.cart_page, "refresh_gate"): self.cart_page.refresh_gate()
        if hasattr(self.library_page, "refresh_gate"): self.library_page.refresh_gate()
        if hasattr(self.admin_page, "refresh_gate"): self.admin_page.refresh_gate()
        if hasattr(self.shop_page, "refresh"): self.shop_page.refresh()

        # Toolbar / Profile
        self._sync_profile_chip()
        self._sync_admin_tab_visibility()
        self.profile_page.refresh()

        # UI-Listen
        self._refresh_library_from_db()
        self.cart_page.set_items(self.cart)
        self.cart_btn.set_count(len(self.cart))

        # ✅ Shop & Detailseite mit Cart-IDs füttern
        if hasattr(self.shop_page, "set_cart_ids"):
            self.shop_page.set_cart_ids(self.cart_ids)
        self.game_info_page.set_cart_ids(self.cart_ids)

    def _sync_profile_chip(self):
        u = store.session.current_user
        if u:
            shown = (u.username or "").strip() or u.email
            self.profile_chip.set_user(shown, getattr(u, "avatar_path", None))
            self.profile_widget_action.setVisible(True)
            if "Profile" in self.actions: self.actions["Profile"].setVisible(False)
        else:
            self.profile_widget_action.setVisible(False)
            if "Profile" in self.actions: self.actions["Profile"].setVisible(True)

    def _sync_admin_tab_visibility(self):
        is_admin = store.has_role("admin")
        if "Admin" in self.actions:
            self.actions["Admin"].setVisible(is_admin)

    # ----- Warenkorb-Logik -----
    def add_to_cart(self, game: dict):
        gid = int(game["id"])
        if store.is_logged_in():
            if gid in store.cart_get_ids():
                self.statusBar().showMessage("Bereits im Warenkorb", 1200); return
            store.cart_add(game)
            self.cart = store.cart_get_items()
            self.cart_ids = {int(g["id"]) for g in self.cart}
        else:
            if gid in self.guest_cart_ids:
                self.statusBar().showMessage("Bereits im Warenkorb", 1200); return
            self.guest_cart.append(game); self.guest_cart_ids.add(gid)
            self.cart = list(self.guest_cart); self.cart_ids = set(self.guest_cart_ids)

        self.cart_page.set_items(self.cart)
        if hasattr(self.shop_page, "set_cart_ids"): self.shop_page.set_cart_ids(self.cart_ids)
        self.game_info_page.set_cart_ids(self.cart_ids)   # ✅ Detailseite updaten
        self.cart_btn.set_count(len(self.cart))
        self.statusBar().showMessage(f'„{game["title"]}“ zum Warenkorb hinzugefügt', 1500)

    def remove_from_cart(self, game: dict):
        gid = int(game["id"])
        if store.is_logged_in():
            store.cart_remove(gid)
            self.cart = store.cart_get_items()
            self.cart_ids = {int(g["id"]) for g in self.cart}
        else:
            self.guest_cart = [g for g in self.guest_cart if int(g["id"]) != gid]
            self.guest_cart_ids.discard(gid)
            self.cart = list(self.guest_cart); self.cart_ids = set(self.guest_cart_ids)

        self.cart_page.set_items(self.cart)
        if hasattr(self.shop_page, "set_cart_ids"): self.shop_page.set_cart_ids(self.cart_ids)
        self.game_info_page.set_cart_ids(self.cart_ids)   # ✅ Detailseite updaten
        self.cart_btn.set_count(len(self.cart))
        self.statusBar().showMessage(f'„{game["title"]}“ aus Warenkorb entfernt', 1500)

    def checkout(self):
        if not self.cart:
            self.statusBar().showMessage("Warenkorb ist leer.", 1500); return
        if not store.is_logged_in():
            self.uncheck_nav(); self.show_page("Profile")
            self.statusBar().showMessage("Bitte einloggen, um zu bezahlen.", 2000); return

        store.add_many_to_library(self.cart)
        store.cart_clear()
        self.cart.clear(); self.cart_ids.clear()
        if hasattr(self.shop_page, "set_cart_ids"): self.shop_page.set_cart_ids(self.cart_ids)
        self.game_info_page.set_cart_ids(self.cart_ids)   # ✅ leeren
        self.cart_page.set_items(self.cart)
        self.cart_btn.set_count(0)

        self._refresh_library_from_db()
        self.statusBar().showMessage("Kauf abgeschlossen – Titel in Library verschoben.", 2000)
        self.uncheck_nav(); self.show_page("Library")

    def remove_from_library(self, game_id: int):
        store.remove_from_library(game_id)
        self._refresh_library_from_db()
        self.statusBar().showMessage("Titel aus Library entfernt.", 1500)

    def show_page(self, name: str):
        if name == "Admin" and not store.has_role("admin"):
            self.uncheck_nav(); self.show_page("Profile")
            self.statusBar().showMessage("Admin-Rechte erforderlich.", 2000); return
        self.stack.setCurrentWidget(self.pages[name])
        if name in self.actions: self.actions[name].setChecked(True)
        self.statusBar().showMessage(f"{name} geöffnet", 1000)

    def open_game(self, game: dict):
        """Von Shop-Titel-Klick geöffnet."""
        self.game_info_page.set_game(game)
        # ✅ aktuelle States verwenden
        self.game_info_page.set_cart_ids(self.cart_ids)
        self.game_info_page.set_owned_ids(self.owned_ids)
        self.stack.setCurrentWidget(self.game_info_page)

    def show_shop(self):
        self.stack.setCurrentWidget(self.shop_page)

    def _open_game_common(self, game: dict):
        self.game_info_page.set_game(game)
        self.game_info_page.set_cart_ids(self.cart_ids)
        self.game_info_page.set_owned_ids(self.owned_ids)
        self.stack.setCurrentWidget(self.game_info_page)

    def open_game_from_shop(self, game: dict):
        self.game_info_page.set_origin("shop")
        self._open_game_common(game)

    def open_game_from_library(self, game: dict):
        self.game_info_page.set_origin("library")
        self._open_game_common(game)

    def _on_game_back(self):
        origin = getattr(self.game_info_page, "_origin", "shop")
        if origin == "library":
            self.stack.setCurrentWidget(self.library_page)
            # Toolbar-Highlight optional:
            if "Library" in self.actions:
                self.uncheck_nav(); self.actions["Library"].setChecked(True)
        else:
            self.stack.setCurrentWidget(self.shop_page)
            if "Shop" in self.actions:
                self.uncheck_nav(); self.actions["Shop"].setChecked(True)

        # ----- Installation (Library) -----
    def _on_install_requested(self, game: dict):
        title = game.get("title") or ""
        slug = game.get("slug") or self._slugify(title)
        install_dir = Path("./Installed") / slug

        self._install_thread, self._install_worker = start_install_thread(slug, install_dir)
        self._install_worker.progress.connect(self._on_install_progress)
        self._install_worker.finished.connect(self._on_install_finished)
        self._install_worker.finished.connect(self._install_thread.quit)
        self._install_worker.finished.connect(self._install_worker.deleteLater)
        self._install_thread.finished.connect(self._install_thread.deleteLater)

        self.statusBar().showMessage(f"Installiere „{title}“…", 2000)
        self._install_thread.start()

    def _on_install_progress(self, pct: int):
        # TODO: Falls du später eine ProgressBar hast – hier updaten
        pass

    def _on_install_finished(self, ok: bool, msg: str):
        if ok:
            # Library neu zeichnen, damit der Button disabled ist
            self._refresh_library_from_db()
            self.statusBar().showMessage("Installation abgeschlossen.", 2000)
        else:
            self.statusBar().showMessage(f"Installation fehlgeschlagen: {msg}", 4000)

    def _open_upload_page(self):
        self.stack.setCurrentWidget(self.game_upload_page)
        self.statusBar().showMessage("Game Upload", 1500)

if __name__ == "__main__":
    app = QApplication(sys.argv)
    win = Main()
    win.show()
    sys.exit(app.exec())
