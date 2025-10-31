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

stripe.api_key = st.secrets.get("stripe_api_key") or "sk_test_XXXXXXXXXXXXXXXXXXXXXXXX"
BASE_URL = st.secrets.get("base_url") or "http://localhost:8501"
SUCCESS_URL = f"{BASE_URL}/?session_id={{CHECKOUT_SESSION_ID}}"
CANCEL_URL = f"{BASE_URL}/"

TREE_CO2_YEAR = 20.0
CAR_MILES_PER_KG = 4.6
FLIGHT_KG_PER_HOUR = 90.0

# API CONFIGS
WALDONIA_BASE = "https://api.waldonia.com/v1"
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
    .impact-card {background:linear-gradient(135deg,#e8f5e8,#d0f0d0);padding:1.5rem;border-radius:20px;text-align:center;box-shadow:0 6px 16px rgba(0,0,0,0.08);transition:0.3s;border:2px solid #90EE90;}
    .impact-card:hover {transform:translateY(-5px);box-shadow:0 12px 24px rgba(0,0,0,0.1);}
    .big-number {font-size:3rem;font-weight:900;color:#228B22;margin:0;}
    .big-label {font-size:1.1rem;color:#006400;font-weight:bold;margin:8px 0 0;}
    .eco-badge {background:#51CF66;color:white;padding:6px 12px;border-radius:16px;font-weight:bold;display:inline-block;margin-right:8px;font-size:0.9em;}
    .reg-badge {background:#888;color:white;padding:6px 12px;border-radius:16px;font-weight:bold;display:inline-block;margin-right:8px;font-size:0.9em;}
    .stButton>button {background:#51CF66;color:white;border-radius:25px;font-weight:bold;padding:0.7rem 1.5rem;}
    .tree-btn button {background:#2E8B57 !important;}
    h1, h2, h3 {color:#006400;}
    .progress-bar {height:20px;border-radius:10px;background:#ddd;}
    .progress-fill {height:100%;border-radius:10px;background:linear-gradient(90deg,#51CF66,#228B22);}
    .hero-title {font-size:1.8rem;font-weight:900;color:#228B22;text-align:center;margin:1.5rem 0;}
    .stMetric {border:1px solid #90EE90;border-radius:12px;padding:10px;background:#f0fff0;}
    .stMetric>label {color:#006400 !important;font-weight:bold;font-size:1.1rem;}
    .stMetric>div>div>div {color:#228B22 !important;font-size:1.8rem;font-weight:bold;}
</style>
""", unsafe_allow_html=True)

# -------------------------------------------------
# DATABASE
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

def create_checkout(name, variant, qty, price, email):
    try:
        session = stripe.checkout.Session.create(
            payment_method_types=["card"],
            line_items=[{
                "price_data": {"currency": "usd", "product_data": {"name": f"{name} ({variant})"}, "unit_amount": int(price * 100)},
                "quantity": qty,
            }],
            mode="payment", success_url=SUCCESS_URL, cancel_url=CANCEL_URL, customer_email=email or None,
        )
        return session.url
    except: return None

def create_stripe_session(amount_cents, description, metadata=None):
    try:
        session = stripe.checkout.Session.create(
            payment_method_types=['card'],
            line_items=[{'price_data': {'currency': 'usd', 'product_data': {'name': 'EcoGigHub Tree Donation', 'description': description}, 'unit_amount': amount_cents}, 'quantity': 1}],
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
    except: return False

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
        impact_entry = {'id': api_id, 'trees': trees, 'co2': offset_tco2, 'api': api_choice, 'date': datetime.now().isoformat(), 'status': 'completed'}
        st.session_state.impacts.append(impact_entry)
        generate_cert(impact_entry)
        return True
    return False

# -------------------------------------------------
# MAIN LAYOUT
# -------------------------------------------------
st.markdown("<h1 style='text-align: center; color: green;'>EcoGigHub CO₂ Calculator</h1>", unsafe_allow_html=True)
# st.markdown("<h2 style='text-align: center; color: gray;'>Choose eco alternatives: </h2>", unsafe_allow_html=True)
st.markdown("<h2 style='text-align: center; color: gray;'>Reduce Emissions -> Save the Planet </h2>", unsafe_allow_html=True)
# st.markdown("<h2 style='text-align: center; color: gray;'>save the planet</h2>", unsafe_allow_html=True)
# st.markdown("<h2 style='text-align: center; color: gray;'> ❤️ Feel Amazing</h2>", unsafe_allow_html=True)

col_left, col_right = st.columns([1, 3])

# LEFT: ADD / EDIT
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
        edited = st.data_editor(st.session_state.basket[["Item","Variant","Quantity"]].copy(), use_container_width=True, hide_index=True,
                               column_config={"Quantity":st.column_config.NumberColumn("Qty",min_value=0,step=1)}, key="edit_qty")
        df_tmp = st.session_state.basket.copy()
        df_tmp.loc[edited.index, "Quantity"] = edited["Quantity"]
        df_tmp = df_tmp[df_tmp["Quantity"]>0].copy()
        st.session_state.basket = recalculate(df_tmp)
        if st.button("Restart", type="secondary"): st.session_state.basket = pd.DataFrame(columns=REQUIRED_COLS); st.rerun()

# RIGHT: DASHBOARD
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

        # Hero
        st.markdown(f"""
        <div class="hero-title">
            You saved <strong>{total_save:,.0f} kg</strong> of CO₂ — 
            equivalent to <strong>{miles:,.0f} miles</strong> not driven!
        </div>
        """, unsafe_allow_html=True)

        # Metrics
        m1, m2, m3 = st.columns(3)
        m1.metric("Regular Footprint", f"{total_reg:,} kg CO₂e")
        m2.metric("Eco Footprint", f"{total_eco:,} kg CO₂e")
        m3.metric("CO₂ Saved", f"{total_save:,} kg", delta=f"+{total_save:,} kg")

        # Impact Cards
        c1,c2,c3,c4 = st.columns(4)
        with c1: st.markdown(f'<div class="impact-card"><div class="big-number">{total_save:,.0f}</div><div class="big-label">kg Saved</div></div>', unsafe_allow_html=True)
        with c2: st.markdown(f'<div class="impact-card"><div class="big-number">{trees:,.0f}</div><div class="big-label">Trees</div></div>', unsafe_allow_html=True)
        with c3: st.markdown(f'<div class="impact-card"><div class="big-number">{miles:,.0f}</div><div class="big-label">Miles</div></div>', unsafe_allow_html=True)
        with c4: st.markdown(f'<div class="impact-card"><div class="big-number">{flights:,.0f}</div><div class="big-label">Flights</div></div>', unsafe_allow_html=True)

        # Donut
        fig_donut = go.Figure(data=[go.Pie(labels=["Eco","Saved"], values=[total_eco,total_save], hole=0.5, marker_colors=["#51CF66","#228B22"], textinfo="label+percent")])
        fig_donut.update_layout(showlegend=False, paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)")
        st.plotly_chart(fig_donut, use_container_width=True, config={'displayModeBar': False})

        # Progress
        progress = min(total_save/1000,1.0)
        st.markdown(f"""
        <div style="margin:30px 0;">
            <div style="font-weight:bold;margin-bottom:8px;">Progress to 1 Ton</div>
            <div class="progress-bar"><div class="progress-fill" style="width:{progress*100}%"></div></div>
            <div style="text-align:right;font-size:0.9rem;margin-top:4px;">{progress*100:.0f}% ({total_save:,.0f} / 1,000 kg)</div>
        </div>
        """, unsafe_allow_html=True)

        # Table
        st.markdown("## Your Eco Choices")
        html = '<table style="width:100%;border-collapse:collapse;"><thead><tr style="background:#e8f5e8;">'
        for h in ["Item","Choice","Qty","Saved (kg)","Price"]: html+=f'<th style="padding:12px;border-bottom:2px solid #90EE90;">{h}</th>'
        html+='</tr></thead><tbody>'
        for _,r in df.iterrows():
            badge = variant_badge(r["Variant"])
            html+=f'<tr style="border-bottom:1px solid #ddd;"><td style="padding:12px;">{r["Item"]}</td><td style="padding:12px;">{badge}</td><td style="padding:12px;text-align:center;">{int(r["Quantity"])}</td><td style="padding:12px;text-align:right;font-weight:bold;color:#228B22;">{r["Savings"]:.1f}</td><td style="padding:12px;text-align:right;">${r["Total $"]:.2f}</td></tr>'
        html+='</tbody></table>'
        st.markdown(html, unsafe_allow_html=True)

        # === COMPLETE PLANT TREES & OFFSET SECTION ===
        st.markdown("## 🌳 **Plant Trees & Offset** (Main Feature!)")
        email = st.text_input("Email", placeholder="you@example.com")

        col_a, col_b = st.columns(2)
        with col_a:
            st.markdown("### Buy Items")
            for idx, row in df.iterrows():
                if row["Unit Price"] > 0:
                    if st.button(f"Buy ×{int(row['Quantity'])} – ${row['Total $']}", key=f"buy_{idx}"):
                        url = create_checkout(row["Item"], row["Variant"], int(row["Quantity"]), row["Unit Price"], email)
                        if url: st.markdown(f"[Pay now]({url})")

        with col_b:
            st.markdown("### **Donate to Trees**")
            api_choice = st.selectbox("🌍 Provider", ["Waldonia (Trees)", "Ecologi (Offsets + Trees)"])
            trees_suggested = max(1, round(total_save / TREE_CO2_YEAR))
            trees = st.slider("🌲 Trees to Plant", 0, 50, trees_suggested)
            offset_tco2 = st.number_input("Direct Offset (tCO₂e)", 0.0, 10.0, round(total_save / 1000, 3)) if "Ecologi" in api_choice else 0

            co2_offset = trees * TREE_CO2_YEAR + (offset_tco2 * 1000)
            cost_trees = trees * 1.0
            cost_offset = offset_tco2 * 6.0
            total_cost = cost_trees + cost_offset

            st.metric("🌲 Trees", trees)
            st.metric("Offset CO₂", f"{co2_offset:,.0f} kg/year")
            st.metric("💰 Total Cost", f"${total_cost:.2f}")

            note = st.text_input("Note", "EcoGigHub Donation")

            # **CELEBRATION TRIGGERED ON BUTTON CLICK**
            if trees > 0 or offset_tco2 > 0:
                if st.button(f"🌳 PLANT {trees:,.0f} TREES & OFFSET", type="primary", help="Click to donate and save the planet!"):
                    amount_cents = int(total_cost * 100)
                    description = f"{trees} Trees + {offset_tco2}t via {api_choice}"
                    metadata = {"trees": trees, "offset_tco2": offset_tco2, "api": api_choice, "email": email}
                    
                    session_url = create_stripe_session(amount_cents, description, metadata)
                    if session_url:
                        st.markdown(f"[💳 Pay & Plant Now]({session_url})")
                        # **st.balloons()**  # 🎉 CELEBRATION BOMBS!
                        st.success(f"🎉 Amazing! You're planting {trees} trees!")
                    else:
                        st.error("Payment setup failed.")

            # Payment success check
            session_id = st.query_params.get("session_id")
            if session_id:
                if verify_stripe_session(session_id):
                    st.success("✅ Payment successful! Triggering tree planting...")
                    if trigger_offset(api_choice, trees, offset_tco2, email, note):
                        # **st.balloons()**  # 🎉 MORE CELEBRATION!
                        st.success(f"🌳 {trees} trees planted! Certificate ready!")
                        st.rerun()
                st.query_params.clear()

            # Track Impacts
            if st.session_state.impacts:
                st.markdown("### 📊 Your Tree Impacts")
                for impact in st.session_state.impacts[-3:]:  # Show last 3
                    st.info(f"**{impact['api']}** | {impact['trees']} trees | ID: {impact['id']}")

        # -------------------------------------------------
        # FINAL BAR CHART WITH LEGEND (BOTTOM)
        # -------------------------------------------------
        st.markdown("---")
        st.markdown("### **Your Carbon Impact Summary**")
        chart_df = pd.DataFrame({
            "Category": ["Regular consumption", "Eco consumption", "CO₂ Saved"],
            "kg CO₂e": [total_reg, total_eco, total_save]
        })
        fig = px.bar(chart_df, x="Category", y="kg CO₂e", color="Category",
                     color_discrete_map={"Regular consumption":"#FF6B6B","Eco consumption":"#51CF66","CO₂ Saved":"#228B22"},
                     text="kg CO₂e")
        fig.update_traces(texttemplate="%{text:,.0f}", textposition="outside")
        fig.update_layout(showlegend=True, legend=dict(orientation="h", y=1.02, x=0.5, xanchor="center"),
                         yaxis_title="kg CO₂e", plot_bgcolor="rgba(0,0,0,0)")
        st.plotly_chart(fig, use_container_width=True)

# -------------------------------------------------
# FOOTER
# -------------------------------------------------
st.markdown("---")
st.markdown("<p style='text-align:center;color:#666;'>Powered by <b>EcoGigHub</b> | Trees: Waldonia & Ecologi | Data: IPCC</p>", unsafe_allow_html=True)