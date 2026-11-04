"""Watch the Federal Register for new or reissued FinCEN GTOs.

When a new order shows up, this script:
  1. adds it to data/gto_orders.csv with status "needs review";
  2. pulls the order's text and drafts a proposed ZIP list in
     data/proposed/gto_zips_<document>.csv;
  3. prints which ZIPs would be added or dropped compared with the
     current list.

It never changes data/gto_zips.csv on its own. A person checks the order
and approves the new list, because a wrong ZIP list means missed filings
or filings that were never required.
"""

from __future__ import annotations

import csv
import re
import sys
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
ORDERS = ROOT / "data" / "gto_orders.csv"
ZIPS = ROOT / "data" / "gto_zips.csv"
PROPOSED = ROOT / "data" / "proposed"

API = "https://www.federalregister.gov/api/v1/documents.json"
PARAMS = {
    "conditions[agencies][]": "financial-crimes-enforcement-network",
    "conditions[term]": '"geographic targeting order"',
    "order": "newest",
    "per_page": "20",
    "fields[]": ["document_number", "title", "publication_date", "html_url", "raw_text_url"],
}
HEADERS = {"User-Agent": "ctr-gto-monitor/1.0 (public-data research script)"}

ORDER_COLUMNS = ["document_number", "publication_date", "title", "url", "status", "notes"]
ZIP_RE = re.compile(r"(?<!\d)(\d{5})(?!\d)")


def known_orders() -> dict[str, dict]:
    with ORDERS.open(newline="", encoding="utf-8") as f:
        return {r["document_number"]: r for r in csv.DictReader(f)}


def current_zips() -> set[str]:
    with ZIPS.open(newline="", encoding="utf-8") as f:
        return {r["zip"] for r in csv.DictReader(f)}


def is_msb_gto(doc: dict) -> bool:
    """Real-estate GTOs exist too; only keep MSB / cash orders."""
    title = (doc.get("title") or "").lower()
    return "geographic targeting order" in title and ("money services" in title or "msb" in title)


def extract_zips(text: str) -> list[str]:
    """ZIP-looking numbers that appear after the order first says 'ZIP'."""
    start = text.lower().find("zip")
    if start == -1:
        return []
    found = []
    for z in ZIP_RE.findall(text[start:]):
        # Federal Register boilerplate includes other 5-digit numbers (FR
        # page numbers, CFR parts). ZIPs in this order's region start 7-8.
        if z[0] in "78" and z not in found:
            found.append(z)
    return found


def append_order(doc: dict) -> None:
    with ORDERS.open("a", newline="", encoding="utf-8") as f:
        csv.DictWriter(f, fieldnames=ORDER_COLUMNS).writerow({
            "document_number": doc["document_number"],
            "publication_date": doc.get("publication_date", ""),
            "title": doc.get("title", ""),
            "url": doc.get("html_url", ""),
            "status": "needs review",
            "notes": "Found by gto_watch. Confirm terms and ZIPs before updating gto_zips.csv.",
        })


def write_proposed(doc_number: str, zips: list[str]) -> Path:
    PROPOSED.mkdir(parents=True, exist_ok=True)
    path = PROPOSED / f"gto_zips_{doc_number}.csv"
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["zip"])
        for z in sorted(zips):
            w.writerow([z])
    return path


def run() -> int:
    resp = requests.get(API, params=PARAMS, headers=HEADERS, timeout=30)
    resp.raise_for_status()
    docs = [d for d in resp.json().get("results", []) if is_msb_gto(d)]
    known = known_orders()
    new = [d for d in docs if d["document_number"] not in known]
    if not new:
        print(f"No new MSB GTOs. Checked {len(docs)} matching documents.")
        return 0

    have = current_zips()
    for doc in new:
        append_order(doc)
        print(f"NEW GTO: {doc['document_number']} ({doc.get('publication_date')}) {doc.get('title')}")
        print(f"  {doc.get('html_url')}")
        if doc.get("raw_text_url"):
            text = requests.get(doc["raw_text_url"], headers=HEADERS, timeout=30).text
            zips = extract_zips(text)
            if zips:
                path = write_proposed(doc["document_number"], zips)
                added = sorted(set(zips) - have)
                dropped = sorted(have - set(zips))
                print(f"  Draft ZIP list: {path.relative_to(ROOT)} ({len(zips)} ZIPs)")
                print(f"  Would add {len(added)}: {' '.join(added[:40])}{' ...' if len(added) > 40 else ''}")
                print(f"  Would drop {len(dropped)}: {' '.join(dropped[:40])}{' ...' if len(dropped) > 40 else ''}")
            else:
                print("  No ZIPs found in the text; review the order manually.")
    return 0


if __name__ == "__main__":
    sys.exit(run())
