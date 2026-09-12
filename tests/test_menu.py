"""P11 buildable menu: the enforcement face of the capability work."""
from syngen.menu import (blocked_checks, buildable_checks, is_blocked,
                         menu_entries, menu_text, required_blocks,
                         required_features)


def test_blocked_paths_are_not_buildable():
    assert "quota_vs_potential" in blocked_checks()
    assert "quota_vs_potential" not in buildable_checks()
    assert is_blocked("quota_vs_potential")
    assert not is_blocked("revenue_vs_plan")


def test_required_blocks_derive_from_signatures():
    assert required_blocks(["revenue_vs_plan"]) == {"quota"}
    assert required_blocks(["blended_margin_trend"]) == {"products"}
    assert required_blocks(["coverage_ratio"]) == {"pipeline", "quota"}
    assert required_blocks(["commit_no_engagement_share"]) == {
        "forecast", "activity"}
    assert required_blocks(["win_rate_flat"]) == set()


def test_required_features_are_dotted_subkeys():
    assert "accounts.market_potential_usd" in required_features(
        ["quota_vs_potential"])
    assert "opportunities.outlier_deals" in required_features(
        ["core_vs_headline_growth"])


def test_menu_text_marks_blocked_and_lists_blocks():
    text = menu_text()
    assert "quota_vs_potential" in text
    assert "BLOCKED" in text
    assert "config needs: quota" in text
    assert len(text) < 12000          # must not recreate the giant manual


def test_every_check_has_a_menu_entry():
    entries = menu_entries()
    assert len(entries) == 33
    assert all("required_blocks" in e for e in entries)
    assert all("blocked" in e for e in entries)
