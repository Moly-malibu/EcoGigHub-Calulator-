import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import stripe
import requests
from datetime import datetime

# -------------------------------------------------
# CONFIG
# -------------------------------------------------
st.set_page_config(
    page_title="EcoGigHub – CO₂ Impact Dashboard",
    page_icon="🌿",
    layout="wide"
)

stripe.api_key = st.secrets.get("stripe_api_key", "sk_test_XXXXXXXXXXXXXXXXXXXXXXXX")
BASE_URL = st.secrets.get("base_url", "http://localhost:8501")
SUCCESS_URL = f"{BASE_URL}/?session_id={{CHECKOUT_SESSION_ID}}"
CANCEL_URL = BASE_URL

TREE_CO2_YEAR = 20.0
CAR_MILES_PER_KG = 4.6
FLIGHT_KG_PER_HOUR = 90.0

# -------------------------------------------------
# API CONFIGS
# -------------------------------------------------
WALDONIA_BASE = "https://api.waldonia.com/v1"
WALDONIA_KEY = st.secrets.get("WALDONIA_API_KEY", "sandbox_key_here")
ECOLOGI_BASE = "https://publicapi.ecologi.com/v1"
ECOLOGI_KEY = st.secrets.get("ECOLOGI_API_KEY", "sandbox_key_here")
ECOLOGI_USERNAME = st.secrets.get("ECOLOGI_USERNAME", "your_username")

# -------------------------------------------------
# STYLES
# -------------------------------------------------
st.markdown("""
<style>
    body, .main {background:#f9fff9;}
    [data-testid="stSidebar"] {background:#e9f7e9;}
    h1, h2, h3, h4 {color:#145A32;}
    .hero {
        text-align:center;
        background:linear-gradient(135deg, #dff8df, #baf2ba);
        border-radius:20px;
        padding:2rem 3rem;
        margin-bottom:2.5rem;
        box-shadow:0 4px 10px rgba(0,0,0,0.05);
    }
    .metric-card {
        text-align:center;
        border-radius:16px;
        background:#f1faf1;
        padding:1.5rem;
        margin:8px;
        box-shadow:0 2px 8px rgba(0,0,0,0.05);
    }
    .metric-title {color:#145A32; font-weight:600;}
    .metric-value {font-size:2rem; color:#1b7d31; font-weight:800;}
    .stButton>button {
        border-radius:25px;
        background:#51CF66;
        color:white;
        font-weight:bold;
        transition:all 0.25s ease;
    }
    .stButton>button:hover {background:#36b854; transform:translateY(-2px);}
    .progress-bar {
        height:18px; border-radius:10px; background:#d9f2d9; margin-top:6px;
    }
    .progress-fill {
        height:18px; border-radius:10px;
        background:linear-gradient(90deg,#36b854,#1b7d31);
    }
    footer {text-align:center; color:#666; margin-top:2em; font-size:0.9rem;}
    table {
        width: 100%;
        border-collapse: collapse;
        margin-top: 1rem;
    }
    th, td {
        padding: 12px;
        border-bottom: 1px solid #ccc;
    }
    th {
        background-color: #e9f7e9;
        color: #145A32;
        font-weight: 600;
        text-align: left;
    }
    .eco-badge {
        background:#51CF66;
        color:white;
        padding:4px 10px;
        border-radius:12px;
        font-weight:bold;
        font-size:0.8rem;
        margin-right:6px;
    }
    .reg-badge {
        background:#888;
        color:white;
        padding:4px 10px;
        border-radius:12px;
        font-weight:bold;
        font-size:0.8rem;
        margin-right:6px;
    }
</style>
""", unsafe_allow_html=True)

# -------------------------------------------------
# DATASETS
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
    "Cleaning Spray (500ml)": {"regular":0.5, "eco":0.2, "price":5},
    "Cement Bag (50kg)": {"regular":10.0, "low-carbon":5.0, "price":10},
    "Paint Can (1L)": {"regular":2.0, "low-voc":1.0, "price":15},
}

gigs = {
    "House Cleaning (1h)": {"standard":0.5, "green":0.1, "price":25},
    "Lawn Mowing (30min)": {"gas":1.2, "electric":0.3, "price":15},
    "Repair Service (1h)": {"standard":0.8, "eco":0.4, "price":40},
    "Construction Task (1h)": {"regular":2.0, "sustainable":1.0, "price":60},
}

REQUIRED_COLS = [
    "Category", "Item", "Variant", "Quantity",
    "Unit CO₂ Regular", "Unit CO₂ Eco", "Unit Price",
    "CO₂ Regular", "CO₂ Eco", "Savings", "Total $"
]

if "basket" not in st.session_state:
    st.session_state.basket = pd.DataFrame(columns=REQUIRED_COLS)
if "impacts" not in st.session_state:
    st.session_state.impacts = []

# -------------------------------------------------
# FUNCTIONS
# -------------------------------------------------
def variant_badge(variant):
    eco_keys = [
        "eco", "recycled", "vegan", "plant-based", "oat", "fair-trade", "local",
        "reusable", "electric", "green", "low-data", "vegetarian", "offset", "bio", 
        "low-voc", "sustainable", "remote"
    ]
    if any(k in variant.lower() for k in eco_keys):
        return f'<span class="eco-badge">Eco</span> {variant.title()}'
    else:
        return f'<span class="reg-badge">Regular</span> {variant.title()}'

def add_item(category, item, variant, qty):
    data = products if category == "Products" else gigs
    d = data[item]
    reg_key = next((k for k in ["regular","car","gas","standard","meat","streaming"] if k in d), list(d.keys())[0])
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
    if df.empty:
        return df.copy()
    df = df.copy()
    df["CO₂ Regular"] = (df["Quantity"] * df["Unit CO₂ Regular"]).round(3)
    df["CO₂ Eco"] = (df["Quantity"] * df["Unit CO₂ Eco"]).round(3)
    df["Savings"] = (df["CO₂ Regular"] - df["CO₂ Eco"]).round(3)
    df["Total $"] = (df["Quantity"] * df["Unit Price"]).round(2)
    return df

def totals(df):
    if df.empty:
        return 0, 0, 0, 0
    return (
        round(df["CO₂ Regular"].sum(), 2), 
        round(df["CO₂ Eco"].sum(), 2), 
        round(df["Savings"].sum(), 2), 
        round(df["Total $"].sum(), 2)
    )

def create_checkout(name, variant, qty, price, email):
    try:
        session = stripe.checkout.Session.create(
            payment_method_types=["card"],
            line_items=[{
                "price_data": {
                    "currency": "usd", 
                    "product_data": {"name": f"{name} ({variant})"},
                    "unit_amount": int(price * 100)
                },
                "quantity": qty,
            }],
            mode="payment", success_url=SUCCESS_URL, cancel_url=CANCEL_URL, customer_email=email or None,
        )
        return session.url
    except Exception:
        return None

def create_stripe_session(amount_cents, description, metadata=None):
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
            mode='payment', success_url=SUCCESS_URL, cancel_url=CANCEL_URL, metadata=metadata or {},
        )
        return session.url
    except Exception as e:
        st.error(f"Stripe Error: {str(e)}")
        return None

def verify_stripe_session(session_id):
    try:
        session = stripe.checkout.Session.retrieve(session_id)
        return session.payment_status == 'paid'
    except Exception:
        return False

@st.cache_data(ttl=3600)
def waldonia_plant_trees(trees, note, metadata):
    url = f"{WALDONIA_BASE}/orders"
    headers = {"Authorization": f"Bearer {WALDONIA_KEY}", "Content-Type": "application/json"}
    payload = {"tree_count": trees, "idempotency_key": f"order_{datetime.now().timestamp()}", "note": note, "metadata": metadata}
    response = requests.post(url, headers=headers, json=payload)
    return response.json() if response.status_code == 201 else None

@st.cache_data(ttl=3600)
def ecologi_offset(co2_tonnes, action="offset"):
    url = f"{ECOLOGI_BASE}/{action}"
    headers = {"Authorization": f"Bearer {ECOLOGI_KEY}", "Content-Type": "application/json"}
    payload = {"tonnes": co2_tonnes, "username": ECOLOGI_USERNAME}
    response = requests.post(url, headers=headers, json=payload)
    return response.json() if response.status_code == 200 else None

def generate_cert(impact_data):
    cert_text = f"""
EcoGigHub Offset Certificate
Date: {datetime.now().strftime('%Y-%m-%d')}
Trees Planted: {impact_data.get('trees', 0)}
CO₂ Offset: {impact_data.get('co2', 0)} t
Provider: {impact_data.get('api', 'N/A')}
ID: {impact_data.get('id', 'N/A')}
Thank you for saving the planet!
"""
    st.download_button("📄 Download Certificate", cert_text, "offset_cert.txt", "text/plain")

def trigger_offset(api_choice, trees, offset_tco2, user_email, note):
    metadata = {"email": user_email, "note": note}
    if api_choice.startswith("Waldonia"):
        impact_data = waldonia_plant_trees(trees, note, metadata)
        api_id = impact_data.get('order_id') if impact_data else None
    else:
        action = "trees" if trees > 0 else "offset"
        tonnes = trees / 333 if action == "trees" else offset_tco2
        impact_data = ecologi_offset(tonnes, action)
        api_id = impact_data.get('transaction_id') if impact_data else None

    if impact_data:
        impact_entry = {
            'id': api_id,
            'trees': trees,
            'co2': offset_tco2,
            'api': api_choice,
            'date': datetime.now().isoformat(),
            'status': 'completed'
        }
        st.session_state.impacts.append(impact_entry)
        generate_cert(impact_entry)
        return True
    return False

# -------------------------------------------------
# GAUGE CHART FUNCTION
# -------------------------------------------------
def draw_gauge(total_save, target=1000):
    fig = go.Figure(go.Indicator(
        mode="gauge+number+delta",
        value=total_save,
        delta={'reference': 0, 'increasing': {'color': "green"}},
        gauge={
            'axis': {'range': [0, target], 'tickwidth': 1, 'tickcolor': "darkgreen"},
            'bar': {'color': "#51CF66"},
            'bgcolor': "white",
            'steps': [
                {'range': [0, target*0.5], 'color': "#FF6B6B"},
                {'range': [target*0.5, target*0.8], 'color': "#FFD966"},
                {'range': [target*0.8, target], 'color': "#51CF66"}
            ],
            'threshold': {
                'line': {'color': "darkgreen", 'width': 4},
                'thickness': 0.75,
                'value': total_save
            }
        },
        title={'text': "CO₂ Saved Towards 1 Ton Goal"},
        domain={'x': [0, 1], 'y': [0, 1]}
    ))
    fig.update_layout(paper_bgcolor='rgba(0,0,0,0)', font={'color': "darkgreen", 'family': "Arial"})
    return fig

# -------------------------------------------------
# MAIN LAYOUT
# -------------------------------------------------
st.markdown("""
<div class='hero'>
    <h1>EcoGigHub CO₂ Calculator</h1>
    <h3>Make sustainable choices and measure your impact</h3>
</div>
""", unsafe_allow_html=True)

col_left, col_right = st.columns([1, 3])

# LEFT: ADD / EDIT
with col_left:
    st.header("Add Item")
    category = st.selectbox("Category", ["Products", "Gig Services"], key="cat")
    data = products if category == "Products" else gigs
    item = st.selectbox("Item", list(data.keys()), key="item")
    variant_opts = [k for k in data[item].keys() if k != "price"]
    variant = st.selectbox("Variant", variant_opts, format_func=lambda x: x.title(), key="var")
    qty = st.number_input("Quantity", min_value=1, value=1, step=1, key="qty")

    if st.button("Add to Basket", type="primary"):
        st.session_state.basket = add_item(category, item, variant, qty)
        st.success(f"Added {qty} × {item} ({variant.title()})")
        st.balloons()

    if not st.session_state.basket.empty:
        st.markdown("### Edit Quantities")
        edited = st.data_editor(
            st.session_state.basket[["Item", "Variant", "Quantity"]].copy(),
            use_container_width=True,
            hide_index=True,
            column_config={"Quantity": st.column_config.NumberColumn("Qty", min_value=0, step=1)},
            key="edit_qty"
        )
        df_tmp = st.session_state.basket.copy()
        df_tmp.loc[edited.index, "Quantity"] = edited["Quantity"]
        df_tmp = df_tmp[df_tmp["Quantity"] > 0].copy()
        st.session_state.basket = recalculate(df_tmp)

        if st.button("Clear Basket", type="secondary"):
            st.session_state.basket = pd.DataFrame(columns=REQUIRED_COLS)
            st.experimental_rerun()

# RIGHT: DASHBOARD & IMPACT
with col_right:
    basket = st.session_state.basket
    if basket.empty:
        st.info("Add items to your basket to see your environmental impact.")
    else:
        df = recalculate(basket)
        total_reg, total_eco, total_save, total_money = totals(df)
        trees = total_save / TREE_CO2_YEAR
        miles = total_save / CAR_MILES_PER_KG
        flights = total_save / FLIGHT_KG_PER_HOUR

        # Show gauge chart for impact summary
        fig_gauge = draw_gauge(total_save)
        st.plotly_chart(fig_gauge, use_container_width=True)

        col_metrics = st.columns(3)
        col_metrics[0].metric("Regular Footprint", f"{total_reg:,} kg CO₂e")
        col_metrics[1].metric("Eco Footprint", f"{total_eco:,} kg CO₂e")
        col_metrics[2].metric("CO₂ Saved", f"{total_save:,} kg", delta=f"+{total_save:,} kg")

        # Impact Cards
        c1, c2, c3, c4 = st.columns(4)
        c1.markdown(f'<div class="metric-card"><div class="metric-value">{total_save:,.0f}</div><div class="metric-title">kg Saved</div></div>', unsafe_allow_html=True)
        c2.markdown(f'<div class="metric-card"><div class="metric-value">{trees:,.0f}</div><div class="metric-title">Trees</div></div>', unsafe_allow_html=True)
        c3.markdown(f'<div class="metric-card"><div class="metric-value">{miles:,.0f}</div><div class="metric-title">Miles</div></div>', unsafe_allow_html=True)
        c4.markdown(f'<div class="metric-card"><div class="metric-value">{flights:,.0f}</div><div class="metric-title">Flights</div></div>', unsafe_allow_html=True)

        # Donut Chart for proportion analysis
        fig_donut = go.Figure(data=[go.Pie(
            labels=["Eco", "Saved"],
            values=[total_eco, total_save],
            hole=0.55,
            marker_colors=["#51CF66", "#228B22"],
            textinfo="label+percent"
        )])
        fig_donut.update_layout(showlegend=False, paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)")
        st.plotly_chart(fig_donut, use_container_width=True, config={'displayModeBar': False})

        # Item Table
        st.markdown("### Your Eco Choices")
        table_html = '<table><thead><tr>'
        headers = ["Item", "Choice", "Qty", "Saved (kg)", "Price"]
        for h in headers:
            table_html += f'<th>{h}</th>'
        table_html += '</tr></thead><tbody>'
        for _, r in df.iterrows():
            badge_html = variant_badge(r["Variant"])
            table_html += (
                f'<tr><td>{r["Item"]}</td>'
                f'<td>{badge_html}</td>'
                f'<td style="text-align:center;">{int(r["Quantity"])}</td>'
                f'<td style="text-align:right; font-weight:bold; color:#228B22;">{r["Savings"]:.1f}</td>'
                f'<td style="text-align:right;">${r["Total $"]:.2f}</td></tr>'
            )
        table_html += '</tbody></table>'
        st.markdown(table_html, unsafe_allow_html=True)

        # Plant Trees & Offset Section
        st.markdown("## 🌳 Plant Trees & Offset")
        email = st.text_input("Email", placeholder="you@example.com")

        col_donate, col_buy = st.columns(2)

        with col_buy:
            st.markdown("### Buy Items")
            for idx, row in df.iterrows():
                if row["Unit Price"] > 0:
                    if st.button(f"Buy ×{int(row['Quantity'])} – ${row['Total $']:.2f}", key=f"buy_{idx}"):
                        url = create_checkout(row["Item"], row["Variant"], int(row["Quantity"]), row["Unit Price"], email)
                        if url:
                            st.markdown(f"[💳 Pay now]({url})")

        with col_donate:
            api_choice = st.selectbox("🌍 Provider", ["Waldonia (Trees)", "Ecologi (Offsets + Trees)"])
            trees_suggested = max(1, round(total_save / TREE_CO2_YEAR))
            trees = st.slider("🌲 Trees to Plant", 0, 50, trees_suggested)
            offset_tco2 = 0.0
            if "Ecologi" in api_choice:
                offset_tco2 = st.number_input("Direct Offset (tCO₂e)", 0.0, 10.0, round(total_save / 1000, 3))

            co2_offset = trees * TREE_CO2_YEAR + (offset_tco2 * 1000)
            cost_trees = trees * 1.0
            cost_offset = offset_tco2 * 6.0
            total_cost = cost_trees + cost_offset

            st.metric("🌲 Trees", trees)
            st.metric("Offset CO₂", f"{co2_offset:,.0f} kg/year")
            st.metric("💰 Total Cost", f"${total_cost:.2f}")

            note = st.text_input("Note", "EcoGigHub Donation")

            if (trees > 0 or offset_tco2 > 0) and st.button(f"🌳 PLANT {trees} TREES & OFFSET", type="primary"):
                amount_cents = int(total_cost * 100)
                description = f"{trees} Trees + {offset_tco2}t via {api_choice}"
                metadata = {"trees": trees, "offset_tco2": offset_tco2, "api": api_choice, "email": email}
                
                session_url = create_stripe_session(amount_cents, description, metadata)
                if session_url:
                    st.markdown(f"[💳 Pay & Plant Now]({session_url})")
                    st.success(f"🎉 Thank you! You're planting {trees} trees!")
                else:
                    st.error("Payment setup failed.")

            session_id = st.query_params.get("session_id", [None])[0]
            if session_id and verify_stripe_session(session_id):
                st.success("✅ Payment successful! Triggering tree planting...")
                if trigger_offset(api_choice, trees, offset_tco2, email, note):
                    st.success(f"🌳 {trees} trees planted! Certificate ready!")
                    st.experimental_rerun()

            # Display recent impacts
            if st.session_state.impacts:
                st.markdown("### 📊 Your Recent Tree Impacts")
                for impact in reversed(st.session_state.impacts[-3:]):  # last 3 impacts most recent on top
                    st.info(f"**{impact['api']}** | {impact['trees']} trees | ID: {impact['id']} | Date: {impact['date'][:10]}")

# -------------------------------------------------
# FOOTER
# -------------------------------------------------
st.markdown("""
<footer>Powered by <b>EcoGigHub</b> | Trees: Waldonia & Ecologi | Data: IPCC</footer>
""", unsafe_allow_html=True)
