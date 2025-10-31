import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import stripe
import requests
from datetime import datetime
import hashlib

# -------------------------------------------------
# CONFIG – WIX & MOBILE READY
# -------------------------------------------------
st.set_page_config(
    page_title="EcoGigHub – Sustainable Business Solutions",
    page_icon="leaf",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# === SECURE SECRETS ===
def safe_secret(path, fallback=""):
    keys = path.split(".")
    try:
        value = st.secrets
        for k in keys:
            value = value[k]
        return value
    except:
        st.warning(f"Using fallback for {path}")
        return fallback

stripe.api_key = safe_secret("stripe.api_key", "sk_test_XXXXXXXXXXXXXXXXXXXXXXXX")
BASE_URL = safe_secret("app.base_url", "http://localhost:8501")
SUCCESS_URL = f"{BASE_URL}/?session_id={{CHECKOUT_SESSION_ID}}"
CANCEL_URL = BASE_URL

WALDONIA_BASE = "https://api.waldonia.com/v1"
WALDONIA_KEY = safe_secret("waldonia.api_key", "sandbox_key_here")

TREE_CO2_YEAR = 20.0
CAR_MILES_PER_KG = 4.6

# -------------------------------------------------
# PROFESSIONAL CSS
# -------------------------------------------------
st.markdown("""
<style>
    .main {background:#ffffff;padding:1.5rem 1rem;max-width:1400px;margin:auto;}
    [data-testid="stSidebar"] {display:none;}
    .css-1d391kg, .css-1y0t9cy {font-family:'Inter', 'Segoe UI', sans-serif !important;}

    h1 {color:#1e3a8a !important;font-weight:800;font-size:2.2rem !important;text-align:center;margin:1rem 0;}
    h2 {color:#166534 !important;font-weight:700;font-size:1.5rem !important;}
    .hero {text-align:center;padding:2.5rem 1rem;background:linear-gradient(135deg,#f0fdf4,#dcfce7);border-radius:20px;margin-bottom:2rem;}
    .hero h1 {color:#166534;margin:0;}
    .hero p {font-size:1.1rem;color:#1e40af;margin:1rem 0 0;}

    .stat-card {
        background:#f8fafc;padding:1.4rem;border-radius:16px;text-align:center;
        border:1px solid #e2e8f0;box-shadow:0 6px 16px rgba(0,0,0,0.05);
        transition:0.3s;
    }
    .stat-card:hover {transform:translateY(-4px);box-shadow:0 12px 24px rgba(0,0,0,0.08);}
    .stat-num {font-size:2.8rem;font-weight:900;color:#166534;margin:0;line-height:1;}
    .stat-label {font-size:1rem;color:#1e40af;font-weight:600;margin-top:4px;}

    .badge-eco {background:#22c55e;color:white;padding:6px 14px;border-radius:20px;font-weight:700;font-size:0.85rem;display:inline-block;}
    .badge-reg {background:#64748b;color:white;padding:6px 14px;border-radius:20px;font-weight:700;font-size:0.85rem;display:inline-block;}

    .stButton>button {
        background:#16a34a !important;color:white !important;border-radius:30px !important;
        font-weight:600 !important;padding:0.75rem 1.8rem !important;width:100%;
        box-shadow:0 4px 12px rgba(22,163,74,0.3);transition:0.3s;border:none !important;
    }
    .stButton>button:hover {background:#15803d !important;transform:translateY(-2px);}

    @media (max-width: 768px) {
        .hero {padding:1.5rem 1rem;}
        h1 {font-size:1.8rem !important;}
        .stat-num {font-size:2.2rem;}
        .stButton>button {padding:0.7rem 1.2rem;font-size:0.95rem;}
    }

    .eco-table {font-size:0.95rem;}
    .eco-table th {background:#f0fdf4 !important;color:#166534 !important;font-weight:600;}
    .eco-table td {padding:10px !important;}

    .footer {text-align:center;color:#64748b;font-size:0.9rem;margin-top:3rem;padding:1.5rem 0;border-top:1px solid #e2e8f0;}
</style>
""", unsafe_allow_html=True)

# -------------------------------------------------
# DATA – BUSINESS FOCUSED
# -------------------------------------------------
products = {
    "Corporate T-Shirt (Pack of 10)": {"regular":90.0, "eco":45.0, "price":130},
    "Eco Office Kit (100 units)":     {"regular":50.0, "eco":20.0, "price":299},
    "Reusable Coffee Cups (50)":      {"regular":25.0, "eco":10.0, "price":199},
    "Green Cleaning Service (1h)":    {"standard":0.5, "green":0.1, "price":35},
    "Eco Event Setup (per event)":    {"regular":120.0, "eco":60.0, "price":850},
    "Sustainable Printing (1000 flyers)": {"regular":80.0, "eco":30.0, "price":450},
}

# -------------------------------------------------
# SESSION STATE
# -------------------------------------------------
cols = ["Category","Item","Variant","Quantity","Unit CO₂ Reg","Unit CO₂ Eco","Price",
        "CO₂ Reg","CO₂ Eco","Savings","Total $"]

if "basket" not in st.session_state:
    st.session_state.basket = pd.DataFrame(columns=cols)
if "impacts" not in st.session_state:
    st.session_state.impacts = []

# -------------------------------------------------
# HELPERS
# -------------------------------------------------
def badge(v):
    eco = any(x in v.lower() for x in ["eco","green","sustainable","bio","recycled"])
    return f'<span class="badge-eco">Eco</span> {v.title()}' if eco else f'<span class="badge-reg">Standard</span> {v.title()}'

def add_item(item, variant, qty):
    d = products[item]
    reg_key = "regular" if "regular" in d else "standard"
    row = {
        "Category": "Business", "Item": item, "Variant": variant, "Quantity": qty,
        "Unit CO₂ Reg": d[reg_key], "Unit CO₂ Eco": d[variant], "Price": d["price"],
        "CO₂ Reg": round(qty * d[reg_key], 2), "CO₂ Eco": round(qty * d[variant], 2),
        "Savings": round(qty * (d[reg_key] - d[variant]), 2), "Total $": round(qty * d["price"], 2)
    }
    return pd.concat([st.session_state.basket, pd.DataFrame([row])], ignore_index=True)

def recalc(df):
    if df.empty: return df
    df = df.copy()
    df["CO₂ Reg"] = (df["Quantity"] * df["Unit CO₂ Reg"]).round(2)
    df["CO₂ Eco"] = (df["Quantity"] * df["Unit CO₂ Eco"]).round(2)
    df["Savings"] = (df["CO₂ Reg"] - df["CO₂ Eco"]).round(2)
    df["Total $"] = (df["Quantity"] * df["Price"]).round(2)
    return df

def totals(df):
    if df.empty: return 0,0,0,0
    return (df["CO₂ Reg"].sum(), df["CO₂ Eco"].sum(), df["Savings"].sum(), df["Total $"].sum())

# -------------------------------------------------
# STRIPE & WALDONIA
# -------------------------------------------------
def create_payment(amount, desc):
    try:
        session = stripe.checkout.Session.create(
            payment_method_types=['card'],
            line_items=[{'price_data': {'currency': 'usd', 'product_data': {'name': 'EcoGigHub Tree Donation'}, 'unit_amount': amount}, 'quantity': 1}],
            mode='payment', success_url=SUCCESS_URL, cancel_url=CANCEL_URL
        )
        return session.url
    except Exception as e:
        st.error(f"Payment error: {e}")
        return None

@st.cache_data(ttl=3600)
def plant_trees(trees, note):
    url = f"{WALDONIA_BASE}/orders"
    headers = {"Authorization": f"Bearer {WALDONIA_KEY}", "Content-Type": "application/json"}
    payload = {
        "tree_count": int(trees),
        "idempotency_key": hashlib.md5(str(datetime.now().timestamp()).encode()).hexdigest(),
        "note": note,
        "metadata": {"source": "ecogighub_wix"}
    }
    try:
        r = requests.post(url, headers=headers, json=payload, timeout=10)
        return r.json() if r.status_code == 201 else None
    except:
        return None

# -------------------------------------------------
# MAIN UI
# -------------------------------------------------
st.markdown("""
<div class="hero">
    <h1>EcoGigHub</h1>
    <p>Reduce emissions. Grow your business. Plant real trees.</p>
</div>
""", unsafe_allow_html=True)

# === INPUT + DASHBOARD ===
col1, col2 = st.columns([1, 1], gap="large")

with col1:
    st.markdown("#### Add Sustainable Service")
    item = st.selectbox("Business Item", list(products.keys()), key="item")
    variants = [k for k in products[item].keys() if k != "price"]
    variant = st.selectbox("Version", variants, format_func=lambda x: x.title(), key="var")
    qty = st.number_input("Quantity", 1, 1000, 1, key="qty")
    
    if st.button("Add to Plan", type="primary"):
        st.session_state.basket = add_item(item, variant, qty)
        st.success("Added!")
        st.rerun()

with col2:
    st.markdown("#### Your Impact")
    basket = recalc(st.session_state.basket)
    reg, eco, save, cost = totals(basket)
    trees = save / TREE_CO2_YEAR
    miles = save / CAR_MILES_PER_KG

    if basket.empty:
        st.info("Add your first item to see impact.")
    else:
        # STAT CARDS
        c1, c2, c3, c4 = st.columns(4)
        with c1: st.markdown(f'<div class="stat-card"><div class="stat-num">{save:,.0f}</div><div class="stat-label">kg Saved</div></div>', unsafe_allow_html=True)
        with c2: st.markdown(f'<div class="stat-card"><div class="stat-num">{trees:,.0f}</div><div class="stat-label">Trees</div></div>', unsafe_allow_html=True)
        with c3: st.markdown(f'<div class="stat-card"><div class="stat-num">{miles:,.0f}</div><div class="stat-label">Miles</div></div>', unsafe_allow_html=True)
        with c4: st.markdown(f'<div class="stat-card"><div class="stat-num">${cost:,.0f}</div><div class="stat-label">Cost</div></div>', unsafe_allow_html=True)

        # DONUT CHART
        fig_donut = go.Figure(go.Pie(
            labels=["Eco Footprint", "CO₂ Saved"],
            values=[eco, save],
            hole=0.5,
            marker_colors=["#86efac", "#16a34a"],
            textinfo="label+percent"
        ))
        fig_donut.update_layout(showlegend=False, margin=dict(t=0,b=0,l=0,r=0), height=280)
        st.plotly_chart(fig_donut, use_container_width=True, config={'displayModeBar': False})

        # TABLE
        st.markdown("#### Your Plan")
        disp = basket[["Item", "Variant", "Quantity", "Savings", "Total $"]].copy()
        disp["Variant"] = disp["Variant"].apply(badge)
        disp["Savings"] = disp["Savings"].apply(lambda x: f"{x:,.0f}")
        disp["Total $"] = disp["Total $"].apply(lambda x: f"${x:,.0f}")
        st.dataframe(disp.rename(columns={"Savings": "Saved (kg)", "Total $": "Price"}), use_container_width=True, hide_index=True)

        if st.button("Clear Plan", type="secondary"):
            st.session_state.basket = pd.DataFrame(columns=cols)
            st.rerun()

# === TREE PLANTING SECTION ===
if save > 0:
    st.markdown("## Plant Real Trees")
    trees_to_plant = st.slider("Trees to Plant", 1, 100, int(trees), help="Each tree absorbs ~20 kg CO₂/year")
    cost_trees = trees_to_plant * 1.0
    note = st.text_input("Company Name (on certificate)", "Your Business")

    col_a, col_b = st.columns(2)
    with col_a:
        st.metric("Annual CO₂ Offset", f"{trees_to_plant * TREE_CO2_YEAR:,.0f} kg")
    with col_b:
        st.metric("Donation", f"${cost_trees:.2f}")

    if st.button(f"PLANT {trees_to_plant} TREES", type="primary", use_container_width=True):
        url = create_payment(int(cost_trees * 100), f"{trees_to_plant} Trees for {note}")
        if url:
            st.markdown(f"[Pay & Plant Now]({url})")

    # SUCCESS HANDLER
    sid = st.query_params.get("session_id")
    if sid:
        try:
            session = stripe.checkout.Session.retrieve(sid)
            if session.payment_status == "paid":
                with st.spinner("Planting trees..."):
                    result = plant_trees(trees_to_plant, note)
                    if result:
                        impact = {"id": result.get("order_id"), "trees": trees_to_plant, "date": datetime.now().isoformat()}
                        st.session_state.impacts.append(impact)
                        st.success(f"Planted {trees_to_plant} trees!")
                        st.download_button(
                            "Download Certificate",
                            f"EcoGigHub Certificate\nID: {impact['id']}\nTrees: {trees_to_plant}\nDate: {impact['date'][:10]}\nThank you!",
                            f"certificate_{impact['id']}.txt",
                            "text/plain"
                        )
                        st.balloons()
                        st.rerun()
        except:
            pass
        st.query_params.clear()

# === BAR CHART ===
if not basket.empty:
    st.markdown("### Impact Summary")
    chart_df = pd.DataFrame({
        "Footprint": ["Regular", "Eco", "Saved"],
        "kg CO₂e": [reg, eco, save]
    })
    fig = px.bar(chart_df, x="Footprint", y="kg CO₂e", color="Footprint",
                 color_discrete_map={"Regular":"#ef4444", "Eco":"#86efac", "Saved":"#16a34a"},
                 text="kg CO₂e")
    fig.update_traces(texttemplate="%{text:,.0f}", textposition="outside")
    fig.update_layout(showlegend=False, yaxis_title="kg CO₂e", plot_bgcolor="rgba(0,0,0,0)", height=400)
    st.plotly_chart(fig, use_container_width=True)

# === IMPACT HISTORY ===
if st.session_state.impacts:
    st.markdown("### Your Tree Impact")
    for imp in st.session_state.impacts[-3:]:
        st.info(f"Planted **{imp['trees']} trees** | ID: `{imp['id']}` | {imp['date'][:10]}")

# -------------------------------------------------
# FOOTER
# -------------------------------------------------
st.markdown("""
<div class="footer">
    <strong>EcoGigHub</strong> – Verified by Waldonia • Data: IPCC & LCA<br>
    <em>Wix-Ready • Mobile • Business Impact</em>
</div>
""", unsafe_allow_html=True)