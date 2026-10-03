const BUDDY_KEY = "pepa-buddy";
const IDLE_ACTIONS = ["hop", "look", "walk", "hop", "look"];
const ACTION_MILLISECONDS = {
  hop: 600,
  look: 1800,
  walk: 4200,
  jump: 1500,
  shake: 1000,
  stretch: 900,
};
const MOOD_LINES = {
  running: "On it. This panel shows how far I am.",
  ok: "Done! Have a look at what came out.",
  failed: "That one failed. The log says why.",
  cancelled: "Stopped. Finished work is kept.",
};
const MOOD_ACTIONS = {
  ok: "jump",
  failed: "shake",
};
const SLEEP_MILLISECONDS = 90000;
const SAY_MILLISECONDS = 7000;
const VISITED_KEY = "pepa-visited";

const buddy = document.querySelector("[data-buddy]");
const buddyCalm = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
const buddyState = {tip: 0, sleepTimer: null, sayTimer: null};

if (buddy) {
  startBuddy();
}


function startBuddy() {
  if (buddyIsTucked()) {
    buddy.classList.add("tucked");
  }
  buddy.querySelector("[data-buddy-button]").addEventListener("click", buddyClicked);
  buddy.querySelector("[data-tuck]").addEventListener("click", tuckBuddy);
  if (visitedBefore()) {
    buddy.classList.add("settled");
  }
  document.addEventListener("pointermove", wakeBuddy);
  document.addEventListener("keydown", wakeBuddy);
  wakeBuddy();
  if (!buddyCalm) {
    idleLoop();
  }
}

function visitedBefore() {
  try {
    const visited = sessionStorage.getItem(VISITED_KEY) === "yes";
    sessionStorage.setItem(VISITED_KEY, "yes");
    return visited;
  } catch (error) {
    return false;
  }
}

function buddyIsTucked() {
  try {
    return localStorage.getItem(BUDDY_KEY) === "tucked";
  } catch (error) {
    return false;
  }
}

function rememberTucked(tucked) {
  try {
    localStorage.setItem(BUDDY_KEY, tucked ? "tucked" : "out");
  } catch (error) {
    return;
  }
}

function buddyClicked() {
  if (buddy.classList.contains("tucked")) {
    buddy.classList.remove("tucked");
    rememberTucked(false);
    act("stretch");
    say(tipsData().greeting);
    return;
  }
  act("jump");
  say(nextTip());
}

function tuckBuddy() {
  hideBubble();
  buddy.classList.add("tucked");
  rememberTucked(true);
}

function tipsData() {
  return JSON.parse(document.getElementById("tips").textContent);
}

function nextTip() {
  const section = window.location.pathname.split("/")[1];
  const pages = tipsData().pages;
  const tips = pages[section] || pages[""];
  const tip = tips[buddyState.tip % tips.length];
  buddyState.tip += 1;
  return tip;
}

function say(text) {
  if (buddy.classList.contains("tucked")) {
    return;
  }
  const bubble = buddy.querySelector("[data-bubble]");
  bubble.querySelector("[data-bubble-text]").textContent = text;
  bubble.hidden = false;
  clearTimeout(buddyState.sayTimer);
  buddyState.sayTimer = setTimeout(hideBubble, SAY_MILLISECONDS);
}

function hideBubble() {
  buddy.querySelector("[data-bubble]").hidden = true;
}

function act(action) {
  if (buddyCalm) {
    return;
  }
  buddy.classList.add(action);
  setTimeout(function () {
    buddy.classList.remove(action);
  }, ACTION_MILLISECONDS[action]);
}

function buddyMood(status) {
  if (!buddy) {
    return;
  }
  wakeBuddy();
  if (MOOD_ACTIONS[status]) {
    act(MOOD_ACTIONS[status]);
  }
  if (MOOD_LINES[status]) {
    say(MOOD_LINES[status]);
  }
}

function wakeBuddy() {
  if (buddy.classList.contains("asleep")) {
    buddy.classList.remove("asleep");
    act("stretch");
  }
  clearTimeout(buddyState.sleepTimer);
  buddyState.sleepTimer = setTimeout(function () {
    hideBubble();
    buddy.classList.add("asleep");
  }, SLEEP_MILLISECONDS);
}

async function idleLoop() {
  while (true) {
    await new Promise(function (resolve) {
      setTimeout(resolve, 9000 + Math.random() * 12000);
    });
    const busy = buddy.classList.contains("asleep") || buddy.classList.contains("tucked") || document.hidden;
    if (!busy) {
      act(IDLE_ACTIONS[Math.floor(Math.random() * IDLE_ACTIONS.length)]);
    }
  }
}
