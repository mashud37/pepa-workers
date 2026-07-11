const input = document.getElementById("q");
const tbody = document.querySelector("#results tbody");
const status = document.getElementById("status");
let timer = null;

input.addEventListener("input", () => {
  clearTimeout(timer);
  timer = setTimeout(runSearch, 200);
});

function escapeHtml(s) {
  return (s || "").replace(/[&<>"']/g, c => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  }[c]));
}

async function runSearch() {
  const q = input.value.trim();
  if (!q) {
    tbody.innerHTML = "";
    status.textContent = "";
    return;
  }
  status.textContent = "Searching...";
  let data;
  try {
    const res = await fetch(`/api/search?q=${encodeURIComponent(q)}`);
    data = await res.json();
  } catch (err) {
    status.textContent = `Error: ${err}`;
    return;
  }
  if (data.error) {
    status.textContent = `Error: ${data.error}`;
    tbody.innerHTML = "";
    return;
  }
  renderResults(data);
}

function renderResults(rows) {
  tbody.innerHTML = "";
  status.textContent = `${rows.length} result${rows.length === 1 ? "" : "s"}`;
  for (const r of rows) {
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td><a href="/view/${r.id}" target="_blank">${escapeHtml(r.title) || "(untitled)"}</a></td>
      <td>${escapeHtml(r.authors_raw)}</td>
      <td>${r.has_text ? "yes" : ""}</td>
      <td>${r.has_sum ? "yes" : ""}</td>
      <td><a href="/view/${r.id}" target="_blank">View</a></td>
      <td><button class="open-btn" data-id="${r.id}">Open</button></td>
    `;
    tbody.appendChild(tr);
  }
  tbody.querySelectorAll(".open-btn").forEach(btn => {
    btn.addEventListener("click", async () => {
      const original = btn.textContent;
      btn.textContent = "Opening...";
      btn.disabled = true;
      try {
        const res = await fetch(`/open/${btn.dataset.id}`, { method: "POST" });
        const data = await res.json();
        btn.textContent = data.ok ? "Opened" : "Failed";
      } catch {
        btn.textContent = "Failed";
      }
      setTimeout(() => { btn.textContent = original; btn.disabled = false; }, 1500);
    });
  });
}
