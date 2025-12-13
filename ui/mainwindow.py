from PySide6.QtWidgets import (QMainWindow, QStackedWidget, QWidget, QVBoxLayout, QToolBar, QMessageBox, QStatusBar, QMenu)
from PySide6.QtGui import QAction, QIcon
from core.database import DatabaseManager
from .scan_setup import ScanSetupWidget
from .progress_view import ProgressWidget
from .results_view import ResultsWidget

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Image Deduper")
        self.resize(1000, 700)
        
        self.db = DatabaseManager()
        
        # Central Stack
        self.stack = QStackedWidget()
        self.setCentralWidget(self.stack)
        
        # Widgets
        self.setup_widget = ScanSetupWidget(self.db)
        self.progress_widget = ProgressWidget(self.db)
        self.results_widget = ResultsWidget(self.db)
        
        self.stack.addWidget(self.setup_widget)     # Index 0
        self.stack.addWidget(self.progress_widget)  # Index 1
        self.stack.addWidget(self.results_widget)   # Index 2
        
        self.current_threshold = 5
        self.show_ignored = False
        self.current_roots = []

        # Signals
        self.setup_widget.start_scan.connect(self.start_scan_process)
        self.progress_widget.scan_finished.connect(self.show_results)
        
        # Toolbar
        self.create_toolbar()
        
        # Style
        self.statusBar = QStatusBar()
        self.setStatusBar(self.statusBar)

    def create_toolbar(self):
        toolbar = QToolBar("Main")
        self.addToolBar(toolbar)
        
        new_scan_action = QAction("New Scan", self)
        new_scan_action.triggered.connect(lambda: self.stack.setCurrentIndex(0))
        toolbar.addAction(new_scan_action)
        
        # Menu Bar
        menubar = self.menuBar()
        view_menu = menubar.addMenu("View")
        
        self.act_show_ignored = QAction("Show Ignored/Wrong Pairs", self)
        self.act_show_ignored.setCheckable(True)
        self.act_show_ignored.triggered.connect(self.toggle_ignored)
        view_menu.addAction(self.act_show_ignored)

    def toggle_ignored(self, checked):
        self.show_ignored = checked
        if self.stack.currentIndex() == 2:
            self.show_results()

    def start_scan_process(self, roots, threshold):
        self.current_roots = roots
        self.current_threshold = threshold
        self.stack.setCurrentIndex(1)
        self.progress_widget.start_scan(roots)

    def show_results(self):
        # Result loading happens here (includes deduplication which logs progress)
        self.results_widget.load_results(self.current_threshold, self.show_ignored, self.current_roots)
        
        self.stack.setCurrentIndex(2)
        self.statusBar.showMessage("Scan complete.")
    
    def closeEvent(self, event):
        self.db.close()
        event.accept()
