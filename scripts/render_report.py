#!/usr/bin/env python3
"""Render an Eisenhower classification JSON into an email-client-safe HTML briefing.

Deliberately stdlib-only: no dependencies, no surprises.

Usage:
    python scripts/render_report.py classified.json -o briefing.html --title "Pendenzen-Briefing"
"""

from __future__ import annotations

import argparse
import html
import json
import sys
from datetime import datetime
from pathlib import Path

TEMPLATE_PATH = Path(__file__).resolve().parent.parent / "assets" / "template.html"

QUADRANTS = {
    "q1": {
        "label": "Dringend & wichtig",
        "action": "Sofort erledigen",
        "color": "#c0392b",
        "bg": "#fdf0ee",
    },
    "q2": {
        "label": "Wichtig, nicht dringend",
        "action": "Terminieren",
        "color": "#1f6f43",
        "bg": "#eef7f1",
    },
    "q3": {
        "label": "Dringend, nicht wichtig",
        "action": "Delegieren",
        "color": "#b9770e",
        "bg": "#fdf6e9",
    },
    "q4": {
        "label": "Weder dringend noch wichtig",
        "action": "Streichen / Archivieren",
        "color": "#6b7280",
        "bg": "#f3f4f6",
    },
}

REQUIRED_EMAIL_FIELDS = ("subject", "quadrant")


class ValidationError(Exception):
    """Raised when the classification JSON does not match the expected schema."""


def load_classification(path: Path) -> dict:
    """Load and validate the classification JSON. Fail early with clear messages."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise ValidationError(f"Eingabedatei nicht gefunden: {path}")
    except json.JSONDecodeError as exc:
        raise ValidationError(f"Ungueltiges JSON in {path}: {exc}")

    emails = data.get("emails")
    if not isinstance(emails, list) or not emails:
        raise ValidationError('Schluessel "emails" fehlt, ist leer oder keine Liste.')

    for i, email in enumerate(emails):
        if not isinstance(email, dict):
            raise ValidationError(f"emails[{i}] ist kein Objekt.")
        for field in REQUIRED_EMAIL_FIELDS:
            if not str(email.get(field, "")).strip():
                raise ValidationError(f'emails[{i}]: Pflichtfeld "{field}" fehlt oder ist leer.')
        quadrant = email["quadrant"]
        if quadrant not in QUADRANTS:
            raise ValidationError(
                f'emails[{i}]: unbekannter Quadrant "{quadrant}" (erlaubt: {", ".join(QUADRANTS)}).'
            )
        confidence = email.get("confidence")
        if confidence is not None and not (isinstance(confidence, (int, float)) and 0 <= confidence <= 1):
            raise ValidationError(f"emails[{i}]: confidence muss eine Zahl in [0, 1] sein.")

    return data


def esc(value: object) -> str:
    """HTML-escape any value. Email content is untrusted input."""
    return html.escape(str(value), quote=True)


def render_email_card(email: dict, color: str) -> str:
    """Render a single email as a table row card."""
    meta_parts = []
    if email.get("from"):
        meta_parts.append(f"Von: {esc(email['from'])}")
    if email.get("date"):
        meta_parts.append(esc(email["date"]))
    meta = " &middot; ".join(meta_parts)

    confidence = email.get("confidence")
    confidence_html = (
        f'<span style="color:#8a94a6; font-size:11px;"> &middot; Konfidenz {confidence:.0%}</span>'
        if isinstance(confidence, (int, float))
        else ""
    )

    rows = [
        f'<div style="font-size:14px; font-weight:bold; color:#16181d;">{esc(email["subject"])}</div>'
    ]
    if meta:
        rows.append(f'<div style="font-size:12px; color:#8a94a6; padding-top:3px;">{meta}</div>')
    if email.get("rationale"):
        rows.append(
            f'<div style="font-size:13px; color:#3d4654; padding-top:8px;">{esc(email["rationale"])}{confidence_html}</div>'
        )
    if email.get("suggested_action"):
        rows.append(
            f'<div style="font-size:13px; color:{color}; font-weight:bold; padding-top:6px;">'
            f"&rarr; {esc(email['suggested_action'])}</div>"
        )

    return (
        '<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="margin-top:10px;">'
        f'<tr><td style="background-color:#ffffff; border:1px solid #e4e8ee; border-left:4px solid {color};'
        ' border-radius:4px; padding:12px 16px;">' + "".join(rows) + "</td></tr></table>"
    )


def render_quadrant_section(key: str, emails: list[dict]) -> str:
    """Render one quadrant block; empty quadrants get an explicit placeholder."""
    spec = QUADRANTS[key]
    if emails:
        body = "".join(render_email_card(e, spec["color"]) for e in emails)
    else:
        body = (
            '<div style="font-size:13px; color:#8a94a6; font-style:italic; padding-top:8px;">'
            "Keine E-Mails in diesem Quadranten.</div>"
        )

    return f"""
          <tr>
            <td style="background-color:{spec['bg']}; padding:18px 28px; border-bottom:1px solid #e4e8ee;">
              <div style="font-size:15px; font-weight:bold; color:{spec['color']};">{esc(spec['label'])}</div>
              <div style="font-size:12px; color:#5a6577;">{esc(spec['action'])}</div>
              {body}
            </td>
          </tr>"""


def render_summary_cells(counts: dict[str, int]) -> str:
    """Render the per-quadrant counters in the summary strip."""
    cells = []
    for key, spec in QUADRANTS.items():
        cells.append(
            f'<td align="center" style="padding:4px;">'
            f'<div style="font-size:22px; font-weight:bold; color:{spec["color"]};">{counts[key]}</div>'
            f'<div style="font-size:11px; color:#5a6577;">{esc(spec["action"])}</div></td>'
        )
    return "".join(cells)


def render(data: dict, title: str) -> str:
    """Assemble the full HTML document from the template."""
    template = TEMPLATE_PATH.read_text(encoding="utf-8")

    grouped: dict[str, list[dict]] = {key: [] for key in QUADRANTS}
    for email in data["emails"]:
        grouped[email["quadrant"]].append(email)
    # Within a quadrant, highest confidence first; missing confidence sorts last.
    for emails in grouped.values():
        emails.sort(key=lambda e: -(e.get("confidence") or 0))

    counts = {key: len(emails) for key, emails in grouped.items()}
    total = sum(counts.values())
    generated_at = data.get("generated_at") or datetime.now().astimezone().isoformat(timespec="minutes")

    sections = "".join(render_quadrant_section(key, grouped[key]) for key in QUADRANTS)

    replacements = {
        "{{TITLE}}": esc(title),
        "{{SUBTITLE}}": esc(f"{total} E-Mails klassifiziert nach Eisenhower-Matrix"),
        "{{SUMMARY_CELLS}}": render_summary_cells(counts),
        "{{QUADRANT_SECTIONS}}": sections,
        "{{GENERATED_AT}}": esc(generated_at),
    }
    for placeholder, value in replacements.items():
        template = template.replace(placeholder, value)
    return template


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path, help="Klassifikations-JSON (siehe SKILL.md)")
    parser.add_argument("-o", "--output", type=Path, default=Path("briefing.html"), help="Ziel-HTML-Datei")
    parser.add_argument("--title", default="aestate Pendenzen-Briefing", help="Titel der HTML-Mail")
    args = parser.parse_args(argv)

    try:
        data = load_classification(args.input)
    except ValidationError as exc:
        print(f"Fehler: {exc}", file=sys.stderr)
        return 1

    args.output.write_text(render(data, args.title), encoding="utf-8")
    print(f"Briefing geschrieben: {args.output} ({len(data['emails'])} E-Mails)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
