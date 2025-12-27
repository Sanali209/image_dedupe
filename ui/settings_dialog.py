"""
Settings Dialog for GPU configuration and batch sizes.
"""
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QGroupBox, QLabel, 
    QComboBox, QSpinBox, QPushButton, QFormLayout, QMessageBox
)
from PySide6.QtCore import Qt
from loguru import logger


class SettingsDialog(QDialog):
    """Dialog for configuring GPU device and batch sizes."""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Settings")
        self.setMinimumWidth(400)
        self.setModal(True)
        
        # Import here to avoid circular imports
        from core.gpu_config import GPUConfig
        self.config = GPUConfig()
        
        self._setup_ui()
        self._load_current_settings()
    
    def _setup_ui(self):
        layout = QVBoxLayout(self)
        
        # GPU Selection Group
        gpu_group = QGroupBox("GPU Device")
        gpu_layout = QFormLayout()
        
        self.combo_device = QComboBox()
        self.combo_device.addItem("Auto (Best Available)", "auto")
        
        # Add detected devices
        devices = self.config.get_available_devices()
        for device in devices:
            display_name = f"{device['type'].upper()}: {device['name']}"
            self.combo_device.addItem(display_name, device['id'])
        
        gpu_layout.addRow("Compute Device:", self.combo_device)
        
        # Device info label
        self.lbl_device_info = QLabel("")
        self.lbl_device_info.setStyleSheet("color: gray; font-size: 11px;")
        gpu_layout.addRow("", self.lbl_device_info)
        
        gpu_group.setLayout(gpu_layout)
        layout.addWidget(gpu_group)
        
        # Batch Sizes Group
        batch_group = QGroupBox("Batch Sizes (GPU Memory Usage)")
        batch_layout = QFormLayout()
        
        # Info label
        info_label = QLabel("Larger batches = faster but more GPU memory.\nReduce if you get out-of-memory errors.")
        info_label.setStyleSheet("color: gray; font-size: 11px;")
        batch_layout.addRow(info_label)
        
        # CLIP batch size
        self.spin_clip = QSpinBox()
        self.spin_clip.setRange(1, 256)
        self.spin_clip.setValue(8)
        self.spin_clip.setToolTip("CLIP is memory-intensive. Recommended: 4-8")
        batch_layout.addRow("CLIP Batch Size:", self.spin_clip)
        
        # BLIP batch size
        self.spin_blip = QSpinBox()
        self.spin_blip.setRange(1, 256)
        self.spin_blip.setValue(8)
        self.spin_blip.setToolTip("BLIP is memory-intensive. Recommended: 4-8")
        batch_layout.addRow("BLIP Batch Size:", self.spin_blip)
        
        # MobileNet batch size
        self.spin_mobilenet = QSpinBox()
        self.spin_mobilenet.setRange(1, 256)
        self.spin_mobilenet.setValue(16)
        self.spin_mobilenet.setToolTip("MobileNet is lightweight. Recommended: 16-32")
        batch_layout.addRow("MobileNet Batch Size:", self.spin_mobilenet)
        
        batch_group.setLayout(batch_layout)
        layout.addWidget(batch_group)

        # Database Maintenance
        db_group = QGroupBox("Database Maintenance")
        db_layout = QHBoxLayout()
        
        self.btn_cleanup = QPushButton("Remove Obsolete Data")
        self.btn_cleanup.setToolTip("Remove files that no longer exist and optimize database.")
        self.btn_cleanup.clicked.connect(self._run_maintenance)
        db_layout.addWidget(self.btn_cleanup)
        
        db_group.setLayout(db_layout)
        layout.addWidget(db_group)
        
        # Buttons
        btn_layout = QHBoxLayout()
        
        self.btn_reset = QPushButton("Reset to Defaults")
        self.btn_reset.clicked.connect(self._reset_defaults)
        btn_layout.addWidget(self.btn_reset)
        
        btn_layout.addStretch()
        
        self.btn_cancel = QPushButton("Cancel")
        self.btn_cancel.clicked.connect(self.reject)
        btn_layout.addWidget(self.btn_cancel)
        
        self.btn_save = QPushButton("Save")
        self.btn_save.setDefault(True)
        self.btn_save.clicked.connect(self._save_and_close)
        btn_layout.addWidget(self.btn_save)
        
        layout.addLayout(btn_layout)
        
        # Connect signals
        self.combo_device.currentIndexChanged.connect(self._update_device_info)
    
    def _load_current_settings(self):
        """Load current settings into the dialog."""
        # Device
        current_device = self.config.get_device_id()
        index = self.combo_device.findData(current_device)
        if index >= 0:
            self.combo_device.setCurrentIndex(index)
        
        # Batch sizes
        batch_sizes = self.config.get_all_batch_sizes()
        self.spin_clip.setValue(batch_sizes.get('clip', 8))
        self.spin_blip.setValue(batch_sizes.get('blip', 8))
        self.spin_mobilenet.setValue(batch_sizes.get('mobilenet', 16))
        
        self._update_device_info()
    
    def _update_device_info(self):
        """Update the device info label based on selection."""
        device_id = self.combo_device.currentData()
        
        if device_id == "auto":
            self.lbl_device_info.setText("Automatically selects: DirectML → CUDA → CPU")
        elif device_id.startswith("directml"):
            self.lbl_device_info.setText("DirectML: Works with Intel, AMD, and some NVIDIA GPUs")
        elif device_id.startswith("cuda"):
            self.lbl_device_info.setText("CUDA: Native NVIDIA GPU acceleration (fastest for NVIDIA)")
        else:
            self.lbl_device_info.setText("No GPU acceleration - slowest option")
    
    def _reset_defaults(self):
        """Reset all settings to defaults."""
        self.combo_device.setCurrentIndex(0)  # Auto
        self.spin_clip.setValue(8)
        self.spin_blip.setValue(8)
        self.spin_mobilenet.setValue(16)
    
    def _save_and_close(self):
        """Save settings and close dialog."""
        from core.gpu_config import clear_device_cache
        
        # Save device
        device_id = self.combo_device.currentData()
        self.config.set_device_id(device_id)
        
        # Save batch sizes
        self.config.set_batch_size('clip', self.spin_clip.value())
        self.config.set_batch_size('blip', self.spin_blip.value())
        self.config.set_batch_size('mobilenet', self.spin_mobilenet.value())
        
        # Persist to file
        self.config.save_config()
        
        # Clear device cache so changes take effect
        clear_device_cache()
        
        logger.info(f"Settings saved: device={device_id}, batch_sizes=clip:{self.spin_clip.value()}, blip:{self.spin_blip.value()}, mobilenet:{self.spin_mobilenet.value()}")
        
        QMessageBox.information(
            self, 
            "Settings Saved", 
            "Settings have been saved.\n\nNote: GPU device changes will take effect on the next scan."
        )
        
        self.accept()

    def _run_maintenance(self):
        """Run database maintenance tasks."""
        from core.database import DatabaseManager
        from PySide6.QtWidgets import QProgressDialog
        
        confirm = QMessageBox.question(
            self, "Confirm Maintenance", 
            "This will remove records for files that are no longer on disk and clean up the database.\n"
            "This operation cannot be undone.\n\nContinue?",
            QMessageBox.Yes | QMessageBox.No
        )
        
        if confirm != QMessageBox.Yes:
            return

        db = DatabaseManager()
        
        # Simple progress dialog
        progress = QProgressDialog("Cleaning up database...", "Cancel", 0, 100, self)
        progress.setWindowModality(Qt.WindowModal)
        progress.show()
        
        try:
            # 1. Missing files
            progress.setLabelText("Checking for missing files...")
            
            def update_progress(current, total):
                if progress.wasCanceled(): return
                if total > 0:
                    val = int((current / total) * 50) # First 50%
                    progress.setValue(val)
            
            removed_files = db.cleanup_missing_files(progress_callback=update_progress)
            
            if progress.wasCanceled(): return

            # 2. Orphans
            progress.setLabelText("Cleaning up orphaned records...")
            progress.setValue(60)
            stats = db.cleanup_orphans()
            
            if progress.wasCanceled(): return

            # 3. Optimize
            progress.setLabelText("Optimizing database... (This may take a while)")
            progress.setValue(80)
            db.optimize_database()
            
            progress.setValue(100)
            
            msg = f"Maintenance Complete.\n\nRemoved {removed_files} missing files.\n"
            msg += f"Removed {stats.get('vector_status_removed', 0)} orphaned index records.\n"
            msg += f"Removed {stats.get('relations_removed', 0)} orphaned relations.\n"
            msg += "Database optimized."
            
            QMessageBox.information(self, "Success", msg)
            
        except Exception as e:
            logger.error(f"Maintenance error: {e}")
            QMessageBox.critical(self, "Error", f"An error occurred during maintenance:\n{e}")
        finally:
            progress.close()
            db.close()
