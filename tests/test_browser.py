from __future__ import annotations

import ast
import json
import subprocess
import unittest
from pathlib import Path
from unittest.mock import patch

from ui.browser import (
    ABOUT_BLANK,
    BrowserInputError,
    browser_process_command,
    is_allowed_navigation,
    launch_browser_process,
    normalize_browser_url,
    qt_webengine_available,
)


class BrowserUrlTests(unittest.TestCase):
    def test_adds_https_to_a_host(self):
        self.assertEqual(normalize_browser_url("example.test/path"), "https://example.test/path")

    def test_accepts_http_https_and_about_blank(self):
        self.assertEqual(normalize_browser_url("http://127.0.0.1:8000/"), "http://127.0.0.1:8000/")
        self.assertEqual(normalize_browser_url("https://example.test"), "https://example.test")
        self.assertEqual(normalize_browser_url(ABOUT_BLANK), ABOUT_BLANK)

    def test_rejects_non_web_schemes_and_malformed_hosts(self):
        for value in ("file:///tmp/page", "ftp://example.test", "javascript:alert(1)", "http://", "https://:bad"):
            with self.subTest(value=value), self.assertRaises(BrowserInputError):
                normalize_browser_url(value)

    def test_rejects_whitespace_and_control_characters(self):
        for value in ("https://example.test/a b", "https://example.test/\nnext"):
            with self.subTest(value=value), self.assertRaises(BrowserInputError):
                normalize_browser_url(value)

    def test_about_blank_can_be_rejected_for_external_navigation(self):
        with self.assertRaises(BrowserInputError):
            normalize_browser_url(ABOUT_BLANK, allow_about_blank=False)

    def test_navigation_policy_matches_allowed_schemes(self):
        self.assertTrue(is_allowed_navigation(ABOUT_BLANK))
        self.assertTrue(is_allowed_navigation("https://example.test"))
        self.assertFalse(is_allowed_navigation("file:///tmp/page"))
        self.assertFalse(is_allowed_navigation("mailto:user@example.test"))


class BrowserProcessTests(unittest.TestCase):
    def test_process_command_is_a_list_without_private_url(self):
        command = browser_process_command()
        self.assertIsInstance(command, list)
        self.assertEqual(command[-2:], ["-m", "ui.browser_qt"])
        self.assertNotIn("https://private.example/token", command)

    def test_launch_forwards_initial_url_through_stdin(self):
        class FakeStdin:
            def __init__(self):
                self.value = ""
                self.closed = False

            def write(self, text):
                self.value += text

            def close(self):
                self.closed = True

        class FakeProcess:
            def __init__(self):
                self.stdin = FakeStdin()

        process = FakeProcess()
        with patch("ui.browser.subprocess.Popen", return_value=process) as popen:
            launched = launch_browser_process("example.test/start")

        self.assertIs(launched, process)
        self.assertEqual(
            json.loads(process.stdin.value),
            {"url": "https://example.test/start"},
        )
        self.assertTrue(process.stdin.closed)
        self.assertEqual(popen.call_args.kwargs["stdin"], subprocess.PIPE)

    def test_qt_detection_does_not_require_the_optional_dependency(self):
        with patch("ui.browser.importlib.util.find_spec", side_effect=[None]):
            self.assertFalse(qt_webengine_available())

    def test_browser_launcher_does_not_call_webbrowser(self):
        source = Path("ui/browser.py").read_text(encoding="utf-8")
        tree = ast.parse(source)
        names = {
            node.func.attr
            for node in ast.walk(tree)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
        }
        self.assertNotIn("open", names)
        self.assertNotIn("open_new", names)
        self.assertNotIn("open_new_tab", names)
        self.assertNotIn("webbrowser", source)


if __name__ == "__main__":
    unittest.main(verbosity=2)
