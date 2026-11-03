# brewers-shirt-watch

Pushes an urgent ntfy alert when Brewers merch comes back in stock. Currently watching
the **Gold/Navy (yellow crown) New Era 2026 World Series Side Patch 9TWENTY adjustable
hat** on MLB Shop (same Fanatics stock pool as Fanatics.com and Lids). The yellow hat is
its own listing; the navy hat's page hides sold-out color swatches. New Era and Rally
House don't sell a gold 9TWENTY of this hat. (Previously: women's cream Parade tee S/M,
bought 2026-11-03.) What's watched lives in `ITEM` / `SITES` at the top of `check.py`.

Runs locally on Brian's WSL box as a systemd user timer, every 3-7 min (5 +- 2, re-randomized each run):
`~/.config/systemd/user/shirt-watch.{service,timer}`. MLB Shop is loaded in real headed
Google Chrome via Patchright under xvfb (like delta-watch). If Akamai denies the saved
profile, the run wipes it and retries with a fresh one. Uses delta-watch's venv for
Patchright. ntfy topic in `.env` (gitignored).

- Logs: `journalctl --user -u shirt-watch -n 20`
- Test push: `python3 check.py --test`
- Stop: `systemctl --user disable --now shirt-watch.timer`
- Each restock alerts once (`state.json`). After 6 failed checks in a row on a store
  (~30 min), you get one "watcher blind" notice, and a "recovered" one when it's back.
