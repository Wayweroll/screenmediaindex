const DETAIL_FIELDS = [
  "row_key",
  "reading_id",
  "source_type",
  "source_title",
  "source_year",
  "source",
  "year",
  "magazine_title",
  "issue_date",
  "volume",
  "issue_number",
  "page_range",
  "publisher",
  "edition",
  "isbn",
  "book_title",
  "editor",
  "chapter_pages",
  "pdf_filename",
  "file_location",
  "section",
  "title",
  "author",
  "printed_start_page",
  "pdf_page_number",
  "short_summary",
  "keywords",
  "specific_keywords",
  "people_films_discussed",
  "course_themes",
  "films_filmmakers_performers",
  "reading_type",
  "teaching_use",
  "notes",
  "confidence_note",
];

export async function onRequestGet(context) {
  const db = context.env.DB;
  if (!db) {
    return Response.json({ error: "D1 binding DB is not configured." }, { status: 500 });
  }

  const id = context.params.id;
  const reading = await db
    .prepare(`SELECT ${DETAIL_FIELDS.join(", ")} FROM readings WHERE row_key = ?`)
    .bind(id)
    .first();

  if (!reading) {
    return Response.json({ error: "Reading not found." }, { status: 404 });
  }

  return Response.json(reading, {
    headers: {
      "Cache-Control": "public, max-age=300",
    },
  });
}
