import sys
import re
import os
import subprocess
from pathlib import Path
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QToolBar, QLabel, QWidget,
    QSizePolicy, QStackedWidget, QVBoxLayout, QToolButton, QWidgetAction, QHBoxLayout,
    QDialog, QFormLayout, QLineEdit, QTextEdit, QDialogButtonBox,
    QDoubleSpinBox, QSpinBox, QListWidget, QListWidgetItem
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
from pages.dev_games_page import DevGamesPage

from services.install_worker import start_install_thread
from services import shop_api
from services import dev_api   # NEU
from services.net_image import NetImage
from services.env import abs_url
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
        self._net_image = NetImage(self)
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
        if avatar_path:
            if avatar_path.startswith("http") or avatar_path.startswith("/"):
                url = abs_url(avatar_path)
                def _on_ready(pm: QPixmap):
                    circ = self._circle_pixmap(pm, self.avatar.size())
                    if not circ.isNull():
                        self.avatar.setText("")
                        self.avatar.setPixmap(circ)
                    else:
                        self.avatar.setPixmap(QPixmap())
                        self.avatar.setText("👤")
                self._net_image.load(url, _on_ready, guard=self)
                return
            if Path(avatar_path).exists():
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
        self.owned_ids: set[int] = set()   # Library-IDs (gekauft)

        # ----- Seiten / Stack -----
        self.stack = QStackedWidget(); self.setCentralWidget(self.stack)
        self.shop_page = ShopPage()
        self.cart_page = CartPage()
        self.library_page = LibraryPage()
        self.profile_page = ProfilePage()
        self.admin_page = AdminPage()
        self.game_info_page = GameInfoPage()
        self.game_upload_page = GameUploadPage()
        self.admin_requests_page = None  # Lazy: wird erst beim Öffnen erzeugt
        self.dev_games_page = DevGamesPage()   # NEU
         # DevGames: Buttons verdrahten
        self.dev_games_page.edit_requested.connect(self._on_dev_edit_requested)
        self.dev_games_page.buyers_requested.connect(self._on_dev_buyers_requested)


        self.stack.addWidget(self.game_upload_page)
        self.game_upload_page.back_requested.connect(lambda: self.show_page("Profile"))

        # Signale
        self.shop_page.add_to_cart.connect(self.add_to_cart)
        if hasattr(self.shop_page, "remove_from_cart"):
            self.shop_page.remove_from_cart.connect(self.remove_from_cart)
        self.cart_page.remove_requested.connect(self._on_cart_remove_requested)
        self.cart_page.checkout_requested.connect(self.checkout)
        self.profile_page.game_upload_requested.connect(lambda: self._open_upload_page())

        # Detailseite
        self.shop_page.game_clicked.connect(self.open_game_from_shop)
        self.library_page.item_clicked.connect(self.open_game_from_library)
        self.game_info_page.add_to_cart.connect(self.add_to_cart)
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
            "DevGames": self.dev_games_page,   # NEU
        }
        for name in ("Shop", "Library", "Indie-Verse", "Profile", "Admin", "Cart", "DevGames"):
            self.stack.addWidget(self.pages[name])


        self.library_page.install_requested.connect(self._on_install_requested)
        if hasattr(self.library_page, "start_requested"):
            self.library_page.start_requested.connect(self._on_start_requested)
        if hasattr(self.library_page, "uninstall_requested"):
            self.library_page.uninstall_requested.connect(self._on_uninstall_requested)
        self._install_thread = None
        self._install_worker = None
        self._install_focus_refresh()

        # GameInfoPage in den Stack (ohne Toolbar-Button)
        self.stack.addWidget(self.game_info_page)

        # Erstes Laden
        self._refresh_library_from_db()
        if hasattr(self.shop_page, "set_cart_ids"):
            self.shop_page.set_cart_ids(self.cart_ids)
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
        self.dev_action = QAction("Meine Games", self)
        self.dev_action.setCheckable(True)
        tb.addAction(self.dev_action)
        self.group.addAction(self.dev_action)
        self.dev_action.triggered.connect(lambda: self.show_page("DevGames"))
        self.dev_action.setVisible(False)   # wird abhängig von Rolle eingeblendet

        # Profil-Chip
        self.profile_chip = ProfileChip()
        self.profile_chip.clicked.connect(lambda: self.show_page("Profile"))
        self.profile_widget_action = QWidgetAction(self)
        self.profile_widget_action.setDefaultWidget(self.profile_chip)
        tb.insertAction(self.actions["Profile"], self.profile_widget_action)
        self.profile_widget_action.setVisible(False)

        right_spacer = QWidget(); right_spacer.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        tb.addWidget(right_spacer)

        # --- Admin-only: Game Anfragen (Toolbar) ---
        self.admin_requests_action = QAction("Game Anfragen", self)
        self.admin_requests_action.setCheckable(False)
        self.admin_requests_action.triggered.connect(self._open_admin_requests)
        tb.addAction(self.admin_requests_action)
        self.admin_requests_action.setVisible(False)  # initial versteckt

        # Warenkorb rechts
        self.cart_btn = CartButton(icon_path="assets/cart.png")
        cart_widget_action = QWidgetAction(self); cart_widget_action.setDefaultWidget(self.cart_btn)
        tb.addAction(cart_widget_action)
        end_spacer = QWidget(); end_spacer.setFixedWidth(12); tb.addWidget(end_spacer)
        self.cart_btn.clicked.connect(lambda: (self.uncheck_nav(), self.show_page("Cart")))
        self.cart_btn.set_count(0)

        # Sichtbarkeit Admin-/Dev-Tabs initial
        self._sync_admin_tab_visibility()
        self._sync_dev_tab_visibility()


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
        # 1) Library-Items aus lokaler DB
        items = store.get_library_items()

        merged = []
        for lib_item in items:
            gid = int(lib_item["id"])

            # Start: Library-Daten
            g = dict(lib_item)

            # Titel/Slug
            if not g.get("slug"):
                g["slug"] = self._slugify(g.get("title", ""))
            slug = g.get("slug") or self._slugify(g.get("title", ""))

            # 2) Shop-Metadaten, falls verfügbar
            from_shop = None
            try:
                for it in getattr(self.shop_page, "_games", []):
                    if int(it.get("id", -1)) == gid:
                        from_shop = it
                        break
            except:
                pass

            if from_shop:
                # Shop hat Priorität für Cover/Beschreibung
                g["cover_url"] = from_shop.get("cover_url") or ""
                g["description"] = from_shop.get("description") or ""
            else:
                # 3) Wenn Shop noch nicht geladen → Backend anfragen
                try:
                    api_game = shop_api.get_public_game(gid)
                    if isinstance(api_game, dict):
                        g["cover_url"] = api_game.get("cover_url") or ""
                        g["description"] = api_game.get("description") or ""
                except Exception as e:
                    print("Fehler beim Nachladen für Library:", e)
                    g.setdefault("cover_url", "")
                    g.setdefault("description", "")

            # Install-Status
            install_dir = Path("./Installed") / slug
            g["install_dir"] = str(install_dir)
            g["installed"] = install_dir.exists()

            merged.append(g)

        # 4) Library updaten
        self.library_page.set_items(merged)

        # 5) owned_ids setzen
        self.owned_ids = {int(x["id"]) for x in merged}
        if hasattr(self.shop_page, "set_owned_ids"):
            self.shop_page.set_owned_ids(self.owned_ids)

        # 6) GameInfo synchronisieren
        self.game_info_page.set_cart_ids(self.cart_ids)
        self.game_info_page.set_owned_ids(self.owned_ids)

    def _refresh_dev_games(self):
        """Lädt die Dev-Games vom Distribution-Backend (nur für Dev/Admin)."""
        if not (store.has_role("dev") or store.has_role("admin")):
            self.dev_games_page.set_items([])
            return
        try:
            apps = dev_api.get_my_apps()
        except Exception as e:
            print("get_my_apps failed:", e)
            apps = []
        self.dev_games_page.set_items(apps)

    def _on_dev_edit_requested(self, game: dict):
        """Dev klickt auf 'Bearbeiten' in Meine Games."""
        slug = str(game.get("slug") or "")
        title = str(game.get("title") or "Unbenannt")
        price = float(game.get("price") or 0.0)
        sale = float(game.get("sale_percent") or 0.0)
        desc = str(game.get("description") or "")

        dlg = QDialog(self)
        dlg.setWindowTitle(f"Game bearbeiten – {title}")
        lay = QVBoxLayout(dlg)

        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignRight)

        title_edit = QLineEdit(title)   # <-- NICHT readOnly
        price_spin = QDoubleSpinBox()
        price_spin.setRange(0.0, 9999.0)
        price_spin.setDecimals(2)
        price_spin.setSingleStep(0.50)
        price_spin.setValue(price)

        sale_spin = QSpinBox()
        sale_spin.setRange(0, 90)   # max 90% Rabatt
        sale_spin.setSuffix(" %")
        sale_spin.setValue(int(sale))

        desc_edit = QTextEdit()
        desc_edit.setPlainText(desc)
        desc_edit.setMinimumHeight(100)

        form.addRow("Titel:", title_edit)
        form.addRow("Preis:", price_spin)
        form.addRow("Rabatt:", sale_spin)
        form.addRow("Beschreibung:", desc_edit)

        lay.addLayout(form)

        buttons = QDialogButtonBox(
            QDialogButtonBox.Save | QDialogButtonBox.Cancel
        )
        buttons.accepted.connect(dlg.accept)
        buttons.rejected.connect(dlg.reject)
        lay.addWidget(buttons)

        if dlg.exec() != QDialog.Accepted:
            return  # User hat abgebrochen

        new_title = title_edit.text().strip() or title
        new_price = float(price_spin.value())
        new_sale = float(sale_spin.value())
        new_desc = desc_edit.toPlainText()

        try:
            dev_api.update_app_meta(
                slug,
                title=new_title,
                price=new_price,
                description=new_desc,
                sale_percent=new_sale,
            )
        except Exception as e:
            print("update_app_meta failed:", e)
            self.statusBar().showMessage("Speichern fehlgeschlagen.", 3000)
            return

        self.statusBar().showMessage("Game-Daten gespeichert.", 2000)

        # Dev-Liste + Shop + Library aktualisieren
        self._refresh_dev_games()
        if hasattr(self.shop_page, "refresh"):
            self.shop_page.refresh()
        self._refresh_library_from_db()


    def _on_dev_buyers_requested(self, game: dict):
        """Dev klickt auf 'Käufer' in Meine Games."""
        app_id = int(game.get("id", 0))
        title = str(game.get("title") or "Unbenannt")

        try:
            purchases = dev_api.get_app_purchases(app_id)
        except Exception as e:
            print("get_app_purchases failed:", e)
            self.statusBar().showMessage("Käufer konnten nicht geladen werden.", 3000)
            return

        dlg = QDialog(self)
        dlg.setWindowTitle(f"Käufer – {title}")
        lay = QVBoxLayout(dlg)

        info = QLabel(f"{len(purchases)} Kauf/Käufe")
        info.setStyleSheet("font-size: 13px; color: #d0d0d0;")
        lay.addWidget(info)

        list_widget = QListWidget()
        lay.addWidget(list_widget, 1)

        if not purchases:
            empty = QListWidgetItem("Noch keine Käufe.")
            list_widget.addItem(empty)
        else:
            for p in purchases:
                uid = p.get("user_id")
                price = float(p.get("price") or 0.0)
                ts = str(p.get("purchased_at") or "")
                txt = f"User-ID {uid} – {price:.2f} € – {ts}"
                item = QListWidgetItem(txt)
                list_widget.addItem(item)

        buttons = QDialogButtonBox(QDialogButtonBox.Close)
        buttons.rejected.connect(dlg.reject)
        buttons.accepted.connect(dlg.accept)  # falls man Enter drückt
        lay.addWidget(buttons)

        dlg.resize(480, 320)
        dlg.exec()


    def _on_auth_changed(self):
        if store.is_logged_in():
            try:
                store.ensure_user_scoped_library(store.session.current_user.id)
            except Exception as e:
                self.statusBar().showMessage(f"Library-Migration fehlgeschlagen: {e}", 4000)

            db_cart = store.cart_get_items()
            self.guest_cart.clear()
            self.guest_cart_ids.clear()

            # Wagen aus DB holen und mit Metadaten (inkl. sale_percent) anreichern
            self.cart = [self._find_full_game(g) for g in db_cart]
            self.cart_ids = {int(g["id"]) for g in self.cart}


            # NEU: Session für Uploader spiegeln
            try:
                store.sync_uploader_session_from_current()
            except Exception as e:
                print("Uploader-Session sync failed:", e)
        else:
            self.cart = list(self.guest_cart)
            self.cart_ids = set(self.guest_cart_ids)

        if hasattr(self.cart_page, "refresh_gate"): self.cart_page.refresh_gate()
        if hasattr(self.library_page, "refresh_gate"): self.library_page.refresh_gate()
        if hasattr(self.admin_page, "refresh_gate"): self.admin_page.refresh_gate()
        if hasattr(self.shop_page, "refresh"): self.shop_page.refresh()

        self._sync_profile_chip()
        self._sync_admin_tab_visibility()
        self._sync_dev_tab_visibility()
        self.profile_page.refresh()

        self._refresh_library_from_db()
        self.cart_page.set_items(self.cart)
        self.cart_btn.set_count(len(self.cart))

        if hasattr(self.shop_page, "set_cart_ids"):
            self.shop_page.set_cart_ids(self.cart_ids)
        self.game_info_page.set_cart_ids(self.cart_ids)
        self._refresh_session_from_server()


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
        if hasattr(self, "admin_requests_action"):
            self.admin_requests_action.setVisible(is_admin)

    def _sync_dev_tab_visibility(self):
        is_dev = store.has_role("dev") or store.has_role("admin")
        if hasattr(self, "dev_action"):
            self.dev_action.setVisible(is_dev)
            if not is_dev:
                # falls gerade DevGames angezeigt werden, zurück zum Shop
                if self.stack.currentWidget() is self.dev_games_page:
                    self.show_page("Shop")

    def _install_focus_refresh(self):
        app = QApplication.instance()
        if not app:
            return
        app.applicationStateChanged.connect(self._on_app_state_changed)

    def _on_app_state_changed(self, state: Qt.ApplicationState):
        if state == Qt.ApplicationState.ApplicationActive:
            self._refresh_session_from_server()

    def _refresh_session_from_server(self):
        if not store.is_logged_in() or not store.auth_service:
            return
        token = getattr(store.session.current_user, "token", None)
        if not token:
            return
        refreshed = store.auth_service.me(token)
        if refreshed:
            store.session.current_user = refreshed
            store.save_session()
            self._sync_profile_chip()
            self.profile_page.refresh()
            self._sync_admin_tab_visibility()
            self._sync_dev_tab_visibility()
        else:
            store.session.current_user = None
            store.clear_session()
            self._sync_profile_chip()
            self.profile_page.refresh()
            self._sync_admin_tab_visibility()
            self._sync_dev_tab_visibility()


    # ----- Warenkorb-Logik -----
    def _find_full_game(self, game: dict) -> dict:
        """Sucht ein möglichst vollständiges Game (inkl. cover_url, description, sale_percent)."""
        gid = int(game.get("id", 0))

        # 1) Eingehendes Game kopieren & Defaults setzen
        g = dict(game)
        g.setdefault("cover_url", g.get("cover_url") or "")
        g.setdefault("description", g.get("description") or "")
        g.setdefault("sale_percent", float(g.get("sale_percent") or 0.0))

        # 2) Wenn was fehlt, aus dem Shop-Cache nachziehen
        try:
            for it in getattr(self.shop_page, "_games", []):
                if int(it.get("id", -1)) == gid:
                    if not g.get("cover_url"):
                        g["cover_url"] = it.get("cover_url") or ""
                    if not g.get("description"):
                        g["description"] = it.get("description") or ""
                    if "sale_percent" in it:
                        g["sale_percent"] = float(it.get("sale_percent") or 0.0)
                    break
        except Exception:
            pass

        # 3) Wenn immer noch was fehlt, aus dem Backend holen
        try:
            full = shop_api.get_public_game(gid)
            if isinstance(full, dict):
                if not g.get("cover_url"):
                    g["cover_url"] = full.get("cover_url") or ""
                if not g.get("description"):
                    g["description"] = full.get("description") or ""
                if "sale_percent" in full:
                    g["sale_percent"] = float(full.get("sale_percent") or 0.0)
        except Exception:
            # Backend nicht kritisch für UI
            pass

        return g


    def add_to_cart(self, game: dict):
        gid = int(game["id"])

        # Immer zuerst Daten vervollständigen
        g = self._find_full_game(game)

        if store.is_logged_in():
            if gid in store.cart_get_ids():
                self.statusBar().showMessage("Bereits im Warenkorb", 1200); return
            store.cart_add(g)

            # Wagen aus DB lesen und jedes Game mit Metadaten (inkl. sale_percent) auffüllen
            self.cart = [self._find_full_game(x) for x in store.cart_get_items()]
            self.cart_ids = {int(x["id"]) for x in self.cart}

        else:
            if gid in self.guest_cart_ids:
                self.statusBar().showMessage("Bereits im Warenkorb", 1200); return
            self.guest_cart.append(g)                  # ← auch im Gast-Warenkorb mit cover_url
            self.guest_cart_ids.add(gid)
            self.cart = list(self.guest_cart)
            self.cart_ids = set(self.guest_cart_ids)

        self.cart_page.set_items(self.cart)
        if hasattr(self.shop_page, "set_cart_ids"): self.shop_page.set_cart_ids(self.cart_ids)
        self.game_info_page.set_cart_ids(self.cart_ids)
        self.cart_btn.set_count(len(self.cart))
        self.statusBar().showMessage(f'„{g.get("title","")}“ zum Warenkorb hinzugefügt', 1500)



    def remove_from_cart(self, game: dict):
        gid = int(game["id"])
        if store.is_logged_in():
            store.cart_remove(gid)
            # Rehydrate cart items with metadata (cover_url, sale_percent, …)
            self.cart = [self._find_full_game(g) for g in store.cart_get_items()]
            self.cart_ids = {int(g["id"]) for g in self.cart}
        else:
            self.guest_cart = [g for g in self.guest_cart if int(g["id"]) != gid]
            self.guest_cart_ids.discard(gid)
            self.cart = list(self.guest_cart); self.cart_ids = set(self.guest_cart_ids)

        self.cart_page.set_items(self.cart)
        if hasattr(self.shop_page, "set_cart_ids"): self.shop_page.set_cart_ids(self.cart_ids)
        self.game_info_page.set_cart_ids(self.cart_ids)
        self.cart_btn.set_count(len(self.cart))
        self.statusBar().showMessage(f'„{game["title"]}“ aus Warenkorb entfernt', 1500)

    def checkout(self):
        if not self.cart:
            self.statusBar().showMessage("Warenkorb ist leer.", 1500); return
        if not store.is_logged_in():
            self.uncheck_nav(); self.show_page("Profile")
            self.statusBar().showMessage("Bitte einloggen, um zu bezahlen.", 2000); return

        # Käufe ans Distribution-Backend melden (für Dev-Stats)
        try:
            for g in self.cart:
                app_id = int(g.get("id", 0))
                if app_id <= 0:
                    continue
                base_price = float(g.get("price", 0.0))
                sale = float(g.get("sale_percent") or 0.0)
                effective_price = base_price * (100.0 - sale) / 100.0 if sale > 0 else base_price
                dev_api.report_purchase(app_id, effective_price)
        except Exception as e:
            print("report_purchase failed:", e)

        store.add_many_to_library(self.cart)
        store.cart_clear()
        self.cart.clear(); self.cart_ids.clear()
        if hasattr(self.shop_page, "set_cart_ids"): self.shop_page.set_cart_ids(self.cart_ids)
        self.game_info_page.set_cart_ids(self.cart_ids)
        self.cart_page.set_items(self.cart)
        self.cart_btn.set_count(0)

        self._refresh_library_from_db()
        self.statusBar().showMessage("Kauf abgeschlossen – Titel in Library verschoben.", 2000)
        self.uncheck_nav(); self.show_page("Library")


    def remove_from_library(self, game_id: int):
        store.remove_from_library(game_id)
        self._refresh_library_from_db()
        self.statusBar().showMessage("Titel aus Library entfernt.", 1500)

    def _on_cart_remove_requested(self, game_id: int):
        game = next((g for g in self.cart if int(g.get("id")) == int(game_id)), None)
        if game is None:
            game = {"id": int(game_id), "title": ""}
        self.remove_from_cart(game)



    def show_page(self, name: str):
        if name == "Admin" and not store.has_role("admin"):
            self.uncheck_nav(); self.show_page("Profile")
            self.statusBar().showMessage("Admin-Rechte erforderlich.", 2000); return

        if name == "DevGames":
            if not (store.has_role("dev") or store.has_role("admin")):
                self.uncheck_nav()
                self.show_page("Profile")
                self.statusBar().showMessage("Dev-Rechte erforderlich.", 2000)
                return
            # Daten laden, wenn DevGames geöffnet wird
            self._refresh_dev_games()
            if hasattr(self, "dev_action"):
                self.uncheck_nav()
                self.dev_action.setChecked(True)

        self.stack.setCurrentWidget(self.pages[name])
        if name in self.actions:
            self.actions[name].setChecked(True)
        self.statusBar().showMessage(f"{name} geöffnet", 1000)


    def open_game(self, game: dict):
        self.game_info_page.set_game(game)
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
        if not game.get("slug"):
            try:
                gid = int(game.get("id", 0))
                for g in self.shop_page.all_games():
                    if int(g.get("id", -1)) == gid:
                        slug = g.get("slug") or slug
                        break
            except Exception:
                pass
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
        pass

    def _on_install_finished(self, ok: bool, msg: str):
        if ok:
            self._refresh_library_from_db()
            self.statusBar().showMessage("Installation abgeschlossen.", 2000)
        else:
            self.statusBar().showMessage(f"Installation fehlgeschlagen: {msg}", 4000)

    # ----- Start (Library) -----
    def _find_launch_target(self, install_dir: Path) -> Path | None:
        if not install_dir.exists():
            return None
        candidates: list[Path] = []
        # bevorzugt Top-Level-Exe/.app/.sh/.py
        for p in install_dir.iterdir():
            if p.is_file() and p.suffix.lower() in {".exe", ".bat", ".sh", ".py"}:
                candidates.append(p)
            if p.is_dir() and p.suffix.lower() == ".app":
                candidates.append(p)
        if candidates:
            return candidates[0]
        # fallback: erste ausführbare Datei in Tiefe 2
        for p in install_dir.rglob("*"):
            try:
                if p.is_file() and p.stat().st_mode & 0o111:
                    return p
            except Exception:
                pass
        return None

    def _launch_path(self, target: Path):
        try:
            if target.suffix.lower() == ".py":
                interpreter = sys.executable or "python3"
                cwd = target.parent
                # nur Dateiname übergeben, damit cwd nicht doppelt im Pfad landet
                subprocess.Popen([interpreter, target.name], cwd=str(cwd))
            elif sys.platform.startswith("win"):
                os.startfile(target.resolve())  # type: ignore
            elif sys.platform == "darwin":
                subprocess.Popen(["open", str(target.resolve())])
            else:
                subprocess.Popen([str(target.resolve())])
        except Exception as e:
            self.statusBar().showMessage(f"Start fehlgeschlagen: {e}", 4000)

    def _on_start_requested(self, game: dict):
        slug = game.get("slug") or self._slugify(game.get("title", ""))
        install_dir = Path(game.get("install_dir") or Path("./Installed") / slug)
        target = self._find_launch_target(install_dir)
        if not target:
            self.statusBar().showMessage("Kein ausführbares Spiel gefunden. Installationsordner wird geöffnet.", 4000)
            try:
                if sys.platform.startswith("win"):
                    os.startfile(install_dir)  # type: ignore
                elif sys.platform == "darwin":
                    subprocess.Popen(["open", str(install_dir)])
                else:
                    subprocess.Popen(["xdg-open", str(install_dir)])
            except Exception as e:
                self.statusBar().showMessage(f"Konnte Ordner nicht öffnen: {e}", 4000)
            return
        self._launch_path(target)

    def _on_uninstall_requested(self, game: dict):
        slug = game.get("slug") or self._slugify(game.get("title", ""))
        install_dir = Path(game.get("install_dir") or Path("./Installed") / slug)
        if not install_dir.exists():
            self.statusBar().showMessage("Spiel ist nicht installiert.", 2000)
            return
        try:
            import shutil
            shutil.rmtree(install_dir)
            self.statusBar().showMessage(f"Deinstalliert: {game.get('title')}", 2000)
        except Exception as e:
            self.statusBar().showMessage(f"Deinstallation fehlgeschlagen: {e}", 4000)
        finally:
            self._refresh_library_from_db()

    def _open_upload_page(self):
        self.stack.setCurrentWidget(self.game_upload_page)
        self.statusBar().showMessage("Game Upload", 1500)

    # ----- Admin Requests öffnen -----
    def _open_admin_requests(self):
        try:
            from pages.admin_requests_page import AdminRequestsPage
        except Exception as e:
            self.statusBar().showMessage(f"AdminRequestsPage fehlt: {e}", 4000)
            return

        if self.admin_requests_page is None:
            self.admin_requests_page = AdminRequestsPage()
            self.admin_requests_page.refreshed.connect(self._refresh_shop)
            self.stack.addWidget(self.admin_requests_page)

        self.uncheck_nav()
        self.stack.setCurrentWidget(self.admin_requests_page)
        self.statusBar().showMessage("Game Anfragen geöffnet", 1500)

    def _refresh_shop(self):
        if hasattr(self.shop_page, "refresh"):
            self.shop_page.refresh()
            self.statusBar().showMessage("Shop aktualisiert", 1500)


if __name__ == "__main__":
    app = QApplication(sys.argv)
    win = Main()
    win.show()
    sys.exit(app.exec())
