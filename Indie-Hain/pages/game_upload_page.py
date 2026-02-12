from __future__ import annotations

from pathlib import Path
import re

from PySide6.QtCore import Qt, Signal, QMetaObject
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QFileDialog,
    QComboBox,
    QProgressBar,
    QTextEdit,
    QDoubleSpinBox,
    QMessageBox,
    QFormLayout,
    QCheckBox,
    QFrame,
)

from services.uploader_client import slugify, set_app_meta
from services.upload_worker import start_upload_thread


SEMVER_RE = re.compile(r"^\d+\.\d+\.\d+$")
SLUG_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


class GameUploadPage(QWidget):
    back_requested = Signal()

    def __init__(self):
        super().__init__()
        self.folder: Path | None = None
        self._upload_thread = None
        self._upload_worker = None
        self._pending_reset = False
        self._upload_running = False

        root = QVBoxLayout(self)
        root.setContentsMargins(24, 24, 24, 24)
        root.setSpacing(12)

        title = QLabel("Game Upload")
        title.setStyleSheet("font-size:22px;font-weight:700;")
        subtitle = QLabel("Schnell-Upload fuer Build + Store-Daten in einem Schritt.")
        subtitle.setStyleSheet("color:#a8a8a8;font-size:12px;")
        root.addWidget(title)
        root.addWidget(subtitle)

        root.addWidget(self._make_section_label("Basisdaten"))
        form = QFormLayout()
        form.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)
        form.setLabelAlignment(Qt.AlignLeft)
        form.setHorizontalSpacing(16)
        form.setVerticalSpacing(8)

        self.ed_title = QLineEdit()
        self.ed_title.setPlaceholderText("Spiel-Titel, z. B. Skate Dash")
        form.addRow("Titel*", self.ed_title)

        slug_row = QHBoxLayout()
        slug_row.setContentsMargins(0, 0, 0, 0)
        slug_row.setSpacing(8)
        self.ed_slug = QLineEdit()
        self.ed_slug.setPlaceholderText("slug, z. B. skate-dash")
        self.chk_auto_slug = QCheckBox("Auto")
        self.chk_auto_slug.setChecked(True)
        self.chk_auto_slug.setToolTip("Slug automatisch aus dem Titel erzeugen")
        slug_row.addWidget(self.ed_slug, 1)
        slug_row.addWidget(self.chk_auto_slug, 0)
        form.addRow("Slug*", slug_row)

        self.ed_version = QLineEdit("1.0.0")
        self.ed_version.setPlaceholderText("Version im Format X.Y.Z")
        form.addRow("Version*", self.ed_version)

        platform_row = QHBoxLayout()
        platform_row.setContentsMargins(0, 0, 0, 0)
        platform_row.setSpacing(8)
        self.cmb_platform = QComboBox()
        self.cmb_platform.addItems(["windows", "linux", "mac"])
        self.cmb_channel = QComboBox()
        self.cmb_channel.addItems(["stable", "beta"])
        platform_row.addWidget(self.cmb_platform, 1)
        platform_row.addWidget(self.cmb_channel, 1)
        form.addRow("Plattform / Channel*", platform_row)

        root.addLayout(form)

        root.addWidget(self._make_section_label("Store-Daten"))
        self.price_input = QDoubleSpinBox()
        self.price_input.setRange(0.0, 100000.0)
        self.price_input.setDecimals(2)
        self.price_input.setSingleStep(0.5)
        self.price_input.setValue(0.00)
        root.addWidget(QLabel("Preis (€)*"))
        root.addWidget(self.price_input)

        self.desc_input = QTextEdit()
        self.desc_input.setPlaceholderText("Kurzbeschreibung fuer den Shop...")
        self.desc_input.setMinimumHeight(90)
        root.addWidget(QLabel("Beschreibung*"))
        root.addWidget(self.desc_input)

        cover_row = QHBoxLayout()
        cover_row.setContentsMargins(0, 0, 0, 0)
        cover_row.setSpacing(8)
        self.cover_input = QLineEdit()
        self.cover_input.setPlaceholderText("Cover-URL oder lokale Bilddatei")
        self.btn_pick_cover = QPushButton("Datei waehlen")
        self.btn_pick_cover.clicked.connect(self._pick_cover)
        cover_row.addWidget(self.cover_input, 1)
        cover_row.addWidget(self.btn_pick_cover, 0)
        root.addWidget(QLabel("Cover*"))
        root.addLayout(cover_row)

        root.addWidget(self._make_section_label("Build-Quelle"))
        folder_row = QHBoxLayout()
        folder_row.setContentsMargins(0, 0, 0, 0)
        folder_row.setSpacing(8)
        self.lbl_folder = QLabel("Kein Build-Ordner gewaehlt")
        self.lbl_folder.setWordWrap(True)
        self.btn_pick_folder = QPushButton("Build-Ordner waehlen")
        self.btn_pick_folder.clicked.connect(self._pick_folder)
        folder_row.addWidget(self.lbl_folder, 1)
        folder_row.addWidget(self.btn_pick_folder, 0)
        root.addLayout(folder_row)

        self.lbl_folder_meta = QLabel("")
        self.lbl_folder_meta.setStyleSheet("color:#9aa2ad;font-size:12px;")
        root.addWidget(self.lbl_folder_meta)

        self.status_hint = QLabel("")
        self.status_hint.setStyleSheet("color:#c44; font-size:12px;")
        root.addWidget(self.status_hint)

        action_row = QHBoxLayout()
        action_row.setContentsMargins(0, 0, 0, 0)
        action_row.setSpacing(8)
        action_row.addStretch(1)
        self.btn_reset = QPushButton("Leeren")
        self.btn_back = QPushButton("Zurueck")
        self.btn_upload = QPushButton("Upload starten")
        self.btn_upload.setEnabled(False)
        self.btn_reset.clicked.connect(self._reset_form)
        self.btn_back.clicked.connect(self.back_requested.emit)
        self.btn_upload.clicked.connect(self._start_upload)
        action_row.addWidget(self.btn_reset)
        action_row.addWidget(self.btn_back)
        action_row.addWidget(self.btn_upload)
        root.addLayout(action_row)

        self.phase_lbl = QLabel("Bereit")
        self.phase_lbl.setStyleSheet("color:#9aa2ad;font-size:12px;")
        root.addWidget(self.phase_lbl)

        self.pbar = QProgressBar()
        self.pbar.setValue(0)
        self.pbar.setTextVisible(True)
        root.addWidget(self.pbar)

        self.log = QTextEdit()
        self.log.setReadOnly(True)
        self.log.setFixedHeight(170)
        self.log.setStyleSheet("font-family: Menlo, Consolas, monospace;")
        root.addWidget(self.log)

        self._inputs_for_enable = [
            self.ed_title,
            self.ed_slug,
            self.ed_version,
            self.desc_input,
            self.cover_input,
            self.price_input,
            self.cmb_platform,
            self.cmb_channel,
            self.chk_auto_slug,
            self.btn_pick_cover,
            self.btn_pick_folder,
            self.btn_reset,
        ]

        self.ed_title.textChanged.connect(self._on_title_changed)
        self.chk_auto_slug.toggled.connect(self._on_auto_slug_toggled)
        self.ed_slug.textChanged.connect(self._sync_upload_enabled)
        self.ed_version.textChanged.connect(self._sync_upload_enabled)
        self.cover_input.textChanged.connect(self._sync_upload_enabled)
        self.desc_input.textChanged.connect(self._sync_upload_enabled)
        self.price_input.valueChanged.connect(self._sync_upload_enabled)
        self.cmb_platform.currentIndexChanged.connect(self._sync_upload_enabled)
        self.cmb_channel.currentIndexChanged.connect(self._sync_upload_enabled)

        self._on_auto_slug_toggled(True)
        self._sync_upload_enabled()

    def _make_section_label(self, text: str) -> QLabel:
        label = QLabel(text)
        label.setStyleSheet("font-size:13px;font-weight:700;color:#cfd6df;")
        sep = QFrame()
        sep.setFrameShape(QFrame.HLine)
        sep.setStyleSheet("color:#2a2f36;")
        wrap = QWidget()
        lay = QVBoxLayout(wrap)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(4)
        lay.addWidget(label)
        lay.addWidget(sep)
        return wrap

    def _set_invalid(self, widget, invalid: bool):
        if invalid:
            widget.setStyleSheet("border:1px solid #e54b4b; border-radius:6px; padding:3px;")
        else:
            widget.setStyleSheet("")

    def _append(self, text: str):
        self.log.append(text)

    def _is_url(self, value: str) -> bool:
        lower = value.lower()
        return lower.startswith("http://") or lower.startswith("https://")

    def _on_title_changed(self, text: str):
        if self.chk_auto_slug.isChecked():
            self.ed_slug.setText(slugify(text))
        self._sync_upload_enabled()

    def _on_auto_slug_toggled(self, checked: bool):
        self.ed_slug.setReadOnly(checked)
        if checked:
            self.ed_slug.setText(slugify(self.ed_title.text()))
        self._sync_upload_enabled()

    def _pick_cover(self):
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Cover auswaehlen",
            str(Path.home()),
            "Bilder (*.png *.jpg *.jpeg *.webp *.bmp)",
        )
        if path:
            self.cover_input.setText(path)

    def _pick_folder(self):
        path = QFileDialog.getExistingDirectory(self, "Build-Ordner auswaehlen")
        if not path:
            return
        self.folder = Path(path)
        self.lbl_folder.setText(str(self.folder))
        self._update_folder_meta()
        self._sync_upload_enabled()

    def _update_folder_meta(self):
        if not self.folder or not self.folder.exists() or not self.folder.is_dir():
            self.lbl_folder_meta.setText("")
            return
        try:
            file_count = 0
            total_size = 0
            for fp in self.folder.rglob("*"):
                if fp.is_file():
                    file_count += 1
                    total_size += fp.stat().st_size
            size_mb = total_size / (1024 * 1024)
            self.lbl_folder_meta.setText(f"{file_count} Dateien, {size_mb:.1f} MB")
        except Exception:
            self.lbl_folder_meta.setText("")

    def _validate_form(self) -> tuple[bool, str]:
        ok = True
        issues: list[str] = []

        title = self.ed_title.text().strip()
        if not title:
            ok = False
            issues.append("Titel fehlt")
            self._set_invalid(self.ed_title, True)
        else:
            self._set_invalid(self.ed_title, False)

        slug = self.ed_slug.text().strip()
        if not slug or not SLUG_RE.match(slug):
            ok = False
            issues.append("Slug ungueltig (nur a-z, 0-9, -)")
            self._set_invalid(self.ed_slug, True)
        else:
            self._set_invalid(self.ed_slug, False)

        version = self.ed_version.text().strip()
        if not SEMVER_RE.match(version):
            ok = False
            issues.append("Version muss X.Y.Z sein")
            self._set_invalid(self.ed_version, True)
        else:
            self._set_invalid(self.ed_version, False)

        price = float(self.price_input.value())
        if price < 0.0:
            ok = False
            issues.append("Preis darf nicht negativ sein")
            self._set_invalid(self.price_input, True)
        else:
            self._set_invalid(self.price_input, False)

        desc = self.desc_input.toPlainText().strip()
        if not desc:
            ok = False
            issues.append("Beschreibung fehlt")
            self._set_invalid(self.desc_input, True)
        else:
            self._set_invalid(self.desc_input, False)

        cover = self.cover_input.text().strip()
        if not cover:
            ok = False
            issues.append("Cover fehlt")
            self._set_invalid(self.cover_input, True)
        else:
            if self._is_url(cover):
                self._set_invalid(self.cover_input, False)
            else:
                cover_path = Path(cover)
                if not cover_path.exists() or not cover_path.is_file():
                    ok = False
                    issues.append("Cover-Datei fehlt")
                    self._set_invalid(self.cover_input, True)
                else:
                    self._set_invalid(self.cover_input, False)

        if not self.folder or not self.folder.exists() or not self.folder.is_dir():
            ok = False
            issues.append("Build-Ordner fehlt")
        else:
            has_files = any(fp.is_file() for fp in self.folder.rglob("*"))
            if not has_files:
                ok = False
                issues.append("Build-Ordner ist leer")

        return ok, " | ".join(issues)

    def _sync_upload_enabled(self):
        ok, message = self._validate_form()
        enabled = ok and not self._upload_running
        self.btn_upload.setEnabled(enabled)
        if self._upload_running:
            self.status_hint.setText("Upload laeuft...")
            return
        self.status_hint.setText("" if ok else message)

    def _set_upload_running(self, running: bool):
        self._upload_running = running
        for w in self._inputs_for_enable:
            w.setEnabled(not running)
        self.btn_back.setEnabled(not running)
        self._sync_upload_enabled()

    def _reset_form(self):
        if self._upload_running:
            return
        self.ed_title.clear()
        self.ed_slug.clear()
        self.ed_version.setText("1.0.0")
        self.cmb_platform.setCurrentIndex(0)
        self.cmb_channel.setCurrentIndex(0)
        self.price_input.setValue(0.00)
        self.desc_input.clear()
        self.cover_input.clear()
        self.folder = None
        self.lbl_folder.setText("Kein Build-Ordner gewaehlt")
        self.lbl_folder_meta.setText("")
        self.pbar.setValue(0)
        self.phase_lbl.setText("Bereit")
        self.log.clear()
        self.chk_auto_slug.setChecked(True)
        self._sync_upload_enabled()
        self._pending_reset = False

    def _show_success_dialog(self):
        QMessageBox.information(
            self,
            "Upload erfolgreich",
            "Upload abgeschlossen. Das Spiel wartet jetzt auf Admin-Freigabe.",
        )
        self._reset_form()
        self.back_requested.emit()

    def showEvent(self, event):
        super().showEvent(event)
        if self._pending_reset:
            self._reset_form()

    def _start_upload(self):
        ok, message = self._validate_form()
        if not ok:
            self._append("Fehler: " + message)
            return
        if not self.folder:
            self._append("Fehler: Build-Ordner fehlt")
            return

        title = self.ed_title.text().strip()
        slug = slugify(self.ed_slug.text().strip() or title)
        version = self.ed_version.text().strip()
        platform = self.cmb_platform.currentText()
        channel = self.cmb_channel.currentText()

        self._set_upload_running(True)
        self.phase_lbl.setText("Upload startet...")
        self._append("Start: " + slug)

        self._upload_thread, self._upload_worker = start_upload_thread(
            title,
            slug,
            version,
            platform,
            channel,
            self.folder,
            parent=self,
        )
        self._upload_worker.progress.connect(self.pbar.setValue)
        self._upload_worker.log.connect(self._append)
        self._upload_worker.finished.connect(lambda ok_, msg_: self._on_finished(ok_, msg_, slug))
        self._upload_thread.finished.connect(self._upload_thread.deleteLater)
        self._upload_thread.start()

    def _on_finished(self, ok: bool, msg: str, slug: str):
        if ok:
            self.phase_lbl.setText("Build hochgeladen, speichere Store-Daten...")
            self._append("Upload fertig: " + msg)
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
                self._append("Metadaten gespeichert.")
            except Exception as exc:
                self._append(f"Metadaten-Fehler: {exc}")
            self.phase_lbl.setText("Fertig")
            self.btn_upload.setEnabled(False)
            self._pending_reset = True
            QMetaObject.invokeMethod(self, "_show_success_dialog", Qt.QueuedConnection)
        else:
            self.phase_lbl.setText("Upload fehlgeschlagen")
            self._append("Fehler: " + msg)

        try:
            if self._upload_thread:
                self._upload_thread.quit()
                self._upload_thread.wait()
        except Exception:
            pass

        self._set_upload_running(False)
