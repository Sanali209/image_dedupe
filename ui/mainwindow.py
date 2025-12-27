from PySide6.QtWidgets import (QMainWindow, QStackedWidget, QWidget, QVBoxLayout, QToolBar, QMessageBox, QStatusBar, QMenu)
from PySide6.QtGui import QAction, QIcon
from core.database import DatabaseManager
from core.scan_session import ScanSession
from .scan_setup import ScanSetupWidget
from .progress_view import ProgressWidget
from .results_view import ResultsWidget
from .cluster_view import ClusterViewWidget

class MainWindow(QMainWindow):
    def __init__(self, session, file_repo, cluster_repo, db_manager):
        super().__init__()
        self.setWindowTitle("Image Deduper")
        self.resize(1000, 700)
        
        self.session = session
        self.file_repo = file_repo
        self.cluster_repo = cluster_repo
        self.db = db_manager
        
        # Central Stack
        self.stack = QStackedWidget()
        self.setCentralWidget(self.stack)
        
        # Widgets
        self.setup_widget = ScanSetupWidget(self.session)
        self.progress_widget = ProgressWidget(self.session, self.db)
        self.results_widget = ResultsWidget(self.session, self.file_repo, self.db)
        self.cluster_widget = ClusterViewWidget(self.session, self.cluster_repo, self.file_repo, self.db)
        
        self.stack.addWidget(self.setup_widget)     # Index 0
        self.stack.addWidget(self.progress_widget)  # Index 1
        self.stack.addWidget(self.results_widget)   # Index 2
        self.stack.addWidget(self.cluster_widget)   # Index 3
        
        # Signals
        self.setup_widget.start_scan.connect(self.start_scan_process)
        self.setup_widget.show_pairs.connect(self.show_previous_pairs)
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
        
        # File Menu
        file_menu = menubar.addMenu("File")
        file_menu.addAction(new_scan_action) # Reuse action
        
        act_clear_clusters = QAction("Clear All Clusters", self)
        act_clear_clusters.triggered.connect(lambda: self.cluster_widget.clear_all_clusters())
        file_menu.addAction(act_clear_clusters)
        
        # View Menu
        view_menu = menubar.addMenu("View")
        
        self.act_show_ignored = QAction("Show Annotated Pairs", self)
        self.act_show_ignored.setCheckable(True)
        self.act_show_ignored.triggered.connect(self.toggle_ignored)
        view_menu.addAction(self.act_show_ignored)

        # Cluster View Action
        self.act_cluster_view = QAction("Cluster Organizer", self)
        self.act_cluster_view.triggered.connect(lambda: self.stack.setCurrentIndex(3))
        view_menu.addAction(self.act_cluster_view)

        # Edit Menu
        edit_menu = menubar.addMenu("Edit")
        
        act_settings = QAction("Settings...", self)
        act_settings.triggered.connect(self.open_settings)
        edit_menu.addAction(act_settings)

    def open_settings(self):
        """Open the settings dialog."""
        from .settings_dialog import SettingsDialog
        dialog = SettingsDialog(self)
        dialog.exec()

    def toggle_ignored(self, checked):
        self.session.include_ignored = checked
        if self.stack.currentIndex() == 2:
            self.show_results()

    def start_scan_process(self):
        # Session already updated by SetupWidget before emit
        self.stack.setCurrentIndex(1)
        self.progress_widget.start_scan()

    def show_results(self, existing_results=None):
        # Result loading happens here
        self.results_widget.load_results(existing_results=existing_results)
        
        self.stack.setCurrentIndex(2)
        self.statusBar.showMessage("Scan complete.")
    
    def show_previous_pairs(self):
        """Load previous search results from database, filtered by current threshold."""
        threshold = self.session.threshold
        roots = self.session.roots
        
        # Get all relations and filter by threshold
        relations = self.file_repo.get_relations_by_threshold(threshold)
        
        if not relations:
            from PySide6.QtWidgets import QMessageBox
            QMessageBox.information(self, "No Pairs Found", 
                f"No pairs found with distance ≤ {threshold}.\nTry running a scan first or adjusting the threshold.")
            return
        
        # Filter by current roots if specified
        if roots:
            import os
            # Get all file IDs from selected roots
            files_in_roots = self.file_repo.get_files_in_roots(roots)
            root_file_ids = set(f['id'] for f in files_in_roots)
            
            # Filter relations to only include pairs where both files are in roots
            filtered_relations = [
                r for r in relations 
                if r.id1 in root_file_ids and r.id2 in root_file_ids
            ]
            relations = filtered_relations
            
            if not relations:
                from PySide6.QtWidgets import QMessageBox
                QMessageBox.information(self, "No Pairs Found", 
                    f"No pairs found in selected folders with distance ≤ {threshold}.")
                return
        
        self.statusBar.showMessage(f"Loaded {len(relations)} pairs from database.")
        self.show_results(existing_results=relations)
    
    def closeEvent(self, event):
        # DB lifecycle managed by main.py / DI container
        event.accept()
