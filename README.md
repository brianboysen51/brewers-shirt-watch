# brewers-shirt-watch

Pushes an urgent ntfy alert when the Women's Brewers cream 2026 World Series
Champions Parade tee comes back in size S or M at MLB Shop (same Fanatics stock pool
as Fanatics.com and Lids) or Rally House.

Runs locally on Brian's WSL box as a systemd user timer, every 3-7 min (5 +- 2, re-randomized each run):
`~/.config/systemd/user/shirt-watch.{service,timer}`. MLB Shop is loaded in real headed
Google Chrome via Patchright under xvfb (like delta-watch); Rally House is plain HTTP.
Uses delta-watch's venv for Patchright. ntfy topic in `.env` (gitignored).

- Logs: `journalctl --user -u shirt-watch -n 20`
- Test push: `python3 check.py --test`
- Stop: `systemctl --user disable --now shirt-watch.timer`
- Each restock alerts once (`state.json`). After 6 failed checks in a row on a store
  (~30 min), you get one "watcher blind" notice, and a "recovered" one when it's back.
