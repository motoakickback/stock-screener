import streamlit as st
import requests
import pandas as pd
import os
import re
import json
from datetime import datetime, timedelta
from io import BytesIO
import plotly.graph_objects as go
import numpy as np
import concurrent.futures
# 🚨 必須：ログインパッチと帰還ボタンで使用するコンポーネントをここで宣言
import streamlit.components.v1 as components

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
            # 🚨 JavaScript 狙撃パッチ：指紋認証完了後の自動クリックを強化
            components.html(
                """
                <script>
                const doc = window.parent.document;
                
                function tryAutoLogin() {
                    const input = doc.querySelector('input[type="password"]');
                    const buttons = doc.querySelectorAll('button');
                    let submitBtn = null;
                    
                    for (const btn of buttons) {
                        if (btn.innerText && btn.innerText.includes("認証")) {
                            submitBtn = btn;
                            break;
                        }
                    }

                    if (input && submitBtn) {
                        if (input.value.length > 0) {
                            submitBtn.click();
                            return true;
                        }
                    }
                    return false;
                }

                const monitor = setInterval(() => {
                    if (tryAutoLogin()) {
                        clearInterval(monitor);
                    }
                }, 200);

                doc.addEventListener('input', (e) => {
                    if (e.target.type === 'password') tryAutoLogin();
                });
                </script>
                """,
                height=0,
            )
            
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

API_KEY = st.secrets.get("JQUANTS_API_KEY", "").strip()
headers = {"x-api-key": API_KEY}
BASE_URL = "https://api.jquants.com/v2"

# --- ⏱️ 19:00 完全自動パージ機構 ---
import pytz
jst = pytz.timezone('Asia/Tokyo')
now = datetime.now(jst)

if 'last_auto_purge_date' not in st.session_state:
    st.session_state.last_auto_purge_date = None

if now.hour >= 19:
    today_str = now.strftime('%Y-%m-%d')
    if st.session_state.last_auto_purge_date != today_str:
        st.cache_data.clear()
        st.session_state.tab1_scan_results = None
        st.session_state.tab2_scan_results = None
        st.session_state.tab5_ifd_results = None
        st.session_state.last_auto_purge_date = today_str

# --- ⚙️ システム全体設定の永続化 ---
SETTINGS_FILE = f"saved_settings_{user_id}.json"

def load_settings():
    defaults = {
        "preset_market": "🚀 中小型株 (スタンダード・グロース)", 
        "preset_push_r": "50.0%",
        "sidebar_tactics": "⚖️ バランス (掟達成率 ＞ 到達度)",
        "push_r": 50.0, "limit_d": 4, "bt_lot": 100, "bt_tp": 10, "bt_sl_i": 8, "bt_sl_c": 8, "bt_sell_d": 10,
        "f1_min": 200, "f1_max": 3000, "f2_m30": 2.0, "f3_drop": -50.0,
        "f5_ipo": True, "f6_risk": True, "f7_ex_etf": True, "f8_ex_bio": True,
        "f9_min14": 1.3, "f9_max14": 2.0, "f10_ex_knife": True,
        "f11_ex_wave3": True, "f12_ex_overvalued": True,
        "tab2_rsi_limit": 75, "tab2_vol_limit": 15000, 
        "t3_scope_mode": "🌐 【待伏】 押し目・逆張り",
        "gigi_input": "2134, 3350, 6172, 6740, 7647, 8783, 8836, 8925, 9318",
        "tab1_scan_results": None, "tab2_scan_results": None
    }
    if os.path.exists(SETTINGS_FILE):
        try:
            with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
                saved = json.load(f)
                defaults.update(saved)
        except: pass
    for k, v in defaults.items():
        if k not in st.session_state: st.session_state[k] = v

def save_settings():
    keys = ["preset_market", "preset_push_r", "sidebar_tactics", "push_r", "limit_d", "bt_lot", "bt_tp", "bt_sl_i", "bt_sl_c", "bt_sell_d", 
            "f1_min", "f1_max", "f2_m30", "f3_drop", "f5_ipo", "f6_risk", "f7_ex_etf", "f8_ex_bio", 
            "f9_min14", "f9_max14", "f10_ex_knife", "f11_ex_wave3", "f12_ex_overvalued",
            "tab2_rsi_limit", "tab2_vol_limit", "t3_scope_mode", "gigi_input"]
    current = {k: st.session_state[k] for k in keys if k in st.session_state}
    with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
        json.dump(current, f, ensure_ascii=False, indent=4)

def apply_presets():
    p_rate = st.session_state.get("preset_push_r", "50.0%")
    if p_rate == "25.0%": st.session_state.push_r = 25.0
    elif p_rate == "50.0%": st.session_state.push_r = 50.0
    elif p_rate == "61.8%": st.session_state.push_r = 61.8
    save_settings()

load_settings()

def apply_market_preset():
    preset = st.session_state.get("preset_target", "🚀 中小型株 (50%押し・標準)")
    tactics = st.session_state.get("sidebar_tactics", "⚖️ バランス (掟達成率 ＞ 到達度)")
    if "大型株" in preset:
        st.session_state.push_r = 25.0 if "バランス" in tactics else 45.0
    elif "61.8%" in preset:
        st.session_state.push_r = 61.8
    else:
        st.session_state.push_r = 50.0
    st.session_state.sim_push_r = st.session_state.push_r
    save_settings()

# --- 🌪️ マクロ気象レーダー（日経平均） ---
@st.cache_data(ttl=60, show_spinner=False)
def get_macro_weather():
    try:
        import yfinance as yf
        jst = pytz.timezone('Asia/Tokyo')
        now = datetime.now(jst)
        start_date = (now - timedelta(days=110)).strftime('%Y-%m-%d')
        end_date = (now + timedelta(days=2)).strftime('%Y-%m-%d')
        df_raw = yf.download("^N225", start=start_date, end=end_date, progress=False)
        if not df_raw.empty:
            if isinstance(df_raw.columns, pd.MultiIndex):
                df_raw.columns = df_raw.columns.get_level_values(0)
            df_ni = df_raw.reset_index()
            df_ni['Date'] = pd.to_datetime(df_ni['Date']).dt.tz_localize(None)
            df_ni = df_ni.dropna(subset=['Close'])
            df_ni = df_ni.tail(65)
            latest_row = df_ni.iloc[-1]
            prev_row = df_ni.iloc[-2]
            return {
                "nikkei": {
                    "price": latest_row['Close'], 
                    "diff": latest_row['Close'] - prev_row['Close'], 
                    "pct": ((latest_row['Close'] / prev_row['Close']) - 1) * 100, 
                    "df": df_ni,
                    "date": latest_row['Date'].strftime('%m/%d')
                }
            }
    except: return None

def render_macro_board():
    data = get_macro_weather()
    if data and "nikkei" in data:
        ni = data["nikkei"]; df = ni["df"]; color = "#ef5350" if ni['diff'] >= 0 else "#26a69a"; sign = "+" if ni['diff'] >= 0 else ""
        c1, c2 = st.columns([1, 2.5])
        with c1:
            st.markdown(f"""
            <div style="background: rgba(20, 20, 20, 0.6); padding: 1.2rem; border-radius: 8px; border-left: 4px solid {color}; height: 100%; display: flex; flex-direction: column; justify-content: center;">
                <div style="font-size: 14px; color: #aaa; margin-bottom: 8px;">🌪️ 戦場の天候 (日経平均: {ni['date']})</div>
                <div style="font-size: 26px; font-weight: bold; color: {color}; margin-bottom: 4px;">{ni['price']:,.0f} 円</div>
                <div style="font-size: 16px; color: {color};">({sign}{ni['diff']:,.0f} / {sign}{ni['pct']:.2f}%)</div>
            </div>
            """, unsafe_allow_html=True)
        with c2:
            df['MA25'] = df['Close'].rolling(window=25).mean()
            fig = go.Figure()
            fig.add_trace(go.Scatter(x=df['Date'], y=df['Close'], name='日経平均', mode='lines', line=dict(color='#FFD700', width=2), hovertemplate='日経平均: ¥%{y:,.0f}<extra></extra>'))
            fig.add_trace(go.Scatter(x=df['Date'], y=df['MA25'], name='25日線', mode='lines', line=dict(color='rgba(255, 255, 255, 0.4)', width=1, dash='dot'), hovertemplate='25日線: ¥%{y:,.0f}<extra></extra>'))
            x_min = df['Date'].min()
            x_max = df['Date'].max() + pd.Timedelta(hours=12)
            fig.update_layout(height=160, margin=dict(l=10, r=40, t=10, b=10), xaxis_rangeslider_visible=False, paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)', showlegend=False, hovermode="x unified", yaxis=dict(side="right", tickformat=",.0f", gridcolor='rgba(255,255,255,0.05)'), xaxis=dict(type='date', tickformat='%m/%d', gridcolor='rgba(255,255,255,0.05)', range=[x_min, x_max]))
            st.plotly_chart(fig, use_container_width=True, config={'displayModeBar': False})
        st.markdown("<div style='margin-bottom: 1.5rem;'></div>", unsafe_allow_html=True)
    else: st.warning("📡 外部気象レーダー応答なし")

render_macro_board()

# --- 3. 共通関数 ---
def clean_df(df):
    r_cols = {'AdjustmentOpen': 'AdjO', 'AdjustmentHigh': 'AdjH', 'AdjustmentLow': 'AdjL', 'AdjustmentClose': 'AdjC', 'Open': 'AdjO', 'High': 'AdjH', 'Low': 'AdjL', 'Close': 'AdjC', 'AdjustmentVolume': 'Volume', 'Volume': 'Volume'}
    df = df.rename(columns=r_cols)
    for c in ['AdjO', 'AdjH', 'AdjL', 'AdjC', 'Volume']:
        if c in df.columns: df[c] = pd.to_numeric(df[c], errors='coerce')
    if 'Date' in df.columns:
        df['Date'] = pd.to_datetime(df['Date'])
        df = df.sort_values('Date').dropna(subset=['AdjO', 'AdjH', 'AdjL', 'AdjC']).reset_index(drop=True)
    return df

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
        df['RSI'] = 50; df['MACD_Hist'] = 0; df['ATR'] = 0; df['MA5'] = df['AdjC']; df['MA25'] = df['AdjC']; df['MA75'] = df['AdjC']; return df
    df = df.replace([np.inf, -np.inf], np.nan)
    df.ffill(inplace=True); df.fillna(0, inplace=True)
    delta = df['AdjC'].diff()
    gain = delta.where(delta > 0, 0); loss = -delta.where(delta < 0, 0)
    rs = gain.ewm(alpha=1/14, adjust=False).mean() / (loss.ewm(alpha=1/14, adjust=False).mean() + 1e-10)
    df['RSI'] = 100 - (100 / (1 + rs))
    macd = df['AdjC'].ewm(span=12, adjust=False).mean() - df['AdjC'].ewm(span=26, adjust=False).mean()
    df['MACD_Hist'] = macd - macd.ewm(span=9, adjust=False).mean()
    df['MA5'] = df['AdjC'].rolling(window=5).mean()
    df['MA25'] = df['AdjC'].rolling(window=25).mean()
    df['MA75'] = df['AdjC'].rolling(window=75).mean()
    tr = pd.concat([df['AdjH'] - df['AdjL'], (df['AdjH'] - df['AdjC'].shift(1)).abs(), (df['AdjL'] - df['AdjC'].shift(1)).abs()], axis=1).max(axis=1)
    df['ATR'] = tr.rolling(window=14).mean()
    return df

def get_triage_info(macd_hist, macd_hist_prev, rsi, lc=0, bt=0, mode="待伏"):
    if macd_hist > 0 and macd_hist_prev <= 0: macd_t = "GC直後"
    elif macd_hist > macd_hist_prev: macd_t = "上昇拡大"
    elif macd_hist < 0 and macd_hist < macd_hist_prev: macd_t = "下落継続"
    else: macd_t = "減衰"

    if bt == 0 or lc == 0: return "C👁️", "#616161", 1, macd_t
    dist_pct = ((lc / bt) - 1) * 100 
    if dist_pct < -2.0: return "圏外💀", "#d32f2f", 0, macd_t
    elif dist_pct <= 2.0:
        if rsi <= 45: return "S🔥", "#2e7d32", 5, macd_t
        else: return "A⚡", "#ed6c02", 4.5, macd_t 
    elif dist_pct <= 5.0:
        if rsi <= 50: return "A🪤", "#0288d1", 4.0, macd_t 
        else: return "B📈", "#0288d1", 3, macd_t
    else: return "C👁️", "#616161", 1, macd_t

def get_assault_triage_info(gc_days, lc, rsi_v, df_chart, is_strict=False):
    if gc_days <= 0 or df_chart is None or df_chart.empty: return "圏外 💀", "#424242", 0, ""
    latest = df_chart.iloc[-1]; ma25 = latest.get('MA25', 0)
    score = 50 
    if ma25 > 0:
        if lc >= ma25 * 0.95: score += 10
        if lc >= ma25: score += 10
    if 50 <= rsi_v <= 70: score += 10
    if score >= 80: rank = "S"; bg = "#d32f2f"
    elif score >= 60: rank = "A"; bg = "#f57c00"
    elif score >= 40: rank = "B"; bg = "#fbc02d"
    else: rank = "C 💀"; bg = "#424242"
    return rank, bg, score, "GC発動中"

# --- 4. サイドバー UI ---
st.sidebar.title("🛠️ 戦術コンソール")
st.sidebar.header("📍 ターゲット選別")
st.sidebar.selectbox("市場ターゲット", ["🏢 大型株 (プライム・一部)", "🚀 中小型株 (スタンダード・グロース)"], key="preset_market", on_change=save_settings)
st.sidebar.selectbox("押し目プリセット", ["25.0%", "50.0%", "61.8%"], key="preset_push_r", on_change=apply_presets)
st.sidebar.selectbox("戦術アルゴリズム", ["⚖️ バランス (掟達成率 ＞ 到達度)", "🎯 狙撃優先 (到達度 ＞ 掟達成率)"], key="sidebar_tactics", on_change=save_settings)

st.sidebar.divider()
st.sidebar.header("🔍 ピックアップルール")
c1, c2 = st.sidebar.columns(2)
c1.number_input("価格下限(円)", step=100, key="f1_min", on_change=save_settings)
c2.number_input("価格上限(円)", step=100, key="f1_max", on_change=save_settings)
st.sidebar.number_input("1ヶ月暴騰上限(倍)", step=0.1, key="f2_m30", on_change=save_settings)
st.sidebar.number_input("1年最高値からの下落除外(%)", value=float(st.session_state.get("f3_drop", -50.0)), step=5.0, max_value=0.0, key="f3_drop", on_change=save_settings)

c3, c4 = st.sidebar.columns(2)
c3.number_input("波高下限(倍)", step=0.1, key="f9_min14", on_change=save_settings)
c4.number_input("波高上限(倍)", step=0.1, key="f9_max14", on_change=save_settings)

st.sidebar.checkbox("IPO除外(上場1年未満)", key="f5_ipo", on_change=save_settings)
st.sidebar.checkbox("疑義注記・信用リスク銘柄除外", key="f6_risk", on_change=save_settings)
st.sidebar.checkbox("上昇第3波終了銘柄を除外", key="f11_ex_wave3", on_change=save_settings)
st.sidebar.checkbox("非常に割高・赤字銘柄を除外", key="f12_ex_overvalued", on_change=save_settings)

st.sidebar.divider()
st.sidebar.header("🎯 買いルール")
st.sidebar.number_input("購入ロット(株)", step=100, key="bt_lot", on_change=save_settings)
st.sidebar.number_input("目標到達の猶予期限(日)", step=1, key="limit_d", on_change=save_settings)

st.sidebar.header("💰 売りルール")
st.sidebar.number_input("利確目標(%)", step=1, key="bt_tp", on_change=save_settings)
c5, c6 = st.sidebar.columns(2)
c5.number_input("初期損切(%)", step=1, key="bt_sl_i", on_change=save_settings)
c6.number_input("現在損切(%)", step=1, key="bt_sl_c", on_change=save_settings)
st.sidebar.number_input("最大保持期間(日)", step=1, key="bt_sell_d", on_change=save_settings)

st.sidebar.divider()
st.sidebar.header("🚫 特殊除外フィルター")
st.sidebar.checkbox("ETF・REIT等を除外", key="f7_ex_etf", on_change=save_settings)
st.sidebar.checkbox("医薬品(バイオ)を除外", key="f8_ex_bio", on_change=save_settings)
st.sidebar.checkbox("落ちるナイフ除外(暴落直後)", key="f10_ex_knife", on_change=save_settings)
st.sidebar.text_area("除外銘柄コード (雑なコピペ対応)", key="gigi_input", on_change=save_settings)

st.sidebar.divider()
st.sidebar.header("⚙️ システム管理")
if st.sidebar.button("🔴 キャッシュ強制パージ", use_container_width=True):
    st.cache_data.clear(); st.rerun()
if st.sidebar.button("💾 現在の設定を保存", use_container_width=True):
    save_settings(); st.toast("設定を保存した。")

# --- 5. タブ再構成 ---
tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs(["🌐 【待伏】広域レーダー", "⚡ 【強襲】GC初動レーダー", "🎯 【照準】精密スコープ", "⚙️ 【演習】戦術シミュレータ", "⛺ 【戦線】交戦モニター", "📁 【戦歴】交戦データベース"])
master_df = load_master()

with tab1:
    st.markdown('<h3 style="font-size: clamp(14px, 4.5vw, 24px); margin-bottom: 1rem;">🎯 【待伏】鉄の掟・半値押しレーダー</h3>', unsafe_allow_html=True)
    run_scan_t1 = st.button("🚀 最新データで待伏スキャン開始")

    if run_scan_t1:
        st.toast("🟢 待伏トリガーを確認。索敵開始！", icon="🎯")
        with st.spinner("全銘柄からターゲットを索敵中..."):
            raw = get_hist_data_cached()
            if not raw:
                st.error("データの取得に失敗した。")
                st.session_state.tab1_scan_results = None
            else:
                df = clean_df(pd.DataFrame(raw)).dropna(subset=['AdjC', 'AdjH', 'AdjL']).sort_values(['Code', 'Date'])
                df['Code'] = df['Code'].astype(str)
                v_col = next((col for col in df.columns if col in ['Volume', 'AdjVo', 'Vo', 'AdjustmentVolume']), None)
                avg_vols = df.groupby('Code').tail(5).groupby('Code')[v_col].mean() if v_col else pd.Series(0, index=df['Code'].unique())

                f1_min, f1_max = float(st.session_state.f1_min), float(st.session_state.f1_max)
                f5_ipo, f10_ex_knife = st.session_state.f5_ipo, st.session_state.f10_ex_knife
                push_ratio = st.session_state.push_r / 100.0; limit_d_val = int(st.session_state.limit_d)
                f3_drop_val = float(st.session_state.f3_drop); exclude_etf_flag = st.session_state.f7_ex_etf
                f2_limit = float(st.session_state.f2_m30); f8_bio = st.session_state.f8_ex_bio; f6_risk = st.session_state.f6_risk

                latest_date = df['Date'].max()
                latest_df = df[df['Date'] == latest_date]
                m_mode = "大型" if "大型株" in st.session_state.preset_market else "中小型"
                
                if not master_df.empty:
                    large_kw = ['プライム', '一部']; small_kw = ['スタンダード', 'グロース', '新興', 'マザーズ', 'JASDAQ', '二部']
                    m_target = master_df[master_df['Market'].str.contains('|'.join(large_kw if m_mode == "大型" else small_kw), na=False)]['Code'].unique()
                    df = df[df['Code'].isin(m_target)]

                v_p_codes = latest_df[(latest_df['AdjC'] >= f1_min) & (latest_df['AdjC'] <= f1_max)]['Code'].unique()
                v_v_codes = avg_vols[avg_vols >= 10000].index
                df = df[df['Code'].isin(set(v_p_codes).intersection(set(v_v_codes)))]

                if f5_ipo and not df.empty:
                    s_min = df.groupby('Code')['Date'].min()
                    df = df[df['Code'].isin(s_min[s_min <= (df['Date'].min() + pd.Timedelta(days=15))].index)]

                if exclude_etf_flag and not master_df.empty:
                    inv_mask = master_df['Market'].astype(str).str.contains('ETF|REIT', case=False, na=False) | master_df['Sector'].astype(str).str.contains('ETF|REIT|投信', case=False, na=False)
                    df = df[df['Code'].isin(master_df[~inv_mask]['Code'].unique())]
                
                # 🚨 配線修正：⑧ バイオ除外
                if f8_bio and not master_df.empty:
                    df = df[df['Code'].isin(master_df[~master_df['Sector'].str.contains('医薬品', na=False)]['Code'].unique())]

                g_in = st.session_state.get("gigi_input", "")
                if g_in:
                    bl = re.findall(r'\d{4}', str(g_in))
                    if bl: df = df[~df['Code'].str.extract(r'(\d{4})')[0].isin(bl)]

                master_dict = master_df.set_index('Code')[['CompanyName', 'Market', 'Sector', 'Scale']].to_dict('index') if not master_df.empty else {}
                results = []
                for code, group in df.groupby('Code'):
                    if len(group) < 20: continue 
                    adjc_vals, adjh_vals, adjl_vals = group['AdjC'].values, group['AdjH'].values, group['AdjL'].values
                    lc = adjc_vals[-1]; high_max = adjh_vals.max()

                    # 🚨 配線修正：② 1ヶ月暴騰上限 (20営業日前比)
                    if lc / adjc_vals[max(0, len(adjc_vals)-20)] > f2_limit: continue
                    
                    if lc < high_max * (1 + (f3_drop_val / 100.0)): continue

                    if st.session_state.f11_ex_wave3:
                        peaks = []
                        for j in range(5, len(adjh_vals)-5):
                            if adjh_vals[j] == max(adjh_vals[j-5:j+5]):
                                if not peaks or adjh_vals[j] > peaks[-1] * 1.15: peaks.append(adjh_vals[j])
                        if len(peaks) >= 3 and lc < max(peaks) * 0.85: continue

                    if f10_ex_knife:
                        r4 = adjc_vals[-4:]
                        if len(r4) == 4 and (r4[-1] / r4[0] < 0.85): continue
                    
                    r4h = adjh_vals[-4:]; local_max_idx = r4h.argmax()
                    high_4d_val = r4h[local_max_idx]; global_max_idx = len(adjh_vals) - 4 + local_max_idx
                    low_14d_val = adjl_vals[max(0, global_max_idx - 14) : global_max_idx + 1].min()

                    if low_14d_val <= 0 or high_4d_val <= low_14d_val: continue
                    wave_height = high_4d_val / low_14d_val
                    if not (st.session_state.f9_min14 <= wave_height <= st.session_state.f9_max14): continue
                    
                    target_buy = high_4d_val - ((high_4d_val - low_14d_val) * push_ratio)
                    reach_rate = (target_buy / lc) * 100
                    rsi, macd_h, macd_h_prev, _ = get_fast_indicators(adjc_vals)
                    
                    score = 4 
                    if 1.3 <= wave_height <= 2.0: score += 1
                    if (len(adjh_vals) - 1 - global_max_idx) <= limit_d_val: score += 1
                    if not check_double_top(group.tail(31).iloc[:-1]): score += 1
                    if target_buy * 0.85 <= lc <= target_buy * 1.35: score += 1
                    
                    m_info = master_dict.get(code, {})
                    rank, bg, t_score, _ = get_triage_info(macd_h, macd_h_prev, rsi, lc, target_buy, mode="待伏")
                    results.append({'Code': code, 'Name': m_info.get('CompanyName', f"銘柄 {code[:4]}"), 'Sector': m_info.get('Sector', '不明'), 'Market': m_info.get('Market', '不明'), 'lc': lc, 'RSI': rsi, 'avg_vol': int(avg_vols.get(code, 0)), 'high_4d': high_4d_val, 'low_14d': low_14d_val, 'target_buy': target_buy, 'reach_rate': reach_rate, 'triage_rank': rank, 'triage_bg': bg, 't_score': t_score, 'score': score})
                st.session_state.tab1_scan_results = sorted(results, key=lambda x: (x['t_score'], x['score']), reverse=True)[:30]
                import gc; gc.collect()

    if st.session_state.get("tab1_scan_results"):
        res = st.session_state.tab1_scan_results
        st.success(f"🎯 待伏ロックオン: {len(res)} 銘柄を確認。")
        sab_codes = " ".join([str(r['Code'])[:4] for r in res if str(r['triage_rank']).startswith(('S', 'A', 'B'))])
        if sab_codes:
            st.info("📋 以下のコードをコピーして、照準（TAB3）にペースト可能だ。")
            st.code(sab_codes, language="text")
        for r in res:
            st.divider()
            m_lower = str(r['Market']).lower()
            if 'プライム' in m_lower or '一部' in m_lower: badge_html = '<span style="background-color: #1a237e; color: #ffffff; padding: 0.2rem 0.6rem; border-radius: 4px; font-size: 11px; font-weight: bold;">🏢 プライム/大型</span>'
            elif 'グロース' in m_lower or 'マザーズ' in m_lower: badge_html = '<span style="background-color: #1b5e20; color: #ffffff; padding: 0.2rem 0.6rem; border-radius: 4px; font-size: 11px; font-weight: bold;">🚀 グロース/新興</span>'
            else: badge_html = f'<span style="background-color: #455a64; color: #ffffff; padding: 0.2rem 0.6rem; border-radius: 4px; font-size: 11px; font-weight: bold;">{r.get("Market")}</span>'
            t_badge = f'<span style="background-color: {r.get("triage_bg")}; color: #ffffff; padding: 0.2rem 0.6rem; border-radius: 4px; font-size: 13px; display: inline-block; font-weight: bold; margin-left: 0.5rem;">🎯 優先度: {r.get("triage_rank")}</span>'
            score_val = r.get("score", 0); score_color = "#2e7d32" if score_val >= 7 else "#ff5722"; score_bg = "rgba(46, 125, 50, 0.15)" if score_val >= 7 else "rgba(255, 87, 34, 0.15)"
            score_badge = f'<span style="background-color: {score_bg}; border: 1px solid {score_color}; color: {score_color}; padding: 0.2rem 0.6rem; border-radius: 4px; font-size: 12px; font-weight: bold; margin-left: 0.5rem;">🎖️ 掟スコア: {score_val}/9</span>'
            swing_pct = ((r.get('high_4d', 0) - r.get('low_14d', 0)) / r.get('low_14d', 1)) * 100
            volatility_badge = f'<span style="background-color: #ff9800; color: #ffffff; padding: 0.2rem 0.6rem; border-radius: 4px; font-size: 11px; font-weight: bold; margin-left: 0.5rem; border: 1px solid #e65100;">⚡ 高ボラ ({swing_pct:.1f}%)</span>' if swing_pct >= (40.0 if ('プライム' in m_lower or '一部' in m_lower) else 60.0) else ""
            st.markdown(f'<div style="margin-bottom: 0.8rem;"><h3 style="font-size: clamp(18px, 5vw, 28px); font-weight: bold; margin: 0 0 0.3rem 0;">({str(r["Code"])[:4]}) {r.get("Name")}</h3><div style="display: flex; flex-wrap: wrap; gap: 6px; align-items: center;">{badge_html}{t_badge}{score_badge}{volatility_badge}<span style="background-color: rgba(38, 166, 154, 0.15); border: 1px solid #26a69a; color: #26a69a; padding: 0.1rem 0.5rem; border-radius: 4px; font-size: 12px; margin-left: 4px;">RSI: {r.get("RSI", 50):.1f}%</span><span style="background-color: rgba(255, 215, 0, 0.1); border: 1px solid #FFD700; color: #FFD700; padding: 0.1rem 0.5rem; border-radius: 4px; font-size: 12px;">到達度: {r.get("reach_rate"):.1f}%</span></div></div>', unsafe_allow_html=True)
            m_cols = st.columns([1, 1, 1, 1.2, 1.5])
            m_cols[0].metric("直近高値", f"{int(r.get('high_4d', 0)):,}円"); m_cols[1].metric("起点安値", f"{int(r.get('low_14d', 0)):,}円"); m_cols[2].metric("最新終値", f"{int(r.get('lc', 0)):,}円"); m_cols[3].metric("平均出来高(5日)", f"{int(r.get('avg_vol', 0)):,}株")
            html_buy = f'<div style="background: rgba(255, 215, 0, 0.05); padding: 0.5rem; border-radius: 8px; border: 1px solid rgba(255, 215, 0, 0.2); text-align: center;"><div style="font-size: 13px; color: rgba(250, 250, 250, 0.6); margin-bottom: 2px;">🎯 半値押し 買値目標</div><div style="font-size: 1.8rem; font-weight: bold; color: #FFD700;">{int(r.get("target_buy", 0)):,}<span style="font-size: 14px; margin-left:2px;">円</span></div></div>'
            m_cols[4].markdown(html_buy, unsafe_allow_html=True); st.caption(f"🏢 {r.get('Market','不明')} ｜ 🏭 {r.get('Sector','不明')}")

with tab2:
    st.markdown('<h3 style="font-size: clamp(14px, 4.5vw, 24px); margin-bottom: 1rem;">⚡ 【強襲】GC初動レーダー</h3>', unsafe_allow_html=True)
    c_t2_1, c_t2_2 = st.columns(2)
    rsi_lim_val = c_t2_1.number_input("RSI上限（過熱感の足切り）", step=5, key="tab2_rsi_limit", on_change=save_settings)
    vol_lim_val = c_t2_2.number_input("最低出来高（5日平均）", step=5000, key="tab2_vol_limit", on_change=save_settings)
    run_scan_t2 = st.button("🚀 全軍GC初動スキャン開始", key="btn_assault_scan")

    if run_scan_t2:
        st.toast("🟢 強襲トリガーを確認。索敵開始！", icon="🚀")
        with st.spinner("GC初動候補を抽出中..."):
            raw = get_hist_data_cached()
            if not raw:
                st.session_state.tab2_scan_results = None
            else:
                df = clean_df(pd.DataFrame(raw)).dropna(subset=['AdjC', 'AdjH', 'AdjL']).sort_values(['Code', 'Date'])
                df['Code'] = df['Code'].astype(str)
                v_col = next((col for col in df.columns if col in ['Volume', 'AdjVo', 'Vo', 'AdjustmentVolume']), None)
                avg_vols = df.groupby('Code').tail(5).groupby('Code')[v_col].mean() if v_col else pd.Series(0, index=df['Code'].unique())
                f1_min, f1_max = float(st.session_state.f1_min), float(st.session_state.f1_max)
                f5_ipo = st.session_state.f5_ipo; f3_drop_val = float(st.session_state.f3_drop)
                m_mode = "大型" if "大型株" in st.session_state.preset_market else "中小型"
                if not master_df.empty:
                    target_kw = ['プライム', '一部'] if m_mode=="大型" else ['スタンダード', 'グロース', '新興', 'マザーズ', 'JASDAQ', '二部']
                    m_target_codes = master_df[master_df['Market'].str.contains('|'.join(target_kw), na=False)]['Code'].unique()
                    df = df[df['Code'].isin(m_target_codes)]
                valid_codes = set(df[df['Date']==df['Date'].max()][(df['AdjC']>=f1_min) & (df['AdjC']<=f1_max)]['Code']).intersection(set(avg_vols[avg_vols>=vol_lim_val].index))
                df = df[df['Code'].isin(valid_codes)]
                if f5_ipo and not df.empty:
                    s_min = df.groupby('Code')['Date'].min()
                    df = df[df['Code'].isin(s_min[s_min <= (df['Date'].min() + pd.Timedelta(days=15))].index)]
                g_in = st.session_state.get("gigi_input", "")
                if g_in:
                    bl = re.findall(r'\d{4}', str(g_in))
                    if bl: df = df[~df['Code'].str.extract(r'(\d{4})')[0].isin(bl)]
                master_dict = master_df.set_index(master_df['Code'].astype(str))[['CompanyName', 'Market', 'Sector', 'Scale']].to_dict('index') if not master_df.empty else {}
                results = []
                for code, group in df.groupby('Code'):
                    if len(group) < 20: continue
                    adjc_vals, adjh_vals = group['AdjC'].values, group['AdjH'].values; lc = adjc_vals[-1]
                    if lc < adjh_vals.max() * (1 + (f3_drop_val / 100.0)): continue
                    rsi, m_h, m_hp, h5 = get_fast_indicators(adjc_vals)
                    if rsi > rsi_lim_val: continue
                    gc_days = 1 if len(h5)>=2 and h5[-2]<0 and h5[-1]>=0 else 2 if len(h5)>=3 and h5[-3]<0 and h5[-1]>=0 else 3 if len(h5)>=4 and h5[-4]<0 and h5[-1]>=0 else 0
                    if gc_days == 0: continue
                    latest_ma25 = sum(adjc_vals[-25:]) / 25 if len(adjc_vals) >= 25 else adjc_vals.mean()
                    if lc < (latest_ma25 * 0.95): continue
                    t_rank, t_color, t_score, _ = get_assault_triage_info(gc_days, lc, rsi, pd.DataFrame([{'MA25':latest_ma25}]), is_strict=False)
                    m_i = master_dict.get(str(code), {})
                    results.append({'Code':code, 'Name':m_i.get('CompanyName', f"銘柄 {code[:4]}"), 'Market':m_i.get('Market','不明'), 'Sector':m_i.get('Sector','不明'), 'lc':lc, 'RSI':rsi, 'avg_vol':int(avg_vols.get(code,0)), 'h14':adjh_vals[-14:].max(), 'atr':lc*0.03, 'T_Rank':t_rank, 'T_Color':t_color, 'T_Score':t_score, 'GC_Days':gc_days})
                st.session_state.tab2_scan_results = sorted(results, key=lambda x: (-x['T_Score'], x['GC_Days'], x['RSI']))[:30]
                import gc; gc.collect()

    if st.session_state.get("tab2_scan_results"):
        l_res = st.session_state.tab2_scan_results
        st.success(f"⚡ 強襲ロックオン: GC初動(3日以内) 上位 {len(l_res)} 銘柄を確認。")
        sab_codes = " ".join([str(r.get('Code', ''))[:4] for r in l_res if str(r.get('T_Rank', '')).startswith(('S', 'A', 'B'))])
        if sab_codes:
            st.info("📋 以下のコードをコピーして、照準（TAB3）にペースト可能だ。")
            st.code(sab_codes, language="text")
        for r in l_res:
            st.divider()
            m_l = str(r['Market']).lower()
            if 'プライム' in m_l or '一部' in m_l: b_html = '<span style="background-color: #1a237e; color: #ffffff; padding: 0.2rem 0.6rem; border-radius: 4px; font-size: 11px; font-weight: bold;">🏢 プライム/大型</span>'
            elif 'グロース' in m_l or 'マザーズ' in m_l: b_html = '<span style="background-color: #1b5e20; color: #ffffff; padding: 0.2rem 0.6rem; border-radius: 4px; font-size: 11px; font-weight: bold;">🚀 グロース/新興</span>'
            else: b_html = f'<span style="background-color: #455a64; color: #ffffff; padding: 0.2rem 0.6rem; border-radius: 4px; font-size: 11px; font-weight: bold;">{r["Market"]}</span>'
            t_b = f'<span style="background-color: {r.get("T_Color", "#616161")}; color: #ffffff; padding: 0.2rem 0.6rem; border-radius: 4px; font-size: 13px; display: inline-block; font-weight: bold; margin-left: 0.5rem;">🎯 優先度: {r.get("T_Rank")}</span>'
            st.markdown(f'<div style="margin-bottom: 0.8rem;"><h3 style="font-size: 24px; font-weight: bold; margin: 0 0 0.3rem 0;">({str(r["Code"])[:4]}) {r["Name"]}</h3><div style="display: flex; flex-wrap: wrap; gap: 6px; align-items: center;">{b_html}{t_b}<span style="background-color: rgba(237, 108, 2, 0.15); border: 1px solid #ed6c02; color: #ed6c02; padding: 0.1rem 0.5rem; border-radius: 4px; font-size: 12px;">GC後 {r.get("GC_Days")}日目</span><span style="background-color: rgba(38, 166, 154, 0.15); border: 1px solid #26a69a; color: #26a69a; padding: 0.1rem 0.5rem; border-radius: 4px; font-size: 12px;">RSI: {r.get("RSI", 50):.1f}%</span></div></div>', unsafe_allow_html=True)
            lc_v, h14_v, atr_v = r['lc'], r['h14'], r['atr']
            t_p, d_p = max(h14_v, lc_v + (atr_v * 0.5)), max(h14_v, lc_v + (atr_v * 0.5)) - atr_v
            m_cols = st.columns([1, 1, 1, 1.2, 1.5])
            m_cols[0].metric("最新終値", f"{int(lc_v):,}円"); m_cols[1].metric("RSI", f"{r['RSI']:.1f}%"); m_cols[2].metric("ATR(14d)", f"{int(atr_v):,}円")
            m_cols[3].markdown(f'<div style="background: rgba(239, 83, 80, 0.05); padding: 0.5rem; border-radius: 8px; border: 1px solid rgba(239, 83, 80, 0.3); text-align: center;"><div style="font-size: 13px; color: rgba(250, 250, 250, 0.6); margin-bottom: 2px;">🛡️ 動的防衛線 (-1.0 ATR)</div><div style="font-size: 1.6rem; font-weight: bold; color: #ef5350;">{int(d_p):,}<span style="font-size: 14px; margin-left:2px;">円</span></div></div>', unsafe_allow_html=True)
            m_cols[4].markdown(f'<div style="background: rgba(255, 215, 0, 0.05); padding: 0.5rem; border-radius: 8px; border: 1px solid rgba(255, 215, 0, 0.2); text-align: center;"><div style="font-size: 13px; color: rgba(250, 250, 250, 0.6); margin-bottom: 2px;">🎯 強襲トリガー (14d高値基準)</div><div style="font-size: 1.6rem; font-weight: bold; color: #FFD700;">{int(t_p):,}<span style="font-size: 14px; margin-left:2px;">円</span></div></div>', unsafe_allow_html=True)
            st.caption(f"🏭 {r['Sector']} ｜ 📊 平均出来高: {int(r['avg_vol']):,}株")

with tab3:
    st.markdown('<h3 style="font-size: clamp(14px, 4.5vw, 24px); margin-bottom: 1rem;">🎯 【照準】精密スコープ（戦術別・独立索敵）</h3>', unsafe_allow_html=True)
    T3_AM_WATCH_FILE = f"saved_t3_am_watch_{user_id}.txt"; T3_AM_DAILY_FILE = f"saved_t3_am_daily_{user_id}.txt"; T3_AS_WATCH_FILE = f"saved_t3_as_watch_{user_id}.txt"; T3_AS_DAILY_FILE = f"saved_t3_as_daily_{user_id}.txt"
    def load_t3_text(f_p):
        if os.path.exists(f_p):
            with open(f_p, "r", encoding="utf-8") as f: return f.read()
        return ""
    if "t3_am_watch" not in st.session_state: st.session_state.t3_am_watch = load_t3_text(T3_AM_WATCH_FILE)
    if "t3_am_daily" not in st.session_state: st.session_state.t3_am_daily = load_t3_text(T3_AM_DAILY_FILE)
    if "t3_as_watch" not in st.session_state: st.session_state.t3_as_watch = load_t3_text(T3_AS_WATCH_FILE)
    if "t3_as_daily" not in st.session_state: st.session_state.t3_as_daily = load_t3_text(T3_AS_DAILY_FILE)
    col_s1, col_s2 = st.columns([1.2, 1.8])
    with col_s1:
        scope_mode = st.radio("🎯 解析モードを選択", ["🌐 【待伏】 押し目・逆張り", "⚡ 【強襲】 トレンド・順張り"], key="t3_scope_mode", on_change=save_settings)
        is_ambush = "待伏" in scope_mode; st.markdown("---")
        if is_ambush:
            watch_in = st.text_area("🌐 【待伏】主力監視部隊", value=st.session_state.t3_am_watch, height=120)
            daily_in = st.text_area("🌐 【待伏】本日新規部隊", value=st.session_state.t3_am_daily, height=120)
        else:
            watch_in = st.text_area("⚡ 【強襲】主力監視部隊", value=st.session_state.t3_as_watch, height=120)
            daily_in = st.text_area("⚡ 【強襲】本日新規部隊", value=st.session_state.t3_as_daily, height=120)
        run_scope = st.button("🔫 表示中の部隊を精密スキャン", use_container_width=True, type="primary")
    with col_s2:
        st.markdown("#### 🔍 索敵ステータス")
        if is_ambush: 
            st.info("・【待伏専用】半値押し・黄金比での迎撃判定")
            st.markdown('<div style="font-size: 13px; color: #bbb; background: rgba(255,255,255,0.05); padding: 10px; border-radius: 5px; border-left: 3px solid #2e7d32;"><b>【掟スコア加点基準】</b><br>✅ MACD/RSI優位性 ｜ ✅ 波高1.3〜2.0倍 ｜ ✅ 調整日数規定内<br>✅ 危険波形なし ｜ ✅ 買値±15%圏内 ｜ ✅ PBR 5.0倍以下</div>', unsafe_allow_html=True)
        else: 
            st.warning("・【強襲専用】ATR/14日高値ベースの動的ブレイクアウト判定")
            st.markdown('<div style="font-size: 13px; color: #bbb; background: rgba(255,255,255,0.05); padding: 10px; border-radius: 5px; border-left: 3px solid #ed6c02;"><b>【強襲スコア加点基準】</b><br>⚡ GC発動 ｜ ⚡ 25日線上抜け ｜ ⚡ 出来高急増<br>⚡ 適正RSI ｜ ⚡ PBR 5.0倍以下</div>', unsafe_allow_html=True)

    if run_scope:
        if is_ambush:
            with open(T3_AM_WATCH_FILE, "w", encoding="utf-8") as f: f.write(watch_in)
            with open(T3_AM_DAILY_FILE, "w", encoding="utf-8") as f: f.write(daily_in)
            st.session_state.t3_am_watch, st.session_state.t3_am_daily = watch_in, daily_in
        else:
            with open(T3_AS_WATCH_FILE, "w", encoding="utf-8") as f: f.write(watch_in)
            with open(T3_AS_DAILY_FILE, "w", encoding="utf-8") as f: f.write(daily_in)
            st.session_state.t3_as_watch, st.session_state.t3_as_daily = watch_in, daily_in
        all_text = watch_in + " " + daily_in
        t_codes = list(dict.fromkeys([c.upper() for c in re.findall(r'(?<![a-zA-Z0-9])[a-zA-Z0-9]{4}(?![a-zA-Z0-9])', all_text)]))
        if not t_codes: st.warning("有効な銘柄コードが確認できません。")
        else:
            with st.spinner(f"全 {len(t_codes)} 銘柄を精密計算中..."):
                raw_data_dict = {}
                def fetch_single_data_t3(c):
                    api_c = c if len(c) == 5 else c + "0"
                    data = get_single_data(api_c, 1)
                    per, pbr, mcap = None, None, None
                    try:
                        import yfinance as yf
                        tk = yf.Ticker(c[:4] + ".T"); info = tk.info
                        per = info.get('trailingPE'); pbr = info.get('priceToBook'); mcap = info.get('marketCap')
                    except: pass
                    return c, data, per, pbr, mcap
                with concurrent.futures.ThreadPoolExecutor(max_workers=5) as exe:
                    futs = [exe.submit(fetch_single_data_t3, c) for c in t_codes]
                    for f in concurrent.futures.as_completed(futs):
                        r_c, r_data, r_per, r_pbr, r_mcap = f.result()
                        raw_data_dict[r_c] = {"data": r_data, "per": r_per, "pbr": r_pbr, "mcap": r_mcap}
                scope_results = []
                for c in t_codes:
                    r_s = raw_data_dict.get(c)
                    if not r_s or not r_s["data"]: continue
                    df_s = clean_df(pd.DataFrame(r_s["data"].get("bars", [])))
                    if len(df_s) < 30: continue
                    df_chart = calc_technicals(df_s.copy()); df_14 = df_s.tail(15).iloc[:-1]
                    latest = df_chart.iloc[-1]; prev = df_chart.iloc[-2]
                    lc = latest['AdjC']; h14 = df_14['AdjH'].max(); l14 = df_14['AdjL'].min(); ur = h14 - l14
                    is_dt = check_double_top(df_s.tail(31).iloc[:-1]); is_hs = check_head_shoulders(df_s.tail(31).iloc[:-1])
                    rsi_v = latest.get('RSI', 50); atr_v = int(latest.get('ATR', 0))
                    r_mcap = r_s.get("mcap"); mcap_str = f"{r_mcap / 1e12:.2f}兆円" if r_mcap and r_mcap >= 1e12 else f"{r_mcap / 1e8:.0f}億円" if r_mcap else "-"
                    score = 4
                    if h14 > 0 and l14 > 0:
                        r14 = h14 / l14; idx_m = df_14['AdjH'].idxmax()
                        d_h = len(df_14[df_14['Date'] > df_14.loc[idx_m, 'Date']]) if pd.notna(idx_m) else 0
                        if 1.3 <= r14 <= 2.0: score += 1
                        if d_h <= int(st.session_state.limit_d): score += 1
                        if not is_dt: score += 1
                        if not is_hs: score += 1
                    if is_ambush:
                        bt_p = h14 - (ur * (st.session_state.push_r / 100.0)); s_r = 0.618 if st.session_state.push_r >= 40 else (st.session_state.push_r / 100.0 + 0.15)
                        bt_v = int(h14 - (ur * s_r)) if lc < bt_p else int(bt_p)
                        if bt_v * 0.85 <= lc <= bt_v * 1.35: score += 1
                        rank, bg, t_s, _ = get_triage_info(latest['MACD_Hist'], prev['MACD_Hist'], rsi_v, lc, bt_v, mode="待伏")
                        reach = ((h14 - lc) / (h14 - bt_v) * 100) if (h14 - bt_v) > 0 else 0
                        if r_s['pbr'] and r_s['pbr'] <= 5.0: score += 1
                    else:
                        bt_v = int(max(h14, lc + (atr_v * 0.5))); h_v = df_chart['MACD_Hist'].tail(5).values
                        gc_d = 1 if h_v[-2] < 0 and h_v[-1] >= 0 else 2 if h_v[-3] < 0 and h_v[-1] >= 0 else 3 if h_v[-4] < 0 and h_v[-1] >= 0 else 0
                        rank, bg, t_s, _ = get_assault_triage_info(gc_d, lc, rsi_v, df_chart, is_strict=True)
                        reach = 100 - rsi_v; score = t_s
                    c_n = f"銘柄 {c[:4]}"; c_s = "不明"; c_m = "不明"
                    if not master_df.empty:
                        m_r = master_df[master_df['Code'].astype(str).str.contains(c[:4])]
                        if not m_r.empty: c_n = m_r.iloc[0]['CompanyName']; c_s = m_r.iloc[0]['Sector']; c_m = m_r.iloc[0]['Market']
                    scope_results.append({'code': c, 'name': c_n, 'lc': lc, 'h14': h14, 'l14': l14, 'ur': ur, 'bt_val': bt_v, 'atr_val': atr_v, 'rsi': rsi_v, 'is_dt': is_dt, 'is_hs': is_hs, 'rank': rank, 'bg': bg, 'score': score, 'reach_val': reach, 'df_chart': df_chart, 'per': r_s['per'], 'pbr': r_s['pbr'], 'mcap': mcap_str, 'source': "🛡️ 監視" if c in watch_in else "🚀 新規", 'sector': c_s, 'market': c_m})
                r_order = {"S": 4, "A": 3, "B": 2, "C": 1, "圏外": 0}
                for res in scope_results: res['r_val'] = r_order.get(re.sub(r'[^SABC圏外]', '', res['rank']), 0)
                scope_results = sorted(scope_results, key=lambda x: (x['r_val'], x['score'], x['reach_val']), reverse=True)
                for r in scope_results:
                    st.divider(); s_c = "#42a5f5" if "監視" in r['source'] else "#ffa726"; m_i = r.get('market', '不明'); m_low = str(m_i).lower()
                    if 'プライム' in m_low or '一部' in m_low: m_b = '<span style="background-color: #1a237e; color: #ffffff; padding: 0.2rem 0.6rem; border-radius: 4px; font-size: 11px; font-weight: bold;">🏢 プライム/大型</span>'
                    elif 'グロース' in m_low or 'マザーズ' in m_low: m_b = '<span style="background-color: #1b5e20; color: #ffffff; padding: 0.2rem 0.6rem; border-radius: 4px; font-size: 11px; font-weight: bold;">🚀 グロース/新興</span>'
                    else: m_b = f'<span style="background-color: #455a64; color: #ffffff; padding: 0.2rem 0.6rem; border-radius: 4px; font-size: 11px; font-weight: bold;">{m_i}</span>'
                    s_b = f"<span style='background-color:{s_c}; color:white; padding:2px 6px; border-radius:4px; font-size:12px;'>{r['source']}</span>"; t_b = f"<span style='background-color:{r['bg']}; color:white; padding:2px 8px; border-radius:4px; margin-left:10px; font-weight:bold;'>🎯 優先度: {r['rank']}</span>"
                    st.markdown(f'<div style="margin-bottom: 0.8rem;"><h3 style="font-size: clamp(18px, 5vw, 28px); font-weight: bold; margin: 0;">{s_b} ({r["code"][:4]}) {r["name"]}</h3><div style="display: flex; flex-wrap: wrap; gap: 6px;">{m_b}{t_b}<span style="background:rgba(38,166,154,0.15); border:1px solid #26a69a; color:#26a69a; padding:2px 6px; border-radius:4px; font-size:12px;">RSI: {r["rsi"]:.1f}%</span><span style="background:rgba(255,215,0,0.1); border:1px solid #FFD700; color:#FFD700; padding:2px 6px; border-radius:4px; font-size:12px;">到達度: {r["reach_val"]:.1f}%</span></div></div>', unsafe_allow_html=True)
                    if r['is_dt'] or r['is_hs']: st.error("🚨 【警告】相場転換の危険波形（三尊/Wトップ）を検知。")
                    sc_l, sc_m, sc_r = st.columns([2.5, 3.5, 5.0])
                    with sc_l:
                        atr_calc = r['atr_val'] if r['atr_val'] > 0 else r['lc'] * 0.05
                        c_m1, c_m2 = st.columns(2); c_m1.metric("直近高値", f"{int(r['h14']):,}円"); c_m2.metric("直近安値", f"{int(r['l14']):,}円")
                        c_m3, c_m4 = st.columns(2); c_m3.metric("上昇幅", f"{int(r['ur']):,}円"); c_m4.metric("最新終値", f"{int(r['lc']):,}円")
                        st.metric("🌪️ 1ATR", f"{int(atr_calc):,}円", f"ボラ: {(atr_calc/r['lc'])*100:.1f}%", delta_color="off"); st.caption(f"🏭 {r['sector']}")
                    with sc_m:
                        per_c = "#26a69a" if (r['per'] and r['per'] <= 50) else "#ef5350"; pbr_c = "#26a69a" if (r['pbr'] and r['pbr'] <= 5.0) else "#ef5350"
                        idx_html = f"<div style='display:flex; justify-content:space-between; text-align:center; margin-top:8px;'><div style='flex:1;'><div style='font-size:12px; color:#888;'>📊 PER</div><div style='font-size:1.4rem; color:{per_c}; font-weight:bold;'>{r['per']:.1f}倍</div></div><div style='flex:1;'><div style='font-size:12px; color:#888;'>📉 PBR</div><div style='font-size:1.4rem; color:{pbr_c}; font-weight:bold;'>{r['pbr']:.2f}倍</div></div></div>" if r['per'] else ""
                        box_t = "🎯 買値目標" if is_ambush else "🎯 トリガー (14d高値)"
                        st.markdown(f"<div style='background:rgba(255,215,0,0.05); padding:1rem; border-radius:10px; border:1px solid rgba(255,215,0,0.3); text-align:center;'><div style='font-size:14px;'>{box_t}</div><div style='font-size:2.4rem; font-weight:bold; color:#FFD700;'>{int(r['bt_val']):,}円</div><div style='border-top:1px dashed #444; margin:10px 0;'></div>{idx_html}<div style='text-align:center; margin-top:5px;'><div style='font-size:11px; color:#888;'>💰 時価総額</div><div style='font-size:1.2rem; color:#fff; font-weight:bold;'>{r['mcap']}</div></div></div>", unsafe_allow_html=True)
                    with sc_r:
                        c_t, a_v = r['bt_val'], r['atr_val'] if r['atr_val'] > 0 else r['bt_val'] * 0.05
                        tp_m, sl_m = [0.5, 1.0, 2.0, 3.0], [0.5, 1.0, 2.0]; is_agg = any(m in r['rank'] for m in ["⚡", "🔥", "S"]); r_tps = [2.0, 3.0] if is_agg else [0.5, 1.0]
                        h_mat = f"<div style='background:rgba(255,255,255,0.05); padding:1.2rem; border-radius:8px; border-left:5px solid #FFD700;'><div style='font-size:14px; color:#aaa; margin-bottom:12px; border-bottom:1px solid #444;'>📊 動的ATRマトリクス (基準:{int(c_t):,}円 | 1ATR:{int(a_v):,}円)</div><div style='display:flex; gap:30px;'><div style='flex:1;'><div style='color:#26a69a; border-bottom:2px solid #26a69a;'>【利確目安】</div>"
                        for m in tp_m:
                            v = int(c_t + (a_v * m)); p = ((v / c_t) - 1) * 100
                            if m in r_tps: h_mat += f"<div style='display:flex; justify-content:space-between; background:rgba(38,166,154,0.15); border:1px solid #26a69a; border-radius:4px; padding:2px 6px;'><span style='color:#80cbc4;'>+{m}ATR ({p:+.1f}%)</span><b>{v:,}</b></div>"
                            else: h_mat += f"<div style='display:flex; justify-content:space-between; padding:3px 6px;'><span>+{m}ATR ({p:+.1f}%)</span><b>{v:,}</b></div>"
                        h_mat += "</div><div style='flex:1;'><div style='color:#ef5350; border-bottom:2px solid #ef5350;'>【防衛目安】</div>"
                        for m in sl_m:
                            v = int(c_t - (a_v * m)); p = (1 - (v / c_t)) * 100
                            if m == 1.0: h_mat += f"<div style='display:flex; justify-content:space-between; background:rgba(239,83,80,0.15); border:1px solid #ef5350; border-radius:4px; padding:2px 6px;'><span style='color:#ef9a9a;'>-{m}ATR ({p:.1f}%)</span><b>{v:,}</b></div>"
                            else: h_mat += f"<div style='display:flex; justify-content:space-between; padding:3px 6px;'><span>-{m}ATR ({p:.1f}%)</span><b>{v:,}</b></div>"
                        st.markdown(h_mat + "</div></div></div>", unsafe_allow_html=True); st.expander("ℹ️ 凡例").write("+0.5~1.0:短期, +2.0:スイング, +3.0:極み")
                    st.markdown("---")
                    d_p = r['df_chart'].tail(100).copy(); d_p['display_date'] = d_p['Date'].dt.strftime('%m/%d')
                    fig = go.Figure()
                    fig.add_trace(go.Candlestick(x=d_p['display_date'], open=d_p['AdjO'], high=d_p['AdjH'], low=d_p['AdjL'], close=d_p['AdjC'], name="価格", increasing_line_color='#26a69a', decreasing_line_color='#ef5350'))
                    for m_c, m_n, m_col in [('MA5','5日','#ffca28'),('MA25','25日','#42a5f5'),('MA75','75日','#ab47bc')]:
                        fig.add_trace(go.Scatter(x=d_p['display_date'], y=d_p[m_c], name=m_n, mode='lines', line=dict(color=m_col, width=1.5)))
                    fig.add_trace(go.Scatter(x=d_p['display_date'], y=[r['bt_val']]*len(d_p), name="目標", mode='lines', line=dict(color='#FFD700', width=2, dash='dot')))
                    fig.update_layout(height=450, margin=dict(l=0, r=0, t=10, b=50), xaxis_rangeslider_visible=False, paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)', hovermode="x unified", yaxis=dict(side='right', tickformat=",.0f"), xaxis=dict(type='category', dtick=5))
                    st.plotly_chart(fig, use_container_width=True, config={'displayModeBar': False})

with tab4:
    st.markdown('<h3 style="font-size: clamp(14px, 4.5vw, 24px); margin-bottom: 1rem;">⚙️ 戦術シミュレータ</h3>', unsafe_allow_html=True)
    if "bt_mode_sim_v2" not in st.session_state: st.session_state.bt_mode_sim_v2 = "🌐 【待伏】鉄の掟 (押し目狙撃)"
    cur_m = st.session_state.bt_mode_sim_v2
    if "prev_m" not in st.session_state or st.session_state.prev_m != cur_m:
        if "待伏" in cur_m: st.session_state.sim_sell_d_val, st.session_state.sim_limit_d_val = 10, 4
        else: st.session_state.sim_sell_d_val, st.session_state.sim_limit_d_val = 5, 3
        st.session_state.prev_m = cur_m
    st.session_state['_ui_tp'] = int(st.session_state.get("sim_tp_val", 10))
    st.session_state['_ui_sl'] = int(st.session_state.get("sim_sl_val", 8))
    st.session_state['_ui_lim'] = int(st.session_state.get("sim_limit_d_val", 4))
    st.session_state['_ui_sell'] = int(st.session_state.get("sim_sell_d_val", 10))
    st.session_state['_ui_push'] = float(st.session_state.get("sim_push_r_val", 50.0))
    st.session_state['_ui_req'] = int(st.session_state.get("sim_pass_req_val", 7))
    st.session_state['_ui_rsi_am'] = int(st.session_state.get("sim_rsi_lim_ambush_val", 45))
    st.session_state['_ui_rsi_as'] = int(st.session_state.get("sim_rsi_lim_assault_val", 70))
    st.session_state['_ui_risk'] = int(st.session_state.get("sim_time_risk_val", 5))
    col_b1, col_b2 = st.columns([1, 1.8])
    with col_b1: 
        st.radio("戦術モード", ["🌐 【待伏】鉄の掟 (押し目狙撃)", "⚡ 【強襲】GCブレイクアウト (順張り)"], key="bt_mode_sim_v2")
        bt_c_in = st.text_area("銘柄コード", value="7839\n6614", height=100)
        run_bt = st.button("🔥 仮想実弾テスト実行", use_container_width=True)
        optimize_bt = st.button("🚀 戦術の黄金比率を抽出", use_container_width=True)
    with col_b2:
        def s_p(u, s): st.session_state[s] = st.session_state[u]; save_settings()
        cp1, cp2, cp3, cp4 = st.columns(4)
        cp1.number_input("利確目標(%)", step=1, key="_ui_tp", on_change=s_p, args=("_ui_tp", "sim_tp_val"))
        cp2.number_input("損切目安(%)", step=1, key="_ui_sl", on_change=s_p, args=("_ui_sl", "sim_sl_val"))
        cp3.number_input("買い期限(日)", step=1, key="_ui_lim", on_change=s_p, args=("_ui_lim", "sim_limit_d_val"))
        cp4.number_input("売り期限(日)", step=1, key="_ui_sell", on_change=s_p, args=("_ui_sell", "sim_sell_d_val"))
        st.divider()
        if "待伏" in st.session_state.bt_mode_sim_v2:
            ct1, ct2, ct3 = st.columns(3)
            ct1.number_input("📉 押し目(%)", step=0.1, key="_ui_push", on_change=s_p, args=("_ui_push", "sim_push_r_val"))
            ct2.number_input("掟クリア数", step=1, key="_ui_req", on_change=s_p, args=("_ui_req", "sim_pass_req_val"))
            ct3.number_input("RSI上限", step=5, key="_ui_rsi_am", on_change=s_p, args=("_ui_rsi_am", "sim_rsi_lim_ambush_val"))
        else:
            ct1, ct2 = st.columns(2); ct1.number_input("RSI上限", step=5, key="_ui_rsi_as", on_change=s_p, args=("_ui_rsi_as", "sim_rsi_lim_assault_val"))
            ct2.number_input("時間リスク", step=1, key="_ui_risk", on_change=s_p, args=("_ui_risk", "sim_time_risk_val"))

    if (run_bt or optimize_bt) and bt_c_in:
        t_codes = list(dict.fromkeys([c.upper() for c in re.findall(r'(?<![a-zA-Z0-9])[a-zA-Z0-9]{4}(?![a-zA-Z0-9])', bt_c_in)]))
        if t_codes:
            s_tp, s_sl, s_lim, s_sell, s_push = float(st.session_state.sim_tp_val), float(st.session_state.sim_sl_val), int(st.session_state.sim_limit_d_val), int(st.session_state.sim_sell_d_val), float(st.session_state.sim_push_r_val)
            is_amb = "待伏" in st.session_state.bt_mode_sim_v2
            p1_r = range(25, 66, 5) if optimize_bt else [s_push]
            p2_r = range(5, 10, 1) if (optimize_bt and is_amb) else [int(s_tp)]
            pre_d = {}
            for c in t_codes:
                r = get_single_data(c + "0", 2)
                if r and r.get('bars'):
                    c_d = clean_df(pd.DataFrame(r['bars']))
                    if len(c_d) >= 35: pre_d[c] = calc_technicals(c_d)
            if pre_d:
                opt_res = []
                p_bar = st.progress(0, "検証中...")
                total_iters = len(p1_r) * len(p2_r); c_iter = 0
                for t_p1 in p1_r:
                    for t_p2 in p2_r:
                        all_t = []; c_iter += 1
                        for c, df in pre_d.items():
                            pos = None
                            for i in range(35, len(df)):
                                td, pr = df.iloc[i], df.iloc[i-1]
                                if pos is None:
                                    w14, w30 = df.iloc[i-15:i-1], df.iloc[i-31:i-1]; lc_p, atr_p = pr['AdjC'], pr.get('ATR', 0)
                                    h14, l14 = w14['AdjH'].max(), w14['AdjL'].min()
                                    if l14 <= 0 or atr_p <= 0: continue
                                    if is_amb:
                                        if pr.get('RSI', 50) > st.session_state.sim_rsi_lim_ambush_val: continue
                                        bt_v = int(h14 - ((h14 - l14) * (t_p1 / 100.0))); sc = 4
                                        if 1.3 <= (h14/l14) <= 2.0: sc += 1
                                        if bt_v*0.85 <= lc_p <= bt_v*1.35: sc += 1
                                        if sc >= t_p2 and td['AdjL'] <= bt_v: pos = {'b_i': i, 'b_d': td['Date'], 'b_p': min(td['AdjO'], bt_v)}
                                    else:
                                        if pr.get('RSI', 50) > t_p1: continue
                                        if pr['MACD_Hist'] > 0 and df.iloc[i-2]['MACD_Hist'] <= 0:
                                            trig = h14 if h14 > lc_p else lc_p + (atr_p * 0.5)
                                            if td['AdjH'] >= trig: pos = {'b_i': i, 'b_d': td['Date'], 'b_p': max(td['AdjO'], trig), 'e_atr': atr_p, 'trig': trig}
                                if pos:
                                    bp, held = pos['b_p'], i - pos['b_i']; sp = 0; tp_v = bp * (1 + (s_tp/100.0) if is_amb else 1 + (t_p2/100.0))
                                    sl_v = bp * (1 - (s_sl/100.0)) if is_amb else pos['trig'] - pos['e_atr']
                                    if td['AdjL'] <= sl_v: sp = min(td['AdjO'], sl_v)
                                    elif td['AdjH'] >= tp_v: sp = max(td['AdjO'], tp_v)
                                    elif held >= s_sell: sp = td['AdjC']
                                    if sp > 0:
                                        all_t.append({'損益額(円)': int((sp - bp) * st.session_state.bt_lot), '損益(%)': ((sp/bp)-1)*100})
                                        pos = None
                        if all_t:
                            pdf = pd.DataFrame(all_t); opt_res.append({'P1': t_p1, 'P2': t_p2, '利益': pdf['損益額(円)'].sum(), '勝率': len(pdf[pdf['損益額(円)']>0])/len(pdf), '回数': len(pdf)})
                        p_bar.progress(c_iter / total_iters)
                p_bar.empty()
                if opt_res:
                    best = pd.DataFrame(opt_res).sort_values('利益', ascending=False).iloc[0]
                    st.write(f"### 🏆 最適結果: 利益 {int(best['利益']):,}円 / 勝率 {best['勝率']:.1%}"); st.dataframe(pd.DataFrame(opt_res).head(10))

with tab5:
    st.markdown('<h3 style="font-size: clamp(14px, 4.5vw, 24px); margin-bottom: 1rem;">📡 交戦モニター</h3>', unsafe_allow_html=True)
    FRONTLINE_FILE = f"saved_frontline_{user_id}.csv"
    if 'frontline_df' not in st.session_state:
        if os.path.exists(FRONTLINE_FILE):
            try:
                t_df = pd.read_csv(FRONTLINE_FILE); t_df["銘柄"] = t_df["銘柄"].astype(str)
                for c in ["買値", "第1利確", "第2利確", "損切", "現在値"]: t_df[c] = pd.to_numeric(t_df[c], errors='coerce')
                st.session_state.frontline_df = t_df
            except: st.session_state.frontline_df = pd.DataFrame([{"銘柄": "4259", "買値": 668, "第1利確": 688, "第2利確": 714, "損切": 627, "現在値": 681}])
        else: st.session_state.frontline_df = pd.DataFrame([{"銘柄": "4259", "買値": 668, "第1利確": 688, "第2利確": 714, "損切": 627, "現在値": 681}])
    if st.button("🔄 全軍同期 (yfinance)", use_container_width=True):
        import yfinance as yf; upd = False
        for idx, row in st.session_state.frontline_df.iterrows():
            code = str(row['銘柄']).strip()
            if len(code) >= 4:
                try:
                    tk = yf.Ticker(code[:4] + ".T"); hi = tk.history(period="1d")
                    if not hi.empty: st.session_state.frontline_df.at[idx, '現在値'] = round(hi['Close'].iloc[-1], 1); upd = True
                except: pass
        if upd: st.session_state.frontline_df.to_csv(FRONTLINE_FILE, index=False); st.rerun()
    e_df = st.data_editor(st.session_state.frontline_df, num_rows="dynamic", column_config={"銘柄": st.column_config.TextColumn("銘柄"), "現在値": st.column_config.NumberColumn("🔴 現在値", format="%d")}, use_container_width=True, key="f_editor")
    if not e_df.equals(st.session_state.frontline_df): st.session_state.frontline_df = e_df.copy(); e_df.to_csv(FRONTLINE_FILE, index=False); st.rerun()
    for _, row in e_df.iterrows():
        tkr = str(row.get('銘柄', ''))
        if tkr.strip() == "" or pd.isna(row['買値']) or pd.isna(row['現在値']): continue
        b, t1, t2, s, c = float(row['買値']), float(row['第1利確']), float(row['第2利確']), float(row['損切']), float(row['現在値'])
        if c <= s: txt, col, rgba = "💀 被弾", "#ef5350", "rgba(239, 83, 80, 0.15)"
        elif c < b: txt, col, rgba = "⚠️ 警戒", "#ff9800", "rgba(255, 152, 0, 0.15)"
        elif t1 > 0 and c < t1: txt, col, rgba = "🟢 巡航", "#26a69a", "rgba(38, 166, 154, 0.15)"
        else: txt, col, rgba = "🏆 到達", "#ab47bc", "rgba(171, 71, 188, 0.15)"
        fmt = lambda x: f"¥{int(x):,}" if pd.notna(x) and x > 0 else "未設定"
        st.markdown(f'<div style="margin-bottom: 5px;"><span style="font-size: 18px; font-weight: bold;">部隊 [{tkr}]</span><span style="font-size: 14px; font-weight: bold; color: {col}; margin-left: 15px;">{txt}</span></div><div style="display: flex; justify-content: space-between; align-items: center; background: rgba(255,255,255,0.03); padding: 12px 15px; border-radius: 8px; border-left: 5px solid {col};"><div style="flex: 1;"><div style="font-size: 12px; color: #ef5350;">損切</div><div style="font-size: 16px; font-weight: bold;">{fmt(s)}</div></div><div style="flex: 1;"><div style="font-size: 12px; color: #ffca28;">買値</div><div style="font-size: 16px; font-weight: bold;">{fmt(b)}</div></div><div style="flex: 1.5; text-align: center; background: {rgba}; border: 1px solid {col}; border-radius: 6px;"><div style="font-size: 13px; font-weight: bold;">🔴 現在値</div><div style="font-size: 24px; font-weight: bold;">{fmt(c)}</div></div><div style="flex: 1; text-align: right;"><div style="font-size: 12px; color: #26a69a;">利確1</div><div style="font-size: 16px; font-weight: bold;">{fmt(t1)}</div></div><div style="flex: 1; text-align: right;"><div style="font-size: 12px; color: #42a5f5;">利確2</div><div style="font-size: 16px; font-weight: bold;">{fmt(t2)}</div></div></div>', unsafe_allow_html=True)
        fig = go.Figure(); min_x, max_x = min(s, c, b)*0.98, max(t2 if t2>0 else t1, c, b)*1.02
        fig.add_shape(type="line", x0=min_x, y0=0, x1=max_x, y1=0, line=dict(color="#444", width=2))
        fig.add_shape(type="line", x0=b, y0=0, x1=c, y1=0, line=dict(color="rgba(38,166,154,0.6)" if c>=b else "rgba(239,83,80,0.6)", width=10))
        for p_v, p_n, p_c in [(s, "🛡️ 損切", "#ef5350"), (b, "🏁 買値", "#ffca28"), (t1, "🎯 利確1", "#26a69a"), (t2, "🏆 利確2", "#42a5f5")]:
            if p_v > 0: fig.add_trace(go.Scatter(x=[p_v], y=[0], mode="markers", name=p_n, marker=dict(size=12, color=p_c), hovertemplate=f"<b>{p_n}</b>: ¥%{{x:,.1f}}<extra></extra>"))
        fig.add_trace(go.Scatter(x=[c], y=[0], mode="markers", name="🔴 現在地", marker=dict(size=22, symbol="cross-thin", line=dict(width=3, color=col)), hovertemplate=f"<b>🔴 現在地</b>: ¥%{{x:,.1f}}<extra></extra>"))
        fig.update_layout(height=80, showlegend=False, yaxis=dict(showticklabels=False, range=[-1, 1]), xaxis=dict(showgrid=False, range=[min_x, max_x], tickfont=dict(color="#888"), tickformat=",.0f"), margin=dict(l=10, r=10, t=5, b=5), paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)', dragmode=False)
        st.plotly_chart(fig, use_container_width=True, config={'displayModeBar': False})

with tab6:
    st.markdown('<h3 style="font-size: clamp(14px, 4.5vw, 24px); margin-bottom: 1rem;">📁 事後任務報告 (AAR)</h3>', unsafe_allow_html=True)
    AAR_FILE = f"saved_aar_log_{user_id}.csv"
    def g_sc(c):
        api_c = str(c) if len(str(c)) == 5 else str(c) + "0"
        if not master_df.empty:
            m_r = master_df[master_df['Code'] == api_c]
            if not m_r.empty: return "🏢 大型/中型" if any(x in str(m_r.iloc[0].get('Scale', '')) for x in ["Core30", "Large70", "Mid400"]) else "🚀 小型/新興"
        return "不明"
    if os.path.exists(AAR_FILE):
        try:
            aar_df = pd.read_csv(AAR_FILE); aar_df['決済日'] = aar_df['決済日'].astype(str); aar_df['銘柄'] = aar_df['銘柄'].astype(str)
        except: aar_df = pd.DataFrame(columns=["決済日", "銘柄", "規模", "戦術", "買値", "売値", "株数", "損益額(円)", "損益(%)", "規律", "敗因/勝因メモ"])
    else: aar_df = pd.DataFrame(columns=["決済日", "銘柄", "規模", "戦術", "買値", "売値", "株数", "損益額(円)", "損益(%)", "規律", "敗因/勝因メモ"])
    col_a1, col_a2 = st.columns([1, 2.2])
    with col_a1:
        with st.form("aar_form"):
            ca1, ca2 = st.columns(2); a_date = ca1.date_input("決済日"); a_code = ca2.text_input("銘柄(4桁)")
            a_tact = st.selectbox("戦術", ["🌐 待伏", "⚡ 強襲", "⚠️ その他"]); ca3, ca4, ca5 = st.columns(3)
            a_buy, a_sell, a_lot = ca3.number_input("買値"), ca4.number_input("売値"), ca5.number_input("株数", step=100)
            a_rule = st.radio("規律遵守", ["✅ 遵守", "❌ 違反"]); a_memo = st.text_input("メモ")
            if st.form_submit_button("💾 保存"):
                if a_code and a_buy > 0:
                    prof = int((a_sell - a_buy) * a_lot); p_pct = round(((a_sell / a_buy) - 1) * 100, 2)
                    new = pd.DataFrame([{"決済日": a_date.strftime("%Y-%m-%d"), "銘柄": a_code, "規模": g_sc(a_code), "戦術": a_tact, "買値": a_buy, "売値": a_sell, "株数": a_lot, "損益額(円)": prof, "損益(%)": p_pct, "規律": "遵守" if "遵守" in a_rule else "違反", "敗因/勝因メモ": a_memo}])
                    aar_df = pd.concat([new, aar_df], ignore_index=True).to_csv(AAR_FILE, index=False); st.rerun()
    with col_a2:
        if not aar_df.empty:
            m1, m2, m3, m4 = st.columns(4); tot = len(aar_df); wins = len(aar_df[aar_df['損益額(円)']>0])
            m1.metric("回数", f"{tot}回"); m2.metric("勝率", f"{(wins/tot)*100:.1f}%"); m3.metric("損益", f"{int(aar_df['損益額(円)'].sum()):,}円"); m4.metric("規律", f"{(len(aar_df[aar_df['規律']=='遵守'])/tot)*100:.1f}%")
            st.dataframe(aar_df.style.map(lambda v: 'color: #26a69a' if v>0 else 'color: #ef5350', subset=['損益額(円)']), use_container_width=True)
