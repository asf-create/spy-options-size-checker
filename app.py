import mathimport streamlit as st
# ----------------------------# CONFIG# ----------------------------
MIN_TICK = 0.01 # SPY options tick size
# As account grows, % deployed per main trade shrinks.INVEST_TIERS = [    (25000, 35.0),    (100000, 25.0),    (300000, 15.0),    (float("inf"), 8.0),]
# Risk tiers — cap account risk per trade around ~1–2%RISK_TIERS = [    (25000, 2.0),    (100000, 1.8),    (300000, 1.5),    (float("inf"), 1.2),]
# Base SL on option premiumSL_TRADE1_BASE = 30.0SL_TRADE2_BASE = 24.0
TRADE2_TIGHTENING_RULES = [    (0.25, 4.0),    (0.35, 3.0),    (0.50, 2.0),    (float("inf"), 0.0),]
SL_TRADE2_MIN = 15.0SL_TRADE2_MAX = 26.0
# Target account-gain guidanceMIN_GOAL_ACCT_GAIN = 0.20MAX_GOAL_ACCT_GAIN = 1.00

# ----------------------------# HELPERS# ----------------------------
def tier_lookup(value, tiers):    for max_val, pct in tiers:        if value <= max_val:            return pct    return tiers[-1][1]

def invest_percent(balance, trade_number):    base = tier_lookup(balance, INVEST_TIERS)    return base if trade_number == 1 else base / 2.0

def risk_percent(balance):    return tier_lookup(balance, RISK_TIERS)

def trade2_dynamic_sl(entry_price):    extra = 0.0    for upper, tighten in TRADE2_TIGHTENING_RULES:        if entry_price <= upper:            extra = tighten            break    sl = SL_TRADE2_BASE - extra    return max(SL_TRADE2_MIN, min(SL_TRADE2_MAX, sl))

def compute_tp_percent_for_target_account_gain(    balance,    entry_price,    contracts,    target_account_gain_pct,    fee_per_contract,):    if contracts <= 0 or balance <= 0 or entry_price <= 0:        return None
    profit_goal_net = balance * (target_account_gain_pct / 100.0)
    total_fees_est = fee_per_contract * contracts * 2.0
    profit_goal_gross = profit_goal_net + total_fees_est
    denom = entry_price * 100.0 * contracts    if denom <= 0:        return None
    return (profit_goal_gross / denom) * 100.0

# ----------------------------# CORE CALC# ----------------------------
def calc(balance, entry_price, trade_number, target_gain_pct, fee_per_contract):
    inv_pct = invest_percent(balance, trade_number)    rsk_pct = risk_percent(balance)
    inv_budget = balance * inv_pct / 100.0    rsk_budget = balance * rsk_pct / 100.0
    sl_pct = SL_TRADE1_BASE if trade_number == 1 else trade2_dynamic_sl(entry_price)
    cost_per_contract = entry_price * 100.0    sl_price = entry_price * (1.0 - sl_pct / 100.0)    loss_per_contract = (entry_price - sl_price) * 100.0
    max_by_invest = math.floor(inv_budget / cost_per_contract) if cost_per_contract > 0 else 0    max_by_risk = math.floor(rsk_budget / loss_per_contract) if loss_per_contract > 0 else 0
    contracts = max(0, min(max_by_invest, max_by_risk))
    tp_pct_raw = compute_tp_percent_for_target_account_gain(        balance,        entry_price,        contracts,        target_gain_pct,        fee_per_contract,    ) or 0.0
    tp_price_unrounded = entry_price * (1.0 + tp_pct_raw / 100.0)
    tp_price = round(tp_price_unrounded, 2)
    if tp_price <= entry_price:        tp_price = round(entry_price + MIN_TICK, 2)
    tp_pct_effective = ((tp_price / entry_price) - 1.0) * 100.0 if entry_price > 0 else 0.0
    pos_cost = contracts * cost_per_contract    profit_tp_gross = (tp_price - entry_price) * 100.0 * contracts    loss_sl = (entry_price - sl_price) * 100.0 * contracts
    total_fees_est = fee_per_contract * contracts * 2.0
    net_profit_tp = profit_tp_gross - total_fees_est
    acct_gain_tp_gross = (profit_tp_gross / balance * 100.0) if balance > 0 else 0.0    acct_loss_sl_gross = (loss_sl / balance * 100.0) if balance > 0 else 0.0    acct_gain_tp_net = (net_profit_tp / balance * 100.0) if balance > 0 else 0.0
    return {        "contracts": contracts,        "inv_pct": inv_pct,        "rsk_pct": rsk_pct,        "sl_pct": sl_pct,        "tp_pct_effective": tp_pct_effective,        "pos_cost": pos_cost,        "tp_price": tp_price,        "sl_price": sl_price,        "profit_tp_gross": profit_tp_gross,        "loss_sl": loss_sl,        "total_fees_est": total_fees_est,        "net_profit_tp": net_profit_tp,        "acct_gain_tp_gross": acct_gain_tp_gross,        "acct_loss_sl_gross": acct_loss_sl_gross,        "acct_gain_tp_net": acct_gain_tp_net,        "max_by_invest": max_by_invest,        "max_by_risk": max_by_risk,        "inv_budget": inv_budget,        "rsk_budget": rsk_budget,        "cost_per_contract": cost_per_contract,    }

# ----------------------------# UI# ----------------------------
st.set_page_config(page_title="SPY Options Size Checker", layout="wide")
theme_dark = st.toggle(" Dark mode", value=True)
if theme_dark:    bg = "#0b0f19"    card = "rgba(255,255,255,0.04)"    border = "rgba(255,255,255,0.10)"    text = "rgba(255,255,255,0.92)"    subtle = "rgba(255,255,255,0.70)"else:    bg = "#ffffff"    card = "rgba(0,0,0,0.03)"    border = "rgba(0,0,0,0.10)"    text = "rgba(0,0,0,0.88)"    subtle = "rgba(0,0,0,0.65)"
st.markdown(    f"""<style>html, body, [class*="css"] {{  background-color: {bg};  color: {text};}}.block-container {{  max-width: 980px;  padding-top: 1.6rem;  padding-bottom: 2.2rem;}}.card {{  border: 1px solid {border};  border-radius: 16px;  padding: 14px 16px;  background: {card};}}.small {{  color: {subtle};  font-size: 0.95rem;  line-height: 1.35rem;}}</style>""",    unsafe_allow_html=True,)
st.title("SPY Options Size Checker")
st.markdown(    '<div class="small">'    "This tool helps size SPY options trades based on account balance, capped risk, and small steady account-growth goals "    "(0.20%–1.00% NET per trade after estimated fees)."    "</div>",    unsafe_allow_html=True,)
st.write("")
# Inputs — same as before…
# (The rest of the code stays exactly as in the previous message)
