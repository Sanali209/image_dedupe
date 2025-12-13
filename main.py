import sys
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QCoreApplication
from ui.mainwindow import MainWindow
from loguru import logger
from core.logger import qt_log_handler
import sys

def main():
    # Remove default handler and add ours
    logger.remove()
    logger.add(sys.stderr, format="{time} {level} {message}", level="INFO")
    logger.add(qt_log_handler, format="{time:HH:mm:ss} <level>{message}</level>", level="INFO")

    app = QApplication(sys.argv)
    app.setOrganizationName("Antigravity")
    app.setApplicationName("ImageDeduper")
    
    window = MainWindow()
    window.show()
    
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
