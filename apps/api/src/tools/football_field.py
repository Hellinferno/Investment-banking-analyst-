"""
Football Field — valuation summary range chart.

Collects bear/base/bull equity value ranges from every completed valuation
method (DCF, comps, precedents, LBO) for a deal and renders the classic
horizontal range-bar "football field" chart.

Security / reliability:
  - No external calls; reads only from the in-process store.
  - If matplotlib is unavailable the render function returns None and callers
    degrade gracefully (no chart embedded in the memo/pitchbook).
"""
from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_OUTPUT_DIR = str(Path(__file__).resolve().parent.parent.parent.parent / "data" / "outputs")


# ------------------------------------------------------------------
# Range collection
# ------------------------------------------------------------------

# DB-backed collector: reads the latest completed run per valuation method.
def collect_valuation_ranges(deal_id: str) -> list[dict[str, Any]]:
    from statistics import median

    from database import SessionLocal, ensure_database_ready
    from db_models import AgentRunModel

    ensure_database_ready()
    with SessionLocal() as db:
        runs = (
            db.query(AgentRunModel)
            .filter(AgentRunModel.deal_id == deal_id, AgentRunModel.status == "completed")
            .order_by(AgentRunModel.created_at.desc())
            .all()
        )

    def latest(agent_type: str | None = None, task_name: str | None = None):
        for run in runs:
            if agent_type and run.agent_type != agent_type:
                continue
            if task_name and run.task_name != task_name:
                continue
            return run
        return None

    ranges: list[dict[str, Any]] = []

    dcf_run = latest("modeling", "dcf_model")
    if dcf_run:
        vr = (dcf_run.input_payload or {}).get("valuation_result") or {}
        scenarios = vr.get("scenarios") or {}
        bear_eq = ((scenarios.get("bear") or {}).get("valuation") or {}).get("equity_value")
        base_eq = ((scenarios.get("base") or {}).get("valuation") or {}).get("equity_value")
        bull_eq = ((scenarios.get("bull") or {}).get("valuation") or {}).get("equity_value")
        if base_eq is None:
            base_eq = (vr.get("header") or {}).get("equity_value")
        if base_eq is not None:
            ranges.append({
                "method": "DCF",
                "low": float(bear_eq or base_eq * 0.85),
                "mid": float(base_eq),
                "high": float(bull_eq or base_eq * 1.15),
                "source": dcf_run.id,
            })

    comps_run = latest("comps", "comps_analysis")
    if comps_run:
        cr = (comps_run.input_payload or {}).get("comps_result") or {}
        snapshot = cr.get("deterministic_snapshot") or {}
        scenarios = snapshot.get("scenarios") or {}
        bear_eq = (scenarios.get("bear") or {}).get("equity_value")
        base_eq = (scenarios.get("base") or {}).get("equity_value")
        bull_eq = (scenarios.get("bull") or {}).get("equity_value")
        if base_eq is not None:
            ranges.append({
                "method": "Trading Comps",
                "low": float(bear_eq or base_eq * 0.85),
                "mid": float(base_eq),
                "high": float(bull_eq or base_eq * 1.15),
                "source": comps_run.id,
            })

        latest_ebitda = snapshot.get("latest_ebitda")
        net_debt = snapshot.get("net_debt") or 0
        tx_evs = []
        for tx in cr.get("precedent_transactions") or []:
            try:
                multiple = float(tx.get("ev_ebitda"))
                if latest_ebitda and multiple > 0:
                    tx_evs.append(multiple * float(latest_ebitda) - float(net_debt))
            except (TypeError, ValueError, AttributeError):
                continue
        if len(tx_evs) >= 2:
            tx_evs.sort()
            ranges.append({
                "method": "Precedent Transactions",
                "low": float(tx_evs[0]),
                "mid": float(median(tx_evs)),
                "high": float(tx_evs[-1]),
                "source": comps_run.id,
            })

    lbo_run = latest("modeling", "lbo_model")
    if lbo_run:
        lr = (lbo_run.input_payload or {}).get("lbo_result") or {}
        entry_eq = lr.get("entry_equity")
        exit_eq = lr.get("exit_equity")
        if entry_eq is not None:
            ranges.append({
                "method": "LBO",
                "low": float(entry_eq),
                "mid": float((float(entry_eq) + float(exit_eq or entry_eq)) / 2),
                "high": float(exit_eq or entry_eq),
                "source": lbo_run.id,
            })

    return ranges


# ------------------------------------------------------------------
# Rendering
# ------------------------------------------------------------------

def render_football_field(
    ranges: list[dict[str, Any]],
    path: str,
    current_market_cap: float | None = None,
    currency: str = "INR",
) -> str | None:
    """Render a horizontal bar chart (football field) to a PNG file.

    Returns the path on success, None if matplotlib is unavailable or
    there are no ranges to plot.
    """
    if not ranges:
        logger.info("No valuation ranges to plot — skipping football field.")
        return None

    try:
        import matplotlib
        matplotlib.use("Agg")  # non-interactive backend
        import matplotlib.pyplot as plt
        import matplotlib.ticker as mticker
    except ImportError:
        logger.warning("matplotlib not installed — football field chart disabled.")
        return None

    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)

    # Sort methods in presentation order: DCF first, LBO last
    method_order = {"DCF": 0, "Trading Comps": 1, "Precedent Transactions": 2, "LBO": 3}
    ranges_sorted = sorted(ranges, key=lambda r: method_order.get(r["method"], 99))

    methods = [r["method"] for r in ranges_sorted]
    lows = [r["low"] for r in ranges_sorted]
    mids = [r["mid"] for r in ranges_sorted]
    highs = [r["high"] for r in ranges_sorted]

    n = len(methods)
    fig, ax = plt.subplots(figsize=(10, max(3, 1.2 * n)))

    y_positions = list(range(n))
    bar_height = 0.5

    # Color palette — investment banking navy/steel
    colors = ["#1a3a5c", "#2c5f8a", "#4a90b8", "#6fb0d4"]

    for i, (method, low, mid, high) in enumerate(zip(methods, lows, mids, highs)):
        color = colors[i % len(colors)]
        # Draw range bar (low to high)
        ax.barh(
            i, high - low, left=low, height=bar_height,
            color=color, alpha=0.75, edgecolor="#0d1f33", linewidth=0.8,
        )
        # Draw base case marker
        ax.plot(
            mid, i, marker="D", color="white", markersize=7,
            markeredgecolor="#0d1f33", markeredgewidth=1.2, zorder=5,
        )
        # Label the endpoints
        ax.text(low - (high - low) * 0.02, i, f"{low:,.0f}", va="center", ha="right",
                fontsize=8, color="#555555")
        ax.text(high + (high - low) * 0.02, i, f"{high:,.0f}", va="center", ha="left",
                fontsize=8, color="#555555")

    # Current market cap dashed line
    if current_market_cap and current_market_cap > 0:
        ax.axvline(
            x=current_market_cap, color="#cc3333", linestyle="--",
            linewidth=1.5, alpha=0.8, zorder=4,
        )
        ax.text(
            current_market_cap, n - 0.1, f"Market Cap: {current_market_cap:,.0f}",
            fontsize=8, color="#cc3333", ha="center", va="bottom",
        )

    ax.set_yticks(y_positions)
    ax.set_yticklabels(methods, fontsize=10, fontweight="bold")
    ax.invert_yaxis()

    currency_symbol = "₹" if currency == "INR" else "$"
    ax.set_xlabel(f"Implied Equity Value ({currency_symbol})", fontsize=10, color="#333333")
    ax.xaxis.set_major_formatter(mticker.FuncFormatter(lambda x, _: f"{x:,.0f}"))

    ax.set_title(
        "Valuation Football Field",
        fontsize=14, fontweight="bold", color="#1a1a2e", pad=15,
    )

    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.spines["left"].set_visible(False)
    ax.tick_params(left=False)
    ax.grid(axis="x", alpha=0.3, linestyle="--")

    fig.tight_layout()
    fig.savefig(path, dpi=150, bbox_inches="tight", facecolor="white")
    plt.close(fig)

    logger.info("[FootballField] Chart saved to %s (%d methods)", path, n)
    return path
