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

# --- 2. 認証・通信・グローバル定数 ---
user_id = st.session_state["current_user"]
st.markdown(f'<h1 style="font-size: clamp(24px, 7vw, 42px); font-weight: 900; border-bottom: 2px solid #2e7d32; padding-bottom: 0.5rem; margin-bottom: 1rem;">🎯 戦術スコープ『鉄の掟』 <span style="font-size: 16px; font-weight: normal; color: #888;">(ID: {user_id[:4]}***)</span></h1>', unsafe_allow_html=True)

API_KEY = st.secrets.get("JQUANTS_API_KEY", "").strip()
headers = {"x-api-key": API_KEY}
BASE_URL = "https://api.jquants.com/v2"

# 💎 物理固定：SETTINGS_FILEをグローバルに定義
SETTINGS_FILE = f"saved_settings_{user_id}.json"

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
            if isinstance(df_raw.columns, pd.MultiIndex):
                df_raw.columns = df_raw.columns.get_level_values(0)
            df_ni = df_raw.reset_index()
            df_ni['Date'] = pd.to_datetime(df_ni['Date']).dt.tz_localize(None)
            df_ni = df_ni.dropna(subset=['Close']).tail(65)
            latest = df_ni.iloc[-1]
            prev = df_ni.iloc[-2]
            return {
                "nikkei": {
                    "price": latest['Close'],
                    "diff": latest['Close'] - prev['Close'],
                    "pct": ((latest['Close'] / prev['Close']) - 1) * 100,
                    "df": df_ni,
                    "date": latest['Date'].strftime('%m/%d')
                }
            }
    except:
        return None

def render_macro_board():
    data = get_macro_weather()
    if data and "nikkei" in data:
        ni = data["nikkei"]
        df = ni["df"]
        color = "#ef5350" if ni['diff'] >= 0 else "#26a69a"
        sign = "+" if ni['diff'] >= 0 else ""
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
    else:
        st.warning("📡 外部気象レーダー応答なし")

render_macro_board()

# --- 3. 共通関数 & 演算エンジン ---
def clean_df(df):
    r_cols = {'AdjustmentOpen': 'AdjO', 'AdjustmentHigh': 'AdjH', 'AdjustmentLow': 'AdjL', 'AdjustmentClose': 'AdjC', 'Open': 'AdjO', 'High': 'AdjH', 'Low': 'AdjL', 'Close': 'AdjC', 'AdjustmentVolume': 'Volume', 'Volume': 'Volume'}
    df = df.rename(columns=r_cols)
    for c in ['AdjO', 'AdjH', 'AdjL', 'AdjC', 'Volume']:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors='coerce').astype('float32')
    if 'Date' in df.columns:
        df['Date'] = pd.to_datetime(df['Date'])
        df = df.sort_values(['Code', 'Date']).dropna(subset=['AdjO', 'AdjH', 'AdjL', 'AdjC']).reset_index(drop=True)
    return df

def calc_vector_indicators(df):
    df = df.copy()
    delta = df.groupby('Code')['AdjC'].diff()
    gain = delta.where(delta > 0, 0)
    loss = -delta.where(delta < 0, 0)
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

def calc_technicals(df):
    return calc_vector_indicators(df)

def check_event_mines(code, event_data=None):
    alerts = []
    c = str(code)[:4]
    today = datetime.utcnow() + timedelta(hours=9)
    today_date = today.date()
    max_warning_date = today_date + timedelta(days=14)
    critical_mines = {"8835": "2026-03-30", "3137": "2026-03-27", "4167": "2026-03-27", "4031": "2026-03-27", "2195": "2026-03-27", "4379": "2026-03-27"}
    if c in critical_mines:
        try:
            event_date = datetime.strptime(critical_mines[c], "%Y-%m-%d").date()
            if (event_date - timedelta(days=14)) <= today_date <= event_date:
                alerts.append(f"💣 【地雷警戒】危険イベント接近中（{critical_mines[c]}）")
        except:
            pass
    if not event_data:
        return alerts
    for item in event_data.get("dividend", []):
        d_str = str(item.get("RecordDate", ""))[:10]
        if d_str:
            try:
                target_date = datetime.strptime(d_str, "%Y-%m-%d").date()
                if today_date <= target_date <= max_warning_date:
                    alerts.append(f"💣 【地雷警戒】配当権利落ち日が接近中 ({d_str})")
                    break
            except:
                pass
    for item in event_data.get("earnings", []):
        if str(item.get("Code", ""))[:4] != c:
            continue
        d_str = str(item.get("Date", item.get("DisclosedDate", "")))[:10]
        if d_str:
            try:
                target_date = datetime.strptime(d_str, "%Y-%m-%d").date()
                if today_date <= target_date <= max_warning_date:
                    alerts.append(f"🔥 【地雷警戒】決算発表が接近中 ({d_str})")
                    break
            except:
                pass
    return alerts

def check_double_top(df_sub):
    try:
        v = df_sub['AdjH'].values
        c = df_sub['AdjC'].values
        l = df_sub['AdjL'].values
        if len(v) < 6: return False
        pk = []
        for i in range(1, len(v)-1):
            if v[i] == max(v[i-1:i+2]):
                if not pk or (i - pk[-1][0] > 1):
                    pk.append((i, v[i]))
        if len(v) >= 2 and v[-1] > v[-2]:
            if not pk or (len(v)-1 - pk[-1][0] > 1):
                pk.append((len(v)-1, v[-1]))
        if len(pk) >= 2:
            p2_idx, p2_val = pk[-1]
            p1_idx, p1_val = pk[-2]
            if abs(p2_val - p1_val) / max(p2_val, p1_val) < 0.05:
                valley = min(l[p1_idx:p2_idx+1]) if p2_idx > p1_idx else p1_val
                if valley < min(p1_val, p2_val) * 0.95 and c[-1] < p2_val * 0.97:
                    return True
        return False
    except:
        return False

def check_head_shoulders(df_sub):
    try:
        v = df_sub['AdjH'].values
        c = df_sub['AdjC'].values
        if len(v) < 8: return False
        pk = []
        for i in range(1, len(v)-1):
            if v[i] == max(v[i-1:i+2]):
                if not pk or (i - pk[-1][0] > 1):
                    pk.append((i, v[i]))
        if len(pk) >= 3:
            p3_idx, p3_val = pk[-1]
            p2_idx, p2_val = pk[-2]
            p1_idx, p1_val = pk[-3]
            if p2_val > p1_val and p2_val > p3_val and abs(p3_val - p1_val) / max(p3_val, p1_val) < 0.10 and c[-1] < p3_val * 0.97:
                return True
        return False
    except:
        return False

def check_double_bottom(df_sub):
    try:
        l = df_sub['AdjL'].values
        c = df_sub['AdjC'].values
        h = df_sub['AdjH'].values
        if len(l) < 6: return False
        valleys = []
        for i in range(1, len(l)-1):
            if l[i] == min(l[i-1:i+2]):
                if not valleys or (i - valleys[-1][0] > 1):
                    valleys.append((i, l[i]))
        if len(valleys) >= 2:
            v2_idx, v2_val = valleys[-1]
            v1_idx, v1_val = valleys[-2]
            if abs(v2_val - v1_val) / min(v2_val, v1_val) < 0.05:
                peak = max(h[v1_idx:v2_idx+1]) if v2_idx > v1_idx else v1_val
                if peak > max(v1_val, v2_val) * 1.04 and c[-1] > v2_val * 1.01:
                    return True
        return False
    except:
        return False

@st.cache_data(ttl=3600, show_spinner=False, max_entries=500)
def get_fundamentals(code):
    api_code = str(code) if len(str(code)) >= 5 else str(code) + "0"
    url = f"{BASE_URL}/fins/statements?code={api_code}"
    try:
        r = requests.get(url, headers=headers, timeout=5)
        if r.status_code == 200:
            data = r.json().get("statements", [])
            if data:
                latest = data[0]
                roe = None
                if latest.get("NetIncome") and latest.get("Equity"):
                    try:
                        roe = (float(latest["NetIncome"]) / float(latest["Equity"])) * 100
                    except:
                        pass
                return {
                    "op": latest.get("OperatingProfit"),
                    "er": latest.get("EquityRatio"),
                    "roe": roe
                }
    except:
        pass
    return None
    
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
    except:
        pass
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
    except:
        pass
    return result

@st.cache_data(ttl=3600, max_entries=2, show_spinner=False)
def get_hist_data_cached():
    base = datetime.utcnow() + timedelta(hours=9)
    dates = []
    days = 0
    while len(dates) < 45:
        d = base - timedelta(days=days)
        if d.weekday() < 5:
            dates.append(d.strftime('%Y%m%d'))
        days += 1
    rows = []
    def fetch(dt):
        try:
            r = requests.get(f"{BASE_URL}/equities/bars/daily?date={dt}", headers=headers, timeout=10)
            if r.status_code == 200:
                return r.json().get("data", [])
        except:
            pass
        return []
    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as exe:
        futs = [exe.submit(fetch, dt) for dt in dates]
        for f in concurrent.futures.as_completed(futs):
            res = f.result()
            if res:
                rows.extend(res)
    return rows
    
def get_fast_indicators(prices):
    if len(prices) < 15:
        return 50.0, 0.0, 0.0, np.zeros(5)
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
    if macd_hist > 0 and macd_hist_prev <= 0:
        macd_t = "GC直後"
    elif macd_hist > macd_hist_prev:
        macd_t = "上昇拡大"
    elif macd_hist < 0 and macd_hist < macd_hist_prev:
        macd_t = "下落継続"
    else:
        macd_t = "減衰"

    if mode == "強襲":
        if macd_t == "下落継続" or rsi >= 75:
            return "圏外🚫", "#d32f2f", 0, macd_t
        if gc_days == 1:
            return ("S🔥", "#2e7d32", 5, "GC直後(1日目)") if rsi <= 50 else ("A⚡", "#ed6c02", 4, "GC直後(1日目)")
        else:
            return "B📈", "#0288d1", 3, f"GC継続({gc_days}日目)"

    if bt == 0 or lc == 0:
        return "C👁️", "#616161", 1, macd_t
    dist_pct = ((lc / bt) - 1) * 100 
    if dist_pct < -2.0:
        return "圏外💀", "#d32f2f", 0, macd_t
    elif dist_pct <= 2.0:
        return ("S🔥", "#2e7d32", 5, macd_t) if rsi <= 45 else ("A⚡", "#ed6c02", 4.5, macd_t) 
    elif dist_pct <= 5.0:
        return ("A🪤", "#0288d1", 4.0, macd_t) if rsi <= 50 else ("B📈", "#0288d1", 3, macd_t)
    else:
        return "C👁️", "#616161", 1, macd_t

def get_assault_triage_info(gc_days, lc, rsi_v, df_chart, is_strict=False):
    if gc_days <= 0 or df_chart is None or df_chart.empty:
        return "圏外 💀", "#424242", 0, ""
    row = df_chart.iloc[-1]
    ma25 = row.get('MA25', 0)
    score = 50 
    if ma25 > 0:
        if lc >= ma25 * 0.95:
            score += 10
        if lc >= ma25:
            score += 10
    if 50 <= rsi_v <= 70:
        score += 10
    if score >= 80:
        rank, bg = "S", "#d32f2f"
    elif score >= 60:
        rank, bg = "A", "#f57c00"
    elif score >= 40:
        rank, bg = "B", "#fbc02d"
    else:
        rank, bg = "C 💀", "#424242"
    return rank, bg, score, "GC発動中"

def render_technical_radar(df, buy_price, tp_pct):
    if df.empty or len(df) < 2:
        return ""
    latest = df.iloc[-1]
    prev = df.iloc[-2]
    rsi = latest.get('RSI', 50)
    macd_hist = latest.get('MACD_Hist', 0)
    macd_hist_prev = prev.get('MACD_Hist', 0)
    atr = latest.get('ATR', 0)
    rsi_color = "#ef5350" if rsi <= 30 else "#FFD700" if rsi <= 45 else "#888888"
    rsi_text = "🔥 超売られすぎ" if rsi <= 30 else "⚡ 低RSI" if rsi <= 45 else "⚖️ 中立"
    if rsi >= 70:
        rsi_color = "#26a69a"
        rsi_text = "⚠️ 買われすぎ"
    _, _, _, macd_t = get_triage_info(macd_hist, macd_hist_prev, rsi)
    bg_glow = "border-left: 4px solid #FFD700;"
    days = int((buy_price * (tp_pct / 100.0)) / atr) if atr > 0 else 99
    return f'<div style="background: rgba(255, 255, 255, 0.05); padding: 0.8rem; border-radius: 4px; margin: 1rem 0; {bg_glow}"><div style="font-size: 14px; color: #aaa;">📡 RSI <strong style="color: {rsi_color};">{rsi:.0f}% ({rsi_text})</strong> | MACD <strong style="color: #ef5350;">{macd_t}</strong> | ボラ <strong style="color: #bbb;">{atr:.0f}円</strong> (目標まで約{days}日)</div></div>'

def draw_chart(df, targ_p, tp5=None, tp10=None, tp15=None, tp20=None, chart_key=None):
    df = df.copy()
    fig = go.Figure()
    fig.add_trace(go.Candlestick(x=df['Date'], open=df['AdjO'], high=df['AdjH'], low=df['AdjL'], close=df['AdjC'], name='株価', increasing_line_color='#26a69a', decreasing_line_color='#ef5350'))
    if 'MA5' in df.columns:
        fig.add_trace(go.Scatter(x=df['Date'], y=df['MA5'], mode='lines', name='5日', line=dict(color='#ffca28', width=1.5)))
    if 'MA25' in df.columns:
        fig.add_trace(go.Scatter(x=df['Date'], y=df['MA25'], mode='lines', name='25日', line=dict(color='#42a5f5', width=1.5)))
    if 'MA75' in df.columns:
        fig.add_trace(go.Scatter(x=df['Date'], y=df['MA75'], mode='lines', name='75日', line=dict(color='#ab47bc', width=1.5)))
    fig.add_trace(go.Scatter(x=df['Date'], y=[targ_p]*len(df), mode='lines', name='買値目標', line=dict(color='#FFD700', width=2, dash='dash')))
    fig.update_layout(height=450, margin=dict(l=0, r=60, t=30, b=40), xaxis_rangeslider_visible=True, paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)', hovermode="x unified", yaxis=dict(side="right"))
    st.plotly_chart(fig, use_container_width=True, key=chart_key)

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
        "sim_tp_val": 10.0, "sim_sl_val": 8.0, "sim_limit_d_val": 4, "sim_sell_d_val": 10,
        "sim_push_r_val": 50.0, "sim_pass_req_val": 7, "sim_rsi_lim_ambush_val": 45,
        "sim_rsi_lim_assault_val": 70, "sim_time_risk_val": 5
    }
    if os.path.exists(SETTINGS_FILE):
        try:
            with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
                saved = json.load(f)
                for k, v in saved.items():
                    if k in defaults:
                        defaults[k] = v
        except:
            pass
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v
    # 💎 物理固定：f3_dropは必ず-50.0を維持する。
    st.session_state.f3_drop = -50.0

def save_settings():
    keys = ["preset_market", "preset_push_r", "sidebar_tactics", "push_r", "limit_d", "bt_lot", "bt_tp", "bt_sl_i", "bt_sl_c", "bt_sell_d", 
            "f1_min", "f1_max", "f2_m30", "f3_drop", "f5_ipo", "f6_risk", "f7_ex_etf", "f8_ex_bio", 
            "f9_min14", "f9_max14", "f10_ex_knife", "f11_ex_wave3", "f12_ex_overvalued",
            "tab2_rsi_limit", "tab2_vol_limit", "t3_scope_mode", "gigi_input",
            "sim_tp_val", "sim_sl_val", "sim_limit_d_val", "sim_sell_d_val",
            "sim_push_r_val", "sim_pass_req_val", "sim_rsi_lim_ambush_val",
            "sim_rsi_lim_assault_val", "sim_time_risk_val"]
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
c_sl1, c_sl2 = st.sidebar.columns(2)
c_sl1.number_input("初期損切(%)", step=1, key="bt_sl_i", on_change=save_settings)
c_sl2.number_input("現在損切(%)", step=1, key="bt_sl_c", on_change=save_settings)
st.sidebar.number_input("最大保持期間(日)", step=1, key="bt_sell_d", on_change=save_settings)
st.sidebar.divider()

st.sidebar.header("🚫 特殊除外フィルター")
st.sidebar.checkbox("ETF・REIT等を除外", key="f7_ex_etf", on_change=save_settings)
st.sidebar.checkbox("医薬品(バイオ)を除外", key="f8_ex_bio", on_change=save_settings)
st.sidebar.checkbox("落ちるナイフ除外(暴落直後)", key="f10_ex_knife", on_change=save_settings)
st.sidebar.text_area("除外銘柄コード (雑なコピペ対応)", key="gigi_input", on_change=save_settings)
st.sidebar.divider()

if st.sidebar.button("🔴 キャッシュ強制パージ", use_container_width=True):
    st.cache_data.clear()
    st.session_state.tab1_scan_results = None
    st.session_state.tab2_scan_results = None
    st.rerun()
if st.sidebar.button("💾 現在の設定を保存", use_container_width=True):
    save_settings()
    st.toast("全設定を永久保存した。")

# --- 5. タブ構成の開始 ---
master_df = load_master()
tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs(["🌐 【待伏】広域レーダー", "⚡ 【強襲】GC初動レーダー", "🎯 【照準】精密スコープ", "⚙️ 【演習】戦術シミュレータ", "⛺ 【戦線】交戦モニター", "📁 【戦歴】交戦データベース"])
tactics_mode = st.session_state.sidebar_tactics

with tab1:
    st.markdown('<h3 style="font-size: clamp(14px, 4.5vw, 24px); margin-bottom: 1rem;">🎯 【待伏】鉄の掟・半値押しレーダー</h3>', unsafe_allow_html=True)
    if 'tab1_scan_results' not in st.session_state:
        st.session_state.tab1_scan_results = None
    
    run_scan_t1 = st.button("🚀 最新データで待伏スキャン開始")

    if run_scan_t1:
        st.toast("🟢 待伏トリガーを確認。索敵開始。", icon="🎯")
        with st.spinner("全銘柄からターゲットを索敵中..."):
            raw = get_hist_data_cached()
            if not raw:
                st.error("データの取得に失敗した。")
                st.session_state.tab1_scan_results = None
            else:
                df = clean_df(pd.DataFrame(raw))
                df['Code'] = df['Code'].astype(str)
                v_col = next((col for col in df.columns if col in ['Volume', 'AdjVo', 'Vo', 'AdjustmentVolume']), None)
                avg_vols = df.groupby('Code').tail(5).groupby('Code')[v_col].mean() if v_col else pd.Series(0, index=df['Code'].unique())

                # --- 物理配線：設定の同期 ---
                f1_min, f1_max = float(st.session_state.f1_min), float(st.session_state.f1_max)
                f2_limit, f3_drop_val = float(st.session_state.f2_m30), float(st.session_state.f3_drop)
                f5_ipo, f6_risk = st.session_state.f5_ipo, st.session_state.f6_risk
                f7_ex_etf, f8_bio_flag = st.session_state.f7_ex_etf, st.session_state.f8_ex_bio
                f10_ex_knife, f11_ex_wave3 = st.session_state.f10_ex_knife, st.session_state.f11_ex_wave3
                f12_overvalued = st.session_state.f12_ex_overvalued
                push_ratio = st.session_state.push_r / 100.0
                limit_d_val = int(st.session_state.limit_d)

                latest_date = df['Date'].max()
                latest_df = df[df['Date'] == latest_date]
                
                # 市場フィルタ
                m_mode = "大型" if "大型株" in st.session_state.preset_market else "中小型"
                if not master_df.empty:
                    large_kw = ['プライム', '一部']
                    small_kw = ['スタンダード', 'グロース', '新興', 'マザーズ', 'JASDAQ', '二部']
                    m_codes = master_df[master_df['Market'].str.contains('|'.join(large_kw if m_mode == "大型" else small_kw), na=False)]['Code'].unique()
                    df = df[df['Code'].isin(m_codes)]

                # 基本足切り
                valid_p = latest_df[(latest_df['AdjC'] >= f1_min) & (latest_df['AdjC'] <= f1_max)]['Code'].unique()
                valid_v = avg_vols[avg_vols >= 10000].index
                df = df[df['Code'].isin(set(valid_p).intersection(set(valid_v)))]

                master_dict = master_df.set_index('Code')[['CompanyName', 'Market', 'Sector']].to_dict('index') if not master_df.empty else {}
                results = []
                
                for code, group in df.groupby('Code'):
                    if len(group) < 15: continue 
                    adjc, adjh, adjl = group['AdjC'].values, group['AdjH'].values, group['AdjL'].values
                    lc = adjc[-1]

                    if lc / adjc[max(0, len(adjc)-20)] > f2_limit: continue
                    if lc < adjh.max() * (1 + (f3_drop_val / 100.0)): continue

                    if f11_ex_wave3:
                        pk = []
                        for j in range(5, len(adjh)-5):
                            if adjh[j] == max(adjh[j-5:j+5]):
                                if not pk or adjh[j] > pk[-1] * 1.15:
                                    pk.append(adjh[j])
                        if len(pk) >= 3 and lc < max(pk) * 0.85:
                            continue

                    if f10_ex_knife and len(adjc) >= 4 and (adjc[-1] / adjc[max(0, len(adjc)-4)] < 0.85):
                        continue
                    
                    r4h = adjh[-4:]; h4 = r4h.max()
                    gi = len(adjh) - 4 + r4h.argmax()
                    l14 = adjl[max(0, gi-14) : gi+1].min()
                    if l14 <= 0 or h4 <= l14: continue
                    wh = h4 / l14
                    
                    if not (st.session_state.f9_min14 <= wh <= st.session_state.f9_max14): continue
                    
                    bt = h4 - ((h4 - l14) * push_ratio)
                    rr = (bt / lc) * 100
                    rsi, macdh, macdh_p, _ = get_fast_indicators(adjc)
                    
                    # 🏅 掟スコア計算
                    score = 4 
                    if 1.3 <= wh <= 2.0: score += 1
                    if (len(adjh) - 1 - gi) <= limit_d_val: score += 1
                    if not check_double_top(group.tail(31).iloc[:-1]): score += 1
                    if check_double_bottom(group.tail(31).iloc[:-1]): score += 1
                    if bt * 0.85 <= lc <= bt * 1.35: score += 1

                    if f6_risk or f12_overvalued:
                        fund = get_fundamentals(code)
                        if fund:
                            if f6_risk and (float(fund.get('er', 1)) < 0.20 or float(fund.get('op', 1)) < 0): continue
                            if f12_overvalued and float(fund.get('op', 1)) < 0: continue

                    m_i = master_dict.get(code, {})
                    rank, bg, t_score, _ = get_triage_info(macdh, macdh_p, rsi, lc, bt, mode="待伏")
                    
                    results.append({
                        'Code': code, 'Name': m_i.get('CompanyName', f"銘柄 {code[:4]}"), 'Sector': m_i.get('Sector', '不明'), 'Market': m_i.get('Market', '不明'), 
                        'lc': lc, 'RSI': rsi, 'avg_vol': int(avg_vols.get(code, 0)), 'high_4d': h4, 'low_14d': l14, 'target_buy': bt, 'reach_rate': rr, 
                        'triage_rank': rank, 'triage_bg': bg, 't_score': t_score, 'score': score
                    })
                
                st.session_state.tab1_scan_results = sorted(results, key=lambda x: (x['t_score'], x['score']), reverse=True)[:30]

    # --- TAB1 UI表示フェーズ（物理修正：一括コピーボックスと銘柄リスト） ---
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
                b_html = '<span style="background-color: #1b5e20; color: #ffffff; padding: 0.2rem 0.6rem; border-radius: 4px; font-size: 11px; font-weight: bold;">🚀 グロース/新興</span>'
            else: 
                b_html = f'<span style="background-color: #455a64; color: #ffffff; padding: 0.2rem 0.6rem; border-radius: 4px; font-size: 11px; font-weight: bold;">{r["Market"]}</span>'
            
            t_b = f'<span style="background-color: {r["triage_bg"]}; color: #ffffff; padding: 0.2rem 0.6rem; border-radius: 4px; font-size: 13px; font-weight: bold; margin-left: 0.5rem;">🎯 優先度: {r["triage_rank"]}</span>'
            s_b = f'<span style="background-color: rgba(46,125,50,0.15); border: 1px solid #2e7d32; color: #2e7d32; padding: 0.2rem 0.6rem; border-radius: 4px; font-size: 12px; font-weight: bold; margin-left: 0.5rem;">🎖️ 掟スコア: {r["score"]}/10</span>'
            
            st.markdown(f"""
                <div style="margin-bottom: 0.8rem;">
                    <h3 style="font-size: clamp(18px, 5vw, 28px); font-weight: bold; margin: 0;">({c_code[:4]}) {r["Name"]}</h3>
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
    if 'tab2_scan_results' not in st.session_state:
        st.session_state.tab2_scan_results = None
    
    c_t2_1, c_t2_2 = st.columns(2)
    rsi_lim = c_t2_1.number_input("RSI上限（過熱感の足切り）", step=5, value=75, key="tab2_rsi_limit", on_change=save_settings)
    vol_lim = c_t2_2.number_input("最低出来高（5日平均）", step=5000, value=15000, key="tab2_vol_limit", on_change=save_settings)
    
    run_scan_t2 = st.button("🚀 全軍GC初動スキャン開始", key="btn_assault_scan_trigger")

    if run_scan_t2:
        st.toast("🟢 強襲トリガーを確認。MACDクロスを捕捉する。", icon="🚀")
        with st.spinner("全軍からGC初動候補を抽出中..."):
            raw = get_hist_data_cached()
            if not raw:
                st.error("データの取得に失敗した。")
                st.session_state.tab2_scan_results = None
            else:
                df = clean_df(pd.DataFrame(raw))
                df['Code'] = df['Code'].astype(str)
                v_col = next((col for col in df.columns if col in ['Volume', 'AdjVo', 'Vo', 'AdjustmentVolume']), None)
                avg_vols = df.groupby('Code').tail(5).groupby('Code')[v_col].mean() if v_col else pd.Series(0, index=df['Code'].unique())
                
                # 市場フィルタリング（サイドバー設定連動）
                m_mode = "大型" if "大型株" in st.session_state.preset_market else "中小型"
                if not master_df.empty:
                    large_kw = ['プライム', '一部']
                    small_kw = ['スタンダード', 'グロース', '新興', 'マザーズ', 'JASDAQ', '二部']
                    m_codes = master_df[master_df['Market'].str.contains('|'.join(large_kw if m_mode == "大型" else small_kw), na=False)]['Code'].unique()
                    df = df[df['Code'].isin(m_codes)]
                
                # 基本足切り（価格・出来高）
                valid_codes = set(df[df['Date']==df['Date'].max()][(df['AdjC']>=float(st.session_state.f1_min)) & (df['AdjC']<=float(st.session_state.f1_max))]['Code']).intersection(set(avg_vols[avg_vols>=vol_lim].index))
                df = df[df['Code'].isin(valid_codes)]
                
                master_dict = master_df.set_index('Code')[['CompanyName', 'Market', 'Sector']].to_dict('index') if not master_df.empty else {}
                results = []
                
                for code, group in df.groupby('Code'):
                    if len(group) < 15: continue
                    adjc, adjh = group['AdjC'].values, group['AdjH'].values
                    lc = adjc[-1]
                    rsi, _, _, h_vals = get_fast_indicators(adjc)
                    
                    if rsi > rsi_lim: continue
                    
                    # ⚡ GC判定ロジック (3日以内)
                    gc_d = 1 if len(h_vals)>=2 and h_vals[-2]<0 and h_vals[-1]>=0 else 2 if len(h_vals)>=3 and h_vals[-3]<0 and h_vals[-1]>=0 else 3 if len(h_vals)>=4 and h_vals[-4]<0 and h_vals[-1]>=0 else 0
                    
                    # 掟：トレンド維持フィルタ（25日線近辺）
                    if gc_d == 0 or lc < (group['AdjC'].rolling(window=25).mean().iloc[-1] * 0.95):
                        continue
                    
                    # 🚀 物理配線：財務フィルタ（信用リスク・赤字除外）
                    if st.session_state.f6_risk or st.session_state.f12_ex_overvalued:
                        fund = get_fundamentals(code)
                        if fund:
                            if st.session_state.f6_risk and (float(fund.get('er', 1)) < 0.20 or float(fund.get('op', 1)) < 0): 
                                continue
                            if st.session_state.f12_ex_overvalued and float(fund.get('op', 1)) < 0: 
                                continue
                    
                    # 強襲トリアージ実行
                    t_rank, t_color, t_score, _ = get_assault_triage_info(gc_d, lc, rsi, group, is_strict=False)
                    m_i = master_dict.get(code, {})
                    
                    results.append({
                        'Code': code, 
                        'Name': m_i.get('CompanyName', f"銘柄 {code[:4]}"), 
                        'Market': m_i.get('Market', '不明'), 
                        'Sector': m_i.get('Sector', '不明'),
                        'lc': lc, 
                        'RSI': rsi, 
                        'avg_vol': int(avg_vols.get(code, 0)), 
                        'h14': adjh[-14:].max(), 
                        'atr': adjh[-14:].max() * 0.03, 
                        'T_Rank': t_rank, 
                        'T_Color': t_color, 
                        'T_Score': t_score, 
                        'GC_Days': gc_d
                    })
                
                st.session_state.tab2_scan_results = sorted(results, key=lambda x: (-x['T_Score'], x['GC_Days']))[:30]

    # --- TAB2 UI表示フェーズ（物理修正：重複排除・Turn 24仕様） ---
    if st.session_state.tab2_scan_results:
        light_results = st.session_state.tab2_scan_results
        st.success(f"⚡ 強襲ロックオン: GC初動(3日以内) 上位 {len(light_results)} 銘柄を確認。")
        
        # 📋 銘柄コード一括コピーボックス
        sab_codes = " ".join([str(r['Code'])[:4] for r in light_results if str(r['T_Rank']).startswith(('S', 'A', 'B'))])
        if sab_codes:
            st.info("📋 以下のコードをコピーして、照準（TAB3）へ投入せよ。")
            st.code(sab_codes, language="text")
        
        for r in light_results:
            st.divider()
            m_l = str(r['Market']).lower()
            
            # 🏢 市場バッジ
            if 'プライム' in m_l or '一部' in m_l: 
                badge_html = '<span style="background-color: #1a237e; color: #ffffff; padding: 0.2rem 0.6rem; border-radius: 4px; font-size: 11px; font-weight: bold;">🏢 プライム/大型</span>'
            elif 'グロース' in m_l or 'マザーズ' in m_l: 
                badge_html = '<span style="background-color: #1b5e20; color: #ffffff; padding: 0.2rem 0.6rem; border-radius: 4px; font-size: 11px; font-weight: bold;">🚀 グロース/新興</span>'
            else: 
                badge_html = f'<span style="background-color: #455a64; color: #ffffff; padding: 0.2rem 0.6rem; border-radius: 4px; font-size: 11px; font-weight: bold;">{r["Market"]}</span>'
            
            t_badge = f'<span style="background-color: {r["T_Color"]}; color: #ffffff; padding: 0.2rem 0.6rem; border-radius: 4px; font-size: 13px; font-weight: bold; margin-left: 0.5rem;">🎯 優先度: {r["T_Rank"]}</span>'
            
            st.markdown(f"""
                <div style="margin-bottom: 0.8rem;">
                    <h3 style="font-size: 24px; font-weight: bold; margin: 0 0 0.3rem 0;">({str(r["Code"])[:4]}) {r["Name"]}</h3>
                    <div style="display: flex; flex-wrap: wrap; gap: 6px; align-items: center;">
                        {badge_html}{t_badge}
                        <span style="background-color: rgba(237, 108, 2, 0.15); border: 1px solid #ed6c02; color: #ed6c02; padding: 0.1rem 0.5rem; border-radius: 4px; font-size: 12px;">GC後 {r.get("GC_Days")}日目</span>
                    </div>
                </div>
            """, unsafe_allow_html=True)
            
            lc_v, h14_v, atr_v = r['lc'], r['h14'], r['atr']
            t_p, d_p = max(h14_v, lc_v + (atr_v * 0.5)), max(h14_v, lc_v + (atr_v * 0.5)) - atr_v
            
            m_cols = st.columns([1, 1, 1, 1.2, 1.5])
            m_cols[0].metric("最新終値", f"{int(lc_v):,}円")
            m_cols[1].metric("RSI", f"{r['RSI']:.1f}%")
            m_cols[2].metric("ボラ(推定)", f"{int(atr_v):,}円")
            
            # 🛡️ 防衛線ボックス
            m_cols[3].markdown(f"""
                <div style="background: rgba(239, 83, 80, 0.05); padding: 0.5rem; border-radius: 8px; border: 1px solid rgba(239, 83, 80, 0.3); text-align: center;">
                    <div style="font-size: 13px; color: rgba(250, 250, 250, 0.6); margin-bottom: 2px;">🛡️ 防衛線</div>
                    <div style="font-size: 1.6rem; font-weight: bold; color: #ef5350;">{int(d_p):,}円</div>
                </div>
            """, unsafe_allow_html=True)
            
            # 🎯 トリガーボックス
            m_cols[4].markdown(f"""
                <div style="background: rgba(255, 215, 0, 0.05); padding: 0.5rem; border-radius: 8px; border: 1px solid rgba(255, 215, 0, 0.2); text-align: center;">
                    <div style="font-size: 13px; color: rgba(250, 250, 250, 0.6); margin-bottom: 2px;">🎯 トリガー</div>
                    <div style="font-size: 1.6rem; font-weight: bold; color: #FFD700;">{int(t_p):,}円</div>
                </div>
            """, unsafe_allow_html=True)
            st.caption(f"🏭 {r['Sector']} ｜ 🏢 {r['Market']} ｜ 📊 平均出来高: {int(r['avg_vol']):,}株")

with tab3:
    st.markdown('<h3 style="font-size: clamp(14px, 4.5vw, 24px); margin-bottom: 1rem;">🎯 【照準】精密スコープ（戦術別・独立索敵）</h3>', unsafe_allow_html=True)
    
    # --- 🖥️ 【原典UI完全復旧】 二層式ターゲット入力セクション ---
    T3_AM_WATCH_FILE = f"saved_t3_am_watch_{user_id}.txt"
    T3_AM_DAILY_FILE = f"saved_t3_am_daily_{user_id}.txt"
    T3_AS_WATCH_FILE = f"saved_t3_as_watch_{user_id}.txt"
    T3_AS_DAILY_FILE = f"saved_t3_as_daily_{user_id}.txt"

    def load_t3_text(file_path):
        if os.path.exists(file_path):
            with open(file_path, "r", encoding="utf-8") as f:
                return f.read()
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
        st.markdown("#### 🔍 索敵ステータス")
        if is_ambush: 
            st.info("・【待伏専用】半値押し・黄金比での迎撃判定")
            st.markdown("""
            <div style="font-size: 13px; color: #bbb; background: rgba(255,255,255,0.05); padding: 10px; border-radius: 5px; border-left: 3px solid #2e7d32;">
                <b>【掟スコア加点基準（最大10点）】</b><br>
                ✅ 基礎モメンタム（MACD/RSIの優位性：最大+5点）<br>
                ✅ 波高1.3〜2.0倍（+1点） ｜ ✅ 調整日数が規定内（+1点）<br>
                ✅ 危険波形(Wトップ等)なし（+1点） ｜ ✅ 買値目標の±15%圏内（+1点）<br>
                ✅ 割安性：PBR 5.0倍以下（+1点）
            </div>
            """, unsafe_allow_html=True)
        else: 
            st.warning("・【強襲専用】ATR/14日高値ベースの動的ブレイクアウト判定")
            st.markdown("""
            <div style="font-size: 13px; color: #bbb; background: rgba(255,255,255,0.05); padding: 10px; border-radius: 5px; border-left: 3px solid #ed6c02;">
                <b>【強襲スコア加点基準（最大100点）】</b><br>
                ⚡ GC（ゴールデンクロス）発動（基礎+50点）<br>
                ⚡ 25日線上抜け / 上昇トレンド維持（最大+20点）<br>
                ⚡ 出来高の急増（+10点） ｜ ⚡ RSIの適正過熱感（+10点）<br>
                ⚡ 割安性：PBR 5.0倍以下（+10点）<br>
                <span style="color:#ef5350;">※ パーフェクトオーダー崩壊・過熱(RSI75超)・出来高不足は厳格減点</span>
            </div>
            """, unsafe_allow_html=True)

    if run_scope:
        # ファイル保存ロジック
        if is_ambush:
            for f, d in [(T3_AM_WATCH_FILE, watch_in), (T3_AM_DAILY_FILE, daily_in)]:
                with open(f, "w", encoding="utf-8") as file:
                    file.write(d)
            st.session_state.t3_am_watch, st.session_state.t3_am_daily = watch_in, daily_in
        else:
            for f, d in [(T3_AS_WATCH_FILE, watch_in), (T3_AS_DAILY_FILE, daily_in)]:
                with open(f, "w", encoding="utf-8") as file:
                    file.write(d)
            st.session_state.t3_as_watch, st.session_state.t3_as_daily = watch_in, daily_in

        # 全入力コードの抽出（正規表現）
        all_text = watch_in + " " + daily_in
        t_codes = list(dict.fromkeys([c.upper() for c in re.findall(r'(?<![a-zA-Z0-9])[a-zA-Z0-9]{4}(?![a-zA-Z0-9])', all_text)]))
        
        if not t_codes:
            st.warning("有効な銘柄コードが確認できません。")
        else:
            with st.spinner(f"全 {len(t_codes)} 銘柄を精密計算中..."):
                raw_data_dict = {}
                
                # 🚀 並列処理：株価データと財務指標（ROE含む）を高速取得
                def fetch_single_data_parallel(c):
                    api_code = c if len(c) == 5 else c + "0"
                    data = get_single_data(api_code, 2)
                    per, pbr, mcap, roe_res = None, None, None, None
                    try:
                        import yfinance as yf
                        tk = yf.Ticker(c[:4] + ".T")
                        info = tk.info
                        per = info.get('trailingPE')
                        pbr = info.get('priceToBook')
                        mcap = info.get('marketCap')
                        raw_roe = info.get('returnOnEquity')
                        if raw_roe:
                            roe_res = raw_roe * 100
                    except:
                        pass
                    return c, data, per, pbr, mcap, roe_res
                
                with concurrent.futures.ThreadPoolExecutor(max_workers=5) as exe:
                    futs = [exe.submit(fetch_single_data_parallel, c) for c in t_codes]
                    for f in concurrent.futures.as_completed(futs):
                        res_c, res_data, res_per, res_pbr, res_mcap, res_roe = f.result()
                        raw_data_dict[res_c] = {"data": res_data, "per": res_per, "pbr": res_pbr, "mcap": res_mcap, "roe": res_roe}

                scope_results = []
                for c in t_codes:
                    raw_s = raw_data_dict.get(c)
                    if not raw_s or not raw_s["data"]:
                        continue
                    
                    df_s = clean_df(pd.DataFrame(raw_s["data"].get("bars", [])))
                    if len(df_s) < 35:
                        continue
                    
                    df_chart = calc_technicals(df_s.copy())
                    latest = df_chart.iloc[-1]
                    prev = df_chart.iloc[-2]
                    lc = latest['AdjC']
                    
                    # 基本指標
                    rsi_v = latest.get('RSI', 50)
                    atr_v = int(latest.get('ATR', 0))
                    
                    # 掟：14日窓の計算
                    win_14 = df_s.tail(15).iloc[:-1]
                    h14 = win_14['AdjH'].max()
                    l14 = win_14['AdjL'].min()
                    ur = h14 - l14
                    
                    is_dt = check_double_top(df_s.tail(31).iloc[:-1])
                    is_hs = check_head_shoulders(df_s.tail(31).iloc[:-1])
                    
                    res_mcap = raw_s.get("mcap")
                    mcap_str = f"{res_mcap / 1e12:.2f}兆円" if res_mcap and res_mcap >= 1e12 else f"{res_mcap / 1e8:.0f}億円" if res_mcap else "-"

                    score = 4
                    if h14 > 0 and l14 > 0:
                        r14_val = h14 / l14
                        idxmax = win_14['AdjH'].idxmax()
                        d_high = len(win_14[win_14['Date'] > win_14.loc[idxmax, 'Date']]) if pd.notna(idxmax) else 0
                        if 1.3 <= r14_val <= 2.0: score += 1
                        if d_high <= int(st.session_state.limit_d): score += 1
                        if not is_dt: score += 1
                        if not is_hs: score += 1

                    if is_ambush:
                        bt_val = int(h14 - (ur * (st.session_state.push_r / 100.0)))
                        rank, bg, t_score, _ = get_triage_info(latest['MACD_Hist'], prev['MACD_Hist'], rsi_v, lc, bt_val, mode="待伏")
                        reach_rate = ((h14 - lc) / (h14 - bt_val) * 100) if (h14 - bt_val) > 0 else 0
                        if raw_s['pbr'] and raw_s['pbr'] <= 5.0:
                            score += 1
                        if check_double_bottom(df_s.tail(31).iloc[:-1]):
                            score += 1
                    else:
                        bt_val = int(max(h14, lc + (atr_v * 0.5)))
                        h_p_macd = df_chart['MACD_Hist'].tail(5).values
                        gc_days = 1 if h_p_macd[-2] < 0 and h_p_macd[-1] >= 0 else 2 if h_p_macd[-3] < 0 and h_p_macd[-1] >= 0 else 3 if h_p_macd[-4] < 0 and h_p_macd[-1] >= 0 else 0
                        rank, bg, t_score, _ = get_assault_triage_info(gc_days, lc, rsi_v, df_chart, is_strict=True)
                        reach_rate = 100 - rsi_v
                        if raw_s['pbr'] and raw_s['pbr'] <= 5.0:
                            t_score += 10
                            rank, bg = ("S", "#d32f2f") if t_score >= 80 else ("A", "#f57c00") if t_score >= 60 else ("B", "#fbc02d") if t_score >= 40 else ("C", "#424242")

                    # 市場・業種の取得
                    c_name = f"銘柄 {c[:4]}"
                    c_sector, c_market = "不明", "不明"
                    if not master_df.empty:
                        m_row = master_df[master_df['Code'].astype(str).str.contains(c[:4])]
                        if not m_row.empty:
                            c_name = m_row.iloc[0]['CompanyName']
                            c_sector = m_row.iloc[0]['Sector']
                            c_market = m_row.iloc[0]['Market']

                    scope_results.append({
                        'code': c, 'name': c_name, 'lc': lc, 'h14': h14, 'l14': l14, 'ur': ur, 'bt_val': bt_val, 'atr_val': atr_v, 'rsi': rsi_v,
                        'is_dt': is_dt, 'is_hs': is_hs, 'rank': rank, 'bg': bg, 'score': score, 'reach_val': reach_rate, 'gc_days': gc_days if not is_ambush else 0,
                        'df_chart': df_chart, 'per': raw_s['per'], 'pbr': raw_s['pbr'], 'mcap': mcap_str, 'roe': raw_s['roe'],
                        'source': "🛡️ 監視" if c in watch_in else "🚀 新規", 'sector': c_sector, 'market': c_market
                    })

                # --- 判定順ソート（S > A > B > C） ---
                rank_order = {"S": 4, "A": 3, "B": 2, "C": 1, "圏外": 0}
                for res in scope_results:
                    clean_rank = re.sub(r'[^SABC圏外]', '', res['rank'])
                    res['r_val'] = rank_order.get(clean_rank, 0)
                scope_results = sorted(scope_results, key=lambda x: (x['r_val'], x['score'], x['reach_val']), reverse=True)

                # --- 各銘柄の詳細出力ループ ---
                for r in scope_results:
                    st.divider()
                    source_color = "#42a5f5" if "監視" in r['source'] else "#ffa726"
                    m_i_name = r.get('market', '不明')
                    m_l_name = str(m_i_name).lower()
                    
                    if 'プライム' in m_l_name or '一部' in m_l_name: 
                        m_badge = '<span style="background-color: #1a237e; color: #ffffff; padding: 0.2rem 0.6rem; border-radius: 4px; font-size: 11px; font-weight: bold;">🏢 プライム/大型</span>'
                    elif 'グロース' in m_l_name or 'マザーズ' in m_l_name: 
                        m_badge = '<span style="background-color: #1b5e20; color: #ffffff; padding: 0.2rem 0.6rem; border-radius: 4px; font-size: 11px; font-weight: bold;">🚀 グロース/新興</span>'
                    else: 
                        m_badge = f'<span style="background-color: #455a64; color: #ffffff; padding: 0.2rem 0.6rem; border-radius: 4px; font-size: 11px; font-weight: bold;">{m_i_name}</span>'

                    s_badge = f"<span style='background-color:{source_color}; color:white; padding:2px 6px; border-radius:4px; font-size:12px;'>{r['source']}</span>"
                    t_badge = f"<span style='background-color:{r['bg']}; color:white; padding:2px 8px; border-radius:4px; margin-left:10px; font-weight:bold;'>🎯 優先度: {r['rank']}</span>"
                    
                    st.markdown(f"""
                        <div style="margin-bottom: 0.8rem;">
                            <h3 style="font-size: clamp(18px, 5vw, 28px); font-weight: bold; margin: 0 0 0.3rem 0;">{s_badge} ({r['code'][:4]}) {r['name']}</h3>
                            <div style="display: flex; flex-wrap: wrap; gap: 6px; align-items: center;">
                                {m_badge}{t_badge}
                                <span style="background-color: rgba(38, 166, 154, 0.15); border: 1px solid #26a69a; color: #26a69a; padding: 0.1rem 0.5rem; border-radius: 4px; font-size: 12px;">RSI: {r['rsi']:.1f}%</span>
                                <span style="background-color: rgba(255, 215, 0, 0.1); border: 1px solid #FFD700; color: #FFD700; padding: 0.1rem 0.5rem; border-radius: 4px; font-size: 12px;">到達度: {r['reach_val']:.1f}%</span>
                            </div>
                        </div>
                    """, unsafe_allow_html=True)
                    
                    # --- 🏅 ROE生体スキャンパネル（ボスの要求：進撃判定） ---
                    roe_v = r.get('roe')
                    if roe_v is not None:
                        roe_color = "#26a69a" if roe_v >= 10 else "#ef5350"
                        roe_bg = "rgba(46, 125, 80, 0.1)" if roe_v >= 10 else "rgba(198, 40, 40, 0.1)"
                        roe_status = "進撃" if roe_v >= 10 else "静観"
                        roe_icon = "✅" if roe_v >= 10 else "⚠️"
                        st.markdown(f"""
                            <div style="background: {roe_bg}; border: 1px solid {roe_color}; border-radius: 8px; padding: 0.8rem; margin-bottom: 1rem; display: flex; align-items: center; justify-content: space-between;">
                                <div>
                                    <span style="font-size: 12px; color: #aaa; font-weight: bold;">💎 財務生体スキャン: </span>
                                    <strong style="font-size: 18px; color: {roe_color}; margin-left: 8px;">{roe_icon} ROE {roe_v:.1f}% ｜ {roe_status}</strong>
                                </div>
                            </div>
                        """, unsafe_allow_html=True)
                    
                    if r['is_dt'] or r['is_hs']: 
                        st.error("🚨 【警告】相場転換の危険波形（三尊/Wトップ）を検知。撤退を推奨。")
                    if not is_ambush and r['gc_days'] > 0: 
                        st.success(f"🔥 【GC発動】MACDゴールデンクロスから {r['gc_days']}日目")
                    
                    sc_l, sc_m, sc_r = st.columns([2.5, 3.5, 5.0])
                    with sc_l:
                        atr_val_now = r['atr_val'] if r['atr_val'] > 0 else r['lc'] * 0.05
                        c_m1, c_m2 = st.columns(2)
                        c_m1.metric("直近高値", f"{int(r['h14']):,}円")
                        c_m2.metric("直近安値", f"{int(r['l14']):,}円")
                        c_m3, c_m4 = st.columns(2)
                        c_m3.metric("上昇幅", f"{int(r['ur']):,}円")
                        c_m4.metric("最新終値", f"{int(r['lc']):,}円")
                        st.metric("🌪️ 1ATR", f"{int(atr_val_now):,}円", f"ボラ: {(atr_val_now/r['lc'])*100:.1f}%", delta_color="off")
                        st.caption(f"🏭 {r['sector']}")
                    
                    with sc_m:
                        per_c = "#26a69a" if (r['per'] and r['per'] <= 50) else "#ef5350"
                        pbr_c = "#26a69a" if (r['pbr'] and r['pbr'] <= 5.0) else "#ef5350"
                        roe_c = "#26a69a" if (r['roe'] and r['roe'] >= 10) else "#ef5350"
                        roe_l = "進撃" if (r['roe'] and r['roe'] >= 10) else "静観"
                        
                        # 🚨 ValueError回避ロジック
                        per_fmt = f"{r['per']:.1f}倍" if r['per'] is not None else "-"
                        pbr_fmt = f"{r['pbr']:.2f}倍" if r['pbr'] is not None else "-"
                        roe_fmt = f"{r['roe']:.1f}%" if r['roe'] is not None else "-"

                        html_metrics = f"""
                            <div style='display:flex; justify-content:space-between; text-align:center; margin-top:8px;'>
                                <div style='flex:1;'><div style='font-size:12px; color:#888;'>📊 PER</div><div style='font-size:1.4rem; color:{per_c}; font-weight:bold;'>{per_fmt}</div></div>
                                <div style='flex:1;'><div style='font-size:12px; color:#888;'>📉 PBR</div><div style='font-size:1.4rem; color:{pbr_c}; font-weight:bold;'>{pbr_fmt}</div></div>
                                <div style='flex:1;'><div style='font-size:12px; color:#888;'>📈 ROE({roe_l})</div><div style='font-size:1.4rem; color:{roe_c}; font-weight:bold;'>{roe_fmt}</div></div>
                            </div>
                            <div style='text-align:center; margin-top:5px; border-top:1px solid rgba(255,255,255,0.05); padding-top:5px;'>
                                <div style='font-size:11px; color:#888;'>💰 時価総額</div><div style='font-size:1.2rem; color:#fff; font-weight:bold;'>{r['mcap']}</div>
                            </div>"""
                        box_title = "🎯 買値目標" if is_ambush else "🎯 トリガー (14d高値)"
                        st.markdown(f"""<div style='background:rgba(255,215,0,0.05); padding:1rem; border-radius:10px; border:1px solid rgba(255,215,0,0.3); text-align:center;'><div style='font-size:14px;'>{box_title}</div><div style='font-size:2.4rem; font-weight:bold; color:#FFD700;'>{int(r['bt_val']):,}円</div><div style='border-top:1px dashed #444; margin:10px 0;'></div>{html_metrics}</div>""", unsafe_allow_html=True)

                    with sc_r:
                        c_target = r['bt_val']
                        atr_val_ref = r['atr_val'] if r['atr_val'] > 0 else c_target * 0.05
                        tp_multipliers = [0.5, 1.0, 2.0, 3.0]
                        sl_multipliers = [0.5, 1.0, 2.0]
                        html_matrix = f"<div style='background:rgba(255,255,255,0.05); padding:1.2rem; border-radius:8px; border-left:5px solid #FFD700;'><div style='font-size:14px; color:#aaa; margin-bottom:12px;'>📊 動的ATRマトリクス (基準:{int(c_target):,}円 | 1ATR:{int(atr_val_ref):,}円)</div><div style='display:flex; gap:30px;'><div style='flex:1;'><div style='color:#26a69a; border-bottom:2px solid #26a69a; margin-bottom:8px;'>【利確目安】</div>"
                        for m_val in tp_multipliers:
                            val_res = int(c_target + (atr_val_ref * m_val))
                            html_matrix += f"<div style='display:flex; justify-content:space-between;'><span>+{m_val}ATR</span><b>{val_res:,}</b></div>"
                        html_matrix += "</div><div style='flex:1;'><div style='color:#ef5350; border-bottom:2px solid #ef5350; margin-bottom:8px;'>【防衛目安】</div>"
                        for m_val in sl_multipliers:
                            val_res = int(c_target - (atr_val_ref * m_val))
                            html_matrix += f"<div style='display:flex; justify-content:space-between;'><span>-{m_val}ATR</span><b>{val_res:,}</b></div>"
                        st.markdown(html_matrix + "</div></div></div>", unsafe_allow_html=True)
                    
                    # チャート描画
                    st.markdown("---")
                    df_plot = r['df_chart'].tail(100).copy()
                    df_plot['display_date'] = df_plot['Date'].dt.strftime('%m/%d')
                    fig_scope = go.Figure()
                    fig_scope.add_trace(go.Candlestick(x=df_plot['display_date'], open=df_plot['AdjO'], high=df_plot['AdjH'], low=df_plot['AdjL'], close=df_plot['AdjC'], name="価格", increasing_line_color='#26a69a', decreasing_line_color='#ef5350'))
                    for ma_col, ma_name, ma_color in [('MA5','5日','#ffca28'),('MA25','25日','#42a5f5'),('MA75','75日','#ab47bc')]:
                        fig_scope.add_trace(go.Scatter(x=df_plot['display_date'], y=df_plot[ma_col], name=ma_name, mode='lines', line=dict(color=ma_color, width=1.5)))
                    fig_scope.add_trace(go.Scatter(x=df_plot['display_date'], y=[r['bt_val']]*len(df_plot), name="目標", mode='lines', line=dict(color='#FFD700', width=2, dash='dot')))
                    fig_scope.update_layout(height=450, margin=dict(l=0, r=0, t=10, b=50), xaxis_rangeslider_visible=False, paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)', hovermode="x unified", yaxis=dict(side='right', tickformat=",.0f"), xaxis=dict(type='category', dtick=5), showlegend=True, legend=dict(orientation="h", yanchor="top", y=-0.2, xanchor="center", x=0.5))
                    st.plotly_chart(fig_scope, use_container_width=True, config={'displayModeBar': False})

                    # --- ⚙️ 個別銘柄バックテスト計算ロジック（全行復元） ---
                    st.markdown(f"#### ⚙️ 銘柄 {r['code']} に対する過去1年の戦術介入シミュレーション結果")
                    lot_bt = st.session_state.bt_lot
                    tp_bt = st.session_state.bt_tp / 100.0
                    sli_bt = st.session_state.bt_sl_i / 100.0
                    slc_bt = st.session_state.bt_sl_c / 100.0
                    max_d_bt = st.session_state.bt_sell_d
                    lim_d_bt = st.session_state.limit_d
                    
                    df_bt_sub = r['df_chart'].copy()
                    sim_history = []; bt_count = 0; bt_wins = 0; bt_total_pnl = 0
                    
                    for i_bt in range(50, len(df_bt_sub) - 5):
                        sub_bt = df_bt_sub.iloc[:i_bt+1]
                        cur_bt = sub_bt.iloc[-1]
                        c_vals = sub_bt['AdjC'].values
                        h_vals_bt = sub_bt['AdjH'].values
                        l_vals_bt = sub_bt['AdjL'].values
                        is_entry = False; entry_p_bt = 0
                        
                        if is_ambush:
                            r4h_bt = h_vals_bt[-4:]; h4_bt = r4h_bt.max()
                            gi_bt = len(h_vals_bt)-4+r4h_bt.argmax()
                            l14_bt = l_vals_bt[max(0, gi_bt-14):gi_bt+1].min()
                            if l14_bt > 0 and (h4_bt/l14_bt) >= st.session_state.f9_min14:
                                t_v_bt = h4_bt - ((h4_bt-l14_bt)*(st.session_state.push_r/100.0))
                                if cur_bt['AdjC'] <= t_v_bt and (len(h_vals_bt)-1-gi_bt) <= lim_d_bt: 
                                    is_entry = True
                                    entry_p_bt = cur_bt['AdjC']
                        else:
                            hist_vals_bt = sub_bt['MACD_Hist'].values
                            if hist_vals_bt[-2] < 0 and hist_vals_bt[-1] >= 0 and cur_bt['AdjC'] >= h_vals_bt[-14:].max():
                                is_entry = True
                                entry_p_bt = cur_bt['AdjC']

                        if is_entry:
                            bt_count += 1
                            stop_p_bt = entry_p_bt * (1 - sli_bt)
                            take_p_bt = entry_p_bt * (1 + tp_bt)
                            exit_p_bt = 0; hold_bt = 0
                            for j_bt in range(i_bt+1, min(i_bt+max_d_bt+1, len(df_bt_sub))):
                                nxt_bt = df_bt_sub.iloc[j_bt]
                                hold_bt += 1
                                if nxt_bt['AdjH'] >= take_p_bt:
                                    exit_p_bt = take_p_bt
                                    bt_wins += 1
                                    break
                                if nxt_bt['AdjL'] <= stop_p_bt:
                                    exit_p_bt = stop_p_bt
                                    break
                                if hold_bt >= max_d_bt:
                                    exit_p_bt = nxt_bt['AdjC']
                                    break
                                # トレーリングストップ
                                stop_p_bt = max(stop_p_bt, nxt_bt['AdjC'] * (1 - slc_bt))
                            
                            if exit_p_bt > 0:
                                pnl_bt = (exit_p_bt - entry_p_bt) * lot_bt
                                bt_total_pnl += pnl_bt
                                sim_history.append({"日付": sub_bt.iloc[-1]['Date'].strftime('%m/%d'), "保有": f"{hold_bt}日", "買値": int(entry_p_bt), "売値": int(exit_p_bt), "損益": int(pnl_bt)})

                    if bt_count > 0:
                        bt_res_cols = st.columns(4)
                        bt_res_cols[0].metric("試行数", f"{bt_count}回")
                        bt_res_cols[1].metric("勝率", f"{(bt_wins/bt_count)*100:.1f}%")
                        bt_res_cols[2].metric("累計損益", f"{int(bt_total_pnl):,}円")
                        bt_res_cols[3].metric("期待値", f"{int(bt_total_pnl/bt_count):,}円")
                        with st.expander("📝 介入履歴詳細"):
                            st.table(pd.DataFrame(sim_history).tail(10))
                    else:
                        st.info("ℹ️ 現在の掟に合致する過去1年のシグナルは検出されなかった。")
                        
with tab4:
    st.markdown('<h3 style="font-size: clamp(14px, 4.5vw, 24px); margin-bottom: 1rem;">⚙️ 戦術シミュレータ (2年間のバックテスト)</h3>', unsafe_allow_html=True)
    
    # 🚨 AttributeErrorを物理的に抹殺する初期化プロトコル
    def force_init_sim_final_v24():
        s = st.session_state
        initial_keys = {
            "sim_tp_val": 10.0, 
            "sim_sl_val": 8.0, 
            "sim_limit_d_val": 4, 
            "sim_sell_d_val": 10,
            "sim_push_r_val": 50.0,
            "sim_pass_req_val": 7,
            "sim_rsi_lim_ambush_val": 45,
            "sim_rsi_lim_assault_val": 70,
            "sim_time_risk_val": 5
        }
        for k, v in initial_keys.items():
            if k not in s:
                s[k] = v

    force_init_sim_final_v24()

    # UI同期用ヘルパー
    def sync_sim_p(ui_key, store_key):
        st.session_state[store_key] = st.session_state[ui_key]
        save_settings()

    # UI側表示用キーの強制同期
    st.session_state['_ui4_tp'] = int(st.session_state.sim_tp_val)
    st.session_state['_ui4_sl'] = int(st.session_state.sim_sl_val)
    st.session_state['_ui4_lim'] = int(st.session_state.sim_limit_d_val)
    st.session_state['_ui4_sell'] = int(st.session_state.sim_sell_d_val)
    st.session_state['_ui4_push'] = float(st.session_state.sim_push_r_val)

    if "bt_mode_sim_v2" not in st.session_state:
        st.session_state.bt_mode_sim_v2 = "🌐 【待伏】鉄の掟 (押し目狙撃)"

    col_b1, col_b2 = st.columns([1, 1.8])
    T4_CODES_FILE = f"saved_t4_codes_{user_id}.txt"
    default_t4_codes = "7839\n6614"
    if os.path.exists(T4_CODES_FILE):
        with open(T4_CODES_FILE, "r", encoding="utf-8") as f:
            default_t4_codes = f.read()

    with col_b1:
        st.markdown("🔍 **検証戦術**")
        st.radio("戦術モード", ["🌐 【待伏】鉄の掟 (押し目狙撃)", "⚡ 【強襲】GCブレイクアウト (順張り)"], key="bt_mode_sim_v2")
        bt_codes_in = st.text_area("検証対象コード (一括入力)", value=default_t4_codes, height=100, key="bt_codes_sim_v2")
        run_bt = st.button("🔥 仮想実弾テスト実行", use_container_width=True, type="primary")
        optimize_bt = st.button("🚀 戦術最適化レポート (黄金比抽出)", use_container_width=True)
        
    with col_b2:
        st.markdown("#### ⚙️ 戦術パラメーター（演習用チューニング）")
        cp1, cp2, cp3, cp4 = st.columns(4)
        cp1.number_input("🎯 利確(%)", step=1, key="_ui4_tp", on_change=sync_sim_p, args=("_ui4_tp", "sim_tp_val"))
        cp2.number_input("🛡️ 損切(%)", step=1, key="_ui4_sl", on_change=sync_sim_p, args=("_ui4_sl", "sim_sl_val"))
        cp3.number_input("買い猶予", step=1, key="_ui4_lim", on_change=sync_sim_p, args=("_ui4_lim", "sim_limit_d_val"))
        cp4.number_input("売り期限", step=1, key="_ui4_sell", on_change=sync_sim_p, args=("_ui4_sell", "sim_sell_d_val"))
        st.divider()
        st.markdown("##### 🌐 【待伏】シミュレータ固有設定")
        ct1, ct2 = st.columns(2)
        ct1.number_input("📉 押し目待ち(%)", step=0.1, key="_ui4_push", on_change=sync_sim_p, args=("_ui4_push", "sim_push_r_val"))
        st.info("※ このタブでの検証は「砂場」であり、実戦環境（TAB1/2）の設定とは独立してパラメータを探索可能だ。")

    if (run_bt or optimize_bt) and bt_codes_in:
        with open(T4_CODES_FILE, "w", encoding="utf-8") as f:
            f.write(bt_codes_in)
        t_codes_sim = list(dict.fromkeys([c.upper() for c in re.findall(r'(?<![a-zA-Z0-9])[a-zA-Z0-9]{4}(?![a-zA-Z0-9])', bt_codes_in)]))
        
        if not t_codes_sim:
            st.warning("有効なコードが見つかりません。")
        else:
            sim_tp = float(st.session_state.sim_tp_val)
            sim_sl_init = float(st.session_state.sim_sl_val)
            sim_sell_limit = int(st.session_state.sim_sell_d_val)
            is_ambush_mode = "待伏" in st.session_state.bt_mode_sim_v2
            p1_range_sim = range(25, 66, 5) if optimize_bt else [int(st.session_state.sim_push_r_val)]
            
            with st.spinner("過去2年間のデータをプリロード中..."):
                preloaded_sim_dfs = {}
                for code_sim in t_codes_sim:
                    raw_sim = get_single_data(code_sim + "0", 2)
                    if raw_sim and raw_sim.get('bars'):
                        df_sim_raw = clean_df(pd.DataFrame(raw_sim['bars']))
                        if len(df_sim_raw) >= 35:
                            preloaded_sim_dfs[code_sim] = calc_technicals(df_sim_raw)
            
            if not preloaded_sim_dfs:
                st.error("解析可能なデータがありません。")
                st.stop()

            opt_results_sim = []
            p_bar_sim_total = st.progress(0, "総当たり戦術検証中...")
            total_it_sim_exec = len(p1_range_sim)
            curr_it_sim_exec = 0
            
            for t_p_val_sim in p1_range_sim:
                curr_it_sim_exec += 1
                trade_logs_sim = []
                for code_sim, df_sim_exec in preloaded_sim_dfs.items():
                    pos_sim = None
                    for i_sim in range(35, len(df_sim_exec)):
                        t_day_sim = df_sim_exec.iloc[i_sim]
                        p_day_sim = df_sim_exec.iloc[i_sim-1]
                        if pos_sim is None:
                            h14_sim_exec = df_sim_exec.iloc[i_sim-15:i_sim-1]['AdjH'].max()
                            l14_sim_exec = df_sim_exec.iloc[i_sim-15:i_sim-1]['AdjL'].min()
                            if is_ambush_mode:
                                bt_trigger_sim = int(h14_sim_exec - ((h14_sim_exec - l14_sim_exec) * (t_p_val_sim / 100.0)))
                                if t_day_sim['AdjL'] <= bt_trigger_sim: 
                                    pos_sim = {'b_i': i_sim, 'b_d': t_day_sim['Date'], 'b_p': min(t_day_sim['AdjO'], bt_trigger_sim)}
                            else:
                                if p_day_sim.get('MACD_Hist', 0) > 0 and df_sim_exec.iloc[i_sim-2].get('MACD_Hist', 0) <= 0 and t_day_sim['AdjH'] >= h14_sim_exec:
                                    pos_sim = {'b_i': i_sim, 'b_d': t_day_sim['Date'], 'b_p': t_day_sim['AdjO']}
                        else:
                            held_d_sim = i_sim - pos_sim['b_i']
                            b_price_sim = pos_sim['b_p']
                            s_price_sim = 0
                            tp_price_sim = b_price_sim * (1 + (sim_tp / 100.0))
                            sl_price_sim = b_price_sim * (1 - sim_sl_init / 100.0)
                            
                            if t_day_sim['AdjL'] <= sl_price_sim: s_price_sim = sl_price_sim
                            elif t_day_sim['AdjH'] >= tp_price_sim: s_price_sim = tp_price_sim
                            elif held_d_sim >= sim_sell_limit: s_price_sim = t_day_sim['AdjC']
                            
                            if s_price_sim > 0:
                                trade_logs_sim.append({'銘柄': code_sim, '決済日': t_day_sim['Date'], '買値': int(b_price_sim), '売値': int(s_price_sim), '損益': int((s_price_sim - b_price_sim) * st.session_state.bt_lot), '勝敗': 1 if s_price_sim > b_price_sim else 0})
                                pos_sim = None
                
                if trade_logs_sim:
                    tdf_sim_res = pd.DataFrame(trade_logs_sim)
                    opt_results_sim.append({'Push率': t_p_val_sim, '利益': tdf_sim_res['損益'].sum(), '勝率': tdf_sim_res['勝敗'].mean(), '回数': len(trade_logs_sim), 'data': tdf_sim_res})
                p_bar_sim_total.progress(curr_it_sim_exec / total_it_sim_exec)
            
            p_bar_sim_total.empty()
            if optimize_bt and opt_results_sim:
                res_df_sim_final = pd.DataFrame(opt_results_sim).sort_values('利益', ascending=False)
                best_sim_final = res_df_sim_final.iloc[0]
                st.markdown(f"### 🏆 最適化結果: 推奨Push率 {best_sim_final['Push率']}%")
                c1_s, c2_s, c3_s = st.columns(3)
                c1_s.metric("最高利益額", f"{int(best_sim_final['利益']):,}円")
                c2_s.metric("期待勝率", f"{best_sim_final['勝率']*100:.1f}%")
                c3_s.metric("取引回数", f"{best_sim_final['回数']}回")
                st.dataframe(res_df_sim_final.drop(columns=['data']).style.background_gradient(subset=['利益']), use_container_width=True)
            elif run_bt and opt_results_sim:
                tdf_final_exec = opt_results_sim[0]['data'].sort_values('決済日')
                tdf_final_exec['累積損益'] = tdf_final_exec['損益'].cumsum()
                st.success("🎯 バックテスト完了。")
                st.markdown(f"### 総合損益: {tdf_final_exec['損益'].sum():,}円")
                fig_sim_curve = go.Figure()
                fig_sim_curve.add_trace(go.Scatter(x=tdf_final_exec['決済日'], y=tdf_final_exec['累積損益'], mode='lines+markers', name='資産推移', line=dict(color='#FFD700')))
                fig_sim_curve.update_layout(paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0.1)', height=400, margin=dict(l=0,r=0,t=20,b=0))
                st.plotly_chart(fig_sim_curve, use_container_width=True)
                st.dataframe(tdf_final_exec.style.format({'買値': '{:,}', '売値': '{:,}', '損益': '{:,}'}), use_container_width=True)

with tab5:
    st.markdown('<h3 style="font-size: clamp(14px, 4.5vw, 24px); margin-bottom: 1rem;">📡 交戦モニター (全軍生存圏レーダー)</h3>', unsafe_allow_html=True)
    FRONTLINE_FILE_PATH = f"saved_frontline_{user_id}.csv"
    if 'frontline_df' not in st.session_state:
        if os.path.exists(FRONTLINE_FILE_PATH):
            try:
                st.session_state.frontline_df = pd.read_csv(FRONTLINE_FILE_PATH)
                st.session_state.frontline_df["銘柄"] = st.session_state.frontline_df["銘柄"].astype(str)
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
                tk_fr_sync = yf.Ticker(c_fr_sync[:4] + ".T")
                h_fr_sync = tk_fr_sync.history(period="1d")
                if not h_fr_sync.empty:
                    st.session_state.frontline_df.at[idx_fr, '現在値'] = round(h_fr_sync['Close'].iloc[-1], 1)
                    updated_fr_sync = True
        if updated_fr_sync:
            st.session_state.frontline_df.to_csv(FRONTLINE_FILE_PATH, index=False)
            st.rerun()

    edited_frontline_df = st.data_editor(st.session_state.frontline_df, num_rows="dynamic", use_container_width=True, key="frontline_editor_v24_final")
    if not edited_frontline_df.equals(st.session_state.frontline_df):
        st.session_state.frontline_df = edited_frontline_df
        edited_frontline_df.to_csv(FRONTLINE_FILE_PATH, index=False)
        st.rerun()

    st.markdown("---")
    for idx_mon, r_mon in edited_frontline_df.iterrows():
        t_m, b_m, tp1_m, tp2_m, s_m, c_m = str(r_mon.get('銘柄', '')), r_mon['買値'], r_mon['第1利確'], r_mon['第2利確'], r_mon['損切'], r_mon['現在値']
        if not t_m or pd.isna(b_m) or pd.isna(c_m): continue
        if c_m <= s_m: col_m, txt_m = "#ef5350", "💀 被弾（防衛線突破）"
        elif c_m < b_m: col_m, txt_m = "#ff9800", "⚠️ 警戒（損切圏内）"
        elif tp1_m > 0 and c_m < tp1_m: col_m, txt_m = "#26a69a", "🟢 巡航（第1目標へ）"
        elif tp2_m > 0 and c_m < tp2_m: col_m, txt_m = "#42a5f5", "🛡️ 無敵化（第2目標へ）"
        else: col_m, txt_m = "#ab47bc", "🏆 任務完了（利確推奨）"
        
        st.markdown(f'<div style="background: rgba(255,255,255,0.03); padding: 12px; border-radius: 8px; border-left: 5px solid {col_m}; margin-bottom: 5px;"><strong>部隊 [{t_m}]</strong> {txt_m} ｜ 現在: ¥{int(c_m):,} (買: ¥{int(b_m):,})</div>', unsafe_allow_html=True)
        fig_mon = go.Figure()
        fig_mon.add_trace(go.Scatter(x=[s_m, b_m, tp1_m, tp2_m], y=[0,0,0,0], mode='markers', marker=dict(size=12, color=['#ef5350','#ffca28','#26a69a','#42a5f5']), name="目標"))
        fig_mon.add_trace(go.Scatter(x=[c_m], y=[0], mode='markers', marker=dict(size=22, symbol='cross-thin', line=dict(width=3, color=col_m)), name="現在地"))
        fig_mon.update_layout(height=80, margin=dict(l=10, r=10, t=10, b=10), paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)', yaxis=dict(visible=False), xaxis=dict(showgrid=False, zeroline=False))
        st.plotly_chart(fig_mon, use_container_width=True, config={'displayModeBar': False})

with tab6:
    st.markdown('<h3 style="font-size: 24px;">📁 事後任務報告 (AAR) & 総合戦績</h3>', unsafe_allow_html=True)
    AAR_LOG_FILE = f"saved_aar_log_{user_id}.csv"
    if os.path.exists(AAR_LOG_FILE):
        aar_df_final = pd.read_csv(AAR_LOG_FILE)
    else:
        aar_df_final = pd.DataFrame(columns=["決済日", "銘柄", "戦術", "買値", "売値", "株数", "損益額(円)", "損益(%)", "規律", "メモ"])

    col_aar1, col_aar2 = st.columns([1, 2.2])
    with col_aar1:
        st.markdown("#### 📝 戦果報告")
        with st.form("aar_form_v24_final"):
            d_aar = st.date_input("決済日")
            c_aar = st.text_input("銘柄コード")
            t_aar = st.selectbox("戦術", ["待伏", "強襲", "他"])
            b_aar = st.number_input("買値")
            s_aar = st.number_input("売値")
            l_aar = st.number_input("株数", step=100)
            r_aar = st.radio("規律", ["遵守", "違反"])
            m_aar = st.text_input("メモ")
            if st.form_submit_button("記録を保存"):
                p_aar = int((s_aar - b_aar) * l_aar)
                pp_aar = round(((s_aar / b_aar) - 1) * 100, 2) if b_aar != 0 else 0
                nd_aar = pd.DataFrame([{"決済日":d_aar, "銘柄":c_aar, "戦術":t_aar, "買値":b_aar, "売値":s_aar, "株数":l_aar, "損益額(円)":p_aar, "損益(%)":pp_aar, "規律":r_aar, "メモ":m_aar}])
                pd.concat([nd_aar, aar_df_final]).to_csv(AAR_LOG_FILE, index=False)
                st.rerun()

    with col_aar2:
        if not aar_df_final.empty:
            aar_df_final["損益額(円)"] = pd.to_numeric(aar_df_final["損益額(円)"], errors='coerce')
            tot_p_aar = aar_df_final["損益額(円)"].sum()
            w_cnt_aar = len(aar_df_final[aar_df_final["損益額(円)"] > 0])
            w_rate_aar = (w_cnt_aar / len(aar_df_final)) * 100
            
            # PF（プロフィットファクター）
            gross_p_aar = aar_df_final[aar_df_final["損益額(円)"] > 0]["損益額(円)"].sum()
            gross_l_aar = abs(aar_df_final[aar_df_final["損益額(円)"] < 0]["損益額(円)"].sum())
            pf_aar = round(gross_p_aar / gross_l_aar, 2) if gross_l_aar > 0 else 9.99
            
            # 規律遵守率
            adh_aar = (len(aar_df_final[aar_df_final["規律"] == "遵守"]) / len(aar_df_final)) * 100

            m1_a, m2_a, m3_a, m4_a = st.columns(4)
            m1_a.metric("総損益", f"{int(tot_p_aar):,}円")
            m2_a.metric("勝率", f"{w_rate_aar:.1f}%")
            m3_a.metric("PF", pf_aar)
            m4_a.metric("規律遵守率", f"{adh_aar:.1f}%")
            
            # 実資産損益曲線
            import plotly.express as px
            aar_df_final['決済日'] = pd.to_datetime(aar_df_final['決済日'])
            tdf_aar_curve = aar_df_final.sort_values('決済日')
            tdf_aar_curve['累積'] = tdf_aar_curve['損益額(円)'].cumsum()
            fig_aar_equity = px.line(tdf_aar_curve, x='決済日', y='累積', title="実資産推移 (Real Equity Curve)", markers=True)
            fig_aar_equity.update_traces(line_color='#26a69a')
            fig_aar_equity.update_layout(paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0.1)', height=300, margin=dict(l=0,r=0,t=30,b=0))
            st.plotly_chart(fig_aar_equity, use_container_width=True)

    st.dataframe(aar_df_final, use_container_width=True)
