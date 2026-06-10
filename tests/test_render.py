#!/usr/bin/env python3
"""Tests for render_report.py — stdlib only, run with: python -m unittest discover tests"""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from render_report import ValidationError, load_classification, render  # noqa: E402


def write_tmp(content: str) -> Path:
    path = Path(tempfile.mktemp(suffix=".json"))
    path.write_text(content, encoding="utf-8")
    return path


def valid_email(**overrides) -> dict:
    email = {"subject": "Test", "quadrant": "q1", "confidence": 0.9}
    email.update(overrides)
    return email


class TestValidation(unittest.TestCase):
    def test_missing_emails_key(self):
        with self.assertRaises(ValidationError):
            load_classification(write_tmp("{}"))

    def test_empty_email_list(self):
        with self.assertRaises(ValidationError):
            load_classification(write_tmp('{"emails": []}'))

    def test_invalid_json(self):
        with self.assertRaises(ValidationError):
            load_classification(write_tmp("not json"))

    def test_missing_file(self):
        with self.assertRaises(ValidationError):
            load_classification(Path("/nonexistent/file.json"))

    def test_unknown_quadrant(self):
        data = json.dumps({"emails": [valid_email(quadrant="q9")]})
        with self.assertRaises(ValidationError):
            load_classification(write_tmp(data))

    def test_missing_subject(self):
        data = json.dumps({"emails": [{"quadrant": "q1"}]})
        with self.assertRaises(ValidationError):
            load_classification(write_tmp(data))

    def test_confidence_out_of_range(self):
        data = json.dumps({"emails": [valid_email(confidence=1.5)]})
        with self.assertRaises(ValidationError):
            load_classification(write_tmp(data))

    def test_valid_minimal_email(self):
        data = json.dumps({"emails": [{"subject": "x", "quadrant": "q4"}]})
        loaded = load_classification(write_tmp(data))
        self.assertEqual(len(loaded["emails"]), 1)


class TestRendering(unittest.TestCase):
    def test_html_injection_is_escaped(self):
        data = {
            "emails": [
                valid_email(
                    subject="<script>alert(1)</script>",
                    rationale='Test & <img src=x onerror="x">',
                )
            ]
        }
        html_out = render(data, "Titel")
        self.assertNotIn("<script>alert", html_out)
        self.assertIn("&lt;script&gt;", html_out)
        self.assertNotIn("<img src=x", html_out)

    def test_empty_quadrants_get_placeholder(self):
        data = {"emails": [valid_email(quadrant="q1")]}
        html_out = render(data, "Titel")
        self.assertIn("Keine E-Mails in diesem Quadranten", html_out)

    def test_all_quadrant_labels_present(self):
        data = {"emails": [valid_email()]}
        html_out = render(data, "Titel")
        for label in ("Sofort erledigen", "Terminieren", "Delegieren", "Streichen"):
            self.assertIn(label, html_out)

    def test_umlauts_survive(self):
        data = {"emails": [valid_email(subject="Wasserschaden Zürich – Prüfung nötig")]}
        html_out = render(data, "Titel")
        self.assertIn("Zürich", html_out)


if __name__ == "__main__":
    unittest.main()
