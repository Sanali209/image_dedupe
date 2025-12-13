# Tachyon Image Deduper

A powerful, high-performance desktop application for finding and managing duplicate images. Built with Python, PySide6, and BK-Tree algorithms for efficient fuzzy matching.

## Features

### Core Functionality
*   **Intelligent Deduplication**: Uses Perceptual Hashing (pHash) and Hamming Distance to find similar images, not just exact byte-matches.
*   **High Performance**: Implements a BK-Tree (Burkhard-Keller Tree) data structure for O(log n) fuzzy matching speeds, capable of handling tens of thousands of images.
*   **Persistent Database**: SQLite backend stores image hashes, allowing for fast incremental scans without re-hashing unchanged files.
*   **Scalable**: Supports scanning multiple directory roots simultaneously.

### Advanced User Interface
*   **Grouped Results**: Displays duplicate groups of any size, not just pairs.
*   **Side-by-Side Comparison**: Visually compare images with zoom/pan support (planned) and metadata display.
*   **Visual Difference Mode**: Toggle a high-contrast "Show Difference" heatmap to instantly spot pixel-level discrepancies between similar images.
*   **Context Menus**: Right-click on images to "Show in Explorer" or "Move to Folder".

### Resolution Actions
*   **Flexible Deletion**: Delete Left, Delete Right, or use Smart Actions ("Delete Smaller File", "Delete Lower Res").
*   **Replacement**: Replace one file with the content of another ("Replace Left < Right" and vice versa).
*   **Smart Mark as Not Duplicate**:
    *   **Not Duplicate**: Mark pairs as false positives (ignored in future scans).
    *   **Near Duplicate**: Keep both but acknowledge similarity.
    *   **Similar / Same Set**: Categorize relations for organization.
    *   *Choices are saved in the database to prevent re-flagging.*
*   **File Management**: "Move to Folder" with automatic naming collision resolution (e.g., auto-renaming `image.jpg` to `image_1.jpg` if the target exists).

### Configuration
*   **Adjustable Threshold**: Fine-tune the strictness of the matching algo (Hamming Distance).
*   **Logging**: Real-time log view within the application for tracking background processes.

## Installation

1.  **Clone the Repository**:
    ```bash
    git clone https://github.com/yourusername/tachyon-gemini.git
    cd tachyon-gemini
    ```

2.  **Create a Virtual Environment** (Recommended):
    ```bash
    python -m venv .venv
    source .venv/bin/activate  # On Windows: .venv\Scripts\activate
    ```

3.  **Install Dependencies**:
    ```bash
    pip install -r requirements.txt
    ```

## Usage

1.  **Run the Application**:
    ```bash
    python main.py
    ```

2.  **Scan Folders**:
    *   Add folders to the list in the "Setup" tab.
    *   Adjust the "Similarity Threshold" (default is 5). Lower means stricter matching, higher means looser.
    *   Click "Start Scan".

3.  **Review Duplicates**:
    *   Navigate through duplicate groups in the "Results" tab.
    *   Use the "Next Image" / "Prev Image" buttons to cycle through matches in large groups.
    *   Use the buttons or shortcuts to Resolve the duplicates.
    *   Right-click images for file operations.

## Technologies Used
*   **GUI**: PySide6 (Qt)
*   **Algorithms**: ImageHash (pHash), BK-Tree (Custom Implementation)
*   **Database**: SQLite
*   **Image Processing**: Pillow (PIL), NumPy
*   **Logging**: Loguru

## License
MIT
