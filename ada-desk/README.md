# Ada Desk

A fully working 5-page site combining your Stitch templates (Home, Published,
Spiked, Cycle Log, API Reference) into one consistent, connected front end.

## Run it

No build step needed — it's static HTML/CSS/JS.

- **Quickest:** double-click `index.html` to open it in a browser.
- **Better (so relative paths/fonts behave):** serve it locally, e.g.
  `python3 -m http.server 8000` from this folder, then visit
  `http://localhost:8000`.
- Or drag the whole `ada-desk` folder into Netlify/Vercel/GitHub Pages — it's
  ready to host as-is.

## What's here

```
ada-desk/
├── index.html         Home — Ada Primary status, system metrics, live feed
├── published.html      Published Intelligence reports list
├── spiked.html          Spiked Topics (rejected analysis cycles)
├── cycle-log.html       Chronological terminal-style cycle log
├── api.html              API reference docs
└── assets/
    ├── css/styles.css          shared styling (glass panels, animations, nav states)
    └── js/
        ├── tailwind-config.js   shared Tailwind theme (colors/type from your DESIGN.md)
        ├── main.js               all current interactivity (see below)
        └── agent-api.js          <-- plug your real agent API in here
```

## What already works, with no backend

- Real navigation between all 5 pages, with the sidebar correctly
  highlighting whichever page you're on.
- Mobile: hamburger menu opens a slide-out drawer (works down to phone widths).
- "Initiate Cycle" button on every page (shows a toast + loading state).
- Home page's Active Analysis Feed streams new fake log lines every few
  seconds, so it feels alive.
- Cycle Log's "Scanning cluster beta-9" line ticks upward on its own.
- Spiked page's search box live-filters the list as you type.
- Spiked "Re-Evaluate" / "Merge Data" buttons give visual feedback.
- API page's copy-to-clipboard buttons actually copy.
- Published page's "Fetch Older Records" responds when clicked.

All of that is local demo behavior — no network calls yet.

## Where to add your agent API

Everything you need to change lives in **`assets/js/agent-api.js`**. It's a
single `AdaAgentAPI` object with stub methods (`initiateCycle`, `fetchFeed`,
`fetchPublished`, `fetchSpiked`, `fetchCycleLog`) and a `baseUrl`/`apiKey` you
fill in. Once implemented, wire it into `assets/js/main.js` at the two
`TODO(agent-api)` comments (currently the Initiate Cycle button just shows a
demo toast). From there you can extend the same pattern to load real data
into the Published/Spiked/Cycle Log lists instead of the static markup
that's there now.
