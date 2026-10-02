const confirmDialog = document.getElementById("confirm");

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
      log.insertBefore(document.createTextNode(data.lines.join("\n") + "\n"), pending);
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
  status.className = "status status-" + data.status;
  panel.querySelector("[data-elapsed]").textContent = data.elapsed;

  const stepDots = panel.querySelectorAll("[data-steps] .dot");
  for (let index = 0; index < stepDots.length; index++) {
    stepDots[index].className = "dot dot-" + data.steps[index].status;
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
  badge.textContent = data.running;
  badge.hidden = data.running === 0;
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
    region.innerHTML = fresh.innerHTML;
    delay = Number(fresh.dataset.live || 0);
  }
}
