"""Make a synthetic week of kiosk transactions.

Everything here is invented: customers, kiosks, and amounts. A handful of
scenarios are planted on purpose so the daily report has something to
show, and the rest is ordinary background activity.
"""

from __future__ import annotations

import csv
import random
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "sample" / "transactions.csv"

# Fake kiosks. Three sit in covered GTO ZIPs (El Paso, Laredo, Albuquerque).
KIOSKS = {
    "K-PHX-01": ("85004", "AZ"),
    "K-TUC-02": ("85705", "AZ"),
    "K-ELP-03": ("79901", "TX"),   # GTO
    "K-LRD-04": ("78041", "TX"),   # GTO
    "K-ABQ-05": ("87102", "NM"),   # GTO
    "K-DAL-06": ("75201", "TX"),
    "K-LAX-07": ("90012", "CA"),
}

FIRST = ["Avery", "Jordan", "Riley", "Casey", "Morgan", "Quinn", "Rowan", "Skyler",
         "Harper", "Emerson", "Reese", "Dakota", "Parker", "Sage", "Finley", "Kendall"]
LAST = ["Testwell", "Sampleton", "Demo", "Fakerson", "Mockley", "Placeholder",
        "Synthia", "Notreal"]

START = datetime(2026, 10, 12, 8, 0)     # Monday
DAYS = 7


def _name(rng: random.Random) -> str:
    return f"{rng.choice(FIRST)} {rng.choice(LAST)}"


def build(seed: int = 1219) -> list[dict]:
    rng = random.Random(seed)
    rows: list[dict] = []
    counter = 0

    def add(day: int, hour: float, cust: str, name: str, kiosk: str, direction: str, amount: float):
        nonlocal counter
        counter += 1
        zip_code, state = KIOSKS[kiosk]
        rows.append({
            "txn_id": f"T{counter:05d}",
            "timestamp": (START + timedelta(days=day, hours=hour)).isoformat(timespec="minutes"),
            "customer_id": cust,
            "customer_name": name,
            "kiosk_id": kiosk,
            "kiosk_zip": zip_code,
            "kiosk_state": state,
            "direction": direction,
            "amount_usd": f"{amount:.2f}",
        })

    # Background: 60 customers, small everyday amounts.
    for i in range(60):
        cust, name = f"C{100 + i}", _name(rng)
        for _ in range(rng.randint(1, 4)):
            kiosk = rng.choice(list(KIOSKS))
            direction = "cash_in" if rng.random() < 0.9 else "cash_out"
            add(rng.randrange(DAYS), rng.uniform(0, 12), cust, name, kiosk, direction,
                round(rng.uniform(40, 750), 2))

    # Planted scenarios (day 3 = Thursday 2026-10-15) ---------------------
    # 1. One cash-in over $10,000.
    add(3, 1.5, "C900", "Avery Testwell", "K-PHX-01", "cash_in", 12500.00)
    # 2. Three cash-ins that only cross $10,000 once aggregated, two kiosks.
    add(3, 2.0, "C901", "Jordan Sampleton", "K-PHX-01", "cash_in", 4000.00)
    add(3, 5.0, "C901", "Jordan Sampleton", "K-TUC-02", "cash_in", 3800.00)
    add(3, 9.0, "C901", "Jordan Sampleton", "K-TUC-02", "cash_in", 2900.00)
    # 3. Cash in and cash out each under $10,000. Not aggregated together.
    add(3, 3.0, "C902", "Riley Demo", "K-DAL-06", "cash_in", 6000.00)
    add(3, 6.0, "C902", "Riley Demo", "K-DAL-06", "cash_out", 5500.00)
    # 4. Exactly $10,000: not a CTR (must be MORE than $10,000).
    add(3, 4.0, "C903", "Casey Fakerson", "K-LAX-07", "cash_in", 10000.00)
    # 5. GTO ZIP transactions in the $1,000 to $10,000 range.
    add(3, 1.0, "C904", "Morgan Mockley", "K-ELP-03", "cash_in", 2500.00)
    add(3, 7.0, "C905", "Quinn Placeholder", "K-LRD-04", "cash_in", 1000.00)
    # 6. Exactly $10,000 in a GTO ZIP: the GTO covers it.
    add(3, 8.0, "C906", "Rowan Synthia", "K-ABQ-05", "cash_in", 10000.00)
    # 7. Same amount outside a GTO ZIP: nothing to file.
    add(3, 8.5, "C907", "Skyler Notreal", "K-PHX-01", "cash_in", 2500.00)
    # 8. Structuring lead near the CTR line, across three days.
    add(1, 3.0, "C908", "Harper Demo", "K-DAL-06", "cash_in", 9500.00)
    add(2, 3.5, "C908", "Harper Demo", "K-DAL-06", "cash_in", 9800.00)
    add(3, 2.5, "C908", "Harper Demo", "K-PHX-01", "cash_in", 9700.00)
    # 9. Structuring lead near the GTO line, inside a covered ZIP.
    add(3, 1.0, "C909", "Emerson Testwell", "K-ELP-03", "cash_in", 950.00)
    add(3, 4.0, "C909", "Emerson Testwell", "K-ELP-03", "cash_in", 975.00)
    add(3, 10.0, "C909", "Emerson Testwell", "K-ELP-03", "cash_in", 990.00)

    rows.sort(key=lambda r: r["timestamp"])
    return rows


def write(rows: list[dict], path: Path = OUT) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)


if __name__ == "__main__":
    data = build()
    write(data)
    print(f"Wrote {len(data)} synthetic transactions to {OUT.relative_to(ROOT)}")
