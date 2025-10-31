import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import stripe
import requests
from datetime import datetime
import hashlib

# -------------------------------------------------
# SECURE CONFIG
# -------------------------------------------------
st.set_page_config(
    page_title="EcoGigHub – CO₂ Impact Calculator",
    page_icon="leaf",
    layout="wide",
    initial_sidebar_state="expanded"
)

# === SAFE SECRETS (NO ECOLOGI) ===
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

# Waldonia Only
WALDONIA_BASE = "https://api.waldonia.com/v1"
WALDONIA_KEY = safe_secret("waldonia.api_key", "sandbox_key_here")

# Constants
TREE_CO2_YEAR = 20.0
CAR_MILES_PER_KG = 4.6
FLIGHT_KG_PER_HOUR = 90.0

# -------------------------------------------------
# CSS (Professional)
# -------------------------------------------------
st.markdown("""
<style>
    .main {background:#fafdfa;padding:2rem;}
    [data-testid="stSidebar"] {background:#e8f5e9;border-right:2px solid #90EE90;}
    h1, h2, h3 {color:#166534 !important;font-weight:700;}
    .hero-title {font-size:2.1rem;font-weight:800;color:#166534;text-align:center;margin:1.8rem 0 1rem;}
    .section-header {font-size:1.4rem;color:#166534;font-weight:600;border-bottom:2px solid #86efac;padding-bottom:8px;margin:2rem 0 1rem;}
    .impact-card {background:linear-gradient(135deg,#ecfdf5,#d1fae5);padding:1.6rem;border-radius:16px;text-align:center;
                  box-shadow:0 8px 20px rgba(0,0,0,0.07);border:1px solid #86efac;transition:0.3s;}
    .impact-card:hover {transform:translateY(-6px);box-shadow:0 16px 32px rgba(0,0,0,0.12);}
    .big-number {font-size:3.2rem;font-weight:900;color:#166534;margin:0;}
    .big-label {font-size:1.15rem;color:#15803d;font-weight:600;margin-top:6px;}
    .eco-badge {background:#22c55e;color:white;padding:6px 14px;border-radius:20px;font-weight:700;font-size:0.85rem;display:inline-block;}
    .reg-badge {background:#94a3b8;color:white;padding:6px 14px;border-radius:20px;font-weight:700;font-size:0.85rem;display:inline-block;}
    .stButton>button {background:#16a34a !important;color:white !important;border-radius:30px !important;
                      font-weight:600 !important;padding:0.75rem 1.8rem !important;box-shadow:0 4px 12px rgba(22,163,74,0.3);}
    .stButton>button:hover {background:#15803d !important;transform:translateY(-2px);}
    .progress-bar {height:24px;border-radius:12px;background:#e5e7eb;overflow:hidden;}
    .progress-fill {height:100%;border-radius:12px;background:linear-gradient(90deg,#22c55e,#16a34a);transition:width 0.6s ease;}
    .footer {text-align:center;color:#6b7280;font-size:0.9rem;margin-top:3rem;padding-top:1.5rem;border-top:1px solid #e5e7eb;}
</style>
""", unsafe_allow_html=True)

# -------------------------------------------------
# DATA
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
    "Cleaning Spray (500ml)": {"regular":0.5, "eco":0.2, "price":5},
    "Cement Bag (50kg)":     {"regular":10.0, "low-carbon":5.0, "price":10},
    "Paint Can (1L)":        {"regular":2.0, "low-voc":1.0, "price":15},
}

gigs = {
    "House Cleaning (1h)":   {"standard":0.5, "green":0.1, "price":25},
    "Lawn Mowing (30min)":   {"gas":1.2, "electric":0.3, "price":15},
    "Repair Service (1h)":   {"standard":0.8, "eco":0.4, "price":40},
    "Construction Task (1h)": {"regular":2.0, "sustainable":1.0, "price":60},
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
if "user_email" not in st.session_state:
    st.session_state.user_email = ""

# -------------------------------------------------
# HELPERS
# -------------------------------------------------
def variant_badge(v):
    eco_keywords = ["eco","bio","vegan","plant","oat","fair","recycled","refurbished","electric","green","sustainable","low"]
    if any(k in v.lower() for k in eco_keywords):
        return f'<span class="eco-badge">Eco</span> {v.title()}'
    return f'<span class="reg-badge">Regular</span> {v.title()}'

def add_item(category, item, variant, qty):
    data = products if category == "Products" else gigs
    d = data[item]
    reg_key = next((k for k in ["regular","standard","gas"] if k in d), list(d.keys())[0])
    unit_co2_reg = d[reg_key]
    unit_co2_eco = d[variant]
    unit_price = d.get("price", 0)
    
    row = {
        "Category": category, "Item": item, "Variant": variant, "Quantity": qty,
        "Unit CO₂ Regular": unit_co2_reg, "Unit CO₂ Eco": unit_co2_eco, "Unit Price": unit_price,
        "CO₂ Regular": round(qty * unit_co2_reg, 3), "CO₂ Eco": round(qty * unit_co2_eco, 3),
        "Savings": round(qty * (unit_co2_reg - unit_co2_eco), 3), "Total $": round(qty * unit_price, 2)
    }
    return pd.concat([st.session_state.basket, pd.DataFrame([row])], ignore_index=True)

def recalculate(df):
    if df.empty: return df.copy()
    df = df.copy()
    df["CO₂ Regular"] = (df["Quantity"] * df["Unit CO₂ Regular"]).round(3)
    df["CO₂ Eco"] = (df["Quantity"] * df["Unit CO₂ Eco"]).round(3)
    df["Savings"] = (df["CO₂ Regular"] - df["CO₂ Eco"]).round(3)
    df["Total $"] = (df["Quantity"] * df["Unit Price"]).round(2)
    return df

def totals(df):
    if df.empty: return 0, 0, 0, 0
    return (
        round(df["CO₂ Regular"].sum(), 2),
        round(df["CO₂ Eco"].sum(), 2),
        round(df["Savings"].sum(), 2),
        round(df["Total $"].sum(), 2)
    )

def create_stripe_session(amount_cents, description):
    try:
        session = stripe.checkout.Session.create(
            payment_method_types=['card'],
            line_items=[{
                'price_data': {
                    'currency': 'usd',
                    'product_data': {'name': 'EcoGigHub Tree Donation', 'description': description},
                    'unit_amount': amount_cents
                },
                'quantity': 1
            }],
            mode='payment',
            success_url=SUCCESS_URL,
            cancel_url=CANCEL_URL,
            customer_email=st.session_state.user_email or None
        )
        return session.url
    except Exception as e:
        st.error(f"Payment error: {str(e)}")
        return None

def verify_stripe_session(session_id):
    try:
        session = stripe.checkout.Session.retrieve(session_id)
        return session.payment_status == 'paid'
    except:
        return False

@st.cache_data(ttl=3600)
def waldonia_plant_trees(trees, note, metadata):
    url = f"{WALDONIA_BASE}/orders"
    headers = {"Authorization": f"Bearer {WALDONIA_KEY}", "Content-Type": "application/json"}
    payload = {
        "tree_count": int(trees),
        "idempotency_key": hashlib.md5(f"{datetime.now()}_{trees}".encode()).hexdigest(),
        "note": note,
        "metadata": metadata
    }
    try:
        response = requests.post(url, headers=headers, json=payload, timeout=10)
        return response.json() if response.status_code == 201 else None
    except:
        return None

def generate_certificate(impact):
    cert = f"""
══════════════════════════════════════════════════════════════
                     ECOGIGHUB TREE PLANTING CERTIFICATE
══════════════════════════════════════════════════════════════
Date: {datetime.now().strftime('%B %d, %Y')}
Certificate ID: {impact.get('id', 'PENDING')}
Trees Planted: {impact.get('trees', 0):,}
CO₂ Offset (annual): {impact.get('trees', 0) * TREE_CO2_YEAR:,.0f} kg
Provider: Waldonia
──────────────────────────────────────────────────────────────
Thank you for saving the planet. Your trees are growing!
══════════════════════════════════════════════════════════════
    """
    return cert

def trigger_planting(trees, email, note):
    metadata = {"email": email, "note": note, "app": "EcoGigHub"}
    result = waldonia_plant_trees(trees, note, metadata)
    if result:
        impact = {
            'id': result.get('order_id'),
            'trees': trees,
            'co2': trees * TREE_CO2_YEAR,
            'date': datetime.now().isoformat(),
            'status': 'planted'
        }
        st.session_state.impacts.append(impact)
        st.success(f"Planted {trees} trees!")
        st.download_button(
            "Download Certificate",
            generate_certificate(impact),
            f"certificate_{impact['id']}.txt",
            "text/plain"
        )
        st.balloons()
        return True
    else:
        st.error("Failed to plant trees. Try again.")
        return False

# -------------------------------------------------
# MAIN APP
# -------------------------------------------------
st.markdown("""
<div class="hero-title">
    <span style="color:#166534;">EcoGigHub</span> <span style="color:#16a34a;">CO₂ Calculator</span>
</div>
<p style="text-align:center;font-size:1.2rem;color:#4b5563;margin-bottom:2rem;">
    Choose eco. Reduce emissions. Plant real trees.
</p>
""", unsafe_allow_html=True)

col_left, col_right = st.columns([1.1, 2.9])

# LEFT: INPUT
with col_left:
    st.markdown("<div class='section-header'>Add Item</div>", unsafe_allow_html=True)
    category = st.selectbox("Category", ["Products", "Gig Services"], key="cat")
    data = products if category == "Products" else gigs
    item = st.selectbox("Item", list(data.keys()), key="item")
    variants = [k for k in data[item].keys() if k != "price"]
    variant = st.selectbox("Variant", variants, format_func=lambda x: x.title(), key="var")
    qty = st.number_input("Quantity", min_value=1, value=1, step=1, key="qty")

    if st.button("Add to Basket", type="primary", use_container_width=True):
        st.session_state.basket = add_item(category, item, variant, qty)
        st.success("Added!")
        st.rerun()

    if not st.session_state.basket.empty:
        st.markdown("<div class='section-header'>Edit</div>", unsafe_allow_html=True)
        edited = st.data_editor(
            st.session_state.basket[["Item", "Variant", "Quantity"]].copy(),
            use_container_width=True,
            hide_index=True,
            column_config={"Quantity": st.column_config.NumberColumn("Qty", min_value=0, step=1)},
            key="edit"
        )
        df_tmp = st.session_state.basket.copy()
        df_tmp.loc[edited.index, "Quantity"] = edited["Quantity"]
        df_tmp = df_tmp[df_tmp["Quantity"] > 0].reset_index(drop=True)
        st.session_state.basket = recalculate(df_tmp)

        if st.button("Clear All", type="secondary", use_container_width=True):
            st.session_state.basket = pd.DataFrame(columns=REQUIRED_COLS)
            st.rerun()

# RIGHT: DASHBOARD
with col_right:
    basket = recalculate(st.session_state.basket)
    total_reg, total_eco, total_save, total_cost = totals(basket)

    if basket.empty:
        st.info("Add items to see your impact.")
    else:
        trees = total_save / TREE_CO2_YEAR
        miles = total_save / CAR_MILES_PER_KG

        st.markdown(f"""
        <div style="background:linear-gradient(135deg,#ecfdf5,#d1fae5);padding:1.8rem;border-radius:16px;text-align:center;margin-bottom:1.5rem;">
            <div style="font-size:2.8rem;font-weight:900;color:#166534;">{total_save:,.0f} kg</div>
            <div style="font-size:1.3rem;color:#15803d;">= {trees:,.0f} trees worth of CO₂ saved</div>
        </div>
        """, unsafe_allow_html=True)

        m1, m2, m3 = st.columns(3)
        m1.metric("Regular", f"{total_reg:,.0f} kg")
        m2.metric("Eco", f"{total_eco:,.0f} kg")
        m3.metric("Saved", f"{total_save:,.0f} kg", delta=f"+{total_save:,.0f} kg")

        c1, c2, c3 = st.columns(3)
        with c1: st.markdown(f'<div class="impact-card"><div class="big-number">{total_save:,.0f}</div><div class="big-label">kg Saved</div></div>', unsafe_allow_html=True)
        with c2: st.markdown(f'<div class="impact-card"><div class="big-number">{trees:,.0f}</div><div class="big-label">Trees</div></div>', unsafe_allow_html=True)
        with c3: st.markdown(f'<div class="impact-card"><div class="big-number">{miles:,.0f}</div><div class="big-label">Miles</div></div>', unsafe_allow_html=True)

        # Table
        st.markdown("<div class='section-header'>Your Choices</div>", unsafe_allow_html=True)
        display = basket[["Item", "Variant", "Quantity", "Savings", "Total $"]].copy()
        display["Variant"] = display["Variant"].apply(variant_badge)
        display["Savings"] = display["Savings"].apply(lambda x: f"{x:.1f}")
        display["Total $"] = display["Total $"].apply(lambda x: f"${x:.2f}")
        st.dataframe(display.rename(columns={"Savings": "Saved (kg)", "Total $": "Cost"}), use_container_width=True, hide_index=True)

        # PLANT TREES
        st.markdown("<div class='section-header'>Plant Real Trees</div>", unsafe_allow_html=True)
        email = st.text_input("Email (for certificate)", value=st.session_state.user_email, key="email")
        st.session_state.user_email = email

        trees_to_plant = st.slider("Trees to Plant", 1, 50, max(1, int(total_save / TREE_CO2_YEAR)))
        cost = trees_to_plant * 1.0  # $1 per tree
        note = st.text_input("Note", "EcoGigHub User")

        st.metric("CO₂ Offset (annual)", f"{trees_to_plant * TREE_CO2_YEAR:,.0f} kg")
        st.metric("Cost", f"${cost:.2f}")

        if st.button(f"PLANT {trees_to_plant} TREES NOW", type="primary", use_container_width=True):
            url = create_stripe_session(int(cost * 100), f"{trees_to_plant} Trees via Waldonia")
            if url:
                st.markdown(f"[Pay & Plant]({url})")

        # Payment Success
        session_id = st.query_params.get("session_id")
        if session_id and verify_stripe_session(session_id):
            with st.spinner("Planting your trees..."):
                if trigger_planting(trees_to_plant, email, note):
                    st.rerun()
            st.query_params.clear()

        if st.session_state.impacts:
            st.markdown("<div class='section-header'>Your Trees</div>", unsafe_allow_html=True)
            for imp in st.session_state.impacts[-3:]:
                st.info(f"Planted {imp['trees']} trees | ID: `{imp['id']}`")


# -------------------------------------------------
# FOOTER
# -------------------------------------------------
st.markdown("""
<div class="footer">
    <strong>EcoGigHub</strong> • Trees by Waldonia • Data: IPCC<br>
    <em>No Ecologi. No extra cost. Just real impact.</em>
</div>
""", unsafe_allow_html=True)