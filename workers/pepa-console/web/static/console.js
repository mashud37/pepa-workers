const confirmDialog = document.getElementById("confirm");
const calm = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

const CONFETTI_COLOURS = [
  "#0b57d0",
  "#d93025",
  "#f6b8b3",
  "#1e8e3e",
  "#f9ab00",
];
const CONFETTI_PIECES = 18;

const THEME_NAMES = {
  system: "Theme: follows the system",
  light: "Theme: light",
  dark: "Theme: dark",
};
const ADDRESS_GROUPS = {
  service: "Services",
  computer: "On this computer",
};
const MENU_STEPS = {
  ArrowDown: 1,
  ArrowUp: -1,
};
const openedMenu = {menu: null, anchor: null, pick: null};

const AFTER_SEND = {
  run: showRun,
  stop: function () {},
  answer: clearAnswer,
};

document.addEventListener("submit", function (event) {
  const form = event.target;
  if (form.dataset.confirm && form.dataset.confirmed !== "yes") {
    event.preventDefault();
    askFirst(form);
    return;
  }
  form.dataset.confirmed = "";
  if (form.dataset.fetch) {
    event.preventDefault();
    sendForm(form);
  }
});

document.addEventListener("click", function (event) {
  if (event.target.tagName === "DIALOG") {
    event.target.close();
    return;
  }
  const opener = event.target.closest("[data-open]");
  if (opener) {
    document.getElementById(opener.dataset.open).showModal();
  }
  const closer = event.target.closest("[data-close]");
  if (closer) {
    closer.closest("dialog").close();
  }
  const dismiss = event.target.closest("[data-dismiss]");
  if (dismiss) {
    dismiss.closest(".snackbar").remove();
  }
});

document.addEventListener("change", function (event) {
  if (event.target.matches("[data-autosubmit]")) {
    event.target.form.requestSubmit();
  }
});

for (const panel of document.querySelectorAll(".run")) {
  followRun(panel);
}

const liveRegion = document.querySelector("[data-live]");
if (liveRegion) {
  keepRegionFresh(liveRegion);
}

const pickDialog = document.getElementById("pick");
if (pickDialog) {
  document.addEventListener("click", handlePickClick);
}

if (!calm) {
  for (const count of document.querySelectorAll("[data-count]")) {
    countUp(count);
  }
}

for (const select of document.querySelectorAll("select")) {
  enhanceSelect(select);
}
document.addEventListener("click", handleMenuClick);
document.addEventListener("keydown", handleMenuKeys);
labelThemeButton();


function askFirst(form) {
  document.getElementById("confirm-text").textContent = form.dataset.confirm;
  document.getElementById("confirm-detail").textContent = form.dataset.confirmDetail || "";
  document.getElementById("confirm-button").textContent = form.dataset.confirmButton || "Run";
  confirmDialog.returnValue = "";
  confirmDialog.onclose = function () {
    if (confirmDialog.returnValue === "ok") {
      form.dataset.confirmed = "yes";
      form.requestSubmit();
    }
  };
  confirmDialog.showModal();
}

async function sendForm(form) {
  let data;
  try {
    const response = await fetch(form.action, {
      method: "POST",
      body: new FormData(form),
      headers: {Accept: "application/json"},
    });
    data = await response.json();
  } catch (error) {
    showMessage("The console did not accept that. Reload the page and try again.");
    return;
  }
  if (data.error) {
    showMessage(data.error);
    return;
  }
  AFTER_SEND[form.dataset.fetch](form, data);
}

function showRun(form, data) {
  const slot = document.getElementById(form.dataset.slot);
  slot.innerHTML = data.panel;
  const dialog = form.closest("dialog");
  if (dialog) {
    dialog.close();
  }
  followRun(slot.querySelector(".run"));
}

function clearAnswer(form) {
  form.elements.text.value = "";
  form.hidden = true;
}

function handlePickClick(event) {
  const opener = event.target.closest("[data-pick]");
  if (opener) {
    openPicker(opener);
    return;
  }
  const up = event.target.closest("[data-pick-up]");
  if (up) {
    showFolder(up.dataset.parent || "");
    return;
  }
  const entry = event.target.closest("[data-folder]");
  if (entry) {
    showFolder(entry.dataset.folder);
  }
}

function openPicker(opener) {
  pickDialog.querySelector("[data-pick-app]").value = opener.dataset.app;
  pickDialog.querySelector("[data-pick-slot]").value = opener.dataset.slot;
  pickDialog.querySelector("[data-pick-title]").textContent = opener.dataset.label;
  pickDialog.querySelector("[data-pick-path]").value = opener.dataset.path;
  pickDialog.showModal();
  showFolder(opener.dataset.path);
}

async function showFolder(path) {
  let data;
  try {
    const response = await fetch(pickDialog.dataset.browse + "?path=" + encodeURIComponent(path));
    data = await response.json();
  } catch (error) {
    showMessage("The console did not answer. Reload the page and try again.");
    return;
  }
  pickDialog.querySelector("[data-pick-here]").textContent = data.path || "This computer";
  const up = pickDialog.querySelector("[data-pick-up]");
  up.hidden = data.parent === null;
  up.dataset.parent = data.parent || "";
  if (data.path) {
    pickDialog.querySelector("[data-pick-path]").value = data.path;
  }
  showFolderList(data.folders);
  pickDialog.querySelector("[data-pick-note]").textContent = pickNote(data);
}

function showFolderList(folders) {
  const list = pickDialog.querySelector("[data-pick-list]");
  list.replaceChildren();
  for (const folder of folders) {
    const button = document.createElement("button");
    button.type = "button";
    button.dataset.folder = folder.path;
    button.textContent = folder.name;
    const item = document.createElement("li");
    item.append(button);
    list.append(item);
  }
}

function pickNote(data) {
  if (data.message) {
    return data.message;
  }
  if (data.folders.length === 0) {
    return "Nothing inside this one. Use it as it is, or go back up.";
  }
  return "";
}

function showMessage(text) {
  const old = document.querySelector(".snackbar");
  if (old) {
    old.remove();
  }
  const bar = document.createElement("div");
  bar.className = "snackbar";
  bar.setAttribute("role", "status");
  bar.textContent = text;
  document.body.append(bar);
}

function wait(milliseconds) {
  return new Promise(function (resolve) {
    setTimeout(resolve, milliseconds);
  });
}

async function followRun(panel) {
  const log = panel.querySelector("[data-lines]");
  const pending = panel.querySelector("[data-pending]");
  let next = 0;
  while (panel.isConnected) {
    let data;
    try {
      const response = await fetch(panel.dataset.log + "?after=" + next);
      data = await response.json();
    } catch (error) {
      const status = panel.querySelector("[data-status]");
      status.textContent = "Console stopped";
      status.className = "status status-failed";
      return;
    }

    const atBottom = log.scrollTop + log.clientHeight >= log.scrollHeight - 40;
    if (data.lines.length > 0) {
      const chunk = document.createElement("span");
      chunk.className = "fresh";
      chunk.textContent = data.lines.join("\n") + "\n";
      log.insertBefore(chunk, pending);
    }
    pending.textContent = data.partial;
    if (atBottom) {
      log.scrollTop = log.scrollHeight;
    }
    next = data.next;
    showState(panel, data);

    if (data.status !== "running" && data.lines.length === 0) {
      return;
    }
    await wait(Number(panel.dataset.poll));
  }
}

function showState(panel, data) {
  const status = panel.querySelector("[data-status]");
  let statusText = data.label;
  if (data.status === "failed" && data.exit_code !== null) {
    statusText += " · exit " + data.exit_code;
  }
  status.textContent = statusText;
  const before = panel.dataset.last;
  panel.dataset.last = data.status;
  status.className = "status status-" + data.status;
  if (before && before !== data.status) {
    popOnce(status);
  }
  if (before === undefined && data.status === "running") {
    buddyMood("running");
  }
  if (before === "running" && data.status !== "running") {
    buddyMood(data.status);
    if (data.status === "ok" && !calm) {
      throwConfetti(status);
    }
  }
  panel.querySelector("[data-elapsed]").textContent = data.elapsed;

  const stepDots = panel.querySelectorAll("[data-steps] .dot");
  for (let index = 0; index < stepDots.length; index++) {
    showDot(stepDots[index], data.steps[index].status);
  }

  const row = panel.closest("details");
  if (row) {
    const rowDot = row.querySelector("[data-dot]");
    rowDot.className = "dot dot-" + data.status;
    rowDot.hidden = false;
  }

  const stop = panel.querySelector('[data-fetch="stop"]');
  stop.hidden = data.cancel_url === null;
  if (data.cancel_url) {
    stop.action = data.cancel_url;
  }

  const answer = panel.querySelector('[data-fetch="answer"]');
  const asking = data.input_url !== null && data.partial.trim() !== "";
  if (asking) {
    answer.action = data.input_url;
  }
  if (asking && answer.hidden) {
    answer.hidden = false;
    const typingElsewhere = document.activeElement.matches("input, textarea, select");
    if (!typingElsewhere) {
      answer.elements.text.focus({preventScroll: true});
    }
  }
  if (!asking) {
    answer.hidden = true;
  }

  document.body.classList.toggle("busy", data.running > 0);
  const badge = document.querySelector("[data-running]");
  if (badge.textContent !== String(data.running)) {
    popOnce(badge);
  }
  badge.textContent = data.running;
  badge.hidden = data.running === 0;
}

function showDot(dot, stepStatus) {
  const before = dot.dataset.status;
  dot.dataset.status = stepStatus;
  dot.className = "dot dot-" + stepStatus;
  if (before && before !== stepStatus) {
    popOnce(dot);
  }
}

function popOnce(element) {
  element.classList.add("pop");
  element.addEventListener("animationend", function () {
    element.classList.remove("pop");
  }, {once: true});
}

function throwConfetti(anchor) {
  const box = anchor.getBoundingClientRect();
  for (let index = 0; index < CONFETTI_PIECES; index++) {
    const angle = (index / CONFETTI_PIECES) * 2 * Math.PI;
    const distance = 36 + Math.random() * 44;
    const piece = document.createElement("span");
    piece.className = "confetti";
    piece.style.left = box.left + 16 + "px";
    piece.style.top = box.top + box.height / 2 + "px";
    piece.style.background = CONFETTI_COLOURS[index % CONFETTI_COLOURS.length];
    piece.style.setProperty("--dx", Math.cos(angle) * distance + "px");
    piece.style.setProperty("--dy", Math.sin(angle) * distance - 24 + "px");
    piece.addEventListener("animationend", function () {
      piece.remove();
    });
    document.body.append(piece);
  }
}

async function countUp(element) {
  const target = Number(element.dataset.count);
  const suffix = element.dataset.suffix || "";
  const frames = 24;
  for (let frame = 1; frame <= frames; frame++) {
    const progress = 1 - Math.pow(1 - frame / frames, 3);
    element.textContent = Math.round(target * progress).toLocaleString("en") + suffix;
    await wait(28);
  }
}

async function keepRegionFresh(region) {
  let delay = Number(region.dataset.live);
  while (delay > 0) {
    await wait(delay);
    let page;
    try {
      const response = await fetch(window.location.href);
      page = new DOMParser().parseFromString(await response.text(), "text/html");
    } catch (error) {
      return;
    }
    const fresh = page.querySelector("[data-region]");
    if (!fresh) {
      return;
    }
    region.dataset.refreshed = "yes";
    region.innerHTML = fresh.innerHTML;
    delay = Number(fresh.dataset.live || 0);
  }
}


// ---- Theme ----

function cycleTheme() {
  const now = savedTheme();
  const next = THEME_CHOICES[(THEME_CHOICES.indexOf(now) + 1) % THEME_CHOICES.length];
  saveTheme(next);
  applyTheme(next);
  labelThemeButton();
}

function labelThemeButton() {
  const button = document.querySelector("[data-theme-toggle]");
  button.setAttribute("aria-label", THEME_NAMES[savedTheme()]);
  button.title = THEME_NAMES[savedTheme()];
}


// ---- Dropdown menus ----

function handleMenuClick(event) {
  if (event.target.closest("[data-theme-toggle]")) {
    cycleTheme();
    return;
  }
  const option = event.target.closest(".menu-option");
  if (option) {
    chooseOption(option);
    return;
  }
  if (event.target.closest(".menu")) {
    return;
  }
  const opener = event.target.closest(".select-button, [data-pick-address], [data-list-models]");
  const sameOpener = opener !== null && opener === openedMenu.anchor;
  closeMenu();
  if (opener === null || sameOpener) {
    return;
  }
  if (opener.matches(".select-button")) {
    showSelectMenu(opener);
  } else if (opener.matches("[data-pick-address]")) {
    showAddressMenu(opener);
  } else {
    showModelMenu(opener);
  }
}

function handleMenuKeys(event) {
  if (openedMenu.menu === null) {
    if (event.key === "ArrowDown" && event.target.matches(".select-button")) {
      event.preventDefault();
      showSelectMenu(event.target);
    }
    return;
  }
  if (event.key === "Escape") {
    event.preventDefault();
    const anchor = openedMenu.anchor;
    closeMenu();
    anchor.focus();
    return;
  }
  if (event.key === "Tab") {
    closeMenu();
    return;
  }
  const step = MENU_STEPS[event.key];
  if (step) {
    event.preventDefault();
    moveFocus(step);
  }
}

function openMenu(anchor, groups, chosen, pick) {
  const menu = document.createElement("div");
  menu.className = "menu";
  menu.setAttribute("role", "listbox");
  for (const group of groups) {
    if (group.label) {
      const heading = document.createElement("div");
      heading.className = "menu-group";
      heading.textContent = group.label;
      menu.append(heading);
    }
    for (const item of group.items) {
      menu.append(menuOption(item, chosen));
    }
  }
  const box = (anchor.closest(".combo") || anchor).getBoundingClientRect();
  menu.style.left = box.left + window.scrollX + "px";
  menu.style.top = box.bottom + window.scrollY + 4 + "px";
  menu.style.minWidth = box.width + "px";
  document.body.append(menu);
  anchor.setAttribute("aria-expanded", "true");
  openedMenu.menu = menu;
  openedMenu.anchor = anchor;
  openedMenu.pick = pick;
  const first = menu.querySelector('[aria-selected="true"]') || menu.querySelector(".menu-option");
  if (first) {
    first.focus();
  }
}

function menuOption(item, chosen) {
  const option = document.createElement("button");
  option.type = "button";
  option.className = "menu-option";
  option.setAttribute("role", "option");
  option.setAttribute("aria-selected", String(item.value === chosen));
  option.dataset.value = item.value;
  const label = document.createElement("span");
  label.textContent = item.label;
  option.append(label);
  if (item.detail) {
    const detail = document.createElement("span");
    detail.className = "menu-detail";
    detail.textContent = item.detail;
    option.append(detail);
  }
  return option;
}

function closeMenu() {
  if (openedMenu.menu === null) {
    return;
  }
  openedMenu.menu.remove();
  openedMenu.anchor.setAttribute("aria-expanded", "false");
  openedMenu.menu = null;
  openedMenu.anchor = null;
  openedMenu.pick = null;
}

function chooseOption(option) {
  const anchor = openedMenu.anchor;
  const pick = openedMenu.pick;
  closeMenu();
  pick(option.dataset.value);
  anchor.focus();
}

function moveFocus(step) {
  const options = Array.from(openedMenu.menu.querySelectorAll(".menu-option"));
  const now = options.indexOf(document.activeElement);
  const next = Math.min(Math.max(now + step, 0), options.length - 1);
  options[next].focus();
}

function enhanceSelect(select) {
  const button = document.createElement("button");
  button.type = "button";
  button.className = "select-button";
  button.setAttribute("aria-haspopup", "listbox");
  button.setAttribute("aria-expanded", "false");
  button.append(document.createElement("span"));
  select.classList.add("visually-hidden");
  select.tabIndex = -1;
  select.after(button);
  showChoice(select, button);
  select.addEventListener("change", function () {
    showChoice(select, button);
  });
}

function showChoice(select, button) {
  const option = select.options[select.selectedIndex];
  const choice = option ? option.textContent : "";
  button.firstChild.textContent = choice;
  const field = select.closest("label");
  const name = field && field.querySelector("span") ? field.querySelector("span").textContent : select.getAttribute("aria-label");
  button.setAttribute("aria-label", (name || "Choice") + ": " + choice);
}

function showSelectMenu(button) {
  const select = button.previousElementSibling;
  const items = [];
  for (const option of select.options) {
    items.push({value: option.value, label: option.textContent, detail: option.dataset.detail || ""});
  }
  openMenu(button, [{label: "", items: items}], select.value, function (value) {
    select.value = value;
    select.dispatchEvent(new Event("change", {bubbles: true}));
  });
}

function showAddressMenu(button) {
  const addresses = JSON.parse(document.getElementById("addresses").textContent);
  const checked = button.closest(".model-card").querySelector('input[type="radio"]:checked');
  const route = checked ? checked.value : "";
  const groups = [];
  for (const name in ADDRESS_GROUPS) {
    if (route && route !== name) {
      continue;
    }
    const items = [];
    for (const address of addresses[name]) {
      items.push({value: address.value, label: address.label, detail: address.value});
    }
    groups.push({label: ADDRESS_GROUPS[name], items: items});
  }
  const input = button.closest(".combo").querySelector("input");
  openMenu(button, groups, input.value, function (value) {
    input.value = value;
  });
}

async function showModelMenu(button) {
  const input = button.closest(".combo").querySelector("input");
  const form = new FormData();
  form.append("token", document.querySelector('input[name="token"]').value);
  form.append("app", button.dataset.app);
  form.append("base_url", button.closest(".model-card").querySelector("[data-address]").value);
  const label = button.textContent;
  button.textContent = "Looking…";
  button.disabled = true;
  let data;
  try {
    const response = await fetch(button.dataset.listUrl, {method: "POST", body: form});
    data = await response.json();
  } catch (error) {
    data = {error: "The console did not answer. Reload the page and try again."};
  }
  button.textContent = label;
  button.disabled = false;
  if (data.error) {
    showMessage(data.error);
    return;
  }
  const items = [];
  for (const name of data.models) {
    items.push({value: name, label: name, detail: ""});
  }
  openMenu(button, [{label: "", items: items}], input.value, function (value) {
    input.value = value;
  });
}
