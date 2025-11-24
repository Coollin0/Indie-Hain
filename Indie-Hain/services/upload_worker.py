from PySide6.QtCore import QObject, Signal, Slot, QThread
from pathlib import Path
from services.uploader_client import upload_folder

class UploadWorker(QObject):
    progress = Signal(int)
    log = Signal(str)
    finished = Signal(bool, str)  # ok, message

    def __init__(self, title: str, slug: str, version: str, platform: str, channel: str, folder: Path):
        super().__init__()
        self.title, self.slug, self.version = title, slug, version
        self.platform, self.channel, self.folder = platform, channel, folder

    @Slot()
    def run(self):
        try:
            url = upload_folder(
                self.title, self.slug, self.version, self.platform, self.channel, self.folder,
                on_progress=lambda p: self.progress.emit(p),
                on_log=lambda s: self.log.emit(s),
            )
            self.finished.emit(True, url)
        except Exception as e:
            self.finished.emit(False, str(e))

def start_upload_thread(title: str, slug: str, version: str, platform: str, channel: str, folder: Path):
    th = QThread()
    w = UploadWorker(title, slug, version, platform, channel, folder)
    w.moveToThread(th)
    th.started.connect(w.run)
    return th, w
