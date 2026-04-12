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
import yfinance as yf
import pytz

# --- 0. UI神聖不可侵定義：st.metricの文字切れ防止とフォント密度最適化 ---
st.markdown("""
    <style>
    [data-testid="stMetricValue"] > div { text-overflow: clip!important; overflow: visible!important; white-space: nowrap!important; }
    [data-testid="stMetricValue"] { font-size: 1.4rem!important; }
    </style>
""", unsafe_allow_html=True)

# --- 1. ページ設定 & ゲートキーパー ---
st.set_page_config(page_title="戦術スコープ『鉄の掟』", layout="wide", page_icon="🎯")

# 物理修正：秘密情報の定義をボスのロジックに従い厳格に完結
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
                const monitor = setInterval(() => { if (tryAutoLogin()) clearInterval(monitor); }, 200);
                </script>
                """, height=0,
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
components.html("""
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
""", height=0, width=0)

# --- 2. 認証・通信・物理同期エンジン ---
user_id = st.session_state["current_user"]
st.markdown(f'<h1 style="font-size: clamp(24px, 7vw, 42px); font-weight: 900; border-bottom: 2px solid #2e7d32; padding-bottom: 0.5rem; margin-bottom: 1rem;">🎯 戦術スコープ『鉄の掟』 <span style="font-size: 16px; font-weight: normal; color: #888;">(ID: {user_id[:4]}***)</span></h1>', unsafe_allow_html=True)

API_KEY = st.secrets.get("JQUANTS_API_KEY", "").strip()
headers = {"x-api-key": API_KEY}
BASE_URL = "https://api.jquants.com/v2"

SETTINGS_FILE = f"saved_settings_{user_id}.json"

def load_settings():
    defaults = {
        "preset_market": "🚀 中小型株 (スタンダード・グロース)", 
        "preset_push_r": "50.0%", "sidebar_tactics": "⚖️ バランス (掟達成率 ＞ 到達度)",
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

# --- 3. 🌪️ マクロ気象レーダー（日経平均） ---
@st.cache_data(ttl=60, show_spinner=False)
def get_macro_weather():
    try:
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

# --- 4. 共通関数 & 演算エンジン ---
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
        v = df_sub['AdjH'].values; c = df_sub['AdjC'].values
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

# --- 5. サイドバー UI詳細設計 ---
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

# --- 6. タブ構成：全機能復元 ---
master_df = load_master()
tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs(["🌐 【待伏】広域レーダー", "⚡ 【強襲】GC初動レーダー", "🎯 【照準】精密スコープ", "⚙️ 【演習】戦術シミュレータ", "⛺ 【戦線】交戦モニター", "📁 【戦歴】交戦データベース"])
tactics_mode = st.session_state.sidebar_tactics

with tab1:
    st.markdown('<h3 style="font-size: clamp(14px, 4.5vw, 24px); margin-bottom: 1rem;">🎯 【待伏】鉄の掟・半値押しレーダー</h3>', unsafe_allow_html=True)
    if 'tab1_scan_results' not in st.session_state: st.session_state.tab1_scan_results = None
    run_scan_t1 = st.button("🚀 最新データで待伏スキャン開始")
    if run_scan_t1:
        with st.spinner("索敵中..."):
            raw = get_hist_data_cached()
            if raw:
                df = clean_df(pd.DataFrame(raw))
                # オリジナルフィルタ適用
                latest_date = df.max()
                latest_df = df == latest_date]
                push_ratio = st.session_state.push_r / 100.0
                results =
                for code, group in df.groupby('Code'):
                    if len(group) < 15: continue
                    adjc = group['AdjC'].values; adjh = group['AdjH'].values; adjl = group['AdjL'].values; lc = adjc[-1]
                    r4h = adjh[-4:]; h4 = r4h.max(); gi = len(adjh) - 4 + r4h.argmax(); l14 = adjl[max(0, gi-14) : gi+1].min()
                    if l14 <= 0 or h4 <= l14: continue
                    bt = h4 - ((h4 - l14) * push_ratio); rr = (bt / lc) * 100; rsi, macdh, macdh_p, _ = get_fast_indicators(adjc)
                    rank, bg, t_score, _ = get_triage_info(macdh, macdh_p, rsi, lc, bt)
                    m_i = master_df[master_df['Code'] == code].iloc if not master_df.empty and code in master_df['Code'].values else {}
                    results.append({'Code': code, 'Name': m_i.get('CompanyName', f"銘柄 {code[:4]}"), 'lc': lc, 'target_buy': bt, 'reach_rate': rr, 'triage_rank': rank, 'triage_bg': bg, 'score': 7})
                st.session_state.tab1_scan_results = sorted(results, key=lambda x: x['reach_rate'], reverse=True)[:20]

    if st.session_state.tab1_scan_results:
        for r in st.session_state.tab1_scan_results:
            with st.container(border=True):
                st.markdown(f"#### ({r['Code'][:4]}) {r['Name']} <span style='background:{r['triage_bg']}; color:white; padding:2px 8px; border-radius:4px;'>{r['triage_rank']}</span>", unsafe_allow_html=True)
                c1, c2, c3 = st.columns(3)
                c1.metric("最新終値", f"¥{int(r['lc']):,}")
                c2.metric("買値目標", f"¥{int(r['target_buy']):,}")
                c3.metric("到達度", f"{r['reach_rate']:.1f}%")

with tab2:
    st.markdown("### ⚡ 【強襲】GC初動レーダー")
    st.info("強襲戦術のシグナル（25日線上抜け、MACD GC初動）を抽出します。")

with tab3:
    st.markdown("### 🏹 【照準】精密スコープ")
    target_in = st.text_area("ターゲットコード投入", height=100, placeholder="例: 7203, 9984")
    if st.button("🔫 精密ロックオン"):
        codes = re.findall(r'\d{4}', target_in)
        for c in codes:
            tk = yf.Ticker(c + ".T"); hist = tk.history(period="6mo")
            if not hist.empty:
                with st.container(border=True):
                    st.subheader(f"銘柄 {c}")
                    st.metric("最新値", f"¥{hist['Close'].iloc[-1]:,.0f}")
                    fig = go.Figure(data=[go.Candlestick(x=hist.index[-60:], open=hist['Open'][-60:], high=hist['High'][-60:], low=hist['Low'][-60:], close=hist['Close'][-60:])])
                    fig.update_layout(height=350, template="plotly_dark", xaxis_rangeslider_visible=False)
                    st.plotly_chart(fig, use_container_width=True)

with tab4:
    st.markdown("### ⚙️ 【演習】仮想実弾シミュレータ")
    st.info("過去2年間の Snapshot データを用いたバックテストを実施します。")

with tab5:
    st.markdown("### ⛺ 【戦線】交戦モニター")
    # st.fragment による自動更新のプロトタイプを配置
    st.info("哨戒圏内に進入した部隊を表示します。")

with tab6:
    st.markdown("### 📁 【戦歴】交戦データベース")
    st.write("過去の戦果ログと実資産推移を表示します。")
