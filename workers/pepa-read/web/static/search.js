const input = document.getElementById("q");
const tbody = document.querySelector("#results tbody");
const status = document.getElementById("status");
const pager = document.getElementById("pager");
const LIMIT = 20;
let timer = null;
let state = { q: "", offset: 0 };

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
  state = { q, offset };
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

function _fileActions(id, which, label) {
  return `
    <a href="/view/${id}?which=${which}" title="Read ${label} inside pepa-reader">Preview</a>
    <button class="open-btn" data-id="${id}" data-which="${which}"
            title="Launch ${label} in its default Windows app">Open</button>
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

(function initFromUrl() {
  const params = new URLSearchParams(location.search);
  const q = params.get("q") || "";
  const offset = parseInt(params.get("offset") || "0", 10);
  if (q) {
    input.value = q;
    runSearch(q, offset);
  }
})();
