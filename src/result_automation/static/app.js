"use strict";

const paths = {
  brand: '<path d="M4 5h16M4 12h16M4 19h16M9 5v14"/>',
  folder: '<path d="M3 7a2 2 0 0 1 2-2h5l2 2h7a2 2 0 0 1 2 2v10H3Z"/>',
  file: '<path d="M14 3H6a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V9Z"/><path d="M14 3v6h6M8 13h8M8 17h5"/>',
  "scan-file": '<path d="M8 4H4v4m12-4h4v4M4 16v4h4m12-4v4h-4M8 8h8v8H8Z"/><path d="M2 12h20"/>',
  scan: '<path d="M7 3H3v4m14-4h4v4M3 17v4h4m14-4v4h-4M3 12h18M7 8h10m-10 8h10"/>',
  plus: '<path d="M12 5v14M5 12h14"/>',
  monitor: '<rect x="3" y="4" width="18" height="13" rx="2"/><path d="M8 21h8m-4-4v4"/>',
  help: '<circle cx="12" cy="12" r="9"/><path d="M9.5 8.5a2.5 2.5 0 0 1 4.7 1.3c0 1.7-2.2 1.9-2.2 3.7M12 17h.01"/>',
  "arrow-up-right": '<path d="M7 17 17 7M7 7h10v10"/>',
  "arrow-right": '<path d="M4 12h16m-6-6 6 6-6 6"/>',
  grid: '<rect x="3" y="3" width="7" height="7" rx="1"/><rect x="14" y="3" width="7" height="7" rx="1"/><rect x="3" y="14" width="7" height="7" rx="1"/><rect x="14" y="14" width="7" height="7" rx="1"/>',
  download: '<path d="M12 3v12m-5-5 5 5 5-5M4 16v4h16v-4"/>',
  upload: '<path d="M12 16V4m-5 5 5-5 5 5M4 16v4h16v-4"/>',
  more: '<circle cx="5" cy="12" r="1"/><circle cx="12" cy="12" r="1"/><circle cx="19" cy="12" r="1"/>',
  table: '<rect x="3" y="4" width="18" height="16" rx="2"/><path d="M3 9h18M3 14h18M10 9v11"/>',
  trash: '<path d="M3 6h18M9 6V3h6v3M5 6l1 15h12l1-15M10 10v7m4-7v7"/>',
  shield: '<path d="M12 3 4 6v6c0 5 8 9 8 9s8-4 8-9V6Z"/><path d="m9 12 2 2 4-4"/>',
  lock: '<rect x="5" y="10" width="14" height="11" rx="2"/><path d="M8 10V7a4 4 0 0 1 8 0v3m-4 5v2"/>',
  "check-circle": '<circle cx="12" cy="12" r="9"/><path d="m8 12 3 3 5-6"/>',
  check: '<path d="m5 12 4 4L19 6"/>',
  users: '<path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2m20 0v-2a4 4 0 0 0-3-3.87"/><circle cx="9" cy="7" r="4"/><path d="M16 3a4 4 0 0 1 0 8"/>',
  flag: '<path d="M4 22V3m0 1c5-4 11 4 16 0v11c-5 4-11-4-16 0"/>',
  columns: '<rect x="3" y="4" width="18" height="16" rx="2"/><path d="M9 4v16m6-16v16"/>',
  "chevron-left": '<path d="m15 5-7 7 7 7"/>',
  "chevron-right": '<path d="m9 5 7 7-7 7"/>',
  "chevron-down": '<path d="m6 9 6 6 6-6"/>',
  expand: '<path d="M8 3H3v5m13-5h5v5M3 16v5h5m13-5v5h-5"/>',
  pointer: '<path d="m4 3 7 18 2-8 8-2Z"/>',
  search: '<circle cx="10.5" cy="10.5" r="6.5"/><path d="m16 16 5 5"/>',
  edit: '<path d="m16 3 5 5-12 12-6 1 1-6Z"/><path d="m13 6 5 5"/>',
  sliders: '<path d="M4 7h7m4 0h5M4 17h3m4 0h9"/><circle cx="13" cy="7" r="2"/><circle cx="9" cy="17" r="2"/>',
  reset: '<path d="M3 11a9 9 0 1 1 2 7M3 4v7h7"/>',
  close: '<path d="m6 6 12 12M6 18 18 6"/>',
};
const $ = id => document.getElementById(id);
const icon = name => `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${paths[name] || paths.file}</svg>`;
const escapeHTML = value => String(value ?? "").replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
const clone = object => JSON.parse(JSON.stringify(object));
function fillIcons(root = document) { root.querySelectorAll("[data-icon]").forEach(node => node.innerHTML = icon(node.dataset.icon)); }
fillIcons();

const state = {doc: null, documents: [], page: 1, selected: null, filter: "all", sort: "source", query: "", lowConfidence: .7, drafts: new Map(), selection: null,
  drag: null, zoom: false, mutating: false, exporting: false, openToken: 0, poll: null, editId: null, editNew: false};

function toast(message, error = false) {
  const node = document.createElement("div");
  node.className = `toast${error ? " error" : ""}`;
  node.innerHTML = icon(error ? "flag" : "check-circle") + `<span>${escapeHTML(message)}</span>`;
  $("toasts").append(node);
  setTimeout(() => node.remove(), error ? 7500 : 4200);
}

function connected(ok) {
  $("connection").classList.toggle("offline", !ok);
  $("connection").innerHTML = `<span class="status-dot"></span>${ok ? "Processing stays local" : "Backend disconnected"}`;
}

async function api(path, options = {}) {
  let response;
  try { response = await fetch(path, options); }
  catch { connected(false); throw new Error("Cannot reach the local backend. Keep its terminal running and try again."); }
  connected(true);
  if (response.status === 204) return null;
  let data;
  try { data = await response.json(); }
  catch { throw new Error("The backend returned an unexpected response."); }
  if (!response.ok) {
    const detail = Array.isArray(data.detail) ? data.detail.map(item => item.msg).join("; ") : data.detail;
    const error = new Error(detail || "The request could not be completed.");
    error.status = response.status;
    throw error;
  }
  return data;
}

function confirmAction(title, message, label = "Continue", danger = false) {
  const dialog = $("confirmDialog");
  if (dialog.open) return Promise.resolve(false);
  $("confirmTitle").textContent = title;
  $("confirmMessage").textContent = message;
  $("confirmAccept").textContent = label;
  $("confirmAccept").style.background = danger ? "#a4594a" : "";
  return new Promise(resolve => {
    const finish = value => { dialog.close(); resolve(value); };
    $("confirmAccept").onclick = () => finish(true);
    $("confirmCancel").onclick = () => finish(false);
    dialog.oncancel = event => { event.preventDefault(); finish(false); };
    dialog.showModal();
  });
}

function dateLabel(value) {
  const date = new Date(value);
  return date.toLocaleDateString(undefined, {month:"short", day:"numeric"}) + " at " + date.toLocaleTimeString(undefined, {hour:"2-digit", minute:"2-digit"});
}

function view(name) {
  for (const id of ["homeView", "documentView", "progressView"]) $(id).hidden = id !== name;
  $("documentActions").hidden = name !== "documentView";
}

function documentSubtitle(doc) {
  if (doc.status === "ready") return `${doc.row_count} rows · ${doc.page_count} ${doc.page_count === 1 ? "page" : "pages"}`;
  return ({uploading:"Receiving file",queued:"Waiting to extract",processing:"Extracting…",cancelling:"Cancelling…",cancelled:"Cancelled",error:"Needs attention"})[doc.status] || doc.status;
}

function libraryMarkup(doc) {
  const indicator = doc.status === "error" ? "error" : ["queued","processing","cancelling"].includes(doc.status) ? "processing" : doc.review_count ? "review" : "";
  return `<button class="recent-item${state.doc?.id === doc.id ? " current" : ""}" data-document="${doc.id}" title="${escapeHTML(doc.filename)}"><span class="recent-file-icon">${icon("file")}</span><span class="recent-text"><strong>${escapeHTML(doc.filename)}</strong><small>${escapeHTML(documentSubtitle(doc))}</small></span><span class="recent-indicator ${indicator}"></span></button>`;
}

function renderLibrary() {
  $("documentCount").textContent = state.documents.length;
  $("recentList").innerHTML = state.documents.length ? state.documents.slice(0, 15).map(libraryMarkup).join("") : '<div class="sidebar-empty">Your marksheets will appear here.</div>';
  $("libraryList").innerHTML = state.documents.length ? state.documents.map(libraryMarkup).join("") : '<p class="dialog-description">No documents yet. Add a marksheet to get started.</p>';
}

async function refreshLibrary() { state.documents = await api("/api/documents"); renderLibrary(); }
function updateLibrary(doc) {
  const index = state.documents.findIndex(item => item.id === doc.id);
  if (index < 0) state.documents.unshift(doc); else state.documents[index] = doc;
  renderLibrary();
}

async function canLeave() {
  if (!state.drafts.size) return true;
  return confirmAction("Discard column selections?", "Your row edits are already saved. These column selections have not been applied yet.", "Discard selections");
}

async function goHome() {
  if (!await canLeave()) return;
  clearTimeout(state.poll); state.openToken++; state.doc = null; state.drafts.clear(); state.selection = null;
  localStorage.removeItem("result-desk-document");
  $("eyebrow").textContent = "A LITTLE LESS DATA ENTRY";
  $("titleText").textContent = "From marksheet to spreadsheet.";
  $("titleDescription").textContent = "Extract rolls and marks. Check the details. Get on with your day.";
  $("breadcrumbName").textContent = "Documents";
  view("homeView"); renderLibrary();
}

async function openDocument(id, checkDrafts = true) {
  if (checkDrafts && !await canLeave()) return;
  const token = ++state.openToken;
  clearTimeout(state.poll);
  state.drafts.clear(); state.selection = null; state.page = 1; state.selected = null; state.query = ""; state.filter = "all";
  $("searchInput").value = "";
  try {
    const doc = await api(`/api/documents/${id}`);
    if (token !== state.openToken) return;
    localStorage.setItem("result-desk-document", id);
    applyDocument(doc);
    if (doc.status !== "ready" && !["error", "cancelled"].includes(doc.status)) pollDocument(id, token);
  } catch (error) { toast(error.message, true); }
}

function pollDocument(id, token) {
  clearTimeout(state.poll);
  state.poll = setTimeout(async () => {
    if (token !== state.openToken) return;
    try {
      const doc = await api(`/api/documents/${id}`);
      if (token !== state.openToken) return;
      applyDocument(doc);
      if (!["ready", "error", "cancelled"].includes(doc.status)) pollDocument(id, token);
      else if (doc.status === "ready") toast(`Extracted ${doc.row_count} rows. Your review is ready.`);
    } catch (error) {
      if (token === state.openToken) { $("progressMessage").textContent = error.message; pollDocument(id, token); }
    }
  }, 800);
}

function applyDocument(doc) {
  state.doc = doc;
  updateLibrary(doc);
  $("breadcrumbName").textContent = doc.filename;
  $("eyebrow").textContent = doc.status === "ready" ? "YOUR MARKSHEET WORKSPACE" : "LOCAL EXTRACTION";
  $("titleText").textContent = doc.filename;
  document.title = `${doc.filename} — Result Desk`;
  if (doc.status !== "ready") { renderProgress(doc); return; }
  view("documentView");
  state.page = Math.min(state.page, doc.pages.length) || 1;
  if (!doc.records.some(row => row.id === state.selected)) state.selected = (doc.records.find(row => row.page === state.page) || doc.records[0])?.id || null;
  $("titleDescription").textContent = `${doc.page_count} ${doc.page_count === 1 ? "page" : "pages"} · ${[...new Set(doc.pages.map(page => page.method))].join(" + ")} · Added ${dateLabel(doc.created_at)}`;
  $("totalRows").textContent = doc.row_count;
  $("needsReview").textContent = doc.review_count;
  $("verifiedRows").textContent = doc.verified_count;
  $("allCount").textContent = doc.row_count;
  $("reviewCount").textContent = doc.review_count;
  $("confidenceCount").textContent = doc.records.filter(needsConfidenceReview).length;
  $("maxMark").value = doc.max_mark ?? "";
  $("absentCodes").value = (doc.absent_codes || []).join(", ");
  $("allowFractions").checked = doc.allow_fractions !== false;
  $("sortRows").value = state.sort;
  $("pageSelect").innerHTML = doc.pages.map(page => `<option value="${page.number}">Page ${page.number} of ${doc.page_count}</option>`).join("");
  $("warnings").hidden = !doc.warnings.length;
  $("warnings").innerHTML = doc.warnings.map(warning => `<span>${escapeHTML(warning)}</span>`).join("");
  $("exportLayoutNote").textContent = doc.export_columns ? `${doc.export_columns.length} export columns: ${doc.export_columns.map(column => column.name).join(" → ")}` : "Choose source columns, rename headings, and arrange your Excel preview.";
  $("downloadSource").href = `/api/documents/${doc.id}/source`;
  renderRows(); renderPage(); setMutationState();
}

function renderProgress(doc) {
  view("progressView");
  const failed = doc.status === "error", cancelled = doc.status === "cancelled";
  $("titleDescription").textContent = "Your document is processed by the backend on this computer.";
  $("jobBadge").textContent = failed ? "LET’S TAKE ANOTHER LOOK" : cancelled ? "EXTRACTION STOPPED" : "WORKING ON YOUR COMPUTER";
  $("progressTitle").textContent = failed ? "We couldn’t read this file" : cancelled ? "Extraction cancelled" : doc.status === "queued" ? "Your document is in line" : "Reading your marksheet";
  $("progressMessage").textContent = doc.error || doc.progress;
  $("jobSpinner").hidden = failed || cancelled;
  $("cancelJob").hidden = failed || cancelled;
  $("cancelJob").disabled = doc.status === "cancelling";
  $("retryUpload").hidden = !(failed || cancelled);
  $("removeFailed").hidden = !(failed || cancelled);
  $("progressNote").textContent = failed && /password/i.test(doc.error || "") ? "Use the upload dialog again and enter the PDF password there." : failed ? "Try an upright, clear PDF or image. Your original file has not been changed." : cancelled ? "You can upload another document whenever you’re ready." : "You can leave this page open. Your document will appear here when it’s ready.";
}

async function importFile(file) {
  if (!file || !await canLeave()) return;
  if (file.size > 50 * 1024 * 1024) { toast("Choose a file smaller than 50 MB.", true); return; }
  if (!/\.(pdf|png|jpe?g|tiff?|bmp|webp)$/i.test(file.name)) { toast("Choose a PDF, PNG, JPEG, TIFF, BMP, or WebP file.", true); return; }
  if ($("uploadDialog").open) $("uploadDialog").close();
  const form = new FormData(); form.append("file", file); form.append("force_ocr", $("forceOCR").checked);
  if ($("pdfPassword").value) form.append("password", $("pdfPassword").value);
  $("forceOCR").checked = false; $("pdfPassword").value = "";
  clearTimeout(state.poll); state.openToken++; state.drafts.clear();
  view("progressView");
  $("titleText").textContent = file.name; $("titleDescription").textContent = "Adding your document to the local workspace…";
  $("progressTitle").textContent = "Bringing in your marksheet"; $("progressMessage").textContent = "Saving the file on this computer…";
  $("jobBadge").textContent = "LOCAL UPLOAD"; $("jobSpinner").hidden = false; $("cancelJob").hidden = true;
  $("retryUpload").hidden = true; $("removeFailed").hidden = true;
  try {
    const doc = await api("/api/documents", {method:"POST", body:form});
    await refreshLibrary(); await openDocument(doc.id, false);
  } catch (error) { toast(error.message, true); await goHome(); }
}

function currentPage() { return state.doc?.pages?.[state.page - 1]; }
function currentRow() { return state.doc?.records?.find(row => row.id === state.selected); }
function isLowConfidence(row) { return row.method === "Local OCR" && Number(row.confidence ?? 1) < state.lowConfidence; }
function needsConfidenceReview(row) { return isLowConfidence(row) && !row.reviewed; }
function filteredRows() {
  let rows = (state.doc?.records || []).filter(row => (!state.query || row.roll.includes(state.query))
    && (state.filter !== "review" || row.issues.length)
    && (state.filter !== "confidence" || needsConfidenceReview(row)));
  if (state.sort === "confidence") rows = [...rows].sort((a, b) => Number(a.confidence ?? 1) - Number(b.confidence ?? 1) || a.roll.localeCompare(b.roll));
  return rows;
}

function renderRows() {
  if (state.doc?.status !== "ready") return;
  const rows = filteredRows();
  $("filterAll").classList.toggle("active", state.filter === "all");
  $("filterReview").classList.toggle("active", state.filter === "review");
  $("filterConfidence").classList.toggle("active", state.filter === "confidence");
  $("tableBody").innerHTML = rows.map(row => {
    const low = needsConfidenceReview(row);
    const confidence = low ? `<span class="confidence-chip" title="Local OCR confidence ${Number(row.confidence).toFixed(2)}">${Math.round(Number(row.confidence) * 100)}%</span>` : "";
    const verify = row.reviewed
      ? `<button class="row-verify done" disabled title="This row is already reviewed" aria-label="Already reviewed">${icon("check")}</button>`
      : `<button class="row-verify" data-verify="${row.id}" title="Mark this row reviewed (R)" aria-label="Mark roll ${escapeHTML(row.roll || "blank")} reviewed" aria-keyshortcuts="R">${icon("check")}</button>`;
    return `<tr data-row="${row.id}" tabindex="0" aria-selected="${row.id === state.selected}" class="${row.id === state.selected ? "selected" : ""}${low ? " low-confidence" : ""}"><td>${escapeHTML(row.roll || "—")}</td><td>${escapeHTML(row.mark || "—")}</td><td><span class="row-status ${row.issues.length ? "needs-review" : row.reviewed ? "reviewed" : ""}" title="${escapeHTML(row.issues.join("; "))}">${escapeHTML(row.status)}</span>${confidence}</td><td>${verify}</td><td><button class="icon-button" data-edit="${row.id}" aria-label="Edit roll ${escapeHTML(row.roll || "blank")}">${icon("edit")}</button></td></tr>`;
  }).join("");
  $("emptyRows").hidden = rows.length > 0;
  $("emptyRowsMessage").textContent = !state.doc.records.length ? "Select the roll and marks columns on the source, then re-extract the page." : state.filter === "review" && !state.query ? "No rows currently need review." : state.filter === "confidence" ? "No rows are below the confidence threshold." : "Try a different roll number or change the filter.";
  $("visibleCount").textContent = `Showing ${rows.length} of ${state.doc.row_count} rows`;
  renderDetail();
}

function selectRow(id, scroll = false, focus = false) {
  const row = state.doc?.records.find(record => record.id === id);
  if (!row) return;
  state.selected = id;
  const changedPage = state.page !== row.page;
  state.page = row.page;
  renderRows(); renderPage();
  if (changedPage) $("pageViewport").scrollTop = 0;
  const element = $("tableBody").querySelector(`[data-row="${CSS.escape(id)}"]`);
  if (scroll) element?.scrollIntoView({block:"nearest"});
  if (focus) element?.focus({preventScroll:true});
}

function moveSelection(position) {
  const rows = filteredRows();
  if (!rows.length) return;
  const current = rows.findIndex(row => row.id === state.selected);
  let index = current;
  if (position === "first") index = 0;
  else if (position === "last") index = rows.length - 1;
  else if (position === "next") index = current < 0 ? 0 : Math.min(current + 1, rows.length - 1);
  else if (position === "previous") index = current < 0 ? rows.length - 1 : Math.max(current - 1, 0);
  selectRow(rows[index].id, true, true);
}

function renderDetail() {
  const row = currentRow();
  $("rowDetail").hidden = !row;
  if (!row) return;
  $("detailTitle").textContent = `Roll ${row.roll || "—"}`;
  const score = row.method === "Local OCR" ? ` · OCR confidence ${Number(row.confidence ?? 0).toFixed(2)}${isLowConfidence(row) ? " (low)" : ""}` : "";
  $("rowProvenance").textContent = row.method === "Manual" ? "Manually added row · No original cell recorded" : `Page ${row.page} · ${row.method} · Original: ${row.raw_roll || "(blank)"} → ${row.raw_mark || "(blank)"}${score}`;
  $("rowIssues").hidden = !row.issues.length;
  $("rowIssues").textContent = row.issues.join(" · ");
  $("reviewState").innerHTML = icon(row.issues.length ? "flag" : "check-circle") + (row.issues.length ? "Check the highlighted issues" : row.reviewed ? "Verified by you" : "No validation issues");
  $("verifyRow").innerHTML = icon("check") + (row.reviewed ? "Verified" : "Mark verified");
  $("verifyRow").disabled = state.mutating || row.reviewed;
  $("rowCrop").parentElement.hidden = row.method === "Manual";
  drawCrop();
}

function renderMarkCandidates(page) {
  const select = $("markCandidateSelect");
  const layout = state.drafts.get(state.page) || page.layout;
  const candidates = page.mark_candidates || [];
  select.innerHTML = "";
  for (const candidate of candidates) {
    const option = document.createElement("option");
    option.value = candidate.id;
    option.textContent = `${candidate.label}${candidate.max_mark != null ? ` · max ${candidate.max_mark}` : ""}`;
    option.title = candidate.label;
    select.append(option);
  }
  let selected = candidates.find(candidate => layout
    && Math.abs(candidate.left - layout.mark[0]) < .003 && Math.abs(candidate.right - layout.mark[1]) < .003);
  if (!selected && layout) {
    const option = document.createElement("option");
    option.value = "";
    option.textContent = `Custom: ${layout.label || "selection"}`;
    select.append(option);
    select.value = "";
  } else if (selected) {
    select.value = selected.id;
  }
  if (!candidates.length) {
    const option = document.createElement("option");
    option.value = "";
    option.textContent = layout?.label || "No columns detected";
    select.append(option);
  }
  select.disabled = state.mutating || !layout;
  $("columnBadge").textContent = layout?.automatic ? "AUTO-DETECTED" : layout ? "CUSTOM" : "NO COLUMN";
}

function renderPage() {
  const page = currentPage();
  if (!page) return;
  $("pageSelect").value = state.page;
  $("prevPage").disabled = state.page <= 1;
  $("nextPage").disabled = state.page >= state.doc.page_count;
  renderMarkCandidates(page);
  $("sourceMethod").innerHTML = '<span class="status-dot"></span>' + escapeHTML(page.method);
  const image = $("pageImage");
  image.alt = `Original marksheet, page ${page.number} of ${state.doc.page_count}`;
  if (image.dataset.url !== page.image_url) { image.dataset.url = page.image_url; image.src = page.image_url; }
  $("pageSheet").classList.toggle("selecting", !!state.selection);
  $("selectRoll").setAttribute("aria-pressed", state.selection === "roll");
  $("selectMark").setAttribute("aria-pressed", state.selection === "mark");
  $("selectionHint").classList.toggle("selecting", !!state.selection);
  $("selectionHint").innerHTML = icon("pointer") + (state.selection ? `Drag around the ${state.selection === "roll" ? "roll" : "marks"} cells, first student to last. Exclude the header.` : "Click a result to find its original row.");
  $("selectionActions").hidden = !state.drafts.has(state.page);
  resizePreview(); drawOverlay(); setMutationState();
}

function resizePreview() {
  const page = currentPage();
  if (!page) return;
  const viewport = $("pageViewport"), width = Math.max(100, viewport.clientWidth - 34), height = Math.max(100, viewport.clientHeight - 34);
  $("pageSheet").style.width = Math.floor(state.zoom ? width : Math.min(width, height * page.width / page.height)) + "px";
  drawCrop();
}

function rect(box, color, fill = .02, dashed = false) {
  return `<rect x="${box[0] * 1000}" y="${box[1] * 1000}" width="${(box[2]-box[0]) * 1000}" height="${(box[3]-box[1]) * 1000}" fill="${color}" fill-opacity="${fill}" stroke="${color}" stroke-width="1.6" vector-effect="non-scaling-stroke" ${dashed ? 'stroke-dasharray="5 4"' : ""}/>`;
}

function drawOverlay() {
  const page = currentPage();
  if (!page) return;
  const layout = state.drafts.get(state.page) || page.layout;
  let markup = "";
  if (layout) markup += rect([layout.roll[0],layout.top,layout.roll[1],layout.bottom], "#548763") + rect([layout.mark[0],layout.top,layout.mark[1],layout.bottom], "#c39a51");
  const row = currentRow();
  if (row && row.page === state.page && row.method !== "Manual") markup += rect(row.box, "#6396bc", .06);
  if (state.drag) {
    const {start, end} = state.drag;
    markup += rect([Math.min(start.x,end.x),Math.min(start.y,end.y),Math.max(start.x,end.x),Math.max(start.y,end.y)], state.selection === "roll" ? "#548763" : "#c39a51", .12, true);
  }
  $("pageOverlay").innerHTML = markup;
}

function drawCrop() {
  const image = $("pageImage"), row = currentRow();
  if (!row || row.page !== state.page || !image.complete || !image.naturalWidth) return;
  const canvas = $("rowCrop"), ratio = window.devicePixelRatio || 1;
  const [x0,y0,x1,y1] = row.box;
  const sx = Math.max(0, x0 * image.naturalWidth - 3), sy = Math.max(0, y0 * image.naturalHeight - 3);
  const sw = Math.min(image.naturalWidth-sx, (x1-x0) * image.naturalWidth + 6), sh = Math.min(image.naturalHeight-sy, (y1-y0) * image.naturalHeight + 6);
  if (sw <= 0 || sh <= 0) return;
  const scale = Math.min((canvas.parentElement.clientWidth - 10) / sw, (canvas.parentElement.clientHeight - 10) / sh);
  if (scale <= 0) return;
  canvas.width = Math.ceil(sw*scale*ratio); canvas.height = Math.ceil(sh*scale*ratio);
  canvas.style.width = `${sw*scale}px`; canvas.style.height = `${sh*scale}px`;
  const context = canvas.getContext("2d"); context.setTransform(ratio,0,0,ratio,0,0);
  context.fillStyle = "white"; context.fillRect(0,0,sw*scale,sh*scale);
  context.drawImage(image,sx,sy,sw,sh,0,0,sw*scale,sh*scale);
}

function setMutationState() {
  const ready = state.doc?.status === "ready";
  for (const id of ["addRow","editRow","selectRoll","selectMark","applyAll","applyPage","resetColumns","saveRow","chooseColumns"]) $(id).disabled = state.mutating || !ready;
  $("markCandidateSelect").disabled = state.mutating || !currentPage()?.layout;
  $("exportExcel").disabled = state.mutating || state.exporting || !ready || !state.doc?.row_count || !!state.drafts.size;
  $("exportCSV").disabled = $("exportExcel").disabled;
  $("savedState").classList.toggle("saving", state.mutating || !!state.drafts.size);
  $("savedState").innerHTML = icon(state.mutating ? "reset" : "check-circle") + (state.mutating ? "Saving changes…" : state.drafts.size ? "Apply your column selections to update results" : "All changes saved locally");
  if (ready && currentRow()) $("verifyRow").disabled = state.mutating || currentRow().reviewed;
}

async function mutate(endpoint, body, method = "POST", message = "Changes saved.") {
  if (state.mutating || state.doc?.status !== "ready") return null;
  const id = state.doc.id, version = state.doc.version;
  state.mutating = true; setMutationState();
  try {
    const doc = await api(`/api/documents/${id}/${endpoint}`, {method, headers:{"Content-Type":"application/json"}, body:JSON.stringify({...body,version})});
    if (state.doc?.id === id) applyDocument(doc);
    else updateLibrary(doc);
    if (message) toast(message);
    return doc;
  } catch (error) {
    if (error.status === 409 && state.doc?.id === id) {
      try { applyDocument(await api(`/api/documents/${id}`)); } catch { /* Keep the existing review visible. */ }
    }
    throw error;
  } finally { state.mutating = false; setMutationState(); }
}

function setPage(number) {
  if (!state.doc?.pages || number < 1 || number > state.doc.page_count) return;
  state.page = number; state.selection = null; state.drag = null;
  state.selected = state.doc.records.find(row => row.page === number)?.id || null;
  renderRows(); renderPage(); $("pageViewport").scrollTop = 0;
  if (state.selected) $("tableBody").querySelector(`[data-row="${CSS.escape(state.selected)}"]`)?.scrollIntoView({block:"nearest"});
}

function point(event) {
  const bounds = $("pageOverlay").getBoundingClientRect();
  return {x:Math.max(0,Math.min(1,(event.clientX-bounds.left)/bounds.width)), y:Math.max(0,Math.min(1,(event.clientY-bounds.top)/bounds.height))};
}

$("pageOverlay").addEventListener("pointerdown", event => {
  if (state.mutating) return;
  if (!state.selection) {
    const at = point(event);
    const row = state.doc?.records.find(row => row.page === state.page && row.box[1] <= at.y && row.box[3] >= at.y && row.box[0] <= at.x && row.box[2] >= at.x);
    if (row) selectRow(row.id, true);
    return;
  }
  event.preventDefault(); event.currentTarget.setPointerCapture(event.pointerId);
  state.drag = {start:point(event), end:point(event)}; drawOverlay();
});
$("pageOverlay").addEventListener("pointermove", event => { if (state.drag) { state.drag.end = point(event); drawOverlay(); } });
$("pageOverlay").addEventListener("pointercancel", () => { state.drag = null; drawOverlay(); });
$("pageOverlay").addEventListener("pointerup", event => {
  if (!state.drag || !state.selection) return;
  const start = state.drag.start, end = point(event);
  const left = Math.min(start.x,end.x), right = Math.max(start.x,end.x), top = Math.min(start.y,end.y), bottom = Math.max(start.y,end.y);
  state.drag = null;
  if (right-left < .008 || bottom-top < .01) { drawOverlay(); return; }
  const layout = clone(state.drafts.get(state.page) || currentPage().layout || {roll:[.05,.2],mark:[.8,.95],top:0,bottom:1,label:"Custom marks column",max_mark:null,automatic:false});
  layout[state.selection] = [left,right]; layout.top = top; layout.bottom = bottom; layout.automatic = false;
  if (state.selection === "mark") { layout.label = "Custom marks column"; layout.max_mark = null; }
  state.drafts.set(state.page,layout); state.selection = null; renderPage();
});

async function reextract(scope) {
  const page = currentPage();
  if (!page || state.mutating) return;
  const layout = state.drafts.get(state.page) || page.layout;
  if (scope !== "auto" && !layout) { toast("Select the roll and marks columns first.",true); return; }
  const all = scope !== "page";
  if (!await confirmAction(all ? "Re-extract all pages?" : "Re-extract this page?", `This replaces row edits and verification on ${all ? "all pages" : "this page"}. ${scope === "auto" ? "Columns will be detected automatically." : "The selected columns will be used."}`, "Re-extract")) return;
  try {
    const doc = await mutate("reextract", {page:state.page,scope,layout:scope === "auto" ? null : layout},"POST","Results updated from the source.");
    if (doc) { if (all) state.drafts.clear(); else state.drafts.delete(state.page); state.selection = null; renderPage(); }
  } catch (error) { toast(error.message,true); }
}

async function verifyRowById(id) {
  const row = state.doc?.records.find(record => record.id === id);
  if (!row || state.mutating || state.doc?.status !== "ready") return;
  if (row.reviewed) { toast("This row is already reviewed."); return; }
  try { await mutate(`rows/${row.id}`,{roll:row.roll,mark:row.mark,reviewed:true},"PATCH","Reading verified. Any remaining validation issues still need correction."); }
  catch (error) { toast(error.message,true); }
}

function showEdit(id = null) {
  if (state.mutating || state.doc?.status !== "ready") return;
  const row = id ? state.doc.records.find(r => r.id === id) : currentRow();
  state.editNew = id === "new";
  if (!row && !state.editNew) return;
  state.editId = state.editNew ? null : row.id;
  $("editTitle").textContent = state.editNew ? "Add a student row" : `Edit roll ${row.roll || "—"}`;
  $("editOriginal").textContent = state.editNew ? `Add a missing student to page ${state.page}.` : `Original reading: ${row.raw_roll || "(blank)"} → ${row.raw_mark || "(blank)"} · Page ${row.page}`;
  $("editRoll").value = state.editNew ? "" : row.roll;
  $("editMark").value = state.editNew ? "" : row.mark;
  $("deleteRow").hidden = state.editNew;
  $("editError").hidden = true;
  $("editDialog").showModal(); $("editRoll").focus(); $("editRoll").select();
}

$("editForm").addEventListener("submit", async event => {
  event.preventDefault();
  if (state.mutating) return;
  const values = {roll:$("editRoll").value.trim(),mark:$("editMark").value.trim(),reviewed:true};
  try {
    const doc = state.editNew ? await mutate("rows",{...values,page:state.page},"POST","Student row added.") : await mutate(`rows/${state.editId}`,values,"PATCH","Values saved and reading verified.");
    if (doc) { $("editDialog").close(); if (state.editNew) selectRow(doc.records.at(-1).id,true); else selectRow(state.editId); }
  } catch (error) { $("editError").textContent = error.message; $("editError").hidden = false; }
});

$("deleteRow").onclick = async () => {
  if (!await confirmAction("Delete this row?", "It will be removed from the extracted results. Your original document will stay intact.", "Delete row", true)) return;
  try { await mutate(`rows/${state.editId}`,{},"DELETE","Row removed."); $("editDialog").close(); }
  catch (error) { $("editError").textContent = error.message; $("editError").hidden = false; }
};

async function exportFile(format, prepared = false, version = state.doc?.version) {
  if (!state.doc || state.mutating || state.exporting) return;
  if (state.drafts.size) { toast("Apply or discard column selections before exporting.",true); return; }
  if (!prepared) { await ColumnDesigner.open(format); return; }
  if (state.doc.review_count && !await confirmAction("A few rows still need a look", `${state.doc.review_count} rows need review. You can export now; their status and issues will be included in the spreadsheet.`, "Export anyway")) return;
  state.exporting = true; setMutationState();
  const id = state.doc.id, filename = state.doc.filename.replace(/\.[^.]+$/,"") + `.results.${format}`;
  try {
    const response = await fetch(`/api/documents/${id}/export/${format}?version=${version}`);
    if (!response.ok) { const error = await response.json(); throw new Error(error.detail || "Export failed."); }
    const blob = await response.blob(), url = URL.createObjectURL(blob), link = document.createElement("a");
    link.href = url; link.download = filename; document.body.append(link); link.click(); link.remove();
    setTimeout(() => URL.revokeObjectURL(url),30000);
    toast(`${format === "xlsx" ? "Excel workbook" : "CSV"} downloaded. All extracted rows are included.`);
  } catch (error) { toast(error.message || "Could not download the export.",true); }
  finally { state.exporting = false; setMutationState(); }
}

async function deleteDocument() {
  if (!state.doc || !await confirmAction("Delete this document?", "This removes its uploaded copy and saved review from Result Desk. Your original file outside the app will not be changed.","Delete document",true)) return;
  try {
    await api(`/api/documents/${state.doc.id}`,{method:"DELETE"});
    state.drafts.clear(); await refreshLibrary(); await goHome(); toast("Document removed from this workspace.");
  } catch (error) { toast(error.message,true); }
}

$("homeButton").onclick = goHome;
$("libraryButton").onclick = () => { renderLibrary(); $("libraryDialog").showModal(); };
for (const id of ["recentList","libraryList"]) $(id).onclick = event => {
  const button = event.target.closest("[data-document]");
  if (button) { if ($("libraryDialog").open) $("libraryDialog").close(); openDocument(button.dataset.document); }
};
$("helpButton").onclick = () => $("helpDialog").showModal();
for (const id of ["newDocument","sidebarNew","retryUpload"]) $(id).onclick = () => $("uploadDialog").showModal();
for (const id of ["chooseFile","dialogChooseFile"]) $(id).onclick = () => $("fileInput").click();
$("fileInput").onchange = event => { const file = event.target.files[0]; event.target.value = ""; importFile(file); };
$("forceUpload").onclick = () => { $("forceOCR").checked = true; $("moreMenu").hidden = true; $("uploadDialog").showModal(); };
$("moreButton").onclick = () => { $("moreMenu").hidden = !$("moreMenu").hidden; $("moreButton").setAttribute("aria-expanded",!$("moreMenu").hidden); };
document.addEventListener("click",event => { if (!event.target.closest(".menu-container")) { $("moreMenu").hidden = true; $("moreButton").setAttribute("aria-expanded","false"); } });
$("exportExcel").onclick = () => exportFile("xlsx");
$("chooseColumns").onclick = () => ColumnDesigner.open("xlsx");
$("exportCSV").onclick = () => { $("moreMenu").hidden = true; exportFile("csv"); };
$("deleteDocument").onclick = () => { $("moreMenu").hidden = true; deleteDocument(); };
$("removeFailed").onclick = deleteDocument;
$("cancelJob").onclick = async () => { try { applyDocument(await api(`/api/documents/${state.doc.id}/cancel`,{method:"POST"})); } catch(error) { toast(error.message,true); } };
$("prevPage").onclick = () => setPage(state.page-1);
$("nextPage").onclick = () => setPage(state.page+1);
$("pageSelect").onchange = event => setPage(Number(event.target.value));
$("zoomButton").onclick = () => { state.zoom = !state.zoom; resizePreview(); };
$("selectRoll").onclick = () => { state.selection = state.selection === "roll" ? null : "roll"; renderPage(); };
$("selectMark").onclick = () => { state.selection = state.selection === "mark" ? null : "mark"; renderPage(); };
$("discardSelection").onclick = () => { state.drafts.delete(state.page); state.selection = null; renderPage(); };
$("applyPage").onclick = () => reextract("page");
$("applyAll").onclick = () => reextract("all");
$("resetColumns").onclick = () => reextract("auto");
$("pageImage").onload = () => { resizePreview(); drawCrop(); };
$("pageImage").onerror = () => toast("Could not load the source page. Check that the local backend is running.",true);
new ResizeObserver(resizePreview).observe($("pageViewport"));
$("filterAll").onclick = () => { state.filter = "all"; renderRows(); };
for (const id of ["filterReview","reviewShortcut"]) $(id).onclick = () => { state.filter = "review"; renderRows(); };
$("filterConfidence").onclick = () => { state.filter = "confidence"; renderRows(); };
$("sortRows").onchange = event => { state.sort = event.target.value; renderRows(); };
$("markCandidateSelect").onchange = event => {
  const page = currentPage();
  const candidate = (page?.mark_candidates || []).find(item => item.id === event.target.value);
  if (!candidate) return;
  const layout = clone(state.drafts.get(state.page) || page.layout || {roll:[.05,.2],mark:[.8,.95],top:0,bottom:1,label:"Custom marks column",max_mark:null,automatic:false});
  layout.mark = [candidate.left, candidate.right];
  layout.top = candidate.top; layout.bottom = candidate.bottom;
  layout.label = candidate.label; layout.max_mark = candidate.max_mark; layout.automatic = false;
  state.drafts.set(state.page, layout); state.selection = null;
  renderPage(); setMutationState();
  toast(`Marks column set to ${candidate.label}. Re-extract this page or apply it to all pages.`);
};
$("searchInput").oninput = event => { state.query = event.target.value.trim(); renderRows(); };
$("tableBody").onclick = event => {
  const verify = event.target.closest("[data-verify]"), edit = event.target.closest("[data-edit]"), row = event.target.closest("[data-row]");
  if (row) selectRow(row.dataset.row);
  if (verify) verifyRowById(verify.dataset.verify);
  if (edit) showEdit(edit.dataset.edit);
};
$("tableBody").ondblclick = event => { const row = event.target.closest("[data-row]"); if (row) showEdit(row.dataset.row); };
$("tableBody").onkeydown = event => {
  const row = event.target.closest("[data-row]");
  if (row && event.key === "Enter" && !event.target.closest("button, input, select, a")) {
    event.preventDefault();
    if (state.selected !== row.dataset.row) selectRow(row.dataset.row);
    verifyRowById(row.dataset.row);
  }
};
$("editRow").onclick = () => showEdit();
$("addRow").onclick = () => showEdit("new");
$("closeEdit").onclick = () => $("editDialog").close();
$("verifyRow").onclick = () => { const row = currentRow(); if (row) verifyRowById(row.id); };
$("settingsForm").onsubmit = async event => {
  event.preventDefault();
  const input = $("maxMark").value;
  const codes = $("absentCodes").value.split(",").map(code => code.trim()).filter(Boolean);
  try { await mutate("settings",{max_mark:input === "" ? null : Number(input),absent_codes:codes,allow_fractions:$("allowFractions").checked},"PATCH","Validation settings saved."); }
  catch(error) { toast(error.message,true); }
};

window.addEventListener("dragover",event => { if (event.dataTransfer.types.includes("Files")) { event.preventDefault(); document.body.classList.add("is-dragging"); } });
window.addEventListener("dragleave",event => { if (!event.relatedTarget) document.body.classList.remove("is-dragging"); });
window.addEventListener("drop",event => { event.preventDefault(); document.body.classList.remove("is-dragging"); if (event.dataTransfer.files.length) importFile(event.dataTransfer.files[0]); });
document.addEventListener("keydown",event => {
  if (document.querySelector("dialog[open]")) return;
  const typing = event.target.matches("input,textarea,select,[contenteditable]");
  if (event.key === "Escape") { state.selection = null; state.drag = null; $("moreMenu").hidden = true; renderPage(); }
  if (event.key === "/" && !typing && state.doc?.status === "ready") { event.preventDefault(); $("searchInput").focus(); }
  const position = {ArrowDown:"next",ArrowUp:"previous",Home:"first",End:"last"}[event.key];
  if (position && !typing && !event.ctrlKey && !event.metaKey && !event.altKey && !event.shiftKey && state.doc?.status === "ready") {
    event.preventDefault();
    moveSelection(position);
  }
  if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "e" && state.doc?.status === "ready") { event.preventDefault(); exportFile("xlsx"); }
  if (event.key.toLowerCase() === "r" && !typing && !event.ctrlKey && !event.metaKey && !event.altKey && state.doc?.status === "ready") {
    const row = currentRow();
    if (row && !row.reviewed) { event.preventDefault(); verifyRowById(row.id); }
  }
});

async function initialize() {
  try {
    const health = await api("/api/health");
    state.lowConfidence = Number(health.low_confidence_threshold) || .7;
    await refreshLibrary();
    const examples = await api("/api/examples");
    $("examplesSection").hidden = !examples.length;
    $("exampleList").innerHTML = examples.map(example => `<button class="example-card" data-example="${example.id}"><span class="example-icon">${icon("file")}</span><span class="example-copy"><strong>${escapeHTML(example.title)}</strong><small>${escapeHTML(example.description)}</small></span><span>${icon("arrow-up-right")}</span></button>`).join("");
    $("exampleList").onclick = async event => {
      const button = event.target.closest("[data-example]");
      if (!button || !await canLeave()) return;
      button.disabled = true;
      try { const doc = await api(`/api/examples/${button.dataset.example}`,{method:"POST"}); await refreshLibrary(); await openDocument(doc.id,false); }
      catch(error) { toast(error.message,true); }
      finally { button.disabled = false; }
    };
    const saved = localStorage.getItem("result-desk-document");
    if (saved && state.documents.some(doc => doc.id === saved)) await openDocument(saved,false);
    else if (state.documents.length) await openDocument(state.documents[0].id,false);
  } catch(error) { toast(error.message,true); }
}
initialize();
