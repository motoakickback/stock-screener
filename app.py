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

# --- ⚙️ システム全体設定の永続化 ---
SETTINGS_FILE = f"saved_settings_{user_id}.json"

def load_settings():
    defaults = {
        "preset_target": "🚀 中小型株 (50%押し・標準)", "sidebar_tactics": "⚖️ バランス (掟達成率 ＞ 到達度)",
        "push_r": 50.0, "limit_d": 4, "bt_lot": 100, "bt_tp": 10, "bt_sl_i": 8, "bt_sl_c": 8, "bt_sell_d": 10,
        "f1_min": 200, "f1_max": 3000, "f2_m30": 2.0, "f3_drop": -30, "f4_mlong": 3.0,
        "f5_ipo": True, "f6_risk": True, "f7_ex_etf": True, "f8_ex_bio": True,
        "f9_min14": 1.3, "f9_max14": 2.0, "f10_ex_knife": True,
        "tab1_etf_filter": True, "tab2_rsi_limit": 75, "tab2_vol_limit": 15000, 
        "tab2_ipo_filter": True, "tab2_etf_filter": True, "t3_scope_mode": "🌐 【待伏】 押し目・逆張り",
        "bt_mode_sim_v2": "🌐 【待伏】鉄の掟 (押し目狙撃)", 
        # 新しく設定したTab4用の永続化キー
        "sim_tp_val": 10, "sim_sl_val": 8, "sim_limit_d_val": 4, "sim_sell_d_val": 10, "sim_push_r_val": 50.0,
        "sim_pass_req_val": 7, "sim_rsi_lim_ambush_val": 45, "sim_rsi_lim_assault_val": 70, "sim_time_risk_val": 5
    }
    if os.path.exists(SETTINGS_FILE):
        try:
            with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
                defaults.update(json.load(f))
        except: pass
    for k, v in defaults.items():
        if k not in st.session_state: st.session_state[k] = v

def save_settings():
    keys = ["preset_target", "sidebar_tactics", "push_r", "limit_d", "bt_lot", "bt_tp", "bt_sl_i", "bt_sl_c", "bt_sell_d", 
            "f1_min", "f1_max", "f2_m30", "f3_drop", "f4_mlong", "f5_ipo", "f6_risk", "f7_ex_etf", "f8_ex_bio", 
            "f9_min14", "f9_max14", "f10_ex_knife", "tab1_etf_filter", "tab2_rsi_limit", "tab2_vol_limit", 
            "tab2_ipo_filter", "tab2_etf_filter", "t3_scope_mode", "bt_mode_sim_v2", 
            "sim_tp_val", "sim_sl_val", "sim_limit_d_val", "sim_sell_d_val", "sim_push_r_val", 
            "sim_pass_req_val", "sim_rsi_lim_ambush_val", "sim_rsi_lim_assault_val", "sim_time_risk_val"]
    current = {k: st.session_state[k] for k in keys if k in st.session_state}
    
    # 🚨 修正：既存の設定をロードしてマージする（非表示要素の消失を防ぐ防衛網）
    if os.path.exists(SETTINGS_FILE):
        try:
            with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
                existing = json.load(f)
                existing.update(current)
                current = existing
        except: pass
        
    with open(SETTINGS_FILE, "w", encoding="utf-8") as f: json.dump(current, f, ensure_ascii=False)

load_settings()

def apply_market_preset():
    preset = st.session_state.get("preset_target", "🚀 中小型株 (50%押し・標準)")
    tactics = st.session_state.get("sidebar_tactics", "⚖️ バランス (掟達成率 ＞ 到達度)")
    if "大型株" in preset: st.session_state.push_r = 25.0 if "バランス" in tactics else 45.0
    elif "61.8%" in preset: st.session_state.push_r = 61.8
    else: st.session_state.push_r = 50.0
    st.session_state.sim_push_r = st.session_state.push_r
    save_settings()

# --- 🌤️ マクロ気象レーダー（日経平均）モジュール ---
# 【修正】不要なヘッダー偽装を排除し、標準通信のままTTL（キャッシュ保持）のみ60秒へ短縮
@st.cache_data(ttl=60, show_spinner=False)
def get_macro_weather():
    try:
        import yfinance as yf
        import pandas as pd
        
        # セッション偽装を行わず、標準のまま呼び出す
        tk_ni = yf.Ticker("^N225")
        hist_ni = tk_ni.history(period="3mo")
        
        if len(hist_ni) >= 2:
            lc_ni = hist_ni['Close'].iloc[-1]; prev_ni = hist_ni['Close'].iloc[-2]
            diff_ni = lc_ni - prev_ni; pct_ni = (diff_ni / prev_ni) * 100
            df_ni = hist_ni.reset_index()
            if 'Date' in df_ni.columns:
                df_ni['Date'] = pd.to_datetime(df_ni['Date'], utc=True).dt.tz_convert('Asia/Tokyo').dt.tz_localize(None)
            return {"nikkei": {"price": lc_ni, "diff": diff_ni, "pct": pct_ni, "df": df_ni}}
    except: 
        return None

def render_macro_board():
    data = get_macro_weather()
    if data and "nikkei" in data:
        ni = data["nikkei"]; df = ni["df"]; color = "#ef5350" if ni['diff'] >= 0 else "#26a69a"; sign = "+" if ni['diff'] >= 0 else ""
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
            fig.add_trace(go.Scatter(x=df['Date'], y=df['Close'], mode='lines', line=dict(color='#FFD700', width=2)))
            fig.add_trace(go.Scatter(x=df['Date'], y=df['MA25'], mode='lines', line=dict(color='rgba(255, 255, 255, 0.4)', width=1, dash='dot')))
            fig.update_layout(height=160, margin=dict(l=10, r=20, t=10, b=10), xaxis_rangeslider_visible=False, paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)', showlegend=False, yaxis=dict(side="right", tickformat=",.0f"))
            st.plotly_chart(fig, use_container_width=True, config={'displayModeBar': False})
        st.markdown("<div style='margin-bottom: 1.5rem;'></div>", unsafe_allow_html=True)
    else:
        st.warning("⚠️ 外部気象レーダー応答なし。")
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
    df.ffill(inplace=True)
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
        if macd_t == "下落継続" or rsi >= 75: return "圏外🚫", "#d32f2f", 0, macd_t
        if gc_days == 1:
            if rsi <= 50: return "S🔥", "#2e7d32", 5, "GC直後(1日目)"
            else: return "A⚡", "#ed6c02", 4, "GC直後(1日目)"
        elif gc_days == 2:
            if rsi <= 55: return "A⚡", "#ed6c02", 4, "GC継続(2日目)"
            else: return "B📈", "#0288d1", 3, "GC継続(2日目)"
        elif gc_days >= 3:
            return "B📈", "#0288d1", 3, f"GC継続({gc_days}日目)"
        else: return "C👁️", "#616161", 1, macd_t
    else:
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
    """ 強襲(順張り)専用のスコアリングエンジン """
    if gc_days <= 0 or df_chart is None or df_chart.empty:
        return "圏外 💀", "#424242", 0, ""
        
    latest = df_chart.iloc[-1]
    ma5 = latest.get('MA5', 0)
    ma25 = latest.get('MA25', 0)
    ma75 = latest.get('MA75', 0)
    
    # 出来高の安全な取得
    v_col = next((col for col in df_chart.columns if col in ['Volume', 'AdjVo', 'Vo', 'AdjustmentVolume']), None)
    vol_latest = latest[v_col] if v_col else 0
    vol_avg = df_chart[v_col].tail(5).mean() if v_col else 0

    score = 50  # GC発動の基礎点

    # ⚖️ 【中間加点】Tab2/Tab3共通の基礎評価
    if ma25 > 0:
        if lc >= ma25 * 0.95: score += 10  # 沼からの脱出初動（+10点）
        if lc >= ma25: score += 10         # 25日線上抜け（+10点）
    if vol_avg > 0 and vol_latest > vol_avg * 1.5: score += 10 # 出来高の爆発（+10点）
    if 50 <= rsi_v <= 70: score += 10      # 強い上昇モメンタム（+10点）

    # 💀 【超厳格減点】Tab3（精密スコープ）専用の処刑ロジック
    if is_strict:
        # パーフェクトオーダーの崩壊は大幅減点（騙しの可能性大）
        if not (lc > ma5 > ma25 > ma75): score -= 40
        # 出来高が伴っていないGCはフェイクとみなす
        if vol_avg > 0 and vol_latest <= vol_avg * 1.2: score -= 20
        # RSI過熱(75超)は高値掴みのリスク大
        if rsi_v > 75: score -= 20

    # 🎯 最終ランク判定
    if score >= 80: rank = "S"; bg = "#d32f2f"
    elif score >= 60: rank = "A"; bg = "#f57c00"
    elif score >= 40: rank = "B"; bg = "#fbc02d"
    else: rank = "C 💀"; bg = "#424242"
    
    return rank, bg, score, "GC発動中"

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
st.sidebar.header("🎯 対象市場 (一括換装)")
st.sidebar.radio("プリセット選択", ["🚀 中小型株 (50%押し・標準)", "⚓ 中小型株 (61.8%押し・深海)", "🏢 大型株 (25%押し・トレンド)"], key="preset_target", on_change=apply_market_preset)
market_filter_mode = "大型" if "大型株" in st.session_state.preset_target else "中小型"

st.sidebar.radio("🕹️ 戦術モード切替", ["⚖️ バランス (掟達成率 ＞ 到達度)", "⚔️ 攻め重視 (三川シグナル優先)", "🛡️ 守り重視 (鉄壁シグナル優先)"], key="sidebar_tactics", on_change=apply_market_preset)

st.sidebar.header("🔍 ピックアップルール")
c_f1_1, c_f1_2 = st.sidebar.columns(2)
f1_min = c_f1_1.number_input("① 下限(円)", step=100, key="f1_min", on_change=save_settings)
f1_max = c_f1_2.number_input("① 上限(円)", step=100, key="f1_max", on_change=save_settings) 
f2_m30 = st.sidebar.number_input("② 1ヶ月暴騰上限(倍)", step=0.1, key="f2_m30", on_change=save_settings)
f3_drop = st.sidebar.number_input("③ 半年〜1年下落除外(%)", step=5, key="f3_drop", on_change=save_settings)
f4_mlong = st.sidebar.number_input("④ 上げ切り除外(倍)", step=0.5, key="f4_mlong", on_change=save_settings)
f5_ipo = st.sidebar.checkbox("⑤ IPO除外(英字コード等)", key="f5_ipo", on_change=save_settings)
f6_risk = st.sidebar.checkbox("⑥ 疑義注記銘柄除外", key="f6_risk", on_change=save_settings)
f7_ex_etf = st.sidebar.checkbox("⑦ ETF・REIT等を除外", key="f7_ex_etf", on_change=save_settings)
f8_ex_bio = st.sidebar.checkbox("⑧ 医薬品(バイオ)を除外", key="f8_ex_bio", on_change=save_settings)
c_f9_1, c_f9_2 = st.sidebar.columns(2)
f9_min14 = c_f9_1.number_input("⑨ 下限(倍)", step=0.1, key="f9_min14", on_change=save_settings)
f9_max14 = c_f9_2.number_input("⑨ 上限(倍)", step=0.1, key="f9_max14", on_change=save_settings)
f10_ex_knife = st.sidebar.checkbox("⑩ 落ちるナイフ除外(暴落/連続下落)", key="f10_ex_knife", on_change=save_settings)

st.sidebar.header("🎯 買いルール")
push_r = st.sidebar.number_input("① 押し目(%)", step=0.1, format="%.1f", key="push_r", on_change=save_settings)
limit_d = st.sidebar.number_input("② 買い期限(日)", step=1, key="limit_d", on_change=save_settings)
st.sidebar.number_input("③ 仮想Lot(株数)", step=100, key="bt_lot", on_change=save_settings)

st.sidebar.header("🛡️ 売りルール（鉄の掟）")
st.sidebar.number_input("① 利確目標 (+%)", step=1, key="bt_tp", on_change=save_settings)
st.sidebar.number_input("② 損切/ザラ場 (-%)", step=1, key="bt_sl_i", on_change=save_settings)
st.sidebar.number_input("③ 損切/終値 (-%)", step=1, key="bt_sl_c", on_change=save_settings)
st.sidebar.number_input("④ 強制撤退/売り期限 (日)", step=1, key="bt_sell_d", on_change=save_settings)

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
    st.sidebar.success("全記憶を強制パージした。最新データを再取得する。")
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
    exclude_etf_flag_t1 = st.sidebar.checkbox("ETF・REITを除外 (待伏)", key="tab1_etf_filter", on_change=save_settings)

    if run_scan_t1:
        st.toast("🟢 待伏トリガーを確認。索敵開始！", icon="🎯")
        with st.spinner("全銘柄からサイドバー条件（全フィルター同期）に合致するターゲットを索敵中..."):
            raw = get_hist_data_cached()
            if not raw:
                st.error("データの取得に失敗した。")
                st.session_state.tab1_scan_results = None
            else:
                df = clean_df(pd.DataFrame(raw)).dropna(subset=['AdjC', 'AdjH', 'AdjL']).sort_values(['Code', 'Date'])
                v_col = next((col for col in df.columns if col in ['Volume', 'AdjVo', 'Vo', 'AdjustmentVolume']), None)
                if v_col:
                    df[v_col] = pd.to_numeric(df[v_col], errors='coerce').fillna(0)
                    avg_vols = df.groupby('Code').tail(5).groupby('Code')[v_col].mean()
                else: avg_vols = pd.Series(0, index=df['Code'].unique())

                # 🚨 同期パッチ：① 価格上下限フィルターの適用
                f1_min = float(st.session_state.f1_min)
                f1_max = float(st.session_state.f1_max)
                f5_ipo = st.session_state.f5_ipo
                f10_ex_knife = st.session_state.f10_ex_knife

                latest_date = df['Date'].max()
                latest_df = df[df['Date'] == latest_date]
                valid_price_codes = latest_df[(latest_df['AdjC'] >= f1_min) & (latest_df['AdjC'] <= f1_max)]['Code'].unique()
                valid_vol_codes = avg_vols[avg_vols >= 10000].index
                valid_codes = set(valid_price_codes).intersection(set(valid_vol_codes))
                df = df[df['Code'].isin(valid_codes)]

                # 🚨 同期パッチ：⑤ IPO（上場1年未満）除外フィルターのスマート適用
                if f5_ipo and not df.empty:
                    # APIが取得した最も古い日付（約1年前のピンポイント日）を基準とする
                    oldest_global_date = df['Date'].min()
                    # 各銘柄が持つ最古のデータ日付を算出
                    stock_min_dates = df.groupby('Code')['Date'].min()
                    # 基準日から +15日 以内にデータが存在していれば「1年前から上場している」と判定
                    threshold_date = oldest_global_date + pd.Timedelta(days=15)
                    valid_seasoned_codes = stock_min_dates[stock_min_dates <= threshold_date].index
                    df = df[df['Code'].isin(valid_seasoned_codes)]

                if exclude_etf_flag_t1 and not master_df.empty:
                    invalid_mask = master_df['Market'].astype(str).str.contains('ETF|REIT', case=False, na=False) | master_df['Sector'].astype(str).str.contains('ETF|REIT|投信', case=False, na=False)
                    valid_codes = master_df[~invalid_mask]['Code'].unique()
                    df = df[df['Code'].isin(valid_codes)]

                if not master_df.empty:
                    if "大型株" in st.session_state.preset_target: m_mask = master_df['Market'].astype(str).str.contains('プライム|一部', na=False)
                    else: m_mask = master_df['Market'].astype(str).str.contains('スタンダード|グロース|新興|マザーズ|JASDAQ|二部', na=False)
                    df = df[df['Code'].isin(master_df[m_mask]['Code'].unique())]

                if st.session_state.f8_ex_bio and not master_df.empty:
                    df = df[df['Code'].isin(master_df[~master_df['Sector'].astype(str).str.contains('医薬品', case=False, na=False)]['Code'].unique())]

                if gigi_input:
                    target_blacklist = re.findall(r'\d{4}', str(gigi_input))
                    if target_blacklist:
                        df['Temp_Code'] = df['Code'].astype(str).str.extract(r'(\d{4})')[0]
                        df = df[~df['Temp_Code'].isin(target_blacklist)].drop(columns=['Temp_Code'])

                master_dict = master_df.set_index('Code')[['CompanyName', 'Market', 'Sector', 'Scale']].to_dict('index') if not master_df.empty else {}
                
                push_ratio = st.session_state.push_r / 100.0
                min14 = float(st.session_state.f9_min14)
                max14 = float(st.session_state.f9_max14)
                limit_d = int(st.session_state.limit_d)

                results = []
                for code, group in df.groupby('Code'):
                    if len(group) < 15: continue 
                    avg_vol = int(avg_vols.get(code, 0))
                    if avg_vol < 10000: continue
                    
                    # 🚨 同期パッチ：⑩ 落ちるナイフ除外（直近3日間で15%以上の致命的暴落をパージ）
                    if f10_ex_knife:
                        recent_4d = group['AdjC'].values[-4:]
                        if len(recent_4d) == 4 and (recent_4d[-1] / recent_4d[0] < 0.85):
                            continue
                    
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
                    # ⑨ 波高フィルター
                    if not (min14 <= high_4d_val / low_10d_val <= max14): continue
                    
                    wave_len = high_4d_val - low_10d_val
                    if wave_len <= 0: continue
                    target_buy = high_4d_val - (wave_len * push_ratio)
                    reach_rate = (target_buy / lc) * 100

                    rsi, macd_h, macd_h_prev, _ = get_fast_indicators(adjc_vals)
                    
                    # --- 🎖️ 掟スコアの計算 ---
                    df_14 = group.tail(15).iloc[:-1]
                    df_30 = group.tail(31).iloc[:-1]
                    h14_real = df_14['AdjH'].max()
                    l14_real = df_14['AdjL'].min()
                    
                    score = 4 # ベース点
                    if h14_real > 0 and l14_real > 0:
                        r14 = h14_real / l14_real
                        idxmax = df_14['AdjH'].idxmax()
                        d_high = len(df_14[df_14['Date'] > df_14.loc[idxmax, 'Date']]) if pd.notna(idxmax) else 0
                        is_dt = check_double_top(df_30)
                        is_hs = check_head_shoulders(df_30)

                        if 1.3 <= r14 <= 2.0: score += 1
                        if d_high <= limit_d: score += 1
                        if not is_dt: score += 1
                        if not is_hs: score += 1
                        if target_buy * 0.85 <= lc <= target_buy * 1.35: score += 1
                    # ----------------------------------------------------

                    m_info = master_dict.get(code, {})
                    c_name = m_info.get('CompanyName', f"銘柄 {code[:4]}")
                    c_market = m_info.get('Market', '不明'); c_sector = m_info.get('Sector', '不明'); c_scale = m_info.get('Scale', '不明')
                    rank, bg, t_score, _ = get_triage_info(macd_h, macd_h_prev, rsi, lc, target_buy, mode="待伏")

                    results.append({'Code': code, 'Name': c_name, 'Sector': c_sector, 'Market': c_market, 'Scale': c_scale, 'lc': lc, 'RSI': rsi, 'avg_vol': avg_vol, 'high_4d': high_4d_val, 'low_14d': low_10d_val, 'target_buy': target_buy, 'reach_rate': reach_rate, 'triage_rank': rank, 'triage_bg': bg, 't_score': t_score, 'score': score})
                        
                if not results:
                    st.warning("現在、掟を満たすターゲットは存在しない。")
                    st.session_state.tab1_scan_results = []
                else:
                    st.session_state.tab1_scan_results = sorted(results, key=lambda x: (x['t_score'], x['score']), reverse=True)[:30]
                import gc; gc.collect()

    if st.session_state.tab1_scan_results:
        light_results = st.session_state.tab1_scan_results
        st.success(f"🎯 待伏ロックオン: {len(light_results)} 銘柄を確認。")
        sab_codes = " ".join([str(r.get('Code', ''))[:4] for r in light_results if str(r.get('triage_rank', '')).startswith(('S', 'A', 'B'))])
        other_codes = " ".join([str(r.get('Code', ''))[:4] for r in light_results if not str(r.get('triage_rank', '')).startswith(('S', 'A', 'B'))])
        
        st.info("📋 以下のコードをコピーして、照準（TAB3）にペースト可能だ。")
        if sab_codes:
            st.markdown("**🎯 優先度 S・A・B (主力標的)**")
            st.code(sab_codes, language="text")
        if other_codes:
            with st.expander("👀 優先度 C・圏外 (監視対象)"):
                st.code(other_codes, language="text")
        
        for r in light_results:
            st.divider()
            c = str(r.get('Code', '0000')); n = r.get('Name', f"銘柄 {c[:4]}")
            m_lower = str(r.get('Market', '不明')).lower()
            if 'プライム' in m_lower or '一部' in m_lower: badge_html = '<span style="background-color: #1a237e; color: #ffffff; padding: 0.2rem 0.6rem; border-radius: 4px; font-size: 11px; font-weight: bold;">🏢 プライム/大型</span>'
            elif 'グロース' in m_lower or 'マザーズ' in m_lower: badge_html = '<span style="background-color: #1b5e20; color: #ffffff; padding: 0.2rem 0.6rem; border-radius: 4px; font-size: 11px; font-weight: bold;">🚀 グロース/新興</span>'
            else: badge_html = f'<span style="background-color: #455a64; color: #ffffff; padding: 0.2rem 0.6rem; border-radius: 4px; font-size: 11px; font-weight: bold;">{r.get("Market")}</span>'
            
            triage_badge = f'<span style="background-color: {r.get("triage_bg")}; color: #ffffff; padding: 0.2rem 0.6rem; border-radius: 4px; font-size: 13px; display: inline-block; font-weight: bold; margin-left: 0.5rem;">🎯 優先度: {r.get("triage_rank")}</span>'
            
            score_val = r.get("score", 0)
            score_color = "#2e7d32" if score_val >= 7 else "#ff5722"
            score_bg = "rgba(46, 125, 50, 0.15)" if score_val >= 7 else "rgba(255, 87, 34, 0.15)"
            score_badge = f'<span style="background-color: {score_bg}; border: 1px solid {score_color}; color: {score_color}; padding: 0.2rem 0.6rem; border-radius: 4px; font-size: 12px; font-weight: bold; margin-left: 0.5rem;">🎖️ 掟スコア: {score_val}/9</span>'
            
            swing_pct = ((r.get('high_4d', 0) - r.get('low_14d', 0)) / r.get('low_14d', 1)) * 100
            volatility_badge = f'<span style="background-color: #ff9800; color: #ffffff; padding: 0.2rem 0.6rem; border-radius: 4px; font-size: 11px; font-weight: bold; margin-left: 0.5rem; border: 1px solid #e65100;">⚡ 高ボラ ({swing_pct:.1f}%)</span>' if swing_pct >= (40.0 if ('プライム' in m_lower or '一部' in m_lower) else 60.0) else ""

            st.markdown(f"""
                <div style="margin-bottom: 0.8rem;">
                    <h3 style="font-size: clamp(18px, 5vw, 28px); font-weight: bold; margin: 0 0 0.3rem 0;">({c[:4]}) {n}</h3>
                    <div style="display: flex; flex-wrap: wrap; gap: 6px; align-items: center;">
                        {badge_html}{triage_badge}{score_badge}{volatility_badge}
                        <span style="background-color: rgba(38, 166, 154, 0.15); border: 1px solid #26a69a; color: #26a69a; padding: 0.1rem 0.5rem; border-radius: 4px; font-size: 12px; margin-left: 4px;">RSI: {r.get("RSI", 50):.1f}%</span>
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
    rsi_limit = col_t2_1.number_input("RSI上限（過熱感の足切り）", step=5, key="tab2_rsi_limit", on_change=save_settings)
    vol_limit = col_t2_2.number_input("最低出来高（5日平均）", step=5000, key="tab2_vol_limit", on_change=save_settings)
    
    run_scan_t2 = st.button("🚀 全軍GC初動スキャン開始", key="btn_assault_scan")
    exclude_ipo_flag = st.sidebar.checkbox("IPO銘柄を除外 (強襲)", key="tab2_ipo_filter", on_change=save_settings)
    exclude_etf_flag_t2 = st.sidebar.checkbox("ETF・REITを除外 (強襲)", key="tab2_etf_filter", on_change=save_settings)

    if run_scan_t2:
        st.toast("🟢 強襲トリガーを確認。索敵開始！", icon="🚀")
        with st.spinner("全銘柄の波形からGC初動候補を抽出中..."):
            raw = get_hist_data_cached()
            if not raw:
                st.error("データの取得に失敗した。")
            else:
                df = clean_df(pd.DataFrame(raw)).dropna(subset=['AdjC', 'AdjH', 'AdjL']).sort_values(['Code', 'Date'])
                v_col = next((col for col in df.columns if col in ['Volume', 'AdjVo', 'Vo', 'AdjustmentVolume']), None)
                if v_col:
                    df[v_col] = pd.to_numeric(df[v_col], errors='coerce').fillna(0)
                    avg_vols = df.groupby('Code').tail(5).groupby('Code')[v_col].mean()
                else: avg_vols = pd.Series(0, index=df['Code'].unique())

                # 🚨 同期パッチ：① 価格上下限フィルターの適用
                f1_min = float(st.session_state.f1_min)
                f1_max = float(st.session_state.f1_max)
                f5_ipo = st.session_state.f5_ipo
                f8_ex_bio = st.session_state.f8_ex_bio

                latest_date = df['Date'].max()
                latest_df = df[df['Date'] == latest_date]
                valid_price_codes = latest_df[(latest_df['AdjC'] >= f1_min) & (latest_df['AdjC'] <= f1_max)]['Code'].unique()
                valid_vol_codes = avg_vols[avg_vols >= vol_limit].index
                valid_codes = set(valid_price_codes).intersection(set(valid_vol_codes))
                df = df[df['Code'].isin(valid_codes)]

                # 🚨 同期パッチ：⑤ IPO（上場1年未満）除外フィルター
                if f5_ipo and not df.empty:
                    oldest_global_date = df['Date'].min()
                    stock_min_dates = df.groupby('Code')['Date'].min()
                    threshold_date = oldest_global_date + pd.Timedelta(days=15)
                    valid_seasoned_codes = stock_min_dates[stock_min_dates <= threshold_date].index
                    df = df[df['Code'].isin(valid_seasoned_codes)]

                # 🚨 同期パッチ：⑦ ETF・REIT等を除外
                if exclude_etf_flag_t2 and not master_df.empty:
                    invalid_mask = master_df['Market'].astype(str).str.contains('ETF|REIT', case=False, na=False) | master_df['Sector'].astype(str).str.contains('ETF|REIT|投信', case=False, na=False)
                    df = df[df['Code'].isin(master_df[~invalid_mask]['Code'].unique())]

                # 🚨 同期パッチ：⑧ 医薬品(バイオ)を除外
                if f8_ex_bio and not master_df.empty:
                    df = df[df['Code'].isin(master_df[~master_df['Sector'].astype(str).str.contains('医薬品', case=False, na=False)]['Code'].unique())]

                # 🚨 同期パッチ：対象市場（大型/中小型）の適用
                if not master_df.empty:
                    if "大型株" in st.session_state.preset_target: m_mask = master_df['Market'].astype(str).str.contains('プライム|一部', na=False)
                    else: m_mask = master_df['Market'].astype(str).str.contains('スタンダード|グロース|新興|マザーズ|JASDAQ|二部', na=False)
                    df = df[df['Code'].isin(master_df[m_mask]['Code'].unique())]

                # 🚨 同期パッチ：⑥ 疑義注記銘柄除外（ブラックリスト適用）
                if gigi_input:
                    target_blacklist = re.findall(r'\d{4}', str(gigi_input))
                    if target_blacklist:
                        df['Temp_Code'] = df['Code'].astype(str).str.extract(r'(\d{4})')[0]
                        df = df[~df['Temp_Code'].isin(target_blacklist)].drop(columns=['Temp_Code'])

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
                    
                    # 🚨 修正：強襲ロジック用 ATRおよび14日高値の算出
                    if len(adjh_vals) >= 14:
                        h14 = adjh_vals[-14:].max()
                        # 簡易ATR(14d)の算出
                        h_v = adjh_vals[-14:]; l_v = adjl_vals[-14:]; c_prev_v = adjc_vals[-15:-1]
                        tr = np.maximum(h_v - l_v, np.maximum(abs(h_v - c_prev_v), abs(l_v - c_prev_v)))
                        atr_val = tr.mean()
                    else:
                        h14 = lc; atr_val = lc * 0.03 # 予備計算

                    latest_ma25 = sum(adjc_vals[-25:]) / 25 if len(adjc_vals) >= 25 else 0
                    if latest_ma25 > 0 and lc < (latest_ma25 * 0.95): continue

                    dummy_df = pd.DataFrame([{'MA5': 0, 'MA25': latest_ma25, 'MA75': 0, 'Volume': 0}])
                    t_rank, t_color, t_score, t_macd = get_assault_triage_info(gc_days, lc, rsi, dummy_df, is_strict=False)
                        
                    m_info = master_dict.get(code, {})
                    c_name = m_info.get('CompanyName', f"銘柄 {code[:4]}")
                    c_market = m_info.get('Market', '不明'); c_sector = m_info.get('Sector', '不明')
                    scale_val = str(m_info.get('Scale', ''))
                    c_scale = "🏢 大型/中型" if any(x in scale_val for x in ["Core30", "Large70", "Mid400"]) else "🚀 小型/新興"

                    results.append({'Code': code, 'Name': c_name, 'Sector': c_sector, 'Market': c_market, 'Scale': c_scale, 'lc': lc, 'RSI': rsi, 'avg_vol': avg_vol, 'h14': h14, 'atr': atr_val, 'T_Rank': t_rank, 'T_Color': t_color, 'T_Score': t_score, 'GC_Days': gc_days})
                        
                if not results:
                    st.warning("現在、GC初動条件を満たすターゲットは存在しない。")
                    st.session_state.tab2_scan_results = []
                else:
                    st.session_state.tab2_scan_results = sorted(results, key=lambda x: (-x['T_Score'], x['GC_Days'], x['RSI']))[:30]
                import gc; gc.collect()

    if st.session_state.tab2_scan_results:
        light_results = st.session_state.tab2_scan_results
        st.success(f"⚡ 強襲ロックオン: GC初動(3日以内) 上位 {len(light_results)} 銘柄を確認。")
        sab_codes = " ".join([str(r.get('Code', ''))[:4] for r in light_results if str(r.get('T_Rank', '')).startswith(('S', 'A', 'B'))])
        
        st.info("📋 以下のコードをコピーして、照準（TAB3）にペースト可能だ。")
        if sab_codes:
            st.markdown("**🎯 優先度 S・A・B (主力標的)**")
            st.code(sab_codes, language="text")
        
        for r in light_results:
            st.divider()
            lc_val = r.get('lc', 0); h14_val = r.get('h14', 0); atr_v = r.get('atr', 0)
            
            # 🚨 動的ロジック適用：トリガーと防衛線
            t_price = max(h14_val, lc_val + (atr_v * 0.5))
            d_price = t_price - atr_v

            triage_badge = f'<span style="background-color: {r.get("T_Color", "#616161")}; color: #ffffff; padding: 0.2rem 0.6rem; border-radius: 4px; font-size: 13px; display: inline-block; font-weight: bold; margin-left: 0.5rem;">🎯 優先度: {r.get("T_Rank")}</span>'
            
            st.markdown(f"""
                <div style="margin-bottom: 0.8rem;">
                    <h3 style="font-size: 24px; font-weight: bold; margin: 0 0 0.3rem 0;">({str(r['Code'])[:4]}) {r['Name']}</h3>
                    <div style="display: flex; gap: 4px; align-items: center;">
                        {triage_badge}
                        <span style="background-color: rgba(237, 108, 2, 0.15); border: 1px solid #ed6c02; color: #ed6c02; padding: 0.1rem 0.5rem; border-radius: 4px; font-size: 12px;">GC後 {r.get('GC_Days')}日目</span>
                    </div>
                </div>
            """, unsafe_allow_html=True)
            
            m_cols = st.columns([1, 1, 1, 1.2, 1.5])
            m_cols[0].metric("最新終値", f"{int(lc_val):,}円")
            m_cols[1].metric("RSI", f"{r.get('RSI', 50):.1f}%")
            m_cols[2].metric("ATR(14d)", f"{int(atr_v):,}円")
            
            html_sl = f"""<div style="background: rgba(239, 83, 80, 0.05); padding: 0.5rem; border-radius: 8px; border: 1px solid rgba(239, 83, 80, 0.3); text-align: center;">
                <div style="font-size: 13px; color: rgba(250, 250, 250, 0.6); margin-bottom: 2px;">🛡️ 動的防衛線 (-1.0 ATR)</div>
                <div style="font-size: 1.6rem; font-weight: bold; color: #ef5350;">{int(d_price):,}<span style="font-size: 14px; margin-left:2px;">円</span></div></div>"""
            m_cols[3].markdown(html_sl, unsafe_allow_html=True)

            html_buy_assault = f"""<div style="background: rgba(255, 215, 0, 0.05); padding: 0.5rem; border-radius: 8px; border: 1px solid rgba(255, 215, 0, 0.2); text-align: center;">
                <div style="font-size: 13px; color: rgba(250, 250, 250, 0.6); margin-bottom: 2px;">🎯 強襲トリガー (14d高値基準)</div>
                <div style="font-size: 1.6rem; font-weight: bold; color: #FFD700;">{int(t_price):,}<span style="font-size: 14px; margin-left:2px;">円</span></div></div>"""
            m_cols[4].markdown(html_buy_assault, unsafe_allow_html=True)

with tab3:
    st.markdown('<h3 style="font-size: clamp(14px, 4.5vw, 24px); margin-bottom: 1rem;">🎯 【照準】精密スコープ（戦術別・独立索敵）</h3>', unsafe_allow_html=True)
    
    T3_AM_WATCH_FILE = f"saved_t3_am_watch_{user_id}.txt"
    T3_AM_DAILY_FILE = f"saved_t3_am_daily_{user_id}.txt"
    T3_AS_WATCH_FILE = f"saved_t3_as_watch_{user_id}.txt"
    T3_AS_DAILY_FILE = f"saved_t3_as_daily_{user_id}.txt"

    def load_t3_text(file_path):
        if os.path.exists(file_path):
            with open(file_path, "r", encoding="utf-8") as f: return f.read()
        return ""

    if "t3_am_watch" not in st.session_state: st.session_state.t3_am_watch = load_t3_text(T3_AM_WATCH_FILE)
    if "t3_am_daily" not in st.session_state: st.session_state.t3_am_daily = load_t3_text(T3_AM_DAILY_FILE)
    if "t3_as_watch" not in st.session_state: st.session_state.t3_as_watch = load_t3_text(T3_AS_WATCH_FILE)
    if "t3_as_daily" not in st.session_state: st.session_state.t3_as_daily = load_t3_text(T3_AS_DAILY_FILE)

    col_s1, col_s2 = st.columns([1.2, 1.8])
    with col_s1:
        scope_mode = st.radio("🎯 解析モードを選択", ["🌐 【待伏】 押し目・逆張り", "⚡ 【強襲】 トレンド・順張り"], key="t3_scope_mode", on_change=save_settings)
        is_ambush = "待伏" in scope_mode
        st.markdown("---")
        if is_ambush:
            watch_in = st.text_area("🌐 【待伏】主力監視部隊", value=st.session_state.t3_am_watch, height=120)
            daily_in = st.text_area("🌐 【待伏】本日新規部隊", value=st.session_state.t3_am_daily, height=120)
        else:
            watch_in = st.text_area("⚡ 【強襲】主力監視部隊", value=st.session_state.t3_as_watch, height=120)
            daily_in = st.text_area("⚡ 【強襲】本日新規部隊", value=st.session_state.t3_as_daily, height=120)
        run_scope = st.button("🔫 表示中の部隊を精密スキャン", use_container_width=True, type="primary")
        
    with col_s2:
        st.markdown("#### 🔍 索敵ステータス")
        if is_ambush: st.info("・【待伏専用】半値押し・黄金比での迎撃判定")
        else: st.warning("・【強襲専用】ATR/14日高値ベースの動的ブレイクアウト判定")

    if run_scope:
        if is_ambush:
            for f, d in [(T3_AM_WATCH_FILE, watch_in), (T3_AM_DAILY_FILE, daily_in)]:
                with open(f, "w", encoding="utf-8") as file: file.write(d)
            st.session_state.t3_am_watch, st.session_state.t3_am_daily = watch_in, daily_in
        else:
            for f, d in [(T3_AS_WATCH_FILE, watch_in), (T3_AS_DAILY_FILE, daily_in)]:
                with open(f, "w", encoding="utf-8") as file: file.write(d)
            st.session_state.t3_as_watch, st.session_state.t3_as_daily = watch_in, daily_in

        all_text = watch_in + " " + daily_in
        t_codes = list(dict.fromkeys([c.upper() for c in re.findall(r'(?<![a-zA-Z0-9])[a-zA-Z0-9]{4}(?![a-zA-Z0-9])', all_text)]))
        
        if not t_codes: st.warning("コードが確認できません。")
        else:
            with st.spinner(f"精密計算中..."):
                scope_results = []
                for c in t_codes:
                    api_code = c if len(c) == 5 else c + "0"
                    raw_s = get_single_data(api_code, 1)
                    if not raw_s: continue
                    df_s = clean_df(pd.DataFrame(raw_s.get("bars", [])))
                    if len(df_s) < 30: continue
                        
                    df_chart = calc_technicals(df_s.copy())
                    df_14 = df_s.tail(15).iloc[:-1]
                    latest = df_chart.iloc[-1]; prev = df_chart.iloc[-2]
                    lc = latest['AdjC']; h14 = df_14['AdjH'].max(); l14 = df_14['AdjL'].min()
                    ur = h14 - l14
                    
                    is_dt = check_double_top(df_14); is_hs = check_head_shoulders(df_14); is_db = check_double_bottom(df_14)
                    rsi_v = latest.get('RSI', 50); atr_val = int(latest.get('ATR', 0))
                    
                    bt_val = 0; reach_val = 0; sl_val = 0; tp_val = 0; gc_days = 0; is_bt_broken = False; is_trend_broken = False
                    
                    if is_ambush:
                        bt_primary = h14 - (ur * (st.session_state.push_r / 100.0))
                        shift_ratio = 0.618 if st.session_state.push_r >= 40 else (st.session_state.push_r / 100.0 + 0.15)
                        bt_secondary = h14 - (ur * shift_ratio)
                        is_bt_broken = lc < bt_primary
                        bt_val = int(bt_secondary if is_bt_broken else bt_primary)
                        is_trend_broken = lc < ((h14 - (ur * 0.618)) * 0.98)
                        rank, bg, score, macd_t = get_triage_info(latest.get('MACD_Hist', 0), prev.get('MACD_Hist', 0), rsi_v, lc, bt_val, mode="待伏")
                        reach_val = ((h14 - lc) / (h14 - bt_val) * 100) if (h14 - bt_val) > 0 else 0
                    else:
                        # 🚨 修正：強襲モードの動的パラメーター算出
                        bt_val = int(max(h14, lc + (atr_val * 0.5))) # トリガー
                        tp_val = int(lc * 1.10)
                        hist_vals = df_chart['MACD_Hist'].tail(5).values
                        if hist_vals[-2] < 0 and hist_vals[-1] >= 0: gc_days = 1
                        elif hist_vals[-3] < 0 and hist_vals[-2] >= 0 and hist_vals[-1] >= 0: gc_days = 2
                        elif hist_vals[-4] < 0 and hist_vals[-3] >= 0 and hist_vals[-2] >= 0 and hist_vals[-1] >= 0: gc_days = 3
                        rank, bg, score, macd_t = get_assault_triage_info(gc_days, lc, rsi_v, df_chart, is_strict=True)
                        reach_val = 100 - rsi_v

                    scope_results.append({
                        'code': c, 'name': df_chart.iloc[0].get('Name', f"銘柄 {c[:4]}"), 'lc': lc, 'h14': h14, 'l14': l14, 'ur': ur, 
                        'bt_val': bt_val, 'is_bt_broken': is_bt_broken, 'is_trend_broken': is_trend_broken, 
                        'is_dt': is_dt, 'is_hs': is_hs, 'is_db': is_db, 'gc_days': gc_days, 'rank': rank, 'bg': bg, 'score': score, 
                        'reach_val': reach_val, 'atr_val': atr_val, 'rsi': rsi_v, 'df_chart': df_chart,
                        'source': "🛡️ 監視" if c in watch_in else "🚀 新規"
                    })
                
                scope_results = sorted(scope_results, key=lambda x: (x['score'], x['reach_val']), reverse=True)
                for r in scope_results:
                    st.divider()
                    # 🚨 修正：消滅していた source_color の定義を復活
                    source_color = "#42a5f5" if "監視" in r['source'] else "#ffa726"
                    
                    html_source = f"<span style='background-color:{source_color}; color:white; padding:2px 6px; border-radius:4px; font-size:12px;'>{r['source']}</span>"
                    html_rank = f"<span style='background-color:{r['bg']}; color:white; padding:2px 8px; border-radius:4px; margin-left:10px;'>🎯 {r['rank']}</span>"
                    st.markdown(f"### {html_source} ({r['code'][:4]}) {r['name']} {html_rank}", unsafe_allow_html=True)                    
                    if r['is_dt'] or r['is_hs']: st.error("🚨 危険波形検知（三尊/Wトップ）")
                    if not is_ambush and r['gc_days'] > 0: st.success(f"🔥 MACD GC後 {r['gc_days']}日目")
                    
                    c_base = r['bt_val'] if is_ambush else r['lc']
                    sc_left, sc_mid, sc_right = st.columns([2.5, 3.5, 5.0])
                    
                    with sc_mid:
                        if is_ambush:
                            html_buy_scope = f"<div style='background:rgba(255,215,0,0.05); padding:1rem; border-radius:8px; border:1px solid rgba(255,215,0,0.3); text-align:center;'><div style='font-size:14px;'>🎯 買値目標</div><div style='font-size:2.4rem; font-weight:bold; color:#FFD700;'>{int(r['bt_val']):,}円</div></div>"
                        else:
                            # 🚨 修正：強襲モードの表示（動的）
                            t_p = r['bt_val']; e_p = int(t_p + (r['atr_val'] * 0.2)); d_p = int(t_p - r['atr_val'])
                            html_buy_scope = f"""<div style='background:rgba(255,215,0,0.05); padding:1rem; border-radius:8px; border:1px solid rgba(255,215,0,0.3);'>
                                <div style='font-size:13px; text-align:center;'>🎯 トリガー (14d高値/ATR基準)</div>
                                <div style='font-size:2rem; font-weight:bold; color:#FFD700; text-align:center;'>{int(t_p):,}円</div>
                                <div style='border-top:1px dashed #444; margin:8px 0;'></div>
                                <div style='display:flex; justify-content:space-between;'><span>⚔️ 執行(+0.2ATR)</span><span style='color:#FFD700;'>{int(e_p):,}円</span></div>
                                <div style='display:flex; justify-content:space-between;'><span>🛡️ 防衛(-1.0ATR)</span><span style='color:#ef5350;'>{int(d_p):,}円</span></div></div>"""
                        st.markdown(html_buy_scope, unsafe_allow_html=True)

                    with sc_right:
                        c_target = r['bt_val']
                        tp_list = [5, 10, 15, 20]; sl_list = [5, 8, 10]
                        html_matrix = f"<div style='background:rgba(255,255,255,0.05); padding:1rem; border-radius:8px; border-left:5px solid #FFD700;'><div style='font-size:13px; color:#aaa; margin-bottom:8px;'>📊 期待値マトリクス (基準:{int(c_target):,}円)</div><div style='display:flex; gap:20px;'>"
                        html_matrix += "<div style='flex:1;'><div style='color:#26a69a; border-bottom:1px solid #26a69a;'>利確</div>" + "".join([f"<div style='display:flex; justify-content:space-between;'><span>+{p}%</span><b>{int(c_target*(1+p/100)):,}</b></div>" for p in tp_list]) + "</div>"
                        html_matrix += "<div style='flex:1;'><div style='color:#ef5350; border-bottom:1px solid #ef5350;'>損切</div>" + "".join([f"<div style='display:flex; justify-content:space-between;'><span>-{l}%</span><b>{int(c_target*(1-l/100)):,}</b></div>" for l in sl_list]) + "</div></div></div>"
                        st.markdown(html_matrix, unsafe_allow_html=True)
                    
                    st.markdown(render_technical_radar(r['df_chart'], c_base, 10), unsafe_allow_html=True)
                    draw_chart(r['df_chart'], c_base, chart_key=f"t3_chart_{r['code']}")

with tab4:
    st.markdown('<h3 style="font-size: clamp(14px, 4.5vw, 24px); margin-bottom: 1rem;">⚙️ 戦術シミュレータ (2年間のバックテスト)</h3>', unsafe_allow_html=True)
    
    # --- 🚨 セーフティ・ガード：初期値とモード切替時の挙動制御 ---
    if "bt_mode_sim_v2" not in st.session_state:
        st.session_state.bt_mode_sim_v2 = "🌐 【待伏】鉄の掟 (押し目狙撃)"

    current_mode = st.session_state.bt_mode_sim_v2
    if "prev_mode_for_defaults" not in st.session_state:
        st.session_state.prev_mode_for_defaults = current_mode

    # モード切替時の「買い期限」連動（強襲=3日 / 待伏=4日）
    if st.session_state.prev_mode_for_defaults != current_mode:
        if "待伏" in current_mode:
            st.session_state.sim_sell_d_val = 10
            st.session_state.sim_limit_d_val = 4
        else:
            st.session_state.sim_sell_d_val = 5
            st.session_state.sim_limit_d_val = 3
        st.session_state.prev_mode_for_defaults = current_mode

    # JSONに「0」が保存されてしまった場合の自動修復（リカバリー）
    if st.session_state.get("sim_tp_val", 0) == 0: st.session_state.sim_tp_val = 10
    if st.session_state.get("sim_sl_val", 0) == 0: st.session_state.sim_sl_val = 8
    if st.session_state.get("sim_limit_d_val", 0) == 0: st.session_state.sim_limit_d_val = 4
    if st.session_state.get("sim_sell_d_val", 0) == 0: st.session_state.sim_sell_d_val = 10
    if st.session_state.get("sim_push_r_val", 0) == 0: st.session_state.sim_push_r_val = st.session_state.get("push_r", 50.0)
    if st.session_state.get("sim_pass_req_val", 0) == 0: st.session_state.sim_pass_req_val = 7
    if st.session_state.get("sim_rsi_lim_ambush_val", 0) == 0: st.session_state.sim_rsi_lim_ambush_val = 45
    if st.session_state.get("sim_rsi_lim_assault_val", 0) == 0: st.session_state.sim_rsi_lim_assault_val = 70
    if st.session_state.get("sim_time_risk_val", 0) == 0: st.session_state.sim_time_risk_val = 5
    
    # プリセット（サイドバー）の変更を検知して連動
    current_sidebar_push_r = st.session_state.get("push_r", 50.0)
    if "last_sidebar_push_r" not in st.session_state or st.session_state.last_sidebar_push_r != current_sidebar_push_r:
        st.session_state.sim_push_r_val = current_sidebar_push_r
        st.session_state.last_sidebar_push_r = current_sidebar_push_r

    # 🚨 双方向同期機構：Store(実データ) -> UI用Key へ値を強制セット (連動問題の完全解決)
    st.session_state['_ui_tp'] = int(st.session_state.sim_tp_val)
    st.session_state['_ui_sl'] = int(st.session_state.sim_sl_val)
    st.session_state['_ui_lim'] = int(st.session_state.sim_limit_d_val)
    st.session_state['_ui_sell'] = int(st.session_state.sim_sell_d_val)
    st.session_state['_ui_push'] = float(st.session_state.sim_push_r_val)
    st.session_state['_ui_req'] = int(st.session_state.sim_pass_req_val)
    st.session_state['_ui_rsi_am'] = int(st.session_state.sim_rsi_lim_ambush_val)
    st.session_state['_ui_rsi_as'] = int(st.session_state.sim_rsi_lim_assault_val)
    st.session_state['_ui_risk'] = int(st.session_state.sim_time_risk_val)

    col_b1, col_b2 = st.columns([1, 1.8])
    T4_FILE = f"saved_t4_codes_{user_id}.txt"
    default_t4 = "7839\n6614"
    if os.path.exists(T4_FILE):
        with open(T4_FILE, "r", encoding="utf-8") as f: default_t4 = f.read()

    with col_b1: 
        st.markdown("🔍 **検証戦術**")
        st.radio("戦術モード", ["🌐 【待伏】鉄の掟 (押し目狙撃)", "⚡ 【強襲】GCブレイクアウト (順張り)"], key="bt_mode_sim_v2")
        bt_c_in = st.text_area("銘柄コード", value=default_t4, height=100, key="bt_codes_sim_v2")
        run_bt = st.button("🔥 仮想実弾テスト実行", use_container_width=True)
        optimize_bt = st.button("🚀 戦術の黄金比率を抽出 (最適化)", use_container_width=True)
        
    with col_b2:
        st.markdown("#### ⚙️ 戦術パラメーター（演習用チューニング）")
        st.info("※ 戦術切替時、売り期限は自動で「待伏:10日 / 強襲:5日」に再装填されます。")
        cp1, cp2, cp3, cp4 = st.columns(4)
        
        # 🚨 UI -> Store への同期コールバック (value属性を削除し、純粋にkeyで状態を管理)
        def sync_param(ui_key, store_key):
            st.session_state[store_key] = st.session_state[ui_key]
            save_settings()

        cp1.number_input("🎯 利確目標(%)", step=1, key="_ui_tp", on_change=sync_param, args=("_ui_tp", "sim_tp_val"))
        cp2.number_input("🛡️ 損切目安(%)", step=1, key="_ui_sl", on_change=sync_param, args=("_ui_sl", "sim_sl_val"))
        cp3.number_input("⏳ 買い期限(日)", step=1, key="_ui_lim", on_change=sync_param, args=("_ui_lim", "sim_limit_d_val"))
        cp4.number_input("⏳ 売り期限(日)", step=1, key="_ui_sell", on_change=sync_param, args=("_ui_sell", "sim_sell_d_val"))
        
        st.divider()
        if "待伏" in st.session_state.bt_mode_sim_v2:
            st.markdown("##### 🌐 【待伏】シミュレータ固有設定")
            ct1, ct2, ct3 = st.columns(3)
            ct1.number_input("📉 押し目待ち(%)", step=0.1, format="%.1f", key="_ui_push", on_change=sync_param, args=("_ui_push", "sim_push_r_val"))
            ct2.number_input("掟クリア要求数", step=1, max_value=9, min_value=1, key="_ui_req", on_change=sync_param, args=("_ui_req", "sim_pass_req_val"))
            ct3.number_input("RSI上限 (過熱感)", step=5, key="_ui_rsi_am", on_change=sync_param, args=("_ui_rsi_am", "sim_rsi_lim_ambush_val"))
        else:
            st.markdown("##### ⚡ 【強襲】シミュレータ固有設定")
            ct1, ct2 = st.columns(2)
            ct1.number_input("RSI上限 (過熱感)", step=5, key="_ui_rsi_as", on_change=sync_param, args=("_ui_rsi_as", "sim_rsi_lim_assault_val"))
            ct2.number_input("時間リスク上限（到達予想日数）", step=1, key="_ui_risk", on_change=sync_param, args=("_ui_risk", "sim_time_risk_val"))

    if (run_bt or optimize_bt) and bt_c_in:
        with open(T4_FILE, "w", encoding="utf-8") as f: f.write(bt_c_in)
        t_codes = list(dict.fromkeys([c.upper() for c in re.findall(r'(?<![a-zA-Z0-9])[a-zA-Z0-9]{4}(?![a-zA-Z0-9])', bt_c_in)]))
        
        if not t_codes: st.warning("有効なコードが見つかりません。")
        else:
            sim_tp = float(st.session_state.sim_tp_val)
            sim_sl_i = float(st.session_state.sim_sl_val)
            sim_limit_d = int(st.session_state.sim_limit_d_val)
            sim_sell_d = int(st.session_state.sim_sell_d_val)
            sim_push_r = float(st.session_state.sim_push_r_val)

            is_ambush = "待伏" in st.session_state.bt_mode_sim_v2
            if is_ambush:
                sim_pass_req = int(st.session_state.sim_pass_req_val)
                sim_rsi_lim_ambush = int(st.session_state.sim_rsi_lim_ambush_val)
                p1_range = range(25, 66, 5) if optimize_bt else [sim_push_r]
                p2_range = range(5, 10, 1) if optimize_bt else [sim_pass_req]
                p1_name, p2_name = "Push率(%)", "要求Score"
            else:
                sim_rsi_lim_assault = int(st.session_state.sim_rsi_lim_assault_val)
                sim_time_risk = int(st.session_state.sim_time_risk_val)
                p1_range = range(30, 85, 5) if optimize_bt else [sim_rsi_lim_assault]
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
                                    rsi_prev = prev.get('RSI', 50)
                                    idxmax = win_14['AdjH'].idxmax()
                                    d_high = len(win_14[win_14['Date'] > win_14.loc[idxmax, 'Date']]) if pd.notna(idxmax) else 0
                                    is_dt = check_double_top(win_30); is_hs = check_head_shoulders(win_30)
                                    bt_val = int(h14 - ((h14 - l14) * (t_p1 / 100.0)))
                                    
                                    if rsi_prev > sim_rsi_lim_ambush:
                                        continue

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
                                                # 🚨 新ロジック：固定1%を廃止し、14日高値 or ATR基準の動的ブレイクに変更
                                                eval_h14 = df.iloc[max(0, idx_eval-14):idx_eval]['AdjH'].max()
                                                eval_atr = df.iloc[idx_eval].get('ATR', 0)
                                                eval_c = df.iloc[idx_eval]['AdjC']
                                                # 高値を抜けるか、既に高値圏ならATRの半分を上抜けた位置をトリガーとする
                                                trigger_price = eval_h14 if eval_h14 > eval_c else eval_c + (eval_atr * 0.5)
                                                break
                                    
                                    if gc_triggered and rsi_prev <= t_p1 and exp_days < sim_time_risk:
                                        if td['AdjH'] >= trigger_price:
                                            # 🚨 新ロジック：執行値の上限を Trigger + (ATR * 0.2) とする
                                            exec_limit = trigger_price + (atr_prev * 0.2)
                                            exec_p = min(max(td['AdjO'], trigger_price), exec_limit)
                                            pos = {'b_i': i, 'b_d': td['Date'], 'b_p': exec_p, 'entry_atr': atr_prev, 'trigger': trigger_price}
                                            
                            else:
                                bp = pos['b_p']; held = i - pos['b_i']; sp = 0
                                current_tp = sim_tp if is_ambush else t_p2
                                e_atr = pos.get('entry_atr', prev.get('ATR', 0))
                                t_price = pos.get('trigger', bp)
                                
                                # 🚨 新ロジック：防衛線(損切)をATRベース（トリガーから -1.0 ATR）に換装
                                sl_val = t_price - (e_atr * 1.0)
                                tp_val = bp * (1 + (current_tp / 100.0)) # 利確は従来の%最適化目標を維持
                                
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
            
            # 🚨 修正：プログレスバー消去と結果出力のインデントをループの「外」へ完全移動
            p_bar.empty()

            if optimize_bt and opt_results:
                st.markdown(f"### 🏆 {st.session_state.bt_mode_sim_v2.split()[1]}・最適化レポート")
                opt_df = pd.DataFrame(opt_results).sort_values('総合利益(円)', ascending=False)
                best = opt_df.iloc[0]
                c1, c2, c3 = st.columns(3)
                c1.metric(f"推奨 {p1_name}", f"{int(best[p1_name])} " + ("%" if is_ambush else ""))
                c2.metric(f"推奨 {p2_name}", f"{int(best[p2_name])} " + ("点" if is_ambush else "%"))
                c3.metric("期待勝率", f"{round(best['勝率']*100, 1)} %")
                st.write("#### 📊 パラメーター別収益ヒートマップ（上位10選）")
                st.dataframe(opt_df.head(10).style.format({'総合利益(円)': '{:,}', '勝率': '{:.2%}'}), use_container_width=True, hide_index=True)
                if is_ambush: st.info(f"💡 【推奨戦術】現在の地合いでは、高値から {int(best[p1_name])}% の押し目位置に指値を展開し、掟スコア {int(best[p2_name])}点 以上で迎撃するのが最も期待値が高いと解析されます。")
            elif run_bt:
                if not opt_results: st.warning("指定された期間・条件でシグナル点灯（約定）は確認できませんでした。")
                else:
                    tdf = pd.DataFrame(all_t).sort_values('決済日').reset_index(drop=True)
                    tdf['累積損益(円)'] = tdf['損益額(円)'].cumsum()
                    st.success("🎯 バックテスト完了。")
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

    FRONTLINE_FILE = f"saved_frontline_{user_id}.csv"

    if 'frontline_df' not in st.session_state:
        if os.path.exists(FRONTLINE_FILE):
            try:
                temp_df = pd.read_csv(FRONTLINE_FILE)
                if "銘柄" in temp_df.columns:
                    temp_df["銘柄"] = temp_df["銘柄"].astype(str)
                for col in ["買値", "第1利確", "第2利確", "損切", "現在値"]:
                    if col in temp_df.columns:
                        temp_df[col] = pd.to_numeric(temp_df[col], errors='coerce')
                st.session_state.frontline_df = temp_df
            except:
                st.session_state.frontline_df = pd.DataFrame([
                    {"銘柄": "4259", "買値": 650.0, "第1利確": 688.0, "第2利確": 714.0, "損切": 627.0, "現在値": 670.0},
                    {"銘柄": "4691", "買値": 1588.0, "第1利確": 1635.0, "第2利確": 1635.0, "損切": 1508.0, "現在値": 1600.0},
                    {"銘柄": "3137", "買値": 267.0, "第1利確": 260.0, "第2利確": 267.0, "損切": 248.0, "現在値": 254.0}
                ])
        else:
            st.session_state.frontline_df = pd.DataFrame([
                {"銘柄": "4259", "買値": 650.0, "第1利確": 688.0, "第2利確": 714.0, "損切": 627.0, "現在値": 670.0},
                {"銘柄": "4691", "買値": 1588.0, "第1利確": 1635.0, "第2利確": 1635.0, "損切": 1508.0, "現在値": 1600.0},
                {"銘柄": "3137", "買値": 267.0, "第1利確": 260.0, "第2利確": 267.0, "損切": 248.0, "現在値": 254.0}
            ])

    # --- 🛰️ 衛星通信：現在値の一括同期ボタン ---
    if st.button("🔄 全軍の現在値を自動取得 (yfinance同期)", use_container_width=True):
        with st.spinner("衛星通信中... 各部隊の現在地を再取得しています"):
            import yfinance as yf
            updated = False
            for idx, row in st.session_state.frontline_df.iterrows():
                code = str(row['銘柄']).strip()
                if len(code) >= 4:
                    api_code = code[:4] + ".T"  # 日本株のティッカー形式に変換
                    try:
                        tk = yf.Ticker(api_code)
                        hist = tk.history(period="1d")
                        if not hist.empty:
                            latest_price = hist['Close'].iloc[-1]
                            st.session_state.frontline_df.at[idx, '現在値'] = round(latest_price, 1)
                            updated = True
                    except:
                        pass
            
            if updated:
                st.session_state.frontline_df.to_csv(FRONTLINE_FILE, index=False)
                st.success("🎯 現在値の同期が完了しました。（※yfinanceの仕様上、最大20分の遅延が含まれます）")
                st.rerun()
            else:
                st.warning("データの取得に失敗しました。")
    # ---------------------------------------------

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

    if not edited_df.equals(st.session_state.frontline_df):
        st.session_state.frontline_df = edited_df.copy()
        edited_df.to_csv(FRONTLINE_FILE, index=False)
        st.rerun()

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
        bar_color = "rgba(38, 166, 154, 0.7)" if cur >= buy else "rgba(239, 83, 80, 0.7)"
        fig.add_shape(type="line", x0=buy, y0=0, x1=cur, y1=0, line=dict(color=bar_color, width=12))
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
        try:
            aar_df = pd.read_csv(AAR_FILE)
            if "規模" not in aar_df.columns:
                aar_df.insert(2, "規模", aar_df["銘柄"].apply(get_scale_for_code))
                aar_df.to_csv(AAR_FILE, index=False)
            
            aar_df['決済日'] = aar_df['決済日'].astype(str)
            aar_df['銘柄'] = aar_df['銘柄'].astype(str)
            aar_df['買値'] = pd.to_numeric(aar_df['買値'], errors='coerce')
            aar_df['売値'] = pd.to_numeric(aar_df['売値'], errors='coerce')
            aar_df['株数'] = pd.to_numeric(aar_df['株数'], errors='coerce')
            aar_df['損益額(円)'] = pd.to_numeric(aar_df['損益額(円)'], errors='coerce')
            aar_df['損益(%)'] = pd.to_numeric(aar_df['損益(%)'], errors='coerce')
            
            aar_df = aar_df.sort_values(['決済日', '銘柄'], ascending=[True, True]).reset_index(drop=True)
        except:
            aar_df = pd.DataFrame(columns=["決済日", "銘柄", "規模", "戦術", "買値", "売値", "株数", "損益額(円)", "損益(%)", "規律", "敗因/勝因メモ"])
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
                st.success(f"銘柄 {aar_code} の戦果を司令部データベースに記録完了。")
                st.rerun()
            else: st.error("銘柄コード、買値、売値を正しく入力せよ。")
        
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
                                st.success(f"🎯 新規の戦果のみを抽出し、既存の記録と統合完了。")
                                st.rerun()
                            else: st.warning("解析可能な決済済みペア（買いと売りのセット）が確認できなかった。")
                        else: st.error("CSVフォーマットが認識不能。「約定日」「銘柄」を含むヘッダ行が必須だ。")
                    except Exception as e: st.error(f"解析エラー: {e}")

        if not aar_df.empty:
            if st.button("🗑️ 全記録を消去 (データベース初期化)", key="reset_aar", use_container_width=True):
                os.remove(AAR_FILE)
                st.rerun()

    with col_a2:
        st.markdown("#### 📊 司令部 総合戦績ダッシュボード")
        if aar_df.empty: st.warning("現在、交戦記録（データ）がない。左のフォームから入力するか、CSVをアップロードせよ。")
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
            st.caption("※表のセルを直接ダブルクリックすると、「戦術」「規律」「メモ」を直接編集（上書き保存）可能。")

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
