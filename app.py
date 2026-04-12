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
import streamlit.components.v1 as components
import gc

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

# --- 2. 認証・通信・物理同期エンジン ---
user_id = st.session_state["current_user"]
st.markdown(f'<h1 style="font-size: clamp(24px, 7vw, 42px); font-weight: 900; border-bottom: 2px solid #2e7d32; padding-bottom: 0.5rem; margin-bottom: 1rem;">🎯 戦術スコープ『鉄の掟』 <span style="font-size: 16px; font-weight: normal; color: #888;">(ID: {user_id[:4]}***)</span></h1>', unsafe_allow_html=True)

API_KEY = st.secrets.get("JQUANTS_API_KEY", "").strip()
headers = {"x-api-key": API_KEY}
BASE_URL = "https://api.jquants.com/v2"

SETTINGS_FILE = f"saved_settings_{user_id}.json"

def load_settings():
    """設定をロードし、0.0による機能不全を物理的に強制回避する"""
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
        "gigi_input": "2134, 3350, 6172, 6740, 7647, 8783, 8836, 8925, 9318"
    }
    if os.path.exists(SETTINGS_FILE):
        try:
            with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
                saved = json.load(f)
                for k, v in saved.items():
                    if k in defaults:
                        if k != "f1_min" and isinstance(v, (int, float)) and v == 0: continue
                        defaults[k] = v
        except: pass
    for k, v in defaults.items():
        if k not in st.session_state: st.session_state[k] = v
        else:
            if k != "f1_min" and isinstance(st.session_state[k], (int, float)) and st.session_state[k] == 0:
                st.session_state[k] = v
    if st.session_state.f3_drop == 0: st.session_state.f3_drop = -50.0

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

# --- 🌪️ マクロ気象レーダー（日経平均） ---
@st.cache_data(ttl=60, show_spinner=False)
def get_macro_weather():
    try:
        import yfinance as yf
        import pytz
        jst = pytz.timezone('Asia/Tokyo')
        now = datetime.now(jst)
        start_date = (now - timedelta(days=110)).strftime('%Y-%m-%d')
        end_date = (now + timedelta(days=2)).strftime('%Y-%m-%d')
        df_raw = yf.download("^N225", start=start_date, end=end_date, progress=False)
        if not df_raw.empty:
            if isinstance(df_raw.columns, pd.MultiIndex): df_raw.columns = df_raw.columns.get_level_values(0)
            df_ni = df_raw.reset_index()
            df_ni['Date'] = pd.to_datetime(df_ni['Date']).dt.tz_localize(None)
            df_ni = df_ni.dropna(subset=['Close']).tail(65)
            latest = df_ni.iloc[-1]; prev = df_ni.iloc[-2]
            return {"nikkei": {"price": latest['Close'], "diff": latest['Close'] - prev['Close'], "pct": ((latest['Close'] / prev['Close']) - 1) * 100, "df": df_ni, "date": latest['Date'].strftime('%m/%d')}}
    except: return None

def render_macro_board():
    data = get_macro_weather()
    if data and "nikkei" in data:
        ni = data["nikkei"]; df = ni["df"]; color = "#ef5350" if ni['diff'] >= 0 else "#26a69a"; sign = "+" if ni['diff'] >= 0 else ""
        c1, c2 = st.columns([1, 2.5])
        with c1:
            st.markdown(f'<div style="background: rgba(20, 20, 20, 0.6); padding: 1.2rem; border-radius: 8px; border-left: 4px solid {color}; height: 100%; display: flex; flex-direction: column; justify-content: center;"><div style="font-size: 14px; color: #aaa; margin-bottom: 8px;">🌪️ 戦場の天候 (日経平均: {ni["date"]})</div><div style="font-size: 26px; font-weight: bold; color: {color}; margin-bottom: 4px;">{ni["price"]:,.0f} 円</div><div style="font-size: 16px; color: {color};">({sign}{ni["diff"]:,.0f} / {sign}{ni["pct"]:.2f}%)</div></div>', unsafe_allow_html=True)
        with c2:
            df['MA25'] = df['Close'].rolling(window=25).mean()
            fig = go.Figure()
            fig.add_trace(go.Scatter(x=df['Date'], y=df['Close'], name='日経平均', mode='lines', line=dict(color='#FFD700', width=2), hovertemplate='日経平均: ¥%{y:,.0f}<extra></extra>'))
            fig.add_trace(go.Scatter(x=df['Date'], y=df['MA25'], name='25日線', mode='lines', line=dict(color='rgba(255, 255, 255, 0.4)', width=1, dash='dot'), hovertemplate='25日線: ¥%{y:,.0f}<extra></extra>'))
            fig.update_layout(height=160, margin=dict(l=10, r=40, t=10, b=10), xaxis_rangeslider_visible=False, paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)', showlegend=False, hovermode="x unified", yaxis=dict(side="right", tickformat=",.0f", gridcolor='rgba(255,255,255,0.05)'), xaxis=dict(type='date', tickformat='%m/%d', gridcolor='rgba(255,255,255,0.05)', range=[df['Date'].min(), df['Date'].max() + pd.Timedelta(hours=12)]))
            st.plotly_chart(fig, use_container_width=True, config={'displayModeBar': False})
        st.markdown("<div style='margin-bottom: 1.5rem;'></div>", unsafe_allow_html=True)
    else: st.warning("📡 外部気象レーダー応答なし")

render_macro_board()

# --- 3. 共通関数 & 演算エンジン ---
def clean_df(df):
    r_cols = {'AdjustmentOpen': 'AdjO', 'AdjustmentHigh': 'AdjH', 'AdjustmentLow': 'AdjL', 'AdjustmentClose': 'AdjC', 'Open': 'AdjO', 'High': 'AdjH', 'Low': 'AdjL', 'Close': 'AdjC', 'AdjustmentVolume': 'Volume', 'Volume': 'Volume'}
    df = df.rename(columns=r_cols)
    for c in ['AdjO', 'AdjH', 'AdjL', 'AdjC', 'Volume']:
        if c in df.columns: df[c] = pd.to_numeric(df[c], errors='coerce').astype('float32')
    if 'Date' in df.columns:
        df['Date'] = pd.to_datetime(df['Date'])
        df = df.sort_values(['Code', 'Date']).dropna(subset=['AdjO', 'AdjH', 'AdjL', 'AdjC']).reset_index(drop=True)
    return df

def calc_vector_indicators(df):
    df = df.copy()
    delta = df.groupby('Code')['AdjC'].diff()
    gain = delta.where(delta > 0, 0); loss = -delta.where(delta < 0, 0)
    avg_gain = gain.groupby(df['Code']).ewm(alpha=1/14, adjust=False).mean().reset_index(level=0, drop=True)
    avg_loss = loss.groupby(df['Code']).ewm(alpha=1/14, adjust=False).mean().reset_index(level=0, drop=True)
    df['RSI'] = (100 - (100 / (1 + (avg_gain / (avg_loss + 1e-10))))).astype('float32')
    ema12 = df.groupby('Code')['AdjC'].ewm(span=12, adjust=False).mean().reset_index(level=0, drop=True)
    ema26 = df.groupby('Code')['AdjC'].ewm(span=26, adjust=False).mean().reset_index(level=0, drop=True)
    macd = ema12 - ema26
    signal = macd.groupby(df['Code']).ewm(span=9, adjust=False).mean().reset_index(level=0, drop=True)
    df['MACD_Hist'] = (macd - signal).astype('float32')
    df['MA25'] = df.groupby('Code')['AdjC'].transform(lambda x: x.rolling(25).mean()).astype('float32')
    df['MA5'] = df.groupby('Code')['AdjC'].transform(lambda x: x.rolling(5).mean()).astype('float32')
    df['MA75'] = df.groupby('Code')['AdjC'].transform(lambda x: x.rolling(75).mean()).astype('float32')
    tr = pd.concat([df['AdjH']-df['AdjL'], (df['AdjH']-df.groupby('Code')['AdjC'].shift(1)).abs(), (df['AdjL']-df.groupby('Code')['AdjC'].shift(1)).abs()], axis=1).max(axis=1)
    df['ATR'] = tr.groupby(df['Code']).transform(lambda x: x.rolling(14).mean()).astype('float32')
    return df

def calc_technicals(df): return calc_vector_indicators(df)

def check_double_top(df_sub):
    try:
        v = df_sub['AdjH'].values; c = df_sub['AdjC'].values; l = df_sub['AdjL'].values
        if len(v) < 6: return False
        pk = []
        for i in range(1, len(v)-1):
            if v[i] == max(v[i-1:i+2]): pk.append((i, v[i]))
        if len(pk) >= 2:
            p2_idx, p2_val = pk[-1]; p1_idx, p1_val = pk[-2]
            if abs(p2_val - p1_val) / max(p2_val, p1_val) < 0.05 and c[-1] < p2_val * 0.97: return True
        return False
    except: return False

def check_head_shoulders(df_sub):
    try:
        v = df_sub['AdjH'].values; c = df_sub['AdjC'].values
        if len(v) < 8: return False
        pk = []
        for i in range(1, len(v)-1):
            if v[i] == max(v[i-1:i+2]): pk.append((i, v[i]))
        if len(pk) >= 3:
            p3_idx, p3_val = pk[-1]; p2_idx, p2_val = pk[-2]; p1_idx, p1_val = pk[-3]
            if p2_val > p1_val and p2_val > p3_val and abs(p3_val - p1_val) / max(p3_val, p1_val) < 0.10: return True
        return False
    except: return False

def get_fast_indicators(prices):
    if len(prices) < 15: return 50.0, 0.0, 0.0, np.zeros(5)
    p = np.array(prices, dtype='float32')
    ema12 = pd.Series(p).ewm(span=12, adjust=False).mean().values
    ema26 = pd.Series(p).ewm(span=26, adjust=False).mean().values
    macd = ema12 - ema26; signal = pd.Series(macd).ewm(span=9, adjust=False).mean().values
    hist = macd - signal; diff = np.diff(p[-15:]); g = np.sum(np.maximum(diff, 0)); l = np.sum(np.abs(np.minimum(diff, 0)))
    rsi = 100 - (100 / (1 + (g / (l + 1e-10)))); return rsi, hist[-1], hist[-2], hist[-5:]

def get_triage_info(macd_hist, macd_hist_prev, rsi, lc=0, bt=0, mode="待伏"):
    macd_t = "GC直後" if macd_hist > 0 and macd_hist_prev <= 0 else "上昇拡大" if macd_hist > macd_hist_prev else "下落継続" if macd_hist < 0 and macd_hist < macd_hist_prev else "減衰"
    if bt == 0 or lc == 0: return "C👁️", "#616161", 1, macd_t
    dist_pct = ((lc / bt) - 1) * 100 
    if dist_pct < -2.0: return "圏外💀", "#d32f2f", 0, macd_t
    elif dist_pct <= 2.0: return ("S🔥", "#2e7d32", 5, macd_t) if rsi <= 45 else ("A⚡", "#ed6c02", 4.5, macd_t) 
    elif dist_pct <= 5.0: return ("A🪤", "#0288d1", 4.0, macd_t) if rsi <= 50 else ("B📈", "#0288d1", 3, macd_t)
    else: return "C👁️", "#616161", 1, macd_t

@st.cache_data(ttl=86400)
def load_master():
    try:
        r1 = requests.get("https://www.jpx.co.jp/markets/statistics-equities/misc/01.html", headers={'User-Agent': 'Mozilla/5.0'}, timeout=10)
        m = re.search(r'href="([^"]+data_j\.xls)"', r1.text)
        if m:
            r2 = requests.get("https://www.jpx.co.jp" + m.group(1), headers={'User-Agent': 'Mozilla/5.0'}, timeout=15)
            df = pd.read_excel(BytesIO(r2.content), engine='xlrd')[['コード', '銘柄名', '33業種区分', '市場・商品区分']]
            df.columns = ['Code', 'CompanyName', 'Sector', 'Market']
            df['Code'] = df['Code'].astype(str) + "0"; return df
    except: pass
    return pd.DataFrame()

@st.cache_data(ttl=3600, show_spinner=False, max_entries=500)
def get_fundamentals(code):
    api_code = str(code) if len(str(code)) >= 5 else str(code) + "0"; url = f"{BASE_URL}/fins/statements?code={api_code}"
    try:
        r = requests.get(url, headers=headers, timeout=5)
        if r.status_code == 200:
            data = r.json().get("statements", [])
            if data:
                latest = data[0]; roe = None
                if latest.get("NetIncome") and latest.get("Equity"):
                    try: roe = (float(latest["NetIncome"]) / float(latest["Equity"])) * 100
                    except: pass
                return {"op": latest.get("OperatingProfit"), "er": latest.get("EquityRatio"), "roe": roe}
    except: pass
    return None

@st.cache_data(ttl=3600, show_spinner=False)
def get_single_data(code, yrs=1):
    base = datetime.utcnow() + timedelta(hours=9); f_d = (base - timedelta(days=365*yrs)).strftime('%Y%m%d'); t_d = base.strftime('%Y%m%d')
    result = {"bars": [], "events": {"dividend": [], "earnings": []}}
    try:
        api_code = str(code) if len(str(code)) >= 5 else str(code) + "0"; url = f"{BASE_URL}/equities/bars/daily?code={api_code}&from={f_d}&to={t_d}"
        r_bars = requests.get(url, headers=headers, timeout=10)
        if r_bars.status_code == 200: result["bars"] = r_bars.json().get("daily_quotes") or r_bars.json().get("data") or []
    except: pass
    return result

@st.cache_data(ttl=3600, max_entries=2, show_spinner=False)
def get_hist_data_cached():
    base = datetime.utcnow() + timedelta(hours=9); dates = []; days = 0
    while len(dates) < 45:
        d = base - timedelta(days=days); 
        if d.weekday() < 5: dates.append(d.strftime('%Y%m%d'))
        days += 1
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
            res = f.result(); 
            if res: rows.extend(res)
    return rows

def get_assault_triage_info(gc_days, lc, rsi_v, df_chart, is_strict=False):
    if gc_days <= 0 or df_chart is None or df_chart.empty: return "圏外 💀", "#424242", 0, ""
    row = df_chart.iloc[-1]; ma25 = row.get('MA25', 0); score = 50 
    if ma25 > 0:
        if lc >= ma25 * 0.95: score += 10
        if lc >= ma25: score += 10
    if 50 <= rsi_v <= 70: score += 10
    if score >= 80: rank, bg = "S🔥", "#d32f2f"
    elif score >= 60: rank, bg = "A⚡", "#f57c00"
    elif score >= 40: rank, bg = "B📈", "#fbc02d"
    else: rank, bg = "C👁️", "#424242"
    return rank, bg, score, "GC発動中"

# --- 4. サイドバー UI詳細設計 ---
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
st.sidebar.number_input("1年最高値からの下落除外(%)", step=5.0, max_value=0.0, key="f3_drop", on_change=save_settings)

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
cs1, cs2 = st.sidebar.columns(2)
cs1.number_input("初期損切(%)", step=1, key="bt_sl_i", on_change=save_settings)
cs2.number_input("現在損切(%)", step=1, key="bt_sl_c", on_change=save_settings)
st.sidebar.number_input("最大保持期間(日)", step=1, key="bt_sell_d", on_change=save_settings)
st.sidebar.divider()

st.sidebar.header("🚫 特殊除外フィルター")
st.sidebar.checkbox("ETF・REIT等を除外", key="f7_ex_etf", on_change=save_settings)
st.sidebar.checkbox("医薬品(バイオ)を除外", key="f8_ex_bio", on_change=save_settings)
st.sidebar.checkbox("落ちるナイフ除外(暴落直後)", key="f10_ex_knife", on_change=save_settings)
st.sidebar.text_area("除外銘柄コード (雑なコピペ対応)", key="gigi_input", on_change=save_settings)
st.sidebar.divider()

if st.sidebar.button("🔴 キャッシュ強制パージ", use_container_width=True):
    st.cache_data.clear(); st.session_state.tab1_scan_results = None; st.session_state.tab2_scan_results = None; st.rerun()
if st.sidebar.button("💾 現在の設定を保存", use_container_width=True):
    save_settings(); st.toast("全設定を永久保存した。")

# --- 5. タブ構成の開始 ---
master_df = load_master()
tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs(["🌐 【待伏】広域レーダー", "⚡ 【強襲】GC初動レーダー", "🎯 【照準】精密スコープ", "⚙️ 【演習】戦術シミュレータ", "⛺ 【戦線】交戦モニター", "📁 【戦歴】交戦データベース"])
tactics_mode = st.session_state.sidebar_tactics

with tab1:
    st.markdown('<h3 style="font-size: clamp(14px, 4.5vw, 24px); margin-bottom: 1rem;">🎯 【待伏】鉄の掟・半値押しレーダー</h3>', unsafe_allow_html=True)
    if 'tab1_scan_results' not in st.session_state: st.session_state.tab1_scan_results = None
    run_scan_t1 = st.button("🚀 最新データで待伏スキャン開始")

    if run_scan_t1:
        st.toast("🟢 待伏トリガーを確認。索敵開始！", icon="🎯")
        with st.spinner("全銘柄からターゲットを索敵中..."):
            raw = get_hist_data_cached()
            if not raw:
                st.error("データの取得に失敗した。")
                st.session_state.tab1_scan_results = None
            else:
                df = clean_df(pd.DataFrame(raw))
                df['Code'] = df['Code'].astype(str)
                v_col = next((col for col in df.columns if col in ['Volume', 'AdjVo', 'Vo', 'AdjustmentVolume']), None)
                if v_col:
                    df[v_col] = pd.to_numeric(df[v_col], errors='coerce').fillna(0)
                    avg_vols = df.groupby('Code').tail(5).groupby('Code')[v_col].mean()
                else: avg_vols = pd.Series(0, index=df['Code'].unique())

                # --- 物理配線：サイドバー設定の同期 ---
                f1_min, f1_max = float(st.session_state.f1_min), float(st.session_state.f1_max)
                f2_limit = float(st.session_state.f2_m30)
                f3_drop_val = float(st.session_state.f3_drop)
                f5_ipo = st.session_state.f5_ipo
                f7_ex_etf = st.session_state.f7_ex_etf
                f8_bio_flag = st.session_state.f8_ex_bio
                f10_ex_knife = st.session_state.f10_ex_knife
                push_ratio = st.session_state.push_r / 100.0
                limit_d_val = int(st.session_state.limit_d)

                latest_date = df['Date'].max()
                latest_df = df[df['Date'] == latest_date]
                
                # 市場フィルター
                m_mode = "大型" if "大型株" in st.session_state.preset_market else "中小型"
                if not master_df.empty:
                    large_keywords = ['プライム', '一部']; small_keywords = ['スタンダード', 'グロース', '新興', 'マザーズ', 'JASDAQ', '二部']
                    m_target_codes = master_df[master_df['Market'].str.contains('|'.join(large_keywords if m_mode == "大型" else small_keywords), na=False)]['Code'].unique()
                    df = df[df['Code'].isin(m_target_codes)]

                # 基本足切り
                valid_price_codes = latest_df[(latest_df['AdjC'] >= f1_min) & (latest_df['AdjC'] <= f1_max)]['Code'].unique()
                valid_vol_codes = avg_vols[avg_vols >= 10000].index
                df = df[df['Code'].isin(set(valid_price_codes).intersection(set(valid_vol_codes)))]

                # 🚫 IPO除外 (Turn 43 ロジック継承)
                if f5_ipo and not df.empty:
                    stock_min_dates = df.groupby('Code')['Date'].min()
                    df = df[df['Code'].isin(stock_min_dates[stock_min_dates <= (df['Date'].min() + pd.Timedelta(days=15))].index)]

                # 🚫 ETF/REIT除外
                if f7_ex_etf and not master_df.empty:
                    invalid_mask = master_df['Market'].astype(str).str.contains('ETF|REIT', case=False, na=False) | master_df['Sector'].astype(str).str.contains('ETF|REIT|投信', case=False, na=False)
                    df = df[df['Code'].isin(master_df[~invalid_mask]['Code'].unique())]
                
                # 🚫 医薬品(バイオ)除外
                if f8_bio_flag and not master_df.empty:
                    bio_codes = master_df[master_df['Sector'].str.contains('医薬品', na=False)]['Code'].unique()
                    df = df[~df['Code'].isin(bio_codes)]

                # 🚫 ブラックリスト (gigi_input)
                g_in = st.session_state.get("gigi_input", "")
                if g_in:
                    bl = re.findall(r'\d{4}', str(g_in))
                    if bl: df = df[~df['Code'].str.extract(r'(\d{4})')[0].isin(bl)]

                master_dict = master_df.set_index('Code')[['CompanyName', 'Market', 'Sector']].to_dict('index') if not master_df.empty else {}
                results = []
                for code, group in df.groupby('Code'):
                    if len(group) < 15: continue 
                    adjc_vals, adjh_vals, adjl_vals = group['AdjC'].values, group['AdjH'].values, group['AdjL'].values; lc = adjc_vals[-1]
                    
                    # 1ヶ月暴騰上限チェック
                    if lc / adjc_vals[max(0, len(adjc_vals)-20)] > f2_limit: continue
                    # 1年最高値からの下落率チェック
                    if lc < adjh_vals.max() * (1 + (f3_drop_val / 100.0)): continue
                    
                    # 第3波終了除外
                    if st.session_state.f11_ex_wave3:
                        peaks = []
                        for j in range(5, len(adjh_vals)-5):
                            if adjh_vals[j] == max(adjh_vals[j-5:j+5]):
                                if not peaks or adjh_vals[j] > peaks[-1] * 1.15: peaks.append(adjh_vals[j])
                        if len(peaks) >= 3 and lc < max(peaks) * 0.85: continue
                        
                    # 落ちるナイフ除外
                    if st.session_state.f10_ex_knife and len(adjc_vals) >= 4 and (adjc_vals[-1] / adjc_vals[-4] < 0.85): continue
                    
                    # 波形算出
                    r4h = adjh_vals[-4:]; h4 = r4h.max(); gi = len(adjh_vals) - 4 + r4h.argmax(); l14 = adjl_vals[max(0, gi-14) : gi+1].min()
                    if l14 <= 0 or h4 <= l14: continue
                    wh = h4 / l14
                    
                    # 波高制限
                    if not (st.session_state.f9_min14 <= wh <= st.session_state.f9_max14): continue
                    
                    # 目標値・指標算出
                    bt = h4 - ((h4 - l14) * push_ratio); rr = (bt / lc) * 100; rsi, macdh, macdh_p, _ = get_fast_indicators(adjc_vals)
                    
                    # 🏅 掟スコア計算
                    score = 4 
                    if 1.3 <= wh <= 2.0: score += 1
                    if (len(adjh_vals) - 1 - gi) <= limit_d_val: score += 1
                    if not check_double_top(group.tail(31).iloc[:-1]): score += 1
                    if bt * 0.85 <= lc <= bt * 1.35: score += 1
                    
                    # 財務生体スキャン
                    if st.session_state.f6_risk or st.session_state.f12_ex_overvalued:
                        fund = get_fundamentals(code)
                        if fund:
                            if st.session_state.f6_risk and (float(fund.get('er', 1)) < 0.20 or float(fund.get('op', 1)) < 0): continue
                            if st.session_state.f12_ex_overvalued and float(fund.get('op', 1)) < 0: continue
                    
                    m_i = master_dict.get(code, {}); rank, bg, t_score, _ = get_triage_info(macdh, macdh_p, rsi, lc, bt)
                    results.append({'Code': code, 'Name': m_i.get('CompanyName', f"銘柄 {code[:4]}"), 'Sector': m_i.get('Sector', '不明'), 'Market': m_i.get('Market', '不明'), 'lc': lc, 'RSI': rsi, 'avg_vol': int(avg_vols.get(code, 0)), 'high_4d': h4, 'low_14d': l14, 'target_buy': bt, 'reach_rate': rr, 'triage_rank': rank, 'triage_bg': bg, 't_score': t_score, 'score': score})
                
                st.session_state.tab1_scan_results = sorted(results, key=lambda x: (x['t_score'], x['score']), reverse=True)[:30]

    if st.session_state.tab1_scan_results:
        light_results = st.session_state.tab1_scan_results
        st.success(f"🎯 待伏ロックオン: {len(light_results)} 銘柄を選別。")
        
        # 📋 銘柄コード一括コピーボックス
        sab_codes = " ".join([str(r['Code'])[:4] for r in light_results if str(r['triage_rank']).startswith(('S', 'A', 'B'))])
        if sab_codes:
            st.info("📋 以下のコードをコピーして照準（TAB3）へ投入せよ。")
            st.code(sab_codes, language="text")
            
        for r in light_results:
            st.divider()
            c_code = str(r['Code']); m_l = str(r['Market']).lower()
            
            # 🏢 市場バッジ
            if 'プライム' in m_l or '一部' in m_l: 
                b_html = '<span style="background-color: #1a237e; color: #ffffff; padding: 0.2rem 0.6rem; border-radius: 4px; font-size: 11px; font-weight: bold;">🏢 プライム/大型</span>'
            elif 'グロース' in m_l or 'マザーズ' in m_l: 
                b_html = '<span style="background-color: #1b5e20; color: #ffffff; padding: 0.2rem 0.6rem; border-radius: 4px; font-size: 11px; font-weight: bold;">🚀 中小型</span>'
            else: 
                b_html = f'<span style="background-color: #455a64; color: #ffffff; padding: 0.2rem 0.6rem; border-radius: 4px; font-size: 11px; font-weight: bold;">{r["Market"]}</span>'
            
            t_b = f'<span style="background-color: {r["triage_bg"]}; color: #ffffff; padding: 0.2rem 0.6rem; border-radius: 4px; font-size: 13px; font-weight: bold; margin-left: 0.5rem;">🎯 優先度: {r["triage_rank"]}</span>'
            s_b = f'<span style="background-color: rgba(46,125,50,0.15); border: 1px solid #2e7d32; color: #2e7d32; padding: 0.2rem 0.6rem; border-radius: 4px; font-size: 12px; font-weight: bold; margin-left: 0.5rem;">🎖️ 掟スコア: {r["score"]}/9</span>'
            
            st.markdown(f"""
                <div style="margin-bottom: 0.8rem;">
                    <h3 style="font-size: 24px; font-weight: bold; margin: 0;">({c_code[:4]}) {r["Name"]}</h3>
                    <div style="display: flex; flex-wrap: wrap; gap: 6px; align-items: center;">
                        {b_html}{t_b}{s_b}
                        <span style="background-color: rgba(38, 166, 154, 0.15); border: 1px solid #26a69a; color: #26a69a; padding: 0.1rem 0.5rem; border-radius: 4px; font-size: 12px; margin-left: 4px;">RSI: {r["RSI"]:.1f}%</span>
                        <span style="background-color: rgba(255, 215, 0, 0.1); border: 1px solid #FFD700; color: #FFD700; padding: 0.1rem 0.5rem; border-radius: 4px; font-size: 12px;">到達度: {r["reach_rate"]:.1f}%</span>
                    </div>
                </div>
            """, unsafe_allow_html=True)
            
            m_cols = st.columns([1, 1, 1, 1.2, 1.5])
            m_cols[0].metric("直近高値", f"{int(r['high_4d']):,}円")
            m_cols[1].metric("起点安値", f"{int(r['low_14d']):,}円")
            m_cols[2].metric("最新終値", f"{int(r['lc']):,}円")
            m_cols[3].metric("平均出来高", f"{int(r['avg_vol']):,}株")
            
            m_cols[4].markdown(f"""
                <div style="background: rgba(255, 215, 0, 0.05); padding: 0.5rem; border-radius: 8px; border: 1px solid rgba(255, 215, 0, 0.2); text-align: center;">
                    <div style="font-size: 13px; color: #aaa;">🎯 買値目標</div>
                    <div style="font-size: 1.8rem; font-weight: bold; color: #FFD700;">{int(r["target_buy"]):,}<span style="font-size: 14px;">円</span></div>
                </div>
            """, unsafe_allow_html=True)
            st.caption(f"🏢 {r.get('Market', '不明')} ｜ 🏭 {r.get('Sector', '不明')}")

with tab2:
    st.markdown('<h3 style="font-size: clamp(14px, 4.5vw, 24px); margin-bottom: 1rem;">⚡ 【強襲】GC初動レーダー</h3>', unsafe_allow_html=True)
    if 'tab2_scan_results' not in st.session_state: st.session_state.tab2_scan_results = None
    
    col_t2_1, col_t2_2 = st.columns(2)
    rsi_limit_val = col_t2_1.number_input("RSI上限（過熱感の足切り）", step=5, value=st.session_state.tab2_rsi_limit, key="ui_tab2_rsi_box", on_change=save_settings)
    vol_limit_val = col_t2_2.number_input("最低出来高（5日平均）", step=5000, value=st.session_state.tab2_vol_limit, key="ui_tab2_vol_box", on_change=save_settings)
    
    run_scan_t2 = st.button("🚀 全軍GC初動スキャン開始", key="btn_assault_scan_trigger")

    if run_scan_t2:
        st.toast("🟢 強襲トリガーを確認。索敵開始！", icon="🚀")
        with st.spinner("GC初動候補を抽出中..."):
            raw = get_hist_data_cached()
            if not raw:
                st.session_state.tab2_scan_results = None
            else:
                df = clean_df(pd.DataFrame(raw))
                df['Code'] = df['Code'].astype(str)
                
                # 出来高カラムの特定と平均算出
                v_col = next((col for col in df.columns if col in ['Volume', 'AdjVo', 'Vo', 'AdjustmentVolume']), None)
                if v_col:
                    df[v_col] = pd.to_numeric(df[v_col], errors='coerce').fillna(0)
                    avg_vols = df.groupby('Code').tail(5).groupby('Code')[v_col].mean()
                else:
                    avg_vols = pd.Series(0, index=df['Code'].unique())

                # --- 物理配線：設定の同期 ---
                f1_min, f1_max = float(st.session_state.f1_min), float(st.session_state.f1_max)
                f2_limit = float(st.session_state.f2_m30)
                f3_drop_val = float(st.session_state.f3_drop)
                f5_ipo = st.session_state.f5_ipo
                f7_ex_etf = st.session_state.f7_ex_etf
                f8_bio_flag = st.session_state.f8_ex_bio
                f10_ex_knife = st.session_state.f10_ex_knife
                f11_ex_wave3 = st.session_state.f11_ex_wave3
                f12_overvalued = st.session_state.f12_ex_overvalued
                g_in = st.session_state.get("gigi_input", "")
                m_mode = "大型" if "大型株" in st.session_state.preset_market else "中小型"
                
                # 市場フィルター
                if not master_df.empty:
                    m_target_codes = master_df[master_df['Market'].str.contains('|'.join(['プライム', '一部'] if m_mode=="大型" else ['スタンダード', 'グロース', '新興', 'マザーズ', 'JASDAQ', '二部']), na=False)]['Code'].unique()
                    df = df[df['Code'].isin(m_target_codes)]

                # 基本足切り
                latest_date = df['Date'].max()
                latest_df = df[df['Date'] == latest_date]
                valid_price_codes = latest_df[(latest_df['AdjC'] >= f1_min) & (latest_df['AdjC'] <= f1_max)]['Code'].unique()
                valid_vol_codes = avg_vols[avg_vols >= vol_limit_val].index
                df = df[df['Code'].isin(set(valid_price_codes).intersection(set(valid_vol_codes)))]

                # IPO除外
                if f5_ipo and not df.empty:
                    stock_min_dates = df.groupby('Code')['Date'].min()
                    df = df[df['Code'].isin(stock_min_dates[stock_min_dates <= (df['Date'].min() + pd.Timedelta(days=15))].index)]

                # ETF/REIT除外
                if f7_ex_etf and not master_df.empty:
                    invalid_mask = master_df['Market'].astype(str).str.contains('ETF|REIT', case=False, na=False) | master_df['Sector'].astype(str).str.contains('ETF|REIT|投信', case=False, na=False)
                    df = df[df['Code'].isin(master_df[~invalid_mask]['Code'].unique())]

                # 医薬品(バイオ)除外
                if f8_bio_flag and not master_df.empty:
                    bio_codes = master_df[master_df['Sector'].str.contains('医薬品', na=False)]['Code'].unique()
                    df = df[~df['Code'].isin(bio_codes)]

                # ブラックリスト (gigi_input)
                if g_in:
                    bl = re.findall(r'\d{4}', str(g_in))
                    if bl: df = df[~df['Code'].str.extract(r'(\d{4})')[0].isin(bl)]
                
                master_dict = master_df.set_index('Code')[['CompanyName', 'Market', 'Sector']].to_dict('index') if not master_df.empty else {}
                results = []
                for code, group in df.groupby('Code'):
                    if len(group) < 30: continue
                    
                    adjc_vals, adjh_vals = group['AdjC'].values, group['AdjH'].values
                    lc = adjc_vals[-1]
                    
                    # 1ヶ月暴騰上限 (20日前比)
                    prev_20_val = adjc_vals[max(0, len(adjc_vals)-20)]
                    if prev_20_val > 0 and (lc / prev_20_val) > f2_limit: continue
                    
                    # 1年最高値からの下落率
                    if lc < adjh_vals.max() * (1 + (f3_drop_val / 100.0)): continue

                    # 第3波終了除外
                    if f11_ex_wave3:
                        peaks = []
                        for j in range(5, len(adjh_vals)-5):
                            if adjh_vals[j] == max(adjh_vals[j-5:j+5]):
                                if not peaks or adjh_vals[j] > peaks[-1] * 1.15: peaks.append(adjh_vals[j])
                        if len(peaks) >= 3 and lc < max(peaks) * 0.85: continue

                    # 落ちるナイフ除外
                    if f10_ex_knife:
                        recent_4d = adjc_vals[-4:]
                        if len(recent_4d) == 4 and (recent_4d[-1] / recent_4d[0] < 0.85): continue
                    
                    rsi, _, _, hist_vals = get_fast_indicators(adjc_vals)
                    if rsi > rsi_limit_val: continue
                    
                    # ⚡ GC判定ロジック
                    gc_days = 1 if len(hist_vals)>=2 and hist_vals[-2]<0 and hist_vals[-1]>=0 else 2 if len(hist_vals)>=3 and hist_vals[-3]<0 and hist_vals[-1]>=0 else 3 if len(hist_vals)>=4 and hist_vals[-4]<0 and hist_vals[-1]>=0 else 0
                    if gc_days == 0: continue
                    
                    ma25 = group['AdjC'].rolling(window=25).mean().iloc[-1]
                    if lc < (ma25 * 0.95): continue
                    
                    # 財務生体スキャン
                    if st.session_state.f6_risk or f12_overvalued:
                        fund = get_fundamentals(code)
                        if fund:
                            if st.session_state.f6_risk and (float(fund.get('er', 1)) < 0.20 or float(fund.get('op', 1)) < 0): continue
                            if f12_overvalued and float(fund.get('op', 1)) < 0: continue

                    group_calc = group.copy()
                    group_calc['MA25'] = group['AdjC'].rolling(window=25).mean()
                    t_rank, t_color, t_score, _ = get_assault_triage_info(gc_days, lc, rsi, group_calc, is_strict=False)
                    m_i = master_dict.get(code, {})
                    results.append({
                        'Code': code, 'Name': m_i.get('CompanyName', f"銘柄 {code[:4]}"), 
                        'Market': m_i.get('Market', '不明'), 'Sector': m_i.get('Sector', '不明'), 
                        'lc': lc, 'RSI': rsi, 'avg_vol': int(avg_vols.get(code, 0)), 'h14': adjh_vals[-14:].max(), 
                        'atr': adjh_vals[-14:].max()*0.03, 'T_Rank': t_rank, 'T_Color': t_color, 'T_Score': t_score, 'GC_Days': gc_days
                    })
                
                st.session_state.tab2_scan_results = sorted(results, key=lambda x: (-x['T_Score'], x['GC_Days']))[:30]

    if st.session_state.tab2_scan_results:
        light_results = st.session_state.tab2_scan_results
        st.success(f"⚡ 強襲ロックオン: GC初動(3日以内) 上位 {len(light_results)} 銘柄を確認。")
        sab_codes = " ".join([str(r['Code'])[:4] for r in light_results if str(r['T_Rank']).startswith(('S', 'A', 'B'))])
        if sab_codes:
            st.info("📋 以下のコードをコピーして、照準（TAB3）にペースト可能だ。")
            st.code(sab_codes, language="text")
        
        for r in light_results:
            st.divider()
            m_lower = str(r['Market']).lower()
            if 'プライム' in m_lower or '一部' in m_lower: badge_html = '<span style="background-color: #1a237e; color: #ffffff; padding: 0.2rem 0.6rem; border-radius: 4px; font-size: 11px; font-weight: bold;">🏢 プライム/大型</span>'
            elif 'グロース' in m_lower or 'マザーズ' in m_lower: badge_html = '<span style="background-color: #1b5e20; color: #ffffff; padding: 0.2rem 0.6rem; border-radius: 4px; font-size: 11px; font-weight: bold;">🚀 グロース/新興</span>'
            else: badge_html = f'<span style="background-color: #455a64; color: #ffffff; padding: 0.2rem 0.6rem; border-radius: 4px; font-size: 11px; font-weight: bold;">{r["Market"]}</span>'
            t_badge = f'<span style="background-color: {r["T_Color"]}; color: #ffffff; padding: 0.2rem 0.6rem; border-radius: 4px; font-size: 13px; display: inline-block; font-weight: bold; margin-left: 0.5rem;">🎯 優先度: {r["T_Rank"]}</span>'

            st.markdown(f"""
                <div style="margin-bottom: 0.8rem;">
                    <h3 style="font-size: 24px; font-weight: bold; margin: 0 0 0.3rem 0;">({str(r['Code'])[:4]}) {r['Name']}</h3>
                    <div style="display: flex; flex-wrap: wrap; gap: 6px; align-items: center;">
                        {badge_html}{t_badge}
                        <span style="background-color: rgba(237, 108, 2, 0.15); border: 1px solid #ed6c02; color: #ed6c02; padding: 0.1rem 0.5rem; border-radius: 4px; font-size: 12px;">GC後 {r.get('GC_Days')}日目</span>
                    </div>
                </div>
            """, unsafe_allow_html=True)
            
            lc_v, h14_v, atr_v = r['lc'], r['h14'], r['atr']
            t_price, d_price = max(h14_v, lc_v + (atr_v * 0.5)), max(h14_v, lc_v + (atr_v * 0.5)) - atr_v
            
            m_cols = st.columns([1, 1, 1, 1.2, 1.5])
            m_cols[0].metric("最新終値", f"{int(lc_v):,}円")
            m_cols[1].metric("RSI", f"{r['RSI']:.1f}%")
            m_cols[2].metric("ボラ(推定)", f"{int(atr_v):,}円")
            m_cols[3].markdown(f'<div style="background: rgba(239, 83, 80, 0.05); padding: 0.5rem; border-radius: 8px; border: 1px solid rgba(239, 83, 80, 0.3); text-align: center;"><div style="font-size: 13px; color: rgba(250, 250, 250, 0.6); margin-bottom: 2px;">🛡️ 防衛線</div><div style="font-size: 1.6rem; font-weight: bold; color: #ef5350;">{int(d_price):,}円</div></div>', unsafe_allow_html=True)
            m_cols[4].markdown(f'<div style="background: rgba(255, 215, 0, 0.05); padding: 0.5rem; border-radius: 8px; border: 1px solid rgba(255, 215, 0, 0.2); text-align: center;"><div style="font-size: 13px; color: rgba(250, 250, 250, 0.6); margin-bottom: 2px;">🎯 トリガー</div><div style="font-size: 1.6rem; font-weight: bold; color: #FFD700;">{int(t_price):,}円</div></div>', unsafe_allow_html=True)
            st.caption(f"🏭 {r['Sector']} ｜ 📊 平均出来高: {int(r['avg_vol']):,}株")
            
with tab3:
    # 📱 モバイル表示時の右側切れを物理排除し、パディングを最適化するレスポンシブパッチ
    st.markdown("""
        <style>
        @media (max-width: 768px) {
            .stMain { padding-left: 0.5rem !important; padding-right: 0.5rem !important; }
            div[data-testid="stHorizontalBlock"] { gap: 0 !important; }
            div[style*="border-left"] { border-left: 3px solid #FFD700 !important; padding: 0.8rem !important; }
            .stMetric { min-width: 70px !important; }
        }
        </style>
    """, unsafe_allow_html=True)

    st.markdown('<h3 style="font-size: clamp(14px, 4.5vw, 24px); margin-bottom: 1rem;">🎯 【照準】精密スコープ（戦術別・独立索敵）</h3>', unsafe_allow_html=True)
    
    # --- 🖥️ 【原典UI完全復旧】 二層式ターゲット入力セクション ---
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
        # 🎯 解析モードの選択
        scope_mode = st.radio("🎯 解析モードを選択", ["🌐 【待伏】 押し目・逆張り", "⚡ 【強襲】 トレンド・順張り"], key="t3_scope_mode", on_change=save_settings)
        is_ambush = "待伏" in scope_mode
        st.markdown("---")
        
        # 二層式入力枠の出し分け（監視部隊 / 本日新規部隊）
        if is_ambush:
            watch_in = st.text_area("🌐 【待伏】主力監視部隊", value=st.session_state.t3_am_watch, height=120)
            daily_in = st.text_area("🌐 【待伏】本日新規部隊", value=st.session_state.t3_am_daily, height=120)
        else:
            watch_in = st.text_area("⚡ 【強襲】主力監視部隊", value=st.session_state.t3_as_watch, height=120)
            daily_in = st.text_area("⚡ 【強襲】本日新規部隊", value=st.session_state.t3_as_daily, height=120)
            
        run_scope = st.button("🔫 表示中の全部隊を精密スキャン", use_container_width=True, type="primary")
        
    with col_s2:
        # 💎 物理再編：垂直リスト形式バナー（視認性向上）
        st.markdown("#### 🔍 索敵ステータス")
        if is_ambush: 
            st.info("・【待伏専用】半値押し・黄金比での迎撃判定")
            st.markdown("""
            <div style="font-size: 13px; color: #bbb; background: rgba(255,255,255,0.05); padding: 12px; border-radius: 5px; border-left: 3px solid #2e7d32; line-height: 1.6;">
                <b style="color: #2e7d32; font-size: 14px;">【掟スコア加点基準（最大10点）】</b><br>
                ✅ 基礎モメンタム（MACD/RSI優位：最大+5点）<br>
                ✅ 波高1.3〜2.0倍（+1点）<br>
                ✅ 調整日数が規定内（+1点）<br>
                ✅ 危険波形(Wトップ等)なし（+1点）<br>
                ✅ 買値目標の±15%圏内（+1点）<br>
                ✅ 割安性：PBR 5.0倍以下（+1点）
            </div>
            """, unsafe_allow_html=True)
        else: 
            st.warning("・【強襲専用】ATR/14日高値ベースの動的ブレイクアウト判定")
            st.markdown("""
            <div style="font-size: 13px; color: #bbb; background: rgba(255,255,255,0.05); padding: 12px; border-radius: 5px; border-left: 3px solid #ed6c02; line-height: 1.6;">
                <b style="color: #ed6c02; font-size: 14px;">【強襲スコア加点基準（最大100点）】</b><br>
                ⚡ GC（ゴールデンクロス）発動（基礎+50点）<br>
                ⚡ 25日線上抜け / 上昇トレンド維持（最大+20点）<br>
                ⚡ 出来高の急増（+10点）<br>
                ⚡ RSIの適正過熱感（+10点）<br>
                ⚡ 割安性：PBR 5.0倍以下（+10点）<br>
                <span style="color:#ef5350;">※ 波形崩壊・過熱・出来高不足は厳格減点</span>
            </div>
            """, unsafe_allow_html=True)

    if run_scope:
        # ファイル保存ロジック（物理永続化）
        if is_ambush:
            for f, d in [(T3_AM_WATCH_FILE, watch_in), (T3_AM_DAILY_FILE, daily_in)]:
                with open(f, "w", encoding="utf-8") as file: file.write(d)
            st.session_state.t3_am_watch, st.session_state.t3_am_daily = watch_in, daily_in
        else:
            for f, d in [(T3_AS_WATCH_FILE, watch_in), (T3_AS_DAILY_FILE, daily_in)]:
                with open(f, "w", encoding="utf-8") as file: file.write(d)
            st.session_state.t3_as_watch, st.session_state.t3_as_daily = watch_in, daily_in

        # 全入力コードの抽出（正規表現）
        t_codes = list(dict.fromkeys([c.upper() for c in re.findall(r'(?<![a-zA-Z0-9])[a-zA-Z0-9]{4}(?![a-zA-Z0-9])', watch_in + " " + daily_in)]))
        
        if t_codes:
            with st.spinner(f"全 {len(t_codes)} 銘柄を物理演算中..."):
                raw_data_dict = {}
                def fetch_parallel(c):
                    api_code = c + "0"
                    data = get_single_data(api_code, 2)
                    per, pbr, mcap, roe_res = None, None, None, None
                    try:
                        import yfinance as yf
                        tk = yf.Ticker(c + ".T")
                        info = tk.info
                        per, pbr, mcap = info.get('trailingPE'), info.get('priceToBook'), info.get('marketCap')
                        if info.get('returnOnEquity'): roe_res = info['returnOnEquity'] * 100
                    except: pass
                    return c, data, per, pbr, mcap, roe_res
                
                with concurrent.futures.ThreadPoolExecutor(max_workers=5) as exe:
                    futs = [exe.submit(fetch_parallel, c) for c in t_codes]
                    for f in concurrent.futures.as_completed(futs):
                        res_c, res_data, res_per, res_pbr, res_mcap, res_roe = f.result()
                        raw_data_dict[res_c] = {"data": res_data, "per": res_per, "pbr": res_pbr, "mcap": res_mcap, "roe": res_roe}

                scope_results = []
                for c in t_codes:
                    raw_s = raw_data_dict.get(c)
                    if not raw_s or not raw_s["data"]: continue
                    df_s = clean_df(pd.DataFrame(raw_s["data"].get("bars", [])))
                    if len(df_s) < 35: continue
                    df_chart = calc_technicals(df_s.copy())
                    latest = df_chart.iloc[-1]; lc = latest['AdjC']
                    rsi_v, atr_v = latest.get('RSI', 50), int(latest.get('ATR', 0))
                    win_14 = df_s.tail(15).iloc[:-1]; h14 = win_14['AdjH'].max(); l14 = win_14['AdjL'].min(); ur = h14 - l14
                    is_dt = check_double_top(df_s.tail(31).iloc[:-1]); is_hs = check_head_shoulders(df_s.tail(31).iloc[:-1])
                    
                    if is_ambush:
                        bt_val = int(h14 - (ur * (st.session_state.push_r / 100.0)))
                        dist_p = ((lc / bt_val) - 1) * 100
                        # 💎 判定ロジック：圏外緩和（-10%まで許容）
                        if dist_p < -10.0: rank, bg = "圏外💀", "#d32f2f"
                        elif dist_p <= 2.0: rank, bg = ("S🔥", "#2e7d32") if rsi_v <= 45 else ("A⚡", "#ed6c02")
                        elif dist_p <= 10.0: rank, bg = ("B📈", "#0288d1")
                        else: rank, bg = ("C👁️", "#616161")
                        reach_rate = ((h14 - lc) / (h14 - bt_val) * 100) if (h14 - bt_val) > 0 else 0
                    else:
                        bt_val = int(max(h14, lc + (atr_v * 0.5)))
                        h_p_macd = df_chart['MACD_Hist'].tail(5).values
                        gc_days = 1 if h_p_macd[-2] < 0 and h_p_macd[-1] >= 0 else 2 if h_p_macd[-3] < 0 and h_p_macd[-1] >= 0 else 0
                        rank, bg, t_score, _ = get_assault_triage_info(gc_days, lc, rsi_v, df_chart, is_strict=True)
                        reach_rate = 100 - rsi_v

                    c_name, c_market = f"銘柄 {c}", "不明"
                    if not master_df.empty:
                        target_5 = c + "0"
                        m_row = master_df[master_df['Code'] == target_5]
                        if not m_row.empty: c_name, c_market = m_row.iloc[0]['CompanyName'], m_row.iloc[0]['Market']

                    scope_results.append({
                        'code': c, 'name': c_name, 'lc': lc, 'h14': h14, 'l14': l14, 'ur': ur, 'bt_val': bt_val, 'atr_val': atr_v, 'rsi': rsi_v,
                        'is_dt': is_dt, 'is_hs': is_hs, 'rank': rank, 'bg': bg, 'reach_val': reach_rate, 'df_chart': df_chart, 
                        'per': raw_s['per'], 'pbr': raw_s['pbr'], 'mcap': raw_s['mcap'], 'roe': raw_s['roe'],
                        'source': "🛡️ 監視" if c in watch_in else "🚀 新規", 'market': c_market
                    })

                rank_order = {"S🔥": 4, "S": 4, "A⚡": 3, "A": 3, "B📈": 2, "B": 2, "C👁️": 1, "C": 1}
                scope_results = sorted(scope_results, key=lambda x: (rank_order.get(x['rank'], 0), x['reach_val']), reverse=True)

                for r in scope_results:
                    st.divider()
                    m_l = str(r['market']).lower()
                    if 'プライム' in m_l or '一部' in m_l: m_badge = '<span style="background-color: #1a237e; color: #ffffff; padding: 0.2rem 0.6rem; border-radius: 4px; font-size: 11px; font-weight: bold;">🏢 プライム/大型</span>'
                    elif 'スタンダード' in m_l or 'グロース' in m_l or 'マザーズ' in m_l: m_badge = '<span style="background-color: #1b5e20; color: #ffffff; padding: 0.2rem 0.6rem; border-radius: 4px; font-size: 11px; font-weight: bold;">🚀 中小型</span>'
                    else: m_badge = f'<span style="background-color: #455a64; color: #ffffff; padding: 0.2rem 0.6rem; border-radius: 4px; font-size: 11px; font-weight: bold;">{r["market"]}</span>'

                    s_badge = f"<span style='background-color:{'#42a5f5' if '監視' in r['source'] else '#ffa726'}; color:white; padding:2px 6px; border-radius:4px; font-size:12px;'>{r['source']}</span>"
                    t_badge = f"<span style='background-color:{r['bg']}; color:white; padding:2px 8px; border-radius:4px; margin-left:10px; font-weight:bold;'>🎯 優先度: {r['rank']}</span>"
                    st.markdown(f"### {s_badge} ({r['code'][:4]}) {r['name']}\n<div style='margin-bottom: 0.8rem;'>{m_badge}{t_badge} <span style='background-color:rgba(38,166,154,0.15); color:#26a69a; padding:0.1rem 0.5rem; border-radius:4px; font-size:12px; margin-left:10px;'>RSI: {r['rsi']:.1f}%</span><span style='background-color:rgba(255,215,0,0.1); color:#FFD700; padding:0.1rem 0.5rem; border-radius:4px; font-size:12px; margin-left:5px;'>到達度: {r['reach_val']:.1f}%</span></div>", unsafe_allow_html=True)

                    if r['is_dt'] or r['is_hs']: st.error("🚨 【警告】危険波形（三尊/Wトップ等）を検知。")
                    
                    # 💎 UI黄金比レイアウト
                    sc_l, sc_m, sc_r = st.columns([2.0, 3.5, 5.5])
                    with sc_l:
                        atr_now = r['atr_val'] if r['atr_val'] > 0 else r['lc'] * 0.05
                        c_m1, c_m2 = st.columns(2); c_m1.metric("直近高値", f"{int(r['h14']):,}円"); c_m2.metric("最新終値", f"{int(r['lc']):,}円")
                        st.metric("🌪️ 1ATR", f"{int(atr_now):,}円", f"ボラ: {(atr_now/r['lc'])*100:.1f}%", delta_color="off")
                    
                    with sc_m:
                        per_c = "#26a69a" if (r['per'] and r['per'] <= 50) else "#ef5350"
                        pbr_c = "#26a69a" if (r['pbr'] and r['pbr'] <= 5.0) else "#ef5350"
                        roe_c = "#26a69a" if (r['roe'] and r['roe'] >= 10) else "#ef5350"
                        pv = f"{r['per']:.1f}倍" if r['per'] else "-"
                        pbv = f"{r['pbr']:.2f}倍" if r['pbr'] else "-"
                        rv = f"{r['roe']:.1f}%" if r['roe'] else "-"
                        mc_v = f"{int(r['mcap']/1e8):,}億円" if r['mcap'] else "-"
                        
                        h_metrics = f"""
                            <div style='display:flex; justify-content:space-between; text-align:center; margin-top:8px;'>
                                <div style='flex:1;'><div style='font-size:11px; color:#888;'>📊 PER</div><div style='font-size:1.3rem; color:{per_c}; font-weight:bold;'>{pv}</div></div>
                                <div style='flex:1;'><div style='font-size:11px; color:#888;'>📉 PBR</div><div style='font-size:1.3rem; color:{pbr_c}; font-weight:bold;'>{pbv}</div></div>
                                <div style='flex:1;'><div style='font-size:11px; color:#888;'>📡 ROE</div><div style='font-size:1.3rem; color:{roe_c}; font-weight:bold;'>{rv}</div></div>
                            </div>
                            <div style='text-align:center; margin-top:10px; border-top:1px solid rgba(255,255,255,0.1); padding-top:5px;'>
                                <div style='font-size:11px; color:#888;'>💰 時価総額</div><div style='font-size:1.3rem; color:#fff; font-weight:bold;'>{mc_v}</div>
                            </div>"""
                        st.markdown(f"<div style='background:rgba(255,215,0,0.05); padding:1rem; border-radius:10px; border:1px solid rgba(255,215,0,0.3); text-align:center;'><div style='font-size:14px; color:#FFD700;'>{'🎯 買値目標' if is_ambush else '🎯 トリガー'}</div><div style='font-size:2.4rem; font-weight:bold; color:#FFD700;'>{int(r['bt_val']):,}円</div>{h_metrics}</div>", unsafe_allow_html=True)

                    with sc_r:
                        c_t = r['bt_val']; atr_ref = r['atr_val'] if r['atr_val'] > 0 else c_t * 0.05
                        vol_sig = (atr_ref / r['lc']) * 100; wave_sig = (r['ur'] / r['l14']) * 100 if r['l14'] > 0 else 0
                        tn_ratio = wave_sig / vol_sig if vol_sig > 0 else 0
                        rec_tp_atr = 3.0 if tn_ratio >= 5.0 else 2.0 if tn_ratio >= 2.5 else 1.0
                        
                        html_mat = f"<div style='background:rgba(255,255,255,0.03); padding:1.2rem; border-radius:8px; border-left:5px solid #FFD700;'><div style='font-size:16px; color:#aaa; margin-bottom:14px; font-weight:bold; border-bottom:1px solid #444; padding-bottom:6px;'>📊 動的ATRマトリクス (基準:{int(c_t):,}円 | T/N比: {tn_ratio:.1f})</div><div style='display:flex; gap:20px;'><div style='flex:1;'>"
                        html_mat += "<div style='color:#26a69a; border-bottom:2px solid #26a69a; margin-bottom:10px; font-size:14px; font-weight:bold;'>【利確目安】</div>"
                        for m in [0.5, 1.0, 2.0, 3.0]: 
                            val = int(c_t + (atr_ref * m)); diff_p = ((val / c_t) - 1) * 100
                            style = "background:rgba(38,166,154,0.15); border-radius:4px; padding:2px 4px;" if m == rec_tp_atr else "padding:2px 4px;"
                            html_mat += f"<div style='display:flex; justify-content:space-between; align-items:center; font-size:16px; margin-bottom:4px; {style}'><span>+{m}ATR{ ' ⭐' if m == rec_tp_atr else ''}</span><b>{val:,}<span style='font-size:12px; font-weight:normal; color:#888; margin-left:6px;'>(+{diff_p:.1f}%)</span></b></div>"
                        html_mat += "</div><div style='flex:1;'><div style='color:#ef5350; border-bottom:2px solid #ef5350; margin-bottom:10px; font-size:14px; font-weight:bold;'>【防衛目安】</div>"
                        for m in [0.5, 1.0, 2.0]: 
                            val = int(c_t - (atr_ref * m)); diff_p = ((val / c_t) - 1) * 100
                            style = "background:rgba(239,83,80,0.15); border:1px solid rgba(239,83,80,0.5); border-radius:4px; padding:2px 4px;" if m == 1.0 else "padding:2px 4px;"
                            html_mat += f"<div style='display:flex; justify-content:space-between; align-items:center; font-size:16px; margin-bottom:4px; {style}'><span>-{m}ATR{ ' 🛡️' if m == 1.0 else ''}</span><b>{val:,}<span style='font-size:12px; font-weight:normal; color:#888; margin-left:6px;'>({diff_p:.1f}%)</span></b></div>"
                        st.markdown(html_mat + "</div></div></div>", unsafe_allow_html=True)
                    
                    st.markdown("---")
                    df_p = r['df_chart'].tail(100).copy(); df_p['d_str'] = df_p['Date'].dt.strftime('%m/%d')
                    fig = go.Figure(data=[go.Candlestick(x=df_p['d_str'], open=df_p['AdjO'], high=df_p['AdjH'], low=df_p['AdjL'], close=df_p['AdjC'], name="価格", increasing_line_color='#26a69a', decreasing_line_color='#ef5350')])
                    for ma, n, col in [('MA5','5日','#ffca28'),('MA25','25日','#42a5f5'),('MA75','75日','#ab47bc')]: fig.add_trace(go.Scatter(x=df_p['d_str'], y=df_p[ma], name=n, mode='lines', line=dict(color=col, width=1.5)))
                    fig.add_trace(go.Scatter(x=df_p['d_str'], y=[r['bt_val']]*len(df_p), name="目標", mode='lines', line=dict(color='#FFD700', width=2, dash='dot')))
                    # 💎 凡例高度 y=-0.22
                    fig.update_layout(height=450, margin=dict(l=0, r=0, t=10, b=50), xaxis_rangeslider_visible=False, paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)', hovermode="x unified", yaxis=dict(side='right', tickformat=",.0f"), xaxis=dict(type='category', dtick=5), showlegend=True, legend=dict(orientation="h", yanchor="bottom", y=-0.22, xanchor="center", x=0.5))
                    st.plotly_chart(fig, use_container_width=True, config={'displayModeBar': False})
                        
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

    # JSONリカバリー回路
    if st.session_state.get("sim_tp_val", 0) == 0: st.session_state.sim_tp_val = 10
    if st.session_state.get("sim_sl_val", 0) == 0: st.session_state.sim_sl_val = 8
    if st.session_state.get("sim_limit_d_val", 0) == 0: st.session_state.sim_limit_d_val = 4
    if st.session_state.get("sim_sell_d_val", 0) == 0: st.session_state.sim_sell_d_val = 10
    if st.session_state.get("sim_push_r_val", 0) == 0: st.session_state.sim_push_r_val = st.session_state.get("push_r", 50.0)
    if st.session_state.get("sim_pass_req_val", 0) == 0: st.session_state.sim_pass_req_val = 7
    if st.session_state.get("sim_rsi_lim_ambush_val", 0) == 0: st.session_state.sim_rsi_lim_ambush_val = 45
    if st.session_state.get("sim_rsi_lim_assault_val", 0) == 0: st.session_state.sim_rsi_lim_assault_val = 70
    if st.session_state.get("sim_time_risk_val", 0) == 0: st.session_state.sim_time_risk_val = 5
    
    # 🚨 双方向同期機構
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
        run_bt = st.button("🔥 仮想実弾テスト実行", use_container_width=True, type="primary")
        optimize_bt = st.button("🚀 戦術の黄金比率を抽出 (最適化)", use_container_width=True)
        
    with col_b2:
        st.markdown("#### ⚙️ 戦術パラメーター（演習用チューニング）")
        cp1, cp2, cp3, cp4 = st.columns(4)
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
            ct2.number_input("時間リスク上限", step=1, key="_ui_risk", on_change=sync_param, args=("_ui_risk", "sim_time_risk_val"))

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
            
            with st.spinner("データを取得・解析中..."):
                preloaded_data = {}
                for c in t_codes:
                    raw = get_single_data(c + "0", 2)
                    if not raw or not raw.get('bars'): continue
                    temp_df = pd.DataFrame(raw['bars'])
                    if temp_df.empty: continue
                    try: 
                        processed_df = calc_technicals(clean_df(temp_df))
                        if processed_df is not None and len(processed_df) >= 35:
                            preloaded_data[c] = processed_df
                    except: continue

            if not preloaded_data:
                st.error("解析可能なデータがありません。")
                st.stop()
                
            opt_results = []
            total_iterations = len(p1_range) * len(p2_range)
            current_iter = 0
            p_bar = st.progress(0, "シミュレーション中...")

            for t_p1 in p1_range:
                for t_p2 in p2_range:
                    current_iter += 1
                    all_t = []
                    for c, df in preloaded_data.items():
                        pos = None
                        for i in range(35, len(df)):
                            td = df.iloc[i]; prev = df.iloc[i-1]
                            if pos is None:
                                win_14 = df.iloc[i-15:i-1]; win_30 = df.iloc[i-31:i-1]
                                lc_prev = prev['AdjC']; atr_prev = prev.get('ATR', 0)
                                h14 = win_14['AdjH'].max(); l14 = win_14['AdjL'].min()
                                if pd.isna(h14) or pd.isna(l14) or l14 <= 0: continue
                                
                                if is_ambush:
                                    r14 = h14 / l14; rsi_prev = prev.get('RSI', 50)
                                    idxmax = win_14['AdjH'].idxmax()
                                    d_high = len(win_14[win_14['Date'] > win_14.loc[idxmax, 'Date']]) if pd.notna(idxmax) else 0
                                    bt_val = int(h14 - ((h14 - l14) * (t_p1 / 100.0)))
                                    if rsi_prev > sim_rsi_lim_ambush: continue
                                    score = 4
                                    if 1.3 <= r14 <= 2.0: score += 1
                                    if d_high <= sim_limit_d: score += 1 
                                    if not check_double_top(win_30): score += 1
                                    if not check_head_shoulders(win_30): score += 1
                                    if bt_val * 0.85 <= lc_prev <= bt_val * 1.35: score += 1
                                    
                                    if score >= t_p2:
                                        if td['AdjL'] <= bt_val:
                                            pos = {'b_i': i, 'b_d': td['Date'], 'b_p': min(td['AdjO'], bt_val)}
                                else:
                                    rsi_prev = prev.get('RSI', 50); exp_days = int((lc_prev * (t_p2/100.0)) / atr_prev) if atr_prev > 0 else 99
                                    if prev.get('MACD_Hist', 0) > 0 and df.iloc[i-2].get('MACD_Hist', 0) <= 0 and rsi_prev <= t_p1 and exp_days < sim_time_risk:
                                        trig_p = max(h14, lc_prev + (atr_prev * 0.5))
                                        if td['AdjH'] >= trig_p:
                                            pos = {'b_i': i, 'b_d': td['Date'], 'b_p': max(td['AdjO'], trig_p), 'entry_atr': atr_prev}
                            else:
                                bp = pos['b_p']; held = i - pos['b_i']; sp = 0
                                current_tp = sim_tp if is_ambush else t_p2
                                sl_val = bp - (pos.get('entry_atr', prev.get('ATR', 0)) * 1.0)
                                tp_val = bp * (1 + (current_tp / 100.0))
                                
                                if td['AdjL'] <= sl_val: sp = min(td['AdjO'], sl_val)
                                elif td['AdjH'] >= tp_val: sp = max(td['AdjO'], tp_val)
                                elif held >= sim_sell_d: sp = td['AdjC']
                                
                                if sp > 0:
                                    p_pct = round(((sp / bp) - 1) * 100, 2)
                                    p_amt = int((sp - bp) * st.session_state.bt_lot)
                                    all_t.append({'銘柄': c, '決済日': td['Date'], '買値': int(bp), '売値': int(sp), '損益(%)': p_pct, '損益額': p_amt})
                                    pos = None
                                    
                    if all_t:
                        tdf = pd.DataFrame(all_t)
                        opt_results.append({p1_name: t_p1, p2_name: t_p2, '利益': tdf['損益額'].sum(), '勝率': len(tdf[tdf['損益額']>0])/len(tdf), '回数': len(tdf), 'data': tdf})
                    p_bar.progress(current_iter / total_iterations)
            
            p_bar.empty()
            if optimize_bt and opt_results:
                opt_df = pd.DataFrame(opt_results).sort_values('利益', ascending=False)
                best = opt_df.iloc[0]
                st.markdown(f"### 🏆 最適化結果: 推奨 {p1_name} {best[p1_name]}")
                c1, c2, c3 = st.columns(3)
                c1.metric("利益", f"{int(best['利益']):,}円"); c2.metric("勝率", f"{best['勝率']*100:.1f}%"); c3.metric("取引数", f"{best['回数']}回")
                st.dataframe(opt_df.drop(columns=['data']), use_container_width=True)
            elif run_bt and opt_results:
                tdf = opt_results[0]['data'].sort_values('決済日').reset_index(drop=True)
                tdf['累積'] = tdf['損益額'].cumsum()
                st.success("🎯 バックテスト完了。")
                import plotly.express as px
                fig = px.line(tdf, x='決済日', y='累積', title="仮想資産推移", markers=True)
                fig.update_layout(paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0.1)')
                st.plotly_chart(fig, use_container_width=True)
                st.dataframe(tdf.style.format({'買値': '{:,}', '売値': '{:,}', '損益額': '{:,}'}), use_container_width=True)

with tab5:
    st.markdown('<h3 style="font-size: clamp(14px, 4.5vw, 24px); margin-bottom: 1rem;">📡 交戦モニター (全軍生存圏レーダー)</h3>', unsafe_allow_html=True)
    FRONTLINE_FILE_PATH = f"saved_frontline_{user_id}.csv"
    
    if 'frontline_df' not in st.session_state:
        if os.path.exists(FRONTLINE_FILE_PATH):
            try:
                tmp_df = pd.read_csv(FRONTLINE_FILE_PATH)
                tmp_df["銘柄"] = tmp_df["銘柄"].astype(str)
                st.session_state.frontline_df = tmp_df
            except:
                st.session_state.frontline_df = pd.DataFrame([{"銘柄": "4259", "買値": 668.0, "第1利確": 688.0, "第2利確": 714.0, "損切": 627.0, "現在値": 681.0}])
        else:
            st.session_state.frontline_df = pd.DataFrame([{"銘柄": "4259", "買値": 668.0, "第1利確": 688.0, "第2利確": 714.0, "損切": 627.0, "現在値": 681.0}])

    if st.button("🔄 全軍の現在値を同期 (yfinance)", use_container_width=True):
        import yfinance as yf
        updated_fr_sync = False
        for idx_fr, row_fr in st.session_state.frontline_df.iterrows():
            c_fr_sync = str(row_fr['銘柄']).strip()
            if len(c_fr_sync) >= 4:
                try:
                    tk_fr_sync = yf.Ticker(c_fr_sync[:4] + ".T")
                    h_fr_sync = tk_fr_sync.history(period="1d")
                    if not h_fr_sync.empty:
                        st.session_state.frontline_df.at[idx_fr, '現在値'] = round(h_fr_sync['Close'].iloc[-1], 1)
                        updated_fr_sync = True
                except: pass
        if updated_fr_sync:
            st.session_state.frontline_df.to_csv(FRONTLINE_FILE_PATH, index=False)
            st.rerun()

    edited_frontline_df = st.data_editor(st.session_state.frontline_df, num_rows="dynamic", use_container_width=True, key="frontline_editor_v24_final")
    if not edited_frontline_df.equals(st.session_state.frontline_df):
        st.session_state.frontline_df = edited_frontline_df
        edited_frontline_df.to_csv(FRONTLINE_FILE_PATH, index=False)
        st.rerun()

    # 💎 物理修復：型の安全性を確保し、N/Aを除外
    df_render = edited_frontline_df.copy()
    for col in ["買値", "第1利確", "第2利確", "損切", "現在値"]:
        if col in df_render.columns:
            df_render[col] = pd.to_numeric(df_render[col], errors='coerce')

    st.markdown("---")
    for idx_mon, r_mon in df_render.iterrows():
        t_m, b_m, tp1_m, tp2_m, s_m, c_m = str(r_mon.get('銘柄', '')), r_mon.get('買値'), r_mon.get('第1利確'), r_mon.get('第2利確'), r_mon.get('損切'), r_mon.get('現在値')
        if not t_m or pd.isna(b_m) or pd.isna(c_m): continue
            
        if c_m <= s_m: col_m, txt_m = "#ef5350", "💀 被弾（防衛線突破）"
        elif c_m < b_m: col_m, txt_m = "#ff9800", "⚠️ 警戒（損切圏内）"
        elif tp1_m > 0 and c_m < tp1_m: col_m, txt_m = "#26a69a", "🟢 巡航（第1目標へ）"
        elif tp2_m > 0 and c_m < tp2_m: col_m, txt_m = "#42a5f5", "🛡️ 無敵化（第2目標へ）"
        else: col_m, txt_m = "#ab47bc", "🏆 任務完了（利確推奨）"
        
        st.markdown(f'<div style="background: rgba(255,255,255,0.03); padding: 12px; border-radius: 8px; border-left: 5px solid {col_m}; margin-bottom: 5px;"><strong>部隊 [{t_m}]</strong> {txt_m} ｜ 現在: ¥{int(c_m):,} (買: ¥{int(b_m):,})</div>', unsafe_allow_html=True)
        
        # 💎 物理修復：バー表示エンジン（Plotly Scatter）
        fig_mon = go.Figure()
        # 目標マーカーの設置
        fig_mon.add_trace(go.Scatter(
            x=[s_m, b_m, tp1_m, tp2_m], y=[0, 0, 0, 0], mode='markers', 
            marker=dict(size=12, color=['#ef5350', '#ffca28', '#26a69a', '#42a5f5']), 
            hoverinfo='x', name="目標"
        ))
        # 現在値クロスの設置
        fig_mon.add_trace(go.Scatter(
            x=[c_m], y=[0], mode='markers', 
            marker=dict(size=22, symbol='cross-thin', line=dict(width=3, color=col_m)), 
            hoverinfo='x', name="現在地"
        ))
        # 💎 レイアウト修復：Rangeを動的にしてバーを必ず表示
        fig_mon.update_layout(
            height=80, margin=dict(l=10, r=10, t=10, b=25), 
            paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(255,255,255,0.05)', 
            yaxis=dict(visible=False), 
            xaxis=dict(showgrid=True, gridcolor='rgba(255,255,255,0.1)', tickformat=",.0f", zeroline=False)
        )
        st.plotly_chart(fig_mon, use_container_width=True, config={'displayModeBar': False})
        
with tab6:
    st.markdown('<h3 style="font-size: clamp(14px, 4.5vw, 24px); margin-bottom: 1rem;">📁 事後任務報告 (AAR) & 総合戦績</h3>', unsafe_allow_html=True)
    AAR_LOG_FILE = f"saved_aar_log_{user_id}.csv"
    
    if os.path.exists(AAR_LOG_FILE):
        try:
            aar_df_final = pd.read_csv(AAR_LOG_FILE)
            aar_df_final['決済日'] = aar_df_final['決済日'].astype(str)
            aar_df_final['銘柄'] = aar_df_final['銘柄'].astype(str)
        except:
            aar_df_final = pd.DataFrame(columns=["決済日", "銘柄", "戦術", "買値", "売値", "株数", "損益額(円)", "損益(%)", "規律", "メモ"])
    else:
        aar_df_final = pd.DataFrame(columns=["決済日", "銘柄", "戦術", "買値", "売値", "株数", "損益額(円)", "損益(%)", "規律", "メモ"])

    # 💎 物理復旧：CSV自動解析インポート
    st.markdown("#### 📥 取引履歴CSVの一括同期")
    with st.expander("過去ログの物理結合（証券会社の約定履歴CSV）", expanded=False):
        uploaded_csv = st.file_uploader("約定履歴CSVを選択", type=["csv"], key="aar_csv_uploader_fix")
        if uploaded_csv is not None:
            if st.button("💾 CSVから戦績を抽出して保存", use_container_width=True):
                try:
                    import io
                    raw_data = uploaded_csv.getvalue()
                    try: content = raw_data.decode('utf-8')
                    except: content = raw_data.decode('shift_jis', errors='replace')
                    
                    lines = content.splitlines()
                    h_idx = -1
                    for i, line in enumerate(lines):
                        if "約定日" in line and "銘柄" in line: h_idx = i; break
                    
                    if h_idx != -1:
                        df_csv = pd.read_csv(io.StringIO("\n".join(lines[h_idx:])))
                        df_csv = df_csv[df_csv['取引'].astype(str).str.contains('現物')].copy()
                        records = []
                        for code, group in df_csv.groupby('銘柄コード'):
                            buys, sells = [], []
                            for _, r in group.iterrows():
                                item = {'date': str(r['約定日']).replace('/', '-'), 'qty': int(r['約定数量']), 'price': float(r['約定単価']), 'code': str(code)}
                                if "買" in str(r['取引']): buys.append(item)
                                elif "売" in str(r['取引']): sells.append(item)
                            buys.sort(key=lambda x: x['date']); sells.sort(key=lambda x: x['date'])
                            for s in sells:
                                s_qty, m_qty, m_amt = s['qty'], 0, 0
                                while s_qty > 0 and len(buys) > 0:
                                    b = buys[0]
                                    if b['qty'] <= s_qty:
                                        m_qty += b['qty']; m_amt += b['price']*b['qty']; s_qty -= b['qty']; buys.pop(0)
                                    else:
                                        m_qty += s_qty; m_amt += b['price']*s_qty; b['qty'] -= s_qty; s_qty = 0
                                if m_qty > 0:
                                    avg_b = m_amt / m_qty
                                    records.append({
                                        "決済日": s['date'], "銘柄": s['code'], "戦術": "自動解析",
                                        "買値": round(avg_b, 1), "売値": round(s['price'], 1), "株数": int(m_qty),
                                        "損益額(円)": int((s['price'] - avg_b) * m_qty), "損益(%)": round(((s['price']/avg_b)-1)*100, 2),
                                        "規律": "不明", "メモ": "CSV同期"
                                    })
                        if records:
                            new_df = pd.DataFrame(records)
                            aar_df_final = pd.concat([aar_df_final, new_df]).drop_duplicates(subset=["決済日", "銘柄", "買値", "売値", "株数"]).reset_index(drop=True)
                            aar_df_final.to_csv(AAR_LOG_FILE, index=False)
                            st.success("物理同期完了。")
                            st.rerun()
                except Exception as e: st.error(f"同期失敗：{e}")

    st.divider()
    col_aar1, col_aar2 = st.columns([1, 2.2])
    
    with col_aar1:
        st.markdown("#### 📝 新規戦果報告")
        with st.form("aar_form_v24_final"):
            d_aar = st.date_input("決済日", datetime.today())
            c_aar = st.text_input("銘柄コード")
            t_aar = st.selectbox("戦術", ["待伏", "強襲", "他"])
            b_aar = st.number_input("買値", min_value=0.0, step=1.0)
            s_aar = st.number_input("売値", min_value=0.0, step=1.0)
            l_aar = st.number_input("株数", min_value=0, step=100)
            r_aar = st.radio("規律", ["遵守", "違反"])
            m_aar = st.text_input("メモ")
            if st.form_submit_button("記録を保存"):
                if c_aar and b_aar > 0:
                    p_aar = int((s_aar - b_aar) * l_aar)
                    pp_aar = round(((s_aar / b_aar) - 1) * 100, 2)
                    nd = pd.DataFrame([{
                        "決済日": d_aar.strftime("%Y-%m-%d"), "銘柄": c_aar, "戦術": t_aar, "買値": b_aar, 
                        "売値": s_aar, "株数": l_aar, "損益額(円)": p_aar, "損益(%)": pp_aar, "規律": r_aar, "メモ": m_aar
                    }])
                    pd.concat([nd, aar_df_final]).to_csv(AAR_LOG_FILE, index=False)
                    st.rerun()

    with col_aar2:
        if not aar_df_final.empty:
            df_calc = aar_df_final.copy()
            df_calc["損益額(円)"] = pd.to_numeric(df_calc["損益額(円)"], errors='coerce')
            tot_p = df_calc["損益額(円)"].sum()
            w_rate = (len(df_calc[df_calc["損益額(円)"] > 0]) / len(df_calc)) * 100
            
            m1, m2, m3 = st.columns(3)
            m1.metric("総損益", f"{int(tot_p):,}円")
            m2.metric("勝率", f"{w_rate:.1f}%")
            m3.metric("規律遵守率", f"{(len(df_calc[df_calc['規律']=='遵守'])/len(df_calc))*100:.1f}%")
            
            import plotly.express as px
            df_calc['決済日'] = pd.to_datetime(df_calc['決済日'])
            tdf_curve = df_calc.sort_values('決済日')
            tdf_curve['累積'] = tdf_curve['損益額(円)'].cumsum()
            fig_eq = px.line(tdf_curve, x='決済日', y='累積', title="実資産推移", markers=True)
            fig_eq.update_traces(line_color='#26a69a')
            fig_eq.update_layout(paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0.1)', height=250, margin=dict(l=0, r=0, t=30, b=0))
            st.plotly_chart(fig_eq, use_container_width=True)

    # 戦歴データベース
    if not aar_df_final.empty:
        st.markdown("##### 📜 詳細交戦記録（キル・ログ）")
        st.dataframe(aar_df_final, use_container_width=True)
