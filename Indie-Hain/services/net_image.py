# services/net_image.py
from PySide6.QtCore import QObject, QUrl, Qt
from PySide6.QtNetwork import QNetworkAccessManager, QNetworkRequest, QNetworkReply
from PySide6.QtGui import QPixmap

class NetImage(QObject):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._nam = QNetworkAccessManager(self)

    def load(self, url: str, on_ready, guard: QObject | None = None):
        """Lädt ein Bild asynchron.
        - url: absolute URL
        - on_ready: callback(QPixmap)
        - guard: optionales QObject; reply wird daran geparkt, damit die Lebenszeit übereinstimmt.
        """
        if not url:
            on_ready(QPixmap())
            return

        req = QNetworkRequest(QUrl(url))
        reply: QNetworkReply = self._nam.get(req)

        # Lebenszeit koppeln: wenn guard zerstört wird, wird reply automatisch mit zerstört.
        reply.setParent(guard or self)

        def _done():
            pm = QPixmap()
            if reply.error() == QNetworkReply.NetworkError.NoError:
                data = bytes(reply.readAll())
                pm.loadFromData(data)
            try:
                on_ready(pm)
            finally:
                reply.deleteLater()

        reply.finished.connect(_done)
