import streamlit as st, requests, pandas as pd, time, os, re
from datetime import datetime, timedelta
from io import BytesIO
import plotly.graph_objects as go
import numpy as np
import concurrent.futures

# --- 1. ページ設定 ---
st.set_page_config(page_title="J-Quants 戦略アドバイザー (V13.2)", layout="wide")
st.title("🛡️ J-Quants 戦略アドバイザー (V13.2)")

# --- 2. 認証・通信設定 ---
API_KEY = st.secrets.get("JQUANTS_API_KEY", "").strip()
LINE_TOKEN = st.secrets.get("LINE_CHANNEL_ACCESS_TOKEN", "").strip()
LINE_USER_ID = st.secrets.get("LINE_USER_ID", "").strip()

headers = {"x-api-key": API_KEY}
BASE_URL = "https://api.jquants.com/v2"

def send_line_message(text):
    if not LINE_TOKEN or not LINE_USER_ID: return False
    url = "https://api.line.me/v2/bot/message/push"
    req_headers = {"Content-Type": "application/json", "Authorization": f"Bearer {LINE_TOKEN}"}
    payload = {"to": LINE_USER_ID, "messages": [{"type": "text", "text": text}]}
    try:
        res = requests.post(url, headers=req_headers, json=payload, timeout=10)
        return res.status_code == 200
    except: return False

# --- 3. 共通関数 ---
def clean_df(df):
    rename_cols = {'AdjustmentOpen': 'AdjO', 'AdjustmentHigh': 'AdjH', 'AdjustmentLow': 'AdjL', 'AdjustmentClose': 'AdjC', 'Open': 'AdjO', 'High': 'AdjH', 'Low': 'AdjL', 'Close': 'AdjC'}
    df = df.rename(columns=rename_cols)
    for c in ['AdjO', 'AdjH', 'AdjL', 'AdjC']:
        if c in df.columns: df[c] = pd.to_numeric(df[c], errors='coerce')
    if 'Date' in df.columns: df['Date'] = pd.to_datetime(df['Date']); df = df.sort_values('Date').reset_index(drop=True)
    return df

@st.cache_data(ttl=86400)
def load_master():
    try:
        req_headers = {'User-Agent': 'Mozilla/5.0'}
        res = requests.get("https://www.jpx.co.jp/markets/statistics-equities/misc/01.html", headers=req_headers, timeout=10)
        match = re.search(r'href="([^"]+data_j\.xls)"', res.text)
        if match:
            res2 = requests.get("https://www.jpx.co.jp" + match.group(1), headers=req_headers, timeout=15)
            df = pd.read_excel(BytesIO(res2.content), engine='xlrd')[['コード', '銘柄名', '33業種区分', '市場・商品区分']]
            df.columns = ['Code', 'CompanyName', 'Sector', 'Market']
            df['Code'] = df['Code'].astype(str) + "0"
            return df
    except: pass
    return pd.DataFrame()

@st.cache_data(ttl=86400)
def get_old_codes():
    base = datetime.utcnow() + timedelta(hours=9) - timedelta(days=365)
    for i in range(7):
        d = (base - timedelta(days=i)).strftime('%Y%m%d')
        for v in ["v2", "v1"]:
            try:
                r = requests.get(f"https://api.jquants.com/{v}/listed/info?date={d}", headers=headers, timeout=10)
                if r.status_code == 200 and r.json().get("info"): return pd.DataFrame(r.json()["info"])['Code'].astype(str).tolist()
            except: pass
    return []

@st.cache_data(ttl=3600)
def get_single_data(code, yrs=3):
    base = datetime.utcnow() + timedelta(hours=9)
    f_d, t_d = (base - timedelta(days=365*yrs)).strftime('%Y%m%d'), base.strftime('%Y%m%d')
    try:
        r = requests.get(f"{BASE_URL}/equities/bars/daily?code={code}&from={f_d}&to={t_d}", headers=headers, timeout=15)
        if r.status_code == 200: return r.json().get("data", [])
    except: pass
    return []

@st.cache_data(ttl=3600)
def get_hist_data():
    base = datetime.utcnow() + timedelta(hours=9)
    dates = []
    days = 0
    while len(dates) < 30:
        d = base - timedelta(days=days)
        if d.weekday() < 5: dates.append(d.strftime('%Y%m%d'))
        days += 1
    d_half = base - timedelta(days=180)
    while d_half.weekday() >= 5: d_half -= timedelta(days=1)
    dates.append(d_half.strftime('%Y%m%d'))
    d_year = base - timedelta(days=365)
    while d_year.weekday() >= 5: d_year -= timedelta(days=1)
    dates.append(d_year.strftime('%Y%m%d'))
    
    rows = []
    bar = st.progress(0, "最新の相場データを並列取得中 (神速モード)...")
    def fetch(d):
        try:
            r = requests.get(f"{BASE_URL}/equities/bars/daily?date={d}", headers=headers, timeout=10)
            time.sleep(0.1) 
            if r.status_code == 200: return r.json().get("data", [])
        except: pass
        return []
    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as exe:
        futs = {exe.submit(fetch, d): d for d in dates}
        comp = 0
        for f in concurrent.futures.as_completed(futs):
            res = f.result()
            if res: rows.extend(res)
            comp += 1
            bar.progress(comp/len(dates))
    bar.empty()
    return rows

def draw_chart(df, target_p):
    fig = go.Figure()
    fig.add_trace(go.Candlestick(x=df['Date'], open=df['AdjO'], high=df['AdjH'], low=df['AdjL'], close=df['AdjC'], name='株価', increasing_line_color='#ef5350', decreasing_line_color='#26a69a'))
    fig.add_trace(go.Scatter(x=df['Date'], y=[target_p]*len(df), mode='lines', name='目標(指定%押)', line=dict(color='#FFD700', width=2, dash='dash')))
    fig.update_layout(height=320, margin=dict(l=0, r=0, t=10, b=0), xaxis_rangeslider_visible=False, paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)', hovermode="x unified")
    st.plotly_chart(fig, use_container_width=True)

# --- 4. UI構築 ---
tab1, tab2 = st.tabs(["🚀 実戦（スクリーナー）", "🔬 訓練（一括バックテスト）"])
master_df = load_master()

with tab1:
    st.markdown("### 🌐 ボスの「鉄の掟」全銘柄スクリーニング")
    run_scan = st.button("🚀 最新データで全軍スキャン開始")
    
    st.sidebar.header("🔍 ピックアップルール")
    f1_min = st.sidebar.number_input("① 株価下限 (円)", value=200, step=100)
    f2_max30 = st.sidebar.number_input("② 1ヶ月暴騰上限(倍)", value=2.0, step=0.1)
    f3_drop = st.sidebar.number_input("③ 半年〜1年下落除外(%)", value=-30, step=5)
    f4_max_long = st.sidebar.number_input("④ 上げ切り除外(倍)", value=3.0, step=0.5)
    f5_ipo = st.sidebar.checkbox("⑤ IPO除外", value=True)
    f6_risk = st.sidebar.checkbox("⑥ 疑義注記銘柄除外", value=True)
    
    c1, c2 = st.sidebar.columns(2)
    f7_min14 = c1.number_input("⑦下限(倍)", value=1.3, step=0.1)
    f7_max14 = c2.number_input("⑦上限(倍)", value=2.0, step=0.1)

    st.sidebar.header("🎯 買いルール")
    push_r = st.sidebar.number_input("① 押し目(%)", value=50, step=5)
    limit_d = st.sidebar.number_input("② 買い期限(日)", value=4, step=1)

    if run_scan:
        raw = get_hist_data()
        if not raw: st.error("取得失敗")
        else:
            with st.spinner("全4000銘柄に鉄の掟を一括執行中..."):
                df = clean_df(pd.
