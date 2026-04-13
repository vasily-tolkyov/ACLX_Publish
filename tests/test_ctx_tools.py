from __future__ import annotations

import unittest

from ctx.tool_summary import summarize_bash, summarize_file_read


class ToolSummaryTests(unittest.TestCase):
    def test_summarize_bash_classifies_test_commands(self) -> None:
        summary = summarize_bash("python -m pytest -q", "2 passed", 0)
        self.assertEqual(summary.kind, "test")
        self.assertIn("rc=0", summary.summary)

    def test_summarize_file_read_classifies_python_files(self) -> None:
        summary = summarize_file_read("demo.py", "def run():\n    return True\n")
        self.assertEqual(summary.kind, "py")
        self.assertIn("demo.py", summary.summary)


if __name__ == "__main__":
    unittest.main()
