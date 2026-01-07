import math
import streamlit as st

# ----------------------------
# CONFIG (EDIT AS YOU LIKE)
# ----------------------------

# Path D – deploy tiers: as account grows, % deployed per main trade shrinks.
# These are for Trade #1; Trade #2 automatically uses half of this.
INVEST_TIERS = [
    (25000, 35.0),       # up to 25k → can deploy up to 35% per main trade
    (100000, 25.0),      # 25k–100k → 25%
    (300000, 15.0),      # 100k–300k → 15%
    (float("inf"), 8.0), # 300k+ → 8%
]

# Risk tiers — cap account risk per trade to around 1–2%
RISK_TIERS = [
    (25000, 2.0),        # up to 25k → risk up to 2.0% of account at SL
    (100000, 1.8),       # 25k–100k → 1.8%
    (300000, 1.5),       # 100k–300k → 1.5%
    (float("inf"), 1.2), # 300k+ → 1.2%
]

# Default TP% on the option premium when not in account-target mode
DEFAULT_TP_PERCENT = 10.0

# Base SL on option premium (wider to respect SPY volatility and reduce over-sizing)
SL_TRADE1_BASE = 30.0     # Trade #1: 30% SL on premium
SL_TRADE2_BASE = 24.0     # Starting point for Trade #2, tightened by entry price

# Trade #2 tightening based on entry price (for cheaper contracts, tighten more)
TRADE2_TIGHTENING_RULES = [
    (0.25, 4.0),        # <= 0.25 → tighten by 4%
    (0.35, 3.0),        # <= 0.35 → tighten by 3%
    (0.50, 2.0),        # <= 0.50 → tighten by 2%
    (float("inf"), 0.0) # above → no extra tightening
]
SL_TRADE2_MIN = 15.0     # Floor for SL% on trade 2
SL_TRADE2_MAX = 26.0     # Ceiling for SL% on trade 2

# Soft guidance for account impact
MIN_GOAL_ACCT_GAIN = 0.20   # min useful account gain %
MAX_GOAL_ACCT_GAIN = 3.00   # max sane account gain % for this tool


# ----------------------------
# HELPERS
# ----------------------------

def tier_lookup(value, tiers):
    """Return the percentage for the first tier where value <= max_val."""
    for max_val, pct in tiers:
        if value <= max_val:
            return pct
    return tiers[-1][1]

def invest_percent(balance, trade_number):
    """Deploy % of account based on Path D tiers."""
    base = tier_lookup(balance, INVEST_TIERS)
    # Trade #2 uses half the deploy size of Trade #1
    return base if trade_number == 1 else base / 2.0

def risk_percent(balance):
    """Max account risk % based on account balance."""
    return tier_lookup(balance, RISK_TIERS)

def trade2_dynamic_sl(entry_price):
    """
    For trade #2, tighten SL% based on option price.
    Cheaper contracts → tighter SL floor, within min/max.
    """
    extra = 0.0
    for upper, tighten in TRADE2_TIGHTENING_RULES:
        if entry_price <= upper:
            extra = tighten
            break
    sl = SL_TRADE2_BASE - extra
    return max(SL_TRADE2_MIN, min(SL_TRADE2_MAX, sl))

def compute_tp_percent_for_target_account_gain(balance, entry_price, contracts, target_account_gain_pct):
    """
    Given a desired account % gain for the trade, compute needed TP% on the option premium.
    """
    if contracts <= 0 or balance <= 0 or entry_price <= 0:
        return None
    profit_goal = balance * (target_account_gain_pct / 100.0)
    denom = entry_price * 100.0 * contracts
    if denom <= 0:
        return None
    return (profit_goal / denom) * 100.0

def calc(balance, entry_price, trade_number,
         mode_target_gain, target_gain_pct, tp_pct_manual):
    """
    Core sizing + TP/SL math.
    """
    inv_pct = invest_percent(balance, trade_number)
    rsk_pct = risk_percent(balance)

    inv_budget = balance * inv_pct / 100.0
    rsk_budget = balance * rsk_pct / 100.0

    # SL% on premium
    if trade_number == 1:
        sl_pct = SL_TRADE1_BASE
    else:
        sl_pct = trade2_dynamic_sl(entry_price)

    cost_per_contract = entry_price * 100.0
    sl_price = entry_price * (1.0 - sl_pct / 100.0)
    loss_per_contract = (entry_price - sl_price) * 100.0

    # How many contracts fit both the deploy AND risk limits?
    max_by_invest = math.floor(inv_budget / cost_per_contract) if cost_per_contract > 0 else 0
    max_by_risk = math.floor(rsk_budget / loss_per_contract) if loss_per_contract > 0 else 0
    contracts = max(0, min(max_by_invest, max_by_risk))

    # TP% on the premium, either derived from account target or fixed manually
    if mode_target_gain:
        tp_pct = compute_tp_percent_for_target_account_gain(balance, entry_price, contracts, target_gain_pct)
        tp_pct = tp_pct if tp_pct is not None else 0.0
    else:
        tp_pct = tp_pct_manual

    tp_price = entry_price * (1.0 + tp_pct / 100.0)

    pos_cost = contracts * cost_per_contract
    profit_tp = (tp_price - entry_price) * 100.0 * contracts
    loss_sl = (entry_price - sl_price) * 100.0 * contracts

    acct_gain_tp = (profit_tp / balance * 100.0) if balance > 0 else 0.0
    acct_loss_sl = (loss_sl / balance * 100.0) if balance > 0 else 0.0

    return {
        "contracts": contracts,
        "inv_pct": inv_pct,
        "rsk_pct": rsk_pct,
        "inv_budget": inv_budget,
        "rsk_budget": rsk_budget,
        "sl_pct": sl_pct,
        "tp_pct": tp_pct,
        "cost_per_contract": cost_per_contract,
        "pos_cost": pos_cost,
        "tp_price": tp_price,
        "sl_price": sl_price,
        "profit_tp": profit_tp,
        "loss_sl": loss_sl,
        "max_by_invest": max_by_invest,
        "max_by_risk": max_by_risk,
        "acct_gain_tp": acct_gain_tp,
        "acct_loss_sl": acct_loss_sl,
    }


# ----------------------------
# UI (Responsive + Mobile-friendly)
# ----------------------------

st.set_page_config(page_title="SPY Options Size Checker", layout="wide")

theme_dark = st.toggle("🌗 Dark mode", value=True)

if theme_dark:
    bg = "#0b0f19"
    card = "rgba(255,255,255,0.04)"
    border = "rgba(255,255,255,0.10)"
    text = "rgba(255,255,255,0.92)"
    subtle = "rgba(255,255,255,0.70)"
else:
    bg = "#ffffff"
    card = "rgba(0,0,0,0.03)"
    border = "rgba(0,0,0,0.10)"
    text = "rgba(0,0,0,0.88)"
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
  padding: 14px 16px;
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
    '<div class="small">'
    "Phone + desktop friendly. Auto-sizes contracts using Path D tiers, caps risk ~1–2% of account, "
    "uses SPY-aware SLs, and supports fixed TP% or target account-gain mode with optional Turbo Light trades."
    "</div>",
    unsafe_allow_html=True,
)

st.write("")

# Inputs
c1, c2 = st.columns(2)
with c1:
    balance = st.number_input("Account balance ($)", min_value=0.0, value=467.0, step=10.0)
    entry_price = st.number_input(
        "Entry price (option premium)",
        min_value=0.01,
        value=0.25,
        step=0.01,
        format="%.2f",
    )
with c2:
    trade_number = st.radio("Trade of the week", [1, 2], horizontal=True)
    st.caption("1 = main trade • 2 = reduced trade (half deploy, tighter SL)")

st.write("")

# Estimated fees per contract (regulatory + OCC + broker)
est_fee_per_contract = st.number_input(
    "Estimated fees per contract ($)",
    min_value=0.00,
    value=0.04,    # tweak if you see a different average on Webull
    step=0.01,
    format="%.2f",
    help="Rough average of SEC/OCC/regulatory fees per contract. Used to show net P&L after fees."
)

# Turbo light toggle
turbo_mode = st.toggle("⚡ Turbo light trade (optional high-conviction)", value=False)
if turbo_mode:
    st.caption(
        "Turbo light: same risk rules, but higher account/TP target for this trade "
        "(e.g., a 2–3% ‘special’ trade, still within your global risk rules)."
    )

# Mode: target account gain vs fixed TP%
mode_target_gain = st.toggle("🎯 Target account % gain (auto TP%)", value=True)

if mode_target_gain:
    # Align defaults with your realistic net weekly structure:
    # Trade 1 → ~0.9% account gain target
    # Trade 2 → ~0.3% account gain target
    if turbo_mode:
        default_target_gain = 2.5   # Turbo: heavier but still <= 3%
    else:
        default_target_gain = 0.9 if trade_number == 1 else 0.3

    target_gain_pct = st.slider(
        "Target gain on TOTAL account (%)",
        MIN_GOAL_ACCT_GAIN,
        MAX_GOAL_ACCT_GAIN,
        default_target_gain,
        0.05,
    )
    tp_pct_manual = DEFAULT_TP_PERCENT
else:
    target_gain_pct = 1.0
    # In turbo mode, default to a higher premium TP% (e.g., 20% instead of 10%)
    if turbo_mode:
        default_tp_pct = 20.0
    else:
        default_tp_pct = DEFAULT_TP_PERCENT
    tp_pct_manual = st.slider(
        "Fixed TP (%) on option premium",
        2.0,
        40.0,
        default_tp_pct,
        0.5,
    )

# Core calculations
res = calc(balance, entry_price, trade_number, mode_target_gain, target_gain_pct, tp_pct_manual)

# Compute fee-adjusted P&L and net account gain
total_est_fees = est_fee_per_contract * res["contracts"]
net_profit_tp = res["profit_tp"] - total_est_fees
net_acct_gain_tp = (net_profit_tp / balance * 100.0) if balance > 0 else 0.0

# Summary card
st.markdown('<div class="card">', unsafe_allow_html=True)
s1, s2 = st.columns(2)
with s1:
    st.metric("Contracts", res["contracts"])
    st.metric("Position Cost", f'${res["pos_cost"]:.2f}')
with s2:
    st.metric("Deploy % (auto)", f'{res["inv_pct"]:.1f}%')
    st.metric("Risk % (auto)", f'{res["rsk_pct"]:.1f}%')
st.markdown('</div>', unsafe_allow_html=True)

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
e1.metric("TP Price", f'${res["tp_price"]:.2f}')
e2.metric("SL Price", f'${res["sl_price"]:.2f}')
st.caption(
    f"SL % used: {res['sl_pct']:.1f}% • TP % used: {res['tp_pct']:.2f}%"
    + (" • Turbo Light ON" if turbo_mode else "")
)
st.markdown('</div>', unsafe_allow_html=True)

st.write("")

# P&L card
st.subheader("P&L at TP/SL")
st.markdown('<div class="card">', unsafe_allow_html=True)
p1, p2 = st.columns(2)
p1.metric("Gross Profit at TP", f'${res["profit_tp"]:.2f}')
p2.metric("Loss at SL", f'${res["loss_sl"]:.2f}')
st.caption(
    f"Gross account impact → TP: {res['acct_gain_tp']:.2f}% • SL: {res['acct_loss_sl']:.2f}%"
)
st.write(f"Estimated total fees: **${total_est_fees:.2f}**")
st.write(f"Net profit at TP (after est. fees): **${net_profit_tp:.2f}**")
st.write(f"Net account gain at TP (after est. fees): **{net_acct_gain_tp:.2f}%**")
st.markdown('</div>', unsafe_allow_html=True)

st.write("")

# Weekly goal + risk guidance (use NET gain for guidance)
st.subheader("Goal & Risk Checks")
st.markdown('<div class="card">', unsafe_allow_html=True)

g_net = net_acct_gain_tp
l = res["acct_loss_sl"]

if res["contracts"] == 0 or g_net == 0:
    st.info("This plan currently sizes to 0% account gain (probably 0 contracts).")
else:
    if g_net < MIN_GOAL_ACCT_GAIN:
        st.info(
            f"This trade targets only ~{g_net:.2f}% NET account gain — smaller than your 0.20%+ guidance. "
            "That’s totally fine if the setup is weaker or you want extra safety."
        )
    elif g_net > MAX_GOAL_ACCT_GAIN:
        st.warning(
            f"This trade targets ~{g_net:.2f}% NET account gain, above the 3% guidance. "
            "Strongly consider reducing size or lowering your target."
        )
    else:
        st.success(
            f"This trade targets ~{g_net:.2f}% NET account gain — inside your 0.20%–3.00% goal band."
        )

# Soft cap on account % loss at SL per trade type
max_loss_trade1 = 1.2   # you can tune these
max_loss_trade2 = 0.9
max_loss_allowed = max_loss_trade1 if trade_number == 1 else max_loss_trade2

if l > 0:
    if l > max_loss_allowed:
        st.error(
            f"Warning: this stop would risk ~{l:.2f}% of the account "
            f"(soft max for this trade type: {max_loss_allowed:.2f}%). "
            "Consider fewer contracts or a tighter SL."
        )
    else:
        st.info(
            f"Account loss at SL is ~{l:.2f}% — within your soft risk comfort for this trade type."
        )

st.markdown('</div>', unsafe_allow_html=True)

st.write("")

# Budgets card
st.subheader("Budgets & Limits")
st.markdown('<div class="card">', unsafe_allow_html=True)
st.write(f"Deploy budget: **${res['inv_budget']:.2f}** • Risk budget: **${res['rsk_budget']:.2f}**")
st.write(f"Cost/contract: **${res['cost_per_contract']:.2f}**")
st.write(
    f"Max contracts by deploy: **{res['max_by_invest']}** • "
    f"Max contracts by risk: **{res['max_by_risk']}**"
)
if mode_target_gain:
    st.write(
        f"Target account gain (gross): **{target_gain_pct:.2f}%** → TP% on premium (auto): "
        f"**{res['tp_pct']:.2f}%**"
    )
else:
    st.write(f"TP% on premium (fixed): **{res['tp_pct']:.2f}%**")
st.markdown('</div>', unsafe_allow_html=True)

st.write("")

# Copy-ready block for quick reference
st.subheader("Copy-ready plan")
copy_text = (
    f"ENTRY ${entry_price:.2f} | CONTRACTS {res['contracts']} | "
    f"TP ${res['tp_price']:.2f} (TP% {res['tp_pct']:.2f}) | "
    f"SL ${res['sl_price']:.2f} (SL% {res['sl_pct']:.2f}) | "
    f"POS COST ${res['pos_cost']:.2f} | "
    f"GROSS P@TP ${res['profit_tp']:.2f} | L@SL ${res['loss_sl']:.2f} | "
    f"FEES ~${total_est_fees:.2f} | NET P@TP ${net_profit_tp:.2f} | "
    f"NET ACCT GAIN {net_acct_gain_tp:.2f}%"
)
if turbo_mode:
    copy_text += " | MODE: TURBO LIGHT"

st.code(copy_text, language="text")
st.caption("Chromebook tip: tap-and-hold or drag-select to copy. Desktop: highlight + Ctrl/Cmd+C.")
st.caption("Not financial advice. Tool is for sizing/risk math only.")
