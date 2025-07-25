import fitz # PyMuPDF
import json
import os
import re
from collections import Counter

INPUT_DIR = '/app/input'
OUTPUT_DIR = '/app/output'

def merge_spans_on_same_line(all_spans_data):
    if not all_spans_data:
        return []
    
    merged_lines = []
    current_line = all_spans_data[0].copy()
    
    for i in range(1, len(all_spans_data)):
        next_span = all_spans_data[i]
        
        if next_span['page'] == current_line['page'] and abs(next_span['y0'] - current_line['y0']) < 2:
            current_line['text'] += " " + next_span['text']
        else:
            merged_lines.append(current_line)
            current_line = next_span.copy()
    
    merged_lines.append(current_line)
    return merged_lines

def analyze_document_styles(spans):
    style_counts = Counter((s['font_size'], s['is_bold']) for s in spans)
    
    if not style_counts:
        return {'size': 10.0, 'bold': False}, {}
    
    body_style_tuple = style_counts.most_common(1)[0][0]
    body_style = {'size': body_style_tuple[0], 'bold': body_style_tuple[1]}
    
    heading_candidates = [
        s for s in style_counts
        if s != body_style_tuple and (s[0] > body_style['size'] or s[1])
    ]
    
    heading_styles_sorted = sorted(heading_candidates, key=lambda x: (x[0], x[1]), reverse=True)
    
    heading_level_map = {}
    levels = ['H1', 'H2', 'H3']  # Changed: Only H1, H2, H3
    for i, style in enumerate(heading_styles_sorted[:3]):  # Changed: Only take first 3 styles
        heading_level_map[levels[i]] = style
    
    return body_style, heading_level_map

def identify_headings_and_title(all_spans_data, body_style, heading_level_map):
    title = ""
    headings = []
    
    # Only process spans not marked as in_table
    spans_not_in_table = [s for s in all_spans_data if not s.get("in_table")]
    merged_lines = merge_spans_on_same_line(spans_not_in_table)
    
    if not merged_lines:
        return "", []
    
    # --- Smarter Dynamic Title Detection (First Page, Large Font)
    first_page_lines = [line for line in merged_lines if line['page'] == 1]
    title_lines = []
    title_font_threshold = body_style['size'] * 1.3
    
    for line in first_page_lines:
        if line['font_size'] >= title_font_threshold and len(line['text'].strip()) > 3:
            title_lines.append(line)
        elif title_lines:
            break  # Stop at first non-title-style line after we've begun
    
    if not title_lines and first_page_lines:
        title = max(first_page_lines, key=lambda l: l['font_size'])['text']
    else:
        # Join title lines in top-to-bottom order
        title_lines_sorted = sorted(title_lines, key=lambda l: l['y0'])
        title = " ".join(l['text'].strip() for l in title_lines_sorted)
    
    normalized_title = title.lower().strip()
    
    # --- Heading Extraction Logic ---
    for line in merged_lines:
        text = line['text'].strip()
        if not text or len(text) < 3:
            continue
        
        # Skip TOC dots, versioning, or title duplication
        if re.search(r'\.{5,}', text):
            continue
        if line['page'] <= 3 and re.match(r'^\d+\.\d+\s+\d{1,2} \w+ \d{4}', text):
            continue
        if text.lower() in normalized_title:
            continue
        
        cleaned_text = re.sub(r'\s+\d+$', '', text).strip()
        word_count = len(cleaned_text.split())
        
        # Build style key for matching levels
        line_style = (line['font_size'], line['is_bold'])
        matched_level = None
        for level, style in heading_level_map.items():
            if line_style == style:
                matched_level = level
                break
        
        # Detect numbered headings (e.g., 1.2 Header, 3.1.4 Something)
        is_numbered_heading = bool(re.match(r'^\d+(\.\d+)*[.:]?\s+', text)) and word_count <= 12
        
        # Heuristic: Skip headers that are too long (> 15 words), likely paragraphs
        if matched_level and word_count > 15:
            continue
        
        # Add to heading list - only H1, H2, H3 allowed
        if matched_level and matched_level in ['H1', 'H2', 'H3']:  # Changed: Explicit check
            headings.append({"level": matched_level, "text": cleaned_text, "page": line["page"]})
        elif is_numbered_heading:
            headings.append({"level": "H1", "text": cleaned_text, "page": line["page"]})
    
    # --- Deduplicate Headings ---
    seen = set()
    final_outline = []
    for h in headings:
        key = (h['text'].lower(), h['page'])
        if key not in seen:
            seen.add(key)
            final_outline.append(h)
    
    return title.strip(), final_outline

def filter_outline_headings(outline):
    """
    Filters out headings that are empty or contain only numbers, dots, or commas.
    """
    def is_valid(text):
        if not text or not text.strip():
            return False
        stripped = text.strip()
        if re.fullmatch(r'\d+([.,]?\d+)*[.,]?', stripped):
            return False
        if len(stripped) < 3:
            return False
        return True
    
    return [item for item in outline if is_valid(item["text"])]

def extract_all_span_data(pdf_path):
    """Extract spans and tag those in table-like structures."""
    doc = fitz.open(pdf_path)
    all_spans_data = []
    
    for page_num in range(doc.page_count):
        page = doc.load_page(page_num)
        text_blocks = page.get_text("dict")["blocks"]
        
        for block in text_blocks:
            if block["type"] != 0:
                continue
            
            x_positions = set()
            y_gaps = []
            prev_y = None
            
            for line in block["lines"]:
                for span in line["spans"]:
                    x_positions.add(round(span["bbox"][0], 1))
                if prev_y is not None:
                    gap = abs(line["bbox"][1] - prev_y)
                    y_gaps.append(gap)
                prev_y = line["bbox"][1]
            
            num_cols = len(x_positions)
            avg_y_gap = sum(y_gaps) / len(y_gaps) if y_gaps else 100
            is_table_like = num_cols >= 4 and avg_y_gap < 10
            
            for line in block["lines"]:
                for span in line["spans"]:
                    text = span["text"].strip()
                    if not text:
                        continue
                    
                    font_size = round(span["size"], 2)
                    font_name = span["font"].lower()
                    is_bold = "bold" in font_name or "black" in font_name or "demi" in font_name
                    
                    all_spans_data.append({
                        "text": text,
                        "page": page_num + 1,
                        "font_size": font_size,
                        "is_bold": is_bold,
                        "x0": round(span["bbox"][0], 2),
                        "y0": round(span["bbox"][1], 2),
                        "in_table": is_table_like
                    })
    
    doc.close()
    all_spans_data.sort(key=lambda s: (s['page'], s['y0'], s['x0']))
    return all_spans_data

def main():
    for filename in os.listdir(INPUT_DIR):
        if filename.endswith(".pdf"):
            pdf_path = os.path.join(INPUT_DIR, filename)
            output_filename = filename.replace(".pdf", ".json")
            output_path = os.path.join(OUTPUT_DIR, output_filename)
            
            print(f"Processing {filename}...")
            
            try:
                all_spans_data = extract_all_span_data(pdf_path)
                
                if not all_spans_data:
                    print(f"No text found in {filename}. Skipping.")
                    continue
                
                # 🔍 Heuristic: if most lines are short and evenly spaced (form/table style)
                avg_words = sum(len(s['text'].split()) for s in all_spans_data) / len(all_spans_data)
                unique_x = len(set(round(s['x0']) for s in all_spans_data))
                is_form_like = avg_words < 5 and unique_x > 10
                
                body_style, heading_level_map = analyze_document_styles(all_spans_data)
                
                title, outline = identify_headings_and_title(
                    all_spans_data,
                    body_style,
                    heading_level_map if not is_form_like else {}
                )
                
                if is_form_like:
                    print("Detected form-like layout. Skipping all headings except title.")
                    outline = []
                
                # ✅ Clean headings
                filtered_outline = filter_outline_headings(outline)
                
                output_data = {"title": title, "outline": filtered_outline}
                
                with open(output_path, 'w', encoding='utf-8') as f:
                    json.dump(output_data, f, indent=4, ensure_ascii=False)
                
                print(f"✅ Generated {output_filename}")
                
            except Exception as e:
                print(f"❌ Error processing {filename}: {e}")
        else:
            print(f"Skipping non-PDF file: {filename}")

if __name__ == "__main__":
    main()
