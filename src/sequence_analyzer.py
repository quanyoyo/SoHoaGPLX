"""
Analyzer for driving license number sequences (Rà soát dãy số GPLX).
Determines ranges (e.g. A465975-A466040 or A161541; C244138-C244140)
and evaluates continuity ('Đủ' vs 'Ngắt, không theo thứ tự').
"""
import re
from typing import List, Dict, Any, Tuple

def split_prefix_and_num(license_code: str) -> Tuple[str, int, int]:
    """
    Splits e.g. 'A465975' into ('A', 465975, 6) where 6 is digit padding length.
    Returns ('', -1, 0) if invalid.
    """
    if not license_code:
        return ("", -1, 0)
        
    cleaned = license_code.strip().replace(" ", "").upper()
    match = re.match(r"^([A-Z]{1,2})([0-9]+)$", cleaned)
    if match:
        prefix = match.group(1)
        num_str = match.group(2)
        return (prefix, int(num_str), len(num_str))
    return (cleaned, -1, 0)

def analyze_license_sequences(license_list: List[str]) -> Dict[str, Any]:
    """
    Analyzes a list of license numbers extracted from the PDF.
    Returns:
    - sequence_summary: str (e.g. 'A465975-A466040' or 'A161541; C244138-C244140')
    - status: 'Đủ' or 'Ngắt, không theo thứ tự'
    - total_count: int
    - ranges: List[Tuple[str, str]]
    """
    valid_licenses = [code.strip() for code in license_list if code and code.strip() != "UNKNOWN"]
    total_count = len(valid_licenses)
    
    if total_count == 0:
        return {
            "sequence_summary": "",
            "status": "Không có dữ liệu",
            "total_count": 0,
            "ranges": []
        }
        
    ranges = []
    current_start = valid_licenses[0]
    current_prev = valid_licenses[0]
    
    start_prefix, start_num, start_len = split_prefix_and_num(current_start)
    prev_prefix, prev_num, prev_len = start_prefix, start_num, start_len
    
    is_fully_continuous = True
    
    for i in range(1, total_count):
        curr_code = valid_licenses[i]
        curr_prefix, curr_num, curr_len = split_prefix_and_num(curr_code)
        
        # Check if consecutive: same prefix, same length, and curr_num == prev_num + 1
        if curr_prefix == prev_prefix and curr_num != -1 and curr_num == prev_num + 1:
            current_prev = curr_code
            prev_num = curr_num
        else:
            # Range broke
            is_fully_continuous = False
            if current_start == current_prev:
                ranges.append(current_start)
            else:
                ranges.append(f"{current_start}-{current_prev}")
                
            current_start = curr_code
            current_prev = curr_code
            prev_prefix, prev_num, prev_len = curr_prefix, curr_num, curr_len
            
    # Add final range
    if current_start == current_prev:
        ranges.append(current_start)
    else:
        ranges.append(f"{current_start}-{current_prev}")
        
    sequence_summary = "; ".join(ranges)
    
    # Evaluate status
    # One unbroken range, including a list of a single licence.
    if len(ranges) == 1 and is_fully_continuous:
        status = "Đủ"
    else:
        status = "Ngắt, không theo thứ tự"
        
    return {
        "sequence_summary": sequence_summary,
        "status": status,
        "total_count": total_count,
        "ranges": ranges
    }
