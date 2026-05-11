import streamlit as st
import pandas as pd
import sqlite3
import plotly.express as px
import yfinance as yf
from datetime import datetime, timedelta

# Page config
st.set_page_config(page_title="ETF Monitor Dashboard", layout="wide")

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

st.title("📈 ETF Monitor Dashboard")
df = load_data()

# Implement Key Metrics
today = datetime.now().date()
today_alerts = len(df[df['alert_date'].dt.date == today]) if not df.empty else 0

col1, col2, col3 = st.columns(3)
col1.metric("Total Alerts", len(df))
col2.metric("Today's Alerts", today_alerts)
col3.metric("Markets", df['market'].nunique() if 'market' in df.columns else 0)

# Add Filters and Data Table
st.sidebar.header("Filters")
unique_markets = df['market'].unique() if 'market' in df.columns else []
market_filter = st.sidebar.multiselect("Market", options=unique_markets, default=list(unique_markets))

# RSI Filter
rsi_range = st.sidebar.slider("RSI Range", 0, 100, (0, 100))

name_search = st.sidebar.text_input("Search Ticker/Name")

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
# Display columns selection
display_cols = ['alert_date', 'market', 'ticker', 'name', 'price', 'rsi']
if 'macd_hist' in filtered_df.columns:
    display_cols += ['macd_hist', 'macd_cross', 'ma_bullish']

st.dataframe(
    filtered_df[display_cols].sort_values(by='alert_date', ascending=False), 
    use_container_width=True
)

csv = filtered_df.to_csv(index=False).encode('utf-8-sig')
st.download_button("Download CSV", data=csv, file_name="etf_alerts.csv", mime="text/csv")

st.subheader("Visual Analysis")
c1, col2 = st.columns(2)

with c1:
    st.write("#### Alert Trend")
    if not filtered_df.empty:
        trend_df = filtered_df.groupby(filtered_df['alert_date'].dt.date).size().reset_index(name='count')
        fig_trend = px.line(trend_df, x='alert_date', y='count', title="Daily Alert Count")
        st.plotly_chart(fig_trend, use_container_width=True)
    else:
        st.info("No data available for trend analysis.")

with col2:
    st.write("#### RSI Distribution")
    if 'rsi' in filtered_df.columns and not filtered_df.empty:
        fig_rsi = px.histogram(filtered_df, x='rsi', nbins=20, title="RSI Distribution at Alert")
        fig_rsi.add_vline(x=30, line_dash="dash", line_color="red", annotation_text="Oversold")
        fig_rsi.add_vline(x=70, line_dash="dash", line_color="green", annotation_text="Overbought")
        st.plotly_chart(fig_rsi, use_container_width=True)
    else:
        st.info("No RSI data available.")

@st.cache_data(ttl=3600)
def get_avg_returns(data):
    # For a subset of recent data to keep it fast
    recent_df = data.sort_values(by='alert_date', ascending=False).head(20)
    returns = {1: [], 5: [], 20: []}
    
    for _, row in recent_df.iterrows():
        ticker_symbol = row['ticker']
        if row['market'] == 'KOR' and not (ticker_symbol.endswith('.KS') or ticker_symbol.endswith('.KQ')):
            ticker_symbol = f"{ticker_symbol}.KS"
        
        try:
            # 주말 고려 넉넉하게 40일.
            hist = yf.Ticker(ticker_symbol).history(start=row['alert_date'], end=row['alert_date'] + timedelta(days=40))
            if len(hist) > 1:
                # 알림 당시의 실제 가격이 DB에 있으면 사용, 아니면 T+0 종가 사용
                entry_price = row['price'] if pd.notna(row['price']) else hist.iloc[0]['Close']
                for days in [1, 5, 20]:
                    if len(hist) > days:
                        ret = (hist.iloc[days]['Close'] - entry_price) / entry_price * 100
                        returns[days].append(ret)
        except:
            continue
            
    avg_rets = {k: sum(v)/len(v) if v else 0 for k, v in returns.items()}
    return avg_rets

st.divider()
st.subheader("Performance Analysis (Recent 20 alerts)")
if st.button("Run Performance Analysis"):
    if not df.empty:
        with st.spinner("Fetching historical data..."):
            avg_rets = get_avg_returns(df)
            perf_df = pd.DataFrame({
                'Period': ['T+1', 'T+5', 'T+20'],
                'Avg Return (%)': [avg_rets[1], avg_rets[5], avg_rets[20]]
            })
            fig_perf = px.bar(perf_df, x='Period', y='Avg Return (%)', color='Avg Return (%)', 
                             color_continuous_scale='RdYlGn', title="Average Returns after Alert")
            st.plotly_chart(fig_perf, use_container_width=True)
    else:
        st.warning("No data available to analyze performance.")
