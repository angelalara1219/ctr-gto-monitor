import unittest
from datetime import date, datetime
from decimal import Decimal

from ctr_monitor import gto_watch, rules
from ctr_monitor.generate import build

DAY = date(2026, 10, 15)
GTO = {"79901"}


def t(i, amount, *, cust="C1", direction="cash_in", zip_code="85004", day=DAY, kiosk="K1"):
    return rules.Txn(f"T{i}", datetime.combine(day, datetime.min.time()), cust, "Test Person",
                     kiosk, zip_code, "XX", direction, Decimal(str(amount)))


class CTRTests(unittest.TestCase):
    def test_over_10k_single(self):
        flags = rules.ctr_flags([t(1, 10000.01)], DAY)
        self.assertEqual([f.rule for f in flags], ["CTR - single"])
        self.assertEqual(flags[0].due_date, "2026-10-30")

    def test_exactly_10k_is_not_a_ctr(self):
        self.assertEqual(rules.ctr_flags([t(1, 10000)], DAY), [])

    def test_aggregates_same_customer_same_day(self):
        flags = rules.ctr_flags([t(1, 6000, kiosk="K1"), t(2, 4500, kiosk="K2")], DAY)
        self.assertEqual(flags[0].rule, "CTR - aggregated")
        self.assertEqual(flags[0].total, Decimal("10500"))

    def test_cash_in_and_out_not_combined(self):
        txns = [t(1, 6000), t(2, 6000, direction="cash_out")]
        self.assertEqual(rules.ctr_flags(txns, DAY), [])

    def test_other_days_and_customers_ignored(self):
        txns = [t(1, 6000), t(2, 6000, cust="C2"), t(3, 6000, day=date(2026, 10, 14))]
        self.assertEqual(rules.ctr_flags(txns, DAY), [])


class GTOTests(unittest.TestCase):
    def test_range_is_inclusive_1000_to_10000(self):
        txns = [t(1, 999.99, zip_code="79901"), t(2, 1000, zip_code="79901"),
                t(3, 10000, zip_code="79901"), t(4, 10000.01, zip_code="79901")]
        flags = rules.gto_flags(txns, DAY, GTO)
        self.assertEqual([f.txn_ids[0] for f in flags], ["T2", "T3"])
        self.assertEqual(flags[0].due_date, "2026-11-14")

    def test_outside_covered_zip_ignored(self):
        self.assertEqual(rules.gto_flags([t(1, 2500, zip_code="85004")], DAY, GTO), [])

    def test_zip_list_respects_effective_dates(self):
        self.assertIn("79901", rules.load_gto_zips(on=date(2026, 10, 15)))
        self.assertEqual(rules.load_gto_zips(on=date(2027, 3, 2)), set())
        self.assertNotIn("85004", rules.load_gto_zips())


class StructuringTests(unittest.TestCase):
    def test_near_ctr_pattern_across_days(self):
        txns = [t(1, 9500, day=date(2026, 10, 13)), t(2, 9800)]
        flags = rules.structuring_flags(txns, DAY, GTO)
        self.assertEqual([f.rule for f in flags], ["Structuring lead - CTR"])

    def test_needs_activity_today(self):
        txns = [t(1, 9500, day=date(2026, 10, 13)), t(2, 9800, day=date(2026, 10, 14))]
        self.assertEqual(rules.structuring_flags(txns, DAY, GTO), [])

    def test_near_gto_only_counts_in_covered_zips(self):
        covered = [t(1, 950, zip_code="79901"), t(2, 990, zip_code="79901")]
        elsewhere = [t(3, 950, cust="C2"), t(4, 990, cust="C2")]
        flags = rules.structuring_flags(covered + elsewhere, DAY, GTO)
        self.assertEqual([(f.rule, f.customer_id) for f in flags], [("Structuring lead - GTO", "C1")])


class SampleDataTests(unittest.TestCase):
    def test_sample_day_flags_the_planted_scenarios(self):
        import csv, io
        rows = build()
        buf = io.StringIO()
        w = csv.DictWriter(buf, fieldnames=list(rows[0]))
        w.writeheader(); w.writerows(rows)
        txns = [rules.Txn(r["txn_id"], datetime.fromisoformat(r["timestamp"]), r["customer_id"],
                          r["customer_name"], r["kiosk_id"], r["kiosk_zip"], r["kiosk_state"],
                          r["direction"], Decimal(r["amount_usd"]))
                for r in csv.DictReader(io.StringIO(buf.getvalue()))]
        flags = rules.run_day(txns, DAY, rules.load_gto_zips(on=DAY))
        by_rule = {}
        for f in flags:
            by_rule.setdefault(f.rule, set()).add(f.customer_id)
        self.assertEqual(by_rule["CTR - single"], {"C900"})
        self.assertEqual(by_rule["CTR - aggregated"], {"C901"})
        self.assertEqual(by_rule["GTO"], {"C904", "C905", "C906"})
        self.assertEqual(by_rule["Structuring lead - CTR"], {"C908"})
        self.assertEqual(by_rule["Structuring lead - GTO"], {"C909"})


class WatcherTests(unittest.TestCase):
    def test_msb_filter(self):
        self.assertTrue(gto_watch.is_msb_gto({"title": "Geographic Targeting Order Imposing "
                                              "Recordkeeping and Reporting Requirements on Certain Money Services Businesses"}))
        self.assertFalse(gto_watch.is_msb_gto({"title": "Geographic Targeting Order: Real Estate Title Insurance"}))

    def test_extract_zips_skips_preamble_numbers(self):
        text = ("Federal Register Vol. 91 page 41234. 31 CFR 1010.370. "
                "covered ZIP Codes: El Paso County: 79901, 79902; Bernalillo: 87102. FR Doc 2026-18194")
        self.assertEqual(gto_watch.extract_zips(text), ["79901", "79902", "87102"])

    def test_current_zip_file_is_clean(self):
        zips = gto_watch.current_zips()
        self.assertEqual(len(zips), 304)
        self.assertTrue(all(len(z) == 5 and z.isdigit() for z in zips))


if __name__ == "__main__":
    unittest.main()
