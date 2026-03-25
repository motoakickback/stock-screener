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

# --- 標準チャート（Tab 1, 2, 4用） ---
def draw_chart(df, targ_p, *args, **kwargs):
    df = df.copy()
    df['MA5'] = df['AdjC'].rolling(window=5).mean()
    df['MA25'] = df['AdjC'].rolling(window=25).mean()
    df['MA75'] = df['AdjC'].rolling(window=75).mean() # 🛡️ 75日線
    
    tp10 = targ_p * 1.10 # 🎯 10%ラインのみを内部強制計算
    
    fig = go.Figure()
    fig.add_trace(go.Candlestick(x=df['Date'], open=df['AdjO'], high=df['AdjH'], low=df['AdjL'], close=df['AdjC'], name='株価', increasing_line_color='#ef5350', decreasing_line_color='#26a69a'))
    fig.add_trace(go.Scatter(x=df['Date'], y=df['MA5'], mode='lines', name='5日', line=dict(color='rgba(156, 39, 176, 0.7)', width=1.5)))      
    fig.add_trace(go.Scatter(x=df['Date'], y=df['MA25'], mode='lines', name='25日', line=dict(color='rgba(33, 150, 243, 0.7)', width=1.5)))     
    fig.add_trace(go.Scatter(x=df['Date'], y=df['MA75'], mode='lines', name='75日', line=dict(color='rgba(255, 152, 0, 0.7)', width=1.5)))
    
    fig.add_trace(go.Scatter(x=df['Date'], y=[targ_p]*len(df), mode='lines', name='買値/トリガー', line=dict(color='#FFD700', width=2, dash='dash')))
    fig.add_trace(go.Scatter(x=df['Date'], y=[tp10]*len(df), mode='lines', name='売値(10%)', line=dict(color='rgba(239, 83, 80, 0.8)', width=1.5, dash='dot'))) # ノイズを消去し10%のみ描画
    
    start_date = df['Date'].max() - timedelta(days=45) if len(df) > 30 else df['Date'].min()
    
    fig.update_layout(
        height=450,
        margin=dict(l=0, r=10, t=40, b=0),
        xaxis=dict(
            rangeslider=dict(visible=True, thickness=0.1),
            range=[start_date, df['Date'].max() + timedelta(days=2)],
            type="date"
        ),
        yaxis=dict(fixedrange=False, side="right", automargin=True),
        paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)', hovermode="x unified",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0),
        dragmode="pan"
    )
    st.plotly_chart(fig, use_container_width=True, config={'displayModeBar': False, 'scrollZoom': True})

# --- 高高度モニター（Tab 3用）ズームチャート ---
def draw_chart_t6(df, targ_p, *args, **kwargs):
    df = df.copy()
    df['MA5'] = df['AdjC'].rolling(window=5).mean()
    df['MA25'] = df['AdjC'].rolling(window=25).mean()
    df['MA75'] = df['AdjC'].rolling(window=75).mean()
    
    tp10 = targ_p * 1.10 # 🎯 10%ラインのみを内部強制計算
    
    fig = go.Figure()
    fig.add_trace(go.Candlestick(x=df['Date'], open=df['AdjO'], high=df['AdjH'], low=df['AdjL'], close=df['AdjC'], name='株価', increasing_line_color='#ef5350', decreasing_line_color='#26a69a'))
    fig.add_trace(go.Scatter(x=df['Date'], y=df['MA5'], mode='lines', name='5日線(命綱)', line=dict(color='rgba(156, 39, 176, 0.9)', width=2.5)))      
    fig.add_trace(go.Scatter(x=df['Date'], y=df['MA25'], mode='lines', name='25日', line=dict(color='rgba(33, 150, 243, 0.7)', width=1.5)))     
    fig.add_trace(go.Scatter(x=df['Date'], y=df['MA75'], mode='lines', name='75日', line=dict(color='rgba(255, 152, 0, 0.7)', width=1.5)))
    
    fig.add_trace(go.Scatter(x=df['Date'], y=[targ_p]*len(df), mode='lines', name='現在値', line=dict(color='#FFD700', width=2, dash='dash')))
    fig.add_trace(go.Scatter(x=df['Date'], y=[tp10]*len(df), mode='lines', name='+10%', line=dict(color='rgba(239, 83, 80, 0.9)', width=1.5, dash='dot'))) # 10%のみ描画
    
    last_date = df['Date'].max()
    start_date = df['Date'].iloc[-14] if len(df) >= 14 else df['Date'].min()
    
    visible_df = df[(df['Date'] >= start_date) & (df['Date'] <= last_date)]
    if not visible_df.empty:
        y_max = max(visible_df['AdjH'].max(), tp10)
        y_min = min(visible_df['AdjL'].min(), visible_df['MA5'].min()) 
        y_margin = (y_max - y_min) * 0.05
        y_range = [y_min - y_margin, y_max + y_margin]
    else: 
        y_range = None

    fig.update_layout(
        height=450,
        margin=dict(l=0, r=10, t=40, b=0),
        xaxis=dict(
            rangeslider=dict(visible=True, thickness=0.1),
            range=[start_date, last_date + timedelta(days=2)],
            type="date"
        ),
        yaxis=dict(fixedrange=False, side="right", automargin=True),
        paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)', hovermode="x unified",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0),
        dragmode="pan"
    )
    if y_range: fig.update_layout(yaxis=dict(range=y_range))
    st.plotly_chart(fig, use_container_width=True, config={'displayModeBar': False, 'scrollZoom': True})
    
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
tab1, tab2, tab3, tab4, tab5, tab6, tab7 = st.tabs([
    "🌐 【待伏】広域レーダー", 
    "⚡ 【強襲】GC初動レーダー", 
    "🛸 【観測】高高度モニター", 
    "🎯 精密スコープ", 
    "⚙️ 戦術シミュレータ", 
    "🪤 IFD潜伏カウント", 
    "📁 事後任務報告(AAR)"
])
master_df = load_master()
tactics_mode = st.session_state.sidebar_tactics

# ------------------------------------------
# Tab 1: 広域索敵レーダー（鉄の掟）
# ------------------------------------------
with tab1:
    render_macro_board()
    st.markdown('### 🌐 ボスの「鉄の掟」広域スキャン（50%押し待伏せ）')
    st.caption("※最低限の生存条件をクリアした銘柄を、ボスの定めた『掟（全9項目）』でスコアリングして抽出します。")
    run_scan = st.button(f"🚀 待伏せ部隊スキャン開始 ({tactics_mode.split()[0]}モード)")
    
    if run_scan:
        with st.spinner("全軍から鉄の掟適合銘柄を抽出・採点中..."):
            raw = get_hist_data_cached()
            if not raw: 
                st.error("データ取得に失敗しました。")
            else:
                df = clean_df(pd.DataFrame(raw)).dropna(subset=['AdjC', 'AdjH', 'AdjL']).sort_values(['Code', 'Date'])
                df_30 = df.groupby('Code').tail(30)
                max_date_all = df['Date'].max(); cutoff_date_14 = max_date_all - timedelta(days=14)
                df_14 = df_30[df_30['Date'] >= cutoff_date_14]
                counts = df_14.groupby('Code').size(); valid = counts[counts >= 5].index
                
                if valid.empty: 
                    st.warning("条件を満たすデータが存在しません。")
                else:
                    df_14 = df_14[df_14['Code'].isin(valid)]; df_30 = df_30[df_30['Code'].isin(valid)]
                    df_past = df[~df.index.isin(df_30.index)]; df_past = df_past[df_past['Code'].isin(valid)]
                    
                    agg_14 = df_14.groupby('Code').agg(lc=('AdjC', 'last'), prev_c=('AdjC', lambda x: x.iloc[-2] if len(x) > 1 else np.nan), c_3days_ago=('AdjC', lambda x: x.iloc[-4] if len(x) > 3 else np.nan), h14=('AdjH', 'max'), l14=('AdjL', 'min'))
                    idx_max = df_14.groupby('Code')['AdjH'].idxmax(); h_dates = df_14.loc[idx_max, ['Code', 'Date']].rename(columns={'Date': 'h_date'})
                    df_14_m = df_14.merge(h_dates, on='Code'); d_high = df_14_m[df_14_m['Date'] > df_14_m['h_date']].groupby('Code').size().rename('d_high')
                    agg_30 = df_30.groupby('Code').agg(l30=('AdjL', 'min'))
                    agg_p = df_past.groupby('Code').agg(omax=('AdjH', 'max'), omin=('AdjL', 'min'))
                    sum_df = agg_14.join(d_high, how='left').fillna({'d_high': 0}).join(agg_30).join(agg_p).reset_index()
                    
                    ur = sum_df['h14'] - sum_df['l14']
                    bt_primary = sum_df['h14'] - (ur * (push_r / 100.0)); shift_ratio = 0.618 if push_r >= 40 else (push_r / 100.0 + 0.15)
                    bt_secondary = sum_df['h14'] - (ur * shift_ratio)
                    sum_df['is_bt_broken'] = sum_df['lc'] < bt_primary; sum_df['bt'] = np.where(sum_df['is_bt_broken'], bt_secondary, bt_primary)
                    
                    sum_df['tp15'] = sum_df['bt'] * 1.15
                    sum_df['reach_pct'] = np.where(sum_df['h14'] - sum_df['bt'] > 0, (sum_df['h14'] - sum_df['lc']) / (sum_df['h14'] - sum_df['bt']) * 100, 0)
                    sum_df['r14'] = np.where(sum_df['l14'] > 0, sum_df['h14'] / sum_df['l14'], 0)
                    sum_df['r30'] = np.where(sum_df['l30'] > 0, sum_df['lc'] / sum_df['l30'], 0)
                    sum_df['ldrop'] = np.where((sum_df['omax'].notna()) & (sum_df['omax'] > 0), ((sum_df['lc'] / sum_df['omax']) - 1) * 100, 0)
                    sum_df['lrise'] = np.where((sum_df['omin'].notna()) & (sum_df['omin'] > 0), sum_df['lc'] / sum_df['omin'], 0)
                    sum_df['daily_pct'] = np.where(sum_df['prev_c'] > 0, (sum_df['lc'] / sum_df['prev_c']) - 1, 0)
                    sum_df['pct_3days'] = np.where(sum_df['c_3days_ago'] > 0, (sum_df['lc'] / sum_df['c_3days_ago']) - 1, 0)
                    
                    sum_df = sum_df.merge(df_14.groupby('Code').apply(check_double_top).rename('is_dt'), on='Code', how='left')\
                                   .merge(df_14.groupby('Code').apply(check_head_shoulders).rename('is_hs'), on='Code', how='left')\
                                   .merge(df_14.groupby('Code').apply(check_double_bottom).rename('is_db'), on='Code', how='left')\
                                   .merge(df_30.groupby('Code').apply(check_sakata_patterns).rename('sakata_signal'), on='Code', how='left').fillna({'is_dt': False, 'is_hs': False, 'is_db': False})
                    sum_df['is_defense'] = (~sum_df['is_dt']) & (~sum_df['is_hs']) & (sum_df['lc'] <= (sum_df['l14'] * 1.03))
                    
                    if not master_df.empty: sum_df = pd.merge(sum_df, master_df, on='Code', how='left')
                    if f7_ex_etf and 'Sector' in sum_df.columns: sum_df = sum_df[~sum_df['CompanyName'].astype(str).str.contains("ETF|投信|ブル|ベア|REIT|ﾘｰﾄ", na=False, flags=re.IGNORECASE)]
                    if f8_ex_bio and 'Sector' in sum_df.columns: sum_df = sum_df[sum_df['Sector'] != '医薬品']
                    if f5_ipo:
                        old_c = get_old_codes()
                        if old_c: sum_df = sum_df[sum_df['Code'].isin(old_c)]
                        sum_df = sum_df[~sum_df['Code'].astype(str).str.contains(r'[a-zA-Z]')]
                    if f6_risk and 'CompanyName' in sum_df.columns: sum_df = sum_df[~sum_df['CompanyName'].astype(str).str.contains("疑義|重要事象", na=False)]
                    
                    # 🚨 【修正】絶対除外フィルター（最低限の生存バイアス）
                    sum_df = sum_df[(sum_df['lc'] >= f1_min) & (sum_df['lc'] <= f1_max)]
                    if f10_ex_knife: sum_df = sum_df[(sum_df['daily_pct'] >= -(st.session_state.bt_sl_i / 100.0)) & (sum_df['pct_3days'] >= -(st.session_state.bt_sl_i / 100.0) * 1.5)]
                    
                    # 🎯 【修正】意味のある「掟の採点（スコアリング）」
                    rule_scores = []; passed_counts = []
                    for _, r in sum_df.iterrows():
                        score_list = [
                            r['r30'] <= f2_m30,
                            r['ldrop'] >= f3_drop,
                            (r['lrise'] <= f4_mlong) or (r['lrise'] == 0),
                            (f9_min14 <= r['r14'] <= f9_max14),
                            r['d_high'] <= limit_d,
                            (r['bt'] * 0.85 <= r['lc'] <= r['bt'] * 1.35),
                            not r['is_dt'],
                            not r['is_hs'],
                            not pd.notna(r.get('sakata_signal')) or "下落警戒" not in str(r.get('sakata_signal'))
                        ]
                        passed = sum(score_list)
                        passed_counts.append(passed)
                        rule_scores.append((passed / len(score_list)) * 100)
                    sum_df['rule_pct'] = rule_scores
                    sum_df['passed_rules'] = passed_counts
                    
                    # 掟達成率が「66%以上（9項目のうち6項目以上クリア）」の銘柄だけを抽出
                    sum_df = sum_df[sum_df['rule_pct'] >= 65.0]
                    
                    if tactics_mode.startswith("⚔️"): base_res = sum_df.sort_values(['is_db', 'reach_pct'], ascending=[False, False]).head(40)
                    elif tactics_mode.startswith("🛡️"): base_res = sum_df.sort_values(['is_defense', 'reach_pct'], ascending=[False, False]).head(40)
                    else: base_res = sum_df.sort_values('reach_pct', ascending=False).head(40)
                    
                    if base_res.empty: 
                        st.warning("現在の相場に、標的は存在しません。")
                    else:
                        final_results = []
                        for _, r in base_res.iterrows():
                            c = str(r['Code'])
                            api_code = c if len(c) == 5 else c + "0"
                            raw_s = get_single_data(api_code, 1)
                            hist = pd.DataFrame()
                            t_score = 1; t_rank = "C"; t_bg = "#616161"
                            if raw_s:
                                hist = calc_technicals(clean_df(pd.DataFrame(raw_s)))
                                if len(hist) >= 2:
                                    rank, bg, score, _ = get_triage_info(hist.iloc[-1].get('MACD_Hist', 0), hist.iloc[-2].get('MACD_Hist', 0), hist.iloc[-1].get('RSI', 50))
                                    t_score = score; t_rank = rank; t_bg = bg
                                    
                            r_dict = r.to_dict()
                            r_dict['triage_score'] = t_score; r_dict['triage_rank'] = t_rank; r_dict['triage_bg'] = t_bg; r_dict['hist_df'] = hist
                            final_results.append(r_dict)
                            
                        final_df = pd.DataFrame(final_results)
                        
                        if tactics_mode.startswith("⚔️"): final_df = final_df.sort_values(['triage_score', 'is_db', 'reach_pct'], ascending=[False, False, False])
                        elif tactics_mode.startswith("🛡️"): final_df = final_df.sort_values(['triage_score', 'is_defense', 'reach_pct'], ascending=[False, False, False])
                        else: final_df = final_df.sort_values(['triage_score', 'reach_pct'], ascending=[False, False])
                        
                        st.success(f"🎯 スキャン完了: {len(final_df)} 銘柄クリア")
                        st.markdown("#### 📋 コピペ用コード")
                        if 'Code' in final_df.columns: st.code(",".join([str(c)[:4] for c in final_df['Code']]), language="text")

                        for _, r in final_df.iterrows():
                            st.divider()
                            c = str(r['Code']); n = r['CompanyName'] if not pd.isna(r.get('CompanyName')) else f"銘柄 {c[:4]}"
                            
                            scale_val = str(r.get('Scale', ''))
                            if any(x in scale_val for x in ["Core30", "Large70", "Mid400"]):
                                badge = '<span style="background-color: #0d47a1; color: #ffffff; padding: 0.2rem 0.6rem; border-radius: 4px; font-size: 12px; display: inline-block;">🏢 大型/中型 (推奨: 25%押し)</span>'
                            else:
                                badge = '<span style="background-color: #b71c1c; color: #ffffff; padding: 0.2rem 0.6rem; border-radius: 4px; font-size: 12px; display: inline-block;">🚀 小型/新興 (推奨: 50%押し)</span>'
                            
                            triage_badge = f'<span style="background-color: {r["triage_bg"]}; color: #ffffff; padding: 0.2rem 0.6rem; border-radius: 4px; font-size: 13px; display: inline-block; font-weight: bold; margin-left: 0.5rem;">🎯 優先度: {r["triage_rank"]}</span>'
                            
                            st.markdown(f"""
                                <div style="margin-bottom: 0.8rem;">
                                    <h3 style="font-size: clamp(16px, 5vw, 26px); font-weight: bold; margin: 0 0 0.3rem 0; word-wrap: break-word;">({c[:4]}) {n}</h3>
                                    <div style="display: flex; flex-wrap: wrap; gap: 4px; align-items: center;">{badge}{triage_badge}</div>
                                </div>
                            """, unsafe_allow_html=True)
                            
                            for alert in check_event_mines(c): st.warning(alert)
                            if r.get('is_bt_broken', False): st.error("⚠️ 【第一防衛線突破】買値目標を第二防衛線（黄金比等）へ自動シフトしました。")
                            if r['is_db']: st.success("🔥 【激熱(攻め)】三川（ダブルボトム）底打ち反転波形を検知！")
                            if r['is_defense']: st.info("🛡️ 【鉄壁(守り)】下値支持線(サポート)に極接近。損切りリスクが極小の安全圏です。")
                            if pd.notna(r.get('sakata_signal')):
                                if "下落警戒" in str(r['sakata_signal']): st.error(f"🚨 【波形警告】{r['sakata_signal']}")
                                else: st.success(f"🔥 【反転攻勢】{r['sakata_signal']}")
                            
                            lc_val = int(r.get('lc', 0)); bt_val = int(r.get('bt', 0)); high_val = int(r.get('h14', lc_val)); low_val = int(r.get('l14', 0))
                            wave_len = high_val - low_val if low_val > 0 else 0
                            sl5 = int(bt_val * 0.95); sl8 = int(bt_val * 0.92); sl15 = int(bt_val * 0.85)
                            tp20 = int(bt_val * 1.2); tp15 = int(bt_val * 1.15); tp10 = int(bt_val * 1.1); tp5 = int(bt_val * 1.05)
                            
                            daily_pct = r.get('daily_pct', 0); daily_sign = "+" if daily_pct >= 0 else ""

                            hist_df = r.get('hist_df', pd.DataFrame())
                            avg_vol = int(hist_df['Volume'].tail(5).mean()) if not hist_df.empty and 'Volume' in hist_df.columns else 0
                            reach_pct = r.get('reach_pct', 0)
                            passed_rules = int(r.get('passed_rules', 0))
                            rule_pct_val = r.get('rule_pct', 0)

                            sc0, sc0_1, sc0_2, sc1, sc2, sc3, sc4 = st.columns([0.8, 0.8, 0.8, 0.9, 1.1, 1.8, 1.5])
                            sc0.metric("直近高値", f"{high_val:,}円")
                            sc0_1.metric("直近安値", f"{low_val:,}円")
                            sc0_2.metric("上昇幅", f"{wave_len:,}円")
                            sc1.metric("最新終値", f"{lc_val:,}円", f"{daily_sign}{daily_pct*100:.1f}%", delta_color="inverse")
                            
                            html_buy = f"""<div style="font-family: sans-serif; padding-top: 0.2rem;"><div style="font-size: 14px; color: rgba(250, 250, 250, 0.6); padding-bottom: 0.1rem;">🎯 買値目標</div><div style="font-size: 1.8rem; font-weight: bold; color: #FFD700;">{bt_val:,}円</div></div>"""
                            sc2.markdown(html_buy, unsafe_allow_html=True)
                            
                            html_sell = f"""<div style="font-family: sans-serif; padding-top: 0.2rem;"><div style="font-size: 14px; color: rgba(250, 250, 250, 0.6); padding-bottom: 0.1rem;">🎯 売値目標 ＆ 🛡️ 損切目安</div><div style="font-size: 16px;">
                                <span style="display: inline-block; width: 2.5em; color: #ef5350;">20%</span> <span style="color: #ef5350;">{tp20:,}円</span><br>
                                <span style="display: inline-block; width: 2.5em; color: #ef5350;">15%</span> <span style="color: #ef5350;">{tp15:,}円</span> <span style="color: rgba(250, 250, 250, 0.3); margin: 0 4px;">|</span> <span style="display: inline-block; width: 2.8em; color: #26a69a;">-5%</span> <span style="color: #26a69a;">{sl5:,}円</span><br>
                                <span style="display: inline-block; width: 2.5em; color: #ef5350;">10%</span> <span style="color: #ef5350;">{tp10:,}円</span> <span style="color: rgba(250, 250, 250, 0.3); margin: 0 4px;">|</span> <span style="display: inline-block; width: 2.8em; color: #26a69a;">-8%</span> <span style="color: #26a69a;">{sl8:,}円</span><br>
                                <span style="display: inline-block; width: 2.5em; color: #ef5350;">5%</span> <span style="color: #ef5350;">{tp5:,}円</span> <span style="color: rgba(250, 250, 250, 0.3); margin: 0 4px;">|</span> <span style="display: inline-block; width: 2.8em; color: #26a69a;">-15%</span> <span style="color: #26a69a;">{sl15:,}円</span></div></div>"""
                            sc3.markdown(html_sell, unsafe_allow_html=True)
                            
                            # 🔥 意味のあるスコア表示
                            pct_color = "#26a69a" if passed_rules >= 8 else "#FFD700" if passed_rules >= 6 else "#ef5350"
                            html_stats = f"""
                            <div style="display: flex; flex-direction: column; gap: 8px; margin-top: 0.5rem;">
                                <div style="background: rgba(38, 166, 154, 0.1); border-left: 3px solid #26a69a; padding: 4px 8px; border-radius: 4px;">
                                    <span style="font-size: 12px; color: #aaa;">到達度:</span> <strong style="font-size: 15px; color: #fff;">{reach_pct:.1f}%</strong>
                                </div>
                                <div style="background: rgba(255, 255, 255, 0.05); border-left: 3px solid {pct_color}; padding: 4px 8px; border-radius: 4px;">
                                    <span style="font-size: 12px; color: #aaa;">掟適合:</span> <strong style="font-size: 15px; color: {pct_color};">{passed_rules}/9 条件クリア ({rule_pct_val:.0f}%)</strong>
                                </div>
                                <div style="background: rgba(255, 215, 0, 0.1); border-left: 3px solid #FFD700; padding: 4px 8px; border-radius: 4px;">
                                    <span style="font-size: 12px; color: #aaa;">出来高:</span> <strong style="font-size: 15px; color: #fff;">{avg_vol:,} 株</strong>
                                </div>
                            </div>
                            """
                            sc4.markdown(html_stats, unsafe_allow_html=True)
                            
                            st.caption(f"🏢 {r.get('Market','不明')} ｜ 🏭 {r.get('Sector','不明')} ｜ ⏱️ 高値経過: {int(r.get('d_high', 0))}営業日")
                            
                            bt_stats = calc_historical_win_rate(c[:4], st.session_state.push_r, st.session_state.limit_d, st.session_state.bt_tp, st.session_state.bt_sl_i, st.session_state.bt_sl_c, st.session_state.bt_sell_d, tactics_mode)
                            if bt_stats and bt_stats['total'] > 0:
                                wr = bt_stats['win_rate']; ev = bt_stats['exp_val']
                                wr_color = "#ef5350" if wr >= 60 else "#FFD700" if wr >= 50 else "#888888"
                                st.markdown(f"""
                                <div style="background: rgba(255,255,255,0.05); padding: 0.5rem; border-radius: 4px; margin: 0.5rem 0;">
                                    <span style="font-size: 12px; color: #aaa;">📊 過去2年の掟適合率 ({bt_stats['total']}戦):</span>
                                    <strong style="color: {wr_color}; font-size: 16px; margin-left: 8px;">勝率 {wr:.1f}%</strong>
                                    <span style="font-size: 12px; color: #aaa; margin-left: 12px;">1株期待値:</span>
                                    <strong style="color: {'#ef5350' if ev > 0 else '#26a69a'}; font-size: 16px; margin-left: 8px;">{ev:+.1f}円</strong>
                                </div>
                                """, unsafe_allow_html=True)

                            if not hist_df.empty:
                                st.markdown(render_technical_radar(hist_df, bt_val, st.session_state.bt_tp), unsafe_allow_html=True)
                                draw_chart(hist_df, bt_val, tp15=tp15)
                            
# ------------------------------------------
# Tab 2: GC初動強襲レーダー
# ------------------------------------------
with tab2:
    render_macro_board()
    st.markdown('### ⚡ GC（ゴールデンクロス）初動強襲レーダー')
    st.warning("⚠️ 鉄の掟（50%押し）のフィルターを解除し、純粋なトレンド初動（MACD GC）を検知する遊撃部隊用レーダーです。")
    
    if st.button("⚡ GC遊撃部隊を発進させる"):
        with st.spinner("全軍からMACDゴールデンクロス直後の銘柄を抽出中..."):
            raw = get_hist_data_cached()
            if not raw: 
                st.error("データ取得に失敗しました。")
            else:
                df = clean_df(pd.DataFrame(raw)).dropna(subset=['AdjC', 'AdjH', 'AdjL']).sort_values(['Code', 'Date'])
                df_30 = df.groupby('Code').tail(30)
                
                valid_counts = df_30.groupby('Code').size()
                df_30 = df_30[df_30['Code'].isin(valid_counts[valid_counts >= 26].index)]
                latest_prices = df_30.groupby('Code')['AdjC'].last()
                df_30 = df_30[df_30['Code'].isin(latest_prices[(latest_prices >= f1_min) & (latest_prices <= f1_max)].index)]
                
                results_gc = []
                for code, group in df_30.groupby('Code'):
                    df_calc = calc_technicals(group)
                    avg_vol = df_calc.tail(5).get('Volume', pd.Series([0])).mean()
                    if avg_vol < 50000: continue
                    
                    latest = df_calc.iloc[-1]; prev = df_calc.iloc[-2]
                    lc = latest['AdjC']; ma25 = latest['MA25']
                    macd = latest['MACD']; signal = latest['MACD_Signal']
                    macd_prev = prev['MACD']; signal_prev = prev['MACD_Signal']
                    rsi = latest.get('RSI', 50)
                    
                    is_gc = (macd > signal) and (macd_prev <= signal_prev)
                    is_uptrend = (lc >= ma25) and (rsi < 70)
                    
                    if is_gc and is_uptrend:
                        c_name = "不明"; c_sector = "不明"; c_market = "不明"; c_scale = ""
                        if not master_df.empty:
                            m_row = master_df[master_df['Code'] == code]
                            if not m_row.empty:
                                c_name = m_row.iloc[0]['CompanyName']
                                c_sector = m_row.iloc[0].get('Sector', '不明')
                                c_market = m_row.iloc[0].get('Market', '不明')
                                c_scale = m_row.iloc[0].get('Scale', '')
                        
                        if f7_ex_etf and (c_sector == '-' or bool(re.search("ETF|投信|ブル|ベア|REIT|ﾘｰﾄ", str(c_name), re.IGNORECASE))): 
                            continue
                            
                        # 🔥 優先度スコアを計算して格納
                        _, _, t_score, _ = get_triage_info(latest.get('MACD_Hist', 0), prev.get('MACD_Hist', 0), rsi)
                            
                        results_gc.append({
                            'Code': code, 'Name': c_name, 'Market': c_market, 'Sector': c_sector, 'Scale': c_scale,
                            'lc': lc, 'MA25': ma25, 'RSI': rsi, 
                            'MACD_Hist': latest.get('MACD_Hist', 0), 'MACD_Hist_prev': prev.get('MACD_Hist', 0),
                            'Vol': avg_vol, 'df_chart': df_calc, 'trigger': latest['AdjH'] * 1.01,
                            'triage_score': t_score
                        })
                
                if not results_gc:
                    st.info("本日の市場に、条件を満たすGC初動銘柄はありませんでした。")
                else:
                    st.success(f"⚡ 抽出完了: {len(results_gc)} 銘柄のGC初動を捕捉。")
                    
                    # 🚨 【改修】判定結果（S/A/B/Cスコア）を最優先でソート
                    res_df_gc = pd.DataFrame(results_gc).sort_values(['triage_score', 'Vol'], ascending=[False, False])
                    
                    st.markdown("#### 📋 コピペ用コード (GC遊撃部隊)")
                    if 'Code' in res_df_gc.columns:
                        copy_codes_gc = ",".join([str(c)[:4] for c in res_df_gc['Code']])
                        st.code(copy_codes_gc, language="text")

                    for _, r in res_df_gc.iterrows():
                        st.divider()
                        c = str(r['Code']); n = str(r['Name'])
                        
                        scale_val = str(r.get('Scale', ''))
                        if any(x in scale_val for x in ["Core30", "Large70", "Mid400"]):
                            badge = '<span style="background-color: #0d47a1; color: #ffffff; padding: 0.2rem 0.6rem; border-radius: 4px; font-size: 12px; display: inline-block;">🏢 大型/中型</span>'
                        else:
                            badge = '<span style="background-color: #b71c1c; color: #ffffff; padding: 0.2rem 0.6rem; border-radius: 4px; font-size: 12px; display: inline-block;">🚀 小型/新興</span>'
                        
                        rank, bg, score, _ = get_triage_info(r['MACD_Hist'], r['MACD_Hist_prev'], r['RSI'])
                        triage_badge = f'<span style="background-color: {bg}; color: #ffffff; padding: 0.2rem 0.6rem; border-radius: 4px; font-size: 13px; display: inline-block; font-weight: bold; margin-left: 0.5rem;">🎯 優先度: {rank}</span>'
                        
                        st.markdown(f"""
                            <div style="margin-bottom: 0.8rem;">
                                <h3 style="font-size: clamp(16px, 5vw, 26px); font-weight: bold; margin: 0 0 0.3rem 0; word-wrap: break-word;">({c[:4]}) {n} <span style='background:#ef5350;color:#fff;padding:2px 8px;border-radius:4px;font-size:14px;vertical-align:middle;'>⚡ GC初動</span></h3>
                                <div style="display: flex; flex-wrap: wrap; gap: 4px; align-items: center;">{badge}{triage_badge}</div>
                            </div>
                        """, unsafe_allow_html=True)
                        
                        for alert in check_event_mines(c): st.warning(alert)
                        st.caption(f"🏢 {r.get('Market','不明')} ｜ 🏭 {r.get('Sector','不明')} ｜ 📊 平均出来高: {int(r.get('Vol', 0)):,}株")
                        
                        lc_val = int(r['lc']); trigger_val = int(r['trigger']); ma25_val = int(r['MA25'])
                        tp10 = int(trigger_val * 1.10); tp8 = int(trigger_val * 1.08); sl4 = int(trigger_val * 0.96)
                        
                        sc1, sc2, sc3, sc4 = st.columns([1, 1.2, 1.5, 0.8])
                        sc1.metric("最新終値", f"{lc_val:,}円")
                        
                        html_trigger = f"""<div style="font-family: sans-serif; padding-top: 0.2rem;"><div style="font-size: 14px; color: rgba(250, 250, 250, 0.6); padding-bottom: 0.1rem;">🎯 追撃トリガー (逆指値)</div><div style="font-size: 1.8rem; font-weight: bold; color: #ef5350;">{trigger_val:,}円</div></div>"""
                        sc2.markdown(html_trigger, unsafe_allow_html=True)
                        
                        html_sell_gc = f"""<div style="font-family: sans-serif; padding-top: 0.2rem;"><div style="font-size: 14px; color: rgba(250, 250, 250, 0.6); padding-bottom: 0.1rem;">🎯 短期利確 ＆ 🛡️ 撤退ライン</div><div style="font-size: 16px;">
                            <span style="display: inline-block; width: 2.5em; color: #ef5350;">10%</span> <span style="color: #ef5350;">{tp10:,}円</span><br>
                            <span style="display: inline-block; width: 2.5em; color: #ef5350;">8%</span> <span style="color: #ef5350;">{tp8:,}円</span> <span style="color: rgba(250, 250, 250, 0.3); margin: 0 4px;">|</span> <span style="display: inline-block; width: 2.8em; color: #26a69a;">-4%</span> <span style="color: #26a69a;">{sl4:,}円</span></div></div>"""
                        sc3.markdown(html_sell_gc, unsafe_allow_html=True)
                        
                        sc4.metric("防衛線(25日)", f"{ma25_val:,}円")
                        st.markdown(render_technical_radar(r['df_chart'], r['lc'], 10), unsafe_allow_html=True)
                        draw_chart(r['df_chart'], trigger_val, tp10=tp10)

# ------------------------------------------
# Tab 3: 高高度モニター（イナゴタワー追跡）
# ------------------------------------------
with tab3:
    st.markdown('### 🛸 高高度観測モニター（ブレイクアウト・順張り探知）')
    st.warning("⚠️ 【発砲厳禁】すでに空高く飛んでいるモメンタム銘柄を追跡し、墜落を安全圏から観察・学習するための研究用レーダーです。実弾装填は推奨しません。")
    
    if st.button("🚀 観測機を発進させる（ブレイクアウト全軍スキャン）"):
        with st.spinner("成層圏の熱源（ブレイクアウト・高値更新銘柄）を探索中..."):
            raw = get_hist_data_cached()
            if not raw: 
                st.error("データの取得に失敗しました。")
            else:
                df = clean_df(pd.DataFrame(raw)).dropna(subset=['AdjC', 'AdjH', 'AdjL']).sort_values(['Code', 'Date'])
                df_30 = df.groupby('Code').tail(30)
                
                # 生存フィルター（処理の高速化）
                valid = df_30.groupby('Code').size()
                df_30 = df_30[df_30['Code'].isin(valid[valid >= 15].index)]
                
                latest_prices = df_30.groupby('Code')['AdjC'].last()
                valid_price_codes = latest_prices[(latest_prices >= f1_min) & (latest_prices <= f1_max)].index
                df_30 = df_30[df_30['Code'].isin(valid_price_codes)]
                
                results_t6 = []
                for code, group in df_30.groupby('Code'):
                    df_calc = group.copy()
                    df_calc['MA5'] = df_calc['AdjC'].rolling(window=5).mean()
                    latest = df_calc.iloc[-1]
                    prev = df_calc.iloc[-2]
                    
                    lc = latest['AdjC']
                    ma5 = latest['MA5']
                    h14 = df_calc.tail(14)['AdjH'].max()
                    daily_pct = (lc / prev['AdjC']) - 1 if prev['AdjC'] > 0 else 0
                    
                    # 🚀 純粋なプライスアクション・ブレイクアウト判定
                    if (lc > ma5) and (lc >= h14 * 0.95) and (daily_pct >= 0.03):
                        c_name = "不明"; c_market = "不明"; c_sector = "不明"; c_scale = ""
                        if not master_df.empty:
                            m_row = master_df[master_df['Code'] == code]
                            if not m_row.empty:
                                c_name = m_row.iloc[0]['CompanyName']
                                c_market = m_row.iloc[0].get('Market', '不明')
                                c_sector = m_row.iloc[0].get('Sector', '不明')
                                c_scale = m_row.iloc[0].get('Scale', '')
                                
                        # ETF等の除外
                        if f7_ex_etf and (c_sector == '-' or bool(re.search("ETF|投信|ブル|ベア|REIT|ﾘｰﾄ", str(c_name), re.IGNORECASE))): 
                            continue
                            
                        g_tech = calc_technicals(group.copy())
                        rsi = g_tech.iloc[-1].get('RSI', 50)
                        
                        results_t6.append({
                            'Code': code, 'Name': c_name, 'Market': c_market, 'Sector': c_sector, 'Scale': c_scale,
                            'lc': lc, 'MA5': ma5, 'h14': h14, 'RSI': rsi, 'daily_pct': daily_pct,
                            'df_chart': g_tech
                        })
                        
                if not results_t6: 
                    st.info("現在、成層圏（ブレイクアウト条件合致）を飛行中の機体は観測されませんでした。")
                else:
                    st.success(f"🛸 観測完了: {len(results_t6)} 機の熱源（ブレイクアウト）を捕捉しました。")
                    res_df_t6 = pd.DataFrame(results_t6).sort_values('daily_pct', ascending=False)
                    
                    # 📋 復元：コピペ用コード枠
                    st.markdown("#### 📋 コピペ用コード (高高度観測部隊)")
                    if 'Code' in res_df_t6.columns:
                        copy_codes_t6 = ",".join([str(c)[:4] for c in res_df_t6['Code']])
                        st.code(copy_codes_t6, language="text")

                    for _, r in res_df_t6.iterrows():
                        st.divider()
                        c = str(r['Code']); n = str(r['Name'])
                        
                        # 🏢 復元：規模バッジ
                        scale_val = str(r.get('Scale', ''))
                        if any(x in scale_val for x in ["Core30", "Large70", "Mid400"]):
                            badge = '<span style="background-color: #0d47a1; color: #ffffff; padding: 0.2rem 0.6rem; border-radius: 4px; font-size: 12px; display: inline-block;">🏢 大型/中型</span>'
                        else:
                            badge = '<span style="background-color: #b71c1c; color: #ffffff; padding: 0.2rem 0.6rem; border-radius: 4px; font-size: 12px; display: inline-block;">🚀 小型/新興</span>'
                            
                        st.markdown(f"""
                            <div style="margin-bottom: 0.8rem;">
                                <h3 style="font-size: clamp(16px, 5vw, 26px); font-weight: bold; margin: 0 0 0.3rem 0; color: #e0e0e0;">({c[:4]}) {n}</h3>
                                <div style="display: flex; flex-wrap: wrap; gap: 4px; align-items: center;">
                                    {badge}
                                    <span style="background-color: #616161; color: #ffffff; padding: 0.2rem 0.6rem; border-radius: 4px; font-size: 13px; font-weight: bold;">🛸 観測対象 (本日 +{r['daily_pct']*100:.1f}% 飛翔)</span>
                                </div>
                            </div>
                        """, unsafe_allow_html=True)
                        
                        # 💣 地雷警戒アラート
                        for alert in check_event_mines(c): st.warning(alert)
                        
                        # 🏢 復元：業種・市場データ
                        st.caption(f"🏢 {r.get('Market','不明')} ｜ 🏭 {r.get('Sector','不明')}")
                        
                        col1, col2, col3, col4 = st.columns(4)
                        col1.metric("最新終値", f"{int(r['lc']):,}円", f"+{r['daily_pct']*100:.1f}%")
                        col2.metric("5日移動平均線", f"{int(r['MA5']):,}円", "支持線(割ると墜落)")
                        col3.metric("直近14日高値", f"{int(r['h14']):,}円", "ブレイクライン")
                        col4.metric("過熱度 (RSI)", f"{r['RSI']:.1f}%", "※参考値")
                        
                        st.markdown(render_technical_radar(r['df_chart'], r['lc'], 10), unsafe_allow_html=True)
                        
                        # --- 🎯 復元：高高度専用ズームチャート ---
                        draw_chart_t6(r['df_chart'], r['lc'], int(r['lc']*1.05), int(r['lc']*1.10), int(r['lc']*1.15))
                        
                        st.caption("【観測ポイント】紫色の線（5日線）に沿ってどこまで上昇を続けるか、またはいつ陰線を叩きつけて墜落するかを観察してください。")

# ------------------------------------------
# Tab 4: 精密スコープ照準（個別局地戦）
# ------------------------------------------
with tab4:
    render_macro_board()
    st.markdown('### 🎯 精密スコープ照準（局地戦スキャン）')
    st.caption("※指定された銘柄すべての押し目ラインを計算し、優先度（S/A/B/C）順に精密に解剖します。")
    
    target_codes_str = st.text_area("標的コード（複数可、カンマや改行区切り）", value="7203\n8604", height=100)
    
    if st.button(f"🔫 指定銘柄 一斉スキャン ({st.session_state.sidebar_tactics.split()[0]})") and target_codes_str:
        t_codes = list(dict.fromkeys([c.upper() for c in re.findall(r'(?<![a-zA-Z0-9])[a-zA-Z0-9]{4}(?![a-zA-Z0-9])', target_codes_str)]))
        if not t_codes: 
            st.warning("有効なコードが見つかりません。")
        else:
            with st.spinner(f"{len(t_codes)} 銘柄の弾道を計算中..."):
                results_t4 = []
                for c in t_codes:
                    raw_s = get_single_data(c + "0", 1)
                    if raw_s:
                        df_s = clean_df(pd.DataFrame(raw_s))
                        if df_s.empty: continue
                        hist = calc_technicals(df_s)
                        if len(hist) < 14: continue
                        
                        lc_val = int(hist.iloc[-1]['AdjC'])
                        h14_val = int(hist.tail(14)['AdjH'].max())
                        l14_val = int(hist.tail(14)['AdjL'].min())
                        if l14_val <= 0 or pd.isna(h14_val): continue
                        
                        hist_30 = hist.tail(30)
                        hist_14 = hist.tail(14)
                        hist_past = hist.iloc[:-30] if len(hist) > 30 else pd.DataFrame()

                        l30_val = hist_30['AdjL'].min()
                        omax_val = hist_past['AdjH'].max() if not hist_past.empty else np.nan
                        omin_val = hist_past['AdjL'].min() if not hist_past.empty else np.nan

                        r30 = lc_val / l30_val if l30_val > 0 else 0
                        r14 = h14_val / l14_val if l14_val > 0 else 0
                        ldrop = ((lc_val / omax_val) - 1) * 100 if pd.notna(omax_val) and omax_val > 0 else 0
                        lrise = lc_val / omin_val if pd.notna(omin_val) and omin_val > 0 else 0
                        
                        idx_max = hist_14['AdjH'].idxmax()
                        d_high = len(hist_14[hist_14['Date'] > hist_14.loc[idx_max, 'Date']]) if pd.notna(idx_max) else 0

                        is_dt = check_double_top(hist_30)
                        is_hs = check_head_shoulders(hist_30)
                        
                        wave_len = h14_val - l14_val
                        bt_primary = h14_val - (wave_len * (st.session_state.push_r / 100.0))
                        shift_ratio = 0.618 if st.session_state.push_r >= 40 else (st.session_state.push_r / 100.0 + 0.15)
                        bt_secondary = h14_val - (wave_len * shift_ratio)
                        
                        is_bt_broken = lc_val < bt_primary
                        bt_val = int(bt_secondary if is_bt_broken else bt_primary)
                        
                        denom = h14_val - bt_val
                        reach_pct = ((h14_val - lc_val) / denom * 100) if denom > 0 else 0
                        
                        # 🎯 【修正】意味のある「掟の採点（スコアリング）」
                        sakata_sig = check_sakata_patterns(hist_30)
                        score_list = [
                            (f1_min <= lc_val <= f1_max),
                            (r30 <= f2_m30),
                            (ldrop >= f3_drop),
                            (lrise <= f4_mlong) or (lrise == 0),
                            (f9_min14 <= r14 <= f9_max14),
                            (d_high <= st.session_state.limit_d),
                            (bt_val * 0.85 <= lc_val <= bt_val * 1.35),
                            (not is_dt and not is_hs),
                            (not pd.notna(sakata_sig)) or ("下落警戒" not in str(sakata_sig))
                        ]
                        passed_rules = sum(score_list)
                        rule_pct = (passed_rules / len(score_list)) * 100
                        
                        latest_c = hist.iloc[-1]; prev_c = hist.iloc[-2]
                        rsi_val = latest_c.get('RSI', 50)
                        macd_h = latest_c.get('MACD_Hist', 0); macd_h_prev = prev_c.get('MACD_Hist', 0)
                        
                        rank, bg, score, macd_t = get_triage_info(macd_h, macd_h_prev, rsi_val)
                        
                        results_t4.append({
                            'code': c, 'lc_val': lc_val, 'h14_val': h14_val, 'l14_val': l14_val, 'wave_len': wave_len,
                            'bt_val': bt_val, 'is_bt_broken': is_bt_broken, 'reach_pct': reach_pct, 
                            'rule_pct': rule_pct, 'passed_rules': passed_rules,
                            'hist': hist, 'triage_score': score, 'rank': rank, 'bg': bg, 'macd_t': macd_t, 'prev_c': prev_c
                        })
                
                results_t4.sort(key=lambda x: (x['triage_score'], x['reach_pct']), reverse=True)
                
                for r in results_t4:
                    c = r['code']; hist = r['hist']
                    
                    c_name = f"銘柄 {c}"; c_market = "不明"; c_sector = "不明"; c_scale = ""
                    if not master_df.empty:
                        m_row = master_df[master_df['Code'] == c + "0"]
                        if not m_row.empty:
                            c_name = m_row.iloc[0]['CompanyName']
                            c_market = m_row.iloc[0].get('Market', '不明')
                            c_sector = m_row.iloc[0].get('Sector', '不明')
                            c_scale = m_row.iloc[0].get('Scale', '')
                            
                    scale_val = str(c_scale)
                    if any(x in scale_val for x in ["Core30", "Large70", "Mid400"]):
                        badge = '<span style="background-color: #0d47a1; color: #ffffff; padding: 0.2rem 0.6rem; border-radius: 4px; font-size: 12px; display: inline-block;">🏢 大型/中型</span>'
                    else:
                        badge = '<span style="background-color: #b71c1c; color: #ffffff; padding: 0.2rem 0.6rem; border-radius: 4px; font-size: 12px; display: inline-block;">🚀 小型/新興</span>'
                        
                    triage_badge = f'<span style="background-color: {r["bg"]}; color: #ffffff; padding: 0.2rem 0.6rem; border-radius: 4px; font-size: 13px; display: inline-block; font-weight: bold; margin-left: 0.5rem;">🎯 優先度: {r["rank"]}</span>'
                    
                    st.divider()
                    st.markdown(f"""
                        <div style="margin-bottom: 0.8rem;">
                            <h3 style="font-size: clamp(16px, 5vw, 26px); font-weight: bold; margin: 0 0 0.3rem 0; word-wrap: break-word;">({c[:4]}) {c_name}</h3>
                            <div style="display: flex; flex-wrap: wrap; gap: 4px; align-items: center;">{badge}{triage_badge}</div>
                        </div>
                    """, unsafe_allow_html=True)
                    
                    if r['macd_t'] == "GC直後":
                        st.markdown("<div style='background: linear-gradient(45deg, #b71c1c, #ff5722); color: white; padding: 0.5rem 1rem; border-radius: 6px; font-weight: 900; font-size: 1.1rem; margin-bottom: 0.8rem; border-left: 6px solid #ffeb3b; box-shadow: 0 4px 6px rgba(255,0,0,0.3);'>🔥🔥🔥 【激熱】MACD ゴールデンクロス（GC）発動中！強烈な上昇モメンタムを検知しました！ 🔥🔥🔥</div>", unsafe_allow_html=True)
                    
                    for alert in check_event_mines(c): st.warning(alert)
                    if r['is_bt_broken']: st.error("⚠️ 【第一防衛線突破】買値目標を第二防衛線（黄金比等）へ自動シフトしました。")
                    
                    st.caption(f"🏢 {c_market} ｜ 🏭 {c_sector}")
                    
                    bt_val = r['bt_val']; lc_val = r['lc_val']
                    sl5 = int(bt_val * 0.95); sl8 = int(bt_val * 0.92); sl15 = int(bt_val * 0.85)
                    tp20 = int(bt_val * 1.2); tp15 = int(bt_val * 1.15); tp10 = int(bt_val * 1.1); tp5 = int(bt_val * 1.05)
                    
                    daily_pct = (lc_val / r['prev_c']['AdjC']) - 1 if r['prev_c']['AdjC'] > 0 else 0
                    daily_sign = "+" if daily_pct >= 0 else ""

                    avg_vol = int(hist['Volume'].tail(5).mean()) if not hist.empty and 'Volume' in hist.columns else 0
                    reach_pct = r['reach_pct']
                    passed_rules = r['passed_rules']
                    rule_pct_val = r['rule_pct']

                    sc0, sc0_1, sc0_2, sc1, sc2, sc3, sc4 = st.columns([0.8, 0.8, 0.8, 0.9, 1.1, 1.8, 1.5])
                    sc0.metric("直近高値", f"{r['h14_val']:,}円")
                    sc0_1.metric("直近安値", f"{r['l14_val']:,}円")
                    sc0_2.metric("上昇幅", f"{r['wave_len']:,}円")
                    sc1.metric("最新終値", f"{lc_val:,}円", f"{daily_sign}{daily_pct*100:.1f}%", delta_color="inverse")
                    
                    html_buy = f"""<div style="font-family: sans-serif; padding-top: 0.2rem;"><div style="font-size: 14px; color: rgba(250, 250, 250, 0.6); padding-bottom: 0.1rem;">🎯 買値目標</div><div style="font-size: 1.8rem; font-weight: bold; color: #FFD700;">{bt_val:,}円</div></div>"""
                    sc2.markdown(html_buy, unsafe_allow_html=True)
                    
                    html_sell = f"""<div style="font-family: sans-serif; padding-top: 0.2rem;"><div style="font-size: 14px; color: rgba(250, 250, 250, 0.6); padding-bottom: 0.1rem;">🎯 売値目標 ＆ 🛡️ 損切目安</div><div style="font-size: 16px;">
                        <span style="display: inline-block; width: 2.5em; color: #ef5350;">20%</span> <span style="color: #ef5350;">{tp20:,}円</span><br>
                        <span style="display: inline-block; width: 2.5em; color: #ef5350;">15%</span> <span style="color: #ef5350;">{tp15:,}円</span> <span style="color: rgba(250, 250, 250, 0.3); margin: 0 4px;">|</span> <span style="display: inline-block; width: 2.8em; color: #26a69a;">-5%</span> <span style="color: #26a69a;">{sl5:,}円</span><br>
                        <span style="display: inline-block; width: 2.5em; color: #ef5350;">10%</span> <span style="color: #ef5350;">{tp10:,}円</span> <span style="color: rgba(250, 250, 250, 0.3); margin: 0 4px;">|</span> <span style="display: inline-block; width: 2.8em; color: #26a69a;">-8%</span> <span style="color: #26a69a;">{sl8:,}円</span><br>
                        <span style="display: inline-block; width: 2.5em; color: #ef5350;">5%</span> <span style="color: #ef5350;">{tp5:,}円</span> <span style="color: rgba(250, 250, 250, 0.3); margin: 0 4px;">|</span> <span style="display: inline-block; width: 2.8em; color: #26a69a;">-15%</span> <span style="color: #26a69a;">{sl15:,}円</span></div></div>"""
                    sc3.markdown(html_sell, unsafe_allow_html=True)
                    
                    # 🔥 意味のあるスコア表示
                    pct_color = "#26a69a" if passed_rules >= 8 else "#FFD700" if passed_rules >= 6 else "#ef5350"
                    html_stats = f"""
                    <div style="display: flex; flex-direction: column; gap: 8px; margin-top: 0.5rem;">
                        <div style="background: rgba(38, 166, 154, 0.1); border-left: 3px solid #26a69a; padding: 4px 8px; border-radius: 4px;">
                            <span style="font-size: 12px; color: #aaa;">到達度:</span> <strong style="font-size: 15px; color: #fff;">{reach_pct:.1f}%</strong>
                        </div>
                        <div style="background: rgba(255, 255, 255, 0.05); border-left: 3px solid {pct_color}; padding: 4px 8px; border-radius: 4px;">
                            <span style="font-size: 12px; color: #aaa;">掟適合:</span> <strong style="font-size: 15px; color: {pct_color};">{passed_rules}/9 条件クリア ({rule_pct_val:.0f}%)</strong>
                        </div>
                        <div style="background: rgba(255, 215, 0, 0.1); border-left: 3px solid #FFD700; padding: 4px 8px; border-radius: 4px;">
                            <span style="font-size: 12px; color: #aaa;">出来高:</span> <strong style="font-size: 15px; color: #fff;">{avg_vol:,} 株</strong>
                        </div>
                    </div>
                    """
                    sc4.markdown(html_stats, unsafe_allow_html=True)
                    
                    st.markdown(render_technical_radar(hist, bt_val, st.session_state.bt_tp), unsafe_allow_html=True)
                    draw_chart(hist, bt_val, tp15=tp15)

# ------------------------------------------
# Tab 5: 戦術シミュレータ（デュアル・バックテスト）
# ------------------------------------------
with tab5:
    st.markdown('### ⚙️ 戦術シミュレータ（2年間のバックテスト）')
    
    bt_mode = st.radio("🔍 検証する戦術を選択してください", ["🌐 【待伏】鉄の掟（50%押し）", "⚡ 【強襲】GCブレイクアウト（高値+1%トリガー）"], horizontal=True)
    
    col_1, col_2 = st.columns([2, 1])
    with col_1: 
        bt_c_in = st.text_area("検証コード（複数可、カンマや改行区切り）", value="6614\n4427", height=100)
    with col_2:
        if "待伏" in bt_mode:
            st.info("※左サイドバーの「🎯 買いルール」「🛡️ 売りルール」の設定値を用いてシミュレーションを実行します。")
        else:
            st.info("※強襲モード専用設定（裏側で固定）\n・利確: +8%\n・損切: -4%\n・期限: 5営業日\n・トリガー: GC点灯日の高値+1%")
            bt_tp_gc = 8.0; bt_sl_gc = 4.0; bt_limit_gc = 5

    if st.button(f"🔥 一括バックテスト実行 ({bt_mode.split('】')[0]}】モード)") and bt_c_in:
        t_codes = list(dict.fromkeys([c.upper() for c in re.findall(r'(?<![a-zA-Z0-9])[a-zA-Z0-9]{4}(?![a-zA-Z0-9])', bt_c_in)]))
        if not t_codes: 
            st.warning("有効なコードが見つかりません。")
        else:
            all_t = []; b_bar = st.progress(0, "仮想売買中...")
            for idx, c in enumerate(t_codes):
                raw = get_single_data(c + "0", 2) # 過去2年
                if raw:
                    df = clean_df(pd.DataFrame(raw)).dropna(subset=['AdjO', 'AdjH', 'AdjL', 'AdjC']).reset_index(drop=True)
                    pos = None
                    
                    if "待伏" in bt_mode:
                        # 🌐 待伏モードのバックテストロジック
                        for i in range(30, len(df)):
                            td = df.iloc[i]
                            if pos is None:
                                win_14 = df.iloc[i-14:i]
                                win_30 = df.iloc[i-30:i]
                                rh = win_14['AdjH'].max()
                                rl = win_14['AdjL'].min()
                                if pd.isna(rh) or pd.isna(rl) or rl <= 0: continue
                                
                                h_d = len(win_14[win_14['Date'] > win_14.loc[win_14['AdjH'].idxmax(), 'Date']])
                                if (1.3 <= rh/rl <= 2.0) and (h_d <= st.session_state.limit_d):
                                    if check_double_top(win_30) or check_head_shoulders(win_30): continue
                                    targ = rh - ((rh - rl) * (st.session_state.push_r / 100.0))
                                    if td['AdjL'] <= targ: 
                                        pos = {'b_i': i, 'b_d': td['Date'], 'b_p': min(td['AdjO'], targ)}
                            else:
                                bp = round(pos['b_p'], 1)
                                held = i - pos['b_i']
                                sp = 0
                                rsn = ""
                                
                                sl_i = bp * (1 - (st.session_state.bt_sl_i / 100.0))
                                tp = bp * (1 + (st.session_state.bt_tp / 100.0))
                                sl_c = bp * (1 - (st.session_state.bt_sl_c / 100.0))
                                
                                if td['AdjL'] <= sl_i: 
                                    sp = min(td['AdjO'], sl_i); rsn = f"損切(-{st.session_state.bt_sl_i}%)"
                                elif td['AdjH'] >= tp: 
                                    sp = max(td['AdjO'], tp); rsn = f"利確(+{st.session_state.bt_tp}%)"
                                elif td['AdjC'] <= sl_c: 
                                    sp = td['AdjC']; rsn = f"損切終値(-{st.session_state.bt_sl_c}%)"
                                elif held >= st.session_state.bt_sell_d: 
                                    sp = td['AdjC']; rsn = f"時間切れ({st.session_state.bt_sell_d}日)"
                                    
                                if rsn:
                                    all_t.append({'銘柄': c, '購入日': pos['b_d'].strftime('%Y-%m-%d'), '決済日': td['Date'].strftime('%Y-%m-%d'), '保有日数': held, '買値(円)': bp, '売値(円)': round(sp,1), '損益額(円)': int((sp - bp) * st.session_state.bt_lot), '決済理由': rsn})
                                    pos = None
                    else:
                        # ⚡ 強襲GCモードのバックテストロジック
                        df_tech = calc_technicals(df)
                        for i in range(30, len(df_tech)):
                            td = df_tech.iloc[i]
                            if pos is None:
                                latest = df_tech.iloc[i-1]
                                prev = df_tech.iloc[i-2]
                                
                                is_gc = (latest['MACD'] > latest['MACD_Signal']) and (prev['MACD'] <= prev['MACD_Signal'])
                                is_uptrend = (latest['AdjC'] >= latest['MA25']) and (latest.get('RSI', 50) < 70)
                                
                                if is_gc and is_uptrend:
                                    # トリガー：GC点灯日の高値 + 1%
                                    pos = {'wait_i': i, 'trigger': latest['AdjH'] * 1.01}
                            elif 'wait_i' in pos:
                                if i - pos['wait_i'] > 3: 
                                    pos = None # 3日でトリガーが引かれなければキャンセル（モメンタム消滅）
                                elif td['AdjH'] >= pos['trigger']: 
                                    # トリガー到達でエントリー（窓開け対応で始値とトリガーの高い方）
                                    pos = {'b_i': i, 'b_d': td['Date'], 'b_p': max(td['AdjO'], pos['trigger'])}
                            elif 'b_i' in pos:
                                bp = round(pos['b_p'], 1)
                                held = i - pos['b_i']
                                sp = 0
                                rsn = ""
                                
                                sl = bp * (1 - (bt_sl_gc / 100.0))
                                tp = bp * (1 + (bt_tp_gc / 100.0))
                                
                                if td['AdjL'] <= sl: 
                                    sp = min(td['AdjO'], sl); rsn = f"損切(-{bt_sl_gc}%)"
                                elif td['AdjH'] >= tp: 
                                    sp = max(td['AdjO'], tp); rsn = f"利確(+{bt_tp_gc}%)"
                                elif held >= bt_limit_gc: 
                                    sp = td['AdjC']; rsn = f"時間切れ({bt_limit_gc}日)"
                                    
                                if rsn:
                                    all_t.append({'銘柄': c, '購入日': pos['b_d'].strftime('%Y-%m-%d'), '決済日': td['Date'].strftime('%Y-%m-%d'), '保有日数': held, '買値(円)': bp, '売値(円)': round(sp,1), '損益額(円)': int((sp - bp) * st.session_state.bt_lot), '決済理由': rsn})
                                    pos = None

                b_bar.progress((idx + 1) / len(t_codes))
            b_bar.empty()
            
            if not all_t: 
                st.warning("指定された期間・条件に合致するトレードはありませんでした。")
            else:
                tdf = pd.DataFrame(all_t)
                tot = len(tdf)
                wins = len(tdf[tdf['損益額(円)'] > 0])
                n_prof = tdf['損益額(円)'].sum()
                sprof = tdf[tdf['損益額(円)'] > 0]['損益額(円)'].sum()
                sloss = abs(tdf[tdf['損益額(円)'] <= 0]['損益額(円)'].sum())
                pf = round(sprof / sloss, 2) if sloss > 0 else 'inf'
                
                st.markdown(f"### 💰 総合利益額: {n_prof:,} 円")
                m1, m2, m3, m4 = st.columns(4)
                m1.metric("トレード回数", f"{tot} 回")
                m2.metric("勝率", f"{round((wins/tot)*100,1)} %")
                m3.metric("平均損益額", f"{int(n_prof/tot):,} 円")
                m4.metric("プロフィットファクター", f"{pf}")
                
                st.markdown("#### 📜 詳細交戦記録（トレード履歴）")
                st.dataframe(tdf, use_container_width=True, hide_index=True)

# ------------------------------------------
# Tab 6: IFD-OCO 10日ルール監視（JPXカレンダー準拠）
# ------------------------------------------
with tab6:
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
# Tab 7: 事後任務報告（AAR）
# ------------------------------------------
with tab7:
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
