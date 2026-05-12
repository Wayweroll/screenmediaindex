const LIST_FIELDS = [
  "row_key",
  "reading_id",
  "source_type",
  "source_title",
  "year",
  "issue_date",
  "page_range",
  "section",
  "title",
  "author",
  "short_summary",
  "keywords",
  "teaching_use",
  "file_location",
];

const FILTERS = {
  sourceType: "source_type",
  section: "section",
  teachingUse: "teaching_use",
  year: "year",
};

function json(data, init = {}) {
  return Response.json(data, {
    headers: {
      "Cache-Control": "public, max-age=120",
      ...init.headers,
    },
    ...init,
  });
}

function buildListQuery(searchParams) {
  const where = [];
  const params = [];
  const query = searchParams.get("q")?.trim();

  if (query) {
    const normalized = query
      .normalize("NFD")
      .replace(/[\u0300-\u036f]/g, "")
      .toLowerCase()
      .replace(/[^a-z0-9]+/g, " ")
      .trim();
    const like = `%${normalized}%`;
    where.push("search_text LIKE ?");
    params.push(like);
  }

  for (const [paramName, column] of Object.entries(FILTERS)) {
    const value = searchParams.get(paramName)?.trim();
    if (value) {
      where.push(`${column} = ?`);
      params.push(value);
    }
  }

  const limit = Math.min(Math.max(Number(searchParams.get("limit")) || 50, 1), 100);
  const offset = Math.max(Number(searchParams.get("offset")) || 0, 0);

  return {
    sql: `
      SELECT ${LIST_FIELDS.join(", ")}
      FROM readings
      ${where.length ? `WHERE ${where.join(" AND ")}` : ""}
      ORDER BY
        CASE WHEN source_type = 'Book' THEN 0 ELSE 1 END,
        coalesce(year, 9999),
        lower(coalesce(source_title, '')),
        lower(coalesce(title, ''))
      LIMIT ? OFFSET ?
    `,
    countSql: `
      SELECT count(*) AS total
      FROM readings
      ${where.length ? `WHERE ${where.join(" AND ")}` : ""}
    `,
    params,
    limit,
    offset,
  };
}

async function facets(db) {
  const [sourceTypes, sections, teachingUses, years] = await Promise.all([
    db.prepare("SELECT source_type AS value, count(*) AS count FROM readings WHERE source_type IS NOT NULL GROUP BY source_type ORDER BY source_type").all(),
    db.prepare("SELECT section AS value, count(*) AS count FROM readings WHERE section IS NOT NULL GROUP BY section ORDER BY count DESC, section LIMIT 80").all(),
    db.prepare("SELECT teaching_use AS value, count(*) AS count FROM readings WHERE teaching_use IS NOT NULL GROUP BY teaching_use ORDER BY count DESC, teaching_use").all(),
    db.prepare("SELECT year AS value, count(*) AS count FROM readings WHERE year IS NOT NULL GROUP BY year ORDER BY year DESC").all(),
  ]);

  return {
    sourceTypes: sourceTypes.results,
    sections: sections.results,
    teachingUses: teachingUses.results,
    years: years.results,
  };
}

export async function onRequestGet(context) {
  const db = context.env.DB;
  if (!db) {
    return json({ error: "D1 binding DB is not configured." }, { status: 500 });
  }

  const url = new URL(context.request.url);
  const { sql, countSql, params, limit, offset } = buildListQuery(url.searchParams);
  const [rows, count, facetData] = await Promise.all([
    db.prepare(sql).bind(...params, limit, offset).all(),
    db.prepare(countSql).bind(...params).first(),
    facets(db),
  ]);

  return json({
    readings: rows.results,
    total: count?.total ?? 0,
    limit,
    offset,
    facets: facetData,
  });
}
