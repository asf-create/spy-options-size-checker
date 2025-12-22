import math
import streamlit as st

# ----------------------------
# CONFIG (EDIT AS YOU LIKE)
# ----------------------------
INVEST_TIERS = [
    (1000,  30.0),
    (5000,  25.0),
    (10000, 22.0),
    (25000, 20.0),
    (50000, 15.0),
    (100000, 12.0),
    (float("inf"), 10.0),
]

RISK_TIERS = [
    (1000,  6.0),
    (5000,  5.0),
    (10000, 4.0),
    (25000, 3.0),
    (50000, 2.5),
    (100000, 2.0),
    (float("inf"), 1.5),
]

DEFAULT_TP_PERCENT = 10.0

SL_TRADE1_BASE = 25.0
SL_TRADE2_BASE = 20.0

TRADE2_TIGHTENING_RULES = [
    (0.25, 3.0),
    (0.35, 2.0),
    (0.50, 1.0),
    (float("inf"), 0.0),
]
SL_TRADE2_MIN = 12.0
SL_TRADE2_MAX = 22.0


# ----------------------------
# HELPERS
# ----------------------------
def tier_lookup(value, tiers):
    for max_val, pct in tiers:
        if value <= max_val:
            return pct
    return tiers[-1][1]

def invest_percent(balance, trade_number):
    base = tier_lookup(balance, INVEST_TIERS)
    return base if trade_number == 1 else base / 2.0

def risk_percent(balance):
    return tier_lookup(balance, RISK_TIERS)

def trade2_dynamic_sl(entry_price):
    extra = 0.0
    for upper, tighten in TRADE2_TIGHTENING_RULES:
        if entry_price <= upper:
            extra = tighten
            break
    sl = SL_TRADE2_BASE - extra
    return max(SL_TRADE2_MIN, min(SL_TRADE2_MAX, sl))

def compute_tp_percent_for_target_account_gain(balance, entry_price, contracts, target_account_gain_pct):
    if contracts <= 0 or balance <= 0 or entry_price <= 0:
        return None
    profit_goal = balance * (target_account_gain_pct / 100.0)
    denom = entry_price * 100.0 * contracts
    if denom <= 0:
        return None
    return (profit_goal / denom) * 100.0

def calc(balance, entry_price, trade_number, mode_target_gain, target_gain_pct, tp_pct_manual):
    inv_pct = invest_percent(balance, trade_number)
    rsk_pct = risk_percent(balance)

    inv_budget = balance * inv_pct / 100.0
    rsk_budget = balance * rsk_pct / 100.0

    sl_pct = SL_TRADE1_BASE if trade_number == 1 else trade2_dynamic_sl(entry_price)

    cost_per_contract = entry_price * 100.0
    sl_price = entry_price * (1.0 - sl_pct / 100.0)
    loss_per_contract = (entry_price - sl_price) * 100.0

    max_by_invest = math.floor(inv_budget / cost_per_contract) if cost_per_contract > 0 else 0
    max_by_risk = math.floor(rsk_budget / loss_per_contract) if loss_per_contract > 0 else 0
    contracts = max(0, min(max_by_invest, max_by_risk))

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
        "inv_pct": inv_pct, "rsk_pct": rsk_pct,
        "inv_budget": inv_budget, "rsk_budget": rsk_budget,
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

st.markdown(f"""
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
/* Make inputs & buttons more tappable on mobile */
button[kind="primary"], button[kind="secondary"] {{
  border-radius: 12px !important;
}}
/* Reduce metric overflow on small screens */
[data-testid="stMetricValue"] {{
  font-size: 1.35rem;
}}
/* On small screens, tighten padding and stack nicely */
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
""", unsafe_allow_html=True)

st.title("SPY Options Size Checker")
st.markdown('<div class="small">Phone + desktop friendly. Auto-sizes contracts using deploy/risk tiers, tightens SL on trade #2, and supports fixed TP% or target account-gain mode.</div>', unsafe_allow_html=True)

st.write("")

# Inputs (2 columns works well on desktop; on mobile Streamlit stacks automatically)
c1, c2 = st.columns(2)
with c1:
    balance = st.number_input("Account balance ($)", min_value=0.0, value=467.0, step=10.0)
    entry_price = st.number_input("Entry price (option premium)", min_value=0.01, value=0.25, step=0.01, format="%.2f")
with c2:
    trade_number = st.radio("Trade of the week", [1, 2], horizontal=True)
    st.caption("1 = main trade • 2 = reduced trade")

st.write("")

mode_target_gain = st.toggle("🎯 Target account % gain (auto TP%)", value=True)
if mode_target_gain:
    target_gain_pct = st.slider("Target gain on TOTAL account (%)", 0.10, 3.00, 1.00, 0.05)
    tp_pct_manual = DEFAULT_TP_PERCENT
else:
    target_gain_pct = 1.0
    tp_pct_manual = st.slider("Fixed TP (%) on option premium", 2.0, 30.0, 10.0, 0.5)

res = calc(balance, entry_price, trade_number, mode_target_gain, target_gain_pct, tp_pct_manual)

# Summary (keep to max 2 columns for mobile readability)
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
    st.warning("Under your deploy/risk rules, this entry price is too expensive (contracts = 0).")

st.write("")

# Exit Levels (2 columns so mobile doesn’t squish)
st.subheader("Exit Levels")
st.markdown('<div class="card">', unsafe_allow_html=True)
e1, e2 = st.columns(2)
e1.metric("TP Price", f'${res["tp_price"]:.2f}')
e2.metric("SL Price", f'${res["sl_price"]:.2f}')
st.caption(f"SL % used: {res['sl_pct']:.1f}% • TP % used: {res['tp_pct']:.2f}%")
st.markdown('</div>', unsafe_allow_html=True)

st.write("")

# P&L (2 columns for mobile)
st.subheader("P&L at TP/SL")
st.markdown('<div class="card">', unsafe_allow_html=True)
p1, p2 = st.columns(2)
p1.metric("Profit at TP", f'${res["profit_tp"]:.2f}')
p2.metric("Loss at SL", f'${res["loss_sl"]:.2f}')
st.caption(f"Account impact → TP: {res['acct_gain_tp']:.2f}% • SL: {res['acct_loss_sl']:.2f}%")
st.markdown('</div>', unsafe_allow_html=True)

st.write("")

# Budgets card
st.subheader("Budgets & Limits")
st.markdown('<div class="card">', unsafe_allow_html=True)
st.write(f"Deploy budget: **${res['inv_budget']:.2f}** • Risk budget: **${res['rsk_budget']:.2f}**")
st.write(f"Cost/contract: **${res['cost_per_contract']:.2f}**")
st.write(f"Max contracts by deploy: **{res['max_by_invest']}** • Max contracts by risk: **{res['max_by_risk']}**")
if mode_target_gain:
    st.write(f"Target account gain: **{target_gain_pct:.2f}%** → TP% (auto): **{res['tp_pct']:.2f}%**")
else:
    st.write(f"TP% (fixed): **{res['tp_pct']:.2f}%**")
st.markdown('</div>', unsafe_allow_html=True)

st.write("")

# Copy-ready block (best cross-platform)
st.subheader("Copy-ready plan")
copy_text = (
    f"ENTRY ${entry_price:.2f} | CONTRACTS {res['contracts']} | "
    f"TP ${res['tp_price']:.2f} (TP% {res['tp_pct']:.2f}) | "
    f"SL ${res['sl_price']:.2f} (SL% {res['sl_pct']:.2f}) | "
    f"POS COST ${res['pos_cost']:.2f} | P@TP ${res['profit_tp']:.2f} | L@SL ${res['loss_sl']:.2f}"
)
st.code(copy_text, language="text")
st.caption("Chromebook tip: tap-and-hold or drag-select to copy. Desktop: highlight + Ctrl/Cmd+C.")
st.caption("Not financial advice. Tool is for sizing/risk math only.")
