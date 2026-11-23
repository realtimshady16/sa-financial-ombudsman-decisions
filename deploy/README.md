# Deployment

## Monthly freshness check

`ombudsman-watch.timer` runs `scripts/watch_sitemaps.py` on the first of each month and diffs the
ombuds' sitemaps against **its own baseline** (`local/watch/baseline.json`), not against the census —
the sitemaps and the census describe the same documents with different slugs, so a census comparison
would report a permanent ~41-item disagreement and cry wolf every month.

Install as a user timer:

```bash
cp deploy/ombudsman-watch.service deploy/ombudsman-watch.timer ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now ombudsman-watch.timer
```

**Reading it:** a clean run exits 0 and stays invisible. The service is started with
`--changed-exit`, so when something *was* added or removed it exits 3 and systemd marks the unit
failed — which is how it surfaces, without needing anything to be watching:

```bash
systemctl --user --failed                    # shows ombudsman-watch.service if something changed
journalctl --user -u ombudsman-watch.service # what changed
cat local/watch/latest.md                    # the same, in prose
```

`Persistent=true` means a missed run (machine off on the 1st) fires on the next boot.

The watcher reports; it does not harvest. Picking up new documents means re-running the census and
extraction stages against the new URLs.
