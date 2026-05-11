import streamlit as st
import pandas as pd
import sqlite3
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime, timedelta

# Page config
st.set_page_config(page_title="ETF Monitor Dashboard", layout="wide")

def get_connection():
    return sqlite3.connect("monitor.db")

def load_data():
    conn = get_connection()
    df = pd.read_sql_query("SELECT * FROM history", conn)
    conn.close()
    return df

st.title("📈 ETF Monitor Dashboard")
df = load_data()

# Implement Key Metrics
df['alert_date'] = pd.to_datetime(df['alert_date'])
today = datetime.now().strftime('%Y-%m-%d')
today_alerts = len(df[df['alert_date'].dt.strftime('%Y-%m-%d') == today])

col1, col2, col3 = st.columns(3)
col1.metric("Total Alerts", len(df))
col2.metric("Today's Alerts", today_alerts)
col3.metric("Markets", df['market'].nunique() if 'market' in df.columns else 0)

# Add Filters and Data Table
st.sidebar.header("Filters")
market_filter = st.sidebar.multiselect("Market", options=df['market'].unique() if 'market' in df.columns else [], default=df['market'].unique() if 'market' in df.columns else [])
name_search = st.sidebar.text_input("Search Ticker/Name")

filtered_df = df.copy()
if market_filter:
    filtered_df = filtered_df[filtered_df['market'].isin(market_filter)]
if name_search:
    filtered_df = filtered_df[filtered_df['name'].str.contains(name_search, case=False) | filtered_df['ticker'].str.contains(name_search, case=False)]

st.subheader("Alert History")
st.dataframe(filtered_df.sort_values(by='alert_date', ascending=False), use_container_width=True)

csv = filtered_df.to_csv(index=False).encode('utf-8-sig')
st.download_button("Download CSV", data=csv, file_name="etf_alerts.csv", mime="text/csv")

st.subheader("Visual Analysis")
c1, col2 = st.columns(2)

with c1:
    st.write("#### Alert Trend")
    trend_df = filtered_df.groupby(filtered_df['alert_date'].dt.date).size().reset_index(name='count')
    fig_trend = px.line(trend_df, x='alert_date', y='count', title="Daily Alert Count")
    st.plotly_chart(fig_trend, use_container_width=True)

with col2:
    st.write("#### RSI Distribution")
    if 'rsi' in filtered_df.columns:
        fig_rsi = px.histogram(filtered_df, x='rsi', nbins=20, title="RSI Distribution at Alert")
        fig_rsi.add_vline(x=30, line_dash="dash", line_color="red", annotation_text="Oversold")
        fig_rsi.add_vline(x=70, line_dash="dash", line_color="green", annotation_text="Overbought")
        st.plotly_chart(fig_rsi, use_container_width=True)
