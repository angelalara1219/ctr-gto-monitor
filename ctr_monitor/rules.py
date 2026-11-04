"""Daily CTR, GTO, and structuring checks for a cash-based MSB.

The rules here come from public sources, not from any company's internal
procedures:

  * CTR: 31 CFR 1022.310 requires MSBs to report currency transactions of
    MORE THAN $10,000. Under 31 CFR 1010.313, multiple transactions by or on
    behalf of the same person in one business day are aggregated, with cash
    in and cash out totaled separately.
  * Southwest Border GTO (Federal Register doc. 2026-18194, effective
    2026-09-03 through 2027-03-01): MSBs in covered ZIP codes report
    currency transactions of $1,000 OR MORE, but not more than $10,000,
    within 30 days. The order does not address aggregation, so this tool
    applies it per transaction and does not aggregate.
  * Structuring: patterns of transactions kept just under a threshold.
    These are SAR review leads, not filings.
"""

from __future__ import annotations

import csv
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

CTR_THRESHOLD = Decimal("10000")         # report if total is MORE than this
GTO_MIN = Decimal("1000")                # report if amount is at least this...
GTO_MAX = Decimal("10000")               # ...and not more than this
GTO_FILING_DAYS = 30
GTO_KEY_TERM = "MSB0926GTO"              # CTR Part IV, Field 45

# Structuring lead: 2+ transactions inside this window, each within this
# band below a threshold, by the same customer.
NEAR_BAND = Decimal("0.80")              # 80% to just under the threshold
STRUCTURING_WINDOW_DAYS = 3


@dataclass
class Txn:
    txn_id: str
    timestamp: datetime
    customer_id: str
    customer_name: str
    kiosk_id: str
    kiosk_zip: str
    kiosk_state: str
    direction: str            # "cash_in" or "cash_out"
    amount: Decimal

    @property
    def business_day(self) -> date:
        return self.timestamp.date()


@dataclass
class Flag:
    rule: str
    business_day: str
    customer_id: str
    customer_name: str
    direction: str
    total: Decimal
    txn_ids: list[str] = field(default_factory=list)
    zips: list[str] = field(default_factory=list)
    due_date: str = ""
    note: str = ""

    def as_row(self) -> dict:
        return {
            "rule": self.rule,
            "business_day": self.business_day,
            "customer_id": self.customer_id,
            "customer_name": self.customer_name,
            "direction": self.direction,
            "total_usd": f"{self.total:.2f}",
            "txn_count": len(self.txn_ids),
            "txn_ids": " ".join(self.txn_ids),
            "zips": " ".join(sorted(set(self.zips))),
            "due_date": self.due_date,
            "note": self.note,
        }


# --------------------------------------------------------------- loading

def load_transactions(path: Path) -> list[Txn]:
    with path.open(newline="", encoding="utf-8") as f:
        return [
            Txn(
                txn_id=r["txn_id"],
                timestamp=datetime.fromisoformat(r["timestamp"]),
                customer_id=r["customer_id"],
                customer_name=r["customer_name"],
                kiosk_id=r["kiosk_id"],
                kiosk_zip=r["kiosk_zip"].zfill(5),
                kiosk_state=r["kiosk_state"],
                direction=r["direction"],
                amount=Decimal(r["amount_usd"]),
            )
            for r in csv.DictReader(f)
        ]


def load_gto_zips(path: Path = ROOT / "data" / "gto_zips.csv", on: date | None = None) -> set[str]:
    """ZIPs covered by an order that is in force on the given day."""
    zips = set()
    with path.open(newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            if on and not (date.fromisoformat(r["effective"]) <= on <= date.fromisoformat(r["expires"])):
                continue
            zips.add(r["zip"].zfill(5))
    return zips


# --------------------------------------------------------------- rules

def ctr_flags(txns: list[Txn], day: date) -> list[Flag]:
    """Single or aggregated cash in, or cash out, over $10,000 in a day."""
    groups: dict[tuple[str, str], list[Txn]] = defaultdict(list)
    for t in txns:
        if t.business_day == day:
            groups[(t.customer_id, t.direction)].append(t)
    flags = []
    for (cust, direction), items in sorted(groups.items()):
        total = sum((t.amount for t in items), Decimal("0"))
        if total <= CTR_THRESHOLD:
            continue
        rule = "CTR - single" if len(items) == 1 else "CTR - aggregated"
        flags.append(Flag(
            rule, day.isoformat(), cust, items[0].customer_name, direction, total,
            [t.txn_id for t in items], [t.kiosk_zip for t in items],
            due_date=(day + timedelta(days=15)).isoformat(),
            note="" if len(items) == 1 else f"{len(items)} transactions aggregated across "
                 f"{len({t.kiosk_id for t in items})} kiosk(s)",
        ))
    return flags


def gto_flags(txns: list[Txn], day: date, gto_zips: set[str]) -> list[Flag]:
    """Per-transaction GTO reports for covered ZIPs, $1,000 to $10,000."""
    flags = []
    for t in sorted(txns, key=lambda t: t.timestamp):
        if t.business_day != day or t.kiosk_zip not in gto_zips:
            continue
        if GTO_MIN <= t.amount <= GTO_MAX:
            flags.append(Flag(
                "GTO", day.isoformat(), t.customer_id, t.customer_name, t.direction,
                t.amount, [t.txn_id], [t.kiosk_zip],
                due_date=(day + timedelta(days=GTO_FILING_DAYS)).isoformat(),
                note=f"Enter {GTO_KEY_TERM} in CTR Field 45",
            ))
    return flags


def structuring_flags(txns: list[Txn], day: date, gto_zips: set[str]) -> list[Flag]:
    """Leads for review: repeated amounts just under a threshold.

    Looks back STRUCTURING_WINDOW_DAYS (including today) so a pattern that
    spans a few days is still caught on the day it completes.
    """
    start = day - timedelta(days=STRUCTURING_WINDOW_DAYS - 1)
    window = [t for t in txns if start <= t.business_day <= day]
    bands = [
        ("CTR", CTR_THRESHOLD * NEAR_BAND, CTR_THRESHOLD, lambda t: True),
        ("GTO", GTO_MIN * NEAR_BAND, GTO_MIN, lambda t: t.kiosk_zip in gto_zips),
    ]
    flags = []
    for label, low, high, applies in bands:
        by_cust: dict[tuple[str, str], list[Txn]] = defaultdict(list)
        for t in window:
            if applies(t) and low <= t.amount < high:
                by_cust[(t.customer_id, t.direction)].append(t)
        for (cust, direction), items in sorted(by_cust.items()):
            if len(items) < 2 or not any(t.business_day == day for t in items):
                continue
            total = sum((t.amount for t in items), Decimal("0"))
            flags.append(Flag(
                f"Structuring lead - {label}", day.isoformat(), cust, items[0].customer_name,
                direction, total, [t.txn_id for t in items], [t.kiosk_zip for t in items],
                note=f"{len(items)} transactions between ${low:,.0f} and ${high:,.0f} "
                     f"in {STRUCTURING_WINDOW_DAYS} days; review for SAR",
            ))
    return flags


def run_day(txns: list[Txn], day: date, gto_zips: set[str]) -> list[Flag]:
    return ctr_flags(txns, day) + gto_flags(txns, day, gto_zips) + structuring_flags(txns, day, gto_zips)
