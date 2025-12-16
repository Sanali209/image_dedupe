from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QPushButton, 
                                 QListWidget, QFileDialog, QLabel, QGroupBox, QDoubleSpinBox, QComboBox, QMessageBox)
from PySide6.QtCore import Signal
from loguru import logger

class ScanSetupWidget(QWidget):
    start_scan = Signal() # No args, session is SSOT

    def __init__(self, session):
        super().__init__()
        self.session = session
        self.db = session.db # Convenience
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
        
        # Load saved paths from session
        self.load_from_session()

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
        engine_map = {0: 'phash', 1: 'clip', 2: 'blip', 3: 'mobilenet'}
        engine = engine_map.get(index, 'phash')
        
        # Use session helper
        defaults = self.session.get_engine_threshold_defaults(engine)
        
        self.lbl_thresh.setText(defaults['label'])
        self.spin_thresh.setRange(defaults['min'], defaults['max'])
        self.spin_thresh.setSingleStep(defaults['step'])
        self.spin_thresh.setDecimals(defaults['decimals'])
        self.spin_thresh.setValue(defaults['default'])

    def on_start(self):
        roots = [self.path_list.item(i).text() for i in range(self.path_list.count())]
        
        if not roots:
            QMessageBox.warning(self, "No Folder Selected", "Please add at least one folder to scan.")
            return
        
        # Update Session
        self.session.roots = roots
        
        idx = self.combo_engine.currentIndex()
        if idx == 0: engine = 'phash'
        elif idx == 1: engine = 'clip'
        elif idx == 2: engine = 'blip'
        else: engine = 'mobilenet'
        
        self.session.engine = engine
        self.session.threshold = self.spin_thresh.value()
        
        logger.info(f"Starting scan with Engine: {engine}, Threshold: {self.session.threshold}")
        self.start_scan.emit()

    def load_from_session(self):
        paths = self.session.roots
        self.path_list.addItems(paths)
        # Could also restore engine/thresh last used if we saved it

