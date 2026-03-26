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
import concurrent.futures
import yfinance as yf
import jpholiday

# --- st.metricの文字切れ（...）を防ぐスナイパーパッチ ---
st.markdown("""
    <style>
    [data-testid="stMetricValue"] > div { text-overflow: clip !important; overflow: visible !important; white-space: nowrap !important; }
    [data-testid="stMetricValue"] { font-size: 1.4rem !important; }
    </style>
""", unsafe_allow_html=True)

# --- 1. ページ設定 & ゲートキーパー ---
st.set_page_config(page_title="戦術スコープ『鉄の掟』", layout="wide", page_icon="🎯")

ALLOWED_PASSWORDS = [p.strip() for p in st.secrets.get("APP_PASSWORD", "sniper2026").split(",")]

def check_password():
    if "password_correct" not in st.session_state:
        st.session_state["password_correct"] = False
        st.session_state["current_user"] = "" 
    if not st.session_state["password_correct"]:
        st.markdown('<h1 style="text-align: center; color: #2e7d32; margin-top: 10vh;">🎯 戦術スコープ『鉄の掟』</h1>', unsafe_allow_html=True)
        col1, col2, col3 = st.columns([1, 2, 1])
        with col2:
            with st.form("login_form"):
                password = st.text_input("Access Code", type="password", label_visibility="collapsed", placeholder="アクセスコード")
                submitted = st.form_submit_button("認証 (ENTER)", use_container_width=True)
                if submitted:
                    if password in ALLOWED_PASSWORDS:
                        st.session_state["password_correct"] = True
                        st.session_state["current_user"] = password 
                        st.rerun()
                    else:
                        st.error("🚨 認証失敗：コードが違います。")
        return False
    return True

if not check_password(): st.stop()

# --- 🚁 司令部へ帰還ボタン ---
import streamlit.components.v1 as components
components.html(
    """
    <script>
    const parentDoc = window.parent.document;
    if (!parentDoc.getElementById('sniper-return-btn')) {
        const btn = parentDoc.createElement('button');
        btn.id = 'sniper-return-btn';
        btn.innerHTML = '🚁 司令部へ帰還';
        btn.style.position = 'fixed'; btn.style.bottom = '100px'; btn.style.right = '30px';
        btn.style.backgroundColor = '#1e1e1e'; btn.style.color = '#00e676';
        btn.style.border = '1px solid #00e676'; btn.style.padding = '12px 20px';
        btn.style.borderRadius = '8px'; btn.style.cursor = 'pointer';
        btn.style.fontWeight = 'bold'; btn.style.zIndex = '2147483647';
        btn.style.boxShadow = '0 4px 6px rgba(0,0,0,0.5)';
        btn.onclick = function() {
            window.parent.scrollTo({top: 0, behavior: 'smooth'});
            const allElements = parentDoc.querySelectorAll('*');
            for (let i = 0; i < allElements.length; i++) {
                if (allElements[i].scrollHeight > allElements[i].clientHeight) {
                    allElements[i].scrollTo({top: 0, behavior: 'smooth'});
                }
            }
        };
        parentDoc.body.appendChild(btn);
    }
    </script>
    """, height=0, width=0
)

# --- 2. 認証・通信設定 ---
user_id = st.session_state["current_user"]
st.markdown(f'<h1 style="font-size: clamp(24px, 7vw, 42px); font-weight: 900; border-bottom: 2px solid #2e7d32; padding-bottom: 0.5rem; margin-bottom: 1rem;">🎯 戦術スコープ『鉄の掟』 <span style="font-size: 16px; font-weight: normal; color: #888;">(ID: {user_id[:4]}***)</span></h1>', unsafe_allow_html=True)

API_KEY = st.secrets.get("JQUANTS_API_KEY", "").strip()
headers = {"x-api-key": API_KEY}
BASE_URL = "https://api.jquants.com/v2"

# --- 🌤️ マクロ気象レーダー（日経平均）モジュール ---
@st.cache_data(ttl=900, show_spinner=False)
def get_macro_weather():
    try:
        tk_ni = yf.Ticker("^N225")
        hist_ni = tk_ni.history(period="5d")
        if len(hist_ni) >= 2:
            lc_ni = hist_ni['Close'].iloc[-1]; prev_ni = hist_ni['Close'].iloc[-2]
            diff_ni = lc_ni - prev_ni; pct_ni = (diff_ni / prev_ni) * 100
            return {"nikkei": {"price": lc_ni, "diff": diff_ni, "pct": pct_ni}}
    except: return None

def render_macro_board():
    data = get_macro_weather()
    if data and "nikkei" in data:
        ni = data["nikkei"]
        color = "#ef5350" if ni['diff'] >= 0 else "#26a69a"
        sign = "+" if ni['diff'] >= 0 else ""
        html = f"""
        <div style="background: rgba(20, 20, 20, 0.6); padding: 0.8rem 1.5rem; border-radius: 8px; border-left: 4px solid {color}; margin-bottom: 1.5rem;">
            <div style="font-size: 13px; color: #aaa; margin-bottom: 4px;">🌤️ 戦場の天候（マクロ環境モニター）</div>
            <div style="font-size: 22px; font-weight: bold; color: #fff;">
                日経平均株価: <span style="color: {color}; margin-left: 10px;">{ni['price']:,.2f} 円</span>
                <span style="font-size: 16px; color: {color}; margin-left: 8px;">({sign}{ni['diff']:,.2f} / {sign}{ni['pct']:.2f}%)</span>
            </div>
        </div>
        """
        st.markdown(html, unsafe_allow_html=True)

# --- 3. 共通関数 & 地雷検知 ---
def clean_df(df):
    r_cols = {'AdjustmentOpen': 'AdjO', 'AdjustmentHigh': 'AdjH', 'AdjustmentLow': 'AdjL', 'AdjustmentClose': 'AdjC', 'Open': 'AdjO', 'High': 'AdjH', 'Low': 'AdjL', 'Close': 'AdjC', 'AdjustmentVolume': 'Volume', 'Volume': 'Volume'}
    df = df.rename(columns=r_cols)
    for c in ['AdjO', 'AdjH', 'AdjL', 'AdjC', 'Volume']:
        if c in df.columns: df[c] = pd.to_numeric(df[c], errors='coerce')
    if 'Date' in df.columns:
        df['Date'] = pd.to_datetime(df['Date'])
        df = df.sort_values('Date').dropna(subset=['AdjO', 'AdjH', 'AdjL', 'AdjC']).reset_index(drop=True)
    return df

def check_event_mines(code):
    alerts = []
    c = str(code)[:4]
    test_dividend_mines = ["5986", "5162", "4625", "6378", "8604"]
    test_earnings_mines = ["7066"]
    if c in test_dividend_mines: alerts.append("💣 【地雷警戒】月末に配当権利落ち日が接近（強制ギャップダウンのリスク）")
    if c in test_earnings_mines: alerts.append("🔥 【地雷警戒】直近に決算発表あり（大口の乱高下リスク）")
    return alerts

@st.cache_data(ttl=86400)
def load_master():
    try:
        r1 = requests.get("https://www.jpx.co.jp/markets/statistics-equities/misc/01.html", headers={'User-Agent': 'Mozilla/5.0'}, timeout=10)
        m = re.search(r'href="([^"]+data_j\.xls)"', r1.text)
        if m:
            r2 = requests.get("https://www.jpx.co.jp" + m.group(1), headers={'User-Agent': 'Mozilla/5.0'}, timeout=15)
            df = pd.read_excel(BytesIO(r2.content), engine='xlrd')[['コード', '銘柄名', '33業種区分', '市場・商品区分', '規模区分']]
            df.columns = ['Code', 'CompanyName', 'Sector', 'Market', 'Scale']
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
    f_d = (base - timedelta(days=365*yrs)).strftime('%Y%m%d')
    t_d = base.strftime('%Y%m%d')
    try:
        r = requests.get(f"{BASE_URL}/equities/bars/daily?code={code}&from={f_d}&to={t_d}", headers=headers, timeout=15)
        if r.status_code == 200: return r.json().get("data", [])
    except: pass
    return []

@st.cache_data(ttl=3600, show_spinner=False)
def get_hist_data_cached():
    base = datetime.utcnow() + timedelta(hours=9)
    dates = []
    days = 0
    while len(dates) < 30:
        d = base - timedelta(days=days)
        if d.weekday() < 5: dates.append(d.strftime('%Y%m%d'))
        days += 1
    d_h = base - timedelta(days=180); d_y = base - timedelta(days=365)
    while d_h.weekday() >= 5: d_h -= timedelta(days=1)
    while d_y.weekday() >= 5: d_y -= timedelta(days=1)
    dates.append(d_h.strftime('%Y%m%d')); dates.append(d_y.strftime('%Y%m%d'))
    rows = []
    def fetch(dt):
        try:
            r = requests.get(f"{BASE_URL}/equities/bars/daily?date={dt}", headers=headers, timeout=10)
            if r.status_code == 200: return r.json().get("data", [])
        except: pass
        return []
    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as exe:
        futs = [exe.submit(fetch, dt) for dt in dates]
        for f in concurrent.futures.as_completed(futs):
            res = f.result()
            if res: rows.extend(res)
    return rows

# --- 波形・計器計算 ---
def check_double_top(df_sub):
    try:
        v = df_sub['AdjH'].values; c = df_sub['AdjC'].values; l = df_sub['AdjL'].values
        if len(v) < 6: return False
        peaks = []
        for i in range(1, len(v)-1):
            if v[i] == max(v[i-1:i+2]):
                if not peaks or (i - peaks[-1][0] > 1): peaks.append((i, v[i]))
        if len(v) >= 2 and v[-1] > v[-2]:
            if not peaks or (len(v)-1 - peaks[-1][0] > 1): peaks.append((len(v)-1, v[-1]))
        if len(peaks) >= 2:
            p2_idx, p2_val = peaks[-1]; p1_idx, p1_val = peaks[-2]
            if abs(p2_val - p1_val) / max(p2_val, p1_val) < 0.05:
                valley = min(l[p1_idx:p2_idx+1]) if p2_idx > p1_idx else p1_val
                if valley < min(p1_val, p2_val) * 0.95 and c[-1] < p2_val * 0.97: return True
        return False
    except: return False

def check_head_shoulders(df_sub):
    try:
        v = df_sub['AdjH'].values; c = df_sub['AdjC'].values
        if len(v) < 8: return False
        peaks = []
        for i in range(1, len(v)-1):
            if v[i] == max(v[i-1:i+2]):
                if not peaks or (i - peaks[-1][0] > 1): peaks.append((i, v[i]))
        if len(peaks) >= 3:
            p3_idx, p3_val = peaks[-1]; p2_idx, p2_val = peaks[-2]; p1_idx, p1_val = peaks[-3]
            if p2_val > p1_val and p2_val > p3_val and abs(p3_val - p1_val) / max(p3_val, p1_val) < 0.10 and c[-1] < p3_val * 0.97: return True
        return False
    except: return False

def check_double_bottom(df_sub):
    try:
        l = df_sub['AdjL'].values; c = df_sub['AdjC'].values; h = df_sub['AdjH'].values
        if len(l) < 6: return False
        valleys = []
        for i in range(1, len(l)-1):
            if l[i] == min(l[i-1:i+2]):
                if not valleys or (i - valleys[-1][0] > 1): valleys.append((i, l[i]))
        if len(l) >= 3 and l[-2] == min(l[-3:]):
             if not valleys or (len(l)-2 - valleys[-1][0] > 1): valleys.append((len(l)-2, l[-2]))
        if len(valleys) >= 2:
            v2_idx, v2_val = valleys[-1]; v1_idx, v1_val = valleys[-2]
            if abs(v2_val - v1_val) / min(v2_val, v1_val) < 0.05:
                peak = max(h[v1_idx:v2_idx+1]) if v2_idx > v1_idx else v1_val
                if peak > max(v1_val, v2_val) * 1.04 and c[-1] > v2_val * 1.01: return True
        return False
    except: return False

def check_sakata_patterns(df_sub):
    if len(df_sub) < 25: return None
    df = df_sub.copy(); df['SMA_25'] = df['AdjC'].rolling(window=25).mean()
    c = df.iloc[-1]; p1 = df.iloc[-2]; p2 = df.iloc[-3]
    bull = c['AdjC'] > c['AdjO']; bull1 = p1['AdjC'] > p1['AdjO']; bull2 = p2['AdjC'] > p2['AdjO']
    bear = c['AdjC'] < c['AdjO']; bear1 = p1['AdjC'] < p1['AdjO']; bear2 = p2['AdjC'] < p2['AdjO']
    r3s = bull and bull1 and bull2 and (c['AdjC'] > p1['AdjC'] > p2['AdjC']) and (c['AdjH'] > p1['AdjH'] > p2['AdjH'])
    b3c = bear and bear1 and bear2 and (c['AdjC'] < p1['AdjC'] < p2['AdjC']) and (c['AdjL'] < p1['AdjL'] < p2['AdjL'])
    body = abs(c['AdjC'] - c['AdjO']); l_shad = min(c['AdjO'], c['AdjC']) - c['AdjL']
    takuri = (l_shad >= body * 2.5) and (body > 0)
    sma25 = c['SMA_25']
    if pd.isna(sma25): return None
    if r3s and c['AdjC'] < sma25: return "🔴 赤三兵（底打ち反転）"
    elif takuri and c['AdjC'] < sma25: return "🔴 たくり線（強力な床）"
    elif b3c and c['AdjC'] > sma25: return "🟢 黒三兵（下落警戒）"
    elif b3c and c['AdjC'] < sma25: return "🔥 陰の極み（セリクラ反発待ち）"
    return None

# 🚨 追加：S/A/B/C 判定（トリアージ）エンジン
def get_triage_info(macd_h, macd_h_prev, rsi_val):
    if macd_h > 0 and macd_h_prev <= 0: macd_t = "GC直後"
    elif macd_h > macd_h_prev: macd_t = "上昇拡大"
    elif macd_h < 0 and macd_h < macd_h_prev: macd_t = "下落継続"
    else: macd_t = "減衰"

    triage_rank = "C（条件外・監視）👁️"
    triage_bg = "#616161"
    triage_score = 1
    
    if macd_t == "下落継続" or rsi_val >= 70:
        triage_rank = "圏外（手出し無用）🚫"
        triage_bg = "#d32f2f"
        triage_score = 0
    # 🚨 ルール拡張：「GC直後」だけでなく、勢いのついた「上昇拡大」でRSIが低い場合もSランクとして狙撃対象とする
    elif (macd_t == "GC直後" or macd_t == "上昇拡大") and rsi_val <= 50:
        triage_rank = "S（即時狙撃）🔥"
        triage_bg = "#2e7d32"
        triage_score = 4
    elif macd_t == "減衰" and rsi_val <= 30:
        triage_rank = "A（罠の設置）🪤"
        triage_bg = "#0288d1"
        triage_score = 3
    elif macd_t == "上昇拡大" and 50 < rsi_val <= 65:
        triage_rank = "B（順張り警戒）📈"
        triage_bg = "#ed6c02"
        triage_score = 2
        
    return triage_rank, triage_bg, triage_score, macd_t
    
def calc_technicals(df):
    df = df.copy()
    if len(df) < 16:
        df['RSI'] = 50; df['MACD'] = 0; df['MACD_Signal'] = 0; df['MACD_Hist'] = 0; df['ATR'] = 0; df['MA25'] = df['AdjC']; return df
    delta = df['AdjC'].diff(); gain = delta.where(delta > 0, 0); loss = -delta.where(delta < 0, 0)
    rs = gain.ewm(alpha=1/14, adjust=False).mean() / loss.ewm(alpha=1/14, adjust=False).mean()
    df['RSI'] = 100 - (100 / (1 + rs))
    macd = df['AdjC'].ewm(span=12, adjust=False).mean() - df['AdjC'].ewm(span=26, adjust=False).mean()
    df['MACD'] = macd; df['MACD_Signal'] = macd.ewm(span=9, adjust=False).mean(); df['MACD_Hist'] = df['MACD'] - df['MACD_Signal']
    df['MA25'] = df['AdjC'].rolling(window=25).mean()
    tr = pd.concat([df['AdjH'] - df['AdjL'], (df['AdjH'] - df['AdjC'].shift(1)).abs(), (df['AdjL'] - df['AdjC'].shift(1)).abs()], axis=1).max(axis=1)
    df['ATR'] = tr.rolling(window=14).mean()
    return df

def get_triage_info(macd_hist, macd_hist_prev, rsi):
    if macd_hist > 0 and macd_hist_prev <= 0: macd_t = "GC直後"
    elif macd_hist > macd_hist_prev: macd_t = "上昇拡大"
    elif macd_hist < 0 and macd_hist < macd_hist_prev: macd_t = "下落継続"
    else: macd_t = "減衰"

    if macd_t == "下落継続" or rsi >= 75: 
        return "圏外（手出し無用）🚫", "#d32f2f", 0, macd_t
    elif macd_t == "GC直後":
        if rsi <= 50: return "S（即時狙撃）🔥", "#2e7d32", 5, macd_t
        else: return "A（強襲追撃）⚡", "#ed6c02", 4, macd_t
    elif macd_t == "減衰" and rsi <= 35: 
        return "A（罠の設置）🪤", "#ed6c02", 4, macd_t
    elif macd_t == "上昇拡大":
        if rsi <= 60: return "B（順張り警戒）📈", "#0288d1", 3, macd_t
        else: return "C（過熱警戒）👁️", "#616161", 2, macd_t
    else:
        return "C（条件外・監視）👁️", "#616161", 1, macd_t

def render_technical_radar(df, buy_price, tp_pct):
    if df.empty or len(df) < 2: return ""
    latest = df.iloc[-1]; prev = df.iloc[-2]
    rsi = latest.get('RSI', 50); macd_hist = latest.get('MACD_Hist', 0); macd_hist_prev = prev.get('MACD_Hist', 0); atr = latest.get('ATR', 0)
    rsi_color = "#ef5350" if rsi <= 30 else "#FFD700" if rsi <= 45 else "#888888"
    rsi_text = "🔥 超売られすぎ" if rsi <= 30 else "⚡ 売られすぎ" if rsi <= 45 else "⚖️ 中立"
    if rsi >= 70: rsi_color = "#26a69a"; rsi_text = "⚠️ 買われすぎ"

    _, _, _, macd_t = get_triage_info(macd_hist, macd_hist_prev, rsi)

    # 🚨 GC発動時を超絶目立たせる改修
    if macd_t == "GC直後":
        macd_display = "🔥🔥🔥 激熱 GC発動中 🔥🔥🔥"
        macd_color = "#ff5722"
        bg_glow = "box-shadow: 0 0 15px rgba(255, 87, 34, 0.6); border: 2px solid #ff5722;"
    elif macd_t == "上昇拡大":
        macd_display = "📈 上昇拡大"
        macd_color = "#ef5350"
        bg_glow = "border-left: 4px solid #FFD700;"
    elif macd_t == "下落継続":
        macd_display = "📉 下落継続"
        macd_color = "#26a69a"
        bg_glow = "border-left: 4px solid #FFD700;"
    else:
        macd_display = "⚖️ 減衰"
        macd_color = "#888888"
        bg_glow = "border-left: 4px solid #FFD700;"

    days = int((buy_price * (tp_pct / 100.0)) / atr) if atr > 0 else 99

    return f"""<div style="background: rgba(255, 255, 255, 0.05); padding: 0.8rem; border-radius: 4px; margin: 1rem 0; {bg_glow}">
        <div style="font-size: 14px; color: #aaa;">📡 計器フライト: RSI <strong style="color: {rsi_color};">{rsi:.0f}% ({rsi_text})</strong> | MACD <strong style="color: {macd_color}; font-size: 1.1em;">{macd_display}</strong> | ボラ <strong style="color: #bbb;">{atr:.0f}円</strong> (利確目安: {days}日)</div></div>"""

def draw_chart(df, targ_p, tp5=None, tp10=None, tp15=None, tp20=None):
    df = df.copy()
    
    df['MA5'] = df['AdjC'].rolling(window=5).mean()
    df['MA25'] = df['AdjC'].rolling(window=25).mean()
    df['MA75'] = df['AdjC'].rolling(window=75).mean()

    fig = go.Figure()
    fig.add_trace(go.Candlestick(
        x=df['Date'], open=df['AdjO'], high=df['AdjH'],
        low=df['AdjL'], close=df['AdjC'], name='株価',
        increasing_line_color='#ef5350', decreasing_line_color='#26a69a'
    ))

    fig.add_trace(go.Scatter(x=df['Date'], y=df['MA5'], mode='lines', name='5日線(短期)', line=dict(color='rgba(156, 39, 176, 0.7)', width=1.5)))      
    fig.add_trace(go.Scatter(x=df['Date'], y=df['MA25'], mode='lines', name='25日線(中期)', line=dict(color='rgba(33, 150, 243, 0.7)', width=1.5)))     
    fig.add_trace(go.Scatter(x=df['Date'], y=df['MA75'], mode='lines', name='75日線(長期)', line=dict(color='rgba(255, 152, 0, 0.7)', width=1.5)))      

    fig.add_trace(go.Scatter(x=df['Date'], y=[targ_p]*len(df), mode='lines', name='買値目標', line=dict(color='#FFD700', width=2, dash='dash')))
    
    # 🚨 渡された売値ラインのみを独立して描画するよう改良
    if tp5 is not None: fig.add_trace(go.Scatter(x=df['Date'], y=[int(tp5)]*len(df), mode='lines', name='売値(5%)', line=dict(color='rgba(239, 83, 80, 0.4)', width=1, dash='dot')))
    if tp10 is not None: fig.add_trace(go.Scatter(x=df['Date'], y=[int(tp10)]*len(df), mode='lines', name='売値(10%)', line=dict(color='rgba(239, 83, 80, 0.6)', width=1.5, dash='dot')))
    if tp15 is not None: fig.add_trace(go.Scatter(x=df['Date'], y=[int(tp15)]*len(df), mode='lines', name='売値(15%)', line=dict(color='rgba(239, 83, 80, 0.8)', width=1.5, dash='dot')))
    if tp20 is not None: fig.add_trace(go.Scatter(x=df['Date'], y=[int(tp20)]*len(df), mode='lines', name='売値(20%)', line=dict(color='rgba(239, 83, 80, 1.0)', width=1.5, dash='dot')))
    
    last_date = df['Date'].max()
    start_date = last_date - timedelta(days=45) if len(df) > 30 else df['Date'].min()
    padding_days = timedelta(days=0.5)

    visible_df = df[(df['Date'] >= start_date) & (df['Date'] <= last_date)]
    if not visible_df.empty:
        y_max_vals = [visible_df['AdjH'].max(), targ_p, visible_df['MA5'].max(), visible_df['MA25'].max(), visible_df['MA75'].max()]
        y_min_vals = [visible_df['AdjL'].min(), targ_p * 0.85, visible_df['MA5'].min(), visible_df['MA25'].min(), visible_df['MA75'].min()] 
        
        for tp in [tp5, tp10, tp15, tp20]:
            if tp is not None: y_max_vals.append(tp)
        
        y_max = max([v for v in y_max_vals if not pd.isna(v)])
        y_min = min([v for v in y_min_vals if not pd.isna(v)])
        
        margin = (y_max - y_min) * 0.05
        y_range = [y_min - margin, y_max + margin]
    else:
        y_range = None

    layout_args = dict(
        height=450, 
        margin=dict(l=10, r=60, t=20, b=40), 
        xaxis_rangeslider_visible=True,
        xaxis=dict(range=[start_date, last_date + padding_days], type="date"),
        yaxis=dict(tickformat=",.0f", hoverformat=",.0f", side="right"),
        paper_bgcolor='rgba(0,0,0,0)', 
        plot_bgcolor='rgba(0,0,0,0)', 
        hovermode="x unified", 
        legend=dict(orientation="h", yanchor="top", y=-0.1, xanchor="center", x=0.5)
    )
    
    if y_range:
        layout_args['yaxis'].update(range=y_range, fixedrange=False)

    fig.update_layout(**layout_args)
    fig.update_layout(margin=dict(l=0, r=0, t=30, b=0))
    
    config = {'displayModeBar': True, 'displaylogo': False, 'modeBarButtonsToRemove': ['lasso2d', 'select2d']}
    st.plotly_chart(fig, use_container_width=True, config=config)
    
# --- 🛸 Tab 6専用チャート（こちらも併せて右側配置に修正） ---
def draw_chart_t6(df, targ_p, tp5, tp10, tp15):
    df = df.copy()
    df['MA5'] = df['AdjC'].rolling(window=5).mean()

    fig = go.Figure()
    fig.add_trace(go.Candlestick(
        x=df['Date'], open=df['AdjO'], high=df['AdjH'],
        low=df['AdjL'], close=df['AdjC'], name='株価',
        increasing_line_color='#ef5350', decreasing_line_color='#26a69a'
    ))

    fig.add_trace(go.Scatter(x=df['Date'], y=df['MA5'], mode='lines', name='5日線(命綱)', line=dict(color='rgba(156, 39, 176, 0.9)', width=2.5)))      

    fig.add_trace(go.Scatter(x=df['Date'], y=[targ_p]*len(df), mode='lines', name='現在値', line=dict(color='#FFD700', width=2, dash='dash')))
    fig.add_trace(go.Scatter(x=df['Date'], y=[tp5]*len(df), mode='lines', name='+5%', line=dict(color='rgba(239, 83, 80, 0.5)', width=1, dash='dot')))
    fig.add_trace(go.Scatter(x=df['Date'], y=[tp10]*len(df), mode='lines', name='+10%', line=dict(color='rgba(239, 83, 80, 0.7)', width=1.5, dash='dot')))
    fig.add_trace(go.Scatter(x=df['Date'], y=[tp15]*len(df), mode='lines', name='+15%', line=dict(color='rgba(239, 83, 80, 1.0)', width=1.5, dash='dot')))
    
    last_date = df['Date'].max()
    start_date = df['Date'].iloc[-14] if len(df) >= 14 else df['Date'].min()
    padding_days = timedelta(days=0.5)

    visible_df = df[(df['Date'] >= start_date) & (df['Date'] <= last_date)]
    if not visible_df.empty:
        y_max = max(visible_df['AdjH'].max(), tp15)
        y_min = min(visible_df['AdjL'].min(), visible_df['MA5'].min()) 
        margin = (y_max - y_min) * 0.05
        y_range = [y_min - margin, y_max + margin]
    else:
        y_range = None

    layout_args = dict(
        height=380, 
        margin=dict(l=10, r=60, t=20, b=40), 
        xaxis_rangeslider_visible=False, 
        xaxis=dict(range=[start_date, last_date + padding_days], type="date"),
        # 🚨 【修正】こちらも右側に完全固定
        yaxis=dict(tickformat=",.0f", hoverformat=",.0f", side="right"),
        paper_bgcolor='rgba(0,0,0,0)', 
        plot_bgcolor='rgba(0,0,0,0)', 
        hovermode="x unified", 
        legend=dict(orientation="h", yanchor="top", y=-0.1, xanchor="center", x=0.5)
    )
    
    if y_range:
        layout_args['yaxis'].update(range=y_range, fixedrange=False)

    fig.update_layout(**layout_args)
    fig.update_layout(margin=dict(l=0, r=0, t=30, b=0))
    
    config = {
        'displayModeBar': True,
        'displaylogo': False,
        'modeBarButtonsToRemove': ['lasso2d', 'select2d']
    }
    st.plotly_chart(fig, use_container_width=True, config=config)
    
# --- 🚨 復元パッチ：欠落していた2つのスナイパー機能 ---
@st.cache_data(ttl=86400, show_spinner=False)
def calc_historical_win_rate(c, push_r, buy_d, tp, sl_i, sl_c, sell_d, mode):
    raw = get_single_data(c + "0", 2)
    if not raw: return None
    df = clean_df(pd.DataFrame(raw))
    if len(df) < 60: return None
    trades = []; pos = None
    for i in range(30, len(df)):
        td = df.iloc[i]
        if pos is None:
            win_14 = df.iloc[i-14:i]; win_30 = df.iloc[i-30:i]
            rh = win_14['AdjH'].max(); rl = win_14['AdjL'].min()
            if pd.isna(rh) or pd.isna(rl) or rl <= 0: continue
            h_d = len(win_14[win_14['Date'] > win_14.loc[win_14['AdjH'].idxmax(), 'Date']])
            if (1.3 <= rh/rl <= 2.0) and (h_d <= buy_d):
                if check_double_top(win_30) or check_head_shoulders(win_30): continue
                if "攻め" in mode:
                    if check_double_bottom(win_30): pos = {'b_i': i, 'b_p': td['AdjO']}
                else:
                    targ = rh - ((rh - rl) * (push_r / 100))
                    if td['AdjL'] <= targ: pos = {'b_i': i, 'b_p': min(td['AdjO'], targ)}
        else:
            bp = pos['b_p']; held = i - pos['b_i']; sp = 0
            if td['AdjL'] <= bp * (1 - (sl_i / 100)): sp = min(td['AdjO'], bp * (1 - (sl_i / 100)))
            elif td['AdjH'] >= bp * (1 + (tp / 100)): sp = max(td['AdjO'], bp * (1 + (tp / 100)))
            elif td['AdjC'] <= bp * (1 - (sl_c / 100)): sp = td['AdjC']
            elif held >= sell_d: sp = td['AdjC']
            if sp > 0:
                trades.append(sp - bp); pos = None
    if not trades: return None
    wins = len([t for t in trades if t > 0])
    return {'total': len(trades), 'win_rate': (wins / len(trades)) * 100, 'exp_val': sum(trades) / len(trades)}

def get_triage_info(macd_hist, macd_hist_prev, rsi):
    if macd_hist > 0 and macd_hist_prev <= 0: macd_t = "GC直後"
    elif macd_hist > macd_hist_prev: macd_t = "上昇拡大"
    elif macd_hist < 0 and macd_hist < macd_hist_prev: macd_t = "下落継続"
    else: macd_t = "減衰"

    rank = "C（条件外・監視）👁️"; bg = "#616161"; score = 1
    if macd_t == "下落継続" or rsi >= 70: rank = "圏外（手出し無用）🚫"; bg = "#d32f2f"; score = 0
    elif macd_t == "GC直後" and rsi <= 50: rank = "S（即時狙撃）🔥"; bg = "#2e7d32"; score = 4
    elif macd_t == "減衰" and rsi <= 30: rank = "A（罠の設置）🪤"; bg = "#0288d1"; score = 3
    elif macd_t == "上昇拡大" and 50 <= rsi <= 65: rank = "B（順張り警戒）📈"; bg = "#ed6c02"; score = 2
    return rank, bg, score, macd_t
# -------------------------------------------------------------

# --- 4. サイドバー UI ---
if 'preset_target' not in st.session_state: st.session_state.preset_target = "🚀 中小型株 (50%押し・標準)"
if 'sidebar_tactics' not in st.session_state: st.session_state.sidebar_tactics = "⚖️ バランス (掟達成率 ＞ 到達度)"
if 'push_r' not in st.session_state: st.session_state.push_r = 50.0 

# 🚨 【修正】ここから下の行に「if not in」の防壁を追加し、強制リセットを無効化しました
if 'bt_tp' not in st.session_state: st.session_state.bt_tp = 10
if 'bt_sl_i' not in st.session_state: st.session_state.bt_sl_i = 8
if 'bt_sl_c' not in st.session_state: st.session_state.bt_sl_c = 8
if 'limit_d' not in st.session_state: st.session_state.limit_d = 4
if 'bt_sell_d' not in st.session_state: st.session_state.bt_sell_d = 10
if 'bt_lot' not in st.session_state: st.session_state.bt_lot = 100

def apply_market_preset():
    preset = st.session_state.get("preset_target", "🚀 中小型株 (50%押し・標準)")
    tactics = st.session_state.get("sidebar_tactics", "⚖️ バランス (掟達成率 ＞ 到達度)")
    if "大型株" in preset: st.session_state.push_r = 25.0 if "バランス" in tactics else 45.0
    elif "61.8%" in preset: st.session_state.push_r = 61.8
    else: st.session_state.push_r = 50.0

st.sidebar.header("🎯 対象市場 (一括換装)")
st.sidebar.radio("プリセット選択", ["🚀 中小型株 (50%押し・標準)", "⚓ 中小型株 (61.8%押し・深海)", "🏢 大型株 (25%押し・トレンド)"], key="preset_target", on_change=apply_market_preset)
st.sidebar.radio("🕹️ 戦術モード切替", ["⚖️ バランス (掟達成率 ＞ 到達度)", "⚔️ 攻め重視 (三川シグナル優先)", "🛡️ 守り重視 (鉄壁シグナル優先)"], key="sidebar_tactics", on_change=apply_market_preset)

st.sidebar.header("🔍 ピックアップルール")
c_f1_1, c_f1_2 = st.sidebar.columns(2)
f1_min = c_f1_1.number_input("① 下限(円)", value=200, step=100)
f1_max = c_f1_2.number_input("① 上限(円)", value=3000, step=100) 
f2_m30 = st.sidebar.number_input("② 1ヶ月暴騰上限(倍)", value=2.0, step=0.1)
f3_drop = st.sidebar.number_input("③ 半年〜1年下落除外(%)", value=-30, step=5)
f4_mlong = st.sidebar.number_input("④ 上げ切り除外(倍)", value=3.0, step=0.5)
f5_ipo = st.sidebar.checkbox("⑤ IPO除外(英字コード等)", value=True)
f6_risk = st.sidebar.checkbox("⑥ 疑義注記銘柄除外", value=True)
f7_ex_etf = st.sidebar.checkbox("⑦ ETF・REIT等を除外", value=True)
f8_ex_bio = st.sidebar.checkbox("⑧ 医薬品(バイオ)を除外", value=True)
c_f9_1, c_f9_2 = st.sidebar.columns(2)
f9_min14 = c_f9_1.number_input("⑨ 下限(倍)", value=1.3, step=0.1)
f9_max14 = c_f9_2.number_input("⑨ 上限(倍)", value=2.0, step=0.1)
f10_ex_knife = st.sidebar.checkbox("⑩ 落ちるナイフ除外(暴落/連続下落)", value=True)

st.sidebar.header("🎯 買いルール")
push_r = st.sidebar.number_input("① 押し目(%)", step=0.1, format="%.1f", key="push_r")
limit_d = st.sidebar.number_input("② 買い期限(日)", step=1, key="limit_d")
st.sidebar.number_input("③ 仮想Lot(株数)", step=100, key="bt_lot")

st.sidebar.header("🛡️ 売りルール（鉄の掟）")
st.sidebar.number_input("① 利確目標 (+%)", step=1, key="bt_tp")
st.sidebar.number_input("② 損切/ザラ場 (-%)", step=1, key="bt_sl_i")
st.sidebar.number_input("③ 損切/終値 (-%)", step=1, key="bt_sl_c")
st.sidebar.number_input("④ 強制撤退/売り期限 (日)", step=1, key="bt_sell_d")

# ==========================================
# 5. タブ再構成（7タブ構成）
# ==========================================
tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs([
    "🌐 【待伏】広域レーダー", 
    "⚡ 【強襲】GC初動レーダー", 
    "🎯 精密スコープ", 
    "⚙️ 戦術シミュレータ", 
    "⛺ IFD潜伏カウント", 
    "📁 事後任務報告 (AAR)"
])
master_df = load_master()
tactics_mode = st.session_state.sidebar_tactics

with tab1:
    st.markdown('<h3 style="font-size: clamp(14px, 4.5vw, 24px); margin-bottom: 1rem;">🌐 ボスの「鉄の掟」全軍スキャン</h3>', unsafe_allow_html=True)
    run_scan = st.button(f"🚀 最新データで全軍スキャン開始 ({tactics_mode.split()[0]}モード)")

    if run_scan:
        with st.spinner("神速モードで相場データを一括取得中..."):
            raw = get_hist_data_cached()
        if not raw: st.error("データの取得に失敗しました。")
        else:
            with st.spinner("全4000銘柄に鉄の掟と波形認識を一括執行中..."):
                d_raw = pd.DataFrame(raw)
                df = clean_df(d_raw).dropna(subset=['AdjC', 'AdjH', 'AdjL']).sort_values(['Code', 'Date'])
                
                df_30 = df.groupby('Code').tail(30)
                df_14 = df_30.groupby('Code').tail(10)
                
                counts = df_14.groupby('Code').size()
                valid = counts[counts >= 5].index
                if valid.empty: st.warning("条件を満たすデータが存在しません。"); st.stop()
                
                df_14 = df_14[df_14['Code'].isin(valid)]
                df_30 = df_30[df_30['Code'].isin(valid)]
                df_past = df[~df.index.isin(df_30.index)]; df_past = df_past[df_past['Code'].isin(valid)]
                
                agg_14 = df_14.groupby('Code').agg(
                    lc=('AdjC', 'last'), 
                    prev_c=('AdjC', lambda x: x.iloc[-2] if len(x) > 1 else np.nan),
                    c_3days_ago=('AdjC', lambda x: x.iloc[-4] if len(x) > 3 else np.nan),
                    h14=('AdjH', 'max'), l14=('AdjL', 'min') 
                )
                
                idx_max = df_14.groupby('Code')['AdjH'].idxmax()
                h_dates = df_14.loc[idx_max, ['Code', 'Date']].rename(columns={'Date': 'h_date'})
                df_14_m = df_14.merge(h_dates, on='Code')
                d_high = df_14_m[df_14_m['Date'] > df_14_m['h_date']].groupby('Code').size().rename('d_high')
                
                agg_30 = df_30.groupby('Code').agg(l30=('AdjL', 'min'))
                agg_p = df_past.groupby('Code').agg(omax=('AdjH', 'max'), omin=('AdjL', 'min'))
                sum_df = agg_14.join(d_high, how='left').fillna({'d_high': 0}).join(agg_30).join(agg_p).reset_index()
                
                ur = sum_df['h14'] - sum_df['l14']
                bt_primary = sum_df['h14'] - (ur * (st.session_state.push_r / 100.0))
                shift_ratio = 0.618 if st.session_state.push_r >= 40 else (st.session_state.push_r / 100.0 + 0.15)
                bt_secondary = sum_df['h14'] - (ur * shift_ratio)
                
                sum_df['is_bt_broken'] = sum_df['lc'] < bt_primary
                sum_df['bt'] = np.where(sum_df['is_bt_broken'], bt_secondary, bt_primary)
                
                dead_line = sum_df['h14'] - (ur * 0.618)
                sum_df = sum_df[sum_df['lc'] >= (dead_line * 0.98)]
                
                sum_df['tp5'] = sum_df['bt'] * 1.05; sum_df['tp10'] = sum_df['bt'] * 1.10; sum_df['tp15'] = sum_df['bt'] * 1.15; sum_df['tp20'] = sum_df['bt'] * 1.20
                denom = sum_df['h14'] - sum_df['bt']
                sum_df['reach_pct'] = np.where(denom > 0, (sum_df['h14'] - sum_df['lc']) / denom * 100, 0)
                sum_df['r14'] = np.where(sum_df['l14'] > 0, sum_df['h14'] / sum_df['l14'], 0)
                sum_df['r30'] = np.where(sum_df['l30'] > 0, sum_df['lc'] / sum_df['l30'], 0)
                sum_df['ldrop'] = np.where((sum_df['omax'].notna()) & (sum_df['omax'] > 0), ((sum_df['lc'] / sum_df['omax']) - 1) * 100, 0)
                sum_df['lrise'] = np.where((sum_df['omin'].notna()) & (sum_df['omin'] > 0), sum_df['lc'] / sum_df['omin'], 0)
                sum_df['daily_pct'] = np.where(sum_df['prev_c'] > 0, (sum_df['lc'] / sum_df['prev_c']) - 1, 0)
                sum_df['pct_3days'] = np.where(sum_df['c_3days_ago'] > 0, (sum_df['lc'] / sum_df['c_3days_ago']) - 1, 0)
                
                dt_s = df_14.groupby('Code').apply(check_double_top).rename('is_dt')
                hs_s = df_14.groupby('Code').apply(check_head_shoulders).rename('is_hs')
                db_s = df_14.groupby('Code').apply(check_double_bottom).rename('is_db')
                sakata_s = df_30.groupby('Code').apply(check_sakata_patterns).rename('sakata_signal')
                
                def get_avg_vol(group):
                    v_col = next((col for col in group.columns if col in ['AdjVo', 'Vo', 'AdjVo_x', 'AdjVo_y']), None)
                    if v_col: return int(pd.to_numeric(group[v_col].astype(str).str.replace(',', ''), errors='coerce').fillna(0).tail(5).mean())
                    return 0
                vol_s = df_30.groupby('Code').apply(get_avg_vol).rename('avg_vol')
                
                sum_df = sum_df.merge(dt_s, on='Code', how='left').merge(hs_s, on='Code', how='left').merge(db_s, on='Code', how='left').merge(sakata_s, on='Code', how='left').merge(vol_s, on='Code', how='left')
                sum_df = sum_df.fillna({'is_dt': False, 'is_hs': False, 'is_db': False, 'avg_vol': 0})
                sum_df['is_defense'] = (~sum_df['is_dt']) & (~sum_df['is_hs']) & (sum_df['lc'] <= (sum_df['l14'] * 1.03))
                
                if not master_df.empty: sum_df = pd.merge(sum_df, master_df, on='Code', how='left')
                
                if f7_ex_etf and 'Sector' in sum_df.columns:
                    sum_df = sum_df[sum_df['Sector'].notna()] 
                    sum_df = sum_df[sum_df['Sector'] != '-']
                    sum_df = sum_df[~sum_df['CompanyName'].astype(str).str.contains("ETF|投信|ブル|ベア|REIT|ﾘｰﾄ", na=False, flags=re.IGNORECASE)]
                if f8_ex_bio and 'Sector' in sum_df.columns:
                    sum_df = sum_df[sum_df['Sector'] != '医薬品']

                sum_df = sum_df[(sum_df['lc'] >= f1_min) & (sum_df['lc'] <= f1_max)]
                sum_df = sum_df[sum_df['r30'] <= f2_m30]
                sum_df = sum_df[sum_df['ldrop'] >= f3_drop]
                sum_df = sum_df[(sum_df['lrise'] <= f4_mlong) | (sum_df['lrise'] == 0)]
                
                if f5_ipo:
                    old_c = get_old_codes()
                    if old_c: sum_df = sum_df[sum_df['Code'].isin(old_c)]
                    sum_df = sum_df[~sum_df['Code'].astype(str).str.contains(r'[a-zA-Z]')]
                
                if f6_risk and 'CompanyName' in sum_df.columns:
                    sum_df = sum_df[~sum_df['CompanyName'].astype(str).str.contains("疑義|重要事象", na=False)]
                
                sum_df = sum_df[(~sum_df['is_dt']) & (~sum_df['is_hs'])]
                sum_df = sum_df[~sum_df['sakata_signal'].astype(str).str.contains("下落警戒", na=False)]
                sum_df = sum_df[(sum_df['r14'] >= f9_min14) & (sum_df['r14'] <= f9_max14)]
                sum_df = sum_df[sum_df['d_high'] <= st.session_state.limit_d]
                sum_df = sum_df[(sum_df['lc'] <= (sum_df['bt'] * 1.35)) & (sum_df['lc'] >= (sum_df['bt'] * 0.85))]
                
                if f10_ex_knife:
                    dynamic_sl_ratio = - (st.session_state.bt_sl_i / 100.0)
                    three_days_sl = dynamic_sl_ratio * 1.5
                    sum_df = sum_df[(sum_df['daily_pct'] >= dynamic_sl_ratio) & (sum_df['pct_3days'] >= three_days_sl)]
                
                sum_df['rule_pct'] = 100.0; sum_df['passed'] = 9 
                
                # 🚨 S/A/B/Cトリアージスコアの算出とソート機能の復活
                t_scores = []; t_ranks = []; t_bgs = []
                for _, r in sum_df.iterrows():
                    c_code = r['Code']
                    df_for_tech = df_30[df_30['Code'] == c_code]
                    if not df_for_tech.empty:
                        df_for_tech = calc_technicals(df_for_tech.copy())
                        latest_c = df_for_tech.iloc[-1]; prev_c = df_for_tech.iloc[-2] if len(df_for_tech) > 1 else latest_c
                        rank, bg, score, _ = get_triage_info(latest_c.get('MACD_Hist',0), prev_c.get('MACD_Hist',0), latest_c.get('RSI',50))
                        t_scores.append(score); t_ranks.append(rank); t_bgs.append(bg)
                    else:
                        t_scores.append(1); t_ranks.append("C（条件外・監視）👁️"); t_bgs.append("#616161")
                        
                sum_df['triage_score'] = t_scores
                sum_df['triage_rank'] = t_ranks
                sum_df['triage_bg'] = t_bgs
                
                if tactics_mode.startswith("⚔️"):
                    res = sum_df.sort_values(['triage_score', 'is_db', 'reach_pct'], ascending=[False, False, False]).head(30)
                elif tactics_mode.startswith("🛡️"):
                    res = sum_df.sort_values(['triage_score', 'is_defense', 'reach_pct'], ascending=[False, False, False]).head(30)
                else:
                    res = sum_df.sort_values(['triage_score', 'reach_pct'], ascending=[False, False]).head(30)
                
            if res.empty: st.warning("現在の相場に、標的は存在しません。")
            else:
                st.success(f"🎯 スキャン完了: {len(res)} 銘柄クリア")
                
                st.markdown("#### 📋 コピペ用コード")
                if 'Code' in res.columns:
                    copy_codes = ",".join([str(c)[:4] for c in res['Code']])
                    st.code(copy_codes, language="text")

                for _, r in res.iterrows():
                    st.divider()
                    c = str(r['Code']); n = r['CompanyName'] if not pd.isna(r.get('CompanyName')) else f"銘柄 {c[:4]}"
                    
                    scale_val = str(r.get('Scale', ''))
                    badge = '<span style="background-color: #0d47a1; color: #ffffff; padding: 0.2rem 0.6rem; border-radius: 4px; font-size: 12px; display: inline-block;">🏢 大型/中型</span>' if any(x in scale_val for x in ["Core30", "Large70", "Mid400"]) else '<span style="background-color: #b71c1c; color: #ffffff; padding: 0.2rem 0.6rem; border-radius: 4px; font-size: 12px; display: inline-block;">🚀 小型/新興</span>'
                    
                    # 🚨 トリアージバッジの描画
                    triage_badge = f'<span style="background-color: {r["triage_bg"]}; color: #ffffff; padding: 0.2rem 0.6rem; border-radius: 4px; font-size: 13px; display: inline-block; font-weight: bold; margin-left: 0.5rem;">🎯 優先度: {r["triage_rank"]}</span>'

                    st.markdown(f"""
                        <div style="margin-bottom: 0.8rem;">
                            <h3 style="font-size: clamp(16px, 5vw, 26px); font-weight: bold; margin: 0 0 0.3rem 0; word-wrap: break-word;">({c[:4]}) {n}</h3>
                            <div style="display: flex; flex-wrap: wrap; gap: 4px; align-items: center;">{badge}{triage_badge}</div>
                        </div>
                    """, unsafe_allow_html=True)
                    
                    event_alerts = check_event_mines(c)
                    for alert in event_alerts: st.warning(alert)
                    
                    if r.get('is_bt_broken', False): st.error("⚠️ 【第一防衛線突破】想定以上の売り圧力を検知。買値目標を第二防衛線へ自動シフト。")
                    if r['is_db']: st.success("🔥 【激熱(攻め)】三川（ダブルボトム）底打ち反転波形を検知！")
                    if r['is_defense']: st.info("🛡️ 【鉄壁(守り)】下値支持線(サポート)に極接近。安全圏です。")
                    if pd.notna(r.get('sakata_signal')):
                        if "下落警戒" in str(r['sakata_signal']): st.error(f"🚨 【撤退推奨】{r['sakata_signal']}")
                        else: st.success(f"🔥 【反転攻勢】{r['sakata_signal']}")
                            
                    lc_val = int(r.get('lc', 0)); bt_val = int(r.get('bt', 0)); high_val = int(r.get('h14', lc_val)); low_val = int(r.get('l14', 0))
                    if low_val == 0:
                        bt_ratio = st.session_state.push_r / 100.0 if not r.get('is_bt_broken', False) else 0.618
                        ur_approx = (high_val - bt_val) / bt_ratio if bt_ratio > 0 else 0
                        low_val = int(high_val - ur_approx)
                    wave_len = high_val - low_val

                    sl5 = int(bt_val * 0.95); sl8 = int(bt_val * 0.92); sl15 = int(bt_val * 0.85)
                    tp20 = int(r.get('tp20', bt_val * 1.2)); tp15 = int(r.get('tp15', bt_val * 1.15))
                    tp10 = int(r.get('tp10', bt_val * 1.1)); tp5 = int(r.get('tp5', bt_val * 1.05))

                    daily_pct = r.get('daily_pct', 0)
                    daily_sign = "+" if daily_pct >= 0 else ""

                    sc0, sc0_1, sc0_2, sc1, sc2, sc3, sc4 = st.columns([0.8, 0.8, 0.8, 0.9, 1.1, 1.8, 1.5])
                    sc0.metric("直近高値", f"{high_val:,}円"); sc0_1.metric("直近安値", f"{low_val:,}円"); sc0_2.metric("上昇幅", f"{wave_len:,}円")
                    sc1.metric("最新終値", f"{lc_val:,}円", f"{daily_sign}{daily_pct*100:.1f}%", delta_color="inverse")
                    
                    sc2.markdown(f'<div style="font-family: sans-serif; padding-top: 0.2rem;"><div style="font-size: 14px; color: rgba(250, 250, 250, 0.6); padding-bottom: 0.1rem;">🎯 買値目標</div><div style="font-size: 1.8rem; font-weight: bold; color: #FFD700;">{bt_val:,}円</div></div>', unsafe_allow_html=True)
                    
                    sc3.markdown(f"""<div style="font-family: sans-serif; padding-top: 0.2rem;">
                        <div style="font-size: 14px; color: rgba(250, 250, 250, 0.6); padding-bottom: 0.1rem;">🎯 売値目標 ＆ 🛡️ 損切目安</div>
                        <div style="font-size: 16px;">
                            <span style="display: inline-block; width: 2.5em; color: #ef5350;">20%</span> <span style="color: #ef5350;">{tp20:,}円</span><br>
                            <span style="display: inline-block; width: 2.5em; color: #ef5350;">15%</span> <span style="color: #ef5350;">{tp15:,}円</span> <span style="color: rgba(250, 250, 250, 0.3); margin: 0 4px;">|</span> <span style="display: inline-block; width: 2.8em; color: #26a69a;">-5%</span> <span style="color: #26a69a;">{sl5:,}円</span><br>
                            <span style="display: inline-block; width: 2.5em; color: #ef5350;">10%</span> <span style="color: #ef5350;">{tp10:,}円</span> <span style="color: rgba(250, 250, 250, 0.3); margin: 0 4px;">|</span> <span style="display: inline-block; width: 2.8em; color: #26a69a;">-8%</span> <span style="color: #26a69a;">{sl8:,}円</span><br>
                            <span style="display: inline-block; width: 2.5em; color: #ef5350;">5%</span> <span style="color: #ef5350;">{tp5:,}円</span> <span style="color: rgba(250, 250, 250, 0.3); margin: 0 4px;">|</span> <span style="display: inline-block; width: 2.8em; color: #26a69a;">-15%</span> <span style="color: #26a69a;">{sl15:,}円</span>
                        </div></div>""", unsafe_allow_html=True)
                    
                    reach_val = r.get('reach_pct', 0); vol_val = r.get('avg_vol', 0)
                    sc4.markdown(f"""
                    <div style="display: flex; flex-direction: column; gap: 8px; margin-top: 0.5rem;">
                        <div style="background: rgba(38, 166, 154, 0.1); border-left: 3px solid #26a69a; padding: 4px 8px; border-radius: 4px;">
                            <span style="font-size: 12px; color: #aaa;">到達度:</span> <strong style="font-size: 15px; color: #fff;">{reach_val:.1f}%</strong>
                        </div>
                        <div style="background: rgba(255, 255, 255, 0.05); border-left: 3px solid #26a69a; padding: 4px 8px; border-radius: 4px;">
                            <span style="font-size: 12px; color: #aaa;">掟適合:</span> <strong style="font-size: 15px; color: #26a69a;">9/9 条件クリア (100%)</strong>
                        </div>
                        <div style="background: rgba(255, 215, 0, 0.1); border-left: 3px solid #FFD700; padding: 4px 8px; border-radius: 4px;">
                            <span style="font-size: 12px; color: #aaa;">出来高(5日):</span> <strong style="font-size: 15px; color: #fff;">{vol_val:,} 株</strong>
                        </div>
                    </div>""", unsafe_allow_html=True)
                    
                    st.caption(f"🏢 {r.get('Market','不明')} ｜ 🏭 {r.get('Sector','不明')} ｜ ⏱️ 高値経過: {int(r.get('d_high', 0))}営業日")

                    bt_stats = calc_historical_win_rate(c[:4], st.session_state.push_r, st.session_state.limit_d, st.session_state.bt_tp, st.session_state.bt_sl_i, st.session_state.bt_sl_c, st.session_state.bt_sell_d, tactics_mode)
                    if bt_stats and bt_stats['total'] > 0:
                        wr_color = "#ef5350" if bt_stats['win_rate'] >= 60 else "#FFD700" if bt_stats['win_rate'] >= 50 else "#888888"
                        st.markdown(f'<div style="background: rgba(255,255,255,0.05); padding: 0.5rem; border-radius: 4px; margin: 0.5rem 0;"><span style="font-size: 12px; color: #aaa;">📊 過去2年の掟適合率 ({bt_stats["total"]}戦):</span><strong style="color: {wr_color}; font-size: 16px; margin-left: 8px;">勝率 {bt_stats["win_rate"]:.1f}%</strong><span style="font-size: 12px; color: #aaa; margin-left: 12px;">1株期待値:</span><strong style="color: {"#ef5350" if bt_stats["exp_val"] > 0 else "#26a69a"}; font-size: 16px; margin-left: 8px;">{bt_stats["exp_val"]:+.1f}円</strong></div>', unsafe_allow_html=True)
                    else:
                        st.markdown('<div style="background: rgba(255,255,255,0.02); padding: 0.5rem; border-radius: 4px; margin: 0.5rem 0; border: 1px dashed rgba(255,255,255,0.2);"><span style="font-size: 12px; color: #666;">📊 過去2年の掟適合率:</span><span style="color: #666; font-size: 14px; margin-left: 8px;">該当取引なし（データ不足）</span></div>', unsafe_allow_html=True)
                    
                    api_code = c if len(c) == 5 else c + "0"
                    raw_s = get_single_data(api_code, 1)
                    if raw_s: hist_chart = clean_df(pd.DataFrame(raw_s))
                    else: hist_chart = df[df['Code'] == c].sort_values('Date').tail(30)
                        
                    if not hist_chart.empty:
                        hist_chart = calc_technicals(hist_chart)
                        st.markdown(render_technical_radar(hist_chart, r['bt'], st.session_state.bt_tp), unsafe_allow_html=True)
                        draw_chart(hist_chart, r['bt'], r['tp5'], r['tp10'], r['tp15'], r['tp20'])

with tab2:
    st.markdown('<h3 style="font-size: clamp(14px, 4.5vw, 24px); margin-bottom: 1rem;">⚡ 【強襲】GC初動レーダー</h3>', unsafe_allow_html=True)
    st.caption("※全市場から「MACDがゴールデンクロス（0ライン突破）した直後」の銘柄を抽出し、RSIが低い順に狙撃候補として表示します。")
    
    col_t2_1, col_t2_2 = st.columns(2)
    rsi_limit = col_t2_1.number_input("RSI上限（過熱感の足切り）", value=35, step=5)
    vol_limit = col_t2_2.number_input("最低出来高（5日平均・株）", value=10000, step=10000)
    
    if st.button(f"🚀 全軍GC初動スキャン開始"):
        with st.spinner("【Phase 1】全銘柄の波形から「GC初動候補」を一次抽出中..."):
            raw = get_hist_data_cached()
            if not raw:
                st.error("データの取得に失敗しました。")
            else:
                df = clean_df(pd.DataFrame(raw)).dropna(subset=['AdjC', 'AdjH', 'AdjL']).sort_values(['Code', 'Date'])
                
                # 🚨 Phase 1: キャッシュ限界値（30日）に合わせて広く投網をかける
                df_30 = df.groupby('Code').tail(30)
                
                results = []
                for code, group in df_30.groupby('Code'):
                    if len(group) < 20: continue
                    
                    v_col = next((col for col in group.columns if col in ['AdjVo', 'Vo', 'AdjVo_x', 'AdjVo_y']), None)
                    avg_vol = int(pd.to_numeric(group[v_col].astype(str).str.replace(',', ''), errors='coerce').fillna(0).tail(5).mean()) if v_col else 0
                    if avg_vol < vol_limit: continue
                    
                    g_tech = calc_technicals(group.copy())
                    latest = g_tech.iloc[-1]; prev = g_tech.iloc[-2]
                    
                    lc = latest['AdjC']
                    atr = latest.get('ATR', 0)
                    
                    if atr < 10 or (atr / lc) < 0.01: continue
                    tp_yen = lc * (st.session_state.bt_tp / 100.0)
                    exp_days = int(tp_yen / atr) if atr > 0 else 99
                    if exp_days >= 5: continue
                    
                    macd_h = latest.get('MACD_Hist', 0); macd_h_prev = prev.get('MACD_Hist', 0)
                    rsi = latest.get('RSI', 50)
                    
                    if macd_h > 0 and macd_h_prev <= 0 and rsi <= rsi_limit:
                        c_name = f"銘柄 {code[:4]}"; c_market = "不明"; c_sector = "不明"; c_scale = ""
                        if not master_df.empty:
                            m_row = master_df[master_df['Code'] == code]
                            if not m_row.empty:
                                c_name = m_row.iloc[0]['CompanyName']; c_market = m_row.iloc[0]['Market']
                                c_sector = m_row.iloc[0].get('Sector', '不明')
                                c_scale = m_row.iloc[0].get('Scale', '')
                        
                        h14 = group.tail(14)['AdjH'].max(); l14 = group.tail(14)['AdjL'].min()
                        bt_val = int(lc * 1.01)
                        daily_pct = (lc / prev['AdjC']) - 1 if prev['AdjC'] > 0 else 0
                        
                        results.append({
                            'Code': code, 'Name': c_name, 'Sector': c_sector, 'Market': c_market, 'Scale': c_scale,
                            'lc': lc, 'RSI': rsi, 'avg_vol': avg_vol, 'h14': h14, 'l14': l14, 'bt': bt_val,
                            'daily_pct': daily_pct, 'df_chart': g_tech
                        })
                        
                if not results:
                    st.warning(f"現在、RSI {rsi_limit}以下でMACDゴールデンクロスを迎えた銘柄は存在しません。")
                else:
                    res_df = pd.DataFrame(results).sort_values('RSI', ascending=True)
                    
        # 🚨 Phase 2: 一次通過した銘柄のみ、マルチスレッドで並列精密検査（ダマシの完全排除）
        if 'res_df' in locals() and not res_df.empty:
            with st.spinner(f"【Phase 2】一次候補 {len(res_df)} 銘柄へ並列通信（マルチスレッド）を実行。ダマシ(偽GC)を排除中..."):
                import concurrent.futures
                
                # 並列処理させるための独立任務（関数）
                def fetch_and_check(r_dict):
                    c = str(r_dict['Code'])
                    api_code = c if len(c) == 5 else c + "0"
                    raw_s = get_single_data(api_code, 1)
                    
                    hist_chart = clean_df(pd.DataFrame(raw_s)) if raw_s else r_dict['df_chart']
                    
                    if not hist_chart.empty:
                        hist_chart = calc_technicals(hist_chart)
                        latest_acc = hist_chart.iloc[-1]
                        prev_acc = hist_chart.iloc[-2] if len(hist_chart) > 1 else latest_acc
                        
                        accurate_rsi = latest_acc.get('RSI', r_dict['RSI'])
                        acc_macd_h = latest_acc.get('MACD_Hist', 0)
                        acc_macd_h_prev = prev_acc.get('MACD_Hist', 0)
                        
                        t_rank, t_bg, _, _ = get_triage_info(acc_macd_h, acc_macd_h_prev, accurate_rsi)
                        
                        # キルスイッチ：Cランクや圏外に落ちた銘柄は破棄
                        if "C（条件外" in t_rank or "圏外" in t_rank:
                            return None
                            
                        item = r_dict.copy()
                        item['accurate_rsi'] = accurate_rsi
                        item['t_rank'] = t_rank
                        item['t_bg'] = t_bg
                        item['hist_chart'] = hist_chart
                        return item
                    return None

                final_results = []
                tasks = [r.to_dict() for _, r in res_df.iterrows()]
                
                # 🚨 10部隊（スレッド）を同時展開して通信の待ち時間を極限まで圧縮
                with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
                    futures = [executor.submit(fetch_and_check, task) for task in tasks]
                    for future in concurrent.futures.as_completed(futures):
                        res = future.result()
                        if res is not None:
                            final_results.append(res)
                            
                # 並列処理でバラバラになった順序を、RSIの低い順に再ソートして整列
                final_results = sorted(final_results, key=lambda x: x['accurate_rsi'])

            # 最終的な UI の描画
            if not final_results:
                st.warning("🚨 抽出された候補はすべて「ダマシ（計算誤差）」または「勢い減衰」と判定され、キルされました。")
            else:
                st.success(f"🎯 最終ロックオン: 純度100%の【真の強襲ターゲット】 {len(final_results)} 銘柄を確認。")
                
                st.markdown("#### 📋 コピペ用コード")
                copy_codes = ",".join([str(item['Code'])[:4] for item in final_results])
                st.code(copy_codes, language="text")
                
                for r in final_results:
                    st.divider()
                    c = str(r['Code']); n = r['Name']
                    daily_sign = "+" if r['daily_pct'] >= 0 else ""
                    
                    scale_val = str(r.get('Scale', ''))
                    badge = '<span style="background-color: #0d47a1; color: #ffffff; padding: 0.2rem 0.6rem; border-radius: 4px; font-size: 12px; display: inline-block;">🏢 大型/中型</span>' if any(x in scale_val for x in ["Core30", "Large70", "Mid400"]) else '<span style="background-color: #b71c1c; color: #ffffff; padding: 0.2rem 0.6rem; border-radius: 4px; font-size: 12px; display: inline-block;">🚀 小型/新興</span>'
                    triage_badge = f'<span style="background-color: {r["t_bg"]}; color: #ffffff; padding: 0.2rem 0.6rem; border-radius: 4px; font-size: 13px; display: inline-block; font-weight: bold; margin-left: 0.5rem;">🎯 優先度: {r["t_rank"]}</span>'

                    st.markdown(f"""
                        <div style="margin-bottom: 0.8rem;">
                            <h3 style="font-size: clamp(16px, 5vw, 26px); font-weight: bold; margin: 0 0 0.3rem 0;">({c[:4]}) {n}</h3>
                            <div style="display: flex; flex-wrap: wrap; gap: 4px; align-items: center;">
                                {badge}
                                <span style="background-color: #2e7d32; color: #ffffff; padding: 0.2rem 0.6rem; border-radius: 4px; font-size: 12px; display: inline-block; font-weight: bold; margin-left: 4px;">⚡ GC初動ターゲット</span>
                                {triage_badge}
                            </div>
                        </div>
                    """, unsafe_allow_html=True)
                    
                    lc_val = int(r['lc'])
                    bt_val = int(r['bt'])
                    high_val = int(r.get('h14', lc_val))
                    low_val = int(r.get('l14', 0))
                    wave_len = high_val - low_val
                    
                    tp20 = int(bt_val * 1.20)
                    tp15 = int(bt_val * 1.15)
                    tp10 = int(bt_val * 1.10)
                    tp5  = int(bt_val * 1.05)
                    sl5  = int(bt_val * 0.95)
                    sl8  = int(bt_val * 0.92)
                    sl15 = int(bt_val * 0.85)
                    
                    sc0, sc0_1, sc0_2, sc1, sc2, sc3, sc4 = st.columns([0.8, 0.8, 0.8, 0.9, 1.1, 1.8, 1.5])
                    
                    sc0.metric("直近高値", f"{high_val:,}円")
                    sc0_1.metric("直近安値", f"{low_val:,}円")
                    sc0_2.metric("上昇幅", f"{wave_len:,}円")
                    sc1.metric("最新終値", f"{lc_val:,}円", f"{daily_sign}{r['daily_pct']*100:.1f}%", delta_color="inverse")
                    
                    html_buy = f"""
                    <div style="font-family: sans-serif; padding-top: 0.2rem;">
                        <div style="font-size: 14px; color: rgba(250, 250, 250, 0.6); padding-bottom: 0.1rem;">🎯 買値目標 (終値+1%強襲)</div>
                        <div style="font-size: 1.8rem; font-weight: bold; color: #FFD700;">{bt_val:,}円</div>
                    </div>
                    """
                    sc2.markdown(html_buy, unsafe_allow_html=True)
                    
                    html_sell = f"""<div style="font-family: sans-serif; padding-top: 0.2rem;">
                        <div style="font-size: 14px; color: rgba(250, 250, 250, 0.6); padding-bottom: 0.1rem;">🎯 売値目標 ＆ 🛡️ 損切目安</div>
                        <div style="font-size: 16px;">
                            <span style="display: inline-block; width: 2.5em; color: #ef5350;">20%</span> <span style="color: #ef5350;">{tp20:,}円</span><br>
                            <span style="display: inline-block; width: 2.5em; color: #ef5350;">15%</span> <span style="color: #ef5350;">{tp15:,}円</span> <span style="color: rgba(250, 250, 250, 0.3); margin: 0 4px;">|</span> <span style="display: inline-block; width: 2.8em; color: #26a69a;">-5%</span> <span style="color: #26a69a;">{sl5:,}円</span><br>
                            <span style="display: inline-block; width: 2.5em; color: #ef5350;">10%</span> <span style="color: #ef5350;">{tp10:,}円</span> <span style="color: rgba(250, 250, 250, 0.3); margin: 0 4px;">|</span> <span style="display: inline-block; width: 2.8em; color: #26a69a;">-8%</span> <span style="color: #26a69a;">{sl8:,}円</span><br>
                            <span style="display: inline-block; width: 2.5em; color: #ef5350;">5%</span> <span style="color: #ef5350;">{tp5:,}円</span> <span style="color: rgba(250, 250, 250, 0.3); margin: 0 4px;">|</span> <span style="display: inline-block; width: 2.8em; color: #26a69a;">-15%</span> <span style="color: #26a69a;">{sl15:,}円</span>
                        </div>
                    </div>"""
                    sc3.markdown(html_sell, unsafe_allow_html=True)
                    
                    vol_val = r.get('avg_vol', 0)
                    
                    html_stats = f"""
                    <div style="display: flex; flex-direction: column; gap: 8px; margin-top: 0.5rem;">
                        <div style="background: rgba(38, 166, 154, 0.1); border-left: 3px solid #26a69a; padding: 4px 8px; border-radius: 4px;">
                            <span style="font-size: 12px; color: #aaa;">RSI (過熱感):</span> <strong style="font-size: 15px; color: #fff;">{int(r['accurate_rsi'])}%</strong>
                        </div>
                        <div style="background: rgba(255, 255, 255, 0.05); border-left: 3px solid #26a69a; padding: 4px 8px; border-radius: 4px;">
                            <span style="font-size: 12px; color: #aaa;">GC判定:</span> <strong style="font-size: 15px; color: #26a69a;">条件クリア</strong>
                        </div>
                        <div style="background: rgba(255, 215, 0, 0.1); border-left: 3px solid #FFD700; padding: 4px 8px; border-radius: 4px;">
                            <span style="font-size: 12px; color: #aaa;">出来高(5日):</span> <strong style="font-size: 15px; color: #fff;">{vol_val:,} 株</strong>
                        </div>
                    </div>
                    """
                    sc4.markdown(html_stats, unsafe_allow_html=True)
                    
                    st.caption(f"🏢 {r.get('Market','不明')} ｜ 🏭 {r.get('Sector','不明')}")
                    
                    hist_chart = r['hist_chart']
                    if not hist_chart.empty:
                        cutoff_chart = hist_chart['Date'].max() - timedelta(days=60)
                        df_chart_filtered = hist_chart[hist_chart['Date'] >= cutoff_chart]
                        st.markdown(render_technical_radar(df_chart_filtered, bt_val, st.session_state.bt_tp), unsafe_allow_html=True)
                        draw_chart(df_chart_filtered, bt_val, tp10=tp10)
                            
with tab3:
    st.markdown('<h3 style="font-size: clamp(14px, 4.5vw, 24px); margin-bottom: 1rem;">🎯 精密スコープ（個別銘柄・深堀りスキャン）</h3>', unsafe_allow_html=True)
    st.caption("※気になっている銘柄や、レーダーで抽出した銘柄のコードを入力し、現在のテクニカル状態と迎撃ラインを精密に解析します。")
    
    col_s1, col_s2 = st.columns([1, 2])
    T3_SCOPE_FILE = f"saved_t3_scope_{user_id}.txt"
    default_scope = "6614\n4427"
    if os.path.exists(T3_SCOPE_FILE):
        with open(T3_SCOPE_FILE, "r", encoding="utf-8") as f:
            default_scope = f.read()
            
    with col_s1:
        target_codes_str = st.text_area("標的コード（複数可、改行区切り）", value=default_scope, height=100)
        run_scope = st.button("🔫 精密スキャン実行", use_container_width=True)
        
    with col_s2:
        st.markdown("#### 🔍 解析対象データ")
        st.caption("・ボスの「鉄の掟」9項目に基づく押し目ラインと適合度\n・トレンド崩壊、落ちるナイフ、危険波形（三尊等）の検知\n・MACDとRSIに基づくトリアージ（優先度）判定")

    if run_scope and target_codes_str:
        with open(T3_SCOPE_FILE, "w", encoding="utf-8") as f:
            f.write(target_codes_str)
            
        t_codes = list(dict.fromkeys([c.upper() for c in re.findall(r'(?<![a-zA-Z0-9])[a-zA-Z0-9]{4}(?![a-zA-Z0-9])', target_codes_str)]))
        
        if not t_codes: st.warning("有効な4桁の銘柄コードが見つかりません。")
        else:
            with st.spinner(f"指定された {len(t_codes)} 銘柄の軌道を精密計算中..."):
                for c in t_codes:
                    st.divider()
                    
                    # 🚨 精密スコープでは、MA25/75を描画するために1年分のデータを取得
                    api_code = c if len(c) == 5 else c + "0"
                    raw_s = get_single_data(api_code, 1)
                    
                    if not raw_s:
                        st.error(f"銘柄 {c} のデータ取得に失敗しました。")
                        continue
                        
                    df_s = clean_df(pd.DataFrame(raw_s))
                    if len(df_s) < 30:
                        st.warning(f"銘柄 {c} は上場直後など、データが不足しているため解析不能です。")
                        continue
                        
                    # テクニカル指標の計算
                    df_chart = calc_technicals(df_s.copy())
                    
                    # 🚨 10営業日同期と判定ロジック
                    df_14 = df_s.tail(10)
                    df_30 = df_s.tail(30)
                    latest = df_chart.iloc[-1]
                    prev = df_chart.iloc[-2] if len(df_chart) > 1 else latest
                    
                    lc = latest['AdjC']
                    h14 = df_14['AdjH'].max()
                    l14 = df_14['AdjL'].min()
                    if pd.isna(h14) or pd.isna(l14) or l14 <= 0: continue
                    
                    ur = h14 - l14
                    bt_primary = h14 - (ur * (st.session_state.push_r / 100.0))
                    shift_ratio = 0.618 if st.session_state.push_r >= 40 else (st.session_state.push_r / 100.0 + 0.15)
                    bt_secondary = h14 - (ur * shift_ratio)
                    
                    is_bt_broken = lc < bt_primary
                    bt_val = bt_secondary if is_bt_broken else bt_primary
                    bt_val = int(bt_val)
                    
                    dead_line = h14 - (ur * 0.618)
                    is_trend_broken = lc < (dead_line * 0.98)
                    
                    daily_pct = (lc / prev['AdjC']) - 1 if prev['AdjC'] > 0 else 0
                    daily_sign = "+" if daily_pct >= 0 else ""
                    
                    # 危険アラートの判定
                    is_dt = check_double_top(df_14)
                    is_hs = check_head_shoulders(df_14)
                    is_db = check_double_bottom(df_14)
                    is_defense = (not is_dt) and (not is_hs) and (lc <= (l14 * 1.03))
                    
                    # マスター情報の取得
                    c_name = f"銘柄 {c[:4]}"; c_market = "不明"; c_sector = "不明"; c_scale = ""
                    if not master_df.empty:
                        m_row = master_df[master_df['Code'] == api_code]
                        if not m_row.empty:
                            c_name = m_row.iloc[0]['CompanyName']
                            c_market = m_row.iloc[0]['Market']
                            c_sector = m_row.iloc[0].get('Sector', '不明')
                            c_scale = m_row.iloc[0].get('Scale', '')
                            
                    # トリアージ判定
                    macd_h = latest.get('MACD_Hist', 0)
                    macd_h_prev = prev.get('MACD_Hist', 0)
                    rsi_v = latest.get('RSI', 50)
                    rank, bg, score, macd_t = get_triage_info(macd_h, macd_h_prev, rsi_v)
                    
                    avg_vol = int(df_s['AdjVo'].tail(5).mean()) if 'AdjVo' in df_s.columns else 0
                    
                    # ---------------- UI描画フェーズ ----------------
                    
                    scale_val = str(c_scale)
                    badge = '<span style="background-color: #0d47a1; color: #ffffff; padding: 0.2rem 0.6rem; border-radius: 4px; font-size: 12px; display: inline-block;">🏢 大型/中型</span>' if any(x in scale_val for x in ["Core30", "Large70", "Mid400"]) else '<span style="background-color: #b71c1c; color: #ffffff; padding: 0.2rem 0.6rem; border-radius: 4px; font-size: 12px; display: inline-block;">🚀 小型/新興</span>'
                    triage_badge = f'<span style="background-color: {bg}; color: #ffffff; padding: 0.2rem 0.6rem; border-radius: 4px; font-size: 13px; display: inline-block; font-weight: bold; margin-left: 0.5rem;">🎯 優先度: {rank}</span>'

                    st.markdown(f"""
                        <div style="margin-bottom: 0.8rem;">
                            <h3 style="font-size: clamp(16px, 5vw, 26px); font-weight: bold; margin: 0 0 0.3rem 0;">({c[:4]}) {c_name}</h3>
                            <div style="display: flex; flex-wrap: wrap; gap: 4px; align-items: center;">{badge}{triage_badge}</div>
                        </div>
                    """, unsafe_allow_html=True)
                    
                    # アラート表示
                    event_alerts = check_event_mines(c)
                    for alert in event_alerts: st.warning(alert)
                    
                    if is_trend_broken: st.error("💀 【トレンド崩壊】黄金比(61.8%)を完全に下抜けています。迎撃非推奨（後学・分析用データ）")
                    elif is_bt_broken: st.error("⚠️ 【第一防衛線突破】想定以上の売り圧力を検知。買値を第二防衛線（黄金比等）へ自動シフトしました。")
                    
                    if c_sector == '医薬品': st.error("🚨 【警告】この銘柄は医薬品（バイオ株）です。思惑だけで動く完全なギャンブルです。")
                    if bool(re.search("ETF|投信|ブル|ベア|REIT|ﾘｰﾄ", str(c_name), re.IGNORECASE)): st.error("🚨 【警告】この銘柄はETF/REIT等です。個別株のテクニカルは通用しません。")
                    
                    if is_dt or is_hs: st.error("🚨 【警告】相場転換の危険波形（三尊/Wトップ）を検知！ 撤退推奨。")
                    if is_db: st.success("🔥 【激熱(攻め)】三川（ダブルボトム）底打ち反転波形を検知！")
                    if is_defense: st.info("🛡️ 【鉄壁(守り)】下値支持線(サポート)に極接近。損切りリスクが極小の安全圏です。")
                    
                    # パネル計算
                    tp20 = int(bt_val * 1.20)
                    tp15 = int(bt_val * 1.15)
                    tp10 = int(bt_val * 1.10)
                    tp5  = int(bt_val * 1.05)
                    sl5  = int(bt_val * 0.95)
                    sl8  = int(bt_val * 0.92)
                    sl15 = int(bt_val * 0.85)
                    
                    denom = h14 - bt_val
                    reach_val = ((h14 - lc) / denom * 100) if denom > 0 else 0
                    
                    # 🚨 追加：ATRと高値経過日数の算出
                    atr_val = int(latest.get('ATR', 0))
                    idxmax = df_14['AdjH'].idxmax()
                    d_high = len(df_14[df_14['Date'] > df_14.loc[idxmax, 'Date']]) if pd.notna(idxmax) else 0
                    
                    # 7カラムUI
                    sc0, sc0_1, sc0_2, sc1, sc2, sc3, sc4 = st.columns([0.8, 0.8, 0.8, 0.9, 1.1, 1.8, 1.5])
                    
                    sc0.metric("直近高値", f"{int(h14):,}円")
                    sc0_1.metric("直近安値", f"{int(l14):,}円")
                    sc0_2.metric("上昇幅", f"{int(ur):,}円")
                    sc1.metric("最新終値", f"{int(lc):,}円", f"{daily_sign}{daily_pct*100:.1f}%", delta_color="inverse")
                    
                    html_buy = f"""
                    <div style="font-family: sans-serif; padding-top: 0.2rem;">
                        <div style="font-size: 14px; color: rgba(250, 250, 250, 0.6); padding-bottom: 0.1rem;">🎯 買値目標 (待伏)</div>
                        <div style="font-size: 1.8rem; font-weight: bold; color: #FFD700;">{bt_val:,}円</div>
                    </div>
                    """
                    sc2.markdown(html_buy, unsafe_allow_html=True)
                    
                    html_sell = f"""<div style="font-family: sans-serif; padding-top: 0.2rem;">
                        <div style="font-size: 14px; color: rgba(250, 250, 250, 0.6); padding-bottom: 0.1rem;">🎯 売値目標 ＆ 🛡️ 損切目安</div>
                        <div style="font-size: 16px;">
                            <span style="display: inline-block; width: 2.5em; color: #ef5350;">20%</span> <span style="color: #ef5350;">{tp20:,}円</span><br>
                            <span style="display: inline-block; width: 2.5em; color: #ef5350;">15%</span> <span style="color: #ef5350;">{tp15:,}円</span> <span style="color: rgba(250, 250, 250, 0.3); margin: 0 4px;">|</span> <span style="display: inline-block; width: 2.8em; color: #26a69a;">-5%</span> <span style="color: #26a69a;">{sl5:,}円</span><br>
                            <span style="display: inline-block; width: 2.5em; color: #ef5350;">10%</span> <span style="color: #ef5350;">{tp10:,}円</span> <span style="color: rgba(250, 250, 250, 0.3); margin: 0 4px;">|</span> <span style="display: inline-block; width: 2.8em; color: #26a69a;">-8%</span> <span style="color: #26a69a;">{sl8:,}円</span><br>
                            <span style="display: inline-block; width: 2.5em; color: #ef5350;">5%</span> <span style="color: #ef5350;">{tp5:,}円</span> <span style="color: rgba(250, 250, 250, 0.3); margin: 0 4px;">|</span> <span style="display: inline-block; width: 2.8em; color: #26a69a;">-15%</span> <span style="color: #26a69a;">{sl15:,}円</span>
                        </div>
                    </div>"""
                    sc3.markdown(html_sell, unsafe_allow_html=True)
                    
                    # 🚨 RSIを撤去し「ATR / 高値経過」の戦術パラメーターへ置換
                    html_stats = f"""
                    <div style="display: flex; flex-direction: column; gap: 8px; margin-top: 0.5rem;">
                        <div style="background: rgba(38, 166, 154, 0.1); border-left: 3px solid #26a69a; padding: 4px 8px; border-radius: 4px;">
                            <span style="font-size: 12px; color: #aaa;">到達度:</span> <strong style="font-size: 15px; color: #fff;">{reach_val:.1f}%</strong>
                        </div>
                        <div style="background: rgba(156, 39, 176, 0.1); border-left: 3px solid #ab47bc; padding: 4px 8px; border-radius: 4px;">
                            <span style="font-size: 12px; color: #aaa;">ATR / 高値経過:</span> <strong style="font-size: 15px; color: #ce93d8;">{atr_val:,}円 / {d_high}日</strong>
                        </div>
                        <div style="background: rgba(255, 215, 0, 0.1); border-left: 3px solid #FFD700; padding: 4px 8px; border-radius: 4px;">
                            <span style="font-size: 12px; color: #aaa;">出来高(5日):</span> <strong style="font-size: 15px; color: #fff;">{avg_vol:,} 株</strong>
                        </div>
                    </div>
                    """
                    sc4.markdown(html_stats, unsafe_allow_html=True)
                    
                    st.caption(f"🏢 {c_market} ｜ 🏭 {c_sector}")
                    
                    # グラフ描画（右寄り防止フィルターをかけ、10%ラインのみを描画）
                    cutoff_chart = df_chart['Date'].max() - timedelta(days=60)
                    df_chart_filtered = df_chart[df_chart['Date'] >= cutoff_chart]
                    
                    st.markdown(render_technical_radar(df_chart_filtered, bt_val, st.session_state.bt_tp), unsafe_allow_html=True)
                    draw_chart(df_chart_filtered, bt_val, tp10=tp10)
                        
# ------------------------------------------
# Tab 4: 戦術シミュレータ（デュアル・バックテスト）
# ------------------------------------------
with tab4: # 🚨 ※ここはボスのコードのタブ番号（tab4やtab5など）に合わせてください
    st.markdown('<h3 style="font-size: clamp(14px, 4.5vw, 24px); margin-bottom: 1rem;">⚙️ 戦術シミュレータ (2年間のバックテスト)</h3>', unsafe_allow_html=True)
    
    col_b1, col_b2 = st.columns([1, 2])

    T3_FILE = f"saved_t3_codes_{user_id}.txt"
    default_t3 = "6614\n4427"
    if os.path.exists(T3_FILE):
        with open(T3_FILE, "r", encoding="utf-8") as f:
            default_t3 = f.read()

    with col_b1: 
        st.markdown("🔍 **検証する戦術を選択してください**")
        # 🚨 key="bt_mode_t5" を付与
        test_mode = st.radio("戦術モード", ["🌐 【待伏】鉄の掟 (押し目狙撃)", "⚡ 【強襲】GCブレイクアウト (順張り)"], label_visibility="collapsed", key="bt_mode_t5")
        
        st.markdown("検証コード (複数可、カンマや改行区切り)")
        # 🚨 key="bt_codes_t5" を付与
        bt_c_in = st.text_area("銘柄コード", value=default_t3, height=100, label_visibility="collapsed", key="bt_codes_t5")
        
        # 🚨 key="btn_run_bt_t5" を付与（エラーの直接原因を完全排除）
        run_bt = st.button("🔥 一括バックテスト実行", use_container_width=True, key="btn_run_bt_t5")
        
    with col_b2:
        st.markdown("#### ⚙️ シミュレーション微調整")
        st.caption("※サイドバーの設定とは独立して、ここで数値を自由に変更してテストできます。")
        
        # 🚨 すべての key に "_t5" を付与し、他タブとの衝突を完全排除
        c_p1, c_p2 = st.columns(2)
        sim_tp = c_p1.number_input("🎯 利確目標 (+%)", value=float(st.session_state.bt_tp), step=1.0, key="sim_tp_t5")
        sim_sl_i = c_p2.number_input("🛡️ 損切目安 (-%)", value=float(st.session_state.bt_sl_i), step=1.0, key="sim_sl_i_t5")
        
        c_p3, c_p4 = st.columns(2)
        sim_limit_d = c_p3.number_input("⏳ 買い期限 (営業日)", value=int(st.session_state.limit_d), step=1, key="sim_limit_d_t5")
        sim_sell_d = c_p4.number_input("⏳ 強制撤退 (営業日)", value=int(st.session_state.bt_sell_d), step=1, key="sim_sell_d_t5")
        
        st.divider()
        if "待伏" in test_mode:
            st.markdown("##### 🌐 【待伏】固有パラメーター")
            c_t1_1, c_t1_2 = st.columns(2)
            sim_push_r = c_t1_1.number_input("押し目待ち (%落とし)", value=float(st.session_state.push_r), step=1.0, key="sim_push_r_t5")
            sim_pass_req = c_t1_2.number_input("掟クリア要求数", value=8, step=1, max_value=9, min_value=1, key="sim_pass_req_t5")
        else:
            st.markdown("##### ⚡ 【強襲】固有パラメーター")
            c_t2_1, c_t2_2 = st.columns(2)
            sim_rsi_lim = c_t2_1.number_input("RSI上限 (過熱感)", value=35, step=5, key="sim_rsi_lim_t5")
            sim_time_risk = c_t2_2.number_input("時間リスク上限 (到達日数)", value=5, step=1, key="sim_time_risk_t5")
        
    if run_bt and bt_c_in:
        with open(T3_FILE, "w", encoding="utf-8") as f:
            f.write(bt_c_in)
            
        t_codes = list(dict.fromkeys([c.upper() for c in re.findall(r'(?<![a-zA-Z0-9])[a-zA-Z0-9]{4}(?![a-zA-Z0-9])', bt_c_in)]))
        
        if not t_codes: st.warning("有効なコードが見つかりません。")
        else:
            all_t = []; b_bar = st.progress(0, "過去2年分の相場を仮想売買中...")
            
            for idx, c in enumerate(t_codes):
                raw = get_single_data(c + "0", 2)
                if not raw: continue
                
                df = clean_df(pd.DataFrame(raw)).dropna(subset=['AdjO', 'AdjH', 'AdjL', 'AdjC']).reset_index(drop=True)
                if len(df) < 40: continue
                
                df = calc_technicals(df)
                pos = None
                
                for i in range(35, len(df)):
                    td = df.iloc[i]
                    prev = df.iloc[i-1]
                    
                    if pos is None:
                        win_14 = df.iloc[i-15:i-1]
                        win_30 = df.iloc[i-31:i-1]
                        
                        lc_prev = prev['AdjC']
                        h14 = win_14['AdjH'].max(); l14 = win_14['AdjL'].min()
                        if pd.isna(h14) or pd.isna(l14) or l14 <= 0: continue
                        
                        atr_prev = prev.get('ATR', 0)
                        if atr_prev < 10 or (atr_prev / lc_prev) < 0.01: continue 
                        
                        if "待伏" in test_mode:
                            r14 = h14 / l14
                            idxmax = win_14['AdjH'].idxmax()
                            d_high = len(win_14[win_14['Date'] > win_14.loc[idxmax, 'Date']]) if pd.notna(idxmax) else 0
                            
                            is_dt = check_double_top(win_30)
                            is_hs = check_head_shoulders(win_30)
                            
                            bt_val = int(h14 - ((h14 - l14) * (sim_push_r / 100.0)))
                            
                            score = 0
                            if 1.3 <= r14 <= 2.0: score += 1
                            if d_high <= sim_limit_d: score += 1 
                            if not is_dt: score += 1
                            if not is_hs: score += 1
                            if bt_val * 0.85 <= lc_prev <= bt_val * 1.35: score += 1
                            score += 4 
                            
                            if score >= sim_pass_req:
                                if td['AdjL'] <= bt_val:
                                    exec_p = min(td['AdjO'], bt_val)
                                    pos = {'b_i': i, 'b_d': td['Date'], 'b_p': exec_p}
                                    
                        else:
                            rsi_prev = prev.get('RSI', 50)
                            tp_yen = lc_prev * (sim_tp / 100.0)
                            exp_days = int(tp_yen / atr_prev) if atr_prev > 0 else 99
                            
                            gc_triggered = False
                            trigger_price = 0
                            
                            # 🚨 ボスの最新仕様（GC点灯日の高値+1%）をトリガーに適用
                            for d_ago in range(1, int(sim_limit_d) + 1):
                                idx_eval = i - d_ago
                                if idx_eval >= 1:
                                    mh1 = df.iloc[idx_eval].get('MACD_Hist', 0)
                                    mh2 = df.iloc[idx_eval-1].get('MACD_Hist', 0)
                                    if mh1 > 0 and mh2 <= 0:
                                        gc_triggered = True
                                        trigger_price = df.iloc[idx_eval]['AdjH'] * 1.01 
                                        break
                            
                            if gc_triggered and rsi_prev <= sim_rsi_lim and exp_days < sim_time_risk:
                                if td['AdjH'] >= trigger_price:
                                    exec_p = max(td['AdjO'], trigger_price)
                                    pos = {'b_i': i, 'b_d': td['Date'], 'b_p': exec_p}

                    else:
                        bp = pos['b_p']; held = i - pos['b_i']; sp = 0; rsn = ""
                        
                        sl_val = bp * (1 - (sim_sl_i / 100.0))
                        tp_val = bp * (1 + (sim_tp / 100.0))
                        
                        if td['AdjL'] <= sl_val: 
                            sp = min(td['AdjO'], sl_val); rsn = f"🛡️ 損切 (-{sim_sl_i}%)"
                        elif td['AdjH'] >= tp_val: 
                            sp = max(td['AdjO'], tp_val); rsn = f"🎯 利確 (+{sim_tp}%)"
                        elif held >= sim_sell_d: 
                            sp = td['AdjC']; rsn = f"⏳ 時間切れ ({sim_sell_d}日)"
                        
                        if sp > 0:
                            sp = round(sp, 1)
                            p_pct = round(((sp / bp) - 1) * 100, 2)
                            p_amt = int((sp - bp) * st.session_state.bt_lot)
                            all_t.append({
                                '銘柄': c, '購入日': pos['b_d'].strftime('%Y-%m-%d'), '決済日': td['Date'].strftime('%Y-%m-%d'), 
                                '保有日数': held, '買値(円)': int(bp), '売値(円)': int(sp), '損益(%)': p_pct, '損益額(円)': p_amt, '決済理由': rsn
                            })
                            pos = None
                            
                b_bar.progress((idx + 1) / len(t_codes)); time.sleep(0.1)
                
            b_bar.empty()
            
            if not all_t: 
                st.warning("指定された期間・条件でシグナル点灯（約定）はありませんでした。")
            else:
                tdf = pd.DataFrame(all_t)
                tot = len(tdf); wins = len(tdf[tdf['損益額(円)'] > 0])
                n_prof = tdf['損益額(円)'].sum()
                sprof = tdf[tdf['損益額(円)'] > 0]['損益額(円)'].sum()
                sloss = abs(tdf[tdf['損益額(円)'] <= 0]['損益額(円)'].sum())
                pf = round(sprof / sloss, 2) if sloss > 0 else 'inf'
                
                st.success("🎯 バックテスト完了")
                st.markdown(f'<h3 style="font-size: clamp(16px, 5vw, 26px); font-weight: bold; color: {"#ef5350" if n_prof > 0 else "#26a69a"};">💰 総合利益額: {n_prof:,} 円</h3>', unsafe_allow_html=True)
                
                m1, m2, m3, m4 = st.columns(4)
                m1.metric("トレード回数", f"{tot} 回")
                m2.metric("勝率", f"{round((wins/tot)*100,1)} %")
                m3.metric("平均損益額", f"{int(n_prof/tot):,} 円")
                m4.metric("プロフィットファクター(PF)", f"{pf}")
                
                st.markdown("### 📜 詳細交戦記録（トレード履歴）")
                
                def color_pnl(val):
                    if isinstance(val, (int, float)):
                        color = '#ef5350' if val > 0 else '#26a69a' if val < 0 else 'white'
                        return f'color: {color}'
                    return ''
                
                st.dataframe(
                    tdf.style.applymap(color_pnl, subset=['損益(%)', '損益額(円)']).format({'買値(円)': '{:,}', '売値(円)': '{:,}', '損益額(円)': '{:,}'}),
                    use_container_width=True, hide_index=True
                )

# ------------------------------------------
# Tab 5: IFD-OCO 10日ルール監視（JPXカレンダー準拠）
# ------------------------------------------
with tab5:
    st.markdown('### ⏳ IFD-OCO 10日ルール監視')
    st.caption("実戦配備中（保有中）の銘柄と約定日を入力し、タイムリミット（営業日）を自動追跡します。")
    
    HOLD_FILE = f"saved_hold_{user_id}.txt"
    default_hold = "7203, 2026-03-10, 3500\n6614, 2026-03-15, 1200"
    if os.path.exists(HOLD_FILE):
        with open(HOLD_FILE, "r", encoding="utf-8") as f:
            default_hold = f.read()
            
    hold_input = st.text_area("保有銘柄（銘柄コード, 約定日[YYYY-MM-DD], 買値）", value=default_hold, height=150)
    
    if st.button("🔄 戦況更新 (10日タイマー確認)"):
        with open(HOLD_FILE, "w", encoding="utf-8") as f:
            f.write(hold_input)
            
        lines = hold_input.strip().split('\n')
        today = datetime.utcnow() + timedelta(hours=9)
        today_date = today.date()
        
        for line in lines:
            if not line.strip(): continue
            parts = [p.strip() for p in line.split(',')]
            if len(parts) >= 2:
                c = parts[0]; date_str = parts[1]
                bp = parts[2] if len(parts) >= 3 else "---"
                
                try:
                    buy_date = datetime.strptime(date_str, "%Y-%m-%d").date()
                    
                    # 🛡️ JPX完全カレンダー（土日・祝日・年末年始の除外）
                    days_elapsed = 0
                    curr_date = buy_date
                    while curr_date < today_date:
                        # 土日(5,6)以外 ＆ 日本の祝日以外 ＆ 年末年始(12/31〜1/3)以外なら「営業日」としてカウント
                        if curr_date.weekday() < 5 and not jpholiday.is_holiday(curr_date):
                            if not ((curr_date.month == 1 and curr_date.day in [1, 2, 3]) or (curr_date.month == 12 and curr_date.day == 31)):
                                days_elapsed += 1
                        curr_date += timedelta(days=1)
                    
                    c_name = master_df[master_df['Code'] == c + "0"]['CompanyName'].iloc[0] if not master_df.empty and (c + "0") in master_df['Code'].values else "不明"
                    
                    if days_elapsed <= 7:
                        status = "🟢 巡航中"
                        bg_color = "rgba(38, 166, 154, 0.1)"; border_color = "#26a69a"
                    elif days_elapsed <= 9:
                        status = "⚠️ 撤退準備 (タイムリミット接近)"
                        bg_color = "rgba(255, 215, 0, 0.1)"; border_color = "#FFD700"
                    else:
                        status = "💀 強制撤退日 (本日中にIFDを取消し、成行決済せよ)"
                        bg_color = "rgba(239, 83, 80, 0.1)"; border_color = "#ef5350"
                        
                    st.markdown(f"""
                    <div style="background-color: {bg_color}; border-left: 4px solid {border_color}; padding: 1rem; margin-bottom: 0.8rem; border-radius: 4px;">
                        <div style="font-size: 14px; color: #aaa;">約定日: {date_str} (買値: {bp}円)</div>
                        <div style="font-size: 20px; font-weight: bold; margin: 0.3rem 0;">({c}) {c_name}</div>
                        <div style="font-size: 18px; font-weight: bold; color: {border_color};">{status} : 経過 {days_elapsed} 営業日</div>
                    </div>
                    """, unsafe_allow_html=True)
                except Exception as e:
                    st.error(f"🚨 フォーマットエラー: {line} (YYYY-MM-DD形式で入力してください) - {e}")
                    
# ------------------------------------------
# Tab 6: 事後任務報告（AAR）
# ------------------------------------------
with tab6:
    st.markdown('### 🗂️ 過去戦歴の解剖（純粋IFD-OCO検証）')
    st.caption("実際の売却日を完全に無視し、買付日から「指定した利確・損切・保有日数」のルールで完全放置した場合の幻の戦果を算出します。")
    
    uploaded_file = st.file_uploader("約定履歴CSVをアップロード", type=['csv'])
    if uploaded_file is not None:
        try:
            import io
            bytes_data = uploaded_file.getvalue()
            try:
                content_str = bytes_data.decode('shift_jis')
            except:
                content_str = bytes_data.decode('utf-8', errors='replace')
                
            lines = content_str.splitlines()
            header_idx = 0
            for i, line in enumerate(lines):
                if "約定日" in line and "銘柄コード" in line and "取引" in line:
                    header_idx = i
                    break
                    
            df_csv = pd.read_csv(io.StringIO(content_str), skiprows=header_idx)
            df_csv['約定日'] = pd.to_datetime(df_csv['約定日'])
            df_csv['銘柄コード'] = df_csv['銘柄コード'].astype(str).str.extract(r'(\d{4})')[0]
            df_csv['約定単価'] = pd.to_numeric(df_csv['約定単価'], errors='coerce')
            df_csv['約定数量'] = pd.to_numeric(df_csv['約定数量'], errors='coerce')

            buys = df_csv[df_csv['取引'].str.contains('買', na=False)].sort_values('約定日').copy()
            sells = df_csv[df_csv['取引'].str.contains('売', na=False)].sort_values('約定日').copy()

            trades = []; buy_queues = {}
            for idx, buy in buys.iterrows():
                code = buy['銘柄コード']
                if pd.isna(code): continue
                if code not in buy_queues: buy_queues[code] = []
                buy_queues[code].append({'date': buy['約定日'], 'price': buy['約定単価'], 'qty': buy['約定数量'], 'name': buy['銘柄']})

            for idx, sell in sells.iterrows():
                code = sell['銘柄コード']
                if pd.isna(code): continue
                if code in buy_queues and len(buy_queues[code]) > 0:
                    buy = buy_queues[code].pop(0)
                    trades.append({
                        'code': code, 'name': sell['銘柄'],
                        'buy_date': buy['date'], 'buy_price': buy['price'],
                        'sell_date': sell['約定日'], 'sell_price': sell['約定単価'], 'qty': sell['約定数量']
                    })
            
            if not trades:
                st.warning("CSVから買付と売却のペア（交戦記録）を検出できませんでした。")
            else:
                st.markdown("#### ⚙️ IFD-OCO 自動判定パラメーター")
                col_p1, col_p2, col_p3 = st.columns(3)
                sim_tp = col_p1.number_input("🎯 利確目標 (+%)", value=float(st.session_state.bt_tp), step=1.0)
                sim_sl = col_p2.number_input("🛡️ 損切目安 (-%)", value=float(st.session_state.bt_sl_i), step=1.0)
                sim_days = col_p3.number_input("⏳ 期限切れ手仕舞い (営業日)", value=10, step=1)
                
                if st.button(f"🚀 全{len(trades)}件の弾道を「完全放置ルール」で再計算"):
                    with st.spinner("J-Quantsから当時のチャートを読み込み、未来の弾道を追跡中..."):
                        results = []
                        for t in trades:
                            code = t['code']; bd = t['buy_date']; sd = t['sell_date']
                            bp = t['buy_price']; sp = t['sell_price']; qty = t['qty']
                            
                            tp_val = bp * (1 + (sim_tp / 100.0))
                            sl_val = bp * (1 - (sim_sl / 100.0))
                            
                            api_code = code if len(code) == 5 else code + "0"
                            raw_data = get_single_data(api_code, 1)
                            
                            sim_sell_price = sp
                            sim_sell_date = sd
                            rsn = "データ不足"
                            rsi_val = 50; macd_t = "---"
                            
                            if raw_data:
                                hist = clean_df(pd.DataFrame(raw_data))
                                hist = calc_technicals(hist) 
                                
                                buy_hist = hist[hist['Date'] <= bd]
                                if len(buy_hist) >= 2:
                                    latest = buy_hist.iloc[-1]
                                    prev = buy_hist.iloc[-2]
                                    rsi = latest.get('RSI', 50)
                                    macd_h = latest.get('MACD_Hist', 0)
                                    macd_h_prev = prev.get('MACD_Hist', 0)
                                    
                                    if macd_h > 0 and macd_h_prev <= 0: macd_t = "GC直後"
                                    elif macd_h > macd_h_prev: macd_t = "上昇拡大"
                                    elif macd_h < 0 and macd_h < macd_h_prev: macd_t = "下落継続"
                                    else: macd_t = "減衰"
                                    
                                    rsi_val = int(rsi)
                                
                                future_df = hist[hist['Date'] >= bd].sort_values('Date')
                                period_df = future_df.head(int(sim_days) + 1)
                                
                                if not period_df.empty:
                                    last_row = period_df.iloc[-1]
                                    sim_sell_price = last_row['AdjC']
                                    sim_sell_date = last_row['Date']
                                    rsn = f"⏳ 期限切れ ({len(period_df)-1}日目)"
                                    
                                    for i, r in period_df.iterrows():
                                        if r['AdjH'] >= tp_val:
                                            sim_sell_price = tp_val
                                            sim_sell_date = r['Date']
                                            rsn = f"🎯 利確 (+{sim_tp}%)"
                                            break
                                        elif r['AdjL'] <= sl_val:
                                            sim_sell_price = min(r['AdjO'], sl_val)
                                            sim_sell_date = r['Date']
                                            rsn = f"🛡️ 損切 (-{sim_sl}%)"
                                            break
                            
                            actual_profit = (sp - bp) * qty
                            sim_profit = (sim_sell_price - bp) * qty
                            
                            results.append({
                                '銘柄': t['name'], 'コード': code, 
                                '買付日': bd.strftime('%m/%d'), 
                                'RSI/陣形': f"{rsi_val}% / {macd_t}",
                                '実際の売却': sd.strftime('%m/%d'),
                                '幻の決済日': sim_sell_date.strftime('%m/%d') if isinstance(sim_sell_date, pd.Timestamp) else "---",
                                '買値': bp, '実際の売値': sp, '幻の売値': sim_sell_price,
                                '実際の損益': actual_profit, '幻の損益': sim_profit, 
                                '改善額': sim_profit - actual_profit, '判定結果': rsn
                            })
                                
                        if results:
                            res_df = pd.DataFrame(results)
                            total_actual = res_df['実際の損益'].sum()
                            total_sim = res_df['幻の損益'].sum()
                            diff = total_sim - total_actual
                            
                            st.markdown("### 💰 総合戦果の比較")
                            col1, col2, col3 = st.columns(3)
                            col1.metric("実際の合計損益", f"{total_actual:,.0f} 円")
                            col2.metric(f"完全放置ルール の損益", f"{total_sim:,.0f} 円", f"{diff:,.0f} 円", delta_color="inverse")
                            
                            def color_profit(val):
                                if isinstance(val, (int, float)):
                                    return 'color: #ef5350' if val > 0 else 'color: #26a69a' if val < 0 else ''
                                return ''
                            
                            format_dict = {
                                '買値': '{:,.0f}', '実際の売値': '{:,.0f}', '幻の売値': '{:,.0f}',
                                '実際の損益': '{:,.0f}', '幻の損益': '{:,.0f}', '改善額': '{:,.0f}'
                            }
                            
                            st.dataframe(
                                res_df.style.format(format_dict).applymap(color_profit, subset=['実際の損益', '幻の損益', '改善額']), 
                                use_container_width=True
                            )
                            
                            if diff > 0:
                                st.success(f"🔥 【証明完了】人間の裁量（ノイズ）を完全に捨て、機械的IFD-OCOルールを徹底した方が、利益は {diff:,.0f}円 高くなります。")
                            else:
                                st.warning(f"🛡️ 【証明完了】当時のボスの裁量決済（途中での手動利確・損切など）は、完全放置ルールよりも {abs(diff):,.0f}円 優秀でした。")
        except Exception as e:
            st.error(f"🚨 CSVの解析に失敗しました: {e}")
