"""extract_json robustness: real LLM outputs are messy."""
import pytest

from syngen.utils import extract_json, get_at_path, set_at_path


def test_direct_json():
    assert extract_json('{"a": 1}') == {"a": 1}


def test_fenced_json():
    text = "Here is the config:\n```json\n{\"a\": 2}\n```\nThanks!"
    assert extract_json(text) == {"a": 2}


def test_json_embedded_in_prose():
    text = 'The answer is {"a": {"b": 3}} as requested.'
    assert extract_json(text) == {"a": {"b": 3}}


def test_json_with_braces_inside_strings():
    text = '{"formula": "x = {y}", "n": 5}'
    assert extract_json(text) == {"formula": "x = {y}", "n": 5}


def test_empty_raises():
    with pytest.raises(ValueError):
        extract_json("")
    with pytest.raises(ValueError):
        extract_json("no json here at all")


def test_get_set_dotted_paths():
    cfg = {"opportunities": {"discount": {"base_by_quarter": {"EMEA": [12, 12, 12, 12]}}}}
    assert get_at_path(cfg, "opportunities.discount.base_by_quarter.EMEA[2]") == 12
    set_at_path(cfg, "opportunities.discount.base_by_quarter.EMEA[3]", 22)
    assert cfg["opportunities"]["discount"]["base_by_quarter"]["EMEA"] == [12, 12, 12, 22]
    set_at_path(cfg, "seed", 7)
    assert cfg["seed"] == 7
