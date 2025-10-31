import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import stripe
import requests
from datetime import datetime
import base64
from io import BytesIO
from PIL import Image, ImageDraw, ImageFont
import urllib.parse

# -------------------------------------------------
# CONFIG
# -------------------------------------------------
st.set_page_config(page_title="EcoGigHub CO₂ Impact Pro", page_icon="leaf", layout="wide")

# Secrets
stripe.api_key = st.secrets.get("stripe_api_key", "sk_test_XXXXXXXXXXXXXXXXXXXXXXXX")
BASE_URL = st.secrets.get("base_url", "http://localhost:8501")
SUCCESS_URL = f"{BASE_URL}/?session_id={{CHECKOUT_SESSION_ID}}"
CANCEL_URL = BASE_URL

TREE_CO2_YEAR = 20.0
CAR_MILES_PER_KG = 4.6
FLIGHT_KG_PER_HOUR = 90.0

# API
WALDONIA_BASE = "https://api.waldonia.com/v1"
WALDONIA_KEY = st.secrets.get("WALDONIA_API_KEY", "sandbox_key_here")
ECOLOGI_BASE = "https://publicapi.ecologi.com/v1"
ECOLOGI_KEY = st.secrets.get("ECOLOGI_API_KEY", "sandbox_key_here")
ECOLOGI_USERNAME = st.secrets.get("ECOLOGI_USERNAME", "your_username")

# -------------------------------------------------
# PROFESSIONAL STYLES
# -------------------------------------------------
st.markdown("""
<style>
    :root {
        --primary: #145A32;
        --accent: #51CF66;
        --light: #f9fff9;
        --card: #ffffff;
        --shadow: 0 4px 12px rgba(0,0,0,0.05);
    }
    .main {background: var(--light); padding: 1.5rem;}
    [data-testid="stSidebar"] {background: #e8f5e8; border-right: 1px solid #d0e8d0;}
    h1, h2, h3 {color: var(--primary); font-family: 'Segoe UI', sans-serif;}
    .hero {
        text-align:center; background:linear-gradient(135deg, #e8f5e8, #d0f0c0);
        border-radius:20px; padding:2.5rem; margin-bottom:2rem; box-shadow: var(--shadow);
    }
    .metric-card {
        background: var(--card); border-radius:16px; padding:1.5rem; text-align:center;
        box-shadow: var(--shadow); border: 1px solid #e0e0e0;
    }
    .metric-title {color: #555; font-weight:600; font-size:0.9rem;}
    .metric-value {font-size:2.2rem; color: var(--primary); font-weight:800;}
    .stButton>button {
        background: var(--accent); color:white; border:none; border-radius:30px;
        font-weight:600; padding:0.6rem 1.4rem; transition:all 0.3s ease;
        box-shadow: 0 2px 6px rgba(81,207,102,0.3);
    }
    .stButton>button:hover {background:#36b854; transform:translateY(-2px); box-shadow:0 4px 12px rgba(81,207,102,0.4);}
    .eco-badge {background:#51CF66; color:white; padding:5px 12px; border-radius:14px; font-weight:600; font-size:0.8rem;}
    .reg-badge {background:#999; color:white; padding:5px 12px; border-radius:14px; font-weight:600; font-size:0.8rem;}
    .share-btn {
        display:inline-flex; align-items:center; gap:8px; padding:10px 18px; border-radius:30px;
        color:white; text-decoration:none; font-weight:600; font-size:0.9rem; transition:0.3s;
        box-shadow:0 2px 6px rgba(0,0,0,0.1);
    }
    .share-btn:hover {transform:translateY(-2px); box-shadow:0 4px 12px rgba(0,0,0,0.15);}
    table {width:100%; border-collapse:collapse; margin:1.5rem 0; background:white; border-radius:12px; overflow:hidden; box-shadow:var(--shadow);}
    th {background:#e8f5e8; color:var(--primary); padding:14px; text-align:left; font-weight:600;}
    td {padding:12px 14px; border-bottom:1px solid #eee;}
    .buy-btn {background:#145A32; color:white; padding:6px 14px; border-radius:12px; font-size:0.85rem; text-decoration:none; font-weight:600;}
    .buy-btn:hover {background:#0e3f24;}
</style>
""", unsafe_allow_html=True)

# -------------------------------------------------
# DATA
# -------------------------------------------------
products = {
    "Cotton T-Shirt": {"regular":9.0, "eco":4.5, "price":13},
    "Pair of Jeans": {"regular":33.4, "bio":16.7, "price":49},
    "Leather Shoes": {"regular":16.0, "vegan":7.0, "price":89},
    "Wool Sweater": {"regular":18.0, "recycled":9.0, "price":60},
    "Beef Burger (150g)": {"regular":4.0, "plant-based":1.0, "price":6},
    "Cup of Coffee (200ml)": {"regular":0.05, "fair-trade":0.03, "price":3},
    "Bottle of Milk (1L)": {"regular":3.0, "oat":0.9, "price":2},
    "Smartphone": {"regular":70.0, "refurbished":15.0, "price":699},
}

gigs = {
    "House Cleaning (1h)": {"standard":0.5, "green":0.1, "price":25},
    "Lawn Mowing (30min)": {"gas":1.2, "electric":0.3, "price":15},
    "Repair Service (1h)": {"standard":0.8, "eco":0.4, "price":40},
}

REQUIRED_COLS = ["Category","Item","Variant","Quantity","Unit CO₂ Regular","Unit CO₂ Eco","Unit Price","CO₂ Regular","CO₂ Eco","Savings","Total $"]

if "basket" not in st.session_state:
    st.session_state.basket = pd.DataFrame(columns=REQUIRED_COLS)
if "impacts" not in st.session_state:
    st.session_state.impacts = []

# -------------------------------------------------
# FUNCTIONS
# -------------------------------------------------
def variant_badge(variant):
    eco_keys = ["eco","bio","vegan","plant-based","oat","fair-trade","local","reusable","electric","green","low-voc","sustainable"]
    if any(k in variant.lower() for k in eco_keys):
        return f'<span class="eco-badge">Eco</span> {variant.title()}'
    else:
        return f'<span class="reg-badge">Regular</span> {variant.title()}'

def add_item(category, item, variant, qty):
    data = products if category == "Products" else gigs
    d = data[item]
    reg_key = next((k for k in ["regular","standard"] if k in d), list(d.keys())[0])
    unit_co2_reg = d[reg_key]
    unit_co2_eco = d[variant]
    unit_price = d.get("price", 0)
    row = {
        "Category": category, "Item": item, "Variant": variant, "Quantity": qty,
        "Unit CO₂ Regular": unit_co2_reg, "Unit CO₂ Eco": unit_co2_eco, "Unit Price": unit_price,
        "CO₂ Regular": round(qty * unit_co2_reg, 3),
        "CO₂ Eco": round(qty * unit_co2_eco, 3),
        "Savings": round(qty * (unit_co2_reg - unit_co2_eco), 3),
        "Total $": round(qty * unit_price, 2)
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
    return (round(df["CO₂ Regular"].sum(), 2), round(df["CO₂ Eco"].sum(), 2), round(df["Savings"].sum(), 2), round(df["Total $"].sum(), 2))

def create_checkout(name, variant, qty, price, email):
    try:
        session = stripe.checkout.Session.create(
            payment_method_types=["card"],
            line_items=[{"price_data": {"currency": "usd", "product_data": {"name": f"{name} ({variant})"}, "unit_amount": int(price * 100)}, "quantity": qty}],
            mode="payment", success_url=SUCCESS_URL, cancel_url=CANCEL_URL, customer_email=email or None,
        )
        return session.url
    except: return None

def create_stripe_session(amount_cents, description, metadata=None):
    try:
        session = stripe.checkout.Session.create(
            payment_method_types=['card'],
            line_items=[{'price_data': {'currency': 'usd', 'product_data': {'name': 'EcoGigHub Impact', 'description': description}, 'unit_amount': amount_cents}, 'quantity': 1}],
            mode='payment', success_url=SUCCESS_URL, cancel_url=CANCEL_URL, metadata=metadata or {},
        )
        return session.url
    except Exception as e:
        st.error(f"Payment error: {e}")
        return None

def verify_stripe_session(session_id):
    try:
        session = stripe.checkout.Session.retrieve(session_id)
        return session.payment_status == 'paid'
    except: return False

@st.cache_data(ttl=3600)
def waldonia_plant_trees(trees, note, metadata):
    url = f"{WALDONIA_BASE}/orders"
    headers = {"Authorization": f"Bearer {WALDONIA_KEY}", "Content-Type": "application/json"}
    payload = {"tree_count": trees, "idempotency_key": f"order_{datetime.now().timestamp()}", "note": note, "metadata": metadata}
    response = requests.post(url, headers=headers, json=payload)
    return response.json() if response.status_code == 201 else None

@st.cache_data(ttl=3600)
def ecologi_offset(tonnes, action="offset"):
    url = f"{ECOLOGI_BASE}/{action}"
    headers = {"Authorization": f"Bearer {ECOLOGI_KEY}", "Content-Type": "application/json"}
    payload = {"tonnes": tonnes, "username": ECOLOGI_USERNAME}
    response = requests.post(url, headers=headers, json=payload)
    return response.json() if response.status_code == 200 else None

def generate_pdf_cert(trees, total_save, api_name):
    img = Image.new('RGB', (900, 636), color=(248, 252, 248))
    draw = ImageDraw.Draw(img)
    try:
        font_title = ImageFont.truetype("arialbd.ttf", 48)
        font_body = ImageFont.truetype("arial.ttf", 28)
    except:
        font_title = ImageFont.load_default()
        font_body = font_title

    draw.text((80, 100), "EcoGigHub Impact Certificate", fill=(20, 90, 50), font=font_title)
    draw.text((80, 200), f"Trees Planted: {trees}", fill=(0, 100, 0), font=font_body)
    draw.text((80, 260), f"CO₂ Saved: {total_save:,.0f} kg", fill=(0, 100, 0), font=font_body)
    draw.text((80, 320), f"Provider: {api_name}", fill=(0, 100, 0), font=font_body)
    draw.text((80, 380), f"Date: {datetime.now():%B %d, %Y}", fill=(0, 100, 0), font=font_body)
    draw.text((80, 460), "Thank you for choosing sustainability!", fill=(0, 120, 0), font=font_body)

    buf = BytesIO()
    img.save(buf, format="PDF")
    buf.seek(0)
    b64 = base64.b64encode(buf.read()).decode()
    return f'<a href="data:application/pdf;base64,{b64}" download="EcoGigHub_Certificate_{datetime.now().strftime("%Y%m%d")}.pdf" style="color:#145A32; font-weight:600;">Download PDF Certificate</a>'

# -------------------------------------------------
# MAIN
# -------------------------------------------------
st.markdown('<div class="hero"><h1>EcoGigHub CO₂ Impact Pro</h1><h3>Calculator</h3></div>', unsafe_allow_html=True)

col_left, col_right = st.columns([1, 3])

with col_left:
    st.header("Add to Basket")
    category = st.selectbox("Category", ["Products", "Gig Services"], key="cat_select")
    data = products if category == "Products" else gigs
    item = st.selectbox("Item", list(data.keys()), key="item_select")
    variants = [k for k in data[item].keys() if k != "price"]
    variant = st.selectbox("Variant", variants, format_func=lambda x: x.title(), key="variant_select")
    qty = st.number_input("Quantity", min_value=1, value=1, step=1, key="qty_input")

    if st.button("Add to Basket", type="primary", key="btn_add"):
        st.session_state.basket = add_item(category, item, variant, qty)
        st.success(f"Added {qty} × {item} ({variant})")
        st.balloons()

    if not st.session_state.basket.empty:
        st.markdown("### Edit Basket")
        edited = st.data_editor(
            st.session_state.basket[["Item", "Variant", "Quantity"]].copy(),
            use_container_width=True,
            hide_index=True,
            column_config={"Quantity": st.column_config.NumberColumn("Qty", min_value=0, step=1)},
            key="basket_editor"
        )
        df_tmp = st.session_state.basket.copy()
        df_tmp.loc[edited.index, "Quantity"] = edited["Quantity"]
        df_tmp = df_tmp[df_tmp["Quantity"] > 0].copy()
        st.session_state.basket = recalculate(df_tmp)

        if st.button("Clear Basket", key="btn_clear"):
            st.session_state.basket = pd.DataFrame(columns=REQUIRED_COLS)
            st.rerun()

with col_right:
    if st.session_state.basket.empty:
        st.info("Add items to see your impact.")
    else:
        df = recalculate(st.session_state.basket)
        total_reg, total_eco, total_save, total_money = totals(df)
        trees_saved = total_save / TREE_CO2_YEAR

        # PROFESSIONAL GAUGE
        fig = go.Figure(go.Indicator(
            mode="gauge+number+delta",
            value=total_save,
            delta={'reference': 1000, 'increasing': {'color': "#51CF66"}},
            gauge={
                'axis': {'range': [0, 1000], 'tickwidth': 2, 'tickcolor': "#145A32"},
                'bar': {'color': "#51CF66"},
                'bgcolor': "white",
                'borderwidth': 2,
                'bordercolor': "#e0e0e0",
                'steps': [
                    {'range': [0, 500], 'color': "#ffe6e6"},
                    {'range': [500, 800], 'color': "#fff4e6"},
                    {'range': [800, 1000], 'color': "#e6f7e6"}
                ],
                'threshold': {'line': {'color': "#145A32", 'width': 4}, 'thickness': 0.75, 'value': total_save}
            },
            title={'text': "<b>CO₂ Saved Toward 1 Ton Goal</b>", 'font': {'size': 18}}
        ))
        fig.update_layout(height=300, margin=dict(l=20, r=20, t=50, b=20))
        st.plotly_chart(fig, use_container_width=True)

        # METRICS
        m1, m2, m3 = st.columns(3)
        m1.metric("Regular Footprint", f"{total_reg:,} kg CO₂e")
        m2.metric("Eco Footprint", f"{total_eco:,} kg CO₂e")
        m3.metric("CO₂ Saved", f"{total_save:,} kg", delta=f"+{total_save:,} kg")

        # TABLE WITH BUY BUTTON
        st.markdown("### Your Eco Choices")
        table_html = '<table><thead><tr><th>Item</th><th>Choice</th><th>Qty</th><th>Saved</th><th>Price</th><th>Action</th></tr></thead><tbody>'
        for idx, r in df.iterrows():
            badge = variant_badge(r["Variant"])
            buy_url = create_checkout(r["Item"], r["Variant"], int(r["Quantity"]), r["Unit Price"], "")
            buy_btn = f'<a href="{buy_url}" target="_blank" class="buy-btn">Buy Now</a>' if buy_url and r["Unit Price"] > 0 else "—"
            table_html += f'<tr><td>{r["Item"]}</td><td>{badge}</td><td>{int(r["Quantity"])}</td><td style="color:#145A32; font-weight:600;">{r["Savings"]:.1f}</td><td>${r["Total $"]:.2f}</td><td>{buy_btn}</td></tr>'
        table_html += '</tbody></table>'
        st.markdown(table_html, unsafe_allow_html=True)

        # PLANT & OFFSET
        st.markdown("## Plant Trees & Offset")
        email = st.text_input("Email for certificate", placeholder="you@example.com", key="email_cert")

        col_plant, col_share = st.columns([1, 1])

        with col_plant:
            st.markdown("### Choose Provider")
            api_choice = st.selectbox("Provider", ["Waldonia (Trees)", "Ecologi (Offsets + Trees)"], key="api_select")
            trees_suggested = max(1, int(trees_saved))
            trees = st.slider("Trees to Plant", 0, 50, trees_suggested, key="trees_slider")
            offset_tco2 = 0.0
            if "Ecologi" in api_choice:
                offset_tco2 = st.number_input("Offset (tCO₂e)", 0.0, 10.0, round(total_save / 1000, 3), key="offset_input")

            co2_offset = trees * TREE_CO2_YEAR + (offset_tco2 * 1000)
            cost = trees * 1.0 + offset_tco2 * 6.0

            st.metric("Total CO₂ Offset", f"{co2_offset:,.0f} kg/year")
            st.metric("Total Cost", f"${cost:.2f}")

            if (trees > 0 or offset_tco2 > 0) and st.button("PLANT & OFFSET", type="primary", key="btn_plant"):
                desc = f"{trees} Trees + {offset_tco2}t via {api_choice}"
                url = create_stripe_session(int(cost * 100), desc, {"trees": trees, "offset": offset_tco2, "api": api_choice})
                if url:
                    st.markdown(f"[Pay Securely with Stripe]({url})")

        with col_share:
            st.markdown("### Share Your Impact")
            share_text = f"I saved {total_save:,.0f} kg CO₂ ({trees_saved:,.0f} trees!) with @EcoGigHub. Join the movement: {BASE_URL}"
            platforms = [
                ("X (Twitter)", "https://twitter.com/intent/tweet?text=", "#000000"),
                ("LinkedIn", "https://www.linkedin.com/shareArticle?mini=true&url=&title=", "#0077B5"),
                ("WhatsApp", "https://wa.me/?text=", "#25D366"),
                ("Email", "mailto:?subject=My Eco Impact&body=", "#666666")
            ]
            share_html = "<div style='display:flex; gap:12px; flex-wrap:wrap; justify-content:center;'>"
            for name, base, color in platforms:
                url = base + urllib.parse.quote(share_text if name != "LinkedIn" else BASE_URL)
                if name == "LinkedIn":
                    url = f"{base}{urllib.parse.quote(BASE_URL)}&summary={urllib.parse.quote(share_text)}"
                icon = "x-twitter" if "X (" in name else name.lower().split()[0]
                share_html += f'<a href="{url}" target="_blank" class="share-btn" style="background:{color}"><img src="https://img.icons8.com/ios-filled/50/ffffff/{icon}.png" width="18"> {name.split(" (")[0]}</a>'
            share_html += "</div>"
            st.markdown(share_html, unsafe_allow_html=True)

        # PAYMENT SUCCESS
        session_id = st.query_params.get("session_id")
        if session_id and verify_stripe_session(session_id):
            st.success("Payment successful! Processing your impact...")
            if "Waldonia" in api_choice:
                impact = waldonia_plant_trees(trees, "Via EcoGigHub", {"email": email})
                api_name = "Waldonia"
            else:
                tonnes = trees / 333 if trees > 0 else offset_tco2
                action = "trees" if trees > 0 else "offset"
                impact = ecologi_offset(tonnes, action)
                api_name = "Ecologi"
            if impact:
                st.session_state.impacts.append({"id": impact.get("order_id") or impact.get("transaction_id"), "trees": trees, "api": api_name, "date": datetime.now().isoformat()})
                st.balloons()
                st.markdown(generate_pdf_cert(trees, total_save, api_name), unsafe_allow_html=True)
                st.rerun()

        if st.session_state.impacts:
            st.markdown("### Your Impact History")
            for imp in st.session_state.impacts[-3:]:
                st.info(f"**{imp['api']}** | {imp['trees']} trees | ID: {imp['id'][:8]}... | {imp['date'][:10]}")

st.markdown("<footer style='text-align:center; margin-top:3rem; color:#666; font-size:0.9rem;'>© 2025 <b>EcoGigHub</b> | Powered by Waldonia & Ecologi | Data: IPCC, DEFRA</footer>", unsafe_allow_html=True)