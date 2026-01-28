from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QLineEdit, QPushButton, QHBoxLayout,
    QMessageBox, QFrame, QFileDialog, QGridLayout, QCheckBox, QDialog, QDialogButtonBox
)
from PySide6.QtCore import Signal, Qt
from PySide6.QtGui import QPixmap
from pathlib import Path
from data import store
from services.net_image import NetImage
from services.env import abs_url
from auth_service import PasswordResetRequired


class ProfilePage(QWidget):
    logged_in = Signal()
    role_changed = Signal()
    profile_updated = Signal()

    def __init__(self):
        super().__init__()
        self._avatar_src: str | None = None
        self._net_image = NetImage(self)
        self._mode = "chooser"
        self._new_password_buffer: str = ""
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

        sep = QFrame(); sep.setFrameShape(QFrame.HLine)
        lay.addWidget(sep)

        # ---------- Auswahl (Login / Registrieren) ----------
        self.choice_box = QWidget()
        choice_lay = QVBoxLayout(self.choice_box)
        choice_lay.setContentsMargins(0, 12, 0, 12)
        choice_row = QHBoxLayout()
        choice_row.addStretch(1)
        self.btn_choose_login = QPushButton("Login")
        self.btn_choose_register = QPushButton("Registrieren")
        for btn in (self.btn_choose_login, self.btn_choose_register):
            btn.setCursor(Qt.PointingHandCursor)
            btn.setStyleSheet("padding: 10px 22px; border-radius: 18px;")
        choice_row.addWidget(self.btn_choose_login)
        choice_row.addSpacing(14)
        choice_row.addWidget(self.btn_choose_register)
        choice_row.addStretch(1)
        choice_lay.addLayout(choice_row)
        lay.addWidget(self.choice_box)

        # ---------- Auth-Form (Login/Register) ----------
        self.auth_box = QWidget()
        auth_lay = QVBoxLayout(self.auth_box)
        auth_lay.setContentsMargins(0, 6, 0, 6)
        auth_lay.setSpacing(8)

        self.login_form = QWidget()
        login_grid = QGridLayout(self.login_form)
        login_grid.setHorizontalSpacing(8); login_grid.setVerticalSpacing(6)
        self.login_identity = QLineEdit()
        self.login_identity.setPlaceholderText("Benutzername oder E-Mail")
        self.login_pw = QLineEdit()
        self.login_pw.setPlaceholderText("Passwort")
        self.login_pw.setEchoMode(QLineEdit.Password)
        login_grid.addWidget(QLabel("Benutzername / E-Mail:"), 0, 0)
        login_grid.addWidget(self.login_identity, 0, 1)
        login_grid.addWidget(QLabel("Passwort:"), 1, 0)
        login_grid.addWidget(self.login_pw, 1, 1)
        auth_lay.addWidget(self.login_form)

        self.register_form = QWidget()
        reg_grid = QGridLayout(self.register_form)
        reg_grid.setHorizontalSpacing(8); reg_grid.setVerticalSpacing(6)
        self.reg_username = QLineEdit(); self.reg_username.setPlaceholderText("Benutzername")
        self.reg_email = QLineEdit(); self.reg_email.setPlaceholderText("E-Mail")
        self.reg_pw = QLineEdit(); self.reg_pw.setPlaceholderText("Passwort"); self.reg_pw.setEchoMode(QLineEdit.Password)
        reg_grid.addWidget(QLabel("Benutzername:"), 0, 0); reg_grid.addWidget(self.reg_username, 0, 1)
        reg_grid.addWidget(QLabel("E-Mail:"),       1, 0); reg_grid.addWidget(self.reg_email,    1, 1)
        reg_grid.addWidget(QLabel("Passwort:"),     2, 0); reg_grid.addWidget(self.reg_pw,       2, 1)
        auth_lay.addWidget(self.register_form)

        self.keep_logged = QCheckBox("Angemeldet bleiben")
        self.keep_logged.setChecked(False)
        auth_lay.addWidget(self.keep_logged, 0, Qt.AlignHCenter)

        self.auth_action_btn = QPushButton("Login")
        self.auth_action_btn.setCursor(Qt.PointingHandCursor)
        self.auth_action_btn.setStyleSheet("padding: 10px 28px; border-radius: 18px;")
        auth_lay.addWidget(self.auth_action_btn, 0, Qt.AlignHCenter)

        self.btn_auth_back = QPushButton("Zurück")
        self.btn_auth_back.setCursor(Qt.PointingHandCursor)
        self.btn_auth_back.setStyleSheet("padding: 8px 22px; border-radius: 16px;")
        auth_lay.addWidget(self.btn_auth_back, 0, Qt.AlignHCenter)
        lay.addWidget(self.auth_box)

        # ---------- Profil ----------
        self.profile_box = QWidget()
        profile_lay = QVBoxLayout(self.profile_box)
        profile_lay.setContentsMargins(0, 6, 0, 6)
        profile_lay.setSpacing(10)

        avatar_row = QHBoxLayout()
        self.avatar_preview = QLabel("Kein Bild")
        self.avatar_preview.setFixedSize(72, 72)
        self.avatar_preview.setStyleSheet("border: 1px solid #555; border-radius: 8px;")
        self.btn_pick_avatar = QPushButton("Profilbild wählen")
        self.btn_pick_avatar.setCursor(Qt.PointingHandCursor)
        avatar_row.addWidget(self.avatar_preview)
        avatar_row.addWidget(self.btn_pick_avatar)
        avatar_row.addStretch(1)
        profile_lay.addLayout(avatar_row)

        info_grid = QGridLayout()
        info_grid.setHorizontalSpacing(8); info_grid.setVerticalSpacing(6)
        self.profile_name_edit = QLineEdit()
        self.profile_name_edit.setPlaceholderText("Benutzername")
        self.profile_email_lbl = QLabel("")
        self.profile_role_lbl = QLabel("")
        info_grid.addWidget(QLabel("Benutzername:"), 0, 0)
        info_grid.addWidget(self.profile_name_edit, 0, 1)
        info_grid.addWidget(QLabel("E-Mail:"), 1, 0)
        info_grid.addWidget(self.profile_email_lbl, 1, 1)
        info_grid.addWidget(QLabel("Rolle:"), 2, 0)
        info_grid.addWidget(self.profile_role_lbl, 2, 1)
        profile_lay.addLayout(info_grid)

        self.btn_save = QPushButton("Profil speichern")
        self.btn_save.setCursor(Qt.PointingHandCursor)
        self.btn_save.setStyleSheet("padding: 10px 28px; border-radius: 18px;")
        profile_lay.addWidget(self.btn_save, 0, Qt.AlignHCenter)

        self.btn_upgrade = QPushButton("Für 20 € Dev-Funktionen freischalten")
        self.btn_upgrade.setEnabled(False)
        profile_lay.addWidget(self.btn_upgrade, 0, Qt.AlignHCenter)

        self.btn_logout = QPushButton("Logout")
        self.btn_logout.setEnabled(False)
        profile_lay.addWidget(self.btn_logout, 0, Qt.AlignHCenter)

        lay.addWidget(self.profile_box)

        # Events
        self.btn_choose_login.clicked.connect(lambda: self._set_mode("login"))
        self.btn_choose_register.clicked.connect(lambda: self._set_mode("register"))
        self.btn_pick_avatar.clicked.connect(self._pick_avatar)
        self.auth_action_btn.clicked.connect(self._on_auth_action)
        self.btn_auth_back.clicked.connect(self._on_auth_back)
        self.btn_save.clicked.connect(self._on_save)
        self.btn_upgrade.clicked.connect(self._on_upgrade)
        self.btn_logout.clicked.connect(self._on_logout)

        lay.addStretch(1)

    # ---------- Sichtbarkeit Dev/Admin ----------
    def refresh_gate(self):
        pass

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

    def _clear_auth_forms(self):
        self.login_identity.clear()
        self.login_pw.clear()
        self.reg_username.clear()
        self.reg_email.clear()
        self.reg_pw.clear()
        self.keep_logged.setChecked(False)

    def _clear_profile_form(self):
        self.profile_name_edit.clear()
        self.profile_email_lbl.setText("")
        self.profile_role_lbl.setText("")
        self._avatar_src = None
        self.avatar_preview.setPixmap(QPixmap())
        self.avatar_preview.setText("Kein Bild")

    def _set_mode(self, mode: str):
        self._mode = mode
        self.choice_box.setVisible(mode == "chooser")
        self.auth_box.setVisible(mode in ("login", "register"))
        self.profile_box.setVisible(mode == "profile")
        self.login_form.setVisible(mode == "login")
        self.register_form.setVisible(mode == "register")
        self.auth_action_btn.setText("Login" if mode == "login" else "Registrieren")
        self.btn_auth_back.setVisible(mode in ("login", "register"))

    def _on_auth_back(self):
        self._clear_auth_forms()
        self._set_mode("chooser")

    def _sync_state(self):
        u = store.session.current_user
        if u:
            shown_name = (u.username or "").strip() or u.email
            role = getattr(u, "role", "")
            self.status_lbl.setText(f"Eingeloggt als <b>{shown_name}</b> – Rolle: <b>{role}</b>")
            self.btn_logout.setEnabled(True)
            self.btn_upgrade.setEnabled(role == "user")
            self.btn_save.setEnabled(True)
            self._set_mode("profile")
            self.profile_name_edit.setText(shown_name)
            self.profile_email_lbl.setText(u.email or "")
            self.profile_role_lbl.setText(role or "")
            self._load_preview_from_current_user()
        else:
            self.status_lbl.setText("Nicht eingeloggt.")
            self.btn_logout.setEnabled(False)
            self.btn_upgrade.setEnabled(False)
            self.btn_save.setEnabled(False)
            self._clear_profile_form()
            if self._mode not in ("login", "register"):
                self._set_mode("chooser")

    # ---------- Aktionen ----------
    def _on_auth_action(self):
        if self._mode == "register":
            self._on_register()
        else:
            self._on_login()

    def _on_login(self):
        email = self.login_identity.text().strip()
        pw = self.login_pw.text()
        if not email or not pw:
            QMessageBox.warning(self, "Login", "Bitte Benutzername/E-Mail und Passwort angeben.")
            return
        try:
            user = store.auth_service.login(email, pw) if store.auth_service else None
        except PasswordResetRequired:
            if self._handle_password_reset(email, pw):
                # Nach erfolgreichem Reset neu einloggen
                try:
                    user = store.auth_service.login(email, self._new_password_buffer) if store.auth_service else None
                except PasswordResetRequired:
                    user = None
            else:
                user = None
        except Exception as e:
            QMessageBox.critical(self, "Login", f"Fehler: {e}")
            return
        if user:
            store.session.current_user = user
            keep = getattr(self, "keep_logged", None)
            if isinstance(keep, QCheckBox) and keep.isChecked(): store.save_session()
            else: store.clear_session()
            self._clear_auth_forms()
            self._sync_state()
            QMessageBox.information(self, "Login", "Erfolgreich eingeloggt.")
            self.logged_in.emit()
        else:
            QMessageBox.warning(self, "Login", "E-Mail/Benutzername oder Passwort falsch.")

    def _handle_password_reset(self, identity: str, temp_password: str) -> bool:
        dlg = QDialog(self)
        dlg.setWindowTitle("Passwort ändern")
        lay = QVBoxLayout(dlg)
        info = QLabel(
            "Dein Konto benötigt ein neues Passwort.\n"
            "Bitte temporäres Passwort eingeben und neues Passwort setzen."
        )
        info.setStyleSheet("font-size: 12px; color: #ddd;")
        lay.addWidget(info)

        form = QGridLayout()
        form.setHorizontalSpacing(8)
        form.setVerticalSpacing(6)

        temp = QLineEdit()
        temp.setEchoMode(QLineEdit.Password)
        temp.setText(temp_password)
        temp.setPlaceholderText("Temporäres Passwort")

        new_pw = QLineEdit()
        new_pw.setEchoMode(QLineEdit.Password)
        new_pw.setPlaceholderText("Neues Passwort")

        new_pw2 = QLineEdit()
        new_pw2.setEchoMode(QLineEdit.Password)
        new_pw2.setPlaceholderText("Neues Passwort wiederholen")

        form.addWidget(QLabel("Temp Passwort:"), 0, 0)
        form.addWidget(temp, 0, 1)
        form.addWidget(QLabel("Neues Passwort:"), 1, 0)
        form.addWidget(new_pw, 1, 1)
        form.addWidget(QLabel("Wiederholen:"), 2, 0)
        form.addWidget(new_pw2, 2, 1)
        lay.addLayout(form)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(dlg.accept)
        buttons.rejected.connect(dlg.reject)
        lay.addWidget(buttons)

        if dlg.exec() != QDialog.Accepted:
            return False

        temp_val = temp.text().strip()
        npw = new_pw.text()
        npw2 = new_pw2.text()
        if not temp_val or not npw or not npw2:
            QMessageBox.warning(self, "Passwort", "Bitte alle Felder ausfüllen.")
            return False
        if npw != npw2:
            QMessageBox.warning(self, "Passwort", "Passwörter stimmen nicht überein.")
            return False
        if store.auth_service:
            try:
                store.auth_service.reset_password(identity, temp_val, npw)
                self._new_password_buffer = npw
                QMessageBox.information(self, "Passwort", "Passwort geändert. Bitte erneut einloggen.")
                return True
            except Exception as e:
                QMessageBox.critical(self, "Passwort", f"Fehler: {e}")
        return False

    def _on_register(self):
        email = self.reg_email.text().strip()
        pw = self.reg_pw.text()
        uname = self.reg_username.text().strip()
        if not (email and pw and uname):
            QMessageBox.warning(self, "Registrieren", "Bitte Benutzername, E-Mail und Passwort angeben.")
            return
        try:
            user = store.auth_service.register(email, pw, uname, None) if store.auth_service else None
            if not user:
                raise RuntimeError("AuthService nicht verfügbar.")
            store.session.current_user = user
            keep = getattr(self, "keep_logged", None)
            if isinstance(keep, QCheckBox) and keep.isChecked(): store.save_session()
            else: store.clear_session()
            self._clear_auth_forms()
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
            new_name = self.profile_name_edit.text().strip() or u.username or u.email
            updated = store.auth_service.update_profile(u.id, username=new_name, avatar_src_path=self._avatar_src)  # type: ignore
            store.session.current_user = updated
            store.save_session()
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
        if store.auth_service:
            try:
                store.auth_service.logout()
            except Exception:
                pass
        store.session.current_user = None
        store.clear_session()
        self._clear_auth_forms()
        self._clear_profile_form()
        self._sync_state()
        QMessageBox.information(self, "Logout", "Abgemeldet.")
        self.logged_in.emit()
        self.profile_updated.emit()
