import os
import shutil
from .base import Command
from loguru import logger

class FileOperationCommand(Command):
    def __init__(self, file_repo, file_path):
        self.repo = file_repo
        self.file_path = file_path

# --- DELETE COMMAND ---
class DeleteFileCommand(FileOperationCommand):
    def __init__(self, file_repo, file_path):
        super().__init__(file_repo, file_path)
        self.backup_path = f"{file_path}.bak" 
        # Note: Simple backup strategy. For robust undo, might want a trash dir or move to tmp.
        # Moving to .bak in place might clutter.
        # Better: Move to a temp Trash folder managed by the app.
        self.trash_dir = os.path.join(os.path.dirname(file_path), ".trash_tmp")
        self.trash_path = os.path.join(self.trash_dir, os.path.basename(file_path))
        self.was_deleted = False

    def execute(self):
        try:
            if not os.path.exists(self.file_path):
                logger.warning(f"File not found for deletion: {self.file_path}")
                return

            os.makedirs(self.trash_dir, exist_ok=True)
            shutil.move(self.file_path, self.trash_path)
            self.repo.mark_deleted(self.file_path)
            self.was_deleted = True
            logger.info(f"Command: Deleted {self.file_path}")
        except Exception as e:
            logger.error(f"Failed to delete {self.file_path}: {e}")
            raise

    def undo(self):
        if not self.was_deleted: return
        try:
            if os.path.exists(self.trash_path):
                shutil.move(self.trash_path, self.file_path)
                # self.repo.mark_deleted(self.file_path, deleted=False) # INCORRECT: Repo performs hard delete.
                
                # So to Undo, we must re-insert.
                # We need metadata.
                stat = os.stat(self.file_path)
                # We might have lost hash/dims if we didn't save them.
                # Ideally, command should snapshot the file row data before delete.
                self.repo.upsert_file(self.file_path, None, stat.st_size, 0, 0, stat.st_mtime) 
                # Note: Width/Height lost if we don't open image.
                
                logger.info(f"Command: Restored {self.file_path}")
            
            # Clean up trash dir if empty
            if not os.listdir(self.trash_dir):
                os.rmdir(self.trash_dir)
                
        except Exception as e:
            logger.error(f"Failed to undo delete {self.file_path}: {e}")
            raise

# --- IGNORE COMMAND ---
class IgnorePairCommand(Command):
    def __init__(self, file_repo, id1, id2, reason):
        self.repo = file_repo
        self.id1 = id1
        self.id2 = id2
        self.reason = reason
        self.was_ignored = False

    def execute(self):
        self.repo.add_ignored_pair(self.id1, self.id2, self.reason)
        self.was_ignored = True

    def undo(self):
        if self.was_ignored:
            self.repo.remove_ignored_pair(self.id1, self.id2)

class ReplaceFileCommand(FileOperationCommand):
    def __init__(self, file_repo, target_path, source_path_for_content):
        super().__init__(file_repo, target_path)
        self.source_content_path = source_path_for_content
        self.backup_path = None
        self.trash_dir = os.path.join(os.path.dirname(target_path), ".trash_tmp")

    def execute(self):
        # We want to make 'target_path' have content of 'source_content_path'
        # Backup Target
        os.makedirs(self.trash_dir, exist_ok=True)
        backup_filename = os.path.basename(self.file_path) + ".bak"
        self.backup_path = os.path.join(self.trash_dir, backup_filename)
        
        # Create backup
        if os.path.exists(self.file_path):
            shutil.copy2(self.file_path, self.backup_path)
        
        # Perform Copy
        shutil.copy2(self.source_content_path, self.file_path)
        
        # Update DB
        stat = os.stat(self.file_path)
        self.repo.upsert_file(self.file_path, None, stat.st_size, 0, 0, stat.st_mtime)

    def undo(self):
        if self.backup_path and os.path.exists(self.backup_path):
            shutil.copy2(self.backup_path, self.file_path)
            # Restore DB
            stat = os.stat(self.file_path)
            self.repo.upsert_file(self.file_path, None, stat.st_size, 0, 0, stat.st_mtime)
            
            # Clean up
            os.remove(self.backup_path)
            if os.path.exists(self.trash_dir) and not os.listdir(self.trash_dir):
                os.rmdir(self.trash_dir)
