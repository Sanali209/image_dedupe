# Current Project State

**Date:** 2025-12-17
**Status:** Beta / Active Development

## Overview
The project is a functional desktop application for image deduplication. It has transitioned from a basic script to a structured GUI application with advanced features like fuzzy matching caching, and smart resolution.

## Architecture

### Core Components
*   **Scanner (`core/scanner.py`)**: Traverses directories efficiently, handles file hashing (pHash) using multiprocessing (via `ScanWorker`), and updates the database.
*   **Deduper (`core/deduper.py`)**: 
    *   Loads hashes from SQLite.
    *   Performs **Exact Match** grouping (O(1)).
    *   Performs **Fuzzy Matching** using a **BK-Tree** (`core/bktree.py`) for efficient Hamming distance queries. This replaced the previous O(N^2) approach.
    *   Supports filtering results by "scanned roots" to focus on active folders while utilizing the full historical database.
*   **Database (`core/database.py`)**: 
    *   SQLite schema with `files` (path, phash, metadata), `scanned_paths`, and `ignored_pairs`.
    *   `ignored_pairs` table now supports a `reason` column ("not_duplicate", "near_duplicate", "similar", "same_set").
*   **UI (`ui/`)**:
    *   `MainWindow`: Main application shell with StackedLayout navigation and Menu Bar.
    *   `ScanSetupWidget`: Folder selection and threshold configuration.
    *   `ProgressWidget`: Task progress and real-time Loguru log viewer.
    *   `ResultsWidget`: The complex Master-Detail view for reviewing groups. Features include:
        *   Multi-image navigation.
        *   "Show Difference" toggle (PIL ImageChops).
        *   Context Menus (Show in Explorer, Move to Folder).
        *   Smart Actions (Delete Smaller/Lower Res).

## Recent Changes
1.  **Performance**: 
    *   **Virtualized Results List**: Replaced `QListWidget` with `QListView` + `QAbstractListModel` to support 1M+ pairs with zero UI lag.
    *   Switched fuzzy matching to BK-Tree. 
    *   Added `root_paths` filtering to deduplication to improve speed when focusing on specific subfolders.
2.  **UI/UX**:
    *   **Selection Logic Fix**: Fixed issue where resolving the last item in the list caused the comparison view to stall.
    *   Added "Show Difference" visualization.
    *   Added "Mark as..." dropdown with categorization.
    *   Added "Move to Folder" with **smart renaming** (auto-increment suffix) to handle collisions.
    *   Added Status Label to indicate NEW vs MARKED pairs.
3.  **Config**: Added "Similarity Threshold" spinner.
4.  **Stability**:
    *   **Engine Initialization**: Fixed `TypeError` in `CLIPEngine` and `BLIPEngine` constructors.
    *   Fixed `IndexError` in navigation.
    *   Fixed `AttributeError` in UI initialization.
    *   Restored missing imports (`QPixmap`, `defaultdict`).

## Known Limitations / TODO
*   **Async UI**: While `processEvents` is used, very, very large scans might still stutter the UI slightly during the final aggregation phase.
*   **Zoom/Pan**: The `ComparisonWidget` currently scales images to fit. Full zoom/pan support is planned but not implemented.
*   **Thumbnails**: For groups > 2 images, there is no thumbnail strip; users must cycle through images blindly using "Next/Prev".

## Database Schema
```sql
CREATE TABLE files (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    path TEXT UNIQUE NOT NULL,
    phash TEXT,
    file_size INTEGER,
    width INTEGER,
    height INTEGER,
    last_modified REAL
);

CREATE TABLE ignored_pairs (
    hash1 TEXT NOT NULL,
    hash2 TEXT NOT NULL,
    reason TEXT, -- 'not_duplicate', 'near_duplicate', 'similar', 'same_set'
    UNIQUE(hash1, hash2)
);
```
