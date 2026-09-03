// popup.js — the whole flow, on one click:
//   1. inject scrape.js into the active mail tab → get the visible messages
//   2. POST them to the LOCAL Vera core (127.0.0.1:7878) → on-device verdicts
//   3. render the grouped report
// No credentials are read or sent — only what the page already shows. If the
// local Vera isn't running, we say so plainly.

const VERA = "http://127.0.0.1:7878/api/email/triage-messages";
const LABELS = ["good", "marketing", "spam", "unsure"];
const TITLES = { good: "Real / keep", marketing: "Marketing", spam: "Spam", unsure: "Unsure" };

const $ = (id) => document.getElementById(id);
const esc = (s) => (s || "").replace(/[&<>]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;" }[c]));

async function activeTab() {
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  return tab;
}

function isMailTab(url = "") {
  return /https:\/\/(mail\.yahoo\.com|[^/]*\.mail\.yahoo\.com|mail\.google\.com)\//.test(url);
}

async function run() {
  const btn = $("go");
  const result = $("result");
  const foot = $("foot");
  result.innerHTML = "";
  foot.textContent = "";
  btn.disabled = true;
  btn.textContent = "Reading the inbox…";

  try {
    const tab = await activeTab();
    if (!tab || !isMailTab(tab.url)) {
      result.innerHTML = `<p class="err">Open your Yahoo (or Gmail) inbox tab first, then click again.</p>`;
      return;
    }

    // 1. scrape the visible list
    const [{ result: scraped } = {}] = await chrome.scripting.executeScript({
      target: { tabId: tab.id },
      files: ["scrape.js"],
    });
    const messages = (scraped && scraped.messages) || [];
    if (messages.length === 0) {
      result.innerHTML = `<p class="err">Couldn't read any messages from this tab. Make sure the inbox list is on screen and scrolled a bit.</p>`;
      return;
    }

    // 2. hand them to the local Vera core
    btn.textContent = `Triaging ${messages.length}…`;
    let data;
    try {
      const res = await fetch(VERA, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ messages }),
      });
      data = await res.json();
    } catch {
      result.innerHTML = `<p class="err">Can't reach your local Vera. Start the Vera app (or its server) and try again.</p>`;
      return;
    }

    // 3. render
    render(data);
    foot.textContent = `${data.total} read on screen · read-only · on-device`;
  } finally {
    btn.disabled = false;
    btn.textContent = "Triage again";
  }
}

function render(data) {
  const result = $("result");
  const c = data.counts || {};
  const chips = LABELS.map(
    (l) => `<div class="chip ${l}"><b>${c[l] || 0}</b><span>${l}</span></div>`
  ).join("");

  const byLabel = { good: [], marketing: [], spam: [], unsure: [] };
  (data.items || []).forEach((m) => (byLabel[m.label] || byLabel.unsure).push(m));

  // Show the junk first — that's what the user came for.
  const order = ["marketing", "spam", "unsure", "good"];
  const groups = order
    .filter((l) => byLabel[l].length)
    .map((l) => {
      const rows = byLabel[l]
        .map(
          (m) => `<div class="row">
            <div class="from">${esc(m.sender) || "(unknown sender)"}</div>
            <div class="subj">${esc(m.subject) || "(no subject)"}</div>
            <div class="why">${esc(m.reason)}</div>
          </div>`
        )
        .join("");
      return `<div class="group"><h2>${TITLES[l]} (${byLabel[l].length})</h2>${rows}</div>`;
    })
    .join("");

  result.innerHTML = `<div class="counts">${chips}</div>${groups}`;
}

$("go").addEventListener("click", run);
