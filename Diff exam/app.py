# app.py  –  EcoGigHub 4.0  (Never empty, no secrets needed)
import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from datetime import datetime

# ────────────────────── CONFIG ──────────────────────
st.set_page_config(page_title="EcoGigHub", page_icon="leaf", layout="wide")

# Fake secrets – the app works even if you delete .streamlit/secrets.toml
def fake_secret(key, default):
    return st.session_state.get(key, default)

# ────────────────────── DATA ──────────────────────
products = {
    "T-Shirt":      {"regular":9.0, "eco":4.5, "price":13},
    "Jeans":        {"regular":33.4,"bio":16.7,"price":49},
    "Coffee":       {"regular":0.05,"fair":0.03,"price":3},
}
gigs = {
    "Cleaning (1h)": {"standard":0.5,"green":0.1,"price":25},
}

# ────────────────────── SESSION ──────────────────────
COLS = ["Cat","Item","Var","Qty","Reg","Eco","Price","RegTot","EcoTot","Save","$"]
if "basket" not in st.session_state:
    st.session_state.basket = pd.DataFrame(columns=COLS)

# ────────────────────── HELPERS ──────────────────────
def badge(v):
    eco = ["eco","bio","fair","green","vegan","plant","recycled"]
    return f'<span style="background:#22c55e;color:#fff;padding:2px 6px;border-radius:8px;font-size:0.8rem;">Eco</span> {v.title()}' if any(k in v.lower() for k in eco) else f'<span style="background:#94a3b8;color:#fff;padding:2px 6px;border-radius:8px;font-size:0.8rem;">Reg</span> {v.title()}'

def add(cat, item, var, qty):
    d = products if cat=="Products" else gigs
    reg = d[item].get("regular", d[item].get("standard",0))
    eco = d[item].get(var, reg)
    price = d[item].get("price",0)
    row = [cat, item, var, qty, reg, eco, price,
           round(qty*reg,2), round(qty*eco,2), round(qty*(reg-eco),2), round(qty*price,2)]
    return pd.concat([st.session_state.basket, pd.DataFrame([row], columns=COLS)], ignore_index=True)

def recalc(df):
    if df.empty: return df
    df = df.copy()
    df["RegTot"] = (df["Qty"]*df["Reg"]).round(2)
    df["EcoTot"] = (df["Qty"]*df["Eco"]).round(2)
    df["Save"]   = (df["RegTot"]-df["EcoTot"]).round(2)
    df["$"]      = (df["Qty"]*df["Price"]).round(2)
    return df

def totals(df):
    return (df["RegTot"].sum(), df["EcoTot"].sum(), df["Save"].sum(), df["$"].sum())

# ────────────────────── CSS ──────────────────────
st.markdown("""
<style>
    .main {background:#fafdfa;}
    .hero {text-align:center;background:linear-gradient(135deg,#ecfdf5,#d1fae5);padding:2rem;border-radius:20px;margin-bottom:2rem;}
    .card {background:#fff;padding:1rem;border-radius:12px;box-shadow:0 4px 12px rgba(0,0,0,.06);text-align:center;}
    .big {font-size:2.5rem;font-weight:900;color:#166534;margin:0;}
    .lbl {font-size:1rem;color:#15803d;}
</style>
""", unsafe_allow_html=True)

# ────────────────────── LAYOUT ──────────────────────
st.markdown('<div class="hero"><h1>EcoGigHub</h1><p>Add items → see savings → plant trees</p></div>', unsafe_allow_html=True)

left, right = st.columns([1, 2])

# ───── LEFT: ADD ─────
with left:
    st.subheader("Add Item")
    cat = st.selectbox("Category", ["Products","Gig Services"])
    data = products if cat=="Products" else gigs
    item = st.selectbox("Item", list(data.keys()))
    opts = [k for k in data[item] if k!="price"]
    var = st.selectbox("Variant", opts, format_func=lambda x: x.title())
    qty = st.number_input("Qty", 1, step=1)

    if st.button("Add", type="primary"):
        st.session_state.basket = add(cat, item, var, qty)
        st.success("Added!")
        st.rerun()

    if not st.session_state.basket.empty:
        st.subheader("Edit")
        edited = st.data_editor(
            st.session_state.basket[["Item","Var","Qty"]].copy(),
            column_config={"Qty": st.column_config.NumberColumn("Qty", min_value=0, step=1)},
            hide_index=True
        )
        tmp = st.session_state.basket.copy()
        tmp.loc[edited.index, "Qty"] = edited["Qty"]
        tmp = tmp[tmp["Qty"]>0].reset_index(drop=True)
        st.session_state.basket = recalc(tmp)
        if st.button("Clear All"):
            st.session_state.basket = pd.DataFrame(columns=COLS)
            st.rerun()

# ───── RIGHT: DASHBOARD ─────
with right:
    df = recalc(st.session_state.basket)
    reg, eco, sav, money = totals(df)

    if df.empty:
        st.info("Add an item to see your impact.")
    else:
        trees = int(sav / 20)

        # GAUGE
        fig = go.Figure(go.Indicator(
            mode="gauge+number",
            value=sav,
            gauge={'axis': {'range': [0, 1000]},
                   'bar': {'color': "#22c55e"},
                   'steps': [{'range':[0,500],'color':"#fecaca"},
                             {'range':[500,800],'color':"#fde68a"},
                             {'range':[800,1000],'color':"#bbf7d0"}]},
            title={'text':"CO₂ Saved (kg)"}
        ))
        st.plotly_chart(fig, use_container_width=True)

        # METRICS
        c1, c2, c3 = st.columns(3)
        c1.metric("Regular", f"{reg:,.0f} kg")
        c2.metric("Eco", f"{eco:,.0f} kg")
        c3.metric("Saved", f"{sav:,.0f} kg", delta=f"+{sav:,.0f} kg")

        # CARDS
        k1, k2, k3 = st.columns(3)
        k1.markdown(f'<div class="card"><div class="big">{sav:,.0f}</div><div class="lbl">kg Saved</div></div>', unsafe_allow_html=True)
        k2.markdown(f'<div class="card"><div class="big">{trees:,}</div><div class="lbl">Trees</div></div>', unsafe_allow_html=True)
        k3.markdown(f'<div class="card"><div class="big">${money:.2f}</div><div class="lbl">Cost</div></div>', unsafe_allow_html=True)

        # TABLE
        disp = df[["Item","Var","Qty","Save","$"]].copy()
        disp["Var"] = disp["Var"].apply(badge)
        disp["Save"] = disp["Save"].apply(lambda x: f"{x:.1f}")
        disp["$"] = disp["$"].apply(lambda x: f"${x:.2f}")
        st.dataframe(disp.rename(columns={"Save":"Saved (kg)","$":"Cost"}), use_container_width=True, hide_index=True)

        # PLANT (fake – no Stripe)
        st.subheader("Plant Trees")
        trees = st.slider("Trees", 1, 50, trees)
        if st.button("PLANT (demo)"):
            st.success(f"Planted {trees} trees!")
            st.balloons()

st.markdown("<div style='text-align:center;margin-top:3rem;color:#6b7280;font-size:0.9rem;'>EcoGigHub – demo mode</div>", unsafe_allow_html=True)