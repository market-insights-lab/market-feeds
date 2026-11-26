# Piezo feeds

Two separate RSS feeds, harvested daily at 05:17 UTC by GitHub Actions:

- Tenders (EU TED API): `https://raw.githubusercontent.com/USER/REPO/main/feeds/tenders.xml`
- Patents (WIPO Patentscope RSS): `https://raw.githubusercontent.com/USER/REPO/main/feeds/patents.xml`

`data/` keeps every item ever found. Search terms and patent feeds are in `config.json`.
Optional secrets (Settings → Secrets and variables → Actions), comma-separated applicant names used for patent rating: `WATCHLIST` and `COMPETITORS`.
Run now: Actions → "Daily harvest" → Run workflow.
