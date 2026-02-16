from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QTableWidget, QTableWidgetItem,
    QHBoxLayout, QPushButton, QComboBox, QMessageBox, QStackedLayout, QTabWidget
)
from PySide6.QtCore import Qt, Signal
from data import store
from pages.gate_widget import GateWidget
from services import admin_api

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
        controls.addWidget(self.refresh_btn)
        self.btn_requests = QPushButton("Game Anfragen")
        self.btn_requests.clicked.connect(self.open_requests)
        controls.addWidget(self.btn_requests)
        controls.addStretch(1)
        v.addLayout(controls)

        self.tabs = QTabWidget()
        v.addWidget(self.tabs)

        users_tab = QWidget()
        users_lay = QVBoxLayout(users_tab)
        users_lay.setContentsMargins(0, 0, 0, 0)
        users_lay.setSpacing(6)

        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["ID", "E-Mail", "Rolle", "Aktion"])
        self.table.horizontalHeader().setStretchLastSection(True)
        users_lay.addWidget(self.table)
        self.tabs.addTab(users_tab, "Benutzer")

        payments_tab = QWidget()
        payments_lay = QVBoxLayout(payments_tab)
        payments_lay.setContentsMargins(0, 0, 0, 0)
        payments_lay.setSpacing(6)

        hint = QLabel("Neueste Dev-Upgrade Zahlungen/Freischaltungen")
        hint.setStyleSheet("font-size: 12px; color: #888;")
        payments_lay.addWidget(hint)

        self.payments_table = QTableWidget(0, 10)
        self.payments_table.setHorizontalHeaderLabels(
            [
                "ID",
                "User ID",
                "E-Mail",
                "Provider",
                "Betrag",
                "Währung",
                "Bezahlt",
                "Verbraucht",
                "Referenz",
                "Notiz",
            ]
        )
        self.payments_table.horizontalHeader().setStretchLastSection(True)
        payments_lay.addWidget(self.payments_table)
        self.tabs.addTab(payments_tab, "Dev-Upgrades")

        self.refresh_btn.clicked.connect(self._refresh_data)
        self.stack.addWidget(self.content)

        self.refresh_gate()
        if store.has_role("admin"):
            self._refresh_data()

    def refresh_gate(self):
        self.stack.setCurrentWidget(self.content if store.has_role("admin") else self.gate)

    def _refresh_data(self):
        errors: list[str] = []
        try:
            self._load_users()
        except Exception as e:
            errors.append(f"Benutzer: {e}")
        try:
            self._load_dev_upgrade_payments()
        except Exception as e:
            errors.append(f"Dev-Upgrades: {e}")
        if errors:
            QMessageBox.critical(self, "Fehler", "\n".join(errors))

    def _load_users(self):
        if not store.auth_service:
            raise RuntimeError("AuthService nicht verfügbar.")
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

    def _load_dev_upgrade_payments(self):
        items = admin_api.list_dev_upgrade_payments(limit=250)
        self.payments_table.setRowCount(0)
        for item in items:
            row = self.payments_table.rowCount()
            self.payments_table.insertRow(row)

            self.payments_table.setItem(row, 0, QTableWidgetItem(str(item.get("id", ""))))
            self.payments_table.setItem(row, 1, QTableWidgetItem(str(item.get("user_id", ""))))
            self.payments_table.setItem(row, 2, QTableWidgetItem(str(item.get("user_email", ""))))
            self.payments_table.setItem(row, 3, QTableWidgetItem(str(item.get("provider", ""))))
            self.payments_table.setItem(row, 4, QTableWidgetItem(str(item.get("amount", ""))))
            self.payments_table.setItem(row, 5, QTableWidgetItem(str(item.get("currency", ""))))
            self.payments_table.setItem(row, 6, QTableWidgetItem(str(item.get("paid_at", ""))))
            self.payments_table.setItem(
                row,
                7,
                QTableWidgetItem("ja" if item.get("is_consumed") else "nein"),
            )
            self.payments_table.setItem(row, 8, QTableWidgetItem(str(item.get("payment_ref", ""))))
            self.payments_table.setItem(row, 9, QTableWidgetItem(str(item.get("note", ""))))

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
