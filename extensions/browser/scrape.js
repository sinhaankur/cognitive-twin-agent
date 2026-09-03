// scrape.js — injected into the mail tab on demand to READ the visible inbox.
// It only reads what's already rendered (sender, subject, snippet, and whether
// the provider shows an "Unsubscribe" cue). It never types, clicks, deletes, or
// sends anything. Returns an array of plain message objects.
//
// Yahoo and Gmail render their lists very differently, so we detect the host and
// use the right selectors, with a resilient fallback that reads role="row"s.

(function scrapeInbox() {
  const host = location.hostname;
  const out = [];

  function push(sender, subject, snippet, hasUnsub) {
    sender = (sender || "").trim();
    subject = (subject || "").trim();
    if (!sender && !subject) return;
    out.push({
      sender,
      subject,
      snippet: (snippet || "").trim().slice(0, 300),
      hasUnsubscribeLink: !!hasUnsub,
    });
  }

  try {
    if (host.includes("yahoo")) {
      // Yahoo Mail: message rows carry data-test-id="message-list-item".
      const rows = document.querySelectorAll('[data-test-id="message-list-item"], a[href*="/d/folders/"]');
      rows.forEach((row) => {
        const sender =
          row.querySelector('[data-test-id="message-sender-name"]')?.textContent ||
          row.querySelector('[data-test-id="sender-name"]')?.textContent ||
          row.querySelector('span[title]')?.getAttribute("title") ||
          "";
        const subject =
          row.querySelector('[data-test-id="message-subject"]')?.textContent ||
          row.querySelector('h3, [role="heading"]')?.textContent || "";
        const snippet =
          row.querySelector('[data-test-id="message-snippet"]')?.textContent || "";
        const hasUnsub = /unsubscribe/i.test(row.textContent || "");
        push(sender, subject, snippet, hasUnsub);
      });
    } else if (host.includes("google")) {
      // Gmail: rows are <tr class="zA">; sender in .yW span[email], subject .y6.
      document.querySelectorAll("tr.zA").forEach((row) => {
        const sender =
          row.querySelector(".yW span[email]")?.getAttribute("email") ||
          row.querySelector(".yW span[name]")?.getAttribute("name") ||
          row.querySelector(".yW")?.textContent || "";
        const subject = row.querySelector(".y6 span")?.textContent || "";
        const snippet = row.querySelector(".y2")?.textContent || "";
        const hasUnsub = /unsubscribe/i.test(row.textContent || "");
        push(sender, subject, snippet, hasUnsub);
      });
    }

    // Fallback: nothing matched the provider selectors → read generic list rows.
    if (out.length === 0) {
      document.querySelectorAll('[role="row"], li[role="listitem"]').forEach((row) => {
        const txt = (row.textContent || "").trim();
        if (txt.length < 6) return;
        const heading = row.querySelector('[role="heading"], h3, strong, b');
        const subject = heading?.textContent || txt.slice(0, 80);
        const sender = row.querySelector('[title], span[email]')?.getAttribute("title") ||
          row.querySelector('span[email]')?.getAttribute("email") || "";
        push(sender, subject, txt, /unsubscribe/i.test(txt));
      });
    }
  } catch (e) {
    return { error: String(e), messages: [] };
  }

  // De-dupe by sender+subject; cap to keep the payload small.
  const seen = new Set();
  const messages = out.filter((m) => {
    const k = m.sender + "|" + m.subject;
    if (seen.has(k)) return false;
    seen.add(k);
    return true;
  }).slice(0, 200);

  return { messages };
})();
