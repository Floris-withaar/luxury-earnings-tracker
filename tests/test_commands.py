"""Whole commands, run the way the workflows run them, with a stand-in API client and no network."""
import copy
from types import SimpleNamespace
from unittest import mock

from pipeline import fetch, interpret, llm, model, run, validate
from pipeline.common import load

from tests.support import FIXTURE, FakeClient, TempRepoCase, reply

Q4_RELEASE = ("LVMH Moët Hennessy Louis Vuitton, fourth quarter 2026 revenue.\n"
              "Organic revenue growth was 2% in the fourth quarter.\n" + "The Group continued to invest in its Maisons. " * 20)
Q4_ANSWER = {"company": "LVMH", "calendar_quarter": "2026Q4", "period_label": "Q4 2026", "basis": "Organic",
             "group": {"growth_pct": 2, "revenue_m": None, "currency": "EUR", "quote": "Organic revenue growth was 2% in the fourth quarter."},
             "regions": [], "segments": [], "guidance": {"text": None, "numeric": False}, "china": {"text": None}, "warnings": []}
FOUND = {"found": True, "url": "https://www.lvmh.com/q4-2026.pdf", "title": "Q4 2026 revenue", "publisher": "LVMH",
         "published": "2027-01-26", "calendar_quarter": "2026Q4", "alternates": [], "why": "Newer than 2026Q3."}
NOTE = {"note": "Growth was 2% in the quarter.", "themes": ["Steady growth"], "watch": "Check the regional split."}
WATCH = {"companies": [{"id": "lvmh", "name": "LVMH", "ir_domain": "lvmh.com", "first_check_days": 10, "lags": {}}]}


class UpdateCommandTests(TempRepoCase):
    def update(self, client, text=Q4_RELEASE, fetch_error=None, force=True):
        real_load = run.load
        with mock.patch.object(run.llm, "get_client", return_value=client), \
             mock.patch.object(run, "load", side_effect=lambda path, default=None: WATCH if path == run.WATCHLIST else real_load(path, default)), \
             mock.patch.object(fetch, "fetch_text", side_effect=fetch_error, return_value=text) as fetched:
            code = run.cmd_update(SimpleNamespace(company=None, apply=True, force=force))
        return code, fetched

    def test_new_release_is_merged_and_published(self):
        client = FakeClient(FOUND, Q4_ANSWER, NOTE)
        code, fetched = self.update(client)
        self.assertEqual(code, 0)
        fetched.assert_called_once_with("https://www.lvmh.com/q4-2026.pdf")
        data = self.read("data/companies.json")
        lvmh = next(c for c in data["companies"] if c["id"] == "lvmh")
        self.assertEqual(data["latest"], "2026Q4")
        self.assertEqual(lvmh["series"]["2026Q4"]["g"], 2)
        self.assertEqual(lvmh["sources"][lvmh["series"]["2026Q4"]["s"]]["url"], "https://www.lvmh.com/q4-2026.pdf")
        site = self.read("site/data.json")
        self.assertEqual(site["latest"], "2026Q4")
        self.assertEqual(site["notes"]["2026Q4"]["companies"]["lvmh"]["by"], llm.MODELS["interpret"])
        last = site["meta"]["runs"][-1]
        self.assertEqual(last["results"][0]["status"], "merged")
        self.assertEqual(sorted(last["usage"]["steps"]), ["extract", "interpret", "research"])
        self.assertEqual(validate.validate(data)["errors"] + validate.check_built(data), [])

    def test_nothing_is_searched_before_a_release_is_due(self):
        client = FakeClient()
        with mock.patch.object(run.research, "is_due", return_value=False):
            code, fetched = self.update(client, force=False)
        self.assertEqual((code, client.calls, fetched.call_count), (0, [], 0))
        self.assertEqual(self.read("data/run_log.json")[-1]["results"][0]["status"], "not due")

    def test_link_off_the_allowlist_is_not_downloaded(self):
        code, fetched = self.update(FakeClient(dict(FOUND, url="https://www.reuters.com/lvmh-q4")))
        self.assertEqual(fetched.call_count, 0)
        self.assertEqual(self.read("data/run_log.json")[-1]["results"][0]["status"], "source not on the allowlist")
        self.assertEqual(self.read("data/companies.json"), load(FIXTURE))

    def test_blocked_download_is_reported_with_its_reason(self):
        code, _ = self.update(FakeClient(FOUND), fetch_error=fetch.FetchFailed("www.lvmh.com answered HTTP 403"))
        result = self.read("data/run_log.json")[-1]["results"][0]
        self.assertEqual(result["status"], "could not fetch")
        self.assertIn("HTTP 403", result["detail"])
        self.assertEqual(self.read("data/companies.json"), load(FIXTURE))

    def test_cut_off_extraction_changes_nothing(self):
        code, _ = self.update(FakeClient(FOUND, reply(stop="max_tokens"), reply(stop="max_tokens")))
        result = self.read("data/run_log.json")[-1]["results"][0]
        self.assertEqual(result["status"], "error")
        self.assertIn("cut off", result["detail"])
        self.assertEqual(self.read("data/companies.json"), load(FIXTURE))


class EvalAndInterpretCommandTests(TempRepoCase):
    def test_eval_scores_what_it_could_read_and_says_what_it_could_not(self):
        hermes = next(c for c in load(FIXTURE)["companies"] if c["id"] == "hermes")
        series = hermes["series"]["2026Q3"]
        keys = {"asia": "asia_ex_japan", "japan": "japan", "europe": "europe", "americas": "americas", "me": "middle_east_other"}
        answer = {"company": "Hermès", "calendar_quarter": "2026Q3", "basis": "Constant FX", "group": {"growth_pct": series["g"], "quote": "x"},
                  "regions": [{"standard": keys[k], "label": cell["label"], "growth_pct": cell["v"], "quote": "x"}
                              for k, cell in hermes["regions"]["2026Q3"].items() if cell["s"] == series["s"]]}
        expected = 1 + len(answer["regions"])
        url = hermes["sources"][series["s"]]["url"]

        def fake_fetch(link):
            if link == url:
                return "release text"
            raise fetch.FetchFailed("the site answered HTTP 403")

        with mock.patch.object(run.llm, "get_client", return_value=FakeClient(answer)), mock.patch.object(fetch, "fetch_text", side_effect=fake_fetch):
            self.assertEqual(run.cmd_eval(SimpleNamespace()), 0)
        result = self.read("data/eval.json")
        self.assertEqual((result["hits"], result["total"]), (expected, expected))
        self.assertEqual((result["read"], result["releases"], len(result["skipped"])), (1, 6, 5))
        self.assertTrue(all("HTTP 403" in s for s in result["skipped"]))
        self.assertEqual(self.read("site/data.json")["meta"]["eval"]["read"], 1)

    def test_interpret_keeps_good_notes_and_explains_rejected_ones(self):
        invented = {"note": "Growth was 77% in the quarter.", "themes": [], "watch": ""}
        client = FakeClient({"note": "Asia was the weak spot this quarter.", "themes": ["Asia drag"], "watch": "Check Asia next quarter."},
                            invented, reply(stop="max_tokens"), reply(stop="max_tokens"))
        with mock.patch.object(run.llm, "get_client", return_value=client):
            self.assertEqual(run.cmd_interpret(SimpleNamespace()), 0)
        notes = self.read("data/commentary.json")["2026Q3"]["companies"]
        ids = list(notes)
        self.assertEqual(notes[ids[0]]["by"], llm.MODELS["interpret"])
        self.assertEqual(notes[ids[0]]["note"], "Asia was the weak spot this quarter.")
        self.assertEqual(notes[ids[1]]["by"], "rules")
        self.assertIn("77", notes[ids[1]]["rejected"])
        self.assertIn("cut off", notes[ids[2]]["rejected"])
        self.assertTrue(all(notes[i]["by"] == "rules" and notes[i]["note"] for i in ids[1:]))
        log = self.read("data/run_log.json")[-1]
        self.assertIn("77", log["results"][1]["detail"])
        self.assertEqual(self.read("site/data.json")["notes"]["2026Q3"]["companies"][ids[0]]["note"], "Asia was the weak spot this quarter.")


class LimitTests(TempRepoCase):
    def test_cut_off_answer_is_retried_once_with_more_room(self):
        client = FakeClient(reply(stop="max_tokens"), reply('{"ok": true}'))
        self.assertEqual(llm.ask_json("x", step="interpret", client=client), {"ok": True})
        self.assertEqual([c["max_tokens"] for c in client.calls], [llm.LIMITS["interpret"], llm.LIMITS["interpret"] * 2])

    def test_cut_off_twice_is_an_error_even_if_the_text_parses(self):
        client = FakeClient(reply('{"ok": true}', stop="max_tokens"), reply('{"ok": true}', stop="max_tokens"))
        with self.assertRaises(llm.LLMCutOff):
            llm.ask_json("x", step="extract", client=client)
        self.assertLessEqual(client.calls[-1]["max_tokens"], llm.CEILING)

    def test_refusal_is_an_error(self):
        with self.assertRaises(llm.LLMRefused):
            llm.complete("x", step="extract", client=FakeClient(reply(stop="refusal")))

    def test_every_limit_leaves_room_for_thinking(self):
        self.assertTrue(all(limit >= 4000 for limit in llm.LIMITS.values()))
        client = FakeClient(reply("{}"), reply("{}"))
        llm.complete("x", step="interpret", client=client)
        llm.complete("x", step="extract", client=client)
        self.assertEqual(client.calls[0]["output_config"], {"effort": llm.EFFORT["interpret"]})
        self.assertNotIn("output_config", client.calls[1])

    def test_period_names_are_not_treated_as_figures(self):
        payload = {"growth": 4.3, "note": "Nine-month growth of 5.5%"}
        self.assertEqual(interpret.ungrounded("In Q3 2026 growth was 4.3%, after 5.5% over 9M and H1 FY27.", payload), [])
        self.assertEqual(interpret.ungrounded("Growth was 12% in Q3.", payload), ["12"])


class LikeForLikeTests(TempRepoCase):
    def test_a_new_company_does_not_move_the_median_change(self):
        data = load(FIXTURE)
        before = model.compute(data)["2026Q3"]["peer"]
        newcomer = copy.deepcopy(data["companies"][0])
        newcomer.update(id="newco", name="Newco", series={"2026Q3": {"g": 40, "s": 0}}, regions={}, segments={})
        data["companies"].append(newcomer)
        after = model.compute(data)["2026Q3"]["peer"]
        self.assertEqual((after["n"], after["compared"]), (7, 6))
        self.assertNotEqual(after["median"], before["median"])                      # the level includes the newcomer
        self.assertEqual(after["median_like"], before["median"])                    # the change does not
        self.assertEqual(after["median_prev"], before["median_prev"])
        self.assertIn("6 companies that report both quarters", interpret.peer_lede("2026Q3", after))
        self.assertNotIn("report both quarters", interpret.peer_lede("2026Q3", before))


class StaleNoteTests(TempRepoCase):
    """A model note is tied to the exact figures it was written from."""

    def test_note_survives_a_rebuild_but_not_a_change_in_the_figures(self):
        client = FakeClient(*[{"note": "Asia was the weak spot this quarter.", "themes": [], "watch": ""}] * 6)
        with mock.patch.object(run.llm, "get_client", return_value=client):
            run.cmd_interpret(SimpleNamespace())
        data = load(run.COMPANIES)
        run.rebuild(data)
        notes = self.read("data/commentary.json")["2026Q3"]["companies"]
        self.assertTrue(all(n["by"] == llm.MODELS["interpret"] for n in notes.values()))

        kering = next(c for c in data["companies"] if c["id"] == "kering")
        kering["regions"]["2026Q3"]["japan"]["v"] = 9          # one figure changes for one company
        run.save(run.COMPANIES, data)
        run.rebuild(data)
        notes = self.read("data/commentary.json")["2026Q3"]["companies"]
        self.assertEqual(notes["kering"]["by"], "rules")
        self.assertNotEqual(notes["kering"]["note"], "Asia was the weak spot this quarter.")
        self.assertEqual(notes["richemont"]["by"], llm.MODELS["interpret"])   # companies whose figures did not change keep theirs

    def test_a_region_goes_by_the_company_s_own_name(self):
        metrics = model.compute(load(FIXTURE))["2026Q3"]["companies"]["moncler"]
        self.assertEqual(metrics["driver"]["name"], "Asia (APAC, Japan, Korea)")
