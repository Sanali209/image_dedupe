import pytest
from core.commands.base import Command, CommandHistory

class MockCommand(Command):
    """Mock command for testing."""
    def __init__(self, should_fail=False):
        self.executed = False
        self.undone = False
        self.should_fail = should_fail
        
    def execute(self):
        if self.should_fail:
            raise Exception("Mock execution failure")
        self.executed = True
        self.undone = False
        
    def undo(self):
        if self.should_fail:
            raise Exception("Mock undo failure")
        self.undone = True
        self.executed = False

class TestCommandHistory:
    def test_execute_adds_to_undo_stack(self):
        """Test that executing a command adds it to undo stack."""
        history = CommandHistory()
        cmd = MockCommand()
        
        result = history.execute(cmd)
        
        assert result is True
        assert cmd.executed is True
        assert len(history.undo_stack) == 1
        
    def test_execute_clears_redo_stack(self):
        """Test that new execute clears redo stack."""
        history = CommandHistory()
        cmd1 = MockCommand()
        cmd2 = MockCommand()
        
        history.execute(cmd1)
        history.undo()
        assert len(history.redo_stack) == 1
        
        history.execute(cmd2)
        assert len(history.redo_stack) == 0
        
    def test_undo_moves_to_redo_stack(self):
        """Test that undo moves command to redo stack."""
        history = CommandHistory()
        cmd = MockCommand()
        
        history.execute(cmd)
        result = history.undo()
        
        assert result is True
        assert cmd.undone is True
        assert len(history.undo_stack) == 0
        assert len(history.redo_stack) == 1
        
    def test_undo_empty_stack_returns_false(self):
        """Test that undo on empty stack returns False."""
        history = CommandHistory()
        
        result = history.undo()
        
        assert result is False
        
    def test_redo_executes_command(self):
        """Test that redo re-executes command."""
        history = CommandHistory()
        cmd = MockCommand()
        
        history.execute(cmd)
        history.undo()
        result = history.redo()
        
        assert result is True
        assert cmd.executed is True
        assert len(history.undo_stack) == 1
        assert len(history.redo_stack) == 0
        
    def test_redo_empty_stack_returns_false(self):
        """Test that redo on empty stack returns False."""
        history = CommandHistory()
        
        result = history.redo()
        
        assert result is False
        
    def test_max_len_enforcement(self):
        """Test that undo stack respects max_len."""
        history = CommandHistory(max_len=3)
        
        for i in range(5):
            cmd = MockCommand()
            history.execute(cmd)
            
        assert len(history.undo_stack) == 3
        
    def test_execute_failure_handling(self):
        """Test that failed execute doesn't add to stack."""
        history = CommandHistory()
        cmd = MockCommand(should_fail=True)
        
        result = history.execute(cmd)
        
        assert result is False
        assert len(history.undo_stack) == 0
        
    def test_undo_failure_handling(self):
        """Test that failed undo is handled gracefully."""
        history = CommandHistory()
        cmd = MockCommand()
        cmd.should_fail = False
        history.execute(cmd)
        
        cmd.should_fail = True
        result = history.undo()
        
        assert result is False
        # Command should not be in either stack after failed undo
        
    def test_multiple_undo_redo_sequence(self):
        """Test multiple undo/redo operations."""
        history = CommandHistory()
        cmd1 = MockCommand()
        cmd2 = MockCommand()
        cmd3 = MockCommand()
        
        history.execute(cmd1)
        history.execute(cmd2)
        history.execute(cmd3)
        
        history.undo()  # Undo cmd3
        history.undo()  # Undo cmd2
        
        assert len(history.undo_stack) == 1
        assert len(history.redo_stack) == 2
        
        history.redo()  # Redo cmd2
        
        assert len(history.undo_stack) == 2
        assert len(history.redo_stack) == 1
