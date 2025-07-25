# PDF Heading Detection Solution

## Approach
This solution uses PyMuPDF to extract text spans from PDFs and applies heuristic-based heading detection:

- **Font Analysis**: Identifies body text style and larger/bold fonts as potential headings
- **Table Detection**: Filters out table-like content to avoid false heading detection
- **Title Extraction**: Detects document title from first page using font size thresholds
- **Heading Hierarchy**: Maps font styles to heading levels (H1-H4)
- **Cleanup**: Removes duplicates, page numbers, and invalid headings

## Models/Libraries Used
- **PyMuPDF (fitz)**: PDF text extraction and font analysis
- **Python standard library**: JSON output, regex processing, file handling

## Build and Run
