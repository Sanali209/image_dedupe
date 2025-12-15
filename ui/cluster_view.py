import os
import shutil
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QSplitter, QListWidget, 
                                QLabel, QPushButton, QCheckBox, QFrame, QFileDialog, 
                                QListWidgetItem, QMenu, QAbstractItemView, QLineEdit, QMessageBox,
                                QDoubleSpinBox, QComboBox, QGroupBox, QStyledItemDelegate, QStyle, QSizePolicy)
from PySide6.QtCore import Qt, QSize, Signal, QMimeData, QCoreApplication, QRect
from PySide6.QtGui import QPixmap, QIcon, QAction, QPainter, QColor, QFont

from core.deduper import Deduper
from core.thumbnail_manager import ThumbnailManager
from loguru import logger

class ClusterDelegate(QStyledItemDelegate):
    def __init__(self, thumbnail_manager, parent=None):
        super().__init__(parent)
        self.tm = thumbnail_manager
        
    def paint(self, painter, option, index):
        if not index.isValid(): return
        
        # Data
        name = index.data(Qt.DisplayRole)
        cluster_idx = index.data(Qt.UserRole)
        # We need the files to generate preview... 
        # But UserRole stores index. We need access to clusters list?
        # Or store files in UserRole+1?
        # Let's rely on the widget to pass a delegate that knows the data or store paths in data.
        
        files = index.data(Qt.UserRole + 1) # Expecting file list here
        
        painter.save()
        
        # Background
        if option.state & QStyle.State_Selected:
            painter.fillRect(option.rect, option.palette.highlight())
            painter.setPen(option.palette.highlightedText().color())
        else:
            painter.setPen(option.palette.text().color())
            
        rect = option.rect
        
        # Preview Area (Left 100x100)
        preview_size = 100
        preview_rect = QRect(rect.left() + 5, rect.top() + 5, preview_size, preview_size)
        
        if files:
            paths = [f['path'] for f in files]
            pix = self.tm.generate_grid_preview(paths, preview_size)
            if not pix.isNull():
                painter.drawPixmap(preview_rect, pix)
            else:
                painter.fillRect(preview_rect, QColor("#333"))
        else:
             painter.fillRect(preview_rect, QColor("#333"))
             
        # Text Area
        text_rect = QRect(rect.left() + preview_size + 15, rect.top() + 5, rect.width() - preview_size - 20, rect.height() - 10)
        
        # Title
        font_title = painter.font()
        font_title.setBold(True)
        font_title.setPointSize(10)
        painter.setFont(font_title)
        
        title_rect = QRect(text_rect.left(), text_rect.top(), text_rect.width(), 20)
        painter.drawText(title_rect, Qt.AlignLeft | Qt.AlignVCenter, name.split('(')[0].strip())
        
        # Info
        font_info = painter.font()
        font_info.setBold(False)
        font_info.setPointSize(9)
        painter.setFont(font_info)
        
        info_rect = QRect(text_rect.left(), text_rect.top() + 25, text_rect.width(), 20)
        count_text = name.split('(')[1].strip(')') if '(' in name else ""
        painter.drawText(info_rect, Qt.AlignLeft | Qt.AlignVCenter, f"{count_text} items")
        
        painter.restore()
        
    def sizeHint(self, option, index):
        return QSize(200, 110)

class ClusterImageList(QListWidget):
    files_dropped = Signal(list)
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAcceptDrops(True)
        
    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.accept()
        else:
            super().dragEnterEvent(event)
            
    def dragMoveEvent(self, event):
        if event.mimeData().hasUrls():
            event.accept()
        else:
            super().dragMoveEvent(event)
            
    def dropEvent(self, event):
        if event.mimeData().hasUrls():
            event.accept()
            files = []
            for url in event.mimeData().urls():
                if url.isLocalFile():
                    files.append(url.toLocalFile())
            if files:
                self.files_dropped.emit(files)
        else:
            super().dropEvent(event)

class ClusterViewWidget(QWidget):
    def __init__(self, db_manager):
        super().__init__()
        self.db = db_manager
        self.deduper = Deduper(db_manager)
        self.clusters = [] 
        
        # Initialize Thumbnail Manager
        self.tm = ThumbnailManager()
        self.tm.thumbnail_ready.connect(self.on_thumbnail_ready)
        
        self.init_ui()
        
    def init_ui(self):
        layout = QVBoxLayout(self)
        
        # --- Top: Configuration ---
        # We use a horizontal layout for the top panel, split into Standard and AI config
        config_panel = QHBoxLayout()
        
        # Standard Config Group
        config_group = QGroupBox("Standard Config")
        config_layout = QVBoxLayout()
        
        row_chk1 = QHBoxLayout()
        self.chk_exact = QCheckBox("Exact Hash") # Restored
        self.chk_ai_match = QCheckBox("AI Matches") # New strict control
        self.chk_exact.setChecked(True)
        self.chk_ai_match.setChecked(True)
        self.chk_similar = QCheckBox("Similar (User)")
        self.chk_similar.setChecked(True)
        self.chk_same_set = QCheckBox("Same Set")
        self.chk_not_dup = QCheckBox("Not Duplicate")
        
        row_chk1.addWidget(self.chk_exact)
        row_chk1.addWidget(self.chk_ai_match)
        row_chk1.addWidget(self.chk_same_set)
        row_chk1.addWidget(self.chk_not_dup)
        
        row_chk2 = QHBoxLayout()
        self.chk_crop = QCheckBox("Similar Crop")
        self.chk_style = QCheckBox("Similar Style")
        self.chk_other = QCheckBox("Other")
        # Saved AI matches are now implicit
        
        row_chk2.addWidget(self.chk_crop)
        row_chk2.addWidget(self.chk_style)
        row_chk2.addWidget(self.chk_other)
        
        config_layout.addLayout(row_chk1)
        config_layout.addLayout(row_chk2)
        config_group.setLayout(config_layout)
        
        config_panel.addWidget(config_group)
        
        # AI Config Group
        ai_group = QGroupBox("On-Demand AI Clustering (Slow)")
        ai_layout = QVBoxLayout()
        
        row_ai_1 = QHBoxLayout()
        self.chk_ai = QCheckBox("Run On-the-fly AI Similarity")
        self.chk_ai.toggled.connect(self.toggle_ai_controls)
        row_ai_1.addWidget(self.chk_ai)
        
        row_ai_2 = QHBoxLayout()
        self.combo_ai_engine = QComboBox()
        self.combo_ai_engine.addItems(["CLIP", "BLIP", "MobileNet"])
        self.combo_ai_engine.setEnabled(False)
        
        self.spin_ai_thresh = QDoubleSpinBox()
        self.spin_ai_thresh.setRange(0.0, 1.0)
        self.spin_ai_thresh.setSingleStep(0.05)
        self.spin_ai_thresh.setValue(0.1)
        self.spin_ai_thresh.setEnabled(False)
        
        row_ai_2.addWidget(QLabel("Engine:"))
        row_ai_2.addWidget(self.combo_ai_engine)
        row_ai_2.addWidget(QLabel("Dist <"))
        row_ai_2.addWidget(self.spin_ai_thresh)
        
        ai_layout.addLayout(row_ai_1)
        ai_layout.addLayout(row_ai_2)
        ai_group.setLayout(ai_layout)
        ai_group.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        
        config_panel.addWidget(ai_group)
        
        # Action Buttons (Refresh)
        btn_layout = QVBoxLayout()
        btn_layout.setAlignment(Qt.AlignCenter)
        self.btn_detect = QPushButton("Detect\nClusters")
        self.btn_detect.setMinimumHeight(50)
        self.btn_detect.clicked.connect(self.detect_clusters)
        btn_layout.addWidget(self.btn_detect)
        
        config_panel.addLayout(btn_layout)
        
        layout.addLayout(config_panel)
        
        # --- Main: Splitter ---
        splitter = QSplitter(Qt.Horizontal)
        splitter.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding) # Vital for half-dialog fix
        
        # Left: List of Clusters
        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(0,0,0,0)
        left_layout.addWidget(QLabel("<b>Clusters</b>"))
        
        self.cluster_list = QListWidget()
        # Set Delegate
        self.delegate = ClusterDelegate(self.tm)
        self.cluster_list.setItemDelegate(self.delegate)
        # Set Grid Grid mode? No, list mode with custom paint is fine.
        self.cluster_list.setVerticalScrollMode(QAbstractItemView.ScrollPerPixel)
        self.cluster_list.itemSelectionChanged.connect(self.on_cluster_selected)
        self.cluster_list.setContextMenuPolicy(Qt.CustomContextMenu)
        self.cluster_list.customContextMenuRequested.connect(self.show_cluster_context_menu)
        left_layout.addWidget(self.cluster_list)
        
        splitter.addWidget(left_widget)
        splitter.setStretchFactor(0, 1)
        
        # Right: Images Grid
        center_widget = QWidget()
        center_layout = QVBoxLayout(center_widget)
        center_layout.setContentsMargins(0,0,0,0)
        center_layout.addWidget(QLabel("<b>Cluster Contents (Drag to Move)</b>"))
        
        self.image_list = ClusterImageList()
        self.image_list.setViewMode(QListWidget.IconMode)
        self.image_list.setIconSize(QSize(150, 150))
        self.image_list.setResizeMode(QListWidget.Adjust) # Reflow
        self.image_list.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.image_list.setDragEnabled(True) 
        self.image_list.files_dropped.connect(self.handle_dropped_files)
        self.image_list.setContextMenuPolicy(Qt.CustomContextMenu)
        self.image_list.customContextMenuRequested.connect(self.show_image_context_menu)
        center_layout.addWidget(self.image_list)
        
        # Bottom Actions for Selected Cluster
        action_layout = QHBoxLayout()
        action_layout.addWidget(QLabel("Move Cluster To:"))
        self.path_edit = QLineEdit()
        self.btn_browse = QPushButton("Browse...")
        self.btn_execute = QPushButton("Move All Files")
        self.btn_browse.clicked.connect(self.browse_target)
        self.btn_execute.clicked.connect(self.move_cluster_files)
        
        action_layout.addWidget(self.path_edit)
        action_layout.addWidget(self.btn_browse)
        action_layout.addWidget(self.btn_execute)
        
        center_layout.addLayout(action_layout)
        
        splitter.addWidget(center_widget)
        splitter.setStretchFactor(1, 4)
        
        layout.addWidget(splitter)
        
    def toggle_ai_controls(self, checked):
        self.combo_ai_engine.setEnabled(checked)
        self.spin_ai_thresh.setEnabled(checked)

    def detect_clusters(self):
        logger.info("UI: detect_clusters button clicked.")
        criteria = {
            'exact_hash': self.chk_exact.isChecked(),
            'ai_match': self.chk_ai_match.isChecked(),
            'similar': self.chk_similar.isChecked(),
            'same_set': self.chk_same_set.isChecked(),
            'not_duplicate': self.chk_not_dup.isChecked(),
            'similar_crop': self.chk_crop.isChecked(),
            'similar_style': self.chk_style.isChecked(),
            'other': self.chk_other.isChecked(),
            'ai_similarity': self.chk_ai.isChecked(),
            'ai_threshold': self.spin_ai_thresh.value()
        }
        
        if criteria['ai_similarity']:
            engine_name = self.combo_ai_engine.currentText().lower()
            try:
                QCoreApplication.processEvents() # Flush UI
                # We should warn user this might be slow
                self.deduper.set_engine(engine_name)
            except Exception as e:
                QMessageBox.critical(self, "AI Engine Error", str(e))
                return
        
        self.clusters = self.deduper.process_clusters(criteria)
        self.refresh_cluster_list()
        
        # Use new persistence logic
    def refresh_cluster_list(self):
        self.cluster_list.clear()
        for i, clust in enumerate(self.clusters):
            # clust is now a dict: {'id', 'name', 'folder', 'files'}
            name = clust['name']
            count = len(clust['files'])
            
            # Pass file list for preview
            files = clust.get('files', [])
            
            item = QListWidgetItem(f"{name} ({count} items)")
            item.setData(Qt.UserRole, i) # Store index 
            item.setData(Qt.UserRole + 1, files) # Store files for delegate
            
            self.cluster_list.addItem(item)
            
        if self.clusters:
            # self.cluster_list.setCurrentRow(0) # Logic seems fine
            pass
        else:
            self.image_list.clear()
            
    def on_cluster_selected(self):
        items = self.cluster_list.selectedItems()
        if not items: return
        
        row = items[0].data(Qt.UserRole)
        if row < 0 or row >= len(self.clusters): return
        
        cluster = self.clusters[row]
        self.image_list.clear()
        
        # Set Target Folder
        self.path_edit.blockSignals(True)
        self.path_edit.setText(cluster.get('target_folder', ''))
        self.path_edit.blockSignals(False)
        
        try: self.path_edit.editingFinished.disconnect()
        except: pass
        self.path_edit.editingFinished.connect(lambda: self.save_target_folder(row))
        
        for f in cluster['files']:
            item = QListWidgetItem()
            # item.setText(os.path.basename(f['path']))
            item.setToolTip(f['path'])
            item.setData(Qt.UserRole, f['path'])
            
            # Use Thumbnail Manager
            pix = self.tm.get_thumbnail(f['path'], 150)
            if not pix.isNull():
                item.setIcon(QIcon(pix))
            else:
                item.setText("Loading...")
                
            self.image_list.addItem(item)
            
    def on_thumbnail_ready(self, path, pix):
        # Update image list items
        for i in range(self.image_list.count()):
            item = self.image_list.item(i)
            if item.data(Qt.UserRole) == path:
                 item.setIcon(QIcon(pix))
                 item.setText("") # Clear loading text
                 
    def show_cluster_context_menu(self, pos):
        item = self.cluster_list.itemAt(pos)
        if not item: return
        idx = item.data(Qt.UserRole)
        cluster = self.clusters[idx]
        
        menu = QMenu()
        action_rename = menu.addAction("Rename Cluster")
        action_delete = menu.addAction("Delete Cluster")
        menu.addSeparator()
        action_open = menu.addAction("Open Target Folder")
        
        action = menu.exec(self.cluster_list.mapToGlobal(pos))
        
        if action == action_rename:
            self.rename_cluster_dialog(idx)
        elif action == action_delete:
            self.delete_cluster_action(idx)
        elif action == action_open:
            if cluster['target_folder'] and os.path.exists(cluster['target_folder']):
                self.open_in_explorer(cluster['target_folder'])
            else:
                QMessageBox.warning(self, "Error", "Target folder not set or does not exist.")
            
    def ensure_cluster_persistence(self, idx):
        """If cluster at idx is transient (negative ID), create it in DB."""
        if idx < 0 or idx >= len(self.clusters): return None
        cluster = self.clusters[idx]
        if cluster['id'] >= 0: return cluster['id']
        
        # It's transient. Create in DB.
        c_id = self.db.create_cluster(cluster['name'], cluster['target_folder'])
        cluster['id'] = c_id # Update memory
        
        # Persist members
        paths = [f['path'] for f in cluster['files']]
        if paths:
            self.db.add_cluster_members(c_id, paths)
            
        logger.info(f"Persisted transient cluster '{cluster['name']}' to ID {c_id}")
        return c_id

    def save_target_folder(self, row):
        if row < 0 or row >= len(self.clusters): return
        self.ensure_cluster_persistence(row) # Ensure it exists
        
        new_path = self.path_edit.text()
        cluster_id = self.clusters[row]['id']
        self.db.update_cluster(cluster_id, target_folder=new_path)
        self.clusters[row]['target_folder'] = new_path
            
    def rename_cluster_dialog(self, idx):
        from PySide6.QtWidgets import QInputDialog
        old_name = self.clusters[idx]['name']
        new_name, ok = QInputDialog.getText(self, "Rename Cluster", "New Name:", text=old_name)
        if ok and new_name:
            self.ensure_cluster_persistence(idx) # Ensure it exists
            c_id = self.clusters[idx]['id']
            self.db.update_cluster(c_id, name=new_name)
            
            self.clusters[idx]['name'] = new_name
            self.refresh_cluster_list()
            self.cluster_list.setCurrentRow(idx)

    def move_image_to_cluster(self, paths, target_idx):
        # Move logic:
        # 1. Remove from current cluster (in DB and Memory)
        # 2. Add to target cluster (in DB and Memory)
        if isinstance(paths, str): paths = [paths]
        
        self.ensure_cluster_persistence(target_idx) # Ensure target exists
        
        current_idx = self.cluster_list.currentRow()
        current_cluster = self.clusters[current_idx]
        target_cluster = self.clusters[target_idx]
        
        self.db.connect()
        
        moved_count = 0
        for path in paths:
            # Find file obj in memory
            file_obj = None
            idx_to_remove = -1
            for i, f in enumerate(current_cluster['files']):
                if f['path'] == path:
                    file_obj = f
                    idx_to_remove = i
                    break
            
            if file_obj:
                # Update Memory
                current_cluster['files'].pop(idx_to_remove)
                target_cluster['files'].append(file_obj)
                
                # Update DB
                # If current is transient, delete fails gracefully (0 rows).
                # But if current IS real, we must remove.
                if current_cluster['id'] >= 0:
                    self.db.conn.execute("DELETE FROM cluster_members WHERE cluster_id = ? AND file_path = ?", (current_cluster['id'], path))
                
                # Target is guaranteed real now
                self.db.conn.execute("INSERT OR IGNORE INTO cluster_members (cluster_id, file_path) VALUES (?, ?)", (target_cluster['id'], path))
                moved_count += 1
                
        self.db.conn.commit()
        
        if moved_count > 0:
            self.on_cluster_selected(current_idx) # Refresh view
            # Optional: Show status
            # self.statusBar().showMessage(f"Moved {moved_count} files", 2000)

    def clear_all_clusters(self):
        res = QMessageBox.warning(self, "Clear All Clusters", 
                                  "Are you sure you want to DELETE ALL CLUSTERS?\nThis action cannot be undone.", 
                                  QMessageBox.Yes | QMessageBox.No)
        if res == QMessageBox.Yes:
            self.db.delete_all_clusters()
            self.clusters = []
            self.refresh_cluster_list()
            self.image_list.clear() # Clear view
            QMessageBox.information(self, "Cleared", "All clusters have been deleted.")

    def handle_dropped_files(self, file_paths):
        row = self.cluster_list.currentRow()
        if row < 0 or row >= len(self.clusters):
            QMessageBox.warning(self, "No Cluster", "Please select a cluster first.")
            return

        cluster = self.clusters[row]
        current_paths = {f['path'] for f in cluster['files']}
        
        added_count = 0
        duplicates = 0
        valid_extensions = {'.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp', '.tiff'}
        
        for path in file_paths:
            if not os.path.isfile(path): continue
            
            ext = os.path.splitext(path)[1].lower()
            if ext not in valid_extensions: continue
            
            # Duplicate Assist: Prevent adding same path
            if path in current_paths:
                duplicates += 1
                continue
            
            try:
                # Add to DB cluster_members
                self.db.add_cluster_members(cluster['id'], [path])
                
                # Fetch basic metadata for UI display using existing DB util if possible
                f_obj = self.db.get_file_by_path(path)
                if not f_obj:
                    # Manually construct
                    f_obj = {
                        'path': path,
                        'file_size': os.path.getsize(path),
                        'width': 0, 'height': 0, 'phash': '', 'last_modified': 0
                    }
                
                cluster['files'].append(f_obj)
                current_paths.add(path)
                added_count += 1
                
            except Exception as e:
                print(f"Error adding dropped file: {e}")
                
        if added_count > 0:
            self.refresh_cluster_list() # Update count in sidebar
            self.cluster_list.setCurrentRow(row) # Refresh selection/grid
            # Status bar update if available
            parent = self.parent()
            while parent:
                if hasattr(parent, "statusBar"): 
                    parent.statusBar().showMessage(f"Added {added_count} files.", 3000)
                    break
                parent = parent.parent()
            
        if duplicates > 0:
            QMessageBox.information(self, "Duplicates Skipped", f"{duplicates} files were already in this cluster.")

    def create_new_cluster(self):
        # Create in DB
        idx = len(self.clusters) + 1
        name = f"Cluster {idx} (New)"
        c_id = self.db.create_cluster(name)
        
        # Add to memory
        new_clust = {'id': c_id, 'name': name, 'target_folder': '', 'files': []}
        self.clusters.append(new_clust)
        
        self.refresh_cluster_list()
        self.cluster_list.setCurrentRow(len(self.clusters) - 1)
        
    def select_all_images(self):
        self.image_list.selectAll()
        
    def browse_target(self):
        folder = QFileDialog.getExistingDirectory(self, "Select Target Folder")
        if folder:
            self.path_edit.setText(folder)
            self.save_target_folder(self.cluster_list.currentRow())
            
    def move_cluster_files(self):
        row = self.cluster_list.currentRow()
        if row == -1: return
        
        target_dir = self.path_edit.text()
        if not target_dir or not os.path.isdir(target_dir):
            QMessageBox.warning(self, "Error", "Invalid target directory")
            return
            
        cluster = self.clusters[row]
        if not cluster['files']:
            QMessageBox.warning(self, "Empty", "Cluster is empty")
            return
            
        confirm = QMessageBox.question(self, "Confirm Move", f"Move {len(cluster['files'])} files to {target_dir}?")
        if confirm != QMessageBox.Yes: return
        
        failed = []
        moved_count = 0
        
        # Copy list to iterate safely while modifying
        for f in list(cluster['files']): 
            try:
                fname = os.path.basename(f['path'])
                new_path = os.path.join(target_dir, fname)
                
                # Resolve name conflict
                counter = 1
                base, ext = os.path.splitext(new_path)
                while os.path.exists(new_path):
                    new_path = f"{base}_{counter}{ext}"
                    counter += 1
                
                os.makedirs(os.path.dirname(new_path), exist_ok=True)
                shutil.move(f['path'], new_path)
                self.db.move_file(f['path'], new_path)
                
                # Update in memory
                f['path'] = new_path
                moved_count += 1
                
            except Exception as e:
                failed.append(f['path'])
                
        if failed:
            QMessageBox.warning(self, "Partial Success", f"Moved {moved_count} files.\nFailed: {len(failed)}")
        else:
            QMessageBox.information(self, "Success", f"Moved {moved_count} files.")
            
        # Refresh current view
        self.on_cluster_selected(row)

    def delete_cluster_action(self, idx):
        res = QMessageBox.warning(self, "Delete Cluster", 
                                  "Are you sure you want to delete this cluster?\nFiles will NOT be deleted from disk, just ungrouped.", 
                                  QMessageBox.Yes | QMessageBox.No)
        if res == QMessageBox.Yes:
            c_id = self.clusters[idx]['id']
            # If persists, delete. If transient, just remove.
            if c_id >= 0:
                self.db.delete_cluster(c_id)
            self.clusters.pop(idx)
            self.refresh_cluster_list()

    def show_image_context_menu(self, pos):
        # Get all selected items
        selected_items = self.image_list.selectedItems()
        if not selected_items:
            # Fallback to item at pos
            item = self.image_list.itemAt(pos)
            if item: selected_items = [item]
            else: return

        paths = [item.data(Qt.UserRole) for item in selected_items]
        if not paths: return
        
        menu = QMenu()
        action_open = menu.addAction("Show in Explorer")
        action_remove = menu.addAction("Remove from Cluster")
        
        # Submenu for Move to Cluster
        move_menu = menu.addMenu(f"Move {len(paths)} to Cluster...")
        for i, c in enumerate(self.clusters):
            if i == self.cluster_list.currentRow(): continue 
            act = move_menu.addAction(c['name'])
            act.setData(i)
        
        action = menu.exec(self.image_list.mapToGlobal(pos))
        
        if action == action_open:
            self.open_in_explorer(paths[0])
        elif action == action_remove:
            self.remove_images_from_cluster(paths)
        elif action and action.parent() == move_menu:
            target_idx = action.data()
            self.move_image_to_cluster(paths, target_idx)
            
    def remove_images_from_cluster(self, paths):
        row = self.cluster_list.currentRow()
        if row == -1: return
        cluster = self.clusters[row]
        c_id = cluster['id']
        
        # Remove from DB if persistent
        if c_id >= 0:
            self.db.connect()
            for p in paths:
                self.db.remove_cluster_member(c_id, p)
            
        # Remove from Memory
        cluster['files'] = [f for f in cluster['files'] if f['path'] not in paths]
        
        # Refresh
        self.on_cluster_selected(row)
        self.refresh_cluster_list()

    def open_in_explorer(self, path):
        import subprocess, platform
        path = os.path.normpath(path)
        if platform.system() == "Windows":
            subprocess.Popen(f'explorer /select,"{path}"')
        elif platform.system() == "Darwin":
            subprocess.Popen(["open", "-R", path])
        else:
            subprocess.Popen(["xdg-open", os.path.dirname(path)])

