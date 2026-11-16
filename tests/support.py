"""Shared test helpers: a stand-in for the API client and a throwaway copy of the repository's data."""
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from pipeline import llm, run, validate
from pipeline.common import COMPANIES


def reply(text: str = "", stop: str = "end_turn"):
    """One API response. Use stop="max_tokens" for an answer that was cut off."""
    usage = SimpleNamespace(input_tokens=1000, output_tokens=200, server_tool_use=SimpleNamespace(web_search_requests=0))
    content = [SimpleNamespace(type="thinking", thinking="")] + ([SimpleNamespace(type="text", text=text)] if text else [])
    return SimpleNamespace(stop_reason=stop, usage=usage, content=content)


class FakeClient:
    """Stands in for anthropic.Anthropic(). Returns whatever answers it was given, in order."""

    def __init__(self, *answers):
        self.answers, self.calls = list(answers), []
        self.messages = self

    def create(self, **kwargs):
        self.calls.append(kwargs)
        answer = self.answers.pop(0)
        if isinstance(answer, SimpleNamespace):
            return answer
        text = answer if isinstance(answer, str) else json.dumps(answer)
        usage = SimpleNamespace(input_tokens=1000, output_tokens=200, server_tool_use=SimpleNamespace(web_search_requests=2 if kwargs.get("tools") else 0))
        return SimpleNamespace(stop_reason="end_turn", usage=usage, content=[SimpleNamespace(type="text", text=text)])


class TempRepoCase(unittest.TestCase):
    """Points the pipeline at a temporary copy of the dataset, so a test can run whole commands."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        (root / "data" / "review").mkdir(parents=True)
        (root / "site").mkdir()
        (root / "data" / "companies.json").write_text(Path(COMPANIES).read_text(encoding="utf-8"), encoding="utf-8")
        paths = dict(DATA=root / "data", COMPANIES=root / "data" / "companies.json", DERIVED=root / "data" / "derived.json",
                     COMMENTARY=root / "data" / "commentary.json", REVIEW=root / "data" / "review", SITE=root / "site",
                     RUN_LOG=root / "data" / "run_log.json", EVAL=root / "data" / "eval.json")
        self.patches = [mock.patch.multiple(run, **paths), mock.patch.multiple(validate, DERIVED=paths["DERIVED"], SITE=paths["SITE"])]
        for p in self.patches:
            p.start()
        self.root = root
        llm.USAGE.clear()

    def tearDown(self):
        for p in self.patches:
            p.stop()
        self.tmp.cleanup()

    def read(self, relative: str):
        return json.loads((self.root / relative).read_text(encoding="utf-8"))
