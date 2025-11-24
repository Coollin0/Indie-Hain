from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel, QPushButton
from PySide6.QtCore import Qt, Signal

class GateWidget(QWidget):
    go_to_profile = Signal()

    def __init__(self, reason: str = "Bitte einloggen, um fortzufahren."):
        super().__init__()
        lay = QVBoxLayout(self)
        lay.setContentsMargins(24, 24, 24, 24)
        lay.setSpacing(12)

        msg = QLabel(reason, alignment=Qt.AlignCenter)
        msg.setStyleSheet("font-size: 16px;")
        cta = QPushButton("Zum Login / Registrieren")
        cta.clicked.connect(self.go_to_profile.emit)

        lay.addStretch(1)
        lay.addWidget(msg)
        lay.addWidget(cta, alignment=Qt.AlignCenter)
        lay.addStretch(1)
