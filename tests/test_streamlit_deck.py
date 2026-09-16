"""
Tests for the flashcard-deck HTML/JS builder in streamlit_app.py.

streamlit_app.py runs Streamlit code at import time, so instead of
importing the module we lift just `build_flashcard_deck_html` out of it
with ast + exec into a minimal namespace. This keeps the deck's rendered
output under test without a running Streamlit server.
"""

import ast
import html as html_module
import json
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.graph.state import TYPE_ICONS

_APP = os.path.join(os.path.dirname(__file__), "..", "streamlit_app.py")


def _load_deck_builder():
    with open(_APP, encoding="utf-8") as f:
        src = f.read()
    ns = {"json": json, "html_module": html_module, "TYPE_ICONS": TYPE_ICONS}
    # The builder depends on a few module-level defs (the inline SVG icon
    # map and its helper); pull them in too, in source order.
    wanted = {"_SVG_ATTRS", "TYPE_ICONS_SVG", "_type_svg", "build_flashcard_deck_html"}
    for node in ast.parse(src).body:
        name = getattr(node, "name", None)
        if name is None and isinstance(node, ast.Assign):
            name = getattr(node.targets[0], "id", None)
        if name in wanted:
            exec(compile(ast.get_source_segment(src, node), _APP, "exec"), ns)
    if "build_flashcard_deck_html" not in ns:
        raise AssertionError("build_flashcard_deck_html not found in streamlit_app.py")
    return ns["build_flashcard_deck_html"]


build_flashcard_deck_html = _load_deck_builder()


def _card(**over):
    base = {"topic": "Fractions", "type": "QA", "front": "f", "back": "b",
            "difficulty": "easy", "used_interest": ""}
    base.update(over)
    return base


def test_deck_carries_used_interest_value_into_the_card_data():
    html = build_flashcard_deck_html([_card(used_interest="soccer")])
    assert '"used_interest": "soccer"' in html


def test_deck_renders_personalized_tag_element_and_reveal_logic():
    html = build_flashcard_deck_html([_card(used_interest="soccer")])
    # the tag element and the client-side label prefix are in the markup
    assert 'id="usedInterest"' in html
    assert "personalized using: " in html
    # and the logic that shows it only when used_interest is truthy
    assert "if (c.used_interest)" in html
    assert "classList.remove('hidden')" in html
    assert "classList.add('hidden')" in html


def test_deck_tag_starts_hidden_and_empty_interest_shows_nothing():
    html = build_flashcard_deck_html([_card(used_interest="")])
    assert 'class="used-interest hidden"' in html  # element present but hidden
    assert '"used_interest": ""' in html           # this card carries no interest


def test_deck_used_interest_defaults_to_empty_when_key_absent():
    card = {"topic": "T", "type": "QA", "front": "f", "back": "b", "difficulty": "easy"}
    html = build_flashcard_deck_html([card])
    assert '"used_interest": ""' in html


def test_deck_uses_inline_stroke_svg_icons_not_emoji():
    cards = [
        _card(type=t)
        for t in ("CONCEPT", "USE_CASE", "PITFALL", "QA", "SUMMARY")
    ]
    html = build_flashcard_deck_html(cards)
    # one inline SVG per mini-board tile, all inheriting the text colour
    assert html.count('<span class="mini-icon"><svg') == 5
    assert 'stroke="currentColor"' in html
    assert 'fill="none"' in html
    # icon travels into the card data for the JS labels (which now use innerHTML)
    assert '"icon_svg"' in html
    assert "frontLabel').innerHTML" in html and "backLabel').innerHTML" in html
    # the old type-icon emoji are gone from the deck (💡 CONCEPT, 📝 SUMMARY,
    # ❓ QA fallback). The 🎯 in the "personalized using" tag is a separate
    # decorative marker, not a type icon, and is left as-is.
    for emoji in ("💡", "📝", "❓"):
        assert emoji not in html
    # everything is embedded -- no external stylesheet/script/font loads
    assert "https://" not in html


def test_deck_unknown_card_type_falls_back_to_qa_icon():
    html = build_flashcard_deck_html([_card(type="NOT_A_TYPE")])
    # QA icon = a circle + the help-mark path; must still be a valid inline SVG
    assert '<span class="mini-icon"><svg' in html
    assert 'M9.09 9a3 3 0 0 1 5.83 1' in html  # the QA (help-circle) path
