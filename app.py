import streamlit as st
import requests
import pandas as pd
import os
import re
from datetime import datetime, timedelta
from io import BytesIO
import plotly.graph_objects as go
import numpy as np
import concurrent.futures

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

# --- 🚁 司令部へ帰還ボタン (真・完全版) ---
import streamlit.components.v1 as components
components.html(
    """
    <script>
    const parentDoc = window.parent.document;
    const oldBtn = parentDoc.getElementById('sniper-return-btn');
    if (oldBtn) { oldBtn.remove(); }
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
        const containers = parentDoc.querySelectorAll('div, main, section');
        for (let i = 0; i < containers.length; i++) {
            if (containers[i].scrollHeight > containers[i].clientHeight) {
                containers[i].scrollTo({top: 0, behavior: 'smooth'});
            }
        }
    };
    parentDoc.body.appendChild(btn);
    </script>
    """, height=0, width=0
)

# --- 2. 認証・通信設定 ---
user_id = st.session_state["current_user"]
st.markdown(f'<h1 style="font-size: clamp(24px, 7vw, 42px); font-weight: 900; border-bottom: 2px solid #2e7d32; padding-bottom: 0.5rem; margin-bottom: 1rem;">🎯 戦術スコープ『鉄の掟』 <span style="font-size: 16px; font-weight: normal; color: #888;">(ID: {user_id[:4]}***)</span></h1>', unsafe_allow_html=True)

# --- 🔴 安全装置：マニュアル・オーバーライド ---
API_KEY = st.secrets.get("JQUANTS_API_KEY", "").strip()
headers = {"x-api-key": API_KEY}
BASE_URL = "https://api.jquants.com/v2"

# --- ⏱️ 19:00 完全自動パージ機構（第一防衛線） ---
import pytz
jst = pytz.timezone('Asia/Tokyo')
now = datetime.now(jst)

if 'last_auto_purge_date' not in st.session_state:
    st.session_state.last_auto_purge_date = None

if now.hour >= 18:
    today_str = now.strftime('%Y-%m-%d')
    if st.session_state.last_auto_purge_date != today_str:
        st.cache_data.clear()
        st.session_state.tab1_scan_results = None
        st.session_state.tab2_scan_results = None
        st.session_state.tab5_ifd_results = None
        st.session_state.last_auto_purge_date = today_str

# --- 🌤️ マクロ気象レーダー（日経平均）モジュール ---
@st.cache_data(ttl=900, show_spinner=False)
def get_macro_weather():
    try:
        import yfinance as yf
        tk_ni = yf.Ticker("^N225")
        hist_ni = tk_ni.history(period="3mo")
        if len(hist_ni) >= 2:
            lc_ni = hist_ni['Close'].iloc[-1]
            prev_ni = hist_ni['Close'].iloc[-2]
            diff_ni = lc_ni - prev_ni
            pct_ni = (diff_ni / prev_ni) * 100
            
            df_ni = hist_ni.reset_index()
            if 'Date' in df_ni.columns:
                df_ni['Date'] = pd.to_datetime(df_ni['Date'], utc=True).dt.tz_convert('Asia/Tokyo').dt.tz_localize(None)
                
            return {"nikkei": {"price": lc_ni, "diff": diff_ni, "pct": pct_ni, "df": df_ni}}
    except: return None

def render_macro_board():
    data = get_macro_weather()
    if data and "nikkei" in data:
        ni = data["nikkei"]
        df = ni["df"]
        color = "#ef5350" if ni['diff'] >= 0 else "#26a69a"
        sign = "+" if ni['diff'] >= 0 else ""
        
        c1, c2 = st.columns([1, 2.5])
        with c1:
            html = f"""
            <div style="background: rgba(20, 20, 20, 0.6); padding: 1.2rem; border-radius: 8px; border-left: 4px solid {color}; height: 100%; display: flex; flex-direction: column; justify-content: center;">
                <div style="font-size: 14px; color: #aaa; margin-bottom: 8px;">🌤️ 戦場の天候 (日経平均)</div>
                <div style="font-size: 26px; font-weight: bold; color: {color}; margin-bottom: 4px;">{ni['price']:,.2f} 円</div>
                <div style="font-size: 16px; color: {color};">({sign}{ni['diff']:,.2f} / {sign}{ni['pct']:.2f}%)</div>
            </div>
            """
            st.markdown(html, unsafe_allow_html=True)
            
        with c2:
            df['MA25'] = df['Close'].rolling(window=25).mean()
            fig = go.Figure()
            fig.add_trace(go.Scatter(x=df['Date'], y=df['Close'], mode='lines', name='日経平均', line=dict(color='#FFD700', width=2)))
            fig.add_trace(go.Scatter(x=df['Date'], y=df['MA25'], mode='lines', name='25日線', line=dict(color='rgba(255, 255, 255, 0.4)', width=1, dash='dot')))
            fig.update_layout(height=160, margin=dict(l=10, r=20, t=10, b=10), xaxis_rangeslider_visible=False, paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)', showlegend=False, yaxis=dict(side="right", tickformat=",.0f"))
            st.plotly_chart(fig, use_container_width=True, config={'displayModeBar': False})
            
        st.markdown("<div style='margin-bottom: 1.5rem;'></div>", unsafe_allow_html=True)
    else:
        st.warning("⚠️ 現在、外部気象レーダー（Yahoo Finance）からの応答がありません。通信回復を待機しています。")
        st.markdown("<div style='margin-bottom: 1.5rem;'></div>", unsafe_allow_html=True)

render_macro_board()

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

def check_event_mines(code, event_data=None):
    alerts = []
    c = str(code)[:4]
    today = datetime.utcnow() + timedelta(hours=9)
    today_date = today.date()
    max_warning_date = today_date + timedelta(days=14)

    critical_mines = {
        "8835": "2026-03-30", "3137": "2026-03-27", "4167": "2026-03-27",
        "4031": "2026-03-27", "2195": "2026-03-27", "4379": "2026-03-27",
    }

    if c in critical_mines:
        try:
            event_date = datetime.strptime(critical_mines[c], "%Y-%m-%d").date()
            if (event_date - timedelta(days=14)) <= today_date <= event_date:
                alerts.append(f"💣 【地雷警戒】危険イベント接近中（{critical_mines[c]}）")
        except: pass

    if not event_data: return alerts

    for item in event_data.get("dividend", []):
        d_str = str(item.get("RecordDate", ""))[:10]
        if d_str:
            try:
                target_date = datetime.strptime(d_str, "%Y-%m-%d").date()
                if today_date <= target_date <= max_warning_date:
                    alerts.append(f"💣 【地雷警戒】配当権利落ち日が接近中 ({d_str})")
                    break
            except: pass

    for item in event_data.get("earnings", []):
        if str(item.get("Code", ""))[:4] != c: continue
        d_str = str(item.get("Date", item.get("DisclosedDate", "")))[:10]
        if d_str:
            try:
                target_date = datetime.strptime(d_str, "%Y-%m-%d").date()
                if today_date <= target_date <= max_warning_date:
                    alerts.append(f"🔥 【地雷警戒】決算発表が接近中 ({d_str})")
                    break
            except: pass

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

@st.cache_data(ttl=3600, show_spinner=False)
def get_single_data(code, yrs=3):
    import time
    base = datetime.utcnow() + timedelta(hours=9)
    f_d = (base - timedelta(days=365*yrs)).strftime('%Y%m%d')
    t_d = base.strftime('%Y%m%d')
    result = {"bars": [], "events": {"dividend": [], "earnings": []}}
    try:
        api_code = str(code) if len(str(code)) >= 5 else str(code) + "0"
        url = f"{BASE_URL}/equities/bars/daily?code={api_code}&from={f_d}&to={t_d}"
        while url:
            r_bars = requests.get(url, headers=headers, timeout=15)
            if r_bars.status_code == 200:
                data = r_bars.json()
                quotes = data.get("daily_quotes") or data.get("data") or []
                result["bars"].extend(quotes)
                p_key = data.get("pagination_key")
                if p_key:
                    url = f"{BASE_URL}/equities/bars/daily?code={api_code}&from={f_d}&to={t_d}&pagination_key={p_key}"
                    time.sleep(0.1)
                else: url = None
            else: break
        r_div = requests.get(f"{BASE_URL}/fins/dividend?code={api_code}", headers=headers, timeout=10)
        if r_div.status_code == 200: result["events"]["dividend"] = r_div.json().get("dividend") or r_div.json().get("data") or []
    except: pass
    return result

@st.cache_data(ttl=3600, max_entries=2, show_spinner=False)
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

def get_fast_indicators(prices):
    if len(prices) < 15: return 50.0, 0.0, 0.0, np.zeros(5)
    a12, a26, a9 = 2.0/13.0, 2.0/27.0, 2.0/10.0
    e12, e26 = prices[0], prices[0]
    macd_arr = np.zeros(len(prices))
    for i in range(len(prices)):
        e12 = a12 * prices[i] + (1 - a12) * e12
        e26 = a26 * prices[i] + (1 - a26) * e26
        macd_arr[i] = e12 - e26
    signal = macd_arr[0]
    hist_arr = np.zeros(len(prices))
    for i in range(len(prices)):
        signal = a9 * macd_arr[i] + (1 - a9) * signal
        hist_arr[i] = macd_arr[i] - signal
    deltas = np.diff(prices)
    gains = np.maximum(deltas, 0)
    losses = np.maximum(-deltas, 0)
    a_rsi = 1.0/14.0
    ag, al = gains[0], losses[0]
    for i in range(1, len(gains)):
        ag = a_rsi * gains[i] + (1 - a_rsi) * ag
        al = a_rsi * losses[i] + (1 - a_rsi) * al
    rs = ag / (al + 1e-10)
    rsi = 100.0 - (100.0 / (1.0 + rs))
    return rsi, hist_arr[-1], hist_arr[-2], hist_arr[-5:]

def calc_technicals(df):
    df = df.copy()
    if len(df) < 16:
        df['RSI'] = 50; df['MACD'] = 0; df['MACD_Signal'] = 0; df['MACD_Hist'] = 0; df['ATR'] = 0; df['MA5'] = df['AdjC']; df['MA25'] = df['AdjC']; df['MA75'] = df['AdjC']; return df
    df = df.replace([np.inf, -np.inf], np.nan)
    df.ffill(inplace=True) # 🚨 非推奨メソッド(method='ffill')を安全なffill()へ換装
    df.fillna(0, inplace=True)
    delta = df['AdjC'].diff()
    gain = delta.where(delta > 0, 0)
    loss = -delta.where(delta < 0, 0)
    loss_ewm = loss.ewm(alpha=1/14, adjust=False).mean()
    loss_ewm = loss_ewm.replace(0, 0.0001)
    rs = gain.ewm(alpha=1/14, adjust=False).mean() / loss_ewm
    df['RSI'] = 100 - (100 / (1 + rs))
    df['RSI'] = df['RSI'].fillna(50)
    macd = df['AdjC'].ewm(span=12, adjust=False).mean() - df['AdjC'].ewm(span=26, adjust=False).mean()
    df['MACD'] = macd
    df['MACD_Signal'] = macd.ewm(span=9, adjust=False).mean()
    df['MACD_Hist'] = df['MACD'] - df['MACD_Signal']
    temp_close = df['AdjC'].ffill()
    df['MA5'] = temp_close.rolling(window=5).mean()
    df['MA25'] = temp_close.rolling(window=25).mean()
    df['MA75'] = temp_close.rolling(window=75).mean()
    tr = pd.concat([df['AdjH'] - df['AdjL'], (df['AdjH'] - df['AdjC'].shift(1)).abs(), (df['AdjL'] - df['AdjC'].shift(1)).abs()], axis=1).max(axis=1)
    df['ATR'] = tr.rolling(window=14).mean()
    df.fillna(0, inplace=True)
    return df

def get_triage_info(macd_hist, macd_hist_prev, rsi, lc=0, bt=0, mode="待伏", gc_days=0):
    if macd_hist > 0 and macd_hist_prev <= 0: macd_t = "GC直後"
    elif macd_hist > macd_hist_prev: macd_t = "上昇拡大"
    elif macd_hist < 0 and macd_hist < macd_hist_prev: macd_t = "下落継続"
    else: macd_t = "減衰"

    if mode == "強襲":
        if macd_t == "下落継続" or rsi >= 75: return "圏外（手出し無用）🚫", "#d32f2f", 0, macd_t
        if gc_days == 1:
            if rsi <= 50: return "S（即時狙撃）🔥", "#2e7d32", 5, "GC直後(1日目)"
            else: return "A（強襲追撃）⚡", "#ed6c02", 4, "GC直後(1日目)"
        elif gc_days == 2:
            if rsi <= 55: return "A（強襲追撃）⚡", "#ed6c02", 4, "GC継続(2日目)"
            else: return "B（順張り警戒）📈", "#0288d1", 3, "GC継続(2日目)"
        elif gc_days >= 3:
            return "B（順張り警戒）📈", "#0288d1", 3, f"GC継続({gc_days}日目)"
        else: return "C（条件外・監視）👁️", "#616161", 1, macd_t
    else:
        if bt == 0 or lc == 0: return "C（計算不能）👁️", "#616161", 1, macd_t
        dist_pct = ((lc / bt) - 1) * 100 
        if dist_pct < -2.0: return "圏外（防衛線突破）💀", "#d32f2f", 0, macd_t
        elif dist_pct <= 2.0:
            if rsi <= 45: return "S（迎撃態勢）🔥", "#2e7d32", 5, macd_t
            else: return "A（接近中）⚡", "#ed6c02", 4.5, macd_t 
        elif dist_pct <= 5.0:
            if rsi <= 50: return "A（罠の設置）🪤", "#0288d1", 4.0, macd_t 
            else: return "B（高高度）📈", "#0288d1", 3, macd_t
        else: return "C（射程外・監視）👁️", "#616161", 1, macd_t

def render_technical_radar(df, buy_price, tp_pct):
    if df.empty or len(df) < 2: return ""
    latest = df.iloc[-1]; prev = df.iloc[-2]
    rsi = latest.get('RSI', 50); macd_hist = latest.get('MACD_Hist', 0); macd_hist_prev = prev.get('MACD_Hist', 0); atr = latest.get('ATR', 0)
    rsi_color = "#ef5350" if rsi <= 30 else "#FFD700" if rsi <= 45 else "#888888"
    rsi_text = "🔥 超売られすぎ" if rsi <= 30 else "⚡ 売られすぎ" if rsi <= 45 else "⚖️ 中立"
    if rsi >= 70: rsi_color = "#26a69a"; rsi_text = "⚠️ 買われすぎ"

    _, _, _, macd_t = get_triage_info(macd_hist, macd_hist_prev, rsi)

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

def draw_chart(df, targ_p, tp5=None, tp10=None, tp15=None, tp20=None, chart_key=None):
    from datetime import timedelta
    df = df.copy()
    fig = go.Figure()
    fig.add_trace(go.Candlestick(x=df['Date'], open=df['AdjO'], high=df['AdjH'], low=df['AdjL'], close=df['AdjC'], name='株価', increasing_line_color='#26a69a', decreasing_line_color='#ef5350'))
    if 'MA5' in df.columns: fig.add_trace(go.Scatter(x=df['Date'], y=df['MA5'], mode='lines', name='5日', line=dict(color='rgba(156, 39, 176, 0.7)', width=1.5), connectgaps=True))
    if 'MA25' in df.columns: fig.add_trace(go.Scatter(x=df['Date'], y=df['MA25'], mode='lines', name='25日', line=dict(color='rgba(33, 150, 243, 0.7)', width=1.5), connectgaps=True))
    if 'MA75' in df.columns: fig.add_trace(go.Scatter(x=df['Date'], y=df['MA75'], mode='lines', name='75日', line=dict(color='rgba(255, 152, 0, 0.7)', width=1.5), connectgaps=True))
    fig.add_trace(go.Scatter(x=df['Date'], y=[targ_p]*len(df), mode='lines', name='買値目標', line=dict(color='#FFD700', width=2, dash='dash')))
    last_date = df['Date'].max()
    start_date = last_date - timedelta(days=45) if len(df) > 30 else df['Date'].min()
    fig.update_layout(height=450, margin=dict(l=0, r=60, t=30, b=40), xaxis_rangeslider_visible=True, xaxis=dict(range=[start_date, last_date + timedelta(days=0.5)], type="date"), yaxis=dict(tickformat=",.0f", side="right"), paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)', hovermode="x unified", legend=dict(orientation="h", yanchor="top", y=-0.1, xanchor="center", x=0.5))
    st.plotly_chart(fig, use_container_width=True, config={'displayModeBar': True, 'displaylogo': False}, key=chart_key)

# --- 4. サイドバー UI ---
if 'preset_target' not in st.session_state: st.session_state.preset_target = "🚀 中小型株 (50%押し・標準)"
if 'sidebar_tactics' not in st.session_state: st.session_state.sidebar_tactics = "⚖️ バランス (掟達成率 ＞ 到達度)"
if 'push_r' not in st.session_state: st.session_state.push_r = 50.0 

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
market_filter_mode = "大型" if "大型株" in st.session_state.preset_target else "中小型"

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

st.sidebar.markdown("#### 🚨 掟⑥：除外ブラックリスト")
GIGI_FILE = f"saved_gigi_mines_{user_id}.txt"
default_gigi = "2134, 3350, 6172, 6740, 7647, 8783, 8836, 8925, 9318"
if os.path.exists(GIGI_FILE):
    with open(GIGI_FILE, "r", encoding="utf-8") as f:
        default_gigi = f.read()

gigi_input = st.sidebar.text_area("疑義注記・ボロ株コード (カンマ区切り)", value=default_gigi, height=100)
with open(GIGI_FILE, "w", encoding="utf-8") as f:
    f.write(gigi_input)

extracted_codes = re.findall(r'\b\d{4}\b(?!\s*[/年-])', gigi_input)
gigi_mines_list = list(dict.fromkeys(extracted_codes))

st.sidebar.divider()
st.sidebar.markdown("### 🛠️ システム管理")
if st.sidebar.button("🔴 キャッシュ強制パージ (API遅延時用)", use_container_width=True):
    st.cache_data.clear()
    st.session_state.tab1_scan_results = None
    st.session_state.tab2_scan_results = None
    st.session_state.tab5_ifd_results = None
    st.sidebar.success("全記憶を強制パージしました。最新データを再取得します。")
    st.rerun()

# ==========================================
# 5. タブ再構成
# ==========================================
tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs([
    "🌐 【待伏】広域レーダー", "⚡ 【強襲】GC初動レーダー", "🎯 【照準】精密スコープ", 
    "⚙️ 【演習】戦術シミュレータ", "⛺ 【戦線】交戦モニター", "📁 【戦歴】交戦データベース"
])
master_df = load_master()
tactics_mode = st.session_state.sidebar_tactics

with tab1:
    st.markdown('<h3 style="font-size: clamp(14px, 4.5vw, 24px); margin-bottom: 1rem;">🎯 【待伏】鉄の掟・半値押しレーダー</h3>', unsafe_allow_html=True)
    if 'tab1_scan_results' not in st.session_state: st.session_state.tab1_scan_results = None
    run_scan_t1 = st.button("🚀 最新データで待伏スキャン開始")
    exclude_etf_flag_t1 = st.sidebar.checkbox("ETF・REITを除外 (待伏)", value=True, key="tab1_etf_filter")

    if run_scan_t1:
        st.toast("🟢 待伏トリガーを確認。索敵開始！", icon="🎯")
        with st.spinner("全銘柄から適合ターゲットを索敵中..."):
            raw = get_hist_data_cached()
            if not raw:
                st.error("データの取得に失敗しました。")
                st.session_state.tab1_scan_results = None
            else:
                df = clean_df(pd.DataFrame(raw)).dropna(subset=['AdjC', 'AdjH', 'AdjL']).sort_values(['Code', 'Date'])
                v_col = next((col for col in df.columns if col in ['Volume', 'AdjVo', 'Vo', 'AdjustmentVolume']), None)
                if v_col:
                    df[v_col] = pd.to_numeric(df[v_col], errors='coerce').fillna(0)
                    avg_vols = df.groupby('Code').tail(5).groupby('Code')[v_col].mean()
                else: avg_vols = pd.Series(0, index=df['Code'].unique())

                latest_date = df['Date'].max()
                latest_df = df[df['Date'] == latest_date]
                valid_price_codes = latest_df[latest_df['AdjC'] >= 200]['Code'].unique()
                valid_vol_codes = avg_vols[avg_vols >= 10000].index
                valid_codes = set(valid_price_codes).intersection(set(valid_vol_codes))
                df = df[df['Code'].isin(valid_codes)]

                if exclude_etf_flag_t1 and 'master_df' in globals() and not master_df.empty:
                    invalid_mask = master_df['Market'].astype(str).str.contains('ETF|REIT', case=False, na=False) | master_df['Sector'].astype(str).str.contains('ETF|REIT|投信', case=False, na=False)
                    valid_codes = master_df[~invalid_mask]['Code'].unique()
                    df = df[df['Code'].isin(valid_codes)]

                if 'master_df' in globals() and not master_df.empty:
                    if "大型株" in st.session_state.preset_target: m_mask = master_df['Market'].astype(str).str.contains('プライム|一部', na=False)
                    else: m_mask = master_df['Market'].astype(str).str.contains('スタンダード|グロース|新興|マザーズ|JASDAQ|二部', na=False)
                    df = df[df['Code'].isin(master_df[m_mask]['Code'].unique())]

                if f8_ex_bio and 'master_df' in globals() and not master_df.empty:
                    df = df[df['Code'].isin(master_df[~master_df['Sector'].astype(str).str.contains('医薬品', case=False, na=False)]['Code'].unique())]

                if gigi_input:
                    target_blacklist = re.findall(r'\d{4}', str(gigi_input))
                    if target_blacklist:
                        df['Temp_Code'] = df['Code'].astype(str).str.extract(r'(\d{4})')[0]
                        df = df[~df['Temp_Code'].isin(target_blacklist)].drop(columns=['Temp_Code'])

                master_dict = master_df.set_index('Code')[['CompanyName', 'Market', 'Sector', 'Scale']].to_dict('index') if not master_df.empty else {}
                push_ratio = 0.618 if "61.8%" in st.session_state.preset_target else 0.250 if "25%" in st.session_state.preset_target else 0.500
                min14 = float(f9_min14); max14 = float(f9_max14)

                results = []
                for code, group in df.groupby('Code'):
                    if len(group) < 15: continue
                    avg_vol = int(avg_vols.get(code, 0))
                    if avg_vol < 10000: continue
                    adjc_vals = group['AdjC'].values
                    adjh_vals = group['AdjH'].values
                    adjl_vals = group['AdjL'].values
                    lc = adjc_vals[-1]
                    recent_4d_h = adjh_vals[-4:]
                    local_max_idx = recent_4d_h.argmax()
                    high_4d_val = recent_4d_h[local_max_idx]
                    global_max_idx = len(adjh_vals) - 4 + local_max_idx
                    low_10d_val = adjl_vals[max(0, global_max_idx - 10) : global_max_idx + 1].min()

                    if low_10d_val <= 0: continue
                    if not (min14 <= high_4d_val / low_10d_val <= max14): continue
                    wave_len = high_4d_val - low_10d_val
                    if wave_len <= 0: continue
                    rsi, macd_h, macd_h_prev, _ = get_fast_indicators(adjc_vals)
                    target_buy = high_4d_val - (wave_len * push_ratio)
                    reach_rate = (target_buy / lc) * 100
                    
                    m_info = master_dict.get(code, {})
                    c_name = m_info.get('CompanyName', f"銘柄 {code[:4]}")
                    c_market = m_info.get('Market', '不明'); c_sector = m_info.get('Sector', '不明'); c_scale = m_info.get('Scale', '不明')
                    rank, bg, t_score, _ = get_triage_info(macd_h, macd_h_prev, rsi, lc, target_buy, mode="待伏")

                    results.append({'Code': code, 'Name': c_name, 'Sector': c_sector, 'Market': c_market, 'Scale': c_scale, 'lc': lc, 'RSI': rsi, 'avg_vol': avg_vol, 'high_4d': high_4d_val, 'low_14d': low_10d_val, 'target_buy': target_buy, 'reach_rate': reach_rate, 'triage_rank': rank, 'triage_bg': bg, 't_score': t_score})
                        
                if not results:
                    st.warning("現在、掟を満たすターゲットは存在しません。")
                    st.session_state.tab1_scan_results = []
                else:
                    st.session_state.tab1_scan_results = sorted(results, key=lambda x: x['t_score'], reverse=True)[:30]
                import gc; gc.collect()

    if st.session_state.tab1_scan_results:
        light_results = st.session_state.tab1_scan_results
        st.success(f"🎯 待伏ロックオン: {len(light_results)} 銘柄を確認。")
        sa_codes = " ".join([str(r.get('Code', ''))[:4] for r in light_results if str(r.get('triage_rank', '')).startswith(('S', 'A'))])
        other_codes = " ".join([str(r.get('Code', ''))[:4] for r in light_results if not str(r.get('triage_rank', '')).startswith(('S', 'A'))])
        
        st.info("📋 以下のコードをコピーして、照準（TAB3）にペースト可能です。")
        if sa_codes:
            st.markdown("**🎯 優先度 S・A (主力標的)**")
            st.code(sa_codes, language="text")
        if other_codes:
            with st.expander("👀 優先度 B・C・圏外 (監視対象)"): st.code(other_codes, language="text")
        
        for r in light_results:
            st.divider()
            c = str(r.get('Code', '0000')); n = r.get('Name', f"銘柄 {c[:4]}")
            m_lower = str(r.get('Market', '不明')).lower()
            if 'プライム' in m_lower or '一部' in m_lower: badge_html = '<span style="background-color: #1a237e; color: #ffffff; padding: 0.2rem 0.6rem; border-radius: 4px; font-size: 11px; font-weight: bold;">🏢 プライム/大型</span>'
            elif 'グロース' in m_lower or 'マザーズ' in m_lower: badge_html = '<span style="background-color: #1b5e20; color: #ffffff; padding: 0.2rem 0.6rem; border-radius: 4px; font-size: 11px; font-weight: bold;">🚀 グロース/新興</span>'
            else: badge_html = f'<span style="background-color: #455a64; color: #ffffff; padding: 0.2rem 0.6rem; border-radius: 4px; font-size: 11px; font-weight: bold;">{r.get("Market")}</span>'
            
            triage_badge = f'<span style="background-color: {r.get("triage_bg")}; color: #ffffff; padding: 0.2rem 0.6rem; border-radius: 4px; font-size: 13px; display: inline-block; font-weight: bold; margin-left: 0.5rem;">🎯 優先度: {r.get("triage_rank")}</span>'
            swing_pct = ((r.get('high_4d', 0) - r.get('low_14d', 0)) / r.get('low_14d', 1)) * 100
            volatility_badge = f'<span style="background-color: #ff9800; color: #ffffff; padding: 0.2rem 0.6rem; border-radius: 4px; font-size: 11px; font-weight: bold; margin-left: 0.5rem; border: 1px solid #e65100;">⚡ 高ボラ ({swing_pct:.1f}%)</span>' if swing_pct >= (40.0 if ('プライム' in m_lower or '一部' in m_lower) else 60.0) else ""

            st.markdown(f"""
                <div style="margin-bottom: 0.8rem;">
                    <h3 style="font-size: clamp(18px, 5vw, 28px); font-weight: bold; margin: 0 0 0.3rem 0;">({c[:4]}) {n}</h3>
                    <div style="display: flex; flex-wrap: wrap; gap: 6px; align-items: center;">
                        {badge_html}{triage_badge}{volatility_badge}
                        <span style="background-color: rgba(38, 166, 154, 0.15); border: 1px solid #26a69a; color: #26a69a; padding: 0.1rem 0.5rem; border-radius: 4px; font-size: 12px;">RSI: {r.get("RSI", 50):.1f}%</span>
                        <span style="background-color: rgba(255, 215, 0, 0.1); border: 1px solid #FFD700; color: #FFD700; padding: 0.1rem 0.5rem; border-radius: 4px; font-size: 12px;">到達度: {r.get('reach_rate'):.1f}%</span>
                    </div>
                </div>
            """, unsafe_allow_html=True)
            
            m_cols = st.columns([1, 1, 1, 1.2, 1.5])
            m_cols[0].metric("直近高値", f"{int(r.get('high_4d', 0)):,}円")
            m_cols[1].metric("起点安値", f"{int(r.get('low_14d', 0)):,}円")
            m_cols[2].metric("最新終値", f"{int(r.get('lc', 0)):,}円")
            m_cols[3].metric("平均出来高(5日)", f"{int(r.get('avg_vol', 0)):,}株")
            html_buy = f"""
            <div style="background: rgba(255, 215, 0, 0.05); padding: 0.5rem; border-radius: 8px; border: 1px solid rgba(255, 215, 0, 0.2); text-align: center;">
                <div style="font-size: 13px; color: rgba(250, 250, 250, 0.6); margin-bottom: 2px;">🎯 半値押し 買値目標</div>
                <div style="font-size: 1.8rem; font-weight: bold; color: #FFD700;">{int(r.get('target_buy', 0)):,}<span style="font-size: 14px; margin-left:2px;">円</span></div>
            </div>"""
            m_cols[4].markdown(html_buy, unsafe_allow_html=True)
            st.caption(f"🏢 {r.get('Market','不明')} ｜ 🏭 {r.get('Sector','不明')}")

with tab2:
    st.markdown('<h3 style="font-size: clamp(14px, 4.5vw, 24px); margin-bottom: 1rem;">⚡ 【強襲】GC初動レーダー</h3>', unsafe_allow_html=True)
    if 'tab2_scan_results' not in st.session_state: st.session_state.tab2_scan_results = None
    col_t2_1, col_t2_2 = st.columns(2)
    rsi_limit = col_t2_1.number_input("RSI上限（過熱感の足切り）", value=60, step=5)
    vol_limit = col_t2_2.number_input("最低出来高（5日平均）", value=15000, step=5000)
    
    run_scan_t2 = st.button("🚀 全軍GC初動スキャン開始", key="btn_assault_scan")
    exclude_ipo_flag = st.sidebar.checkbox("IPO銘柄を除外 (強襲)", value=True, key="tab2_ipo_filter")
    exclude_etf_flag_t2 = st.sidebar.checkbox("ETF・REITを除外 (強襲)", value=True, key="tab2_etf_filter")

    if run_scan_t2:
        st.toast("🟢 強襲トリガーを確認。索敵開始！", icon="🚀")
        with st.spinner("全銘柄の波形からGC初動候補を抽出中..."):
            raw = get_hist_data_cached()
            if not raw:
                st.error("データの取得に失敗しました。")
            else:
                df = clean_df(pd.DataFrame(raw)).dropna(subset=['AdjC', 'AdjH', 'AdjL']).sort_values(['Code', 'Date'])
                v_col = next((col for col in df.columns if col in ['Volume', 'AdjVo', 'Vo', 'AdjustmentVolume']), None)
                if v_col:
                    df[v_col] = pd.to_numeric(df[v_col], errors='coerce').fillna(0)
                    avg_vols = df.groupby('Code').tail(5).groupby('Code')[v_col].mean()
                else: avg_vols = pd.Series(0, index=df['Code'].unique())

                latest_date = df['Date'].max()
                latest_df = df[df['Date'] == latest_date]
                valid_price_codes = latest_df[latest_df['AdjC'] >= 200]['Code'].unique()
                valid_vol_codes = avg_vols[avg_vols >= vol_limit].index
                valid_codes = set(valid_price_codes).intersection(set(valid_vol_codes))
                df = df[df['Code'].isin(valid_codes)]

                if exclude_etf_flag_t2 and 'master_df' in globals() and not master_df.empty:
                    invalid_mask = master_df['Market'].astype(str).str.contains('ETF|REIT', case=False, na=False) | master_df['Sector'].astype(str).str.contains('ETF|REIT|投信', case=False, na=False)
                    df = df[df['Code'].isin(master_df[~invalid_mask]['Code'].unique())]

                # 🚨 重複していた辞書化処理を片方パージ
                master_dict = master_df.set_index('Code')[['CompanyName', 'Market', 'Sector', 'Scale']].to_dict('index') if not master_df.empty else {}

                results = []
                for code, group in df.groupby('Code'):
                    if exclude_ipo_flag and len(group) < 20: continue
                    if len(group) < 15: continue
                    avg_vol = int(avg_vols.get(code, 0))
                    if avg_vol < vol_limit: continue
                    adjc_vals = group['AdjC'].values
                    rsi, macd_h, macd_h_prev, hist_5d = get_fast_indicators(adjc_vals)
                    if rsi > rsi_limit: continue

                    gc_days = 0
                    if hist_5d[-2] < 0 and hist_5d[-1] >= 0: gc_days = 1
                    elif hist_5d[-3] < 0 and hist_5d[-2] >= 0 and hist_5d[-1] >= 0: gc_days = 2
                    elif hist_5d[-4] < 0 and hist_5d[-3] >= 0 and hist_5d[-2] >= 0 and hist_5d[-1] >= 0: gc_days = 3
                    if gc_days == 0: continue

                    lc = adjc_vals[-1]; adjh_vals = group['AdjH'].values; adjl_vals = group['AdjL'].values
                    if len(adjh_vals) >= 4:
                        local_max_idx = adjh_vals[-4:].argmax()
                        high_4d_val = adjh_vals[-4:][local_max_idx]
                        low_10d_val = adjl_vals[max(0, len(adjh_vals) - 4 + local_max_idx - 10) : len(adjh_vals) - 4 + local_max_idx + 1].min()
                    else: high_4d_val = lc; low_10d_val = lc

                    t_rank, t_color, t_score, t_macd = get_triage_info(macd_h, macd_h_prev, rsi, mode="強襲", gc_days=gc_days)

                    if len(adjc_vals) >= 75:
                        ma5 = adjc_vals[-5:].mean(); ma25 = adjc_vals[-25:].mean(); ma75 = adjc_vals[-75:].mean()
                        strict_score = 0
                        current_vol = group[v_col].values[-1] if v_col in group.columns else 0
                        if current_vol > (avg_vol * 1.5): strict_score += 3
                        elif current_vol > (avg_vol * 1.2): strict_score += 1
                        if lc > ma5 and ma5 > ma25 and ma25 > ma75: strict_score += 3
                        if macd_h > 0 and macd_h > macd_h_prev: strict_score += 2
                        if 55 <= rsi <= 70: strict_score += 2
                        elif 70 < rsi <= 80: strict_score += 1

                        if strict_score >= 9: t_rank = "S"; t_color = "#e53935"
                        elif strict_score >= 7: t_rank = "A"; t_color = "#fb8c00"
                        elif strict_score >= 5: t_rank = "B"; t_color = "#fdd835"
                        else: t_rank = "C"; t_color = "#616161"
                        t_score = strict_score 
                    else:
                        t_rank = "C"; t_color = "#616161"; t_score = 0

                    m_info = master_dict.get(code, {})
                    c_name = m_info.get('CompanyName', f"銘柄 {code[:4]}")
                    c_market = m_info.get('Market', '不明'); c_sector = m_info.get('Sector', '不明')
                    scale_val = str(m_info.get('Scale', ''))
                    c_scale = "🏢 大型/中型" if any(x in scale_val for x in ["Core30", "Large70", "Mid400"]) else "🚀 小型/新興" if scale_val and scale_val != 'nan' and scale_val != '-' else "🐣 グロース/新興"

                    results.append({'Code': code, 'Name': c_name, 'Sector': c_sector, 'Market': c_market, 'Scale': c_scale, 'lc': lc, 'RSI': rsi, 'avg_vol': avg_vol, 'high_val': high_4d_val, 'low_val': low_10d_val, 'T_Rank': t_rank, 'T_Color': t_color, 'T_Score': t_score, 'GC_Days': gc_days})
                        
                if not results:
                    st.warning("現在、GC初動条件を満たすターゲットは存在しません。")
                    st.session_state.tab2_scan_results = []
                else:
                    st.session_state.tab2_scan_results = sorted(results, key=lambda x: (-x['T_Score'], x['GC_Days'], x['RSI']))[:30]
                import gc; gc.collect()

    if st.session_state.tab2_scan_results:
        light_results = st.session_state.tab2_scan_results
        st.success(f"⚡ 強襲ロックオン: GC初動(3日以内) 上位 {len(light_results)} 銘柄を確認。")
        sa_codes = " ".join([str(r.get('Code', ''))[:4] for r in light_results if str(r.get('T_Rank', '')).startswith(('S', 'A'))])
        other_codes = " ".join([str(r.get('Code', ''))[:4] for r in light_results if not str(r.get('T_Rank', '')).startswith(('S', 'A'))])
        
        st.info("📋 以下のコードをコピーして、照準（TAB3）にペースト可能です。")
        if sa_codes: st.markdown("**🎯 優先度 S・A (主力標的)**"); st.code(sa_codes, language="text")
        if other_codes:
            with st.expander("👀 優先度 B・C・圏外 (監視対象)"): st.code(other_codes, language="text")
        
        for r in light_results:
            st.divider()
            c = str(r.get('Code', '0000')); n = r.get('Name', f"銘柄 {c[:4]}")
            m_lower = str(r.get('Market', '不明')).lower()
            if 'プライム' in m_lower or '一部' in m_lower: badge_html = '<span style="background-color: #1a237e; color: #ffffff; padding: 0.2rem 0.6rem; border-radius: 4px; font-size: 11px; font-weight: bold;">🏢 プライム/大型</span>'
            elif 'グロース' in m_lower or 'マザーズ' in m_lower: badge_html = '<span style="background-color: #1b5e20; color: #ffffff; padding: 0.2rem 0.6rem; border-radius: 4px; font-size: 11px; font-weight: bold;">🚀 グロース/新興</span>'
            else: badge_html = f'<span style="background-color: #455a64; color: #ffffff; padding: 0.2rem 0.6rem; border-radius: 4px; font-size: 11px; font-weight: bold;">{r.get("Market")}</span>'

            triage_badge = f'<span style="background-color: {r.get("T_Color", "#616161")}; color: #ffffff; padding: 0.2rem 0.6rem; border-radius: 4px; font-size: 13px; display: inline-block; font-weight: bold; margin-left: 0.5rem;">🎯 優先度: {r.get("T_Rank")}</span>'
            swing_pct = ((r.get('high_val', 0) - r.get('low_val', 0)) / r.get('low_val', 1)) * 100 if r.get('low_val', 0) > 0 else 0
            volatility_badge = f'<span style="background-color: #ff9800; color: #ffffff; padding: 0.2rem 0.6rem; border-radius: 4px; font-size: 11px; font-weight: bold; margin-left: 0.5rem; border: 1px solid #e65100;">⚡ 高ボラ ({swing_pct:.1f}%)</span>' if swing_pct >= (40.0 if ('プライム' in m_lower or '一部' in m_lower) else 60.0) else ""

            st.markdown(f"""
                <div style="margin-bottom: 0.8rem;">
                    <h3 style="font-size: clamp(16px, 5vw, 26px); font-weight: bold; margin: 0 0 0.3rem 0;">({c[:4]}) {n}</h3>
                    <div style="display: flex; flex-wrap: wrap; gap: 4px; align-items: center;">
                        {badge_html}{triage_badge}{volatility_badge}
                        <span style="background-color: rgba(237, 108, 2, 0.15); border: 1px solid #ed6c02; color: #ed6c02; padding: 0.1rem 0.5rem; border-radius: 4px; font-size: 12px; margin-left: 4px;">GC後 {r.get('GC_Days')}日目</span>
                    </div>
                </div>
            """, unsafe_allow_html=True)
            
            lc_val = r.get('lc', 0)
            m_cols = st.columns([1, 1, 1, 1.2, 1.5])
            m_cols[0].metric("最新終値", f"{int(lc_val):,}円")
            m_cols[1].metric("RSI (過熱感)", f"{r.get('RSI', 50):.1f}%")
            m_cols[2].metric("出来高(5日)", f"{int(r.get('avg_vol', 0)):,}株")
            
            html_sl = f"""<div style="background: rgba(239, 83, 80, 0.05); padding: 0.5rem; border-radius: 8px; border: 1px solid rgba(239, 83, 80, 0.3); text-align: center;">
                <div style="font-size: 13px; color: rgba(250, 250, 250, 0.6); margin-bottom: 2px;">🛡️ 逆指値目安 (強襲)</div>
                <div style="font-size: 1.6rem; font-weight: bold; color: #ef5350;">{int(lc_val * 0.95):,}<span style="font-size: 14px; margin-left:2px;">円</span></div></div>"""
            m_cols[3].markdown(html_sl, unsafe_allow_html=True)

            html_buy_assault = f"""<div style="background: rgba(255, 215, 0, 0.05); padding: 0.5rem; border-radius: 8px; border: 1px solid rgba(255, 215, 0, 0.2); text-align: center;">
                <div style="font-size: 13px; color: rgba(250, 250, 250, 0.6); margin-bottom: 2px;">🎯 終値+1% 買値目標</div>
                <div style="font-size: 1.6rem; font-weight: bold; color: #FFD700;">{int(lc_val * 1.01):,}<span style="font-size: 14px; margin-left:2px;">円</span></div></div>"""
            m_cols[4].markdown(html_buy_assault, unsafe_allow_html=True)
            st.caption(f"🏢 {r.get('Market','不明')} ｜ 🏭 {r.get('Sector','不明')}")

with tab3:
    st.markdown('<h3 style="font-size: clamp(14px, 4.5vw, 24px); margin-bottom: 1rem;">🎯 【照準】精密スコープ（個別銘柄・深堀りスキャン）</h3>', unsafe_allow_html=True)
    col_s1, col_s2 = st.columns([1, 2])
    T3_SCOPE_FILE = f"saved_t3_scope_{user_id}.txt"
    default_scope = "6614\n4427"
    if os.path.exists(T3_SCOPE_FILE):
        with open(T3_SCOPE_FILE, "r", encoding="utf-8") as f: default_scope = f.read()
            
    with col_s1:
        scope_mode = st.radio("🎯 解析モード（戦術）を選択", ["🌐 【待伏】 押し目・逆張り", "⚡ 【強襲】 トレンド・順張り"], key="t3_scope_mode")
        target_codes_str = st.text_area("標的コード（複数可、改行区切り）", value=default_scope, height=100)
        run_scope = st.button("🔫 精密スキャン実行", use_container_width=True)
        
    with col_s2:
        st.markdown("#### 🔍 解析対象データ")
        if "待伏" in scope_mode: st.info("・ボスの「鉄の掟」に基づく押し目ライン(半値押し等)と適合度\n・トレンド崩壊、落ちるナイフ、危険波形（三尊等）の検知\n・待伏ロジックに基づくSABC優先度判定")
        else: st.warning("・MACDクロス（GC）からの経過日数とRSIの過熱感\n・順張り用の逆指値（ロスカット）と上値ターゲットの算出\n・強襲ロジックに基づくSABC優先度判定")

    if run_scope and target_codes_str:
        with open(T3_SCOPE_FILE, "w", encoding="utf-8") as f: f.write(target_codes_str)
        t_codes = list(dict.fromkeys([c.upper() for c in re.findall(r'(?<![a-zA-Z0-9])[a-zA-Z0-9]{4}(?![a-zA-Z0-9])', target_codes_str)]))
        
        if not t_codes: st.warning("有効な4桁の銘柄コードが見つかりません。")
        else:
            with st.spinner(f"指定された {len(t_codes)} 銘柄を精密計算中..."):
                scope_results = []
                for c in t_codes:
                    api_code = c if len(c) == 5 else c + "0"
                    raw_s = get_single_data(api_code, 1)
                    if not raw_s: continue
                    bars_data = raw_s.get("bars", []) if isinstance(raw_s, dict) else raw_s
                    df_s = clean_df(pd.DataFrame(bars_data))
                    if len(df_s) < 30: continue
                        
                    df_chart = calc_technicals(df_s.copy())
                    df_14 = df_s.tail(10); df_30 = df_s.tail(30)
                    latest = df_chart.iloc[-1]; prev = df_chart.iloc[-2] if len(df_chart) > 1 else latest
                    
                    lc = latest['AdjC']; h14 = df_14['AdjH'].max(); l14 = df_14['AdjL'].min()
                    if pd.isna(h14) or pd.isna(l14) or l14 <= 0: continue
                    
                    ur = h14 - l14
                    daily_pct = (lc / prev['AdjC']) - 1 if prev['AdjC'] > 0 else 0
                    is_dt = check_double_top(df_14); is_hs = check_head_shoulders(df_14); is_db = check_double_bottom(df_14)
                    is_defense = (not is_dt) and (not is_hs) and (lc <= (l14 * 1.03))
                    
                    m_row = master_df[master_df['Code'] == api_code] if not master_df.empty else pd.DataFrame()
                    c_name = m_row.iloc[0]['CompanyName'] if not m_row.empty else f"銘柄 {c[:4]}"
                    c_market = m_row.iloc[0]['Market'] if not m_row.empty else "不明"
                    c_sector = m_row.iloc[0].get('Sector', '不明') if not m_row.empty else "不明"
                    c_scale = m_row.iloc[0].get('Scale', '') if not m_row.empty else ""
                        
                    macd_h = latest.get('MACD_Hist', 0); macd_h_prev = prev.get('MACD_Hist', 0)
                    rsi_v = latest.get('RSI', 50); atr_val = int(latest.get('ATR', 0))
                    avg_vol = int(df_s['AdjVo'].tail(5).mean()) if 'AdjVo' in df_s.columns else 0
                    
                    bt_val = 0; reach_val = 0; sl_val = 0; tp_val = 0; gc_days = 0; is_bt_broken = False; is_trend_broken = False
                    if "待伏" in scope_mode:
                        bt_primary = h14 - (ur * (st.session_state.push_r / 100.0))
                        shift_ratio = 0.618 if st.session_state.push_r >= 40 else (st.session_state.push_r / 100.0 + 0.15)
                        bt_secondary = h14 - (ur * shift_ratio)
                        is_bt_broken = lc < bt_primary
                        bt_val = int(bt_secondary if is_bt_broken else bt_primary)
                        is_trend_broken = lc < ((h14 - (ur * 0.618)) * 0.98)
                        denom = h14 - bt_val
                        reach_val = ((h14 - lc) / denom * 100) if denom > 0 else 0
                        rank, bg, score, macd_t = get_triage_info(macd_h, macd_h_prev, rsi_v, lc, bt_val, mode="待伏")
                    else:
                        sl_val = int(lc * 0.95); tp_val = int(lc * 1.10)
                        hist_vals = df_chart['MACD_Hist'].tail(5).values
                        if hist_vals[-2] < 0 and hist_vals[-1] >= 0: gc_days = 1
                        elif hist_vals[-3] < 0 and hist_vals[-2] >= 0 and hist_vals[-1] >= 0: gc_days = 2
                        elif hist_vals[-4] < 0 and hist_vals[-3] >= 0 and hist_vals[-2] >= 0 and hist_vals[-1] >= 0: gc_days = 3
                        rank, bg, score, macd_t = get_triage_info(macd_h, macd_h_prev, rsi_v, mode="強襲", gc_days=gc_days)
                        reach_val = 100 - rsi_v

                    idxmax = df_14['AdjH'].idxmax()
                    d_high = len(df_14[df_14['Date'] > df_14.loc[idxmax, 'Date']]) if pd.notna(idxmax) else 0
                    
                    # 🚨 致命的バグの完全修正：地雷探知APIの直接リクエスト換装
                    target_event_data = {"dividend": [], "earnings": []}
                    try:
                        r_div = requests.get(f"{BASE_URL}/fins/dividend?code={api_code}", headers=headers, timeout=5)
                        if r_div.status_code == 200: target_event_data["dividend"] = r_div.json().get("dividend", [])
                        r_earn = requests.get(f"{BASE_URL}/fins/statements?code={api_code}", headers=headers, timeout=5)
                        if r_earn.status_code == 200: target_event_data["earnings"] = r_earn.json().get("statements", [])
                    except: pass
                    
                    alerts = check_event_mines(c, target_event_data)
                    
                    scope_results.append({
                        'code': c, 'name': c_name, 'market': c_market, 'sector': c_sector, 'scale': c_scale,
                        'lc': lc, 'h14': h14, 'l14': l14, 'ur': ur, 'bt_val': bt_val, 'sl_val': sl_val, 'tp_val': tp_val,
                        'is_bt_broken': is_bt_broken, 'is_trend_broken': is_trend_broken, 'daily_pct': daily_pct, 'alerts': alerts,
                        'is_dt': is_dt, 'is_hs': is_hs, 'is_db': is_db, 'is_defense': is_defense, 'gc_days': gc_days,
                        'rank': rank, 'bg': bg, 'score': score, 'reach_val': reach_val, 'atr_val': atr_val,
                        'd_high': d_high, 'avg_vol': avg_vol, 'df_chart': df_chart, 'rsi': rsi_v
                    })
                    
                scope_results = sorted(scope_results, key=lambda x: (x['score'], x['reach_val']), reverse=True)
                
                for r in scope_results:
                    st.divider()
                    c = str(r.get('code', '0000')); n = str(r.get('name', f"銘柄 {c[:4]}"))
                    m_lower = str(r.get('market', '不明')).lower()
                    if 'プライム' in m_lower or '一部' in m_lower: badge_html = '<span style="background-color: #1a237e; color: #ffffff; padding: 0.2rem 0.6rem; border-radius: 4px; font-size: 11px; font-weight: bold;">🏢 プライム/大型</span>'
                    elif 'グロース' in m_lower or 'マザーズ' in m_lower: badge_html = '<span style="background-color: #1b5e20; color: #ffffff; padding: 0.2rem 0.6rem; border-radius: 4px; font-size: 11px; font-weight: bold;">🚀 グロース/新興</span>'
                    else: badge_html = f'<span style="background-color: #455a64; color: #ffffff; padding: 0.2rem 0.6rem; border-radius: 4px; font-size: 11px; font-weight: bold;">{r.get("market")}</span>'

                    triage_badge = f'<span style="background-color: {r.get("bg", "#616161")}; color: #ffffff; padding: 0.2rem 0.6rem; border-radius: 4px; font-size: 13px; display: inline-block; font-weight: bold; margin-left: 0.5rem;">🎯 優先度: {r.get("rank")}</span>'
                    swing_pct = ((r.get('h14', 0) - r.get('l14', 0)) / r.get('l14', 1)) * 100 if r.get('l14', 0) > 0 else 0
                    volatility_badge = f'<span style="background-color: #ff9800; color: #ffffff; padding: 0.2rem 0.6rem; border-radius: 4px; font-size: 11px; font-weight: bold; margin-left: 0.5rem; border: 1px solid #e65100;">⚡ 高ボラ ({swing_pct:.1f}%)</span>' if swing_pct >= (40.0 if ('プライム' in m_lower or '一部' in m_lower) else 60.0) else ""

                    st.markdown(f"""
                        <div style="margin-bottom: 0.8rem;">
                            <h3 style="font-size: clamp(18px, 5vw, 28px); font-weight: bold; margin: 0 0 0.3rem 0;">({c[:4]}) {n}</h3>
                            <div style="display: flex; flex-wrap: wrap; gap: 6px; align-items: center;">
                                {badge_html}{triage_badge}{volatility_badge}
                                <span style="background-color: rgba(38, 166, 154, 0.15); border: 1px solid #26a69a; color: #26a69a; padding: 0.1rem 0.5rem; border-radius: 4px; font-size: 12px;">RSI: {r.get("rsi", 50):.1f}%</span>
                                <span style="background-color: rgba(255, 215, 0, 0.1); border: 1px solid #FFD700; color: #FFD700; padding: 0.1rem 0.5rem; border-radius: 4px; font-size: 12px;">到達度: {r.get('reach_val', 0):.1f}%</span>
                            </div>
                        </div>
                    """, unsafe_allow_html=True)
                            
                    for alert in r.get('alerts', []): st.warning(alert)
                    if r.get('sector') == '医薬品': st.error("🚨 【警告】この銘柄は医薬品（バイオ株）です。思惑だけで動く完全なギャンブルです。")
                    if bool(re.search("ETF|投信|ブル|ベア|REIT|ﾘｰﾄ", str(r.get('name', '')), re.IGNORECASE)): st.error("🚨 【警告】この銘柄はETF/REIT等です。個別株のテクニカルは通用しません。")
                    if r.get('is_dt') or r.get('is_hs'): st.error("🚨 【警告】相場転換の危険波形（三尊/Wトップ）を検知！ 撤退推奨。")
            
                    if "待伏" in scope_mode:
                        if r['is_trend_broken']: st.error("💀 【トレンド崩壊】黄金比(61.8%)を完全に下抜けています。迎撃非推奨（後学・分析用データ）")
                        elif r['is_bt_broken']: st.error("⚠️ 【第一防衛線突破】想定以上の売り圧力を検知。買値を第二防衛線（黄金比等）へ自動シフトしました。")
                        if r['is_db']: st.success("🔥 【激熱(攻め)】三川（ダブルボトム）底打ち反転波形を検知！")
                        if r['is_defense']: st.info("🛡️ 【鉄壁(守り)】下値支持線(サポート)に極接近。損切りリスクが極小の安全圏です。")
                    else:
                        if r.get('gc_days', 0) > 0: st.success(f"🔥 【GC発動】MACDゴールデンクロスから {r['gc_days']}日経過しています。")
                    
                    daily_sign = "+" if r.get('daily_pct', 0) >= 0 else ""
                        
                    if "待伏" in scope_mode:
                        reach_display = f"到達度: {r['reach_val']:.1f}%"
                        c_target = r.get('bt_val', 0)
                        html_buy_scope = f"""
                        <div style="background: rgba(255, 215, 0, 0.05); padding: 1.2rem; border-radius: 8px; border: 1px solid rgba(255, 215, 0, 0.3); text-align: center; height: 100%; display: flex; flex-direction: column; justify-content: center;">
                            <div style="font-size: 15px; color: rgba(250, 250, 250, 0.8); margin-bottom: 8px;">🎯 半値押し 買値目標</div>
                            <div style="font-size: 2.6rem; font-weight: bold; color: #FFD700; line-height: 1.1;">{int(c_target):,}<span style="font-size: 18px; margin-left:4px;">円</span></div>
                        </div>"""
                    else:
                        reach_display = f"RSI: {r.get('rsi', 50):.1f}%"
                        c_target = int(r.get('lc', 0) * 1.01)
                        exec_price = int(r.get('lc', 0) * 1.02)
                        defense_line = int(r.get('lc', 0) * 0.95)
                        html_buy_scope = f"""
                        <div style="background: rgba(255, 215, 0, 0.05); padding: 1rem; border-radius: 8px; border: 1px solid rgba(255, 215, 0, 0.3); display: flex; flex-direction: column; justify-content: center; height: 100%;">
                            <div style="font-size: 14px; color: rgba(250, 250, 250, 0.8); margin-bottom: 4px; text-align: center;">🎯 トリガー (終値+1%)</div>
                            <div style="font-size: 2.2rem; font-weight: bold; color: #FFD700; text-align: center; line-height: 1.1;">{int(c_target):,}<span style="font-size: 16px; margin-left:4px;">円</span></div>
                            <div style="margin: 12px 0 8px 0; border-top: 1px dashed rgba(255, 215, 0, 0.4);"></div>
                            <div style="display: flex; justify-content: space-between; align-items: center; padding: 0 8px; margin-bottom: 8px;">
                                <span style="font-size: 16px; color: #ccc;">⚔️ 執行(+2%)</span><span style="font-size: 20px; font-weight: bold; color: #FFD700;">{exec_price:,}円</span>
                            </div>
                            <div style="display: flex; justify-content: space-between; align-items: center; padding: 0 8px;">
                                <span style="font-size: 16px; color: #ccc;">🛡️ 防衛(-5%)</span><span style="font-size: 20px; font-weight: bold; color: #ef5350;">{defense_line:,}円</span>
                            </div>
                        </div>"""
        
                    tp_list = [5, 8, 10, 15, 20]; sl_list = [3, 5, 8]
                    html_matrix_scope = f"""
                    <div style="background: rgba(255, 255, 255, 0.05); padding: 1.2rem; border-radius: 8px; border-left: 5px solid #FFD700; height: 100%;">
                        <div style="font-size: 15px; color: #aaa; margin-bottom: 12px; border-bottom: 1px solid #444; padding-bottom: 4px;">📊 期待値マトリクス (基準: {int(c_target):,}円)</div>
                        <div style="display: flex; justify-content: space-between; gap: 30px;">
                            <div style="flex: 1;">
                                <div style="font-size: 14px; color: #26a69a; border-bottom: 2px solid #26a69a; margin-bottom: 10px; padding-bottom: 2px;">【 利確目標 】</div>
                                {" ".join([f'<div style="display: flex; align-items: center; margin-bottom: 8px;"><span style="font-size: 16px; color: #eee; width: 45px;">+{p}%</span><span style="flex-grow: 1; border-bottom: 1px dotted rgba(255, 255, 255, 0.3); margin: 0 10px; transform: translateY(4px);"></span><span style="font-size: 20px; font-weight:bold; color: #ffffff;">{int(c_target*(1+p/100)):,}</span></div>' for p in tp_list])}
                            </div>
                            <div style="flex: 1;">
                                <div style="font-size: 14px; color: #ef5350; border-bottom: 2px solid #ef5350; margin-bottom: 10px; padding-bottom: 2px;">【 損切目安 】</div>
                                {" ".join([f'<div style="display: flex; align-items: center; margin-bottom: 8px;"><span style="font-size: 16px; color: #eee; width: 45px;">-{l}%</span><span style="flex-grow: 1; border-bottom: 1px dotted rgba(255, 255, 255, 0.3); margin: 0 10px; transform: translateY(4px);"></span><span style="font-size: 20px; font-weight:bold; color: #ffffff;">{int(c_target*(1-l/100)):,}</span></div>' for l in sl_list])}
                            </div>
                        </div>
                    </div>"""
        
                    html_stats = f"""
                    <div style="display: flex; flex-direction: column; gap: 8px; margin-top: 1rem;">
                        <div style="background: rgba(38, 166, 154, 0.1); border-left: 3px solid #26a69a; padding: 6px 10px; border-radius: 4px;">
                            <span style="font-size: 12px; color: #aaa;">ステータス:</span> <strong style="font-size: 15px; color: #fff;">{reach_display}</strong>
                        </div>
                        <div style="background: rgba(156, 39, 176, 0.1); border-left: 3px solid #ab47bc; padding: 6px 10px; border-radius: 4px;">
                            <span style="font-size: 12px; color: #aaa;">ATR / 高値経過:</span> <strong style="font-size: 15px; color: #ce93d8;">{r.get('atr_val', 0):,}円 / {r.get('d_high', 0)}日</strong>
                        </div>
                        <div style="background: rgba(255, 215, 0, 0.1); border-left: 3px solid #FFD700; padding: 6px 10px; border-radius: 4px;">
                            <span style="font-size: 12px; color: #aaa;">出来高(5日):</span> <strong style="font-size: 15px; color: #fff;">{r.get('avg_vol', 0):,} 株</strong>
                        </div>
                    </div>"""
        
                    sc_left, sc_mid, sc_right = st.columns([2.5, 3.5, 5.0])
                    with sc_left:
                        c_m1, c_m2 = st.columns(2)
                        c_m1.metric("直近高値", f"{int(r.get('h14', 0)):,}円")
                        c_m2.metric("直近安値", f"{int(r.get('l14', 0)):,}円")
                        c_m3, c_m4 = st.columns(2)
                        c_m3.metric("上昇幅", f"{int(r.get('ur', 0)):,}円")
                        c_m4.metric("最新終値", f"{int(r.get('lc', 0)):,}円", f"{daily_sign}{r.get('daily_pct', 0)*100:.1f}%", delta_color="normal")
                        st.markdown(html_stats, unsafe_allow_html=True)
                    with sc_mid: st.markdown(html_buy_scope, unsafe_allow_html=True)
                    with sc_right: st.markdown(html_matrix_scope, unsafe_allow_html=True)
        
                    st.caption(f"🏢 {r.get('market', '不明')} ｜ 🏭 {r.get('sector', '不明')}")
                    from datetime import timedelta
                    cutoff_chart = r['df_chart']['Date'].max() - timedelta(days=60)
                    df_chart_filtered = r['df_chart'][r['df_chart']['Date'] >= cutoff_chart]
                    c_base = r.get('bt_val', 0) if "待伏" in scope_mode else r.get('lc', 0)
                    tp_val = st.session_state.get('bt_tp', 10) 
                    st.markdown(render_technical_radar(df_chart_filtered, c_base, tp_val), unsafe_allow_html=True)
                    draw_chart(df_chart_filtered, c_base, tp10=int(c_base*1.10), chart_key=f"t3_chart_{r.get('code', '0000')}")

with tab4:
    st.markdown('<h3 style="font-size: clamp(14px, 4.5vw, 24px); margin-bottom: 1rem;">⚙️ 戦術シミュレータ (2年間のバックテスト)</h3>', unsafe_allow_html=True)
    col_b1, col_b2 = st.columns([1, 2])
    T4_FILE = f"saved_t4_codes_{user_id}.txt"
    default_t4 = "7839\n6614"
    if os.path.exists(T4_FILE):
        with open(T4_FILE, "r", encoding="utf-8") as f: default_t4 = f.read()

    with col_b1: 
        st.markdown("🔍 **検証する戦術を選択してください**")
        test_mode = st.radio("戦術モード", ["🌐 【待伏】鉄の掟 (押し目狙撃)", "⚡ 【強襲】GCブレイクアウト (順張り)"], label_visibility="collapsed", key="bt_mode_sim_v2")
        st.markdown("検証コード (複数可)")
        bt_c_in = st.text_area("銘柄コード", value=default_t4, height=100, label_visibility="collapsed", key="bt_codes_sim_v2")
        run_bt = st.button("🔥 仮想実弾テスト実行", use_container_width=True, key="btn_run_bt_sim_v2")
        st.divider()
        optimize_bt = st.button("🚀 戦術の黄金比率を抽出 (最適化)", use_container_width=True)
        
    with col_b2:
        st.markdown("#### ⚙️ サイドバー連動パラメーター")
        st.info("※ 以下の基本設定は、画面左側の「サイドバー」の設定値が自動適用されます。")
        c_p1, c_p2, c_p3 = st.columns(3)
        c_p1.metric("🎯 利確目標", f"+{st.session_state.get('bt_tp', 10)}%")
        c_p2.metric("🛡️ 損切目安", f"-{st.session_state.get('bt_sl_i', 8)}%")
        c_p3.metric("⏳ 買い期限", f"{st.session_state.get('limit_d', 4)}日")
        st.divider()
        if "待伏" in test_mode:
            st.markdown("##### 🌐 【待伏】シミュレータ固有設定")
            c_t1_1, c_t1_2 = st.columns(2)
            c_t1_1.metric("📉 押し目待ち", f"{st.session_state.get('push_r', 50.0)}% 落とし")
            sim_pass_req = c_t1_2.number_input("掟クリア要求数", value=8, step=1, max_value=9, min_value=1, key="sim_pass_req_sim_v2")
        else:
            st.markdown("##### ⚡ 【強襲】シミュレータ固有設定")
            c_t2_1, c_t2_2 = st.columns(2)
            sim_rsi_lim = c_t2_1.number_input("RSI上限 (過熱感)", value=45, step=5, key="sim_rsi_lim_sim_v2")
            sim_time_risk = c_t2_2.number_input("時間リスク上限 (到達日数)", value=5, step=1, key="sim_time_risk_sim_v2")

    if (run_bt or optimize_bt) and bt_c_in:
        import time
        with open(T4_FILE, "w", encoding="utf-8") as f: f.write(bt_c_in)
        t_codes = list(dict.fromkeys([c.upper() for c in re.findall(r'(?<![a-zA-Z0-9])[a-zA-Z0-9]{4}(?![a-zA-Z0-9])', bt_c_in)]))
        
        if not t_codes: st.warning("有効なコードが見つかりません。")
        else:
            sim_tp = float(st.session_state.get('bt_tp', 10))
            sim_sl_i = float(st.session_state.get('bt_sl_i', 8))
            sim_limit_d = int(st.session_state.get('limit_d', 4))
            sim_sell_d = int(st.session_state.get('bt_sell_d', 10))
            sim_push_r = float(st.session_state.get('push_r', 50.0))

            is_ambush = "待伏" in test_mode
            if is_ambush:
                p1_range = range(25, 66, 5) if optimize_bt else [sim_push_r]
                p2_range = range(5, 10, 1) if optimize_bt else [int(sim_pass_req)]
                p1_name, p2_name = "Push率(%)", "要求Score"
            else:
                p1_range = range(30, 65, 5) if optimize_bt else [int(sim_rsi_lim)]
                p2_range = range(3, 16, 1) if optimize_bt else [int(sim_tp)]
                p1_name, p2_name = "RSI上限(%)", "利確目標(%)"
            
            with st.spinner("データをプリロード中（高速化処理）..."):
                preloaded_data = {}
                for c in t_codes:
                    raw = get_single_data(c + "0", 2)
                    if not raw or not raw.get('bars'): continue
                    temp_df = pd.DataFrame(raw['bars'])
                    if temp_df.empty: continue
                    try: 
                        clean_data = clean_df(temp_df)
                        target_cols = ['AdjO', 'AdjH', 'AdjL', 'AdjC']
                        if not all(col in clean_data.columns for col in target_cols): continue
                        clean_data = clean_data.dropna(subset=target_cols).reset_index(drop=True)
                        processed_df = calc_technicals(clean_data)
                        if processed_df is not None and isinstance(processed_df, pd.DataFrame) and len(processed_df) >= 35:
                            preloaded_data[c] = processed_df
                    except: continue

            if not preloaded_data:
                st.error("解析可能なデータが取得できませんでした。")
                st.stop()
                
            opt_results = []
            total_iterations = len(p1_range) * len(p2_range)
            current_iter = 0
            p_bar = st.progress(0, f"戦術最適化の総当たり検証中... ({p1_name} × {p2_name})")

            for t_p1 in p1_range:
                for t_p2 in p2_range:
                    current_iter += 1
                    all_t = []
                    for c, df in preloaded_data.items():
                        if df is None or len(df) < 35: continue
                        pos = None
                        for i in range(35, len(df)):
                            td = df.iloc[i]; prev = df.iloc[i-1]
                            if pos is None:
                                win_14 = df.iloc[i-15:i-1]; win_30 = df.iloc[i-31:i-1]
                                lc_prev = prev['AdjC']; atr_prev = prev.get('ATR', 0)
                                h14 = win_14['AdjH'].max(); l14 = win_14['AdjL'].min()
                                if pd.isna(h14) or pd.isna(l14) or l14 <= 0: continue
                                if atr_prev < 10 or (atr_prev / lc_prev) < 0.01: continue
                                
                                if is_ambush:
                                    r14 = h14 / l14
                                    idxmax = win_14['AdjH'].idxmax()
                                    d_high = len(win_14[win_14['Date'] > win_14.loc[idxmax, 'Date']]) if pd.notna(idxmax) else 0
                                    is_dt = check_double_top(win_30); is_hs = check_head_shoulders(win_30)
                                    bt_val = int(h14 - ((h14 - l14) * (t_p1 / 100.0)))
                                    
                                    score = 0
                                    if 1.3 <= r14 <= 2.0: score += 1
                                    if d_high <= sim_limit_d: score += 1 
                                    if not is_dt: score += 1
                                    if not is_hs: score += 1
                                    if bt_val * 0.85 <= lc_prev <= bt_val * 1.35: score += 1
                                    score += 4 
                                    
                                    if score >= t_p2:
                                        if td['AdjL'] <= bt_val:
                                            exec_p = min(td['AdjO'], bt_val)
                                            pos = {'b_i': i, 'b_d': td['Date'], 'b_p': exec_p}
                                else:
                                    rsi_prev = prev.get('RSI', 50); exp_days = int((lc_prev * (t_p2/100.0)) / atr_prev) if atr_prev > 0 else 99
                                    gc_triggered = False; trigger_price = 0
                                    for d_ago in range(1, int(sim_limit_d) + 1):
                                        idx_eval = i - d_ago
                                        if idx_eval >= 1:
                                            if df.iloc[idx_eval].get('MACD_Hist', 0) > 0 and df.iloc[idx_eval-1].get('MACD_Hist', 0) <= 0:
                                                gc_triggered = True
                                                trigger_price = df.iloc[idx_eval]['AdjC'] * 1.01; break
                                    if gc_triggered and rsi_prev <= t_p1 and exp_days < sim_time_risk:
                                        if td['AdjH'] >= trigger_price:
                                            exec_p = max(td['AdjO'], trigger_price)
                                            pos = {'b_i': i, 'b_d': td['Date'], 'b_p': exec_p}
                            else:
                                bp = pos['b_p']; held = i - pos['b_i']; sp = 0
                                current_tp = sim_tp if is_ambush else t_p2
                                sl_val = bp * (1 - (sim_sl_i / 100.0)); tp_val = bp * (1 + (current_tp / 100.0))
                                if td['AdjL'] <= sl_val: sp = min(td['AdjO'], sl_val)
                                elif td['AdjH'] >= tp_val: sp = max(td['AdjO'], tp_val)
                                elif held >= sim_sell_d: sp = td['AdjC']
                                if sp > 0:
                                    sp = round(sp, 1); p_pct = round(((sp / bp) - 1) * 100, 2)
                                    p_amt = int((sp - bp) * st.session_state.bt_lot)
                                    all_t.append({'銘柄': c, '購入日': pos['b_d'], '決済日': td['Date'], '保有日数': held, '買値(円)': int(bp), '売値(円)': int(sp), '損益(%)': p_pct, '損益額(円)': p_amt})
                                    pos = None
                    if all_t:
                        p_df = pd.DataFrame(all_t)
                        total_p = p_df['損益額(円)'].sum()
                        win_r = len(p_df[p_df['損益額(円)'] > 0]) / len(p_df)
                        opt_results.append({p1_name: t_p1, p2_name: t_p2, '総合利益(円)': total_p, '勝率': win_r, '取引回数': len(all_t)})
                    p_bar.progress(current_iter / total_iterations)
            p_bar.empty()

            if optimize_bt and opt_results:
                st.markdown(f"### 🏆 {test_mode.split()[1]}・最適化レポート")
                opt_df = pd.DataFrame(opt_results).sort_values('総合利益(円)', ascending=False)
                best = opt_df.iloc[0]
                c1, c2, c3 = st.columns(3)
                c1.metric(f"推奨 {p1_name}", f"{int(best[p1_name])} " + ("%" if is_ambush else ""))
                c2.metric(f"推奨 {p2_name}", f"{int(best[p2_name])} " + ("点" if is_ambush else "%"))
                c3.metric("期待勝率", f"{round(best['勝率']*100, 1)} %")
                st.write("#### 📊 パラメーター別収益ヒートマップ（上位10選）")
                st.dataframe(opt_df.head(10).style.format({'総合利益(円)': '{:,}', '勝率': '{:.2%}'}), use_container_width=True, hide_index=True)
                if is_ambush: st.info(f"💡 ボス、現在の地合いでは高値から {int(best[p1_name])}% 落ちた位置に指値を置き、掟スコア {int(best[p2_name])}点 以上でエントリーするのが最も効率的です。")
            elif run_bt:
                if not opt_results: st.warning("指定された期間・条件でシグナル点灯（約定）はありませんでした。")
                else:
                    tdf = pd.DataFrame(all_t).sort_values('決済日').reset_index(drop=True)
                    tdf['累積損益(円)'] = tdf['損益額(円)'].cumsum()
                    st.success("🎯 バックテスト完了")
                    import plotly.express as px
                    fig_eq = px.line(tdf, x='決済日', y='累積損益(円)', markers=True, title="💰 仮想資産推移 (Equity Curve)", color_discrete_sequence=["#FFD700"])
                    fig_eq.update_layout(paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0.1)', margin=dict(l=20, r=20, t=40, b=20))
                    st.plotly_chart(fig_eq, use_container_width=True)
                    
                    n_prof = tdf['損益額(円)'].sum()
                    prof_color = "#26a69a" if n_prof > 0 else "#ef5350"
                    st.markdown(f'<h3 style="color: {prof_color};">総合利益額: {n_prof:,} 円</h3>', unsafe_allow_html=True)
                    
                    m1, m2, m3, m4 = st.columns(4)
                    tot = len(tdf); wins = len(tdf[tdf['損益額(円)'] > 0])
                    m1.metric("トレード回数", f"{tot} 回")
                    m2.metric("勝率", f"{round((wins/tot)*100,1)} %")
                    m3.metric("平均損益額", f"{int(n_prof/tot):,} 円" if tot > 0 else "0 円")
                    sloss = abs(tdf[tdf['損益額(円)'] <= 0]['損益額(円)'].sum())
                    m4.metric("PF", round(tdf[tdf['損益額(円)'] > 0]['損益額(円)'].sum() / sloss, 2) if sloss > 0 else 'inf')
                    
                    def color_pnl_tab4(val):
                        if isinstance(val, (int, float)):
                            color = '#26a69a' if val > 0 else '#ef5350' if val < 0 else 'white'
                            return f'color: {color}; font-weight: bold;'
                        return ''
                    
                    styled_tdf = tdf.drop(columns=['累積損益(円)']).style.map(color_pnl_tab4, subset=['損益額(円)', '損益(%)']).format({'買値(円)': '{:,}', '売値(円)': '{:,}', '損益額(円)': '{:,}', '損益(%)': '{:.2f}'})
                    st.dataframe(styled_tdf, use_container_width=True, hide_index=True)

with tab5:
    st.markdown('<h3 style="font-size: clamp(14px, 4.5vw, 24px); margin-bottom: 1rem;">📡 交戦モニター (全軍生存圏レーダー)</h3>', unsafe_allow_html=True)
    st.caption("※ 展開中の全部隊（ポジション）の現在地と防衛線を一覧表示し、戦局を俯瞰します。")

    if 'frontline_df' not in st.session_state:
        st.session_state.frontline_df = pd.DataFrame([
            {"銘柄": "4259", "買値": 650.0, "第1利確": 688.0, "第2利確": 714.0, "損切": 627.0, "現在値": 670.0},
            {"銘柄": "4691", "買値": 1588.0, "第1利確": 1635.0, "第2利確": 1635.0, "損切": 1508.0, "現在値": 1600.0},
            {"銘柄": "3137", "買値": 267.0, "第1利確": 260.0, "第2利確": 267.0, "損切": 248.0, "現在値": 254.0}
        ])

    st.markdown("#### ⚙️ 部隊パラメーター入力 (コントロールパネル)")
    st.caption("※ 直接数値を書き換えてください。下部の「行を追加」で新しい銘柄を無限に追加可能です。")

    edited_df = st.data_editor(
        st.session_state.frontline_df,
        num_rows="dynamic",
        column_config={
            "銘柄": st.column_config.TextColumn("銘柄", required=True),
            "買値": st.column_config.NumberColumn("買値", format="%.1f", required=True),
            "第1利確": st.column_config.NumberColumn("第1利確", format="%.1f", required=True),
            "第2利確": st.column_config.NumberColumn("第2利確", format="%.1f", required=True),
            "損切": st.column_config.NumberColumn("損切", format="%.1f", required=True),
            "現在値": st.column_config.NumberColumn("🔴 現在値", format="%.1f", required=True),
        },
        use_container_width=True,
        key="frontline_editor"
    )

    st.markdown("---")
    st.markdown("#### 🔭 全軍レーダー展開状況")

    active_squads = 0

    for index, row in edited_df.iterrows():
        ticker = str(row.get('銘柄', ''))
        if ticker.strip() == "" or pd.isna(row['買値']) or pd.isna(row['現在値']): continue
            
        buy = float(row['買値']); tp1 = float(row['第1利確']); tp2 = float(row['第2利確']); sl = float(row['損切']); cur = float(row['現在値'])
        active_squads += 1

        if cur <= sl: st_text, st_color = "💀 被弾（防衛線突破・即時撤退）", "#ef5350"
        elif cur < buy: st_text, st_color = "⚠️ 警戒（損切ラインへ後退中）", "#ff9800"
        elif cur < tp1: st_text, st_color = "🟢 巡航中（第1目標へ接近中）", "#26a69a"
        elif cur < tp2: st_text, st_color = "🛡️ 第1目標到達（無敵化推奨）", "#42a5f5"
        else: st_text, st_color = "🏆 最終目標到達（任務完了）", "#ab47bc"

        st.markdown(f"**部隊 [{ticker}]** ｜ 戦況: <span style='color:{st_color}; font-weight:bold;'>{st_text}</span>", unsafe_allow_html=True)

        fig = go.Figure()
        min_x = min(sl, cur) * 0.98; max_x = max(tp2, cur) * 1.02
        fig.add_shape(type="line", x0=min_x, y0=0, x1=max_x, y1=0, line=dict(color="#555", width=2))
        fig.add_trace(go.Scatter(x=[sl, buy, tp1, tp2], y=[0, 0, 0, 0], mode="markers+text", text=["損切", "買値", "第1利確", "第2利確"], textposition="top center", textfont=dict(size=11, color="white"), marker=dict(size=10, color=["#ef5350", "#ffca28", "#26a69a", "#42a5f5"]), hoverinfo="x+text", name="防衛線"))
        fig.add_trace(go.Scatter(x=[cur], y=[0], mode="markers+text", text=[f"現在値<br>{cur}"], textposition="bottom center", textfont=dict(size=12, color=st_color), marker=dict(size=20, symbol="cross-thin", line=dict(width=3, color=st_color)), hoverinfo="x", name="ターゲット"))
        fig.update_layout(height=180, showlegend=False, yaxis=dict(showticklabels=False, showgrid=False, zeroline=False, range=[-1, 1]), xaxis=dict(showgrid=False, zeroline=False, range=[min_x, max_x], tickfont=dict(color="#888")), margin=dict(l=10, r=10, t=30, b=50), paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)', dragmode=False)
        st.plotly_chart(fig, use_container_width=True)

    if active_squads == 0: st.info("現在、展開中の部隊はありません。上の表にデータを入力してください。")

with tab6:
    st.markdown('<h3 style="font-size: clamp(14px, 4.5vw, 24px); margin-bottom: 1rem;">📁 事後任務報告 (AAR) & 戦績ダッシュボード</h3>', unsafe_allow_html=True)
    st.caption("※実際の交戦記録（トレード履歴）を記録し、自身の戦績と「規律遵守度（メンタル）」を可視化・分析します。")
    
    AAR_FILE = f"saved_aar_log_{user_id}.csv"
    
    def get_scale_for_code(code):
        api_code = str(code) if len(str(code)) == 5 else str(code) + "0"
        if not master_df.empty:
            m_row = master_df[master_df['Code'] == api_code]
            if not m_row.empty:
                scale_val = str(m_row.iloc[0].get('Scale', ''))
                return "🏢 大型/中型" if any(x in scale_val for x in ["Core30", "Large70", "Mid400"]) else "🚀 小型/新興"
        return "不明"
    
    if os.path.exists(AAR_FILE):
        aar_df = pd.read_csv(AAR_FILE)
        if "規模" not in aar_df.columns:
            aar_df.insert(2, "規模", aar_df["銘柄"].apply(get_scale_for_code))
            aar_df.to_csv(AAR_FILE, index=False)
        aar_df = aar_df.sort_values(['決済日', '銘柄'], ascending=[True, True]).reset_index(drop=True)
    else:
        aar_df = pd.DataFrame(columns=["決済日", "銘柄", "規模", "戦術", "買値", "売値", "株数", "損益額(円)", "損益(%)", "規律", "敗因/勝因メモ"])

    col_a1, col_a2 = st.columns([1, 2.2])
    
    with col_a1:
        st.markdown("#### 📝 戦果報告フォーム (手動入力)")
        with st.form(key="aar_form"):
            c_f1, c_f2 = st.columns(2)
            import datetime as dt_module
            aar_date = c_f1.date_input("決済日", dt_module.date.today())
            aar_code = c_f2.text_input("銘柄コード (4桁)", max_chars=4)
            aar_tactics = st.selectbox("使用した戦術", ["🌐 待伏 (押し目)", "⚡ 強襲 (順張り)", "⚠️ その他 (裁量・妥協)"])
            c_f3, c_f4, c_f5 = st.columns(3)
            aar_buy = c_f3.number_input("買値 (円)", min_value=0.0, step=1.0, format="%.1f")
            aar_sell = c_f4.number_input("売値 (円)", min_value=0.0, step=1.0, format="%.1f")
            aar_lot = c_f5.number_input("株数", min_value=100, step=100)
            
            st.markdown("**⚖️ 自己評価（メンタル・チェック）**")
            aar_rule = st.radio("ボスの『鉄の掟』を完全に遵守して撃ちましたか？", ["✅ 遵守した (冷徹な狙撃)", "❌ 破った (感情・焦り・妥協)"], horizontal=False)
            aar_memo = st.text_input("特記事項 (なぜそのルールを破ったか、または勝因など)")
            submit_aar = st.form_submit_button("💾 記録をデータバンクへ保存", use_container_width=True)
            
        if submit_aar:
            if aar_code and len(aar_code) >= 4 and aar_buy > 0 and aar_sell > 0:
                profit = int((aar_sell - aar_buy) * aar_lot)
                profit_pct = round(((aar_sell / aar_buy) - 1) * 100, 2)
                new_data = pd.DataFrame([{
                    "決済日": aar_date.strftime("%Y-%m-%d"), "銘柄": aar_code, "規模": get_scale_for_code(aar_code),
                    "戦術": aar_tactics.split(" ")[1] if " " in aar_tactics else aar_tactics,
                    "買値": aar_buy, "売値": aar_sell, "株数": aar_lot, "損益額(円)": profit, "損益(%)": profit_pct,
                    "規律": "遵守" if "遵守" in aar_rule else "違反", "敗因/勝因メモ": aar_memo
                }])
                aar_df = pd.concat([new_data, aar_df], ignore_index=True).sort_values(['決済日', '銘柄'], ascending=[True, True]).reset_index(drop=True)
                aar_df.to_csv(AAR_FILE, index=False)
                st.success(f"銘柄 {aar_code} の戦果を司令部データベースに記録しました。")
                st.rerun()
            else: st.error("銘柄コード、買値、売値を正しく入力してください。")
        
        with st.expander("📥 証券会社の取引履歴(CSV)から自動一括登録", expanded=True):
            st.caption("アップロードされたCSVから「現物買」と「現物売」を自動でペアリングし、損益を算出してデータベースへ一括登録します。（※重複データは自動排除されます）")
            uploaded_csv = st.file_uploader("約定履歴CSVファイルをアップロード", type=["csv"], key="aar_csv_uploader")
            if uploaded_csv is not None:
                if st.button("⚙️ CSVから戦果を自動解析して追加", use_container_width=True, key="btn_parse_csv"):
                    try:
                        import io
                        try: content = uploaded_csv.getvalue().decode('utf-8')
                        except UnicodeDecodeError: content = uploaded_csv.getvalue().decode('shift_jis', errors='replace')
                        lines = content.splitlines()
                        header_idx = -1
                        for i, line in enumerate(lines):
                            if "約定日" in line and "銘柄" in line:
                                header_idx = i; break
                                
                        if header_idx != -1:
                            csv_data = "\n".join(lines[header_idx:])
                            df_csv = pd.read_csv(io.StringIO(csv_data))
                            df_csv = df_csv[df_csv['取引'].astype(str).str.contains('現物')].copy()
                            records = []
                            for code, group in df_csv.groupby('銘柄コード'):
                                buys, sells = [], []
                                for _, row in group.iterrows():
                                    item = {'date': str(row['約定日']).replace('/', '-'), 'qty': int(row['約定数量']), 'price': float(row['約定単価']), 'code': str(code)}
                                    if "買" in str(row['取引']): buys.append(item)
                                    elif "売" in str(row['取引']): sells.append(item)
                                buys.sort(key=lambda x: x['date']); sells.sort(key=lambda x: x['date'])
                                for s in sells:
                                    sell_qty = s['qty']; matched_qty, matched_buy_amount = 0, 0
                                    while sell_qty > 0 and len(buys) > 0:
                                        b = buys[0]
                                        if b['qty'] <= sell_qty:
                                            matched_qty += b['qty']; matched_buy_amount += b['price'] * b['qty']; sell_qty -= b['qty']; buys.pop(0)
                                        else:
                                            matched_qty += sell_qty; matched_buy_amount += b['price'] * sell_qty; b['qty'] -= sell_qty; sell_qty = 0
                                    if matched_qty > 0:
                                        avg_buy_price = matched_buy_amount / matched_qty
                                        profit = (s['price'] - avg_buy_price) * matched_qty
                                        profit_pct = ((s['price'] / avg_buy_price) - 1) * 100
                                        records.append({
                                            "決済日": s['date'], "銘柄": s['code'], "規模": get_scale_for_code(s['code']), "戦術": "自動解析",
                                            "買値": round(avg_buy_price, 1), "売値": round(s['price'], 1), "株数": int(matched_qty),
                                            "損益額(円)": int(profit), "損益(%)": round(profit_pct, 2), "規律": "不明(要修正)", "敗因/勝因メモ": "CSV自動取り込み"
                                        })
                            if records:
                                new_df = pd.DataFrame(records)
                                aar_df = pd.concat([aar_df, new_df], ignore_index=True)
                                aar_df['決済日'] = aar_df['決済日'].astype(str)
                                aar_df['銘柄'] = aar_df['銘柄'].astype(str)
                                aar_df['買値'] = aar_df['買値'].astype(float).round(1)
                                aar_df['売値'] = aar_df['売値'].astype(float).round(1)
                                aar_df['株数'] = aar_df['株数'].astype(int)
                                aar_df = aar_df.drop_duplicates(subset=["決済日", "銘柄", "買値", "売値", "株数"], keep='first').reset_index(drop=True)
                                aar_df = aar_df.sort_values(['決済日', '銘柄'], ascending=[True, True]).reset_index(drop=True)
                                aar_df.to_csv(AAR_FILE, index=False)
                                st.success(f"🎯 新規の戦果のみを抽出し、既存の編集内容は維持したまま統合しました！")
                                st.rerun()
                            else: st.warning("解析可能な決済済みペア（買いと売りのセット）が見つかりませんでした。")
                        else: st.error("CSVフォーマットが認識できませんでした。「約定日」「銘柄」を含むヘッダ行が必要です。")
                    except Exception as e: st.error(f"解析エラー: {e}")

        if not aar_df.empty:
            if st.button("🗑️ 全記録を消去 (データベース初期化)", key="reset_aar", use_container_width=True):
                os.remove(AAR_FILE)
                st.rerun()

    with col_a2:
        st.markdown("#### 📊 司令部 総合戦績ダッシュボード")
        if aar_df.empty: st.warning("現在、交戦記録（データ）がありません。左のフォームから入力するか、CSVをアップロードしてください。")
        else:
            tot_trades = len(aar_df)
            wins = len(aar_df[aar_df['損益額(円)'] > 0])
            losses = len(aar_df[aar_df['損益額(円)'] <= 0])
            win_rate = round((wins / tot_trades) * 100, 1) if tot_trades > 0 else 0
            
            tot_profit = aar_df['損益額(円)'].sum()
            gross_profit = aar_df[aar_df['損益額(円)'] > 0]['損益額(円)'].sum()
            gross_loss = abs(aar_df[aar_df['損益額(円)'] < 0]['損益額(円)'].sum())
            pf = round(gross_profit / gross_loss, 2) if gross_loss > 0 else float('inf')
            
            rule_adherence = round((len(aar_df[aar_df['規律'] == '遵守']) / tot_trades) * 100, 1) if tot_trades > 0 else 0
            
            m1, m2, m3, m4 = st.columns(4)
            m1.metric("総交戦回数", f"{tot_trades} 回")
            m2.metric("実戦 勝率", f"{win_rate}%", f"{wins}勝 {losses}敗", delta_color="off")
            m3.metric("総合 実損益", f"{int(tot_profit):,} 円", f"実戦PF: {pf}")
            m4.metric("⚖️ 規律遵守率", f"{rule_adherence}%", "感情排除のバロメーター", delta_color="off")
            
            st.markdown("##### 💰 現実の資産推移 (Real Equity Curve)")
            aar_df_sorted = aar_df.sort_values('決済日', ascending=True).reset_index(drop=True)
            aar_df_sorted['累積損益(円)'] = aar_df_sorted['損益額(円)'].cumsum()
            
            import plotly.express as px
            fig_real_eq = px.line(aar_df_sorted, x='決済日', y='累積損益(円)', markers=True, color_discrete_sequence=["#26a69a"])
            fig_real_eq.update_layout(paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0.1)', margin=dict(l=20, r=20, t=10, b=20), xaxis_title="", yaxis_title="実損益額 (円)", height=250, hovermode="x unified")
            st.plotly_chart(fig_real_eq, use_container_width=True)
            
            def color_pnl(val):
                if isinstance(val, (int, float)):
                    color = '#26a69a' if val > 0 else '#ef5350' if val < 0 else 'white'
                    return f'color: {color}; font-weight: bold;'
                return ''
                
            def color_rule(val):
                if val == '違反': return 'color: #ef5350; font-weight: bold; background-color: rgba(239, 83, 80, 0.1);'
                elif '不明' in str(val): return 'color: #9e9e9e;'
                return 'color: #26a69a;'

            st.markdown("##### 📜 詳細交戦記録（キル・ログ）")
            st.caption("※表のセルを直接ダブルクリックすると、「戦術」「規律」「メモ」を直接編集（上書き保存）できます。")

            styled_df = aar_df.style.map(color_pnl, subset=['損益額(円)', '損益(%)']).map(color_rule, subset=['規律'])

            edited_df = st.data_editor(
                styled_df,
                column_config={
                    "規模": st.column_config.TextColumn("規模", disabled=True),
                    "戦術": st.column_config.SelectboxColumn("戦術", options=["待伏", "強襲", "自動解析", "その他"], required=True),
                    "規律": st.column_config.SelectboxColumn("規律", options=["遵守", "違反", "不明(要修正)"], required=True),
                    "敗因/勝因メモ": st.column_config.TextColumn("敗因/勝因メモ", max_chars=200),
                    "買値": st.column_config.NumberColumn("買値", format="%.1f"),
                    "売値": st.column_config.NumberColumn("売値", format="%.1f"),
                    "株数": st.column_config.NumberColumn("株数", format="%d"),
                    "損益額(円)": st.column_config.NumberColumn("損益額(円)", format="%d"),
                    "損益(%)": st.column_config.NumberColumn("損益(%)", format="%.2f"),
                },
                disabled=["決済日", "銘柄", "規模", "買値", "売値", "株数", "損益額(円)", "損益(%)"],
                hide_index=True, use_container_width=True, key="aar_data_editor"
            )
            
            if not edited_df.equals(aar_df):
                edited_df.to_csv(AAR_FILE, index=False)
                st.rerun()
