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
