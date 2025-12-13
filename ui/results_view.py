import os
import re
import subprocess
import platform
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QSplitter, QListWidget, 
                               QLabel, QPushButton, QScrollArea, QFrame, QMessageBox, QListWidgetItem, QMenu,
                               QDialog, QLineEdit, QFileDialog, QDialogButtonBox, QGridLayout, QSizePolicy)
from PySide6.QtCore import Qt, QSize, Signal
from PySide6.QtGui import QPixmap, QImage, QFont
import shutil
from PIL import Image, ImageChops, ImageEnhance, ImageOps
import numpy as np
from core.deduper import Deduper

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
        
        self.layout.addWidget(self.panel_images, 2)
        
        # --- RIGHT PANEL (CONTROLS) ---
        self.panel_controls = QWidget()
        ctrl_layout = QVBoxLayout(self.panel_controls)
        ctrl_layout.setAlignment(Qt.AlignTop)
        
        # 1. Header Area (Status + Diff)
        # self.lbl_status created in controller usually, but here we own it visually
        self.lbl_status = QLabel("Status: New Match")
        self.lbl_status.setAlignment(Qt.AlignCenter)
        self.lbl_status.setStyleSheet("font-weight: bold; font-size: 14px; color: #44ee44; margin-bottom: 10px;")
        
        self.btn_diff = QPushButton("Show Visual Diff")
        self.btn_diff.setCheckable(True)
        self.btn_diff.clicked.connect(self.action_diff_toggle.emit)
        
        ctrl_layout.addWidget(self.lbl_status)
        ctrl_layout.addWidget(self.btn_diff)
        ctrl_layout.addSpacing(20)
        
        # 2. Attribute Grid
        # Cols: Name | Size | Res | Actions
        self.grid = QGridLayout()
        self.grid.setHorizontalSpacing(15)
        self.grid.setVerticalSpacing(15)
        
        # -- Helpers to create stacked widget pairs --
        def create_stack(w1, w2, w3=None):
            f = QFrame()
            l = QVBoxLayout(f)
            l.setContentsMargins(0,0,0,0)
            l.setSpacing(5)
            l.addWidget(w1)
            l.addWidget(w2)
            if w3: l.addWidget(w3)
            return f

        # -- Column 0: Names --
        self.lbl_name_top = QLabel()
        self.lbl_name_top.setWordWrap(True)
        self.lbl_name_top.setStyleSheet("font-weight: bold;")
        self.lbl_name_bottom = QLabel()
        self.lbl_name_bottom.setWordWrap(True)
        self.lbl_name_bottom.setStyleSheet("font-weight: bold;")
        
        stack_names = create_stack(QLabel("Name (Top)"), self.lbl_name_top, 
                                   create_stack(QLabel("Name (Bottom)"), self.lbl_name_bottom)) 
        # Actually logic says "Top" then "Bottom". Let's grouping nicely.
        # User sketch: "Top Name" Box, "Bottom Name" Box.
        # Better: Just put labels directly in VBox.
        
        vbox_names = QVBoxLayout()
        vbox_names.addWidget(QLabel("<b>Top Name:</b>"))
        vbox_names.addWidget(self.lbl_name_top)
        vbox_names.addSpacing(10)
        vbox_names.addWidget(QLabel("<b>Bottom Name:</b>"))
        vbox_names.addWidget(self.lbl_name_bottom)
        w_names = QWidget(); w_names.setLayout(vbox_names)
        
        self.grid.addWidget(w_names, 0, 0)

        # -- Column 1: Sizes --
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
        
        self.grid.addWidget(w_sizes, 0, 1)

        # -- Column 2: Dimensions --
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
        
        self.grid.addWidget(w_res, 0, 2)
        
        # -- Column 3: Delete Buttons --
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
        
        self.grid.addWidget(w_del, 0, 3)

        # -- Row 1: Paths --
        self.lbl_folder_top = QLabel()
        self.lbl_folder_top.setStyleSheet("color: #aaa;")
        self.lbl_folder_top.setWordWrap(True)
        
        self.lbl_folder_bottom = QLabel()
        self.lbl_folder_bottom.setStyleSheet("color: #aaa;")
        self.lbl_folder_bottom.setWordWrap(True)
        
        vbox_paths = QVBoxLayout()
        vbox_paths.addWidget(QLabel("<b>Top Path:</b>"))
        vbox_paths.addWidget(self.lbl_folder_top)
        vbox_paths.addSpacing(5)
        vbox_paths.addWidget(QLabel("<b>Bottom Path:</b>"))
        vbox_paths.addWidget(self.lbl_folder_bottom)
        w_paths = QWidget(); w_paths.setLayout(vbox_paths)
        
        self.grid.addWidget(w_paths, 1, 0, 1, 4) # Span full width

        ctrl_layout.addLayout(self.grid)
        ctrl_layout.addSpacing(20)
        
        # 3. Ignore Actions
        ign_layout = QHBoxLayout()
        self.btn_ign_not = QPushButton("Not Duplicate")
        self.btn_ign_sim = QPushButton("Similar")
        self.btn_ign_set = QPushButton("Same Set")
        
        self.btn_ign_not.clicked.connect(lambda: self.action_ignore.emit('not_duplicate'))
        self.btn_ign_sim.clicked.connect(lambda: self.action_ignore.emit('similar'))
        self.btn_ign_set.clicked.connect(lambda: self.action_ignore.emit('same_set'))
        
        ign_layout.addWidget(self.btn_ign_not)
        ign_layout.addWidget(self.btn_ign_sim)
        ign_layout.addWidget(self.btn_ign_set)
        ctrl_layout.addLayout(ign_layout)
        
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

class ResultsWidget(QWidget):
    def __init__(self, db_manager):
        super().__init__()
        self.db = db_manager
        self.deduper = Deduper(db_manager)
        
        self.layout = QVBoxLayout(self)
        
        self.splitter = QSplitter(Qt.Horizontal)
        self.layout.addWidget(self.splitter)
        
        self.group_list = QListWidget()
        self.group_list.currentRowChanged.connect(self.on_group_selected)
        self.splitter.addWidget(self.group_list)
        
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

    def load_results(self, threshold=5, include_ignored=False, root_paths=None):
        self.include_ignored = include_ignored # Store state
        self.groups = self.deduper.find_duplicates(threshold, include_ignored, root_paths)
        self.group_list.clear()
        
        for i, group in enumerate(self.groups):
            self.group_list.addItem(f"Group {i+1}: {len(group)} images")
            
        if self.groups:
            self.group_list.setCurrentRow(0)
        else:
            QMessageBox.information(self, "Scan Complete", "No duplicates found.")

    def on_group_selected(self, row):
        if row < 0 or row >= len(self.groups): return
        self.current_group_idx = row
        group = self.groups[row]
        if len(group) >= 2:
            self.right_index = 1
            self.update_comparison()

    def update_comparison(self):
        if self.current_group_idx == -1: return
        group = self.groups[self.current_group_idx]
        if self.right_index >= len(group):
            self.right_index = len(group) - 1
        
        left = group[0]
        right = group[self.right_index]
        
        self.comparison.load_pair(left, right)
        
        if self.comparison.btn_diff.isChecked():
            self.show_diff_image(left, right)
            
        reason = self.db.get_ignore_reason(left['phash'], right['phash'])
        if reason:
            self.comparison.lbl_status.setText(f"Marked as: {reason}")
            self.comparison.lbl_status.setStyleSheet("color: #eebb00; font-weight: bold; margin-bottom: 10px; font-size: 14px;")
        else:
            self.comparison.lbl_status.setText("Status: New Match")
            self.comparison.lbl_status.setStyleSheet("color: #44ee44; font-weight: bold; margin-bottom: 10px; font-size: 14px;")

        self.comparison.btn_next.setEnabled(self.right_index < len(group) - 1)
        self.comparison.btn_prev.setEnabled(self.right_index > 1)
        self.comparison.lbl_counter.setText(f"Comparing 1 & {self.right_index + 1} of {len(group)}")

    def next_image(self):
        if self.current_group_idx == -1: return
        self.right_index += 1
        self.update_comparison()

    def prev_image(self):
        if self.current_group_idx == -1: return
        self.right_index -= 1
        self.update_comparison()

    def resolve(self, action, reason=None):
        if self.current_group_idx == -1: return
        group = self.groups[self.current_group_idx]
        if len(group) < 2: return
        
        left = group[0]
        right = group[self.right_index]
        
        try:
            if action == 'delete_left':
                os.remove(left['path'])
                self.db.mark_deleted(left['path'])
                group.pop(0)
            elif action == 'delete_right':
                os.remove(right['path'])
                self.db.mark_deleted(right['path'])
                group.pop(self.right_index)
                if self.right_index >= len(group): self.right_index = len(group) - 1
            elif action == 'ignore':
                self.db.add_ignored_pair(left['phash'], right['phash'], reason)
                if not getattr(self, 'include_ignored', False):
                    # Hide ignored mode -> Remove this specific right image from view
                    # effectively behaving like 'delete_right' but without file deletion
                    group.pop(self.right_index)
                    if self.right_index >= len(group): self.right_index = len(group) - 1
                else:
                    # Show ignored mode -> Just update status
                    self.update_comparison()
                    return 
            elif action == 'l_r': 
                shutil.copy2(right['path'], left['path'])
                self.db.upsert_file(left['path'], right['phash'], right['file_size'],right['width'], right['height'], os.path.getmtime(left['path']))
                group.pop(0)
            elif action == 'r_l': 
                shutil.copy2(left['path'], right['path'])
                self.db.upsert_file(right['path'], left['phash'], left['file_size'], left['width'], left['height'], os.path.getmtime(right['path']))
                group.pop(self.right_index)
                if self.right_index >= len(group): self.right_index = len(group) - 1
        except Exception as e:
            QMessageBox.critical(self, "Error", str(e))
            return

        if len(group) < 2:
            self.groups.pop(self.current_group_idx)
            self.group_list.takeItem(self.current_group_idx)
            if self.current_group_idx >= len(self.groups): self.current_group_idx = len(self.groups) - 1
            self.group_list.setCurrentRow(self.current_group_idx)
        else:
            self.update_comparison()
            self.group_list.item(self.current_group_idx).setText(f"Group {self.current_group_idx+1}: {len(group)} images")

    def smart_resolve(self, criteria):
        if self.current_group_idx == -1: return
        group = self.groups[self.current_group_idx]
        left = group[0]
        right = group[self.right_index]
        action = None
        if criteria == 'size':
            if left['file_size'] < right['file_size']: action = 'delete_left'
            elif right['file_size'] < left['file_size']: action = 'delete_right'
        elif criteria == 'res':
            if (left['width']*left['height']) < (right['width']*right['height']): action = 'delete_left'
            elif (right['width']*right['height']) < (left['width']*left['height']): action = 'delete_right'
        if action: self.resolve(action)
        else: QMessageBox.information(self, "Info", "Files are equal in this criteria.")

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
        found = False
        if self.current_group_idx != -1:
            group = self.groups[self.current_group_idx]
            for i, f in enumerate(group):
                if f['path'] == old_path:
                    new_f = dict(f)
                    new_f['path'] = new_path
                    group[i] = new_f
                    found = True
                    break
        if found: self.update_comparison()
