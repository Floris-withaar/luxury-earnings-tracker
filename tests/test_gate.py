"""Tests for the data gate, the download guards and the full flow. No network, no API key."""
import copy
import json
import unittest
from datetime import date
from unittest import mock

from pipeline import fetch, model, run, validate
from pipeline.common import COMPANIES, WATCHLIST, load

from tests.support import FIXTURE, FakeClient, TempRepoCase
from tests.test_pipeline import ANSWER, RELEASE


def dataset():
    return copy.deepcopy(load(FIXTURE))


def company(data, cid):
    return next(c for c in data["companies"] if c["id"] == cid)


class GateTests(unittest.TestCase):
    def test_the_published_dataset_passes(self):
        result = validate.validate(load(COMPANIES), load(WATCHLIST), today=date(2026, 11, 16))
        self.assertEqual(result["errors"], [])
        self.assertGreater(result["figures"], 90)

    def test_built_files_match_the_dataset(self):
        self.assertEqual(validate.check_built(load(COMPANIES)), [])

    def test_figure_without_a_source_is_an_error(self):
        data = dataset()
        company(data, "hermes")["series"]["2026Q3"]["s"] = 99
        self.assertTrue(any("Hermès" in e and "no valid source" in e for e in validate.validate(data)["errors"]))

    def test_impossible_growth_is_an_error(self):
        data = dataset()
        company(data, "lvmh")["series"]["2026Q3"]["g"] = 400
        self.assertTrue(any("outside" in e for e in validate.validate(data)["errors"]))

    def test_malformed_quarter_and_stale_latest_are_errors(self):
        data = dataset()
        lvmh = company(data, "lvmh")
        lvmh["series"]["2026-Q4"] = dict(lvmh["series"]["2026Q3"])
        self.assertTrue(any("not a quarter" in e for e in validate.validate(data)["errors"]))
        data = dataset()
        data["latest"] = "2026Q2"
        self.assertTrue(any("latest is" in e for e in validate.validate(data)["errors"]))

    def test_unknown_region_bucket_and_duplicate_company_are_errors(self):
        data = dataset()
        regions = company(data, "kering")["regions"]["2026Q3"]
        regions["mars"] = dict(next(iter(regions.values())))
        data["companies"].append(copy.deepcopy(company(data, "prada")))
        errors = validate.validate(data)["errors"]
        self.assertTrue(any("not a region bucket" in e for e in errors))
        self.assertTrue(any("more than once" in e for e in errors))

    def test_group_outside_its_regions_is_a_warning(self):
        data = dataset()
        company(data, "hermes")["series"]["2026Q3"]["g"] = 30
        result = validate.validate(data)
        self.assertEqual(result["errors"], [])
        self.assertTrue(any("lies outside its regions" in w for w in result["warnings"]))

    def test_large_swing_and_gap_are_warnings(self):
        data = dataset()
        moncler = company(data, "moncler")
        moncler["series"]["2026Q3"]["g"] = -40
        del company(data, "prada")["series"]["2026Q1"]
        warnings = validate.validate(data)["warnings"]
        self.assertTrue(any("Moncler" in w and "moved" in w for w in warnings))
        self.assertTrue(any("Prada" in w and "no figure between" in w for w in warnings))

    def test_a_quarter_the_company_never_reports_alone_is_not_a_gap(self):
        data = dataset()
        del company(data, "hermes")["series"]["2026Q2"]
        company(data, "hermes")["regions"].pop("2026Q2", None)
        watchlist = {"companies": [{"id": c["id"], "name": c["name"], "ir_domain": "example.com"} for c in data["companies"]]}
        gaps = lambda: [w for w in validate.validate(data, watchlist, today=date(2026, 11, 1))["warnings"] if "no figure between" in w]
        self.assertEqual(len(gaps()), 1)
        next(e for e in watchlist["companies"] if e["id"] == "hermes")["skip_quarters"] = [2]
        self.assertEqual(gaps(), [])
        del company(data, "hermes")["series"]["2026Q1"]          # a first-quarter hole is still a fault
        company(data, "hermes")["regions"].pop("2026Q1", None)
        self.assertEqual(len(gaps()), 1)

    def test_a_checked_swing_is_not_flagged_again(self):
        data = dataset()
        company(data, "hermes")["series"]["2026Q3"]["g"] = 40
        swings = lambda: [w for w in validate.validate(data)["warnings"] if "Hermès: growth moved" in w]
        self.assertEqual(len(swings()), 1)
        company(data, "hermes")["series"]["2026Q3"]["checked"] = "Checked against the release."
        self.assertEqual(swings(), [])

    def test_grouping_file_is_checked(self):
        data = dataset()
        company(data, "lvmh")["segments"]["2026Q3"].append({"name": "Brand new line", "g": 3})
        self.assertTrue(any("Brand new line" in w for w in validate.validate(data)["warnings"]))
        errors, warnings = [], []
        validate.check_taxonomy(data["companies"], {"industries": [{"id": "goods"}], "companies": {"lvmh": {"industry": "boats"}},
                                                     "categories": [{"id": "x"}], "segments": {"lvmh": {"Wine": "y"}}}, errors, warnings)
        self.assertEqual(len(errors), 2)
        self.assertTrue(any("grouped with the first industry" in w for w in warnings))

    def test_stale_company_is_a_warning(self):
        warnings = validate.validate(load(FIXTURE), load(WATCHLIST), today=date(2027, 6, 1))["warnings"]
        self.assertTrue(any("LVMH" in w and "expected" in w for w in warnings))
        fresh = validate.validate(load(FIXTURE), load(WATCHLIST), today=date(2026, 11, 16))["warnings"]
        self.assertFalse(any("expected" in w for w in fresh))

    def test_company_missing_from_the_watchlist_is_a_warning(self):
        data = dataset()
        newcomer = copy.deepcopy(company(data, "prada"))
        newcomer.update(id="newco", name="Newco")
        data["companies"].append(newcomer)
        warnings = validate.validate(data, load(WATCHLIST), today=date(2026, 11, 16))["warnings"]
        self.assertTrue(any("Not on the watchlist" in w and "Newco" in w for w in warnings))

    def test_press_figures_are_counted(self):
        self.assertTrue(any("press reports" in w for w in validate.validate(load(FIXTURE))["warnings"]))


class FetchGuardTests(unittest.TestCase):
    def setUp(self):
        self.domains = fetch.allowlist(load(WATCHLIST))

    def test_company_sites_and_wires_are_trusted(self):
        self.assertTrue(fetch.is_trusted("https://www.lvmh.com/en/publications/q3", self.domains))
        self.assertTrue(fetch.is_trusted("https://assets.finance.hermes.com/s3fs-public/x.pdf", self.domains))
        self.assertTrue(fetch.is_trusted("https://www.globenewswire.com/news-release/2026/x.html", self.domains))

    def test_a_company_s_own_document_store_can_be_listed(self):
        self.assertTrue(fetch.is_trusted("https://lvmh-com.cdn.prismic.io/lvmh-com/x_Presentation.pdf", self.domains))
        self.assertFalse(fetch.is_trusted("https://other-company.cdn.prismic.io/x.pdf", self.domains))
        self.assertFalse(fetch.is_trusted("https://prismic.io/x.pdf", self.domains))

    def test_lookalikes_news_sites_and_plain_http_are_not(self):
        for url in ["https://lvmh.com.evil.example/q3.pdf", "https://evil-lvmh.com/q3.pdf", "https://notlvmh.com/x",
                    "https://www.reuters.com/business/lvmh", "http://www.lvmh.com/q3.pdf", "ftp://www.lvmh.com/q3.pdf",
                    "https://example.com/?u=https://www.lvmh.com/"]:
            self.assertFalse(fetch.is_trusted(url, self.domains), url)

    def test_private_and_local_addresses_are_refused(self):
        for url in ["http://127.0.0.1/x", "http://localhost:8000/x", "http://169.254.169.254/latest/meta-data/", "http://10.0.0.5/x",
                    "http://192.168.1.1/", "http://[::1]/x", "file:///etc/passwd", "http://printer.local/x", "https:///nohost"]:
            with self.assertRaises(fetch.UntrustedSource, msg=url):
                fetch.check_public(url)

    def test_hostname_that_resolves_to_a_private_address_is_refused(self):
        with mock.patch("socket.getaddrinfo", return_value=[(2, 1, 6, "", ("10.1.2.3", 0))]):
            with self.assertRaises(fetch.UntrustedSource):
                fetch.check_public("https://internal.example.com/x")
        with mock.patch("socket.getaddrinfo", return_value=[(2, 1, 6, "", ("93.184.216.34", 0))]):
            fetch.check_public("https://example.com/x")

    def test_redirect_to_a_private_address_is_refused(self):
        hop = mock.Mock(is_redirect=True, status_code=302, headers={"location": "http://169.254.169.254/latest/"})
        with mock.patch("socket.getaddrinfo", return_value=[(2, 1, 6, "", ("93.184.216.34", 0))]), mock.patch("requests.get", return_value=hop) as get:
            with self.assertRaises(fetch.UntrustedSource):
                fetch.fetch_text("https://example.com/release.pdf")
        self.assertEqual(get.call_count, 1)
        self.assertFalse(get.call_args.kwargs["allow_redirects"])


class FlowTests(TempRepoCase):
    """One saved release goes through every step and ends up in the file the website reads."""

    def source(self):
        return {"url": "https://www.burberryplc.com/q2.pdf", "title": "Second quarter trading update", "calendar_quarter": "2026Q3"}

    def test_release_to_site_data(self):
        data = load(run.COMPANIES)
        result = run.process_release(data, "Burberry", RELEASE, self.source(), client=FakeClient(ANSWER), company_id=None, apply=True)
        self.assertEqual(result["status"], "merged", result)
        self.assertEqual(result["checks"], "6/6")
        run.save(run.COMPANIES, data)
        run.rebuild(data, use_llm=False)

        site = json.loads((self.root / "site" / "data.json").read_text())
        burberry = next(c for c in site["companies"] if c["id"] == "burberry-group")
        self.assertEqual(burberry["series"]["2026Q3"]["g"], 4)
        self.assertEqual(burberry["regions"]["2026Q3"]["japan"]["v"], 9)
        self.assertEqual(burberry["sources"][burberry["series"]["2026Q3"]["s"]]["url"], "https://www.burberryplc.com/q2.pdf")
        self.assertEqual(len(site["model"]["2026Q3"]["companies"]), 7)
        self.assertEqual(site["model"]["2026Q3"]["peer"]["median"], model.compute(data)["2026Q3"]["peer"]["median"])
        self.assertIn("burberry-group", site["notes"]["2026Q3"]["companies"])
        self.assertEqual(site["meta"]["quality"]["errors"], 0)
        # The six original companies are untouched and every check still passes.
        before = {c["id"]: c for c in load(FIXTURE)["companies"]}
        for c in site["companies"]:
            if c["id"] in before:
                self.assertEqual(c, before[c["id"]])
        self.assertEqual(validate.validate(data)["errors"] + validate.check_built(data), [])
        self.assertNotIn("99", json.dumps(burberry))   # the instruction planted in the release had no effect

    def test_untrusted_source_is_never_merged(self):
        data = load(run.COMPANIES)
        result = run.process_release(data, "Burberry", RELEASE, self.source(), client=FakeClient(ANSWER), company_id=None, apply=True, trusted=False)
        self.assertEqual(result["status"], "needs review")
        self.assertTrue(any("allowlist" in f for f in result["flags"]))
        self.assertEqual(len(data["companies"]), 6)

    def test_draft_that_breaks_the_gate_is_not_merged(self):
        text = RELEASE.replace("grew 4%", "grew 400%")
        answer = copy.deepcopy(ANSWER)
        answer["group"].update(growth_pct=400, quote="Comparable store sales grew 400% in the quarter")
        data = load(run.COMPANIES)
        result = run.process_release(data, "Burberry", text, self.source(), client=FakeClient(answer), company_id=None, apply=True)
        self.assertNotEqual(result["status"], "merged", result)
        self.assertEqual(len(data["companies"]), 6)

    def test_gate_has_the_last_word_on_a_merge(self):
        data = load(run.COMPANIES)
        blocked = {"errors": ["Burberry Group 2026Q3: group growth has no valid source."], "warnings": [], "figures": 0, "companies": 0}
        with mock.patch.object(validate, "validate", return_value=blocked):
            result = run.process_release(data, "Burberry", RELEASE, self.source(), client=FakeClient(ANSWER), company_id=None, apply=True)
        self.assertEqual(result["status"], "blocked by the data gate")
        self.assertEqual(len(data["companies"]), 6)
        self.assertFalse(json.loads((self.root / "data" / "review" / "burberry-group-2026Q3.json").read_text())["auto_merge"])

    def test_rebuild_without_new_data_changes_nothing(self):
        data = load(run.COMPANIES)
        run.rebuild(data, use_llm=False)
        first = json.loads((self.root / "site" / "data.json").read_text())
        run.rebuild(data, use_llm=False)
        second = json.loads((self.root / "site" / "data.json").read_text())
        self.assertEqual(first, second)


if __name__ == "__main__":
    unittest.main()
