# Tachyon Image Deduper

A powerful, high-performance desktop application for finding and managing duplicate images. Now featuring **AI-Powered Matching** and **Sticky Clusters** for long-term organization.

## Key Features

### 🧠 Intelligent Matching Engines
*   **Perceptual Hash (pHash)**: Finds resized, rotated, or slightly modified images using Hamming Distance and BK-Tree acceleration.
*   **AI (MobileNetV3)**: Semantic duplicate detection. Finds images that "look" the same even if pixels differ significantly (e.g. slight crop, different format, compression artifacts).
*   **CLIP (Beta)**: Advanced semantic understanding.
*   **BLIP (Experimental)**: High-fidelity semantic matching using Salesforce's BLIP visual encoder. Excellent for conceptual duplicates, though more resource-intensive.

### 📦 Sticky Clusters (New!)
Organize your image library into persistent groups called "Clusters".
*   **Persistence**: Once you rename, edit, or move files into a cluster, it is **saved forever** in the database.
*   **Auto-Expansion**: Future scans will automatically detect new matches and add them to your existing sticky clusters.
*   **Drag & Drop**: Easily add images to clusters by dragging them from your file explorer.
*   **Advanced Management**:
    *   **Rename**: Give meaningful names to your clusters.
    *   **Set Target**: Define a target folder for each cluster to auto-move files.
    *   **Context Menus**: Right-click to Delete clusters, Remove images, or Open folders.

### 🔍 Precision Filtering
Control exactly how matches are found:
*   **Exact Hash**: Match only mathematically identical images.
*   **AI Matches**: Toggle AI-based loose matching on/off.
*   **Flexible Criteria**: Combine multiple criteria (Similar Crop, Same Style, etc.) to refine your results.

### 💻 Advanced User Interface
*   **Grouped Results**: Displays duplicate groups of any size.
*   **Visual Difference Mode**: Toggle a high-contrast heatmap to spot pixel-level discrepancies.
*   **Main Menu Actions**: Global commands like "Clear All Clusters" and "New Scan" are easily accessible.
*   **Dark Mode**: Sleek, modern interface built with PySide6.

## Installation

1.  **Clone the Repository**:
    ```bash
    git clone https://github.com/yourusername/tachyon-gemini.git
    cd tachyon-gemini
    ```

2.  **Create a Virtual Environment**:
    ```bash
    python -m venv .venv
    # Windows
    .venv\Scripts\activate
    # Linux/Mac
    source .venv/bin/activate
    ```

3.  **Install Dependencies**:
    ```bash
    pip install -r requirements.txt
    ```
    *Note: This project uses PyTorch and Transformers for AI features, which may require a significant download.*

## Usage

1.  **Run the Application**:
    ```bash
    python main.py
    ```

2.  **Start a Scan**:
    *   Add folders in the "Setup" tab.
    *   Select your engine (pHash or MobileNet).
    *   Click "Start Scan".

3.  **Organize Clusters**:
    *   Switch to the **Cluster Organizer** tab.
    *   **Detect**: Click "Detect Clusters" to group related images.
    *   **Refine**: Uncheck boxes like "AI Matches" if you want stricter groups.
    *   **Save**: Rename a cluster or interact with it to make it "Sticky". It will persist across restarts.
    *   **Move**: Use right-click actions to move files to their cluster's target folder.

## Technologies Used
*   **GUI**: PySide6 (Qt)
*   **AI/ML**: PyTorch, MobileNetV3, CLIP (Transformers)
*   **Database**: SQLite (optimized for graph relationships)
*   **Storage**: ChromaDB (optional vector store)
*   **Image Processing**: Pillow (PIL), NumPy

## Technical Specifications

### Embedding Models
| Engine | Model Source | Vector Size | Best For |
| :--- | :--- | :--- | :--- |
| **MobileNet** | `mobilenet_v3_small` (torchvision) | 576 dim | **Speed**. Fast scans, finding near-exact duplicates (crops, watermarks). |
| **CLIP** | `clip-ViT-B-32` (sentence-transformers) | 512 dim | **Standard**. Good balance of strictness and semantic understanding. |
| **BLIP** | `blip-image-captioning-base` (transformers) | 768 dim | **Semantic Depth**. Finds conceptual matches (e.g. same object from different angles). Slower but high fidelity. |

## License
MIT
