import mathimport streamlit as st
# ----------------------------# CONFIG (EDIT AS YOU LIKE)# ----------------------------
# Path D – deploy tiers: as account grows, % deployed per main trade shrinks.# These are for Trade #1; Trade #2 automatically uses half of this.INVEST_TIERS = [    (25000, 35.0), # up to 25k -> can deploy up to 35% per main trade    (100000, 25.0), # 25k–100k -> 25%    (300000, 15.0), # 100k–300k -> 15%    (float("inf"), 8.0), # 300k+ -> 8%]
# Risk tiers — cap account risk per trade to around 1–2%RISK_TIERS = [    (25000, 2.0), # up to 25k -> risk up to 2.0% of account at SL    (100000, 1.8), # 25k–100k -> 1.8%    (300000, 1.5), # 100k–300k -> 1.5%    (float("inf"), 1.2), # 300k+ -> 1.2%]
# Base SL on option premiumSL_TRADE1_BASE = 25.0 # Trade #1: 25% SL on premiumSL_TRADE2_BASE = 20.0 # Starting point for Trade #2, tightened by entry price
# Trade #2 tightening based on entry price (for cheaper contracts, tighten more)TRADE2_TIGHTENING_RULES = [    (0.25, 3.0), # <= 0.25 -> tighten by 3%    (0.35, 2.0), # <= 0.35 -> tighten by 2%    (0.50, 1.0), # <= 0.50 -> tighten by 1%    (float("inf"), 0.0), # above -> no extra tightening]SL_TRADE2_MIN = 12.0 # Floor for SL% on trade 2SL_TRADE2_MAX = 22.0 # Ceiling for SL% on trade 2

# ----------------------------# HELPERS# ----------------------------
def tier_lookup(value, tiers):    """Return the percentage for the first tier where value <= max_val."""    for max_val, pct in tiers:        if value <= max_val:            return pct    return tiers[-1][1]

def invest_percent(balance, trade_number):    """Deploy % of account based on Path D tiers."""    base = tier_lookup(balance, INVEST_TIERS)    # Trade #2 uses half the deploy size of Trade #1    return base if trade_number == 1 else base / 2.0

def risk_percent(balance):    """Max account risk % based on account balance."""    return tier_lookup(balance, RISK_TIERS)

def trade2_dynamic_sl(entry_price):    """    For trade #2, tighten SL% based on option price.    Cheaper contracts -> tighter SL floor, within min/max.    """    extra = 0.0    for upper, tighten in TRADE2_TIGHTENING_RULES:        if entry_price <= upper:            extra = tighten            break    sl = SL_TRADE2_BASE - extra    return max(SL_TRADE2_MIN, min(SL_TRADE2_MAX, sl))

def compute_tp_percent_for_target_account_gain(    balance,    entry_price,    contracts,    target_account_gain_pct,    fee_per_contract):    """    Given a desired NET account % gain for the trade, compute needed TP% on the option premium.    We gross up by estimated round-trip fees so the NET gain is as close as possible    to the requested percentage.    """    if contracts <= 0 or balance <= 0 or entry_price <= 0:        return None
    # Net target in dollars (what we actually want after fees)    profit_goal_net = balance * (target_account_gain_pct / 100.0)
    # Estimated round-trip fees (buy + sell)    total_fees_est = fee_per_contract * contracts * 2.0
    # We need at least this much PROFIT BEFORE FEES to hit the net goal    profit_goal_gross = profit_goal_net + total_fees_est
    denom = entry_price * 100.0 * contracts    if denom <= 0:        return None
    return (profit_goal_gross / denom) * 100.0

def calc(    balance,    entry_price,    trade_number,    target_gain_pct,    fee_per_contract):    """    Core sizing + TP/SL math.    All account impact percentages are based on ACCOUNT balance, not contract size.    """    inv_pct = invest_percent(balance, trade_number)    rsk_pct = risk_percent(balance)
    inv_budget = balance * inv_pct / 100.0    rsk_budget = balance * rsk_pct / 100.0
    # SL% on premium    if trade_number == 1:        sl_pct = SL_TRADE1_BASE    else:        sl_pct = trade2_dynamic_sl(entry_price)
    cost_per_contract = entry_price * 100.0    sl_price = entry_price * (1.0 - sl_pct / 100.0)    loss_per_contract = (entry_price - sl_price) * 100.0
    # How many contracts fit both the deploy AND risk limits?    if cost_per_contract > 0:        max_by_invest = math.floor(inv_budget / cost_per_contract)    else:        max_by_invest = 0
    if loss_per_contract > 0:        max_by_risk = math.floor(rsk_budget / loss_per_contract)    else:        max_by_risk = 0
    contracts = max(0, min(max_by_invest, max_by_risk))
    # TP% on the premium derived from account target (NET of fees)    tp_pct_raw = compute_tp_percent_for_target_account_gain(        balance,        entry_price,        contracts,        target_gain_pct,        fee_per_contract,    )    if tp_pct_raw is None:        tp_pct_raw = 0.0
    # Ideal (unrounded) TP price    tp_price_unrounded = entry_price * (1.0 + tp_pct_raw / 100.0)
    # Round to the nearest cent.    tp_price = round(tp_price_unrounded, 2)
    # If rounding would make TP equal to entry (no profit),    # bump TP by one cent.    if tp_price <= entry_price:        tp_price = round(entry_price + 0.01, 2)
    # Effective TP% after rounding    tp_pct_effective = (tp_price / entry_price - 1.0) * 100.0
    # Position-level P&L (gross, before fees)    pos_cost = contracts * cost_per_contract    profit_tp_gross = (tp_price - entry_price) * 100.0 * contracts    loss_sl = (entry_price - sl_price) * 100.0 * contracts
    # Fees    total_fees_est = fee_per_contract * contracts * 2.0
    # Net profit after fees    net_profit_tp = profit_tp_gross - total_fees_est
    # Account-level impact (gross)    if balance > 0:        acct_gain_tp_gross = profit_tp_gross / balance * 100.0        acct_loss_sl_gross = loss_sl / balance * 100.0    else:        acct_gain_tp_gross = 0.0        acct_loss_sl_gross = 0.0
    # Account-level impact (net, after fees)    if balance > 0:        acct_gain_tp_net = net_profit_tp / balance * 100.0    else:        acct_gain_tp_net = 0.0
    return {        "contracts": contracts,        "inv_pct": inv_pct,        "rsk_pct": rsk_pct,        "inv_budget": inv_budget,        "rsk_budget": rsk_budget,        "sl_pct": sl_pct,        "tp_pct_effective": tp_pct_effective,        "cost_per_contract": cost_per_contract,        "pos_cost": pos_cost,        "tp_price": tp_price,        "sl_price": sl_price,        "profit_tp_gross": profit_tp_gross,        "loss_sl": loss_sl,        "max_by_invest": max_by_invest,        "max_by_risk": max_by_risk,        "acct_gain_tp_gross": acct_gain_tp_gross,        "acct_loss_sl_gross": acct_loss_sl_gross,        "total_fees_est": total_fees_est,        "net_profit_tp": net_profit_tp,        "acct_gain_tp_net": acct_gain_tp_net,    }

# ----------------------------# UI (Responsive + Mobile-friendly)# ----------------------------
st.set_page_config(page_title="SPY Options Size Checker", layout="wide")
theme_dark = st.toggle(" Dark mode", value=True)
if theme_dark:    bg = "#0b0f19"    card = "rgba(255,255,255,0.04)"    border = "rgba(255,255,255,0.10)"    text = "rgba(255,255,255,0.92)"    subtle = "rgba(255,255,255,0.70)"else:    bg = "#ffffff"    card = "rgba(0,0,0,0.03)"    border = "rgba(0,0,0,0.10)"    text = "rgba(0,0,0,0.88)"    subtle = "rgba(0,0,0,0.65)"
st.markdown(    f"""<style>html, body, [class*="css"] {{  background-color: {bg};  color: {text};}}.block-container {{  max-width: 980px;  padding-top: 1.6rem;  padding-bottom: 2.2rem;}}.card {{  border: 1px solid {border};  border-radius: 16px;  padding: 14px 16px;  background: {card};}}.small-text {{  color: {subtle};  font-size: 0.95rem;  line-height: 1.35rem;}}button[kind="primary"], button[kind="secondary"] {{  border-radius: 12px !important;}}[data-testid="stMetricValue"] {{  font-size: 1.35rem;}}@media (max-width: 700px) {{  .block-container {{    padding-left: 0.9rem;    padding-right: 0.9rem;  }}  [data-testid="stMetricValue"] {{    font-size: 1.15rem;  }}}}</style>""",    unsafe_allow_html=True,)
st.title("SPY Options Size Checker")
st.markdown(    '<div class="small-text">'    "Phone + desktop friendly. Auto-sizes contracts using Path D tiers, caps risk around 1–2% of the account, "    "tightens SL on trade #2, and targets a small, steady account gain (0.20%–1.00%) per trade after estimated fees."    "</div>",    unsafe_allow_html=True,)
st.write("")
# Inputsc1, c2 = st.columns(2)with c1:    balance = st.number_input("Account balance ($)", min_value=0.0, value=467.0, step=10.0)    entry_price = st.number_input(        "Entry price (option premium)",        min_value=0.01,        value=0.25,        step=0.01,        format="%.2f",    )with c2:    trade_number = st.radio("Trade of the week", [1, 2], horizontal=True)    st.caption("1 = main trade • 2 = secondary trade (half deploy, tighter SL)")    fee_per_contract = st.number_input(        "Estimated fees per contract ($, round trip)",        min_value=0.00,        value=0.04,        step=0.01,        format="%.2f",        help="Approximate total buy+sell fee per contract (e.g. Webull ORF).",    )
st.write("")
# Target account gain slider (always on, no Turbo / no manual TP mode)default_target_gain = 0.80 if trade_number == 1 else 0.40target_gain_pct = st.slider(    "Target gain on TOTAL account (%)",    min_value=0.20,    max_value=1.00,    value=default_target_gain,    step=0.01,    help="All sizing is based on account % gain, not contract %. Range is 0.20%–1.00% per trade.",)
# Core calculationsres = calc(    balance=balance,    entry_price=entry_price,    trade_number=trade_number,    target_gain_pct=target_gain_pct,    fee_per_contract=fee_per_contract,)
# Summary cardst.markdown('<div class="card">', unsafe_allow_html=True)s1, s2 = st.columns(2)with s1:    st.metric("Contracts", res["contracts"])    st.metric("Position Cost", f"${res['pos_cost']:.2f}")with s2:    st.metric("Deploy % (auto)", f"{res['inv_pct']:.1f}%")    st.metric("Risk % (auto)", f"{res['rsk_pct']:.1f}%")st.markdown("</div>", unsafe_allow_html=True)
if res["contracts"] == 0:    st.warning(        "Under your deploy/risk rules, this entry price is too expensive for any contracts "        "(contracts = 0). Consider a cheaper strike or smaller premium."    )
st.write("")
# Exit levelsst.subheader("Exit Levels")st.markdown('<div class="card">', unsafe_allow_html=True)e1, e2 = st.columns(2)e1.metric("TP Price", f"${res['tp_price']:.2f}")e2.metric("SL Price", f"${res['sl_price']:.2f}")st.caption(    f"SL % used: {res['sl_pct']:.1f}% • Effective TP % on premium: {res['tp_pct_effective']:.2f}%")st.markdown("</div>", unsafe_allow_html=True)
st.write("")
# P&L cardst.subheader("P&L at TP/SL")st.markdown('<div class="card">', unsafe_allow_html=True)p1, p2 = st.columns(2)p1.metric("Profit at TP (gross)", f"${res['profit_tp_gross']:.2f}")p2.metric("Loss at SL (gross)", f"${res['loss_sl']:.2f}")
st.caption(    f"Gross account impact -> TP: {res['acct_gain_tp_gross']:.2f}% • "    f"SL: {res['acct_loss_sl_gross']:.2f}% (based on ACCOUNT balance).")st.caption(    f"Estimated total fees: ${res['total_fees_est']:.2f} | "    f"Net profit at TP (after est. fees): ${res['net_profit_tp']:.2f} | "    f"Net account gain at TP (after est. fees): {res['acct_gain_tp_net']:.2f}%")st.markdown("</div>", unsafe_allow_html=True)
st.write("")
# Budgets cardst.subheader("Budgets & Limits")st.markdown('<div class="card">', unsafe_allow_html=True)st.write(f"Deploy budget: **${res['inv_budget']:.2f}** • Risk budget: **${res['rsk_budget']:.2f}**")st.write(f"Cost per contract: **${res['cost_per_contract']:.2f}**")st.write(    f"Max contracts by deploy: **{res['max_by_invest']}** • "    f"Max contracts by risk: **{res['max_by_risk']}**")st.write(    f"Requested account gain: **{target_gain_pct:.2f}%** "    f"(net, after est. fees, as close as cents allow).")st.markdown("</div>", unsafe_allow_html=True)
st.write("")
# Copy-ready block for quick referencest.subheader("Copy-ready plan")copy_text = (    f"ENTRY ${entry_price:.2f} | CONTRACTS {res['contracts']} | "    f"TP ${res['tp_price']:.2f} (eff. TP% on premium {res['tp_pct_effective']:.2f}%) | "    f"SL ${res['sl_price']:.2f} (SL% {res['sl_pct']:.1f}%) | "    f"POS COST ${res['pos_cost']:.2f} | "    f"GROSS P@TP ${res['profit_tp_gross']:.2f} | L@SL ${res['loss_sl']:.2f} | "    f"NET P@TP (after est. fees) ${res['net_profit_tp']:.2f} "    f"({res['acct_gain_tp_net']:.2f}% of account)")
st.code(copy_text, language="text")st.caption("Chromebook tip: tap-and-hold or drag-select to copy. Desktop: highlight + Ctrl/Cmd+C.")st.caption("Not financial advice. Tool is for sizing/risk math only.")
