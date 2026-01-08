import math
import streamlit as st

# ----------------------------
# CONFIG
# ----------------------------

MIN_TICK = 0.01  # SPY options tick size

# As account grows, % deployed per main trade shrinks.
INVEST_TIERS = [
    (25000, 35.0),
    (100000, 25.0),
    (300000, 15.0),
    (float("inf"), 8.0),
]

# Risk tiers — cap account risk per trade around ~1–2%
RISK_TIERS = [
    (25000, 2.0),
    (100000, 1.8),
    (300000, 1.5),
    (float("inf"), 1.2),
]

# Base SL on option premium
SL_TRADE1_BASE = 30.0          # Trade 1 SL% on premium
SL_TRADE2_BASE = 24.0          # Starting SL% for trade 2 before tightening

# Trade 2: tighter SL for cheaper contracts
TRADE2_TIGHTENING_RULES = [
    (0.25, 4.0),
    (0.35, 3.0),
    (0.50, 2.0),
    (float("inf"), 0.0),
]
SL_TRADE2_MIN = 15.0
SL_TRADE2_MAX = 26.0

# Target account-gain guidance
MIN_GOAL_ACCT_GAIN = 0.20
MAX_GOAL_ACCT_GAIN = 1.00


# ----------------------------
# HELPERS
# ----------------------------

def tier_lookup(value, tiers):
    """Return percentage for the first tier where value <= max_val."""
    for max_val, pct in tiers:
        if value <= max_val:
            return pct
    return tiers[-1][1]


def invest_percent(balance, trade_number):
    """
    Trade #1 gets full deploy %.
    Trade #2 gets half deploy %.
    """
    base = tier_lookup(balance, INVEST_TIERS)
    return base if trade_number == 1 else base / 2.0


def base_risk_percent(balance):
    """Base risk% from tiers (before trade-2 reduction)."""
    return tier_lookup(balance, RISK_TIERS)


def trade2_dynamic_sl(entry_price):
    """Tighten SL% for trade #2 based on option price."""
    extra = 0.0
    for upper, tighten in TRADE2_TIGHTENING_RULES:
        if entry_price <= upper:
            extra = tighten
            break
    sl = SL_TRADE2_BASE - extra
    return max(SL_TRADE2_MIN, min(SL_TRADE2_MAX, sl))


def compute_tp_percent_for_target_account_gain(
    balance,
    entry_price,
    contracts,
    target_account_gain_pct,
    fee_per_contract,
):
    """
    Given a desired NET account % gain for the trade, compute needed TP% on the option premium.
    We gross up by estimated round-trip fees so the NET gain is as close as possible
    to the requested percentage.
    """
    if contracts <= 0 or balance <= 0 or entry_price <= 0:
        return None

    # Target net profit in dollars (after fees)
    profit_goal_net = balance * (target_account_gain_pct / 100.0)

    # Estimated round-trip fees (buy + sell)
    total_fees_est = fee_per_contract * contracts * 2.0

    # Need this much gross profit on the option to hit the net goal
    profit_goal_gross = profit_goal_net + total_fees_est

    denom = entry_price * 100.0 * contracts
    if denom <= 0:
        return None

    return (profit_goal_gross / denom) * 100.0


# ----------------------------
# CORE CALC
# ----------------------------


def calc(balance, entry_price, trade_number, target_gain_pct, fee_per_contract):
    """
    Core sizing + TP/SL math.

    All account impact percentages are based on ACCOUNT balance, not contract size.

    Instead of always using the maximum contracts, we search all valid contract counts
    and pick the one whose NET account gain (after fees) is closest to target_gain_pct.
    """

    inv_pct = invest_percent(balance, trade_number)
    rsk_pct_base = base_risk_percent(balance)

    # Trade #2 uses half risk budget as well as half deploy
    if trade_number == 1:
        rsk_pct = rsk_pct_base
    else:
        rsk_pct = rsk_pct_base / 2.0

    inv_budget = balance * inv_pct / 100.0
    rsk_budget = balance * rsk_pct / 100.0

    # SL% used for actual P&L
    if trade_number == 1:
        sl_pct = SL_TRADE1_BASE
    else:
        sl_pct = trade2_dynamic_sl(entry_price)

    cost_per_contract = entry_price * 100.0

    # Actual SL price & per-contract loss
    sl_price = entry_price * (1.0 - sl_pct / 100.0)
    loss_per_contract_actual = (entry_price - sl_price) * 100.0

    # ---- RISK LIMIT: do NOT let tighter SL on trade 2 increase size ----
    if trade_number == 1:
        sl_pct_risk = sl_pct
    else:
        # For risk budgeting we pretend trade 2 has the same SL% as trade 1,
        # so trade 2 cannot be larger just because the SL is tighter.
        sl_pct_risk = SL_TRADE1_BASE

    sl_price_risk = entry_price * (1.0 - sl_pct_risk / 100.0)
    loss_per_contract_risk = (entry_price - sl_price_risk) * 100.0
    # --------------------------------------------------------------------

    # Contract limits from deploy & risk budgets
    if cost_per_contract > 0:
        max_by_invest = math.floor(inv_budget / cost_per_contract)
    else:
        max_by_invest = 0

    if loss_per_contract_risk > 0:
        max_by_risk = math.floor(rsk_budget / loss_per_contract_risk)
    else:
        max_by_risk = 0

    max_contracts = max(0, min(max_by_invest, max_by_risk))

    # If nothing fits, return a "zero" plan
    if max_contracts == 0:
        return {
            "contracts": 0,
            "inv_pct": inv_pct,
            "rsk_pct": rsk_pct,
            "sl_pct": sl_pct,
            "tp_pct_effective": 0.0,
            "pos_cost": 0.0,
            "tp_price": entry_price,
            "sl_price": sl_price,
            "profit_tp_gross": 0.0,
            "loss_sl": 0.0,
            "total_fees_est": 0.0,
            "net_profit_tp": 0.0,
            "acct_gain_tp_gross": 0.0,
            "acct_loss_sl_gross": 0.0,
            "acct_gain_tp_net": 0.0,
            "max_by_invest": max_by_invest,
            "max_by_risk": max_by_risk,
            "inv_budget": inv_budget,
            "rsk_budget": rsk_budget,
            "cost_per_contract": cost_per_contract,
        }

    # SEARCH over all possible contract counts (1..max_contracts)
    best = None

    for n in range(1, max_contracts + 1):
        # 1) what TP% on premium is needed (before rounding)?
        tp_pct_raw = compute_tp_percent_for_target_account_gain(
            balance,
            entry_price,
            n,
            target_gain_pct,
            fee_per_contract,
        )
        if tp_pct_raw is None:
            continue

        # 2) ideal (unrounded) TP price
        tp_price_unrounded = entry_price * (1.0 + tp_pct_raw / 100.0)

        # 3) round to nearest cent
        tp_price = round(tp_price_unrounded, 2)

        # 4) ensure TP > entry, otherwise bump by one tick
        if tp_price <= entry_price:
            tp_price = round(entry_price + MIN_TICK, 2)

        # 5) effective TP% after rounding
        if entry_price > 0:
            tp_pct_effective = ((tp_price / entry_price) - 1.0) * 100.0
        else:
            tp_pct_effective = 0.0

        # 6) position-level P&L (gross)
        pos_cost = n * cost_per_contract
        profit_tp_gross = (tp_price - entry_price) * 100.0 * n
        loss_sl = loss_per_contract_actual * n

        # 7) fees (round-trip)
        total_fees_est = fee_per_contract * n * 2.0

        # 8) net profit after fees
        net_profit_tp = profit_tp_gross - total_fees_est

        # 9) account-level impact
        if balance > 0:
            acct_gain_tp_gross = profit_tp_gross / balance * 100.0
            acct_loss_sl_gross = loss_sl / balance * 100.0
            acct_gain_tp_net = net_profit_tp / balance * 100.0
        else:
            acct_gain_tp_gross = 0.0
            acct_loss_sl_gross = 0.0
            acct_gain_tp_net = 0.0

        # 10) how close are we to target (NET account %)?
        diff = abs(acct_gain_tp_net - target_gain_pct)

        candidate = {
            "contracts": n,
            "inv_pct": inv_pct,
            "rsk_pct": rsk_pct,
            "sl_pct": sl_pct,
            "tp_pct_effective": tp_pct_effective,
            "pos_cost": pos_cost,
            "tp_price": tp_price,
            "sl_price": sl_price,
            "profit_tp_gross": profit_tp_gross,
            "loss_sl": loss_sl,
            "total_fees_est": total_fees_est,
            "net_profit_tp": net_profit_tp,
            "acct_gain_tp_gross": acct_gain_tp_gross,
            "acct_loss_sl_gross": acct_loss_sl_gross,
            "acct_gain_tp_net": acct_gain_tp_net,
            "max_by_invest": max_by_invest,
            "max_by_risk": max_by_risk,
            "inv_budget": inv_budget,
            "rsk_budget": rsk_budget,
            "cost_per_contract": cost_per_contract,
            "diff_from_target": diff,
        }

        # Keep the candidate closest to target_gain_pct (NET)
        if best is None or diff < best["diff_from_target"]:
            best = candidate

    if best is None:
        # Shouldn't really happen, but safe fallback
        return {
            "contracts": 0,
            "inv_pct": inv_pct,
            "rsk_pct": rsk_pct,
            "sl_pct": sl_pct,
            "tp_pct_effective": 0.0,
            "pos_cost": 0.0,
            "tp_price": entry_price,
            "sl_price": sl_price,
            "profit_tp_gross": 0.0,
            "loss_sl": 0.0,
            "total_fees_est": 0.0,
            "net_profit_tp": 0.0,
            "acct_gain_tp_gross": 0.0,
            "acct_loss_sl_gross": 0.0,
            "acct_gain_tp_net": 0.0,
            "max_by_invest": max_by_invest,
            "max_by_risk": max_by_risk,
            "inv_budget": inv_budget,
            "rsk_budget": rsk_budget,
            "cost_per_contract": cost_per_contract,
        }

    best.pop("diff_from_target", None)
    return best


# ----------------------------
# UI
# ----------------------------

st.set_page_config(page_title="SPY Options Size Checker", layout="wide")

theme_dark = st.toggle("🌗 Dark mode", value=True)

if theme_dark:
    bg = "#0b0f19"
    card = "#101624"
    border = "rgba(255,255,255,0.12)"
    text = "rgba(255,255,255,0.96)"
    subtle = "rgba(255,255,255,0.72)"
else:
    bg = "#ffffff"
    card = "#f5f5f7"
    border = "rgba(0,0,0,0.10)"
    text = "rgba(0,0,0,0.90)"
    subtle = "rgba(0,0,0,0.65)"

st.markdown(
    f"""
<style>
html, body, [class*="css"] {{
  background-color: {bg};
  color: {text};
}}
.block-container {{
  max-width: 980px;
  padding-top: 1.6rem;
  padding-bottom: 2.2rem;
}}
.card {{
  border: 1px solid {border};
  border-radius: 16px;
  padding: 16px 18px;
  background: {card};
}}
.small {{
  color: {subtle};
  font-size: 0.95rem;
  line-height: 1.35rem;
}}
button[kind="primary"], button[kind="secondary"] {{
  border-radius: 12px !important;
}}
[data-testid="stMetricValue"] {{
  font-size: 1.35rem;
}}
@media (max-width: 700px) {{
  .block-container {{
    padding-left: 0.9rem;
    padding-right: 0.9rem;
  }}
  [data-testid="stMetricValue"] {{
    font-size: 1.15rem;
  }}
}}
</style>
""",
    unsafe_allow_html=True,
)

st.title("SPY Options Size Checker")

st.markdown(
    '<div class="card small">'
    "Phone + desktop friendly. Sizes SPY options from your account balance, "
    "caps risk around ~1–2% per trade, and aims for small steady account gains "
    "(0.20%–1.00% net per trade after estimated fees). "
    "<br><br>"
    "<b>Trade 1</b>: full deploy & risk tiers. "
    "<b>Trade 2</b>: half deploy, half risk budget, tighter SL so the second "
    "trade is always lighter than the first."
    "</div>",
    unsafe_allow_html=True,
)

st.write("")

# Inputs
c1, c2 = st.columns(2)
with c1:
    balance = st.number_input(
        "Account balance ($)",
        min_value=0.0,
        value=467.0,
        step=10.0,
    )
with c2:
    trade_number = st.radio("Trade of the week", [1, 2], horizontal=True)
st.caption("1 = main trade • 2 = secondary trade (half deploy, half risk budget, tighter SL).")

c3, c4 = st.columns(2)
with c3:
    entry_price = st.number_input(
        "Entry price (option premium)",
        min_value=0.01,
        value=0.25,
        step=0.01,
        format="%.2f",
    )
with c4:
    fee_per_contract = st.number_input(
        "Estimated fees per contract ($, round trip)",
        min_value=0.00,
        value=0.04,
        step=0.01,
        format="%.2f",
        help="Approximate total of all commissions/fees for one contract: buy + sell.",
    )

st.write("")

# Target account gain slider (always account-based, net-of-fees target)
default_target_gain = 0.80 if trade_number == 1 else 0.40
target_gain_pct = st.slider(
    "Target gain on TOTAL account (%)",
    min_value=MIN_GOAL_ACCT_GAIN,
    max_value=MAX_GOAL_ACCT_GAIN,
    value=default_target_gain,
    step=0.01,
    help="All sizing is based on account % gain, not contract %. Range is 0.20%–1.00% per trade.",
)

# Core calculations
res = calc(
    balance=balance,
    entry_price=entry_price,
    trade_number=trade_number,
    target_gain_pct=target_gain_pct,
    fee_per_contract=fee_per_contract,
)

# Summary card
st.markdown('<div class="card">', unsafe_allow_html=True)
s1, s2 = st.columns(2)
with s1:
    st.metric("Contracts", res["contracts"])
    st.metric("Position Cost", f'${{res["pos_cost"]:.2f}')
with s2:
    st.metric("Deploy % (auto)", f'{res["inv_pct"]:.1f}%')
    st.metric("Risk % (auto)", f'{res["rsk_pct"]:.1f}%')
st.markdown("</div>", unsafe_allow_html=True)

if res["contracts"] == 0:
    st.warning(
        "Under your deploy/risk rules, this entry price is too expensive for any contracts "
        "(contracts = 0). Consider a cheaper strike or smaller premium."
    )

st.write("")

# Exit levels
st.subheader("Exit Levels")
st.markdown('<div class="card">', unsafe_allow_html=True)
e1, e2 = st.columns(2)
e1.metric("TP Price", f'${{res["tp_price"]:.2f}')
e2.metric("SL Price", f'${{res["sl_price"]:.2f}')
st.caption(
    f"SL % used: {res['sl_pct']:.1f}% • Effective TP % on premium: {res['tp_pct_effective']:.2f}%"
)
st.markdown("</div>", unsafe_allow_html=True)

st.write("")

# P&L card
st.subheader("P&L at TP/SL")
st.markdown('<div class="card">', unsafe_allow_html=True)
p1, p2 = st.columns(2)
p1.metric("Profit at TP (gross)", f'${{res["profit_tp_gross"]:.2f}')
p2.metric("Loss at SL (gross)", f'${{res["loss_sl"]:.2f}')

st.caption(
    f"Gross account impact → TP: {res['acct_gain_tp_gross']:.2f}% • "
    f"SL: {res['acct_loss_sl_gross']:.2f}% (based on ACCOUNT balance)."
)
st.caption(
    f"Estimated total fees: ${{res['total_fees_est']:.2f}}  |  "
    f"Net profit at TP (after est. fees): ${{res['net_profit_tp']:.2f}}  |  "
    f"Net account gain at TP (after est. fees): {res['acct_gain_tp_net']:.2f}%"
)
st.markdown("</div>", unsafe_allow_html=True)

st.write("")

# Budgets & limits
st.subheader("Budgets & Limits")
st.markdown('<div class="card">', unsafe_allow_html=True)
st.write(f"Deploy budget: **${{res['inv_budget']:.2f}}** • Risk budget: **${{res['rsk_budget']:.2f}}**")
st.write(f"Cost/contract: **${{res['cost_per_contract']:.2f}}**")
st.write(
    f"Max contracts by deploy: **{res['max_by_invest']}** • "
    f"Max contracts by risk: **{res['max_by_risk']}**"
)
st.markdown("</div>", unsafe_allow_html=True)

st.write("")

# Copy-ready block
st.subheader("Copy-ready plan")
copy_text = (
    f"ENTRY ${entry_price:.2f} | CONTRACTS {res['contracts']} | "
    f"TP ${res['tp_price']:.2f} | SL ${res['sl_price']:.2f} | "
    f"POS COST ${res['pos_cost']:.2f} | "
    f"P@TP (gross) ${res['profit_tp_gross']:.2f} | "
    f"L@SL (gross) ${res['loss_sl']:.2f} | "
    f"NET P@TP (after est. fees) ${res['net_profit_tp']:.2f} | "
    f"NET ACCT GAIN {res['acct_gain_tp_net']:.2f}%"
)
st.code(copy_text, language="text")
st.caption("Not financial advice. Tool is for position sizing / risk math only.")
