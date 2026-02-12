import sys
import re
import os
import subprocess
from pathlib import Path
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QToolBar, QLabel, QWidget,
    QSizePolicy, QStackedWidget, QVBoxLayout, QToolButton, QWidgetAction, QHBoxLayout,
    QDialog, QFormLayout, QLineEdit, QTextEdit, QDialogButtonBox,
    QDoubleSpinBox, QSpinBox, QListWidget, QListWidgetItem, QFileDialog, QStyle, QMessageBox
)

from PySide6.QtGui import QAction, QActionGroup, QIcon, QPixmap, QPainter, QPainterPath, QDesktopServices
from PySide6.QtCore import Qt, QSize, Signal, QUrl

from pages.shop_page import ShopPage
from pages.cart_page import CartPage
from pages.library_page import LibraryPage
from pages.profile_page import ProfilePage
from pages.game_info_page import GameInfoPage
from pages.game_upload_page import GameUploadPage
from pages.dev_games_page import DevGamesPage

from services.install_worker import start_install_thread
from services import shop_api
from services import dev_api   # NEU
from services.net_image import NetImage
from services.env import (
    abs_url,
    install_root,
    legacy_install_roots,
    add_legacy_install_dir,
    launcher_theme,
    set_launcher_theme,
)
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
        lay = QHBoxLayout(self); lay.setContentsMargins(0, 0, 0, 0); lay.setSpacing(0)
        abs_icon = (Path(__file__).resolve().parent / icon_path).resolve()
        self.btn = QToolButton(self)
        icon = QIcon(str(abs_icon))
        if icon.isNull():
            fallback = self.style().standardIcon(QStyle.SP_FileDialogDetailedView)
            if fallback.isNull():
                self.btn.setText("Cart")
                self.btn.setToolButtonStyle(Qt.ToolButtonTextOnly)
            else:
                self.btn.setIcon(fallback)
                self.btn.setToolButtonStyle(Qt.ToolButtonIconOnly)
        else:
            self.btn.setIcon(icon)
            self.btn.setToolButtonStyle(Qt.ToolButtonIconOnly)
        self.btn.setIconSize(QSize(22, 22))
        self.btn.setFixedSize(38, 38)
        self.btn.setCursor(Qt.PointingHandCursor)
        self.btn.setToolTip("Warenkorb")
        self.btn.clicked.connect(self.clicked.emit)
        self.badge = QLabel("", self.btn)
        self.badge.setAlignment(Qt.AlignCenter)
        self.badge.setFixedHeight(18)
        self.badge.hide()
        lay.addWidget(self.btn)
        self.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        self.setFixedSize(40, 40)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._position_badge()

    def _position_badge(self):
        if not self.badge.text():
            return
        self.badge.adjustSize()
        width = max(18, self.badge.width() + 8)
        self.badge.setFixedSize(width, 18)
        x = self.btn.width() - int(width * 0.55)
        self.badge.move(x, -4)

    def set_count(self, n: int):
        count = max(0, int(n))
        if count <= 0:
            self.badge.hide()
            self.badge.setText("")
            self.btn.setToolTip("Warenkorb")
            return
        self.badge.setText("99+" if count > 99 else str(count))
        self._position_badge()
        self.badge.show()
        self.btn.setToolTip(f"Warenkorb ({count})")

    def set_theme(self, theme: str):
        dark = theme == "dark"
        label_color = "#e8e8e8" if dark else "#1a1a1a"
        btn_bg = "transparent" if dark else "rgba(0,0,0,0.04)"
        btn_hover = "rgba(255,255,255,0.08)" if dark else "rgba(0,0,0,0.08)"
        badge_bg = "#d04f4f" if dark else "#b93a3a"
        badge_fg = "#ffffff"
        self.btn.setStyleSheet(
            "QToolButton{"
            f"background:{btn_bg}; border-radius:10px; color:{label_color}; font-size:11px; font-weight:700;"
            "}"
            f"QToolButton:hover{{background:{btn_hover};}}"
        )
        self.badge.setStyleSheet(
            "QLabel{"
            f"background:{badge_bg}; color:{badge_fg}; border-radius:9px;"
            "font-size:11px; font-weight:700; padding:0 4px;"
            "}"
        )
        self._position_badge()


# --------- Profil-Chip (rund maskiert) ----------
class ProfileChip(QWidget):
    clicked = Signal()
    def __init__(self):
        super().__init__()
        self.setObjectName("profileChip")
        lay = QHBoxLayout(self); lay.setContentsMargins(6,2,6,2); lay.setSpacing(8)
        self.avatar = QLabel(); self.avatar.setFixedSize(24, 24)
        self.avatar.setAlignment(Qt.AlignCenter)
        self.name = QLabel("Profile")
        lay.addWidget(self.avatar); lay.addWidget(self.name)
        self.setCursor(Qt.PointingHandCursor)
        self._net_image = NetImage(self)
        self._theme = "dark"
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
        display_name = username or "Profile"
        self.name.setText(display_name)
        if avatar_path:
            if avatar_path.startswith("http") or avatar_path.startswith("/"):
                url = abs_url(avatar_path)
                def _on_ready(pm: QPixmap, fallback_name=display_name):
                    circ = self._circle_pixmap(pm, self.avatar.size())
                    if not circ.isNull():
                        self.avatar.setText("")
                        self.avatar.setStyleSheet("border:none; background:transparent;")
                        self.avatar.setPixmap(circ)
                    else:
                        self._set_avatar_placeholder(fallback_name)
                self._net_image.load(url, _on_ready, guard=self)
                return
            if Path(avatar_path).exists():
                pm = QPixmap(avatar_path); circ = self._circle_pixmap(pm, self.avatar.size())
                if not circ.isNull():
                    self.avatar.setText("")
                    self.avatar.setStyleSheet("border:none; background:transparent;")
                    self.avatar.setPixmap(circ)
                    return
        self._set_avatar_placeholder(display_name)

    def _set_avatar_placeholder(self, name: str):
        label = (name or "").strip()
        initial = label[0].upper() if label else "P"
        if not initial.isalnum():
            initial = "P"
        if self._theme == "dark":
            bg = "#2f3740"
            fg = "#f2f4f7"
            border = "#4a5562"
        else:
            bg = "#d9e1ec"
            fg = "#243142"
            border = "#b7c3d3"
        self.avatar.setPixmap(QPixmap())
        self.avatar.setText(initial)
        self.avatar.setStyleSheet(
            f"QLabel{{background:{bg}; color:{fg}; border:1px solid {border};"
            "border-radius:12px; font-size:12px; font-weight:700;}}"
        )

    def set_theme(self, theme: str):
        self._theme = theme
        dark = theme == "dark"
        fg = "#e8e8e8" if dark else "#1a1a1a"
        hover_bg = "rgba(255,255,255,0.07)" if dark else "rgba(0,0,0,0.06)"
        self.name.setStyleSheet(f"color: {fg}; font-size: 16px;")
        self.setStyleSheet(
            "QWidget#profileChip{border-radius:10px; padding:2px 4px;}"
            f"QWidget#profileChip:hover{{background:{hover_bg};}}"
        )
        if self.avatar.pixmap() is None or self.avatar.pixmap().isNull():
            self._set_avatar_placeholder(self.name.text())


class Main(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Indie-Hain")
        self.resize(1000, 650)

        store.init_db()
        self._theme = launcher_theme()
        self._theme_syncing = False

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
        self.game_info_page = GameInfoPage()
        self.game_upload_page = GameUploadPage()
        self.dev_games_page = DevGamesPage()   # NEU
         # DevGames: Buttons verdrahten
        self.dev_games_page.edit_requested.connect(self._on_dev_edit_requested)
        self.dev_games_page.buyers_requested.connect(self._on_dev_buyers_requested)
        self.dev_games_page.unpublish_requested.connect(self._on_dev_unpublish_requested)


        self.stack.addWidget(self.game_upload_page)
        self.game_upload_page.back_requested.connect(lambda: self.show_page("DevGames"))

        # Signale
        self.shop_page.add_to_cart.connect(self.add_to_cart)
        if hasattr(self.shop_page, "remove_from_cart"):
            self.shop_page.remove_from_cart.connect(self.remove_from_cart)
        self.cart_page.remove_requested.connect(self._on_cart_remove_requested)
        self.cart_page.checkout_requested.connect(self.checkout)
        self.dev_games_page.upload_requested.connect(lambda: self._open_upload_page())

        # Detailseite
        self.shop_page.game_clicked.connect(self.open_game_from_shop)
        self.library_page.item_clicked.connect(self.open_game_from_library)
        self.game_info_page.add_to_cart.connect(self.add_to_cart)
        self.game_info_page.back_requested.connect(self._on_game_back)

        if hasattr(self.cart_page, "go_to_profile"):
            self.cart_page.go_to_profile.connect(lambda: (self.uncheck_nav(), self.show_page("Profile")))
        if hasattr(self.library_page, "go_to_profile"):
            self.library_page.go_to_profile.connect(lambda: (self.uncheck_nav(), self.show_page("Profile")))
        self.profile_page.logged_in.connect(self._on_auth_changed)
        self.profile_page.role_changed.connect(self._on_auth_changed)
        if hasattr(self.profile_page, "profile_updated"):
            self.profile_page.profile_updated.connect(self._on_auth_changed)

        # Seiten registrieren
        self.pages = {
            "Shop": self.shop_page,
            "Library": self.library_page,
            "Indie-Verse": SimplePage("Indie-Verse"),
            "Profile": self.profile_page,
            "Cart": self.cart_page,
            "DevGames": self.dev_games_page,   # NEU
        }
        for name in ("Shop", "Library", "Indie-Verse", "Profile", "Cart", "DevGames"):
            self.stack.addWidget(self.pages[name])


        self.library_page.install_requested.connect(self._on_install_requested)
        if hasattr(self.library_page, "start_requested"):
            self.library_page.start_requested.connect(self._on_start_requested)
        if hasattr(self.library_page, "uninstall_requested"):
            self.library_page.uninstall_requested.connect(self._on_uninstall_requested)
        if hasattr(self.library_page, "open_requested"):
            self.library_page.open_requested.connect(self._on_library_open_requested)
        if hasattr(self.library_page, "rescan_requested"):
            self.library_page.rescan_requested.connect(self._on_library_rescan)
        if hasattr(self.library_page, "legacy_path_requested"):
            self.library_page.legacy_path_requested.connect(self._on_library_add_path)
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
        for name in ("Shop", "Library", "Indie-Verse", "Profile"):
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

        self.theme_btn = QToolButton(self)
        self.theme_btn.setObjectName("themeToggle")
        self.theme_btn.setCheckable(True)
        self.theme_btn.setCursor(Qt.PointingHandCursor)
        self.theme_btn.toggled.connect(self._on_theme_toggled)
        theme_action = QWidgetAction(self)
        theme_action.setDefaultWidget(self.theme_btn)
        tb.addAction(theme_action)

        # Warenkorb rechts
        self.cart_btn = CartButton(icon_path="assets/cart.png")
        cart_widget_action = QWidgetAction(self); cart_widget_action.setDefaultWidget(self.cart_btn)
        tb.addAction(cart_widget_action)
        end_spacer = QWidget(); end_spacer.setFixedWidth(12); tb.addWidget(end_spacer)
        self.cart_btn.clicked.connect(lambda: (self.uncheck_nav(), self.show_page("Cart")))
        self.cart_btn.set_count(0)

        self._apply_theme()
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

    def _on_theme_toggled(self, checked: bool):
        if self._theme_syncing:
            return
        self._theme = "dark" if checked else "light"
        set_launcher_theme(self._theme)
        self._apply_theme()
        self.statusBar().showMessage(
            f"Theme: {'Dark' if self._theme == 'dark' else 'Light'}",
            1600,
        )

    def _apply_theme(self):
        dark = self._theme == "dark"

        if dark:
            base_qss = """
                QMainWindow { background: #131416; color: #e8e8e8; }
                QWidget { color: #e8e8e8; }
                QStatusBar { background: #111315; color: #d8d8d8; border-top: 1px solid #2b2f34; }
                QLineEdit, QTextEdit, QPlainTextEdit, QListWidget, QComboBox, QSpinBox, QDoubleSpinBox {
                    background: #1f2226; color: #f2f2f2; border: 1px solid #383d44; border-radius: 8px;
                }
                QPushButton {
                    background: #2b2f34; color: #f3f3f3; border: 1px solid #3d434b; border-radius: 10px; padding: 6px 12px;
                }
                QPushButton:hover { background: #343a43; }
                QPushButton:pressed { background: #262b33; }
            """
            toolbar_qss = """
                QToolBar { spacing: 14px; background: #111315; border: none; }
                QToolButton { font-size: 16px; padding: 8px 16px; color: #e8e8e8; border: 1px solid transparent; border-radius: 8px; }
                QToolButton:hover { background: rgba(255,255,255,0.07); }
                QToolButton:checked { background: #dcdcdc; color: #111; border-radius: 8px; }
            """
            theme_btn_qss = """
                QToolButton#themeToggle {
                    font-size: 13px; font-weight: 700;
                    color: #e8e8e8; background: rgba(255,255,255,0.08);
                    border: 1px solid #3a4048; border-radius: 10px; padding: 6px 12px;
                }
                QToolButton#themeToggle:hover { background: rgba(255,255,255,0.14); }
                QToolButton#themeToggle:pressed { background: rgba(255,255,255,0.2); }
            """
        else:
            base_qss = """
                QMainWindow { background: #f4f6f9; color: #171717; }
                QWidget { color: #171717; }
                QStatusBar { background: #e6eaf0; color: #1d1d1d; border-top: 1px solid #c9d1dc; }
                QLineEdit, QTextEdit, QPlainTextEdit, QListWidget, QComboBox, QSpinBox, QDoubleSpinBox {
                    background: #ffffff; color: #171717; border: 1px solid #c4ccd8; border-radius: 8px;
                }
                QPushButton {
                    background: #ffffff; color: #1a1a1a; border: 1px solid #bcc6d4; border-radius: 10px; padding: 6px 12px;
                }
                QPushButton:hover { background: #f2f5fa; }
                QPushButton:pressed { background: #e8edf5; }
            """
            toolbar_qss = """
                QToolBar { spacing: 14px; background: #e9edf3; border: none; }
                QToolButton { font-size: 16px; padding: 8px 16px; color: #171717; border: 1px solid transparent; border-radius: 8px; }
                QToolButton:hover { background: rgba(0,0,0,0.08); }
                QToolButton:checked { background: #1f2937; color: #f3f4f6; border-radius: 8px; }
            """
            theme_btn_qss = """
                QToolButton#themeToggle {
                    font-size: 13px; font-weight: 700;
                    color: #171717; background: rgba(0,0,0,0.05);
                    border: 1px solid #bcc6d4; border-radius: 10px; padding: 6px 12px;
                }
                QToolButton#themeToggle:hover { background: rgba(0,0,0,0.1); }
                QToolButton#themeToggle:pressed { background: rgba(0,0,0,0.14); }
            """

        self.setStyleSheet(base_qss)
        self.tb.setStyleSheet(toolbar_qss)
        self.theme_btn.setStyleSheet(theme_btn_qss)

        self._theme_syncing = True
        self.theme_btn.setChecked(dark)
        self.theme_btn.setText("Dark" if dark else "Light")
        self.theme_btn.setToolTip("Theme wechseln (launcher-intern)")
        self._theme_syncing = False

        self.cart_btn.set_theme(self._theme)
        self.profile_chip.set_theme(self._theme)

    def _refresh_library_from_db(self):
        # 1) Library-Items aus lokaler DB
        items = store.get_library_items()

        merged = []
        missing_count = 0
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
            install_dir = self._resolve_install_dir(slug)
            g["install_dir"] = str(install_dir)
            installed = install_dir.exists()
            g["installed"] = installed
            if not installed:
                missing_count += 1

            merged.append(g)

        # 4) Library updaten
        self.library_page.set_items(merged)
        if hasattr(self.library_page, "set_missing_count"):
            self.library_page.set_missing_count(missing_count)

        # 5) owned_ids setzen
        self.owned_ids = {int(x["id"]) for x in merged}
        if hasattr(self.shop_page, "set_owned_ids"):
            self.shop_page.set_owned_ids(self.owned_ids)

        # 6) GameInfo synchronisieren
        self.game_info_page.set_cart_ids(self.cart_ids)
        self.game_info_page.set_owned_ids(self.owned_ids)

    def _on_library_rescan(self):
        self.statusBar().showMessage("Bibliothek wird aktualisiert…")
        self._refresh_library_from_db()
        self.statusBar().showMessage("Bibliothek aktualisiert", 4000)

    def _on_library_open_requested(self, game: dict):
        install_dir = str(game.get("install_dir") or "")
        if not install_dir:
            slug = str(game.get("slug") or self._slugify(game.get("title", "")))
            install_dir = str(self._resolve_install_dir(slug))
        if install_dir and Path(install_dir).exists():
            QDesktopServices.openUrl(QUrl.fromLocalFile(install_dir))
        else:
            self.statusBar().showMessage("Installationsordner nicht gefunden.", 4000)

    def _on_library_add_path(self):
        start_dir = str(install_root())
        path = QFileDialog.getExistingDirectory(
            self,
            "Legacy-Installationsordner auswählen",
            start_dir,
        )
        if not path:
            return
        add_legacy_install_dir(Path(path))
        self.statusBar().showMessage("Legacy-Installationspfad hinzugefügt.", 4000)
        self._refresh_library_from_db()

    def _resolve_install_dir(self, slug: str) -> Path:
        primary = install_root() / slug
        if primary.exists():
            return primary
        for base in legacy_install_roots():
            candidate = base / slug
            if candidate.exists():
                return candidate
        return primary

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

    def _on_dev_unpublish_requested(self, game: dict):
        slug = str(game.get("slug") or "").strip()
        title = str(game.get("title") or "Unbenannt")
        if not slug:
            self.statusBar().showMessage("Game-Slug fehlt.", 3000)
            return

        is_approved = str(game.get("is_approved")).strip().lower() in {"1", "true", "yes", "approved"}
        if not is_approved:
            self.statusBar().showMessage("Game ist bereits nicht im Shop.", 2500)
            return

        res = QMessageBox.question(
            self,
            "Aus Shop entfernen",
            f"Soll „{title}“ aus dem Shop entfernt werden?\nDas Game bleibt in „Meine Games“ erhalten.",
            QMessageBox.Yes | QMessageBox.Cancel,
            QMessageBox.Cancel,
        )
        if res != QMessageBox.Yes:
            return

        try:
            dev_api.unpublish_app(slug)
        except Exception as e:
            print("unpublish_app failed:", e)
            self.statusBar().showMessage("Konnte Game nicht aus dem Shop entfernen.", 4000)
            return

        self.statusBar().showMessage("Game aus dem Shop entfernt.", 2500)
        self._refresh_dev_games()
        if hasattr(self.shop_page, "refresh"):
            self.shop_page.refresh()
        self._refresh_library_from_db()


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
        if hasattr(self.shop_page, "refresh"): self.shop_page.refresh()

        self._sync_profile_chip()
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
        refreshed = store.auth_service.me()
        if refreshed:
            store.session.current_user = refreshed
            store.save_session()
            self._sync_profile_chip()
            self.profile_page.refresh()
            self._sync_dev_tab_visibility()
        else:
            store.session.current_user = None
            store.clear_session()
            self._sync_profile_chip()
            self.profile_page.refresh()
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
        install_dir = install_root() / slug

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
        install_dir = Path(game.get("install_dir") or self._resolve_install_dir(slug))
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
        install_dir = Path(game.get("install_dir") or self._resolve_install_dir(slug))
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

    def _refresh_shop(self):
        if hasattr(self.shop_page, "refresh"):
            self.shop_page.refresh()
            self.statusBar().showMessage("Shop aktualisiert", 1500)


if __name__ == "__main__":
    app = QApplication(sys.argv)
    win = Main()
    win.show()
    sys.exit(app.exec())
