// The highlighted tab slides for longer the further it travels, so a long jump does not look like a teleport.
const TAB_KEY = "pepa-tab";
const SLIDE_SECONDS = 0.2;
const SECONDS_PER_TAB = 0.07;
const LONGEST_SLIDE = 0.55;

function currentTabIndex() {
  const tabs = Array.from(document.querySelectorAll(".tabs a"));
  return tabs.findIndex(function (tab) {
    return tab.getAttribute("aria-current") === "page";
  });
}

window.addEventListener("pageswap", function () {
  try {
    sessionStorage.setItem(TAB_KEY, String(currentTabIndex()));
  } catch (error) {
    return;
  }
});

window.addEventListener("pagereveal", function () {
  let before = -1;
  try {
    before = Number(sessionStorage.getItem(TAB_KEY) || -1);
  } catch (error) {
    return;
  }
  const now = currentTabIndex();
  if (before < 0 || now < 0) {
    return;
  }
  const seconds = Math.min(LONGEST_SLIDE, SLIDE_SECONDS + SECONDS_PER_TAB * Math.abs(now - before));
  document.documentElement.style.setProperty("--tab-slide", `${seconds}s`);
});
