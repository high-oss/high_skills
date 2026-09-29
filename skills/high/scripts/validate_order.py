# Copyright (c) 2026 Truestock
# SPDX-License-Identifier: MIT

"""Pre-flight order validation — the server's own rules, checked locally.

HIGH validates an order body with class-validator and returns every failure
at once. Running the same rules before the call turns a 400 into a readable
message, and turns the agent's confirmation preview into something that
reflects what will actually be sent.

The rules here mirror libs/common/src/dto/request/orders.ts and its
validators. When the API adds a flavor or a conditional field, this file is
what needs updating.

    from scripts.validate_order import validate

    verdict = validate(body, lot_size=scrip.lot_size)
    if not verdict.ok:
        for error in verdict.errors:
            print(error)
    print(verdict.preview)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

try:
    from .high_helpers import load_config
except ImportError:
    from high_helpers import load_config  # type: ignore[no-redef]

TRADEABLE_EXCHANGES = ("NSE", "BSE", "NSEFO", "BSEFO", "NSECDSFO", "BSECDSFO", "MCXFO")
TRADE_SIDES = ("B", "S")
PRODUCT_TYPES = ("INTRADAY", "DELIVERY", "MTF")
ORDER_FLAVORS = ("REGULAR", "BO", "CO", "GTT")
ORDER_TYPES = ("LIMIT", "MARKET", "STOP_LOSS", "STOP_LOSS_MARKET")
ORDER_VALIDITY = ("DAY", "IOC", "YEAR")
LEG_INDICATORS = ("ENTRY_LEG", "STOP_LOSS_LEG", "TARGET_LEG")

# Which flavors each product type permits — the server's IsFlavorValid.
FLAVORS_BY_PRODUCT = {
    "INTRADAY": ("REGULAR", "BO", "CO"),
    "DELIVERY": ("REGULAR", "GTT"),
    "MTF": ("REGULAR", "GTT"),
}

# Segments whose contracts trade in lots, so quantity must be a multiple.
DERIVATIVE_SEGMENTS = ("NSEFO", "BSEFO", "NSECDSFO", "BSECDSFO", "MCXFO")

PRICED_ORDER_TYPES = ("LIMIT", "STOP_LOSS")
STOP_ORDER_TYPES = ("STOP_LOSS", "STOP_LOSS_MARKET")


@dataclass
class Verdict:
    """The outcome of a pre-flight check.

    `ok` gates the call. `warnings` do not — they are things the user should
    see in the preview and confirm, such as a large notional.
    """

    ok: bool
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    preview: str = ""

    def __bool__(self) -> bool:
        return self.ok


def _number(body: Dict[str, Any], key: str) -> Optional[float]:
    value = body.get(key)
    if value is None or isinstance(value, bool):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def validate(
    body: Dict[str, Any],
    *,
    lot_size: Optional[int] = None,
    config: Optional[Dict[str, Any]] = None,
) -> Verdict:
    """Check an order body against HIGH's rules and the configured caps."""
    settings = config if config is not None else load_config()
    errors: List[str] = []
    warnings: List[str] = []

    trade_side = body.get("tradeSide")
    product_type = body.get("productType")
    flavor = body.get("flavor")
    order_type = body.get("orderType")
    validity = body.get("validity")
    quantity = _number(body, "quantity")
    price = _number(body, "price")
    trigger_price = _number(body, "triggerPrice")
    target_price = _number(body, "targetPrice")
    stoploss_price = _number(body, "stoplossPrice")
    disclosed = _number(body, "disclosedQuantity")
    leg_indicator = body.get("legIndicator")

    # --- identity: exactly one of the two accepted paths ------------------
    trading_symbol = body.get("tradingSymbol")
    exchange_segment = body.get("exchangeSegment")
    scrip_code = body.get("scripCode")

    if not trading_symbol and not (exchange_segment and scrip_code):
        errors.append(
            "Identify the instrument: send tradingSymbol, or both exchangeSegment and scripCode."
        )
    if exchange_segment and exchange_segment not in TRADEABLE_EXCHANGES:
        errors.append(f"exchangeSegment must be one of {', '.join(TRADEABLE_EXCHANGES)}.")
    if scrip_code is not None and not str(scrip_code).isdigit():
        errors.append("scripCode must be digits only, sent as a string, e.g. '2885'.")

    # --- enums ------------------------------------------------------------
    if trade_side not in TRADE_SIDES:
        errors.append("tradeSide must be 'B' (buy) or 'S' (sell) — not 'BUY' or 'SELL'.")
    if product_type not in PRODUCT_TYPES:
        errors.append(f"productType must be one of {', '.join(PRODUCT_TYPES)} — there is no CNC on HIGH.")
    if flavor not in ORDER_FLAVORS:
        errors.append(f"flavor must be one of {', '.join(ORDER_FLAVORS)}.")
    if order_type not in ORDER_TYPES:
        errors.append(f"orderType must be one of {', '.join(ORDER_TYPES)}.")
    if validity not in ORDER_VALIDITY:
        errors.append(f"validity must be one of {', '.join(ORDER_VALIDITY)}.")

    # --- product x flavor -------------------------------------------------
    if product_type in FLAVORS_BY_PRODUCT and flavor in ORDER_FLAVORS:
        permitted = FLAVORS_BY_PRODUCT[product_type]
        if flavor not in permitted:
            errors.append(
                f"flavor must be one of {'/'.join(permitted)} for {product_type} orders. "
                f"BO and CO are INTRADAY only; GTT is DELIVERY/MTF only."
            )

    # --- quantity ---------------------------------------------------------
    if quantity is None or quantity <= 0:
        errors.append("quantity should be greater than 0.")
    elif lot_size and lot_size > 1:
        if quantity % lot_size:
            errors.append(
                f"quantity {int(quantity)} is not a multiple of the lot size {lot_size}. "
                f"Nearest valid: {int(quantity // lot_size) * lot_size or lot_size}."
            )

    # --- conditional prices ----------------------------------------------
    if order_type in PRICED_ORDER_TYPES and price is None:
        errors.append(f"price is required for {order_type} orders.")
    if order_type == "MARKET" and price is not None:
        warnings.append("price is ignored on a MARKET order.")

    if flavor == "GTT" and trigger_price is None:
        errors.append("triggerPrice is required for a GTT order.")
    if order_type in STOP_ORDER_TYPES and trigger_price is None:
        errors.append(f"triggerPrice is required for {order_type} orders.")

    if flavor == "BO":
        if target_price is None:
            errors.append("targetPrice is required for a bracket (BO) order.")
        if stoploss_price is None:
            errors.append("stoplossPrice is required for a bracket (BO) order.")
    elif target_price is not None:
        errors.append("targetPrice applies to bracket (BO) orders only.")

    if flavor == "CO" and stoploss_price is None:
        errors.append("stoplossPrice is required for a cover (CO) order.")
    if flavor in ("REGULAR", "GTT") and stoploss_price is not None:
        errors.append("stoplossPrice applies to BO and CO orders only.")

    # --- leg indicator ----------------------------------------------------
    if flavor in ("BO", "CO"):
        if leg_indicator not in LEG_INDICATORS:
            errors.append(f"legIndicator must be one of {', '.join(LEG_INDICATORS)} for {flavor} orders.")
    elif leg_indicator is not None:
        errors.append("legIndicator is only applicable for BO/CO orders.")

    # --- disclosed quantity ----------------------------------------------
    if disclosed is not None and disclosed > 0:
        if not (flavor == "REGULAR" and validity == "DAY"):
            errors.append("disclosedQuantity applies to REGULAR orders with DAY validity only.")
        elif quantity is not None and disclosed > quantity:
            errors.append("disclosedQuantity must be 0 or less than or equal to quantity.")

    # --- stop-loss direction sanity --------------------------------------
    if flavor in ("BO", "CO") and price is not None and stoploss_price is not None:
        if trade_side == "B" and stoploss_price >= price:
            errors.append("For a buy, stoplossPrice must be below the entry price.")
        if trade_side == "S" and stoploss_price <= price:
            errors.append("For a sell, stoplossPrice must be above the entry price.")
    if flavor == "BO" and price is not None and target_price is not None:
        if trade_side == "B" and target_price <= price:
            errors.append("For a buy, targetPrice must be above the entry price.")
        if trade_side == "S" and target_price >= price:
            errors.append("For a sell, targetPrice must be below the entry price.")

    # --- configured guardrails -------------------------------------------
    max_quantity = settings.get("max_order_quantity")
    if max_quantity and quantity and quantity > max_quantity:
        errors.append(
            f"quantity {int(quantity)} exceeds the configured cap of {max_quantity}. "
            f"Raise max_order_quantity in config.json if this is deliberate."
        )

    if not settings.get("allow_market_orders", False) and order_type in ("MARKET", "STOP_LOSS_MARKET"):
        warnings.append(
            f"{order_type} is not enabled in config (allow_market_orders is false). "
            f"Confirm the user really asked for a market order."
        )

    if body.get("isAMO") and not settings.get("allow_amo", False):
        warnings.append("isAMO is set but allow_amo is false in config. Confirm the after-market intent.")

    reference_price = price if price is not None else trigger_price
    notional = (quantity or 0) * (reference_price or 0)
    max_value = settings.get("max_order_value")
    if settings.get("risk_warnings", True) and max_value and notional > max_value:
        warnings.append(f"Notional Rs. {notional:,.2f} exceeds Rs. {max_value:,.2f}.")
    if order_type == "MARKET" and reference_price is None:
        warnings.append("Notional cannot be estimated for a MARKET order without a reference price.")

    return Verdict(
        ok=not errors,
        errors=errors,
        warnings=warnings,
        preview=build_preview(body, notional=notional, warnings=warnings, lot_size=lot_size),
    )


def build_preview(
    body: Dict[str, Any],
    *,
    notional: float = 0.0,
    warnings: Optional[List[str]] = None,
    lot_size: Optional[int] = None,
) -> str:
    """The human-readable block shown before asking for confirmation.

    Every conditional price the flavor carries appears here — that is the
    point. A bracket order that silently lost its stop-loss should be
    obvious on the screen, not discovered at the exchange.
    """
    side = {"B": "BUY", "S": "SELL"}.get(str(body.get("tradeSide")), str(body.get("tradeSide")))
    instrument = body.get("tradingSymbol") or f"{body.get('exchangeSegment')}:{body.get('scripCode')}"
    quantity = body.get("quantity")

    lines = [
        "",
        "  ORDER PREVIEW",
        "  " + "-" * 46,
        f"  {side} {quantity} x {instrument}",
        f"  product    {body.get('productType')}",
        f"  flavor     {body.get('flavor')}",
        f"  type       {body.get('orderType')}    validity {body.get('validity')}",
    ]

    if body.get("price") is not None:
        lines.append(f"  price      {body['price']}")
    if body.get("triggerPrice") is not None:
        lines.append(f"  trigger    {body['triggerPrice']}")
    if body.get("targetPrice") is not None:
        lines.append(f"  target     {body['targetPrice']}")
    if body.get("stoplossPrice") is not None:
        lines.append(f"  stop-loss  {body['stoplossPrice']}")
    if body.get("trailSL") is not None:
        lines.append(f"  trail SL   {body['trailSL']} ticks")
    if body.get("legIndicator"):
        lines.append(f"  leg        {body['legIndicator']}")
    if body.get("disclosedQuantity"):
        lines.append(f"  disclosed  {body['disclosedQuantity']}")
    if lot_size and lot_size > 1 and quantity:
        lines.append(f"  lots       {int(quantity) // lot_size} x {lot_size}")
    if body.get("isAMO"):
        lines.append("  AMO        yes")
    if body.get("isSlice"):
        lines.append("  sliced     yes")
    if notional:
        lines.append(f"  notional   Rs. {notional:,.2f}")

    for warning in warnings or []:
        lines.append(f"  !  {warning}")

    lines.append("  " + "-" * 46)
    return "\n".join(lines)


__all__ = [
    "FLAVORS_BY_PRODUCT",
    "LEG_INDICATORS",
    "ORDER_FLAVORS",
    "ORDER_TYPES",
    "ORDER_VALIDITY",
    "PRODUCT_TYPES",
    "TRADEABLE_EXCHANGES",
    "TRADE_SIDES",
    "Verdict",
    "build_preview",
    "validate",
]
