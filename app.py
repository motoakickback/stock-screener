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

    rank = "C（条件外・監視）👁️"; bg = "#616161"; score = 1
    if macd_t == "下落継続" or rsi >= 70: rank = "圏外（手出し無用）🚫"; bg = "#d32f2f"; score = 0
    elif macd_t == "GC直後" and rsi <= 50: rank = "S（即時狙撃）🔥"; bg = "#2e7d32"; score = 4
    elif macd_t == "減衰" and rsi <= 30: rank = "A（罠の設置）🪤"; bg = "#0288d1"; score = 3
    elif macd_t == "上昇拡大" and 50 <= rsi <= 65: rank = "B（順張り警戒）📈"; bg = "#ed6c02"; score = 2
    return rank, bg, score, macd_t

def render_technical_radar(df, buy_price, tp_pct):
    if df.empty or len(df) < 2: return ""
    latest = df.iloc[-1]; prev = df.iloc[-2]
    rsi = latest.get('RSI', 50); macd_hist = latest.get('MACD_Hist', 0); macd_hist_prev = prev.get('MACD_Hist', 0); atr = latest.get('ATR', 0)
    rsi_color = "#ef5350" if rsi <= 30 else "#FFD700" if rsi <= 45 else "#888888"
    rsi_text = "🔥 超売られすぎ" if rsi <= 30 else "⚡ 売られすぎ" if rsi <= 45 else "⚖️ 中立"
    if rsi >= 70: rsi_color = "#26a69a"; rsi_text = "⚠️ 買われすぎ"
    
    _, _, _, macd_t = get_triage_info(macd_hist, macd_hist_prev, rsi)
    macd_color = "#ef5350" if macd_t in ["GC直後", "上昇拡大"] else "#26a69a" if macd_t == "下落継続" else "#888888"
    
    days = int((buy_price * (tp_pct / 100.0)) / atr) if atr > 0 else 99
    return f"""<div style="background: rgba(255, 255, 255, 0.05); padding: 0.8rem; border-radius: 4px; margin: 1rem 0; border-left: 4px solid #FFD700;">
        <div style="font-size: 13px; color: #aaa;">📡 計器フライト: RSI <strong style="color: {rsi_color};">{rsi:.0f}% ({rsi_text})</strong> | MACD <strong style="color: {macd_color};">{macd_t}</strong> | ボラ <strong style="color: #bbb;">{atr:.0f}円</strong> (利確目安: {days}日)</div></div>"""

# --- 標準チャート（Tab 1, 2, 4用） ---
def draw_chart(df, targ_p, tp5=None, tp10=None, tp15=None, tp20=None):
    df = df.copy(); df['MA5'] = df['AdjC'].rolling(window=5).mean(); df['MA25'] = df['AdjC'].rolling(window=25).mean(); df['MA75'] = df['AdjC'].rolling(window=75).mean()
    fig = go.Figure()
    fig.add_trace(go.Candlestick(x=df['Date'], open=df['AdjO'], high=df['AdjH'], low=df['AdjL'], close=df['AdjC'], name='株価', increasing_line_color='#ef5350', decreasing_line_color='#26a69a'))
    fig.add_trace(go.Scatter(x=df['Date'], y=df['MA5'], mode='lines', name='5日', line=dict(color='rgba(156, 39, 176, 0.7)', width=1.5)))      
    fig.add_trace(go.Scatter(x=df['Date'], y=df['MA25'], mode='lines', name='25日', line=dict(color='rgba(33, 150, 243, 0.7)', width=1.5)))     
    fig.add_trace(go.Scatter(x=df['Date'], y=[targ_p]*len(df), mode='lines', name='買値/トリガー', line=dict(color='#FFD700', width=2, dash='dash')))
    if tp10: fig.add_trace(go.Scatter(x=df['Date'], y=[tp10]*len(df), mode='lines', name='売値(10%)', line=dict(color='rgba(239, 83, 80, 0.6)', width=1, dash='dot')))
    if tp15: fig.add_trace(go.Scatter(x=df['Date'], y=[tp15]*len(df), mode='lines', name='売値(15%)', line=dict(color='rgba(239, 83, 80, 0.8)', width=1.5, dash='dot')))
    start_date = df['Date'].max() - timedelta(days=45) if len(df) > 30 else df['Date'].min()
    fig.update_layout(height=400, margin=dict(l=10, r=60, t=20, b=40), xaxis_rangeslider_visible=False, xaxis=dict(range=[start_date, df['Date'].max() + timedelta(days=1)], type="date"), paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)', hovermode="x unified", legend=dict(orientation="h", yanchor="top", y=-0.1, xanchor="center", x=0.5))
    st.plotly_chart(fig, use_container_width=True)

# --- 高高度モニター（Tab 3用）ズームチャート ---
def draw_chart_t6(df, targ_p, tp5, tp10, tp15):
    df = df.copy(); df['MA5'] = df['AdjC'].rolling(window=5).mean()
    fig = go.Figure()
    fig.add_trace(go.Candlestick(x=df['Date'], open=df['AdjO'], high=df['AdjH'], low=df['AdjL'], close=df['AdjC'], name='株価', increasing_line_color='#ef5350', decreasing_line_color='#26a69a'))
    fig.add_trace(go.Scatter(x=df['Date'], y=df['MA5'], mode='lines', name='5日線(命綱)', line=dict(color='rgba(156, 39, 176, 0.9)', width=2.5)))      
    fig.add_trace(go.Scatter(x=df['Date'], y=[targ_p]*len(df), mode='lines', name='現在値', line=dict(color='#FFD700', width=2, dash='dash')))
    fig.add_trace(go.Scatter(x=df['Date'], y=[tp5]*len(df), mode='lines', name='+5%', line=dict(color='rgba(239, 83, 80, 0.5)', width=1, dash='dot')))
    fig.add_trace(go.Scatter(x=df['Date'], y=[tp10]*len(df), mode='lines', name='+10%', line=dict(color='rgba(239, 83, 80, 0.7)', width=1.5, dash='dot')))
    fig.add_trace(go.Scatter(x=df['Date'], y=[tp15]*len(df), mode='lines', name='+15%', line=dict(color='rgba(239, 83, 80, 1.0)', width=1.5, dash='dot')))
    
    last_date = df['Date'].max()
    start_date = df['Date'].iloc[-14] if len(df) >= 14 else df['Date'].min() # 14日間に強制ズーム
    
    visible_df = df[(df['Date'] >= start_date) & (df['Date'] <= last_date)]
    if not visible_df.empty:
        y_max = max(visible_df['AdjH'].max(), tp15); y_min = min(visible_df['AdjL'].min(), visible_df['MA5'].min()) 
        margin = (y_max - y_min) * 0.05; y_range = [y_min - margin, y_max + margin]
    else: y_range = None

    fig.update_layout(height=380, margin=dict(l=10, r=60, t=20, b=40), xaxis_rangeslider_visible=False, xaxis=dict(range=[start_date, last_date + timedelta(days=0.5)], type="date"), paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)', hovermode="x unified", legend=dict(orientation="h", yanchor="top", y=-0.1, xanchor="center", x=0.5))
    if y_range: fig.update_layout(yaxis=dict(range=y_range, fixedrange=False))
    st.plotly_chart(fig, use_container_width=True)

# --- 4. サイドバー UI ---
if 'preset_target' not in st.session_state: st.session_state.preset_target = "🚀 中小型株 (50%押し・標準)"
if 'sidebar_tactics' not in st.session_state: st.session_state.sidebar_tactics = "⚖️ バランス (掟達成率 ＞ 到達度)"
if 'push_r' not in st.session_state: st.session_state.push_r = 50.0 
st.session_state.bt_tp = 10; st.session_state.bt_sl_i = 8; st.session_state.bt_sl_c = 8; st.session_state.limit_d = 4; st.session_state.bt_sell_d = 10
st.session_state.bt_lot = 100

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
    "🎯 精密スコープ照準", 
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
    run_scan = st.button(f"🚀 待伏せ部隊スキャン開始 ({tactics_mode.split()[0]}モード)")
    if run_scan:
        with st.spinner("全軍から鉄の掟適合銘柄を抽出中..."):
            raw = get_hist_data_cached()
            if not raw: st.error("データ取得失敗")
            else:
                df = clean_df(pd.DataFrame(raw)).dropna(subset=['AdjC', 'AdjH', 'AdjL']).sort_values(['Code', 'Date'])
                df_30 = df.groupby('Code').tail(30)
                max_date_all = df['Date'].max(); cutoff_date_14 = max_date_all - timedelta(days=14)
                df_14 = df_30[df_30['Date'] >= cutoff_date_14]
                counts = df_14.groupby('Code').size(); valid = counts[counts >= 5].index
                if valid.empty: st.warning("条件を満たすデータなし"); st.stop()
                
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
                sum_df = sum_df[sum_df['lc'] >= ((sum_df['h14'] - ur * 0.618) * 0.98)]
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
                
                sum_df = sum_df[(sum_df['lc'] >= f1_min) & (sum_df['lc'] <= f1_max) & (sum_df['r30'] <= f2_m30) & (sum_df['ldrop'] >= f3_drop) & ((sum_df['lrise'] <= f4_mlong) | (sum_df['lrise'] == 0))]
                sum_df = sum_df[(~sum_df['is_dt']) & (~sum_df['is_hs']) & (~sum_df['sakata_signal'].astype(str).str.contains("下落警戒", na=False))]
                sum_df = sum_df[(sum_df['r14'] >= f9_min14) & (sum_df['r14'] <= f9_max14) & (sum_df['d_high'] <= limit_d)]
                sum_df = sum_df[(sum_df['lc'] <= (sum_df['bt'] * 1.35)) & (sum_df['lc'] >= (sum_df['bt'] * 0.85))]
                if f10_ex_knife: sum_df = sum_df[(sum_df['daily_pct'] >= -(st.session_state.bt_sl_i / 100.0)) & (sum_df['pct_3days'] >= -(st.session_state.bt_sl_i / 100.0) * 1.5)]
                
                if tactics_mode.startswith("⚔️"): res = sum_df.sort_values(['is_db', 'reach_pct'], ascending=[False, False]).head(30)
                elif tactics_mode.startswith("🛡️"): res = sum_df.sort_values(['is_defense', 'reach_pct'], ascending=[False, False]).head(30)
                else: res = sum_df.sort_values('reach_pct', ascending=False).head(30)
                
                if res.empty: st.warning("標的は存在しません。")
                else:
                    st.success(f"🎯 スキャン完了: {len(res)} 銘柄クリア")
                    st.markdown("#### 📋 コピペ用コード")
                    if 'Code' in res.columns: st.code(",".join([str(c)[:4] for c in res['Code']]), language="text")

                    for _, r in res.iterrows():
                        st.divider()
                        c = str(r['Code']); n = r['CompanyName'] if not pd.isna(r.get('CompanyName')) else f"銘柄 {c[:4]}"
                        st.markdown(f"### ({c[:4]}) {n}", unsafe_allow_html=True)
                        for alert in check_event_mines(c): st.warning(alert)
                        if r['is_db']: st.success("🔥 三川（ダブルボトム）底打ち反転波形！")
                        if r['is_defense']: st.info("🛡️ 下値支持線(サポート)に極接近。")
                        
                        # --- 🎯 復元：目標値の完全表示 ---
                        lc_val = int(r.get('lc', 0)); bt_val = int(r.get('bt', 0)); high_val = int(r.get('h14', lc_val)); low_val = int(r.get('l14', 0))
                        wave_len = high_val - low_val if low_val > 0 else 0
                        sl5 = int(bt_val * 0.95); sl8 = int(bt_val * 0.92); sl15 = int(bt_val * 0.85)
                        tp20 = int(bt_val * 1.2); tp15 = int(bt_val * 1.15); tp10 = int(bt_val * 1.1); tp5 = int(bt_val * 1.05)
                        daily_pct = r.get('daily_pct', 0); daily_sign = "+" if daily_pct >= 0 else ""

                        sc0, sc0_1, sc0_2, sc1, sc2, sc3, sc4 = st.columns([0.8, 0.8, 0.8, 0.9, 1.1, 1.8, 0.7])
                        sc0.metric("直近高値", f"{high_val:,}円"); sc0_1.metric("直近安値", f"{low_val:,}円"); sc0_2.metric("上昇幅", f"{wave_len:,}円")
                        sc1.metric("最新終値", f"{lc_val:,}円", f"{daily_sign}{daily_pct*100:.1f}%", delta_color="inverse")
                        
                        html_buy = f"""<div style="font-family: sans-serif; padding-top: 0.2rem;"><div style="font-size: 14px; color: rgba(250, 250, 250, 0.6); padding-bottom: 0.1rem;">🎯 買値目標</div><div style="font-size: 1.8rem; font-weight: bold; color: #FFD700;">{bt_val:,}円</div></div>"""
                        sc2.markdown(html_buy, unsafe_allow_html=True)
                        
                        html_sell = f"""<div style="font-family: sans-serif; padding-top: 0.2rem;"><div style="font-size: 14px; color: rgba(250, 250, 250, 0.6); padding-bottom: 0.1rem;">🎯 売値目標 ＆ 🛡️ 損切目安</div><div style="font-size: 16px;">
                            <span style="display: inline-block; width: 2.5em; color: #ef5350;">20%</span> <span style="color: #ef5350;">{tp20:,}円</span><br>
                            <span style="display: inline-block; width: 2.5em; color: #ef5350;">15%</span> <span style="color: #ef5350;">{tp15:,}円</span> <span style="color: rgba(250, 250, 250, 0.3); margin: 0 4px;">|</span> <span style="display: inline-block; width: 2.8em; color: #26a69a;">-5%</span> <span style="color: #26a69a;">{sl5:,}円</span><br>
                            <span style="display: inline-block; width: 2.5em; color: #ef5350;">10%</span> <span style="color: #ef5350;">{tp10:,}円</span> <span style="color: rgba(250, 250, 250, 0.3); margin: 0 4px;">|</span> <span style="display: inline-block; width: 2.8em; color: #26a69a;">-8%</span> <span style="color: #26a69a;">{sl8:,}円</span><br>
                            <span style="display: inline-block; width: 2.5em; color: #ef5350;">5%</span> <span style="color: #ef5350;">{tp5:,}円</span> <span style="color: rgba(250, 250, 250, 0.3); margin: 0 4px;">|</span> <span style="display: inline-block; width: 2.8em; color: #26a69a;">-15%</span> <span style="color: #26a69a;">{sl15:,}円</span></div></div>"""
                        sc3.markdown(html_sell, unsafe_allow_html=True)
                        sc4.metric("到達度", f"{r['reach_pct']:.1f}%")
                        # ----------------------------------------
                        
                        api_code = c if len(c) == 5 else c + "0"
                        raw_s = get_single_data(api_code, 1)
                        if raw_s:
                            hist = calc_technicals(clean_df(pd.DataFrame(raw_s)))
                            st.markdown(render_technical_radar(hist, r['bt'], st.session_state.bt_tp), unsafe_allow_html=True)
                            draw_chart(hist, r['bt'], tp15=r['tp15'])

# ------------------------------------------
# Tab 2: GC初動強襲レーダー
# ------------------------------------------
with tab2:
    render_macro_board()
    st.markdown('### ⚡ GC（ゴールデンクロス）初動強襲レーダー')
    if st.button("⚡ GC遊撃部隊を発進させる"):
        with st.spinner("全軍からMACDゴールデンクロス直後の銘柄を抽出中..."):
            raw = get_hist_data_cached()
            if not raw: st.error("データ取得失敗")
            else:
                df = clean_df(pd.DataFrame(raw)).dropna(subset=['AdjC', 'AdjH', 'AdjL']).sort_values(['Code', 'Date'])
                df_30 = df.groupby('Code').tail(30)
                valid_counts = df_30.groupby('Code').size(); df_30 = df_30[df_30['Code'].isin(valid_counts[valid_counts >= 26].index)]
                latest_prices = df_30.groupby('Code')['AdjC'].last(); df_30 = df_30[df_30['Code'].isin(latest_prices[(latest_prices >= f1_min) & (latest_prices <= f1_max)].index)]
                
                results_gc = []
                for code, group in df_30.groupby('Code'):
                    df_calc = calc_technicals(group)
                    avg_vol = df_calc.tail(5).get('Volume', pd.Series([0])).mean()
                    if avg_vol < 50000: continue
                    latest = df_calc.iloc[-1]; prev = df_calc.iloc[-2]
                    
                    if (latest['MACD'] > latest['MACD_Signal']) and (prev['MACD'] <= prev['MACD_Signal']) and (latest['AdjC'] >= latest['MA25']) and (latest.get('RSI', 50) < 70):
                        c_name = master_df[master_df['Code'] == code]['CompanyName'].iloc[0] if not master_df.empty and code in master_df['Code'].values else "不明"
                        if f7_ex_etf and bool(re.search("ETF|投信|ブル|ベア|REIT|ﾘｰﾄ", str(c_name), re.IGNORECASE)): continue
                        results_gc.append({'Code': code, 'Name': c_name, 'lc': latest['AdjC'], 'MA25': latest['MA25'], 'RSI': latest.get('RSI', 50), 'Vol': avg_vol, 'df_chart': df_calc, 'trigger': latest['AdjH'] * 1.01})
                
                if not results_gc: st.info("GC初動銘柄はありませんでした。")
                else:
                    st.success(f"⚡ 抽出完了: {len(results_gc)} 銘柄捕捉。")
                    res_df_gc = pd.DataFrame(results_gc).sort_values('Vol', ascending=False)
                    st.markdown("#### 📋 コピペ用コード (GC部隊)")
                    if 'Code' in res_df_gc.columns: st.code(",".join([str(c)[:4] for c in res_df_gc['Code']]), language="text")

                    for _, r in res_df_gc.iterrows():
                        st.divider()
                        c = str(r['Code']); n = str(r['Name'])
                        st.markdown(f"### ({c[:4]}) {n} <span style='background:#ef5350;color:#fff;padding:2px 8px;border-radius:4px;font-size:12px;'>⚡ GC初動</span>", unsafe_allow_html=True)
                        for alert in check_event_mines(c): st.warning(alert)
                        
                        # --- 🎯 復元：強襲専用の目標値表示 ---
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
                        # ----------------------------------------
                        
                        st.markdown(render_technical_radar(r['df_chart'], r['lc'], 10), unsafe_allow_html=True)
                        draw_chart(r['df_chart'], r['trigger'], tp10=tp10)

# ------------------------------------------
# Tab 3: 高高度モニター（イナゴタワー追跡）
# ------------------------------------------
with tab3:
    st.markdown('### 🛸 高高度観測モニター（ブレイクアウト・順張り探知）')
    if st.button("🚀 観測機を発進させる"):
        with st.spinner("成層圏の熱源を探索中..."):
            raw = get_hist_data_cached()
            if raw:
                df_30 = clean_df(pd.DataFrame(raw)).dropna(subset=['AdjC', 'AdjH', 'AdjL']).sort_values(['Code', 'Date']).groupby('Code').tail(30)
                valid = df_30.groupby('Code').size(); df_30 = df_30[df_30['Code'].isin(valid[valid >= 15].index)]
                results_t6 = []
                for code, group in df_30.groupby('Code'):
                    df_calc = group.copy(); df_calc['MA5'] = df_calc['AdjC'].rolling(window=5).mean()
                    latest = df_calc.iloc[-1]; prev = df_calc.iloc[-2]
                    lc = latest['AdjC']; h14 = df_calc.tail(14)['AdjH'].max(); daily_pct = (lc / prev['AdjC']) - 1 if prev['AdjC'] > 0 else 0
                    if (lc > latest['MA5']) and (lc >= h14 * 0.95) and (daily_pct >= 0.03):
                        c_name = master_df[master_df['Code'] == code]['CompanyName'].iloc[0] if not master_df.empty and code in master_df['Code'].values else "不明"
                        if f7_ex_etf and bool(re.search("ETF|投信", str(c_name), re.IGNORECASE)): continue
                        results_t6.append({'Code': code, 'Name': c_name, 'lc': lc, 'MA5': latest['MA5'], 'h14': h14, 'daily_pct': daily_pct, 'df_chart': calc_technicals(group.copy())})
                if not results_t6: st.info("観測対象なし。")
                else:
                    st.success(f"🛸 観測完了: {len(results_t6)} 機捕捉。")
                    for r in sorted(results_t6, key=lambda x: x['daily_pct'], reverse=True):
                        st.divider()
                        st.markdown(f"### ({r['Code'][:4]}) {r['Name']} <span style='background:#616161;color:#fff;padding:2px 8px;border-radius:4px;font-size:12px;'>🛸 観測対象 (本日 +{r['daily_pct']*100:.1f}%)</span>", unsafe_allow_html=True)
                        col1, col2, col3 = st.columns(3)
                        col1.metric("最新終値", f"{int(r['lc']):,}円")
                        col2.metric("5日線 (割ると墜落)", f"{int(r['MA5']):,}円")
                        col3.metric("直近高値", f"{int(r['h14']):,}円")
                        
                        # --- 🎯 復元：高高度専用ズームチャート ---
                        draw_chart_t6(r['df_chart'], r['lc'], int(r['lc']*1.05), int(r['lc']*1.10), int(r['lc']*1.15))

# ------------------------------------------
# Tab 4: 精密スコープ照準（個別局地戦）
# ------------------------------------------
with tab4:
    render_macro_board()
    st.markdown('### 🎯 精密スコープ照準（局地戦スキャン）')
    target_codes_str = st.text_area("標的コード（複数可、カンマや改行区切り）", value="7203\n8604", height=100)
    if st.button(f"🔫 指定銘柄 一斉スキャン ({tactics_mode.split()[0]})") and target_codes_str:
        t_codes = list(dict.fromkeys([c.upper() for c in re.findall(r'(?<![a-zA-Z0-9])[a-zA-Z0-9]{4}(?![a-zA-Z0-9])', target_codes_str)]))
        if not t_codes: st.warning("有効なコードが見つかりません。")
        else:
            with st.spinner(f"{len(t_codes)} 銘柄を計算中..."):
                for c in t_codes:
                    raw_s = get_single_data(c + "0", 1)
                    if raw_s:
                        hist = calc_technicals(clean_df(pd.DataFrame(raw_s)))
                        if not hist.empty:
                            lc_val = int(hist.iloc[-1]['AdjC']); h14_val = int(hist.tail(14)['AdjH'].max()); l14_val = int(hist.tail(14)['AdjL'].min())
                            bt_val = int(h14_val - ((h14_val - l14_val) * (st.session_state.push_r / 100.0)))
                            st.divider()
                            c_name = master_df[master_df['Code'] == c + "0"]['CompanyName'].iloc[0] if not master_df.empty and (c+"0") in master_df['Code'].values else f"銘柄 {c}"
                            st.markdown(f"### ({c}) {c_name}", unsafe_allow_html=True)
                            for alert in check_event_mines(c): st.warning(alert)
                            
                            # --- 🎯 復元：目標値の完全表示（Tab4） ---
                            wave_len = h14_val - l14_val
                            sl5 = int(bt_val * 0.95); sl8 = int(bt_val * 0.92); sl15 = int(bt_val * 0.85)
                            tp20 = int(bt_val * 1.2); tp15 = int(bt_val * 1.15); tp10 = int(bt_val * 1.1); tp5 = int(bt_val * 1.05)

                            sc0, sc0_1, sc0_2, sc1, sc2, sc3 = st.columns([0.8, 0.8, 0.8, 0.9, 1.1, 1.8])
                            sc0.metric("直近高値", f"{h14_val:,}円"); sc0_1.metric("直近安値", f"{l14_val:,}円"); sc0_2.metric("上昇幅", f"{wave_len:,}円")
                            sc1.metric("最新終値", f"{lc_val:,}円")
                            
                            html_buy = f"""<div style="font-family: sans-serif; padding-top: 0.2rem;"><div style="font-size: 14px; color: rgba(250, 250, 250, 0.6); padding-bottom: 0.1rem;">🎯 買値目標</div><div style="font-size: 1.8rem; font-weight: bold; color: #FFD700;">{bt_val:,}円</div></div>"""
                            sc2.markdown(html_buy, unsafe_allow_html=True)
                            
                            html_sell = f"""<div style="font-family: sans-serif; padding-top: 0.2rem;"><div style="font-size: 14px; color: rgba(250, 250, 250, 0.6); padding-bottom: 0.1rem;">🎯 売値目標 ＆ 🛡️ 損切目安</div><div style="font-size: 16px;">
                                <span style="display: inline-block; width: 2.5em; color: #ef5350;">20%</span> <span style="color: #ef5350;">{tp20:,}円</span><br>
                                <span style="display: inline-block; width: 2.5em; color: #ef5350;">15%</span> <span style="color: #ef5350;">{tp15:,}円</span> <span style="color: rgba(250, 250, 250, 0.3); margin: 0 4px;">|</span> <span style="display: inline-block; width: 2.8em; color: #26a69a;">-5%</span> <span style="color: #26a69a;">{sl5:,}円</span><br>
                                <span style="display: inline-block; width: 2.5em; color: #ef5350;">10%</span> <span style="color: #ef5350;">{tp10:,}円</span> <span style="color: rgba(250, 250, 250, 0.3); margin: 0 4px;">|</span> <span style="display: inline-block; width: 2.8em; color: #26a69a;">-8%</span> <span style="color: #26a69a;">{sl8:,}円</span><br>
                                <span style="display: inline-block; width: 2.5em; color: #ef5350;">5%</span> <span style="color: #ef5350;">{tp5:,}円</span> <span style="color: rgba(250, 250, 250, 0.3); margin: 0 4px;">|</span> <span style="display: inline-block; width: 2.8em; color: #26a69a;">-15%</span> <span style="color: #26a69a;">{sl15:,}円</span></div></div>"""
                            sc3.markdown(html_sell, unsafe_allow_html=True)
                            
                            st.markdown(render_technical_radar(hist, bt_val, st.session_state.bt_tp), unsafe_allow_html=True)
                            draw_chart(hist, bt_val, tp15=tp15)

# ------------------------------------------
# Tab 5: 戦術シミュレータ（デュアル・バックテスト）
# ------------------------------------------
with tab5:
    st.markdown('### ⚙️ 戦術シミュレータ（2年間のバックテスト）')
    bt_mode = st.radio("🔍 検証する戦術を選択してください", ["🌐 【待伏】鉄の掟（50%押し）", "⚡ 【強襲】GCブレイクアウト（高値+1%トリガー）"], horizontal=True)
    col_1, col_2 = st.columns([2, 1])
    with col_1: bt_c_in = st.text_area("検証コード（複数可）", value="6614\n4427", height=100)
    with col_2:
        if "待伏" in bt_mode: st.info("※左サイドバーの「🎯 買いルール」「🛡️ 売りルール」の設定値を用いてシミュレーションを実行します。")
        else:
            st.info("※強襲モード専用設定\n・利確: +8%\n・損切: -4%\n・期限: 5営業日\n・トリガー: GC点灯日の高値+1%")
            bt_tp_gc = 8.0; bt_sl_gc = 4.0; bt_limit_gc = 5

    if st.button("🔥 一括バックテスト実行") and bt_c_in:
        t_codes = list(dict.fromkeys([c.upper() for c in re.findall(r'(?<![a-zA-Z0-9])[a-zA-Z0-9]{4}(?![a-zA-Z0-9])', bt_c_in)]))
        if not t_codes: st.warning("有効なコードが見つかりません。")
        else:
            all_t = []; b_bar = st.progress(0, "仮想売買中...")
            for idx, c in enumerate(t_codes):
                raw = get_single_data(c + "0", 2)
                if raw:
                    df = clean_df(pd.DataFrame(raw)).dropna(subset=['AdjO', 'AdjH', 'AdjL', 'AdjC']).reset_index(drop=True)
                    pos = None
                    if "待伏" in bt_mode:
                        for i in range(30, len(df)):
                            td = df.iloc[i]
                            if pos is None:
                                win_14 = df.iloc[i-14:i]; win_30 = df.iloc[i-30:i]; rh = win_14['AdjH'].max(); rl = win_14['AdjL'].min()
                                if pd.isna(rh) or pd.isna(rl) or rl <= 0: continue
                                if (1.3 <= rh/rl <= 2.0) and (len(win_14[win_14['Date'] > win_14.loc[win_14['AdjH'].idxmax(), 'Date']]) <= st.session_state.limit_d):
                                    if check_double_top(win_30) or check_head_shoulders(win_30): continue
                                    targ = rh - ((rh - rl) * (st.session_state.push_r / 100))
                                    if td['AdjL'] <= targ: pos = {'b_i': i, 'b_d': td['Date'], 'b_p': min(td['AdjO'], targ)}
                            else:
                                bp = round(pos['b_p'], 1); held = i - pos['b_i']; sp = 0; rsn = ""
                                sl_i = bp * (1 - (st.session_state.bt_sl_i / 100)); tp = bp * (1 + (st.session_state.bt_tp / 100)); sl_c = bp * (1 - (st.session_state.bt_sl_c / 100))
                                if td['AdjL'] <= sl_i: sp = min(td['AdjO'], sl_i); rsn = f"損切(-{st.session_state.bt_sl_i}%)"
                                elif td['AdjH'] >= tp: sp = max(td['AdjO'], tp); rsn = f"利確(+{st.session_state.bt_tp}%)"
                                elif td['AdjC'] <= sl_c: sp = td['AdjC']; rsn = f"損切終値(-{st.session_state.bt_sl_c}%)"
                                elif held >= st.session_state.bt_sell_d: sp = td['AdjC']; rsn = f"時間切れ({st.session_state.bt_sell_d}日)"
                                if rsn:
                                    all_t.append({'銘柄': c, '購入日': pos['b_d'].strftime('%Y-%m-%d'), '決済日': td['Date'].strftime('%Y-%m-%d'), '保有': held, '買値': bp, '売値': round(sp,1), '損益額': int((sp - bp) * st.session_state.bt_lot), '理由': rsn})
                                    pos = None
                    else:
                        df_tech = calc_technicals(df)
                        for i in range(30, len(df_tech)):
                            td = df_tech.iloc[i]
                            if pos is None:
                                latest = df_tech.iloc[i-1]; prev = df_tech.iloc[i-2]
                                if (latest['MACD'] > latest['MACD_Signal']) and (prev['MACD'] <= prev['MACD_Signal']) and (latest['AdjC'] >= latest['MA25']) and (latest.get('RSI', 50) < 70):
                                    pos = {'wait_i': i, 'trigger': latest['AdjH'] * 1.01}
                            elif 'wait_i' in pos:
                                if i - pos['wait_i'] > 3: pos = None
                                elif td['AdjH'] >= pos['trigger']: pos = {'b_i': i, 'b_d': td['Date'], 'b_p': max(td['AdjO'], pos['trigger'])}
                            elif 'b_i' in pos:
                                bp = round(pos['b_p'], 1); held = i - pos['b_i']; sp = 0; rsn = ""
                                sl = bp * (1 - (bt_sl_gc / 100)); tp = bp * (1 + (bt_tp_gc / 100))
                                if td['AdjL'] <= sl: sp = min(td['AdjO'], sl); rsn = f"損切(-{bt_sl_gc}%)"
                                elif td['AdjH'] >= tp: sp = max(td['AdjO'], tp); rsn = f"利確(+{bt_tp_gc}%)"
                                elif held >= bt_limit_gc: sp = td['AdjC']; rsn = f"時間切れ({bt_limit_gc}日)"
                                if rsn:
                                    all_t.append({'銘柄': c, '購入日': pos['b_d'].strftime('%Y-%m-%d'), '決済日': td['Date'].strftime('%Y-%m-%d'), '保有': held, '買値': bp, '売値': round(sp,1), '損益額': int((sp - bp) * st.session_state.bt_lot), '理由': rsn})
                                    pos = None

                b_bar.progress((idx + 1) / len(t_codes))
            b_bar.empty()
            if not all_t: st.warning("条件に合致するトレードはありませんでした。")
            else:
                tdf = pd.DataFrame(all_t); tot = len(tdf); wins = len(tdf[tdf['損益額'] > 0])
                n_prof = tdf['損益額'].sum(); sprof = tdf[tdf['損益額'] > 0]['損益額'].sum(); sloss = abs(tdf[tdf['損益額'] <= 0]['損益額'].sum())
                pf = round(sprof / sloss, 2) if sloss > 0 else 'inf'
                st.markdown(f"### 💰 総合利益額: {n_prof:,} 円")
                m1, m2, m3, m4 = st.columns(4)
                m1.metric("トレード回数", f"{tot} 回"); m2.metric("勝率", f"{round((wins/tot)*100,1)} %")
                m3.metric("平均損益額", f"{int(n_prof/tot):,} 円"); m4.metric("PF", f"{pf}")
                st.dataframe(tdf, use_container_width=True, hide_index=True)

# ------------------------------------------
# Tab 6: IFD-OCO 10日ルール監視
# ------------------------------------------
with tab6:
    st.markdown('### ⏳ IFD-OCO 10日ルール監視')
    hold_input = st.text_area("保有銘柄（銘柄コード, 約定日[YYYY-MM-DD], 買値）", value="7203, 2026-03-10, 3500", height=100)
    if st.button("🔄 戦況更新 (10日タイマー確認)"):
        today = datetime.utcnow() + timedelta(hours=9)
        for line in hold_input.strip().split('\n'):
            if not line.strip(): continue
            parts = [p.strip() for p in line.split(',')]
            if len(parts) >= 2:
                c = parts[0]; date_str = parts[1]; bp = parts[2] if len(parts) >= 3 else "---"
                try:
                    buy_date = datetime.strptime(date_str, "%Y-%m-%d")
                    days_elapsed = np.busday_count(buy_date.date(), today.date())
                    if days_elapsed <= 7: status = "🟢 巡航中"; bg = "rgba(38, 166, 154, 0.1)"; bdc = "#26a69a"
                    elif days_elapsed <= 9: status = "⚠️ 撤退準備"; bg = "rgba(255, 215, 0, 0.1)"; bdc = "#FFD700"
                    else: status = "💀 強制撤退日"; bg = "rgba(239, 83, 80, 0.1)"; bdc = "#ef5350"
                    st.markdown(f"<div style='background:{bg};border-left:4px solid {bdc};padding:1rem;margin-bottom:0.8rem;'><b>({c})</b> 経過 {days_elapsed} 営業日 - {status}</div>", unsafe_allow_html=True)
                except: st.error(f"🚨 フォーマットエラー: {line}")

# ------------------------------------------
# Tab 7: 事後任務報告（AAR）
# ------------------------------------------
with tab7:
    st.markdown('### 🗂️ 過去戦歴の解剖（純粋IFD-OCO検証）')
    st.info("※現在開発中のため、Tab 5（バックテスト）をご利用ください。") # AAR用CSV処理は文字数限界のため仮置き
