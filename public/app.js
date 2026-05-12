const state = {
  limit: 50,
  offset: 0,
  total: 0,
  loading: false,
};

const fields = {
  search: document.querySelector("#search"),
  sourceType: document.querySelector("#sourceType"),
  section: document.querySelector("#section"),
  teachingUse: document.querySelector("#teachingUse"),
  year: document.querySelector("#year"),
};

const results = document.querySelector("#results");
const count = document.querySelector("#count");
const loadMore = document.querySelector("#loadMore");
const reset = document.querySelector("#reset");
const dialog = document.querySelector("#detailDialog");

function clean(value) {
  return value === null || value === undefined || value === "" ? "Unknown" : value;
}

function debounce(callback, delay = 250) {
  let timeout;
  return (...args) => {
    window.clearTimeout(timeout);
    timeout = window.setTimeout(() => callback(...args), delay);
  };
}

function params() {
  const searchParams = new URLSearchParams({
    limit: String(state.limit),
    offset: String(state.offset),
  });

  for (const [name, field] of Object.entries(fields)) {
    if (field.value) searchParams.set(name === "search" ? "q" : name, field.value);
  }

  return searchParams;
}

function option(label, value = label, countValue = null) {
  const item = document.createElement("option");
  item.value = value ?? "";
  item.textContent = countValue === null ? label : `${label} (${countValue})`;
  return item;
}

function fillSelect(select, values, firstLabel) {
  if (select.options.length > 1) return;
  select.append(
    ...values
      .filter((item) => item.value !== null && item.value !== "")
      .map((item) => option(item.value, item.value, item.count)),
  );
  select.options[0].textContent = firstLabel;
}

function renderFacets(facets) {
  fillSelect(fields.sourceType, facets.sourceTypes, "All sources");
  fillSelect(fields.section, facets.sections, "All sections");
  fillSelect(fields.teachingUse, facets.teachingUses, "All uses");
  fillSelect(fields.year, facets.years, "All years");
}

function renderReading(reading) {
  const article = document.createElement("article");
  article.className = "reading";

  const title = clean(reading.title || reading.source_title);
  const source = clean(reading.source_title);
  const summary = reading.short_summary || "No summary available yet.";
  const page = reading.page_range || reading.chapter_pages || reading.printed_start_page;

  article.innerHTML = `
    <div class="reading-header">
      <div>
        <p class="eyebrow">${clean(reading.source_type)}</p>
        <h3>${title}</h3>
      </div>
      <button class="open-detail" type="button">Details</button>
    </div>
    <div class="meta">
      <span class="pill">${source}</span>
      <span class="pill">${clean(reading.year || reading.issue_date)}</span>
      <span class="pill">${clean(reading.section)}</span>
      ${page ? `<span class="pill">Pages ${page}</span>` : ""}
    </div>
    <p>${summary}</p>
  `;

  article.querySelector("button").addEventListener("click", () => showDetail(reading.row_key));
  return article;
}

async function loadReadings({ append = false } = {}) {
  if (state.loading) return;
  state.loading = true;
  loadMore.textContent = "Loading...";

  try {
    const response = await fetch(`/api/readings?${params()}`);
    if (!response.ok) throw new Error("The reading index could not be loaded.");
    const data = await response.json();

    state.total = data.total;
    renderFacets(data.facets);
    if (!append) results.replaceChildren();
    results.append(...data.readings.map(renderReading));
    state.offset += data.readings.length;

    count.textContent = `${state.total.toLocaleString()} readings`;
    loadMore.hidden = state.offset >= state.total;
    loadMore.textContent = "Load more";
  } catch (error) {
    results.innerHTML = `<article class="reading"><h3>Index unavailable</h3><p>${error.message}</p></article>`;
    count.textContent = "Not connected";
    loadMore.hidden = true;
  } finally {
    state.loading = false;
  }
}

function resetResults() {
  state.offset = 0;
  loadReadings();
}

function addMeta(list, label, value) {
  if (!value) return;
  const dt = document.createElement("dt");
  const dd = document.createElement("dd");
  dt.textContent = label;
  dd.textContent = value;
  list.append(dt, dd);
}

async function showDetail(id) {
  const response = await fetch(`/api/readings/${encodeURIComponent(id)}`);
  if (!response.ok) return;
  const reading = await response.json();
  const title = reading.title || reading.source_title || "Untitled reading";
  const meta = document.querySelector("#detailMeta");
  const keywords = document.querySelector("#detailKeywords");

  document.querySelector("#detailSource").textContent = `${clean(reading.source_type)} / ${clean(reading.section)}`;
  document.querySelector("#detailTitle").textContent = title;
  document.querySelector("#detailSummary").textContent = reading.short_summary || "No summary available yet.";
  meta.replaceChildren();
  keywords.replaceChildren();

  addMeta(meta, "Source", reading.source_title);
  addMeta(meta, "Author", reading.author);
  addMeta(meta, "Year", reading.year || reading.source_year);
  addMeta(meta, "Pages", reading.page_range || reading.chapter_pages || reading.printed_start_page);
  addMeta(meta, "Teaching use", reading.teaching_use);
  addMeta(meta, "Location", reading.file_location);
  addMeta(meta, "Notes", reading.notes);

  const keywordItems = (reading.specific_keywords || reading.keywords || "")
    .split(";")
    .map((item) => item.trim())
    .filter(Boolean)
    .slice(0, 18);
  keywords.append(...keywordItems.map((item) => {
    const span = document.createElement("span");
    span.className = "pill";
    span.textContent = item;
    return span;
  }));

  dialog.showModal();
}

for (const field of Object.values(fields)) {
  field.addEventListener("input", debounce(resetResults));
}

reset.addEventListener("click", () => {
  for (const field of Object.values(fields)) field.value = "";
  resetResults();
});

loadMore.addEventListener("click", () => loadReadings({ append: true }));
document.querySelector("#closeDetail").addEventListener("click", () => dialog.close());

loadReadings();
