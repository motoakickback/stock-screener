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

# --- ⏱️ 19:00 完全自動パージ機構（第一防衛線） ---
from datetime import datetime, timedelta
import pytz

def check_and_auto_purge():
    jst = pytz.timezone('Asia/Tokyo')
    now = datetime.now(jst)
    
    # 状態管理キーが存在しなければ初期化
    if 'last_auto_purge_date' not in st.session_state:
        st.session_state.last_auto_purge_date = None

    # 本日の19時を回っているか判定
    if now.hour >= 19:
        today_str = now.strftime('%Y-%m-%d')
        # 今日、まだ自動パージを実行していなければ執行する
        if st.session_state.last_auto_purge_date != today_str:
            st.cache_data.clear() # APIキャッシュを全焼却
            
            # 各タブの保持データをリセット
            st.session_state.tab1_scan_results = None
            st.session_state.tab2_scan_results = None
            st.session_state.tab5_ifd_results = None
            
            st.session_state.last_auto_purge_date = today_str
            # ここでリロードはせず、この後の処理で最新データを取得させる

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
    
    // 🚨 【重要】過去のゾンビボタン（脳死状態の残骸）を発見次第、完全に破壊する
    const oldBtn = parentDoc.getElementById('sniper-return-btn');
    if (oldBtn) {
        oldBtn.remove();
    }

    // 新しい機体（ボタン）の生成と配備
    const btn = parentDoc.createElement('button');
    btn.id = 'sniper-return-btn';
    btn.innerHTML = '🚁 司令部へ帰還';
    btn.style.position = 'fixed'; btn.style.bottom = '100px'; btn.style.right = '30px';
    btn.style.backgroundColor = '#1e1e1e'; btn.style.color = '#00e676';
    btn.style.border = '1px solid #00e676'; btn.style.padding = '12px 20px';
    btn.style.borderRadius = '8px'; btn.style.cursor = 'pointer';
    btn.style.fontWeight = 'bold'; btn.style.zIndex = '2147483647';
    btn.style.boxShadow = '0 4px 6px rgba(0,0,0,0.5)';
    
    // トリガー処理（確実に機能するスクロール）
    btn.onclick = function() {
        // 1. 基本領域のスクロール
        window.parent.scrollTo({top: 0, behavior: 'smooth'});
        
        // 2. Streamlit内部コンテナのスクロール（フリーズ防止のため対象をdiv, main等に限定）
        const containers = parentDoc.querySelectorAll('div, main, section');
        for (let i = 0; i < containers.length; i++) {
            // スクロール可能な領域を見つけたらトップへ戻す
            if (containers[i].scrollHeight > containers[i].clientHeight) {
                containers[i].scrollTo({top: 0, behavior: 'smooth'});
            }
        }
    };
    
    // 画面へ出力
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

# --- 🔴 安全装置：マニュアル・オーバーライド ---
API_KEY = st.secrets.get("JQUANTS_API_KEY", "").strip()
headers = {"x-api-key": API_KEY}
BASE_URL = "https://api.jquants.com/v2"

# --- ⏱️ 19:00 完全自動パージ機構（第一防衛線） ---
import pytz
from datetime import datetime

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
        import pandas as pd
        tk_ni = yf.Ticker("^N225")
        # トレンドを視認するため過去3ヶ月分を取得
        hist_ni = tk_ni.history(period="3mo")
        if len(hist_ni) >= 2:
            lc_ni = hist_ni['Close'].iloc[-1]
            prev_ni = hist_ni['Close'].iloc[-2]
            diff_ni = lc_ni - prev_ni
            pct_ni = (diff_ni / prev_ni) * 100
            
            df_ni = hist_ni.reset_index()
            if 'Date' in df_ni.columns:
                df_ni['Date'] = pd.to_datetime(df_ni['Date']).dt.tz_localize(None)
                
            return {"nikkei": {"price": lc_ni, "diff": diff_ni, "pct": pct_ni, "df": df_ni}}
    except: return None

def render_macro_board():
    import plotly.graph_objects as go
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
            
            # 🚨 修正箇所：折れ線グラフ（Scatter / lines）に変更
            fig.add_trace(go.Scatter(
                x=df['Date'], y=df['Close'], mode='lines', name='日経平均',
                line=dict(color='#FFD700', width=2) # 視認性の高い主線
            ))
            fig.add_trace(go.Scatter(
                x=df['Date'], y=df['MA25'], mode='lines', name='25日線',
                line=dict(color='rgba(255, 255, 255, 0.4)', width=1, dash='dot') # 控えめな補助線
            ))
            
            fig.update_layout(
                height=160, margin=dict(l=10, r=20, t=10, b=10),
                xaxis_rangeslider_visible=False,
                paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)',
                showlegend=False,
                yaxis=dict(side="right", tickformat=",.0f")
            )
            st.plotly_chart(fig, use_container_width=True, config={'displayModeBar': False})
            
        st.markdown("<div style='margin-bottom: 1.5rem;'></div>", unsafe_allow_html=True)
    else:
        # 🚨 堅牢化パッチ：エラー時のサイレント消失を防ぎ、警告を明示する
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
    from datetime import datetime, timedelta
    
    # 基準時刻（JST）と判定用ウィンドウの設定
    today = datetime.utcnow() + timedelta(hours=9)
    today_date = today.date()
    # 14日後の境界線を設定（この日より先のイベントは無視する）
    max_warning_date = today_date + timedelta(days=14)

    # --- 1. 絶対防衛線（手動設定：14日前～当日まで表示） ---
    # 形式: "銘柄コード": "イベント当日(YYYY-MM-DD)"
    critical_mines = {
        "8835": "2026-03-30", # 権利落ち
        "3137": "2026-03-27", # 個別材料
        "4167": "2026-03-27",
        "4031": "2026-03-27",
        "2195": "2026-03-27",
        "4379": "2026-03-27",
    }

    if c in critical_mines:
        try:
            event_date = datetime.strptime(critical_mines[c], "%Y-%m-%d").date()
            # 判定：今日が「イベント14日前以降」かつ「イベント当日まで」
            if (event_date - timedelta(days=14)) <= today_date <= event_date:
                alerts.append(f"💣 【地雷警戒】危険イベント接近中（{critical_mines[c]}）")
        except: pass

    if not event_data:
        return alerts

    # --- 2. APIデータ（配当：14日前～当日まで表示） ---
    for item in event_data.get("dividend", []):
        d_str = str(item.get("RecordDate", ""))[:10]
        if d_str:
            try:
                target_date = datetime.strptime(d_str, "%Y-%m-%d").date()
                if today_date <= target_date <= max_warning_date:
                    alerts.append(f"💣 【地雷警戒】配当権利落ち日が接近中 ({d_str})")
                    break
            except: pass

    # --- 3. APIデータ（決算：14日前～当日まで表示） ---
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

@st.cache_data(ttl=3600, show_spinner=False)
def get_single_data(code, yrs=3):
    base = datetime.utcnow() + timedelta(hours=9)
    f_d = (base - timedelta(days=365*yrs)).strftime('%Y%m%d')
    t_d = base.strftime('%Y%m%d')
    
    result = {"bars": [], "events": {"dividend": [], "earnings": []}}
    c = str(code)[:4]
    
    try:
        # 🚨 パッチ1：J-Quants APIの仕様に合わせ、確実に5桁(末尾0等)でリクエストする
        api_code = str(code) if len(str(code)) >= 5 else str(code) + "0"

        # 1. 既存の株価取得
        # 【修正】 code={c} を code={api_code} に変更して5桁でリクエスト
        r_bars = requests.get(f"{BASE_URL}/equities/bars/daily?code={api_code}&from={f_d}&to={t_d}", headers=headers, timeout=15)
        if r_bars.status_code == 200:
            result["bars"] = r_bars.json().get("data", [])
        
        # 2. 配当情報の取得
        # 【念のため修正】 こちらも code={api_code} に統一し、エラーの余地を完全に排除
        r_div = requests.get(f"https://api.jquants.com/v2/fins/dividend?code={api_code}", headers=headers, timeout=10)
        if r_div.status_code == 200:
            result["events"]["dividend"] = r_div.json().get("data", [])

    except Exception as e:
        print(f"API Error: {e}")
        
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
        df['RSI'] = 50; df['MACD'] = 0; df['MACD_Signal'] = 0; df['MACD_Hist'] = 0; df['ATR'] = 0; df['MA5'] = df['AdjC']; df['MA25'] = df['AdjC']; df['MA75'] = df['AdjC']; return df
    
    # 🚨 防衛パッチ：計算前の生データの欠損（NaNやInf）を強制補間
    df = df.replace([np.inf, -np.inf], np.nan)
    df.fillna(method='ffill', inplace=True)
    df.fillna(0, inplace=True)

    delta = df['AdjC'].diff()
    gain = delta.where(delta > 0, 0)
    loss = -delta.where(delta < 0, 0)
    
    # RSIの計算（ゼロ割りやNaNを徹底排除）
    loss_ewm = loss.ewm(alpha=1/14, adjust=False).mean()
    loss_ewm = loss_ewm.replace(0, 0.0001) # ゼロ割りを防ぐための微小値
    rs = gain.ewm(alpha=1/14, adjust=False).mean() / loss_ewm
    df['RSI'] = 100 - (100 / (1 + rs))
    df['RSI'] = df['RSI'].fillna(50) # RSIのNaNは中立(50)として扱う
    
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
    
    # 🚨 最終防衛：計算終了後に残ったすべてのNaNを0で埋め尽くし、Plotlyのクラッシュを完全に防ぐ
    df.fillna(0, inplace=True)
    
    return df

# 🚨 置き換え対象：def get_triage_info(macd_hist, macd_hist_prev, rsi): ～ のブロック全て
def get_triage_info(macd_hist, macd_hist_prev, rsi, lc=0, bt=0, mode="待伏"):
    # 1. MACDの基本状態（共通処理）
    if macd_hist > 0 and macd_hist_prev <= 0:
        macd_t = "GC直後"
    elif macd_hist > macd_hist_prev:
        macd_t = "上昇拡大"
    elif macd_hist < 0 and macd_hist < macd_hist_prev:
        macd_t = "下落継続"
    else:
        macd_t = "減衰"

    # 2. 戦術別のSABC判定
    if mode == "強襲":
        # 【強襲（順張り）用ロジック】
        if macd_t == "下落継続" or rsi >= 75:
            return "圏外（手出し無用）🚫", "#d32f2f", 0, macd_t
        elif macd_t == "GC直後":
            if rsi <= 50: return "S（即時狙撃）🔥", "#2e7d32", 5, macd_t
            else: return "A（強襲追撃）⚡", "#ed6c02", 4, macd_t
        elif macd_t == "上昇拡大":
            if rsi <= 60: return "B（順張り警戒）📈", "#0288d1", 3, macd_t
            else: return "C（過熱警戒）👁️", "#616161", 2, macd_t
        else:
            return "C（条件外・監視）👁️", "#616161", 1, macd_t

    else:
        # 【待伏（逆張り）用ロジック】
        # 🚨 司令部要求：接近中(オレンジ)を 4.5点、罠(青)を 4.0点に設定
        if bt == 0 or lc == 0:
            return "C（計算不能）👁️", "#616161", 1, macd_t

        dist_pct = ((lc / bt) - 1) * 100 

        if dist_pct < -2.0:
            return "圏外（防衛線突破）💀", "#d32f2f", 0, macd_t
        elif dist_pct <= 2.0: # -2.0% ～ +2.0% (射程圏内)
            if rsi <= 45: 
                return "S（迎撃態勢）🔥", "#2e7d32", 5, macd_t
            else: 
                return "A（接近中）⚡", "#ed6c02", 4.5, macd_t 
        elif dist_pct <= 5.0: # +2.0% ～ +5.0% (準備段階)
            if rsi <= 50: 
                return "A（罠の設置）🪤", "#0288d1", 4.0, macd_t 
            else: 
                return "B（高高度）📈", "#0288d1", 3, macd_t
        else:
            return "C（射程外・監視）👁️", "#616161", 1, macd_t

# 565行目以降にあった重複した else ブロックは削除しました
    else:
        # 【待伏（逆張り）用ロジック】: 買値目標(bt)との距離とRSIを重視
        if bt == 0 or lc == 0:
            return "C（計算不能）👁️", "#616161", 1, macd_t

        dist_pct = ((lc / bt) - 1) * 100 # 目標値までの距離(%)

        if dist_pct < -2.0:
            return "圏外（防衛線突破）💀", "#d32f2f", 0, macd_t
        elif dist_pct <= 2.0: # -2.0% ～ +2.0% の交戦距離
            if rsi <= 45: return "S（迎撃態勢）🔥", "#2e7d32", 5, macd_t
            else: return "A（接近中）⚡", "#ed6c02", 4, macd_t
        elif dist_pct <= 5.0: # +2.0% ～ +5.0%
            if rsi <= 50: return "A（罠の設置）🪤", "#0288d1", 4, macd_t
            else: return "B（高高度）📈", "#0288d1", 3, macd_t
        else:
            return "C（射程外・監視）👁️", "#616161", 1, macd_t

def render_technical_radar(df, buy_price, tp_pct):
    if df.empty or len(df) < 2: return ""
    latest = df.iloc[-1]; prev = df.iloc[-2]
    rsi = latest.get('RSI', 50); macd_hist = latest.get('MACD_Hist', 0); macd_hist_prev = prev.get('MACD_Hist', 0); atr = latest.get('ATR', 0)
    rsi_color = "#ef5350" if rsi <= 30 else "#FFD700" if rsi <= 45 else "#888888"
    rsi_text = "🔥 超売られすぎ" if rsi <= 30 else "⚡ 売られすぎ" if rsi <= 45 else "⚖️ 中立"
    if rsi >= 70: rsi_color = "#26a69a"; rsi_text = "⚠️ 買われすぎ"

    _, _, _, macd_t = get_triage_info(macd_hist, macd_hist_prev, rsi)

    # 🚨 GC発動時を超絶目立たせる改修
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

# --- チャート描画エンジンの更新（ID重複エラー対策版） ---
def draw_chart(df, targ_p, tp5=None, tp10=None, tp15=None, tp20=None, chart_key=None):
    import plotly.graph_objects as go
    from datetime import timedelta
    
    df = df.copy()
    fig = go.Figure()
    
    # ローソク足
    fig.add_trace(go.Candlestick(
        x=df['Date'], open=df['AdjO'], high=df['AdjH'],
        low=df['AdjL'], close=df['AdjC'], name='株価',
        increasing_line_color='#ef5350', decreasing_line_color='#26a69a'
    ))

    # 移動平均線
    if 'MA5' in df.columns: fig.add_trace(go.Scatter(x=df['Date'], y=df['MA5'], mode='lines', name='5日', line=dict(color='rgba(156, 39, 176, 0.7)', width=1.5), connectgaps=True))
    if 'MA25' in df.columns: fig.add_trace(go.Scatter(x=df['Date'], y=df['MA25'], mode='lines', name='25日', line=dict(color='rgba(33, 150, 243, 0.7)', width=1.5), connectgaps=True))
    if 'MA75' in df.columns: fig.add_trace(go.Scatter(x=df['Date'], y=df['MA75'], mode='lines', name='75日', line=dict(color='rgba(255, 152, 0, 0.7)', width=1.5), connectgaps=True))

    # ターゲットライン
    fig.add_trace(go.Scatter(x=df['Date'], y=[targ_p]*len(df), mode='lines', name='買値目標', line=dict(color='#FFD700', width=2, dash='dash')))
    
    last_date = df['Date'].max()
    start_date = last_date - timedelta(days=45) if len(df) > 30 else df['Date'].min()
    
    fig.update_layout(
        height=450, margin=dict(l=0, r=60, t=30, b=40),
        xaxis_rangeslider_visible=True,
        xaxis=dict(range=[start_date, last_date + timedelta(days=0.5)], type="date"),
        yaxis=dict(tickformat=",.0f", side="right"),
        paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)',
        hovermode="x unified", legend=dict(orientation="h", yanchor="top", y=-0.1, xanchor="center", x=0.5)
    )
    
    # 🚨 修正の核心：固有の key を付与して重複エラーを防ぐ
    config = {'displayModeBar': True, 'displaylogo': False}
    st.plotly_chart(fig, use_container_width=True, config=config, key=chart_key)
    
# --- 🚨 復元パッチ：欠落していた2つのスナイパー機能 ---
@st.cache_data(ttl=86400, show_spinner=False)
def calc_historical_win_rate(c, push_r, buy_d, tp, sl_i, sl_c, sell_d, mode):
    raw = get_single_data(c + "0", 2)
    if not raw: return None
    # --- ここから差し替え ---
    if isinstance(raw, dict) and 'bars' in raw:
        temp_df = pd.json_normalize(raw['bars'])
    else:
        temp_df = pd.json_normalize(raw)

    rename_map = {}
    for col in temp_df.columns:
        c_up = col.upper()
        if c_up.endswith('ADJO') or c_up.endswith('OPEN') or c_up == 'O': rename_map[col] = 'AdjO'
        if c_up.endswith('ADJH') or c_up.endswith('HIGH') or c_up == 'H': rename_map[col] = 'AdjH'
        if c_up.endswith('ADJL') or c_up.endswith('LOW') or c_up == 'L':  rename_map[col] = 'AdjL'
        if c_up.endswith('ADJC') or c_up.endswith('CLOSE') or c_up == 'C': rename_map[col] = 'AdjC'

    temp_df = temp_df.rename(columns=rename_map)
    # 重複カラムの排除
    temp_df = temp_df.loc[:, ~temp_df.columns.duplicated()]
    
    target_cols = ['AdjO', 'AdjH', 'AdjL', 'AdjC']
    if all(col in temp_df.columns for col in target_cols):
        df = clean_df(temp_df).dropna(subset=target_cols).reset_index(drop=True)
    else:
        # データが破損している場合は空のデータフレームを生成し、後続ループを安全にスキップさせる
        df = pd.DataFrame(columns=target_cols)
    # --- ここまで差し替え ---
    if len(df) < 60: return None
    trades = []; pos = None
    for i in range(30, len(df)):
        td = df.iloc[i]
        if pos is None:
            win_14 = df.iloc[i-14:i]; win_30 = df.iloc[i-30:i]
            rh = win_14['AdjH'].max(); rl = win_14['AdjL'].min()
            if pd.isna(rh) or pd.isna(rl) or rl <= 0: continue
            h_d = len(win_14[win_14['Date'] > win_14.loc[win_14['AdjH'].idxmax(), 'Date']])
            if (1.3 <= rh/rl <= 2.0) and (h_d <= buy_d):
                if check_double_top(win_30) or check_head_shoulders(win_30): continue
                if "攻め" in mode:
                    if check_double_bottom(win_30): pos = {'b_i': i, 'b_p': td['AdjO']}
                else:
                    targ = rh - ((rh - rl) * (push_r / 100))
                    if td['AdjL'] <= targ: pos = {'b_i': i, 'b_p': min(td['AdjO'], targ)}
        else:
            bp = pos['b_p']; held = i - pos['b_i']; sp = 0
            if td['AdjL'] <= bp * (1 - (sl_i / 100)): sp = min(td['AdjO'], bp * (1 - (sl_i / 100)))
            elif td['AdjH'] >= bp * (1 + (tp / 100)): sp = max(td['AdjO'], bp * (1 + (tp / 100)))
            elif td['AdjC'] <= bp * (1 - (sl_c / 100)): sp = td['AdjC']
            elif held >= sell_d: sp = td['AdjC']
            if sp > 0:
                trades.append(sp - bp); pos = None
    if not trades: return None
    wins = len([t for t in trades if t > 0])
    return {'total': len(trades), 'win_rate': (wins / len(trades)) * 100, 'exp_val': sum(trades) / len(trades)}

# --- 4. サイドバー UI ---
if 'preset_target' not in st.session_state: st.session_state.preset_target = "🚀 中小型株 (50%押し・標準)"
if 'sidebar_tactics' not in st.session_state: st.session_state.sidebar_tactics = "⚖️ バランス (掟達成率 ＞ 到達度)"
if 'push_r' not in st.session_state: st.session_state.push_r = 50.0 

# 🚨 【修正】ここから下の行に「if not in」の防壁を追加し、強制リセットを無効化しました
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

# 🚨 【修正後】表の丸ごとコピペに対応する「自動抽出スナイパー」パッチ
import re
# 4桁の数字であり、かつ直後に「/」や「-」や「年」が続かないもの（日付の「2019」等を排除）だけを抽出
extracted_codes = re.findall(r'\b\d{4}\b(?!\s*[/年-])', gigi_input)
# 重複を排除してリスト化
gigi_mines_list = list(dict.fromkeys(extracted_codes))

# --- 🔴 安全装置：マニュアル・オーバーライド（第二防衛線） ---
st.sidebar.divider()
st.sidebar.markdown("### 🛠️ システム管理")
if st.sidebar.button("🔴 キャッシュ強制パージ (API遅延時用)", use_container_width=True, help="18時以降もデータが古い場合、このボタンで強制的にJ-Quantsへ再取得を要求します。"):
    st.cache_data.clear()
    st.session_state.tab1_scan_results = None
    st.session_state.tab2_scan_results = None
    st.session_state.tab5_ifd_results = None
    st.sidebar.success("全記憶を強制パージしました。最新データを再取得します。")
    st.rerun()

# ==========================================
# 5. タブ再構成（6タブ構成）
# ==========================================
tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs([
    "🌐 【待伏】広域レーダー", 
    "⚡ 【強襲】GC初動レーダー", 
    "🎯 【照準】精密スコープ", 
    "⚙️ 戦術シミュレータ", 
    "⛺ IFD潜伏カウント", 
    "📁 事後任務報告 (AAR)"
])
master_df = load_master()
tactics_mode = st.session_state.sidebar_tactics

with tab1:
    st.markdown('<h3 style="font-size: clamp(14px, 4.5vw, 24px); margin-bottom: 1rem;">🎯 【待伏】鉄の掟・半値押しレーダー</h3>', unsafe_allow_html=True)
    
    if 'tab1_scan_results' not in st.session_state:
        st.session_state.tab1_scan_results = None

    run_scan_t1 = st.button("🚀 最新データで待伏スキャン開始")
    exclude_etf_flag_t1 = st.sidebar.checkbox("ETF・REITを除外 (待伏)", value=True, key="tab1_etf_filter")

    # ==========================================
    # 💥 フェーズ1：純粋な半値押しスキャン（Tab 1専用）
    # ==========================================
    if run_scan_t1:
        st.toast("🟢 待伏トリガーを確認。索敵開始！", icon="🎯")
        with st.spinner("全銘柄から「鉄の掟（半値押し）」適合ターゲットを索敵中..."):
            raw = get_hist_data_cached()
            if not raw:
                st.error("データの取得に失敗しました。")
                st.session_state.tab1_scan_results = None
            else:
                df = clean_df(pd.DataFrame(raw)).dropna(subset=['AdjC', 'AdjH', 'AdjL']).sort_values(['Code', 'Date'])
                if exclude_etf_flag_t1 and 'master_df' in globals() and not master_df.empty:
                    invalid_mask = master_df['Market'].astype(str).str.contains('ETF|REIT', case=False, na=False) | \
                                   master_df['Sector'].astype(str).str.contains('ETF|REIT|投信', case=False, na=False) | \
                                   master_df['CompanyName'].astype(str).str.contains('ETF|REIT|ファンド|投資法人', case=False, na=False)
                    valid_codes = master_df[~invalid_mask]['Code'].unique()
                    df = df[df['Code'].isin(valid_codes)]

                results = []
                for code, group in df.groupby('Code'):
                    # 🚨 案A：API取得仕様に合わせた足切り
                    if len(group) < 15: continue
                    
                    lc = group.iloc[-1]['AdjC']
                    if lc < 200: continue
                    
                    # 出来高の足切り
                    v_col = next((col for col in group.columns if col in ['AdjVo', 'Vo', 'AdjVo_x', 'AdjVo_y']), None)
                    avg_vol = int(pd.to_numeric(group[v_col].astype(str).str.replace(',', ''), errors='coerce').fillna(0).tail(5).mean()) if v_col else 0
                    if avg_vol < 10000: continue
                    
                    # 波形の計算（10営業日固定・鉄の掟フィルタ）
                    group_reset = group.reset_index(drop=True)
                    recent_4d = group_reset.tail(4)
                    high_idx = recent_4d['AdjH'].idxmax()
                    high_4d_val = recent_4d.loc[high_idx, 'AdjH']
                    
                    # 🚨 10営業日（2週間）の安値を正確に取得
                    start_idx = max(0, high_idx - 10)
                    window_10d = group_reset.iloc[start_idx : high_idx + 1]
                    low_10d_val = window_10d['AdjL'].min()

                    # 🚨 【鉄の掟 第九条】サイドバーの設定値（下限・上限）を反映
                    rise_ratio = high_4d_val / low_10d_val
                    if not (f9_min14 <= rise_ratio <= f9_max14):
                        continue

                    # 🚨 変数名を low_10d_val に統一して計算
                    wave_len = high_4d_val - low_10d_val
                    if wave_len <= 0: continue
                    
                    target_buy = high_4d_val - (wave_len / 2.0)
                    reach_rate = (target_buy / lc) * 100
                    
                    # テクニカル計算
                    g_tech = calc_technicals(group.copy())
                    rsi = g_tech.iloc[-1].get('RSI', 50)
                    
                    # 🚨 【修正：変数定義】ここで c_scale を含め、全てのマスター情報を定義します
                    c_name = f"銘柄 {code[:4]}"; c_market = "不明"; c_sector = "不明"; c_scale = "不明"
                    if not master_df.empty:
                        m_row = master_df[master_df['Code'] == code]
                        if not m_row.empty:
                            c_name = m_row.iloc[0]['CompanyName']
                            c_market = m_row.iloc[0]['Market']
                            c_sector = m_row.iloc[0].get('Sector', '不明')
                            c_scale = m_row.iloc[0].get('Scale', '不明') # ← これが漏れていました

                    # 🎯 トリアージ判定（SABC）
                    rank, bg, t_score, _ = get_triage_info(
                        g_tech.iloc[-1].get('MACD_Hist', 0), 
                        g_tech.iloc[-2].get('MACD_Hist', 0) if len(g_tech)>1 else 0, 
                        rsi, lc, target_buy, mode="待伏"
                    )

                    # 🚀 データの格納（変数名を最新の 10d 版に同期）
                    results.append({
                        'Code': code, 'Name': c_name, 'Sector': c_sector, 'Market': c_market,
                        'Scale': c_scale, 'lc': lc, 'RSI': rsi, 'avg_vol': avg_vol, 
                        'high_4d': high_4d_val, 'low_14d': low_10d_val, # ← ここを修正
                        'target_buy': target_buy, 'reach_rate': reach_rate, 
                        'triage_rank': rank, 'triage_bg': bg, 't_score': t_score
                    })
                        
                if not results:
                    st.warning("現在、掟を満たすターゲットは存在しません。")
                    st.session_state.tab1_scan_results = []
                else:
                    # 🚨 到達度とRSIの総合スコアでソートし、上位30件だけを抽出（UIの激重化を防ぐ）
                    sorted_results = sorted(results, key=lambda x: x['t_score'], reverse=True)
                    st.session_state.tab1_scan_results = sorted_results[:30]
                
                del raw, df, results
                import gc; gc.collect()

    # ==========================================
    # 🖼️ フェーズ2：UI描画（Tab 1専用）
    # ==========================================
    if st.session_state.tab1_scan_results:
        light_results = st.session_state.tab1_scan_results
        st.success(f"🎯 待伏ロックオン: {len(light_results)} 銘柄を確認。")
        
        # --- Tab 1（待伏）UI描画：高密度・完全版 ---
        # --- Tab 1（待伏）UI描画：ボスの「重装甲」完全復刻版 ---
        for r in light_results:
            st.divider()
            c = str(r.get('Code', '0000')); n = r.get('Name', f"銘柄 {c[:4]}")
            
            # 変数一括抽出（安全装置）
            target_buy_val = int(r.get('target_buy', 0))
            reach_val = r.get('reach_rate', 0)
            high_val = int(r.get('high_4d', 0))
            low_val = int(r.get('low_14d', 0))
            lc_val = int(r.get('lc', 0))
            avg_vol_val = int(r.get('avg_vol', 0))
            t_rank = r.get('triage_rank', '不明')
            t_bg = r.get('triage_bg', '#616161')
            scale_val = str(r.get('Scale', ''))
            
            # 🏢 規模・優先度バッジ（重装甲レイアウト）
            badge = '<span style="background-color: #0d47a1; color: #ffffff; padding: 0.2rem 0.6rem; border-radius: 4px; font-size: 12px; display: inline-block;">🏢 大型/中型</span>' if any(x in scale_val for x in ["Core30", "Large70", "Mid400"]) else '<span style="background-color: #b71c1c; color: #ffffff; padding: 0.2rem 0.6rem; border-radius: 4px; font-size: 12px; display: inline-block;">🚀 小型/新興</span>'
            triage_badge = f'<span style="background-color: {t_bg}; color: #ffffff; padding: 0.2rem 0.6rem; border-radius: 4px; font-size: 13px; display: inline-block; font-weight: bold; margin-left: 0.5rem;">🎯 優先度: {t_rank}</span>'

            st.markdown(f"""
                <div style="margin-bottom: 0.8rem;">
                    <h3 style="font-size: clamp(18px, 5vw, 28px); font-weight: bold; margin: 0 0 0.3rem 0;">({c[:4]}) {n}</h3>
                    <div style="display: flex; flex-wrap: wrap; gap: 6px; align-items: center;">
                        {badge}{triage_badge}
                        <span style="background-color: rgba(38, 166, 154, 0.15); border: 1px solid #26a69a; color: #26a69a; padding: 0.1rem 0.5rem; border-radius: 4px; font-size: 12px;">RSI: {r.get("RSI", 50):.1f}%</span>
                        <span style="background-color: rgba(255, 215, 0, 0.1); border: 1px solid #FFD700; color: #FFD700; padding: 0.1rem 0.5rem; border-radius: 4px; font-size: 12px;">到達度: {reach_val:.1f}%</span>
                    </div>
                </div>
            """, unsafe_allow_html=True)
            
            # 📊 メトリクスエリア：平均出来高を独立させて復活
            m_cols = st.columns([1, 1, 1, 1.2, 1.5])
            m_cols[0].metric("直近高値", f"{high_val:,}円")
            m_cols[1].metric("起点安値", f"{low_val:,}円")
            m_cols[2].metric("最新終値", f"{lc_val:,}円")
            # 🔥 復活：平均出来高
            m_cols[3].metric("平均出来高(5日)", f"{avg_vol_val:,}株")
            
            # 🎯 買値目標（右端に配置）
            html_buy = f"""
            <div style="background: rgba(255, 215, 0, 0.05); padding: 0.5rem; border-radius: 8px; border: 1px solid rgba(255, 215, 0, 0.2); text-align: center;">
                <div style="font-size: 13px; color: rgba(250, 250, 250, 0.6); margin-bottom: 2px;">🎯 半値押し 買値目標</div>
                <div style="font-size: 1.8rem; font-weight: bold; color: #FFD700;">{target_buy_val:,}<span style="font-size: 14px; margin-left:2px;">円</span></div>
            </div>
            """
            m_cols[4].markdown(html_buy, unsafe_allow_html=True)
            
            st.caption(f"🏢 {r.get('Market','不明')} ｜ 🏭 {r.get('Sector','不明')} ｜ ⏱️ 高値経過: {int(r.get('d_high', 0))}日")

            # 📈 チャート描画（固有キーを渡してエラーを完全封鎖）
            hist_chart = pd.DataFrame()
            api_code = c if len(c) == 5 else c + "0"
            raw_s = get_single_data(api_code, 1)
            
            if raw_s and "bars" in raw_s and len(raw_s["bars"]) > 0:
                temp_df = pd.DataFrame(raw_s["bars"])
                rename_map = {}
                for col in temp_df.columns:
                    c_up = col.upper()
                    if c_up.endswith('ADJO') or c_up.endswith('OPEN') or c_up == 'O': rename_map[col] = 'AdjO'
                    if c_up.endswith('ADJH') or c_up.endswith('HIGH') or c_up == 'H': rename_map[col] = 'AdjH'
                    if c_up.endswith('ADJL') or c_up.endswith('LOW') or c_up == 'L':  rename_map[col] = 'AdjL'
                    if c_up.endswith('ADJC') or c_up.endswith('CLOSE') or c_up == 'C': rename_map[col] = 'AdjC'
                dedup_df = temp_df.rename(columns=rename_map).loc[:, ~temp_df.rename(columns=rename_map).columns.duplicated()]
                hist_chart = calc_technicals(clean_df(dedup_df))
            
            if not hist_chart.empty:
                st.markdown(render_technical_radar(hist_chart, target_buy_val, st.session_state.bt_tp), unsafe_allow_html=True)
                # 🚨 chart_key に銘柄コードを渡して一意に識別させる
                draw_chart(hist_chart, target_buy_val, target_buy_val*1.05, target_buy_val*1.1, target_buy_val*1.15, target_buy_val*1.2, chart_key=f"chart_{c}")
                del hist_chart
        import gc; gc.collect()

with tab2:
    st.markdown('<h3 style="font-size: clamp(14px, 4.5vw, 24px); margin-bottom: 1rem;">⚡ 【強襲】GC初動レーダー</h3>', unsafe_allow_html=True)
    
    if 'tab2_scan_results' not in st.session_state:
        st.session_state.tab2_scan_results = None

    col_t2_1, col_t2_2 = st.columns(2)
    rsi_limit = col_t2_1.number_input("RSI上限（過熱感の足切り）", value=40, step=5)
    vol_limit = col_t2_2.number_input("最低出来高（5日平均）", value=10000, step=10000)
    
    run_scan_t2 = st.button("🚀 全軍GC初動スキャン開始", key="btn_assault_scan")
    exclude_ipo_flag = st.sidebar.checkbox("IPO銘柄を除外", value=True, key="tab2_ipo_filter")

    # ==========================================
    # 💥 フェーズ1：GC初動順張りスキャン（Tab 2専用）
    # ==========================================
    if run_scan_t2:
        st.toast("🟢 強襲トリガーを確認。索敵開始！", icon="🚀")
        with st.spinner("【Phase 1】全銘柄の波形から「GC初動候補」を抽出中..."):
            raw = get_hist_data_cached()
            if not raw:
                st.error("データの取得に失敗しました。")
            else:
                df = clean_df(pd.DataFrame(raw)).dropna(subset=['AdjC', 'AdjH', 'AdjL']).sort_values(['Code', 'Date'])
                results = []
                for code, group in df.groupby('Code'):
                    # 🚨 案A：API取得上限(32件)未満しかデータがない銘柄を「上場直後のIPO」とみなして弾く
                    if exclude_ipo_flag and len(group) < 31: continue
                    if len(group) < 15: continue
                    
                    lc = group.iloc[-1]['AdjC']
                    if lc < 200: continue
                    
                    v_col = next((col for col in group.columns if col in ['AdjVo', 'Vo', 'AdjVo_x', 'AdjVo_y']), None)
                    avg_vol = int(pd.to_numeric(group[v_col].astype(str).str.replace(',', ''), errors='coerce').fillna(0).tail(5).mean()) if v_col else 0
                    if avg_vol < vol_limit: continue
                    
                    g_tech = calc_technicals(group.copy())
                    if len(g_tech) < 2: continue
                    
                    latest = g_tech.iloc[-1]
                    prev = g_tech.iloc[-2]
                    rsi = latest.get('RSI', 50)
                    macd_hist = latest.get('MACD_Hist', 0)
                    prev_hist = prev.get('MACD_Hist', 0)
                    
                    if rsi > rsi_limit: continue
                    if not (prev_hist < 0 and macd_hist >= 0): continue # GC判定
                    
                    c_name = f"銘柄 {code[:4]}"; c_market = "不明"; c_sector = "不明"
                    if not master_df.empty:
                        m_row = master_df[master_df['Code'] == code]
                        if not m_row.empty:
                            c_name = m_row.iloc[0]['CompanyName']; c_market = m_row.iloc[0]['Market']; c_sector = m_row.iloc[0].get('Sector', '不明')

                    results.append({
                        'Code': code, 'Name': c_name, 'Sector': c_sector, 'Market': c_market,
                        'lc': lc, 'RSI': rsi, 'avg_vol': avg_vol
                    })
                        
                if not results:
                    st.warning("現在、GC初動条件を満たすターゲットは存在しません。")
                    st.session_state.tab2_scan_results = []
                else:
                    st.session_state.tab2_scan_results = sorted(results, key=lambda x: x['RSI']) # RSIが低い順
                
                del raw, df, results
                import gc; gc.collect()

    # ==========================================
    # 🖼️ フェーズ2：UI描画（Tab 2専用）
    # ==========================================
    if st.session_state.tab2_scan_results:
        light_results = st.session_state.tab2_scan_results
        st.success(f"⚡ 強襲ロックオン: GC初動 {len(light_results)} 銘柄を確認。")
        for r in light_results:
            st.divider()
            c = str(r.get('Code', '0000'))
            n = r.get('Name', f"銘柄 {c[:4]}")
            lc_val = r.get('lc', 0)
            rsi_val = r.get('RSI', 50)
            vol_val = r.get('avg_vol', 0)

            st.markdown(f"""
                <div style="margin-bottom: 0.8rem;">
                    <h3 style="font-size: clamp(16px, 5vw, 26px); font-weight: bold; margin: 0 0 0.3rem 0;">({c[:4]}) {n}</h3>
                </div>
            """, unsafe_allow_html=True)
            
            sc0, sc1, sc2, sc3 = st.columns([1, 1, 1, 1.5])
            sc0.metric("最新終値", f"{int(lc_val):,}円")
            sc1.metric("逆指値目安", f"{int(lc_val * 1.01):,}円")
            
            html_stats = f"""
            <div style="display: flex; flex-direction: column; gap: 8px;">
                <div style="background: rgba(38, 166, 154, 0.1); border-left: 3px solid #26a69a; padding: 4px 8px; border-radius: 4px;">
                    <span style="font-size: 12px; color: #aaa;">RSI (過熱感):</span> <strong style="font-size: 15px; color: #fff;">{rsi_val:.1f}%</strong>
                </div>
                <div style="background: rgba(255, 255, 255, 0.05); border-left: 3px solid #26a69a; padding: 4px 8px; border-radius: 4px;">
                    <span style="font-size: 12px; color: #aaa;">GC判定:</span> <strong style="font-size: 15px; color: #26a69a;">条件クリア</strong>
                </div>
                <div style="background: rgba(255, 215, 0, 0.1); border-left: 3px solid #FFD700; padding: 4px 8px; border-radius: 4px;">
                    <span style="font-size: 12px; color: #aaa;">出来高(5日):</span> <strong style="font-size: 15px; color: #fff;">{int(vol_val):,} 株</strong>
                </div>
            </div>
            """
            sc3.markdown(html_stats, unsafe_allow_html=True)
            st.caption(f"🏢 {r.get('Market','不明')} ｜ 🏭 {r.get('Sector','不明')}")
            
            # 🚨 修正完了: ここで確実に最新APIデータを取得してからチャートを描く
            hist_chart = pd.DataFrame()
            api_code = c if len(c) == 5 else c + "0"
            raw_s = get_single_data(api_code, 1)
            
            if raw_s and "bars" in raw_s and len(raw_s["bars"]) > 0:
                temp_df = pd.DataFrame(raw_s["bars"])
                rename_map = {}
                for col in temp_df.columns:
                    c_up = col.upper()
                    if c_up.endswith('ADJO') or c_up.endswith('OPEN') or c_up == 'O': rename_map[col] = 'AdjO'
                    if c_up.endswith('ADJH') or c_up.endswith('HIGH') or c_up == 'H': rename_map[col] = 'AdjH'
                    if c_up.endswith('ADJL') or c_up.endswith('LOW') or c_up == 'L':  rename_map[col] = 'AdjL'
                    if c_up.endswith('ADJC') or c_up.endswith('CLOSE') or c_up == 'C': rename_map[col] = 'AdjC'
                dedup_df = temp_df.rename(columns=rename_map).loc[:, ~temp_df.rename(columns=rename_map).columns.duplicated()]
                hist_chart = calc_technicals(clean_df(dedup_df))
            else:
                st.error(f"銘柄 {c[:4]} のチャートデータ取得に失敗しました。")
                
            if not hist_chart.empty:
                st.markdown(render_technical_radar(hist_chart, lc_val, lc_val * 1.1), unsafe_allow_html=True)
                draw_chart(hist_chart, lc_val, lc_val*1.05, lc_val*1.1, lc_val*1.15, lc_val*1.2)
                del hist_chart
        import gc; gc.collect()

    # ==========================================
    # 🖼️ フェーズ2：UI描画（Tab 1専用）
    # ==========================================
    if 'tab1_scan_results' in st.session_state and st.session_state.tab1_scan_results is not None:
        light_results = st.session_state.tab1_scan_results
        
        if not light_results:
            pass # 警告はPhase1で出力済み
        else:
            st.success(f"🎯 待伏ロックオン: 鉄の掟をクリアした【半値押しターゲット】 {len(light_results)} 銘柄を確認。")
            
            for r in light_results:
                st.divider()
                # 🚨 古いメモリが来ても絶対にクラッシュさせない防弾処理
                c = str(r.get('Code', '0000'))
                n = r.get('Name', r.get('CompanyName', f"銘柄 {c[:4]}"))
                
                # 安全なデータ抽出（古いデータの場合は0を代入して回避）
                reach_val = r.get('reach_rate', 0)
                high_val = r.get('high_4d', 0)
                low_val = r.get('low_14d', 0)
                lc_val = r.get('lc', 0)
                target_buy_val = r.get('target_buy', 0)
                
                if reach_val >= 100:
                    reach_badge = f'<span style="background-color: #2e7d32; color: #ffffff; padding: 0.2rem 0.6rem; border-radius: 4px; font-size: 13px; font-weight: bold;">🎯 到達率: {reach_val:.1f}% (射程内)</span>'
                elif reach_val > 0:
                    reach_badge = f'<span style="background-color: #f57c00; color: #ffffff; padding: 0.2rem 0.6rem; border-radius: 4px; font-size: 13px; font-weight: bold;">⏳ 到達率: {reach_val:.1f}% (接近中)</span>'
                else:
                    reach_badge = '<span style="background-color: #888888; color: #ffffff; padding: 0.2rem 0.6rem; border-radius: 4px; font-size: 13px; font-weight: bold;">⚠️ 旧データ（再スキャン推奨）</span>'

                st.markdown(f"""
                    <div style="margin-bottom: 0.8rem;">
                        <h3 style="font-size: clamp(16px, 5vw, 26px); font-weight: bold; margin: 0 0 0.3rem 0;">({c[:4]}) {n}</h3>
                        <div style="display: flex; flex-wrap: wrap; gap: 4px; align-items: center;">
                            {reach_badge}
                            <span style="background-color: rgba(255,255,255,0.1); color: #ccc; padding: 0.2rem 0.6rem; border-radius: 4px; font-size: 12px;">RSI: {r.get("RSI", 50):.1f}%</span>
                        </div>
                    </div>
                """, unsafe_allow_html=True)
                
                sc0, sc1, sc2, sc3 = st.columns([1, 1, 1, 1.5])
                sc0.metric("直近高値(4日以内)", f"{int(high_val):,}円")
                sc1.metric("起点安値(2週間)", f"{int(low_val):,}円")
                sc2.metric("最新終値", f"{int(lc_val):,}円")
                
                html_buy = f"""
                <div style="font-family: sans-serif; padding-top: 0.2rem;">
                    <div style="font-size: 14px; color: rgba(250, 250, 250, 0.6); padding-bottom: 0.1rem;">🎯 半値押し 買値目標</div>
                    <div style="font-size: 1.8rem; font-weight: bold; color: #FFD700;">{int(target_buy_val):,}円</div>
                </div>
                """
                sc3.markdown(html_buy, unsafe_allow_html=True)
                
                vol_val = r.get('avg_vol', 0)
                # 🚨 防弾仕様：古いメモリが来てもエラーで落とさず、代替データ(RSI)を入れる
                acc_rsi_val = r.get('accurate_rsi', r.get('RSI', 50))
                
                html_stats = f"""
                <div style="display: flex; flex-direction: column; gap: 8px; margin-top: 0.5rem;">
                    <div style="background: rgba(38, 166, 154, 0.1); border-left: 3px solid #26a69a; padding: 4px 8px; border-radius: 4px;">
                        <span style="font-size: 12px; color: #aaa;">RSI (過熱感):</span> <strong style="font-size: 15px; color: #fff;">{int(acc_rsi_val)}%</strong>
                    </div>
                    <div style="background: rgba(255, 255, 255, 0.05); border-left: 3px solid #26a69a; padding: 4px 8px; border-radius: 4px;">
                        <span style="font-size: 12px; color: #aaa;">GC判定:</span> <strong style="font-size: 15px; color: #26a69a;">条件クリア</strong>
                    </div>
                    <div style="background: rgba(255, 215, 0, 0.1); border-left: 3px solid #FFD700; padding: 4px 8px; border-radius: 4px;">
                        <span style="font-size: 12px; color: #aaa;">出来高(5日):</span> <strong style="font-size: 15px; color: #fff;">{vol_val:,} 株</strong>
                    </div>
                </div>
                """
                sc4.markdown(html_stats, unsafe_allow_html=True)
                
                st.caption(f"🏢 {r.get('Market','不明')} ｜ 🏭 {r.get('Sector','不明')}")
                
                # 🚨 チャート描画：過去の巨大データを引き回さず、キャッシュAPIから必要な時だけ瞬時に呼び出して描画する
                hist_chart = pd.DataFrame()
                api_code = c if len(c) == 5 else c + "0"
                raw_s = get_single_data(api_code, 1)
                
                if raw_s and "bars" in raw_s and len(raw_s["bars"]) > 0:
                    temp_df = pd.DataFrame(raw_s["bars"])
                    rename_map = {}
                    for col in temp_df.columns:
                        c_up = col.upper()
                        if c_up.endswith('ADJO') or c_up.endswith('OPEN') or c_up == 'O': rename_map[col] = 'AdjO'
                        if c_up.endswith('ADJH') or c_up.endswith('HIGH') or c_up == 'H': rename_map[col] = 'AdjH'
                        if c_up.endswith('ADJL') or c_up.endswith('LOW') or c_up == 'L':  rename_map[col] = 'AdjL'
                        if c_up.endswith('ADJC') or c_up.endswith('CLOSE') or c_up == 'C': rename_map[col] = 'AdjC'
                    renamed_df = temp_df.rename(columns=rename_map)
                    dedup_df = renamed_df.loc[:, ~renamed_df.columns.duplicated()]
                    hist_chart = clean_df(dedup_df)
                else:
                    st.error(f"銘柄 {c[:4]} の最新チャートデータがAPIから取得できませんでした。")
                    
                if not hist_chart.empty:
                    from datetime import timedelta
                    cutoff_chart = hist_chart['Date'].max() - timedelta(days=60)
                    df_chart_filtered = hist_chart[hist_chart['Date'] >= cutoff_chart]
                    
                    df_chart_filtered = calc_technicals(df_chart_filtered)
                    st.markdown(render_technical_radar(df_chart_filtered, bt_val, st.session_state.bt_tp), unsafe_allow_html=True)
                    
                    tp5_val  = int(r.get('tp5', bt_val * 1.05))
                    tp10_val = int(r.get('tp10', bt_val * 1.10))
                    tp15_val = int(r.get('tp15', bt_val * 1.15))
                    tp20_val = int(r.get('tp20', bt_val * 1.20))

                    draw_chart(df_chart_filtered, bt_val, tp5_val, tp10_val, tp15_val, tp20_val)
                    
                    # 🚨 描画済みの重いオブジェクトは速やかに破壊し、メモリのオーバーフローを防ぐ
                    del hist_chart, df_chart_filtered
                    
                bt_stats = calc_historical_win_rate(c[:4], st.session_state.push_r, st.session_state.limit_d, st.session_state.bt_tp, st.session_state.bt_sl_i, st.session_state.bt_sl_c, st.session_state.bt_sell_d, tactics_mode)
                
                if bt_stats and bt_stats['total'] > 0:
                    wr_color = "#ef5350" if bt_stats['win_rate'] >= 60 else "#FFD700" if bt_stats['win_rate'] >= 50 else "#888888"
                    st.markdown(f'<div style="background: rgba(255,255,255,0.05); padding: 0.5rem; border-radius: 4px; margin: 0.5rem 0;"><span style="font-size: 12px; color: #aaa;">📊 過去2年の掟適合率 ({bt_stats["total"]}戦):</span><strong style="color: {wr_color}; font-size: 16px; margin-left: 8px;">勝率 {bt_stats["win_rate"]:.1f}%</strong><span style="font-size: 12px; color: #aaa; margin-left: 12px;">1株期待値:</span><strong style="color: {"#ef5350" if bt_stats["exp_val"] > 0 else "#26a69a"}; font-size: 16px; margin-left: 8px;">{bt_stats["exp_val"]:+.1f}円</strong></div>', unsafe_allow_html=True)
                else:
                    st.markdown('<div style="background: rgba(255,255,255,0.02); padding: 0.5rem; border-radius: 4px; margin: 0.5rem 0; border: 1px dashed rgba(255,255,255,0.2);"><span style="font-size: 12px; color: #666;">📊 過去2年の掟適合率:</span><span style="color: #666; font-size: 14px; margin-left: 8px;">該当取引なし（データ不足）</span></div>', unsafe_allow_html=True)

    import gc
    gc.collect()  # 処理済みの不要なメモリを強制排出
                    
with tab3:
    st.markdown('<h3 style="font-size: clamp(14px, 4.5vw, 24px); margin-bottom: 1rem;">🎯 【照準】精密スコープ（個別銘柄・深堀りスキャン）</h3>', unsafe_allow_html=True)
    st.caption("※気になっている銘柄や、レーダーで抽出した銘柄のコードを入力し、現在のテクニカル状態と迎撃ラインを精密に解析します。")
    
    col_s1, col_s2 = st.columns([1, 2])
    T3_SCOPE_FILE = f"saved_t3_scope_{user_id}.txt"
    default_scope = "6614\n4427"
    if os.path.exists(T3_SCOPE_FILE):
        with open(T3_SCOPE_FILE, "r", encoding="utf-8") as f:
            default_scope = f.read()
            
    with col_s1:
        target_codes_str = st.text_area("標的コード（複数可、改行区切り）", value=default_scope, height=100)
        run_scope = st.button("🔫 精密スキャン実行", use_container_width=True)
        
    with col_s2:
        st.markdown("#### 🔍 解析対象データ")
        st.caption("・ボスの「鉄の掟」9項目に基づく押し目ラインと適合度\n・トレンド崩壊、落ちるナイフ、危険波形（三尊等）の検知\n・MACDとRSIに基づくトリアージ（優先度）判定")

    if run_scope and target_codes_str:
        with open(T3_SCOPE_FILE, "w", encoding="utf-8") as f:
            f.write(target_codes_str)
            
        t_codes = list(dict.fromkeys([c.upper() for c in re.findall(r'(?<![a-zA-Z0-9])[a-zA-Z0-9]{4}(?![a-zA-Z0-9])', target_codes_str)]))
        
        if not t_codes: st.warning("有効な4桁の銘柄コードが見つかりません。")
        else:
            with st.spinner(f"指定された {len(t_codes)} 銘柄の軌道を精密計算・ソート中..."):
                
                # 🚨 段階1：全銘柄のデータを計算し、リストに格納する（まだ描画しない）
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
                    bt_primary = h14 - (ur * (st.session_state.push_r / 100.0))
                    shift_ratio = 0.618 if st.session_state.push_r >= 40 else (st.session_state.push_r / 100.0 + 0.15)
                    bt_secondary = h14 - (ur * shift_ratio)
                    
                    is_bt_broken = lc < bt_primary
                    bt_val = int(bt_secondary if is_bt_broken else bt_primary)
                    
                    dead_line = h14 - (ur * 0.618)
                    is_trend_broken = lc < (dead_line * 0.98)
                    daily_pct = (lc / prev['AdjC']) - 1 if prev['AdjC'] > 0 else 0
                    
                    is_dt = check_double_top(df_14); is_hs = check_head_shoulders(df_14); is_db = check_double_bottom(df_14)
                    is_defense = (not is_dt) and (not is_hs) and (lc <= (l14 * 1.03))
                    
                    c_name = f"銘柄 {c[:4]}"; c_market = "不明"; c_sector = "不明"; c_scale = ""
                    if not master_df.empty:
                        m_row = master_df[master_df['Code'] == api_code]
                        if not m_row.empty:
                            c_name = m_row.iloc[0]['CompanyName']; c_market = m_row.iloc[0]['Market']
                            c_sector = m_row.iloc[0].get('Sector', '不明'); c_scale = m_row.iloc[0].get('Scale', '')
                            
                    macd_h = latest.get('MACD_Hist', 0); macd_h_prev = prev.get('MACD_Hist', 0)
                    rsi_v = latest.get('RSI', 50)
                    # ⭕️ 修正後（モード"待伏"を指定。※Tab3は精密スコープなので待伏基準が最適です）
                    rank, bg, score, macd_t = get_triage_info(macd_h, macd_h_prev, rsi_v, lc, bt_val, mode="待伏")
                    
                    denom = h14 - bt_val
                    reach_val = ((h14 - lc) / denom * 100) if denom > 0 else 0
                    atr_val = int(latest.get('ATR', 0))
                    idxmax = df_14['AdjH'].idxmax()
                    d_high = len(df_14[df_14['Date'] > df_14.loc[idxmax, 'Date']]) if pd.notna(idxmax) else 0
                    avg_vol = int(df_s['AdjVo'].tail(5).mean()) if 'AdjVo' in df_s.columns else 0
                    
                    # ⭕️ 修正後（Tab3専用・地雷探知APIの直接通信）
                    # 広域スキャンではスキップした配当・決算データを、ここで初めてピンポイントで取得する
                    target_event_data = {"dividend": [], "earnings": []}
                    try:
                        # 1. 配当データ（権利落ち日）の取得
                        # ※ cli は J-Quants API のクライアントインスタンス（st.session_state.cli 等）に合わせて調整してください
                        res_div = cli.get_dividend(code=api_code) 
                        if res_div is not None and not res_div.empty: # DataFrameの場合
                            target_event_data["dividend"] = res_div.to_dict(orient="records")
                            
                        # 2. 決算データ（決算発表日）の取得
                        res_earn = cli.get_statements(code=api_code)
                        if res_earn is not None and not res_earn.empty: # DataFrameの場合
                            target_event_data["earnings"] = res_earn.to_dict(orient="records")
                    except Exception as e:
                        # 通信エラーやデータ無し（新興株など）の場合はスキップ
                        # ※フェイルセーフとして登録した絶対防衛線（critical_mines）は引き続き機能します
                        pass
                    
                    # 取得した生データを地雷判定ロジックへ流し込む
                    alerts = check_event_mines(c, target_event_data)
                    
                    # データを辞書として格納
                    scope_results.append({
                        'code': c, 'name': c_name, 'market': c_market, 'sector': c_sector, 'scale': c_scale,
                        'lc': lc, 'h14': h14, 'l14': l14, 'ur': ur, 'bt_val': bt_val, 'is_bt_broken': is_bt_broken,
                        'is_trend_broken': is_trend_broken, 'daily_pct': daily_pct, 'alerts': alerts,
                        'is_dt': is_dt, 'is_hs': is_hs, 'is_db': is_db, 'is_defense': is_defense,
                        'rank': rank, 'bg': bg, 'score': score, 'reach_val': reach_val, 'atr_val': atr_val,
                        'd_high': d_high, 'avg_vol': avg_vol, 'df_chart': df_chart
                    })
                    
                # 🚨 段階2：S/A/B/Cスコア順、同点なら到達度（reach_val）が高い順にソート
                scope_results = sorted(scope_results, key=lambda x: (x['score'], x['reach_val']), reverse=True)
                
                # 🚨 段階3：ソート済みのリストを展開してUIに描画
                for r in scope_results:
                    st.divider()
                    
                    scale_val = str(r['scale'])
                    badge = '<span style="background-color: #0d47a1; color: #ffffff; padding: 0.2rem 0.6rem; border-radius: 4px; font-size: 12px; display: inline-block;">🏢 大型/中型</span>' if any(x in scale_val for x in ["Core30", "Large70", "Mid400"]) else '<span style="background-color: #b71c1c; color: #ffffff; padding: 0.2rem 0.6rem; border-radius: 4px; font-size: 12px; display: inline-block;">🚀 小型/新興</span>'
                    triage_badge = f'<span style="background-color: {r["bg"]}; color: #ffffff; padding: 0.2rem 0.6rem; border-radius: 4px; font-size: 13px; display: inline-block; font-weight: bold; margin-left: 0.5rem;">🎯 優先度: {r["rank"]}</span>'

                    st.markdown(f"""
                        <div style="margin-bottom: 0.8rem;">
                            <h3 style="font-size: clamp(16px, 5vw, 26px); font-weight: bold; margin: 0 0 0.3rem 0;">({r['code'][:4]}) {r['name']}</h3>
                            <div style="display: flex; flex-wrap: wrap; gap: 4px; align-items: center;">{badge}{triage_badge}</div>
                        </div>
                    """, unsafe_allow_html=True)
                    
                    for alert in r['alerts']: st.warning(alert)
                    
                    if r['is_trend_broken']: st.error("💀 【トレンド崩壊】黄金比(61.8%)を完全に下抜けています。迎撃非推奨（後学・分析用データ）")
                    elif r['is_bt_broken']: st.error("⚠️ 【第一防衛線突破】想定以上の売り圧力を検知。買値を第二防衛線（黄金比等）へ自動シフトしました。")
                    
                    if r['sector'] == '医薬品': st.error("🚨 【警告】この銘柄は医薬品（バイオ株）です。思惑だけで動く完全なギャンブルです。")
                    if bool(re.search("ETF|投信|ブル|ベア|REIT|ﾘｰﾄ", str(r['name']), re.IGNORECASE)): st.error("🚨 【警告】この銘柄はETF/REIT等です。個別株のテクニカルは通用しません。")
                    
                    if r['is_dt'] or r['is_hs']: st.error("🚨 【警告】相場転換の危険波形（三尊/Wトップ）を検知！ 撤退推奨。")
                    if r['is_db']: st.success("🔥 【激熱(攻め)】三川（ダブルボトム）底打ち反転波形を検知！")
                    if r['is_defense']: st.info("🛡️ 【鉄壁(守り)】下値支持線(サポート)に極接近。損切りリスクが極小の安全圏です。")
                    
                    tp20 = int(r['bt_val'] * 1.20); tp15 = int(r['bt_val'] * 1.15)
                    tp10 = int(r['bt_val'] * 1.10); tp5  = int(r['bt_val'] * 1.05)
                    sl5  = int(r['bt_val'] * 0.95); sl8  = int(r['bt_val'] * 0.92); sl15 = int(r['bt_val'] * 0.85)
                    
                    daily_sign = "+" if r['daily_pct'] >= 0 else ""
                    
                    sc0, sc0_1, sc0_2, sc1, sc2, sc3, sc4 = st.columns([0.8, 0.8, 0.8, 0.9, 1.1, 1.8, 1.5])
                    sc0.metric("直近高値", f"{int(r['h14']):,}円")
                    sc0_1.metric("直近安値", f"{int(r['l14']):,}円")
                    sc0_2.metric("上昇幅", f"{int(r['ur']):,}円")
                    sc1.metric("最新終値", f"{int(r['lc']):,}円", f"{daily_sign}{r['daily_pct']*100:.1f}%", delta_color="inverse")
                    
                    html_buy = f"""
                    <div style="font-family: sans-serif; padding-top: 0.2rem;">
                        <div style="font-size: 14px; color: rgba(250, 250, 250, 0.6); padding-bottom: 0.1rem;">🎯 買値目標 (待伏)</div>
                        <div style="font-size: 1.8rem; font-weight: bold; color: #FFD700;">{r['bt_val']:,}円</div>
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
                    
                    html_stats = f"""
                    <div style="display: flex; flex-direction: column; gap: 8px; margin-top: 0.5rem;">
                        <div style="background: rgba(38, 166, 154, 0.1); border-left: 3px solid #26a69a; padding: 4px 8px; border-radius: 4px;">
                            <span style="font-size: 12px; color: #aaa;">到達度:</span> <strong style="font-size: 15px; color: #fff;">{r['reach_val']:.1f}%</strong>
                        </div>
                        <div style="background: rgba(156, 39, 176, 0.1); border-left: 3px solid #ab47bc; padding: 4px 8px; border-radius: 4px;">
                            <span style="font-size: 12px; color: #aaa;">ATR / 高値経過:</span> <strong style="font-size: 15px; color: #ce93d8;">{r['atr_val']:,}円 / {r['d_high']}日</strong>
                        </div>
                        <div style="background: rgba(255, 215, 0, 0.1); border-left: 3px solid #FFD700; padding: 4px 8px; border-radius: 4px;">
                            <span style="font-size: 12px; color: #aaa;">出来高(5日):</span> <strong style="font-size: 15px; color: #fff;">{r['avg_vol']:,} 株</strong>
                        </div>
                    </div>
                    """
                    sc4.markdown(html_stats, unsafe_allow_html=True)
                    st.caption(f"🏢 {r['market']} ｜ 🏭 {r['sector']}")
                    
                    from datetime import timedelta
                    cutoff_chart = r['df_chart']['Date'].max() - timedelta(days=60)
                    df_chart_filtered = r['df_chart'][r['df_chart']['Date'] >= cutoff_chart]
                    
                    st.markdown(render_technical_radar(df_chart_filtered, r['bt_val'], st.session_state.bt_tp), unsafe_allow_html=True)
                    draw_chart(df_chart_filtered, r['bt_val'], tp10=tp10)
                        
# ------------------------------------------
# Tab 4: 戦術シミュレータ（デュアル・バックテスト）
# ------------------------------------------
with tab4:
    st.markdown('<h3 style="font-size: clamp(14px, 4.5vw, 24px); margin-bottom: 1rem;">⚙️ 戦術シミュレータ (2年間のバックテスト)</h3>', unsafe_allow_html=True)
    
    col_b1, col_b2 = st.columns([1, 2])

    T4_FILE = f"saved_t4_codes_{user_id}.txt"
    default_t4 = "7839\n6614"
    if os.path.exists(T4_FILE):
        with open(T4_FILE, "r", encoding="utf-8") as f:
            default_t4 = f.read()

    with col_b1: 
        st.markdown("🔍 **検証する戦術を選択してください**")
        test_mode = st.radio("戦術モード", ["🌐 【待伏】鉄の掟 (押し目狙撃)", "⚡ 【強襲】GCブレイクアウト (順張り)"], label_visibility="collapsed", key="bt_mode_sim_v2")
        
        st.markdown("検証コード (複数可)")
        bt_c_in = st.text_area("銘柄コード", value=default_t4, height=100, label_visibility="collapsed", key="bt_codes_sim_v2")
        
        run_bt = st.button("🔥 仮想実弾テスト実行", use_container_width=True, key="btn_run_bt_sim_v2")
        st.divider()
        optimize_bt = st.button("🚀 戦術の黄金比率を抽出 (最適化)", use_container_width=True, help="現在のモードに応じた最強のパラメーター組み合わせを全自動で探索します。")
        
    with col_b2:
        st.markdown("#### ⚙️ シミュレーション微調整")
        c_p1, c_p2 = st.columns(2)
        sim_tp = c_p1.number_input("🎯 利確目標 (+%)", value=float(st.session_state.bt_tp), step=1.0, key="sim_tp_sim_v2")
        sim_sl_i = c_p2.number_input("🛡️ 損切目安 (-%)", value=float(st.session_state.bt_sl_i), step=1.0, key="sim_sl_i_sim_v2")
        
        c_p3, c_p4 = st.columns(2)
        sim_limit_d = c_p3.number_input("⏳ 買い期限 (営業日)", value=int(st.session_state.limit_d), step=1, key="sim_limit_d_sim_v2")
        sim_sell_d = c_p4.number_input("⏳ 強制撤退 (営業日)", value=int(st.session_state.bt_sell_d), step=1, key="sim_sell_d_sim_v2")
        
        st.divider()
        if "待伏" in test_mode:
            st.markdown("##### 🌐 【待伏】固有パラメーター")
            c_t1_1, c_t1_2 = st.columns(2)
            sim_push_r = c_t1_1.number_input("押し目待ち (%落とし)", value=float(st.session_state.push_r), step=1.0, key="sim_push_r_sim_v2")
            sim_pass_req = c_t1_2.number_input("掟クリア要求数", value=8, step=1, max_value=9, min_value=1, key="sim_pass_req_sim_v2")
        else:
            st.markdown("##### ⚡ 【強襲】固有パラメーター")
            c_t2_1, c_t2_2 = st.columns(2)
            sim_rsi_lim = c_t2_1.number_input("RSI上限 (過熱感)", value=45, step=5, key="sim_rsi_lim_sim_v2")
            sim_time_risk = c_t2_2.number_input("時間リスク上限 (到達日数)", value=5, step=1, key="sim_time_risk_sim_v2")

    # ==========================================
    # 🚀 ここから下が実行ブロック（高速化適用済み）
    # ==========================================
    if (run_bt or optimize_bt) and bt_c_in:
        import pandas as pd
        import time
        with open(T4_FILE, "w", encoding="utf-8") as f: f.write(bt_c_in)
        t_codes = list(dict.fromkeys([c.upper() for c in re.findall(r'(?<![a-zA-Z0-9])[a-zA-Z0-9]{4}(?![a-zA-Z0-9])', bt_c_in)]))
        
        if not t_codes:
            st.warning("有効なコードが見つかりません。")
        else:
            is_ambush = "待伏" in test_mode
            if is_ambush:
                p1_range = range(5, 26, 2) if optimize_bt else [int(sim_push_r)]
                p2_range = range(5, 10, 1) if optimize_bt else [int(sim_pass_req)]
                p1_name, p2_name = "Push率(%)", "要求Score"
            else:
                p1_range = range(30, 65, 5) if optimize_bt else [int(sim_rsi_lim)]
                p2_range = range(3, 16, 1) if optimize_bt else [int(sim_tp)]
                p1_name, p2_name = "RSI上限(%)", "利確目標(%)"
            
            # --- 1. データの事前取得と計算（プリロード） ---
            with st.spinner("データをプリロード中（高速化処理）..."):
                preloaded_data = {}
                for c in t_codes:
                    raw = get_single_data(c + "0", 2)
                    if not raw: continue
                    if isinstance(raw, dict) and 'bars' in raw: temp_df = pd.json_normalize(raw['bars'])
                    else: temp_df = pd.json_normalize(raw)
                    if temp_df.empty: continue
                    
                    rename_map = {}
                    for col in temp_df.columns:
                        c_up = col.upper()
                        if c_up.endswith('ADJO') or c_up.endswith('OPEN') or c_up == 'O': rename_map[col] = 'AdjO'
                        if c_up.endswith('ADJH') or c_up.endswith('HIGH') or c_up == 'H': rename_map[col] = 'AdjH'
                        if c_up.endswith('ADJL') or c_up.endswith('LOW') or c_up == 'L': rename_map[col] = 'AdjL'
                        if c_up.endswith('ADJC') or c_up.endswith('CLOSE') or c_up == 'C': rename_map[col] = 'AdjC'
                    
                    temp_df = temp_df.rename(columns=rename_map).loc[:, ~temp_df.rename(columns=rename_map).columns.duplicated()]
                    target_cols = ['AdjO', 'AdjH', 'AdjL', 'AdjC']
                    if not all(col in temp_df.columns for col in target_cols): continue
                    
                    try: 
                        df = clean_df(temp_df).dropna(subset=target_cols).reset_index(drop=True)
                        df = calc_technicals(df) # テクニカル指標を1回だけ計算
                        preloaded_data[c] = df
                    except: continue

            if not preloaded_data:
                st.error("解析可能なデータが取得できませんでした。")
                st.stop()

            # --- 2. 超高速最適化ループ ---
            opt_results = []
            total_iterations = len(p1_range) * len(p2_range)
            current_iter = 0
            
            p_bar = st.progress(0, f"戦術最適化の総当たり検証中... ({p1_name} × {p2_name})")

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
                                    all_t.append({
                                        '銘柄': c, '購入日': pos['b_d'], '決済日': td['Date'], 
                                        '保有日数': held, '買値(円)': int(bp), '売値(円)': int(sp), '損益(%)': p_pct, '損益額(円)': p_amt
                                    })
                                    pos = None
                    
                    if all_t:
                        p_df = pd.DataFrame(all_t)
                        total_p = p_df['損益額(円)'].sum()
                        win_r = len(p_df[p_df['損益額(円)'] > 0]) / len(p_df)
                        opt_results.append({p1_name: t_p1, p2_name: t_p2, '総合利益(円)': total_p, '勝率': win_r, '取引回数': len(all_t)})
                    
                    p_bar.progress(current_iter / total_iterations)
            
            p_bar.empty()

            # --- 3. 結果の表示 ---
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
                
                if is_ambush:
                    st.info(f"💡 ボス、現在の地合いでは高値から {int(best[p1_name])}% 落ちた位置に指値を置き、掟スコア {int(best[p2_name])}点 以上でエントリーするのが最も効率的です。")
            
            elif run_bt:
                if not opt_results:
                    st.warning("指定された期間・条件でシグナル点灯（約定）はありませんでした。")
                else:
                    tdf = pd.DataFrame(all_t).sort_values('決済日').reset_index(drop=True)
                    tdf['累積損益(円)'] = tdf['損益額(円)'].cumsum()
                    st.success("🎯 バックテスト完了")
                    
                    import plotly.express as px
                    fig_eq = px.line(tdf, x='決済日', y='累積損益(円)', markers=True, title="💰 仮想資産推移 (Equity Curve)", color_discrete_sequence=["#FFD700"])
                    fig_eq.update_layout(paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0.1)', margin=dict(l=20, r=20, t=40, b=20))
                    st.plotly_chart(fig_eq, use_container_width=True)
                    
                    n_prof = tdf['損益額(円)'].sum()
                    st.markdown(f'<h3 style="color: {"#ef5350" if n_prof > 0 else "#26a69a"};">総合利益額: {n_prof:,} 円</h3>', unsafe_allow_html=True)
                    
                    m1, m2, m3, m4 = st.columns(4)
                    tot = len(tdf); wins = len(tdf[tdf['損益額(円)'] > 0])
                    m1.metric("トレード回数", f"{tot} 回")
                    m2.metric("勝率", f"{round((wins/tot)*100,1)} %")
                    m3.metric("平均損益額", f"{int(n_prof/tot):,} 円" if tot > 0 else "0 円")
                    sloss = abs(tdf[tdf['損益額(円)'] <= 0]['損益額(円)'].sum())
                    m4.metric("PF", round(tdf[tdf['損益額(円)'] > 0]['損益額(円)'].sum() / sloss, 2) if sloss > 0 else 'inf')
                    
                    st.dataframe(tdf.drop(columns=['累積損益(円)']).style.format({'買値(円)': '{:,}', '売値(円)': '{:,}', '損益額(円)': '{:,}', '損益(%)': '{:.2f}'}), use_container_width=True, hide_index=True)
                
# ------------------------------------------
# Tab 5: IFD-OCO 10日ルール監視（JPXカレンダー準拠）
# ------------------------------------------
with tab5:
    st.markdown('<h3 style="font-size: clamp(14px, 4.5vw, 24px); margin-bottom: 1rem;">⛺ IFD潜伏カウント（指値・逆指値の接近アラート）</h3>', unsafe_allow_html=True)
    st.caption("※証券会社に仕掛けた指値（待伏）や逆指値（強襲）のコードと価格を入力し、現在値との距離や「注文の賞味期限」を監視します。")
    
    if 'tab5_ifd_results' not in st.session_state:
        st.session_state.tab5_ifd_results = None

    col_i1, col_i2 = st.columns([1, 2])
    
    T5_FILE = f"saved_t5_ifd_{user_id}.txt"
    default_ifd = "6614, 2500\n4427, 1200" # コード, 指値
    if os.path.exists(T5_FILE):
        with open(T5_FILE, "r", encoding="utf-8") as f:
            default_ifd = f.read()

    with col_i1:
        st.markdown("📝 **監視リスト入力**")
        st.caption("書式: `銘柄コード, 設定した指値` (改行で複数入力)")
        ifd_in = st.text_area("IFD注文リスト", value=default_ifd, height=150, label_visibility="collapsed", key="ifd_in_t5")
        
        c_exp1, c_exp2 = st.columns(2)
        expire_d = c_exp1.number_input("⏳ 注文の有効期限 (日)", value=int(st.session_state.limit_d), step=1, key="expire_d_t5")
        run_ifd = st.button("📡 潜伏レーダー更新", use_container_width=True, key="btn_run_ifd_t5")
        
    with col_i2:
        st.markdown("#### 🛡️ 参謀の監視プロトコル")
        st.info("・現在値が指値に接近（±2%以内）すると激熱アラートが点灯します。\n・強襲（逆指値）の場合は上に抜けたら、待伏（指値）の場合は下に落ちたら約定とみなします。\n・相場環境は日々変化します。有効期限を過ぎた注文は、速やかに取り消す（パージする）ことを推奨します。")

    # ==========================================
    # 💥 フェーズ1：計算とデータ抽出（ボタンが押された時のみ実行）
    # ==========================================
    if run_ifd and ifd_in:
        with open(T5_FILE, "w", encoding="utf-8") as f:
            f.write(ifd_in)
            
        lines = ifd_in.strip().split('\n')
        targets = []
        for line in lines:
            parts = [p.strip() for p in line.split(',')]
            if len(parts) >= 2 and parts[0].isdigit():
                targets.append({'code': parts[0], 'price': int(parts[1])})
                
        if not targets:
            st.warning("有効な形式（コード, 指値）で見つかりません。")
            st.session_state.tab5_ifd_results = []
        else:
            with st.spinner("前線に展開中の各部隊（注文）の現在地を照会中..."):
                processed_results = []
                for t in targets:
                    c = t['code']
                    order_p = t['price']
                    
                    api_code = c if len(c) == 5 else c + "0"
                    raw_s = get_single_data(api_code, 1)
                    
                    if not raw_s:
                        st.error(f"銘柄 {c} の通信に失敗しました。")
                        continue
                        
                    # 🚨 防衛パッチ：APIのカラム重複エラーを排除しつつデータを構築
                    if raw_s and "bars" in raw_s and len(raw_s["bars"]) > 0:
                        temp_df = pd.DataFrame(raw_s["bars"])
                        rename_map = {}
                        for col in temp_df.columns:
                            c_up = col.upper()
                            if c_up.endswith('ADJO') or c_up.endswith('OPEN') or c_up == 'O': rename_map[col] = 'AdjO'
                            if c_up.endswith('ADJH') or c_up.endswith('HIGH') or c_up == 'H': rename_map[col] = 'AdjH'
                            if c_up.endswith('ADJL') or c_up.endswith('LOW') or c_up == 'L':  rename_map[col] = 'AdjL'
                            if c_up.endswith('ADJC') or c_up.endswith('CLOSE') or c_up == 'C': rename_map[col] = 'AdjC'
                        renamed_df = temp_df.rename(columns=rename_map)
                        dedup_df = renamed_df.loc[:, ~renamed_df.columns.duplicated()]
                        df_s = clean_df(dedup_df)
                    else:
                        continue
                        
                    if df_s.empty: continue
                    
                    df_chart = calc_technicals(df_s)
                    latest = df_chart.iloc[-1]
                    prev = df_chart.iloc[-2] if len(df_chart) > 1 else latest
                    
                    lc = int(latest['AdjC'])
                    daily_pct = (lc / prev['AdjC']) - 1 if prev['AdjC'] > 0 else 0
                    daily_sign = "+" if daily_pct >= 0 else ""
                    
                    c_name = f"銘柄 {c[:4]}"; c_market = "不明"; c_sector = "不明"
                    if not master_df.empty:
                        m_row = master_df[master_df['Code'] == api_code]
                        if not m_row.empty:
                            c_name = m_row.iloc[0]['CompanyName']; c_market = m_row.iloc[0]['Market']; c_sector = m_row.iloc[0].get('Sector', '不明')
                    
                    diff_yen = lc - order_p
                    diff_pct = (diff_yen / lc) * 100 if lc > 0 else 0
                    
                    alert_html = ""
                    if abs(diff_pct) <= 2.0:
                        alert_html = '<span style="background-color: #ef5350; color: #ffffff; padding: 0.2rem 0.6rem; border-radius: 4px; font-size: 13px; font-weight: bold; margin-left: 0.5rem;">🔥 約定目前（交戦距離）</span>'
                    elif diff_yen > 0:
                        alert_html = '<span style="background-color: #0288d1; color: #ffffff; padding: 0.2rem 0.6rem; border-radius: 4px; font-size: 13px; font-weight: bold; margin-left: 0.5rem;">📡 高度待機中（上空）</span>'
                    else:
                        alert_html = '<span style="background-color: #ed6c02; color: #ffffff; padding: 0.2rem 0.6rem; border-radius: 4px; font-size: 13px; font-weight: bold; margin-left: 0.5rem;">📉 買値割れ（既に通過）</span>'
                    
                    processed_results.append({
                        'code': c, 'name': c_name, 'market': c_market, 'sector': c_sector,
                        'lc': lc, 'order_p': order_p, 'daily_pct': daily_pct, 'daily_sign': daily_sign,
                        'diff_yen': diff_yen, 'diff_pct': diff_pct, 'alert_html': alert_html
                    })
                    
                    # 🚨 極限最適化：1銘柄の計算が終わるたびに一時データを完全に破棄
                    del temp_df, renamed_df, dedup_df, df_s, df_chart
                
                # フェーズ1の完了：セッション変数へロックオン
                st.session_state.tab5_ifd_results = processed_results
                import gc
                gc.collect()

    # ==========================================
    # 🖼️ フェーズ2：UI描画（セッションから読み出し）
    # ==========================================
    if st.session_state.tab5_ifd_results is not None:
        results = st.session_state.tab5_ifd_results
        
        if not results:
            pass # エラー時はPhase1で警告済み
        else:
            st.success(f"📡 潜伏レーダー展開中: {len(results)} 部隊を捕捉。（データ保持中）")
            
            for r in results:
                st.divider()
                st.markdown(f"""
                    <div style="margin-bottom: 0.8rem;">
                        <h3 style="font-size: clamp(16px, 5vw, 24px); font-weight: bold; margin: 0 0 0.3rem 0;">({r['code'][:4]}) {r['name']}</h3>
                        <div style="display: flex; align-items: center; gap: 8px;">
                            {r['alert_html']}
                            <span style="font-size: 13px; color: #aaa;">| 🏢 {r['market']} | 🏭 {r['sector']}</span>
                        </div>
                    </div>
                """, unsafe_allow_html=True)
                
                sc1, sc2, sc3 = st.columns([1, 1, 1.5])
                
                sc1.metric("最新終値", f"{r['lc']:,}円", f"{r['daily_sign']}{r['daily_pct']*100:.1f}%", delta_color="inverse")
                
                html_order = f"""
                <div style="font-family: sans-serif; padding-top: 0.2rem;">
                    <div style="font-size: 14px; color: rgba(250, 250, 250, 0.6); padding-bottom: 0.1rem;">🎯 設置済み 指値/逆指値</div>
                    <div style="font-size: 1.8rem; font-weight: bold; color: #FFD700;">{r['order_p']:,}円</div>
                </div>
                """
                sc2.markdown(html_order, unsafe_allow_html=True)
                
                dist_color = "#ef5350" if abs(r['diff_pct']) <= 2.0 else "#26a69a"
                html_dist = f"""
                <div style="font-family: sans-serif; padding-top: 0.2rem;">
                    <div style="font-size: 14px; color: rgba(250, 250, 250, 0.6); padding-bottom: 0.1rem;">📏 現在値との乖離（距離）</div>
                    <div style="font-size: 1.5rem; font-weight: bold; color: {dist_color};">
                        {"+" if r['diff_yen'] > 0 else ""}{r['diff_yen']:,}円 ({"+" if r['diff_pct'] > 0 else ""}{r['diff_pct']:.1f}%)
                    </div>
                </div>
                """
                sc3.markdown(html_dist, unsafe_allow_html=True)

    import gc
    gc.collect()  # 処理済みの不要なメモリを強制排出
                    
# ------------------------------------------
# Tab 6: 事後任務報告（AAR）
# ------------------------------------------
with tab6:
    st.markdown('<h3 style="font-size: clamp(14px, 4.5vw, 24px); margin-bottom: 1rem;">📁 事後任務報告 (AAR) & 戦績ダッシュボード</h3>', unsafe_allow_html=True)
    st.caption("※実際の交戦記録（トレード履歴）を記録し、自身の戦績と「規律遵守度（メンタル）」を可視化・分析します。")
    
    AAR_FILE = f"saved_aar_log_{user_id}.csv"
    
    # 🚨 銘柄コードから企業規模を判定する関数
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
        # 🚨 過去のデータに「規模」カラムがない場合の自動補完
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
            import datetime
            aar_date = c_f1.date_input("決済日", datetime.date.today())
            aar_code = c_f2.text_input("銘柄コード (4桁)", max_chars=4)
            
            aar_tactics = st.selectbox("使用した戦術", ["🌐 待伏 (押し目)", "⚡ 強襲 (順張り)", "⚠️ その他 (裁量・妥協)"])
            
            c_f3, c_f4, c_f5 = st.columns(3)
            aar_buy = c_f3.number_input("買値 (円)", min_value=0.0, step=1.0, format="%.1f")
            aar_sell = c_f4.number_input("売値 (円)", min_value=0.0, step=1.0, format="%.1f")
            aar_lot = c_f5.number_input("株数", min_value=100, step=100)
            
            st.markdown("**⚖️ 自己評価（メンタル・チェック）**")
            aar_rule = st.radio("ボスの『鉄の掟』を完全に遵守して撃ちましたか？", 
                                ["✅ 遵守した (冷徹な狙撃)", "❌ 破った (感情・焦り・妥協)"], horizontal=False)
            
            aar_memo = st.text_input("特記事項 (なぜそのルールを破ったか、または勝因など)")
            
            submit_aar = st.form_submit_button("💾 記録をデータバンクへ保存", use_container_width=True)
            
        if submit_aar:
            if aar_code and len(aar_code) >= 4 and aar_buy > 0 and aar_sell > 0:
                profit = int((aar_sell - aar_buy) * aar_lot)
                profit_pct = round(((aar_sell / aar_buy) - 1) * 100, 2)
                
                new_data = pd.DataFrame([{
                    "決済日": aar_date.strftime("%Y-%m-%d"),
                    "銘柄": aar_code,
                    "規模": get_scale_for_code(aar_code),
                    "戦術": aar_tactics.split(" ")[1] if " " in aar_tactics else aar_tactics,
                    "買値": aar_buy,
                    "売値": aar_sell,
                    "株数": aar_lot,
                    "損益額(円)": profit,
                    "損益(%)": profit_pct,
                    "規律": "遵守" if "遵守" in aar_rule else "違反",
                    "敗因/勝因メモ": aar_memo
                }])
                
                aar_df = pd.concat([new_data, aar_df], ignore_index=True)
                aar_df = aar_df.sort_values(['決済日', '銘柄'], ascending=[True, True]).reset_index(drop=True)
                aar_df.to_csv(AAR_FILE, index=False)
                st.success(f"銘柄 {aar_code} の戦果を司令部データベースに記録しました。")
                st.rerun()
            else:
                st.error("銘柄コード、買値、売値を正しく入力してください。")
        
        with st.expander("📥 証券会社の取引履歴(CSV)から自動一括登録", expanded=True):
            st.caption("アップロードされたCSVから「現物買」と「現物売」を自動でペアリングし、損益を算出してデータベースへ一括登録します。（※重複データは自動排除されます）")
            uploaded_csv = st.file_uploader("約定履歴CSVファイルをアップロード", type=["csv"], key="aar_csv_uploader")
            
            if uploaded_csv is not None:
                if st.button("⚙️ CSVから戦果を自動解析して追加", use_container_width=True, key="btn_parse_csv"):
                    try:
                        import io
                        try:
                            content = uploaded_csv.getvalue().decode('utf-8')
                        except UnicodeDecodeError:
                            content = uploaded_csv.getvalue().decode('shift_jis', errors='replace')
                            
                        lines = content.splitlines()
                        
                        header_idx = -1
                        for i, line in enumerate(lines):
                            if "約定日" in line and "銘柄" in line:
                                header_idx = i
                                break
                                
                        if header_idx != -1:
                            csv_data = "\n".join(lines[header_idx:])
                            df_csv = pd.read_csv(io.StringIO(csv_data))
                            
                            df_csv = df_csv[df_csv['取引'].astype(str).str.contains('現物')].copy()
                            records = []
                            
                            for code, group in df_csv.groupby('銘柄コード'):
                                buys, sells = [], []
                                for _, row in group.iterrows():
                                    item = {
                                        'date': str(row['約定日']).replace('/', '-'),
                                        'qty': int(row['約定数量']),
                                        'price': float(row['約定単価']),
                                        'code': str(code)
                                    }
                                    if "買" in str(row['取引']): buys.append(item)
                                    elif "売" in str(row['取引']): sells.append(item)
                                
                                buys.sort(key=lambda x: x['date'])
                                sells.sort(key=lambda x: x['date'])
                                
                                for s in sells:
                                    sell_qty = s['qty']
                                    matched_qty, matched_buy_amount = 0, 0
                                    
                                    while sell_qty > 0 and len(buys) > 0:
                                        b = buys[0]
                                        if b['qty'] <= sell_qty:
                                            matched_qty += b['qty']
                                            matched_buy_amount += b['price'] * b['qty']
                                            sell_qty -= b['qty']
                                            buys.pop(0)
                                        else:
                                            matched_qty += sell_qty
                                            matched_buy_amount += b['price'] * sell_qty
                                            b['qty'] -= sell_qty
                                            sell_qty = 0
                                            
                                    if matched_qty > 0:
                                        avg_buy_price = matched_buy_amount / matched_qty
                                        profit = (s['price'] - avg_buy_price) * matched_qty
                                        profit_pct = ((s['price'] / avg_buy_price) - 1) * 100
                                        
                                        records.append({
                                            "決済日": s['date'],
                                            "銘柄": s['code'],
                                            "規模": get_scale_for_code(s['code']),
                                            "戦術": "自動解析",
                                            "買値": round(avg_buy_price, 1),
                                            "売値": round(s['price'], 1),
                                            "株数": int(matched_qty),
                                            "損益額(円)": int(profit),
                                            "損益(%)": round(profit_pct, 2),
                                            "規律": "不明(要修正)",
                                            "敗因/勝因メモ": "CSV自動取り込み"
                                        })
                                        
                            if records:
                                new_df = pd.DataFrame(records)
                                aar_df = pd.concat([new_df, aar_df], ignore_index=True)
                                aar_df = aar_df.drop_duplicates(subset=["決済日", "銘柄", "買値", "売値", "株数"]).reset_index(drop=True)
                                aar_df = aar_df.sort_values(['決済日', '銘柄'], ascending=[True, True]).reset_index(drop=True)
                                aar_df.to_csv(AAR_FILE, index=False)
                                st.success(f"🎯 {len(records)} 件の戦果を解析し、データベースに自動追加しました！")
                                st.rerun()
                            else:
                                st.warning("解析可能な決済済みペア（買いと売りのセット）が見つかりませんでした。")
                        else:
                            st.error("CSVフォーマットが認識できませんでした。「約定日」「銘柄」を含むヘッダ行が必要です。")
                    except Exception as e:
                        st.error(f"解析エラー: {e}")

        if not aar_df.empty:
            if st.button("🗑️ 全記録を消去 (データベース初期化)", key="reset_aar", use_container_width=True):
                os.remove(AAR_FILE)
                st.rerun()

    with col_a2:
        st.markdown("#### 📊 司令部 総合戦績ダッシュボード")
        if aar_df.empty:
            st.warning("現在、交戦記録（データ）がありません。左のフォームから入力するか、CSVをアップロードしてください。")
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
            fig_real_eq = px.line(aar_df_sorted, x='決済日', y='累積損益(円)', markers=True, 
                             color_discrete_sequence=["#26a69a"])
            fig_real_eq.update_layout(
                paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0.1)',
                margin=dict(l=20, r=20, t=10, b=20),
                xaxis_title="", yaxis_title="実損益額 (円)",
                height=250, hovermode="x unified"
            )
            st.plotly_chart(fig_real_eq, use_container_width=True)
            
            # 🚨 利益は赤、損失は緑のカラーリング関数
            def color_pnl(val):
                if isinstance(val, (int, float)):
                    color = '#ef5350' if val > 0 else '#26a69a' if val < 0 else 'white'
                    return f'color: {color}; font-weight: bold;'
                return ''
                
            def color_rule(val):
                if val == '違反': return 'color: #ef5350; font-weight: bold; background-color: rgba(239, 83, 80, 0.1);'
                elif '不明' in str(val): return 'color: #9e9e9e;'
                return 'color: #26a69a;'

            st.markdown("##### 📜 詳細交戦記録（キル・ログ）")
            st.caption("※表のセルを直接ダブルクリックすると、「戦術」「規律」「メモ」を直接編集（上書き保存）できます。")

            # 色を適用したStylerオブジェクトを作成
            styled_df = aar_df.style.map(color_pnl, subset=['損益額(円)', '損益(%)']).map(color_rule, subset=['規律'])

            # 🚨 st.data_editorによる直接編集可能なインタラクティブボード
            edited_df = st.data_editor(
                styled_df,
                column_config={
                    "規模": st.column_config.TextColumn("規模", disabled=True),
                    "戦術": st.column_config.SelectboxColumn(
                        "戦術",
                        help="使用した戦術を選択",
                        options=["待伏", "強襲", "自動解析", "その他"],
                        required=True,
                    ),
                    "規律": st.column_config.SelectboxColumn(
                        "規律",
                        help="鉄の掟を守れたか",
                        options=["遵守", "違反", "不明(要修正)"],
                        required=True,
                    ),
                    "敗因/勝因メモ": st.column_config.TextColumn(
                        "敗因/勝因メモ",
                        max_chars=200,
                    ),
                    "買値": st.column_config.NumberColumn("買値", format="%.1f"),
                    "売値": st.column_config.NumberColumn("売値", format="%.1f"),
                    "株数": st.column_config.NumberColumn("株数", format="%d"),
                    "損益額(円)": st.column_config.NumberColumn("損益額(円)", format="%d"),
                    "損益(%)": st.column_config.NumberColumn("損益(%)", format="%.2f"),
                },
                disabled=["決済日", "銘柄", "規模", "買値", "売値", "株数", "損益額(円)", "損益(%)"],
                hide_index=True,
                use_container_width=True,
                key="aar_data_editor"
            )
            
            # セルが編集された場合、自動でCSVに上書き保存して再読み込み
            if not edited_df.equals(aar_df):
                edited_df.to_csv(AAR_FILE, index=False)
                st.rerun()
