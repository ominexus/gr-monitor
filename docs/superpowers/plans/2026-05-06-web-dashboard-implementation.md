# ETF Monitor Web Dashboard Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a Streamlit-based web dashboard to visualize ETF alert history and performance from SQLite.

**Architecture:** A standalone Python script `dashboard.py` that connects to `monitor.db`. It uses Streamlit for the UI, Plotly for charts, and Pandas for data manipulation.

**Tech Stack:** Python, Streamlit, Plotly, Pandas, SQLite3

---

### Task 1: Project Setup & Database Connection

**Files:**
- Create: `dashboard.py`
- Modify: `requirements.txt` (if exists, or list dependencies)

- [ ] **Step 1: Install dependencies**

Run: `pip install streamlit plotly pandas`

- [ ] **Step 2: Create `dashboard.py` skeleton with DB connection**

```python
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
st.write(f"Loaded {len(df)} records.")
```

- [ ] **Step 3: Verify basic execution**

Run: `streamlit run dashboard.py`
Expected: A web page opens showing the title and the number of records loaded from `monitor.db`.

- [ ] **Step 4: Commit**

```bash
git add dashboard.py
git commit -m "chore: initial dashboard setup and db connection"
```

---

### Task 2: Overview Metrics & Interactive Table

**Files:**
- Modify: `dashboard.py`

- [ ] **Step 1: Implement Key Metrics**

```python
# Insert after load_data()
df['alert_date'] = pd.to_datetime(df['alert_date'])
today = datetime.now().strftime('%Y-%m-%d')
today_alerts = len(df[df['alert_date'].dt.strftime('%Y-%m-%d') == today])

col1, col2, col3 = st.columns(3)
col1.metric("Total Alerts", len(df))
col2.metric("Today's Alerts", today_alerts)
col3.metric("Markets", df['market'].nunique() if 'market' in df.columns else 0)
```

- [ ] **Step 2: Add Filters and Data Table**

```python
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
```

- [ ] **Step 3: Verify UI**

Run: `streamlit run dashboard.py`
Expected: Metrics at the top, sidebar filters working, and a data table displayed.

- [ ] **Step 4: Commit**

```bash
git add dashboard.py
git commit -m "feat: add overview metrics and interactive table with filters"
```

---

### Task 3: Alert Trend & RSI Distribution Charts

**Files:**
- Modify: `dashboard.py`

- [ ] **Step 1: Add Alert Trend Chart**

```python
st.subheader("Visual Analysis")
c1, col2 = st.columns(2)

with c1:
    st.write("#### Alert Trend")
    trend_df = df.groupby(df['alert_date'].dt.date).size().reset_index(name='count')
    fig_trend = px.line(trend_df, x='alert_date', y='count', title="Daily Alert Count")
    st.plotly_chart(fig_trend, use_container_width=True)

with col2:
    st.write("#### RSI Distribution")
    if 'rsi' in df.columns:
        fig_rsi = px.histogram(df, x='rsi', nbins=20, title="RSI Distribution at Alert")
        fig_rsi.add_vline(x=30, line_dash="dash", line_color="red", annotation_text="Oversold")
        fig_rsi.add_vline(x=70, line_dash="dash", line_color="green", annotation_text="Overbought")
        st.plotly_chart(fig_rsi, use_container_width=True)
```

- [ ] **Step 2: Verify Charts**

Run: `streamlit run dashboard.py`
Expected: Line chart for daily alerts and histogram for RSI values displayed side-by-side.

- [ ] **Step 3: Commit**

```bash
git add dashboard.py
git commit -m "feat: add alert trend and RSI distribution charts"
```

---

### Task 4: Performance Analysis (Backtest Integration)

**Files:**
- Modify: `dashboard.py`

- [ ] **Step 1: Implement simplified backtest logic for dashboard**

```python
import yfinance as yf

@st.cache_data(ttl=3600)
def get_avg_returns(data):
    # For a subset of recent data to keep it fast
    recent_df = data.sort_values(by='alert_date', ascending=False).head(20)
    returns = {1: [], 5: [], 20: []}
    
    for _, row in recent_df.iterrows():
        ticker_symbol = row['ticker']
        if row['market'] == 'KOR' and not ticker_symbol.endswith('.KS'):
            ticker_symbol = f"{ticker_symbol}.KS"
        
        try:
            hist = yf.Ticker(ticker_symbol).history(start=row['alert_date'], end=row['alert_date'] + timedelta(days=40))
            if len(hist) > 1:
                entry_price = row['price'] if row['price'] else hist.iloc[0]['Close']
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
    with st.spinner("Fetching historical data..."):
        avg_rets = get_avg_returns(df)
        perf_df = pd.DataFrame({
            'Period': ['T+1', 'T+5', 'T+20'],
            'Avg Return (%)': [avg_rets[1], avg_rets[5], avg_rets[20]]
        })
        fig_perf = px.bar(perf_df, x='Period', y='Avg Return (%)', color='Avg Return (%)', 
                         color_continuous_scale='RdYlGn', title="Average Returns after Alert")
        st.plotly_chart(fig_perf, use_container_width=True)
```

- [ ] **Step 2: Final Verification**

Run: `streamlit run dashboard.py`
Expected: All sections (Metrics, Filters, Table, Trends, RSI, Performance) working correctly.

- [ ] **Step 3: Commit & Cleanup**

```bash
git add dashboard.py
git commit -m "feat: add performance analysis bar chart"
```
