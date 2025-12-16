import sys
import os

sys.path.append(os.getcwd())

try:
    from PySide6.QtWidgets import QApplication
    from core.database import DatabaseManager
    from core.scan_session import ScanSession
    from ui.mainwindow import MainWindow

    # 1. Setup
    app = QApplication(sys.argv)
    db = DatabaseManager(":memory:")
    
    # 2. Test Session Logic
    session = ScanSession(db)
    session.roots = ["C:/test/path"]
    session.engine = 'clip'
    session.threshold = 0.2
    
    print("Session state set.")
    
    assert session.roots == ["C:/test/path"]
    assert session.engine == 'clip'
    assert session.threshold == 0.2
    print("Session assertion passed.")
    
    # 3. Test UI Instantiation (mocking db in session)
    # We need a fresh session with the main window's DB context usually, 
    # but here we just check if MainWindow inits without error.
    
    window = MainWindow() # Will create its own persistent DB connection usually
    # To test our ephemeral DB, we'd need dependency injection in MainWindow, 
    # but MainWindow creates its own DBManager. That's fine for integration test.
    
    print("MainWindow instantiated successfully.")
    
    # Check if session propogated
    assert isinstance(window.setup_widget.session, ScanSession)
    assert isinstance(window.results_widget.session, ScanSession)
    print("Session propagation verified.")
    
    # Clean up
    window.close()
    print("Verification SCRIPT PASSED.")

except Exception as e:
    print(f"Verification Failed: {e}")
    sys.exit(1)
