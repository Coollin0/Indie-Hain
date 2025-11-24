# services/install_worker.py
from PySide6.QtCore import QObject, Signal, Slot, QThread
from pathlib import Path
from distribution_client.downloader import get_manifest, install_from_manifest

class InstallWorker(QObject):
    progress = Signal(int)         # optional (0..100)
    finished = Signal(bool, str)   # (ok, message)

    def __init__(self, slug: str, install_dir: Path, platform: str = "windows", channel: str = "stable"):
        super().__init__()
        self.slug = slug
        self.install_dir = install_dir
        self.platform = platform
        self.channel = channel

    @Slot()
    def run(self):
        try:
            man = get_manifest(self.slug, self.platform, self.channel)
            install_from_manifest(man, self.install_dir)  # simple; 100% am Ende
            self.progress.emit(100)
            self.finished.emit(True, "Installiert")
        except Exception as e:
            self.finished.emit(False, str(e))

def start_install_thread(slug: str, install_dir: Path):
    thread = QThread()
    worker = InstallWorker(slug, install_dir)
    worker.moveToThread(thread)
    thread.started.connect(worker.run)
    return thread, worker
