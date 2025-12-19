
from PySide6.QtWidgets import QApplication, QListWidget, QListWidgetItem
from PySide6.QtCore import Qt
import sys

def run_test():
    app = QApplication(sys.argv)
    list_widget = QListWidget()
    
    # Add 3 items
    for i in range(3):
        list_widget.addItem(f"Item {i}")
        
    list_widget.show()
    
    current_idx_tracker = [-1]
    
    def on_row_changed(row):
        print(f"Signal: Current Row Changed to {row}")
        current_idx_tracker[0] = row
        
    list_widget.currentRowChanged.connect(on_row_changed)
    
    # Select last item
    print("Selecting index 2")
    list_widget.setCurrentRow(2) 
    QApplication.processEvents()
    print(f"Tracker is: {current_idx_tracker[0]}")
    
    # Simulate logic in resolve()
    print("\n--- Simulating Removal of Last Item ---")
    idx = 2
    
    print("Blocking signals")
    list_widget.blockSignals(True)
    print("Taking item 2")
    list_widget.takeItem(idx)
    list_widget.blockSignals(False)
    
    # Logic from ResultsWidget
    # idx (2) is not < len (2)
    new_len = 2 # 0, 1
    
    print(f"Setting current row to {new_len - 1} (1)")
    list_widget.setCurrentRow(new_len - 1)
    QApplication.processEvents()
    
    print(f"Tracker is: {current_idx_tracker[0]}")
    
    if current_idx_tracker[0] == 2:
        print("FAIL: Tracker stuck at 2 (Out of bounds)")
    elif current_idx_tracker[0] == 1:
        print("SUCCESS: Tracker updated to 1")
    else:
        print(f"Unknown state: {current_idx_tracker[0]}")

    QTimer.singleShot(100, app.quit)
    # app.exec() # We don't want to hang, just run logic. 
    # Actually for Qt signals to fire we need event loop or processEvents
    
if __name__ == "__main__":
    from PySide6.QtCore import QTimer
    run_test()
