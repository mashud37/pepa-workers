(function () {
  const KEY = "pepa-reader-theme";
  const root = document.documentElement;

  function apply(theme) {
    if (theme === "light" || theme === "dark") {
      root.dataset.theme = theme;
    } else {
      delete root.dataset.theme;
    }
  }

  apply(localStorage.getItem(KEY));

  document.addEventListener("DOMContentLoaded", () => {
    const btn = document.getElementById("theme-toggle");
    if (!btn) return;
    btn.addEventListener("click", () => {
      const current = root.dataset.theme
        || (matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light");
      const next = current === "dark" ? "light" : "dark";
      apply(next);
      localStorage.setItem(KEY, next);
    });
  });
})();
