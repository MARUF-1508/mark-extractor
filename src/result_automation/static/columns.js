"use strict";

// A local draft keeps heading/order/cell changes together until Save or Export.
// Preview requests read cached source words; they do not rerun OCR or save edits.
const ColumnDesigner = (() => {
  let design = null;
  let generation = 0;
  let timer;
  const q = id => document.getElementById(id);
  const palette = ["#548763", "#c39a51", "#678fba", "#a584b9", "#4a9b96", "#bd7e70"];
  const color = id => id === "roll" ? palette[0] : id === "marks" ? palette[1] : palette[[...id].reduce((n,c) => n + c.charCodeAt(0),0) % palette.length];
  const grip = '<svg viewBox="0 0 20 20" fill="currentColor" aria-hidden="true"><circle cx="7" cy="5" r="1.3"/><circle cx="13" cy="5" r="1.3"/><circle cx="7" cy="10" r="1.3"/><circle cx="13" cy="10" r="1.3"/><circle cx="7" cy="15" r="1.3"/><circle cx="13" cy="15" r="1.3"/></svg>';

  function error(message = "") {
    if (design) design.error = message;
    q("designerError").textContent = message;
    q("designerError").hidden = !message;
  }

  function validation() {
    if (!design?.columns.length) return "Select at least one column to export.";
    if (design.columns.length > 32) return "Select up to 32 columns.";
    const names = design.columns.map(column => column.name.trim().toLocaleLowerCase());
    if (names.some(name => !name)) return "Give every column a heading.";
    if (new Set(names).size !== names.length) return "Give each column a different heading.";
    return "";
  }

  function controls() {
    if (!design) return;
    const invalid = validation();
    const busy = design.loading || design.saving;
    q("saveExportLayout").disabled = !!invalid || busy || !design.dirty;
    q("exportDesigned").disabled = !!invalid || busy;
    q("closeDesigner").disabled = !!design.saving;
    q("drawColumn").disabled = !!design.saving || design.columns.length >= 32;
    q("designerCount").textContent = `${design.columns.length} ${design.columns.length === 1 ? "column" : "columns"} · ${state.doc.row_count} rows`;
    q("designerStatus").textContent = design.saving ? "Saving your layout…" : design.loading ? "Reading the selected source cells…" : design.dirty ? "Preview your changes before exporting" : "Layout saved on this computer";
    q("designerStatusDetail").textContent = invalid || "Drag column handles or use the arrows. Cell values are editable.";
    q("designerStatusDetail").classList.toggle("invalid", !!invalid);
  }

  function touched() {
    if (!design) return;
    design.dirty = true; design.touched = true; error(); controls();
  }

  function payload() {
    const ids = new Set(design.columns.map(c => c.id));
    const overrides = {};
    for (const [row, cells] of Object.entries(design.overrides)) {
      const selected = Object.fromEntries(Object.entries(cells).filter(([id]) => ids.has(id)));
      if (Object.keys(selected).length) overrides[row] = selected;
    }
    return {version:design.version, columns:design.columns.map(c => ({...c,name:c.name.trim()})), overrides};
  }

  async function refreshPreview() {
    clearTimeout(timer);
    if (!design) return;
    const current = design, sequence = ++current.sequence;
    if (validation()) { current.loading = false; renderTable(); controls(); return; }
    current.loading = true; controls();
    try {
      const preview = await api(`/api/documents/${current.id}/columns/preview`, {
        method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(payload()),
      });
      if (design !== current || sequence !== current.sequence) return;
      current.rows = preview.rows;
      error(); renderTable();
    } catch (err) {
      if (design === current && sequence === current.sequence) error(err.status === 409 ? "This review changed in another tab. Close this preview and reopen it to load the latest version." : err.message);
    } finally {
      if (design === current && sequence === current.sequence) { current.loading = false; renderTable(); controls(); }
    }
  }

  function queuePreview() {
    clearTimeout(timer);
    if (!design) return;
    design.sequence++; design.loading = true; controls();
    timer = setTimeout(refreshPreview,150);
  }

  function renderChoices() {
    if (!design) return;
    const chosen = new Set(design.columns.map(c => c.id));
    q("availableColumns").innerHTML = [...design.catalog.values()].map(column => `<label class="column-option"><input type="checkbox" data-column-choice="${column.id}" ${chosen.has(column.id) ? "checked" : ""} ${design.saving ? "disabled" : ""}><span class="column-color" style="background:${color(column.id)}"></span><span><strong>${escapeHTML(column.name)}</strong><small>${column.kind === "number" ? "Number" : "Text / identifier"}${column.id.startsWith("custom-") ? " · Custom region" : ""}</small></span></label>`).join("");
  }

  function renderTable() {
    if (!design) return;
    const focused = document.activeElement;
    const focusName = focused?.dataset.columnName;
    const caret = focusName ? [focused.selectionStart,focused.selectionEnd] : null;
    const columns = design.columns;
    q("designerEmpty").hidden = columns.length > 0;
    q("designerTable").hidden = !columns.length;
    q("designerTable").style.minWidth = `${Math.max(400, 46 + columns.length * 185)}px`;
    q("designerTableHead").innerHTML = '<tr><th class="preview-row-number" scope="col">#</th>' + columns.map((column,index) => `<th scope="col" data-preview-column="${column.id}" style="--column-color:${color(column.id)}"><div class="preview-heading-tools"><button class="column-grip" draggable="true" data-drag-column="${column.id}" aria-label="Drag ${escapeHTML(column.name)} to reorder" title="Drag to move column">${grip}</button><span class="column-position">${index+1}</span><div><button class="column-arrow" data-move="${column.id}" data-direction="-1" ${index === 0 ? "disabled" : ""} aria-label="Move ${escapeHTML(column.name)} left">${icon("chevron-left")}</button><button class="column-arrow" data-move="${column.id}" data-direction="1" ${index === columns.length-1 ? "disabled" : ""} aria-label="Move ${escapeHTML(column.name)} right">${icon("chevron-right")}</button><button class="column-arrow" data-remove-column="${column.id}" aria-label="Remove ${escapeHTML(column.name)} from export">${icon("close")}</button></div></div><input class="preview-heading-input" data-column-name="${column.id}" maxlength="80" value="${escapeHTML(column.name)}" aria-label="Heading for column ${index+1}" title="Rename this column"><select data-column-kind="${column.id}" aria-label="Cell format for column ${index+1}"><option value="text" ${column.kind === "text" ? "selected" : ""}>Text / identifier</option><option value="number" ${column.kind === "number" ? "selected" : ""}>Number</option></select></th>`).join("") + "</tr>";
    q("designerTableBody").innerHTML = design.rows.map((row,index) => `<tr><th class="preview-row-number" scope="row" title="Source page ${row.page}">${index+1}<small>p${row.page}</small></th>` + columns.map(column => {
      const value = design.overrides[row.id]?.[column.id] ?? row.values[column.id] ?? "";
      const original = row.original[column.id] ?? "";
      return `<td><input class="preview-cell${value !== original ? " edited" : ""}" data-preview-row="${row.id}" data-preview-cell="${column.id}" value="${escapeHTML(value)}" maxlength="4096" ${design.loading || design.saving ? "disabled" : ""} aria-label="Row ${index+1}, ${escapeHTML(column.name)}" title="Page ${row.page} · Original: ${escapeHTML(original || "(blank)")}" placeholder="—"></td>`;
    }).join("") + "</tr>").join("");
    if (focusName) {
      const input = q("designerTableHead").querySelector(`[data-column-name="${CSS.escape(focusName)}"]`);
      if (input) {input.focus({preventScroll:true});input.setSelectionRange(...caret);}
    }
    controls();
  }

  function needsSourceValues() {
    return !!design && design.rows.some(row => design.columns.some(column => !(column.id in row.values)));
  }

  function moveColumn(id, directionOrTarget) {
    if (!design || design.saving) return;
    const start = design.columns.findIndex(c => c.id === id);
    const target = typeof directionOrTarget === "number" ? start + directionOrTarget : design.columns.findIndex(c => c.id === directionOrTarget);
    if (start < 0 || target < 0 || target >= design.columns.length || start === target) return;
    const [column] = design.columns.splice(start,1);
    design.columns.splice(target,0,column);
    touched(); renderTable(); renderSource();
  }

  function resizeSource() {
    if (!design || !q("columnDesigner").open) return;
    const page = state.doc.pages[design.page-1];
    const viewport = q("designerViewport");
    const width = Math.max(100,viewport.clientWidth-24), height = Math.max(100,viewport.clientHeight-24);
    q("designerSheet").style.width = Math.floor(design.zoom ? width : Math.min(width,height*page.width/page.height)) + "px";
  }

  function drawBox(box, fill, dashed=false) {
    return `<rect x="${box[0]*1000}" y="${box[1]*1000}" width="${(box[2]-box[0])*1000}" height="${(box[3]-box[1])*1000}" fill="${fill}" fill-opacity=".06" stroke="${fill}" stroke-width="1.5" vector-effect="non-scaling-stroke" ${dashed ? 'stroke-dasharray="5 3"' : ""}/>`;
  }

  function renderSource() {
    if (!design) return;
    const page = state.doc.pages[design.page-1], image = q("designerImage");
    q("designerPage").value = design.page;
    if (image.dataset.url !== page.image_url) { image.dataset.url = page.image_url; image.src = page.image_url; }
    image.alt = `Source page ${page.number} for selecting export columns`;
    q("drawColumn").classList.toggle("drawing",design.drawing);
    q("designerSheet").classList.toggle("drawing",design.drawing);
    q("designerHint").textContent = design.drawing ? "Drag around one source column’s student cells. Exclude the header." : "Select detected columns below, or draw a new region on the page.";
    let markup = design.columns.map(column => column.regions[String(design.page)] ? drawBox(column.regions[String(design.page)],color(column.id)) : "").join("");
    if (design.drag) {
      const {start,end} = design.drag;
      markup += drawBox([Math.min(start.x,end.x),Math.min(start.y,end.y),Math.max(start.x,end.x),Math.max(start.y,end.y)],"#678fba",true);
    } else if (design.pending) markup += drawBox(design.pending,"#678fba",true);
    q("designerOverlay").innerHTML = markup;
    resizeSource();
  }

  async function open(format="xlsx") {
    if (state.doc?.status !== "ready" || state.mutating) return;
    if (state.drafts.size) { toast("Apply or discard the pending source-column selections first.",true); return; }
    if (q("columnDesigner").open) return;
    const token = ++generation;
    design = {id:state.doc.id,version:state.doc.version,columns:[],catalog:new Map(),rows:[],overrides:{},page:state.page,
      format,zoom:false,drawing:false,drag:null,pending:null,loading:true,saving:false,dirty:false,touched:false,sequence:0,error:""};
    q("designerPage").innerHTML = state.doc.pages.map(p => `<option value="${p.number}">Page ${p.number} of ${state.doc.page_count}</option>`).join("");
    q("exportDesigned").innerHTML = icon("download") + (format === "xlsx" ? "Export Excel" : "Export CSV");
    q("availableColumns").innerHTML = '<p class="designer-loading">Finding source columns…</p>';
    q("designerTableHead").innerHTML = ""; q("designerTableBody").innerHTML = "";
    q("designerTable").hidden = true; q("designerEmpty").hidden = false;
    error(); q("columnDesigner").showModal(); renderSource(); controls();
    try {
      const result = await api(`/api/documents/${design.id}/columns`);
      if (token !== generation || !design) return;
      design.version = result.version;
      design.columns = clone(result.preview.columns);
      design.catalog = new Map(result.candidates.map(c => [c.id,clone(c)]));
      for (const c of design.columns) design.catalog.set(c.id,clone(c));
      design.rows = result.preview.rows; design.overrides = clone(result.overrides);
      design.loading = false; design.dirty = !state.doc.export_columns;
      renderChoices(); renderTable(); renderSource(); controls();
    } catch (err) {
      if (token === generation && design) { design.loading = false; error(err.message); controls(); }
    }
  }

  async function close() {
    if (!design || design.saving) return;
    if (design.touched && !await confirmAction("Discard preview changes?","Your saved review stays intact. Unsaved column headings, order, and cell edits will be discarded.","Discard changes")) return;
    clearTimeout(timer); generation++; design = null; q("columnDesigner").close();
  }

  async function save(andExport = false) {
    if (!design || design.loading || design.saving || validation()) return;
    const current = design;
    if (!current.dirty && andExport) {
      q("columnDesigner").close(); design = null; generation++;
      await exportFile(current.format,true,current.version);
      return;
    }
    current.saving = true; state.mutating = true; setMutationState(); controls(); renderChoices();
    try {
      const doc = await api(`/api/documents/${current.id}/columns`,{method:"PUT",headers:{"Content-Type":"application/json"},body:JSON.stringify(payload())});
      applyDocument(doc);
      current.columns = clone(doc.export_columns);
      current.version = doc.version; current.dirty = false; current.touched = false;
      if (andExport) { q("columnDesigner").close(); design = null; generation++; }
      else { error(); toast("Column names, order, and preview edits saved."); }
    } catch (err) { error(err.status === 409 ? "This review changed in another tab. Close and reopen the preview before saving." : err.message); }
    finally {
      current.saving = false; state.mutating = false; setMutationState();
      if (design === current) { controls(); renderChoices(); renderTable(); }
    }
    if (andExport && design === null) await exportFile(current.format,true,current.version);
  }

  q("closeDesigner").onclick = close;
  q("columnDesigner").addEventListener("cancel",event => {event.preventDefault();close();});
  q("saveExportLayout").onclick = () => save(false);
  q("exportDesigned").onclick = () => save(true);
  q("availableColumns").addEventListener("change",event => {
    const id = event.target.dataset.columnChoice;
    if (!design || !id) return;
    if (event.target.checked) design.columns.push(clone(design.catalog.get(id)));
    else design.columns = design.columns.filter(c => c.id !== id);
    touched(); renderTable(); renderSource(); queuePreview();
  });
  q("selectAllColumns").onclick = () => {
    if (!design || design.saving) return;
    for (const c of design.catalog.values()) if (!design.columns.some(selected => selected.id === c.id) && design.columns.length < 32) design.columns.push(clone(c));
    touched(); renderChoices(); renderTable(); renderSource(); queuePreview();
  };
  q("resetExportColumns").onclick = () => {
    if (!design || design.saving) return;
    design.columns = ["roll","marks"].map(id => clone(design.catalog.get(id))).filter(Boolean);
    touched(); renderChoices(); renderTable(); renderSource(); queuePreview();
  };
  q("designerTableHead").addEventListener("input",event => {
    const id = event.target.dataset.columnName;
    if (!design || !id) return;
    const column = design.columns.find(c => c.id === id);
    column.name = event.target.value; design.catalog.set(id,clone(column));
    touched(); renderChoices();
    if (!validation() && needsSourceValues()) queuePreview();
  });
  q("designerTableHead").addEventListener("change",event => {
    const heading = event.target.dataset.columnName;
    if (design && heading) {
      const column = design.columns.find(c => c.id === heading);
      column.name = column.name.trim(); event.target.value = column.name;
      // Keep the checkbox DOM stable while focus moves from a heading to it.
      design.catalog.set(heading,clone(column));controls();
      return;
    }
    const id = event.target.dataset.columnKind;
    if (!design || !id) return;
    const column = design.columns.find(c => c.id === id);
    column.kind = event.target.value; design.catalog.set(id,clone(column));
    touched(); renderChoices(); queuePreview();
  });
  q("designerTableHead").addEventListener("click",event => {
    const move = event.target.closest("[data-move]"), remove = event.target.closest("[data-remove-column]");
    if (move) moveColumn(move.dataset.move,Number(move.dataset.direction));
    if (remove && design && !design.saving) {
      design.columns = design.columns.filter(c => c.id !== remove.dataset.removeColumn);
      touched(); renderChoices(); renderTable(); renderSource();
      if (!validation() && needsSourceValues()) queuePreview();
    }
  });
  q("designerTableBody").addEventListener("input",event => {
    const id = event.target.dataset.previewCell, row = event.target.dataset.previewRow;
    if (!design || !id || !row) return;
    (design.overrides[row] ||= {})[id] = event.target.value;
    const original = design.rows.find(r => r.id === row)?.original[id] ?? "";
    event.target.classList.toggle("edited",event.target.value !== original);
    touched();
  });
  q("designerTableBody").addEventListener("change",event => {
    const id = event.target.dataset.previewCell, row = event.target.dataset.previewRow;
    if (!design || !id || !row) return;
    event.target.value = event.target.value.trim();
    (design.overrides[row] ||= {})[id] = event.target.value;
  });
  q("designerTableHead").addEventListener("dragstart",event => {
    const handle = event.target.closest("[data-drag-column]");
    if (!design || !handle || design.saving) return;
    design.dragColumn = handle.dataset.dragColumn;
    event.dataTransfer.setData("text/plain",design.dragColumn); event.dataTransfer.effectAllowed = "move";
  });
  q("designerTableHead").addEventListener("dragover",event => {
    if (!design?.dragColumn) return;
    event.preventDefault(); event.dataTransfer.dropEffect = "move";
    q("designerTableHead").querySelectorAll(".column-drop-target").forEach(el => el.classList.remove("column-drop-target"));
    event.target.closest("[data-preview-column]")?.classList.add("column-drop-target");
  });
  q("designerTableHead").addEventListener("drop",event => {
    if (!design?.dragColumn) return;
    event.preventDefault(); event.stopPropagation();
    const target = event.target.closest("[data-preview-column]");
    if (target) moveColumn(design.dragColumn,target.dataset.previewColumn);
    design.dragColumn = null;
  });
  q("designerTableHead").addEventListener("dragend",() => {
    if (design) design.dragColumn = null;
    q("designerTableHead").querySelectorAll(".column-drop-target").forEach(el => el.classList.remove("column-drop-target"));
  });
  q("designerPage").onchange = event => { if (design) {design.page = Number(event.target.value);renderSource();} };
  q("designerZoom").onclick = () => {if (design) {design.zoom = !design.zoom;resizeSource();}};
  q("designerImage").onload = resizeSource;
  new ResizeObserver(resizeSource).observe(q("designerViewport"));
  q("drawColumn").onclick = () => {if (design) {design.drawing = !design.drawing;design.drag = null;renderSource();}};

  function point(event) {
    const box = q("designerOverlay").getBoundingClientRect();
    return {x:Math.max(0,Math.min(1,(event.clientX-box.left)/box.width)),y:Math.max(0,Math.min(1,(event.clientY-box.top)/box.height))};
  }
  q("designerOverlay").addEventListener("pointerdown",event => {
    if (!design?.drawing || design.saving) return;
    event.preventDefault(); event.currentTarget.setPointerCapture(event.pointerId);
    design.drag = {start:point(event),end:point(event)};renderSource();
  });
  q("designerOverlay").addEventListener("pointermove",event => {if (design?.drag) {design.drag.end = point(event);renderSource();}});
  q("designerOverlay").addEventListener("pointercancel",() => {if (design) {design.drag = null;renderSource();}});
  q("designerOverlay").addEventListener("pointerup",event => {
    if (!design?.drag) return;
    const start = design.drag.start, end = point(event);
    design.drag = null;
    const box = [Math.min(start.x,end.x),Math.min(start.y,end.y),Math.max(start.x,end.x),Math.max(start.y,end.y)];
    if (box[2]-box[0] < .006 || box[3]-box[1] < .01) {renderSource();return;}
    design.pending = box; design.drawing = false; renderSource();
    q("newColumnName").value = `Column ${design.catalog.size+1}`;q("newColumnKind").value = "number";q("columnAllPages").checked = true;
    q("newColumnDialog").showModal();q("newColumnName").focus();q("newColumnName").select();
  });
  function cancelNew() {q("newColumnDialog").close();if (design) {design.pending = null;renderSource();}}
  q("cancelNewColumn").onclick = cancelNew;
  q("newColumnDialog").addEventListener("cancel",event => {event.preventDefault();cancelNew();});
  q("newColumnForm").onsubmit = event => {
    event.preventDefault();
    if (!design?.pending) return;
    const name = q("newColumnName").value.trim();
    if (!name) return;
    const selected = design.pending, regions = {[String(design.page)]:selected};
    if (q("columnAllPages").checked) for (const page of state.doc.pages) {
      if (page.number !== design.page) regions[String(page.number)] = [selected[0],page.layout?.top ?? selected[1],selected[2],page.layout?.bottom ?? selected[3]];
    }
    const column = {id:"custom-"+crypto.randomUUID().replaceAll("-",""),name,kind:q("newColumnKind").value,source:"region",regions};
    design.catalog.set(column.id,clone(column));design.columns.push(column);design.pending = null;
    q("newColumnDialog").close();touched();renderChoices();renderTable();renderSource();queuePreview();
  };
  return {open};
})();
