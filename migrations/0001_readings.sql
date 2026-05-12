DROP TABLE IF EXISTS readings;

CREATE TABLE readings (
  row_key TEXT PRIMARY KEY,
  reading_id TEXT,
  source_type TEXT,
  source_title TEXT,
  source_year INTEGER,
  source TEXT,
  year INTEGER,
  magazine_title TEXT,
  issue_date TEXT,
  volume TEXT,
  issue_number TEXT,
  page_range TEXT,
  publisher TEXT,
  edition TEXT,
  isbn TEXT,
  book_title TEXT,
  editor TEXT,
  chapter_pages TEXT,
  pdf_filename TEXT,
  pdf_path TEXT,
  file_location TEXT,
  section TEXT,
  title TEXT,
  author TEXT,
  printed_start_page TEXT,
  pdf_page_number TEXT,
  short_summary TEXT,
  keywords TEXT,
  specific_keywords TEXT,
  people_films_discussed TEXT,
  course_themes TEXT,
  films_filmmakers_performers TEXT,
  reading_type TEXT,
  teaching_use TEXT,
  notes TEXT,
  confidence_note TEXT,
  search_text TEXT
);

CREATE INDEX idx_readings_source_type ON readings(source_type);
CREATE INDEX idx_readings_reading_id ON readings(reading_id);
CREATE INDEX idx_readings_section ON readings(section);
CREATE INDEX idx_readings_year ON readings(year);
CREATE INDEX idx_readings_teaching_use ON readings(teaching_use);
CREATE INDEX idx_readings_title ON readings(title);
CREATE INDEX idx_readings_search_text ON readings(search_text);
