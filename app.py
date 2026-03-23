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

# --- st.metricの文字切れ（...）を防ぐスナイパーパッチ ---
st.markdown("""
    <style>
    /* Metric値の省略記号(...)を強制解除 */
    [data-testid="stMetricValue"] > div {
        text-overflow: clip !important;
        overflow: visible !important;
        white-space: nowrap !important;
    }
    
    /* カラムの狭さに合わせてフォントサイズを少し絞る（デフォルトは約1.8rem） */
    [data-testid="stMetricValue"] {
        font-size: 1.4rem !important; 
    }
    </style>
""", unsafe_allow_html=True)

# --- 1. ページ設定 ---
st.set_page_config(page_title="戦術スコープ『鉄の掟』", layout="wide")

# --- 1.5 ユーザー認証（ゲートキーパー） ---
ALLOWED_PASSWORDS = [p.strip() for p in st.secrets.get("APP_PASSWORD", "sniper2026").split(",")]

def check_password():
    if "password_correct" not in st.session_state:
        st.session_state["password_correct"] = False
        st.session_state["current_user"] = "" 

    if not st.session_state["password_correct"]:
        st.markdown('<h1 style="text-align: center; color: #2e7d32; margin-top: 10vh; font-size: clamp(20px, 6vw, 42px); white-space: nowrap;">🎯 戦術スコープ『鉄の掟』</h1>', unsafe_allow_html=True)
        st.markdown('<p style="text-align: center; font-size: clamp(12px, 3vw, 16px); color: #888;">アクセスコードを入力してください</p>', unsafe_allow_html=True)
        
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

if not check_password():
    st.stop()

# ==========================================
# 認証成功後のメインシステム
# ==========================================
user_id = st.session_state["current_user"]
st.markdown(f'<h1 style="font-size: clamp(24px, 7vw, 42px); font-weight: 900; letter-spacing: 0.05em; border-bottom: 2px solid #2e7d32; padding-bottom: 0.5rem; margin-bottom: 1rem;">🎯 戦術スコープ『鉄の掟』 <span style="font-size: 16px; font-weight: normal; color: #888;">(ID: {user_id[:4]}***)</span></h1>', unsafe_allow_html=True)

# --- 2. 認証・通信設定 ---
API_KEY = st.secrets.get("JQUANTS_API_KEY", "").strip()
headers = {"x-api-key": API_KEY}
BASE_URL = "https://api.jquants.com/v2"

# --- 3. 共通関数 ---
def clean_df(df):
    r_cols = {'AdjustmentOpen': 'AdjO', 'AdjustmentHigh': 'AdjH', 'AdjustmentLow': 'AdjL', 'AdjustmentClose': 'AdjC', 'Open': 'AdjO', 'High': 'AdjH', 'Low': 'AdjL', 'Close': 'AdjC'}
    df = df.rename(columns=r_cols)
    for c in ['AdjO', 'AdjH', 'AdjL', 'AdjC']:
        if c in df.columns: df[c] = pd.to_numeric(df[c], errors='coerce')
    if 'Date' in df.columns:
        df['Date'] = pd.to_datetime(df['Date'])
        df = df.sort_values('Date').dropna(subset=['AdjO', 'AdjH', 'AdjL', 'AdjC']).reset_index(drop=True)
    return df

@st.cache_data(ttl=86400, show_spinner=False)
def calc_historical_win_rate(c, push_r, buy_d, tp, sl_i, sl_c, sell_d, mode):
    raw = get_single_data(c + "0", 2) # 過去2年分のデータで検証
    if not raw: return None
    df = clean_df(pd.DataFrame(raw))
    if len(df) < 60: return None
    
    trades = []
    pos = None
    for i in range(30, len(df)):
        td = df.iloc[i]
        if pos is None:
            win_14 = df.iloc[i-14:i]
            win_30 = df.iloc[i-30:i]
            rh = win_14['AdjH'].max(); rl = win_14['AdjL'].min()
            if pd.isna(rh) or pd.isna(rl) or rl <= 0: continue
            idxmax = win_14['AdjH'].idxmax()
            h_d = len(win_14[win_14['Date'] > win_14.loc[idxmax, 'Date']])
            r14 = rh / rl
            
            if (1.3 <= r14 <= 2.0) and (h_d <= buy_d):
                if check_double_top(win_30) or check_head_shoulders(win_30): continue
                
                if "攻め" in mode:
                    if check_double_bottom(win_30): pos = {'b_i': i, 'b_p': td['AdjO']}
                else:
                    targ = rh - ((rh - rl) * (push_r / 100))
                    if td['AdjL'] <= targ: pos = {'b_i': i, 'b_p': min(td['AdjO'], targ)}
        else:
            bp = pos['b_p']; held = i - pos['b_i']; sp = 0
            sl_val_i = bp * (1 - (sl_i / 100)); tp_val = bp * (1 + (tp / 100)); sl_val_c = bp * (1 - (sl_c / 100))
            
            if td['AdjL'] <= sl_val_i: sp = min(td['AdjO'], sl_val_i)
            elif td['AdjH'] >= tp_val: sp = max(td['AdjO'], tp_val)
            elif td['AdjC'] <= sl_val_c: sp = td['AdjC']
            elif held >= sell_d: sp = td['AdjC']
            
            if sp > 0:
                trades.append(sp - bp)
                pos = None
                
    if not trades: return None
    wins = len([t for t in trades if t > 0])
    return {'total': len(trades), 'win_rate': (wins / len(trades)) * 100, 'exp_val': sum(trades) / len(trades)}
    
@st.cache_data(ttl=86400)
def load_master():
    try:
        h = {'User-Agent': 'Mozilla/5.0'}
        r1 = requests.get("https://www.jpx.co.jp/markets/statistics-equities/misc/01.html", headers=h, timeout=10)
        m = re.search(r'href="([^"]+data_j\.xls)"', r1.text)
        if m:
            r2 = requests.get("https://www.jpx.co.jp" + m.group(1), headers=h, timeout=15)
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
    d_h = base - timedelta(days=180)
    while d_h.weekday() >= 5: d_h -= timedelta(days=1)
    dates.append(d_h.strftime('%Y%m%d'))
    d_y = base - timedelta(days=365)
    while d_y.weekday() >= 5: d_y -= timedelta(days=1)
    dates.append(d_y.strftime('%Y%m%d'))
    
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

# ==========================================
# 🚀 2週間（14日間）専用の波形判定モジュール
# ==========================================
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
                if valley < min(p1_val, p2_val) * 0.95:
                    if c[-1] < p2_val * 0.97: return True
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
            if p2_val > p1_val and p2_val > p3_val:
                if abs(p3_val - p1_val) / max(p3_val, p1_val) < 0.10:
                    if c[-1] < p3_val * 0.97: return True
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
                if peak > max(v1_val, v2_val) * 1.04: 
                    if c[-1] > v2_val * 1.01: return True
        return False
    except: return False

def check_sakata_patterns(df_sub):
    if len(df_sub) < 25:
        return None
        
    df = df_sub.copy()
    df['SMA_25'] = df['AdjC'].rolling(window=25).mean()
    
    current = df.iloc[-1]
    prev1 = df.iloc[-2]
    prev2 = df.iloc[-3]
    
    is_bullish = current['AdjC'] > current['AdjO']
    is_bullish_1 = prev1['AdjC'] > prev1['AdjO']
    is_bullish_2 = prev2['AdjC'] > prev2['AdjO']

    is_bearish = current['AdjC'] < current['AdjO']
    is_bearish_1 = prev1['AdjC'] < prev1['AdjO']
    is_bearish_2 = prev2['AdjC'] < prev2['AdjO']

    red_three_soldiers = (
        is_bullish and is_bullish_1 and is_bullish_2 and
        (current['AdjC'] > prev1['AdjC']) and (prev1['AdjC'] > prev2['AdjC']) and
        (current['AdjH'] > prev1['AdjH']) and (prev1['AdjH'] > prev2['AdjH'])
    )

    black_three_crows = (
        is_bearish and is_bearish_1 and is_bearish_2 and
        (current['AdjC'] < prev1['AdjC']) and (prev1['AdjC'] < prev2['AdjC']) and
        (current['AdjL'] < prev1['AdjL']) and (prev1['AdjL'] < prev2['AdjL'])
    )

    body = abs(current['AdjC'] - current['AdjO'])
    lower_shadow = min(current['AdjO'], current['AdjC']) - current['AdjL']
    takuri_line = (lower_shadow >= body * 2.5) and (body > 0)

    sma25 = current['SMA_25']
    if pd.isna(sma25):
        return None

    if red_three_soldiers and (current['AdjC'] < sma25):
        return "🔴 赤三兵（底打ち反転）"
    elif takuri_line and (current['AdjC'] < sma25):
        return "🔴 たくり線（強力な床）"
    elif black_three_crows and (current['AdjC'] > sma25):
        return "🟢 黒三兵（下落警戒）"
    elif black_three_crows and (current['AdjC'] < sma25):
        return "🔥 陰の極み（底値の黒三兵・セリクラ反発待ち）"
        
    return None

# ==========================================
# 📡 狙撃用計器（テクニカル・レーダー）関数群
# ==========================================
def calc_technicals(df):
    df = df.copy()
    if len(df) < 16:   # ← 「16」に変更（これで28日や29日のデータでも計器がフル稼働します）
        df['RSI'] = 50; df['MACD_Hist'] = 0; df['ATR'] = 0
        return df
        
    # RSI (14日)
    delta = df['AdjC'].diff()
    gain = delta.where(delta > 0, 0)
    loss = -delta.where(delta < 0, 0)
    avg_gain = gain.ewm(alpha=1/14, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1/14, adjust=False).mean()
    rs = avg_gain / avg_loss
    df['RSI'] = 100 - (100 / (1 + rs))
    
    # MACD (12, 26, 9)
    ema_fast = df['AdjC'].ewm(span=12, adjust=False).mean()
    ema_slow = df['AdjC'].ewm(span=26, adjust=False).mean()
    macd = ema_fast - ema_slow
    signal = macd.ewm(span=9, adjust=False).mean()
    df['MACD_Hist'] = macd - signal
    
    # ATR（14日間の平均真の値幅：ボラティリティ）
    high_low = df['AdjH'] - df['AdjL']
    high_prev_c = (df['AdjH'] - df['AdjC'].shift(1)).abs()
    low_prev_c = (df['AdjL'] - df['AdjC'].shift(1)).abs()
    tr = pd.concat([high_low, high_prev_c, low_prev_c], axis=1).max(axis=1)
    df['ATR'] = tr.rolling(window=14).mean()
    
    return df

def render_technical_radar(df, buy_price, tp_pct):
    if df.empty or len(df) < 2: return ""
    latest = df.iloc[-1]
    prev = df.iloc[-2]
    
    rsi = latest.get('RSI', 50)
    macd_hist = latest.get('MACD_Hist', 0)
    macd_hist_prev = prev.get('MACD_Hist', 0)
    atr = latest.get('ATR', 0)
    
    # RSI 判定
    rsi_color = "#ef5350" if rsi <= 30 else "#FFD700" if rsi <= 45 else "#888888"
    rsi_text = "🔥 超・売られすぎ" if rsi <= 30 else "⚡ 売られすぎ" if rsi <= 45 else "⚖️ 中立"
    if rsi >= 70: rsi_color = "#26a69a"; rsi_text = "⚠️ 買われすぎ (高値掴み警戒)"
    
    # MACD 判定
    if macd_hist > 0 and macd_hist_prev <= 0:
        macd_text = "🔥 ゴールデンクロス直後"
        macd_color = "#ef5350"
    elif macd_hist > macd_hist_prev:
        macd_text = "📈 上昇モメンタム拡大中"
        macd_color = "#ef5350"
    elif macd_hist < 0 and macd_hist < macd_hist_prev:
        macd_text = "📉 下落圧力継続中 (底掘り警戒)"
        macd_color = "#26a69a"
    else:
        macd_text = "⚖️ モメンタム減衰"
        macd_color = "#888888"
        
    # ボラティリティ（ATR）から利確日数を逆算
    # ⚠️ 内部計算は小数のまま高精度に行う
    tp_yen = buy_price * (tp_pct / 100.0)
    days = int(tp_yen / atr) if atr > 0 else 99
    
    # ⚠️ UI表示時のみフォーマットで整数化（:.0f）。設定値(tp_pct)は小数第1位(:.1f)を残す
    html = f"""
    <div style="background: rgba(255, 255, 255, 0.05); padding: 0.8rem; border-radius: 4px; margin: 1rem 0; border-left: 4px solid #FFD700;">
        <div style="font-size: 13px; color: #aaa; margin-bottom: 6px;">📡 計器フライト（テクニカル・レーダー）</div>
        <div style="display: flex; flex-wrap: wrap; gap: 1.5rem;">
            <div>
                <span style="font-size: 12px; color: #888;">RSI (14日):</span>
                <strong style="color: {rsi_color}; font-size: 15px; margin-left: 4px;">{rsi:.0f}% ({rsi_text})</strong>
            </div>
            <div>
                <span style="font-size: 12px; color: #888;">MACD:</span>
                <strong style="color: {macd_color}; font-size: 15px; margin-left: 4px;">{macd_text}</strong>
            </div>
            <div>
                <span style="font-size: 12px; color: #888;">ボラティリティ:</span>
                <strong style="color: #bbb; font-size: 15px; margin-left: 4px;">1日平均 {atr:.0f}円 変動</strong>
                <span style="font-size: 12px; color: #888; margin-left: 4px;">(利確+{tp_pct:.1f}%までの理論日数: 約 {days} 営業日)</span>
            </div>
        </div>
    </div>
    """
    return html
# ==========================================

def draw_chart(df, targ_p, tp5=None, tp10=None, tp15=None, tp20=None):
    df = df.copy()
    df['MA5'] = df['AdjC'].rolling(window=5).mean()
    df['MA25'] = df['AdjC'].rolling(window=25).mean()
    df['MA75'] = df['AdjC'].rolling(window=75).mean()

    fig = go.Figure()
    fig.add_trace(go.Candlestick(
        x=df['Date'], open=df['AdjO'], high=df['AdjH'],
        low=df['AdjL'], close=df['AdjC'], name='株価',
        increasing_line_color='#ef5350', decreasing_line_color='#26a69a'
    ))

    fig.add_trace(go.Scatter(x=df['Date'], y=df['MA5'], mode='lines', name='5日線(短期)', line=dict(color='rgba(156, 39, 176, 0.7)', width=1.5)))      
    fig.add_trace(go.Scatter(x=df['Date'], y=df['MA25'], mode='lines', name='25日線(中期)', line=dict(color='rgba(33, 150, 243, 0.7)', width=1.5)))     
    fig.add_trace(go.Scatter(x=df['Date'], y=df['MA75'], mode='lines', name='75日線(長期)', line=dict(color='rgba(255, 152, 0, 0.7)', width=1.5)))      

    fig.add_trace(go.Scatter(x=df['Date'], y=[targ_p]*len(df), mode='lines', name='買値目標', line=dict(color='#FFD700', width=2, dash='dash')))
    if tp5 and tp10 and tp15 and tp20:
        fig.add_trace(go.Scatter(x=df['Date'], y=[tp5]*len(df), mode='lines', name='売値(5%)', line=dict(color='rgba(239, 83, 80, 0.4)', width=1, dash='dot')))
        fig.add_trace(go.Scatter(x=df['Date'], y=[tp10]*len(df), mode='lines', name='売値(10%)', line=dict(color='rgba(239, 83, 80, 0.6)', width=1, dash='dot')))
        fig.add_trace(go.Scatter(x=df['Date'], y=[tp15]*len(df), mode='lines', name='売値(15%)', line=dict(color='rgba(239, 83, 80, 0.8)', width=1.5, dash='dot')))
        fig.add_trace(go.Scatter(x=df['Date'], y=[tp20]*len(df), mode='lines', name='売値(20%)', line=dict(color='rgba(239, 83, 80, 1.0)', width=1.5, dash='dot')))
    
    last_date = df['Date'].max()
    start_date = last_date - timedelta(days=45) if len(df) > 30 else df['Date'].min()
    padding_days = timedelta(days=0.5)

    visible_df = df[(df['Date'] >= start_date) & (df['Date'] <= last_date)]
    if not visible_df.empty:
        y_max_vals = [visible_df['AdjH'].max(), targ_p, visible_df['MA5'].max(), visible_df['MA25'].max(), visible_df['MA75'].max()]
        y_min_vals = [visible_df['AdjL'].min(), targ_p * 0.85, visible_df['MA5'].min(), visible_df['MA25'].min(), visible_df['MA75'].min()] 
        if tp20: y_max_vals.append(tp20)
        
        y_max = max([v for v in y_max_vals if not pd.isna(v)])
        y_min = min([v for v in y_min_vals if not pd.isna(v)])
        
        margin = (y_max - y_min) * 0.05
        y_range = [y_min - margin, y_max + margin]
    else:
        y_range = None

    layout_args = dict(
        height=450, 
        margin=dict(l=10, r=60, t=20, b=40), 
        xaxis_rangeslider_visible=True,
        xaxis=dict(range=[start_date, last_date + padding_days], type="date"),
        yaxis=dict(tickformat=",.0f"),
        paper_bgcolor='rgba(0,0,0,0)', 
        plot_bgcolor='rgba(0,0,0,0)', 
        hovermode="x unified", 
        legend=dict(orientation="h", yanchor="top", y=-0.1, xanchor="center", x=0.5)
    )
    
    if y_range:
        layout_args['yaxis'].update(range=y_range, fixedrange=False)

    fig.update_layout(**layout_args)
    fig.update_layout(margin=dict(l=0, r=0, t=30, b=0))
    st.plotly_chart(fig, use_container_width=True)

# --- 【追加パッチ】計器フライト（テクニカル・レーダー） ---
def calc_technicals(df):
    df = df.copy()
    if len(df) < 16:   # ← 「16」に変更（これで28日や29日のデータでも計器がフル稼働します）
        df['RSI'] = 50; df['MACD_Hist'] = 0; df['ATR'] = 0
        return df
        
    # RSI (14日)
    delta = df['AdjC'].diff()
    gain = delta.where(delta > 0, 0)
    loss = -delta.where(delta < 0, 0)
    avg_gain = gain.ewm(alpha=1/14, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1/14, adjust=False).mean()
    rs = avg_gain / avg_loss
    df['RSI'] = 100 - (100 / (1 + rs))
    
    # MACD (12, 26, 9)
    ema_fast = df['AdjC'].ewm(span=12, adjust=False).mean()
    ema_slow = df['AdjC'].ewm(span=26, adjust=False).mean()
    macd = ema_fast - ema_slow
    signal = macd.ewm(span=9, adjust=False).mean()
    df['MACD_Hist'] = macd - signal
    
    # ATR（14日間の平均真の値幅：ボラティリティ）
    high_low = df['AdjH'] - df['AdjL']
    high_prev_c = (df['AdjH'] - df['AdjC'].shift(1)).abs()
    low_prev_c = (df['AdjL'] - df['AdjC'].shift(1)).abs()
    tr = pd.concat([high_low, high_prev_c, low_prev_c], axis=1).max(axis=1)
    df['ATR'] = tr.rolling(window=14).mean()
    
    return df

def render_technical_radar(df, buy_price, tp_pct):
    if df.empty or len(df) < 2: return ""
    latest = df.iloc[-1]
    prev = df.iloc[-2]
    
    rsi = latest.get('RSI', 50)
    macd_hist = latest.get('MACD_Hist', 0)
    macd_hist_prev = prev.get('MACD_Hist', 0)
    atr = latest.get('ATR', 0)
    
    # RSI 判定
    rsi_color = "#ef5350" if rsi <= 30 else "#FFD700" if rsi <= 45 else "#888888"
    rsi_text = "🔥 超・売られすぎ" if rsi <= 30 else "⚡ 売られすぎ" if rsi <= 45 else "⚖️ 中立"
    if rsi >= 70: rsi_color = "#26a69a"; rsi_text = "⚠️ 買われすぎ (高値掴み警戒)"
    
    # MACD 判定
    if macd_hist > 0 and macd_hist_prev <= 0:
        macd_text = "🔥 ゴールデンクロス直後"
        macd_color = "#ef5350"
    elif macd_hist > macd_hist_prev:
        macd_text = "📈 上昇モメンタム拡大中"
        macd_color = "#ef5350"
    elif macd_hist < 0 and macd_hist < macd_hist_prev:
        macd_text = "📉 下落圧力継続中 (底掘り警戒)"
        macd_color = "#26a69a"
    else:
        macd_text = "📉 モメンタム減衰"
        macd_color = "#888888"
        
    # ボラティリティ（ATR）から利確日数を逆算
    tp_yen = buy_price * (tp_pct / 100.0)
    days = int(tp_yen / atr) if atr > 0 else 99
    
    html = f"""
    <div style="background: rgba(255, 255, 255, 0.05); padding: 0.8rem; border-radius: 4px; margin: 1rem 0; border-left: 4px solid #FFD700;">
        <div style="font-size: 13px; color: #aaa; margin-bottom: 6px;">📡 計器フライト（テクニカル・レーダー）</div>
        <div style="display: flex; flex-wrap: wrap; gap: 1.5rem;">
            <div>
                <span style="font-size: 12px; color: #888;">RSI (14日):</span>
                <strong style="color: {rsi_color}; font-size: 15px; margin-left: 4px;">{rsi:.1f}% ({rsi_text})</strong>
            </div>
            <div>
                <span style="font-size: 12px; color: #888;">MACD:</span>
                <strong style="color: {macd_color}; font-size: 15px; margin-left: 4px;">{macd_text}</strong>
            </div>
            <div>
                <span style="font-size: 12px; color: #888;">ボラティリティ:</span>
                <strong style="color: #bbb; font-size: 15px; margin-left: 4px;">1日平均 {atr:.1f}円 変動</strong>
                <span style="font-size: 12px; color: #888; margin-left: 4px;">(利確+{tp_pct}%までの理論日数: 約 {days} 営業日)</span>
            </div>
        </div>
    </div>
    """
    return html
# -------------------------------------------------------------

# ==========================================
# 4. UI構築（デュアル・プリセット機構搭載）
# ==========================================
if 'preset_target' not in st.session_state: st.session_state.preset_target = "🚀 中小型株 (50%押し・標準)"
if 'sidebar_tactics' not in st.session_state: st.session_state.sidebar_tactics = "⚖️ バランス (掟達成率 ＞ 到達度)"
if 'push_r' not in st.session_state: st.session_state.push_r = 50.0 
if 'limit_d' not in st.session_state: st.session_state.limit_d = 4
if 'bt_tp' not in st.session_state: st.session_state.bt_tp = 10
if 'bt_sl_i' not in st.session_state: st.session_state.bt_sl_i = 8
if 'bt_sl_c' not in st.session_state: st.session_state.bt_sl_c = 8
if 'bt_sell_d' not in st.session_state: st.session_state.bt_sell_d = 10
if 'bt_lot' not in st.session_state: st.session_state.bt_lot = 100

def apply_market_preset():
    # キャッシュクリア直後の「記憶喪失状態」でもエラーを出さないための安全装置（getメソッド）
    preset = st.session_state.get("preset_target", "🚀 中小型株 (50%押し・標準)")
    tactics = st.session_state.get("sidebar_tactics", "⚖️ バランス (掟達成率 ＞ 到達度)")
    
    if "大型株" in preset:
        st.session_state.push_r = 25.0 if "バランス" in tactics else 45.0
        st.session_state.bt_tp = 10
    elif "61.8%" in preset:
        st.session_state.push_r = 61.8
        st.session_state.bt_tp = 10
    else:
        st.session_state.push_r = 50.0
        st.session_state.bt_tp = 10
    
    st.session_state.bt_sl_i = 8
    st.session_state.bt_sl_c = 8
    st.session_state.limit_d = 4
    st.session_state.bt_sell_d = 10

st.sidebar.header("🎯 対象市場 (一括換装)")
st.sidebar.radio(
    "プリセット選択",
    [
        "🚀 中小型株 (50%押し・標準)", 
        "⚓ 中小型株 (61.8%押し・黄金比深海)", 
        "🏢 大型株 (25%押し・トレンド追従)"
    ],
    key="preset_target",
    on_change=apply_market_preset,
    help="中小型株(標準): 50%押し。中小型株(深海): パニック相場用の61.8%待ち伏せ。大型株: 25%押し。"
)

st.sidebar.header("🕹️ 戦術モード切替")
tactics_mode = st.sidebar.radio(
    "抽出・ソート優先度",
    ["⚖️ バランス (掟達成率 ＞ 到達度)", "⚔️ 攻め重視 (三川シグナル優先)", "🛡️ 守り重視 (鉄壁シグナル優先)"],
    key="sidebar_tactics",
    on_change=apply_market_preset,
    help="モードを切り替えた際も、現在の市場プリセット（黄金比等）へパラメーターが自動復元されます。"
)

st.sidebar.header("🔍 ピックアップルール")
c_f1_1, c_f1_2 = st.sidebar.columns(2)
f1_min = c_f1_1.number_input("① 下限(円)", value=200, step=100)
f1_max = c_f1_2.number_input("① 上限(円)", value=3000, step=100) 
f2_m30 = st.sidebar.number_input("② 1ヶ月暴騰上限(倍)", value=2.0, step=0.1)
f3_drop = st.sidebar.number_input("③ 半年〜1年下落除外(%)", value=-30, step=5)
f4_mlong = st.sidebar.number_input("④ 上げ切り除外(倍)", value=3.0, step=0.5)
f5_ipo = st.sidebar.checkbox("⑤ IPO除外(英字コード等)", value=True)
f6_risk = st.sidebar.checkbox("⑥ 疑義注記銘柄除外", value=True)

f7_ex_etf = st.sidebar.checkbox("⑦ ETF・REIT等を除外", value=True, help="マクロ連動型や不動産投信を弾きます")
f8_ex_bio = st.sidebar.checkbox("⑧ 医薬品(バイオ)を除外", value=True, help="テクニカルが効かない赤字バイオ株を弾きます")

c_f9_1, c_f9_2 = st.sidebar.columns(2)
f9_min14 = c_f9_1.number_input("⑨ 下限(倍)", value=1.3, step=0.1)
f9_max14 = c_f9_2.number_input("⑨ 上限(倍)", value=2.0, step=0.1)

current_sl = st.session_state.bt_sl_i
f10_ex_knife = st.sidebar.checkbox("⑩ 落ちるナイフ除外(暴落/連続下落)", value=True, help=f"単日で【-{current_sl}.0%】以上、または直近3日間で【-{int(current_sl * 1.5)}.0%】以上の連続暴落をしている銘柄を弾きます")

st.sidebar.header("🎯 買いルール")
push_r = st.sidebar.number_input("① 押し目(%)", step=0.1, format="%.1f", key="push_r")
limit_d = st.sidebar.number_input("② 買い期限(日)", step=1, key="limit_d")
bt_lot = st.sidebar.number_input("③ 仮想Lot(株数)", step=100, key="bt_lot", help="バックテスト用の購入株数")

st.sidebar.header("🛡️ 売りルール（鉄の掟）")
bt_tp = st.sidebar.number_input("① 利確目標 (+%)", step=1, key="bt_tp")
bt_sl_i = st.sidebar.number_input("② 損切/ザラ場 (-%)", step=1, key="bt_sl_i")
bt_sl_c = st.sidebar.number_input("③ 損切/終値 (-%)", step=1, key="bt_sl_c")
bt_sell_d = st.sidebar.number_input("④ 強制撤退/売り期限 (日)", step=1, key="bt_sell_d")

import streamlit.components.v1 as components

# --- 【システムUI拡張】トップへ帰還（全コンテナ強制スクロール版） ---
components.html(
    """
    <script>
    const parentDoc = window.parent.document;
    
    if (!parentDoc.getElementById('sniper-return-btn')) {
        const btn = parentDoc.createElement('button');
        btn.id = 'sniper-return-btn';
        btn.innerHTML = '🚁 司令部（トップ）へ帰還';
        
        // --- スタイリング ---
        btn.style.position = 'fixed';
        btn.style.bottom = '100px'; 
        btn.style.right = '30px';
        btn.style.backgroundColor = '#1e1e1e';
        btn.style.color = '#00e676';
        btn.style.border = '1px solid #00e676';
        btn.style.padding = '12px 20px';
        btn.style.borderRadius = '8px';
        btn.style.cursor = 'pointer';
        btn.style.fontWeight = 'bold';
        btn.style.zIndex = '2147483647';
        btn.style.boxShadow = '0 4px 6px rgba(0,0,0,0.5)';
        btn.style.transition = 'all 0.3s ease';
        
        btn.onmouseover = function() {
            btn.style.backgroundColor = '#00e676';
            btn.style.color = '#1e1e1e';
        };
        btn.onmouseout = function() {
            btn.style.backgroundColor = '#1e1e1e';
            btn.style.color = '#00e676';
        };
        
        // --- 絨毯爆撃型スクロールロジック ---
        btn.onclick = function() {
            // 1. 最上位のウィンドウをスクロール
            window.parent.scrollTo({top: 0, behavior: 'smooth'});
            
            // 2. 画面内のすべての要素を取得し、スクロールバーを持っているか判定
            const allElements = parentDoc.querySelectorAll('*');
            for (let i = 0; i < allElements.length; i++) {
                const el = allElements[i];
                // 要素がスクロール可能（中身がはみ出している）場合
                if (el.scrollHeight > el.clientHeight) {
                    // 強制的に一番上へ巻き上げる
                    el.scrollTo({top: 0, behavior: 'smooth'});
                }
            }
        };
        
        parentDoc.body.appendChild(btn);
    }
    </script>
    """,
    height=0,
    width=0
)
# -------------------------------------------------------------

# ==========================================
# メイン画面（5タブ構成）
# ==========================================

# ==========================================
# メイン画面（5タブ構成）
# ==========================================
# --- 戦術迎撃システム（Tactical Sniper System）UI定義 ---
tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs([
    "🌐 広域索敵レーダー", 
    "🎯 精密スコープ照準", 
    "⚙️ 戦術シミュレータ", 
    "🪤 展開中の罠・潜伏カウント", 
    "📁 事後任務報告 (AAR)",
    "🛸 高高度観測 (NO SHOOT)"
])
master_df = load_master()

with tab1:
    st.markdown('<h3 style="font-size: clamp(14px, 4.5vw, 24px); margin-bottom: 1rem;">🌐 ボスの「鉄の掟」全軍スキャン</h3>', unsafe_allow_html=True)
    run_scan = st.button(f"🚀 最新データで全軍スキャン開始 ({tactics_mode.split()[0]}モード)")

    if run_scan:
        with st.spinner("神速モードで相場データを並列取得中..."):
            raw = get_hist_data_cached()
        if not raw: st.error("データの取得に失敗しました。")
        else:
            with st.spinner("全4000銘柄に鉄の掟と波形認識を一括執行中..."):
                d_raw = pd.DataFrame(raw)
                df = clean_df(d_raw).dropna(subset=['AdjC', 'AdjH', 'AdjL']).sort_values(['Code', 'Date'])
                df_30 = df.groupby('Code').tail(30)
                
                max_date_all = df['Date'].max()
                cutoff_date_14 = max_date_all - timedelta(days=14)
                df_14 = df_30[df_30['Date'] >= cutoff_date_14]
                
                counts = df_14.groupby('Code').size()
                valid = counts[counts >= 5].index
                if valid.empty: st.warning("条件を満たすデータが存在しません。"); st.stop()
                
                df_14 = df_14[df_14['Code'].isin(valid)]
                df_30 = df_30[df_30['Code'].isin(valid)]
                df_past = df[~df.index.isin(df_30.index)]; df_past = df_past[df_past['Code'].isin(valid)]
                
                agg_14 = df_14.groupby('Code').agg(
                    lc=('AdjC', 'last'), 
                    prev_c=('AdjC', lambda x: x.iloc[-2] if len(x) > 1 else np.nan),
                    c_3days_ago=('AdjC', lambda x: x.iloc[-4] if len(x) > 3 else np.nan),
                    h14=('AdjH', 'max'),
                    l14=('AdjL', 'min') 
                )
                
                idx_max = df_14.groupby('Code')['AdjH'].idxmax()
                h_dates = df_14.loc[idx_max, ['Code', 'Date']].rename(columns={'Date': 'h_date'})
                df_14_m = df_14.merge(h_dates, on='Code')
                d_high = df_14_m[df_14_m['Date'] > df_14_m['h_date']].groupby('Code').size().rename('d_high')
                
                agg_30 = df_30.groupby('Code').agg(l30=('AdjL', 'min'))
                agg_p = df_past.groupby('Code').agg(omax=('AdjH', 'max'), omin=('AdjL', 'min'))
                
                sum_df = agg_14.join(d_high, how='left').fillna({'d_high': 0}).join(agg_30).join(agg_p).reset_index()
                
                ur = sum_df['h14'] - sum_df['l14']
                
                bt_primary = sum_df['h14'] - (ur * (push_r / 100.0))
                shift_ratio = 0.618 if push_r >= 40 else (push_r / 100.0 + 0.15)
                bt_secondary = sum_df['h14'] - (ur * shift_ratio)
                
                sum_df['is_bt_broken'] = sum_df['lc'] < bt_primary
                sum_df['bt'] = np.where(sum_df['is_bt_broken'], bt_secondary, bt_primary)
                
                dead_line = sum_df['h14'] - (ur * 0.618)
                sum_df = sum_df[sum_df['lc'] >= (dead_line * 0.98)]
                
                sum_df['tp5'] = sum_df['bt'] * 1.05; sum_df['tp10'] = sum_df['bt'] * 1.10; sum_df['tp15'] = sum_df['bt'] * 1.15; sum_df['tp20'] = sum_df['bt'] * 1.20

                denom = sum_df['h14'] - sum_df['bt']
                sum_df['reach_pct'] = np.where(denom > 0, (sum_df['h14'] - sum_df['lc']) / denom * 100, 0)
                sum_df['r14'] = np.where(sum_df['l14'] > 0, sum_df['h14'] / sum_df['l14'], 0)
                sum_df['r30'] = np.where(sum_df['l30'] > 0, sum_df['lc'] / sum_df['l30'], 0)
                sum_df['ldrop'] = np.where((sum_df['omax'].notna()) & (sum_df['omax'] > 0), ((sum_df['lc'] / sum_df['omax']) - 1) * 100, 0)
                sum_df['lrise'] = np.where((sum_df['omin'].notna()) & (sum_df['omin'] > 0), sum_df['lc'] / sum_df['omin'], 0)
                
                sum_df['daily_pct'] = np.where(sum_df['prev_c'] > 0, (sum_df['lc'] / sum_df['prev_c']) - 1, 0)
                sum_df['pct_3days'] = np.where(sum_df['c_3days_ago'] > 0, (sum_df['lc'] / sum_df['c_3days_ago']) - 1, 0)
                
                dt_s = df_14.groupby('Code').apply(check_double_top).rename('is_dt')
                hs_s = df_14.groupby('Code').apply(check_head_shoulders).rename('is_hs')
                db_s = df_14.groupby('Code').apply(check_double_bottom).rename('is_db')
                
                sakata_s = df_30.groupby('Code').apply(check_sakata_patterns).rename('sakata_signal')
                
                sum_df = sum_df.merge(dt_s, on='Code', how='left').merge(hs_s, on='Code', how='left').merge(db_s, on='Code', how='left').merge(sakata_s, on='Code', how='left')
                sum_df = sum_df.fillna({'is_dt': False, 'is_hs': False, 'is_db': False})
                
                sum_df['is_defense'] = (~sum_df['is_dt']) & (~sum_df['is_hs']) & (sum_df['lc'] <= (sum_df['l14'] * 1.03))
                
                if not master_df.empty: sum_df = pd.merge(sum_df, master_df, on='Code', how='left')
                
                if f7_ex_etf and 'Sector' in sum_df.columns:
                    sum_df = sum_df[sum_df['Sector'].notna()] 
                    sum_df = sum_df[sum_df['Sector'] != '-']
                    sum_df = sum_df[~sum_df['CompanyName'].astype(str).str.contains("ETF|投信|ブル|ベア|REIT|ﾘｰﾄ", na=False, flags=re.IGNORECASE)]
                
                if f8_ex_bio and 'Sector' in sum_df.columns:
                    sum_df = sum_df[sum_df['Sector'] != '医薬品']

                sum_df = sum_df[(sum_df['lc'] >= f1_min) & (sum_df['lc'] <= f1_max)]
                sum_df = sum_df[sum_df['r30'] <= f2_m30]
                sum_df = sum_df[sum_df['ldrop'] >= f3_drop]
                sum_df = sum_df[(sum_df['lrise'] <= f4_mlong) | (sum_df['lrise'] == 0)]
                
                if f5_ipo:
                    old_c = get_old_codes()
                    if old_c: sum_df = sum_df[sum_df['Code'].isin(old_c)]
                    sum_df = sum_df[~sum_df['Code'].astype(str).str.contains(r'[a-zA-Z]')]
                
                if f6_risk and 'CompanyName' in sum_df.columns:
                    sum_df = sum_df[~sum_df['CompanyName'].astype(str).str.contains("疑義|重要事象", na=False)]
                
                sum_df = sum_df[(~sum_df['is_dt']) & (~sum_df['is_hs'])]
                sum_df = sum_df[~sum_df['sakata_signal'].astype(str).str.contains("下落警戒", na=False)]
                
                sum_df = sum_df[(sum_df['r14'] >= f9_min14) & (sum_df['r14'] <= f9_max14)]
                sum_df = sum_df[sum_df['d_high'] <= limit_d]
                
                sum_df = sum_df[(sum_df['lc'] <= (sum_df['bt'] * 1.35)) & (sum_df['lc'] >= (sum_df['bt'] * 0.85))]
                
                if f10_ex_knife:
                    dynamic_sl_ratio = - (st.session_state.bt_sl_i / 100.0)
                    three_days_sl = dynamic_sl_ratio * 1.5
                    sum_df = sum_df[(sum_df['daily_pct'] >= dynamic_sl_ratio) & (sum_df['pct_3days'] >= three_days_sl)]
                
                sum_df['rule_pct'] = float('nan')
                
                if tactics_mode.startswith("⚔️"):
                    res = sum_df.sort_values(['is_db', 'reach_pct'], ascending=[False, False]).head(30)
                elif tactics_mode.startswith("🛡️"):
                    res = sum_df.sort_values(['is_defense', 'reach_pct'], ascending=[False, False]).head(30)
                else:
                    res = sum_df.sort_values('reach_pct', ascending=False).head(30)
                
            if res.empty: st.warning("現在の相場に、標的は存在しません。")
            else:
                st.success(f"🎯 スキャン完了: {len(res)} 銘柄クリア")
                
                st.markdown("#### 📋 コピペ用コード")
                if 'Code' in res.columns:
                    copy_codes = ",".join([str(c)[:4] for c in res['Code']])
                    st.code(copy_codes, language="text")

                for _, r in res.iterrows():
                    st.divider()
                    c = str(r['Code']); n = r['CompanyName'] if not pd.isna(r.get('CompanyName')) else f"銘柄 {c[:4]}"
                    
                    scale_val = str(r.get('Scale', ''))
                    if any(x in scale_val for x in ["Core30", "Large70", "Mid400"]):
                        badge = '<span style="background-color: #0d47a1; color: #ffffff; padding: 0.2rem 0.6rem; border-radius: 4px; font-size: 12px; display: inline-block;">🏢 大型/中型 (推奨: 25%押し)</span>'
                    else:
                        badge = '<span style="background-color: #b71c1c; color: #ffffff; padding: 0.2rem 0.6rem; border-radius: 4px; font-size: 12px; display: inline-block;">🚀 小型/新興 (推奨: 50%押し)</span>'
                    
                    st.markdown(f"""
                        <div style="margin-bottom: 0.8rem;">
                            <h3 style="font-size: clamp(16px, 5vw, 26px); font-weight: bold; margin: 0 0 0.3rem 0; word-wrap: break-word;">({c[:4]}) {n}</h3>
                            <div>{badge}</div>
                        </div>
                    """, unsafe_allow_html=True)
                    
                    if r.get('is_bt_broken', False):
                        st.error("⚠️ 【第一防衛線突破】想定以上の売り圧力を検知。買値目標を第二防衛線（黄金比等）へ自動シフトし、損切値を再設定しました。")
                    
                    if r['is_db']: st.success("🔥 【激熱(攻め)】三川（ダブルボトム）底打ち反転波形を検知！")
                    if r['is_defense']: st.info("🛡️ 【鉄壁(守り)】下値支持線(サポート)に極接近。損切りリスクが極小の安全圏です。")
                    
                    if pd.notna(r.get('sakata_signal')):
                        if "下落警戒" in str(r['sakata_signal']):
                            st.error(f"🚨 【波形警告・撤退推奨】{r['sakata_signal']}")
                        else:
                            st.success(f"🔥 【反転攻勢・激熱】{r['sakata_signal']}")
                            
                    # --- 【完全防衛型 UI描画ブロック】全軍スキャン用 ---
                    lc_val = int(r.get('lc', 0))
                    bt_val = int(r.get('bt', 0))
                    high_val = int(r.get('h14', lc_val))
                    low_val = int(r.get('l14', 0))
                    if low_val == 0:
                        bt_ratio = st.session_state.push_r / 100.0 if not r.get('is_bt_broken', False) else 0.618
                        ur_approx = (high_val - bt_val) / bt_ratio if bt_ratio > 0 else 0
                        low_val = int(high_val - ur_approx)
                    wave_len = high_val - low_val

                    sl5 = int(bt_val * 0.95); sl8 = int(bt_val * 0.92); sl15 = int(bt_val * 0.85)
                    tp20 = int(r.get('tp20', bt_val * 1.2)); tp15 = int(r.get('tp15', bt_val * 1.15))
                    tp10 = int(r.get('tp10', bt_val * 1.1)); tp5 = int(r.get('tp5', bt_val * 1.05))

                    daily_pct = r.get('daily_pct', 0)
                    if pd.isna(daily_pct): daily_pct = 0
                    daily_sign = "+" if daily_pct >= 0 else ""

                    sc0, sc0_1, sc0_2, sc1, sc2, sc3, sc4, sc5 = st.columns([0.8, 0.8, 0.8, 0.9, 1.1, 1.8, 0.7, 0.7])
                    
                    sc0.metric("直近高値", f"{high_val:,}円")
                    sc0_1.metric("直近安値", f"{low_val:,}円")
                    sc0_2.metric("上昇幅", f"{wave_len:,}円")
                    sc1.metric("最新終値", f"{lc_val:,}円", f"{daily_sign}{daily_pct*100:.1f}%", delta_color="inverse")
                    
                    html_buy = f"""
                    <div style="font-family: sans-serif; padding-top: 0.2rem;">
                        <div style="font-size: 14px; color: rgba(250, 250, 250, 0.6); padding-bottom: 0.1rem;">🎯 買値目標</div>
                        <div style="font-size: 1.8rem; font-weight: bold; color: #FFD700;">{bt_val:,}円</div>
                    </div>
                    """
                    sc2.markdown(html_buy, unsafe_allow_html=True)
                    
                    html_sell = f"""<div style="font-family: sans-serif; padding-top: 0.2rem;">
                        <div style="font-size: 14px; color: rgba(250, 250, 250, 0.6); padding-bottom: 0.1rem;">🎯 売値目標 ＆ 🛡️ 損切目安</div>
                        <div style="font-size: 16px;">
                            <span style="display: inline-block; width: 2.5em; color: #ef5350;">20%</span> <span style="color: #ef5350;">{tp20:,}円</span><br>
                            <span style="display: inline-block; width: 2.5em; color: #ef5350;">15%</span> <span style="color: #ef5350;">{tp15:,}円</span> <span style="color: rgba(250, 250, 250, 0.3); margin: 0 4px;">|</span> <span style="display: inline-block; width: 2.8em; color: #26a69a;">-5%</span> <span style="color: #26a69a;">{sl5:,}円</span><br>
                            <span style="display: inline-block; width: 2.5em; color: #ef5350;">10%</span> <span style="color: #ef5350;">{tp10:,}円</span> <span style="color: rgba(250, 250, 250, 0.3); margin: 0 4px;">|</span> <span style="display: inline-block; width: 2.8em; color: #26a69a;">-8%</span> <span style="color: #26a69a;">{sl8:,}円</span><br>
                            <span style="display: inline-block; width: 2.5em; color: #ef5350;">5%</span> <span style="color: #ef5350;">{tp5:,}円</span> <span style="color: rgba(250, 250, 250, 0.3); margin: 0 4px;">|</span> <span style="display: inline-block; width: 2.8em; color: #26a69a;">-15%</span> <span style="color: #26a69a;">{sl15:,}円</span>
                        </div>
                    </div>"""
                    sc3.markdown(html_sell, unsafe_allow_html=True)
                    
                    reach_val = r.get('reach_pct', float('nan'))
                    sc4.metric("到達度", f"{reach_val:.1f}%" if not pd.isna(reach_val) else "---")
                    
                    rule_val = r.get('rule_pct', float('nan'))
                    sc5.metric("掟達成率", f"{rule_val:.0f}%" if not pd.isna(rule_val) else "🔫")
                    
                    passed_info = f" ｜ 🛡️ 掟クリア: {r['passed']}/{r['total']} 条件" if 'passed' in r else ""
                    st.caption(f"🏢 {r.get('Market','不明')} ｜ 🏭 {r.get('Sector','不明')} ｜ ⏱️ 高値経過: {int(r.get('d_high', 0))}日{passed_info}")

                    # --- 【完全防衛版】過去勝率のリアルタイム表示 ---
                    bt_stats = calc_historical_win_rate(
                        c[:4], st.session_state.push_r, st.session_state.limit_d,
                        st.session_state.bt_tp, st.session_state.bt_sl_i, st.session_state.bt_sl_c,
                        st.session_state.bt_sell_d, tactics_mode
                    )
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
                    else:
                        st.markdown(f"""
                        <div style="background: rgba(255,255,255,0.02); padding: 0.5rem; border-radius: 4px; margin: 0.5rem 0; border: 1px dashed rgba(255,255,255,0.2);">
                            <span style="font-size: 12px; color: #666;">📊 過去2年の掟適合率:</span>
                            <span style="color: #666; font-size: 14px; margin-left: 8px;">該当取引なし（大暴落の履歴なし、またはデータ不足）</span>
                        </div>
                        """, unsafe_allow_html=True)
                    # -------------------------------------------------------------
                    
                    # -------------------------------------------------------------
                    # ⚠️ APIには必ず「5桁(c + "0")」または元データ通りの「c」を渡す
                    api_code = c if len(c) == 5 else c + "0"
                    
                    raw_s = get_single_data(api_code, 1)
                    if raw_s:
                        hist = clean_df(pd.DataFrame(raw_s))
                        hist = calc_technicals(hist) # 計器計算
                        st.markdown(render_technical_radar(hist, r['bt'], st.session_state.bt_tp), unsafe_allow_html=True)
                        draw_chart(hist, r['bt'], r['tp5'], r['tp10'], r['tp15'], r['tp20'])
                    else:
                        hist = df[df['Code'] == c].sort_values('Date').tail(30)
                        if not hist.empty: 
                            hist = calc_technicals(hist) # 計器計算
                            st.markdown(render_technical_radar(hist, r['bt'], st.session_state.bt_tp), unsafe_allow_html=True)
                            draw_chart(hist, r['bt'], r['tp5'], r['tp10'], r['tp15'], r['tp20'])
                    # -------------------------------------------------------------

with tab2:
    st.markdown('<h3 style="font-size: clamp(14px, 4.5vw, 24px); margin-bottom: 1rem;">🎯 局地戦（複数・個別スキャン）</h3>', unsafe_allow_html=True)
    st.caption("※指定された銘柄すべての押し目ラインを計算し、戦術モードに応じてソートします。")
    col_s1, col_s2 = st.columns([1, 2])

    T2_FILE = f"saved_t2_codes_{user_id}.txt"
    default_t2 = "7203\n2764"
    if os.path.exists(T2_FILE):
        with open(T2_FILE, "r", encoding="utf-8") as f:
            default_t2 = f.read()

    with col_s1:
        target_codes_str = st.text_area("標的コード（複数可）", value=default_t2, height=100)
        run_single = st.button(f"🔫 指定銘柄 一斉スキャン ({tactics_mode.split()[0]})")
    with col_s2: st.caption("左側の「戦術モード切替」の設定に従って、並び順がダイナミックに変化します。")

    if run_single and target_codes_str:
        with open(T2_FILE, "w", encoding="utf-8") as f:
            f.write(target_codes_str)
            
        t_codes = list(dict.fromkeys([c.upper() for c in re.findall(r'(?<![a-zA-Z0-9])[a-zA-Z0-9]{4}(?![a-zA-Z0-9])', target_codes_str)]))
        
        if not t_codes: st.warning("4桁の有効な銘柄コードが見つかりません。")
        else:
            with st.spinner(f"指定された {len(t_codes)} 銘柄の軌道と掟達成率を計算中..."):
                results = []; charts_data = {}
                for c in t_codes:
                    raw_single = get_single_data(c + "0", 1) 
                    if raw_single:
                        df_s = clean_df(pd.DataFrame(raw_single))
                        
                        if not df_s.empty:
                            max_date_s = df_s['Date'].max()
                            cutoff_date_s = max_date_s - timedelta(days=14)
                            df_14 = df_s[df_s['Date'] >= cutoff_date_s]
                            df_30 = df_s.tail(30)
                            
                            if not df_14.empty:
                                df_past = df_s[~df_s.index.isin(df_30.index)]
                                h14 = df_14['AdjH'].max(); l14 = df_14['AdjL'].min(); lc = df_s['AdjC'].iloc[-1]
                                
                                idxmax = df_14['AdjH'].idxmax(); h_date = df_14.loc[idxmax, 'Date']
                                d_high = len(df_14[df_14['Date'] > h_date])
                                l30 = df_30['AdjL'].min() if not df_30.empty else np.nan
                                omax = df_past['AdjH'].max() if not df_past.empty else np.nan
                                omin = df_past['AdjL'].min() if not df_past.empty else np.nan
                                
                                prev_c = df_s['AdjC'].iloc[-2] if len(df_s) >= 2 else np.nan
                                daily_pct = (lc / prev_c) - 1 if pd.notna(prev_c) and prev_c > 0 else 0
                                
                                if len(df_s) >= 4:
                                    c_3days_ago = df_s['AdjC'].iloc[-4]
                                    pct_3days = (lc / c_3days_ago) - 1 if c_3days_ago > 0 else 0
                                else:
                                    pct_3days = 0
                                
                                bt_primary = h14 - ((h14 - l14) * (push_r / 100.0))
                                shift_ratio_s = 0.618 if push_r >= 40 else (push_r / 100.0 + 0.15)
                                bt_secondary = h14 - ((h14 - l14) * shift_ratio_s)
                                
                                is_bt_broken = lc < bt_primary
                                bt_single = bt_secondary if is_bt_broken else bt_primary
                                
                                dead_line_s = h14 - ((h14 - l14) * 0.618)
                                is_trend_broken = lc < (dead_line_s * 0.98)
                                
                                tp5_s = bt_single * 1.05; tp10_s = bt_single * 1.10; tp15_s = bt_single * 1.15; tp20_s = bt_single * 1.20
                                
                                denom_s = h14 - bt_single
                                reach_s = ((h14 - lc) / denom_s * 100) if denom_s > 0 else 0
                                
                                r14 = h14 / l14 if l14 > 0 else 0
                                r30 = lc / l30 if pd.notna(l30) and l30 > 0 else 0
                                ldrop = ((lc / omax) - 1) * 100 if pd.notna(omax) and omax > 0 else 0
                                lrise = lc / omin if pd.notna(omin) and omin > 0 else 0
                                
                                is_dt = check_double_top(df_14)
                                is_hs = check_head_shoulders(df_14)
                                is_db = check_double_bottom(df_14)
                                is_defense = (not is_dt) and (not is_hs) and (lc <= (l14 * 1.03))
                                
                                sakata_signal = check_sakata_patterns(df_30)
                                
                                c_name = f"銘柄 {c}"; c_market = "不明"; c_sector = "不明"; c_scale = ""
                                if not master_df.empty:
                                    m_row = master_df[master_df['Code'] == c + "0"]
                                    if not m_row.empty:
                                        c_name = m_row.iloc[0]['CompanyName']; c_market = m_row.iloc[0]['Market']; c_sector = m_row.iloc[0]['Sector']; c_scale = m_row.iloc[0].get('Scale', '')
                                
                                flag_knife = False
                                if f10_ex_knife:
                                    dynamic_sl_ratio = - (st.session_state.bt_sl_i / 100.0)
                                    three_days_sl = dynamic_sl_ratio * 1.5
                                    if daily_pct < dynamic_sl_ratio or pct_3days < three_days_sl:
                                        flag_knife = True
                                
                                flag_etf = False
                                if f7_ex_etf:
                                    flag_etf = (c_sector == '不明') or (c_sector == '-') or bool(re.search("ETF|投信|ブル|ベア|REIT|ﾘｰﾄ", str(c_name), re.IGNORECASE))
                                    
                                flag_bio = False
                                if f8_ex_bio:
                                    flag_bio = (c_sector == '医薬品')
                                    
                                flag_ipo = False
                                if f5_ipo:
                                    old_c = get_old_codes()
                                    if (old_c and (c + "0") not in old_c) or re.search(r'[a-zA-Z]', c):
                                        flag_ipo = True
                                
                                score_list = [
                                    (lc >= f1_min) and (lc <= f1_max), r30 <= f2_m30, ldrop >= f3_drop,
                                    (lrise <= f4_mlong) or (lrise == 0),
                                    (f9_min14 <= r14 <= f9_max14), d_high <= limit_d, 
                                    (lc <= (bt_single * 1.35)) and (lc >= (bt_single * 0.85))
                                ]
                                score_list.append(not flag_ipo)
                                score_list.append(not flag_etf)
                                score_list.append(not flag_bio)
                                score_list.append(not flag_knife)
                                if f6_risk: score_list.append(not bool(re.search("疑義|重要事象", str(c_name))))
                                score_list.append(not is_dt and not is_hs)
                                
                                rule_pct = (sum(score_list) / len(score_list)) * 100

                                # --- 【コア改修】ソート前の事前トリアージ判定 ---
                                df_chart = calc_technicals(df_s) # 先に計器を計算
                                rsi_val = 50; macd_t = "不明"
                                if len(df_chart) >= 2:
                                    latest_c = df_chart.iloc[-1]
                                    prev_c = df_chart.iloc[-2]
                                    rsi_val = latest_c.get('RSI', 50)
                                    macd_h = latest_c.get('MACD_Hist', 0)
                                    macd_h_prev = prev_c.get('MACD_Hist', 0)

                                    if macd_h > 0 and macd_h_prev <= 0: macd_t = "GC直後"
                                    elif macd_h > macd_h_prev: macd_t = "上昇拡大"
                                    elif macd_h < 0 and macd_h < macd_h_prev: macd_t = "下落継続"
                                    else: macd_t = "減衰"

                                triage_rank = "C（条件外・監視）👁️"
                                triage_bg = "#616161"
                                triage_score = 1 # ソート用内部スコア (1点)
                                
                                if macd_t == "下落継続" or rsi_val >= 70:
                                    triage_rank = "圏外（手出し無用）🚫"
                                    triage_bg = "#d32f2f"
                                    triage_score = 0 # (0点)
                                elif macd_t == "GC直後" and rsi_val <= 50:
                                    triage_rank = "S（即時狙撃）🔥"
                                    triage_bg = "#2e7d32"
                                    triage_score = 4 # 最優先 (4点)
                                elif macd_t == "減衰" and rsi_val <= 30:
                                    triage_rank = "A（罠の設置）🪤"
                                    triage_bg = "#0288d1"
                                    triage_score = 3 # (3点)
                                elif macd_t == "上昇拡大" and 50 <= rsi_val <= 65:
                                    triage_rank = "B（順張り警戒）📈"
                                    triage_bg = "#ed6c02"
                                    triage_score = 2 # (2点)
                                # ------------------------------------------------

                                results.append({
                                    'Code': c, 'Name': c_name, 'Market': c_market, 'Sector': c_sector, 'Scale': c_scale, 
                                    'lc': lc, 'bt': bt_single, 
                                    'tp5': tp5_s, 'tp10': tp10_s, 'tp15': tp15_s, 'tp20': tp20_s, 
                                    'h14': h14, 'l14': l14, 'd_high': d_high,
                                    'reach_pct': reach_s, 'rule_pct': rule_pct, 'passed': sum(score_list), 
                                    'total': len(score_list), 'is_dt': is_dt, 'is_hs': is_hs, 'is_db': is_db, 
                                    'is_defense': is_defense, 'daily_pct': daily_pct,
                                    'pct_3days': pct_3days, 'is_bt_broken': is_bt_broken,
                                    'is_trend_broken': is_trend_broken, 
                                    'flag_knife': flag_knife, 'flag_etf': flag_etf, 'flag_bio': flag_bio, 'flag_ipo': flag_ipo,
                                    'sakata_signal': sakata_signal,
                                    'triage_score': triage_score, 'triage_rank': triage_rank, 'triage_bg': triage_bg # 追加
                                })
                                charts_data[c] = (df_chart, bt_single, tp5_s, tp10_s, tp15_s, tp20_s) # 計算済みのdfを保存
                
                if results:
                    res_df = pd.DataFrame(results)
                    
                    # --- 【コア改修】複合ソートの実行（スコア > 戦術 > 掟達成率 > 到達度） ---
                    if tactics_mode.startswith("⚔️"):
                        res_df = res_df.sort_values(['triage_score', 'is_db', 'rule_pct', 'reach_pct'], ascending=[False, False, False, False])
                    elif tactics_mode.startswith("🛡️"):
                        res_df = res_df.sort_values(['triage_score', 'is_defense', 'rule_pct', 'reach_pct'], ascending=[False, False, False, False])
                    else:
                        res_df = res_df.sort_values(['triage_score', 'rule_pct', 'reach_pct'], ascending=[False, False, False])
                    # ------------------------------------------------------------------

                    st.success(f"🎯 {len(res_df)} 銘柄の局地戦スキャン完了（モード: {tactics_mode.split()[0]}）")
                    for _, r in res_df.iterrows():
                        st.divider()
                        
                        c = str(r.get('Code', ''))
                        n = str(r.get('Name', ''))
                        
                        scale_val = str(r.get('Scale', ''))
                        if any(x in scale_val for x in ["Core30", "Large70", "Mid400"]):
                            badge = '<span style="background-color: #0d47a1; color: #ffffff; padding: 0.2rem 0.6rem; border-radius: 4px; font-size: 12px; display: inline-block;">🏢 大型/中型 (推奨: 25%押し)</span>'
                        else:
                            badge = '<span style="background-color: #b71c1c; color: #ffffff; padding: 0.2rem 0.6rem; border-radius: 4px; font-size: 12px; display: inline-block;">🚀 小型/新興 (推奨: 50%押し)</span>'
                        
                        # 判定済みのランクとカラーを取得
                        triage_badge = f'<span style="background-color: {r["triage_bg"]}; color: #ffffff; padding: 0.2rem 0.6rem; border-radius: 4px; font-size: 13px; display: inline-block; font-weight: bold; margin-left: 0.5rem;">🎯 優先度: {r["triage_rank"]}</span>'

                        st.markdown(f"""
                            <div style="margin-bottom: 0.8rem;">
                                <h3 style="font-size: clamp(16px, 5vw, 26px); font-weight: bold; margin: 0 0 0.3rem 0; word-wrap: break-word;">({c[:4]}) {n}</h3>
                                <div style="display: flex; flex-wrap: wrap; gap: 4px; align-items: center;">{badge}{triage_badge}</div>
                            </div>
                        """, unsafe_allow_html=True)
                                        
                        if r.get('is_trend_broken'):
                            st.error("💀 【トレンド崩壊】黄金比(61.8%)を完全に下抜けています。迎撃非推奨（後学・分析用データ）")
                        elif r.get('is_bt_broken'):
                            st.error("⚠️ 【第一防衛線突破】想定以上の売り圧力を検知。買値を第二防衛線（黄金比等）へ自動シフトしました。")

                        if r.get('flag_knife'): 
                            if r['daily_pct'] < - (st.session_state.bt_sl_i / 100.0):
                                st.error(f"🚨 【警告】損切設定({st.session_state.bt_sl_i}%)を上回る単日暴落({r['daily_pct']*100:.1f}%)を検知。落ちるナイフのため迎撃非推奨です。")
                            else:
                                st.error(f"🚨 【警告】直近3日間で継続的な大暴落({r['pct_3days']*100:.1f}%)を検知。サイレント・ナイフのため迎撃非推奨です。")
                                
                        if r.get('flag_etf'): 
                            st.error("🚨 【警告】この銘柄はETF/REIT等です。個別株のテクニカルは通用しません。")
                        if r.get('flag_bio'): 
                            st.error("🚨 【警告】この銘柄は医薬品（バイオ株）です。思惑だけで動く完全なギャンブルです。")
                        if r.get('flag_ipo'): 
                            st.error("🚨 【警告】この銘柄は上場1年未満のIPO・新興銘柄です。データ不足のため予測不能です。")
                        
                        if r['is_dt'] or r['is_hs']: st.error("🚨 【警告】相場転換の危険波形（三尊/Wトップ）を検知！ 撤退推奨。")
                        if r['is_db']: st.success("🔥 【激熱(攻め)】三川（ダブルボトム）底打ち反転波形を検知！")
                        if r['is_defense']: st.info("🛡️ 【鉄壁(守り)】下値支持線(サポート)に極接近。損切りリスクが極小の安全圏です。")
                        
                        if pd.notna(r.get('sakata_signal')):
                            if "下落警戒" in str(r['sakata_signal']):
                                st.error(f"🚨 【波形警告・撤退推奨】{r['sakata_signal']}")
                            else:
                                st.success(f"🔥 【反転攻勢・激熱】{r['sakata_signal']}")
                                
                        lc_val = int(r.get('lc', 0))
                        bt_val = int(r.get('bt', 0))
                        high_val = int(r.get('h14', lc_val))
                        low_val = int(r.get('l14', 0))
                        if low_val == 0:
                            bt_ratio = st.session_state.push_r / 100.0 if not r.get('is_bt_broken', False) else 0.618
                            ur_approx = (high_val - bt_val) / bt_ratio if bt_ratio > 0 else 0
                            low_val = int(high_val - ur_approx)
                        wave_len = high_val - low_val

                        sl5 = int(bt_val * 0.95); sl8 = int(bt_val * 0.92); sl15 = int(bt_val * 0.85)
                        tp20 = int(r.get('tp20', bt_val * 1.2)); tp15 = int(r.get('tp15', bt_val * 1.15))
                        tp10 = int(r.get('tp10', bt_val * 1.1)); tp5 = int(r.get('tp5', bt_val * 1.05))

                        daily_pct = r.get('daily_pct', 0)
                        if pd.isna(daily_pct): daily_pct = 0
                        daily_sign = "+" if daily_pct >= 0 else ""

                        sc0, sc0_1, sc0_2, sc1, sc2, sc3, sc4, sc5 = st.columns([0.8, 0.8, 0.8, 0.9, 1.1, 1.8, 0.7, 0.7])
                        
                        sc0.metric("直近高値", f"{high_val:,}円")
                        sc0_1.metric("直近安値", f"{low_val:,}円")
                        sc0_2.metric("上昇幅", f"{wave_len:,}円")
                        sc1.metric("最新終値", f"{lc_val:,}円", f"{daily_sign}{daily_pct*100:.1f}%", delta_color="inverse")
                        
                        html_buy = f"""
                        <div style="font-family: sans-serif; padding-top: 0.2rem;">
                            <div style="font-size: 14px; color: rgba(250, 250, 250, 0.6); padding-bottom: 0.1rem;">🎯 買値目標</div>
                            <div style="font-size: 1.8rem; font-weight: bold; color: #FFD700;">{bt_val:,}円</div>
                        </div>
                        """
                        sc2.markdown(html_buy, unsafe_allow_html=True)
                        
                        html_sell = f"""<div style="font-family: sans-serif; padding-top: 0.2rem;">
                            <div style="font-size: 14px; color: rgba(250, 250, 250, 0.6); padding-bottom: 0.1rem;">🎯 売値目標 ＆ 🛡️ 損切目安</div>
                            <div style="font-size: 16px;">
                                <span style="display: inline-block; width: 2.5em; color: #ef5350;">20%</span> <span style="color: #ef5350;">{tp20:,}円</span><br>
                                <span style="display: inline-block; width: 2.5em; color: #ef5350;">15%</span> <span style="color: #ef5350;">{tp15:,}円</span> <span style="color: rgba(250, 250, 250, 0.3); margin: 0 4px;">|</span> <span style="display: inline-block; width: 2.8em; color: #26a69a;">-5%</span> <span style="color: #26a69a;">{sl5:,}円</span><br>
                                <span style="display: inline-block; width: 2.5em; color: #ef5350;">10%</span> <span style="color: #ef5350;">{tp10:,}円</span> <span style="color: rgba(250, 250, 250, 0.3); margin: 0 4px;">|</span> <span style="display: inline-block; width: 2.8em; color: #26a69a;">-8%</span> <span style="color: #26a69a;">{sl8:,}円</span><br>
                                <span style="display: inline-block; width: 2.5em; color: #ef5350;">5%</span> <span style="color: #ef5350;">{tp5:,}円</span> <span style="color: rgba(250, 250, 250, 0.3); margin: 0 4px;">|</span> <span style="display: inline-block; width: 2.8em; color: #26a69a;">-15%</span> <span style="color: #26a69a;">{sl15:,}円</span>
                            </div>
                        </div>"""
                        sc3.markdown(html_sell, unsafe_allow_html=True)
                        
                        reach_val = r.get('reach_pct', float('nan'))
                        sc4.metric("到達度", f"{reach_val:.1f}%" if not pd.isna(reach_val) else "---")
                        
                        rule_val = r.get('rule_pct', float('nan'))
                        sc5.metric("掟達成率", f"{rule_val:.0f}%" if not pd.isna(rule_val) else "🔫")
                        
                        passed_info = f" ｜ 🛡️ 掟クリア: {r['passed']}/{r['total']} 条件" if 'passed' in r else ""
                        st.caption(f"🏢 {r.get('Market','不明')} ｜ 🏭 {r.get('Sector','不明')} ｜ ⏱️ 高値経過: {int(r.get('d_high', 0))}日{passed_info}")

                        bt_stats = calc_historical_win_rate(
                            c[:4], st.session_state.push_r, st.session_state.limit_d,
                            st.session_state.bt_tp, st.session_state.bt_sl_i, st.session_state.bt_sl_c,
                            st.session_state.bt_sell_d, tactics_mode
                        )
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
                        else:
                            st.markdown(f"""
                            <div style="background: rgba(255,255,255,0.02); padding: 0.5rem; border-radius: 4px; margin: 0.5rem 0; border: 1px dashed rgba(255,255,255,0.2);">
                                <span style="font-size: 12px; color: #666;">📊 過去2年の掟適合率:</span>
                                <span style="color: #666; font-size: 14px; margin-left: 8px;">該当取引なし（大暴落の履歴なし、またはデータ不足）</span>
                            </div>
                            """, unsafe_allow_html=True)
                        
                        # --- テクニカルレーダーとチャート描画 ---
                        df_chart, bt_chart, tp5_c, tp10_c, tp15_c, tp20_c = charts_data[r['Code']]
                        st.markdown(render_technical_radar(df_chart, bt_chart, st.session_state.bt_tp), unsafe_allow_html=True)
                        draw_chart(df_chart, bt_chart, tp5_c, tp10_c, tp15_c, tp20_c)
                        # -------------------------------------------------------------

with tab3:
    st.markdown('<h3 style="font-size: clamp(14px, 4.5vw, 24px); margin-bottom: 1rem;">📉 鉄の掟：一括バックテスト</h3>', unsafe_allow_html=True)
    col_1, col_2 = st.columns([2, 1])

    T3_FILE = f"saved_t3_codes_{user_id}.txt"
    default_t3 = "6614\n3997\n4935"
    if os.path.exists(T3_FILE):
        with open(T3_FILE, "r", encoding="utf-8") as f:
            default_t3 = f.read()

    with col_1: 
        bt_c_in = st.text_area("銘柄コード（複数可）", value=default_t3, height=100)
        run_bt = st.button("🔥 一括バックテスト")
        
    with col_2:
        st.caption("⚙️ パラメーター同期中")
        st.info("左サイドバーの「🎯 買いルール」「🛡️ 売りルール」の設定値を用いて、過去2年間のシミュレーションを実行します。")

    if run_bt and bt_c_in:
        with open(T3_FILE, "w", encoding="utf-8") as f:
            f.write(bt_c_in)
            
        t_codes = list(dict.fromkeys([c.upper() for c in re.findall(r'(?<![a-zA-Z0-9])[a-zA-Z0-9]{4}(?![a-zA-Z0-9])', bt_c_in)]))
        
        if not t_codes: st.warning("有効なコードが見つかりません。")
        else:
            all_t = []; b_bar = st.progress(0, "仮想売買中...")
            for idx, c in enumerate(t_codes):
                raw = get_single_data(c + "0", 2) # 期間を2年に統一
                if raw:
                    df = clean_df(pd.DataFrame(raw)).dropna(subset=['AdjO', 'AdjH', 'AdjL', 'AdjC']).reset_index(drop=True)
                    pos = None
                    for i in range(30, len(df)):
                        td = df.iloc[i]
                        if pos is None:
                            win_14 = df.iloc[i-14:i]
                            win_30 = df.iloc[i-30:i]
                            rh = win_14['AdjH'].max(); rl = win_14['AdjL'].min()
                            
                            if pd.isna(rh) or pd.isna(rl) or rl <= 0: continue
                            
                            idxmax = win_14['AdjH'].idxmax()
                            h_d = len(win_14[win_14['Date'] > win_14.loc[idxmax, 'Date']])
                            r14 = rh / rl
                            
                            # サイドバーの買い期限（st.session_state.limit_d）を参照
                            if (1.3 <= r14 <= 2.0) and (h_d <= st.session_state.limit_d):
                                is_dt = check_double_top(win_30)
                                is_hs = check_head_shoulders(win_30)
                                if is_dt or is_hs:
                                    continue 
                                
                                # サイドバーの戦術モード（tactics_mode）を参照
                                if "攻め" in tactics_mode:
                                    is_db = check_double_bottom(win_30)
                                    if is_db:
                                        exec_p = td['AdjO']
                                        pos = {'b_i': i, 'b_d': td['Date'], 'b_p': exec_p, 'h': rh}
                                else:
                                    # サイドバーの押し目率（st.session_state.push_r）を参照
                                    targ = rh - ((rh - rl) * (st.session_state.push_r / 100))
                                    if td['AdjL'] <= targ:
                                        exec_p = min(td['AdjO'], targ)
                                        pos = {'b_i': i, 'b_d': td['Date'], 'b_p': exec_p, 'h': rh}
                        else:
                            bp = round(pos['b_p'], 1); held = i - pos['b_i']; sp = 0; rsn = ""
                            
                            # サイドバーの利確・損切ルールを参照
                            sl_i = bp * (1 - (st.session_state.bt_sl_i / 100))
                            tp = bp * (1 + (st.session_state.bt_tp / 100))
                            sl_c = bp * (1 - (st.session_state.bt_sl_c / 100))
                            
                            if td['AdjL'] <= sl_i: sp = min(td['AdjO'], sl_i); rsn = f"損切(ザ場-{st.session_state.bt_sl_i}%)"
                            elif td['AdjH'] >= tp: sp = max(td['AdjO'], tp); rsn = f"利確(+{st.session_state.bt_tp}%)"
                            elif td['AdjC'] <= sl_c: sp = td['AdjC']; rsn = f"損切(終値-{st.session_state.bt_sl_c}%)"
                            elif held >= st.session_state.bt_sell_d: sp = td['AdjC']; rsn = f"時間切れ({st.session_state.bt_sell_d}日)"
                            
                            if rsn:
                                sp = round(sp, 1); p_pct = round(((sp / bp) - 1) * 100, 2); p_amt = int((sp - bp) * st.session_state.bt_lot)
                                all_t.append({'銘柄': c, '購入日': pos['b_d'].strftime('%Y-%m-%d'), '決済日': td['Date'].strftime('%Y-%m-%d'), '保有日数': held, '買値(円)': bp, '売値(円)': sp, '損益(%)': p_pct, '損益額(円)': p_amt, '決済理由': rsn})
                                pos = None
                b_bar.progress((idx + 1) / len(t_codes)); time.sleep(0.5)
            b_bar.empty(); st.success("シミュレーション完了")
            
            if not all_t: st.warning("シグナル点灯はありませんでした。")
            else:
                tdf = pd.DataFrame(all_t); tot = len(tdf); wins = len(tdf[tdf['損益額(円)'] > 0])
                n_prof = tdf['損益額(円)'].sum(); sprof = tdf[tdf['損益額(円)'] > 0]['損益額(円)'].sum(); sloss = abs(tdf[tdf['損益額(円)'] <= 0]['損益額(円)'].sum())
                pf = round(sprof / sloss, 2) if sloss > 0 else 'inf'
                
                st.markdown(f'<h3 style="font-size: clamp(16px, 5vw, 26px); font-weight: bold; word-wrap: break-word; margin-bottom: 1rem;">💰 総合利益額: {n_prof:,} 円</h3>', unsafe_allow_html=True)
                m1, m2, m3, m4 = st.columns(4)
                m1.metric("トレード回数", f"{tot} 回"); m2.metric("勝率", f"{round((wins/tot)*100,1)} %")
                m3.metric("平均損益額", f"{int(n_prof/tot):,} 円"); m4.metric("PF", f"{pf}")
                
                st.markdown("### 📜 詳細交戦記録（トレード履歴）")
                st.dataframe(tdf, use_container_width=True, hide_index=True)

with tab4:
    st.markdown('<h3 style="font-size: clamp(14px, 4.5vw, 24px); margin-bottom: 1rem;">⏳ IFD-OCO 10日ルール監視</h3>', unsafe_allow_html=True)
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
        
        for line in lines:
            if not line.strip(): continue
            parts = [p.strip() for p in line.split(',')]
            if len(parts) >= 2:
                c = parts[0]; date_str = parts[1]
                bp = parts[2] if len(parts) >= 3 else "---"
                
                try:
                    buy_date = datetime.strptime(date_str, "%Y-%m-%d")
                    # Numpyの機能で「土日を除外した営業日」を正確にカウント
                    days_elapsed = np.busday_count(buy_date.date(), today.date())
                    
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
                except:
                    st.error(f"🚨 フォーマットエラー: {line} (カンマ区切り、YYYY-MM-DD形式で入力してください)")
with tab5:
    st.markdown('<h3 style="font-size: clamp(14px, 4.5vw, 24px); margin-bottom: 1rem;">🗂️ 過去戦歴の解剖（純粋IFD-OCO検証）</h3>', unsafe_allow_html=True)
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
                            rsi_val = 50; macd_t = "---"; days_val = 99
                            
                            if raw_data:
                                hist = clean_df(pd.DataFrame(raw_data))
                                hist = calc_technicals(hist) 
                                
                                # エントリー時点の計器データ
                                buy_hist = hist[hist['Date'] <= bd]
                                if len(buy_hist) >= 2:
                                    latest = buy_hist.iloc[-1]
                                    prev = buy_hist.iloc[-2]
                                    rsi = latest.get('RSI', 50)
                                    macd_h = latest.get('MACD_Hist', 0)
                                    macd_h_prev = prev.get('MACD_Hist', 0)
                                    atr = latest.get('ATR', 0)
                                    
                                    if macd_h > 0 and macd_h_prev <= 0: macd_t = "GC直後"
                                    elif macd_h > macd_h_prev: macd_t = "上昇拡大"
                                    elif macd_h < 0 and macd_h < macd_h_prev: macd_t = "下落継続"
                                    else: macd_t = "減衰"
                                    
                                    rsi_val = int(rsi)
                                    tp_yen = bp * (sim_tp / 100.0)
                                    days_val = int(tp_yen / atr) if atr > 0 else 99
                                
                                # ⚠️ 買付日から未来に向かって「sim_days」日分だけを抽出
                                future_df = hist[hist['Date'] >= bd].sort_values('Date')
                                period_df = future_df.head(int(sim_days) + 1) # 買付日(0日目)を含むため+1
                                
                                if not period_df.empty:
                                    # 初期値は「期限切れ（最終日の終値）」に設定
                                    last_row = period_df.iloc[-1]
                                    sim_sell_price = last_row['AdjC']
                                    sim_sell_date = last_row['Date']
                                    rsn = f"⏳ 期限切れ手仕舞い ({len(period_df)-1}日目)"
                                    
                                    # 1日ずつ未来へ進み、IFD-OCOの網に引っかかるか判定
                                    for i, r in period_df.iterrows():
                                        if r['AdjH'] >= tp_val:
                                            sim_sell_price = tp_val
                                            sim_sell_date = r['Date']
                                            rsn = f"🎯 利確 (+{sim_tp}%)"
                                            break
                                        elif r['AdjL'] <= sl_val:
                                            # 窓開け下落も考慮し、始値と損切値の低い方を採用
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

# --- 🛸 Tab 6専用チャート（14日間の空中戦ズーム・スコープ） ---
def draw_chart_t6(df, targ_p, tp5, tp10, tp15):
    df = df.copy()
    df['MA5'] = df['AdjC'].rolling(window=5).mean()

    fig = go.Figure()
    fig.add_trace(go.Candlestick(
        x=df['Date'], open=df['AdjO'], high=df['AdjH'],
        low=df['AdjL'], close=df['AdjC'], name='株価',
        increasing_line_color='#ef5350', decreasing_line_color='#26a69a'
    ))

    # 5日線（命綱）のみを太く強調して描画
    fig.add_trace(go.Scatter(x=df['Date'], y=df['MA5'], mode='lines', name='5日線(命綱)', line=dict(color='rgba(156, 39, 176, 0.9)', width=2.5)))      

    # 架空の買値と上値シミュレーション
    fig.add_trace(go.Scatter(x=df['Date'], y=[targ_p]*len(df), mode='lines', name='現在値', line=dict(color='#FFD700', width=2, dash='dash')))
    fig.add_trace(go.Scatter(x=df['Date'], y=[tp5]*len(df), mode='lines', name='+5%', line=dict(color='rgba(239, 83, 80, 0.5)', width=1, dash='dot')))
    fig.add_trace(go.Scatter(x=df['Date'], y=[tp10]*len(df), mode='lines', name='+10%', line=dict(color='rgba(239, 83, 80, 0.7)', width=1.5, dash='dot')))
    fig.add_trace(go.Scatter(x=df['Date'], y=[tp15]*len(df), mode='lines', name='+15%', line=dict(color='rgba(239, 83, 80, 1.0)', width=1.5, dash='dot')))
    
    last_date = df['Date'].max()
    # ⚠️ ここで直近14営業日に強制ズームイン
    start_date = df['Date'].iloc[-14] if len(df) >= 14 else df['Date'].min()
    padding_days = timedelta(days=0.5)

    visible_df = df[(df['Date'] >= start_date) & (df['Date'] <= last_date)]
    if not visible_df.empty:
        y_max = max(visible_df['AdjH'].max(), tp15)
        y_min = min(visible_df['AdjL'].min(), visible_df['MA5'].min()) 
        margin = (y_max - y_min) * 0.05
        y_range = [y_min - margin, y_max + margin]
    else:
        y_range = None

    layout_args = dict(
        height=380, # 少し縦幅を縮めてコンパクトに
        margin=dict(l=10, r=60, t=20, b=40), 
        xaxis_rangeslider_visible=False, # 下の邪魔なスライダーを消去して完全フォーカス
        xaxis=dict(range=[start_date, last_date + padding_days], type="date"),
        yaxis=dict(tickformat=",.0f"),
        paper_bgcolor='rgba(0,0,0,0)', 
        plot_bgcolor='rgba(0,0,0,0)', 
        hovermode="x unified", 
        legend=dict(orientation="h", yanchor="top", y=-0.1, xanchor="center", x=0.5)
    )
    
    if y_range:
        layout_args['yaxis'].update(range=y_range, fixedrange=False)

    fig.update_layout(**layout_args)
    fig.update_layout(margin=dict(l=0, r=0, t=30, b=0))
    st.plotly_chart(fig, use_container_width=True)
# -------------------------------------------------------------

with tab6:
    st.markdown('<h3 style="font-size: clamp(14px, 4.5vw, 24px); margin-bottom: 1rem;">🛸 高高度観測モニター（ブレイクアウト・順張り探知）</h3>', unsafe_allow_html=True)
    st.warning("⚠️ 【発砲厳禁】このレーダーは「すでに空高く飛んでいるモメンタム銘柄」を追跡し、イナゴタワーの形成と墜落を安全圏から観察・学習するための研究用（R&D）レーダーです。実弾の装填は鉄の掟に対する反逆とみなします。")
    
    run_scan_t6 = st.button("🚀 観測機を発進させる（ブレイクアウト全軍スキャン）")
    
    if run_scan_t6:
        with st.spinner("成層圏の熱源（ブレイクアウト・高値更新銘柄）を探索中...（約10〜20秒）"):
            raw = get_hist_data_cached()
            if not raw:
                st.error("データの取得に失敗しました。")
            else:
                d_raw = pd.DataFrame(raw)
                df = clean_df(d_raw).dropna(subset=['AdjC', 'AdjH', 'AdjL']).sort_values(['Code', 'Date'])
                df_30 = df.groupby('Code').tail(30)
                
                # 事前フィルター（処理高速化のため、価格帯とデータ数で足切り）
                counts = df_30.groupby('Code').size()
                valid_counts = counts[counts >= 15].index
                df_30 = df_30[df_30['Code'].isin(valid_counts)]
                
                latest_prices = df_30.groupby('Code')['AdjC'].last()
                valid_price_codes = latest_prices[(latest_prices >= f1_min) & (latest_prices <= f1_max)].index
                df_30 = df_30[df_30['Code'].isin(valid_price_codes)]
                
                results_t6 = []
                
                # --- 🛸 観測レーダー（純粋プライスアクション版） ---
                results_t6 = []
                grouped = df_30.groupby('Code')
                
                for code, group in grouped:
                    # 計器関数を通さず、生のデータで移動平均線を計算（エラー回避）
                    df_calc = group.copy()
                    df_calc['MA5'] = df_calc['AdjC'].rolling(window=5).mean()
                    
                    latest = df_calc.iloc[-1]
                    prev = df_calc.iloc[-2]
                    
                    lc = latest['AdjC']
                    ma5 = latest['MA5']
                    
                    h14 = df_calc.tail(14)['AdjH'].max()
                    daily_pct = (lc / prev['AdjC']) - 1 if prev['AdjC'] > 0 else 0
                    
                    # 🚀 純粋なプライスアクション・ブレイクアウト判定
                    # 1. 5日線の上にある (lc > ma5)
                    # 2. 直近14日高値の「5%以内」にいる (0.95)
                    # 3. 本日「+3%以上」の急騰をしている（daily_pct >= 0.03）
                    
                    if (lc > ma5) and (lc >= h14 * 0.95) and (daily_pct >= 0.03):
                        c_name = "不明"; c_scale = ""; c_sector = "不明"
                        if not master_df.empty:
                            m_row = master_df[master_df['Code'] == code]
                            if not m_row.empty:
                                c_name = m_row.iloc[0]['CompanyName']
                                c_scale = m_row.iloc[0].get('Scale', '')
                                c_sector = m_row.iloc[0].get('Sector', '不明')
                                
                        # ETFや投信などのノイズを除外
                        if f7_ex_etf and (c_sector == '-' or bool(re.search("ETF|投信|ブル|ベア|REIT|ﾘｰﾄ", str(c_name), re.IGNORECASE))):
                            continue
                            
                        # 描画用に計器を計算（RSIなどは参考値として表示）
                        g_tech = calc_technicals(group.copy())
                        rsi = g_tech.iloc[-1].get('RSI', 50)
                        
                        results_t6.append({
                            'Code': code, 'Name': c_name, 'Scale': c_scale,
                            'lc': lc, 'MA5': ma5, 'h14': h14, 'RSI': rsi, 'daily_pct': daily_pct,
                            'df_chart': g_tech
                        })
                
                if not results_t6:
                    st.info("現在、成層圏（ブレイクアウト条件合致）を飛行中の機体は観測されませんでした。")
                else:
                    st.success(f"🛸 観測完了: {len(results_t6)} 機の熱源（ブレイクアウト）を捕捉しました。")
                    
                    # 本日の「上昇率（勢い）」が高い順にソートして表示
                    res_df_t6 = pd.DataFrame(results_t6).sort_values('daily_pct', ascending=False)
                    
                    for _, r in res_df_t6.iterrows():
                        st.divider()
                        c = str(r['Code']); n = str(r['Name'])
                        
                        st.markdown(f"""
                            <div style="margin-bottom: 0.8rem;">
                                <h3 style="font-size: clamp(16px, 5vw, 26px); font-weight: bold; margin: 0 0 0.3rem 0; color: #e0e0e0;">({c[:4]}) {n}</h3>
                                <span style="background-color: #616161; color: #ffffff; padding: 0.2rem 0.6rem; border-radius: 4px; font-size: 12px; display: inline-block;">🛸 観測対象（本日 +{r['daily_pct']*100:.1f}% 飛翔）</span>
                            </div>
                        """, unsafe_allow_html=True)
                        
                        sc1, sc2, sc3, sc4 = st.columns(4)
                        sc1.metric("最新終値", f"{int(r['lc']):,}円", f"+{r['daily_pct']*100:.1f}%")
                        sc2.metric("5日移動平均線", f"{int(r['MA5']):,}円", "支持線(割ると墜落)")
                        sc3.metric("直近14日高値", f"{int(r['h14']):,}円", "ブレイクライン")
                        sc4.metric("過熱度 (RSI)", f"{r['RSI']:.1f}%", "※参考値")
                        
                        st.markdown(render_technical_radar(r['df_chart'], r['lc'], 10), unsafe_allow_html=True)
                        draw_chart_t6(r['df_chart'], r['lc'], int(r['lc']*1.05), int(r['lc']*1.10), int(r['lc']*1.15))
                        
                        st.caption("【観測ポイント】紫色の線（5日線）に沿ってどこまで上昇を続けるか、またはいつ陰線を叩きつけて墜落するかを観察してください。")
