import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import stripe
import requests
from datetime import datetime

# -------------------------------------------------
# CONFIG
# -------------------------------------------------
st.set_page_config(page_title="EcoGigHub – Save the Planet", page_icon="leaf", layout="wide")

# STRIPE
stripe.api_key = st.secrets.get("stripe_api_key") or "sk_test_XXXXXXXXXXXXXXXXXXXXXXXX"
BASE_URL = st.secrets.get("base_url") or f"http://localhost:8501"
SUCCESS_URL = f"{BASE_URL}/?session_id={{CHECKOUT_SESSION_ID}}"
CANCEL_URL = f"{BASE_URL}/"

# CONSTANTS
TREE_CO2_YEAR = 20.0
CAR_MILES_PER_KG = 4.6
FLIGHT_KG_PER_HOUR = 90.0

# === API CONFIGS ===
WALDONIA_BASE = "https://api.waldonia.com/v1" if not st.secrets.get("WALDONIA_SANDBOX") else "https://sandbox.waldonia.com/api/v1"
WALDONIA_KEY = st.secrets.get("WALDONIA_API_KEY", "sandbox_key_here")
ECOLOGI_BASE = "https://publicapi.ecologi.com/v1"
ECOLOGI_KEY = st.secrets.get("ECOLOGI_API_KEY", "sandbox_key_here")
ECOLOGI_USERNAME = st.secrets.get("ECOLOGI_USERNAME", "your_username")

# -------------------------------------------------
# CSS
# -------------------------------------------------
st.markdown("""
<style>
    .main {background:#f8fff8;padding:2rem;}
    [data-testid="stSidebar"] {background:#e8f5e8;}
    .impact-card{background:linear-gradient(135deg,#e8f5e8,#d0f0d0);padding:1.5rem;border-radius:20px;text-align:center;
        box-shadow:0 6px 16px rgba(0,0,0,0.08);transition:0.3s;border:2px solid #90EE90;}
    .impact-card:hover{transform:translateY(-5px);box-shadow:0 12px 24px rgba(0,0,0,0.1);}
    .big-number{font-size:3rem;font-weight:900;color:#228B22;margin:0;}
    .big-label{font-size:1.1rem;color:#006400;font-weight:bold;margin:8px 0 0;}
    .eco-badge{background:#51CF66;color:white;padding:6px 12px;border-radius:16px;font-weight:bold;display:inline-block;margin-right:8px;font-size:0.9em;}
    .reg-badge{background:#888;color:white;padding:6px 12px;border-radius:16px;font-weight:bold;display:inline-block;margin-right:8px;font-size:0.9em;}
    .stButton>button{background:#51CF66;color:white;border-radius:25px;font-weight:bold;padding:0.7rem 1.5rem;}
    h1{color:#006400;text-align:center;}
    .progress-bar{height:20px;border-radius:10px;background:#ddd;}
    .progress-fill{height:100%;border-radius:10px;background:linear-gradient(90deg,#51CF66,#228B22);}
    .hero-title{font-size:1.8rem;font-weight:900;color:#228B22;text-align:center;margin:1.5rem 0;}
    .stMetric{border:1px solid #90EE90;border-radius:12px;padding:10px;background:#f0fff0;}
    .stMetric>label{color:#006400 !important;font-weight:bold;font-size:1.1rem;}
    .stMetric>div>div>div{color:#228B22 !important;font-size:1.8rem;font-weight:bold;}
</style>
""", unsafe_allow_html=True)

# -------------------------------------------------
# DATABASE (add your full list)
# -------------------------------------------------
products = {
    "Cotton T-Shirt":        {"regular":9.0,  "eco":4.5,   "price":13},
    "Pair of Jeans":         {"regular":33.4, "bio":16.7,  "price":49},
    "Leather Shoes":         {"regular":16.0, "vegan":7.0, "price":89},
    "Wool Sweater":          {"regular":18.0, "recycled":9.0,"price":60},
    "Beef Burger (150g)":    {"regular":4.0,  "plant-based":1.0,"price":6},
    "Cup of Coffee (200ml)": {"regular":0.05,"fair-trade":0.03,"price":3},
    "Bottle of Milk (1L)":   {"regular":3.0,  "oat":0.9,       "price":2},
    "Smartphone":            {"regular":70.0,"refurbished":15.0,"price":699},
    "Ride Share (10km)":     {"gas":2.0,  "electric":0.2,"price":15},
    "Flight (1h, economy)":  {"regular":90.0,"offset":0.0,"price":99},
    # ... add cleaning, construction, repair, etc.
}
gigs = {
    "House Cleaning (1h)": {"standard":0.5, "green":0.1, "price":25},
    # ... add all gigs
}

# -------------------------------------------------
# SESSION STATE
# -------------------------------------------------
REQUIRED_COLS = ["Category","Item","Variant","Quantity","Unit CO₂ Regular","Unit CO₂ Eco","Unit Price",
                 "CO₂ Regular","CO₂ Eco","Savings","Total $"]

if "basket" not in st.session_state:
    st.session_state.basket = pd.DataFrame(columns=REQUIRED_COLS)
if "impacts" not in st.session_state:
    st.session_state.impacts = []

# -------------------------------------------------
# HELPERS
# -------------------------------------------------
def variant_badge(v):
    eco_keys = ["eco","recycled","vegan","plant-based","oat","fair-trade","local","reusable",
                "electric","green","low-data","vegetarian","offset","bio","low-voc","sustainable","remote"]
    if any(k in v.lower() for k in eco_keys):
        return f'<span class="eco-badge">Eco</span> {v.title()}'
    return f'<span class="reg-badge">Regular</span> {v.title()}'

def add_item(category, item, variant, qty):
    data = products if category == "Products" else gigs
    d = data[item]
    reg_key = next((k for k in ["regular","car","gas","standard","meat","streaming"] if k in d), list(d.keys())[0])
    unit_co2_reg = d[reg_key]; unit_co2_eco = d[variant]; unit_price = d.get("price",0)
    row = {
        "Category":category,"Item":item,"Variant":variant,"Quantity":qty,
        "Unit CO₂ Regular":unit_co2_reg,"Unit CO₂ Eco":unit_co2_eco,"Unit Price":unit_price,
        "CO₂ Regular":round(qty*unit_co2_reg,3),"CO₂ Eco":round(qty*unit_co2_eco,3),
        "Savings":round(qty*(unit_co2_reg-unit_co2_eco),3),"Total $":round(qty*unit_price,2)
    }
    return pd.concat([st.session_state.basket, pd.DataFrame([row])], ignore_index=True)

def recalculate(df):
    if df.empty: return df.copy()
    df = df.copy()
    df["CO₂ Regular"] = (df["Quantity"]*df["Unit CO₂ Regular"]).round(3)
    df["CO₂ Eco"]     = (df["Quantity"]*df["Unit CO₂ Eco"]).round(3)
    df["Savings"]     = (df["CO₂ Regular"]-df["CO₂ Eco"]).round(3)
    df["Total $"]     = (df["Quantity"]*df["Unit Price"]).round(2)
    return df

def totals(df):
    if df.empty: return 0,0,0,0
    return (round(df["CO₂ Regular"].sum(),2), round(df["CO₂ Eco"].sum(),2),
            round(df["Savings"].sum(),2), round(df["Total $"].sum(),2))

# -------------------------------------------------
# MAIN LAYOUT
# -------------------------------------------------
st.markdown("# EcoGigHub CO₂ Calculator")
col_left, col_right = st.columns([1, 3])

# ---------- LEFT: ADD / EDIT ----------
with col_left:
    st.subheader("Add Item")
    category = st.selectbox("Category", ["Products","Gig Services"], key="cat")
    data = products if category=="Products" else gigs
    item = st.selectbox("Item", list(data.keys()), key="item")
    variant_opts = [k for k in data[item].keys() if k!="price"]
    variant = st.selectbox("Variant", variant_opts, format_func=lambda x:x.title(), key="var")
    qty = st.number_input("Qty", min_value=1, value=1, step=1, key="qty")

    if st.button("Add to Basket", type="primary"):
        st.session_state.basket = add_item(category, item, variant, qty)
        st.success("Added!"); st.balloons()

    if not st.session_state.basket.empty:
        st.markdown("### Edit Qty")
        edited = st.data_editor(
            st.session_state.basket[["Item","Variant","Quantity"]].copy(),
            use_container_width=True, hide_index=True,
            column_config={"Quantity":st.column_config.NumberColumn("Qty",min_value=0,step=1)},
            key="edit_qty")
        df_tmp = st.session_state.basket.copy()
        df_tmp.loc[edited.index, "Quantity"] = edited["Quantity"]
        df_tmp = df_tmp[df_tmp["Quantity"]>0].copy()
        st.session_state.basket = recalculate(df_tmp)

        if st.button("Restart", type="secondary"):
            st.session_state.basket = pd.DataFrame(columns=REQUIRED_COLS)
            st.rerun()

# ---------- RIGHT: DASHBOARD ----------
with col_right:
    basket = st.session_state.basket
    if basket.empty:
        st.info("Add items to see your impact.")
    else:
        df = recalculate(basket)
        total_reg, total_eco, total_save, total_money = totals(df)
        trees = total_save / TREE_CO2_YEAR
        miles = total_save / CAR_MILES_PER_KG
        flights = total_save / FLIGHT_KG_PER_HOUR

        # ---- HERO TITLE ----
        st.markdown(f"""
        <div class="hero-title">
            By choosing the eco version you saved <strong>{total_save:,.0f} kg</strong> of CO₂ — 
            that’s the same as a car driving <strong>{miles:,.0f} miles</strong>!
        </div>
        """, unsafe_allow_html=True)

        # ---- METRICS + CARBON IMPACT CHART (SIDE-BY-SIDE) ----
        m1, m2, m3 = st.columns(3)
        with m1:
            st.metric("Regular Footprint", f"{total_reg:,} kg CO₂e")
        with m2:
            st.metric("Eco Footprint", f"{total_eco:,} kg CO₂e")
        with m3:
            st.metric("CO₂ Saved", f"{total_save:,} kg", delta=f"+{total_save:,} kg")

        # ---- BAR CHART (Your Carbon Impact) ----
        chart_df = pd.DataFrame({
            "Type": ["Regular", "Eco", "Saved"],
            "CO₂ (kg)": [total_reg, total_eco, total_save]
        })
        fig = px.bar(chart_df, x="Type", y="CO₂ (kg)",
                     color="Type",
                     color_discrete_map={"Regular":"#FF6B6B","Eco":"#51CF66","Saved":"#228B22"},
                     text="CO₂ (kg)", title="Your Carbon Impact")
        fig.update_traces(textposition="outside")
        fig.update_layout(showlegend=False, yaxis_title="kg CO₂e")
        st.plotly_chart(fig, use_container_width=True)

        # ---- IMPACT CARDS (Trees, Miles, Flights, kg Saved) ----
        c1,c2,c3,c4 = st.columns(4)
        with c1: st.markdown(f'<div class="impact-card"><div class="big-number">{total_save:,.0f}</div><div class="big-label">kg Saved</div></div>', unsafe_allow_html=True)
        with c2: st.markdown(f'<div class="impact-card"><div class="big-number">{trees:,.0f}</div><div class="big-label">Trees Growing</div></div>', unsafe_allow_html=True)
        with c3: st.markdown(f'<div class="impact-card"><div class="big-number">{miles:,.0f}</div><div class="big-label">Miles Not Driven</div></div>', unsafe_allow_html=True)
        with c4: st.markdown(f'<div class="impact-card"><div class="big-number">{flights:,.0f}</div><div class="big-label">Flights Avoided</div></div>', unsafe_allow_html=True)

        # ---- DONUT CHART ----
        fig_donut = go.Figure(data=[go.Pie(labels=["Eco Footprint","CO₂ Saved"], values=[total_eco,total_save],
                                          hole=0.5, marker_colors=["#51CF66","#228B22"],
                                          textinfo="label+percent", hoverinfo="label+value")])
        fig_donut.update_layout(showlegend=False, paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", margin=dict(t=0,b=0,l=0,r=0))
        st.plotly_chart(fig_donut, use_container_width=True, config={'displayModeBar':False})

        # ---- PROGRESS TO 1 TON ----
        progress = min(total_save/1000,1.0)
        st.markdown(f"""
        <div style="margin:30px 0;">
            <div style="font-weight:bold;margin-bottom:8px;">Progress to 1 Ton Saved</div>
            <div class="progress-bar"><div class="progress-fill" style="width:{progress*100}%"></div></div>
            <div style="text-align:right;font-size:0.9rem;margin-top:4px;">{progress*100:.0f}% ({total_save:,.0f} / 1,000 kg)</div>
        </div>
        """, unsafe_allow_html=True)

        # ---- TABLE OF CHOICES ----
        st.markdown("## Your Eco Choices")
        html = '<table style="width:100%;border-collapse:collapse;font-family:sans-serif;"><thead><tr style="background:#e8f5e8;text-align:left;">'
        for h in ["Item","Choice","Qty","Saved (kg)","Price"]: html+=f'<th style="padding:12px;border-bottom:2px solid #90EE90;">{h}</th>'
        html+='</tr></thead><tbody>'
        for _,r in df.iterrows():
            badge = variant_badge(r["Variant"])
            html+=f'<tr style="border-bottom:1px solid #ddd;"><td style="padding:12px;">{r["Item"]}</td><td style="padding:12px;">{badge}</td>'
            html+=f'<td style="padding:12px;text-align:center;">{int(r["Quantity"])}</td>'
            html+=f'<td style="padding:12px;text-align:right;font-weight:bold;color:#228B22;">{r["Savings"]:.1f}</td>'
            html+=f'<td style="padding:12px;text-align:right;">${r["Total $"]:.2f}</td></tr>'
        html+='</tbody></table>'
        st.markdown(html, unsafe_allow_html=True)

        # ---- BUY & OFFSET (your existing code) ----
        st.markdown("## Buy & Offset")
        email = st.text_input("Email", placeholder="you@example.com")
        col_a, col_b = st.columns(2)
        # ... keep your buy/plant logic here ...

# -------------------------------------------------
# PAYMENT SUCCESS
# -------------------------------------------------
session_id = st.query_params.get("session_id")
if session_id:
    try:
        session = stripe.checkout.Session.retrieve(session_id)
        if session.payment_status == "paid":
            st.success("Payment successful! You're saving the planet!")
            st.balloons()
    except: pass
    finally:
        st.query_params.clear()

# -------------------------------------------------
# FOOTER
# -------------------------------------------------
st.markdown("---")
st.markdown(
    "<p style='text-align:center;color:#666;'>"
    "Powered by <b>EcoGigHub</b> | Data: IPCC, DEFRA, Ecoinvent | "
    "Partners: Waldonia, Ecologi | <a href='#'>Learn More</a></p>",
    unsafe_allow_html=True
)