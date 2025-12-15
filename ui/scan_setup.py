from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QPushButton, 
                                 QListWidget, QFileDialog, QLabel, QGroupBox, QDoubleSpinBox, QComboBox, QMessageBox)
from PySide6.QtCore import Signal
from loguru import logger

class ScanSetupWidget(QWidget):
    start_scan = Signal(list, str, float) # emits root paths, engine_type, threshold

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
        
        # Scan Settings Group
        thresh_group = QGroupBox("Scan Settings")
        t_layout = QVBoxLayout()
        
        # Engine Selection
        row_engine = QHBoxLayout()
        row_engine.addWidget(QLabel("Detection Engine:"))
        self.combo_engine = QComboBox()
        self.combo_engine.addItems(["Standard (pHash)", "AI - CLIP", "AI - BLIP", "AI - MobileNet"])
        self.combo_engine.currentIndexChanged.connect(self.on_engine_changed)
        row_engine.addWidget(self.combo_engine)
        t_layout.addLayout(row_engine)
        
        # Threshold
        row_thresh = QHBoxLayout()
        self.lbl_thresh = QLabel("Similarity Threshold (0-50):")
        row_thresh.addWidget(self.lbl_thresh)
        
        self.spin_thresh = QDoubleSpinBox()
        self.spin_thresh.setRange(0, 50)
        self.spin_thresh.setValue(5)
        self.spin_thresh.setSingleStep(1)
        # self.spin_thresh.setDecimals(2) # Default is 2
        row_thresh.addWidget(self.spin_thresh)
        t_layout.addLayout(row_thresh)
        
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

    def on_engine_changed(self, index):
        # 0 = pHash, 1 = CLIP, 2 = BLIP, 3 = MobileNet
        if index == 0:
            # pHash
            self.lbl_thresh.setText("Similarity Threshold (0-50, int):")
            self.spin_thresh.setRange(0, 50)
            self.spin_thresh.setSingleStep(1)
            self.spin_thresh.setValue(5)
            self.spin_thresh.setDecimals(0)
        else:
            # AI (CLIP/BLIP) - Cosine Distance
            # 0.0 = exact, 0.2 = similar
            self.lbl_thresh.setText("Cosine Distance (0.0 - 1.0, lower is stricter):")
            self.spin_thresh.setRange(0.0, 1.0)
            self.spin_thresh.setSingleStep(0.05)
            self.spin_thresh.setValue(0.1) # Default 0.1
            self.spin_thresh.setDecimals(3)

    def on_start(self):
        roots = [self.path_list.item(i).text() for i in range(self.path_list.count())]
        
        if not roots:
            QMessageBox.warning(self, "No Folder Selected", "Please add at least one folder to scan.")
            return
        
        # Save to DB (Sync)
        existing = set(self.db.get_scanned_paths())
        current = set(roots)
        
        for p in existing - current:
            self.db.remove_scanned_path(p)
        for p in current - existing:
            self.db.add_scanned_path(p)
            
        # Determine engine type string
        idx = self.combo_engine.currentIndex()
        if idx == 0: engine = 'phash'
        elif idx == 1: engine = 'clip'
        elif idx == 2: engine = 'blip'
        else: engine = 'mobilenet'
        
        thresh = self.spin_thresh.value()
        
        logger.info(f"Starting scan with Engine: {engine}, Threshold: {thresh}")
        self.start_scan.emit(roots, engine, thresh)

    def load_paths(self):
        paths = self.db.get_scanned_paths()
        self.path_list.addItems(paths)
