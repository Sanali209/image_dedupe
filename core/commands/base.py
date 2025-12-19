from abc import ABC, abstractmethod
from collections import deque

class Command(ABC):
    @abstractmethod
    def execute(self):
        """Execute the command."""
        pass

    @abstractmethod
    def undo(self):
        """Undo the command."""
        pass

class CommandHistory:
    def __init__(self, max_len=50):
        self.undo_stack = deque(maxlen=max_len)
        self.redo_stack = deque(maxlen=max_len)

    def execute(self, command: Command):
        try:
            command.execute()
            self.undo_stack.append(command)
            self.redo_stack.clear() # Clear redo on new action
            return True
        except Exception as e:
            print(f"Command Execution Failed: {e}")
            return False

    def undo(self):
        if not self.undo_stack:
            return False
        
        command = self.undo_stack.pop()
        try:
            command.undo()
            self.redo_stack.append(command)
            return True
        except Exception as e:
            print(f"Undo Failed: {e}")
            # Put it back? Or discard?
            # Usually discard if undo failed to avoid broken state loop
            return False

    def redo(self):
        if not self.redo_stack:
            return False
            
        command = self.redo_stack.pop()
        try:
            command.execute()
            self.undo_stack.append(command)
            return True
        except Exception as e:
            print(f"Redo Failed: {e}")
            return False
