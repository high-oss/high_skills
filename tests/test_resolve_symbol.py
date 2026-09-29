# Copyright (c) 2026 Truestock
# SPDX-License-Identifier: MIT

"""Ranking and identifier-shaping tests for resolve_symbol.

No network: the scorer is fed fake instrument rows. What is being checked is
that "reliance" finds RELIANCE-EQ rather than RELIANCERETAIL-EQ, and that an
order body never ends up with both identifier paths at once.

    pytest tests/
"""

from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "skills" / "high" / "scripts"))

from resolve_symbol import Scrip, _score, _to_scrip, scrip_keys  # noqa: E402


def row(**overrides):
    base = {
        "exchange": "NSE",
        "segment": "EQ",
        "instrument": None,
        "high_trading_symbol": "RELIANCE-EQ",
        "scrip_key": "NSE@2885",
        "isin": "INE002A01018",
        "scrip_code": 2885,
        "symbol": "RELIANCE",
        "name": "Reliance Industries Ltd",
        "group_series": "EQ",
        "has_fno": 1,
        "underlying_symbol": None,
        "expiry": None,
        "option_type": None,
        "strike_price": None,
        "price_tick": 5,
        "lot_size": 1,
    }
    base.update(overrides)
    return SimpleNamespace(**base)


# --- ranking -------------------------------------------------------------

def test_exact_trading_symbol_scores_best():
    assert _score(row(), "reliance-eq") == 0


def test_exact_bare_symbol_scores_best():
    assert _score(row(), "reliance") == 0


def test_exact_name_beats_a_prefix():
    named = row(symbol="RELI", high_trading_symbol="RELI-EQ", name="Reliance")
    other = row(symbol="RELIANCEPOWER", high_trading_symbol="RELIANCEPOWER-EQ",
                name="Reliance Power Ltd")
    assert _score(named, "reliance") < _score(other, "reliance")


def test_exact_symbol_beats_a_longer_one():
    exact = row()
    longer = row(symbol="RELIANCERETAIL", high_trading_symbol="RELIANCERETAIL-EQ",
                 name="Reliance Retail Ltd")
    assert _score(exact, "reliance") < _score(longer, "reliance")


def test_substring_in_name_still_matches():
    assert _score(row(), "industries") is not None


def test_no_match_returns_none():
    assert _score(row(), "zzzznotathing") is None


def test_ranking_orders_a_realistic_set():
    candidates = [
        row(symbol="RELIANCERETAIL", high_trading_symbol="RELIANCERETAIL-EQ",
            name="Reliance Retail Ltd"),
        row(),
        row(symbol="RELIANCEPOWER", high_trading_symbol="RELIANCEPOWER-EQ",
            name="Reliance Power Ltd"),
    ]
    ranked = sorted(
        ((_score(candidate, "reliance"), candidate.high_trading_symbol) for candidate in candidates),
        key=lambda pair: (pair[0], pair[1]),
    )
    assert ranked[0][1] == "RELIANCE-EQ"


# --- the three identifier forms -----------------------------------------

def test_every_identifier_form_is_carried():
    scrip = _to_scrip(row())
    assert scrip.tradingSymbol == "RELIANCE-EQ"
    assert scrip.exchange == "NSE"
    assert scrip.scripCode == "2885"          # a STRING, as the API wants
    assert scrip.scrip_key == "NSE@2885"      # what the datafeed wants


def test_scrip_code_is_a_string_not_an_int():
    assert isinstance(_to_scrip(row()).scripCode, str)


def test_order_identity_uses_the_trading_symbol_by_default():
    identity = _to_scrip(row()).order_identity()
    assert identity == {"tradingSymbol": "RELIANCE-EQ"}


def test_order_identity_by_code_uses_the_pair():
    identity = _to_scrip(row()).order_identity(by_code=True)
    assert identity == {"exchangeSegment": "NSE", "scripCode": "2885"}


def test_order_identity_never_sends_both_paths():
    # The API requires exactly one of the two. Sending both is a rejection.
    for identity in (_to_scrip(row()).order_identity(), _to_scrip(row()).order_identity(by_code=True)):
        assert not ({"tradingSymbol"} <= set(identity) and {"scripCode"} <= set(identity))


def test_derivative_fields_survive():
    import datetime

    scrip = _to_scrip(row(
        high_trading_symbol="NIFTY-26SEP-24000-CE",
        scrip_key="NSEFO@43210",
        scrip_code=43210,
        exchange="NSEFO",
        underlying_symbol="NIFTY",
        expiry=datetime.date(2026, 9, 29),
        option_type="CE",
        strike_price=24000.0,
        lot_size=75,
    ))
    assert scrip.lot_size == 75
    assert scrip.option_type == "CE"
    assert scrip.strike_price == 24000.0
    assert scrip.expiry == datetime.date(2026, 9, 29)


def test_scrip_keys_collects_feed_keys():
    scrips = [_to_scrip(row()), _to_scrip(row(scrip_key="NSE@11536", scrip_code=11536))]
    assert scrip_keys(scrips) == ["NSE@2885", "NSE@11536"]


def test_scrip_is_immutable():
    scrip = _to_scrip(row())
    try:
        scrip.tradingSymbol = "TCS-EQ"
    except Exception:
        return
    raise AssertionError("Scrip should be frozen.")


def test_scrip_type_is_exported():
    assert isinstance(_to_scrip(row()), Scrip)
