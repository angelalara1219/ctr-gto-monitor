# CTR & GTO Daily Monitor

A daily currency transaction check for a cash-based MSB, like a bitcoin kiosk operator. It flags CTRs (single and aggregated), GTO-covered transactions in FinCEN's Southwest Border ZIP codes, and possible structuring. It also watches FinCEN for GTO changes so the ZIP list doesn't quietly go stale.

> **All data in this repo is synthetic.** The customers, kiosks, and transactions are invented. The rules come from public regulations and the published GTO, not from any company's internal procedures.

## Why I built this

At a kiosk operator, a CTR miss rarely comes from a big obvious $15,000 deposit. It comes from the customer who does $4,000 in Phoenix at 9 a.m. and another $6,500 in Tucson after lunch. Or from the GTO that got reissued over the weekend with a different ZIP list, while the monitoring logic still points at the old one.

I've run this kind of daily review in production. This is a clean, from-scratch version of the idea that anyone can read and run.

— Angela Lara, CAMS

## What it checks

| Check | Rule | Filing |
|---|---|---|
| **CTR, single** | One cash in or cash out over $10,000 | CTR within 15 days |
| **CTR, aggregated** | Same customer, same business day, total over $10,000. Cash in and cash out are totaled **separately**, across all kiosks. | CTR within 15 days |
| **GTO** | Kiosk in a covered ZIP, cash of **$1,000 to $10,000** (both ends included) | CTR within 30 days, with `MSB0926GTO` in Field 45 |
| **Structuring lead, CTR** | 2+ transactions of $8,000 to $9,999.99 by one customer within 3 days | Analyst review for SAR |
| **Structuring lead, GTO** | 2+ transactions of $800 to $999.99 in covered ZIPs within 3 days | Analyst review for SAR |

A few edge cases are handled deliberately, and each has a test:

- **Exactly $10,000 is not a standard CTR.** The rule is *more than* $10,000. In a GTO ZIP, though, exactly $10,000 *is* covered.
- **$6,000 in and $5,500 out the same day is not a CTR.** Cash in and cash out aren't netted or combined.
- **The GTO is applied per transaction.** The order doesn't address aggregation, so the tool doesn't assume it does.
- **GTO ZIPs only count while the order is in force.** Each ZIP carries the order's effective and expiration dates.

## Sample output

The sample week runs Oct 12 to 18, 2026, with a few scenarios planted on Thursday, Oct 15. See the full report: [`reports/report_2026-10-15.md`](reports/report_2026-10-15.md).

| Flag | Customer | What happened |
|---|---|---|
| CTR, single | Avery Testwell | $12,500 cash in at one kiosk |
| CTR, aggregated | Jordan Sampleton | $4,000 + $3,800 + $2,900 across two Arizona kiosks = $10,700 |
| GTO | Morgan Mockley, Quinn Placeholder, Rowan Synthia | $2,500 in El Paso, $1,000 in Laredo, $10,000 in Albuquerque |
| Structuring lead, CTR | Harper Demo | $9,500, $9,800, and $9,700 on three straight days |
| Structuring lead, GTO | Emerson Testwell | $950, $975, and $990 in El Paso in one day |
| *Not flagged* | Riley Demo, Casey Fakerson, Skyler Notreal | $6,000 in and $5,500 out; exactly $10,000 outside a GTO ZIP; $2,500 in Phoenix, which isn't covered |

## The current GTO

[`data/gto_zips.csv`](data/gto_zips.csv) holds the 304 ZIP codes from FinCEN's reissued Southwest Border GTO ([Federal Register 2026-18194](https://public-inspection.federalregister.gov/2026-18194.pdf)). It is effective Sept 3, 2026 through March 1, 2027.

- **Texas:** Cameron, El Paso, Hidalgo, Maverick, and Webb counties
- **New Mexico:** Bernalillo, Doña Ana, and San Juan counties
- **Arizona and California** were in earlier versions and dropped out with this reissue.

[`data/gto_orders.csv`](data/gto_orders.csv) keeps the order history, so you can see how coverage changed over time.

## GTO watcher

GTOs get reissued, narrowed, enjoined, and extended, sometimes on short notice. Every Monday a GitHub Action:

1. checks the [Federal Register API](https://www.federalregister.gov/developers/documentation/api/v1) for FinCEN GTOs aimed at MSBs;
2. if there's a new one, logs it and drafts a proposed ZIP list in `data/proposed/`, showing which ZIPs would be added or dropped;
3. opens a GitHub issue with a review checklist.

It **does not** update the live ZIP list on its own. A wrong list means missed filings or unnecessary ones, so a person confirms the order first.

## Run it

```bash
pip install -r requirements.txt
python -m ctr_monitor.generate                    # rebuild the synthetic week
python -m ctr_monitor.report --date 2026-10-15    # daily report -> reports/
python -m ctr_monitor.gto_watch                   # check for new GTOs
python -m unittest discover -s tests              # 15 tests
```

To run it on your own export, pass `--input path/to/transactions.csv` with these columns: `txn_id, timestamp, customer_id, customer_name, kiosk_id, kiosk_zip, kiosk_state, direction, amount_usd`.

## What this is not

- **Not a filing system.** It tells you what needs a CTR or a closer look. Filing still happens in BSA E-Filing.
- **Not a substitute for customer identity resolution.** Aggregation is only as good as your ability to tell that two transactions belong to the same person.
- **Not legal advice.** Thresholds and ZIPs come from the published order as of November 2026. Always confirm against the current GTO.

## Related

- [FinCEN Advisory & Guidance Tracker](https://github.com/angelalara1219/fincen-advisory-guidance-tracker): FinCEN alerts, advisories, and SAR key terms
- [State Money Transmitter Licensing Tracker](https://github.com/angelalara1219/state-mt-licensing-tracker): NMLS agency alerts and MTMA adoption by state

## License

MIT
