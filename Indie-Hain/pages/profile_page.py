from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QLineEdit, QPushButton, QHBoxLayout,
    QMessageBox, QFrame, QFileDialog, QGridLayout, QCheckBox
)
from PySide6.QtCore import Signal, Qt
from PySide6.QtGui import QPixmap
from pathlib import Path
from data import store
from services.net_image import NetImage
from services.env import abs_url


class ProfilePage(QWidget):
    logged_in = Signal()
    role_changed = Signal()
    profile_updated = Signal()
    game_upload_requested = Signal()

    def __init__(self):
        super().__init__()
        self._avatar_src: str | None = None
        self._net_image = NetImage(self)
        self._build_ui()          # <-- WICHTIG: UI jetzt wirklich aufbauen
        self.refresh_gate()
        self._sync_state()

    # ---------- UI ----------
    def _build_ui(self):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(16, 16, 16, 16)
        lay.setSpacing(10)

        title = QLabel("Profil & Login", alignment=Qt.AlignCenter)
        title.setStyleSheet("font-size: 24px; font-weight: 600;")
        lay.addWidget(title)

        # Statuszeile (wird in _sync_state() gesetzt)
        self.status_lbl = QLabel("", alignment=Qt.AlignCenter)
        self.status_lbl.setTextFormat(Qt.RichText)
        self.status_lbl.setStyleSheet("font-size: 14px; padding: 6px;")
        lay.addWidget(self.status_lbl)

        # Dev/Admin: Game Upload
        row_upload = QHBoxLayout()
        row_upload.addStretch(1)
        self.btn_upload = QPushButton("Game hochladen")
        self.btn_upload.clicked.connect(self.game_upload_requested.emit)
        row_upload.addWidget(self.btn_upload, 0)
        lay.addLayout(row_upload)

        sep = QFrame(); sep.setFrameShape(QFrame.HLine)
        lay.addWidget(sep)

        grid = QGridLayout(); grid.setHorizontalSpacing(8); grid.setVerticalSpacing(6)

        self.username = QLineEdit(); self.username.setPlaceholderText("Benutzername (Pflicht bei Registrierung)")
        self.email = QLineEdit();    self.email.setPlaceholderText("E-Mail")
        self.pw = QLineEdit();       self.pw.setPlaceholderText("Passwort"); self.pw.setEchoMode(QLineEdit.Password)

        self.avatar_preview = QLabel("Kein Bild")
        self.avatar_preview.setFixedSize(64, 64)
        self.avatar_preview.setStyleSheet("border: 1px solid #555;")
        self.btn_pick_avatar = QPushButton("Profilbild wählen")

        grid.addWidget(QLabel("Benutzername:"), 0, 0); grid.addWidget(self.username, 0, 1)
        grid.addWidget(QLabel("E-Mail:"),       1, 0); grid.addWidget(self.email,    1, 1)
        grid.addWidget(QLabel("Passwort:"),     2, 0); grid.addWidget(self.pw,       2, 1)
        grid.addWidget(QLabel("Profilbild:"),   3, 0)
        row = QHBoxLayout(); row.addWidget(self.avatar_preview); row.addWidget(self.btn_pick_avatar); row.addStretch(1)
        grid.addLayout(row, 3, 1)
        lay.addLayout(grid)

        self.keep_logged = QCheckBox("Angemeldet bleiben")
        self.keep_logged.setChecked(False)
        lay.addWidget(self.keep_logged)

        row_btns = QHBoxLayout()
        self.btn_login = QPushButton("Einloggen")
        self.btn_register = QPushButton("Registrieren")
        self.btn_save = QPushButton("Profil speichern")
        row_btns.addWidget(self.btn_login); row_btns.addWidget(self.btn_register); row_btns.addWidget(self.btn_save)
        lay.addLayout(row_btns)

        self.btn_upgrade = QPushButton("Für 20 € Dev-Funktionen freischalten")
        self.btn_upgrade.setEnabled(False)
        lay.addWidget(self.btn_upgrade)

        self.btn_logout = QPushButton("Logout")
        self.btn_logout.setEnabled(False)
        lay.addWidget(self.btn_logout)

        # Events
        self.btn_pick_avatar.clicked.connect(self._pick_avatar)
        self.btn_login.clicked.connect(self._on_login)
        self.btn_register.clicked.connect(self._on_register)
        self.btn_save.clicked.connect(self._on_save)
        self.btn_upgrade.clicked.connect(self._on_upgrade)
        self.btn_logout.clicked.connect(self._on_logout)

        lay.addStretch(1)

    # ---------- Sichtbarkeit Dev/Admin ----------
    def refresh_gate(self):
        is_dev = store.has_role("dev") or store.has_role("admin")
        self.btn_upload.setVisible(is_dev)

    # ---------- Öffentliche API ----------
    def refresh(self):
        self.refresh_gate()
        self._sync_state()

    # ---------- Helpers ----------
    def _pick_avatar(self):
        path, _ = QFileDialog.getOpenFileName(self, "Profilbild wählen", "", "Bilder (*.png *.jpg *.jpeg *.webp *.bmp)")
        if path:
            self._avatar_src = path
            pm = QPixmap(path)
            if not pm.isNull():
                self.avatar_preview.setPixmap(pm.scaled(self.avatar_preview.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation))
            else:
                self.avatar_preview.setText("Ungültig")

    def _load_preview_from_current_user(self):
        u = store.session.current_user
        if u and u.avatar_path:
            if u.avatar_path.startswith("http") or u.avatar_path.startswith("/"):
                url = abs_url(u.avatar_path)
                def _on_ready(pm: QPixmap):
                    if not pm.isNull():
                        self.avatar_preview.setPixmap(pm.scaled(self.avatar_preview.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation))
                    else:
                        self.avatar_preview.setText("Kein Bild")
                self._net_image.load(url, _on_ready, guard=self)
                return
            if Path(u.avatar_path).exists():
                pm = QPixmap(u.avatar_path)
                if not pm.isNull():
                    self.avatar_preview.setPixmap(pm.scaled(self.avatar_preview.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation))
                    return
        self.avatar_preview.setText("Kein Bild")

    def _clear_form(self):
        self.username.clear()
        self.email.clear()
        self.pw.clear()
        self._avatar_src = None
        self.avatar_preview.setPixmap(QPixmap())
        self.avatar_preview.setText("Kein Bild")

    def _sync_state(self):
        u = store.session.current_user
        if u:
            shown_name = (u.username or "").strip() or u.email
            role = getattr(u, "role", "")
            self.status_lbl.setText(f"Eingeloggt als <b>{shown_name}</b> – Rolle: <b>{role}</b>")
            self.btn_logout.setEnabled(True)
            self.btn_upgrade.setEnabled(role == "user")
            self.btn_save.setEnabled(True)
            self._clear_form()
            self._load_preview_from_current_user()
        else:
            self.status_lbl.setText("Nicht eingeloggt.")
            self.btn_logout.setEnabled(False)
            self.btn_upgrade.setEnabled(False)
            self.btn_save.setEnabled(False)
            self._clear_form()

    # ---------- Aktionen ----------
    def _on_login(self):
        email = self.email.text().strip()
        pw = self.pw.text()
        user = store.auth_service.login(email, pw) if store.auth_service else None
        if user:
            store.session.current_user = user
            keep = getattr(self, "keep_logged", None)
            if isinstance(keep, QCheckBox) and keep.isChecked(): store.save_session()
            else: store.clear_session()
            self._clear_form()
            self._sync_state()
            QMessageBox.information(self, "Login", "Erfolgreich eingeloggt.")
            self.logged_in.emit()
        else:
            QMessageBox.warning(self, "Login", "E-Mail oder Passwort falsch.")

    def _on_register(self):
        email = self.email.text().strip()
        pw = self.pw.text()
        uname = self.username.text().strip()
        if not (email and pw and uname):
            QMessageBox.warning(self, "Registrieren", "Bitte Benutzername, E-Mail und Passwort angeben.")
            return
        try:
            user = store.auth_service.register(email, pw, uname, self._avatar_src) if store.auth_service else None
            if not user:
                raise RuntimeError("AuthService nicht verfügbar.")
            store.session.current_user = user
            keep = getattr(self, "keep_logged", None)
            if isinstance(keep, QCheckBox) and keep.isChecked(): store.save_session()
            else: store.clear_session()
            self._clear_form()
            self._sync_state()
            QMessageBox.information(self, "Registrieren", "Konto erstellt und eingeloggt.")
            self.logged_in.emit()
            self.profile_updated.emit()
        except Exception as e:
            QMessageBox.critical(self, "Registrieren", f"Fehler: {e}")

    def _on_save(self):
        u = store.session.current_user
        if not u:
            QMessageBox.information(self, "Profil", "Bitte zuerst einloggen.")
            return
        try:
            new_name = self.username.text().strip() or u.username or u.email
            updated = store.auth_service.update_profile(u.id, username=new_name, avatar_src_path=self._avatar_src)  # type: ignore
            store.session.current_user = updated
            store.save_session()
            self._clear_form()
            self._sync_state()
            QMessageBox.information(self, "Profil", "Profil aktualisiert.")
            self.profile_updated.emit()
        except Exception as e:
            QMessageBox.critical(self, "Profil", f"Fehler: {e}")

    def _on_upgrade(self):
        u = store.session.current_user
        if not u:
            QMessageBox.information(self, "Upgrade", "Bitte zuerst einloggen.")
            return
        new_user = store.auth_service.upgrade_to_dev(u.id)
        store.session.current_user = new_user
        store.save_session()
        self._sync_state()
        QMessageBox.information(self, "Upgrade", "Dev-Funktionen freigeschaltet!")
        self.role_changed.emit()
        self.profile_updated.emit()

    def _on_logout(self):
        store.session.current_user = None
        store.clear_session()
        self._clear_form()
        self._sync_state()
        QMessageBox.information(self, "Logout", "Abgemeldet.")
        self.logged_in.emit()
        self.profile_updated.emit()
