import math
import streamlit as st

# ----------------------------
# CONFIG
# ----------------------------

MIN_TICK = 0.01  # SPY options tick size (usually $0.01 on many strikes)

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
SL_TRADE1_BASE = 30.0  # Trade 1 SL% on premium
SL_TRADE2_BASE = 24.0  # Trade 2 SL% before tightening

# Trade 2: tighter SL for cheaper contracts
TRADE2_TIGHTENING_RULES = [
    (0.25, 4.0),
    (0.35, 3.0),
    (0.50, 2.0),
    (float("inf"), 0.0),
]
SL_TRADE2_MIN = 15.0
SL_TRADE2_MAX = 26.0

# Target account-gain guidance (net of fees)
MIN_GOAL_ACCT_GAIN = 0.20
MAX_GOAL_ACCT_GAIN = 1.00

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

def base_risk_percent(balance):
    return tier_lookup(balance, RISK_TIERS)

def trade2_dynamic_sl(entry_price):
    extra = 0.0
    for upper, tighten in TRADE2_TIGHTENING_RULES:
        if entry_price <= upper:
            extra = tighten
            break
    sl = SL_TRADE2_BASE - extra
    return max(SL_TRADE2_MIN, min(SL_TRADE2_MAX, sl))

def round_to_tick(price, tick=MIN_TICK):
    # Round to nearest cent
    return round(price / tick) * tick

def compute_tp_price_with_cap(entry_price, tp_cap_pct):
    """
    Convert a TP cap (on premium %) into a TP price.
    Ensures TP is at least +1 tick above entry.
    """
    tp_price_unrounded = entry_price * (1.0 + tp_cap_pct / 100.0)
    tp_price = round(tp_price_unrounded, 2)
    if tp_price <= entry_price:
        tp_price = round(entry_price + MIN_TICK, 2)
    return tp_price

def effective_tp_pct(entry_price, tp_price):
    if entry_price <= 0:
        return 0.0
    return ((tp_price / entry_price) - 1.0) * 100.0

def compute_tp_percent_for_target_account_gain_net(
    balance,
    entry_price,
    contracts,
    target_account_gain_pct_net,
    fee_round_trip_per_contract,
):
    """
    Compute TP% on premium needed so that NET account gain (after fees) hits target.
    """
    if contracts <= 0 or balance <= 0 or entry_price <= 0:
        return None

    profit_goal_net = balance * (target_account_gain_pct_net / 100.0)
    total_fees = fee_round_trip_per_contract * contracts
    profit_goal_gross = profit_goal_net + total_fees

    denom = entry_price * 100.0 * contracts
    if denom <= 0:
        return None

    return (profit_goal_gross / denom) * 100.0

# ----------------------------
# CORE CALC
# ----------------------------

def calc(
    balance,
    entry_price,
    trade_number,
    target_gain_pct_net,
    fee_round_trip_per_contract,
    tp_cap_pct,
):
    """
    Picks contract count + TP such that:
      - Uses deploy + risk budgets
      - Targets NET account gain (after fees)
      - TP premium move does NOT exceed tp_cap_pct (effective)
    If impossible, returns max achievable NET gain under the TP cap.
    """
    inv_pct = invest_percent(balance, trade_number)
    rsk_pct_base = base_risk_percent(balance)

    # Trade #2 uses half risk budget as well as half deploy
    rsk_pct = rsk_pct_base if trade_number == 1 else rsk_pct_base / 2.0

    inv_budget = balance * inv_pct / 100.0
    rsk_budget = balance * rsk_pct / 100.0

    # SL% used for actual P&L display
    sl_pct = SL_TRADE1_BASE if trade_number == 1 else trade2_dynamic_sl(entry_price)

    cost_per_contract = entry_price * 100.0
    sl_price = entry_price * (1.0 - sl_pct / 100.0)
    loss_per_contract_actual = (entry_price - sl_price) * 100.0

    # Risk sizing should not allow trade2 to get larger just because SL is tighter
    sl_pct_risk = SL_TRADE1_BASE  # use trade1 SL for risk sizing for both trades
    sl_price_risk = entry_price * (1.0 - sl_pct_risk / 100.0)
    loss_per_contract_risk = (entry_price - sl_price_risk) * 100.0

    max_by_invest = math.floor(inv_budget / cost_per_contract) if cost_per_contract > 0 else 0
    max_by_risk = math.floor(rsk_budget / loss_per_contract_risk) if loss_per_contract_risk > 0 else 0
    max_contracts = max(0, min(max_by_invest, max_by_risk))

    base = {
        "contracts": 0,
        "inv_pct": inv_pct,
        "rsk_pct": rsk_pct,
        "inv_budget": inv_budget,
        "rsk_budget": rsk_budget,
        "sl_pct": sl_pct,
        "sl_price": sl_price,
        "cost_per_contract": cost_per_contract,
        "max_by_invest": max_by_invest,
        "max_by_risk": max_by_risk,
        "tp_cap_pct": tp_cap_pct,
        "feasible": False,
        "note": "",
        "tp_price": entry_price,
        "tp_pct_effective": 0.0,
        "pos_cost": 0.0,
        "profit_tp_gross": 0.0,
        "total_fees": 0.0,
        "net_profit_tp": 0.0,
        "acct_gain_tp_net": 0.0,
        "acct_gain_tp_gross": 0.0,
        "loss_sl": 0.0,
        "acct_loss_sl_gross": 0.0,
        "max_net_gain_possible": 0.0,
    }

    if max_contracts <= 0:
        base["note"] = "No contracts fit your deploy/risk rules at this entry price."
        return base

    # We search all n=1..max_contracts and choose the closest NET account gain to target
    # while enforcing effective TP% <= tp_cap_pct.
    best = None
    for n in range(1, max_contracts + 1):
        # raw tp% needed to hit the NET account goal
        tp_pct_raw = compute_tp_percent_for_target_account_gain_net(
            balance=balance,
            entry_price=entry_price,
            contracts=n,
            target_account_gain_pct_net=target_gain_pct_net,
            fee_round_trip_per_contract=fee_round_trip_per_contract,
        )
        if tp_pct_raw is None:
            continue

        # convert to TP price (rounded)
        tp_price_unrounded = entry_price * (1.0 + tp_pct_raw / 100.0)
        tp_price = round(tp_price_unrounded, 2)
        if tp_price <= entry_price:
            tp_price = round(entry_price + MIN_TICK, 2)

        tp_pct_eff = effective_tp_pct(entry_price, tp_price)

        # Enforce TP cap on premium move
        if tp_pct_eff > tp_cap_pct + 1e-9:
            continue

        pos_cost = n * cost_per_contract
        profit_tp_gross = (tp_price - entry_price) * 100.0 * n
        total_fees = fee_round_trip_per_contract * n
        net_profit_tp = profit_tp_gross - total_fees

        loss_sl = loss_per_contract_actual * n

        acct_gain_tp_gross = (profit_tp_gross / balance * 100.0) if balance > 0 else 0.0
        acct_gain_tp_net = (net_profit_tp / balance * 100.0) if balance > 0 else 0.0
        acct_loss_sl_gross = (loss_sl / balance * 100.0) if balance > 0 else 0.0

        diff = abs(acct_gain_tp_net - target_gain_pct_net)

        candidate = dict(base)
        candidate.update({
            "contracts": n,
            "tp_price": tp_price,
            "tp_pct_effective": tp_pct_eff,
            "pos_cost": pos_cost,
            "profit_tp_gross": profit_tp_gross,
            "total_fees": total_fees,
            "net_profit_tp": net_profit_tp,
            "acct_gain_tp_gross": acct_gain_tp_gross,
            "acct_gain_tp_net": acct_gain_tp_net,
            "loss_sl": loss_sl,
            "acct_loss_sl_gross": acct_loss_sl_gross,
            "feasible": True,
            "_diff": diff,
        })

        # Tie-breakers:
        # - Prefer closest diff
        # - If very close diff, prefer smaller size on trade2, larger size on trade1
        if best is None:
            best = candidate
        else:
            if candidate["_diff"] < best["_diff"] - 1e-9:
                best = candidate
            else:
                # If nearly same diff, apply tie-breaker by trade type
                if abs(candidate["_diff"] - best["_diff"]) <= 0.02:
                    if trade_number == 1 and candidate["contracts"] > best["contracts"]:
                        best = candidate
                    if trade_number == 2 and candidate["contracts"] < best["contracts"]:
                        best = candidate

    if best is not None:
        best.pop("_diff", None)
        return best

    # If we get here, it means the target NET account gain is impossible under tp_cap_pct.
    # Compute maximum possible NET account gain using max_contracts and TP at the cap.
    n = max_contracts
    tp_price_cap = compute_tp_price_with_cap(entry_price, tp_cap_pct)
    tp_pct_eff_cap = effective_tp_pct(entry_price, tp_price_cap)

    pos_cost = n * cost_per_contract
    profit_tp_gross = (tp_price_cap - entry_price) * 100.0 * n
    total_fees = fee_round_trip_per_contract * n
    net_profit_tp = profit_tp_gross - total_fees

    loss_sl = loss_per_contract_actual * n
    acct_gain_tp_gross = (profit_tp_gross / balance * 100.0) if balance > 0 else 0.0
    acct_gain_tp_net = (net_profit_tp / balance * 100.0) if balance > 0 else 0.0
    acct_loss_sl_gross = (loss_sl / balance * 100.0) if balance > 0 else 0.0

    base.update({
        "contracts": n,
        "tp_price": tp_price_cap,
        "tp_pct_effective": tp_pct_eff_cap,
        "pos_cost": pos_cost,
        "profit_tp_gross": profit_tp_gross,
        "total_fees": total_fees,
        "net_profit_tp": net_profit_tp,
        "acct_gain_tp_gross": acct_gain_tp_gross,
        "acct_gain_tp_net": acct_gain_tp_net,
        "loss_sl": loss_sl,
        "acct_loss_sl_gross": acct_loss_sl_gross,
        "max_net_gain_possible": acct_gain_tp_net,
        "feasible": False,
        "note": (
            f"Not feasible to reach {target_gain_pct_net:.2f}% NET with a {tp_cap_pct:.1f}% contract TP cap "
            f"under your deploy/risk limits. Max achievable NET is ~{acct_gain_tp_net:.2f}%."
        ),
    })
    return base

# ----------------------------
# UI (simple, minimalist)
# ----------------------------

st.set_page_config(page_title="SPY Options Size Checker", layout="centered")

st.markdown(
    """
<style>
:root { --card:#0f172a10; --border:#0000001a; --text:#0b1220; --muted:#556070; }
html, body, [class*="css"] { background:#ffffff; color:var(--text); }
.block-container { max-width: 860px; padding-top: 1.4rem; padding-bottom: 2rem; }
.card { border:1px solid var(--border); background:#ffffff; border-radius:16px; padding:16px 18px; }
.small { color:var(--muted); font-size:0.95rem; line-height:1.35rem; }
hr { border:none; border-top:1px solid var(--border); margin:16px 0; }
</style>
""",
    unsafe_allow_html=True,
)

st.title("SPY Options Size Checker")

st.markdown(
    """
<div class="card small">
<b>Goal:</b> size trades to hit a <b>NET account gain</b> target (after fees) while keeping risk controlled.<br>
<b>Important:</b> If you cap the contract move (ex: 3–8%), the target may be impossible when deploy/risk limits prevent buying enough contracts.
The app will show the <b>max achievable</b> net gain when that happens.
</div>
""",
    unsafe_allow_html=True,
)

st.write("")

# Inputs
r1c1, r1c2 = st.columns(2)
with r1c1:
    balance = st.number_input("Account balance ($)", min_value=0.0, value=1500.0, step=50.0)
with r1c2:
    trade_number = st.radio("Trade of the week", [1, 2], horizontal=True)

st.caption("Trade 2 automatically uses half deploy and half risk budget (so it stays smaller).")

r2c1, r2c2 = st.columns(2)
with r2c1:
    entry_price = st.number_input("Entry price (option premium)", min_value=0.01, value=0.25, step=0.01, format="%.2f")
with r2c2:
    fee_round_trip = st.number_input(
        "Estimated fees per contract (round trip, $)",
        min_value=0.00,
        value=0.04,
        step=0.01,
        format="%.2f",
        help="Total estimated fees for one contract including BUY + SELL combined.",
    )

r3c1, r3c2 = st.columns(2)
with r3c1:
    tp_cap_pct = st.selectbox("Max contract TP % (premium move cap)", [3.0, 4.0, 8.0], index=2)
with r3c2:
    default_target = 0.80 if trade_number == 1 else 0.40
    target_gain_pct = st.slider(
        "Target NET account gain (%)",
        min_value=MIN_GOAL_ACCT_GAIN,
        max_value=MAX_GOAL_ACCT_GAIN,
        value=default_target,
        step=0.01,
    )

res = calc(
    balance=balance,
    entry_price=entry_price,
    trade_number=trade_number,
    target_gain_pct_net=target_gain_pct,
    fee_round_trip_per_contract=fee_round_trip,
    tp_cap_pct=tp_cap_pct,
)

st.write("")
st.markdown('<div class="card">', unsafe_allow_html=True)
m1, m2, m3 = st.columns(3)
m1.metric("Contracts", res["contracts"])
m2.metric("Position Cost", f'${res["pos_cost"]:.2f}')
m3.metric("TP Cap", f"{tp_cap_pct:.1f}%")
st.markdown("</div>", unsafe_allow_html=True)

if res["contracts"] == 0:
    st.warning("No contracts fit your deploy/risk limits at this entry price. Try a cheaper contract or lower entry.")
elif not res["feasible"]:
    st.warning(res["note"])

st.write("")
st.subheader("Exit Levels")
st.markdown('<div class="card">', unsafe_allow_html=True)
e1, e2 = st.columns(2)
e1.metric("TP Price", f'${res["tp_price"]:.2f}')
e2.metric("SL Price", f'${res["sl_price"]:.2f}')
st.caption(f"SL % used: {res['sl_pct']:.1f}% • Effective TP % on premium: {res['tp_pct_effective']:.2f}%")
st.markdown("</div>", unsafe_allow_html=True)

st.write("")
st.subheader("P&L (TP/SL)")
st.markdown('<div class="card">', unsafe_allow_html=True)
p1, p2 = st.columns(2)
p1.metric("Net profit at TP", f'${res["net_profit_tp"]:.2f}')
p2.metric("Loss at SL (gross)", f'${res["loss_sl"]:.2f}')
st.caption(
    f"Account impact → NET TP: {res['acct_gain_tp_net']:.2f}% • "
    f"GROSS TP: {res['acct_gain_tp_gross']:.2f}% • "
    f"GROSS SL: {res['acct_loss_sl_gross']:.2f}%"
)
st.caption(f"Estimated total fees (position): ${res['total_fees']:.2f}")
if not res["feasible"] and res["contracts"] > 0:
    st.caption(f"Max achievable NET under cap: ~{res['max_net_gain_possible']:.2f}%")
st.markdown("</div>", unsafe_allow_html=True)

st.write("")
st.subheader("Budgets & Limits")
st.markdown('<div class="card">', unsafe_allow_html=True)
st.write(f"Deploy budget: **${res['inv_budget']:.2f}** • Risk budget: **${res['rsk_budget']:.2f}**")
st.write(f"Cost/contract: **${res['cost_per_contract']:.2f}**")
st.write(f"Max contracts by deploy: **{res['max_by_invest']}** • Max contracts by risk: **{res['max_by_risk']}**")
st.markdown("</div>", unsafe_allow_html=True)

st.write("")
st.subheader("Copy-ready plan")
copy_text = (
    f"ENTRY ${entry_price:.2f} | CONTRACTS {res['contracts']} | "
    f"TP ${res['tp_price']:.2f} (cap {tp_cap_pct:.1f}%) | "
    f"SL ${res['sl_price']:.2f} | "
    f"NET ACCT GAIN @TP {res['acct_gain_tp_net']:.2f}% | "
    f"NET P@TP ${res['net_profit_tp']:.2f} | FEES ${res['total_fees']:.2f}"
)
st.code(copy_text, language="text")
st.caption("Not financial advice. Tool is for position sizing / risk math only.")
