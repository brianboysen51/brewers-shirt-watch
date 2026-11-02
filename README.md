# brewers-shirt-watch

Pushes an urgent ntfy alert when the Women's Brewers cream 2026 World Series
Champions Parade tee comes back in size S or M at MLB Shop, Fanatics, or Rally House.

Runs on GitHub Actions every ~5 min, because Fanatics-run stores block requests
from Brian's UK connection. Secret: `NTFY_TOPIC`.

- Test push: Actions > watch > Run workflow > mode `test`
- Inspect fetched pages: mode `debug`, download the `pages` artifact
- Stop watching: Actions > watch > ... > Disable workflow
- Each restock alerts once; `state.json` records the last seen S/M stock per store.
  After 6 failed checks in a row on a store, you get one "watcher blind" notice.
