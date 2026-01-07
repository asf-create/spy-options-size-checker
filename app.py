import math
import streamlit as st

# ----------------------------
# CONFIG — PATH D & RISK
# ----------------------------

INVEST_TIERS = [
    (25000, 35.0),
    (100000, 25.0),
    (300000, 15.0),
    (float("inf"), 8.0),
]

RISK_TIERS = [
    (25000, 2.0),
    (100000, 1.8),
    (300000, 1.5),
    (float("inf"), 1.2),
]

SL_TRADE1_BASE = 25.0
SL_TRADE2_BASE = 20.0

TRADE2_TIGHTENING_RULES = [
    (0.25, 3.0),
    (0.35, 2.0),
    (0.50, 1.0),
    (float("inf"), 0.0)
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


def compute_tp_percent_from_account_gain(balance, entry_price, contracts, target_gain_pct):
    if balance <= 0 or entry_price <= 0 or contracts <= 0:
        return None
    goal = balance * (target_gain_pct / 100.0)
    denom = entry_price * 100.0 * contracts
    if denom <= 0:
        return None
    return (goal / denom) * 100.0


# ----------------------------
# CORE MATH
# ----------------------------

def calc(balance, entry_price, fee_per_contract, trade_number, target_gain_pct):
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

    tp_pct = compute_tp_percent_from_account_gain(balance, entry_price, contracts, target_gain_pct)
    if tp_pct is None:
        tp_pct = 0.0

    tp_price = entry_price * (1.0 + tp_pct / 100.0)

    pos_cost = contracts * cost_per_contract
    gross_profit = (tp_price - entry_price) * 100.0 * contracts
    gross_loss = (entry_price - sl_price) * 100.0 * contracts

    total_fees = contracts * fee_per_contract * 2

    net_profit = gross_profit - total_fees
    net_loss = gross_loss + total_fees

    acct_gain_net = (net_profit / balance * 100.0) if balance > 0 else 0.0
    acct_loss_net = (net_loss / balance * 100.0) if balance > 0 else 0.0

    return {
        "contracts": contracts,
        "inv_pct": inv_pct,
        "rsk_pct": rsk_pct,
        "sl_pct": sl_pct,
        "tp_pct": tp_pct,
        "tp_price": tp_price,
        "sl_price": sl_price,
        "pos_cost": pos_cost,
        "gross_profit": gross_profit,
        "gross_loss": gross_loss,
        "total_fees": total_fees,
        "net_profit": net_profit,
        "net_loss": net_loss,
        "acct_gain_net": acct_gain_net,
        "acct_loss_net": acct_loss_net,
        "max_by_invest": max_by_invest,
        "max_by_risk": max_by_risk
    }


# ----------------------------
# UI
# ----------------------------

st.set_page_config(page_title="SPY Options Sizing — Path D", layout="wide")

st.title("SPY Options Risk & Position Sizing (Path D — Conservative)")

c1, c2 = st.columns(2)

with c1:
    balance = st.number_input("Account balance ($)", value=500.0, min_value=0.0, step=10.0)
    entry_price = st.number_input("Entry price (option premium)", value=0.25, min_value=0.01, format="%.2f")

with c2:
    trade_number = st.radio("Trade of the week", [1, 2], horizontal=True)
    fee_per_contract = st.number_input("Estimated fees per contract ($)", value=0.04, min_value=0.0, step=0.01)

target_gain_pct = st.slider("Target gain on TOTAL account (%)", 0.20, 1.00, 0.80, 0.05)

res = calc(balance, entry_price, fee_per_contract, trade_number, target_gain_pct)

st.subheader("Position Summary")
st.write(f"Contracts: **{res['contracts']}**")
st.write(f"Position Cost: **${res['pos_cost']:.2f}**")
st.write(f"Deploy %: **{res['inv_pct']:.1f}%**")
st.write(f"Risk %: **{res['rsk_pct']:.1f}%**")

st.subheader("Exit Levels")
st.write(f"TP Price: **${res['tp_price']:.2f}**")
st.write(f"SL Price: **${res['sl_price']:.2f}**")

st.subheader("Account Impact (AFTER FEES)")
st.write(f"Net account gain at TP: **{res['acct_gain_net']:.2f}%**")
st.write(f"Net account loss at SL: **{res['acct_loss_net']:.2f}%**")
st.write(f"Estimated total fees: **${res['total_fees']:.2f}**")
