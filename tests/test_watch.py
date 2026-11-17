"""The weekly watch: what counts as something a person should hear about."""
from datetime import date
from types import SimpleNamespace
from unittest import mock

from pipeline import fetch, run, watch
from pipeline.common import WATCHLIST, load

from tests.support import FIXTURE, FakeClient, TempRepoCase

QUIET = date(2026, 11, 16)     # nothing is due
LATE = date(2027, 6, 1)        # every company should have reported by now


def ok(url):
    return "ok", "HTTP 200"


class WatchTests(TempRepoCase):
    def setUp(self):
        super().setUp()
        run.rebuild(load(run.COMPANIES))
        self.review = mock.patch.object(watch, "REVIEW", self.root / "data" / "review")
        self.review.start()

    def tearDown(self):
        self.review.stop()
        super().tearDown()

    def test_a_healthy_dataset_raises_nothing(self):
        result = watch.watch(load(run.COMPANIES), load(WATCHLIST), today=QUIET, status=ok)
        self.assertEqual(result["alerts"], [])
        self.assertEqual(watch.markdown(result), "")

    def test_an_overdue_release_is_an_alert(self):
        result = watch.watch(load(run.COMPANIES), load(WATCHLIST), today=LATE, status=ok)
        self.assertTrue(any(a.startswith("Overdue: LVMH") for a in result["alerts"]))
        text = watch.markdown(result, run_url="https://example.com/run/1")
        self.assertIn("need a person", text)
        self.assertIn("https://example.com/run/1", text)

    def test_a_link_that_has_gone_is_an_alert_but_a_site_that_refuses_robots_is_not(self):
        data = load(run.COMPANIES)
        dead = data["companies"][0]["sources"][0]["url"]
        refusing = data["companies"][1]["sources"][0]["url"]

        def status(url):
            return ("gone", "HTTP 404") if url == dead else ("refused", "HTTP 403") if url == refusing else ("ok", "HTTP 200")

        alerts = watch.watch(data, load(WATCHLIST), today=QUIET, status=status)["alerts"]
        self.assertEqual(len(alerts), 1)
        self.assertIn("HTTP 404", alerts[0])
        self.assertIn(dead, alerts[0])

    def test_a_network_fault_is_not_mistaken_for_many_dead_links(self):
        result = watch.watch(load(run.COMPANIES), load(WATCHLIST), today=QUIET, status=lambda url: ("gone", "could not be resolved"))
        self.assertEqual(result["alerts"], [])
        self.assertTrue(any("link check" in n for n in result["notes"]))

    def test_a_draft_waiting_for_review_is_an_alert(self):
        (self.root / "data" / "review" / "burberry-2026Q4.json").write_text("{}")
        alerts = watch.watch(load(run.COMPANIES), load(WATCHLIST), today=QUIET, status=ok)["alerts"]
        self.assertEqual(alerts, ["Draft waiting for review: data/review/burberry-2026Q4.json"])

    def test_a_broken_dataset_is_an_alert(self):
        data = load(run.COMPANIES)
        data["companies"][0]["series"]["2026Q3"]["s"] = 99
        alerts = watch.watch(data, load(WATCHLIST), today=QUIET, links=False)["alerts"]
        self.assertTrue(any(a.startswith("Data gate error") for a in alerts))

    def test_standing_notes_do_not_raise_an_alert(self):
        result = watch.watch(load(FIXTURE), load(WATCHLIST), today=QUIET, links=False)
        self.assertTrue(any("press reports" in n for n in result["notes"]))
        self.assertEqual([a for a in result["alerts"] if "press" in a], [])

    def test_the_command_exits_10_and_writes_the_report_when_something_is_wrong(self):
        report = self.root / "watch.md"
        args = SimpleNamespace(report=report, also=None, no_links=True, run_url=None)
        self.assertEqual(run.cmd_watch(args), 0)
        self.assertEqual(report.read_text(), "")
        stuck = self.root / "stuck.txt"
        stuck.write_text("Update: Moncler: could not fetch. www.monclergroup.com answered HTTP 403\n")
        args.also = stuck
        self.assertEqual(run.cmd_watch(args), 10)
        self.assertIn("Moncler: could not fetch", report.read_text())

    def test_an_update_that_gets_stuck_says_so_in_its_report(self):
        found = {"found": True, "url": "https://www.lvmh.com/q4-2026.pdf", "calendar_quarter": "2026Q4", "alternates": [], "why": ""}
        report = self.root / "update-problems.txt"
        with mock.patch.object(run.llm, "get_client", return_value=FakeClient(found)), \
             mock.patch.object(fetch, "fetch_text", side_effect=fetch.FetchFailed("www.lvmh.com answered HTTP 403")):
            run.cmd_update(SimpleNamespace(company="lvmh", apply=True, force=True, report=report))
        text = report.read_text()
        self.assertIn("Update: LVMH: could not fetch", text)
        self.assertIn("HTTP 403", text)


class LinkStatusTests(TempRepoCase):
    def check(self, code=None, error=None):
        response = SimpleNamespace(status_code=code, close=lambda: None)
        with mock.patch("socket.getaddrinfo", return_value=[(2, 1, 6, "", ("93.184.216.34", 0))]), \
             mock.patch("requests.get", side_effect=error, return_value=response):
            return watch.link_status("https://www.example.com/release.pdf")[0]

    def test_only_a_missing_page_counts_as_gone(self):
        self.assertEqual(self.check(200), "ok")
        self.assertEqual(self.check(404), "gone")
        self.assertEqual(self.check(410), "gone")
        self.assertEqual(self.check(403), "refused")
        self.assertEqual(self.check(429), "refused")
        self.assertEqual(self.check(503), "unknown")
        self.assertEqual(self.check(error=TimeoutError()), "unknown")

    def test_a_name_that_no_longer_resolves_counts_as_gone(self):
        import socket
        with mock.patch("socket.getaddrinfo", side_effect=socket.gaierror()):
            self.assertEqual(watch.link_status("https://gone.example.com/x")[0], "gone")
