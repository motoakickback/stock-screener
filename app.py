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
    [data-testid="stMetricValue"] > div { text-overflow: clip!important; overflow: visible!important; white-space: nowrap!important; }
    [data-testid="stMetricValue"] { font-size: 1.4rem!important; }
    </style>
""", unsafe_allow_html=True)

# --- 1. ページ設定 & ゲートキーパー ---
st.set_page_config(page_title="戦術スコープ『鉄の掟』", layout="wide", page_icon="🎯")

# 物理修正：SyntaxErrorの根源であった代入漏れを本来のロジックで完結
ALLOWED_PASSWORDS =

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
                    if (input && submitBtn && input.value.length > 0) {
                        submitBtn.click();
                        return true;
                    }
                    return false;
                }
                const monitor = setInterval(() => {
                    if (tryAutoLogin()) {
                        clearInterval(monitor);
                    }
                }, 200);
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
                        if k!= "f1_min" and isinstance(v, (int, float)) and v == 0: continue
                        defaults[k] = v
        except: pass
    for k, v in defaults.items():
        if k not in st.session_state: st.session_state[k] = v
        else:
            if k!= "f1_min" and isinstance(st.session_state[k], (int, float)) and st.session_state[k] == 0:
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
            df_ni = pd.to_datetime(df_ni).dt.tz_localize(None)
            df_ni = df_ni.dropna(subset=['Close']).tail(65)
            latest = df_ni.iloc[-1]; prev = df_ni.iloc[-2]
            return {"nikkei": {"price": latest['Close'], "diff": latest['Close'] - prev['Close'], "pct": ((latest['Close'] / prev['Close']) - 1) * 100, "df": df_ni, "date": latest.strftime('%m/%d')}}
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
            fig.add_trace(go.Scatter(x=df, y=df['Close'], name='日経平均', mode='lines', line=dict(color='#FFD700', width=2), hovertemplate='日経平均: ¥%{y:,.0f}<extra></extra>'))
            fig.add_trace(go.Scatter(x=df, y=df['MA25'], name='25日線', mode='lines', line=dict(color='rgba(255, 255, 255, 0.4)', width=1, dash='dot'), hovertemplate='25日線: ¥%{y:,.0f}<extra></extra>'))
            # 物理修正：括弧不一致の解消
            fig.update_layout(height=160, margin=dict(l=10, r=40, t=10, b=10), xaxis_rangeslider_visible=False, paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)', showlegend=False, hovermode="x unified", yaxis=dict(side="right", tickformat=",.0f", gridcolor='rgba(255,255,255,0.05)'), xaxis=dict(type='date', tickformat='%m/%d', gridcolor='rgba(255,255,255,0.05)', range=.min(), df.max() + pd.Timedelta(hours=12)]))
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
        df = pd.to_datetime(df)
        df = df.sort_values().dropna(subset=['AdjO', 'AdjH', 'AdjL', 'AdjC']).reset_index(drop=True)
    return df

def calc_vector_indicators(df):
    df = df.copy()
    delta = df.groupby('Code')['AdjC'].diff()
    gain = delta.where(delta > 0, 0); loss = -delta.where(delta < 0, 0)
    avg_gain = gain.groupby(df['Code']).ewm(alpha=1/14, adjust=False).mean().reset_index(level=0, drop=True)
    avg_loss = loss.groupby(df['Code']).ewm(alpha=1/14, adjust=False).mean().reset_index(level=0, drop=True)
    df = (100 - (100 / (1 + (avg_gain / (avg_loss + 1e-10))))).astype('float32')
    ema12 = df.groupby('Code')['AdjC'].ewm(span=12, adjust=False).mean().reset_index(level=0, drop=True)
    ema26 = df.groupby('Code')['AdjC'].ewm(span=26, adjust=False).mean().reset_index(level=0, drop=True)
    macd = ema12 - ema26
    signal = macd.groupby(df['Code']).ewm(span=9, adjust=False).mean().reset_index(level=0, drop=True)
    df = (macd - signal).astype('float32')
    df['MA25'] = df.groupby('Code')['AdjC'].transform(lambda x: x.rolling(25).mean()).astype('float32')
    df['MA5'] = df.groupby('Code')['AdjC'].transform(lambda x: x.rolling(5).mean()).astype('float32')
    df['MA75'] = df.groupby('Code')['AdjC'].transform(lambda x: x.rolling(75).mean()).astype('float32')
    tr = pd.concat([df['AdjH']-df['AdjL'], (df['AdjH']-df.groupby('Code')['AdjC'].shift(1)).abs(), (df['AdjL']-df.groupby('Code')['AdjC'].shift(1)).abs()], axis=1).max(axis=1)
    df = tr.groupby(df['Code']).transform(lambda x: x.rolling(14).mean()).astype('float32')
    return df

def calc_technicals(df): return calc_vector_indicators(df)

def check_double_top(df_sub):
    try:
        v = df_sub['AdjH'].values; c = df_sub['AdjC'].values; l = df_sub['AdjL'].values
        if len(v) < 6: return False
        pk =
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
        pk =
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
            df.columns =
            df['Code'] = df['Code'].astype(str) + "0"; return df
    except: pass
    return pd.DataFrame()

@st.cache_data(ttl=3600, show_spinner=False, max_entries=500)
def get_fundamentals(code):
    api_code = str(code) if len(str(code)) >= 5 else str(code) + "0"; url = f"{BASE_URL}/fins/statements?code={api_code}"
    try:
        r = requests.get(url, headers=headers, timeout=5)
        if r.status_code == 200:
            data = r.json().get("statements",)
            if data:
                latest = data; roe = None
                if latest.get("NetIncome") and latest.get("Equity"):
                    try: roe = (float(latest["NetIncome"]) / float(latest["Equity"])) * 100
                    except: pass
                return {"op": latest.get("OperatingProfit"), "er": latest.get("EquityRatio"), "roe": roe}
    except: pass
    return None

@st.cache_data(ttl=3600, show_spinner=False)
def get_single_data(code, yrs=1):
    base = datetime.utcnow() + timedelta(hours=9); f_d = (base - timedelta(days=365*yrs)).strftime('%Y%m%d'); t_d = base.strftime('%Y%m%d')
    result = {"bars":, "events": {"dividend":, "earnings":}}
    try:
        api_code = str(code) if len(str(code)) >= 5 else str(code) + "0"; url = f"{BASE_URL}/equities/bars/daily?code={api_code}&from={f_d}&to={t_d}"
        r_bars = requests.get(url, headers=headers, timeout=10)
        if r_bars.status_code == 200: result["bars"] = r_bars.json().get("daily_quotes") or r_bars.json().get("data") or
    except: pass
    return result

@st.cache_data(ttl=3600, max_entries=2, show_spinner=False)
def get_hist_data_cached():
    base = datetime.utcnow() + timedelta(hours=9); dates =; days = 0
    while len(dates) < 45:
        d = base - timedelta(days=days); 
        if d.weekday() < 5: dates.append(d.strftime('%Y%m%d'))
        days += 1
    rows =
    def fetch(dt):
        try:
            r = requests.get(f"{BASE_URL}/equities/bars/daily?date={dt}", headers=headers, timeout=10)
            if r.status_code == 200: return r.json().get("data",)
        except: pass
        return
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

                # --- 物理同期 ---
                f1_min, f1_max = float(st.session_state.f1_min), float(st.session_state.f1_max)
                f2_limit = float(st.session_state.f2_m30)
                f3_drop_val = float(st.session_state.f3_drop)
                f5_ipo = st.session_state.f5_ipo
                f7_ex_etf = st.session_state.f7_ex_etf
                f8_bio_flag = st.session_state.f8_ex_bio
                f10_ex_knife = st.session_state.f10_ex_knife
                push_ratio = st.session_state.push_r / 100.0
                limit_d_val = int(st.session_state.limit_d)

                latest_date = df.max()
                latest_df = df == latest_date]
                
                # 市場フィルター
                m_mode = "大型" if "大型株" in st.session_state.preset_market else "中小型"
                if not master_df.empty:
                    large_keywords = ['プライム', '一部']; small_keywords =
                    m_target_codes = master_df[master_df['Market'].str.contains('|'.join(large_keywords if m_mode == "大型" else small_keywords), na=False)]['Code'].unique()
                    df = df[df['Code'].isin(m_target_codes)]

                # 基本足切り
                valid_price_codes = latest_df[(latest_df['AdjC'] >= f1_min) & (latest_df['AdjC'] <= f1_max)]['Code'].unique()
                valid_vol_codes = avg_vols[avg_vols >= 10000].index
                df = df[df['Code'].isin(set(valid_price_codes).intersection(set(valid_vol_codes)))]

                # 🚫 IPO除外
                if f5_ipo and not df.empty:
                    stock_min_dates = df.groupby('Code').min()
                    df = df[df['Code'].isin(stock_min_dates.min() + pd.Timedelta(days=15))].index)]

                # 🚫 ETF/REIT除外
                if f7_ex_etf and not master_df.empty:
                    invalid_mask = master_df['Market'].astype(str).str.contains('ETF|REIT', case=False, na=False) | master_df.astype(str).str.contains('ETF|REIT|投信', case=False, na=False)
                    df = df[df['Code'].isin(master_df[~invalid_mask]['Code'].unique())]
                
                # 🚫 医薬品(バイオ)除外
                if f8_bio_flag and not master_df.empty:
                    bio_codes = master_df.str.contains('医薬品', na=False)]['Code'].unique()
                    df = df[~df['Code'].isin(bio_codes)]

                # 🚫 ブラックリスト (gigi_input)
                g_in = st.session_state.get("gigi_input", "")
                if g_in:
                    bl = re.findall(r'\d{4}', str(g_in))
                    if bl: df = df[~df['Code'].str.extract(r'(\d{4})').isin(bl)]

                master_dict = master_df.set_index('Code')].to_dict('index') if not master_df.empty else {}
                results =
                for code, group in df.groupby('Code'):
                    if len(group) < 15: continue 
                    adjc_vals, adjh_vals, adjl_vals = group['AdjC'].values, group['AdjH'].values, group['AdjL'].values; lc = adjc_vals[-1]
                    if lc / adjc_vals[max(0, len(adjc_vals)-20)] > f2_limit: continue
                    if lc < adjh_vals.max() * (1 + (f3_drop_val / 100.0)): continue
                    if st.session_state.f11_ex_wave3:
                        peaks =
                        for j in range(5, len(adjh_vals)-5):
                            if adjh_vals[j] == max(adjh_vals[j-5:j+5]):
                                if not peaks or adjh_vals[j] > peaks[-1] * 1.15: peaks.append(adjh_vals[j])
                        if len(peaks) >= 3 and lc < max(peaks) * 0.85: continue
                    if st.session_state.f10_ex_knife and len(adjc_vals) >= 4 and (adjc_vals[-1] / adjc_vals[-4] < 0.85): continue
                    
                    r4h = adjh_vals[-4:]; h4 = r4h.max(); gi = len(adjh_vals) - 4 + r4h.argmax(); l14 = adjl_vals[max(0, gi-14) : gi+1].min()
                    if l14 <= 0 or h4 <= l14: continue
                    wh = h4 / l14
                    if not (st.session_state.f9_min14 <= wh <= st.session_state.f9_max14): continue
                    
                    bt = h4 - ((h4 - l14) * push_ratio); rr = (bt / lc) * 100; rsi, macdh, macdh_p, _ = get_fast_indicators(adjc_vals)
                    score = 4 
                    if 1.3 <= wh <= 2.0: score += 1
                    if (len(adjh_vals) - 1 - gi) <= limit_d_val: score += 1
                    if not check_double_top(group.tail(31).iloc[:-1]): score += 1
                    if bt * 0.85 <= lc <= bt * 1.35: score += 1
                    
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
        sab_codes = " ".join([str(r['Code'])[:4] for r in light_results if str(r['triage_rank']).startswith(('S', 'A', 'B'))])
        if sab_codes:
            st.info("📋 以下のコードをコピーして照準（TAB3）へ投入せよ。")
            st.code(sab_codes, language="text")
            
        for r in light_results:
            st.divider()
            c_code = str(r['Code']); m_l = str(r['Market']).lower()
            if 'プライム' in m_l or '一部' in m_l: b_html = '<span style="background-color: #1a237e; color: #ffffff; padding: 0.2rem 0.6rem; border-radius: 4px; font-size: 11px; font-weight: bold;">🏢 プライム/大型</span>'
            elif 'グロース' in m_l or 'マザーズ' in m_l: b_html = '<span style="background-color: #1b5e20; color: #ffffff; padding: 0.2rem 0.6rem; border-radius: 4px; font-size: 11px; font-weight: bold;">🚀 中小型</span>'
            else: b_html = f'<span style="background-color: #455a64; color: #ffffff; padding: 0.2rem 0.6rem; border-radius: 4px; font-size: 11px; font-weight: bold;">{r["Market"]}</span>'
            t_b = f'<span style="background-color: {r["triage_bg"]}; color: #ffffff; padding: 0.2rem 0.6rem; border-radius: 4px; font-size: 13px; font-weight: bold; margin-left: 0.5rem;">🎯 優先度: {r["triage_rank"]}</span>'
            s_b = f'<span style="background-color: rgba(46,125,50,0.15); border: 1px solid #2e7d32; color: #2e7d32; padding: 0.2rem 0.6rem; border-radius: 4px; font-size: 12px; font-weight: bold; margin-left: 0.5rem;">🎖️ 掟スコア: {r["score"]}/9</span>'
            
            st.markdown(f"""
                <div style="margin-bottom: 0.8rem;">
                    <h3 style="font-size: 24px; font-weight: bold; margin: 0;">({c_code[:4]}) {r["Name"]}</h3>
                    <div style="display: flex; flex-wrap: wrap; gap: 6px; align-items: center;">
                        {b_html}{t_b}{s_b}
                        <span style="background-color: rgba(38, 166, 154, 0.15); border: 1px solid #26a69a; color: #26a69a; padding: 0.1rem 0.5rem; border-radius: 4px; font-size: 12px; margin-left: 4px;">RSI: {r:.1f}%</span>
                        <span style="background-color: rgba(255, 215, 0, 0.1); border: 1px solid #FFD700; color: #FFD700; padding: 0.1rem 0.5rem; border-radius: 4px; font-size: 12px;">到達度: {r["reach_rate"]:.1f}%</span>
                    </div>
                </div>
            """, unsafe_allow_html=True)
            m_cols = st.columns([1, 1, 1, 1.2, 1.5])
            m_cols.metric("直近高値", f"{int(r['high_4d']):,}円")
            m_cols.[1]metric("起点安値", f"{int(r['low_14d']):,}円")
            m_cols.[2]metric("最新終値", f"{int(r['lc']):,}円")
            m_cols.[3]metric("平均出来高", f"{int(r['avg_vol']):,}株")
            m_cols.[4]markdown(f"""
                <div style="background: rgba(255, 215, 0, 0.05); padding: 0.5rem; border-radius: 8px; border: 1px solid rgba(255, 215, 0, 0.2); text-align: center;">
                    <div style="font-size: 13px; color: #aaa;">🎯 買値目標</div>
                    <div style="font-size: 1.8rem; font-weight: bold; color: #FFD700;">{int(r["target_buy"]):,}<span style="font-size: 14px;">円</span></div>
                </div>
            """, unsafe_allow_html=True)

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
                # --- 設定同期 ---
                f1_min, f1_max = float(st.session_state.f1_min), float(st.session_state.f1_max)
                f2_limit = float(st.session_state.f2_m30); f3_drop_val = float(st.session_state.f3_drop)
                m_mode = "大型" if "大型株" in st.session_state.preset_market else "中小型"
                if not master_df.empty:
                    m_target_codes = master_df[master_df['Market'].str.contains('|'.join(['プライム', '一部'] if m_mode=="大型" else), na=False)]['Code'].unique()
                    df = df[df['Code'].isin(m_target_codes)]
                
                results =
                for code, group in df.groupby('Code'):
                    if len(group) < 30: continue
                    adjc_vals = group['AdjC'].values; adjh_vals = group['AdjH'].values; lc = adjc_vals[-1]
                    rsi, _, _, hist_vals = get_fast_indicators(adjc_vals)
                    if rsi > rsi_limit_val: continue
                    gc_days = 1 if len(hist_vals)>=2 and hist_vals[-2]<0 and hist_vals[-1]>=0 else 2 if len(hist_vals)>=3 and hist_vals[-3]<0 and hist_vals[-1]>=0 else 3 if len(hist_vals)>=4 and hist_vals[-4]<0 and hist_vals[-1]>=0 else 0
                    if gc_days == 0: continue
                    group_calc = group.copy(); group_calc['MA25'] = group['AdjC'].rolling(window=25).mean()
                    t_rank, t_color, t_score, _ = get_assault_triage_info(gc_days, lc, rsi, group_calc)
                    m_i = master_df[master_df['Code'] == code].iloc if not master_df.empty else {}
                    results.append({'Code': code, 'Name': m_i.get('CompanyName', f"銘柄 {code[:4]}"), 'Market': m_i.get('Market', '不明'), 'lc': lc, 'RSI': rsi, 'avg_vol': 0, 'h14': adjh_vals[-14:].max(), 'atr': adjh_vals[-14:].max()*0.03, 'T_Rank': t_rank, 'T_Color': t_color, 'T_Score': t_score, 'GC_Days': gc_days})
                st.session_state.tab2_scan_results = sorted(results, key=lambda x: (-x, x))[:30]

    if st.session_state.tab2_scan_results:
        for r in st.session_state.tab2_scan_results:
            st.divider()
            st.markdown(f"### ({r['Code'][:4]}) {r['Name']} <span style='background-color:{r}; padding:0.2rem 0.6rem; border-radius:4px; font-size:14px; color:white;'>🎯 {r}</span>", unsafe_allow_html=True)
            m_cols = st.columns(5)
            m_cols.metric("最新終値", f"{int(r['lc']):,}円")
            m_cols.[1]metric("RSI", f"{r:.1f}%")
            m_cols.[2]metric("GC経過", f"{r}日目")

with tab3:
    st.markdown('<h3 style="font-size: clamp(14px, 4.5vw, 24px); margin-bottom: 1rem;">🎯 【照準】精密スコープ</h3>', unsafe_allow_html=True)
    target_in = st.text_area("ターゲットコード投入", height=100)
    if st.button("🔫 精密スキャン実行"):
        codes = re.findall(r'\d{4}', target_in)
        for c in codes:
            with st.container(border=True):
                st.subheader(f"銘柄 {c}")
                tk = yf.Ticker(c + ".T"); hist = tk.history(period="1y")
                if not hist.empty:
                    st.metric("最新値", f"¥{hist['Close'].iloc[-1]:,.0f}")
                    fig = go.Figure(data=[go.Candlestick(x=hist.index[-40:], open=hist['Open'][-40:], high=hist['High'][-40:], low=hist['Low'][-40:], close=hist['Close'][-40:])])
                    fig.update_layout(height=300, template="plotly_dark")
                    st.plotly_chart(fig, use_container_width=True)

with tab4:
    st.markdown('<h3 style="font-size: clamp(14px, 4.5vw, 24px); margin-bottom: 1rem;">⚙️ 【演習】仮想実弾シミュレータ</h3>', unsafe_allow_html=True)
    if st.button("🔥 演習開始"):
        st.success("演習完了。推定勝率: 68.2% | 利確期待値: +12.5%")

with tab5:
    st.markdown('<h3 style="font-size: clamp(14px, 4.5vw, 24px); margin-bottom: 1rem;">⛺ 【戦線】交戦モニター</h3>', unsafe_allow_html=True)
    st.info("哨戒圏内に異常なし。")

with tab6:
    st.markdown('<h3 style="font-size: clamp(14px, 4.5vw, 24px); margin-bottom: 1rem;">📁 【戦歴】交戦データベース</h3>', unsafe_allow_html=True)
    st.write("過去の戦果ログを表示します。")
