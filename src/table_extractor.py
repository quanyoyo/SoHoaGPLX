"""Extract GPLX lists from OCR and the geometry of each PDF page."""
from dataclasses import dataclass, replace
import re
from statistics import median
import unicodedata

import cv2
import numpy as np

from src.naming_rules import LICENSE_NUMBER
from src.sequence_analyzer import split_prefix_and_num
from src.vietnamese_utils import clean_vietnamese_name, normalize_vietnamese_address, normalize_nationality


def _key(text):
    folded = unicodedata.normalize("NFD", text.lower().replace("đ", "d"))
    return re.sub(r"[^a-z0-9]", "", folded)


_HEADINGS = {
    "stt": ("stt", "sott", "s6tt", "s0tt", "tt", "sothutu"),
    "full_name": ("hovaten", "hoten", "hotenthisinh", "hotencongdan"),
    "birth_year": ("namsinh", "ngaysinh", "ngaythangnamsinh", "tuoi"),
    "address": ("noicutru", "diachi", "noidangkyhokhau", "noithuongtru", "hokhau", "noicutruthuongtru"),
    "license_number": ("sobang", "sogplx", "s6gplx", "sogiayphep", "magplx", "gplx", "sogplxdaduoccap",
                       "sobanglaixe", "magiayphep", "masobang", "sogiaypheplaixe"),
    "nationality": ("quoctich", "qu0ctich"),
    "photo": ("anh", "anh3x4", "anh4x6", "anhchandung"),
    "signature": ("kynhan", "chuky"),
    "issue_date": ("ngaycap", "ngaycapgplx"),
    "license_class": ("hang", "hanggplx", "hangbang"),
    "register_index": (
        "sottbangke", "s6ttbangke", "sttbangke", "sobangke", "sotthoso", "masohoso", "mahoso",
        "ttbke", "ttbangke", "bke", "ttbk", "sottbk", "sottbke", "sttbke", "bangke",
    ),
    "identity": ("cccd", "cmnd", "socccd", "socmnd", "dinhdanhcanhan", "sodinhdanhcanhan", "socancuoc"),
    "expiry_date": ("ngayhethan", "ngayhethieuluc", "ngayhieuluc"),
    "return_date": ("ngaytra",),
}
_ROLES = {alias: role for role, aliases in _HEADINGS.items() for alias in aliases}
# OCR occasionally joins adjacent column headings into a single quadrilateral.
_MERGED = (
    ("namsinh", "quoctich", "Năm sinh", "Quốc tịch"),
    ("sobang", "kynhan", "Số bằng", "Ký nhận"),
    ("sogplx", "ngaycap", "Số GPLX", "Ngày cấp"),
)
_LICENSE_CONFIDENCE = 0.70
# Only lists with a name column and a birth column are read ("Họ và tên"/"Họ tên" and
# "Năm sinh"/"Ngày sinh"/"Ngày tháng năm sinh"); other tables in the PDF are skipped.
_BIRTH_HEADINGS = {"namsinh", "ngaysinh", "ngaythangnamsinh"}


def is_citizen_list(columns):
    return any(c["role"] == "full_name" for c in columns) and any(
        c["role"] == "birth_year" and _key(c["label"]) in _BIRTH_HEADINGS for c in columns
    )


def source_column_role(label):
    return _ROLES.get(_key(str(label or "")), "other")


@dataclass(frozen=True)
class Box:
    text: str
    score: float
    x0: float
    y0: float
    x1: float
    y1: float

    @property
    def x(self):
        return (self.x0 + self.x1) / 2

    @property
    def y(self):
        return (self.y0 + self.y1) / 2


@dataclass
class PageGrid:
    # Positions and extents are normalized to the rendered page size.
    ink: np.ndarray
    vertical: list
    horizontal: list

    def is_blank(self, bounds):
        x0, y0, x1, y1 = bounds
        height, width = self.ink.shape
        mx = max(2, int((x1 - x0) * width * 0.035))
        my = max(2, int((y1 - y0) * height * 0.10))
        crop = self.ink[max(0, int(y0 * height) + my):min(height, int(y1 * height) - my),
                        max(0, int(x0 * width) + mx):min(width, int(x1 * width) - mx)]
        if crop.shape[0] < 5 or crop.shape[1] < 8:
            return False
        _, _, stats, _ = cv2.connectedComponentsWithStats(crop, connectivity=8)
        # Ignore scan specks and thin pieces of a printed horizontal rule.
        min_area = max(4, round(min(height, width) / 250))
        thin = max(2, round(height * .004))
        marks = [(x, y, w, h) for x, y, w, h, a in stats[1:] if a >= min_area]
        for x, y, w, h in marks:
            if w <= thin and (x == 0 or x + w == crop.shape[1]):
                continue
            if h <= thin:
                same_rule = [(a, b) for a, cy, b, ch in marks if ch <= thin and abs(cy - y) <= thin]
                if w >= crop.shape[1] * .55 or (
                    len(same_rule) >= 3 and max(a + b for a, b in same_rule) - min(a for a, _ in same_rule) >= crop.shape[1] * .45
                ):
                    continue
            return False
        return True


def measure_page_grid(image):
    gray = np.asarray(image.convert("L"))
    height, width = gray.shape
    binary = cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_MEAN_C, cv2.THRESH_BINARY_INV, 31, 12)

    def lines(vertical):
        gap = max(7, (height if vertical else width) // 65)
        closed = cv2.morphologyEx(binary, cv2.MORPH_CLOSE, np.ones((gap, 1) if vertical else (1, gap), np.uint8))
        kernel = (1, max(16, height // 22)) if vertical else (max(25, width // 17), 1)
        mask = cv2.morphologyEx(closed, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_RECT, kernel))
        contours = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)[0]
        segments = []
        for contour in contours:
            x, y, w, h = cv2.boundingRect(contour)
            if vertical and h > height * .10 and w < max(14, width * .02):
                segments.append(((x + w / 2) / width, y / height, (y + h) / height))
            if not vertical and w > width * .20 and h < max(14, height * .025):
                segments.append(((y + h / 2) / height, x / width, (x + w) / width))
        return sorted(segments)

    return PageGrid(binary, lines(True), lines(False))


def _boxes(result, size):
    width, height = size
    return [
        Box(str(text).strip(), float(score), min(xs) / width, min(ys) / height, max(xs) / width, max(ys) / height)
        for points, text, score in result if str(text).strip()
        for xs, ys in [tuple(zip(*points))]
    ]


def _split_merged(box):
    key = _key(box.text)
    if key in _ROLES:
        return [box]
    for first, second, label1, label2 in _MERGED:
        # The cell border between the headings is often read as "|", "I", "l" or "1".
        if re.fullmatch(rf"[il1]*{first}[il1]{{0,2}}{second}[il1]*", key):
            split = box.x0 + (box.x1 - box.x0) * len(first) / len(first + second)
            return [replace(box, text=label1, x1=split), replace(box, text=label2, x0=split)]
    return [box]


def _license(text):
    # NFKC turns full-width OCR punctuation ("：AH515423") into ASCII before stripping it.
    code = re.sub(r"\s+", "", unicodedata.normalize("NFKC", text).upper()).strip(".,:;")
    return code if LICENSE_NUMBER.fullmatch(code) else ""


def _joined_rules(horizontal, gap=.05):
    """Join collinear pieces of one printed rule that a scan defect broke apart."""
    joined = []
    for y, x0, x1 in sorted(horizontal, key=lambda line: (line[0], line[1])):
        for i, (jy, jx0, jx1) in enumerate(joined):
            if abs(jy - y) < .003 and x0 - jx1 < gap and jx0 - x1 < gap:
                joined[i] = (jy, min(jx0, x0), max(jx1, x1))
                break
        else:
            joined.append((y, x0, x1))
    return joined


def _header_columns(boxes, anchor, grid, left, right):
    height = anchor.y1 - anchor.y0
    # A rule may fade out right under the heading on a scan; a long rule ending near it still counts.
    spanning = [y for y, x0, x1 in _joined_rules(grid.horizontal)
                if x0 - .12 <= anchor.x <= x1 + .12 and x1 - x0 >= min(.32, (right - left) * .65)]
    below = [y for y in spanning if anchor.y1 - height * .10 <= y <= anchor.y1 + height * 1.75]
    above = [y for y in spanning if anchor.y0 - height * 1.75 <= y <= anchor.y0 + height * .10]
    top = max(above, default=anchor.y0 - height * 1.30)
    bottom = min(below, default=anchor.y1 + height * .95)
    candidates = [
        part for box in boxes if left <= box.x < right and top <= box.y < bottom
        and re.search(r"[A-Za-zÀ-ỹ]", box.text) and not _license(box.text) and not _key(box.text).startswith("trang")
        for part in _split_merged(box)
    ]
    rules = [(x, end - start) for x, start, end in grid.vertical
             if left <= x <= right and start < bottom + .035 and end > bottom + .065]
    dividers = [x for x, _ in rules]
    length = dict(rules)
    groups = []
    for box in sorted(candidates, key=lambda item: item.x):
        if groups:
            previous = groups[-1]
            closest = min(previous, key=lambda p: abs(p.x - box.x))
            different_line = abs(closest.y - box.y) > height * .30
            overlap = min(closest.x1, box.x1) - max(closest.x0, box.x0)
            separated = any(min(closest.x, box.x) + .003 < x < max(closest.x, box.x) - .003 for x in dividers)
            if different_line and overlap > 0 and not separated:
                previous.append(box)
                continue
        groups.append([box])

    labels, spans = [], []
    for group in groups:
        label = " ".join(b.text for b in sorted(group, key=lambda b: (b.y, b.x)))
        labels.append(label)
        spans.append((min(b.x0 for b in group), max(b.x1 for b in group)))
    roles = [_ROLES.get(_key(label), "other") for label in labels]
    positive = set(roles)
    if "full_name" not in positive or not (
        "license_number" in positive
        or ("birth_year" in positive and bool(positive & {"address", "stt", "issue_date", "register_index"}))
        or {"stt", "address"} <= positive
    ):
        return None
    # Use the printed rule between headers where visible. OCR box gaps fill in damaged rules.
    edges = [max((x for x in dividers if x < spans[0][0] + .005), default=left)]
    for (_, end), (start, _) in zip(spans, spans[1:]):
        midpoint = (end + start) / 2
        # Text aligned down a column can look like a short rule; the printed rule runs the table's height.
        edges.append(min((x for x in dividers if end - .005 <= x <= start + .005),
                         key=lambda x: (-round(length[x], 2), abs(x - midpoint)), default=midpoint))
    edges.append(min((x for x in dividers if x > spans[-1][1] - .005), default=right))
    if any(a >= b for a, b in zip(edges, edges[1:])):
        return None
    columns = [
        {"label": label, "role": role, "left": x0, "right": x1}
        for label, role, x0, x1 in zip(labels, roles, edges, edges[1:])
    ]
    return bottom, columns


def _name_anchors(boxes):
    """Boxes reading "Họ và tên"/"Họ tên", including a heading wrapped over two lines
    ("Họ" above "và tên"), which OCR returns as two boxes."""
    anchors = [box for box in boxes if _ROLES.get(_key(box.text)) == "full_name"]
    for top in boxes:
        if _key(top.text) not in ("ho", "hova"):
            continue
        height = top.y1 - top.y0
        for below in boxes:
            if (below is not top and -height * .3 <= below.y0 - top.y1 <= height * .8
                    and min(top.x1, below.x1) - max(top.x0, below.x0) > 0
                    and _ROLES.get(_key(top.text + below.text)) == "full_name"):
                anchors.append(Box(f"{top.text} {below.text}", min(top.score, below.score),
                                   min(top.x0, below.x0), top.y0, max(top.x1, below.x1), below.y1))
    return anchors


def _name(text):
    return len(re.findall(r"[A-Za-zÀ-ỹ]+", text)) >= 2 and _key(text) not in _ROLES


def _other_section(text):
    return _key(text).startswith(("danhsachdusathach", "danhsachkhongtrungtuyen", "danhsachthisinhkhongtrungtuyen",
                                  "thanhtien", "phisathach", "thongketonghop"))


def _read_rows(boxes, columns, start, end, grid, page_number):
    def in_column(box, column):
        return column["left"] <= box.x < column["right"]

    roles = [c["role"] for c in columns]
    name_index = roles.index("full_name")
    stt_index = roles.index("stt") if "stt" in roles else None
    register_index = roles.index("register_index") if "register_index" in roles else None
    license_index = roles.index("license_number") if roles.count("license_number") == 1 else None
    boxes = [b for b in boxes if start <= b.y < end and columns[0]["left"] <= b.x < columns[-1]["right"]]
    def list_continues_below(marker):
        # OCR drops accents, so a wrapped name ending in "Công" reads like a "Cộng" total.
        return any(b.y > marker.y1 and (_license(b.text) or (
            stt_index is not None and in_column(b, columns[stt_index]) and re.fullmatch(r"[0-9]{1,4}[.)]?", b.text)))
            for b in boxes)

    totals = [b.y0 for b in boxes if _other_section(b.text) or (
        _key(b.text) in {"tongcong", "cong", "congdon", "tongso"} and not list_continues_below(b))]
    if totals:
        end = min(end, min(totals))
        boxes = [b for b in boxes if b.y < end]
    if not boxes:
        return []
    glyph = median(b.y1 - b.y0 for b in boxes)
    rules = [y for y, a, b in grid.horizontal if b - a >= (columns[-1]["right"] - columns[0]["left"]) * .42
             and a < columns[name_index]["right"]]
    def own_data(other):
        # Values that belong to one person; a wrapped address line has none of them.
        return _license(other.text) or any(
            in_column(other, c) and re.fullmatch(r"[0-9]{4}|[0-9]{1,2}/[0-9]{1,2}/[0-9]{2,4}", other.text)
            for c in columns if c["role"] in {"birth_year", "issue_date"})
    names = sorted((b for b in boxes if in_column(b, columns[name_index]) and _name(b.text)), key=lambda b: b.y)
    entries = []
    for b in names:
        aligned = [other for other in boxes if abs(other.y - b.y) <= glyph * .66
                   and not in_column(other, columns[name_index])]
        has_index = stt_index is not None and any(
            in_column(other, columns[stt_index]) and re.fullmatch(r"[0-9]{1,4}[.)]?", other.text)
            for other in aligned
        )
        has_data = any(
            _license(other.text) or any(in_column(other, c) and len(other.text) > 2
                                        for c in columns if c["role"] in {"birth_year", "address", "issue_date"})
            for other in aligned
        )
        if (has_index or has_data or (len(columns) == 2 and "license_number" in roles)) and (
            not entries or b.y - entries[-1][0].y > glyph * .67
        ):
            weak = license_index is not None and not has_index and not any(map(own_data, aligned))
            entries.append((b, b.score >= .62, weak))
    anchors = (
        (stt_index, lambda text: re.fullmatch(r"[0-9]{1,4}[.)]?", text), 0),
        (register_index, lambda text: re.fullmatch(r"[0-9]{4,12}", text), .70),
        (license_index, _license, _LICENSE_CONFIDENCE),
    )
    for index, is_anchor, confidence in anchors:
        if index is None:
            continue
        for box in boxes:
            if not in_column(box, columns[index]) or box.score < confidence or not is_anchor(box.text):
                continue
            if any(abs(entry.y - box.y) <= glyph for entry, _, _ in entries):
                continue
            if any(other is not box and abs(other.y - box.y) <= glyph and own_data(other) for other in boxes):
                entries.append((box, False, False))
    entries.sort(key=lambda item: item[0].y)
    # A name line with only address text and no rule above it is the previous person's wrapped line.
    entries = [entry for i, entry in enumerate(entries) if not (
        entry[2] and i and not any(entries[i - 1][0].y < y < entry[0].y for y in rules))]
    if not entries:
        return []
    centers = [b.y for b, _, _ in entries]
    gaps = [b - a for a, b in zip(centers, centers[1:])]
    typical = median(gaps) if gaps else glyph * 2
    def boundary(a, b):
        midpoint = (a + b) / 2
        return min((y for y in rules if a < y < b), key=lambda y: abs(y - midpoint), default=midpoint)

    top_edge = max((y for y in rules if start <= y < centers[0] and centers[0] - y <= typical), default=start)
    # A rule through the last text line (a scan streak) is not that row's bottom edge.
    last_line = max(b.y for b in boxes if abs(b.y - centers[-1]) <= glyph * .66)
    bottom_edge = min((y for y in rules if last_line < y <= end and y - centers[-1] <= typical),
                      default=min(end, centers[-1] + max(typical * .65, glyph)))
    row_edges = [top_edge, *(boundary(a, b) for a, b in zip(centers, centers[1:])), bottom_edge]
    rows = []
    for i, (_, confident, _) in enumerate(entries):
        y0, y1 = row_edges[i:i+2]
        cells, scores, bounds = [], [], []
        for column in columns:
            found = [b for b in boxes if y0 <= b.y < y1 and in_column(b, column)]
            found.sort(key=lambda b: (round(b.y / max(glyph * .5, .001)), b.x))
            cells.append(" ".join(b.text for b in found))
            scores.append(min((b.score for b in found if _key(b.text)), default=1.0))
            bounds.append((column["left"], y0, column["right"], y1))
        raw_stt = cells[stt_index] if stt_index is not None else ""
        stt = re.fullmatch(r"([0-9]{1,4})[.)]?", raw_stt)
        rows.append({"cells": cells, "scores": scores, "bounds": bounds, "page_number": page_number,
                     "stt": int(stt[1]) if stt else None, "identity_confident": confident})
    return rows


def split_camel_case(s: str) -> str:
    """Insert a space between lowercase and uppercase letters in joined words (e.g. HaVanHai -> Ha Van Hai)."""
    res = []
    for i, ch in enumerate(s):
        if i > 0 and ch.isupper() and s[i - 1].islower():
            res.append(" ")
        res.append(ch)
    return "".join(res)


# A register code is 4-10 digits. OCR may put a stray mark before it ("I 201061", "|201063")
# and "/" or ":" between it and the name ("201062/Vu Duc Cong").
_LEAD = r"[:;.\s\-/(|]*(?:[Il|]\s*)?"
_GAP = r"\s*[-:(/\s]*\s*"
_RE_STT = re.compile(r"^([0-9]{1,4})[.)]?$")
_RE_STT_AND_CODE = re.compile(r"^([0-9]{1,4})[.)\-]?\s+([0-9]{4,10})$")
_RE_CODE_AND_NAME = re.compile(rf"^{_LEAD}([0-9]{{4,10}}){_GAP}([A-Za-zÀ-ỹ].*)$")
# A cell holding "STT code Family" or "code Family": the first words of the name were read into it.
_RE_STT_CODE_AND_NAME = re.compile(rf"^(?:([0-9]{{1,4}})[.)\-]?\s+)?{_LEAD}([0-9]{{4,10}}){_GAP}([A-Za-zÀ-ỹ].*)$")


def _clean_name(name):
    name = split_camel_case(name)
    name = re.sub(r"^[:;.\s\-/(|]+", "", name)
    return re.sub(r"[:;.\s\-/)\]|]+$", "", name).strip()


def _join_name(head, rest):
    return _clean_name(f"{head} {rest}".strip())


def _keep_review(row, name, guessed):
    """The OCR doubt about a name survives the split.

    A name whose first words were found in another column, or a name of one word, is a guess
    of where the name starts: the row is shown for review (yellow) until someone checks it.
    """
    row["identity_confident"] = (
        bool(row.get("identity_confident", True)) and bool(name) and not guessed and len(name.split()) > 1
    )


def _recover_missing_columns(rows, columns):
    """Recover missing STT or register index columns when OCR drops column headers.

    Handles cases where:
    1. STT column header was missed by OCR, so Col 0 has STT numbers (69..80), and
       register numbers (201117..201128) are prepended to names in full_name or joined
       with STT in Col 0 (e.g. '76 201124', or '28 201076 Tran Quy' with the name's first words).
       Reconstructs separate STT and TT B.Kê columns.
    2. TT B.Kê column header was missed by OCR, so full_name has register numbers prepended.
    3. Both columns exist, but individual rows merged register numbers into full_name, or
       the first words of the name into TT B.Kê.
    """
    if not rows or not columns:
        return

    roles = [c.get("role") for c in columns]
    if "full_name" not in roles:
        return
    name_idx = roles.index("full_name")

    has_stt = "stt" in roles
    has_reg = "register_index" in roles

    if has_stt and has_reg:
        reg_idx = roles.index("register_index")
        for row in rows:
            cells = row.get("cells", [])
            if len(cells) <= max(reg_idx, name_idx):
                continue
            c_reg = cells[reg_idx].strip()
            c_name = cells[name_idx].strip()
            m_reg = _RE_CODE_AND_NAME.match(c_reg)
            if m_reg:
                cells[reg_idx] = m_reg.group(1)
                cells[name_idx] = _join_name(m_reg.group(2), c_name)
                _keep_review(row, cells[name_idx], guessed=True)
            elif not c_reg:
                m = _RE_CODE_AND_NAME.match(c_name)
                if m:
                    cells[reg_idx] = m.group(1)
                    cells[name_idx] = _clean_name(m.group(2))
                    _keep_review(row, cells[name_idx], guessed=False)
                elif _RE_STT_AND_CODE.match(cells[0].strip()):
                    m_both = _RE_STT_AND_CODE.match(cells[0].strip())
                    cells[0] = m_both.group(1)
                    row["stt"] = int(m_both.group(1))
                    cells[reg_idx] = m_both.group(2)
        return

    n = len(rows)
    stt_in_col0 = 0
    code_in_table = 0

    for row in rows:
        cells = row.get("cells", [])
        if not cells:
            continue
        c0 = cells[0].strip()
        c_name = cells[name_idx].strip() if len(cells) > name_idx else ""
        merged = bool(_RE_STT_CODE_AND_NAME.match(c0))
        if _RE_STT.match(c0) or _RE_STT_AND_CODE.match(c0) or merged:
            stt_in_col0 += 1
        if _RE_STT_AND_CODE.match(c0) or merged or _RE_CODE_AND_NAME.match(c_name):
            code_in_table += 1

    code_ratio = code_in_table / n
    stt_col0_ratio = stt_in_col0 / n

    if code_ratio < 0.30:
        return

    if not has_stt and stt_col0_ratio >= 0.50:
        col0 = columns[0]
        col0_left = col0["left"]
        col0_right = col0["right"]
        mid = col0_left + (col0_right - col0_left) * 0.40

        reg_label = col0.get("label") or "TT B.Kê"
        if _key(reg_label) in _HEADINGS.get("stt", ()):
            reg_label = "TT B.Kê"

        stt_col = {"label": "STT", "role": "stt", "left": col0_left, "right": mid}
        reg_col = {"label": reg_label, "role": "register_index", "left": mid, "right": col0_right}
        new_columns = [stt_col, reg_col] + list(columns[1:])

        for row in rows:
            cells = row.get("cells", [])
            c0 = cells[0].strip() if len(cells) > 0 else ""
            c_name = cells[name_idx].strip() if len(cells) > name_idx else ""

            stt_str = ""
            reg_str = ""
            name_str = c_name
            guessed = False

            m_both = _RE_STT_AND_CODE.match(c0)
            m_merged = None if m_both else _RE_STT_CODE_AND_NAME.match(c0)
            if m_both:
                stt_str = m_both.group(1)
                reg_str = m_both.group(2)
            elif m_merged:
                stt_str = m_merged.group(1) or ""
                reg_str = m_merged.group(2)
                name_str = f"{m_merged.group(3)} {c_name}"
                guessed = True
            else:
                m_stt = _RE_STT.match(c0)
                stt_str = m_stt.group(1) if m_stt else c0
                m_code_name = _RE_CODE_AND_NAME.match(c_name)
                if m_code_name:
                    reg_str = m_code_name.group(1)
                    name_str = m_code_name.group(2)

            name_str = _clean_name(name_str)

            row["stt"] = int(stt_str) if stt_str.isdigit() else None

            new_cells = [stt_str, reg_str] + list(cells[1:])
            new_cells[name_idx + 1] = name_str
            row["cells"] = new_cells

            if "scores" in row and row["scores"]:
                s0 = row["scores"][0]
                row["scores"] = [s0, s0] + list(row["scores"][1:])
            if "bounds" in row and row["bounds"]:
                b0 = row["bounds"][0]
                b_mid = (b0[0] + b0[2]) / 2
                row["bounds"] = [(b0[0], b0[1], b_mid, b0[3]), (b_mid, b0[1], b0[2], b0[3])] + list(row["bounds"][1:])
            _keep_review(row, name_str, guessed)

        columns[:] = new_columns
        return

    if has_stt and not has_reg and code_ratio >= 0.30:
        name_col = columns[name_idx]
        name_left = name_col["left"]
        name_right = name_col["right"]
        mid = name_left + (name_right - name_left) * 0.35

        reg_col = {"label": "TT B.Kê", "role": "register_index", "left": name_left, "right": mid}
        new_name_col = {**name_col, "left": mid}

        new_columns = list(columns[:name_idx]) + [reg_col, new_name_col] + list(columns[name_idx + 1:])

        for row in rows:
            cells = row.get("cells", [])
            c_name = cells[name_idx].strip() if len(cells) > name_idx else ""
            c0 = cells[0].strip() if len(cells) > 0 else ""

            reg_str = ""
            name_str = c_name
            guessed = False

            m_both = _RE_STT_AND_CODE.match(c0)
            m_merged = None if m_both else _RE_STT_CODE_AND_NAME.match(c0)
            if m_both:
                cells[0] = m_both.group(1)
                row["stt"] = int(m_both.group(1))
                reg_str = m_both.group(2)
            elif m_merged and m_merged.group(1):
                cells[0] = m_merged.group(1)
                row["stt"] = int(m_merged.group(1))
                reg_str = m_merged.group(2)
                name_str = f"{m_merged.group(3)} {c_name}"
                guessed = True
            else:
                m_code_name = _RE_CODE_AND_NAME.match(c_name)
                if m_code_name:
                    reg_str = m_code_name.group(1)
                    name_str = m_code_name.group(2)

            name_str = _clean_name(name_str)

            new_cells = list(cells[:name_idx]) + [reg_str, name_str] + list(cells[name_idx + 1:])
            row["cells"] = new_cells

            if "scores" in row and row["scores"]:
                s_name = row["scores"][name_idx] if len(row["scores"]) > name_idx else 1.0
                row["scores"] = list(row["scores"][:name_idx]) + [s_name, s_name] + list(row["scores"][name_idx + 1:])
            if "bounds" in row and row["bounds"]:
                b_name = row["bounds"][name_idx] if len(row["bounds"]) > name_idx else (0, 0, 0, 0)
                b_mid = (b_name[0] + b_name[2]) / 2
                row["bounds"] = (
                    list(row["bounds"][:name_idx])
                    + [(b_name[0], b_name[1], b_mid, b_name[3]), (b_mid, b_name[1], b_name[2], b_name[3])]
                    + list(row["bounds"][name_idx + 1:])
                )
            _keep_review(row, name_str, guessed)

        columns[:] = new_columns
        return


def _finish_rows(rows, columns, grid):
    _recover_missing_columns(rows, columns)
    roles = [c["role"] for c in columns]
    valid_columns = [i for i, role in enumerate(roles) if role == "license_number"]
    inferred = False
    if not valid_columns:
        for i, role in enumerate(roles):
            if role != "other":
                continue
            values = [row["cells"][i] for row in rows if row["cells"][i]]
            matches = sum(bool(_license(value)) for value in values)
            if matches >= 2 and matches / len(values) >= .67:
                valid_columns.append(i)
        inferred = len(valid_columns) == 1
    index = valid_columns[0] if len(valid_columns) == 1 else None
    if inferred:
        columns[index]["role"] = "license_number"
        columns[index]["inferred"] = True
    for row in rows:
        row["license_number"] = ""
        if index is None:
            row["license_state"] = "unknown_column"
            continue
        value = row["cells"][index]
        code = _license(value)
        if code and row["scores"][index] >= _LICENSE_CONFIDENCE:
            row["license_number"] = code
            row["license_state"] = "valid"
        elif not value and not columns[index].get("inferred") and grid.is_blank(row["bounds"][index]):
            row["license_state"] = "blank"
        else:
            row["license_state"] = "uncertain"
    return rows


def _compatible(previous, current):
    return len(previous) == len(current) and all(
        a["role"] == b["role"] and (_key(a["label"]) == _key(b["label"]) or a["role"] != "other")
        and abs(a["right"] - b["right"]) <= .08 and abs(a["left"] - b["left"]) <= .08
        for a, b in zip(previous, current)
    )


def _continues(table, rows, page_number, *, headerless=False):
    last = table["rows"][-1]
    distance = page_number - last["page_number"]
    if distance < 1 or (headerless and distance != 1):
        return False
    order = [row["stt"] for row in rows if row["stt"] is not None]
    if order and (order[0] == 1 or order != sorted(set(order))):
        return False
    if order and last["stt"] is not None and rows[0]["stt"] is not None:
        return order[0] > last["stt"] if distance == 1 else order[0] == last["stt"] + 1
    prefix, number, _ = split_prefix_and_num(last["license_number"])
    next_prefix, next_number, _ = split_prefix_and_num(rows[0]["license_number"])
    if prefix == next_prefix and number >= 0 and 0 < next_number - number <= (20 if distance == 1 else 1):
        return True
    # Without STT or a known endpoint, only an unlabeled, aligned run can continue.
    if headerless and len(rows) >= 2:
        roles = [c["role"] for c in table["columns"]]
        if not {"birth_year", "address"} <= set(roles):
            return False
        birth, address = roles.index("birth_year"), roles.index("address")
        return all(row["identity_confident"] and re.fullmatch(r"[0-9]{4}|[0-9]{1,2}/[0-9]{1,2}/[0-9]{4}", row["cells"][birth])
                   and _name(row["cells"][address]) for row in rows)
    return False


def _align_columns(columns, grid):
    """Transfer the previous layout when the printed dividers moved together on the scan."""
    edges = [columns[0]["left"], *(c["right"] for c in columns)]
    shifts = []
    for edge in edges:
        nearest = min((x for x, start, end in grid.vertical if end - start >= .20 and abs(x - edge) <= .03),
                      key=lambda x: abs(x - edge), default=None)
        if nearest is not None:
            shifts.append(nearest - edge)
    offset = median(shifts) if len(shifts) >= 3 and max(shifts) - min(shifts) < .02 else 0
    return [{**c, "left": max(0, c["left"] + offset), "right": min(1, c["right"] + offset)} for c in columns]


class LicenseTableExtractor:
    """Accumulate independent lists while keeping source columns, cells, and page numbers."""

    def __init__(self):
        self.tables = []
        self.previous_columns = None
        # True after a table without the required columns; its unlabeled follow-up pages are skipped.
        self.skipping = False

    def _read_repeated_header(self, boxes, columns, start, end, grid, page_number):
        """Read a page with the previous list's columns when its heading repeats that list.

        A repeated heading is often scanned worse than the first one, so its own column edges
        can be off. Returns (columns, rows) when those rows continue the list, otherwise None.
        """
        if not self.tables or not _same_layout(self.tables[-1]["columns"], columns):
            return None
        table = self.tables[-1]
        layout = [dict(c) for c in _align_columns(table["columns"], grid)]
        rows = _read_rows(boxes, layout, start, end, grid, page_number)
        if not rows:
            return None
        _finish_rows(rows, layout, grid)
        return (layout, rows) if _continues(table, rows, page_number) else None

    def read_page(self, ocr_result, size, grid, page_number):
        boxes = _boxes(ocr_result, size)
        anchors = sorted(_name_anchors(boxes), key=lambda b: (b.y, b.x))
        bands = []
        for anchor in anchors:
            if not bands or anchor.y - bands[-1][0].y > max(.012, (anchor.y1 - anchor.y0) * .6):
                bands.append([])
            bands[-1].append(anchor)
        headers = []
        for band in bands:
            band.sort(key=lambda b: b.x)
            left = 0.0
            for i, anchor in enumerate(band):
                right = 1.0
                if i + 1 < len(band):
                    next_anchor = band[i + 1]
                    split = [b.x0 for b in boxes if anchor.x < b.x < next_anchor.x
                             and abs(b.y - anchor.y) < .04 and _ROLES.get(_key(b.text)) == "stt"]
                    right = min(split, default=(anchor.x + next_anchor.x) / 2)
                parsed = _header_columns(boxes, anchor, grid, left, right)
                if parsed and not any(_other_section(b.text) and 0 < anchor.y - b.y < .10 for b in boxes):
                    headers.append((anchor.y, *parsed))
                left = right
        if headers:
            for i, (y, start, columns) in enumerate(headers):
                if not is_citizen_list(columns):
                    self.skipping = True
                    continue
                self.skipping = False
                end = next((h[0] for h in headers[i + 1:] if h[0] - y > .015), 1.0)
                rows = _read_rows(boxes, columns, start, end, grid, page_number)
                if not rows:
                    continue
                _finish_rows(rows, columns, grid)
                own = (self.tables and _continues(self.tables[-1], rows, page_number)
                       and _compatible(self.previous_columns, columns))
                repeated = self._read_repeated_header(boxes, columns, start, end, grid, page_number)
                if repeated and (not own or _quality(repeated[1]) > _quality(rows)):
                    columns, rows = repeated
                    self.tables[-1]["rows"].extend(rows)
                elif own:
                    self.tables[-1]["rows"].extend(rows)
                else:
                    self.tables.append({"columns": columns, "rows": rows})
                self.previous_columns = columns
        elif self.tables and not self.skipping:
            # An unlabeled page needs matching row geometry and ordinal continuity.
            columns = _align_columns(self.previous_columns, grid)
            rows = _read_rows(boxes, columns, 0.0, 1.0, grid, page_number)
            if rows:
                _finish_rows(rows, columns, grid)
                previous = self.tables[-1]
                if _continues(previous, rows, page_number, headerless=True):
                    previous["rows"].extend(rows)
                elif page_number == previous["rows"][-1]["page_number"] + 1:
                    # Retain a review marker when the next page resembles the list but cannot be joined safely.
                    previous.setdefault("unresolved_pages", []).append(page_number)


def _quality(rows):
    """Rows with a valid licence number and a confidently read person."""
    return sum((r["license_state"] == "valid") + bool(r["identity_confident"]) for r in rows)


def _same_layout(previous, current):
    """The repeated heading of one list, even when OCR missed or misread a minor heading."""
    if previous is None or abs(len(previous) - len(current)) > 2:
        return False
    for role in ("full_name", "birth_year", "license_number"):
        mine = [c for c in previous if c["role"] == role]
        theirs = [c for c in current if c["role"] == role]
        if len(mine) != 1 or len(theirs) != 1:
            return False
        # A column next to a missed heading absorbs that space, so compare by containment.
        (a,), (b,) = mine, theirs
        if not (a["left"] <= (b["left"] + b["right"]) / 2 <= a["right"]
                or b["left"] <= (a["left"] + a["right"]) / 2 <= b["right"]):
            return False
    return True


def apply_cell_edit(table, row, column_index, value):
    """Store a reviewed cell. The user's value is confirmed, so its OCR doubt is cleared."""
    role = table["columns"][column_index]["role"]
    row["cells"][column_index] = value
    if column_index < len(row.get("scores", [])):
        row["scores"][column_index] = 1.0
    row["_edited"] = True
    if role == "license_number" and [c["role"] for c in table["columns"]].count("license_number") == 1:
        code = _license(value)
        row["license_number"] = code
        row["license_state"] = "valid" if code else ("blank" if not value else "uncertain")
    elif role == "full_name":
        row["identity_confident"] = bool(value)
    elif role == "stt":
        match = re.fullmatch(r"([0-9]{1,4})[.)]?", value)
        row["stt"] = int(match[1]) if match else None


def project_citizen(values, *, stt, page_number, license_number):
    """Keep the lookup representation consistent for OCR and Excel imports."""
    return {
        "stt": stt,
        "page_number": page_number,
        "full_name": clean_vietnamese_name(values.get("full_name", "")),
        "birth_year": values.get("birth_year", ""),
        "address": normalize_vietnamese_address(values.get("address", "")),
        "nationality": normalize_nationality(values["nationality"]) if values.get("nationality") else "",
        "license_number": license_number,
    }


def table_citizens(table):
    """Project source rows onto the fields used by the current review and search."""
    roles = [c["role"] for c in table["columns"]]
    citizens = []
    for position, row in enumerate(table["rows"], start=1):
        values = dict(zip(roles, row["cells"]))
        citizen = project_citizen(
            values, stt=row["stt"] if row["stt"] is not None else position,
            page_number=row["page_number"], license_number=row["license_number"],
        )
        citizen["license_state"] = row["license_state"]
        citizens.append(citizen)
    return citizens
