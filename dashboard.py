import streamlit as st
import pandas as pd
import sqlite3
import plotly.express as px
import yfinance as yf
from datetime import datetime, timedelta

# Page config
st.set_page_config(page_title="ETF Monitor", page_icon="📈", layout="wide")

# Custom CSS for Mobile Optimization
st.markdown("""
    <style>
    /* Reduce padding for mobile */
    .block-container {
        padding-top: 1rem;
        padding-bottom: 1rem;
        padding-left: 0.8rem;
        padding-right: 0.8rem;
    }
    /* Responsive metrics */
    [data-testid="stMetricValue"] {
        font-size: 1.5rem !important;
    }
    /* Force buttons to be full width on mobile */
    .stButton > button {
        width: 100%;
    }
    </style>
    """, unsafe_allow_html=True)

def get_connection():
    return sqlite3.connect("monitor.db")

@st.cache_data(ttl=300)  # Cache for 5 minutes
def load_data():
    conn = get_connection()
    try:
        df = pd.read_sql_query("SELECT * FROM history", conn)
        # Centralize alert_date conversion
        if 'alert_date' in df.columns:
            df['alert_date'] = pd.to_datetime(df['alert_date'])
        return df
    finally:
        conn.close()

st.title("📈 ETF Monitor")
df = load_data()

# --- Performance Summary Stats ---
def calculate_summary_stats(data):
    if data.empty:
        return 0, 0
    # 최근 50개 알림 데이터 기준 (너무 많으면 느림)
    recent = data.sort_values(by='alert_date', ascending=False).head(30)
    # T+5 수익률 기준 승률 계산 (실제론 get_avg_returns와 유사한 로직 필요)
    # 여기서는 간단히 표시하기 위해 예시 데이터를 사용하거나, 
    # 실제 연산이 필요하면 get_avg_returns 결과를 활용합니다.
    return len(recent), 0 # 임시

# Implement Key Metrics (Always 3 columns, but compact)
today = datetime.now().date()
today_alerts = len(df[df['alert_date'].dt.date == today]) if not df.empty else 0

m1, m2, m3 = st.columns(3)
m1.metric("Total alerts", len(df))
m2.metric("Today", today_alerts)
m3.metric("Markets", df['market'].nunique() if 'market' in df.columns else 0)

# Add Filters in an Expander for mobile space saving
with st.expander("🔍 Filters & Search", expanded=False):
    unique_markets = df['market'].unique() if 'market' in df.columns else []
    market_filter = st.multiselect("Market", options=unique_markets, default=list(unique_markets))
    rsi_range = st.slider("RSI Range", 0, 100, (0, 100))
    name_search = st.text_input("Ticker/Name Search")

filtered_df = df.copy()
if market_filter:
    filtered_df = filtered_df[filtered_df['market'].isin(market_filter)]
if rsi_range:
    filtered_df = filtered_df[(filtered_df['rsi'] >= rsi_range[0]) & (filtered_df['rsi'] <= rsi_range[1])]
if name_search:
    filtered_df = filtered_df[
        filtered_df['name'].str.contains(name_search, case=False, na=False) | 
        filtered_df['ticker'].str.contains(name_search, case=False, na=False)
    ]

st.subheader("Alert History")
# Display columns selection - Simplified for Mobile screen
display_cols = ['alert_date', 'ticker', 'name', 'price', 'rsi']
if 'macd_hist' in filtered_df.columns:
    display_cols += ['macd_hist']
if 'vol_ratio' in filtered_df.columns:
    display_cols += ['vol_ratio']

st.dataframe(
    filtered_df[display_cols].sort_values(by='alert_date', ascending=False), 
    use_container_width=True,
    hide_index=True
)

csv = filtered_df.to_csv(index=False).encode('utf-8-sig')
st.download_button("📥 Download CSV", data=csv, file_name="etf_alerts.csv", mime="text/csv", use_container_width=True)

st.subheader("Visual Analysis")
# Use tabs for charts on mobile to save vertical space
tab1, tab2 = st.tabs(["📈 Trend", "📊 RSI"])

with tab1:
    if not filtered_df.empty:
        trend_df = filtered_df.groupby(filtered_df['alert_date'].dt.date).size().reset_index(name='count')
        fig_trend = px.line(trend_df, x='alert_date', y='count', title="Daily Alerts")
        fig_trend.update_layout(margin=dict(l=10, r=10, t=30, b=10))
        st.plotly_chart(fig_trend, use_container_width=True)
    else:
        st.info("No data.")

with tab2:
    if 'rsi' in filtered_df.columns and not filtered_df.empty:
        fig_rsi = px.histogram(filtered_df, x='rsi', nbins=15, title="RSI Dist")
        fig_rsi.add_vline(x=30, line_dash="dash", line_color="red")
        fig_rsi.add_vline(x=70, line_dash="dash", line_color="green")
        fig_rsi.update_layout(margin=dict(l=10, r=10, t=30, b=10))
        st.plotly_chart(fig_rsi, use_container_width=True)
    else:
        st.info("No RSI data.")

@st.cache_data(ttl=3600)
def get_avg_returns(data):
    recent_df = data.sort_values(by='alert_date', ascending=False).head(20)
    returns = {1: [], 5: [], 20: []}
    for _, row in recent_df.iterrows():
        ticker_symbol = row['ticker']
        if row['market'] == 'KOR' and not (ticker_symbol.endswith('.KS') or ticker_symbol.endswith('.KQ')):
            ticker_symbol = f"{ticker_symbol}.KS"
        try:
            hist = yf.Ticker(ticker_symbol).history(start=row['alert_date'], end=row['alert_date'] + timedelta(days=40))
            if len(hist) > 1:
                entry_price = row['price'] if pd.notna(row['price']) else hist.iloc[0]['Close']
                for days in [1, 5, 20]:
                    if len(hist) > days:
                        ret = (hist.iloc[days]['Close'] - entry_price) / entry_price * 100
                        returns[days].append(ret)
        except: continue
    avg_rets = {k: sum(v)/len(v) if v else 0 for k, v in returns.items()}
    return avg_rets

st.divider()
st.subheader("Performance (Recent 20)")
if st.button("🚀 Run Performance Analysis"):
    if not df.empty:
        with st.spinner("Analyzing..."):
            avg_rets = get_avg_returns(df)
            perf_df = pd.DataFrame({
                'Period': ['T+1', 'T+5', 'T+20'],
                'Avg Return (%)': [avg_rets[1], avg_rets[5], avg_rets[20]]
            })
            fig_perf = px.bar(perf_df, x='Period', y='Avg Return (%)', color='Avg Return (%)', 
                             color_continuous_scale='RdYlGn')
            fig_perf.update_layout(margin=dict(l=10, r=10, t=30, b=10))
            st.plotly_chart(fig_perf, use_container_width=True)
    else:
        st.warning("No data.")
