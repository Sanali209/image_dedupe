from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QPushButton, 
                                 QListWidget, QFileDialog, QLabel, QGroupBox, QSpinBox)
from PySide6.QtCore import Signal

class ScanSetupWidget(QWidget):
    start_scan = Signal(list, int) # emits list of root paths, threshold

    def __init__(self, db_manager):
        super().__init__()
        self.db = db_manager
        self.layout = QVBoxLayout(self)
        
        # Folder List
        group = QGroupBox("Folders to Scan")
        vbox = QVBoxLayout()
        self.path_list = QListWidget()
        vbox.addWidget(self.path_list)
        
        btn_layout = QHBoxLayout()
        self.btn_add = QPushButton("Add Folder")
        self.btn_remove = QPushButton("Remove Selected")
        self.btn_clear = QPushButton("Clear All")
        
        btn_layout.addWidget(self.btn_add)
        btn_layout.addWidget(self.btn_remove)
        btn_layout.addWidget(self.btn_clear)
        vbox.addLayout(btn_layout)
        group.setLayout(vbox)
        
        self.layout.addWidget(group)
        
        # Threshold Settings
        thresh_group = QGroupBox("Scan Settings")
        t_layout = QHBoxLayout()
        t_layout.addWidget(QLabel("Similarity Threshold (0-20, higher = loosely similar):"))
        self.spin_thresh = QSpinBox()
        self.spin_thresh.setRange(0, 50)
        self.spin_thresh.setValue(5)
        t_layout.addWidget(self.spin_thresh)
        thresh_group.setLayout(t_layout)
        self.layout.addWidget(thresh_group)
        
        # Start Button
        self.btn_start = QPushButton("Start Scan")
        self.btn_start.setStyleSheet("font-size: 16px; font-weight: bold; padding: 10px;")
        self.layout.addWidget(self.btn_start)
        
        # Connections
        self.btn_add.clicked.connect(self.add_folder)
        self.btn_remove.clicked.connect(self.remove_folder)
        self.btn_clear.clicked.connect(self.path_list.clear)
        self.btn_start.clicked.connect(self.on_start)
        
        # Load saved paths
        self.load_paths()

    def add_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Select Folder")
        if folder:
            # Check duplicates in UI
            items = [self.path_list.item(i).text() for i in range(self.path_list.count())]
            if folder not in items:
                self.path_list.addItem(folder)

    def remove_folder(self):
        for item in self.path_list.selectedItems():
            self.path_list.takeItem(self.path_list.row(item))

    def on_start(self):
        roots = [self.path_list.item(i).text() for i in range(self.path_list.count())]
        # Save to DB
        # First clear old? Or just upsert?
        # Let's simple sync: remove all, add all.
        existing = set(self.db.get_scanned_paths())
        current = set(roots)
        
        for p in existing - current:
            self.db.remove_scanned_path(p)
        for p in current - existing:
            self.db.add_scanned_path(p)
            
        self.start_scan.emit(roots, self.spin_thresh.value())

    def load_paths(self):
        paths = self.db.get_scanned_paths()
        self.path_list.addItems(paths)
