from typing import List, Dict
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QListWidget, QListWidgetItem,
    QHBoxLayout, QLabel, QPushButton, QFrame, QStackedLayout
)
from PySide6.QtCore import Signal
from pages.gate_widget import GateWidget
from data import store

class CartItemWidget(QFrame):
    remove_clicked = Signal(dict)
    def __init__(self, game: Dict, parent=None):
        super().__init__(parent)
        self.game = game
        self.setFrameShape(QFrame.NoFrame)
        layout = QHBoxLayout(self); layout.setContentsMargins(4,4,4,4); layout.setSpacing(10)
        title = QLabel(f'{game["title"]} — {float(game["price"]):.2f} €')
        layout.addWidget(title); layout.addStretch()
        remove_btn = QPushButton("Entfernen")
        remove_btn.setStyleSheet("QPushButton {color: red;}")
        remove_btn.clicked.connect(lambda: self.remove_clicked.emit(self.game))
        layout.addWidget(remove_btn)

class CartPage(QWidget):
    checkout_clicked = Signal()
    item_removed = Signal(dict)
    go_to_profile = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.items: List[Dict] = []

        self.stack = QStackedLayout(self)

        self.gate = GateWidget("Bitte logge dich ein, um den Warenkorb zu sehen und zu bezahlen.")
        self.gate.go_to_profile.connect(self.go_to_profile.emit)
        gate_holder = QWidget(); glay = QVBoxLayout(gate_holder); glay.addWidget(self.gate)
        self.stack.addWidget(gate_holder)

        self.content = QWidget()
        v = QVBoxLayout(self.content); v.setContentsMargins(12,12,12,12); v.setSpacing(8)
        self.list = QListWidget(); v.addWidget(self.list)

        bottom = QHBoxLayout()
        self.total_lbl = QLabel("Summe: 0,00 €"); bottom.addWidget(self.total_lbl); bottom.addStretch()
        self.checkout_btn = QPushButton("Zur Kasse"); bottom.addWidget(self.checkout_btn)
        v.addLayout(bottom)
        self.checkout_btn.clicked.connect(self.checkout_clicked.emit)

        self.stack.addWidget(self.content)
        self.refresh_gate()

    def refresh_gate(self):
        self.stack.setCurrentWidget(self.content if store.is_logged_in() else self.stack.widget(0))

    def set_items(self, items: List[Dict]):
        self.items = list(items)
        self._refresh()

    def _refresh(self):
        self.refresh_gate()
        self.list.clear()
        total = 0.0
        for g in self.items:
            total += float(g["price"])
            item = QListWidgetItem(self.list)
            widget = CartItemWidget(g)
            widget.remove_clicked.connect(self.remove_item)
            item.setSizeHint(widget.sizeHint())
            self.list.setItemWidget(item, widget)
        self.total_lbl.setText(f"Summe: {total:.2f} €")

    def remove_item(self, game: Dict):
        self.items = [g for g in self.items if int(g["id"]) != int(game["id"])]
        self._refresh()
        self.item_removed.emit(game)
