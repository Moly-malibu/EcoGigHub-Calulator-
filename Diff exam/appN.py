import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import requests
import json
from datetime import datetime
from io import BytesIO
import base64  # For PDF sim

# Page config
st.set_page_config(
    page_title="EcoGigHub CO2 Calculator",
    page_icon="🌿",
    layout="wide"
)

# Custom Eco Theme
st.markdown("""
<style>
    .main {background-color: #f8fff8; padding: 2rem;}
    [data-testid="stSidebar"] {background-color: #e8f5e8;}
    .stMetric {border: 1px solid #90EE90; border-radius: 12px; padding: 10px; background: #f0fff0;}
    .stMetric > label {color: #006400 !important; font-weight: bold; font-size: 1.1rem;}
    .stMetric > div > div > div {color: #228B22 !important; font-size: 1.8rem; font-weight: bold;}
    .stPlotlyChart {border-radius: 12px; box-shadow: 0 4px 8px rgba(0,0,0,0.1);}
    .stButton > button {background-color: #51CF66; color: white; border-radius: 20px; font-weight: bold;}
    .clear-btn > button {background-color: #FF6B6B !important; color: white !important; border-radius: 20px; font-weight: bold;}
    .stDataEditor {border: 1px solid #90EE90; border-radius: 10px;}
    h1, h2, h3 {color: #006400;}
</style>
""", unsafe_allow_html=True)

# === EXTENDED CO2 DATABASE ===
products = {
    # Clothing (kg CO₂e per item)
    "Cotton T-Shirt": {"regular": 9.0, "eco": 4.5},
    "Pair of Jeans": {"regular": 33.4, "bio": 16.7},
    "Leather Shoes": {"regular": 16.0, "vegan": 7.0},
    "Wool Sweater": {"regular": 18.0, "recycled": 9.0},
    "Polyester Jacket": {"regular": 15.0, "recycled": 6.0},

    # Food & Drinks (kg CO₂e per unit)
    "Beef Burger (150g)": {"regular": 4.0, "plant-based": 1.0},
    "Cup of Coffee (200ml)": {"regular": 0.05, "fair-trade": 0.03},
    "Bottle of Milk (1L)": {"regular": 3.0, "oat": 0.9},
    "Chocolate Bar (100g)": {"regular": 4.6, "organic": 3.2},
    "Avocado (1 unit)": {"regular": 0.85, "local": 0.4},
    "Bread Loaf (800g)": {"regular": 1.4, "organic": 1.0},
    "Pizza (margherita)": {"regular": 3.2, "vegan": 1.8},

    # Electronics (kg CO₂e per item)
    "Smartphone": {"regular": 70.0, "refurbished": 15.0},
    "Laptop (14\")": {"regular": 300.0, "eco-brand": 180.0},

    # Packaging
    "Plastic Bottle (500ml)": {"regular": 0.08, "reusable": 0.01},
    "Paper Bag": {"regular": 0.05, "recycled": 0.02},
}

gigs = {
    # Transport (kg CO₂e per service)
    "Car Delivery (5km)": {"car": 0.8, "bike": 0.05},
    "Ride Share (10km)": {"gas": 2.0, "electric": 0.2},
    "Flight (1h, economy)": {"regular": 90.0, "offset": 0.0},
    "Train Ride (100km)": {"diesel": 6.0, "electric": 2.5},

    # Services
    "House Cleaning (1h)": {"standard": 0.5, "green": 0.1},
    "Lawn Mowing (30min)": {"gas": 1.2, "electric": 0.3},
    "Online Meeting (1h)": {"streaming": 0.05, "low-data": 0.01},
    "Event Catering (per person)": {"meat": 5.0, "vegetarian": 2.0},
}

# === API CONFIGS ===
# Waldonia: Trees only (€1/tree)
WALDONIA_BASE = "https://api.waldonia.com/v1" if not st.secrets.get("WALDONIA_SANDBOX") else "https://sandbox.waldonia.com/api/v1"
WALDONIA_KEY = st.secrets.get("WALDONIA_API_KEY", "sandbox_key_here")

# Ecologi: Trees + Offsets (~$6/tCO₂e)
ECOLOGI_BASE = "https://publicapi.ecologi.com/v1"
ECOLOGI_KEY = st.secrets.get("ECOLOGI_API_KEY", "sandbox_key_here")
ECOLOGI_USERNAME = st.secrets.get("ECOLOGI_USERNAME", "your_username")

SANDBOX_MODE = "sandbox" in WALDONIA_KEY or "sandbox" in ECOLOGI_KEY  # Fixed typo

@st.cache_data(ttl=3600)
def waldonia_plant_trees(trees, note, metadata):
    """Plant trees via Waldonia API."""
    url = f"{WALDONIA_BASE}/orders"
    headers = {"Authorization": f"Bearer {WALDONIA_KEY}", "Content-Type": "application/json"}
    payload = {
        "tree_count": trees,
        "idempotency_key": f"order_{datetime.now().timestamp()}",
        "note": note,
        "metadata": metadata
    }
    response = requests.post(url, headers=headers, json=payload)
    if response.status_code == 201:
        return response.json()  # Returns order_id, etc.
    else:
        st.error(f"Waldonia Error: {response.text}")
        return None

@st.cache_data(ttl=3600)
def ecologi_offset(co2_tonnes, action="offset"):  # action: 'trees' or 'offset'
    """Offset via Ecologi API (trees or general)."""
    url = f"{ECOLOGI_BASE}/{action}"
    headers = {"Authorization": f"Bearer {ECOLOGI_KEY}", "Content-Type": "application/json"}
    payload = {"tonnes": co2_tonnes, "username": ECOLOGI_USERNAME}
    response = requests.post(url, headers=headers, json=payload)
    if response.status_code == 200:
        return response.json()  # Returns transaction_id, trees_planted, etc.
    else:
        st.error(f"Ecologi Error: {response.text}")
        return None

@st.cache_data(ttl=3600)
def ecologi_track(transaction_id):
    """Track Ecologi impact."""
    url = f"{ECOLOGI_BASE}/track/{transaction_id}"
    headers = {"Authorization": f"Bearer {ECOLOGI_KEY}"}
    response = requests.get(url, headers=headers)
    if response.status_code == 200:
        return response.json()
    return None

# Session state
if 'basket' not in st.session_state:
    st.session_state.basket = pd.DataFrame(columns=[
        'Category', 'Item', 'Variant', 'Quantity', 'CO₂ Regular', 'CO₂ Eco', 'Savings'
    ])
if 'impacts' not in st.session_state:
    st.session_state.impacts = []

# === FUNCTIONS ===
def add_item(category, item, variant, qty, co2_reg, co2_eco):
    new_row = pd.DataFrame({
        'Category': [category],
        'Item': [item],
        'Variant': [variant],
        'Quantity': [qty],
        'CO₂ Regular': [round(qty * co2_reg, 3)],
        'CO₂ Eco': [round(qty * co2_eco, 3)],
        'Savings': [round(qty * (co2_reg - co2_eco), 3)]
    })
    return pd.concat([st.session_state.basket, new_row], ignore_index=True)

def calculate_totals(df):
    if df.empty:
        return 0, 0, 0
    reg = df['CO₂ Regular'].sum()
    eco = df['CO₂ Eco'].sum()
    save = df['Savings'].sum()
    return round(reg, 2), round(eco, 2), round(save, 2)

def clear_basket():
    st.session_state.basket = pd.DataFrame(columns=[
        'Category', 'Item', 'Variant', 'Quantity', 'CO₂ Regular', 'CO₂ Eco', 'Savings'
    ])
    st.success("🗑️ Basket cleared! Start fresh.")

def generate_cert(impact_data):
    """Simulate PDF cert download."""
    cert_text = f"""
    EcoGigHub Offset Certificate
    Date: {datetime.now().strftime('%Y-%m-%d')}
    Trees Planted: {impact_data.get('trees', 0)}
    CO₂ Offset: {impact_data.get('co2', 0)} t
    ID: {impact_data.get('id', 'N/A')}
    Thank you for your contribution!
    """
    st.download_button("📄 Download Certificate", cert_text, "offset_cert.txt", "text/plain")

# Gauge chart function
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

# === SIDEBAR: Add Items ===
with st.sidebar:
    st.header("🌱 Add to Basket")
    category = st.selectbox("Category", ["Products", "Gig Services"])
    data = products if category == "Products" else gigs

    item = st.selectbox("Item", list(data.keys()))
    variant_options = list(data[item].keys())
    variant = st.selectbox("Variant", variant_options, format_func=lambda x: x.title())

    qty = st.number_input("Quantity", min_value=1, value=1, step=1)

    co2_reg = data[item].get("regular", list(data[item].values())[0])
    co2_eco = data[item].get(variant.lower(), data[item][variant_options[1]] if len(variant_options) > 1 else co2_reg)

    if st.button("➕ Add to Basket"):
        st.session_state.basket = add_item(category, item, variant, qty, co2_reg, co2_eco)
        st.success(f"Added {qty} × {item}")

# === MAIN APP ===
col1, col2 = st.columns([2, 1])

with col1:
    st.title("🌍 EcoGigHub CO₂ Impact Calculator")
    st.markdown("**Choose eco alternatives and see your carbon savings in real-time.**")

    if not st.session_state.basket.empty:
        edited_df = st.data_editor(
            st.session_state.basket,
            use_container_width=True,
            hide_index=True,
            column_config={
                "Quantity": st.column_config.NumberColumn("Qty", min_value=0, step=1),
                "CO₂ Regular": st.column_config.NumberColumn("Regular (kg)", format="%.3f"),
                "CO₂ Eco": st.column_config.NumberColumn("Eco (kg)", format="%.3f"),
                "Savings": st.column_config.NumberColumn("Saved (kg)", format="%.3f")
            }
        )
        st.session_state.basket = edited_df[edited_df['Quantity'] > 0].copy()

        # Clear Basket Button (Clear & Prominent)
        col_clear, _ = st.columns([1, 3])
        with col_clear:
            if st.button("🗑️ Clear Basket", key="clear_basket", help="Reset all items and start over"):
                if st.session_state.basket.shape[0] > 0:  # Confirmation only if not empty
                    st.warning("Are you sure? This will clear your entire basket.")
                    if st.button("Yes, Clear It!", key="confirm_clear", type="primary"):
                        clear_basket()
                        st.rerun()
                else:
                    st.info("Basket is already empty!")

        # Update totals
        total_reg, total_eco, total_save = calculate_totals(st.session_state.basket)

        # Metrics
        m1, m2, m3 = st.columns(3)
        m1.metric("🛒 Regular Footprint", f"{total_reg} kg CO₂e")
        m2.metric("🌿 Eco Footprint", f"{total_eco} kg CO₂e")
        m3.metric("✅ CO₂ Saved", f"{total_save} kg", delta=f"+{total_save} kg")

        # Bar Chart
        chart_df = pd.DataFrame({
            'Type': ['Regular', 'Eco', 'Saved'],
            'CO₂ (kg)': [total_reg, total_eco, total_save]
        })
        fig = px.bar(chart_df, x='Type', y='CO₂ (kg)',
                     color='Type',
                     color_discrete_map={'Regular': '#FF6B6B', 'Eco': '#51CF66', 'Saved': '#228B22'},
                     text='CO₂ (kg)',
                     title="Your Carbon Impact")
        fig.update_traces(textposition='outside')
        fig.update_layout(showlegend=False, yaxis_title="kg CO₂e")
        st.plotly_chart(fig, use_container_width=True)

        # Gauge Chart (Progress to 1 Ton)
        fig_gauge = draw_gauge(total_save)
        st.plotly_chart(fig_gauge, use_container_width=True)

with col2:
    st.header("🌳 Offset with APIs")
    st.markdown("**Plant trees or offset CO₂ via Waldonia/Ecologi.**")

    api_choice = st.selectbox("API Provider", ["Waldonia (Trees)", "Ecologi (Offsets + Trees)"])

    total_save = calculate_totals(st.session_state.basket)[2]
    trees_suggested = max(1, round(total_save / 20))  # 20kg/tree/year
    trees = st.slider("Trees to Plant", 0, 50, trees_suggested)
    offset_tco2 = st.number_input("Direct Offset (tCO₂e)", 0.0, 10.0, round(total_save / 1000000, 3)) if api_choice == "Ecologi (Offsets + Trees)" else 0

    co2_offset = trees * 20 + (offset_tco2 * 1000)
    cost_trees = trees * 1.0  # €1/tree Waldonia
    cost_offset = offset_tco2 * 6.0  # ~$6/t Ecologi
    total_cost = cost_trees + cost_offset

    st.metric("🌲 Trees", trees)
    st.metric("Offset CO₂", f"{co2_offset} kg/year")
    st.metric("Est. Cost", f"${total_cost:.2f}")

    user_email = st.text_input("Email (for cert)", "user@example.com")
    note = st.text_input("Note", "EcoGigHub Contribution")

    if trees > 0 or offset_tco2 > 0:
        if st.button("🚀 Donate Now", type="primary"):
            if api_choice.startswith("Waldonia"):
                impact_data = waldonia_plant_trees(trees, note, {"email": user_email})
                api_id = impact_data.get('order_id') if impact_data else None
            else:  # Ecologi
                action = "trees" if trees > 0 else "offset"
                impact_data = ecologi_offset(offset_tco2 if action == "offset" else trees / 333, action)  # Approx trees to tCO₂e
                api_id = impact_data.get('transaction_id') if impact_data else None

            if impact_data:
                impact_entry = {
                    'id': api_id,
                    'trees': trees,
                    'co2': offset_tco2,
                    'api': api_choice,
                    'date': datetime.now().isoformat(),
                    'status': 'pending'
                }
                st.session_state.impacts.append(impact_entry)
                st.balloons()
                st.success(f"Processed! ID: {api_id}. Track below.")
                generate_cert(impact_entry)

    # Track Impacts
    if st.session_state.impacts:
        st.subheader("📊 Track Impacts")
        for impact in st.session_state.impacts:
            if impact['api'].startswith("Ecologi"):
                track_data = ecologi_track(impact['id'])
                if track_data:
                    status = track_data.get('status', 'unknown')
                    location = track_data.get('location', 'N/A')
                    st.info(f"**{impact['api']} {impact['id']}**: {status} | Trees: {impact['trees']} | Loc: {location}")
            else:
                st.info(f"**Waldonia {impact['id']}**: Pending | Trees: {impact['trees']}")

    st.caption(f"Sandbox: {SANDBOX_MODE}. Waldonia: €1/tree. Ecologi: ~$6/t. Docs: [Waldonia](https://waldonia.com/api) | [Ecologi](https://docs.ecologi.com)")

# Footer
st.markdown("---")
st.markdown(
    "<p style='text-align: center; color: #666;'>"
    "Powered by <b>EcoGigHub</b> | APIs: Waldonia & Ecologi | Data: IPCC, DEFRA | "
    "<a href='#'>Learn More</a></p>",
    unsafe_allow_html=True
)