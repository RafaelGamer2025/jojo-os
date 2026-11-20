from __future__ import annotations

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class GitHubSenderBatchTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.script = (ROOT / "ENVIAR_ARQUIVO_GITHUB.bat").read_text(encoding="utf-8").lower()

    def test_stages_only_selected_relative_file(self) -> None:
        self.assertIn('git -c "%root%" add -- "%rel%"', self.script)
        self.assertIn('git -c "%root%" diff --cached --quiet', self.script)
        self.assertNotIn("add -a", self.script)
        self.assertNotIn("add --all", self.script)

    def test_push_is_normal_current_branch_push_without_force(self) -> None:
        self.assertIn('git -c "%root%" push origin head', self.script)
        self.assertNotIn("--force", self.script)
        self.assertNotIn("push -f", self.script)

    def test_remote_must_be_github_and_is_not_echoed(self) -> None:
        self.assertIn("github\\.com", self.script)
        self.assertNotIn("echo %remote%", self.script)
        self.assertIn("$env:jojo_git_remote", self.script)

    def test_no_access_token_is_embedded(self) -> None:
        self.assertIn("git credential manager", self.script)
        self.assertNotRegex(self.script, r"gh[pousr]_[a-z0-9]{20,}")
        self.assertNotIn("github_pat_", self.script)


if __name__ == "__main__":
    unittest.main(verbosity=2)
