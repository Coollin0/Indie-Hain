from __future__ import annotations
from pathlib import Path
import re
from PySide6.QtCore import Qt, Signal, QMetaObject
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton,
    QFileDialog, QComboBox, QProgressBar, QTextEdit, QDoubleSpinBox, QMessageBox
)
from services.uploader_client import slugify, set_app_meta
from services.upload_worker import start_upload_thread


SEMVER = re.compile(r"^\d+\.\d+\.\d+$")  # simple 1.2.3 check


class GameUploadPage(QWidget):
    back_requested = Signal()

    def __init__(self):
        super().__init__()
        root = QVBoxLayout(self)
        root.setContentsMargins(24, 24, 24, 24)
        root.setSpacing(12)

        title = QLabel("🎮 Game Upload")
        title.setStyleSheet("font-size:22px;font-weight:700;")
        root.addWidget(title)

        # Basisfelder
        self.ed_title = QLineEdit()
        self.ed_title.setPlaceholderText("Spiel-Titel (z. B. Skate Dash)")
        self.ed_slug = QLineEdit()
        self.ed_slug.setPlaceholderText("slug (auto aus Titel)")
        self.ed_version = QLineEdit("1.0.0")
        self.ed_version.setPlaceholderText("Version (z. B. 1.0.0)")

        self.cmb_platform = QComboBox()
        self.cmb_platform.addItems(["windows", "linux", "mac"])
        self.cmb_channel = QComboBox()
        self.cmb_channel.addItems(["stable", "beta"])

        for lbl, w in [
            ("Titel*", self.ed_title),
            ("Slug*", self.ed_slug),
            ("Version*", self.ed_version),
            ("Platform*", self.cmb_platform),
            ("Channel*", self.cmb_channel),
        ]:
            row = QHBoxLayout()
            row.addWidget(QLabel(lbl, alignment=Qt.AlignLeft), 1)
            row.addWidget(w, 4)
            root.addLayout(row)

        # Preis (Pflicht; > 0.00 – falls 0 erlaubt sein soll, unten in _validate_form anpassen)
        self.price_input = QDoubleSpinBox()
        self.price_input.setRange(0.0, 100000.0)
        self.price_input.setDecimals(2)
        self.price_input.setSingleStep(0.5)
        self.price_input.setValue(0.00)
        root.addWidget(QLabel("Preis (€)*"))
        root.addWidget(self.price_input)

        # Beschreibung (Pflicht)
        self.desc_input = QTextEdit()
        self.desc_input.setPlaceholderText("Kurzbeschreibung / Store-Text…")
        root.addWidget(QLabel("Beschreibung*"))
        root.addWidget(self.desc_input)

        # Cover (Pflicht: URL oder Datei)
        cover_row = QHBoxLayout()
        self.cover_input = QLineEdit()
        self.cover_input.setPlaceholderText("Cover-URL oder Datei auswählen…")
        btn_cover = QPushButton("Cover wählen…")
        def pick_cover():
            p, _ = QFileDialog.getOpenFileName(
                self, "Cover auswählen", str(Path.home()), "Bilder (*.png *.jpg *.jpeg)"
            )
            if p:
                self.cover_input.setText(p)
        btn_cover.clicked.connect(pick_cover)
        cover_row.addWidget(self.cover_input)
        cover_row.addWidget(btn_cover)
        root.addWidget(QLabel("Cover*"))
        root.addLayout(cover_row)

        # Build-Ordner (Pflicht)
        self.folder: Path | None = None
        pick_row = QHBoxLayout()
        self.lbl_folder = QLabel("Kein Ordner gewählt")
        btn_pick = QPushButton("Build-Ordner wählen…")
        btn_pick.clicked.connect(self._pick_folder)
        pick_row.addWidget(self.lbl_folder, 4)
        pick_row.addWidget(btn_pick, 0)
        root.addLayout(pick_row)

        # Buttons
        row_btn = QHBoxLayout()
        self.btn_upload = QPushButton("Game uploaden")
        self.btn_upload.setEnabled(False)  # wird über Validator freigeschaltet
        self.btn_back = QPushButton("Zurück")
        self.btn_back.clicked.connect(self.back_requested.emit)
        row_btn.addStretch(1)
        row_btn.addWidget(self.btn_back)
        row_btn.addWidget(self.btn_upload)
        root.addLayout(row_btn)

        # Progress + Log
        self.pbar = QProgressBar()
        self.pbar.setValue(0)
        self.log = QTextEdit()
        self.log.setReadOnly(True)
        self.log.setFixedHeight(160)
        root.addWidget(self.pbar)
        root.addWidget(self.log)

        # Verhalten
        self.ed_title.textChanged.connect(self._sync_slug_from_title)
        # Live-Validation auf alle relevanten Inputs
        for w in [self.ed_title, self.ed_slug, self.ed_version, self.desc_input, self.cover_input]:
            try:
                w.textChanged.connect(self._sync_upload_enabled)  # QLineEdit
            except Exception:
                try:
                    w.textChanged.connect(self._sync_upload_enabled)  # QTextEdit
                except Exception:
                    pass
        self.price_input.valueChanged.connect(self._sync_upload_enabled)
        self.cmb_platform.currentIndexChanged.connect(self._sync_upload_enabled)
        self.cmb_channel.currentIndexChanged.connect(self._sync_upload_enabled)

        self.btn_upload.clicked.connect(self._start_upload)
        self._upload_thread = None
        self._upload_worker = None
        self._pending_reset = False

        # initialer Zustand
        self._sync_upload_enabled()
        # Hinweis, warum deaktiviert (optional Label)
        self.status_hint = QLabel("")
        self.status_hint.setStyleSheet("color:#c44; font-size:12px;")
        root.insertWidget(root.count() - 4, self.status_hint)  # vor Buttons/Progress einfügen

    # ----------------- Validation Helpers -----------------

    def _set_invalid(self, widget, invalid: bool):
        widget.setStyleSheet("border: 1px solid #e33; border-radius:6px; padding:3px;" if invalid else "")

    def _is_url(self, s: str) -> bool:
        return s.lower().startswith(("http://", "https://"))

    def _validate_form(self) -> tuple[bool, str]:
        ok = True
        msgs = []

        # Titel
        title = self.ed_title.text().strip()
        if not title:
            ok = False; msgs.append("Titel fehlt."); self._set_invalid(self.ed_title, True)
        else:
            self._set_invalid(self.ed_title, False)

        # Slug (leer? -> auto aus Titel, aber Pflicht: nicht leer)
        slug = self.ed_slug.text().strip() or slugify(title)
        if not slug:
            ok = False; msgs.append("Slug fehlt."); self._set_invalid(self.ed_slug, True)
        else:
            self.ed_slug.setText(slug)
            self._set_invalid(self.ed_slug, False)

        # Semver
        version = self.ed_version.text().strip()
        if not version or not SEMVER.match(version):
            ok = False; msgs.append("Version im Format X.Y.Z angeben (z. B. 1.0.0)."); self._set_invalid(self.ed_version, True)
        else:
            self._set_invalid(self.ed_version, False)

        # Preis (hier erzwingen wir > 0.00 – wenn 0 erlaubt sein soll, ändere auf >= 0.00)
        price = float(self.price_input.value())
        if price < 0.0:
            ok = False; msgs.append("Preis darf nicht negativ sein."); self._set_invalid(self.price_input, True)
        else:
            self._set_invalid(self.price_input, False)

        # Beschreibung (Pflicht)
        desc = self.desc_input.toPlainText().strip()
        if not desc:
            ok = False; msgs.append("Beschreibung fehlt."); self._set_invalid(self.desc_input, True)
        else:
            self._set_invalid(self.desc_input, False)

        # Cover (Pflicht: URL oder existierende Datei)
        cover = self.cover_input.text().strip()
        if not cover:
            ok = False; msgs.append("Cover fehlt."); self._set_invalid(self.cover_input, True)
        else:
            if self._is_url(cover):
                self._set_invalid(self.cover_input, False)
            else:
                p = Path(cover)
                if not p.exists() or not p.is_file():
                    ok = False; msgs.append("Cover-Datei existiert nicht."); self._set_invalid(self.cover_input, True)
                else:
                    self._set_invalid(self.cover_input, False)

        # Build-Ordner (Pflicht + nicht leer)
        if not self.folder or not self.folder.exists() or not self.folder.is_dir():
            ok = False; msgs.append("Build-Ordner fehlt.")
        return ok, " | ".join(msgs)

    def _sync_upload_enabled(self):
        ok, msg = self._validate_form()
        self.btn_upload.setEnabled(ok)
        if hasattr(self, "status_hint"):
            self.status_hint.setText("" if ok else msg)

    # ----------------- UI Actions -----------------

    def _sync_slug_from_title(self, s: str):
        if not self.ed_slug.text().strip():
            self.ed_slug.setText(slugify(s))
        self._sync_upload_enabled()

    def _pick_folder(self):
        path = QFileDialog.getExistingDirectory(self, "Build-Ordner auswählen")
        if path:
            self.folder = Path(path)
            self.lbl_folder.setText(str(self.folder))
        self._sync_upload_enabled()

    def _reset_form(self):
        self.ed_title.clear()
        self.ed_slug.clear()
        self.ed_version.setText("1.0.0")
        self.price_input.setValue(0.00)
        self.desc_input.clear()
        self.cover_input.clear()
        self.folder = None
        self.lbl_folder.setText("Kein Ordner gewählt")
        self.pbar.setValue(0)
        self.log.clear()
        if hasattr(self, "status_hint"):
            self.status_hint.setText("")
        self.btn_upload.setEnabled(False)
        self._sync_upload_enabled()
        try:
            self.cover_input.setStyleSheet("")
            self.ed_title.setStyleSheet("")
            self.ed_slug.setStyleSheet("")
            self.ed_version.setStyleSheet("")
            self.desc_input.setStyleSheet("")
            self.price_input.setStyleSheet("")
        except Exception:
            pass
        self._pending_reset = False

    def _append(self, s: str):
        self.log.append(s)

    def _show_success_dialog(self):
        QMessageBox.information(
            self,
            "Upload erfolgreich",
            "Upload erfolgreich abgeschlossen.\nKlicke auf OK, um zu Meine Games zurückzukehren.",
        )
        self._reset_form()
        self.back_requested.emit()

    def showEvent(self, event):
        super().showEvent(event)
        if getattr(self, "_pending_reset", False):
            self._reset_form()

    # ----------------- Upload Flow -----------------

    def _start_upload(self):
        ok, msg = self._validate_form()
        if not ok:
            self._append("❗ " + msg)
            return

        title = self.ed_title.text().strip()
        slug = slugify(self.ed_slug.text().strip() or title)
        version = self.ed_version.text().strip()
        platform = self.cmb_platform.currentText()
        channel = self.cmb_channel.currentText()

        self.btn_upload.setEnabled(False)
        self._append("Upload startet…")

        self._upload_thread, self._upload_worker = start_upload_thread(
            title, slug, version, platform, channel, self.folder,
            parent = self,
        )
        self._upload_worker.progress.connect(self.pbar.setValue)
        self._upload_worker.log.connect(self._append)
        self._upload_worker.finished.connect(
            lambda ok_, msg_: self._on_finished(ok_, msg_, slug)
        )
        self._upload_thread.finished.connect(self._upload_thread.deleteLater)
        self._upload_thread.start()

    def _on_finished(self, ok: bool, msg: str, slug: str):
        if ok:
            self._append(f"✅ Fertig: {msg}")
            try:
                cover = self.cover_input.text().strip()
                title = self.ed_title.text().strip()
                set_app_meta(
                    slug,
                    float(self.price_input.value()),
                    self.desc_input.toPlainText().strip(),
                    cover,
                    title,
                )
                self._append("📝 Metadaten gespeichert.")
            except Exception as e:
                self._append(f"⚠️ Metadaten-Fehler: {e}")
            # Nach Erfolg Upload-Button sperren, Back bleibt aktiv
            self.btn_upload.setEnabled(False)
            # Erfolgsdialog + Reset im UI-Thread ausführen
            self._pending_reset = True
            QMetaObject.invokeMethod(self, "_show_success_dialog", Qt.QueuedConnection)
        else:
            self._append(f"❌ Fehler: {msg}")

        # wichtig: Thread sauber beenden, sonst „QThread: Destroyed while…“
        try:
            if self._upload_thread:
                self._upload_thread.quit()
                self._upload_thread.wait()
        except Exception:
            pass

        if not ok:
            self.btn_upload.setEnabled(True)
            self._sync_upload_enabled()
