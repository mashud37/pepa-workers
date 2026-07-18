const input = document.getElementById("q");
const tbody = document.querySelector("#results tbody");
const status = document.getElementById("status");
const pager = document.getElementById("pager");
const manageTbody = document.querySelector("#list-manager-table tbody");
const LIMIT = 20;
let timer = null;
let state = { mode: "search", q: "", offset: 0 };
let lastSearch = { q: "", offset: 0 };
let allLists = [];

input.addEventListener("input", () => {
  clearTimeout(timer);
  timer = setTimeout(() => runSearch(input.value.trim(), 0), 200);
});

const helpModal = document.getElementById("help-modal");
document.getElementById("help-btn").addEventListener("click", () => helpModal.showModal());
document.getElementById("help-close").addEventListener("click", () => helpModal.close());
helpModal.addEventListener("click", (e) => {
  if (e.target === helpModal) helpModal.close();
});

function escapeHtml(s) {
  return (s || "").replace(/[&<>"']/g, c => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  }[c]));
}

function syncUrl(q, offset) {
  const params = new URLSearchParams();
  if (q) params.set("q", q);
  if (offset) params.set("offset", offset);
  const qs = params.toString();
  history.replaceState({ q, offset }, "", qs ? `/?${qs}` : "/");
}

async function runSearch(q, offset) {
  state = { mode: "search", q, offset };
  lastSearch = { q, offset };
  syncUrl(q, offset);

  if (!q) {
    tbody.innerHTML = "";
    pager.innerHTML = "";
    status.textContent = "";
    return;
  }
  status.textContent = "Searching...";
  let data;
  try {
    const res = await fetch(`/api/search?q=${encodeURIComponent(q)}&offset=${offset}&limit=${LIMIT}`);
    data = await res.json();
  } catch (err) {
    status.textContent = `Error: ${err}`;
    return;
  }
  if (data.error) {
    status.textContent = `Error: ${data.error}`;
    tbody.innerHTML = "";
    pager.innerHTML = "";
    return;
  }
  renderResults(data.results);
  renderPager(data);
}

async function viewList(listId, listName) {
  state = { mode: "list", listId, listName };
  pager.innerHTML = "";
  status.textContent = "Loading...";
  let data;
  try {
    const res = await fetch(`/api/lists/${listId}/items`);
    data = await res.json();
  } catch (err) {
    status.textContent = `Error: ${err}`;
    return;
  }
  const items = data.items || [];
  renderResults(items);
  const backLink = `<button type="button" id="back-to-search" class="link-btn">&larr; back to search</button>`;
  status.innerHTML = `${items.length} item${items.length === 1 ? "" : "s"} in list "${escapeHtml(listName)}" &nbsp; ${backLink}`;
  document.getElementById("back-to-search").addEventListener("click", () => {
    input.value = lastSearch.q || "";
    runSearch(lastSearch.q || "", lastSearch.offset || 0);
  });
}

function refreshView() {
  if (state.mode === "list") {
    viewList(state.listId, state.listName);
  } else {
    runSearch(state.q, state.offset);
  }
}

function _fileActions(id, which, label) {
  return `
    <a href="/view/${id}?which=${which}" title="Read ${label} inside pepa-reader">Preview</a>
    <button class="open-btn" data-id="${id}" data-which="${which}"
            title="Launch ${label} in its default Windows app">Open</button>
  `;
}

function _listCellHtml(docId, memberIds) {
  const chips = memberIds.map(lid => {
    const l = allLists.find(x => x.id === lid);
    return `<span class="chip">${escapeHtml(l ? l.name : "?")}
      <button class="chip-x" data-list="${lid}" data-doc="${docId}" title="Remove from list">&times;</button></span>`;
  }).join("");
  const options = allLists
    .filter(l => !memberIds.includes(l.id))
    .map(l => `<option value="${l.id}">${escapeHtml(l.name)}</option>`)
    .join("");
  return `
    <span class="chips">${chips}</span>
    <select class="list-select" data-doc="${docId}">
      <option value="" selected disabled>+ add to list</option>
      ${options}
      <option value="__new__">+ New list...</option>
    </select>
  `;
}

function renderResults(rows) {
  tbody.innerHTML = "";
  for (const r of rows) {
    const tr = document.createElement("tr");
    const textActions = r.has_text ? _fileActions(r.id, "text", "the pepa-prep text file") : "";
    const sumActions = r.has_sum ? _fileActions(r.id, "sum", "the pepa-sum summary file") : "";
    tr.innerHTML = `
      <td>${escapeHtml(r.stem)}</td>
      <td>${escapeHtml(r.title) || "(untitled)"}</td>
      <td>${escapeHtml(r.authors_raw)}</td>
      <td><span class="actions">${textActions}</span></td>
      <td><span class="actions">${sumActions}</span></td>
      <td>${_listCellHtml(r.id, r.lists || [])}</td>
    `;
    tbody.appendChild(tr);
  }
  tbody.querySelectorAll(".open-btn").forEach(btn => {
    btn.addEventListener("click", async () => {
      const original = btn.textContent;
      btn.textContent = "Opening...";
      btn.disabled = true;
      try {
        const res = await fetch(`/open/${btn.dataset.id}?which=${btn.dataset.which}`, { method: "POST" });
        const data = await res.json();
        btn.textContent = data.ok ? "Opened" : "Failed";
      } catch {
        btn.textContent = "Failed";
      }
      setTimeout(() => { btn.textContent = original; btn.disabled = false; }, 1500);
    });
  });
  tbody.querySelectorAll(".chip-x").forEach(btn => {
    btn.addEventListener("click", async () => {
      await fetch(`/api/lists/${btn.dataset.list}/items/${btn.dataset.doc}`, { method: "DELETE" });
      await refreshLists();
      refreshView();
    });
  });
  tbody.querySelectorAll(".list-select").forEach(sel => {
    sel.addEventListener("change", () => {
      if (sel.value === "__new__") {
        _promptNewList(sel, sel.dataset.doc);
      } else if (sel.value) {
        _addToList(sel.value, sel.dataset.doc);
      }
    });
  });
}

async function _addToList(listId, docId) {
  await fetch(`/api/lists/${listId}/items/${docId}`, { method: "POST" });
  await refreshLists();
  refreshView();
}

function _promptNewList(select, docId) {
  const box = document.createElement("input");
  box.type = "text";
  box.className = "list-new-input";
  box.placeholder = "List name, Enter to add";
  select.replaceWith(box);
  box.focus();
  let done = false;
  async function commit() {
    if (done) return;
    done = true;
    const name = box.value.trim();
    if (!name) {
      refreshView();
      return;
    }
    const res = await fetch("/api/lists", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name }),
    });
    const data = await res.json();
    if (!data.ok) {
      status.textContent = `Error: ${data.error}`;
      refreshView();
      return;
    }
    await _addToList(data.id, docId);
  }
  box.addEventListener("keydown", (e) => {
    if (e.key === "Enter") commit();
    if (e.key === "Escape") { done = true; refreshView(); }
  });
  box.addEventListener("blur", commit);
}

async function refreshLists() {
  const res = await fetch("/api/lists");
  const data = await res.json();
  allLists = data.lists || [];
  renderListManager();
}

function renderListManager() {
  manageTbody.innerHTML = "";
  for (const l of allLists) {
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td><input type="text" class="list-name-input" data-id="${l.id}" value="${escapeHtml(l.name)}"></td>
      <td>${l.count}</td>
      <td>
        <button class="list-view-btn" data-id="${l.id}" data-name="${escapeHtml(l.name)}">View</button>
        <a href="/list/${l.id}/export">Export</a>
        <button class="list-delete-btn" data-id="${l.id}" data-name="${escapeHtml(l.name)}">Delete</button>
      </td>
    `;
    manageTbody.appendChild(tr);
  }
  manageTbody.querySelectorAll(".list-view-btn").forEach((btn) => {
    btn.addEventListener("click", () => {
      viewList(btn.dataset.id, btn.dataset.name);
      window.scrollTo({ top: 0, behavior: "smooth" });
    });
  });
  manageTbody.querySelectorAll(".list-name-input").forEach((inp) => {
    inp.addEventListener("change", async () => {
      const res = await fetch(`/api/lists/${inp.dataset.id}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name: inp.value.trim() }),
      });
      const data = await res.json();
      if (!data.ok) status.textContent = `Error: ${data.error}`;
      await refreshLists();
      refreshView();
    });
  });
  manageTbody.querySelectorAll(".list-delete-btn").forEach((btn) => {
    btn.addEventListener("click", async () => {
      if (!confirm(`Delete list "${btn.dataset.name}"? This cannot be undone.`)) return;
      await fetch(`/api/lists/${btn.dataset.id}`, { method: "DELETE" });
      await refreshLists();
      refreshView();
    });
  });
}

function renderPager(data) {
  const { total, offset, limit } = data;
  pager.innerHTML = "";
  if (total === 0) {
    status.textContent = "0 results";
    return;
  }
  const from = offset + 1;
  const to = Math.min(offset + limit, total);
  status.textContent = `${total} result${total === 1 ? "" : "s"}`;

  const prev = document.createElement("button");
  prev.textContent = "< Prev";
  prev.disabled = offset <= 0;
  prev.addEventListener("click", () => runSearch(state.q, Math.max(0, offset - limit)));

  const range = document.createElement("span");
  range.textContent = `${from}-${to} of ${total}`;

  const next = document.createElement("button");
  next.textContent = "Next >";
  next.disabled = to >= total;
  next.addEventListener("click", () => runSearch(state.q, offset + limit));

  pager.append(prev, range, next);
}

(async function initFromUrl() {
  await refreshLists();
  const params = new URLSearchParams(location.search);
  const q = params.get("q") || "";
  const offset = parseInt(params.get("offset") || "0", 10);
  if (q) {
    input.value = q;
    runSearch(q, offset);
  }
})();
