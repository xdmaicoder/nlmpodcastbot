"""Unit tests for title validation and extraction logic."""

import unittest
from pathlib import Path
from services.antigravity_runner import is_valid_title, build_pipeline_prompt


class TestTitleExtraction(unittest.TestCase):
    def test_is_valid_title(self):
        # Invalid titles
        self.assertFalse(is_valid_title(None))
        self.assertFalse(is_valid_title(""))
        self.assertFalse(is_valid_title("   "))
        self.assertFalse(is_valid_title("Untitled notebook"))
        self.assertFalse(is_valid_title("untitled notebook"))
        self.assertFalse(is_valid_title("UNTITLED NOTEBOOK"))
        self.assertFalse(is_valid_title("`Untitled notebook`"))
        self.assertFalse(is_valid_title("《Untitled notebook》"))
        self.assertFalse(is_valid_title("untitled"))
        self.assertFalse(is_valid_title("无标题"))
        self.assertFalse(is_valid_title("无标题笔记本"))
        self.assertFalse(is_valid_title("未命名笔记本"))

        # Valid titles
        self.assertTrue(is_valid_title("2027年最赚钱的AI创业方向"))
        self.assertTrue(is_valid_title("AI 架构演进全解析"))
        self.assertTrue(is_valid_title("NotebookLM 播客速递"))

    def test_build_pipeline_prompt_without_custom_title(self):
        prompt = build_pipeline_prompt(
            title=None,
            sources=["https://example.com/article"],
            output_dir=Path("/tmp/outputs"),
        )
        # Should not instruct to name it Untitled notebook or output Untitled notebook in step 1
        self.assertIn("notebook_create()", prompt)
        self.assertIn("notebook_get", prompt)
        self.assertIn("绝对不要输出任何标题", prompt)

    def test_build_pipeline_prompt_with_custom_title(self):
        prompt = build_pipeline_prompt(
            title="自定义大模型实战",
            sources=["https://example.com/article"],
            output_dir=Path("/tmp/outputs"),
        )
        self.assertIn('notebook_create(title="自定义大模型实战")', prompt)
        self.assertIn('{"title": "自定义大模型实战"}', prompt)

    def test_extract_title_from_stdout_lines(self):
        # Simulate realistic stdout where initial line had Untitled notebook and later line had the real title
        raw_stdout_lines = [
            'root agent idle; waiting up to 35m0s for 1 background task(s)',
            '```json',
            '{"title": "Untitled notebook"}',
            '```',
            'Step 6: calling notebook_get...',
            '{"title": "2027年最赚钱的AI创业方向"}',
            '- **自动生成标题**: `2027年最赚钱的AI创业方向`',
            'All steps done.',
        ]
        
        # Reproduction of runner extraction logic
        notebooklm_title = None
        import re, json
        for line in raw_stdout_lines:
            stripped = line.strip()
            if not stripped:
                continue
            json_candidates = []
            if stripped[0] in "{[":
                json_candidates.append(stripped)
            else:
                match = re.search(r'\{[^{}]*"title"[^{}]*\}', stripped)
                if match:
                    json_candidates.append(match.group(0))

            for cand_json in json_candidates:
                try:
                    parsed = json.loads(cand_json)
                    if isinstance(parsed, dict) and isinstance(parsed.get("title"), str):
                        cand_title = parsed["title"].strip()
                        if is_valid_title(cand_title):
                            notebooklm_title = cand_title
                except json.JSONDecodeError:
                    continue

        self.assertEqual(notebooklm_title, "2027年最赚钱的AI创业方向")


if __name__ == "__main__":
    unittest.main()
