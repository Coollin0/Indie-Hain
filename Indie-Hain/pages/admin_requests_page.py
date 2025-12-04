# pages/admin_requests_page.py
from __future__ import annotations
import json
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QListWidget, QListWidgetItem, QPushButton,
    QLabel, QTextEdit, QMessageBox, QSplitter, QSizePolicy, QAbstractItemView   #  👈 hinzufügen
)

from PySide6.QtCore import Qt, QUrl, Signal
from PySide6.QtGui import QDesktopServices
from services import admin_api

class AdminRequestsPage(QWidget):
    refreshed = Signal()
    
    def __init__(self):
        super().__init__()
        self.setObjectName("AdminRequestsPage")

        # Widgets
        self.requests_list = QListWidget()
        self.requests_list.setSelectionMode(QAbstractItemView.SingleSelection)  # 👈 so ist’s richtig

        self.files_list = QListWidget()
        self.files_list.setSelectionMode(QAbstractItemView.SingleSelection)     # 👈 dito

        self.refresh_btn = QPushButton("Aktualisieren")
        self.view_manifest_btn = QPushButton("Manifest ansehen")
        self.verify_btn = QPushButton("Datei prüfen (Hashes)")
        self.download_btn = QPushButton("Datei speichern")
        self.approve_btn = QPushButton("Freigeben")
        self.reject_btn = QPushButton("Ablehnen")
        self.zip_btn = QPushButton("Alle Dateien als ZIP")

        # rechts: Details
        self.title_label = QLabel("Details"); self.title_label.setStyleSheet("font-size:16px; font-weight:600;")
        self.subinfo_label = QLabel("")
        self.manifest_view = QTextEdit(); self.manifest_view.setReadOnly(True)
        self.manifest_view.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        right_box = QVBoxLayout()
        right_box.addWidget(self.title_label)
        right_box.addWidget(self.subinfo_label)
        right_box.addWidget(QLabel("Dateien im Build:"))
        right_box.addWidget(self.files_list, 1)
        right_box.addWidget(QLabel("Manifest (JSON):"))
        right_box.addWidget(self.manifest_view, 2)
        right = QWidget(); right.setLayout(right_box)

        # Split
        split = QSplitter(Qt.Horizontal)
        split.addWidget(self.requests_list)
        split.addWidget(right)
        split.setSizes([320, 680])

        # Bottom Buttons
        btns = QHBoxLayout()
        btns.addWidget(self.refresh_btn)
        btns.addStretch(1)
        btns.addWidget(self.view_manifest_btn)
        btns.addWidget(self.verify_btn)
        btns.addWidget(self.download_btn)
        btns.addWidget(self.reject_btn)
        btns.addWidget(self.approve_btn)
        btns.addWidget(self.zip_btn)

        # Layout
        lay = QVBoxLayout(self)
        header = QLabel("🛡️  Game Anfragen"); header.setStyleSheet("font-size:20px; font-weight:700;")
        lay.addWidget(header)
        lay.addWidget(split, 1)
        lay.addLayout(btns)

        # Signals
        self.refresh_btn.clicked.connect(self.refresh)
        self.view_manifest_btn.clicked.connect(self.on_view_manifest)
        self.verify_btn.clicked.connect(self.on_verify)
        self.download_btn.clicked.connect(self.on_download)
        self.approve_btn.clicked.connect(self.on_approve)
        self.reject_btn.clicked.connect(self.on_reject)
        self.requests_list.itemSelectionChanged.connect(self._clear_details)
        self.zip_btn.clicked.connect(self.on_zip_download)

        # State
        self._last_manifest = None
        self.refresh()

    # Helpers
    def _current_submission_id(self):
        it = self.requests_list.currentItem()
        return it.data(Qt.UserRole) if it else None

    def _current_file_path(self):
        it = self.files_list.currentItem()
        return it.data(Qt.UserRole) if it else None

    def _clear_details(self):
        self.title_label.setText("Details")
        self.subinfo_label.setText("")
        self.manifest_view.clear()
        self.files_list.clear()
        self._last_manifest = None

    # Actions
    def refresh(self):
        self.requests_list.clear()
        try:
            items = admin_api.list_submissions(status="pending")
        except Exception as e:
            QMessageBox.warning(self, "Fehler", f"Konnte Anfragen nicht laden:\n{e}")
            return

        if not items:
            it = QListWidgetItem("Keine offenen Anfragen.")
            it.setFlags(it.flags() & ~Qt.ItemIsSelectable)
            self.requests_list.addItem(it)
            self.requests_list.setEnabled(False)
            return

        self.requests_list.setEnabled(True)
        for s in items:
            txt = f'[{s["id"]}] {s["app_slug"]}  v{s["version"]}  ({s["platform"]}/{s["channel"]})  – User #{s["user_id"]}'
            it = QListWidgetItem(txt)
            it.setData(Qt.UserRole, s["id"])
            self.requests_list.addItem(it)

    def on_view_manifest(self):
        sid = self._current_submission_id()
        if not sid:
            QMessageBox.information(self, "Hinweis", "Bitte zuerst eine Anfrage auswählen.")
            return
        try:
            m = admin_api.get_manifest(sid)
        except Exception as e:
            QMessageBox.warning(self, "Fehler", f"Manifest konnte nicht geladen werden:\n{e}")
            return

        self._last_manifest = m
        app = m.get("app", "?"); version = m.get("version", "?")
        platform = m.get("platform", "?"); channel = m.get("channel", "?")
        self.title_label.setText(f"Manifest: {app} v{version}")
        self.subinfo_label.setText(f"{platform}/{channel} • Dateien: {len(m.get('files', []))} • total_size: {m.get('total_size', 0)}")

        # JSON anzeigen
        self.manifest_view.setPlainText(json.dumps(m, ensure_ascii=False, indent=2))

        # Dateienliste füllen
        self.files_list.clear()
        for f in m.get("files", []):
            txt = f'{f.get("path")}  • {f.get("size",0)} B'
            it = QListWidgetItem(txt)
            it.setData(Qt.UserRole, f.get("path"))
            self.files_list.addItem(it)

    def on_verify(self):
        sid = self._current_submission_id()
        path = self._current_file_path()
        if not sid or not path:
            QMessageBox.information(self, "Hinweis", "Bitte Anfrage und Datei auswählen.")
            return
        try:
            res = admin_api.verify_file(sid, path)
        except Exception as e:
            QMessageBox.warning(self, "Fehler", f"Prüfung fehlgeschlagen:\n{e}")
            return

        msg = []
        msg.append(f'Chunks: {"OK" if res.get("chunk_ok") else "FEHLER"}')
        msg.append(f'Datei-Hash: {"OK" if res.get("file_ok") else "FEHLER"}')
        if res.get("expected"):
            msg.append(f'Expected: {res["expected"]}')
        QMessageBox.information(self, "Prüfergebnis", "\n".join(msg))

    def on_download(self):
        sid = self._current_submission_id()
        path = self._current_file_path()
        if not sid or not path:
            QMessageBox.information(self, "Hinweis", "Bitte Anfrage und Datei auswählen.")
            return
        url = admin_api.file_download_url(sid, path)
        QDesktopServices.openUrl(QUrl(url))

    def on_approve(self):
        sid = self._current_submission_id()
        if not sid:
            QMessageBox.information(self, "Hinweis", "Bitte zuerst eine Anfrage auswählen.")
            return
        if QMessageBox.question(self, "Freigeben", f"Submission #{sid} wirklich freigeben?") != QMessageBox.StandardButton.Yes:
            return
        try:
            admin_api.approve_submission(sid)
        except Exception as e:
            QMessageBox.warning(self, "Fehler", f"Freigabe fehlgeschlagen:\n{e}")
            return
        QMessageBox.information(self, "Erfolg", f"Submission #{sid} freigegeben.")
        self._clear_details()
        self.refresh()
        self.refreshed.emit()

    def on_reject(self):
        sid = self._current_submission_id()
        if not sid:
            QMessageBox.information(self, "Hinweis", "Bitte zuerst eine Anfrage auswählen.")
            return
        if QMessageBox.question(self, "Ablehnen", f"Submission #{sid} ablehnen?") != QMessageBox.StandardButton.Yes:
            return
        try:
            admin_api.reject_submission(sid, note="Nicht konform")
        except Exception as e:
            QMessageBox.warning(self, "Fehler", f"Ablehnung fehlgeschlagen:\n{e}")
            return
        QMessageBox.information(self, "OK", f"Submission #{sid} abgelehnt.")
        self._clear_details()
        self.refresh()
        self.refreshed.emit()

    def on_zip_download(self):
        sid = self._current_submission_id()
        if not sid:
            QMessageBox.information(self, "Hinweis", "Bitte zuerst eine Anfrage auswählen.")
            return
        url = admin_api.zip_download_url(sid)
        # Im Browser/Default-Downloader öffnen
        QDesktopServices.openUrl(QUrl(url))