import os
import itertools
import re
import subprocess
import platform
from loguru import logger
from core.commands.base import CommandHistory
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QSplitter, QListWidget, QListView, 
                               QLabel, QPushButton, QScrollArea, QFrame, QMessageBox, QListWidgetItem, QMenu,
                               QDialog, QLineEdit, QFileDialog, QDialogButtonBox, QGridLayout, QSizePolicy)
from PySide6.QtCore import Qt, QSize, Signal, QTimer
from PySide6.QtGui import QPixmap, QImage, QFont, QKeySequence, QShortcut
import shutil
from PIL import Image, ImageChops, ImageEnhance, ImageOps
import numpy as np
from core.deduper import Deduper
from PySide6.QtCore import QAbstractListModel, QModelIndex

class PairsModel(QAbstractListModel):
    def __init__(self, pairs=None, parent=None):
        super().__init__(parent)
        self._pairs = pairs or []

    def rowCount(self, parent=QModelIndex()):
        return len(self._pairs)

    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid() or not (0 <= index.row() < len(self._pairs)):
            return None
        
        if role == Qt.DisplayRole:
            left, right, rel = self._pairs[index.row()]
            n1 = os.path.basename(left['path'])
            n2 = os.path.basename(right['path'])
            return f"{n1} vs {n2}"
        
        return None

    def setPairs(self, pairs):
        self.beginResetModel()
        self._pairs = pairs
        self.endResetModel()

    def removePairAt(self, index):
        if 0 <= index < len(self._pairs):
            self.beginRemoveRows(QModelIndex(), index, index)
            del self._pairs[index]
            self.endRemoveRows()
            return True
        return False

class MoveFileDialog(QDialog):
    def __init__(self, current_path, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Move File")
        self.resize(500, 150)
        self.layout = QVBoxLayout(self)
        
        self.layout.addWidget(QLabel(f"Moving: {os.path.basename(current_path)}"))
        self.layout.addWidget(QLabel("To Location:"))
        
        browse_layout = QHBoxLayout()
        self.path_edit = QLineEdit(current_path)
        self.btn_browse = QPushButton("Browse Folder...")
        browse_layout.addWidget(self.path_edit)
        browse_layout.addWidget(self.btn_browse)
        self.layout.addLayout(browse_layout)
        
        self.buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        self.layout.addWidget(self.buttons)
        
        self.btn_browse.clicked.connect(self.browse_folder)
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        
    def browse_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Select Destination Folder", os.path.dirname(self.path_edit.text()))
        if folder:
            filename = os.path.basename(self.path_edit.text())
            new_path = os.path.join(folder, filename)
            self.path_edit.setText(new_path)

    def get_new_path(self):
        return self.path_edit.text()

class ComparisonWidget(QWidget):
    file_moved = Signal(str, str) # old_path, new_path
    smart_action = Signal(str) # 'size', 'res'
    replace_action = Signal(str) # 'l_r', 'r_l'
    
    action_delete_left = Signal()
    action_delete_right = Signal()
    action_ignore = Signal(str) # reason
    action_prev = Signal()
    action_next = Signal()
    action_diff_toggle = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        
        self.layout = QHBoxLayout(self) # Panels Layout
        
        # --- LEFT PANEL (IMAGES) ---
        self.panel_images = QWidget()
        img_layout = QVBoxLayout(self.panel_images)
        img_layout.setContentsMargins(0,0,0,0)
        
        self.lbl_img_top = self.create_img_label("left")   
        self.lbl_img_bottom = self.create_img_label("right") 
        
        img_layout.addWidget(self.lbl_img_top)
        img_layout.addWidget(self.lbl_img_bottom)
        
        self.layout.addWidget(self.panel_images, 1)  # Stretch to fill available space
        
        # --- RIGHT PANEL (CONTROLS) ---
        self.panel_controls = QWidget()
        self.panel_controls.setMinimumWidth(500)  # Fixed minimum width
        self.panel_controls.setMaximumWidth(500)  # Fixed maximum width
        ctrl_layout = QVBoxLayout(self.panel_controls)
        ctrl_layout.setAlignment(Qt.AlignTop)
        
        
        # 1. Header Area (Status + Diff)
        self.lbl_status = QLabel("Status: New Match")
        self.lbl_status.setAlignment(Qt.AlignCenter)
        self.lbl_status.setStyleSheet("font-weight: bold; font-size: 14px; color: #44ee44; margin-bottom: 10px;")
        
        self.lbl_distance = QLabel("Distance: N/A")
        self.lbl_distance.setAlignment(Qt.AlignCenter)
        self.lbl_distance.setStyleSheet("font-size: 12px; color: #aaaaaa; margin-bottom: 5px;")
        
        self.btn_diff = QPushButton("Show Visual Diff")
        self.btn_diff.setCheckable(True)
        self.btn_diff.clicked.connect(self.action_diff_toggle.emit)
        
        ctrl_layout.addWidget(self.lbl_status)
        ctrl_layout.addWidget(self.lbl_distance)
        ctrl_layout.addWidget(self.btn_diff)
        ctrl_layout.addSpacing(10)
        
        # 2. Annotation Buttons (MOVED TO TOP for better UX)
        ign_layout = QGridLayout()
        ign_layout.setSpacing(5)
        
        # Define buttons
        btn_dup = QPushButton("Duplicate")
        btn_near = QPushButton("Near Duplicate")
        btn_sim = QPushButton("Similar")
        btn_crop = QPushButton("Crop Duplicate")
        btn_style = QPushButton("Similar Style")
        btn_person = QPushButton("Same Person")
        btn_set = QPushButton("Same Image Set")
        btn_other = QPushButton("Other")
        btn_not = QPushButton("Not Duplicate")
        
        # Connect signals
        btn_dup.clicked.connect(lambda: self.action_ignore.emit('duplicate'))
        btn_near.clicked.connect(lambda: self.action_ignore.emit('near_duplicate'))
        btn_sim.clicked.connect(lambda: self.action_ignore.emit('similar'))
        btn_crop.clicked.connect(lambda: self.action_ignore.emit('crop_duplicate'))
        btn_style.clicked.connect(lambda: self.action_ignore.emit('similar_style'))
        btn_person.clicked.connect(lambda: self.action_ignore.emit('same_person'))
        btn_set.clicked.connect(lambda: self.action_ignore.emit('same_image_set'))
        btn_other.clicked.connect(lambda: self.action_ignore.emit('other'))
        btn_not.clicked.connect(lambda: self.action_ignore.emit('not_duplicate'))
        
        # Add to Grid (3 cols)
        ign_layout.addWidget(btn_dup, 0, 0)
        ign_layout.addWidget(btn_near, 0, 1)
        ign_layout.addWidget(btn_sim, 0, 2)
        ign_layout.addWidget(btn_crop, 1, 0)
        ign_layout.addWidget(btn_style, 1, 1)
        ign_layout.addWidget(btn_person, 1, 2)
        ign_layout.addWidget(btn_set, 2, 0)
        ign_layout.addWidget(btn_other, 2, 1)
        ign_layout.addWidget(btn_not, 2, 2)
        
        ctrl_layout.addLayout(ign_layout)
        ctrl_layout.addSpacing(20)
        
        # 3. Attribute Grid (Names, Sizes, Dimensions, Delete Buttons)
        self.grid = QGridLayout()
        self.grid.setHorizontalSpacing(15)
        self.grid.setVerticalSpacing(15)
        
        # -- Column 0: Sizes --
        self.lbl_size_top = QLabel()
        self.lbl_size_bottom = QLabel()
        self.btn_del_size = QPushButton("Delete Smaller")
        self.btn_del_size.clicked.connect(lambda: self.smart_action.emit('size'))
        
        vbox_sizes = QVBoxLayout()
        vbox_sizes.addWidget(QLabel("<b>Top Size:</b>"))
        vbox_sizes.addWidget(self.lbl_size_top)
        vbox_sizes.addSpacing(10)
        vbox_sizes.addWidget(QLabel("<b>Bottom Size:</b>"))
        vbox_sizes.addWidget(self.lbl_size_bottom)
        vbox_sizes.addWidget(self.btn_del_size)
        w_sizes = QWidget(); w_sizes.setLayout(vbox_sizes)
        
        self.grid.addWidget(w_sizes, 0, 0)

        # -- Column 1: Dimensions --
        self.lbl_res_top = QLabel()
        self.lbl_res_bottom = QLabel()
        self.btn_del_res = QPushButton("Delete Lower Res")
        self.btn_del_res.clicked.connect(lambda: self.smart_action.emit('res'))
        
        vbox_res = QVBoxLayout()
        vbox_res.addWidget(QLabel("<b>Top Dim:</b>"))
        vbox_res.addWidget(self.lbl_res_top)
        vbox_res.addSpacing(10)
        vbox_res.addWidget(QLabel("<b>Bottom Dim:</b>"))
        vbox_res.addWidget(self.lbl_res_bottom)
        vbox_res.addWidget(self.btn_del_res)
        w_res = QWidget(); w_res.setLayout(vbox_res)
        
        self.grid.addWidget(w_res, 0, 1)
        
        # -- Column 2: Delete Buttons --
        self.btn_del_top = QPushButton("Delete Top")
        self.btn_del_top.setStyleSheet("background-color: #552222; font-weight: bold; min-height: 30px;")
        self.btn_del_top.clicked.connect(self.action_delete_left.emit)
        
        self.btn_del_bottom = QPushButton("Delete Bottom")
        self.btn_del_bottom.setStyleSheet("background-color: #552222; font-weight: bold; min-height: 30px;")
        self.btn_del_bottom.clicked.connect(self.action_delete_right.emit)
        
        vbox_del = QVBoxLayout()
        vbox_del.setAlignment(Qt.AlignVCenter)
        vbox_del.addWidget(self.btn_del_top)
        vbox_del.addSpacing(20)
        vbox_del.addWidget(self.btn_del_bottom)
        w_del = QWidget(); w_del.setLayout(vbox_del)
        
        self.grid.addWidget(w_del, 0, 2)

        # -- File Details (Names + Paths) --
        self.lbl_name_top = QLabel()
        self.lbl_name_top.setWordWrap(True)
        self.lbl_name_top.setStyleSheet("font-weight: bold;")
        
        self.lbl_name_bottom = QLabel()
        self.lbl_name_bottom.setWordWrap(True)
        self.lbl_name_bottom.setStyleSheet("font-weight: bold;")

        self.lbl_folder_top = QLabel()
        self.lbl_folder_top.setStyleSheet("color: #aaa;")
        self.lbl_folder_top.setWordWrap(True)
        self.lbl_folder_bottom = QLabel()
        self.lbl_folder_bottom.setStyleSheet("color: #aaa;")
        self.lbl_folder_bottom.setWordWrap(True)
        
        vbox_details = QVBoxLayout()
        
        # Top Group
        vbox_details.addWidget(QLabel("<b>Top Image:</b>"))
        vbox_details.addWidget(self.lbl_name_top)
        vbox_details.addWidget(self.lbl_folder_top)
        vbox_details.addSpacing(15)
        
        # Bottom Group
        vbox_details.addWidget(QLabel("<b>Bottom Image:</b>"))
        vbox_details.addWidget(self.lbl_name_bottom)
        vbox_details.addWidget(self.lbl_folder_bottom)
        
        w_details = QWidget(); w_details.setLayout(vbox_details)
        
        self.grid.addWidget(w_details, 1, 0, 1, 3) # Span full width (3 cols)

        ctrl_layout.addLayout(self.grid)
        
        ctrl_layout.addStretch()
        
        # 4. Navigation
        nav_layout = QHBoxLayout()
        self.btn_prev = QPushButton("< Prev Pair")
        self.lbl_counter = QLabel("1 of 1")
        self.lbl_counter.setAlignment(Qt.AlignCenter)
        self.btn_next = QPushButton("Next Pair >")
        
        self.btn_prev.clicked.connect(self.action_prev.emit)
        self.btn_next.clicked.connect(self.action_next.emit)
        
        nav_layout.addWidget(self.btn_prev)
        nav_layout.addWidget(self.lbl_counter)
        nav_layout.addWidget(self.btn_next)
        ctrl_layout.addLayout(nav_layout)
        
        self.layout.addWidget(self.panel_controls, 1) # Stretch factor 1
        
        self.current_pair = None 

    def create_img_label(self, side):
        l = QLabel()
        l.setAlignment(Qt.AlignCenter)
        l.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        l.setMinimumSize(200, 200) 
        l.setStyleSheet("background-color: #222; border: 1px solid #444;")
        l.setContextMenuPolicy(Qt.CustomContextMenu)
        l.setProperty("side", side)
        l.customContextMenuRequested.connect(lambda pos: self.show_context_menu(pos, l))
        return l
        
    def show_context_menu(self, pos, label):
        if not self.current_pair: return
        side = label.property("side")
        path = self.current_pair[0]['path'] if side == 'left' else self.current_pair[1]['path']
        
        menu = QMenu(self)
        action_open = menu.addAction("Show in Explorer")
        action_move = menu.addAction("Move to Folder...")
        menu.addSeparator()
        
        if side == 'left':
            action_replace = menu.addAction("Replace Bottom < Top (Overwrite Bottom)")
        else:
            action_replace = menu.addAction("Replace Top < Bottom (Overwrite Top)")
        
        action = menu.exec(label.mapToGlobal(pos))
        
        if action == action_open:
            self.open_in_explorer(path)
        elif action == action_move:
            self.move_file_dialog(path)
        elif action == action_replace:
            if side == 'left': self.replace_action.emit('r_l') 
            else: self.replace_action.emit('l_r')

    def move_file_dialog(self, current_path):
        dlg = MoveFileDialog(current_path, self)
        if dlg.exec():
            target_path = dlg.get_new_path()
            if target_path != current_path:
                try:
                    final_path = self.resolve_naming_conflict(target_path)
                    os.makedirs(os.path.dirname(final_path), exist_ok=True)
                    shutil.move(current_path, final_path)
                    self.file_moved.emit(current_path, final_path)
                    if final_path != target_path:
                        QMessageBox.information(self, "Renamed", f"Renamed to:\n{os.path.basename(final_path)}")
                except Exception as e:
                    QMessageBox.critical(self, "Error", str(e))

    def resolve_naming_conflict(self, path):
        if not os.path.exists(path): return path
        base, ext = os.path.splitext(path)
        match = re.search(r'_(\d+)$', base)
        if match:
            counter = int(match.group(1))
            prefix = base[:match.start()]
        else:
            counter = 0
            prefix = base
        while True:
            counter += 1
            new_path = f"{prefix}_{counter}{ext}"
            if not os.path.exists(new_path): return new_path

    def open_in_explorer(self, path):
        path = os.path.normpath(path)
        if platform.system() == "Windows":
            subprocess.Popen(f'explorer /select,"{path}"')
        elif platform.system() == "Darwin":
            subprocess.Popen(["open", "-R", path])
        else:
            subprocess.Popen(["xdg-open", os.path.dirname(path)])

    def generate_path_diff_html(self, path_a, path_b):
        # Normalize and split by standard separators
        parts_a = re.split(r'[\\/]', path_a)
        parts_b = re.split(r'[\\/]', path_b)
        
        # Filter out empty strings (e.g. from leading/trailing slashes or double slashes)
        parts_a = [p for p in parts_a if p]
        parts_b = [p for p in parts_b if p]
        
        html_a = []
        html_b = []
        
        limit = max(len(parts_a), len(parts_b))
        
        for i in range(limit):
            seg_a = parts_a[i] if i < len(parts_a) else None
            seg_b = parts_b[i] if i < len(parts_b) else None
            
            if seg_a is not None and seg_b is not None and seg_a.lower() == seg_b.lower():
                # Match (Case insensitive for Windows usually, but let's be visual)
                # Actually, precise string match is better for "identical"
                if seg_a == seg_b:
                    html_a.append(f"<span style='color:#44ee44'>{seg_a}</span>")
                    html_b.append(f"<span style='color:#44ee44'>{seg_b}</span>")
                else: 
                     # Allow case difference? User said similar. 
                     # Let's stick to strict match for green, else red.
                    html_a.append(f"<span style='color:#ff4444'>{seg_a}</span>")
                    html_b.append(f"<span style='color:#ff4444'>{seg_b}</span>")
            else:
                # Mismatch or Missing
                if seg_a is not None:
                    html_a.append(f"<span style='color:#ff4444'>{seg_a}</span>")
                if seg_b is not None:
                    html_b.append(f"<span style='color:#ff4444'>{seg_b}</span>")
        
        sep = "\\" # consistent visual separator
        return (sep.join(html_a), sep.join(html_b))

    def load_pair(self, left, right):
        self.current_pair = (left, right)
        
        self.set_image(self.lbl_img_top, left['path'])
        self.set_image(self.lbl_img_bottom, right['path'])
        
        # Populate separated metadata
        self.lbl_name_top.setText(os.path.basename(left['path']))
        
        # Folder Path Diffing
        html_top, html_bottom = self.generate_path_diff_html(os.path.dirname(left['path']), os.path.dirname(right['path']))
        self.lbl_folder_top.setText(html_top)
        
        self.lbl_name_bottom.setText(os.path.basename(right['path']))
        self.lbl_folder_bottom.setText(html_bottom)
        
        self.lbl_res_top.setText(f"{left['width']} x {left['height']}")
        self.lbl_res_bottom.setText(f"{right['width']} x {right['height']}")
        
        l_mb = left['file_size'] / 1024 / 1024
        r_mb = right['file_size'] / 1024 / 1024
        self.lbl_size_top.setText(f"{l_mb:.2f} MB")
        self.lbl_size_bottom.setText(f"{r_mb:.2f} MB")

    def set_image(self, label, path):
        if not os.path.exists(path):
            label.setText("File Not Found")
            return
        pixmap = QPixmap(path)
        if not pixmap.isNull():
            label.setPixmap(pixmap.scaled(label.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation))
        else:
            label.setText("Invalid Image")

    def clear(self):
        self.current_pair = None
        self.lbl_img_top.clear()
        self.lbl_img_bottom.clear()
        self.lbl_name_top.clear()
        self.lbl_name_bottom.clear()
        self.lbl_folder_top.clear()
        self.lbl_folder_bottom.clear()
        self.lbl_res_top.clear()
        self.lbl_res_bottom.clear()
        self.lbl_size_top.clear()
        self.lbl_size_bottom.clear()
        self.lbl_status.clear()
        self.lbl_counter.clear()


class ResultsWidget(QWidget):
    def __init__(self, session, file_repo, db_manager):
        super().__init__()
        self.session = session
        self.file_repo = file_repo
        self.db = db_manager
        self.deduper = Deduper(self.db, self.file_repo)
        
        self.command_history = CommandHistory()
        
        self.layout = QVBoxLayout(self)
        
        self.splitter = QSplitter(Qt.Horizontal)
        self.layout.addWidget(self.splitter)
        
        self.model = PairsModel()
        self.group_view = QListView()
        self.group_view.setModel(self.model)
        self.group_view.selectionModel().currentRowChanged.connect(self.on_group_selected_idx)
        self.splitter.addWidget(self.group_view)
        
        self.comparison = ComparisonWidget()
        self.splitter.addWidget(self.comparison)
        self.splitter.setStretchFactor(1, 4)
        
        self.comparison.action_delete_left.connect(lambda: self.resolve('delete_left'))
        self.comparison.action_delete_right.connect(lambda: self.resolve('delete_right'))
        self.comparison.action_ignore.connect(lambda reason: self.resolve('ignore', reason))
        
        self.comparison.action_prev.connect(self.prev_image)
        self.comparison.action_next.connect(self.next_image)
        self.comparison.action_diff_toggle.connect(self.update_comparison)
        
        self.comparison.smart_action.connect(self.smart_resolve)
        self.comparison.replace_action.connect(self.resolve)
        self.comparison.file_moved.connect(self.on_file_moved)

        self.groups = []
        self.current_group_idx = -1
        self.right_index = 1

        # Keyboard shortcut for undo
        QShortcut(QKeySequence("Ctrl+Z"), self, self.undo)
    
    def undo(self):
        """Undo the last action."""
        if self.command_history.undo():
            self.refresh_current_view()
    

    def load_results(self, existing_results=None):
        self.include_ignored = self.session.include_ignored
        
        relations = []
        if existing_results is not None:
             relations = existing_results
        else:
             # Initialize engine
             engine_type = self.session.engine
             try:
                 self.deduper.set_engine(engine_type)
                 # Deduper now returns List[FileRelation]
                 relations = self.deduper.find_duplicates(
                     self.session.threshold, 
                     self.session.include_ignored, 
                     self.session.roots
                 )
             except Exception as e:
                 QMessageBox.critical(self, "Engine Error", f"Failed to load engine {engine_type}:\n{e}")
                 return

        # Hydrate relations with file info
        from core.models import FileRelation, RelationType
        
        # 1. Collect all File IDs
        all_ids = set()
        valid_relations = []
        for item in relations:
            if isinstance(item, FileRelation):
                all_ids.add(item.id1)
                all_ids.add(item.id2)
                valid_relations.append(item)
            else:
                pass
        
        logger.info(f"ResultsView: Received {len(relations)} relations, extracted {len(all_ids)} unique file IDs.")

        # 2. Bulk Fetch Files
        files_map = {}
        if all_ids:
            rows = self.file_repo.get_files_by_ids(list(all_ids))
            for r in rows:
                files_map[r['id']] = r
        
        logger.info(f"ResultsView: Hydrated {len(files_map)} files from DB.")

        # 3. Build Pairs List
        self.pairs = []
        for rel in valid_relations:
            # FIX: Properly filter based on annotation mode
            # When "Show Annotated" is OFF (include_ignored=False), only show NEW_MATCH pairs
            if not self.include_ignored:
                if rel.relation_type != RelationType.NEW_MATCH:
                    logger.debug(f"Filtering out {rel.relation_type.value} pair: {rel.id1}<->{rel.id2}")
                    continue
            
            # When "Show Annotated" is ON (include_ignored=True), show all pairs (no filtering)
                
            left = files_map.get(rel.id1)
            right = files_map.get(rel.id2)
            
            if left and right:
                self.pairs.append((left, right, rel))
            else:
                logger.error(
                    f"ResultsView: Missing file data for relation {rel.id1} <-> {rel.id2}. "
                    f"This indicates orphaned database records (relations referencing deleted files). "
                    f"Run database maintenance to clean up orphaned data."
                )

        logger.info(f"ResultsView: Built {len(self.pairs)} pairs for display (Visible only: {not self.include_ignored}).")
        
        # Virtualized Load
        self.model.setPairs(self.pairs)
        
        if self.pairs:
            self.group_view.setCurrentIndex(self.model.index(0, 0))
            self.comparison.setVisible(True)
        else:
            self.comparison.setVisible(False)


    # Virtualization removed the need for load_next_batch


    def is_pair_visible(self, left, right):
        if getattr(self, 'include_ignored', False):
            return True
        # Use IDs for filtering (robust against renames)
        return not self.db.is_ignored(left['id'], right['id'])

    def find_next_visible_index(self, group, start_index, direction=1):
        idx = start_index
        while 1 <= idx < len(group):
            if self.is_pair_visible(group[0], group[idx]):
                return idx
            idx += direction
        return -1


    def on_group_selected_idx(self, current, previous):
        if not current.isValid(): return
        self.current_pair_idx = current.row()
        self.update_comparison()

    # Legacy method signature adapter if needed, but we changed connection
    # def on_group_selected(self, row): ...


    def update_comparison(self):
        if self.current_pair_idx < 0 or self.current_pair_idx >= len(self.pairs): return
        
        left, right, rel = self.pairs[self.current_pair_idx]
        
        self.comparison.load_pair(left, right)
        
        if self.comparison.btn_diff.isChecked():
            self.show_diff_image(left, right)
        
        # Display distance
        if rel and hasattr(rel, 'distance') and rel.distance is not None:
            self.comparison.lbl_distance.setText(f"Distance: {rel.distance:.2f}")
        else:
            self.comparison.lbl_distance.setText("Distance: N/A")
            
        reason = self.db.get_ignore_reason(left['id'], right['id'])
        if reason:
            self.comparison.lbl_status.setText(f"Marked as: {reason}")
            self.comparison.lbl_status.setStyleSheet("color: #eebb00; font-weight: bold; margin-bottom: 10px; font-size: 14px;")
        else:
            self.comparison.lbl_status.setText("Status: New Match")
            self.comparison.lbl_status.setStyleSheet("color: #44ee44; font-weight: bold; margin-bottom: 10px; font-size: 14px;")

        # Navigation is now via list, so disable inner next/prev
        self.comparison.btn_next.setEnabled(False)
        self.comparison.btn_prev.setEnabled(False)
        
        self.comparison.btn_next.setEnabled(self.current_pair_idx < len(self.pairs) - 1)
        self.comparison.btn_prev.setEnabled(self.current_pair_idx > 0)
        
        self.comparison.lbl_counter.setText(f"Pair {self.current_pair_idx + 1} of {len(self.pairs)}")

    def next_image(self):
        if self.current_pair_idx < len(self.pairs) - 1:
            self.group_view.setCurrentIndex(self.model.index(self.current_pair_idx + 1, 0))

    def prev_image(self):
        if self.current_pair_idx > 0:
            self.group_view.setCurrentIndex(self.model.index(self.current_pair_idx - 1, 0))

    def resolve(self, action, reason=None):
        if getattr(self, 'current_pair_idx', -1) == -1: return
        if self.current_pair_idx >= len(self.pairs): return
        
        left, right, rel = self.pairs[self.current_pair_idx]
        
        try:
            if action == 'delete_left':
                deleted_file_id = left['id']
                os.remove(left['path'])
                self.db.mark_deleted(left['path'])
                # NEW: Remove all pairs containing the deleted file from UI
                self.remove_pairs_containing_file(deleted_file_id)
                return  # Exit early since we handled UI update
            elif action == 'delete_right':
                deleted_file_id = right['id']
                os.remove(right['path'])
                self.db.mark_deleted(right['path'])
                # NEW: Remove all pairs containing the deleted file from UI
                self.remove_pairs_containing_file(deleted_file_id)
                return  # Exit early since we handled UI update
            elif action == 'ignore':
                self.db.add_ignored_pair_id(left['id'], right['id'], reason)
                if not getattr(self, 'include_ignored', False):
                    # Hide ignored mode -> Move to next visible
                    # We do NOT pop if we want to potentially see it later if mode toggled.
                    # But previous logic popped. If we pop, we modify the group in memory.
                    # If we don't pop, the count is confused. user: "100 images" -> "1 of 100".
                    # If we hide 99, navigation feels weird if they are still in list (just skipped).
                    # "Comparing 1 & 1 of 100", Press Next -> "Comparing 1 & 100 of 100".
                    # Ideally we reload results.
                    # But for now, let's stick to "Skip".
                    # Wait, if we 'ignore', it becomes invisible.
                    # So we should seek next visible.
                    pass
                else:
                    self.update_comparison()
                    # Auto-advance even in 'Show Annotated' mode for better workflow
                    self.next_image()
                    return 
            elif action == 'l_r': 
                shutil.copy2(right['path'], left['path'])
                self.db.upsert_file(left['path'], None, right['file_size'], right['width'], right['height'], os.path.getmtime(left['path']))
            elif action == 'r_l': 
                shutil.copy2(left['path'], right['path'])
                self.db.upsert_file(right['path'], None, left['file_size'], left['width'], left['height'], os.path.getmtime(right['path']))
                # group.pop(self.right_index) # This was for old group logic
                # Refresh UI (Remove this pair)
            # Efficiently remove current pair from list and select next
            idx = self.current_pair_idx
            
            # Model-based removal
            success = self.model.removePairAt(idx)
            # Note: pairs list inside model is same reference as self.pairs if we passed it?
            # Actually we passed self.pairs but model might have stored it. 
            # If model modifies it, self.pairs is modified too if it's the same object.
            # PairsModel(self.pairs) -> self._pairs = pairs. Yes.
            # So `del self.pairs[idx]` is redundant if model does it.
            # Let's rely on model to do the deletion to ensure consistency.
            # Wait, `removePairAt` executes `del self._pairs[index]`.
            # So we should NOT delete from self.pairs again if they are the same list object.
            
            if idx < len(self.pairs):
                new_idx_q = self.model.index(idx, 0)
                self.group_view.setCurrentIndex(new_idx_q)
                
                # Manual forced update if index matches (signal might not fire if same row reused?)
                # In QListView/QAbstractItemModel, rows shift. 
                # If we remove row 5, row 6 becomes row 5.
                # If selection was 5, does it stay 5?
                # Usually yes. So signal might NOT fire since "current row" is still 5.
                self.current_pair_idx = idx
                self.update_comparison()
                
            elif len(self.pairs) > 0:
                # We were at the end
                new_idx = len(self.pairs) - 1
                self.group_view.setCurrentIndex(self.model.index(new_idx, 0))
                self.current_pair_idx = new_idx
                self.update_comparison()
            else:
                self.comparison.clear() # Clear view
        
        except Exception as e:
            QMessageBox.critical(self, "Error", str(e))
            return



    def smart_resolve(self, criteria):
        if self.current_pair_idx == -1 or self.current_pair_idx >= len(self.pairs): return
        left, right, rel = self.pairs[self.current_pair_idx]
        
        action = None
        if criteria == 'size':
            if left['file_size'] < right['file_size']: action = 'delete_left'
            elif right['file_size'] < left['file_size']: action = 'delete_right'
        elif criteria == 'res':
            if (left['width']*left['height']) < (right['width']*right['height']): action = 'delete_left'
            elif (right['width']*right['height']) < (left['width']*left['height']): action = 'delete_right'
        if action: self.resolve(action)
        else: QMessageBox.information(self, "Info", "Files are equal in this criteria.")

    def remove_pairs_containing_file(self, file_id: int):
        """
        Remove all pairs from the UI list that reference the given file ID.
        Called after deleting a file to cascade the removal to all affected pairs.
        
        Args:
            file_id: The database ID of the deleted file
        """
        indices_to_remove = []
        
        # Find all pairs containing the deleted file
        for idx, (left, right, rel) in enumerate(self.pairs):
            if left['id'] == file_id or right['id'] == file_id:
                indices_to_remove.append(idx)
        
        if not indices_to_remove:
            logger.warning(f"No pairs found containing deleted file ID {file_id}")
            return
        
        logger.info(f"Removing {len(indices_to_remove)} pairs containing deleted file ID {file_id}")
        
        # Remove in reverse order to preserve indices
        for idx in reversed(indices_to_remove):
            self.model.removePairAt(idx)
        
        # Update UI to show next available pair
        if len(self.pairs) > 0:
            # Clamp current_pair_idx to valid range
            self.current_pair_idx = min(self.current_pair_idx, len(self.pairs) - 1)
            self.group_view.setCurrentIndex(self.model.index(self.current_pair_idx, 0))
            self.update_comparison()
        else:
            self.comparison.clear()
            QMessageBox.information(self, "All Pairs Reviewed", 
                "No more pairs to review. All pairs have been processed.")

    def show_diff_image(self, left, right):
        # self.comparison.set_image(self.comparison.lbl_img_top, left['path'])
        try:
            img_l = Image.open(left['path']).convert('RGB')
            img_r = Image.open(right['path']).convert('RGB')
            if img_l.size != img_r.size: img_r = img_r.resize(img_l.size)
            diff = ImageChops.difference(img_l, img_r)
            diff_mag = diff.convert('L')
            diff_mag = ImageOps.autocontrast(diff_mag, cutoff=0)
            highlight = Image.new('RGB', img_r.size, (255, 0, 255))
            combined = img_r.copy()
            combined.paste(highlight, (0,0), diff_mag)
            qim = QImage(combined.convert("RGBA").tobytes("raw", "RGBA"), combined.width, combined.height, QImage.Format_RGBA8888)
            pix = QPixmap.fromImage(qim)
            lbl = self.comparison.lbl_img_bottom
            lbl.setPixmap(pix.scaled(lbl.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation))
        except Exception as e:
            self.comparison.lbl_img_bottom.setText(f"Diff Error: {e}")

    def on_file_moved(self, old_path, new_path):
        self.db.move_file(old_path, new_path)
        # Update pairs in memory
        found = False
        for i, (left, right, rel) in enumerate(self.pairs):
            updated = False
            l_new, r_new = dict(left), dict(right)
            
            if left['path'] == old_path:
                l_new['path'] = new_path
                updated = True
            elif right['path'] == old_path:
                r_new['path'] = new_path
                updated = True
                
            if updated:
                self.pairs[i] = (l_new, r_new, rel)
                found = True
        
        if found and 0 <= self.current_pair_idx < len(self.pairs):
             self.update_comparison()
