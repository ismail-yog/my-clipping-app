import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock

# Add project root to path
sys.path.append(str(Path(__file__).parent.parent.resolve()))

import config
from processor.seo import SEOMetadata, SEOGenerator

class TestSEOGenerator(unittest.TestCase):
    def setUp(self):
        self.seo = SEOGenerator()

    def test_seo_metadata_dataclass(self):
        meta = SEOMetadata(
            title="INSANE play by Shroud! 😱",
            description="Shroud clutched the 1v5. #shroud #twitch #gaming",
            tags=["shroud", "twitch", "gaming", "clutch"],
            hook_text="HE DID WHAT?!",
            thumbnail_prompt="UNBELIEVABLE",
            generated_by="ollama"
        )
        self.assertEqual(meta.title, "INSANE play by Shroud! 😱")
        self.assertEqual(meta.description, "Shroud clutched the 1v5. #shroud #twitch #gaming")
        self.assertEqual(meta.tags, ["shroud", "twitch", "gaming", "clutch"])
        self.assertEqual(meta.hook_text, "HE DID WHAT?!")
        self.assertEqual(meta.thumbnail_prompt, "UNBELIEVABLE")
        self.assertEqual(meta.generated_by, "ollama")

    def test_build_prompt(self):
        prompt = self.seo._build_prompt("kill 5 players", "Shroud", "joy", "twitch")
        self.assertIn("Shroud", prompt)
        self.assertIn("twitch", prompt)
        self.assertIn("joy", prompt)
        self.assertIn("kill 5 players", prompt)

    def test_parse_response_success(self):
        response_text = """
Some raw LLM text before JSON
{
  "title": "INSANE CLUTCH BY SHROUD! 😱",
  "description": "Watch Shroud pull off an insane 1v5 clutch in Valorant! #shroud #valorant #shorts",
  "tags": ["shroud", "valorant", "gaming", "clutch", "shorts"],
  "hook_text": "HE DID WHAT?!",
  "thumbnail_prompt": "UNBELIEVABLE"
}
Some raw LLM text after JSON
"""
        meta = self.seo._parse_response(response_text)
        self.assertIsNotNone(meta)
        self.assertEqual(meta.title, "INSANE CLUTCH BY SHROUD! 😱")
        self.assertEqual(meta.description, "Watch Shroud pull off an insane 1v5 clutch in Valorant! #shroud #valorant #shorts")
        self.assertEqual(meta.tags, ["shroud", "valorant", "gaming", "clutch", "shorts"])
        self.assertEqual(meta.hook_text, "HE DID WHAT?!")
        self.assertEqual(meta.thumbnail_prompt, "UNBELIEVABLE")
        self.assertEqual(meta.generated_by, "ollama")

    def test_parse_response_with_markdown_wrap(self):
        response_text = """
```json
{
  "title": "INSANE CLUTCH BY SHROUD! 😱",
  "description": "Watch Shroud pull off an insane 1v5 clutch in Valorant!",
  "tags": ["shroud", "valorant", "gaming", "clutch", "shorts"],
  "hook_text": "HE DID WHAT?!",
  "thumbnail_prompt": "UNBELIEVABLE"
}
```
"""
        meta = self.seo._parse_response(response_text)
        self.assertIsNotNone(meta)
        self.assertEqual(meta.title, "INSANE CLUTCH BY SHROUD! 😱")
        self.assertEqual(meta.generated_by, "ollama")

    def test_template_generate(self):
        meta = self.seo._template_generate("kill 5 players", "Shroud", "joy")
        self.assertEqual(meta.title, "JOY moment from Shroud!")
        self.assertEqual(meta.description, "kill 5 players...")
        self.assertIn("shroud", meta.tags)
        self.assertEqual(meta.hook_text, "WATCH THIS 👀")
        self.assertEqual(meta.thumbnail_prompt, "Shroud REACTS")
        self.assertEqual(meta.generated_by, "template")

    @patch('processor.seo.SEOGenerator._call_ollama')
    def test_generate_pipeline(self, mock_call_ollama):
        # 1. Test success with primary model
        mock_call_ollama.side_effect = lambda prompt, model: {
            "llama3": '{"title": "PRIMARY TITLE", "description": "desc", "tags": ["tag1"], "hook_text": "hook", "thumbnail_prompt": "thumb"}',
            "mistral": '{"title": "FALLBACK TITLE", "description": "desc", "tags": ["tag1"], "hook_text": "hook", "thumbnail_prompt": "thumb"}'
        }.get(model)

        self.seo.model = "llama3"
        self.seo.fallback_model = "mistral"

        meta = self.seo.generate("test transcript", "Shroud", "joy", "twitch")
        self.assertEqual(meta.title, "PRIMARY TITLE")
        self.assertEqual(meta.generated_by, "ollama")

        # 2. Test fallback model when primary fails
        mock_call_ollama.side_effect = lambda prompt, model: {
            "llama3": None, # fails primary
            "mistral": '{"title": "FALLBACK TITLE", "description": "desc", "tags": ["tag1"], "hook_text": "hook", "thumbnail_prompt": "thumb"}'
        }.get(model)

        meta = self.seo.generate("test transcript", "Shroud", "joy", "twitch")
        self.assertEqual(meta.title, "FALLBACK TITLE")
        self.assertEqual(meta.generated_by, "ollama")

        # 3. Test template fallback when both fail
        mock_call_ollama.side_effect = lambda prompt, model: None

        meta = self.seo.generate("test transcript", "Shroud", "joy", "twitch")
        self.assertEqual(meta.title, "JOY moment from Shroud!")
        self.assertEqual(meta.generated_by, "template")

if __name__ == "__main__":
    unittest.main()
