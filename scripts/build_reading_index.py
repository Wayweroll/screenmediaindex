#!/usr/bin/env python3
"""Build a course-planning index from Sight and Sound PDF contents pages."""

from __future__ import annotations

import csv
import hashlib
import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

from pypdf import PdfReader


ROOT = Path(__file__).resolve().parents[1]
OUTPUT_DIR = ROOT / "outputs"
CSV_PATH = OUTPUT_DIR / "reading_index.csv"
GUIDE_PATH = OUTPUT_DIR / "reading_guide.md"

MAGAZINE = "Sight and Sound"

SECTION_HEADINGS = {
    "features": "Features",
    "regulars": "Regulars",
    "rushes": "Rushes",
    "wide angle": "Wide Angle",
    "opening scenes": "Opening Scenes",
    "talkies": "Talkies",
    "reviews": "Reviews overview",
    "from the archive": "From the Archive",
    "endings": "Endings",
    "letters": "Letters",
    "editorial": "Editorial",
    "contributors": "Contributors",
    "in this issue": "In This Issue",
}

EXCLUDED_TITLES = {
    "contributors",
    "also in this issue",
    "in this issue",
    "contents",
    "regulars",
    "features",
    "reviews",
}

REVIEW_SECTION_RE = re.compile(
    r"^(?:films|dvd|dvd & blu-ray|blu-ray|books|wider screen|television)\b", re.I
)

AUTHOR_RE = re.compile(
    r"\b(?:By|by|talks to|interview(?:s|ed by)?|asks|hears from|recalls|on)\s+"
    r"([A-Z][A-Za-zÀ-ÖØ-öø-ÿ'’.-]+(?:\s+[A-Z][A-Za-zÀ-ÖØ-öø-ÿ'’.-]+){0,3})"
)

MONTHS = (
    "January",
    "February",
    "March",
    "April",
    "May",
    "June",
    "July",
    "August",
    "September",
    "October",
    "November",
    "December",
    "Summer",
    "Winter",
)

THEME_RULES = [
    ("animation", ["animation", "animated", "anime", "miyazaki", "ghibli", "akira"]),
    ("documentary", ["documentary", "doc ", "docu", "cph:dox", "nonfiction"]),
    ("film industry", ["industry", "streaming", "vod", "netflix", "cinemas", "box office", "hollywood", "production", "distrib"]),
    ("archives", ["archive", "restoration", "rediscovery", "silent era", "from the archive", "lost and found"]),
    ("star studies", ["star", "actor", "actress", "performance", "acting", "performer"]),
    ("adaptation", ["adaptation", "novel", "book", "bront", "literary", "shakespeare"]),
    ("race", ["race", "black", "panther", "colonial", "indigenous", "diaspora", "racism"]),
    ("gender", ["gender", "women", "woman", "femin", "trans", "queer", "lgbt", "sexuality"]),
    ("national cinema", ["iran", "japan", "korea", "china", "french", "italian", "british", "australian", "india", "african", "latin"]),
    ("cinephilia", ["cineph", "critics", "poll", "cinema history", "scala", "sight and sound", "moviegoing"]),
    ("television", ["television", "tv ", "series", "bbc"]),
    ("experimental film", ["experimental", "avant-garde", "video art", "artists' film"]),
    ("genre", ["horror", "western", "thriller", "noir", "musical", "science fiction", "sci-fi"]),
]

TYPE_RULES = [
    ("interview", ["talks to", "interview", "in conversation", "at the movies with"]),
    ("profile", ["profile", "career", "star", "auteur", "director"]),
    ("archive piece", ["from the archive", "archive"]),
    ("column", ["talkies", "opening scenes", "rushes", "wide angle", "endings", "editorial", "letters"]),
    ("festival report", ["festival", "cannes", "venice", "berlin", "locarno", "sundance", "cph:dox"]),
    ("industry analysis", ["industry", "streaming", "vod", "cinemas", "box office", "production"]),
    ("obituary/tribute", ["obituary", "tribute", "in memoriam"]),
]


@dataclass
class Entry:
    reading_id: str
    source_type: str
    source_title: str
    source_year: str
    source: str
    year: str
    magazine_title: str
    issue_date: str
    volume: str
    issue_number: str
    page_range: str
    publisher: str
    edition: str
    isbn: str
    book_title: str
    editor: str
    chapter_pages: str
    pdf_filename: str
    pdf_path: str
    file_location: str
    section: str
    title: str
    author: str
    printed_start_page: str
    pdf_page_number: str
    short_summary: str
    keywords: str
    specific_keywords: str
    people_films_discussed: str
    course_themes: str
    films_filmmakers_performers: str
    reading_type: str
    teaching_use: str
    notes: str
    confidence_note: str


@dataclass
class Issue:
    path: Path
    page_count: int
    issue_date: str
    volume: str
    issue_number: str
    text: str
    ocr_used: bool = False
    entries: list[Entry] = field(default_factory=list)
    review_context: str = ""


@dataclass
class Book:
    path: Path
    page_count: int
    title: str
    author: str
    year: str
    category: str
    publisher: str
    edition: str
    isbn: str
    text: str
    entries: list[Entry] = field(default_factory=list)


def clean_text(text: str) -> str:
    text = text.replace("\x00", " ")
    text = text.replace("Sight&Sound", "Sight and Sound")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def normalize_title(text: str) -> str:
    text = re.sub(r"\s+", " ", text).strip(" -–—·|")
    text = re.sub(r"^(?:·|•)\s*", "", text)
    return text


def sentence_case_title(text: str) -> str:
    title = normalize_title(text)
    words = title.split()
    if len(words) == 2 and words[0].lower() == words[1].lower():
        title = words[0]
    if len(title) > 4 and title.upper() == title:
        keep = {"TV", "BFI", "BBC", "VOD", "DVD", "XR", "AI", "UK", "US"}
        cased_words = []
        for word in title.split():
            clean = word.strip(".,:;!?()[]")
            cased_words.append(word if clean in keep else word.capitalize())
        title = " ".join(cased_words)
    return title


def infer_issue_from_filename(path: Path) -> str:
    stem = path.stem
    stem = re.sub(r"^\d{4}-\d{2}[a-z]?\s+", "", stem)
    stem = stem.replace("Sight and Sound - ", "")
    return stem


def extract_issue_metadata(path: Path, text: str) -> tuple[str, str, str]:
    issue_date = infer_issue_from_filename(path)

    volume = ""
    issue = ""
    match = re.search(r"\bvolume\s+(\d+)\s+issue\s+(\d+)\b", text, re.I)
    if match:
        volume, issue = match.groups()
    else:
        match = re.search(r"\bVOLUME\s+(\d+)\s+ISSUE\s+(\d+)\b", text)
        if match:
            volume, issue = match.groups()

    return issue_date, volume, issue


def extract_pages(path: Path, max_pages: int = 8) -> tuple[int, str, bool]:
    reader = PdfReader(str(path))
    chunks = []
    for idx, page in enumerate(reader.pages[: min(max_pages, len(reader.pages))], start=1):
        page_text = page.extract_text() or ""
        chunks.append(f"\n[[PDF_PAGE {idx}]]\n{page_text}")
    text = clean_text("\n".join(chunks))
    ocr_used = False
    if len(text) < 200:
        ocr_name = str(path.relative_to(ROOT)).replace("/", "__")
        ocr_name = re.sub(r"\.pdf$", ".txt", ocr_name, flags=re.I)
        ocr_path = OUTPUT_DIR / "ocr_text" / ocr_name
        if ocr_path.exists():
            text = clean_text(ocr_path.read_text(encoding="utf-8", errors="ignore"))
            ocr_used = True
    return len(reader.pages), text, ocr_used


def first_page_for_printed_page(printed_page: str) -> str:
    if not printed_page.isdigit():
        return ""
    return str(int(printed_page) + 1)


def year_from_issue_date(issue_date: str, fallback_filename: str) -> str:
    match = re.search(r"\b(19|20)\d{2}\b", issue_date)
    if match:
        return match.group(0)
    match = re.search(r"\b(19|20)\d{2}\b", fallback_filename)
    return match.group(0) if match else ""


def year_from_text(*values: str) -> str:
    joined = " ".join(value or "" for value in values)
    years = re.findall(r"\b(?:19|20)\d{2}\b", joined)
    return years[-1] if years else ""


def make_reading_id(issue: Issue, page: str, title: str) -> str:
    stem = issue.path.stem.lower()
    stem = re.sub(r"[^a-z0-9]+", "-", stem).strip("-")
    title_key = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")[:48]
    canonical_path = str(issue.path.relative_to(ROOT)).replace(
        "Sight & Sound Magazine/Indexed/", "Sight & Sound Magazine/"
    )
    digest_source = f"{canonical_path}|{page}|{title}"
    digest = hashlib.sha1(digest_source.encode("utf-8")).hexdigest()[:8]
    return f"sns-{stem}-p{page}-{title_key}-{digest}"


def make_book_reading_id(path: Path, page: str, title: str) -> str:
    stem = path.stem.lower()
    stem = re.sub(r"[^a-z0-9]+", "-", stem).strip("-")[:70]
    title_key = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")[:48]
    digest_source = f"{path.relative_to(ROOT)}|{page}|{title}"
    digest = hashlib.sha1(digest_source.encode("utf-8")).hexdigest()[:8]
    return f"book-{stem}-p{page or 'na'}-{title_key}-{digest}"


def get_themes(text: str) -> list[str]:
    hay = f" {text.lower()} "
    themes = [theme for theme, needles in THEME_RULES if any(n in hay for n in needles)]
    return sorted(set(themes)) or ["film history/criticism"]


def get_reading_type(section: str, text: str) -> str:
    hay = f"{section} {text}".lower()
    for reading_type, needles in TYPE_RULES:
        if any(n in hay for n in needles):
            return reading_type
    return "essay"


def get_teaching_use(themes: list[str], reading_type: str, summary: str) -> str:
    uses = []
    hay = summary.lower()
    if reading_type == "interview":
        uses.append("case study")
    if reading_type == "archive piece":
        uses.append("historical primary source")
    if "industry" in themes or "streaming" in hay:
        uses.append("industry context")
    if any(theme in themes for theme in ["race", "gender", "national cinema"]):
        uses.append("debate/discussion")
    if reading_type in {"essay", "column"}:
        uses.append("introductory")
    return "; ".join(dict.fromkeys(uses[:2])) or "case study"


def get_author(text: str) -> str:
    match = AUTHOR_RE.search(text)
    if match:
        author = match.group(1)
        author = re.sub(r"\b(?:about|with|and|on|the|his|her)$", "", author).strip()
        return author
    return ""


def keyword_candidates(text: str) -> list[str]:
    candidates = re.findall(
        r"\b(?:[A-Z][A-Za-zÀ-ÖØ-öø-ÿ'’.-]+|[A-Z]{2,})(?:\s+(?:[A-Z][A-Za-zÀ-ÖØ-öø-ÿ'’.-]+|[A-Z]{2,})){0,4}",
        text,
    )
    stop = {
        "Sight",
        "Sound",
        "The",
        "This",
        "From",
        "By",
        "In",
        "May",
        "June",
        "March",
        "April",
        "September",
        "October",
        "November",
        "December",
        "Summer",
        "Winter",
        "Features",
        "Regulars",
        "Reviews",
        "Opening Scenes",
        "Talkies",
    }
    clean = []
    for candidate in candidates:
        candidate = normalize_title(candidate)
        if len(candidate) < 3 or candidate in stop or candidate.isdigit():
            continue
        if not any(char.islower() for char in candidate) and len(candidate) <= 4:
            clean.append(candidate)
        elif candidate.split()[0] not in stop:
            clean.append(candidate)
    counts = Counter(clean)
    return [item for item, _ in counts.most_common(8)]


def summary_from_text(title: str, text: str) -> str:
    text = normalize_title(text)
    text = re.sub(r"\[\[PDF_PAGE \d+\]\]", " ", text, flags=re.I)
    text = re.sub(r"\b(?:FEATURES|REGULARS|REVIEWS|IN THIS ISSUE|CONTENTS)\b", "", text, flags=re.I)
    text = text.replace(title, "", 1).strip(" .:-")
    sentences = re.split(r"(?<=[.!?])\s+", text)
    usable = []
    for sentence in sentences:
        sentence = normalize_title(sentence)
        if 35 <= len(sentence) <= 280 and not REVIEW_SECTION_RE.search(sentence):
            usable.append(sentence)
        if len(usable) == 2:
            break
    if usable:
        return " ".join(usable)
    return f"Course-relevant {title} piece from this issue; verify details against the PDF contents page."


def classify_section(title: str, context: str, current_section: str) -> str:
    hay = f"{title} {context}".lower()
    for key, value in SECTION_HEADINGS.items():
        if key in hay:
            return value
    return current_section or "Features"


def good_title(title: str) -> bool:
    if not title:
        return False
    lower = title.lower()
    if lower in EXCLUDED_TITLES:
        return False
    if REVIEW_SECTION_RE.search(title):
        return False
    if len(title) < 4 or len(title) > 130:
        return False
    if sum(ch.isalpha() for ch in title) < 4:
        return False
    if re.search(
        r"\[\[|members enjoy|order from|all rights reserved|advert|amazon prime|"
        r"discover the bfi|powerhouse|on dvd and digital|for full details|"
        r"criterion collection|curzon home cinema|in cinemas|southampton row|"
        r"stephen st|annual subscription|photography by|illustration by|"
        r"www\.|newwavefilms|a film by|^may be$|^april$",
        lower,
    ):
        return False
    if len(re.findall(r"\b\d{1,3}\b", title)) > 2:
        return False
    return True


def parse_new_layout(issue: Issue) -> list[tuple[str, str, str, str]]:
    text = issue.text
    pattern = re.compile(r"(?m)^\s*(\d{1,3})\s*$")
    matches = list(pattern.finditer(text))
    rows = []
    for idx, match in enumerate(matches):
        page = match.group(1)
        if int(page) < 5 or int(page) > issue.page_count + 5:
            continue
        start = match.end()
        end = matches[idx + 1].start() if idx + 1 < len(matches) else min(len(text), start + 900)
        block = text[start:end].strip()
        lines = [normalize_title(line) for line in block.splitlines() if normalize_title(line)]
        if not lines:
            continue
        usable_lines = [
            line
            for line in lines[:5]
            if len(line) <= 150
            and not re.search(r"^(REVIEWS|ALSO IN THIS ISSUE|[A-Z]+ \d{4}|WINTER|SUMMER)$", line, re.I)
            and not line.startswith("[[")
        ]
        if not usable_lines:
            continue
        title = usable_lines[0]
        if (title[:1].islower() or len(title) > 55) and any(line.isupper() and good_title(line) for line in usable_lines[1:]):
            title = next(line for line in usable_lines[1:] if line.isupper() and good_title(line))
        if title.isupper() and len(usable_lines) > 1 and usable_lines[1].isupper() and len(title) < 40:
            title = f"{title} {usable_lines[1]}"
        title = sentence_case_title(title)
        if not good_title(title):
            continue
        section = classify_section(title, block, "Features")
        rows.append((page, section, title, block))
    return rows


def parse_old_layout(issue: Issue) -> list[tuple[str, str, str, str]]:
    rows = []
    lines = [normalize_title(line) for line in issue.text.splitlines() if normalize_title(line)]
    current_section = "Features"
    for idx, line in enumerate(lines):
        lower = line.lower()
        if lower in SECTION_HEADINGS:
            current_section = SECTION_HEADINGS[lower]
            continue
        match = re.match(r"^(\d{1,3})\s+(.+)$", line)
        if not match:
            continue
        page, rest = match.groups()
        if int(page) < 5 or int(page) > issue.page_count + 5:
            continue
        context_lines = [rest]
        lookahead = lines[idx + 1 : idx + 6]
        for next_line in lookahead:
            if re.match(r"^\d{1,3}\s+", next_line):
                break
            if next_line.lower() in SECTION_HEADINGS:
                break
            context_lines.append(next_line)
        block = " ".join(context_lines)
        title = rest
        if len(title) > 80:
            title = re.split(r"\s{2,}| With | The | About | – | - ", title)[0]
        caps = re.findall(r"\b[A-Z][A-Z0-9&:’' -]{2,50}\b", block)
        caps = [cap.strip() for cap in caps if good_title(cap.strip()) and cap.strip().lower() not in {"all rights reserved"}]
        if (title[:1].islower() or title.endswith("?")) and caps:
            title = caps[0]
        title = re.sub(r"\s+IMAGE.*$", "", title, flags=re.I)
        title = sentence_case_title(title)
        title = re.sub(r"\[\[PDF_PAGE \d+\]\].*", "", title, flags=re.I).strip()
        if not good_title(title):
            continue
        section = classify_section(title, block, current_section)
        rows.append((page, section, title, block))
    return rows


def parse_ocr_cover_features(issue: Issue) -> list[tuple[str, str, str, str]]:
    if "[[PDF_PAGE" not in issue.text:
        return []
    rows = []
    page3 = ""
    match = re.search(r"\[\[PDF_PAGE 3\]\](.*?)(?:\[\[PDF_PAGE 4\]\]|$)", issue.text, re.S | re.I)
    if match:
        page3 = match.group(1)
    lines = [normalize_title(line) for line in page3.splitlines() if normalize_title(line)]
    joined = " ".join(lines)
    feature_patterns = [
        (r"Robert Eggers.*?By Jonathan Romney", "The Northman"),
        (r"PAUL VERHOEVEN.*?formidable 50-year career", "Paul Verhoeven"),
        (r"MOTHERHOOD.*?cinema is finally catching up", "Motherhood and the Movies"),
        (r"DORIS DAY.*?Hollywood legend", "Doris Day at 100"),
        (r"The great Norwegian actor.*?stayed with her", "Liv Ullmann"),
        (r"Twenty years after.*?reinvent the industry", "The Digital Revolution"),
        (r"BLACK FILM BULLETIN.*?rising stars", "Black Film Bulletin"),
        (r"MIA HANSEN.*?cult of .male genius", "Mia Hansen-Love"),
        (r"JOACHIM.*?Andrei Tarkovsky", "Joachim Trier"),
        (r"TERENCE.*?Ben Walters", "Terence Davies"),
        (r"JOHN WATERS.*?Hannah McGill", "John Waters"),
    ]
    for pattern, title in feature_patterns:
        found = re.search(pattern, joined, re.I)
        if found:
            rows.append(("", "Features", title, found.group(0)))
    return rows


def parse_bulleted_departments(issue: Issue) -> list[tuple[str, str, str, str]]:
    rows = []
    department_page = ""
    department = ""
    for raw_line in issue.text.splitlines():
        line = normalize_title(raw_line)
        if not line:
            continue
        match = re.match(r"^(\d{1,3})\s*(?:\|\s*)?([A-Z][A-Z &-]+)$", line)
        if match:
            department_page, department = match.groups()
            department = sentence_case_title(department)
            continue
        if line.startswith(("·", "•")) or raw_line.strip().startswith(("·", "•")):
            title = sentence_case_title(line)
            title = re.sub(r"^(?:·|•)\s*", "", title)
            if department and good_title(title) and not REVIEW_SECTION_RE.search(department):
                rows.append((department_page, department, title, title))
    return rows


def dedupe(rows: Iterable[tuple[str, str, str, str]]) -> list[tuple[str, str, str, str]]:
    seen = set()
    out = []
    for page, section, title, block in rows:
        key = (page, re.sub(r"\W+", "", title.lower())[:60])
        if key in seen:
            continue
        seen.add(key)
        out.append((page, section, title, block))
    return out


def make_entry(issue: Issue, page: str, section: str, title: str, block: str) -> Entry:
    summary = summary_from_text(title, block)
    themes = get_themes(f"{section} {title} {summary} {block}")
    reading_type = get_reading_type(section, f"{title} {summary} {block}")
    keywords = keyword_candidates(f"{title} {summary} {block}")
    author = get_author(block)
    confidence = "High: extracted from contents page."
    if "verify details" in summary:
        confidence = "Medium: title/page extracted, summary inferred; verify against PDF."
    if not author:
        confidence += " Author not visible in contents extraction."
    if not page:
        confidence = "Medium: OCR recovered the feature from the contents spread, but the printed page number was not reliably captured."
    source_year = year_from_issue_date(issue.issue_date, issue.path.name)
    keyword_text = "; ".join(keywords)
    people_films = "; ".join(keywords[:5])
    return Entry(
        reading_id=make_reading_id(issue, page, title),
        source_type="Magazine article",
        source_title=MAGAZINE,
        source_year=source_year,
        source=MAGAZINE,
        year=source_year,
        magazine_title=MAGAZINE,
        issue_date=issue.issue_date,
        volume=issue.volume,
        issue_number=issue.issue_number,
        page_range=page,
        publisher="BFI",
        edition="",
        isbn="",
        book_title="",
        editor="",
        chapter_pages="",
        pdf_filename=issue.path.name,
        pdf_path=str(issue.path.relative_to(ROOT)),
        file_location=str(issue.path.relative_to(ROOT)),
        section=section,
        title=title,
        author=author,
        printed_start_page=page,
        pdf_page_number=first_page_for_printed_page(page),
        short_summary=summary,
        keywords=keyword_text,
        specific_keywords=keyword_text,
        people_films_discussed=people_films,
        course_themes="; ".join(themes),
        films_filmmakers_performers=people_films,
        reading_type=reading_type,
        teaching_use=get_teaching_use(themes, reading_type, summary),
        notes=confidence,
        confidence_note=confidence,
    )


def make_extraction_note(issue: Issue) -> Entry:
    source_year = year_from_issue_date(issue.issue_date, issue.path.name)
    confidence = "Low: article-level contents could not be reliably indexed from this PDF. Manual review recommended."
    return Entry(
        reading_id=make_reading_id(issue, "", f"OCR review needed: {issue.issue_date}"),
        source_type="Issue extraction note",
        source_title=MAGAZINE,
        source_year=source_year,
        source=MAGAZINE,
        year=source_year,
        magazine_title=MAGAZINE,
        issue_date=issue.issue_date,
        volume=issue.volume,
        issue_number=issue.issue_number,
        page_range="",
        publisher="BFI",
        edition="",
        isbn="",
        book_title="",
        editor="",
        chapter_pages="",
        pdf_filename=issue.path.name,
        pdf_path=str(issue.path.relative_to(ROOT)),
        file_location=str(issue.path.relative_to(ROOT)),
        section="Extraction note",
        title=f"OCR review needed: {issue.issue_date}",
        author="",
        printed_start_page="",
        pdf_page_number="",
        short_summary="This scanned PDF needs manual contents review before assigning readings; OCR did not recover enough reliable article-level metadata.",
        keywords="OCR; manual review; scanned PDF",
        specific_keywords="OCR; manual review; scanned PDF",
        people_films_discussed="",
        course_themes="metadata review",
        films_filmmakers_performers="",
        reading_type="extraction note",
        teaching_use="manual follow-up",
        notes=confidence,
        confidence_note=confidence,
    )


def extract_review_context(text: str) -> str:
    reviews = []
    capture = False
    for raw_line in text.splitlines():
        line = normalize_title(raw_line)
        if not line:
            continue
        if line.upper() == "REVIEWS" or re.match(r"^\d{1,3}\s*\|\s*FILMS", line, re.I):
            capture = True
            continue
        if capture and re.match(r"^(FROM THE ARCHIVE|ENDINGS|THIS MONTH|EDITORIAL)$", line, re.I):
            break
        if capture and (line.startswith(("·", "•")) or re.match(r"^[A-Z][A-Za-z].+", line)):
            cleaned = re.sub(r"^(?:·|•)\s*", "", line)
            if good_title(cleaned):
                reviews.append(cleaned)
        if len(reviews) >= 18:
            break
    return "; ".join(reviews[:18])


def build_issue(path: Path) -> Issue:
    page_count, text, ocr_used = extract_pages(path)
    issue_date, volume, issue_number = extract_issue_metadata(path, text)
    issue = Issue(path=path, page_count=page_count, issue_date=issue_date, volume=volume, issue_number=issue_number, text=text, ocr_used=ocr_used)
    rows = []
    if issue.ocr_used:
        rows.extend(parse_ocr_cover_features(issue))
    else:
        rows.extend(parse_new_layout(issue))
        rows.extend(parse_old_layout(issue))
        rows.extend(parse_bulleted_departments(issue))
    rows = dedupe(rows)
    issue.entries = [make_entry(issue, *row) for row in rows]
    if not issue.entries:
        issue.entries = [make_extraction_note(issue)]
    issue.review_context = extract_review_context(text)
    return issue


def clean_book_filename(path: Path) -> str:
    stem = path.stem
    stem = re.sub(r"\s*\((?:z-library|1lib|z-lib|b-ok|libgen).*?\)", "", stem, flags=re.I)
    stem = stem.replace("_", " ")
    stem = re.sub(r"\s+", " ", stem).strip()
    return stem


def split_book_title_author(path: Path, metadata_title: str = "", metadata_author: str = "") -> tuple[str, str]:
    stem = clean_book_filename(path)
    author = normalize_title(metadata_author or "")
    title = normalize_title(metadata_title or "")
    if title and len(title) > 140:
        title = ""
    if not title:
        title = stem
    patterns = [
        r"^(?P<title>.+?)\s+-\s+(?P<author>[A-Z][A-Za-zÀ-ÖØ-öø-ÿ .,'’&-]{4,})$",
        r"^(?P<title>.+?)\.\s+(?P<author>[A-Z][A-Za-zÀ-ÖØ-öø-ÿ .,'’&-]{4,})$",
        r"^(?P<title>.+?)\s+by\s+(?P<author>[A-Z][A-Za-zÀ-ÖØ-öø-ÿ .,'’&-]{4,})$",
    ]
    for pattern in patterns:
        match = re.match(pattern, stem, re.I)
        if match:
            title = normalize_title(match.group("title"))
            if not author:
                author = normalize_title(match.group("author"))
            break
    title = re.sub(r"\b(?:pdf|epub)\b$", "", title, flags=re.I).strip(" .-")
    author = re.sub(r"\s+", " ", author).strip(" .-")
    return sentence_case_title(title), author


def extract_book_text(path: Path, max_pages: int = 35) -> tuple[int, str, dict]:
    reader = PdfReader(str(path))
    metadata = dict(reader.metadata or {})
    chunks = []
    for idx, page in enumerate(reader.pages[: min(max_pages, len(reader.pages))], start=1):
        chunks.append(f"\n[[PDF_PAGE {idx}]]\n{page.extract_text() or ''}")
    return len(reader.pages), clean_text("\n".join(chunks)), metadata


def parse_book_metadata(path: Path, text: str, metadata: dict) -> tuple[str, str, str, str, str]:
    title, author = split_book_title_author(
        path,
        str(metadata.get("/Title") or ""),
        str(metadata.get("/Author") or ""),
    )
    publisher = ""
    edition = ""
    isbn = ""
    pub_match = re.search(r"\b(?:Routledge|Focal Press|University of [A-Z][A-Za-z ]+ Press|BFI|Palgrave|McFarland|Bloomsbury|Oxford University Press|Cambridge University Press|Wiley|Pearson|Sage|Wallflower)\b", text)
    if pub_match:
        publisher = pub_match.group(0)
    edition_match = re.search(r"\b(\d+(?:st|nd|rd|th)\s+ed(?:ition)?|[Ff]ifth edition|[Ss]eventh edition|[Uu]pdated expanded ed(?:ition)?)\b", text)
    if edition_match:
        edition = edition_match.group(1)
    isbn_match = re.search(r"\bISBN(?:-1[03])?:?\s*([0-9Xx][0-9Xx -]{8,20})", text)
    if isbn_match:
        isbn = re.sub(r"\s+", " ", isbn_match.group(1)).strip()
    return title, author, publisher, edition, isbn


def book_category(path: Path) -> str:
    try:
        rel = path.relative_to(ROOT)
    except ValueError:
        return "Books"
    parts = rel.parts
    if len(parts) >= 3 and parts[0] == "Books":
        return parts[2]
    return "Books"


def themes_for_book(category: str, text: str) -> list[str]:
    themes = set(get_themes(f"{category} {text}"))
    category_lower = category.lower()
    if "cinematography" in category_lower:
        themes.update(["cinematography", "visual style"])
    if "directing" in category_lower or "production" in category_lower:
        themes.update(["directing", "production practice", "film industry"])
    if "documentary" in category_lower:
        themes.add("documentary")
    if "editing" in category_lower:
        themes.add("editing")
    if "experimental" in category_lower or "media theory" in category_lower:
        themes.update(["experimental film", "media theory"])
    if "analysis" in category_lower:
        themes.update(["film analysis", "film theory"])
    if "history" in category_lower:
        themes.update(["film history/criticism", "film culture"])
    if "genre" in category_lower:
        themes.add("genre")
    if "world cinemas" in category_lower or "national" in category_lower:
        themes.add("national cinema")
    return sorted(themes)


def book_keywords(category: str, title: str, chapter: str, author: str) -> str:
    keywords = keyword_candidates(f"{category} {title} {chapter} {author}")
    for value in [category, title, author]:
        if value and value not in keywords:
            keywords.insert(0, value)
    return "; ".join(dict.fromkeys(keywords[:10]))


def book_summary(book_title: str, chapter_title: str, category: str, author: str) -> str:
    if chapter_title and chapter_title != book_title:
        return f"Chapter from {book_title} useful for teaching {category.lower()}; focuses on {chapter_title.lower()}."
    author_part = f" by {author}" if author else ""
    return f"Book-level entry for {book_title}{author_part}, useful for teaching {category.lower()}."


def parse_toc_entries(text: str) -> list[tuple[str, str]]:
    lines = [normalize_title(line) for line in text.splitlines() if normalize_title(line)]
    start = 0
    for idx, line in enumerate(lines[:120]):
        if re.search(r"\b(contents|table of contents)\b", line, re.I):
            start = idx + 1
            break
    window = lines[start : start + 260]
    entries = []
    pending = ""
    back_matter = re.compile(r"^(notes|bibliography|references|works cited|index|filmography|appendix|acknowledg|about the author|copyright)\b", re.I)
    for line in window:
        line = re.sub(r"\.{2,}", " ", line)
        line = re.sub(r"\s+", " ", line).strip()
        if not line or line.startswith("[["):
            continue
        candidate = f"{pending} {line}".strip() if pending else line
        match = re.match(r"^(?P<title>.+?)\s+(?P<page>\d{1,4}|[ivxlcdm]{1,8})$", candidate, re.I)
        if not match:
            if len(line) < 90 and not re.search(r"\d{1,4}$", line):
                pending = candidate[:160]
            continue
        title = normalize_title(match.group("title"))
        page = match.group("page")
        pending = ""
        title = re.sub(r"^(chapter|part)\s+\d+[:.\s-]*", "", title, flags=re.I)
        title = re.sub(r"^\d+\s+", "", title)
        if not good_title(title) or back_matter.search(title):
            continue
        if len(entries) > 0 and entries[-1][0].lower() == title.lower():
            continue
        entries.append((sentence_case_title(title), page))
        if len(entries) >= 70:
            break
    if len(entries) < 3:
        return []
    return entries


def make_book_entry(book: Book, chapter_title: str, start_page: str, end_page: str = "") -> Entry:
    is_chapter = bool(chapter_title and chapter_title != book.title)
    title = chapter_title if is_chapter else book.title
    page_range = start_page if not end_page else f"{start_page}-{end_page}"
    themes = themes_for_book(book.category, f"{book.title} {title} {book.author}")
    keywords = book_keywords(book.category, book.title, title, book.author)
    confidence = "Medium: chapter title and page extracted from table of contents; verify page range before assigning." if is_chapter else "Medium: book-level fallback; table of contents was not reliably parsed."
    reading_type = "book chapter" if is_chapter else "book"
    teaching_use = "introductory"
    if any(theme in themes for theme in ["production practice", "cinematography", "editing", "directing"]):
        teaching_use = "practice reference"
    elif any(theme in themes for theme in ["film theory", "media theory", "experimental film"]):
        teaching_use = "theory-adjacent"
    elif "national cinema" in themes or "genre" in themes:
        teaching_use = "case study"
    return Entry(
        reading_id=make_book_reading_id(book.path, start_page, title),
        source_type="Book chapter" if is_chapter else "Book",
        source_title=book.title,
        source_year=book.year,
        source=book.title,
        year=book.year,
        magazine_title="",
        issue_date="",
        volume="",
        issue_number="",
        page_range=page_range,
        publisher=book.publisher,
        edition=book.edition,
        isbn=book.isbn,
        book_title=book.title,
        editor="",
        chapter_pages=page_range,
        pdf_filename=book.path.name,
        pdf_path=str(book.path.relative_to(ROOT)),
        file_location=str(book.path.relative_to(ROOT)),
        section=book.category,
        title=title,
        author=book.author,
        printed_start_page=start_page,
        pdf_page_number="",
        short_summary=book_summary(book.title, title, book.category, book.author),
        keywords=keywords,
        specific_keywords=keywords,
        people_films_discussed="",
        course_themes="; ".join(themes),
        films_filmmakers_performers="",
        reading_type=reading_type,
        teaching_use=teaching_use,
        notes=confidence,
        confidence_note=confidence,
    )


def build_book(path: Path) -> Book:
    page_count, text, metadata = extract_book_text(path)
    title, author, publisher, edition, isbn = parse_book_metadata(path, text, metadata)
    category = book_category(path)
    year = year_from_text(text[:6000], path.name)
    book = Book(
        path=path,
        page_count=page_count,
        title=title,
        author=author,
        year=year,
        category=category,
        publisher=publisher,
        edition=edition,
        isbn=isbn,
        text=text,
    )
    toc = parse_toc_entries(text)
    if toc:
        for idx, (chapter_title, start_page) in enumerate(toc):
            next_page = toc[idx + 1][1] if idx + 1 < len(toc) and toc[idx + 1][1].isdigit() and start_page.isdigit() else ""
            end_page = str(int(next_page) - 1) if next_page and int(next_page) > int(start_page) else ""
            book.entries.append(make_book_entry(book, chapter_title, start_page, end_page))
    else:
        book.entries.append(make_book_entry(book, book.title, "", ""))
    return book


def write_csv(entries: list[Entry]) -> None:
    OUTPUT_DIR.mkdir(exist_ok=True)
    fields = list(Entry.__dataclass_fields__.keys())
    with CSV_PATH.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        for entry in entries:
            writer.writerow({field: sanitize_cell(getattr(entry, field)) for field in fields})


def sanitize_cell(value: str) -> str:
    if value is None:
        return ""
    text = str(value)
    return re.sub(r"[\x00-\x08\x0B\x0C\x0E-\x1F]", "", text)


def safe_int(value: str) -> int:
    return int(value) if str(value).isdigit() else 0


def write_guide(issues: list[Issue], books: list[Book], entries: list[Entry]) -> None:
    by_theme: dict[str, list[Entry]] = defaultdict(list)
    for entry in entries:
        for theme in entry.course_themes.split("; "):
            by_theme[theme].append(entry)
    ocr_count = len(list((OUTPUT_DIR / "ocr_text").glob("*.txt"))) if (OUTPUT_DIR / "ocr_text").exists() else 0

    lines = [
        "# Sight and Sound Reading Guide",
        "",
        "Generated from the magazine and book PDFs in this folder. The CSV is the primary sortable index; this guide is for quick browsing while designing a course.",
        "",
        f"- Magazine PDFs scanned: {len(issues)}",
        f"- Book PDFs scanned: {len(books)}",
        f"- Readings indexed: {len(entries)}",
        f"- OCR fallback files used where needed: {ocr_count}",
        "- Scope: features, columns, interviews, archive pieces, and substantial recurring departments; routine review lists are summarized by issue rather than indexed item by item.",
        "- CSV fields support mixed readings and course reuse, including stable reading IDs, source type/title/year, file location, magazine issue data, book publisher/edition/ISBN, and chapter book/editor/page data.",
        "- OCR-derived rows are useful for discovery, but rows with medium confidence should be checked against the PDF before assigning them.",
        "",
        "## Theme Browse",
        "",
    ]

    for theme, theme_entries in sorted(by_theme.items(), key=lambda item: (-len(item[1]), item[0])):
        lines.append(f"### {theme.title()}")
        for entry in sorted(theme_entries, key=lambda e: (e.source_title, e.issue_date, safe_int(e.printed_start_page)))[:30]:
            if entry.source_type.startswith("Book"):
                ref = f"{entry.book_title}, pp. {entry.page_range or 'n/a'}, `{entry.pdf_path}`"
            else:
                ref = f"{entry.issue_date}, p. {entry.printed_start_page}, `{entry.pdf_path}`"
            use = f" Best use: {entry.teaching_use}."
            lines.append(f"- **{entry.title}** ({ref}) - {entry.short_summary}{use}")
        if len(theme_entries) > 30:
            lines.append(f"- ...and {len(theme_entries) - 30} more in the CSV.")
        lines.append("")

    lines.extend(["## Book Overview", ""])
    for book in sorted(books, key=lambda b: (b.category, b.title)):
        lines.append(f"### {book.title} - `{book.path.relative_to(ROOT)}`")
        details = [f"Pages: {book.page_count}", f"indexed readings: {len(book.entries)}", f"category: {book.category}"]
        if book.author:
            details.append(f"author/editor: {book.author}")
        if book.year:
            details.append(f"year: {book.year}")
        lines.append("- " + "; ".join(details))
        for entry in book.entries[:12]:
            page = f"pp. {entry.page_range}" if entry.page_range else "book-level"
            lines.append(f"- {page}: **{entry.title}** - {entry.short_summary}")
        if len(book.entries) > 12:
            lines.append(f"- ...and {len(book.entries) - 12} more chapter entries in the CSV.")
        lines.append("")

    lines.extend(["## Issue Overview", ""])
    for issue in sorted(issues, key=lambda i: i.path.name):
        lines.append(f"### {issue.issue_date} - `{issue.path.relative_to(ROOT)}`")
        lines.append(f"- Pages: {issue.page_count}; indexed readings: {len(issue.entries)}")
        if issue.volume or issue.issue_number:
            lines.append(f"- Volume/issue: {issue.volume or '?'} / {issue.issue_number or '?'}")
        if issue.review_context:
            lines.append(f"- Review context: {issue.review_context}")
        for entry in sorted(issue.entries, key=lambda e: safe_int(e.printed_start_page))[:12]:
            lines.append(f"- p. {entry.printed_start_page}: **{entry.title}** [{entry.section}] - {entry.short_summary}")
        if len(issue.entries) > 12:
            lines.append(f"- ...and {len(issue.entries) - 12} more entries in the CSV.")
        lines.append("")

    GUIDE_PATH.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    magazine_roots = [ROOT / "Sight & Sound Magazine" / "Indexed", ROOT / "Sight & Sound Magazine" / "Incoming"]
    book_roots = [ROOT / "Books" / "Indexed", ROOT / "Books" / "Incoming"]
    magazine_pdfs = []
    for base in magazine_roots:
        if base.exists():
            magazine_pdfs.extend(sorted(base.glob("**/*.pdf")) + sorted(base.glob("**/*.PDF")))
    book_pdfs = []
    for base in book_roots:
        if base.exists():
            book_pdfs.extend(sorted(base.glob("**/*.pdf")) + sorted(base.glob("**/*.PDF")))

    issues = []
    for path in magazine_pdfs:
        try:
            issues.append(build_issue(path))
        except Exception as exc:  # Keep the batch useful even if one PDF is odd.
            print(f"ERROR\t{path.relative_to(ROOT)}\t{exc}")
    books = []
    for path in book_pdfs:
        try:
            books.append(build_book(path))
        except Exception as exc:
            print(f"ERROR\t{path.relative_to(ROOT)}\t{exc}")

    entries = [entry for issue in issues for entry in issue.entries]
    entries.extend(entry for book in books for entry in book.entries)
    entries.sort(key=lambda e: (e.source_type, e.source_title, e.pdf_filename, safe_int(e.printed_start_page), e.title))
    write_csv(entries)
    write_guide(issues, books, entries)
    print(f"Magazine PDFs scanned: {len(issues)}")
    print(f"Book PDFs scanned: {len(books)}")
    print(f"Readings indexed: {len(entries)}")
    print(f"Wrote: {CSV_PATH}")
    print(f"Wrote: {GUIDE_PATH}")
    sparse = [issue.path.name for issue in issues if len(issue.entries) < 5]
    if sparse:
        print("Sparse issues:")
        for name in sparse:
            print(f"- {name}")


if __name__ == "__main__":
    main()
