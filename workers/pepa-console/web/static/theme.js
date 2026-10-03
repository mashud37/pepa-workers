const THEME_KEY = "pepa-theme";
const THEME_CHOICES = ["system", "light", "dark"];
const systemDark = window.matchMedia("(prefers-color-scheme: dark)");

function savedTheme() {
  let choice = "system";
  try {
    choice = localStorage.getItem(THEME_KEY) || "system";
  } catch (error) {
    return "system";
  }
  return THEME_CHOICES.includes(choice) ? choice : "system";
}

function applyTheme(choice) {
  const dark = choice === "dark" || (choice === "system" && systemDark.matches);
  document.documentElement.dataset.theme = dark ? "dark" : "light";
  document.documentElement.dataset.themeChoice = choice;
}

function saveTheme(choice) {
  try {
    localStorage.setItem(THEME_KEY, choice);
  } catch (error) {
    return;
  }
}

applyTheme(savedTheme());
systemDark.addEventListener("change", function () {
  applyTheme(savedTheme());
});
