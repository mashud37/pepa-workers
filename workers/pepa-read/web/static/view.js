document.getElementById("back-btn").addEventListener("click", () => {
  if (document.referrer && document.referrer.includes(location.host)) {
    history.back();
  } else {
    location.href = "/";
  }
});
document.querySelectorAll(".open-btn").forEach((btn) => {
  btn.addEventListener("click", async () => {
    const status = document.getElementById("open-status");
    status.textContent = " opening...";
    const res = await fetch(`/open/${btn.dataset.id}?which=${btn.dataset.which}`, {method: "POST"});
    const data = await res.json();
    status.textContent = data.ok ? " opened" : ` failed: ${data.error}`;
  });
});
