# app.py
import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import requests
import json
from datetime import datetime
import stripe
import base64
from urllib.parse import quote_plus

# -------------------------------------------------
# CONFIG
# -------------------------------------------------
st.set_page_config(
    page_title="EcoGigHub – Save the Planet",
    page_icon="leaf",
    layout="wide",
    initial_sidebar_state="expanded"
)

# STRIPE
stripe.api_key = st.secrets["stripe"]["api_key"]
BASE_URL = st.secrets["app"]["base_url"]
SUCCESS_URL = f"{BASE_URL}/?session_id={{CHECKOUT_SESSION_ID}}"
CANCEL_URL = f"{BASE_URL}/"

# WALDONIA API
WALDONIA_BASE = "https://api.waldonia.com/v1"
WALDONIA_KEY = st.secrets["waldonia"]["api_key"]
TEST_MODE = "sandbox" in WALDONIA_KEY.lower()

# CONSTANTS
TREE_CO2_YEAR = 20.0
CAR_MILES_PER_KG = 4.6
FLIGHT_KG_PER_HOUR = 90.0
GLOBAL_AVG_PERSON = 4900

# -------------------------------------------------
# CSS
# -------------------------------------------------
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700;900&display=swap');
    html, body, [class*="css"] {font-family: 'Inter', sans-serif;}
    .main {background:#f8fff8;padding:2rem 1rem;}
    [data-testid="stSidebar"] {background:#e8f5e8; border-right: 1px solid #c8e6c9;}
    
    .impact-card {
        background: white; padding:1.8rem; border-radius:20px; text-align:center;
        box-shadow:0 8px 20px rgba(0,0,0,0.06); transition:all 0.3s ease;
        border:2px solid #90EE90; position:relative; overflow:hidden;
    }
    .impact-card::before {
        content:''; position:absolute; top:0; left:0; right:0; height:4px;
        background:linear-gradient(90deg,#51CF66,#228B22); opacity:0; transition:0.3s;
    }
    .impact-card:hover::before {opacity:1;}
    .impact-card:hover {transform:translateY(-6px); box-shadow:0 16px 32px rgba(0,0,0,0.1);}
    
    .big-number {font-size:3.2rem; font-weight:900; color:#228B22; margin:0; line-height:1;}
    .big-label {font-size:1.1rem; color:#006400; font-weight:600; margin:8px 0 0;}
    
    .eco-badge {background:#51CF66;color:white;padding:6px 14px;border-radius:20px;font-weight:700;
                display:inline-block;margin-right:8px;font-size:0.85em;}
    .reg-badge {background:#999;color:white;padding:6px 14px;border-radius:20px;font-weight:700;
                display:inline-block;margin-right:8px;font-size:0.85em;}
    
    .stButton>button {
        background:#51CF66;color:white;border-radius:25px;font-weight:700;
        padding:0.7rem 1.8rem; border:none; transition:0.3s; width:100%;
    }
    .stButton>button:hover {background:#3ab358; transform:translateY(-2px);}
    .restart-btn button {background:#FF6B6B !important; color:white !important;}
    
    h1, h2, h3 {color:#006400;}
    .hero-title {
        font-size:2rem; font-weight:900; color:#228B22; text-align:center;
        margin:2rem 0; line-height:1.4; background:linear-gradient(135deg,#e8f5e8,#d0f0d0);
        padding:1.5rem; border-radius:20px; box-shadow:0 4px 12px rgba(0,0,0,0.05);
    }
    .progress-bar {height:24px; border-radius:12px; background:#e0e0e0; overflow:hidden;}
    .progress-fill {
        height:100%; border-radius:12px; background:linear-gradient(90deg,#51CF66,#228B22);
        width:0%; transition: width 1.2s ease;
    }
    .donut-chart, .bar-comparison {border-radius:20px; padding:1rem; background:#fff; box-shadow:0 4px 16px rgba(0,0,0,0.08);}
    
    .share-btn {
        background:#228B22; color:white; border-radius:50px; padding:0.6rem 1.2rem;
        font-weight:600; text-decoration:none; display:inline-block; margin:0.5rem;
        transition:0.3s;
    }
    .share-btn:hover {background:#1a6b1a; transform:scale(1.05);}
    
    .footer {text-align:center; color:#666; font-size:0.9rem; margin-top:3rem;}
</style>
""", unsafe_allow_html=True)

# -------------------------------------------------
# DATABASE
# -------------------------------------------------
products = {
    "Cotton T-Shirt":        {"regular":9.0,  "eco":4.5,   "price":13, "cat": "Clothing"},
    "Pair of Jeans":         {"regular":33.4, "bio":16.7,  "price":49, "cat": "Clothing"},
    "Leather Shoes":         {"regular":16.0, "vegan":7.0, "price":89, "cat": "Clothing"},
    "Wool Sweater":          {"regular":18.0, "recycled":9.0,"price":60, "cat": "Clothing"},
    "Beef Burger (150g)":    {"regular":4.0,  "plant-based":1.0,"price":6, "cat": "Food"},
    "Cup of Coffee (200ml)": {"regular":0.05,"fair-trade":0.03,"price":3, "cat": "Food"},
    "Bottle of Milk (1L)":   {"regular":3.0,  "oat":0.9,       "price":2, "cat": "Food"},
    "Smartphone":            {"regular":70.0,"refurbished":15.0,"price":699, "cat": "Tech"},
}

gigs = {
    "Ride Share (10km)":     {"gas":2.0,  "electric":0.2,"price":15, "cat": "Transport"},
    "Flight (1h, economy)":  {"regular":90.0,"offset":0.0,"price":99, "cat": "Transport"},
    "House Cleaning (1h)":   {"standard":0.5, "green":0.1, "price":25, "cat": "Services"},
    "Lawn Mowing (30min)":   {"gas":1.2, "electric":0.3, "price":18, "cat": "Services"},
}

# -------------------------------------------------
# SESSION STATE
# -------------------------------------------------
REQUIRED_COLS = ["Category","Item","Variant","Quantity","Unit CO₂ Regular","Unit CO₂ Eco","Unit Price","CO₂ Regular","CO₂ Eco","Savings","Total $"]

if "basket" not in st.session_state:
    st.session_state.basket = pd.DataFrame(columns=REQUIRED_COLS)
if "impacts" not in st.session_state:
    st.session_state.impacts = []

for col in REQUIRED_COLS:
    if col not in st.session_state.basket.columns:
        dtype = "object" if col in ["Category","Item","Variant"] else "float64"
        st.session_state.basket[col] = pd.Series(dtype=dtype)

# -------------------------------------------------
# HELPERS
# -------------------------------------------------
def add_item(category, item, variant, qty):
    data = products if category == "Products" else gigs
    d = data[item]
    reg_key = next((k for k in ["regular","gas","standard"] if k in d), list(d.keys())[0])
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
    df["CO₂ Eco"]     = (df["Quantity"] * df["Unit CO₂ Eco"]).round(3)
    df["Savings"]     = (df["CO₂ Regular"] - df["CO₂ Eco"]).round(3)
    df["Total $"]     = (df["Quantity"] * df["Unit Price"]).round(2)
    return df

def totals(df):
    if df.empty: return 0, 0, 0, 0
    return (
        round(df["CO₂ Regular"].sum(), 2),
        round(df["CO₂ Eco"].sum(), 2),
        round(df["Savings"].sum(), 2),
        round(df["Total $"].sum(), 2)
    )

def variant_badge(v):
    eco_keywords = ["eco","recycled","vegan","plant-based","oat","fair-trade","electric","offset","bio","green"]
    if any(k in v.lower() for k in eco_keywords):
        return f'<span class="eco-badge">Eco</span> {v.replace("-", " ").title()}'
    return f'<span class="reg-badge">Regular</span> {v.title()}'

@st.cache_data(ttl=3600)
def waldonia_plant_trees(trees, note, metadata):
    url = f"{WALDONIA_BASE}/orders"
    headers = {"Authorization": f"Bearer {WALDONIA_KEY}", "Content-Type": "application/json"}
    payload = {
        "tree_count": trees,
        "idempotency_key": f"order_{datetime.now().timestamp()}",
        "note": note,
        "metadata": metadata
    }
    try:
        response = requests.post(url, headers=headers, json=payload)
        if response.status_code == 201:
            return response.json()
        else:
            st.error(f"Waldonia Error: {response.text}")
            return None
    except Exception as e:
        st.error(f"Request failed: {e}")
        return None

def create_checkout(trees, email, note):
    try:
        session = stripe.checkout.Session.create(
            payment_method_types=["card"],
            line_items=[{
                "price_data": {
                    "currency": "usd",
                    "product_data": {"name": f"Plant {trees} trees via Waldonia"},
                    "unit_amount": 100,
                },
                "quantity": trees,
            }],
            mode="payment",
            success_url=SUCCESS_URL,
            cancel_url=CANCEL_URL,
            customer_email=email or None,
            metadata={"type": "trees", "note": note}
        )
        return session.url
    except Exception as e:
        st.error(f"Stripe Error: {e}")
        return None

def export_csv(df):
    csv = df.to_csv(index=False)
    b64 = base64.b64encode(csv.encode()).decode()
    href = f'<a href="data:file/csv;base64,{b64}" download="ecogighub_impact.csv" class="share-btn">Download CSV</a>'
    return href

# -------------------------------------------------
# SIDEBAR
# -------------------------------------------------
with st.sidebar:
    st.image("https://img.icons8.com/fluency/48/000000/leaf.png", width=48)
    st.markdown("## EcoGigHub")
    st.markdown("**Calculate. Choose. Change.**")
    st.markdown("---")

    category = st.selectbox("Category", ["Products", "Gig Services"], key="cat")
    data = products if category == "Products" else gigs
    item = st.selectbox("Item", list(data.keys()), key="item")
    variant_opts = [k for k in data[item].keys() if k not in ["price", "cat"]]
    variant = st.selectbox("Variant", variant_opts, format_func=lambda x: x.replace("-", " ").title(), key="var")
    qty = st.number_input("Quantity", min_value=1, value=1, step=1, key="qty")

    if st.button("Add to Basket", type="primary"):
        st.session_state.basket = add_item(category, item, variant, qty)
        st.success("Added!")
        st.balloons()

    if not st.session_state.basket.empty:
        if st.button("Clear Basket", type="secondary"):
            st.session_state.basket = pd.DataFrame(columns=REQUIRED_COLS)
            st.rerun()

# -------------------------------------------------
# MAIN PAGE
# -------------------------------------------------
st.markdown("<h1 style='text-align:center;'>EcoGigHub CO₂ Calculator</h1>", unsafe_allow_html=True)
st.markdown("<p style='text-align:center;font-size:1.2rem;color:#006400;'>Choose eco alternatives → reduce emissions → save the planet</p>", unsafe_allow_html=True)

col1, col2 = st.columns([1, 3])

with col1:
    if not st.session_state.basket.empty:
        st.markdown("### Edit Quantities")
        edited_df = st.data_editor(
            st.session_state.basket[["Item", "Variant", "Quantity"]].copy(),
            use_container_width=True,
            hide_index=True,
            column_config={
                "Item": st.column_config.TextColumn("Item", disabled=True),
                "Variant": st.column_config.TextColumn("Choice", disabled=True),
                "Quantity": st.column_config.NumberColumn("Qty", min_value=0, step=1),
            },
            key="edit_qty"
        )
        df_temp = st.session_state.basket.copy()
        df_temp.loc[edited_df.index, "Quantity"] = edited_df["Quantity"]
        df_temp = df_temp[df_temp["Quantity"] > 0].copy()
        st.session_state.basket = recalculate(df_temp)

with col2:
    basket = st.session_state.basket
    if basket.empty:
        st.info("Add items to see your impact.")
    else:
        df = recalculate(basket)
        total_reg, total_eco, total_save, total_money = totals(df)
        trees = total_save / TREE_CO2_YEAR
        miles = total_save / CAR_MILES_PER_KG
        flights = total_save / FLIGHT_KG_PER_HOUR
        global_percent = (total_save / GLOBAL_AVG_PERSON) * 100

        st.markdown(f"""
        <div class="hero-title">
            You saved <strong>{total_save:,.0f} kg</strong> of CO₂ — 
            that’s like driving <strong>{miles:,.0f} miles</strong> in a car!
            <br><small style="color:#006400;">Equivalent to <strong>{global_percent:.2f}%</strong> of one person's annual emissions.</small>
        </div>
        """, unsafe_allow_html=True)

        c1, c2, c3, c4 = st.columns(4)
        with c1:
            st.markdown(f"""
            <div class="impact-card">
                <div style="font-size:2.2rem;">CO₂</div>
                <div class="big-number">{total_save:,.0f}</div>
                <div class="big-label">kg Saved</div>
            </div>
            """, unsafe_allow_html=True)
        with c2:
            st.markdown(f"""
            <div class="impact-card">
                <div style="font-size:2.2rem;">Tree</div>
                <div class="big-number">{trees:,.0f}</div>
                <div class="big-label">Trees Growing</div>
            </div>
            """, unsafe_allow_html=True)
        with c3:
            st.markdown(f"""
            <div class="impact-card">
                <div style="font-size:2.2rem;">Car</div>
                <div class="big-number">{miles:,.0f}</div>
                <div class="big-label">Miles Not Driven</div>
            </div>
            """, unsafe_allow_html=True)
        with c4:
            st.markdown(f"""
            <div class="impact-card">
                <div style="font-size:2.2rem;">Plane</div>
                <div class="big-number">{flights:,.0f}</div>
                <div class="big-label">Flight Hours Avoided</div>
            </div>
            """, unsafe_allow_html=True)

        # Gráfica Comparativa
        st.markdown("## Regular vs Eco: Your Impact")
        reg_eco_df = df.groupby("Category").agg({"CO₂ Regular": "sum", "CO₂ Eco": "sum"}).reset_index()
        reg_eco_df = pd.melt(reg_eco_df, id_vars="Category", value_vars=["CO₂ Regular", "CO₂ Eco"],
                             var_name="Type", value_name="CO₂ (kg)")
        reg_eco_df["Type"] = reg_eco_df["Type"].str.replace("CO₂ ", "")

        fig_bar = px.bar(reg_eco_df, x="Category", y="CO₂ (kg)", color="Type",
                         barmode="group", color_discrete_map={"Regular": "#FF6B6B", "Eco": "#51CF66"},
                         text="CO₂ (kg)", title="Products vs Services: Eco vs Regular")
        fig_bar.update_traces(textposition='outside')
        fig_bar.update_layout(showlegend=True, yaxis_title="kg CO₂e")
        st.plotly_chart(fig_bar, use_container_width=True, config={'displayModeBar': False})

        # Donut
        st.markdown("## Footprint Breakdown")
        fig = go.Figure(data=[go.Pie(
            labels=["Eco Footprint", "CO₂ Saved"],
            values=[total_eco, total_save],
            hole=0.55,
            marker_colors=["#51CF66", "#228B22"],
            textinfo="label+percent",
            hoverinfo="label+value+percent"
        )])
        fig.update_layout(showlegend=False, paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", margin=dict(t=0, b=0, l=0, r=0), height=300)
        st.plotly_chart(fig, use_container_width=True, config={'displayModeBar': False})

        # Table
        st.markdown("## Your Eco Choices")
        html = '<table style="width:100%;border-collapse:collapse;font-family:sans-serif;font-size:0.95rem;">'
        html += '<thead><tr style="background:#e8f5e8;text-align:left;">'
        for col in ["Item", "Choice", "Qty", "Saved (kg)", "Price"]:
            html += f'<th style="padding:12px;border-bottom:2px solid #90EE90;font-weight:600;">{col}</th>'
        html += '</tr></thead><tbody>'
        for _, row in df.iterrows():
            badge = variant_badge(row['Variant'])
            html += f'<tr style="border-bottom:1px solid #eee;">'
            html += f'<td style="padding:12px;">{row["Item"]}</td>'
            html += f'<td style="padding:12px;">{badge}</td>'
            html += f'<td style="padding:12px;text-align:center;">{int(row["Quantity"])}</td>'
            html += f'<td style="padding:12px;text-align:right;font-weight:700;color:#228B22;">{row["Savings"]:.1f}</td>'
            html += f'<td style="padding:12px;text-align:right;">${row["Total $"]:.2f}</td>'
            html += '</tr>'
        html += f'<tr style="background:#f0fff0;font-weight:700;">'
        html += f'<td colspan="3" style="padding:12px;text-align:right;">Total</td>'
        html += f'<td style="padding:12px;text-align:right;color:#228B22;">{total_save:,.1f}</td>'
        html += f'<td style="padding:12px;text-align:right;">${total_money:.2f}</td>'
        html += '</tr></tbody></table>'
        st.markdown(html, unsafe_allow_html=True)

        # Plant Trees
        st.markdown("## Plant Real Trees with Waldonia")
        email = st.text_input("Your Email", placeholder="you@example.com", key="email_plant")
        note = st.text_input("Note", placeholder="Thanks for saving the planet!", key="note_plant")
        trees_to_plant = st.slider("Trees to Plant", 1, 50, max(1, int(trees)), key="trees_slider")

        col_a, col_b = st.columns(2)
        with col_a:
            if st.button(f"Plant {trees_to_plant} Trees – ${trees_to_plant:.2f}", type="primary", use_container_width=True):
                url = create_checkout(trees_to_plant, email, note)
                if url:
                    st.markdown(f"[Pay with Stripe]({url})", unsafe_allow_html=True)
                    st.balloons()

        with col_b:
            st.markdown("### Share")
            share_text = f"I saved {total_save:,.0f} kg CO₂ and planted {trees_to_plant} trees with @EcoGigHub!"
            st.markdown(f'''
            <a href="https://twitter.com/intent/tweet?text={quote_plus(share_text)}" target="_blank" class="share-btn">Twitter</a>
            <a href="https://www.linkedin.com/shareArticle?mini=true&url={BASE_URL}&title={quote_plus(share_text)}" target="_blank" class="share-btn">LinkedIn</a>
            ''', unsafe_allow_html=True)
            st.markdown(export_csv(df), unsafe_allow_html=True)

# -------------------------------------------------
# PAYMENT SUCCESS
# -------------------------------------------------
session_id = st.query_params.get("session_id")
if session_id:
    try:
        session = stripe.checkout.Session.retrieve(session_id)
        if session.payment_status == "paid" and session.metadata.get("type") == "trees":
            trees = int(session.amount_total / 100)
            email = session.customer_email
            note = session.metadata.get("note", "EcoGigHub")

            with st.spinner("Planting trees..."):
                impact = waldonia_plant_trees(trees, note, {"email": email})
                if impact:
                    st.success(f"Planted {trees} trees! ID: {impact.get('order_id')}")
                    st.balloons()
                    st.session_state.impacts.append({"id": impact.get("order_id"), "trees": trees, "date": datetime.now().isoformat()})
                    cert = f"EcoGigHub Certificate\nTrees: {trees}\nID: {impact.get('order_id')}\nThank you!"
                    st.download_button("Download Certificate", cert, "certificate.txt", "text/plain")
    except Exception as e:
        st.error("Payment OK, but tree planting failed.")
    finally:
        st.query_params.clear()

# -------------------------------------------------
# WEBHOOK DE STRIPE (PLANTAR ÁRBOLES AUTOMÁTICAMENTE)
# -------------------------------------------------
import json
import os
from flask import Flask, request, jsonify

webhook_secret = st.secrets.get("stripe", {}).get("webhook_secret", "")

if webhook_secret and not st._is_running_with_streamlit:
    app = Flask(__name__)

    @app.route('/webhook', methods=['POST'])
    def stripe_webhook():
        payload = request.data
        sig_header = request.headers.get('Stripe-Signature')
        event = None

        try:
            event = stripe.Webhook.construct_event(
                payload, sig_header, webhook_secret
            )
        except ValueError:
            return jsonify(success=False), 400
        except stripe.error.SignatureVerificationError:
            return jsonify(success=False), 400

        if event['type'] == 'checkout.session.completed':
            session = event['data']['object']
            if session.get('metadata', {}).get('type') == 'trees':
                trees = int(session['amount_total'] / 100)
                email = session.get('customer_details', {}).get('email', 'unknown')
                note = session.get('metadata', {}).get('note', 'EcoGigHub')

                impact = waldonia_plant_trees(trees, note, {"email": email})
                if impact:
                    return jsonify(success=True, order_id=impact.get('order_id')), 200

        return jsonify(success=True), 200

    if __name__ == '__main__':
        app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 8080)))




# -------------------------------------------------
# FOOTER
# -------------------------------------------------
st.markdown("---")
st.markdown("""
<div class="footer">
    <p>Powered by <strong>EcoGigHub</strong> | Payments: Stripe | Trees: Waldonia API | Data: IPCC, DEFRA, UN | 
    <a href="#">Learn More</a></p>
</div>
""", unsafe_allow_html=True)
