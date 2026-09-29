# Copyright (c) 2026 Truestock
# SPDX-License-Identifier: MIT

"""Cases derived from HIGH's own order validators.

These mirror libs/common/src/dto/request/orders.ts and IsFlavorValid in the
high-api repo. When the API adds a flavor or a conditional field, a failure
here is the signal that validate_order.py has fallen behind.

    pytest tests/
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "skills" / "high" / "scripts"))

from validate_order import validate  # noqa: E402

CONFIG = {
    "max_order_value": 50_000,
    "max_order_quantity": 1_000,
    "allow_market_orders": True,
    "allow_amo": True,
    "risk_warnings": True,
}


def base(**overrides):
    body = {
        "tradingSymbol": "RELIANCE-EQ",
        "tradeSide": "B",
        "productType": "DELIVERY",
        "flavor": "REGULAR",
        "orderType": "LIMIT",
        "validity": "DAY",
        "quantity": 10,
        "price": 2450,
        "isAMO": False,
    }
    body.update(overrides)
    return body


def errors(body, **kwargs):
    return validate(body, config=CONFIG, **kwargs).errors


# --- identity ------------------------------------------------------------

def test_accepts_trading_symbol():
    assert validate(base(), config=CONFIG).ok


def test_accepts_segment_and_scrip_code():
    body = base()
    del body["tradingSymbol"]
    body.update({"exchangeSegment": "NSE", "scripCode": "2885"})
    assert validate(body, config=CONFIG).ok


def test_rejects_neither_identifier():
    body = base()
    del body["tradingSymbol"]
    assert any("Identify the instrument" in error for error in errors(body))


def test_rejects_non_numeric_scrip_code():
    body = base()
    del body["tradingSymbol"]
    body.update({"exchangeSegment": "NSE", "scripCode": "RELIANCE"})
    assert any("digits only" in error for error in errors(body))


def test_rejects_unknown_exchange_segment():
    body = base()
    del body["tradingSymbol"]
    body.update({"exchangeSegment": "NASDAQ", "scripCode": "2885"})
    assert any("exchangeSegment" in error for error in errors(body))


# --- enums, and other brokers' vocabulary --------------------------------

@pytest.mark.parametrize("side", ["BUY", "SELL", "b", ""])
def test_rejects_non_high_trade_sides(side):
    assert any("tradeSide" in error for error in errors(base(tradeSide=side)))


def test_rejects_cnc_product_type():
    # Dhan and several other brokers use CNC. HIGH does not.
    assert any("productType" in error for error in errors(base(productType="CNC")))


def test_rejects_unknown_flavor():
    assert any("flavor" in error for error in errors(base(flavor="SUPER")))


def test_accepts_year_validity_for_gtt():
    body = base(flavor="GTT", validity="YEAR", triggerPrice=2400)
    assert validate(body, config=CONFIG).ok


# --- product x flavor, i.e. IsFlavorValid --------------------------------

@pytest.mark.parametrize("flavor", ["REGULAR", "BO", "CO"])
def test_intraday_permits_regular_bo_co(flavor):
    body = base(productType="INTRADAY", flavor=flavor)
    if flavor in ("BO", "CO"):
        body["stoplossPrice"] = 2400
        body["legIndicator"] = "ENTRY_LEG"
    if flavor == "BO":
        body["targetPrice"] = 2500
    assert validate(body, config=CONFIG).ok


def test_intraday_rejects_gtt():
    body = base(productType="INTRADAY", flavor="GTT", triggerPrice=2400)
    assert any("BO/CO/REGULAR" in error or "flavor must be" in error for error in errors(body))


@pytest.mark.parametrize("product", ["DELIVERY", "MTF"])
def test_delivery_and_mtf_reject_bracket(product):
    body = base(productType=product, flavor="BO", targetPrice=2500, stoplossPrice=2400,
                legIndicator="ENTRY_LEG")
    assert any("flavor must be" in error for error in errors(body))


@pytest.mark.parametrize("product", ["DELIVERY", "MTF"])
def test_delivery_and_mtf_permit_gtt(product):
    body = base(productType=product, flavor="GTT", validity="YEAR", triggerPrice=2400)
    assert validate(body, config=CONFIG).ok


# --- conditional fields --------------------------------------------------

def test_limit_requires_price():
    body = base()
    del body["price"]
    assert any("price is required" in error for error in errors(body))


def test_gtt_requires_trigger_price():
    body = base(productType="DELIVERY", flavor="GTT", validity="YEAR")
    assert any("triggerPrice is required" in error for error in errors(body))


def test_stop_loss_order_type_requires_trigger_price():
    assert any("triggerPrice is required" in error for error in errors(base(orderType="STOP_LOSS")))


def test_bracket_requires_target_and_stoploss():
    body = base(productType="INTRADAY", flavor="BO", legIndicator="ENTRY_LEG")
    found = errors(body)
    assert any("targetPrice is required" in error for error in found)
    assert any("stoplossPrice is required" in error for error in found)


def test_cover_requires_stoploss():
    body = base(productType="INTRADAY", flavor="CO", legIndicator="ENTRY_LEG")
    assert any("stoplossPrice is required" in error for error in errors(body))


def test_cover_rejects_target_price():
    body = base(productType="INTRADAY", flavor="CO", stoplossPrice=2400,
                targetPrice=2500, legIndicator="ENTRY_LEG")
    assert any("targetPrice applies to bracket" in error for error in errors(body))


def test_regular_rejects_stoploss_price():
    assert any("stoplossPrice applies" in error for error in errors(base(stoplossPrice=2400)))


# --- leg indicator -------------------------------------------------------

def test_leg_indicator_required_for_bracket():
    body = base(productType="INTRADAY", flavor="BO", targetPrice=2500, stoplossPrice=2400)
    assert any("legIndicator must be one of" in error for error in errors(body))


def test_leg_indicator_rejected_on_regular():
    body = base(legIndicator="ENTRY_LEG")
    assert any("only applicable for BO/CO" in error for error in errors(body))


def test_leg_indicator_rejected_on_gtt():
    body = base(productType="DELIVERY", flavor="GTT", validity="YEAR",
                triggerPrice=2400, legIndicator="ENTRY_LEG")
    assert any("only applicable for BO/CO" in error for error in errors(body))


# --- disclosed quantity --------------------------------------------------

def test_disclosed_quantity_allowed_on_regular_day():
    assert validate(base(disclosedQuantity=5), config=CONFIG).ok


def test_disclosed_quantity_cannot_exceed_quantity():
    body = base(disclosedQuantity=50)
    assert any("less than or equal to quantity" in error for error in errors(body))


def test_disclosed_quantity_rejected_on_ioc():
    body = base(validity="IOC", disclosedQuantity=5)
    assert any("REGULAR orders with DAY validity" in error for error in errors(body))


# --- lot size ------------------------------------------------------------

def test_fno_quantity_must_be_a_lot_multiple():
    body = base(tradingSymbol="NIFTY-26SEP-FUT", productType="INTRADAY", quantity=100)
    assert any("not a multiple of the lot size" in error for error in errors(body, lot_size=75))


def test_fno_quantity_accepts_exact_lots():
    body = base(tradingSymbol="NIFTY-26SEP-FUT", productType="INTRADAY", quantity=150, price=100)
    assert validate(body, lot_size=75, config=CONFIG).ok


# --- stop-loss direction -------------------------------------------------

def test_buy_stoploss_must_be_below_entry():
    body = base(productType="INTRADAY", flavor="CO", stoplossPrice=2500,
                legIndicator="ENTRY_LEG")
    assert any("must be below the entry price" in error for error in errors(body))


def test_buy_target_must_be_above_entry():
    body = base(productType="INTRADAY", flavor="BO", targetPrice=2400,
                stoplossPrice=2300, legIndicator="ENTRY_LEG")
    assert any("must be above the entry price" in error for error in errors(body))


def test_sell_stoploss_must_be_above_entry():
    body = base(tradeSide="S", productType="INTRADAY", flavor="CO",
                stoplossPrice=2400, legIndicator="ENTRY_LEG")
    assert any("must be above the entry price" in error for error in errors(body))


# --- configured caps -----------------------------------------------------

def test_quantity_cap_is_enforced():
    assert any("exceeds the configured cap" in error for error in errors(base(quantity=5000)))


def test_large_notional_warns_but_does_not_block():
    verdict = validate(base(quantity=100), config=CONFIG)
    assert verdict.ok
    assert any("exceeds" in warning for warning in verdict.warnings)


def test_market_order_warns_when_not_allowed():
    config = {**CONFIG, "allow_market_orders": False}
    body = base(orderType="MARKET")
    del body["price"]
    verdict = validate(body, config=config)
    assert verdict.ok
    assert any("market order" in warning for warning in verdict.warnings)


# --- preview -------------------------------------------------------------

def test_preview_shows_every_conditional_price():
    body = base(productType="INTRADAY", flavor="BO", targetPrice=2500,
                stoplossPrice=2400, trailSL=5, legIndicator="ENTRY_LEG")
    preview = validate(body, config=CONFIG).preview
    for expected in ("BUY", "RELIANCE-EQ", "BO", "target", "stop-loss", "trail SL", "notional"):
        assert expected in preview
