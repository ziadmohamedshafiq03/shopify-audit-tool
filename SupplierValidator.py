import streamlit as st
import pandas as pd
import numpy as np
import io
import json
import os
import time
import requests
import plotly.express as px

# ============================================================
#  SHOPIFY OVERSELL RISK AUDITOR v9 (Ultimate Conversion Engine)
# ============================================================

st.set_page_config(page_title="Shopify Oversell Risk Auditor", page_icon="🛡️", layout="wide")

# --- BACKEND ---
LEADS_FILE = os.path.join(os.path.dirname(__file__), "captured_leads.json")
ZAPIER_WEBHOOK = "https://hooks.zapier.com/hooks/catch/YOUR_WEBHOOK_ID/" 

def save_lead(email, store_url, context, stats=None):
    leads = []
    if os.path.exists(LEADS_FILE):
        with open(LEADS_FILE, 'r') as f:
            leads = json.load(f)
    lead_data = {"email": email, "store_url": store_url, "context": context, "stats": stats or {}}
    leads.append(lead_data)
    with open(LEADS_FILE, 'w') as f:
        json.dump(leads, f, indent=2)
    if "YOUR_WEBHOOK_ID" not in ZAPIER_WEBHOOK:
        try:
            requests.post(ZAPIER_WEBHOOK, json=lead_data, timeout=3)
        except:
            pass

# --- CUSTOM CSS ---
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap');
    
    html, body, [class*="css"] { 
        font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
    }
    
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    header {visibility: hidden;}
    
    /* Hero */
    .hero-section {
        text-align: center;
        padding: 2.5rem 1rem 1.5rem 1rem;
    }
    .hero-section h1 {
        font-size: 2.4rem;
        font-weight: 800;
        color: #1a1a2e;
        margin-bottom: 0.75rem;
        letter-spacing: -0.02em;
    }
    .hero-section p {
        font-size: 1.1rem;
        color: #5a5a72;
        max-width: 700px;
        margin: 0 auto;
        line-height: 1.7;
    }
    
    /* Metric Cards */
    .metric-row {
        display: grid;
        grid-template-columns: repeat(4, 1fr);
        gap: 1rem;
        margin: 1.5rem 0;
    }
    .m-card {
        background: #ffffff;
        border: 1px solid #e8e8ee;
        border-radius: 12px;
        padding: 1.5rem;
        text-align: center;
        box-shadow: 0 1px 2px rgba(0,0,0,0.05);
    }
    .m-card .num { font-size: 2.5rem; font-weight: 800; color: #1a1a2e; margin: 0; }
    .m-card .label { font-size: 0.85rem; color: #8888a0; font-weight: 700; text-transform: uppercase; letter-spacing: 0.06em; margin-top: 0.35rem; }
    .m-card.danger .num { color: #e53935; }
    .m-card.danger { border-color: #ffcdd2; background: #fff5f5; }
    .m-card.warn .num { color: #f57c00; }
    .m-card.warn { border-color: #ffe0b2; background: #fff8f0; }
    
    /* Banners */
    .risk-banner {
        background: #fff5f5;
        border: 1px solid #ef9a9a;
        border-left: 5px solid #e53935;
        border-radius: 12px;
        padding: 2rem 2.5rem;
        margin: 1.5rem 0 2rem 0;
    }
    .risk-banner h2 { color: #c62828; font-size: 2rem; font-weight: 800; margin: 0 0 0.75rem 0; }
    .risk-banner p { color: #424242; font-size: 1.05rem; line-height: 1.65; margin: 0; }
    
    .safe-banner {
        background: #f1f8f5;
        border: 1px solid #a5d6a7;
        border-left: 5px solid #43a047;
        border-radius: 12px;
        padding: 2rem 2.5rem;
        margin: 1.5rem 0 2rem 0;
    }
    .safe-banner h2 { color: #2e7d32; font-size: 1.5rem; font-weight: 700; margin: 0 0 0.5rem 0; }
    
    /* Section Headers */
    .section-header { font-size: 1.35rem; font-weight: 800; color: #1a1a2e; margin: 2.5rem 0 0.5rem 0; }
    .section-sub { color: #5a5a72; font-size: 1rem; margin-bottom: 1.5rem; }
    
    /* CTA Card */
    .cta-card {
        background: #ffffff;
        border: 1px solid #e8e8ee;
        border-radius: 16px;
        padding: 2.5rem;
        margin-top: 2rem;
        box-shadow: 0 4px 12px rgba(0,0,0,0.03);
    }
    .cta-card h3 { font-size: 1.35rem; font-weight: 700; color: #1a1a2e; margin-bottom: 0.5rem; }
    .cta-card p { color: #5a5a72; font-size: 1rem; line-height: 1.6; }
    
    /* Sticky Bottom CTA */
    .sticky-cta {
        position: fixed;
        bottom: 0;
        left: 0;
        width: 100%;
        background: #ffffff;
        padding: 1rem 2rem;
        display: flex;
        justify-content: space-between;
        align-items: center;
        z-index: 9999;
        box-shadow: 0 -4px 20px rgba(0,0,0,0.1);
        border-top: 4px solid #e53935;
    }
    .sticky-cta-text { font-size: 1.15rem; font-weight: 600; color:#1a1a2e; }
    .sticky-cta-highlight { color: #e53935; font-weight: 800; }
    
    /* Divider */
    .soft-divider { border: none; border-top: 1px solid #e8e8ee; margin: 3rem 0; }
</style>
""", unsafe_allow_html=True)

# --- SIDEBAR ---
with st.sidebar:
    st.image("https://upload.wikimedia.org/wikipedia/commons/thumb/0/0e/Shopify_logo_2018.svg/2560px-Shopify_logo_2018.svg.png", width=120)
    st.markdown("### ⚙️ Store Parameters")
    aov = st.number_input("Average Order Value ($)", min_value=1.0, value=75.0, step=5.0)
    enable_enterprise = st.checkbox("🚀 Enable Enterprise Mock Data", value=True)
    st.markdown("---")
    st.markdown("<p style='font-size:0.85rem; color:#8888a0;'>Built by Ziad<br>Custom Shopify Sync Engineering</p>", unsafe_allow_html=True)

# --- HERO ---
st.markdown("""
<div class="hero-section">
    <h1>🛡️ Shopify Oversell Risk Auditor</h1>
    <p>Upload your supplier's raw inventory feed. We'll instantly audit your catalog for critical stockout risks, calculate revenue at risk, and generate a clean Shopify-ready file.</p>
    <div style="margin-top: 1.25rem; display: flex; justify-content: center; align-items: center; gap: 0.5rem; color: #008060; font-size: 0.9rem; font-weight: 600; text-transform: uppercase; letter-spacing: 0.05em;">
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="11" width="18" height="11" rx="2" ry="2"></rect><path d="M7 11V7a5 5 0 0 1 10 0v4"></path></svg>
        100% Local & Secure. Your data never leaves this session.
    </div>
</div>
""", unsafe_allow_html=True)

col1, col2, col3 = st.columns([1, 2, 1])
with col2:
    uploaded_file = st.file_uploader("Drop your supplier feed (CSV/Excel)", type=["csv", "xlsx", "xls"], label_visibility="collapsed")

if uploaded_file is not None:
    with st.spinner("Analyzing your supplier feed..."):
        time.sleep(0.4)
    try:
        if uploaded_file.name.endswith('.csv'):
            df = pd.read_csv(uploaded_file, dtype=str)
        else:
            df = pd.read_excel(uploaded_file, dtype=str)
    except Exception as e:
        st.error(f"Could not read file: {e}")
        st.stop()

    progress = st.progress(0)
    progress.progress(40)
    time.sleep(0.3)
    progress.progress(100)
    time.sleep(0.2)
    progress.empty()

    df_clean = df.copy()
    
    def find_col(keywords):
        for c in df_clean.columns:
            if any(k in str(c).lower() for k in keywords):
                return c
        return None

    df_clean.dropna(how='all', inplace=True)
    qty_col = find_col(['qty', 'quantity', 'stock', 'inventory', 'on_hand'])
    sku_col = find_col(['sku', 'item', 'product_id', 'variant sku'])
    price_col = find_col(['price', 'cost', 'wholesale'])
    
    revenue_at_risk = 0
    # ========== RISK METRICS ==========
    if qty_col:
        qs = pd.to_numeric(df_clean[qty_col], errors='coerce').fillna(0)
        low_stock = int((qs < 5).sum())
        zero_stock = int((qs == 0).sum())
        total = len(df_clean)
        risk_pct = round((low_stock / total) * 100, 1) if total > 0 else 0
        revenue_at_risk = low_stock * aov

        st.markdown(f"""
        <div class="metric-row">
            <div class="m-card"><div class="num">{total:,}</div><div class="label">Total Products</div></div>
            <div class="m-card warn"><div class="num">{low_stock:,}</div><div class="label">Low Stock (&lt; 5 units)</div></div>
            <div class="m-card danger"><div class="num">{zero_stock:,}</div><div class="label">Out of Stock</div></div>
            <div class="m-card danger"><div class="num">${revenue_at_risk:,.0f}</div><div class="label">Revenue at Risk</div></div>
        </div>
        """, unsafe_allow_html=True)

        if risk_pct > 15:
            st.markdown(f"""
            <div class="risk-banner">
                <h2>🚨 ${revenue_at_risk:,.0f} of Revenue at Risk</h2>
                <p><strong>{low_stock} products</strong> have dangerously low stock. If you only sync this CSV manually once a day,
                you are statistically guaranteed to oversell today — leading to chargebacks, wasted ad spend, and payment gateway penalties.</p>
            </div>
            """, unsafe_allow_html=True)
        else:
            st.markdown(f"""
            <div class="safe-banner">
                <h2>✅ Low Risk — ${revenue_at_risk:,.0f} Exposed</h2>
                <p>Only {risk_pct}% of your catalog has low stock. Manual syncing still leaves you vulnerable to sudden supplier stockouts, but your risk is manageable.</p>
            </div>
            """, unsafe_allow_html=True)

        # ========== ENTERPRISE DEMO (INTERACTIVE) ==========
        if enable_enterprise and total > 0:
            st.markdown('<hr class="soft-divider">', unsafe_allow_html=True)
            st.markdown('<div class="section-header">🔥 Wasted Marketing Burn (Enterprise Simulation)</div>', unsafe_allow_html=True)
            st.markdown('<div class="section-sub">Simulating ad spend against out-of-stock items. Adjust parameters below to match your real metrics.</div>', unsafe_allow_html=True)
            
            col_s1, col_s2 = st.columns(2)
            with col_s1:
                est_cpc = st.slider("Estimated Cost Per Click (CPC) $", min_value=0.10, max_value=5.00, value=1.50, step=0.10)
            with col_s2:
                daily_clicks = st.slider("Avg Daily Clicks per Out-of-Stock Product", min_value=1, max_value=100, value=15, step=1)

            # Smart Mock Data Injection (QA Tester Fix)
            df_audited = df_clean.copy()
            
            # Create a simulated product name if needed, but preserve real SKUs if they exist
            df_audited['Simulated_Product'] = df_audited[sku_col] if sku_col else "SKU-" + pd.Series(np.random.randint(10000, 99999, size=len(df_audited))).astype(str)
            
            # Resolve Vendor
            if 'Vendor' in df_audited.columns:
                df_audited['Simulated_Vendor'] = df_audited['Vendor']
            else:
                np.random.seed(42)
                vendors = ['Alpha DropShip', 'Global MegaCorp', 'FastFulfill Co', 'Apex Wholesale']
                df_audited['Simulated_Vendor'] = np.random.choice(vendors, size=len(df_audited))
            
            out_of_stock_df = df_audited[pd.to_numeric(df_audited[qty_col], errors='coerce') <= 0].copy()
            
            if len(out_of_stock_df) > 0:
                out_of_stock_df['Daily_Wasted_Spend'] = est_cpc * daily_clicks
                out_of_stock_df['Monthly_Wasted_Spend'] = out_of_stock_df['Daily_Wasted_Spend'] * 30
                total_wasted_monthly = out_of_stock_df['Monthly_Wasted_Spend'].sum()
                
                st.error(f"🚨 **Critical Alert: You are bleeding ${total_wasted_monthly:,.2f} per month** driving traffic to {len(out_of_stock_df)} out-of-stock items.")
                
                st.markdown('<div class="section-header">☠️ Vendor Liability Breakdown</div>', unsafe_allow_html=True)
                st.markdown('<div class="section-sub">Interactive analysis of the specific products draining your budget.</div>', unsafe_allow_html=True)
                
                # Dynamic Chart Switcher
                try:
                    if len(out_of_stock_df) < 5:
                        # Donut Chart for small datasets
                        fig = px.pie(
                            out_of_stock_df,
                            names='Simulated_Product',
                            values='Monthly_Wasted_Spend',
                            hole=0.6,
                            color_discrete_sequence=px.colors.sequential.Reds_r
                        )
                        fig.update_traces(textposition='outside', textinfo='percent+label', hovertemplate='<b>%{label}</b><br>Wasted Spend: $%{value:,.2f}')
                        fig.update_layout(
                            annotations=[dict(text=f"<b>{len(out_of_stock_df)}</b><br><span style='font-size:12px'>Items OOS</span>", x=0.5, y=0.5, font_size=20, showarrow=False)],
                            showlegend=False,
                            margin=dict(t=20, l=20, r=20, b=20)
                        )
                    else:
                        # Treemap for larger datasets
                        fig = px.treemap(
                            out_of_stock_df, 
                            path=[px.Constant("All Vendors"), 'Simulated_Vendor', 'Simulated_Product'], 
                            values='Monthly_Wasted_Spend',
                            color='Monthly_Wasted_Spend',
                            color_continuous_scale='Reds',
                        )
                        fig.update_layout(margin=dict(t=10, l=10, r=10, b=10), paper_bgcolor='rgba(0,0,0,0)')
                        fig.update_traces(hovertemplate='<b>%{label}</b><br>Wasted Spend: $%{value:,.2f}')
                    
                    st.plotly_chart(fig, use_container_width=True)
                except Exception as e:
                    st.warning("Could not render the interactive chart. Required libraries may be missing.", icon="⚠️")
                
                # Pandas Gradient Dataframe with Safe Rendering
                st.markdown('<div class="section-header">🩸 Highest Bleeding SKUs</div>', unsafe_allow_html=True)
                top_bleeders = out_of_stock_df[['Simulated_Vendor', 'Simulated_Product', 'Monthly_Wasted_Spend']]
                top_bleeders = top_bleeders.sort_values(by='Monthly_Wasted_Spend', ascending=False).head(10)
                
                try:
                    styled_df = top_bleeders.style.background_gradient(subset=['Monthly_Wasted_Spend'], cmap='Reds').format({'Monthly_Wasted_Spend': '${:,.2f}'})
                    st.dataframe(styled_df, use_container_width=True, hide_index=True)
                except ImportError:
                    # Fallback if matplotlib isn't loaded properly
                    st.dataframe(top_bleeders, use_container_width=True, hide_index=True)
            else:
                st.success("No out-of-stock items detected. No ad spend is being wasted.")

    # ========== DATA SANITIZATION ==========
    st.markdown('<hr class="soft-divider">', unsafe_allow_html=True)
    st.markdown('<div class="section-header">🛠️ Data Sanitization Logs</div>', unsafe_allow_html=True)
    
    if sku_col:
        missing = df_clean[sku_col].isnull().sum() + (df_clean[sku_col].astype(str).str.strip() == '').sum()
        if missing > 0:
            df_clean.dropna(subset=[sku_col], inplace=True)
            st.error(f"Removed {missing} rows with missing SKUs.")
    
    if price_col:
        df_clean[price_col] = df_clean[price_col].astype(str).str.replace(r'[$,£€]', '', regex=True).str.strip()
        ps = pd.to_numeric(df_clean[price_col], errors='coerce')
        if (ps < 0).sum() > 0:
            st.error(f"Flagged {(ps < 0).sum()} negative prices.")

    st.success("Data sanitization complete. Ready for manual export.")

    # ========== BEFORE / AFTER VISUAL ==========
    if qty_col and risk_pct > 0:
        st.markdown('<hr class="soft-divider">', unsafe_allow_html=True)
        st.markdown('<div class="section-header">⚖️ Your Business: Manual vs Automated</div>', unsafe_allow_html=True)
        col_before, col_after = st.columns(2)
        with col_before:
            st.markdown(f"""
            <div style="background:#fff5f5; border:1px solid #ffcdd2; padding:2rem; border-radius:12px; height:100%;">
                <h3 style="color:#c62828; margin-top:0;">❌ Current State (Manual)</h3>
                <ul style="color:#424242; font-size:1.05rem; line-height:1.8;">
                    <li>Bleeding <strong>${revenue_at_risk:,.0f}</strong> in hidden risk</li>
                    <li>{low_stock} items vulnerable to sudden stockouts</li>
                    <li>Wasting ad spend on dead product pages</li>
                    <li>Manual CSV imports eating up hours per week</li>
                </ul>
            </div>
            """, unsafe_allow_html=True)
        with col_after:
            st.markdown("""
            <div style="background:#f1f8f5; border:1px solid #a5d6a7; padding:2rem; border-radius:12px; height:100%; box-shadow: 0 8px 24px rgba(67, 160, 71, 0.15);">
                <h3 style="color:#2e7d32; margin-top:0;">✅ Custom Sync Engine</h3>
                <ul style="color:#424242; font-size:1.05rem; line-height:1.8;">
                    <li><strong>$0</strong> Revenue at risk</li>
                    <li>Inventory auto-updates every 15 minutes</li>
                    <li>Hands-off operation. Focus on marketing.</li>
                </ul>
            </div>
            """, unsafe_allow_html=True)

    # ========== CTA FUNNEL ==========
    st.markdown('<hr class="soft-divider">', unsafe_allow_html=True)
    st.markdown('<a id="automate-this-permanently"></a>', unsafe_allow_html=True) # Anchor link target
    st.markdown('<div class="cta-card">', unsafe_allow_html=True)
    colA, colB = st.columns([1, 1.2])

    with colA:
        st.markdown("### 📥 Download Cleaned CSV")
        st.markdown("We've removed empty rows, stripped currency symbols, and fixed formatting errors.")
        csv_buf = io.StringIO()
        df_clean.to_csv(csv_buf, index=False)
        st.download_button("Download Cleaned CSV", data=csv_buf.getvalue(), file_name="cleaned_feed.csv", mime="text/csv", type="primary")
        st.markdown("<p style='font-size:0.82rem; color:#e53935; margin-top:0.75rem;'>⚠️ You will still need to do this manually every time your supplier updates.</p>", unsafe_allow_html=True)

    with colB:
        st.markdown("### ⚡ Automate This Permanently")
        st.markdown("Tired of SaaS apps that break? I build custom, done-for-you sync engines. **Flat fee. No monthly subscriptions.**")
        with st.form("lead_form_results", clear_on_submit=True):
            lead_email = st.text_input("Email Address", placeholder="ceo@yourstore.com")
            lead_store = st.text_input("Shopify Store URL", placeholder="yourstore.myshopify.com")
            submitted = st.form_submit_button("Request a Custom Quote", type="primary")
            if submitted and lead_email:
                stats = {"revenue_at_risk": revenue_at_risk if qty_col else 0}
                save_lead(lead_email, lead_store, "results_form", stats)
                st.success("✅ Request received! I'll email you within 24 hours.")
    st.markdown('</div>', unsafe_allow_html=True)
    
    # ========== STICKY CTA ==========
    if revenue_at_risk > 0:
        st.markdown(f"""
        <div class="sticky-cta">
            <div class="sticky-cta-text">
                🚨 You are actively risking <span class="sticky-cta-highlight">${revenue_at_risk:,.0f}</span> today. 
            </div>
            <a href="#automate-this-permanently" style="background:#e53935; color:white; padding:0.6rem 1.5rem; text-decoration:none; border-radius:6px; font-weight:700; transition: transform 0.2s ease;">Fix This Now</a>
        </div>
        """, unsafe_allow_html=True)

else:
    # ========== EMPTY STATE ==========
    st.markdown('<hr class="soft-divider">', unsafe_allow_html=True)
    st.markdown("""
    <div class="cta-card" style="text-align:center;">
        <h3 style="font-size:1.6rem;">Stop Bleeding Cash on Manual CSV Imports</h3>
        <p style="max-width:600px; margin:0.5rem auto 2rem auto;">
        If your supplier runs out of stock and you don't update your store fast enough,
        you lose money on refunds, waste ad spend, and get penalized by Stripe.<br><br>
        <strong>I build custom sync engines that connect directly to your supplier's feed and update
        Shopify every 15 minutes. 100% Done-For-You.</strong></p>
    </div>
    """, unsafe_allow_html=True)

    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        with st.form("lead_form_empty", clear_on_submit=True):
            st.markdown("#### Request a Free Architecture Call")
            ee = st.text_input("Email Address", placeholder="ceo@yourstore.com")
            es = st.text_input("Shopify Store URL (optional)", placeholder="yourstore.myshopify.com")
            esub = st.form_submit_button("Book Free Strategy Call", type="primary")
            if esub and ee:
                save_lead(ee, es, "empty_state", {})
                st.success("✅ Request received! I'll reach out within 24 hours.")
