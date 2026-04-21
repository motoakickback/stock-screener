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
import pytz
import time # 🚨 プロファイリング用に追加

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
        # 🚨 ボスの指示通り「鉄の掟」へ修正
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

# --- 🚀 物理配線：19:00自動パージ用キャッシュキー生成 ---
def get_cache_key():
    try:
        tz = pytz.timezone('Asia/Tokyo')
        now = datetime.now(tz)
        if now.hour < 19:
            reset_base = (now - timedelta(days=1)).replace(hour=19, minute=0, second=0, microsecond=0)
        else:
            reset_base = now.replace(hour=19, minute=0, second=0, microsecond=0)
        return f"iron_rule_v2026_{reset_base.strftime('%Y%m%d_%H')}"
    except:
        return datetime.now().strftime('%Y%m%d_H')

import pytz
from datetime import datetime, timedelta

# 🚨 兵站同期クロック：19時を境にキャッシュキーを強制更新する物理ロジック
_now = datetime.now(pytz.timezone('Asia/Tokyo'))
# 19時未満なら「前日」、19時以降なら「当日」の年月日をキーにする
_logical_date = _now if _now.hour >= 19 else _now - timedelta(days=1)
cache_key = f"jquants_data_{_logical_date.strftime('%Y%m%d')}"

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
    btn.style.backgroundColor = '#1e1e1e'; btn.style.color = '#26a69a';
    btn.style.border = '1px solid #26a69a'; btn.style.padding = '12px 20px';
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

if "login_time" not in st.session_state:
    st.session_state.login_time = time.time()

st.write(f"⏱ 経過時間: {time.time() - st.session_state.login_time:.2f}秒")

# --- ⚙️ 設定の永続化 ---
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
        "gigi_input": "2134, 3350, 6172, 6740, 7647, 8783, 8836, 8925, 9318"
    }
    saved_data = {}
    if os.path.exists(SETTINGS_FILE):
        try:
            with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
                saved_data = json.load(f)
        except: pass

    for k, v in defaults.items():
        target_val = saved_data.get(k, v)
        if k not in st.session_state:
            st.session_state[k] = target_val

def save_settings():
    keys_to_save = [
        "preset_market", "preset_push_r", "sidebar_tactics", "push_r", "limit_d", "bt_lot", "bt_tp", "bt_sl_i", "bt_sl_c", "bt_sell_d", 
        "f1_min", "f1_max", "f2_m30", "f3_drop", "f5_ipo", "f6_risk", "f7_ex_etf", "f8_ex_bio", 
        "f9_min14", "f9_max14", "f10_ex_knife", "f11_ex_wave3", "f12_ex_overvalued",
        "tab2_rsi_limit", "tab2_vol_limit", "t3_scope_mode", "gigi_input"
    ]
    current_settings = {k: st.session_state[k] for k in keys_to_save if k in st.session_state}
    try:
        with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
            json.dump(current_settings, f, ensure_ascii=False, indent=4)
    except: pass

def apply_presets():
    p_rate = st.session_state.get("preset_push_r", "50.0%")
    if p_rate == "25.0%": st.session_state.push_r = 25.0
    elif p_rate == "50.0%": st.session_state.push_r = 50.0
    elif p_rate == "61.8%": st.session_state.push_r = 61.8
    save_settings()

load_settings()

# --- 🌪️ 1. マクロ気象レーダー ---
@st.cache_data(ttl=600, show_spinner=False)
def get_macro_weather():
    try:
        import yfinance as yf
        tk = yf.Ticker("^N225")
        df_raw = tk.history(period="3mo")
        if not df_raw.empty:
            df_ni = df_raw.reset_index()
            if df_ni['Date'].dt.tz is not None:
                df_ni['Date'] = df_ni['Date'].dt.tz_convert('Asia/Tokyo').dt.tz_localize(None)
            df_ni = df_ni.dropna(subset=['Close'])
            if len(df_ni) >= 2:
                latest, prev = df_ni.iloc[-1], df_ni.iloc[-2]
                return {
                    "nikkei": {
                        "price": float(latest['Close']),
                        "diff": float(latest['Close'] - prev['Close']),
                        "pct": ((float(latest['Close']) / float(prev['Close'])) - 1) * 100,
                        "df": df_ni,
                        "date": latest['Date'].strftime('%m/%d')
                    }
                }
    except: pass
    return None

def fetch_current_prices_fast(codes):
    results = {}
    tz_jst = pytz.timezone('Asia/Tokyo')
    base = datetime.now(tz_jst)
    f_d, t_d = (base - timedelta(days=7)).strftime('%Y%m%d'), base.strftime('%Y%m%d')
    def fetch_single(code):
        clean_code = str(code).replace('.0', '').strip()
        api_code = clean_code if len(clean_code) >= 5 else clean_code + "0"
        url = f"{BASE_URL}/equities/bars/daily?code={api_code}&from={f_d}&to={t_d}"
        try:
            r = requests.get(url, headers=headers, timeout=3.0)
            if r.status_code == 200:
                data = r.json().get("daily_quotes") or r.json().get("data") or []
                if data:
                    latest = sorted(data, key=lambda x: x['Date'])[-1]
                    val = latest.get("Close") or latest.get("C") or latest.get("AdjC")
                    if val is not None: return code, float(val)
        except: pass
        return code, None
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
        futs = {executor.submit(fetch_single, c): c for c in codes}
        for f in concurrent.futures.as_completed(futs):
            c_code, price = f.result()
            if price is not None: results[c_code] = price
    return results

# --- 🌪️ 2. マクロ気象・司令部通信（実戦配線） ---
# 🚨 1/3で定義済みの関数を呼び出し。定義の後方に配置し NameError を排除。
weather = get_macro_weather()
nikkei_pct_api = weather['nikkei']['pct'] if weather else 0.0

def render_macro_board():
    """日経平均 3mo ＆ MA25 精密レーダーの描画（原本 100% 復元）"""
    data = get_macro_weather()
    if data and "nikkei" in data:
        ni = data["nikkei"]
        df = ni["df"]
        
        # 🚨 カラーコード厳格化：利益=緑(#26a69a), 損失=赤(#ef5350)
        color = "#26a69a" if ni['diff'] >= 0 else "#ef5350" 
        sign = "+" if ni['diff'] >= 0 else ""
        
        # 🚨 カラム比率を調整し、グラフ側(c2)を拡大。
        c1, c2 = st.columns([1, 4]) 
        
        with c1:
            st.markdown(f"""
                <div style="background: rgba(20, 20, 20, 0.6); padding: 1.2rem; border-radius: 8px; border-left: 4px solid {color}; height: 100%; display: flex; flex-direction: column; justify-content: center;">
                    <div style="font-size: 14px; color: #aaa; margin-bottom: 8px;">🌪️ 戦場の天候 (日経平均: {ni["date"]})</div>
                    <div style="font-size: 26px; font-weight: bold; color: {color}; margin-bottom: 4px;">{ni["price"]:,.0f} 円</div>
                    <div style="font-size: 16px; color: {color};">({sign}{ni["diff"]:,.0f} / {sign}{ni["pct"]:.2f}%)</div>
                </div>
            """, unsafe_allow_html=True)
            
        with c2:
            # 🚨 3mo表示＋MA25描画＋高さ拡張
            df['MA25'] = df['Close'].rolling(window=25).mean()
            fig = go.Figure()
            
            fig.add_trace(go.Scatter(
                x=df['Date'], y=df['Close'], name='日経平均', mode='lines', 
                line=dict(color='#FFD700', width=2), 
                hovertemplate='日経平均: ¥%{y:,.0f}<extra></extra>'
            ))
            
            fig.add_trace(go.Scatter(
                x=df['Date'], y=df['MA25'], name='25日線', mode='lines', 
                line=dict(color='rgba(255, 255, 255, 0.5)', width=1.5, dash='dot'), 
                hovertemplate='25日線: ¥%{y:,.0f}<extra></extra>'
            ))
            
            y_min, y_max = df['Close'].min(), df['Close'].max()
            
            fig.update_layout(
                height=220, 
                margin=dict(l=0, r=40, t=15, b=10), 
                xaxis_rangeslider_visible=False, 
                paper_bgcolor='rgba(0,0,0,0)', 
                plot_bgcolor='rgba(0,0,0,0)', 
                showlegend=False, 
                hovermode="x unified", 
                yaxis=dict(
                    side="right", tickformat=",.0f", gridcolor='rgba(255,255,255,0.05)', 
                    autorange=True, range=[y_min * 0.98, y_max * 1.05], fixedrange=True
                ), 
                xaxis=dict(
                    type='date', tickformat='%m/%d', gridcolor='rgba(255,255,255,0.05)', 
                    range=[df['Date'].min(), df['Date'].max() + pd.Timedelta(hours=24)], fixedrange=True
                )
            )
            
            st.plotly_chart(fig, use_container_width=True, config={'displayModeBar': False, 'staticPlot': False})
            
        st.markdown("<div style='margin-bottom: 1.5rem;'></div>", unsafe_allow_html=True)
    else:
        st.warning("📡 外部気象レーダー応答なし")

render_macro_board()

# --- 3. 共通関数 & 演算エンジン ---
# 🚨 メモリ極限圧縮装甲：データ型をダウングレードし、RAM消費量を60%削減する
def clean_df(df):
    if df is None or df.empty: 
        return pd.DataFrame()
    
    # 1. 不要な列を早期に破棄してメモリ解放
    keep_cols = ['Code', 'Date', 'AdjO', 'AdjH', 'AdjL', 'AdjC', 'Volume']
    df = df[[c for c in keep_cols if c in df.columns]].copy()
    
    if 'Date' in df.columns:
        df['Date'] = pd.to_datetime(df['Date'])
        
    # 2. 巨大な float64（64ビット）を float32（32ビット）に半減圧縮
    for col in ['AdjO', 'AdjH', 'AdjL', 'AdjC', 'Volume']:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors='coerce').astype('float32')
            
    # 3. 文字列（object）のCodeを「カテゴリ型」に変換して極限圧縮
    if 'Code' in df.columns:
        df['Code'] = df['Code'].astype('category')
        
    return df.dropna(subset=['AdjC']).sort_values(['Code', 'Date']).reset_index(drop=True)

def calc_vector_indicators(df):
    """テクニカル指標のベクトル演算。陰の極み用 BB -3σ を追加"""
    df = df.copy()
    
    # RSI (14)
    delta = df.groupby('Code')['AdjC'].diff()
    gain = delta.where(delta > 0, 0)
    loss = -delta.where(delta < 0, 0)
    avg_gain = gain.groupby(df['Code']).ewm(alpha=1/14, adjust=False).mean().reset_index(level=0, drop=True)
    avg_loss = loss.groupby(df['Code']).ewm(alpha=1/14, adjust=False).mean().reset_index(level=0, drop=True)
    df['RSI'] = (100 - (100 / (1 + (avg_gain / (avg_loss + 1e-10))))).astype('float32')
    
    # MACD (12, 26, 9)
    ema12 = df.groupby('Code')['AdjC'].ewm(span=12, adjust=False).mean().reset_index(level=0, drop=True)
    ema26 = df.groupby('Code')['AdjC'].ewm(span=26, adjust=False).mean().reset_index(level=0, drop=True)
    macd = ema12 - ema26
    signal = macd.groupby(df['Code']).ewm(span=9, adjust=False).mean().reset_index(level=0, drop=True)
    df['MACD_Hist'] = (macd - signal).astype('float32')
    
    # MA (5, 25, 75)
    df['MA5'] = df.groupby('Code')['AdjC'].transform(lambda x: x.rolling(5).mean()).astype('float32')
    df['MA25'] = df.groupby('Code')['AdjC'].transform(lambda x: x.rolling(25).mean()).astype('float32')
    df['MA75'] = df.groupby('Code')['AdjC'].transform(lambda x: x.rolling(75).mean()).astype('float32')
    
    # 🚨 陰の極み用：ボリンジャーバンド -3σ (20日)
    ma20 = df.groupby('Code')['AdjC'].transform(lambda x: x.rolling(20).mean())
    std20 = df.groupby('Code')['AdjC'].transform(lambda x: x.rolling(20).std())
    df['BB_L3'] = (ma20 - (std20 * 3)).astype('float32')
    
    # ATR (14)
    tr = pd.concat([
        df['AdjH'] - df['AdjL'], 
        (df['AdjH'] - df.groupby('Code')['AdjC'].shift(1)).abs(), 
        (df['AdjL'] - df.groupby('Code')['AdjC'].shift(1)).abs()
    ], axis=1).max(axis=1)
    df['ATR'] = tr.groupby(df['Code']).transform(lambda x: x.rolling(14).mean()).astype('float32')
    
    return df

def calc_technicals(df):
    return calc_vector_indicators(df)

def check_event_mines(code, event_data=None):
    """地雷警戒（原本復元）"""
    alerts = []
    c = str(code)[:4]
    today = datetime.utcnow() + timedelta(hours=9)
    today_date = today.date()
    max_warning_date = today_date + timedelta(days=14)
    
    critical_mines = {
        "8835": "2026-03-30", "3137": "2026-03-27", "4167": "2026-03-27", 
        "4031": "2026-03-27", "2195": "2026-03-27", "4379": "2026-03-27"
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

def check_double_top(df_sub):
    try:
        v = df_sub['AdjH'].values
        c = df_sub['AdjC'].values
        l = df_sub['AdjL'].values
        if len(v) < 6: return False
        peaks = []
        for i in range(1, len(v)-1):
            if v[i] == max(v[i-1:i+2]):
                if not peaks or (i - peaks[-1][0] > 1): peaks.append((i, v[i]))
        if len(v) >= 2 and v[-1] > v[-2]:
            if not peaks or (len(v)-1 - peaks[-1][0] > 1): peaks.append((len(v)-1, v[-1]))
        if len(peaks) >= 2:
            p2_idx, p2_val = peaks[-1]
            p1_idx, p1_val = peaks[-2]
            if abs(p2_val - p1_val) / max(p2_val, p1_val) < 0.05:
                valley = min(l[p1_idx:p2_idx+1]) if p2_idx > p1_idx else p1_val
                if valley < min(p1_val, p2_val) * 0.95 and c[-1] < p2_val * 0.97: return True
        return False
    except: return False

def check_head_shoulders(df_sub):
    try:
        v = df_sub['AdjH'].values
        c = df_sub['AdjC'].values
        if len(v) < 8: return False
        peaks = []
        for i in range(1, len(v)-1):
            if v[i] == max(v[i-1:i+2]):
                if not peaks or (i - peaks[-1][0] > 1): peaks.append((i, v[i]))
        if len(peaks) >= 3:
            p3_idx, p3_val = peaks[-1]
            p2_idx, p2_val = peaks[-2]
            p1_idx, p1_val = peaks[-3]
            if p2_val > p1_val and p2_val > p3_val and abs(p3_val - p1_val) / max(p3_val, p1_val) < 0.10 and c[-1] < p3_val * 0.97: 
                return True
        return False
    except: return False

def check_double_bottom(df_sub):
    try:
        l = df_sub['AdjL'].values
        c = df_sub['AdjC'].values
        h = df_sub['AdjH'].values
        if len(l) < 6: return False
        valleys = []
        for i in range(1, len(l)-1):
            if l[i] == min(l[i-1:i+2]):
                if not valleys or (i - valleys[-1][0] > 1): valleys.append((i, l[i]))
        if len(valleys) >= 2:
            v2_idx, v2_val = valleys[-1]
            v1_idx, v1_val = valleys[-2]
            if abs(v2_val - v1_val) / min(v2_val, v1_val) < 0.05:
                peak = max(h[v1_idx:v2_idx+1]) if v2_idx > v1_idx else v1_val
                if peak > max(v1_val, v2_val) * 1.04 and c[-1] > v2_val * 1.01: return True
        return False
    except: return False

def check_oversold_ultimate(df_sub):
    """🚨 新兵装：陰の極み（Oversold Ultimate）検知"""
    try:
        if len(df_sub) < 20: return False
        t = df_sub.iloc[-1]
        lc, lo, ll, lh, bbl3, rsi = t['AdjC'], t['AdjO'], t['AdjL'], t['AdjH'], t['BB_L3'], t['RSI']
        if lc <= bbl3 and rsi <= 25:
            body_v = abs(lc - lo)
            shadow_l = min(lc, lo) - ll
            full_rng = lh - ll
            if full_rng > 0 and shadow_l > (body_v * 2.5) and (shadow_l / full_rng) > 0.6: 
                return True
        return False
    except: return False

@st.cache_data(ttl=3600, show_spinner=False, max_entries=200)
def get_fundamentals(code):
    api_code = str(code) if len(str(code)) >= 5 else str(code) + "0"
    url = f"{BASE_URL}/fins/statements?code={api_code}"
    try:
        r = requests.get(url, headers=headers, timeout=3.0)
        if r.status_code == 200:
            data = r.json().get("statements", [])
            if not data: return None
            latest = data[0]
            res = {
                "op": latest.get("OperatingProfit"), "cap": latest.get("MarketCapitalization"), 
                "er": latest.get("EquityRatio"), "roe": None, "per": latest.get("PER"), "pbr": latest.get("PBR")
            }
            ni, eq = latest.get("NetIncome"), latest.get("Equity")
            if ni is not None and eq is not None:
                try: res["roe"] = (float(ni) / float(eq)) * 100
                except: res["roe"] = 0.0
            return res
    except: pass
    return None

@st.cache_data(ttl=86400)
def load_master():
    """JPXマスタ取得。英字銘柄を物理保護しつつ5桁規格化。"""
    try:
        r1 = requests.get("https://www.jpx.co.jp/markets/statistics-equities/misc/01.html", headers={'User-Agent': 'Mozilla/5.0'}, timeout=10)
        m = re.search(r'href="([^"]+data_j\.xls)"', r1.text)
        if m:
            r2 = requests.get("https://www.jpx.co.jp" + m.group(1), headers={'User-Agent': 'Mozilla/5.0'}, timeout=15)
            df = pd.read_excel(BytesIO(r2.content), engine='xlrd')[['コード', '銘柄名', '33業種区分', '市場・商品区分']]
            df.columns = ['Code', 'CompanyName', 'Sector', 'Market']
            # 🚨 523A等対応：4文字なら末尾0付与、5文字以上なら維持
            df['Code'] = df['Code'].astype(str).apply(lambda x: x if len(x) >= 5 else x + "0")
            return df
    except: pass
    return pd.DataFrame()

@st.cache_data(ttl=3600, show_spinner=False)
def get_single_data(code, yrs=1):
    base = datetime.utcnow() + timedelta(hours=9)
    f_d = (base - timedelta(days=365*yrs)).strftime('%Y%m%d')
    t_d = base.strftime('%Y%m%d')
    result = {"bars": [], "events": {"dividend": [], "earnings": []}}
    try:
        api_code = str(code) if len(str(code)) >= 5 else str(code) + "0"
        url = f"{BASE_URL}/equities/bars/daily?code={api_code}&from={f_d}&to={t_d}"
        r_bars = requests.get(url, headers=headers, timeout=10)
        if r_bars.status_code == 200: 
            result["bars"] = r_bars.json().get("daily_quotes") or r_bars.json().get("data") or []
    except: pass
    return result

import time # 🚨 リトライ用の待機モジュール（未インポートなら関数内で使用）

# 🚨 新規部隊：マクロ気象観測（独立した関数として最上段に配置）
def get_nikkei_macro_status():
    """日経平均の25日乖離率を取得し、戦術アラートを生成する"""
    try:
        import yfinance as yf
        n225 = yf.Ticker("^N225")
        df_n = n225.history(period="60d")
        if df_n.empty: return None
        
        df_n['MA25'] = df_n['Close'].rolling(window=25).mean()
        latest_close = df_n['Close'].iloc[-1]
        latest_ma25 = df_n['MA25'].iloc[-1]
        
        div_rate = ((latest_close - latest_ma25) / latest_ma25) * 100
        
        if div_rate >= 8.0:
            status, color, icon = "⚠️ 異常過熱（強襲停止）", "#ef5350", "🔥"
        elif div_rate >= 5.0:
            status, color, icon = "🟡 警戒：高値圏", "#ffca28", "⚡"
        elif div_rate <= -8.0:
            status, color, icon = "⚠️ 異常パニック（待伏好機）", "#42a5f5", "💎"
        elif div_rate <= -5.0:
            status, color, icon = "🔵 警戒：安値圏", "#26a69a", "⚓"
        else:
            status, color, icon = "🟢 巡航速度", "#66bb6a", "🚢"
            
        return {
            "close": latest_close,
            "ma25": latest_ma25,
            "div_rate": div_rate,
            "status": status,
            "color": color,
            "icon": icon
        }
    except:
        return None

# 🚨 既存部隊：データ取得（マクロ関数の「下」に配置することでスコープ破壊を防ぐ）
@st.cache_data(ttl=86400, max_entries=1, show_spinner=False)
def get_hist_data_cached(key):
    """19時リセット同期付 260日兵站確保（対レート制限・不屈のリトライ仕様）"""
    abort_flag = False
    last_error = ""
    base = datetime.now(pytz.timezone('Asia/Tokyo'))
    dates, days = [], 0
    while len(dates) < 260:
        d = base - timedelta(days=days)
        if d.weekday() < 5: dates.append(d.strftime('%Y%m%d'))
        days += 1
        if days > 400: break

    # 🚨 高速化兵装：TCPコネクションの使い回し ＋ 自動再試行アダプタ
    from requests.adapters import HTTPAdapter
    from urllib3.util.retry import Retry
    import time
    
    session = requests.Session()
    session.headers.update(headers)
    
    # 物理的な通信切断（500系エラー）に対する自動再試行を根底に組み込む
    retries = Retry(total=3, backoff_factor=0.5, status_forcelist=[500, 502, 503, 504])
    adapter = HTTPAdapter(pool_connections=10, pool_maxsize=10, max_retries=retries)
    session.mount('https://', adapter)

    # 🚨 第一防衛線：単発偵察（Recon by Fire）
    try:
        recon_url = f"{BASE_URL}/equities/bars/daily?date={dates[0]}"
        recon_res = session.get(recon_url, timeout=5.0)
        if recon_res.status_code in [401, 403]:
            raise ValueError(f"🚨 兵站断絶: API認証エラー({recon_res.status_code})。トークンが失効しています。")
    except requests.exceptions.Timeout:
        raise ValueError("🚨 兵站断絶: APIサーバーが沈黙しています（タイムアウト）。")
    except Exception as e:
        if "🚨" not in str(e):
            raise ValueError(f"🚨 兵站断絶: 物理的な通信障害 - {str(e)}")
        else:
            raise e

    rows = []

    def fetch(dt):
        nonlocal abort_flag, last_error
        if abort_flag: return []
        
        # 🚨 不屈の再試行ロジック：429（制限）などで弾かれても最大4回再突撃する
        for attempt in range(4):
            if abort_flag: return []
            try:
                r = session.get(f"{BASE_URL}/equities/bars/daily?date={dt}", timeout=10.0)
                if r.status_code == 200:
                    return r.json().get("data", [])
                elif r.status_code == 429:
                    time.sleep(1.0 * (attempt + 1)) # 制限を食らったら1秒→2秒と待機を延ばして再突撃
                    continue
                elif r.status_code in [401, 403]:
                    abort_flag = True
                    last_error = f"認証エラー({r.status_code})"
                    return []
                elif r.status_code >= 500:
                    time.sleep(1.0)
                    continue
                else:
                    abort_flag = True
                    last_error = f"未知のAPI応答({r.status_code})"
                    return []
            except Exception as e:
                time.sleep(1.0) # タイムアウト等の物理エラーでも1秒待って再突撃
                continue
        
        # 4回の再突撃すべてに失敗した場合のみ、全軍撤退を決定
        abort_flag = True
        last_error = f"通信リトライ限界突破 (Date: {dt})"
        return []

    # 🚨 ステルス機動：並列数を2に絞り、0.1秒のインターバルを強制
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as exe:
        futs = {exe.submit(fetch, dt): dt for dt in dates}
        for f in concurrent.futures.as_completed(futs):
            if abort_flag: 
                break 
            res = f.result()
            if res: rows.extend(res)
            time.sleep(0.1)

    if abort_flag:
        # Streamlit Cloudの黒塗りを突破し、画面上にエラー詳細を直接刻み込む
        st.error(f"🚨 兵站断絶: 本隊の突撃中に通信が遮断されました。詳細: {last_error}")
        raise ValueError(f"🚨 兵站断絶: 本隊の突撃中に通信が遮断されました。詳細: {last_error}")
        
    if not rows:
        raise ValueError("🚨 兵站断絶: データが取得できませんでした。")

    df = pd.DataFrame(rows)
    del rows
    gc.collect()
    
    return df

def get_fast_indicators(prices):
    if len(prices) < 15: return 50.0, 0.0, 0.0, np.zeros(5)
    p = np.array(prices, dtype='float32')
    ema12 = pd.Series(p).ewm(span=12, adjust=False).mean().values
    ema26 = pd.Series(p).ewm(span=26, adjust=False).mean().values
    macd = ema12 - ema26
    signal = pd.Series(macd).ewm(span=9, adjust=False).mean().values
    hist = macd - signal
    diff = np.diff(p[-15:])
    g = np.sum(np.maximum(diff, 0))
    l = np.sum(np.abs(np.minimum(diff, 0)))
    rsi = 100 - (100 / (1 + (g / (l + 1e-10))))
    return rsi, hist[-1], hist[-2], hist[-5:]

def get_triage_info(macd_hist, macd_hist_prev, rsi, lc=0, bt=0, mode="待伏", gc_days=0):
    """【鉄の掟】階層判定エンジン。"""
    tactics = st.session_state.get("sidebar_tactics", "⚖️ バランス (掟達成率 ＞ 到達度)")
    is_assault_mode = "狙撃優先" in tactics
    sl_limit_pct = float(st.session_state.get("bt_sl_c", 8.0))
    
    if macd_hist > 0 and macd_hist_prev <= 0: macd_t = "GC直後"
    elif macd_hist > macd_hist_prev: macd_t = "上昇拡大"
    elif macd_hist < 0 and macd_hist < macd_hist_prev: macd_t = "下落継続"
    else: macd_t = "減衰"
    
    if mode == "強襲":
        if macd_t == "下落継続" or rsi >= 75: return "圏外🚫", "#ef5350", 0, macd_t
        if is_assault_mode:
            if gc_days == 1: return "S🔥", "#26a69a", 5, "GC直後(1日目)"
            return "A⚡", "#ed6c02", 4, f"GC継続({gc_days}日目)"
        else:
            if gc_days == 1: 
                return ("S🔥", "#26a69a", 5, "GC直後") if rsi <= 50 else ("A⚡", "#ed6c02", 4, "GC直後")
            return "B📈", "#0288d1", 3, f"GC継続({gc_days}日目)"
            
    if bt == 0 or lc == 0: return "C👁️", "#616161", 1, macd_t
    
    dist_pct = ((lc / bt) - 1) * 100 
    if dist_pct < -sl_limit_pct: return "圏外💀", "#ef5350", 0, f"損切突破({dist_pct:.1f}%)"
    
    if is_assault_mode:
        if dist_pct <= 2.0: return "S🔥", "#26a69a", 5.5, macd_t
        elif dist_pct <= 6.0: return "A⚡", "#ed6c02", 4.5, macd_t
        elif dist_pct <= 10.0: return "B📈", "#0288d1", 3.5, macd_t
    else:
        if dist_pct <= 2.0: 
            return ("S🔥", "#26a69a", 5, macd_t) if rsi <= 45 else ("A⚡", "#ed6c02", 4.5, macd_t) 
        elif dist_pct <= 5.0: 
            return ("A🪤", "#0288d1", 4.0, macd_t) if rsi <= 50 else ("B📈", "#0288d1", 3, macd_t)
            
    return "C👁️", "#616161", 1, macd_t

def get_assault_triage_info(gc_days, lc, rsi_v, df_chart, is_strict=False):
    """強襲モード専用：25日線との距離、RSI、鮮度を複合した精密判定"""
    if gc_days <= 0 or df_chart is None or df_chart.empty: 
        return "圏外 💀", "#424242", 0, ""

    tactics = st.session_state.get("sidebar_tactics", "⚖️ バランス (掟達成率 ＞ 到達度)")
    is_assault_mode = "狙撃優先" in tactics
    
    row = df_chart.iloc[-1]
    ma25 = row.get('MA25', 0)
    score = 50 

    if ma25 > 0:
        if lc >= ma25 * 0.95: score += 10
        if lc >= ma25: score += 10
    
    if is_assault_mode:
        if 50 <= rsi_v <= 75: score += 15
    else:
        if 50 <= rsi_v <= 65: score += 10
        elif rsi_v > 70: score -= 20

    score -= (gc_days - 1) * 5

    if score >= (85 if is_strict else 80): 
        rank, bg = "S🔥", "#26a69a"
    elif score >= (65 if is_strict else 60): 
        rank, bg = "A⚡", "#ed6c02"
    elif score >= (45 if is_strict else 40): 
        rank, bg = "B📈", "#0288d1"
    else: 
        rank, bg = "C 💀", "#424242"

    return rank, bg, score, f"GC {gc_days}日目"


# --- 📺 UI描画関数 ---
def render_technical_radar(df, buy_price, tp_pct):
    """ボスの計器盤を物理復元 ＆ 『陰の極み』検知配線"""
    if df.empty or len(df) < 2: return ""
    latest = df.iloc[-1]
    prev = df.iloc[-2]
    rsi = latest.get('RSI', 50)
    macd_hist = latest.get('MACD_Hist', 0)
    macd_hist_prev = prev.get('MACD_Hist', 0)
    atr = latest.get('ATR', 0)
    
    # 🚨 カラーコード厳格化：売られすぎ＝緑（ポジ）、買われすぎ＝赤（ネガ）
    rsi_color = "#26a69a" if rsi <= 30 else "#4db6ac" if rsi <= 45 else "#888888" 
    rsi_text = "🔥 超売られすぎ" if rsi <= 30 else "⚡ 売られすぎ" if rsi <= 45 else "⚖️ 中立"
    if rsi >= 70: 
        rsi_color = "#ef5350"
        rsi_text = "⚠️ 買われすぎ"
    
    _, _, _, macd_t = get_triage_info(macd_hist, macd_hist_prev, rsi)
    
    # 🚨 陰の極み判定を統合
    if check_oversold_ultimate(df):
        macd_display = "💎 【陰の極み】底打ち最終波形 💎"
        macd_color = "#26a69a"
        bg_glow = "box-shadow: 0 0 20px rgba(38, 166, 154, 0.8); border: 2px solid #26a69a;"
    elif macd_t == "GC直後": 
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
    
    return f'<div style="background: rgba(255, 255, 255, 0.05); padding: 0.8rem; border-radius: 4px; margin: 1rem 0; {bg_glow}"><div style="font-size: 14px; color: #aaa;">📡 計器フライト: RSI <strong style="color: {rsi_color};">{rsi:.0f}% ({rsi_text})</strong> | MACD <strong style="color: {macd_color}; font-size: 1.1em;">{macd_display}</strong> | ボラ <strong style="color: #bbb;">{atr:.0f}円</strong> (利確目安: {days}日)</div></div>'

def render_tab3_scope_logic(df, code, company_name):
    """【照準】50%/61.8%自動追尾・目標算出エンジン"""
    if df.empty: return None
    p_high, p_low = df['AdjH'].max(), df['AdjL'].min()
    current_p = df.iloc[-1]['AdjC']
    
    # 座標算出
    p_50 = p_low + (p_high - p_low) * 0.50
    p_618 = p_low + (p_high - p_low) * 0.382
    
    # 🚨 判定：50%ラインを7%以上（パニック水準）割り込んだら61.8%へ下方修正
    is_panic = current_p < (p_50 * 0.93)
    targ_p = p_618 if is_panic else p_50
    label = "💎 61.8% 押し (深海モード)" if is_panic else "⚖️ 50.0% 押し (標準モード)"
    color = "#26a69a" if is_panic else "#FFD700"
    
    # UI出力
    st.markdown(f"""
        <div style="background: rgba(30, 30, 30, 0.7); padding: 1rem; border-radius: 8px; border-left: 5px solid {color}; margin-bottom: 1rem;">
            <h3 style="margin: 0;">{code} {company_name}</h3>
            <p style="color: #aaa; margin: 0.2rem 0;">戦闘モード: <strong style="color: {color};">{label}</strong></p>
            <div style="display: flex; gap: 2rem; margin-top: 0.5rem;">
                <div><small>現在値</small><br><span style="font-size: 1.5rem;">¥{current_p:,.0f}</span></div>
                <div><small>目標買値</small><br><span style="font-size: 1.5rem; color: {color};">¥{targ_p:,.0f}</span></div>
            </div>
        </div>
    """, unsafe_allow_html=True)
    return targ_p

def draw_chart(df, targ_p, tp5=None, tp10=None, tp15=None, tp20=None, chart_key=None):
    """右余白ゼロ、初期2ヶ月ズーム、全ホバー情報、NaNクラッシュ防止を備えたチャート"""
    if df is None or df.empty: return
    df_plot = df.copy()
    
    for col in ['AdjO', 'AdjH', 'AdjL', 'AdjC', 'MA5', 'MA25', 'MA75']:
        if col in df_plot.columns:
            df_plot[col] = pd.to_numeric(df_plot[col], errors='coerce').astype('float64')

    fig = go.Figure()
    
    fig.add_trace(go.Candlestick(
        x=df_plot['Date'], open=df_plot['AdjO'], high=df_plot['AdjH'], low=df_plot['AdjL'], close=df_plot['AdjC'], 
        name='株価', increasing_line_color='#26a69a', decreasing_line_color='#ef5350',
        hovertemplate="始値：%{open:,.0f}<br>終値：%{close:,.0f}<br>高値：%{high:,.0f}<br>安値：%{low:,.0f}<extra></extra>"
    ))
    
    fig.add_trace(go.Scatter(
        x=df_plot['Date'], y=[targ_p]*len(df_plot), name='目標', 
        line=dict(color='#FFD700', width=2, dash='dash'), hovertemplate="目標：%{y:,.0f}<extra></extra>"
    ))
    
    for m_c, m_n, m_col in [('MA5', 'MA5', '#ffca28'), ('MA25', 'MA25', '#42a5f5'), ('MA75', 'MA75', '#ab47bc')]:
        if m_c in df_plot.columns: 
            fig.add_trace(go.Scatter(
                x=df_plot['Date'], y=df_plot[m_c], name=m_n, line=dict(color=m_col, width=1.5), 
                connectgaps=True, hovertemplate=f"{m_n}：%{{y:,.0f}}<extra></extra>"
            ))
            
    last_date = df_plot['Date'].max()
    initial_start = last_date - timedelta(days=60) 
    
    # 🚨 防弾：NaNによるValueErrorクラッシュを防止
    try:
        y_min, y_max = float(df_plot['AdjL'].min()), float(df_plot['AdjH'].max())
        if pd.isna(y_min) or pd.isna(y_max):
            y_min, y_max = float(df_plot['AdjC'].min()) * 0.9, float(df_plot['AdjC'].max()) * 1.1
    except:
        y_min, y_max = 0, 100

    fig.update_layout(
        height=550, 
        margin=dict(l=0, r=0, t=30, b=40), 
        hovermode="x unified", dragmode="zoom",
        paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)',
        xaxis=dict(type="date", range=[initial_start, last_date + timedelta(days=2)], fixedrange=False, rangeslider=dict(visible=True, thickness=0.05)),
        yaxis=dict(tickformat=",.0f", side="right", fixedrange=False, autorange=True, range=[y_min * 0.95, y_max * 1.10]), 
        legend=dict(orientation="h", yanchor="top", y=-0.1, xanchor="center", x=0.5)
    )
    
    st.plotly_chart(fig, use_container_width=True, config={'displayModeBar': False, 'scrollZoom': True, 'displaylogo': False}, key=f"{chart_key or 'chart'}_{cache_key}")


# --- 4. サイドバー UI（原典 100% 復旧） ---
# 🚨 英語の不純物を排除し、ボスの原本タイトルを復元
st.sidebar.title("🛠️ 戦術コンソール")

# --- 🌐 マクロ地合い連動システム ---
st.sidebar.markdown("### 🌐 マクロ地合い連動")
use_macro = st.sidebar.toggle("地合い連動を有効化", value=True)

st.session_state.push_penalty = 0.0
st.session_state.rsi_penalty = 0
st.session_state.macro_alert = "🟢 平時（通常ロジック稼働）"

if use_macro:
    api_nikkei_pct = weather['nikkei']['pct'] if weather else 0.0
    manual_pct = st.sidebar.number_input(
        "日経騰落率（API値自動入力 %）", 
        value=float(api_nikkei_pct), 
        step=0.1, 
        format="%.2f",
        help="暴落シミュレーションをする場合は数値を書き換えてください。"
    )

    if manual_pct <= -2.0:
        st.session_state.push_penalty = 0.10  
        st.session_state.rsi_penalty = 20     
        st.session_state.macro_alert = f"🔴 厳戒態勢（日経 {manual_pct:+.2f}%）"
    elif manual_pct <= -1.0:
        st.session_state.push_penalty = 0.05  
        st.session_state.rsi_penalty = 10     
        st.session_state.macro_alert = f"🟠 警戒態勢（日経 {manual_pct:+.2f}%）"
    else:
        st.session_state.macro_alert = f"🟢 平時（日経 {manual_pct:+.2f}%）"

st.sidebar.divider()

st.sidebar.header("📍 ターゲット選別")
market_options = ["🏢 大型株 (プライム・一部)", "🚀 中小型株 (スタンダード・グロース)"]
st.sidebar.selectbox("市場ターゲット", options=market_options, index=market_options.index(st.session_state.preset_market) if st.session_state.preset_market in market_options else 1, key="preset_market", on_change=save_settings)

push_r_options = ["25.0%", "50.0%", "61.8%"]
st.sidebar.selectbox("押し目プリセット", options=push_r_options, index=push_r_options.index(st.session_state.preset_push_r) if st.session_state.preset_push_r in push_r_options else 1, key="preset_push_r", on_change=apply_presets)

tactics_options = ["⚖️ バランス (掟達成率 ＞ 到達度)", "🎯 狙撃優先 (到達度 ＞ 掟達成率)"]
st.sidebar.selectbox("戦術アルゴリズム", options=tactics_options, index=tactics_options.index(st.session_state.sidebar_tactics) if st.session_state.sidebar_tactics in tactics_options else 0, key="sidebar_tactics", on_change=save_settings)

st.sidebar.divider()

st.sidebar.header("🔍 ピックアップルール")
c1, c2 = st.sidebar.columns(2)
with c1:
    st.number_input("価格下限(円)", value=int(st.session_state.f1_min), step=100, key="f1_min", on_change=save_settings)
with c2:
    st.number_input("価格上限(円)", value=int(st.session_state.f1_max), step=100, key="f1_max", on_change=save_settings)

st.sidebar.number_input("1ヶ月暴騰上限(倍)", value=float(st.session_state.f2_m30), step=0.1, key="f2_m30", on_change=save_settings)
st.sidebar.number_input("1年最高値からの下落除外(%)", value=float(st.session_state.f3_drop), step=5.0, max_value=0.0, key="f3_drop", on_change=save_settings)

c3, c4 = st.sidebar.columns(2)
with c3:
    st.number_input("波高下限(倍)", value=float(st.session_state.f9_min14), step=0.1, key="f9_min14", on_change=save_settings)
with c4:
    st.number_input("波高上限(倍)", value=float(st.session_state.f9_max14), step=0.1, key="f9_max14", on_change=save_settings)

st.sidebar.checkbox("🚀 IPO除外(上場1年/200日未満)", value=bool(st.session_state.f5_ipo), key="f5_ipo", on_change=save_settings)
st.sidebar.checkbox("疑義注記・信用リスク銘柄除外", value=bool(st.session_state.f6_risk), key="f6_risk", on_change=save_settings)
st.sidebar.checkbox("上昇第3波終了銘柄を除外", value=bool(st.session_state.f11_ex_wave3), key="f11_ex_wave3", on_change=save_settings)
st.sidebar.checkbox("非常に割高・赤字銘柄を除外", value=bool(st.session_state.f12_ex_overvalued), key="f12_ex_overvalued", on_change=save_settings)

st.sidebar.divider()

st.sidebar.header("🎯 買いルール")
st.sidebar.number_input("購入ロット(株)", value=int(st.session_state.bt_lot), step=100, key="bt_lot", on_change=save_settings)
st.sidebar.number_input("猶予期限(日)", value=int(st.session_state.limit_d), step=1, key="limit_d", on_change=save_settings)

st.sidebar.header("💰 売りルール")
st.sidebar.number_input("利確目標(%)", value=int(st.session_state.bt_tp), step=1, key="bt_tp", on_change=save_settings)

c_sl1, c_sl2 = st.sidebar.columns(2)
with c_sl1:
    st.number_input("初期損切(%)", value=int(st.session_state.bt_sl_i), step=1, key="bt_sl_i", on_change=save_settings)
with c_sl2:
    st.number_input("現在損切(%)", value=int(st.session_state.bt_sl_c), step=1, key="bt_sl_c", on_change=save_settings)

st.sidebar.number_input("最大保持期間(日)", value=int(st.session_state.bt_sell_d), step=1, key="bt_sell_d", on_change=save_settings)

st.sidebar.divider()

st.sidebar.header("🚫 特殊除外フィルター")
st.sidebar.checkbox("ETF・REIT等を除外", value=bool(st.session_state.f7_ex_etf), key="f7_ex_etf", on_change=save_settings)
st.sidebar.checkbox("医薬品(バイオ)を除外", value=bool(st.session_state.f8_ex_bio), key="f8_ex_bio", on_change=save_settings)
st.sidebar.checkbox("落ちるナイフ除外(暴落直後)", value=bool(st.session_state.f10_ex_knife), key="f10_ex_knife", on_change=save_settings)
st.sidebar.text_area("除外銘柄コード", value=str(st.session_state.gigi_input), key="gigi_input", on_change=save_settings)

st.sidebar.divider()

if st.sidebar.button("🔴 キャッシュ強制パージ", use_container_width=True):
    st.cache_data.clear()
    st.session_state.tab1_scan_results = None
    st.session_state.tab2_scan_results = None
    st.rerun()

if st.sidebar.button("💾 設定を保存", use_container_width=True):
    save_settings()
    st.toast("全設定を永久保存した。")

st.sidebar.caption(f"KEY: {cache_key}")

# ==========================================
# (2) メイン画面の描画スタート（サイドバー定義の直後など）
# ==========================================
st.title("ボスのアプリタイトル...")

# ⬇️⬇️⬇️ ここにマクロ気象局を挿入 ⬇️⬇️⬇️
# --- 📍 マクロ気象局アラートの表示 ---
n225_macro = get_nikkei_macro_status()
if n225_macro:
    div_v = n225_macro['div_rate']
    st.markdown(f"""
        <div style="background: rgba(255,255,255,0.05); padding: 1rem; border-radius: 10px; border-left: 5px solid {n225_macro['color']}; margin-bottom: 1rem;">
            <div style="display: flex; justify-content: space-between; align-items: center;">
                <span style="font-size: 14px; color: #aaa;">📡 マクロ気象観測：日経平均25日乖離率</span>
                <span style="font-size: 18px; font-weight: bold; color: {n225_macro['color']};">{n225_macro['icon']} {n225_macro['status']}</span>
            </div>
            <div style="display: flex; gap: 20px; margin-top: 5px;">
                <div><span style="font-size: 12px; color: #888;">日経現在値:</span> <b style="font-size: 16px;">{n225_macro['close']:,.0f}円</b></div>
                <div><span style="font-size: 12px; color: #888;">25日移動平均:</span> <b style="font-size: 16px;">{n225_macro['ma25']:,.0f}円</b></div>
                <div><span style="font-size: 12px; color: #888;">乖離率:</span> <b style="font-size: 20px; color: {n225_macro['color']};">{div_v:+.2f}%</b></div>
            </div>
        </div>
    """, unsafe_allow_html=True)
    st.session_state.macro_alert = n225_macro['status']

# --- 5. タブ構成（原本UI ＆ NameError物理根絶配置） ---
# 🚨 修正：load_masterの実行行。すべての定義が終わったここで行う。
master_df = load_master()

tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs([
    "🌐 【待伏】広域レーダー", 
    "⚡ 【強襲】GC初動レーダー", 
    "🎯 【照準】精密スコープ", 
    "⚙️ 【演習】戦術シミュレータ", 
    "⛺ 【戦線】交戦モニター", 
    "📁 【戦歴】交戦データベース"
])
tactics_mode = st.session_state.sidebar_tactics

# --- 6. タブコンテンツ (TAB1: 待伏レーダー) ---
with tab1:
    st.markdown(f'<h3 style="font-size: 24px;">🎯 【待伏】2026式・マクロ連動スキャン</h3>', unsafe_allow_html=True)
    st.info(f"現在の地合い連動：{st.session_state.get('macro_alert', '未設定')}")
    
    master_map_t1 = {}
    if not master_df.empty:
        m_df_tmp = master_df[['Code', 'CompanyName', 'Market', 'Sector']].copy()
        m_df_tmp['Code'] = m_df_tmp['Code'].astype(str).apply(lambda x: x if len(x) >= 5 else x + "0")
        master_map_t1 = m_df_tmp.set_index('Code').to_dict('index')
        del m_df_tmp

    if 'tab1_scan_results' not in st.session_state: st.session_state.tab1_scan_results = None
    
    run_scan_t1 = st.button("🚀 索敵開始", key="btn_scan_t1_macro")

    if run_scan_t1:
        st.session_state.tab1_scan_results = None
        gc.collect() 
        t_global_start = time.time()
        
        with st.status("🚀 索敵スキャンを実行中... 兵站ルートを開拓しています", expanded=True) as status:
            st.write("📡 第1段階：260日分のローソク足データを取得中...")
            raw = get_hist_data_cached(cache_key)
            t_fetch = time.time()
            st.write(f"✔️ 第1段階完了：兵站確保 [{t_fetch - t_global_start:.2f}秒]")
            
            if raw is not None and len(raw) > 0:
                st.write("🧽 第2段階：データ洗浄・規格統一を実行中...")
                full_df = clean_df(pd.DataFrame(raw))
                full_df['Code'] = full_df['Code'].astype(str).apply(lambda x: x if len(x) >= 5 else x + "0")
                
                push_penalty = st.session_state.get('push_penalty', 0.0)
                config_t1 = {
                    "f1_min": float(st.session_state.f1_min), "f1_max": float(st.session_state.f1_max),
                    "f2_m30": float(st.session_state.f2_m30), "f3_drop": float(st.session_state.f3_drop),
                    "push_r": float(st.session_state.push_r), "push_penalty": push_penalty,
                    "f9_min14": float(st.session_state.f9_min14), "f9_max14": float(st.session_state.f9_max14),
                    "limit_d": int(st.session_state.limit_d), "f12_ex_overvalued": st.session_state.f12_ex_overvalued,
                    "tactics": st.session_state.get("sidebar_tactics", "⚖️ バランス"), "sl_c": float(st.session_state.get("bt_sl_c", 8.0))
                }

                m_mode = "大型" if "大型株" in st.session_state.preset_market else "中小型"
                target_keywords = ['プライム','一部'] if m_mode=="大型" else ['スタンダード','グロース','新興','マザーズ','JASDAQ','二部']
                m_targets = [c for c, m in master_map_t1.items() if any(k in str(m['Market']) for k in target_keywords)]
                
                latest_date = full_df['Date'].max()
                mask = (full_df['Date'] == latest_date) & (full_df['AdjC'] >= config_t1["f1_min"]) & (full_df['AdjC'] <= config_t1["f1_max"])
                valid_codes = set(full_df[mask]['Code']).intersection(set(m_targets))
                
                v_col = next((col for col in full_df.columns if col in ['Volume', 'AdjVo', 'Vo']), 'Volume')
                avg_vols = full_df.groupby('Code').tail(5).groupby('Code')[v_col].mean()

                df = full_df[full_df['Code'].isin(valid_codes)]
                t_clean = time.time()
                st.write(f"✔️ 第2段階完了：データ洗浄 [{t_clean - t_fetch:.2f}秒]")
                st.write("⚙️ 第3段階：並列演算・フィルタリングを実行中...")

                def scan_unit_t1_parallel(code, group, cfg, v_avg):
                    c_vals = group['AdjC'].values
                    lc = c_vals[-1]
                    p20 = c_vals[max(0, len(c_vals)-20)]
                    if p20 > 0 and (lc / p20) > cfg["f2_m30"]: return None
                    
                    h_vals, l_vals = group['AdjH'].values, group['AdjL'].values
                    if lc < h_vals.max() * (1 + (cfg["f3_drop"] / 100.0)): return None
                    
                    r4h = h_vals[-4:]; h4 = r4h.max()
                    g_max_idx = len(h_vals) - 4 + r4h.argmax()
                    l14 = l_vals[max(0, g_max_idx - 14) : g_max_idx + 1].min()

                    if l14 <= 0 or h4 <= l14: return None
                    wh = h4 / l14
                    if not (cfg["f9_min14"] <= wh <= cfg["f9_max14"]): return None
                    
                    if cfg["f12_ex_overvalued"]:
                        f_data = get_fundamentals(code[:4])
                        if f_data and ((f_data.get("op", 0) or 0) < 0): return None
                    
                    rsi, _, _, _ = get_fast_indicators(c_vals)
                    base_push = (h4 - l14) * (cfg["push_r"] / 100.0)
                    target_buy = h4 - base_push
                    target_buy = target_buy * (1.0 - cfg["push_penalty"]) 
                    
                    score = 4
                    if 1.3 <= wh <= 2.0: score += 1
                    if (len(h_vals) - 1 - g_max_idx) <= cfg["limit_d"]: score += 1
                    if not check_double_top(group.tail(31).iloc[:-1]): score += 1
                    if target_buy * 0.85 <= lc <= target_buy * 1.35: score += 1
                    
                    dist_pct = ((lc / target_buy) - 1) * 100
                    if dist_pct < -cfg["sl_c"]: rank, bg, t_score = "圏外💀", "#ef5350", 0
                    elif dist_pct <= 2.0: rank, bg, t_score = "S🔥", "#26a69a", 5.5
                    elif dist_pct <= 6.0: rank, bg, t_score = "A⚡", "#ed6c02", 4.5
                    else: rank, bg, t_score = "B📈", "#0288d1", 3.5

                    is_ultimate = check_oversold_ultimate(group)

                    return {
                        'Code': code, 'lc': float(lc), 'RSI': float(rsi), 'target_buy': float(target_buy), 
                        'reach_rate': float((target_buy / lc) * 100), 'triage_rank': rank, 'triage_bg': bg, 
                        't_score': t_score, 'score': score, 'high_4d': float(h4), 'low_14d': float(l14), 'avg_vol': int(v_avg),
                        'ultimate': is_ultimate
                    }

                results = []
                with concurrent.futures.ThreadPoolExecutor(max_workers=3) as exe:
                    futures = {exe.submit(scan_unit_t1_parallel, c, g, config_t1, avg_vols.get(c, 0)): c for c, g in df.groupby('Code')}
                    for f in concurrent.futures.as_completed(futures):
                        try:
                            res = f.result()
                            if res: results.append(res)
                        except: pass
                
                sorted_raw = sorted(results, key=lambda x: (x['t_score'], x['score']), reverse=True)
                filtered_results = []
                sector_counts = {}
                for r in sorted_raw:
                    sector = master_map_t1.get(str(r['Code']), {}).get('Sector', '不明')
                    if sector_counts.get(sector, 0) < 3:
                        filtered_results.append(r)
                        sector_counts[sector] = sector_counts.get(sector, 0) + 1
                    if len(filtered_results) >= 30: break
                
                st.session_state.tab1_scan_results = filtered_results
                t_calc = time.time()
                
                st.write(f"✔️ 第3段階完了：並列演算・フィルタリング [{t_calc - t_clean:.2f}秒]")
                status.update(label=f"🎯 スキャン完了！ (総所要時間: {t_calc - t_global_start:.2f}秒)", state="complete", expanded=False)

    if st.session_state.tab1_scan_results:
        light_results = st.session_state.tab1_scan_results
        st.success(f"🎯 待伏ロックオン: {len(light_results)} 銘柄（マクロ連動・セクター分散適用済）")
        
        sab_codes = " ".join([str(r['Code'])[:4] for r in light_results if str(r['triage_rank']).startswith(('S', 'A', 'B'))])
        st.info("📋 以下のコードをコピーして、照準（TAB3）にペースト可能だ。")
        st.code(sab_codes, language="text")
        
        for r in light_results:
            st.divider()
            # 🚨 防弾：UIループ中のNaNクラッシュを根絶する解毒関数
            def safe_int(x):
                try: return int(float(x)) if not pd.isna(x) else 0
                except: return 0

            c_code = str(r['Code']); m_info = master_map_t1.get(c_code, {})
            m_lower = str(m_info.get('Market', '')).lower()
            if 'プライム' in m_lower or '一部' in m_lower: badge_html = '<span style="background-color: #1a237e; color: #ffffff; padding: 0.2rem 0.6rem; border-radius: 4px; font-size: 11px; font-weight: bold;">🏢 プライム/大型</span>'
            elif 'グロース' in m_lower or 'マザーズ' in m_lower: badge_html = '<span style="background-color: #1b5e20; color: #ffffff; padding: 0.2rem 0.6rem; border-radius: 4px; font-size: 11px; font-weight: bold;">🚀 グロース/新興</span>'
            else: badge_html = f'<span style="background-color: #455a64; color: #ffffff; padding: 0.2rem 0.6rem; border-radius: 4px; font-size: 11px; font-weight: bold;">{m_info.get("Market","不明")}</span>'
            
            u_badge = '<span style="background-color: #26a69a; color: #ffffff; padding: 0.2rem 0.6rem; border-radius: 4px; font-size: 13px; font-weight: bold; margin-left: 0.5rem; box-shadow: 0 0 10px rgba(38,166,154,0.5);">💎 陰の極み</span>' if r.get('ultimate') else ""
            t_badge = f'<span style="background-color: {r["triage_bg"]}; color: #ffffff; padding: 0.2rem 0.6rem; border-radius: 4px; font-size: 13px; font-weight: bold; margin-left: 0.5rem;">🎯 優先度: {r["triage_rank"]}</span>'
            score_val = safe_int(r["score"]); score_color = "#26a69a" if score_val >= 8 else "#ff5722"; score_bg = "rgba(38, 166, 154, 0.15)" if score_val >= 8 else "rgba(255, 87, 34, 0.15)"
            score_badge = f'<span style="background-color: {score_bg}; border: 1px solid {score_color}; color: {score_color}; padding: 0.2rem 0.6rem; border-radius: 4px; font-size: 12px; font-weight: bold; margin-left: 0.5rem;">🎖️ 掟スコア: {score_val}/9</span>'
            sector_badge = f'<span style="background-color: #607d8b; color: #ffffff; padding: 0.1rem 0.5rem; border-radius: 4px; font-size: 12px; margin-left: 0.5rem;">🏭 {m_info.get("Sector", "不明")}</span>'
            
            st.markdown(f"""
                <div style="margin-bottom: 0.8rem;">
                    <h3 style="font-size: clamp(18px, 5vw, 28px); font-weight: bold; margin: 0 0 0.3rem 0;">({c_code[:4]}) {m_info.get('CompanyName', '不明')}</h3>
                    <div style="display: flex; flex-wrap: wrap; gap: 6px; align-items: center;">
                        {badge_html}{u_badge}{t_badge}{score_badge}{sector_badge}
                        <span style="background-color: rgba(38, 166, 154, 0.15); border: 1px solid #26a69a; color: #26a69a; padding: 0.1rem 0.5rem; border-radius: 4px; font-size: 12px;">RSI: {r["RSI"]:.1f}%</span>
                        <span style="background-color: rgba(255, 215, 0, 0.1); border: 1px solid #FFD700; color: #FFD700; padding: 0.1rem 0.5rem; border-radius: 4px; font-size: 12px;">到達度: {r['reach_rate']:.1f}%</span>
                    </div>
                </div>
            """, unsafe_allow_html=True)
            
            m_cols = st.columns([1, 1, 1, 1.2, 1.5])
            # 🚨 防弾：全て safe_int で保護
            m_cols[0].metric("直近高値", f"{safe_int(r['high_4d']):,}円")
            m_cols[1].metric("起点安値", f"{safe_int(r['low_14d']):,}円")
            m_cols[2].metric("最新終値", f"{safe_int(r['lc']):,}円")
            m_cols[3].metric("平均出来高", f"{safe_int(r['avg_vol']):,}株")
            m_cols[4].markdown(f"""<div style="background: rgba(255, 215, 0, 0.05); padding: 0.5rem; border-radius: 8px; border: 1px solid rgba(255, 215, 0, 0.2); text-align: center;"><div style="font-size: 13px; color: rgba(250, 250, 250, 0.6); margin-bottom: 2px;">🎯 買値目標(連動済)</div><div style="font-size: 1.8rem; font-weight: bold; color: #FFD700;">{safe_int(r['target_buy']):,}<span style="font-size: 14px; margin-left:2px;">円</span></div></div>""", unsafe_allow_html=True)

# --- 7. タブコンテンツ (TAB2: 強襲レーダー) ---
with tab2:
    st.markdown('<h3 style="font-size: 24px;">⚡ 【強襲】2026式・マクロ連動スキャン</h3>', unsafe_allow_html=True)
    st.info(f"現在の地合い連動：{st.session_state.get('macro_alert', '未設定')}")
    
    if 'tab2_scan_results' not in st.session_state: st.session_state.tab2_scan_results = None
    
    master_map_t2 = {}
    if not master_df.empty:
        m_df_tmp = master_df[['Code', 'CompanyName', 'Market', 'Sector']].copy()
        m_df_tmp['Code'] = m_df_tmp['Code'].astype(str).apply(lambda x: x if len(x) >= 5 else x + "0")
        master_map_t2 = m_df_tmp.set_index('Code').to_dict('index')
        del m_df_tmp

    col_t2_1, col_t2_2 = st.columns(2)
    if 'tab2_rsi_limit' not in st.session_state: st.session_state.tab2_rsi_limit = 70
    if 'tab2_vol_limit' not in st.session_state: st.session_state.tab2_vol_limit = 50000
    
    rsi_lim = col_t2_1.number_input("RSI上限（過熱感の足切り）", value=int(st.session_state.tab2_rsi_limit), step=5, key="t2_rsi_v2026_final_physical_lock")
    vol_lim = col_t2_2.number_input("最低出来高（5日平均）", value=int(st.session_state.tab2_vol_limit), step=5000, key="t2_vol_v2026_final_physical_lock")

    if st.button("🚀 強襲開始", key="btn_scan_t2_macro_physical_lock"):
        st.session_state.tab2_scan_results = None
        gc.collect()
        t_global_start = time.time()

        with st.status("🚀 索敵スキャンを実行中... 強襲ルートを計算しています", expanded=True) as status:
            try:
                st.write("📡 第1段階：260日分のローソク足データを取得中...")
                raw = get_hist_data_cached(cache_key)
                t_fetch = time.time()
                st.write(f"✔️ 第1段階完了：兵站確保 [{t_fetch - t_global_start:.2f}秒]")
                
                if raw is None or len(raw) == 0:
                    st.error("J-Quants APIからの応答が途絶。")
                else:
                    st.write("🧽 第2段階：データ洗浄・地合い適用中...")
                    full_df = clean_df(pd.DataFrame(raw))
                    full_df['Code'] = full_df['Code'].astype(str).apply(lambda x: x if len(x) >= 5 else x + "0")
                    for col in ['AdjC', 'AdjH', 'AdjL']:
                        if col in full_df.columns:
                            full_df[col] = full_df[col].astype('float32')

                    rsi_penalty = st.session_state.get('rsi_penalty', 0)
                    effective_rsi_limit = float(rsi_lim) - rsi_penalty
                    
                    config_t2 = {
                        "f1_min": float(st.session_state.f1_min), "f1_max": float(st.session_state.f1_max),
                        "rsi_lim": effective_rsi_limit, "vol_lim": float(vol_lim),
                        "f12_ex_overvalued": st.session_state.f12_ex_overvalued,
                        "tactics": st.session_state.get("sidebar_tactics", "⚖️ バランス")
                    }
                    
                    v_col = next((col for col in full_df.columns if col in ['Volume', 'AdjVo', 'Vo']), 'Volume')
                    if v_col not in full_df.columns: full_df[v_col] = 100000
                    
                    avg_vols_series = full_df.groupby('Code').tail(5).groupby('Code')[v_col].mean().fillna(0).astype(int)
                    
                    m_mode = "大型" if "大型株" in st.session_state.preset_market else "中小型"
                    target_keywords = ['プライム','一部'] if m_mode=="大型" else ['スタンダード','グロース','新興','マザーズ','JASDAQ','二部']
                    m_targets = [c for c, m in master_map_t2.items() if any(k in str(m['Market']) for k in target_keywords)]
                    
                    latest_date = full_df['Date'].max()
                    mask = (full_df['Date'] == latest_date) & (full_df['AdjC'] >= config_t2["f1_min"]) & (full_df['AdjC'] <= config_t2["f1_max"])
                    valid_codes = set(full_df[mask]['Code']).intersection(set(m_targets)).intersection(set(avg_vols_series[avg_vols_series >= config_t2["vol_lim"]].index))
                    
                    df = full_df[full_df['Code'].isin(valid_codes)]
                    del full_df; gc.collect()
                    t_clean = time.time()
                    st.write(f"✔️ 第2段階完了：データ洗浄 [{t_clean - t_fetch:.2f}秒]")
                    st.write("⚙️ 第3段階：並列演算・フィルタリングを実行中...")

                    def scan_unit_t2_parallel(code, group, cfg, v_avg):
                        c_vals = group['AdjC'].values
                        lc = c_vals[-1]
                        rsi, _, _, hist = get_fast_indicators(c_vals)
                        
                        if rsi > cfg["rsi_lim"]: return None
                        
                        gc_days = 0
                        if len(hist) >= 4:
                            if hist[-2] < 0 and hist[-1] >= 0: gc_days = 1
                            elif hist[-3] < 0 and hist[-1] >= 0: gc_days = 2
                            elif hist[-4] < 0 and hist[-1] >= 0: gc_days = 3
                        if gc_days == 0: return None

                        if cfg["f12_ex_overvalued"]:
                            f_data = get_fundamentals(code[:4])
                            if f_data and (f_data.get("op", 0) or 0) < 0: return None
                        
                        is_assault = "狙撃優先" in cfg["tactics"]
                        t_rank, t_color, t_score, _ = get_assault_triage_info(gc_days, lc, rsi, group, is_strict=is_assault)
                        
                        h_vals = group['AdjH'].values
                        h14 = h_vals[-14:].max()
                        atr = h14 * 0.03
                        
                        return {'Code': code, 'lc': float(lc), 'RSI': float(rsi), 'T_Rank': t_rank, 'T_Color': t_color, 'T_Score': t_score, 'GC_Days': gc_days, 'h14': float(h14), 'atr': float(atr), 'avg_vol': int(v_avg)}

                    results = []
                    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
                        futures = [executor.submit(scan_unit_t2_parallel, c, g, config_t2, avg_vols_series.get(c, 0)) for c, g in df.groupby('Code')]
                        for f in concurrent.futures.as_completed(futures):
                            try:
                                res = f.result()
                                if res: results.append(res)
                            except: pass
                    
                    sorted_raw = sorted(results, key=lambda x: (-x['T_Score'], x['GC_Days']))
                    filtered_results = []
                    sector_counts = {}
                    for r in sorted_raw:
                        sector = master_map_t2.get(str(r['Code']), {}).get('Sector', '不明')
                        if sector_counts.get(sector, 0) < 3:
                            filtered_results.append(r)
                            sector_counts[sector] = sector_counts.get(sector, 0) + 1
                        if len(filtered_results) >= 30: break
                    
                    st.session_state.tab2_scan_results = filtered_results
                    t_calc = time.time()
                    
                    st.write(f"✔️ 第3段階完了：並列演算・フィルタリング [{t_calc - t_clean:.2f}秒]")
                    status.update(label=f"🎯 スキャン完了！ (総所要時間: {t_calc - t_global_start:.2f}秒)", state="complete", expanded=False)

            except Exception as e:
                st.error(f"🚨 スキャン中に内部エラーが発生しました。処理を安全に中断しました。\n詳細: {str(e)}")
                status.update(label="🚨 エラー発生により中断", state="error")

    if st.session_state.tab2_scan_results:
        res_list = st.session_state.tab2_scan_results
        st.success(f"⚡ 強襲ロックオン: GC発動(3日以内) 上位 {len(res_list)} 銘柄（セクター分散適用済）")
        
        sab_codes = " ".join([str(r['Code'])[:4] for r in res_list if str(r['T_Rank']).startswith(('S', 'A', 'B'))])
        st.info("📋 以下のコードをコピーして、照準（TAB3）にペースト可能だ。")
        st.code(sab_codes, language="text")

        for r in res_list:
            st.divider()
            # 🚨 防弾：UIループ中のNaNクラッシュを根絶する解毒関数
            def safe_int(x):
                try: return int(float(x)) if not pd.isna(x) else 0
                except: return 0

            c_code = str(r['Code']); m_info = master_map_t2.get(c_code, {})
            m_lower = str(m_info.get('Market', '')).lower()
            if 'プライム' in m_lower or '一部' in m_lower: badge_html = '<span style="background-color: #1a237e; color: #ffffff; padding: 0.2rem 0.6rem; border-radius: 4px; font-size: 11px; font-weight: bold;">🏢 プライム/大型</span>'
            elif 'グロース' in m_lower or 'マザーズ' in m_lower: badge_html = '<span style="background-color: #1b5e20; color: #ffffff; padding: 0.2rem 0.6rem; border-radius: 4px; font-size: 11px; font-weight: bold;">🚀 グロース/新興</span>'
            else: badge_html = f'<span style="background-color: #455a64; color: #ffffff; padding: 0.2rem 0.6rem; border-radius: 4px; font-size: 11px; font-weight: bold;">{m_info.get("Market","不明")}</span>'
            
            t_badge = f'<span style="background-color: {r["T_Color"]}; color: #ffffff; padding: 0.2rem 0.6rem; border-radius: 4px; font-size: 13px; font-weight: bold; margin-left: 0.5rem;">🎯 優先度: {r["T_Rank"]}</span>'
            sector_badge = f'<span style="background-color: #607d8b; color: #ffffff; padding: 0.1rem 0.5rem; border-radius: 4px; font-size: 12px; margin-left: 0.5rem;">🏭 {m_info.get("Sector", "不明")}</span>'
            
            st.markdown(f"""
                <div style="margin-bottom: 0.8rem;">
                    <h3 style="font-size: 24px; font-weight: bold; margin: 0 0 0.3rem 0;">({c_code[:4]}) {m_info.get('CompanyName', '不明')}</h3>
                    <div style="display: flex; flex-wrap: wrap; gap: 6px; align-items: center;">
                        {badge_html}{t_badge}{sector_badge}
                        <span style="background-color: rgba(237, 108, 2, 0.15); border: 1px solid #ed6c02; color: #ed6c02; padding: 0.1rem 0.5rem; border-radius: 4px; font-size: 12px;">GC発動 {r['GC_Days']}日目</span>
                        <span style="background-color: rgba(38, 166, 154, 0.15); border: 1px solid #26a69a; color: #26a69a; padding: 0.1rem 0.5rem; border-radius: 4px; font-size: 12px;">RSI: {r['RSI']:.1f}%</span>
                    </div>
                </div>
            """, unsafe_allow_html=True)
            
            # 🚨 防弾：全て safe_int で保護
            lc_v, h14_v, atr_v = safe_int(r.get('lc', 0)), safe_int(r.get('h14', 0)), safe_int(r.get('atr', 0))
            t_price = max(h14_v, lc_v + int(atr_v * 0.5))
            d_price = t_price - atr_v
            
            m_cols = st.columns([1, 1, 1, 1.2, 1.5])
            m_cols[0].metric("最新終値", f"{lc_v:,}円")
            m_cols[1].metric("RSI", f"{r['RSI']:.1f}%")
            m_cols[2].metric("ボラ(推定)", f"{atr_v:,}円")
            m_cols[3].markdown(f'<div style="background: rgba(239, 83, 80, 0.05); padding: 0.5rem; border-radius: 8px; border: 1px solid rgba(239, 83, 80, 0.3); text-align: center;"><div style="font-size: 13px; color: rgba(250, 250, 250, 0.6); margin-bottom: 2px;">🛡️ 防衛線</div><div style="font-size: 1.6rem; font-weight: bold; color: #ef5350;">{d_price:,}円</div></div>', unsafe_allow_html=True)
            m_cols[4].markdown(f'<div style="background: rgba(255, 215, 0, 0.05); padding: 0.5rem; border-radius: 8px; border: 1px solid rgba(255, 215, 0, 0.2); text-align: center;"><div style="font-size: 13px; color: rgba(250, 250, 250, 0.6); margin-bottom: 2px;">🎯 トリガー</div><div style="font-size: 1.6rem; font-weight: bold; color: #FFD700;">{t_price:,}円</div></div>', unsafe_allow_html=True)
            
# --- 8. タブコンテンツ (TAB3: 精密スコープ) ---
with tab3:
        st.markdown('<h3 style="font-size: clamp(14px, 4.5vw, 24px); margin-bottom: 1rem;">🎯 【照準】精密スコープ（戦術ウェイト・UI完全復元版）</h3>', unsafe_allow_html=True)
        
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
            scope_mode = st.radio("🎯 解析モードを選択", ["🌐 【待伏】 押し目・逆張り", "⚡ 【強襲】 トレンド・順張り"], key=f"t3_scope_mode_vfinal_{cache_key}")
            is_ambush = "待伏" in scope_mode
            st.markdown("---")
            
            if is_ambush:
                watch_in = st.text_area("🌐 【待伏】主力監視部隊", value=st.session_state.t3_am_watch, height=120, key=f"t3_am_watch_ui_vfinal")
                daily_in = st.text_area("🌐 【待伏】本日新規部隊", value=st.session_state.t3_am_daily, height=120, key=f"t3_am_daily_ui_vfinal")
            else:
                watch_in = st.text_area("⚡ 【強襲】主力監視部隊", value=st.session_state.t3_as_watch, height=120, key=f"t3_as_watch_ui_vfinal")
                daily_in = st.text_area("⚡ 【強襲】本日新規部隊", value=st.session_state.t3_as_daily, height=120, key=f"t3_as_daily_ui_vfinal")
                
            run_scope = st.button("🔫 表示中の部隊を精密スキャン", use_container_width=True, type="primary", key=f"t3_run_btn_vfinal_{cache_key}")
            
        with col_s2:
            st.markdown("#### 🔍 索敵ステータス")
            if is_ambush:
                st.info("**🛡️ 待伏（アンブッシュ）モード：底打ち反転の迎撃戦**\n- **主戦場**: 直近高安の黄金比における底堅いエリア。\n- **判定核**: MACDの好転に加え、「たくり足」「陽の包み足」等。\n- **安全装置**: PBR 5.0倍以下の割安性を評価し「大底圏」を狙撃。")
            else:
                st.info("**⚡ 強襲（アサルト）モード：トレンド初動の電撃戦**\n- **主戦場**: 14日高値周辺。上昇へのエネルギー解放の瞬間。\n- **判定核**: MACD GCの鮮度(1〜3日)と出来高急増。\n- **突破力**: 直近高値のブレイクアウトを評価し加速局面へ同乗。")

        if run_scope:
            if is_ambush:
                st.session_state.t3_am_watch, st.session_state.t3_am_daily = watch_in, daily_in
                for f, d in [(T3_AM_WATCH_FILE, watch_in), (T3_AM_DAILY_FILE, daily_in)]:
                    with open(f, "w", encoding="utf-8") as file: file.write(d)
            else:
                st.session_state.t3_as_watch, st.session_state.t3_as_daily = watch_in, daily_in
                for f, d in [(T3_AS_WATCH_FILE, watch_in), (T3_AS_DAILY_FILE, daily_in)]:
                    with open(f, "w", encoding="utf-8") as file: file.write(d)

            import unicodedata
            raw_all_text = watch_in + " " + daily_in
            all_text = unicodedata.normalize('NFKC', raw_all_text).upper()
            t_codes = list(dict.fromkeys([c for c in re.findall(r'(?<![A-Z0-9])[0-9]{3}[0-9A-Z][0-9]?(?![A-Z0-9])', all_text)]))
            
            if not t_codes:
                st.warning("有効な銘柄コードが確認できません。")
            else:
                t_global_start = time.time()
                
                with st.status(f"🚀 全 {len(t_codes)} 銘柄を精密スキャン中...", expanded=True) as status:
                    st.write("📡 第1段階：並列データ収集（J-Quants / yfinance）を実行中...")
                    
                    def fetch_parallel_t3(c):
                        try:
                            c_str = str(c).upper().strip()
                            api_code = c_str if len(c_str) >= 5 else c_str + "0"
                            data = get_single_data(api_code, 1)
                            
                            if not data or not isinstance(data.get("bars"), list) or len(data.get("bars", [])) < 30:
                                try:
                                    import yfinance as yf
                                    tk = yf.Ticker(c_str + ".T")
                                    hist = tk.history(period="1y")
                                    if not hist.empty:
                                        bars = [{'Code': api_code, 'Date': dt.strftime('%Y-%m-%d'), 'AdjO': float(row['Open']), 'AdjH': float(row['High']), 'AdjL': float(row['Low']), 'AdjC': float(row['Close']), 'Volume': float(row['Volume'])} for dt, row in hist.iterrows()]
                                        data = {"bars": bars, "events": {"dividend": [], "earnings": []}}
                                    else: data = None
                                except: data = None

                            f_data = get_fundamentals(c_str)
                            r_per, r_pbr, r_mcap, r_roe = None, None, None, None
                            if f_data:
                                r_per = f_data.get('per') or f_data.get('PER') or f_data.get('trailingPE')
                                r_pbr = f_data.get('pbr') or f_data.get('PBR') or f_data.get('priceToBook')
                                r_mcap = f_data.get('mcap') or f_data.get('MCAP') or f_data.get('marketCap')
                                r_roe = f_data.get('roe') or f_data.get('ROE') or f_data.get('returnOnEquity')
                                if r_roe is None:
                                    ni, eq = f_data.get("NetIncome"), f_data.get("Equity")
                                    if ni is not None and eq is not None and float(eq) != 0:
                                        try: r_roe = (float(ni) / float(eq)) * 100
                                        except: pass

                            if any(v is None for v in [r_per, r_pbr, r_mcap, r_roe]):
                                try:
                                    import yfinance as yf
                                    tk_f = yf.Ticker(c_str + ".T")
                                    info = tk_f.info
                                    if info:
                                        r_per = r_per or info.get('trailingPE')
                                        r_pbr = r_pbr or info.get('priceToBook')
                                        r_mcap = r_mcap or info.get('marketCap')
                                        if r_roe is None:
                                            raw_roe = info.get('returnOnEquity')
                                            if raw_roe: r_roe = raw_roe * 100
                                except: pass
                            return c_str, data, r_per, r_pbr, r_mcap, r_roe
                        except:
                            return str(c), None, None, None, None, None

                    raw_data_dict = {}
                    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as exe:
                        futs = [exe.submit(fetch_parallel_t3, c) for c in t_codes]
                        for f in concurrent.futures.as_completed(futs):
                            try:
                                res_c, res_data, r_per, r_pbr, r_mcap, r_roe = f.result()
                                raw_data_dict[str(res_c)] = {"data": res_data, "per": r_per, "pbr": r_pbr, "mcap": r_mcap, "roe": r_roe}
                            except: continue

                    t_fetch = time.time()
                    st.write(f"✔️ 第1段階完了：データ収集 [{t_fetch - t_global_start:.2f}秒]")
                    st.write("⚙️ 第2段階：解析・スコアリング処理を実行中...")

                    scope_results = []
                    for c in t_codes:
                        target_key = str(c).upper().strip()
                        try:
                            raw_s = raw_data_dict.get(target_key)
                            if not raw_s: raw_s = {} 

                            api_code = target_key if len(target_key) >= 5 else target_key + "0"
                            c_name, c_sector, c_market = f"銘柄 {target_key}", "不明", "不明"
                            if not master_df.empty:
                                m_row = master_df[master_df['Code'].astype(str).isin([target_key, api_code])]
                                if not m_row.empty:
                                    c_name, c_sector, c_market = m_row.iloc[0]['CompanyName'], m_row.iloc[0]['Sector'], m_row.iloc[0]['Market']

                            res_per, res_pbr, res_roe, raw_mcap = raw_s.get('per'), raw_s.get('pbr'), raw_s.get('roe'), raw_s.get('mcap')
                            
                            try: res_roe = float(res_roe) if res_roe is not None else None
                            except: res_roe = None
                            if res_roe is not None and 0 < abs(res_roe) < 1.0: res_roe = res_roe * 100

                            if raw_mcap is not None:
                                try:
                                    rmc = float(raw_mcap)
                                    if rmc >= 1e12: res_mcap_str = f"{rmc / 1e12:.2f}兆円"
                                    elif rmc >= 1e8: res_mcap_str = f"{rmc / 1e8:.0f}億円"
                                    else: res_mcap_str = f"{int(rmc):,}"
                                except: res_mcap_str = "-"
                            else: res_mcap_str = "-"

                            bars = raw_s.get("data", {}).get("bars", []) if raw_s.get("data") else []

                            if st.session_state.get('f5_ipo', False):
                                try:
                                    m_row = master_df[master_df['Code'].astype(str).isin([target_key, api_code])]
                                    if not m_row.empty:
                                        ld_col = [col for col in m_row.columns if 'Listing' in col]
                                        if ld_col and pd.notna(m_row.iloc[0][ld_col[0]]):
                                            target_dt = pd.to_datetime(m_row.iloc[0][ld_col[0]]).replace(tzinfo=None)
                                            if (datetime.now().replace(tzinfo=None) - target_dt).days < 365:
                                                continue 
                                except Exception:
                                    pass

                            if not bars or len(bars) < 20:
                                scope_results.append({
                                    'code': target_key, 'name': c_name, 'lc': 0, 'h14': 0, 'l14': 0, 'ur': 0, 'bt_val': 0, 'atr_val': 0, 'rsi': 50,
                                    'rank': '圏外💀', 'bg': '#616161', 'score': 0, 'reach_val': 0, 'gc_days': 0, 'df_chart': pd.DataFrame(),
                                    'per': res_per, 'pbr': res_pbr, 'roe': res_roe, 'mcap': res_mcap_str, 'source': "🛡️ 監視" if target_key in watch_in else "🚀 新規", 
                                    'sector': c_sector, 'market': c_market, 'alerts': ["⚠️ 兵站データ不足"], 'error': True, 'is_deep': False
                                })
                                continue

                            df_raw = pd.DataFrame(bars)
                            if 'Code' not in df_raw.columns: df_raw['Code'] = api_code
                            df_s = clean_df(df_raw)
                            
                            if df_s.empty or len(df_s) < 20:
                                scope_results.append({
                                    'code': target_key, 'name': c_name, 'lc': 0, 'h14': 0, 'l14': 0, 'ur': 0, 'bt_val': 0, 'atr_val': 0, 'rsi': 50,
                                    'rank': '圏外💀', 'bg': '#616161', 'score': 0, 'reach_val': 0, 'gc_days': 0, 'df_chart': pd.DataFrame(),
                                    'per': res_per, 'pbr': res_pbr, 'roe': res_roe, 'mcap': res_mcap_str, 'source': "🛡️ 監視" if target_key in watch_in else "🚀 新規", 
                                    'sector': c_sector, 'market': c_market, 'alerts': ["⚠️ 兵站データ破損（有効なローソク足が不足）"], 'error': True, 'is_deep': False
                                })
                                continue

                            try: df_chart_full = calc_technicals(df_s.copy())
                            except: df_chart_full = df_s.copy()
                            
                            t_latest, t_prev, t_pprev = df_chart_full.iloc[-1], df_chart_full.iloc[-2], df_chart_full.iloc[-3]
                            lc, lo, lh, ll = float(t_latest['AdjC']), float(t_latest['AdjO']), float(t_latest['AdjH']), float(t_latest['AdjL'])
                            pc, po, ph, pl = float(t_prev['AdjC']), float(t_prev['AdjO']), float(t_prev['AdjH']), float(t_prev['AdjL'])
                            pph = float(t_pprev['AdjH'])
                            
                            h14 = float(df_chart_full.tail(15).iloc[:-1]['AdjH'].max())
                            l14 = float(df_chart_full.tail(15).iloc[:-1]['AdjL'].min())
                            ur_v = (h14 - l14)
                            rsi_v = float(t_latest.get('RSI', 50))
                            atr_v = float(t_latest.get('ATR', lc * 0.05))
                            df_mini = df_chart_full.tail(260).copy()
                            
                            score, alerts, gc_days, is_deep = 0, [], 0, False
                            alerts.extend(check_event_mines(target_key, raw_s.get("data", {}).get("events")))

                            if is_ambush:
                                score = 4
                                base_push_r = st.session_state.push_r / 100.0
                                bt_val_standard = h14 - (ur_v * base_push_r)
                                bt_val_deep = h14 - (ur_v * 0.618)
                                # 🚨 戦術補正：オーバーシュート判定を 10%下落(0.90) から 5%下落(0.95) へタイト化
                                panic_line = bt_val_standard * 0.95 

                                if lc < panic_line:
                                    bt_val = int(bt_val_deep)
                                    is_deep = True
                                    alerts.append(f"💎 【深海待伏】オーバーシュート(標準目標から5%以上下落)を検知。買値を61.8%押しへ下方修正。")
                                else: bt_val = int(bt_val_standard)

                                m1, m2 = float(t_latest.get('MACD_Hist', 0)), float(t_prev.get('MACD_Hist', 0))
                                _, _, t_score, _ = get_triage_info(m1, m2, rsi_v, lc, bt_val, mode="待伏")
                                score += t_score
                                if res_pbr is not None and res_pbr <= 5.0: score += 2
                                
                                body_v, shadow_l, full_rng = abs(lc - lo), min(lc, lo) - ll, lh - ll
                                if full_rng > 0 and shadow_l > (body_v * 2.5) and (shadow_l / full_rng) > 0.6 and rsi_v < 45:
                                    alerts.append("🟢 【酒田】たくり線検知。底打ち反転の急所。")
                                    score += 5
                                
                                if check_double_bottom(df_chart_full.tail(31)): alerts.append("🟢 【酒田】二重底（ダブルボトム）形成。底打ち反転。")
                                if check_oversold_ultimate(df_chart_full): alerts.append("💎 【陰の極み】最終波形。絶好の狙撃ポイント。")

                                reach_rate = ((h14 - lc) / (h14 - bt_val) * 100) if (h14 - bt_val) > 0 else 0
                                rank, bg_c = ("S級待伏🔥", "#1b5e20") if score >= 12 else ("A級待伏💎", "#2e7d32") if score >= 8 else ("B級待伏🛡️", "#4caf50") if score >= 5 else ("圏外💀", "#616161")
                            else:
                                bt_val = int(max(h14, lc + (atr_v * 0.5)))
                                hist_vals = df_mini['MACD_Hist'].tail(5).values
                                gc_score = 0
                                if len(hist_vals) >= 2:
                                    if hist_vals[-2] < 0 and hist_vals[-1] >= 0: gc_days, gc_score = 1, 60
                                    elif len(hist_vals) >= 3 and hist_vals[-3] < 0 and hist_vals[-1] >= 0: gc_days, gc_score = 2, 40
                                    else: gc_score = 5
                                
                                if pph > ph and lh > ph and abs(pph - lh) < (pph * 0.02) and rsi_v > 70: alerts.append("🔴 【酒田】三尊警戒。戦域は天井圏。")
                                if check_double_top(df_chart_full.tail(31)): alerts.append("🔴 【酒田】二重天井（ダブルトップ）形成の兆候。")

                                if res_roe is not None and res_roe >= 10.0: score += 10
                                score = gc_score + (10 if (res_roe is not None and res_roe >= 10.0) else 0)
                                reach_rate = (lc / h14) * 100 if h14 > 0 else 0
                                rank, bg_c = ("S級強襲⚡", "#1b5e20") if score >= 80 else ("A級強襲🔥", "#2e7d32") if score >= 60 else ("B級強襲📈", "#4caf50") if score >= 40 else ("圏外💀", "#616161")

                            scope_results.append({
                                'code': target_key, 'name': c_name, 'lc': lc, 'h14': h14, 'l14': l14, 'ur': ur_v, 'bt_val': bt_val, 'atr_val': atr_v, 'rsi': rsi_v,
                                'rank': rank, 'bg': bg_c, 'score': score, 'reach_val': reach_rate, 'gc_days': gc_days, 'df_chart': df_mini, 
                                'per': res_per, 'pbr': res_pbr, 'roe': res_roe, 'mcap': res_mcap_str,
                                'source': "🛡️ 監視" if target_key in watch_in else "🚀 新規", 'sector': c_sector, 'market': c_market, 
                                'alerts': alerts, 'error': False, 'is_deep': is_deep
                            })
                        except Exception as e:
                            scope_results.append({
                                'code': target_key, 'name': c_name if 'c_name' in locals() else f"銘柄 {target_key}", 'lc': 0, 'h14': 0, 'l14': 0, 'ur': 0, 'bt_val': 0, 'atr_val': 0, 'rsi': 50,
                                'rank': '圏外💀', 'bg': '#616161', 'score': 0, 'reach_val': 0, 'gc_days': 0, 'df_chart': pd.DataFrame(),
                                'per': None, 'pbr': None, 'roe': None, 'mcap': "-", 'source': "🛡️ 監視" if target_key in watch_in else "🚀 新規", 
                                'sector': "不明", 'market': "不明", 'alerts': [f"⚠️ 演算中に致命傷が発生: {str(e)}"], 'error': True, 'is_deep': False
                            })
                            continue

                    rank_order = {"S": 4, "A": 3, "B": 2, "圏外": 0}
                    for res in scope_results:
                        res['r_val'] = rank_order.get(re.sub(r'[^SABC圏外]', '', res['rank']), 0)
                    scope_results = sorted(scope_results, key=lambda x: (x['r_val'], x['score'], x['reach_val']), reverse=True)
                    
                    t_calc = time.time()
                    st.write(f"✔️ 第2段階完了：解析・スコアリング [{t_calc - t_fetch:.2f}秒]")
                    status.update(label=f"🎯 スキャン完了！ (総所要時間: {t_calc - t_global_start:.2f}秒)", state="complete", expanded=False)

            # --- 🎨 6. 神聖UI描画（絶対防弾化） ---
            for index, r in enumerate(scope_results):
                st.divider()
                
                def safe_int(x):
                    try: return int(float(x)) if not pd.isna(x) else 0
                    except: return 0
                def safe_float(x):
                    try: return float(x) if not pd.isna(x) else None
                    except: return None
                
                has_chart = not (r.get('error') or r.get('df_chart') is None or r['df_chart'].empty)

                source_color = "#42a5f5" if "監視" in r['source'] else "#ffa726"
                m_lower = str(r['market']).lower()
                if 'プライム' in m_lower or '一部' in m_lower: m_badge = '<span style="background-color: #1a237e; color: #ffffff; padding: 0.2rem 0.6rem; border-radius: 4px; font-size: 11px; font-weight: bold;">🏢 プライム/大型</span>'
                elif 'グロース' in m_lower or 'マザーズ' in m_lower: m_badge = '<span style="background-color: #1b5e20; color: #ffffff; padding: 0.2rem 0.6rem; border-radius: 4px; font-size: 11px; font-weight: bold;">🚀 グロース/新興</span>'
                else: m_badge = f'<span style="background-color: #455a64; color: #ffffff; padding: 0.2rem 0.6rem; border-radius: 4px; font-size: 11px; font-weight: bold;">{r["market"]}</span>'
                
                s_badge = f"<span style='background-color:{source_color}; color:white; padding:2px 6px; border-radius:4px; font-size:12px;'>{r['source']}</span>"
                t_badge = f"<span style='background-color:{r['bg']}; color:white; padding:2px 8px; border-radius:4px; margin-left:10px; font-weight:bold;'>🎯 優先度: {r['rank']}</span>"
                gc_badge = f"<span style='background-color: #1b5e20; color: #ffffff; padding: 2px 10px; border-radius: 4px; font-size: 13px; font-weight: bold; margin-left: 10px; border: 1px solid #81c784;'>⚡ GC発動 {r['gc_days']}日目</span>" if r.get('gc_days', 0) > 0 else ""
                
                st.markdown(f"""
                    <div style="margin-bottom: 0.8rem;">
                        <h3 style="font-size: clamp(18px, 5vw, 28px); font-weight: bold; margin: 0 0 0.3rem 0;">{s_badge} ({r['code']}) {r['name']}</h3>
                        <div style="display: flex; flex-wrap: wrap; gap: 6px; align-items: center;">
                            {m_badge}{t_badge}{gc_badge}
                            <span style="background-color: #607d8b; color: #ffffff; padding: 0.1rem 0.5rem; border-radius: 4px; font-size: 12px;">🏭 {r['sector']}</span>
                            <span style="background-color: rgba(38, 166, 154, 0.15); border: 1px solid #26a69a; color: #26a69a; padding: 0.1rem 0.5rem; border-radius: 4px; font-size: 12px;">RSI: {safe_float(r.get('rsi', 0)) or 0:.1f}%</span>
                        </div>
                    </div>
                """, unsafe_allow_html=True)
                
                if r.get('alerts'):
                    for alert in r['alerts']:
                        if any(mark in alert for mark in ["🟢", "⚡", "🔥", "💎"]): st.success(alert)
                        elif any(mark in alert for mark in ["🔴", "💀", "💣", "⚠️"]): st.error(alert)
                        else: st.warning(alert)

                if not has_chart:
                    st.warning("⚠️ ローソク足データが不足または破損しているため、チャートの描画をスキップしました。")
                    if not (r.get('per') or r.get('pbr')): 
                        continue
                
                sc_left, sc_mid, sc_right = st.columns([2.5, 3.5, 5.0])
                
                with sc_left:
                    h14_v, l14_v, ur_v, lc_v = safe_int(r.get('h14')), safe_int(r.get('l14')), safe_int(r.get('ur')), safe_int(r.get('lc'))
                    atr_v = safe_float(r.get('atr_val')) or 0.0
                    atr_pct = (atr_v / lc_v * 100) if lc_v > 0 else 0
                    
                    c_m1, c_m2 = st.columns(2)
                    c_m1.metric("直近高値", f"{h14_v:,}円")
                    c_m2.metric("起点安値", f"{l14_v:,}円")
                    c_m3, c_m4 = st.columns(2)
                    c_m3.metric("波高(14d)", f"{ur_v:,}円")
                    c_m4.metric("最新終値", f"{lc_v:,}円")
                    st.metric("🌪️ 1ATR", f"{safe_int(atr_v):,}円", f"ボラ: {atr_pct:.1f}%", delta_color="off")
                
                with sc_mid:
                    roe_v, per_v, pbr_v = safe_float(r.get('roe')), safe_float(r.get('per')), safe_float(r.get('pbr'))
                    
                    roe_s, roe_c = (f"{roe_v:.1f}%", "#26a69a") if roe_v and roe_v >= 10.0 else (f"{roe_v:.1f}%" if roe_v else "-", "#ef5350")
                    per_s, per_c = (f"{per_v:.1f}倍", "#26a69a") if per_v and per_v <= 20.0 else (f"{per_v:.1f}倍" if per_v else "-", "#ef5350")
                    pbr_s, pbr_c = (f"{pbr_v:.2f}倍", "#26a69a") if pbr_v and pbr_v <= 5.0 else (f"{pbr_v:.2f}倍" if pbr_v else "-", "#ef5350")
                    mcap_s = str(r.get('mcap', "-"))
                    
                    box_title = ("💎 深海買値(61.8%)" if r.get('is_deep') else "🎯 買値目標") if is_ambush else "🎯 トリガー"
                    
                    st.markdown(f"""
                        <div style='background:rgba(255,215,0,0.05); padding:1.2rem; border-radius:10px; border:1px solid rgba(255,215,0,0.3); text-align:center;'>
                            <div style='font-size:14px; color: #eee; margin-bottom: 0.4rem;'>{box_title}</div>
                            <div style='font-size:2.4rem; font-weight:bold; color:#FFD700; margin: 0.2rem 0;'>{safe_int(r.get('bt_val')):,}円</div>
                            <div style='display:flex; justify-content:space-around; margin-top:10px; font-size:12px; border-top:1px dashed #444; padding-top:10px;'>
                                <div style='flex:1;'><div style='color:#888; font-size:10px;'>PER</div><div style='color:{per_c}; font-weight:bold; font-size:1.1rem;'>{per_s}</div></div>
                                <div style='flex:1;'><div style='color:#888; font-size:10px;'>PBR</div><div style='color:{pbr_c}; font-weight:bold; font-size:1.1rem;'>{pbr_s}</div></div>
                                <div style='flex:1;'><div style='color:#888; font-size:10px;'>ROE</div><div style='color:{roe_c}; font-weight:bold; font-size:1.1rem;'>{roe_s}</div></div>
                            </div>
                            <div style='margin-top:5px; border-top:1px solid rgba(255,255,255,0.05); padding-top:5px;'>
                                <span style='color:#888; font-size:11px;'>時価総額: </span><span style='color:#fff; font-size:11px; font-weight:bold;'>{mcap_s}</span>
                            </div>
                        </div>
                    """, unsafe_allow_html=True)

                with sc_right:
                    c_target = safe_int(r.get('bt_val'))
                    is_agg = any(mark in r['rank'] for mark in ["⚡", "🔥", "S"])
                    rec_tps = [2.0, 3.0] if is_agg else [0.5, 1.0]
                    
                    html_matrix = f"<div style='background:rgba(255,255,255,0.05); padding:1.2rem; border-radius:8px; border-left:5px solid #FFD700; min-height: 125px;'><div style='font-size:14px; color:#aaa; margin-bottom:12px; border-bottom:1px solid #444; padding-bottom:4px;'>📊 動的ATRマトリクス (基準:{c_target:,}円)</div><div style='display:flex; gap:30px;'><div style='flex:1;'><div style='color:#26a69a; border-bottom:2px solid #26a69a; margin-bottom:8px;'>【利確目安】</div>"
                    
                    for m in [0.5, 1.0, 2.0, 3.0]:
                        val = int(c_target + (atr_v * m))
                        pct = ((val / c_target) - 1) * 100 if c_target > 0 else 0
                        style = "background:rgba(38,166,154,0.15); border:1px solid #26a69a; border-radius:4px; padding:2px 6px;" if m in rec_tps else "padding:3px 6px;"
                        label = "<span style='font-size:10px; background:#26a69a; color:white; padding:1px 4px; border-radius:2px; margin-left:2px;'>推奨</span>" if m in rec_tps else ""
                        html_matrix += f"<div style='display:flex; justify-content:space-between; margin-bottom:4px; {style}'><span>+{m}ATR <span style='font-size:10px; color:#888;'>({pct:+.1f}%)</span>{label}</span><b style='font-size:1.1rem;'>{val:,}</b></div>"
                    
                    html_matrix += "</div><div style='flex:1;'><div style='color:#ef5350; border-bottom:2px solid #ef5350; margin-bottom:8px;'>【防衛目安】</div>"
                    
                    for m in [0.5, 1.0, 2.0]:
                        val = int(c_target - (atr_v * m))
                        pct = (1 - (val / c_target)) * 100 if c_target > 0 else 0
                        style = "background:rgba(239,83,80,0.15); border:1px solid #ef5350; border-radius:4px; padding:2px 6px;" if m == 1.0 else "padding:3px 6px;"
                        label = "<span style='font-size:10px; background:#ef5350; color:white; padding:1px 4px; border-radius:2px; margin-left:2px;'>鉄則</span>" if m == 1.0 else ""
                        html_matrix += f"<div style='display:flex; justify-content:space-between; margin-bottom:4px; {style}'><span>-{m}ATR <span style='font-size:10px; color:#888;'>({pct:.1f}%)</span>{label}</span><b style='font-size:1.1rem;'>{val:,}</b></div>"
                    
                    st.markdown(html_matrix + "</div></div></div>", unsafe_allow_html=True)

                if has_chart:
                    try:
                        st.markdown(render_technical_radar(r['df_chart'], c_target, st.session_state.bt_tp), unsafe_allow_html=True)
                    except Exception as e:
                        st.error(f"⚠️ レーダー描画エラー: {str(e)}")
                    st.markdown("---")
                    try:
                        draw_chart(r['df_chart'], c_target, chart_key=f"t3_chart_final_{r['code']}_{index}_{cache_key}")
                    except Exception as e:
                        st.error(f"⚠️ チャート描画エラー: {str(e)}")
                    
# --- 9. タブコンテンツ (TAB4: 戦術シミュレータ) ---
with tab4:
    st.markdown('<h3 style="font-size: clamp(14px, 4.5vw, 24px); margin-bottom: 1rem;">⚙️ 戦術シミュレータ (2年間のバックテスト)</h3>', unsafe_allow_html=True)
    
    # --- 🛡️ 状態初期化・物理ロック回路 ---
    # 1. 物理デフォルト値と保存用キーの導通確認
    tab4_defaults = {
        "bt_mode_sim_v2": "🌐 【待伏】鉄の掟 (押し目狙撃)",
        "sim_tp_val": 10, "sim_sl_val": 8, "sim_limit_d_val": 4, "sim_sell_d_val": 10,
        "sim_push_r_val": st.session_state.get("push_r", 50.0),
        "sim_pass_req_val": 7, "sim_rsi_lim_ambush_val": 45,
        "sim_rsi_lim_assault_val": 70, "sim_time_risk_val": 5
    }

    for k, v in tab4_defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v
        # 🚨 物理リカバリー：意図しない0化を防止
        elif isinstance(v, (int, float)) and st.session_state[k] == 0:
            st.session_state[k] = v

    # 2. モード切替検知とパラメーター自動再装填
    current_mode = st.session_state.bt_mode_sim_v2
    if "prev_mode_for_sync" not in st.session_state:
        st.session_state.prev_mode_for_sync = current_mode

    if st.session_state.prev_mode_for_sync != current_mode:
        if "待伏" in current_mode:
            st.session_state.sim_limit_d_val = 4
            st.session_state.sim_sell_d_val = 10
        else:
            st.session_state.sim_limit_d_val = 3
            st.session_state.sim_sell_d_val = 5
        st.session_state.prev_mode_for_sync = current_mode
        save_settings()

    # 3. サイドバーの「押し目率」変更を検知して演習値へ強制反映
    current_sidebar_push = st.session_state.get("push_r", 50.0)
    if "last_known_sidebar_push" not in st.session_state:
        st.session_state.last_known_sidebar_push = current_sidebar_push

    if st.session_state.last_known_sidebar_push != current_sidebar_push:
        st.session_state.sim_push_r_val = current_sidebar_push
        st.session_state.last_known_sidebar_push = current_sidebar_push
        save_settings()

    col_b1, col_b2 = st.columns([1, 1.8])
    T4_FILE = f"saved_t4_codes_{user_id}.txt"
    default_t4 = "7839\n6614"
    if os.path.exists(T4_FILE):
        try:
            with open(T4_FILE, "r", encoding="utf-8") as f: default_t4 = f.read()
        except: pass

    with col_b1: 
        st.markdown("🔍 **検証戦術**")
        # 💎 物理ロック：key指定によりst.session_state.bt_mode_sim_v2と直結
        st.radio("戦術モード", ["🌐 【待伏】鉄の掟 (押し目狙撃)", "⚡ 【強襲】GCブレイクアウト (順張り)"], key="bt_mode_sim_v2", on_change=save_settings)
        bt_c_in = st.text_area("銘柄コード", value=default_t4, height=100, key="bt_codes_sim_v2")
        run_bt = st.button("🔥 仮想実弾テスト実行", use_container_width=True)
        optimize_bt = st.button("🚀 戦術の黄金比率を抽出 (最適化)", use_container_width=True)
        
    with col_b2:
        st.markdown("#### ⚙️ 戦術パラメーター（演習用チューニング）")
        st.info("※ 戦術切替時、買い期限は自動で「待伏:4日 / 強襲:3日」に最適化されます。")
        cp1, cp2, cp3, cp4 = st.columns(4)
        
        # 💎 物理ロック：value指定を廃止し、keyのみでステートと1:1接続。入力即保存。
        cp1.number_input("🎯 利確目標(%)", step=1, key="sim_tp_val", on_change=save_settings)
        cp2.number_input("🛡️ 損切目安(%)", step=1, key="sim_sl_val", on_change=save_settings)
        cp3.number_input("⏳ 買い期限(日)", step=1, key="sim_limit_d_val", on_change=save_settings)
        cp4.number_input("⏳ 売り期限(日)", step=1, key="sim_sell_d_val", on_change=save_settings)
        
        st.divider()
        if "待伏" in st.session_state.bt_mode_sim_v2:
            st.markdown("##### 🌐 【待伏】シミュレータ固有設定")
            ct1, ct2, ct3 = st.columns(3)
            ct1.number_input("📉 押し目待ち(%)", step=0.1, format="%.1f", key="sim_push_r_val", on_change=save_settings)
            ct2.number_input("掟クリア要求数", step=1, max_value=9, min_value=1, key="sim_pass_req_val", on_change=save_settings)
            ct3.number_input("RSI上限 (過熱感)", step=5, key="sim_rsi_lim_ambush_val", on_change=save_settings)
        else:
            st.markdown("##### ⚡ 【強襲】シミュレータ固有設定")
            ct1, ct2 = st.columns(2)
            ct1.number_input("RSI上限 (過熱感)", step=5, key="sim_rsi_lim_assault_val", on_change=save_settings)
            ct2.number_input("時間リスク上限（到達予想日数）", step=1, key="sim_time_risk_val", on_change=save_settings)

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
                    # 🚨 英字銘柄規格化
                    api_code = c if len(c) >= 5 else c + "0"
                    raw = get_single_data(api_code, 2)
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
                                if atr_prev < 1 or (atr_prev / lc_prev) < 0.01: continue
                                
                                if is_ambush:
                                    r14 = h14 / l14
                                    rsi_prev = prev.get('RSI', 50)
                                    idxmax = win_14['AdjH'].idxmax()
                                    d_high = len(win_14[win_14['Date'] > win_14.loc[idxmax, 'Date']]) if pd.notna(idxmax) else 0
                                    bt_val = int(h14 - ((h14 - l14) * (t_p1 / 100.0)))
                                    
                                    if rsi_prev > sim_rsi_lim_ambush:
                                        continue

                                    score = 0
                                    if 1.3 <= r14 <= 2.0: score += 1
                                    if d_high <= sim_limit_d: score += 1 
                                    if not check_double_top(win_30): score += 1
                                    if not check_head_shoulders(win_30): score += 1
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
                                                eval_h14 = df.iloc[max(0, idx_eval-14):idx_eval]['AdjH'].max()
                                                eval_atr = df.iloc[idx_eval].get('ATR', 0)
                                                eval_c = df.iloc[idx_eval]['AdjC']
                                                trigger_price = eval_h14 if eval_h14 > eval_c else eval_c + (eval_atr * 0.5)
                                                break
                                    
                                    if gc_triggered and rsi_prev <= t_p1 and exp_days < sim_time_risk:
                                        if td['AdjH'] >= trigger_price:
                                            exec_limit = trigger_price + (atr_prev * 0.2)
                                            exec_p = min(max(td['AdjO'], trigger_price), exec_limit)
                                            pos = {'b_i': i, 'b_d': td['Date'], 'b_p': exec_p, 'entry_atr': atr_prev, 'trigger': trigger_price}
                                            
                            else:
                                bp = pos['b_p']; held = i - pos['b_i']; sp = 0
                                current_tp = sim_tp if is_ambush else t_p2
                                e_atr = pos.get('entry_atr', prev.get('ATR', 0))
                                t_price = pos.get('trigger', bp)
                                
                                sl_val = t_price - (e_atr * 1.0)
                                tp_val = bp * (1 + (current_tp / 100.0))
                                
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

# --- 10. タブコンテンツ (TAB5: 交戦モニター) ---
with tab5:
    st.markdown('<h3 style="font-size: clamp(14px, 4.5vw, 24px); margin-bottom: 1rem;">📡 交戦モニター (全軍生存圏レーダー)</h3>', unsafe_allow_html=True)
    st.caption("※ 銘柄コードと株数を入力し、確定（Enter）後に『🔄 全軍同期』を押してください。")

    # 🚨 【物理パッチ】Enter信号をArrowDownに変換し、左上リセットを物理的に封殺するスクリプト
    components.html(
        """
        <script>
        const doc = window.parent.document;
        const sniperEntryPatch = () => {
            const editors = doc.querySelectorAll('div[data-testid="stDataEditor"]');
            editors.forEach(editor => {
                // 既存のリスナーとの衝突を防ぐため、一度クリアする代わりにキャプチャフェーズで奪取
                if (editor.dataset.sniperPatched === 'true') return;
                
                editor.addEventListener('keydown', (e) => {
                    if (e.key === 'Enter') {
                        // ブラウザ標準のEnter挙動（再描画・左上遷移）を阻止
                        e.stopPropagation();
                        
                        // 物理的に「下矢印キー」のイベントを生成し、セル移動を強制
                        const downEvent = new KeyboardEvent('keydown', {
                            key: 'ArrowDown',
                            code: 'ArrowDown',
                            keyCode: 40,
                            which: 40,
                            bubbles: true,
                            cancelable: true
                        });
                        e.target.dispatchEvent(downEvent);
                    }
                }, true); // Capture phaseで確実に実行
                
                editor.dataset.sniperPatched = 'true';
            });
        };
        
        // 描画遅延に対応するため監視を継続
        const observer = new MutationObserver(sniperEntryPatch);
        observer.observe(doc.body, { childList: true, subtree: true });
        sniperEntryPatch();
        </script>
        """,
        height=0,
    )

    FRONTLINE_FILE = f"saved_frontline_{user_id}.csv"
    target_cols = ["銘柄", "株数", "買値", "現在値", "損切", "第1利確", "第2利確", "atr"]

    # --- 1. 物理初期化 ---
    if 'frontline_df' not in st.session_state:
        if os.path.exists(FRONTLINE_FILE):
            try:
                temp_df = pd.read_csv(FRONTLINE_FILE)
                rename_map = {'code': '銘柄', 'price': '現在値', 'buy': '買値', 'target': '第1利確', 'stop': '損切', 'lot': '株数'}
                temp_df = temp_df.rename(columns=rename_map).reindex(columns=target_cols)
                # 🚨 5桁規格化 ＆ 文字列化
                temp_df['銘柄'] = temp_df['銘柄'].astype(str).str.replace(r'\.0$', '', regex=True).replace('nan', '')
                num_cols = ["株数", "買値", "第1利確", "第2利確", "損切", "現在値", "atr"]
                for c in num_cols:
                    temp_df[c] = pd.to_numeric(temp_df[c], errors='coerce')
                
                default_lot = int(st.session_state.get("bt_lot", 100))
                temp_df['株数'] = temp_df['株数'].fillna(default_lot)
                st.session_state.frontline_df = temp_df
            except:
                st.session_state.frontline_df = pd.DataFrame(columns=target_cols)
        else:
            st.session_state.frontline_df = pd.DataFrame(columns=target_cols)

    # --- 2. 司令部エディタ ---
    # 🚨 安定化のため、keyにcache_keyを混ぜず固定（再描画によるフォーカス喪失を抑制）
    working_df = st.data_editor(
        st.session_state.frontline_df,
        num_rows="dynamic",
        use_container_width=True,
        key="frontline_editor_stable_vfinal",
        hide_index=True,
        column_config={
            "銘柄": st.column_config.TextColumn("銘柄コード", required=True),
            "株数": st.column_config.NumberColumn("株数", format="%d", min_value=0),
            "買値": st.column_config.NumberColumn("買値", format="%d"),
            "現在値": st.column_config.NumberColumn("現在値", format="%d"),
            "損切": st.column_config.NumberColumn("損切", format="%d"),
            "第1利確": st.column_config.NumberColumn("利確1", format="%d"),
            "第2利確": st.column_config.NumberColumn("利確2", format="%d"),
            "atr": st.column_config.NumberColumn("ATR", format="%.1f"),
        }
    )

    # --- 3. コマンドユニット ---
    col_c1, col_c2 = st.columns(2)
    with col_c1:
        if st.button("🔄 全軍の現在値を同期", use_container_width=True, type="primary"):
            codes = [str(c).replace('.0', '').strip() for c in working_df['銘柄'].tolist() if pd.notna(c) and str(c).strip() != "" and str(c).strip() != "nan"]
            if codes:
                with st.spinner("J-Quants 接続中..."):
                    new_prices = fetch_current_prices_fast(codes)
                    if new_prices:
                        for c_code, c_price in new_prices.items():
                            mask = working_df['銘柄'].astype(str).str.replace(r'\.0$', '', regex=True) == str(c_code)
                            working_df.loc[mask, '現在値'] = c_price
                        st.session_state.frontline_df = working_df.copy()
                        st.success(f"✅ {len(new_prices)} 銘柄の同期を完了。")
                        st.rerun()
            else:
                st.warning("同期対象の銘柄コードがありません。")

    with col_c2:
        if st.button("💾 戦況をファイルに保存", use_container_width=True):
            st.session_state.frontline_df = working_df.copy()
            st.session_state.frontline_df.to_csv(FRONTLINE_FILE, index=False)
            st.toast("✅ 戦況を固定保存しました。", icon="💾")

    st.markdown("---")

    # --- 4. 戦況描画ユニット ---
    active_squads = 0
    sl_mult = float(st.session_state.get("bt_sl_c_mult", 2.5))
    
    name_map = {}
    if not master_df.empty:
        master_df_tmp = master_df.copy()
        master_df_tmp['Code_Str'] = master_df_tmp['Code'].astype(str).apply(lambda x: x if len(x) >= 5 else x + "0")
        name_map = dict(zip(master_df_tmp['Code_Str'], master_df_tmp['CompanyName']))

    for index, row in working_df.iterrows():
        ticker_raw = str(row.get('銘柄', '')).replace('.0', '').strip()
        if not ticker_raw or ticker_raw in ["nan", "None", ""]: continue
        
        ticker_search = ticker_raw if len(ticker_raw) >= 5 else ticker_raw + "0"
        company_name = name_map.get(ticker_search, "不明銘柄")

        def to_i(v):
            try: return int(float(v)) if pd.notna(v) and str(v).strip() != "" else 0
            except: return 0

        qty = to_i(row.get('株数', 0))
        buy, cur = to_i(row['買値']), to_i(row['現在値'])
        tp1, tp2 = to_i(row['第1利確']), to_i(row['第2利確'])
        atr_v = float(row['atr']) if pd.notna(row['atr']) and str(row['atr']).strip() != "" else float(buy * 0.03)
        
        active_squads += 1
        
        final_sl = to_i(row['損切']) if to_i(row['損切']) > 0 else int(buy - (atr_v * sl_mult)) if buy > 0 else 0
        cur_pct = ((cur / buy) - 1) * 100 if buy > 0 and cur > 0 else 0.0
        profit_amt = (cur - buy) * qty if buy > 0 and cur > 0 else 0
        sl_pct = ((final_sl / buy) - 1) * 100 if buy > 0 and final_sl > 0 else 0.0

        if cur <= 0: st_text, st_color, bg_rgba = "📡 待機中", "#888888", "rgba(136, 136, 136, 0.1)"
        elif cur <= final_sl: st_text, st_color, bg_rgba = "💀 被弾", "#ef5350", "rgba(239, 83, 80, 0.15)"
        elif cur < buy: st_text, st_color, bg_rgba = "⚠️ 警戒", "#ff9800", "rgba(255, 152, 0, 0.15)"
        elif tp1 > 0 and cur >= tp1: st_text, st_color, bg_rgba = "🛡️ 第1到達", "#42a5f5", "rgba(66, 165, 245, 0.15)"
        elif tp2 > 0 and cur >= tp2: st_text, st_color, bg_rgba = "🏆 任務完了", "#ab47bc", "rgba(171, 71, 188, 0.15)"
        else: st_text, st_color, bg_rgba = "🟢 巡航中", "#26a69a", "rgba(38, 166, 154, 0.15)"

        st.markdown(f"""
            <div style="margin-bottom: 5px;">
                <span style="font-size: 18px; font-weight: bold; color: #fff;">部隊 [{ticker_raw}] {company_name}</span>
                <span style="font-size: 14px; font-weight: bold; color: {st_color}; margin-left: 15px;">{st_text}</span>
                <span style="font-size: 14px; color: #aaa; margin-left: 10px;">(兵力: {qty:,}株)</span>
            </div>
        """, unsafe_allow_html=True)

        m_cols = st.columns([1, 1, 1.2, 1, 1])
        m_cols[0].metric("損切目安", f"¥{final_sl:,}", f"{sl_pct:+.1f}%" if sl_pct != 0 else None, delta_color="normal")
        m_cols[1].metric("買値", f"¥{buy:,}")
        
        with m_cols[2]:
            st.markdown(f"""
                <div style="background: {bg_rgba}; padding: 8px; border-radius: 6px; border: 1px solid {st_color}; text-align: center;">
                    <div style="font-size: 11px; color: {st_color}; font-weight: bold;">🔴 損益状況</div>
                    <div style="font-size: 20px; color: #fff; font-weight: bold;">¥{profit_amt:+,}</div>
                    <div style="font-size: 13px; color: {st_color}; font-weight: bold;">¥{cur:,} / {cur_pct:+.2f}%</div>
                </div>
            """, unsafe_allow_html=True)
            
        m_cols[3].metric("利確1", f"¥{tp1:,}" if tp1 > 0 else "---")
        m_cols[4].metric("利確2", f"¥{tp2:,}" if tp2 > 0 else "---")

        if cur > 0:
            pts = [v for v in [final_sl, cur, buy, tp1, tp2] if v > 0]
            mx, mi = max(pts)*1.02, min(pts)*0.98
            fig = go.Figure()
            fig.add_trace(go.Scatter(x=[mi, mx], y=[0, 0], mode='lines', line=dict(color="#444", width=2), hoverinfo='skip'))
            fig.add_trace(go.Scatter(x=[buy, cur], y=[0, 0], mode='lines', line=dict(color="rgba(38,166,154,0.6)" if cur>=buy else "rgba(239,83,80,0.6)", width=12), hoverinfo='skip'))
            
            for p_v, p_n, p_c in [(final_sl,"🛡️ 損切","#ef5350"),(buy,"🏁 買値","#ffca28"),(tp1,"🎯 利確1","#26a69a"),(tp2,"🏆 利確2","#42a5f5")]:
                if p_v > 0: fig.add_trace(go.Scatter(x=[p_v], y=[0], mode="markers", marker=dict(size=10, color=p_c), hovertemplate=f"{p_n}: ¥%{{x:,.0f}}<extra></extra>"))
            
            fig.add_trace(go.Scatter(
                x=[cur], y=[0], mode="markers", 
                marker=dict(size=18, symbol="cross-thin", line=dict(width=3, color=st_color)), 
                hovertemplate=f"現在地: ¥%{{x:,.0f}}<br>損益: ¥{profit_amt:+,}<extra></extra>"
            ))
            
            fig.update_layout(
                height=70, showlegend=False, 
                yaxis=dict(showticklabels=False, range=[-1,1], fixedrange=True), 
                xaxis=dict(showgrid=False, range=[mi, mx], tickformat=",.0f", fixedrange=True), 
                margin=dict(l=10,r=10,t=5,b=5), paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)', dragmode=False
            )
            st.plotly_chart(fig, use_container_width=True, key=f"frontline_bar_{ticker_raw}_{index}_{cache_key}", config={'displayModeBar': False})
        
        st.markdown("<div style='margin-bottom: 20px;'></div>", unsafe_allow_html=True)

    if active_squads == 0:
        st.info("部隊未展開。有効な銘柄コードがないか、保存されていません。")
        
# --- 11. タブコンテンツ (TAB6: 戦績ダッシュボード) ---
with tab6:
    import datetime as dt_module
    st.markdown('<h3 style="font-size: clamp(14px, 4.5vw, 24px); margin-bottom: 1rem;">📁 事後任務報告 (AAR) & 戦績ダッシュボード</h3>', unsafe_allow_html=True)
    st.caption("※ 記録の編集は下部の『🛠️ 戦績編集コンソール』で行ってください。")
    
    AAR_FILE = f"saved_aar_log_{user_id}.csv"
    
    # --- 🛡️ 1. 物理初期化回路 ---
    def get_scale_for_code(code):
        # 🚨 英字銘柄（523A等）対応の5桁規格化
        api_code = str(code) if len(str(code)) >= 5 else str(code) + "0"
        if not master_df.empty:
            m_row = master_df[master_df['Code'].astype(str) == api_code]
            if not m_row.empty:
                scale_val = str(m_row.iloc[0].get('Scale', ''))
                return "🏢 大型/中型" if any(x in scale_val for x in ["Core30", "Large70", "Mid400"]) else "🚀 小型/新興"
        return "不明"

    if 'aar_df_stable' not in st.session_state:
        if os.path.exists(AAR_FILE):
            try:
                df_l = pd.read_csv(AAR_FILE)
                df_l['決済日'] = df_l['決済日'].astype(str)
                df_l['銘柄'] = df_l['銘柄'].astype(str).str.replace(r'\.0$', '', regex=True)
                for c in ['買値', '売値', '株数', '損益額(円)', '損益(%)']:
                    if c in df_l.columns:
                        df_l[c] = pd.to_numeric(df_l[c], errors='coerce').fillna(0)
                st.session_state.aar_df_stable = df_l.sort_values(['決済日', '銘柄'], ascending=[False, True]).reset_index(drop=True)
            except:
                st.session_state.aar_df_stable = pd.DataFrame(columns=["決済日", "銘柄", "規模", "戦術", "買値", "売値", "株数", "損益額(円)", "損益(%)", "規律", "敗因/勝因メモ"])
        else:
            st.session_state.aar_df_stable = pd.DataFrame(columns=["決済日", "銘柄", "規模", "戦術", "買値", "売値", "株数", "損益額(円)", "損益(%)", "規律", "敗因/勝因メモ"])

    col_a1, col_a2 = st.columns([1, 2.2])
    
    with col_a1:
        st.markdown("#### 📝 戦果報告フォーム")
        with st.form(key="aar_form_v10_final", clear_on_submit=False):
            c_f1, c_f2 = st.columns(2)
            f_date = c_f1.date_input("決済日", value=dt_module.date.today())
            f_code = c_f2.text_input("銘柄コード", max_chars=4)
            t_opts = ["🌐 待伏 (押し目)", "⚡ 強襲 (順張り)", "⚠️ その他"]
            f_tactics = st.selectbox("使用した戦術", options=t_opts)
            c_f3, c_f4, c_f5 = st.columns(3)
            f_buy = c_f3.number_input("買値", min_value=0.0, step=1.0, format="%.0f")
            f_sell = c_f4.number_input("売値", min_value=0.0, step=1.0, format="%.0f")
            f_lot = c_f5.number_input("株数", min_value=100, step=100)
            r_opts = ["✅ 遵守した (冷徹な狙撃)", "❌ 破った (感情・焦り・妥協)"]
            f_rule = st.radio("規律を守ったか？", options=r_opts)
            f_memo = st.text_input("特記事項")
            
            if st.form_submit_button("💾 記録を保存", use_container_width=True):
                if f_code and f_buy > 0 and f_sell > 0:
                    profit = int((f_sell - f_buy) * f_lot)
                    p_pct = round(((f_sell / f_buy) - 1) * 100, 2)
                    new_entry = pd.DataFrame([{
                        "決済日": f_date.strftime("%Y-%m-%d"), "銘柄": f_code, "規模": get_scale_for_code(f_code),
                        "戦術": f_tactics, "買値": int(f_buy), "売値": int(f_sell), "株数": int(f_lot),
                        "損益額(円)": profit, "損益(%)": p_pct, "規律": "遵守" if "遵守" in f_rule else "違反", "敗因/勝因メモ": f_memo
                    }])
                    st.session_state.aar_df_stable = pd.concat([new_entry, st.session_state.aar_df_stable], ignore_index=True).sort_values(['決済日', '銘柄'], ascending=[False, True]).reset_index(drop=True)
                    st.session_state.aar_df_stable.to_csv(AAR_FILE, index=False)
                    st.rerun()

        with st.expander("📥 CSV一括登録"):
            uploaded_csv = st.file_uploader("約定履歴CSV", type=["csv"], key="aar_csv_uploader_v10")
            if uploaded_csv is not None:
                if st.button("⚙️ 解析・統合", use_container_width=True):
                    try:
                        import io
                        raw = uploaded_csv.getvalue()
                        try: content = raw.decode('utf-8')
                        except: content = raw.decode('shift_jis', errors='replace')
                        lines = content.splitlines(); h_idx = -1
                        for i, line in enumerate(lines):
                            if "約定日" in line and "銘柄" in line: h_idx = i; break
                        if h_idx != -1:
                            df_csv = pd.read_csv(io.StringIO("\n".join(lines[h_idx:])))
                            df_csv.columns = df_csv.columns.str.strip()
                            if '取引' in df_csv.columns: df_csv = df_csv[df_csv['取引'].astype(str).str.contains('現物')].copy()
                            records = []
                            c_col = '銘柄コード' if '銘柄コード' in df_csv.columns else '銘柄'
                            for code, group in df_csv.groupby(c_col):
                                buys, sells = [], []
                                for _, row in group.iterrows():
                                    item = {'date': str(row['約定日']).replace('/', '-'), 'qty': int(row['約定数量']), 'price': float(row['約定単価']), 'code': str(code).strip()}
                                    if "買" in str(row['取引']): buys.append(item)
                                    elif "売" in str(row['取引']): sells.append(item)
                                buys.sort(key=lambda x: x['date']); sells.sort(key=lambda x: x['date'])
                                for s in sells:
                                    s_qty, m_qty, m_amt = s['qty'], 0, 0
                                    while s_qty > 0 and len(buys) > 0:
                                        b = buys[0]
                                        if b['qty'] <= s_qty: m_qty += b['qty']; m_amt += b['price']*b['qty']; s_qty -= b['qty']; buys.pop(0)
                                        else: m_qty += s_qty; m_amt += b['price']*s_qty; b['qty'] -= s_qty; s_qty = 0
                                    if m_qty > 0:
                                        avg_b = m_amt / m_qty
                                        records.append({"決済日": s['date'], "銘柄": s['code'], "規模": get_scale_for_code(s['code']), "戦術": "自動解析", "買値": int(avg_b), "売値": int(s['price']), "株数": int(m_qty), "損益額(円)": int((s['price']-avg_b)*m_qty), "損益(%)": round(((s['price']/avg_b)-1)*100, 2), "規律": "不明", "敗因/勝因メモ": "CSV自動取り込み"})
                            if records:
                                st.session_state.aar_df_stable = pd.concat([st.session_state.aar_df_stable, pd.DataFrame(records)], ignore_index=True).drop_duplicates(subset=["決済日", "銘柄", "買値", "売値", "株数"]).sort_values(['決済日', '銘柄'], ascending=[False, True]).reset_index(drop=True)
                                st.session_state.aar_df_stable.to_csv(AAR_FILE, index=False); st.rerun()
                    except Exception as e: st.error(f"エラー: {e}")

    with col_a2:
        st.markdown("#### 📊 司令部 総合戦績")
        w_df = st.session_state.aar_df_stable
        if not w_df.empty:
            m1, m2, m3, m4 = st.columns(4)
            tot_p = w_df['損益額(円)'].sum()
            w_rate = (len(w_df[w_df['損益額(円)'] > 0]) / len(w_df)) * 100
            loss_sum = abs(w_df[w_df['損益額(円)'] < 0]['損益額(円)'].sum())
            pf = round(w_df[w_df['損益額(円)'] > 0]['損益額(円)'].sum() / loss_sum, 2) if loss_sum > 0 else 9.9
            adh = (len(w_df[w_df['規律'] == '遵守']) / len(w_df)) * 100
            m1.metric("総交戦", f"{len(w_df)}回"); m2.metric("勝率", f"{w_rate:.1f}%"); m3.metric("損益", f"{int(tot_p):,}円", f"PF: {pf}"); m4.metric("遵守率", f"{adh:.1f}%")
            
            import plotly.express as px
            df_curv = w_df.sort_values('決済日', ascending=True).copy()
            df_curv['累積'] = df_curv['損益額(円)'].cumsum()
            fig = px.line(df_curv, x='決済日', y='累積', markers=True, color_discrete_sequence=["#26a69a"])
            fig.update_layout(paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0.1)', height=250, margin=dict(l=10, r=10, t=10, b=10))
            st.plotly_chart(fig, use_container_width=True)

    # --- 📜 詳細交戦記録 (視認性重視) ---
    st.divider()
    st.markdown("##### 📜 詳細交戦記録 (キル・ログ)")
    
    def apply_performance_colors(val):
        try:
            v = float(val)
            if v >= 1.0: return 'color: #26a69a; font-weight: bold;'
            elif v <= -1.0: return 'color: #ef5350; font-weight: bold;'
            else: return 'color: #ffffff;'
        except: return 'color: #ffffff;'

    def apply_rule_style(val):
        if val == '遵守': return 'color: #26a69a;'
        elif val == '違反': return 'color: #ef5350;'
        else: return 'color: #ffffff;'

    styled_view = st.session_state.aar_df_stable.style.map(apply_performance_colors, subset=['損益額(円)', '損益(%)']).map(apply_rule_style, subset=['規律'])
    
    # 🚨 修正の要諦：買値・売値を整数フォーマットに物理固定
    st.dataframe(
        styled_view,
        column_config={
            "買値": st.column_config.NumberColumn(format="¥%,d"),
            "売値": st.column_config.NumberColumn(format="¥%,d"),
            "損益額(円)": st.column_config.NumberColumn(format="¥%,d"),
            "損益(%)": st.column_config.NumberColumn(format="%.2f%%"),
        },
        hide_index=True, use_container_width=True
    )

    with st.expander("🛠️ 戦績編集コンソール (一括修正・削除)"):
        st.warning("※ 編集後、必ず下の『確定』ボタンを押してください。")
        working_log_df = st.data_editor(
            st.session_state.aar_df_stable, 
            column_config={
                "規模": st.column_config.TextColumn("規模", disabled=True),
                "戦術": st.column_config.SelectboxColumn("戦術", options=["待伏", "強襲", "自動解析", "その他"], required=True),
                "規律": st.column_config.SelectboxColumn("規律", options=["遵守", "違反", "不明"], required=True),
                "買値": st.column_config.NumberColumn("買値", format="%d"),
                "売値": st.column_config.NumberColumn("売値", format="%d"),
            },
            hide_index=True, use_container_width=True, key="aar_editor_maintenance_v10"
        )

        if st.button("💾 戦績の変更を確定し、色彩を同期", use_container_width=True, type="primary"):
            st.session_state.aar_df_stable = working_log_df.copy()
            # 物理強制：保存時にも整数へ変換
            for col in ["買値", "売値", "株数", "損益額(円)"]:
                st.session_state.aar_df_stable[col] = pd.to_numeric(st.session_state.aar_df_stable[col], errors='coerce').fillna(0).astype(int)
            st.session_state.aar_df_stable.to_csv(AAR_FILE, index=False)
            st.success("✅ 整数化完了。色彩規律を再適用しました。")
            st.rerun()
			
