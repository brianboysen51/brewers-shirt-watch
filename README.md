# brewers-shirt-watch

Pushes an urgent ntfy alert when the Women's Brewers cream 2026 World Series
Champions Parade tee comes back in size S or M at Rally House.

Runs on GitHub Actions every ~5 min. Secret: `NTFY_TOPIC`. MLB Shop / Fanatics / Lids
are not watched: their Akamai bot wall returns 403 to any scripted request.

- Test push: Actions > watch > Run workflow > mode `test`
- Inspect fetched pages: mode `debug`, download the `pages` artifact
- Stop watching: Actions > watch > ... > Disable workflow
- Each restock alerts once; `state.json` records the last seen S/M stock per store.
  After 6 failed checks in a row on a store, you get one "watcher blind" notice.
