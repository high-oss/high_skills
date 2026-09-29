# Copyright (c) 2026 Truestock
# SPDX-License-Identifier: MIT

"""Holdings, positions, funds and working orders in one view.

    python examples/portfolio_summary.py
    python examples/portfolio_summary.py --exit-all      # guarded, asks first

Positions and holdings are not the same thing: positions are today's open
exposure, holdings are settled delivery stock. Conflating them produces wrong
P&L, so they are reported separately here.

--exit-all demonstrates portfolio.exit_all_positions(), the most destructive
call on the surface. It shows every position and requires confirmation first.
"""

from __future__ import annotations

import sys

from high_openapi import HighApiError

from scripts.high_helpers import confirm, describe_error, get_client


def rows_of(value):
    """The SDK returns pydantic models; some wrap their list in .root."""
    return list(value.root if hasattr(value, "root") else value)


def main(argv) -> None:
    exit_all = "--exit-all" in argv

    with get_client() as high:
        try:
            funds = high.portfolio.funds()
            positions = rows_of(high.portfolio.positions())
            holdings = rows_of(high.portfolio.holdings())
            orders = rows_of(high.orders.list())
            trades = rows_of(high.orders.trades())
        except HighApiError as error:
            print(describe_error(error))
            raise

        print("\nFUNDS")
        print(f"  available   {getattr(funds, 'availableBalance', funds)}")

        print(f"\nPOSITIONS ({len(positions)}) — today's open exposure")
        for position in positions:
            print(f"  {position}")
        if not positions:
            print("  none")

        print(f"\nHOLDINGS ({len(holdings)}) — settled delivery stock")
        for holding in holdings:
            print(f"  {holding}")
        if not holdings:
            print("  none")

        print(f"\nORDERS TODAY ({len(orders)})")
        for order in orders:
            print(f"  {order}")
        if not orders:
            print("  none")

        print(f"\nFILLS TODAY ({len(trades)})")
        for trade in trades:
            print(f"  {trade}")
        if not trades:
            print("  none")

        if not exit_all:
            return

        # --- the destructive path ----------------------------------------
        if not positions:
            print("\nNothing to exit.")
            return

        preview = "\n".join(f"    {position}" for position in positions)
        prompt = (
            f"\n  EXIT ALL POSITIONS\n"
            f"  {'-' * 46}\n"
            f"  This closes all {len(positions)} position(s) at market, immediately:\n"
            f"{preview}\n"
            f"  {'-' * 46}"
        )

        if not confirm(prompt):
            print("Not exited.")
            return

        try:
            print(f"\n{high.portfolio.exit_all_positions()}")
        except HighApiError as error:
            print(describe_error(error))
            raise


if __name__ == "__main__":
    main(sys.argv[1:])
