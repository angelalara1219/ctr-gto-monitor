"""Run the daily checks and write a CSV plus a readable Markdown summary.

    python -m ctr_monitor.report --date 2026-10-15
    python -m ctr_monitor.report --date 2026-10-15 --input path/to/transactions.csv
"""

from __future__ import annotations

import argparse
import csv
from datetime import date
from pathlib import Path

from . import rules

ROOT = rules.ROOT
DEFAULT_INPUT = ROOT / "data" / "sample" / "transactions.csv"
REPORTS = ROOT / "reports"

FIELDS = ["rule", "business_day", "customer_id", "customer_name", "direction",
          "total_usd", "txn_count", "txn_ids", "zips", "due_date", "note"]


def write_csv(flags: list[rules.Flag], path: Path) -> None:
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        for fl in flags:
            w.writerow(fl.as_row())


def markdown(flags: list[rules.Flag], day: date, txn_count: int, gto_zip_count: int) -> str:
    def section(title: str, prefix: str, explain: str) -> list[str]:
        items = [f for f in flags if f.rule.startswith(prefix)]
        out = [f"## {title} ({len(items)})", "", explain, ""]
        if not items:
            return out + ["_None today._", ""]
        out += ["| Customer | Direction | Total | Txns | ZIP(s) | Due | Note |",
                "|---|---|---:|---:|---|---|---|"]
        for f in items:
            r = f.as_row()
            out.append(f"| {r['customer_name']} ({r['customer_id']}) | {r['direction']} | "
                       f"${f.total:,.2f} | {r['txn_count']} | {r['zips']} | "
                       f"{r['due_date'] or '—'} | {r['note'] or f.rule} |")
        return out + [""]

    lines = [
        f"# Daily CTR / GTO report: {day.isoformat()}",
        "",
        f"Transactions reviewed: **{txn_count}** · GTO ZIPs in force: **{gto_zip_count}** · "
        f"Items flagged: **{len(flags)}**",
        "",
        "_Synthetic data. No real customers or transactions._",
        "",
    ]
    lines += section("CTRs to file", "CTR",
                     "Cash in or cash out over $10,000 in one business day, single or aggregated. "
                     "Due 15 days after the transaction.")
    lines += section("GTO CTRs to file", "GTO",
                     f"Covered ZIP, ${rules.GTO_MIN:,.0f} to ${rules.GTO_MAX:,.0f} in cash. "
                     f"Due {rules.GTO_FILING_DAYS} days after the transaction.")
    lines += section("Structuring leads to review", "Structuring",
                     "Repeated amounts just under a reporting threshold. These need an analyst's "
                     "judgment, not an automatic filing.")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--date", required=True, help="Business day to review (YYYY-MM-DD)")
    ap.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    ap.add_argument("--out", type=Path, default=REPORTS)
    args = ap.parse_args(argv)

    day = date.fromisoformat(args.date)
    txns = rules.load_transactions(args.input)
    zips = rules.load_gto_zips(on=day)
    flags = rules.run_day(txns, day, zips)

    args.out.mkdir(parents=True, exist_ok=True)
    write_csv(flags, args.out / f"report_{day}.csv")
    reviewed = sum(1 for t in txns if t.business_day == day)
    (args.out / f"report_{day}.md").write_text(markdown(flags, day, reviewed, len(zips)), encoding="utf-8")
    print(f"{day}: {reviewed} transactions, {len(flags)} flagged -> {args.out}/report_{day}.md")


if __name__ == "__main__":
    main()
