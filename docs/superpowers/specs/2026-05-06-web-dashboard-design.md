# ETF Monitor - Web Dashboard Design Spec

**Title:** SQLite-based ETF Alert Dashboard
**Status:** Approved
**Technology Stack:** Streamlit, Plotly, Pandas, SQLite3

## 1. Overview
Replace Google Sheets logging with a self-hosted web dashboard that visualizes data from `monitor.db`. The dashboard provides a comprehensive view of alert history, technical indicators (RSI), and strategy performance.

## 2. Architecture
- **Data Source:** `monitor.db` (SQLite)
- **Backend/Frontend:** Streamlit (Python-based reactive web framework)
- **Charts:** Plotly (for interactive line, bar, and histogram charts)

## 3. Key Features

### 3.1. Overview Metrics (Top Row)
- **Total Alerts:** Total number of records in the `history` table.
- **Today's Alerts:** Number of alerts triggered since midnight.
- **Avg. Return (T+5):** The average percentage return 5 days after an alert (queried from backtest logic).

### 3.2. Data Visualization
- **Alert Trend Chart:** A time-series line chart showing the daily count of alerts.
- **RSI Distribution:** A histogram showing the frequency of RSI values at the time of alerts (highlighting the 30 and 70 thresholds).
- **Performance Summary:** A bar chart showing average returns at T+1, T+3, T+5, T+10, T+20, and T+60 intervals.

### 3.3. Interactive History Table
- A searchable and filterable table (using `st.dataframe` or `st.data_editor`).
- Filters for **Market** (KOR/USA), **Date Range**, and **Stock Name**.
- Option to download the filtered view as a CSV.

## 4. Technical Details
- **Database Connection:** Use `sqlite3` to query the `history` table.
- **Integration:** The dashboard reads from the same `monitor.db` that `etf_monitor.py` writes to.
- **Auto-Refresh:** Set a periodic refresh interval (e.g., every 5 minutes) to stay up-to-date with new alerts.

## 5. Deployment
- The dashboard can be run locally via `streamlit run dashboard.py`.
- For remote access, it can be hosted on a cloud provider (e.g., Streamlit Cloud, AWS EC2, or a private server).

## 6. Success Criteria
- [ ] Successfully reads and displays all data from `monitor.db`.
- [ ] Charts update correctly when new data is added to the database.
- [ ] Interactive filters work without lagging or errors.
