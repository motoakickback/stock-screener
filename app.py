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
                    // Streamlitのパスワード入力欄と送信ボタンを特定
                    const input = doc.querySelector('input[type="password"]');
                    const buttons = doc.querySelectorAll('button');
                    let submitBtn = null;
                    
                    // 「認証」という文字を含むフォーム送信ボタンを探す
                    for (const btn of buttons) {
                        if (btn.innerText && btn.innerText.includes("認証")) {
                            submitBtn = btn;
                            break;
                        }
                    }

                    if (input && submitBtn) {
                        // ブラウザの補完や指紋認証により、値が入った瞬間を検知
                        if (input.value.length > 0) {
                            // ボタンを物理的にクリック
                            submitBtn.click();
                            return true; // 成功
                        }
                    }
                    return false;
                }

                // 指紋認証の時間を考慮し、高頻度（200ms）で監視を継続
                const monitor = setInterval(() => {
                    if (tryAutoLogin()) {
                        clearInterval(monitor); // ログイン実行後に監視停止
                    }
                }, 200);

                // 念のため、入力イベントもフックしておく（手動入力・補完両対応）
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
    # 🚨 参謀が選定した「真のデフォルト値」
    defaults = {
        "preset_market": "🚀 中小型株 (スタンダード・グロース)", 
        "preset_push_r": "50.0%",
        "sidebar_tactics": "⚖️ バランス (掟達成率 ＞ 到達度)",
        "push_r": 50.0, "limit_d": 4, "bt_lot": 100, "bt_tp": 10, "bt_sl_i": 8, "bt_sl_c": 8, "bt_sell_d": 10,
        "f1_min": 200, "f1_max": 3000, "f2_m30": 2.0, "f3_drop": -50.0,
        "f5_ipo": True, "f6_risk": True, "f7_ex_etf": True, "f8_ex_bio": True,
        "f9_min14": 1.3, "f9_max14": 2.0, "f10_ex_knife": True,
        "f11_ex_wave3": True, "f12_ex_overvalued": True,
        "tab1_etf_filter": True, "tab2_rsi_limit": 75, "tab2_vol_limit": 15000, 
        "tab2_ipo_filter": True, "tab2_etf_filter": True, "t3_scope_mode": "🌐 【待伏】 押し目・逆張り",
        "bt_mode_sim_v2": "🌐 【待伏】鉄の掟 (押し目狙撃)", 
        "sim_tp_val": 10, "sim_sl_val": 8, "sim_limit_d_val": 4, "sim_sell_d_val": 10, "sim_push_r_val": 50.0,
        "sim_pass_req_val": 7, "sim_rsi_lim_ambush_val": 45, "sim_rsi_lim_assault_val": 70, "sim_time_risk_val": 5,
        "gigi_input": "2134, 3350, 6172, 6740, 7647, 8783, 8836, 8925, 9318"
    }

    # 1. まずJSONから読み込み
    if os.path.exists(SETTINGS_FILE):
        try:
            with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
                saved = json.load(f)
                # 🚨 異常値（0）の浄化ロジック
                for k, v in saved.items():
                    if k in defaults:
                        # 0 または 空文字 の場合はデフォルト値を採用（f3_drop以外）
                        if k != "f3_drop" and isinstance(v, (int, float)) and v == 0:
                            continue
                        defaults[k] = v
        except: pass
    
    # 2. Session Stateへ展開（0の場合は強制上書き）
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v
        else:
            # 既にSession Stateにある値が0の場合も、デフォルト値で叩き直す
            if k != "f3_drop" and isinstance(st.session_state[k], (int, float)) and st.session_state[k] == 0:
                st.session_state[k] = v

def save_settings():
    keys = ["preset_market", "preset_push_r", "sidebar_tactics", "push_r", "limit_d", "bt_lot", "bt_tp", "bt_sl_i", "bt_sl_c", "bt_sell_d", 
            "f1_min", "f1_max", "f2_m30", "f3_drop", "f5_ipo", "f6_risk", "f7_ex_etf", "f8_ex_bio", 
            "f9_min14", "f9_max14", "f10_ex_knife", "f11_ex_wave3", "f12_ex_overvalued",
            "tab1_etf_filter", "tab2_rsi_limit", "tab2_vol_limit", 
            "tab2_ipo_filter", "tab2_etf_filter", "t3_scope_mode", "bt_mode_sim_v2", 
            "sim_tp_val", "sim_sl_val", "sim_limit_d_val", "sim_sell_d_val", "sim_push_r_val", 
            "sim_pass_req_val", "sim_rsi_lim_ambush_val", "sim_rsi_lim_assault_val", "sim_time_risk_val", "gigi_input"]
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
    # (既存のプリセット連動ロジック)
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
        from datetime import datetime, timedelta
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
            fig.add_trace(go.Scatter(
                x=df['Date'], y=df['Close'], name='日経平均', mode='lines', 
                line=dict(color='#FFD700', width=2),
                hovertemplate='日経平均: ¥%{y:,.0f}<extra></extra>'
            ))
            fig.add_trace(go.Scatter(
                x=df['Date'], y=df['MA25'], name='25日線', mode='lines', 
                line=dict(color='rgba(255, 255, 255, 0.4)', width=1, dash='dot'),
                hovertemplate='25日線: ¥%{y:,.0f}<extra></extra>'
            ))
            
            x_min = df['Date'].min()
            x_max = df['Date'].max() + pd.Timedelta(hours=12)
            
            fig.update_layout(
                height=160, margin=dict(l=10, r=40, t=10, b=10),
                xaxis_rangeslider_visible=False, paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)', 
                showlegend=False, hovermode="x unified",
                yaxis=dict(side="right", tickformat=",.0f", gridcolor='rgba(255,255,255,0.05)'),
                xaxis=dict(
                    type='date', tickformat='%m/%d', gridcolor='rgba(255,255,255,0.05)',
                    range=[x_min, x_max] 
                )
            )
            st.plotly_chart(fig, use_container_width=True, config={'displayModeBar': False})
        st.markdown("<div style='margin-bottom: 1.5rem;'></div>", unsafe_allow_html=True)
    else: st.warning("📡 外部気象レーダー応答なし")

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
        if lc >= ma25: score += 10          # 25日線上抜け（+10点）
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
st.sidebar.title("🛠️ 戦術コンソール")

# --- 1. ターゲット選別 ---
st.sidebar.header("📍 ターゲット選別")
st.sidebar.selectbox("市場ターゲット", ["🏢 大型株 (プライム・一部)", "🚀 中小型株 (スタンダード・グロース)"], key="preset_market", on_change=save_settings)
st.sidebar.selectbox("押し目プリセット", ["25.0%", "50.0%", "61.8%"], key="preset_push_r", on_change=apply_presets)
st.sidebar.selectbox("戦術アルゴリズム", ["⚖️ バランス (掟達成率 ＞ 到達度)", "🎯 狙撃優先 (到達度 ＞ 掟達成率)"], key="sidebar_tactics", on_change=save_settings)

st.sidebar.divider()

# --- 2. ピックアップルール ---
st.sidebar.header("🔍 ピックアップルール")
c_f1_1, c_f1_2 = st.sidebar.columns(2)
c_f1_1.number_input("価格下限(円)", step=100, key="f1_min", on_change=save_settings)
c_f1_2.number_input("価格上限(円)", step=100, key="f1_max", on_change=save_settings)
st.sidebar.number_input("1ヶ月暴騰上限(倍)", step=0.1, key="f2_m30", on_change=save_settings)
st.sidebar.number_input("1年最高値からの下落除外(%)", step=5.0, max_value=0.0, key="f3_drop", on_change=save_settings)

# 波高の設定
c_f9_1, c_f9_2 = st.sidebar.columns(2)
c_f9_1.number_input("波高下限(倍)", step=0.1, key="f9_min14", on_change=save_settings)
c_f9_2.number_input("波高上限(倍)", step=0.1, key="f9_max14", on_change=save_settings)

st.sidebar.checkbox("IPO除外(上場1年未満)", key="f5_ipo", on_change=save_settings)
st.sidebar.checkbox("疑義注記・信用リスク銘柄除外", key="f6_risk", on_change=save_settings)
st.sidebar.checkbox("上昇第3波終了銘柄を除外", key="f11_ex_wave3", on_change=save_settings)
st.sidebar.checkbox("非常に割高・赤字銘柄を除外", key="f12_ex_overvalued", on_change=save_settings)

st.sidebar.divider()

# --- 3. 買い・売りルール ---
st.sidebar.header("🎯 買いルール")
st.sidebar.number_input("購入ロット(株)", step=100, key="bt_lot", on_change=save_settings)
st.sidebar.number_input("目標到達の猶予期限(日)", step=1, key="limit_d", on_change=save_settings)

st.sidebar.header("💰 売りルール")
st.sidebar.number_input("利確目標(%)", step=1, key="bt_tp", on_change=save_settings)
c_sl_1, c_sl_2 = st.sidebar.columns(2)
c_sl_1.number_input("初期損切(%)", step=1, key="bt_sl_i", on_change=save_settings)
c_sl_2.number_input("現在損切(%)", step=1, key="bt_sl_c", on_change=save_settings)
st.sidebar.number_input("最大保持期間(日)", step=1, key="bt_sell_d", on_change=save_settings)

st.sidebar.divider()

# --- 4. 特殊除外フィルター ---
st.sidebar.header("🚫 特殊除外フィルター")
st.sidebar.checkbox("ETF・REIT等を除外", key="f7_ex_etf", on_change=save_settings)
st.sidebar.checkbox("医薬品(バイオ)を除外", key="f8_ex_bio", on_change=save_settings)
st.sidebar.checkbox("落ちるナイフ除外(暴落直後)", key="f10_ex_knife", on_change=save_settings)
st.sidebar.text_area("除外銘柄コード (雑なコピペ対応)", key="gigi_input", on_change=save_settings)

st.sidebar.divider()

# --- 5. システム管理 ---
st.sidebar.header("⚙️ システム管理")
if st.sidebar.button("🔴 キャッシュ強制パージ", use_container_width=True):
    st.cache_data.clear()
    st.session_state.tab1_scan_results = None
    st.session_state.tab2_scan_results = None
    st.rerun()

if st.sidebar.button("💾 現在の設定を保存", use_container_width=True):
    save_settings()
    st.toast("全設定を永久保存した。")
    
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

                # --- 設定同期 ---
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
                g_in = st.session_state.get("gigi_input", "")
                if g_in:
                    bl = re.findall(r'\d{4}', str(g_in))
                    if bl: df = df[~df['Code'].str.extract(r'(\d{4})')[0].isin(bl)]

                master_dict = master_df.set_index('Code')[['CompanyName', 'Market', 'Sector']].to_dict('index') if not master_df.empty else {}
                
                results = []
                for code, group in df.groupby('Code'):
                    if len(group) < 15: continue 
                    adjc_vals, adjh_vals, adjl_vals = group['AdjC'].values, group['AdjH'].values, group['AdjL'].values
                    lc = adjc_vals[-1]

                    # 1ヶ月暴騰上限 (20日前比)
                    prev_20_val = adjc_vals[max(0, len(adjc_vals)-20)]
                    if prev_20_val > 0 and (lc / prev_20_val) > f2_limit: continue

                    # 1年最高値からの下落率
                    if lc < adjh_vals.max() * (1 + (f3_drop_val / 100.0)): continue

                    # 第3波終了
                    if st.session_state.f11_ex_wave3:
                        peaks = []
                        for j in range(5, len(adjh_vals)-5):
                            if adjh_vals[j] == max(adjh_vals[j-5:j+5]):
                                if not peaks or adjh_vals[j] > peaks[-1] * 1.15: peaks.append(adjh_vals[j])
                        if len(peaks) >= 3 and lc < max(peaks) * 0.85: continue

                    # 落ちるナイフ
                    if f10_ex_knife:
                        recent_4d = adjc_vals[-4:]
                        if len(recent_4d) == 4 and (recent_4d[-1] / recent_4d[0] < 0.85): continue
                    
                    # 押し目計算
                    recent_4d_h = adjh_vals[-4:]; local_max_idx = recent_4d_h.argmax()
                    high_4d_val = recent_4d_h[local_max_idx]; global_max_idx = len(adjh_vals) - 4 + local_max_idx
                    low_14d_val = adjl_vals[max(0, global_max_idx - 14) : global_max_idx + 1].min()

                    if low_14d_val <= 0 or high_4d_val <= low_14d_val: continue
                    wave_height = high_4d_val / low_14d_val
                    if not (st.session_state.f9_min14 <= wave_height <= st.session_state.f9_max14): continue
                    
                    target_buy = high_4d_val - ((high_4d_val - low_14d_val) * push_ratio)
                    reach_rate = (target_buy / lc) * 100

                    # 指標
                    rsi, macd_h, macd_h_prev, _ = get_fast_indicators(adjc_vals)
                    
                    # 🏅 掟スコア計算
                    score = 4 
                    if 1.3 <= wave_height <= 2.0: score += 1
                    if (len(adjh_vals) - 1 - global_max_idx) <= limit_d_val: score += 1
                    if not check_double_top(group.tail(31).iloc[:-1]): score += 1
                    if target_buy * 0.85 <= lc <= target_buy * 1.35: score += 1

                    m_info = master_dict.get(code, {})
                    rank, bg, t_score, _ = get_triage_info(macd_h, macd_h_prev, rsi, lc, target_buy, mode="待伏")

                    results.append({
                        'Code': code, 'Name': m_info.get('CompanyName', f"銘柄 {code[:4]}"),
                        'Sector': m_info.get('Sector', '不明'), 'Market': m_info.get('Market', '不明'),
                        'lc': lc, 'RSI': rsi, 'avg_vol': int(avg_vols.get(code, 0)), 'high_4d': high_4d_val, 
                        'low_14d': low_14d_val, 'target_buy': target_buy, 'reach_rate': reach_rate, 
                        'triage_rank': rank, 'triage_bg': bg, 't_score': t_score, 'score': score
                    })
                
                st.session_state.tab1_scan_results = sorted(results, key=lambda x: (x['t_score'], x['score']), reverse=True)[:30]

    if st.session_state.tab1_scan_results:
        light_results = st.session_state.tab1_scan_results
        st.success(f"🎯 待伏ロックオン: {len(light_results)} 銘柄を確認。")
        sab_codes = " ".join([str(r['Code'])[:4] for r in light_results if str(r['triage_rank']).startswith(('S', 'A', 'B'))])
        other_codes = " ".join([str(r['Code'])[:4] for r in light_results if not str(r['triage_rank']).startswith(('S', 'A', 'B'))])
        
        st.info("📋 以下のコードをコピーして、照準（TAB3）にペースト可能だ。")
        if sab_codes:
            st.markdown("**🎯 優先度 S・A・B (主力標的)**")
            st.code(sab_codes, language="text")
        if other_codes:
            with st.expander("👀 優先度 C・圏外 (監視対象)"):
                st.code(other_codes, language="text")
        
        for r in light_results:
            st.divider()
            c_code = str(r['Code']); m_lower = str(r['Market']).lower()
            if 'プライム' in m_lower or '一部' in m_lower: badge_html = '<span style="background-color: #1a237e; color: #ffffff; padding: 0.2rem 0.6rem; border-radius: 4px; font-size: 11px; font-weight: bold;">🏢 プライム/大型</span>'
            elif 'グロース' in m_lower or 'マザーズ' in m_lower: badge_html = '<span style="background-color: #1b5e20; color: #ffffff; padding: 0.2rem 0.6rem; border-radius: 4px; font-size: 11px; font-weight: bold;">🚀 グロース/新興</span>'
            else: badge_html = f'<span style="background-color: #455a64; color: #ffffff; padding: 0.2rem 0.6rem; border-radius: 4px; font-size: 11px; font-weight: bold;">{r["Market"]}</span>'
            
            t_badge = f'<span style="background-color: {r["triage_bg"]}; color: #ffffff; padding: 0.2rem 0.6rem; border-radius: 4px; font-size: 13px; display: inline-block; font-weight: bold; margin-left: 0.5rem;">🎯 優先度: {r["triage_rank"]}</span>'
            score_val = r["score"]; score_color = "#2e7d32" if score_val >= 8 else "#ff5722"; score_bg = "rgba(46, 125, 50, 0.15)" if score_val >= 8 else "rgba(255, 87, 34, 0.15)"
            score_badge = f'<span style="background-color: {score_bg}; border: 1px solid {score_color}; color: {score_color}; padding: 0.2rem 0.6rem; border-radius: 4px; font-size: 12px; font-weight: bold; margin-left: 0.5rem;">🎖️ 掟スコア: {score_val}/9</span>'
            
            swing_pct = ((r['high_4d'] - r['low_14d']) / r['low_14d']) * 100
            volatility_badge = f'<span style="background-color: #ff9800; color: #ffffff; padding: 0.2rem 0.6rem; border-radius: 4px; font-size: 11px; font-weight: bold; margin-left: 0.5rem; border: 1px solid #e65100;">⚡ 高ボラ ({swing_pct:.1f}%)</span>' if swing_pct >= (40.0 if ('プライム' in m_lower or '一部' in m_lower) else 60.0) else ""

            st.markdown(f"""
                <div style="margin-bottom: 0.8rem;">
                    <h3 style="font-size: clamp(18px, 5vw, 28px); font-weight: bold; margin: 0 0 0.3rem 0;">({c_code[:4]}) {r['Name']}</h3>
                    <div style="display: flex; flex-wrap: wrap; gap: 6px; align-items: center;">
                        {badge_html}{t_badge}{score_badge}{volatility_badge}
                        <span style="background-color: rgba(38, 166, 154, 0.15); border: 1px solid #26a69a; color: #26a69a; padding: 0.1rem 0.5rem; border-radius: 4px; font-size: 12px; margin-left: 4px;">RSI: {r["RSI"]:.1f}%</span>
                        <span style="background-color: rgba(255, 215, 0, 0.1); border: 1px solid #FFD700; color: #FFD700; padding: 0.1rem 0.5rem; border-radius: 4px; font-size: 12px;">到達度: {r['reach_rate']:.1f}%</span>
                    </div>
                </div>
            """, unsafe_allow_html=True)
            
            m_cols = st.columns([1, 1, 1, 1.2, 1.5])
            m_cols[0].metric("直近高値", f"{int(r['high_4d']):,}円")
            m_cols[1].metric("起点安値", f"{int(r['low_14d']):,}円")
            m_cols[2].metric("最新終値", f"{int(r['lc']):,}円")
            m_cols[3].metric("平均出来高", f"{int(r['avg_vol']):,}株")
            
            html_buy = f"""
            <div style="background: rgba(255, 215, 0, 0.05); padding: 0.5rem; border-radius: 8px; border: 1px solid rgba(255, 215, 0, 0.2); text-align: center;">
                <div style="font-size: 13px; color: rgba(250, 250, 250, 0.6); margin-bottom: 2px;">🎯 半値押し 買値目標</div>
                <div style="font-size: 1.8rem; font-weight: bold; color: #FFD700;">{int(r['target_buy']):,}<span style="font-size: 14px; margin-left:2px;">円</span></div>
            </div>"""
            m_cols[4].markdown(html_buy, unsafe_allow_html=True)
            st.caption(f"🏢 {r.get('Market','不明')} ｜ 🏭 {r.get('Sector','不明')}")

with tab2:
    st.markdown('<h3 style="font-size: clamp(14px, 4.5vw, 24px); margin-bottom: 1rem;">⚡ 【強襲】GC初動レーダー</h3>', unsafe_allow_html=True)
    if 'tab2_scan_results' not in st.session_state: st.session_state.tab2_scan_results = None
    col_t2_1, col_t2_2 = st.columns(2)
    rsi_limit_val = col_t2_1.number_input("RSI上限（過熱感の足切り）", step=5, key="tab2_rsi_limit", on_change=save_settings)
    vol_limit_val = col_t2_2.number_input("最低出来高（5日平均）", step=5000, key="tab2_vol_limit", on_change=save_settings)
    run_scan_t2 = st.button("🚀 全軍GC初動スキャン開始")

    if run_scan_t2:
        st.toast("🟢 強襲トリガーを確認。索敵開始！", icon="🚀")
        with st.spinner("GC初動候補を抽出中..."):
            raw = get_hist_data_cached()
            if not raw:
                st.session_state.tab2_scan_results = None
            else:
                df = clean_df(pd.DataFrame(raw))
                df['Code'] = df['Code'].astype(str)
                v_col = next((col for col in df.columns if col in ['Volume', 'AdjVo', 'Vo', 'AdjustmentVolume']), None)
                avg_vols = df.groupby('Code').tail(5).groupby('Code')[v_col].mean() if v_col else pd.Series(0, index=df['Code'].unique())

                f1_min, f1_max = float(st.session_state.f1_min), float(st.session_state.f1_max)
                f5_ipo = st.session_state.f5_ipo; f3_drop_val = float(st.session_state.f3_drop)
                m_mode = "大型" if "大型株" in st.session_state.preset_market else "中小型"
                
                if not master_df.empty:
                    m_target_codes = master_df[master_df['Market'].str.contains('|'.join(['プライム', '一部'] if m_mode=="大型" else ['スタンダード', 'グロース', '新興', 'マザーズ', 'JASDAQ', '二部']), na=False)]['Code'].unique()
                    df = df[df['Code'].isin(m_target_codes)]

                valid_codes = set(df[df['Date']==df['Date'].max()][(df['AdjC']>=f1_min) & (df['AdjC']<=f1_max)]['Code']).intersection(set(avg_vols[avg_vols>=vol_limit_val].index))
                df = df[df['Code'].isin(valid_codes)]

                if f5_ipo and not df.empty:
                    stock_min_dates = df.groupby('Code')['Date'].min()
                    df = df[df['Code'].isin(stock_min_dates[stock_min_dates <= (df['Date'].min() + pd.Timedelta(days=15))].index)]
                
                master_dict = master_df.set_index('Code')[['CompanyName', 'Market', 'Sector']].to_dict('index') if not master_df.empty else {}
                results = []
                for code, group in df.groupby('Code'):
                    if len(group) < 15: continue
                    adjc_vals, adjh_vals = group['AdjC'].values, group['AdjH'].values; lc = adjc_vals[-1]
                    if lc < adjh_vals.max() * (1 + (f3_drop_val / 100.0)): continue
                    
                    rsi, _, _, hist_vals = get_fast_indicators(adjc_vals)
                    if rsi > rsi_limit_val: continue
                    
                    gc_days = 1 if len(hist_vals)>=2 and hist_vals[-2]<0 and hist_vals[-1]>=0 else 2 if len(hist_vals)>=3 and hist_vals[-3]<0 and hist_vals[-1]>=0 else 3 if len(hist_vals)>=4 and hist_vals[-4]<0 and hist_vals[-1]>=0 else 0
                    if gc_days == 0: continue
                    
                    ma25 = group['AdjC'].rolling(window=25).mean().iloc[-1]
                    if lc < (ma25 * 0.95): continue
                    
                    t_rank, t_color, t_score, _ = get_assault_triage_info(gc_days, lc, rsi, group, is_strict=False)
                    m_i = master_dict.get(code, {})
                    results.append({
                        'Code':code, 'Name':m_i.get('CompanyName', f"銘柄 {code[:4]}"), 
                        'Market':m_i.get('Market','不明'), 'Sector':m_i.get('Sector','不明'), 
                        'lc':lc, 'RSI':rsi, 'avg_vol':int(avg_vols.get(code,0)), 'h14':adjh_vals[-14:].max(), 
                        'atr':group['AdjH'].values[-14:].max()*0.03, 'T_Rank':t_rank, 'T_Color':t_color, 'T_Score':t_score, 'GC_Days':gc_days
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
    st.markdown('<h3 style="font-size: clamp(14px, 4.5vw, 24px); margin-bottom: 1rem;">🎯 【照準】単一銘柄・精密分析スコープ</h3>', unsafe_allow_html=True)
    
    # ターゲット入力セクション
    c_in1, c_in2 = st.columns([1, 1])
    t3_target = c_in1.text_input("ターゲット銘柄コード（4桁）", key="t3_code_input", placeholder="例: 9101").strip()
    t3_mode = c_in2.radio("分析モードを選択せよ", ["🌐 【待伏】 押し目・逆張り", "⚡ 【強襲】 順張り・GC初動"], key="t3_scope_mode", horizontal=True, on_change=save_settings)
    
    t3_run = st.button("🚀 精密スキャン & 戦術シミュレーション実行", key="btn_t3_scan_full", use_container_width=True)

    if t3_run and t3_target:
        with st.spinner(f"銘柄 {t3_target} を精密ロックオン中..."):
            # 1. ヒストリカルデータ取得 (2年分)
            res = get_single_data(t3_target, yrs=2)
            if not res or not res.get("bars"):
                st.error("📡 データの取得に失敗した。コードが市場に存在するか確認せよ。")
            else:
                df_t3 = clean_df(pd.DataFrame(res["bars"]))
                df_t3 = calc_vector_indicators(df_t3)
                latest = df_t3.iloc[-1]
                prev = df_t3.iloc[-2]
                lc = latest['AdjC']
                
                # 2. 財務データ取得（スナイパー・フェッチ）
                fund = get_fundamentals(t3_target)
                
                # --- 🏅 財務ステータスパネル（ROE検閲統合・原典デザイン） ---
                if fund:
                    roe_val = fund.get('roe')
                    if roe_val is not None:
                        # 判定：ROE 10%以上を「進撃（緑）」、未満を「静観（赤）」
                        roe_color = "#2e7d32" if roe_val >= 10 else "#c62828"
                        roe_bg = "rgba(46, 125, 80, 0.15)" if roe_val >= 10 else "rgba(198, 40, 40, 0.15)"
                        roe_status = "買い（進撃）" if roe_val >= 10 else "見送り（静観）"
                        roe_icon = "✅" if roe_val >= 10 else "⚠️"
                        
                        st.markdown(f"""
                            <div style="background: {roe_bg}; border: 2px solid {roe_color}; border-radius: 12px; padding: 1.2rem; margin-bottom: 1.5rem; display: flex; align-items: center; justify-content: space-between; box-shadow: 0 4px 12px rgba(0,0,0,0.2);">
                                <div>
                                    <div style="font-size: 13px; color: #aaa; margin-bottom: 4px; font-weight: bold;">💎 財務生体スキャン</div>
                                    <div style="font-size: 22px; font-weight: 900; color: {roe_color};">{roe_icon} ROE {roe_val:.1f}% ｜ {roe_status}</div>
                                </div>
                                <div style="text-align: right; border-left: 1px solid rgba(255,255,255,0.1); padding-left: 1.5rem;">
                                    <div style="font-size: 12px; color: #888;">営業利益: <span style="color: #eee;">{int(fund.get('op', 0)):,}</span></div>
                                    <div style="font-size: 12px; color: #888;">自己資本比率: <span style="color: #eee;">{fund.get('er', 0)*100:.1f}%</span></div>
                                </div>
                            </div>
                        """, unsafe_allow_html=True)
                    else:
                        st.warning("📊 ROEデータが取得不能。テクニカル判断へ移行する。")
                else:
                    st.caption("📡 財務通信不通。波形分析のみ継続。")

                # --- 3. 掟の判定ロジック ---
                adjc = df_t3['AdjC'].values
                adjh = df_t3['AdjH'].values
                adjl = df_t3['AdjL'].values
                
                if "待伏" in t3_mode:
                    # 待伏ロジック復元
                    r4h = adjh[-4:]; high_4d = r4h.max(); g_max_idx = len(adjh) - 4 + r4h.argmax()
                    low_14d = adjl[max(0, g_max_idx - 14) : g_max_idx + 1].min()
                    push_r = st.session_state.push_r / 100.0
                    target_val = high_4d - ((high_4d - low_14d) * push_r)
                    reach_rate = (target_val / lc) * 100
                    rank, bg, _, _ = get_triage_info(latest['MACD_Hist'], prev['MACD_Hist'], latest['RSI'], lc, target_val, mode="待伏")
                    
                    target_box_html = f"""
                    <div style="background: rgba(255, 215, 0, 0.05); padding: 0.8rem; border-radius: 8px; border: 1px solid rgba(255, 215, 0, 0.3); text-align: center;">
                        <div style="font-size: 14px; color: #FFD700; margin-bottom: 4px;">🎯 待伏 買値目標</div>
                        <div style="font-size: 2rem; font-weight: bold; color: #FFD700;">{int(target_val):,}<span style="font-size: 16px; margin-left:4px;">円</span></div>
                    </div>"""
                else:
                    # 強襲ロジック復元
                    hist_vals = df_t3['MACD_Hist'].values
                    gc_days = 1 if len(hist_vals)>=2 and hist_vals[-2]<0 and hist_vals[-1]>=0 else 2 if len(hist_vals)>=3 and hist_vals[-3]<0 and hist_vals[-1]>=0 else 3 if len(hist_vals)>=4 and hist_vals[-4]<0 and hist_vals[-1]>=0 else 0
                    atr = latest['ATR']
                    h14 = adjh[-14:].max()
                    target_val = max(h14, lc + (atr * 0.5)) # 強襲トリガー価格
                    defense_p = target_val - atr
                    reach_rate = (lc / target_val) * 100
                    rank, bg, _, _ = get_assault_triage_info(gc_days, lc, latest['RSI'], df_t3)
                    
                    target_box_html = f"""
                    <div style="background: rgba(38, 166, 154, 0.05); padding: 0.8rem; border-radius: 8px; border: 1px solid rgba(38, 166, 154, 0.3); text-align: center;">
                        <div style="font-size: 14px; color: #26a69a; margin-bottom: 4px;">🎯 強襲 トリガー</div>
                        <div style="font-size: 2rem; font-weight: bold; color: #26a69a;">{int(target_val):,}<span style="font-size: 16px; margin-left:4px;">円</span></div>
                    </div>"""

                # --- 4. メイン表示セクション ---
                m_info = master_df[master_df['Code'] == str(t3_target) + "0"].iloc[0] if not master_df.empty and (str(t3_target) + "0") in master_df['Code'].values else None
                name = m_info['CompanyName'] if m_info is not None else f"銘柄 {t3_target}"
                sector = m_info['Sector'] if m_info is not None else "不明"
                market = m_info['Market'] if m_info is not None else "不明"

                st.markdown(f"""
                    <div style="margin-bottom: 1.5rem;">
                        <h2 style="font-size: clamp(24px, 5vw, 36px); font-weight: 900; margin:0;">({t3_target}) {name}</h2>
                        <div style="display: flex; flex-wrap: wrap; align-items: center; gap: 10px; margin-top: 5px;">
                            <span style="background-color: #455a64; color: #ffffff; padding: 0.2rem 0.6rem; border-radius: 4px; font-size: 12px; font-weight: bold;">{market}</span>
                            <span style="color: #888; font-size: 14px;">{sector}</span>
                            <span style="background-color: {bg}; color: #ffffff; padding: 0.2rem 0.6rem; border-radius: 4px; font-size: 14px; font-weight: bold; margin-left: 10px;">🎯 優先度: {rank}</span>
                        </div>
                    </div>
                """, unsafe_allow_html=True)

                m_cols = st.columns([1, 1, 1, 1.5])
                m_cols[0].metric("最新終値", f"{int(lc):,}円", f"{latest['AdjC'] - prev['AdjC']:.1f}円")
                m_cols[1].metric("RSI(14d)", f"{latest['RSI']:.1f}%")
                m_cols[2].metric("目標到達度", f"{reach_rate:.1f}%")
                m_cols[3].markdown(target_box_html, unsafe_allow_html=True)

                st.markdown(render_technical_radar(df_t3, target_val, st.session_state.bt_tp), unsafe_allow_html=True)

                # --- 5. 鉄の掟・詳細検閲 ---
                with st.expander("🛡️ 鉄の掟・詳細検閲報告書", expanded=True):
                    c1, c2 = st.columns(2)
                    if "待伏" in t3_mode:
                        wave_h = high_4d / low_14d if low_14d > 0 else 0
                        c1.markdown(f"🔹 **直近高値(4d):** `{int(high_4d):,}`円")
                        c1.markdown(f"🔹 **起点安値(14d):** `{int(low_14d):,}`円")
                        c1.markdown(f"🔹 **波高倍率:** `{wave_h:.2f}`倍 " + ("✅" if st.session_state.f9_min14 <= wave_h <= st.session_state.f9_max14 else "❌"))
                        days_since_high = len(adjh) - 1 - g_max_idx
                        c2.markdown(f"🔸 **高値からの経過:** `{days_since_high}`日 " + ("✅" if days_since_high <= st.session_state.limit_d else "❌"))
                        c2.markdown(f"🔸 **Wトップ検知:** " + ("⚠️ 危険" if check_double_top(df_t3.tail(30)) else "✅ 安全"))
                        c2.markdown(f"🔸 **落ちるナイフ:** " + ("⚠️ 危険" if lc/adjc[max(0, len(adjc)-4)] < 0.85 else "✅ 安全"))
                    else:
                        c1.markdown(f"🔹 **GC発生状況:** " + (f"🔥 {gc_days}日目" if gc_days > 0 else "❌ 未発生"))
                        c1.markdown(f"🔹 **14日最高値:** `{int(h14):,}`円")
                        c1.markdown(f"🔹 **ATR(14d):** `{int(atr):,}`円")
                        c2.markdown(f"🔸 **強襲防衛線:** `{int(defense_p):,}`円")
                        c2.markdown(f"🔸 **MA25乖離:** `{(lc/latest['MA25'] - 1)*100:.1f}`% " + ("✅" if lc >= latest['MA25']*0.95 else "❌"))
                        c2.markdown(f"🔸 **三尊検知:** " + ("⚠️ 危険" if check_head_shoulders(df_t3.tail(40)) else "✅ 安全"))

                # --- 6. 戦術シミュレーション計算（復元・統合） ---
                st.divider()
                st.markdown("#### ⚙️ この銘柄に対する戦術シミュレーション結果")
                
                # シミュレーション・パラメータ
                lot = st.session_state.bt_lot; tp = st.session_state.bt_tp / 100.0
                sli = st.session_state.bt_sl_i / 100.0; slc = st.session_state.bt_sl_c / 100.0
                max_d = st.session_state.bt_sell_d; lim_d = st.session_state.limit_d
                
                sim_results = []; trade_count = 0; wins = 0; total_pnl = 0
                
                # 単一銘柄の全履歴からシグナルを抽出してバックテスト
                for i in range(50, len(df_t3)-5):
                    sub = df_t3.iloc[:i+1]; cur = sub.iloc[-1]; c_vals = sub['AdjC'].values; h_vals = sub['AdjH'].values; l_vals = sub['AdjL'].values
                    entry_sig = False; t_p = 0
                    
                    if "待伏" in t3_mode:
                        # 過去時点での待伏判定
                        r4h_s = h_vals[-4:]; h4_s = r4h_s.max(); gi_s = len(h_vals)-4+r4h_s.argmax()
                        l14_s = l_vals[max(0, gi_s-14):gi_s+1].min()
                        if l14_s > 0 and h4_s/l14_s >= st.session_state.f9_min14:
                            t_p = h4_s - ((h4_s-l14_s)*push_r)
                            if cur['AdjC'] <= t_p and (len(h_vals)-1-gi_s) <= lim_d: entry_sig = True
                    else:
                        # 過去時点での強襲判定
                        h_s = sub['MACD_Hist'].values
                        gc_s = 1 if h_s[-2]<0 and h_s[-1]>=0 else 0
                        if gc_s == 1 and cur['AdjC'] >= h_vals[-14:].max():
                            t_p = cur['AdjC']; entry_sig = True

                    if entry_sig:
                        trade_count += 1
                        entry_price = cur['AdjC']; stop_price = entry_price * (1 - sli)
                        take_profit = entry_price * (1 + tp); exit_price = 0; hold = 0
                        
                        for j in range(i+1, min(i+max_d+1, len(df_t3))):
                            nxt = df_t3.iloc[j]; hold += 1
                            if nxt['AdjH'] >= take_profit: exit_price = take_profit; wins += 1; break
                            if nxt['AdjL'] <= stop_price: exit_price = stop_price; break
                            if hold >= max_d: exit_price = nxt['AdjC']; break
                            stop_price = max(stop_price, nxt['AdjC'] * (1 - slc))
                        
                        if exit_price > 0:
                            pnl = (exit_price - entry_price) * lot
                            total_pnl += pnl
                            sim_results.append({"エントリー": sub.iloc[-1]['Date'].strftime('%Y/%m/%d'), "保有": hold, "損益": pnl})

                # シミュレーション結果の表示
                if trade_count > 0:
                    c1, c2, c3, c4 = st.columns(4)
                    c1.metric("試行回数", f"{trade_count}回")
                    c2.metric("勝率", f"{(wins/trade_count)*100:.1f}%")
                    c3.metric("累積損益", f"{int(total_pnl):,}円")
                    c4.metric("期待値/回", f"{int(total_pnl/trade_count):,}円")
                    
                    if sim_results:
                        with st.expander("📝 取引履歴詳細（直近10件）"):
                            st.table(pd.DataFrame(sim_results).tail(10))
                else:
                    st.info("ℹ️ 指定された期間内に、現在の設定値で合致する過去のシグナルは見つからなかった。")

                # 7. 地雷警告 & チャート描画
                mines = check_event_mines(t3_target)
                for mine in mines: st.warning(mine)
                draw_chart(df_t3, target_val, chart_key=f"t3_chart_{t3_target}")
                        
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

with tab5:
    st.markdown('<h3 style="font-size: clamp(14px, 4.5vw, 24px); margin-bottom: 1rem;">📡 交戦モニター (全軍生存圏レーダー)</h3>', unsafe_allow_html=True)
    st.caption("※ 展開中の全部隊の現在地と防衛線を一覧表示します。")

    FRONTLINE_FILE = f"saved_frontline_{user_id}.csv"

    if 'frontline_df' not in st.session_state:
        if os.path.exists(FRONTLINE_FILE):
            try:
                temp_df = pd.read_csv(FRONTLINE_FILE)
                if "銘柄" in temp_df.columns: temp_df["銘柄"] = temp_df["銘柄"].astype(str)
                for col in ["買値", "第1利確", "第2利確", "損切", "現在値"]:
                    if col in temp_df.columns: temp_df[col] = pd.to_numeric(temp_df[col], errors='coerce')
                st.session_state.frontline_df = temp_df
            except:
                st.session_state.frontline_df = pd.DataFrame([{"銘柄": "4259", "買値": 668.0, "第1利確": 688.0, "第2利確": 714.0, "損切": 627.0, "現在値": 681.0}])
        else:
            st.session_state.frontline_df = pd.DataFrame([{"銘柄": "4259", "買値": 668.0, "第1利確": 688.0, "第2利確": 714.0, "損切": 627.0, "現在値": 681.0}])

    # --- 同期ボタン ---
    if st.button("🔄 全軍の現在値を同期 (yfinance)", use_container_width=True):
        import yfinance as yf
        updated = False
        for idx, row in st.session_state.frontline_df.iterrows():
            code = str(row['銘柄']).strip()
            if len(code) >= 4:
                try:
                    tk = yf.Ticker(code[:4] + ".T"); hist = tk.history(period="1d")
                    if not hist.empty:
                        st.session_state.frontline_df.at[idx, '現在値'] = round(hist['Close'].iloc[-1], 1)
                        updated = True
                except: pass
        if updated:
            st.session_state.frontline_df.to_csv(FRONTLINE_FILE, index=False)
            st.rerun()

    # 🚨 整数表示への強制換装
    edited_df = st.data_editor(
        st.session_state.frontline_df,
        num_rows="dynamic",
        column_config={
            "銘柄": st.column_config.TextColumn("銘柄", required=True),
            "買値": st.column_config.NumberColumn("買値", format="%d"),
            "第1利確": st.column_config.NumberColumn("第1利確", format="%d"),
            "第2利確": st.column_config.NumberColumn("第2利確", format="%d"),
            "損切": st.column_config.NumberColumn("損切", format="%d"),
            "現在値": st.column_config.NumberColumn("🔴 現在値", format="%d"),
        },
        use_container_width=True,
        key="frontline_editor"
    )

    if not edited_df.equals(st.session_state.frontline_df):
        st.session_state.frontline_df = edited_df.copy()
        edited_df.to_csv(FRONTLINE_FILE, index=False)
        st.rerun()

    st.markdown("---")
    active_squads = 0
    for index, row in edited_df.iterrows():
        ticker = str(row.get('銘柄', ''))
        if ticker.strip() == "" or pd.isna(row['買値']) or pd.isna(row['現在値']): continue
        buy = float(row['買値']); tp1 = float(row['第1利確']); tp2 = float(row['第2利確']); sl = float(row['損切']); cur = float(row['現在値'])
        active_squads += 1

        if cur <= sl: st_text, st_color, bg_rgba = "💀 被弾（防衛線突破）", "#ef5350", "rgba(239, 83, 80, 0.15)"
        elif cur < buy: st_text, st_color, bg_rgba = "⚠️ 警戒（損切ラインへ後退中）", "#ff9800", "rgba(255, 152, 0, 0.15)"
        elif tp1 > 0 and cur < tp1: st_text, st_color, bg_rgba = "🟢 巡航中（第1目標へ接近中）", "#26a69a", "rgba(38, 166, 154, 0.15)"
        elif tp2 > 0 and cur < tp2: st_text, st_color, bg_rgba = "🛡️ 第1目標到達（無敵化推奨）", "#42a5f5", "rgba(66, 165, 245, 0.15)"
        else: st_text, st_color, bg_rgba = "🏆 最終目標到達（任務完了）", "#ab47bc", "rgba(171, 71, 188, 0.15)"

        fmt = lambda x: f"¥{int(x):,}" if pd.notna(x) and x > 0 else "未設定"
        
        st.markdown(f"""
        <div style="margin-bottom: 5px;"><span style="font-size: 18px; font-weight: bold; color: #fff;">部隊 [{ticker}]</span><span style="font-size: 14px; font-weight: bold; color: {st_color}; margin-left: 15px;">{st_text}</span></div>
        <div style="display: flex; justify-content: space-between; align-items: center; background: rgba(255,255,255,0.03); padding: 12px 15px; border-radius: 8px; border-left: 5px solid {st_color};">
            <div style="flex: 1; text-align: left;"><div style="font-size: 12px; color: #ef5350;">損切</div><div style="font-size: 16px; color: #fff; font-weight: bold;">{fmt(sl)}</div></div>
            <div style="flex: 1; text-align: left;"><div style="font-size: 12px; color: #ffca28;">買値</div><div style="font-size: 16px; color: #fff; font-weight: bold;">{fmt(buy)}</div></div>
            <div style="flex: 1.5; text-align: center; background: {bg_rgba}; padding: 8px; border-radius: 6px; border: 1px solid {st_color};"><div style="font-size: 13px; color: {st_color}; font-weight: bold;">🔴 現在値</div><div style="font-size: 24px; color: #fff; font-weight: bold;">{fmt(cur)}</div></div>
            <div style="flex: 1; text-align: right;"><div style="font-size: 12px; color: #26a69a;">利確1</div><div style="font-size: 16px; color: #fff; font-weight: bold;">{fmt(tp1)}</div></div>
            <div style="flex: 1; text-align: right;"><div style="font-size: 12px; color: #42a5f5;">利確2</div><div style="font-size: 16px; color: #fff; font-weight: bold;">{fmt(tp2)}</div></div>
        </div>
        """, unsafe_allow_html=True)
        
        fig = go.Figure()
        min_x = min(sl, cur, buy) * 0.98; max_x = max(tp2 if tp2 > 0 else tp1, cur, buy) * 1.02
        fig.add_shape(type="line", x0=min_x, y0=0, x1=max_x, y1=0, line=dict(color="#444", width=2))
        fig.add_shape(type="line", x0=buy, y0=0, x1=cur, y1=0, line=dict(color="rgba(38,166,154,0.6)" if cur>=buy else "rgba(239,83,80,0.6)", width=10))
        
        points = [
            (sl, "🛡️ 損切(防衛線)", "#ef5350"),
            (buy, "🏁 買値(出撃点)", "#ffca28"),
            (tp1, "🎯 利確1(第1目標)", "#26a69a"),
            (tp2, "🏆 利確2(最終目標)", "#42a5f5")
        ]
        
        for p_val, p_name, p_color in points:
            if p_val > 0:
                fig.add_trace(go.Scatter(
                    x=[p_val], y=[0], mode="markers",
                    name=p_name, 
                    marker=dict(size=12, color=p_color),
                    hovertemplate=f"<b>{p_name}</b><br>価格: ¥%{{x:,.1f}}<extra></extra>"
                ))

        fig.add_trace(go.Scatter(
            x=[cur], y=[0], mode="markers",
            name="🔴 現在地",
            marker=dict(size=22, symbol="cross-thin", line=dict(width=3, color=st_color)),
            hovertemplate=f"<b>🔴 現在地</b><br>価格: ¥%{{x:,.1f}}<extra></extra>"
        ))
        
        fig.update_layout(
            height=80, showlegend=False, 
            yaxis=dict(showticklabels=False, range=[-1, 1]), 
            xaxis=dict(showgrid=False, range=[min_x, max_x], tickfont=dict(color="#888"), tickformat=",.0f"), 
            margin=dict(l=10, r=10, t=5, b=5), paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)', dragmode=False
        )
        st.plotly_chart(fig, use_container_width=True, config={'displayModeBar': False})
        st.markdown("<div style='margin-bottom: 25px;'></div>", unsafe_allow_html=True)

    if active_squads == 0: st.info("展開中の部隊はありません。")
        
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
