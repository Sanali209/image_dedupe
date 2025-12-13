from PySide6.QtWidgets import QWidget, QVBoxLayout, QProgressBar, QLabel, QPushButton, QTextEdit
from PySide6.QtCore import Signal
from PySide6.QtGui import QTextCursor
from core.scanner import ScanWorker
from core.logger import qt_log_handler
from loguru import logger

class ProgressWidget(QWidget):
    scan_finished = Signal()

    def __init__(self, db_manager):
        super().__init__()
        self.db = db_manager
        self.layout = QVBoxLayout(self)
        
        self.status_label = QLabel("Initializing...")
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        
        self.log_view = QTextEdit()
        self.log_view.setReadOnly(True)
        self.log_view.setStyleSheet("background-color: #1e1e1e; color: #00ff00; font-family: Consolas;")
        
        self.btn_cancel = QPushButton("Cancel")
        self.btn_cancel.clicked.connect(self.cancel_scan)
        
        self.layout.addWidget(self.status_label)
        self.layout.addWidget(self.progress_bar)
        self.layout.addWidget(self.log_view)
        self.layout.addWidget(self.btn_cancel)
        
        # Connect Logger
        qt_log_handler.log_signal.connect(self.append_log)
        
        self.worker = None

    def append_log(self, text):
        self.log_view.append(text)
        # Autoscroll
        cursor = self.log_view.textCursor()
        cursor.movePosition(QTextCursor.End)
        self.log_view.setTextCursor(cursor)

    def start_scan(self, roots):
        self.status_label.setText("Scanning...")
        self.progress_bar.setValue(0)
        self.btn_cancel.setEnabled(True)
        
        self.worker = ScanWorker(roots, self.db.db_path)
        self.worker.progress.connect(self.update_progress)
        self.worker.file_processed.connect(self.update_file_label)
        self.worker.finished_scan.connect(self.on_finished)
        self.worker.start()

    def update_progress(self, current, total):
        self.progress_bar.setMaximum(total)
        self.progress_bar.setValue(current)
        self.status_label.setText(f"Processed {current}/{total}")

    def update_file_label(self, path):
        # Optional: showing fast changing text might lag UI
        pass

    def on_finished(self):
        self.worker.deleteLater()
        self.worker = None
        self.scan_finished.emit()

    def cancel_scan(self):
        if self.worker:
            self.status_label.setText("Stopping...")
            self.btn_cancel.setEnabled(False)
            self.worker.stop()
