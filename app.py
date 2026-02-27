import streamlit as st
import requests
import pandas as pd
import time
import os
import re
from datetime import datetime, timedelta
from io import BytesIO
import plotly.graph_objects as go
import numpy as np

# --- 1. ページ設定 ---
st.set_page_config(page_title="J-Quants 戦略スクリーナー (V11.7)", layout="wide")
st.title("🛡️ J-Quants 戦略アドバイザー (V11.7)")

# --- 2. 認証情報 ---
API_KEY = st.secrets["JQUANTS_API_KEY"].strip()
headers = {"x-api-key": API_KEY}
BASE_URL = "https://api.jquants.com/v2"

# --- 3. 共通関数群 ---
def clean_dataframe(df):
    rename_cols = {
        'AdjustmentOpen': 'AdjO', 'AdjustmentHigh': 'AdjH',
        'AdjustmentLow': 'AdjL', 'AdjustmentClose': 'AdjC',
        'Open': 'AdjO', 'High': 'AdjH', 'Low': 'AdjL', 'Close': 'AdjC'
    }
    df = df.rename(columns=rename_cols)
    for col in ['AdjO', 'AdjH', 'AdjL', 'AdjC']:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors='coerce')
    if 'Date' in df.columns:
        df['Date'] = pd.to_datetime(df['Date'])
        df = df.sort_values('Date').reset_index(drop=True)
    return df

@st.cache_data(ttl=86400)
def load_brand_master():
    try:
        req_headers = {'User-Agent': 'Mozilla/5.0'}
        page_url = "https://www.jpx.co.jp/markets/statistics-equities/misc/01.html"
        page_res = requests.get(page_url, headers=req_headers, timeout=10)
        match = re.search(r'href="([^"]+data_j\.xls)"', page_res.text)
        if match:
            excel_url = "https://www.jpx.co.jp" + match.group(1)
            res = requests.get(excel_url, headers=req_headers, timeout=15)
            df = pd.read_excel(BytesIO(res.content), engine='xlrd')
            df = df[['コード', '銘柄名', '33業種区分', '市場・商品区分']]
            df.columns = ['Code', 'CompanyName', 'Sector', 'Market']
            df['Code'] = df['Code'].astype(str) + "0"
            return df
    except: pass
    return pd.DataFrame()

@st.cache_data(ttl=86400)
def get_old_codes():
    base_date = datetime.utcnow() + timedelta(hours=9) - timedelta(days=365)
    for i in range(7):
        target_date = (base_date - timedelta(days=i)).strftime('%Y%m%d')
        for version in ["v2", "v1"]:
            try:
                res = requests.get(f"https://api.jquants.com/{version}/listed/info?date={target_date}", headers=headers, timeout=10)
                if res.status_code == 200:
                    data = res.json().get("info", [])
                    if data: return pd.DataFrame(data)['Code'].astype(str).tolist()
            except: pass
    return []

@st.cache_data(ttl=3600)
def get_single_stock_data(code, years=3):
    base_date = datetime.utcnow() + timedelta(hours=9)
    from_date = (base_date - timedelta(days=365 * years)).strftime('%Y%m%d')
    to_date = base_date.strftime('%Y%m%d')
    url = f"{BASE_URL}/equities/bars/daily?code={code}&from={from_date}&to={to_date}"
    try:
        res = requests.get(url, headers=headers, timeout=15)
        if res.status_code == 200: return res.json().get("data", [])
    except: pass
    return []

@st.cache_data(ttl=3600)
def get_historical_data_for_screening():
    base_date = datetime.utcnow() + timedelta(hours=9)
    target_dates = []
    days_count = 0
    while len(target_dates) < 30:
        d = base_date - timedelta(days=days_count)
        if d.weekday() < 5: target_dates.append(d.strftime('%Y%m%d'))
        days_count += 1
    
    d_half = base_date - timedelta(days=180)
    while d_half.weekday() >= 5: d_half -= timedelta(days=1)
    target_dates.append(d_half.strftime('%Y%m%d'))
    
    d_year = base_date - timedelta(days=365)
    while d_year.weekday() >= 5: d_year -= timedelta(days=1)
    target_dates.append(d_year.strftime('%Y%m%d'))
    
    all_rows = []
    p_bar = st.progress(0, text="最新の相場データを取得中...")
    for i, d in enumerate(target_dates):
        url = f"{BASE_URL}/equities/bars/daily?date={d}"
        try:
            res = requests.get(url, headers=headers, timeout=10)
            if res.status_code == 200: all_rows.extend(res.json().get("data", []))
        except: pass
        p_bar.progress((i + 1) / len(target_dates))
        time.sleep(0.5)
    p_bar.empty()
    return all_rows

def draw_candlestick(df, target_price):
    fig = go.Figure()
    fig.add_trace(go.Candlestick(
        x=df['Date'], open=df['AdjO'], high=df['AdjH'], low=df['AdjL'], close=df['AdjC'],
        name='株価', increasing_line_color='#ef5350', decreasing_line_color='#26a69a'
    ))
    fig.add_trace(go.Scatter(
        x=df['Date'], y=[target_price]*len(df),
        mode='lines', name='買値目標(指定%押)', line=dict(color='#FFD700', width=2, dash='dash')
    ))
    fig.update_layout(
        height=320, margin=dict(l=0, r=0, t=10, b=0), xaxis_rangeslider_visible=False,
        paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)', hovermode="x unified"
    )
    st.plotly_chart(fig, use_container_width=True)

# --- 4. UI構築 ---
tab1, tab2 = st.tabs(["🚀 実戦（スクリーナー）", "🔬 訓練（一括バックテスト）"])
master_df = load_brand_master()

# ==========================================
# タブ1: 実戦（スクリーナー）
# ==========================================
with tab1:
    st.markdown("### 🌐 ボスの「鉄の掟」全銘柄スクリーニング")
    run_full_scan = st.button("🚀 最新データで全軍スキャン開始")
    
    st.sidebar.header("🔍 ピックアップルール (①〜⑦)")
    f1_min_price = st.sidebar.number_input("① 株価下限 (円)", value=200, step=100)
    f2_max_30d_ratio = st.sidebar.number_input("② 1ヶ月以内の暴騰上限 (倍)", value=2.0, step=0.1)
    f3_drop_rate = st.sidebar.number_input("③ 半年〜1年の下落除外 (基準%)", value=-30, step=5)
    f4_max_long_ratio = st.sidebar.number_input("④ 上げ切り除外 (過去からの上昇倍率)", value=3.0, step=0.5)
    f5_ipo = st.sidebar.checkbox("⑤ IPO除外 (上場1年未満)", value=True)
    f6_risk = st.sidebar.checkbox("⑥ 疑義注記銘柄を除外", value=True)
    
    st.sidebar.caption("⑦ 14日以内の初動暴騰条件")
    c_f7_1
