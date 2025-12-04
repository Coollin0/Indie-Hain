from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QTableWidget, QTableWidgetItem,
    QHBoxLayout, QPushButton, QComboBox, QMessageBox, QStackedLayout
)
from PySide6.QtCore import Qt, Signal
from data import store
from pages.gate_widget import GateWidget

_ROLES = ["user", "dev", "admin"]

class AdminPage(QWidget):
    go_to_profile = Signal()

    def __init__(self):
        super().__init__()
        self.stack = QStackedLayout(self)

        self.gate = GateWidget("Admin-Bereich – bitte als Admin einloggen.")
        self.gate.go_to_profile.connect(self.go_to_profile.emit)
        self.stack.addWidget(self.gate)

        self.content = QWidget()
        v = QVBoxLayout(self.content); v.setContentsMargins(12,12,12,12); v.setSpacing(8)
        title = QLabel("Admin-Konsole"); title.setAlignment(Qt.AlignLeft)
        title.setStyleSheet("font-size: 22px; font-weight: 600;")
        v.addWidget(title)

        controls = QHBoxLayout()
        self.refresh_btn = QPushButton("Aktualisieren")
        controls.addWidget(self.refresh_btn); controls.addStretch(1)
        v.addLayout(controls)

        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["ID", "E-Mail", "Rolle", "Aktion"])
        self.table.horizontalHeader().setStretchLastSection(True)
        v.addWidget(self.table)

        self.refresh_btn.clicked.connect(self._load_users)
        self.stack.addWidget(self.content)

        self.btn_requests = QPushButton("Game Anfragen")
        self.btn_requests.clicked.connect(lambda: self.open_requests())

        self.refresh_gate()
        if store.has_role("admin"):
            self._load_users()

    def refresh_gate(self):
        self.stack.setCurrentWidget(self.content if store.has_role("admin") else self.gate)

    def _load_users(self):
        if not store.auth_service:
            QMessageBox.critical(self, "Fehler", "AuthService nicht verfügbar."); return
        users = store.auth_service.list_users()
        self.table.setRowCount(0)
        for u in users:
            r = self.table.rowCount()
            self.table.insertRow(r)
            self.table.setItem(r, 0, QTableWidgetItem(str(u.id)))
            self.table.setItem(r, 1, QTableWidgetItem(u.email))
            combo = QComboBox(); combo.addItems(_ROLES); combo.setCurrentText(u.role)
            self.table.setCellWidget(r, 2, combo)
            apply_btn = QPushButton("Übernehmen")
            apply_btn.clicked.connect(lambda _, row=r: self._apply_row(row))
            self.table.setCellWidget(r, 3, apply_btn)

    def _apply_row(self, row: int):
        try:
            uid = int(self.table.item(row, 0).text())
            role_widget = self.table.cellWidget(row, 2)
            new_role = role_widget.currentText() if isinstance(role_widget, QComboBox) else "user"
            updated = store.auth_service.set_role(uid, new_role)  # type: ignore
            if store.session.current_user and store.session.current_user.id == uid:
                store.session.current_user = updated
            QMessageBox.information(self, "OK", f"Rolle aktualisiert: {updated.email} -> {updated.role}")
        except Exception as e:
            QMessageBox.critical(self, "Fehler", str(e))

    def open_requests(self):
        from pages.admin_requests_page import AdminRequestsPage
        page = AdminRequestsPage()
        self.parent().stack.addWidget(page)
        self.parent().stack.setCurrentWidget(page)
