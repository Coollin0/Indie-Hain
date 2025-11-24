from __future__ import annotations
from pathlib import Path
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton,
    QFileDialog, QComboBox, QProgressBar, QTextEdit
)
from services.uploader_client import slugify
from services.upload_worker import start_upload_thread

class GameUploadPage(QWidget):
    back_requested = Signal()

    def __init__(self):
        super().__init__()
        root = QVBoxLayout(self); root.setContentsMargins(24,24,24,24); root.setSpacing(12)

        title = QLabel("🎮 Game Upload"); title.setStyleSheet("font-size:22px;font-weight:700;")
        root.addWidget(title)

        self.ed_title = QLineEdit(); self.ed_title.setPlaceholderText("Spiel-Titel (z. B. Skate Dash)")
        self.ed_slug = QLineEdit(); self.ed_slug.setPlaceholderText("slug (auto aus Titel)")
        self.ed_version = QLineEdit("1.0.0"); self.ed_version.setPlaceholderText("Version (z. B. 1.0.0)")
        self.cmb_platform = QComboBox(); self.cmb_platform.addItems(["windows","linux","mac"])
        self.cmb_channel = QComboBox(); self.cmb_channel.addItems(["stable","beta"])

        for lbl, w in [
            ("Titel", self.ed_title), ("Slug", self.ed_slug), ("Version", self.ed_version),
            ("Platform", self.cmb_platform), ("Channel", self.cmb_channel),
        ]:
            row = QHBoxLayout(); row.addWidget(QLabel(lbl, alignment=Qt.AlignLeft), 1); row.addWidget(w, 4)
            root.addLayout(row)

        # Ordnerwahl
        self.folder = None
        pick_row = QHBoxLayout()
        self.lbl_folder = QLabel("Kein Ordner gewählt"); 
        btn_pick = QPushButton("Build-Ordner wählen…")
        btn_pick.clicked.connect(self._pick_folder)
        pick_row.addWidget(self.lbl_folder, 4); pick_row.addWidget(btn_pick, 0)
        root.addLayout(pick_row)

        # Buttons
        row_btn = QHBoxLayout()
        self.btn_upload = QPushButton("Game uploaden")
        self.btn_back = QPushButton("Zurück")
        self.btn_back.clicked.connect(self.back_requested.emit)
        row_btn.addStretch(1); row_btn.addWidget(self.btn_back); row_btn.addWidget(self.btn_upload)
        root.addLayout(row_btn)

        # Progress/Log
        self.pbar = QProgressBar(); self.pbar.setValue(0)
        self.log = QTextEdit(); self.log.setReadOnly(True); self.log.setFixedHeight(160)
        root.addWidget(self.pbar); root.addWidget(self.log)

        # Verhalten
        self.ed_title.textChanged.connect(self._sync_slug_from_title)
        self.btn_upload.clicked.connect(self._start_upload)
        self._upload_thread = None
        self._upload_worker = None

    def _sync_slug_from_title(self, s: str):
        if not self.ed_slug.text().strip():
            self.ed_slug.setText(slugify(s))

    def _pick_folder(self):
        path = QFileDialog.getExistingDirectory(self, "Build-Ordner auswählen")
        if path:
            self.folder = Path(path)
            self.lbl_folder.setText(str(self.folder))

    def _start_upload(self):
        title = self.ed_title.text().strip()
        slug = self.ed_slug.text().strip() or slugify(title)
        version = self.ed_version.text().strip() or "1.0.0"
        platform = self.cmb_platform.currentText()
        channel = self.cmb_channel.currentText()
        if not title or not slug or not self.folder:
            self._append("Bitte Titel/Slug wählen und Ordner auswählen."); return

        self.btn_upload.setEnabled(False)
        self._append("Upload startet…")

        self._upload_thread, self._upload_worker = start_upload_thread(
            title, slug, version, platform, channel, self.folder
        )
        self._upload_worker.progress.connect(self.pbar.setValue)
        self._upload_worker.log.connect(self._append)
        self._upload_worker.finished.connect(self._on_finished)
        self._upload_worker.finished.connect(self._upload_thread.quit)
        self._upload_worker.finished.connect(self._upload_worker.deleteLater)
        self._upload_thread.finished.connect(self._upload_thread.deleteLater)
        self._upload_thread.start()

    def _append(self, s: str):
        self.log.append(s)

    def _on_finished(self, ok: bool, msg: str):
        if ok:
            self._append(f"✅ Fertig: {msg}")
        else:
            self._append(f"❌ Fehler: {msg}")
        self.btn_upload.setEnabled(True)
