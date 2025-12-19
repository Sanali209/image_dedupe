import sys
from PySide6.QtWidgets import QApplication
from ui.mainwindow import MainWindow
from loguru import logger
from core.logger import qt_log_handler
from core.database import DatabaseManager
from core.di import ServiceContainer
from core.repositories.file_repository import FileRepository
from core.repositories.cluster_repository import ClusterRepository
from core.scan_session import ScanSession

def main():
    # Remove default handler and add ours
    logger.remove()
    logger.add(sys.stderr, format="{time} {level} {message}", level="INFO")
    logger.add(qt_log_handler, format="{time:HH:mm:ss} <level>{message}</level>", level="INFO")

    # Dependency Injection Setup
    db = DatabaseManager()
    file_repo = FileRepository(db)
    cluster_repo = ClusterRepository(db)
    session = ScanSession(file_repo)

    ServiceContainer.register(DatabaseManager, db)
    ServiceContainer.register(FileRepository, file_repo)
    ServiceContainer.register(ClusterRepository, cluster_repo)
    ServiceContainer.register(ScanSession, session)

    app = QApplication(sys.argv)
    app.setApplicationName("ImageDeduper")
    
    # Inject dependencies into MainWindow
    window = MainWindow(session, file_repo, cluster_repo, db)
    window.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
