# Line Tracker (browser overlay)

A tiny Chrome/Edge extension that draws a **live graph of any number on a web page** — an odds
price, an over/under total — including on 1xbet. It's a *read-only overlay*: it reads the text of
the element you click, graphs it over time, and **sends nothing anywhere and places nothing.**

It works on any site because it's a real extension (content scripts run even on pages with strict
security policies). It exists so you can *see the tracking/graphing concept working against a real
page*. On its own it gives you **no betting edge** — that still requires a sharp fair line to
compare against (see the repo's `FINDINGS.md`).

## Install (one time, ~1 minute)

1. Open Chrome or Edge and go to **`chrome://extensions`** (Edge: `edge://extensions`).
2. Turn on **Developer mode** (top-right toggle).
3. Click **Load unpacked**.
4. Select this **`extension`** folder (the one containing `manifest.json`).

A "📈 Line Tracker" card appears in the bottom-right of every page.

## Use

1. Open the page with the numbers you want to watch (e.g. a 1xbet game page).
2. In the card, click **🎯 Pick a number**.
3. Click the exact number on the page you want to track (the odds like `1.87`, or a total like `81.5`).
4. It now polls that number every 2 seconds and draws it live. **Pause** / **Clear** as needed;
   drag the card by its blue header; **✕** closes it.

**To check it's accurate:** watch the big number in the card — it should always match the number
you clicked on the page. When 1xbet moves the line/price, the graph moves with it.

## Honest limits

- It reads **one book's own number** (1xbet's). That is not an edge by itself — an edge is 1xbet
  being off a **sharp** line, which needs a sharp data source we don't have for free.
- Automated reading of a sportsbook can violate its terms; 1xbet limits/bans accounts it thinks are
  sharp or automated. This tool is for *seeing the graph work*, not for gaining an advantage.
- It tracks whatever element you click. If a site re-renders that element, re-pick it.
