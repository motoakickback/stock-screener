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

# --- st.metric縺ｮ譁・ｭ怜・繧鯉ｼ・..・峨ｒ髦ｲ縺舌せ繝翫う繝代・繝代ャ繝・---
st.markdown("""
    <style>
    [data-testid="stMetricValue"] > div { text-overflow: clip !important; overflow: visible !important; white-space: nowrap !important; }
    [data-testid="stMetricValue"] { font-size: 1.4rem !important; }
    </style>
""", unsafe_allow_html=True)

# --- 1. 繝壹・繧ｸ險ｭ螳・& 繧ｲ繝ｼ繝医く繝ｼ繝代・ ---
st.set_page_config(page_title="謌ｦ陦薙せ繧ｳ繝ｼ繝励朱延縺ｮ謗溘・, layout="wide", page_icon="識")

ALLOWED_PASSWORDS = [p.strip() for p in st.secrets.get("APP_PASSWORD", "sniper2026").split(",")]

def check_password():
    if "password_correct" not in st.session_state:
        st.session_state["password_correct"] = False
        st.session_state["current_user"] = "" 
    if not st.session_state["password_correct"]:
        st.markdown('<h1 style="text-align: center; color: #2e7d32; margin-top: 10vh;">識 謌ｦ陦薙せ繧ｳ繝ｼ繝励朱延縺ｮ謗溘・/h1>', unsafe_allow_html=True)
        col1, col2, col3 = st.columns([1, 2, 1])
        with col2:
            with st.form("login_form"):
                password = st.text_input("Access Code", type="password", label_visibility="collapsed", placeholder="繧｢繧ｯ繧ｻ繧ｹ繧ｳ繝ｼ繝・)
                submitted = st.form_submit_button("隱崎ｨｼ (ENTER)", use_container_width=True)
                if submitted:
                    if password in ALLOWED_PASSWORDS:
                        st.session_state["password_correct"] = True
                        st.session_state["current_user"] = password 
                        st.rerun()
                    else:
                        st.error("圷 隱崎ｨｼ螟ｱ謨暦ｼ壹さ繝ｼ繝峨′驕輔＞縺ｾ縺吶・)
        return False
    return True

if not check_password(): st.stop()

# --- 噤 蜿ｸ莉､驛ｨ縺ｸ蟶ｰ驍・・繧ｿ繝ｳ ---
import streamlit.components.v1 as components
components.html(
    """
    <script>
    const parentDoc = window.parent.document;
    const oldBtn = parentDoc.getElementById('sniper-return-btn');
    if (oldBtn) { oldBtn.remove(); }
    const btn = parentDoc.createElement('button');
    btn.id = 'sniper-return-btn';
    btn.innerHTML = '噤 蜿ｸ莉､驛ｨ縺ｸ蟶ｰ驍・;
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

# --- 2. 隱崎ｨｼ繝ｻ騾壻ｿ｡險ｭ螳・---
user_id = st.session_state["current_user"]
st.markdown(f'<h1 style="font-size: clamp(24px, 7vw, 42px); font-weight: 900; border-bottom: 2px solid #2e7d32; padding-bottom: 0.5rem; margin-bottom: 1rem;">識 謌ｦ陦薙せ繧ｳ繝ｼ繝励朱延縺ｮ謗溘・<span style="font-size: 16px; font-weight: normal; color: #888;">(ID: {user_id[:4]}***)</span></h1>', unsafe_allow_html=True)

API_KEY = st.secrets.get("JQUANTS_API_KEY", "").strip()
headers = {"x-api-key": API_KEY}
BASE_URL = "https://api.jquants.com/v2"

# --- 竢ｱ・・19:00 螳悟・閾ｪ蜍輔ヱ繝ｼ繧ｸ讖滓ｧ・---
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

# --- 笞呻ｸ・繧ｷ繧ｹ繝・Β蜈ｨ菴楢ｨｭ螳壹・豌ｸ邯壼喧 ---
SETTINGS_FILE = f"saved_settings_{user_id}.json"

# --- 笞呻ｸ・繧ｷ繧ｹ繝・Β蜈ｨ菴楢ｨｭ螳壹・豌ｸ邯壼喧 ---
SETTINGS_FILE = f"saved_settings_{user_id}.json"

def load_settings():
    defaults = {
        "preset_target": "噫 荳ｭ蟆丞梛譬ｪ (50%謚ｼ縺励・讓呎ｺ・", "sidebar_tactics": "笞厄ｸ・繝舌Λ繝ｳ繧ｹ (謗滄＃謌千紫 ・・蛻ｰ驕泌ｺｦ)",
        "push_r": 50.0, "limit_d": 4, "bt_lot": 100, "bt_tp": 10, "bt_sl_i": 8, "bt_sl_c": 8, "bt_sell_d": 10,
        "f1_min": 200, "f1_max": 3000, "f2_m30": 2.0, "f3_drop": -30, "f4_mlong": 3.0,
        "f5_ipo": True, "f6_risk": True, "f7_ex_etf": True, "f8_ex_bio": True,
        "f9_min14": 1.3, "f9_max14": 2.0, "f10_ex_knife": True,
        "tab1_etf_filter": True, "tab2_rsi_limit": 75, "tab2_vol_limit": 15000, 
        "tab2_ipo_filter": True, "tab2_etf_filter": True, "t3_scope_mode": "倹 縲仙ｾ・ｼ上・謚ｼ縺礼岼繝ｻ騾・ｼｵ繧・,
        "bt_mode_sim_v2": "倹 縲仙ｾ・ｼ上鷹延縺ｮ謗・(謚ｼ縺礼岼迢呎茶)", 
        # 譁ｰ縺励￥險ｭ螳壹＠縺鬱ab4逕ｨ縺ｮ豌ｸ邯壼喧繧ｭ繝ｼ
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
    
    # 圷 菫ｮ豁｣・壽里蟄倥・險ｭ螳壹ｒ繝ｭ繝ｼ繝峨＠縺ｦ繝槭・繧ｸ縺吶ｋ・磯撼陦ｨ遉ｺ隕∫ｴ縺ｮ豸亥､ｱ繧帝亟縺宣亟陦帷ｶｲ・・
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
    preset = st.session_state.get("preset_target", "噫 荳ｭ蟆丞梛譬ｪ (50%謚ｼ縺励・讓呎ｺ・")
    tactics = st.session_state.get("sidebar_tactics", "笞厄ｸ・繝舌Λ繝ｳ繧ｹ (謗滄＃謌千紫 ・・蛻ｰ驕泌ｺｦ)")
    if "螟ｧ蝙区ｪ" in preset: st.session_state.push_r = 25.0 if "繝舌Λ繝ｳ繧ｹ" in tactics else 45.0
    elif "61.8%" in preset: st.session_state.push_r = 61.8
    else: st.session_state.push_r = 50.0
    st.session_state.sim_push_r = st.session_state.push_r
    save_settings()

# --- 研・・繝槭け繝ｭ豌苓ｱ｡繝ｬ繝ｼ繝繝ｼ・域律邨悟ｹｳ蝮・ｼ峨Δ繧ｸ繝･繝ｼ繝ｫ ---
# 縲蝉ｿｮ豁｣縲台ｸ崎ｦ√↑繝倥ャ繝繝ｼ蛛ｽ陬・ｒ謗帝勁縺励∵ｨ呎ｺ夜壻ｿ｡縺ｮ縺ｾ縺ｾTTL・医く繝｣繝・す繝･菫晄戟・峨・縺ｿ60遘偵∈遏ｭ邵ｮ
@st.cache_data(ttl=60, show_spinner=False)
def get_macro_weather():
    try:
        import yfinance as yf
        import pandas as pd
        
        # 繧ｻ繝・す繝ｧ繝ｳ蛛ｽ陬・ｒ陦後ｏ縺壹∵ｨ呎ｺ悶・縺ｾ縺ｾ蜻ｼ縺ｳ蜃ｺ縺・
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
                <div style="font-size: 14px; color: #aaa; margin-bottom: 8px;">研・・謌ｦ蝣ｴ縺ｮ螟ｩ蛟・(譌･邨悟ｹｳ蝮・</div>
                <div style="font-size: 26px; font-weight: bold; color: {color}; margin-bottom: 4px;">{ni['price']:,.2f} 蜀・/div>
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
        st.warning("笞・・螟夜Κ豌苓ｱ｡繝ｬ繝ｼ繝繝ｼ蠢懃ｭ斐↑縺励・)
        st.markdown("<div style='margin-bottom: 1.5rem;'></div>", unsafe_allow_html=True)
render_macro_board()

# --- 3. 蜈ｱ騾夐未謨ｰ & 蝨ｰ髮ｷ讀懃衍 ---
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
                alerts.append(f"張 縲仙慍髮ｷ隴ｦ謌偵大些髯ｺ繧､繝吶Φ繝域磁霑台ｸｭ・・critical_mines[c]}・・)
        except: pass

    if not event_data: return alerts

    for item in event_data.get("dividend", []):
        d_str = str(item.get("RecordDate", ""))[:10]
        if d_str:
            try:
                target_date = datetime.strptime(d_str, "%Y-%m-%d").date()
                if today_date <= target_date <= max_warning_date:
                    alerts.append(f"張 縲仙慍髮ｷ隴ｦ謌偵鷹・蠖捺ｨｩ蛻ｩ關ｽ縺｡譌･縺梧磁霑台ｸｭ ({d_str})")
                    break
            except: pass

    for item in event_data.get("earnings", []):
        if str(item.get("Code", ""))[:4] != c: continue
        d_str = str(item.get("Date", item.get("DisclosedDate", "")))[:10]
        if d_str:
            try:
                target_date = datetime.strptime(d_str, "%Y-%m-%d").date()
                if today_date <= target_date <= max_warning_date:
                    alerts.append(f"櫨 縲仙慍髮ｷ隴ｦ謌偵第ｱｺ邂礼匱陦ｨ縺梧磁霑台ｸｭ ({d_str})")
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
            df = pd.read_excel(BytesIO(r2.content), engine='xlrd')[['繧ｳ繝ｼ繝・, '驫俶氛蜷・, '33讌ｭ遞ｮ蛹ｺ蛻・, '蟶ょｴ繝ｻ蝠・刀蛹ｺ蛻・, '隕乗ｨ｡蛹ｺ蛻・]]
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

def get_triage_info(macd_hist, macd_hist_prev, rsi, lc=0, bt=0, mode="蠕・ｼ・, gc_days=0):
    if macd_hist > 0 and macd_hist_prev <= 0: macd_t = "GC逶ｴ蠕・
    elif macd_hist > macd_hist_prev: macd_t = "荳頑・諡｡螟ｧ"
    elif macd_hist < 0 and macd_hist < macd_hist_prev: macd_t = "荳玖誠邯咏ｶ・
    else: macd_t = "貂幄｡ｰ"

    if mode == "蠑ｷ隘ｲ":
        if macd_t == "荳玖誠邯咏ｶ・ or rsi >= 75: return "蝨丞､役泅ｫ", "#d32f2f", 0, macd_t
        if gc_days == 1:
            if rsi <= 50: return "S櫨", "#2e7d32", 5, "GC逶ｴ蠕・1譌･逶ｮ)"
            else: return "A笞｡", "#ed6c02", 4, "GC逶ｴ蠕・1譌･逶ｮ)"
        elif gc_days == 2:
            if rsi <= 55: return "A笞｡", "#ed6c02", 4, "GC邯咏ｶ・2譌･逶ｮ)"
            else: return "B嶋", "#0288d1", 3, "GC邯咏ｶ・2譌･逶ｮ)"
        elif gc_days >= 3:
            return "B嶋", "#0288d1", 3, f"GC邯咏ｶ・{gc_days}譌･逶ｮ)"
        else: return "C早・・, "#616161", 1, macd_t
    else:
        if bt == 0 or lc == 0: return "C早・・, "#616161", 1, macd_t
        dist_pct = ((lc / bt) - 1) * 100 
        if dist_pct < -2.0: return "蝨丞､役汳", "#d32f2f", 0, macd_t
        elif dist_pct <= 2.0:
            if rsi <= 45: return "S櫨", "#2e7d32", 5, macd_t
            else: return "A笞｡", "#ed6c02", 4.5, macd_t 
        elif dist_pct <= 5.0:
            if rsi <= 50: return "Aｪ､", "#0288d1", 4.0, macd_t 
            else: return "B嶋", "#0288d1", 3, macd_t
        else: return "C早・・, "#616161", 1, macd_t

def get_assault_triage_info(gc_days, lc, rsi_v, df_chart, is_strict=False):
    """ 蠑ｷ隘ｲ(鬆・ｼｵ繧・蟆ら畑縺ｮ繧ｹ繧ｳ繧｢繝ｪ繝ｳ繧ｰ繧ｨ繝ｳ繧ｸ繝ｳ """
    if gc_days <= 0 or df_chart is None or df_chart.empty:
        return "蝨丞､・逐", "#424242", 0, ""
        
    latest = df_chart.iloc[-1]
    ma5 = latest.get('MA5', 0)
    ma25 = latest.get('MA25', 0)
    ma75 = latest.get('MA75', 0)
    
    # 蜃ｺ譚･鬮倥・螳牙・縺ｪ蜿門ｾ・
    v_col = next((col for col in df_chart.columns if col in ['Volume', 'AdjVo', 'Vo', 'AdjustmentVolume']), None)
    vol_latest = latest[v_col] if v_col else 0
    vol_avg = df_chart[v_col].tail(5).mean() if v_col else 0

    score = 50  # GC逋ｺ蜍輔・蝓ｺ遉守せ

    # 笞厄ｸ・縲蝉ｸｭ髢灘刈轤ｹ縲禅ab2/Tab3蜈ｱ騾壹・蝓ｺ遉手ｩ穂ｾ｡
    if ma25 > 0:
        if lc >= ma25 * 0.95: score += 10  # 豐ｼ縺九ｉ縺ｮ閼ｱ蜃ｺ蛻晏虚・・10轤ｹ・・
        if lc >= ma25: score += 10         # 25譌･邱壻ｸ頑栢縺托ｼ・10轤ｹ・・
    if vol_avg > 0 and vol_latest > vol_avg * 1.5: score += 10 # 蜃ｺ譚･鬮倥・辷・匱・・10轤ｹ・・
    if 50 <= rsi_v <= 70: score += 10      # 蠑ｷ縺・ｸ頑・繝｢繝｡繝ｳ繧ｿ繝・・10轤ｹ・・

    # 逐 縲占ｶ・宍譬ｼ貂帷せ縲禅ab3・育ｲｾ蟇・せ繧ｳ繝ｼ繝暦ｼ牙ｰら畑縺ｮ蜃ｦ蛻代Ο繧ｸ繝・け
    if is_strict:
        # 繝代・繝輔ぉ繧ｯ繝医が繝ｼ繝繝ｼ縺ｮ蟠ｩ螢翫・螟ｧ蟷・ｸ帷せ・磯ｨ吶＠縺ｮ蜿ｯ閭ｽ諤ｧ螟ｧ・・
        if not (lc > ma5 > ma25 > ma75): score -= 40
        # 蜃ｺ譚･鬮倥′莨ｴ縺｣縺ｦ縺・↑縺ЖC縺ｯ繝輔ぉ繧､繧ｯ縺ｨ縺ｿ縺ｪ縺・
        if vol_avg > 0 and vol_latest <= vol_avg * 1.2: score -= 20
        # RSI驕守・(75雜・縺ｯ鬮伜､謗ｴ縺ｿ縺ｮ繝ｪ繧ｹ繧ｯ螟ｧ
        if rsi_v > 75: score -= 20

    # 識 譛邨ゅΛ繝ｳ繧ｯ蛻､螳・
    if score >= 80: rank = "S"; bg = "#d32f2f"
    elif score >= 60: rank = "A"; bg = "#f57c00"
    elif score >= 40: rank = "B"; bg = "#fbc02d"
    else: rank = "C 逐"; bg = "#424242"
    
    return rank, bg, score, "GC逋ｺ蜍穂ｸｭ"

def render_technical_radar(df, buy_price, tp_pct):
    if df.empty or len(df) < 2: return ""
    latest = df.iloc[-1]; prev = df.iloc[-2]
    rsi = latest.get('RSI', 50); macd_hist = latest.get('MACD_Hist', 0); macd_hist_prev = prev.get('MACD_Hist', 0); atr = latest.get('ATR', 0)
    rsi_color = "#ef5350" if rsi <= 30 else "#FFD700" if rsi <= 45 else "#888888"
    rsi_text = "櫨 雜・｣ｲ繧峨ｌ縺吶℃" if rsi <= 30 else "笞｡ 螢ｲ繧峨ｌ縺吶℃" if rsi <= 45 else "笞厄ｸ・荳ｭ遶・
    if rsi >= 70: rsi_color = "#26a69a"; rsi_text = "笞・・雋ｷ繧上ｌ縺吶℃"

    _, _, _, macd_t = get_triage_info(macd_hist, macd_hist_prev, rsi)

    if macd_t == "GC逶ｴ蠕・:
        macd_display = "櫨櫨櫨 豼辭ｱ GC逋ｺ蜍穂ｸｭ 櫨櫨櫨"
        macd_color = "#ff5722"
        bg_glow = "box-shadow: 0 0 15px rgba(255, 87, 34, 0.6); border: 2px solid #ff5722;"
    elif macd_t == "荳頑・諡｡螟ｧ":
        macd_display = "嶋 荳頑・諡｡螟ｧ"
        macd_color = "#ef5350"
        bg_glow = "border-left: 4px solid #FFD700;"
    elif macd_t == "荳玖誠邯咏ｶ・:
        macd_display = "悼 荳玖誠邯咏ｶ・
        macd_color = "#26a69a"
        bg_glow = "border-left: 4px solid #FFD700;"
    else:
        macd_display = "笞厄ｸ・貂幄｡ｰ"
        macd_color = "#888888"
        bg_glow = "border-left: 4px solid #FFD700;"

    days = int((buy_price * (tp_pct / 100.0)) / atr) if atr > 0 else 99
    return f"""<div style="background: rgba(255, 255, 255, 0.05); padding: 0.8rem; border-radius: 4px; margin: 1rem 0; {bg_glow}">
        <div style="font-size: 14px; color: #aaa;">藤 險亥勣繝輔Λ繧､繝・ RSI <strong style="color: {rsi_color};">{rsi:.0f}% ({rsi_text})</strong> | MACD <strong style="color: {macd_color}; font-size: 1.1em;">{macd_display}</strong> | 繝懊Λ <strong style="color: #bbb;">{atr:.0f}蜀・/strong> (蛻ｩ遒ｺ逶ｮ螳・ {days}譌･)</div></div>"""

def draw_chart(df, targ_p, tp5=None, tp10=None, tp15=None, tp20=None, chart_key=None):
    from datetime import timedelta
    df = df.copy()
    fig = go.Figure()
    fig.add_trace(go.Candlestick(x=df['Date'], open=df['AdjO'], high=df['AdjH'], low=df['AdjL'], close=df['AdjC'], name='譬ｪ萓｡', increasing_line_color='#26a69a', decreasing_line_color='#ef5350'))
    if 'MA5' in df.columns: fig.add_trace(go.Scatter(x=df['Date'], y=df['MA5'], mode='lines', name='5譌･', line=dict(color='rgba(156, 39, 176, 0.7)', width=1.5), connectgaps=True))
    if 'MA25' in df.columns: fig.add_trace(go.Scatter(x=df['Date'], y=df['MA25'], mode='lines', name='25譌･', line=dict(color='rgba(33, 150, 243, 0.7)', width=1.5), connectgaps=True))
    if 'MA75' in df.columns: fig.add_trace(go.Scatter(x=df['Date'], y=df['MA75'], mode='lines', name='75譌･', line=dict(color='rgba(255, 152, 0, 0.7)', width=1.5), connectgaps=True))
    fig.add_trace(go.Scatter(x=df['Date'], y=[targ_p]*len(df), mode='lines', name='雋ｷ蛟､逶ｮ讓・, line=dict(color='#FFD700', width=2, dash='dash')))
    last_date = df['Date'].max()
    start_date = last_date - timedelta(days=45) if len(df) > 30 else df['Date'].min()
    fig.update_layout(height=450, margin=dict(l=0, r=60, t=30, b=40), xaxis_rangeslider_visible=True, xaxis=dict(range=[start_date, last_date + timedelta(days=0.5)], type="date"), yaxis=dict(tickformat=",.0f", side="right"), paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)', hovermode="x unified", legend=dict(orientation="h", yanchor="top", y=-0.1, xanchor="center", x=0.5))
    st.plotly_chart(fig, use_container_width=True, config={'displayModeBar': True, 'displaylogo': False}, key=chart_key)

# --- 4. 繧ｵ繧､繝峨ヰ繝ｼ UI ---
st.sidebar.header("識 蟇ｾ雎｡蟶ょｴ (荳諡ｬ謠幄｣・")
st.sidebar.radio("繝励Μ繧ｻ繝・ヨ驕ｸ謚・, ["噫 荳ｭ蟆丞梛譬ｪ (50%謚ｼ縺励・讓呎ｺ・", "笞・荳ｭ蟆丞梛譬ｪ (61.8%謚ｼ縺励・豺ｱ豬ｷ)", "召 螟ｧ蝙区ｪ (25%謚ｼ縺励・繝医Ξ繝ｳ繝・"], key="preset_target", on_change=apply_market_preset)
market_filter_mode = "螟ｧ蝙・ if "螟ｧ蝙区ｪ" in st.session_state.preset_target else "荳ｭ蟆丞梛"

st.sidebar.radio("併・・謌ｦ陦薙Δ繝ｼ繝牙・譖ｿ", ["笞厄ｸ・繝舌Λ繝ｳ繧ｹ (謗滄＃謌千紫 ・・蛻ｰ驕泌ｺｦ)", "笞費ｸ・謾ｻ繧・㍾隕・(荳牙ｷ昴す繧ｰ繝翫Ν蜆ｪ蜈・", "孱・・螳医ｊ驥崎ｦ・(驩・｣√す繧ｰ繝翫Ν蜆ｪ蜈・"], key="sidebar_tactics", on_change=apply_market_preset)

st.sidebar.header("剥 繝斐ャ繧ｯ繧｢繝・・繝ｫ繝ｼ繝ｫ")
c_f1_1, c_f1_2 = st.sidebar.columns(2)
f1_min = c_f1_1.number_input("竭 荳矩剞(蜀・", step=100, key="f1_min", on_change=save_settings)
f1_max = c_f1_2.number_input("竭 荳企剞(蜀・", step=100, key="f1_max", on_change=save_settings) 
f2_m30 = st.sidebar.number_input("竭｡ 1繝ｶ譛域垓鬨ｰ荳企剞(蛟・", step=0.1, key="f2_m30", on_change=save_settings)
f3_drop = st.sidebar.number_input("竭｢ 蜊雁ｹｴ縲・蟷ｴ荳玖誠髯､螟・%)", step=5, key="f3_drop", on_change=save_settings)
f4_mlong = st.sidebar.number_input("竭｣ 荳翫￡蛻・ｊ髯､螟・蛟・", step=0.5, key="f4_mlong", on_change=save_settings)
f5_ipo = st.sidebar.checkbox("竭､ IPO髯､螟・闍ｱ蟄励さ繝ｼ繝臥ｭ・", key="f5_ipo", on_change=save_settings)
f6_risk = st.sidebar.checkbox("竭･ 逍醍ｾｩ豕ｨ險倬釜譟・勁螟・, key="f6_risk", on_change=save_settings)
f7_ex_etf = st.sidebar.checkbox("竭ｦ ETF繝ｻREIT遲峨ｒ髯､螟・, key="f7_ex_etf", on_change=save_settings)
f8_ex_bio = st.sidebar.checkbox("竭ｧ 蛹ｻ阮ｬ蜩・繝舌う繧ｪ)繧帝勁螟・, key="f8_ex_bio", on_change=save_settings)
c_f9_1, c_f9_2 = st.sidebar.columns(2)
f9_min14 = c_f9_1.number_input("竭ｨ 荳矩剞(蛟・", step=0.1, key="f9_min14", on_change=save_settings)
f9_max14 = c_f9_2.number_input("竭ｨ 荳企剞(蛟・", step=0.1, key="f9_max14", on_change=save_settings)
f10_ex_knife = st.sidebar.checkbox("竭ｩ 關ｽ縺｡繧九リ繧､繝暮勁螟・證ｴ關ｽ/騾｣邯壻ｸ玖誠)", key="f10_ex_knife", on_change=save_settings)

st.sidebar.header("識 雋ｷ縺・Ν繝ｼ繝ｫ")
push_r = st.sidebar.number_input("竭 謚ｼ縺礼岼(%)", step=0.1, format="%.1f", key="push_r", on_change=save_settings)
limit_d = st.sidebar.number_input("竭｡ 雋ｷ縺・悄髯・譌･)", step=1, key="limit_d", on_change=save_settings)
st.sidebar.number_input("竭｢ 莉ｮ諠ｳLot(譬ｪ謨ｰ)", step=100, key="bt_lot", on_change=save_settings)

st.sidebar.header("孱・・螢ｲ繧翫Ν繝ｼ繝ｫ・磯延縺ｮ謗滂ｼ・)
st.sidebar.number_input("竭 蛻ｩ遒ｺ逶ｮ讓・(+%)", step=1, key="bt_tp", on_change=save_settings)
st.sidebar.number_input("竭｡ 謳榊・/繧ｶ繝ｩ蝣ｴ (-%)", step=1, key="bt_sl_i", on_change=save_settings)
st.sidebar.number_input("竭｢ 謳榊・/邨ょ､ (-%)", step=1, key="bt_sl_c", on_change=save_settings)
st.sidebar.number_input("竭｣ 蠑ｷ蛻ｶ謦､騾/螢ｲ繧頑悄髯・(譌･)", step=1, key="bt_sell_d", on_change=save_settings)

st.sidebar.markdown("#### 圷 謗溪則・夐勁螟悶ヶ繝ｩ繝・け繝ｪ繧ｹ繝・)
GIGI_FILE = f"saved_gigi_mines_{user_id}.txt"
default_gigi = "2134, 3350, 6172, 6740, 7647, 8783, 8836, 8925, 9318"
if os.path.exists(GIGI_FILE):
    with open(GIGI_FILE, "r", encoding="utf-8") as f:
        default_gigi = f.read()

gigi_input = st.sidebar.text_area("逍醍ｾｩ豕ｨ險倥・繝懊Ο譬ｪ繧ｳ繝ｼ繝・(繧ｫ繝ｳ繝槫玄蛻・ｊ)", value=default_gigi, height=100)
with open(GIGI_FILE, "w", encoding="utf-8") as f:
    f.write(gigi_input)

extracted_codes = re.findall(r'\b\d{4}\b(?!\s*[/蟷ｴ-])', gigi_input)
gigi_mines_list = list(dict.fromkeys(extracted_codes))

st.sidebar.divider()
st.sidebar.markdown("### 屏・・繧ｷ繧ｹ繝・Β邂｡逅・)
if st.sidebar.button("閥 繧ｭ繝｣繝・す繝･蠑ｷ蛻ｶ繝代・繧ｸ (API驕・ｻｶ譎ら畑)", use_container_width=True):
    st.cache_data.clear()
    st.session_state.tab1_scan_results = None
    st.session_state.tab2_scan_results = None
    st.session_state.tab5_ifd_results = None
    st.sidebar.success("蜈ｨ險俶・繧貞ｼｷ蛻ｶ繝代・繧ｸ縺励◆縲よ怙譁ｰ繝・・繧ｿ繧貞・蜿門ｾ励☆繧九・)
    st.rerun()

# ==========================================
# 5. 繧ｿ繝門・讒区・
# ==========================================
tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs([
    "倹 縲仙ｾ・ｼ上大ｺ・沺繝ｬ繝ｼ繝繝ｼ", "笞｡ 縲仙ｼｷ隘ｲ縲賎C蛻晏虚繝ｬ繝ｼ繝繝ｼ", "識 縲千・貅悶醍ｲｾ蟇・せ繧ｳ繝ｼ繝・, 
    "笞呻ｸ・縲先ｼ皮ｿ偵第姶陦薙す繝溘Η繝ｬ繝ｼ繧ｿ", "笵ｺ 縲先姶邱壹台ｺ､謌ｦ繝｢繝九ち繝ｼ", "刀 縲先姶豁ｴ縲台ｺ､謌ｦ繝・・繧ｿ繝吶・繧ｹ"
])
master_df = load_master()
tactics_mode = st.session_state.sidebar_tactics

with tab1:
    st.markdown('<h3 style="font-size: clamp(14px, 4.5vw, 24px); margin-bottom: 1rem;">識 縲仙ｾ・ｼ上鷹延縺ｮ謗溘・蜊雁､謚ｼ縺励Ξ繝ｼ繝繝ｼ</h3>', unsafe_allow_html=True)
    if 'tab1_scan_results' not in st.session_state: st.session_state.tab1_scan_results = None
    run_scan_t1 = st.button("噫 譛譁ｰ繝・・繧ｿ縺ｧ蠕・ｼ上せ繧ｭ繝｣繝ｳ髢句ｧ・)
    exclude_etf_flag_t1 = st.sidebar.checkbox("ETF繝ｻREIT繧帝勁螟・(蠕・ｼ・", key="tab1_etf_filter", on_change=save_settings)

    if run_scan_t1:
        st.toast("泙 蠕・ｼ上ヨ繝ｪ繧ｬ繝ｼ繧堤｢ｺ隱阪らｴ｢謨ｵ髢句ｧ具ｼ・, icon="識")
        with st.spinner("蜈ｨ驫俶氛縺九ｉ繧ｵ繧､繝峨ヰ繝ｼ譚｡莉ｶ・亥・繝輔ぅ繝ｫ繧ｿ繝ｼ蜷梧悄・峨↓蜷郁・縺吶ｋ繧ｿ繝ｼ繧ｲ繝・ヨ繧堤ｴ｢謨ｵ荳ｭ..."):
            raw = get_hist_data_cached()
            if not raw:
                st.error("繝・・繧ｿ縺ｮ蜿門ｾ励↓螟ｱ謨励＠縺溘・)
                st.session_state.tab1_scan_results = None
            else:
                df = clean_df(pd.DataFrame(raw)).dropna(subset=['AdjC', 'AdjH', 'AdjL']).sort_values(['Code', 'Date'])
                v_col = next((col for col in df.columns if col in ['Volume', 'AdjVo', 'Vo', 'AdjustmentVolume']), None)
                if v_col:
                    df[v_col] = pd.to_numeric(df[v_col], errors='coerce').fillna(0)
                    avg_vols = df.groupby('Code').tail(5).groupby('Code')[v_col].mean()
                else: avg_vols = pd.Series(0, index=df['Code'].unique())

                # 圷 蜷梧悄繝代ャ繝・ｼ壺蔵 萓｡譬ｼ荳贋ｸ矩剞繝輔ぅ繝ｫ繧ｿ繝ｼ縺ｮ驕ｩ逕ｨ
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

                # 圷 蜷梧悄繝代ャ繝・ｼ壺側 IPO・井ｸ雁ｴ1蟷ｴ譛ｪ貅・蛾勁螟悶ヵ繧｣繝ｫ繧ｿ繝ｼ縺ｮ繧ｹ繝槭・繝磯←逕ｨ
                if f5_ipo and not df.empty:
                    # API縺悟叙蠕励＠縺滓怙繧ょ商縺・律莉假ｼ育ｴ・蟷ｴ蜑阪・繝斐Φ繝昴う繝ｳ繝域律・峨ｒ蝓ｺ貅悶→縺吶ｋ
                    oldest_global_date = df['Date'].min()
                    # 蜷・釜譟・′謖√▽譛蜿､縺ｮ繝・・繧ｿ譌･莉倥ｒ邂怜・
                    stock_min_dates = df.groupby('Code')['Date'].min()
                    # 蝓ｺ貅匁律縺九ｉ +15譌･ 莉･蜀・↓繝・・繧ｿ縺悟ｭ伜惠縺励※縺・ｌ縺ｰ縲・蟷ｴ蜑阪°繧我ｸ雁ｴ縺励※縺・ｋ縲阪→蛻､螳・
                    threshold_date = oldest_global_date + pd.Timedelta(days=15)
                    valid_seasoned_codes = stock_min_dates[stock_min_dates <= threshold_date].index
                    df = df[df['Code'].isin(valid_seasoned_codes)]

                if exclude_etf_flag_t1 and not master_df.empty:
                    invalid_mask = master_df['Market'].astype(str).str.contains('ETF|REIT', case=False, na=False) | master_df['Sector'].astype(str).str.contains('ETF|REIT|謚穂ｿ｡', case=False, na=False)
                    valid_codes = master_df[~invalid_mask]['Code'].unique()
                    df = df[df['Code'].isin(valid_codes)]

                if not master_df.empty:
                    if "螟ｧ蝙区ｪ" in st.session_state.preset_target: m_mask = master_df['Market'].astype(str).str.contains('繝励Λ繧､繝|荳驛ｨ', na=False)
                    else: m_mask = master_df['Market'].astype(str).str.contains('繧ｹ繧ｿ繝ｳ繝繝ｼ繝榎繧ｰ繝ｭ繝ｼ繧ｹ|譁ｰ闊・繝槭じ繝ｼ繧ｺ|JASDAQ|莠碁Κ', na=False)
                    df = df[df['Code'].isin(master_df[m_mask]['Code'].unique())]

                if st.session_state.f8_ex_bio and not master_df.empty:
                    df = df[df['Code'].isin(master_df[~master_df['Sector'].astype(str).str.contains('蛹ｻ阮ｬ蜩・, case=False, na=False)]['Code'].unique())]

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
                    
                    # 圷 蜷梧悄繝代ャ繝・ｼ壺束 關ｽ縺｡繧九リ繧､繝暮勁螟厄ｼ育峩霑・譌･髢薙〒15%莉･荳翫・閾ｴ蜻ｽ逧・垓關ｽ繧偵ヱ繝ｼ繧ｸ・・
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
                    # 竭ｨ 豕｢鬮倥ヵ繧｣繝ｫ繧ｿ繝ｼ
                    if not (min14 <= high_4d_val / low_10d_val <= max14): continue
                    
                    wave_len = high_4d_val - low_10d_val
                    if wave_len <= 0: continue
                    target_buy = high_4d_val - (wave_len * push_ratio)
                    reach_rate = (target_buy / lc) * 100

                    rsi, macd_h, macd_h_prev, _ = get_fast_indicators(adjc_vals)
                    
                    # --- 事・・謗溘せ繧ｳ繧｢縺ｮ險育ｮ・---
                    df_14 = group.tail(15).iloc[:-1]
                    df_30 = group.tail(31).iloc[:-1]
                    h14_real = df_14['AdjH'].max()
                    l14_real = df_14['AdjL'].min()
                    
                    score = 4 # 繝吶・繧ｹ轤ｹ
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
                    c_name = m_info.get('CompanyName', f"驫俶氛 {code[:4]}")
                    c_market = m_info.get('Market', '荳肴・'); c_sector = m_info.get('Sector', '荳肴・'); c_scale = m_info.get('Scale', '荳肴・')
                    rank, bg, t_score, _ = get_triage_info(macd_h, macd_h_prev, rsi, lc, target_buy, mode="蠕・ｼ・)

                    results.append({'Code': code, 'Name': c_name, 'Sector': c_sector, 'Market': c_market, 'Scale': c_scale, 'lc': lc, 'RSI': rsi, 'avg_vol': avg_vol, 'high_4d': high_4d_val, 'low_14d': low_10d_val, 'target_buy': target_buy, 'reach_rate': reach_rate, 'triage_rank': rank, 'triage_bg': bg, 't_score': t_score, 'score': score})
                        
                if not results:
                    st.warning("迴ｾ蝨ｨ縲∵次繧呈ｺ縺溘☆繧ｿ繝ｼ繧ｲ繝・ヨ縺ｯ蟄伜惠縺励↑縺・・)
                    st.session_state.tab1_scan_results = []
                else:
                    st.session_state.tab1_scan_results = sorted(results, key=lambda x: (x['t_score'], x['score']), reverse=True)[:30]
                import gc; gc.collect()

    if st.session_state.tab1_scan_results:
        light_results = st.session_state.tab1_scan_results
        st.success(f"識 蠕・ｼ上Ο繝・け繧ｪ繝ｳ: {len(light_results)} 驫俶氛繧堤｢ｺ隱阪・)
        sab_codes = " ".join([str(r.get('Code', ''))[:4] for r in light_results if str(r.get('triage_rank', '')).startswith(('S', 'A', 'B'))])
        other_codes = " ".join([str(r.get('Code', ''))[:4] for r in light_results if not str(r.get('triage_rank', '')).startswith(('S', 'A', 'B'))])
        
        st.info("搭 莉･荳九・繧ｳ繝ｼ繝峨ｒ繧ｳ繝斐・縺励※縲∫・貅厄ｼ・AB3・峨↓繝壹・繧ｹ繝亥庄閭ｽ縺縲・)
        if sab_codes:
            st.markdown("**識 蜆ｪ蜈亥ｺｦ S繝ｻA繝ｻB (荳ｻ蜉帶ｨ咏噪)**")
            st.code(sab_codes, language="text")
        if other_codes:
            with st.expander("操 蜆ｪ蜈亥ｺｦ C繝ｻ蝨丞､・(逶｣隕門ｯｾ雎｡)"):
                st.code(other_codes, language="text")
        
        for r in light_results:
            st.divider()
            c = str(r.get('Code', '0000')); n = r.get('Name', f"驫俶氛 {c[:4]}")
            m_lower = str(r.get('Market', '荳肴・')).lower()
            if '繝励Λ繧､繝' in m_lower or '荳驛ｨ' in m_lower: badge_html = '<span style="background-color: #1a237e; color: #ffffff; padding: 0.2rem 0.6rem; border-radius: 4px; font-size: 11px; font-weight: bold;">召 繝励Λ繧､繝/螟ｧ蝙・/span>'
            elif '繧ｰ繝ｭ繝ｼ繧ｹ' in m_lower or '繝槭じ繝ｼ繧ｺ' in m_lower: badge_html = '<span style="background-color: #1b5e20; color: #ffffff; padding: 0.2rem 0.6rem; border-radius: 4px; font-size: 11px; font-weight: bold;">噫 繧ｰ繝ｭ繝ｼ繧ｹ/譁ｰ闊・/span>'
            else: badge_html = f'<span style="background-color: #455a64; color: #ffffff; padding: 0.2rem 0.6rem; border-radius: 4px; font-size: 11px; font-weight: bold;">{r.get("Market")}</span>'
            
            triage_badge = f'<span style="background-color: {r.get("triage_bg")}; color: #ffffff; padding: 0.2rem 0.6rem; border-radius: 4px; font-size: 13px; display: inline-block; font-weight: bold; margin-left: 0.5rem;">識 蜆ｪ蜈亥ｺｦ: {r.get("triage_rank")}</span>'
            
            score_val = r.get("score", 0)
            score_color = "#2e7d32" if score_val >= 7 else "#ff5722"
            score_bg = "rgba(46, 125, 50, 0.15)" if score_val >= 7 else "rgba(255, 87, 34, 0.15)"
            score_badge = f'<span style="background-color: {score_bg}; border: 1px solid {score_color}; color: {score_color}; padding: 0.2rem 0.6rem; border-radius: 4px; font-size: 12px; font-weight: bold; margin-left: 0.5rem;">事・・謗溘せ繧ｳ繧｢: {score_val}/9</span>'
            
            swing_pct = ((r.get('high_4d', 0) - r.get('low_14d', 0)) / r.get('low_14d', 1)) * 100
            volatility_badge = f'<span style="background-color: #ff9800; color: #ffffff; padding: 0.2rem 0.6rem; border-radius: 4px; font-size: 11px; font-weight: bold; margin-left: 0.5rem; border: 1px solid #e65100;">笞｡ 鬮倥・繝ｩ ({swing_pct:.1f}%)</span>' if swing_pct >= (40.0 if ('繝励Λ繧､繝' in m_lower or '荳驛ｨ' in m_lower) else 60.0) else ""

            st.markdown(f"""
                <div style="margin-bottom: 0.8rem;">
                    <h3 style="font-size: clamp(18px, 5vw, 28px); font-weight: bold; margin: 0 0 0.3rem 0;">({c[:4]}) {n}</h3>
                    <div style="display: flex; flex-wrap: wrap; gap: 6px; align-items: center;">
                        {badge_html}{triage_badge}{score_badge}{volatility_badge}
                        <span style="background-color: rgba(38, 166, 154, 0.15); border: 1px solid #26a69a; color: #26a69a; padding: 0.1rem 0.5rem; border-radius: 4px; font-size: 12px; margin-left: 4px;">RSI: {r.get("RSI", 50):.1f}%</span>
                        <span style="background-color: rgba(255, 215, 0, 0.1); border: 1px solid #FFD700; color: #FFD700; padding: 0.1rem 0.5rem; border-radius: 4px; font-size: 12px;">蛻ｰ驕泌ｺｦ: {r.get('reach_rate'):.1f}%</span>
                    </div>
                </div>
            """, unsafe_allow_html=True)
            
            m_cols = st.columns([1, 1, 1, 1.2, 1.5])
            m_cols[0].metric("逶ｴ霑鷹ｫ伜､", f"{int(r.get('high_4d', 0)):,}蜀・)
            m_cols[1].metric("襍ｷ轤ｹ螳牙､", f"{int(r.get('low_14d', 0)):,}蜀・)
            m_cols[2].metric("譛譁ｰ邨ょ､", f"{int(r.get('lc', 0)):,}蜀・)
            m_cols[3].metric("蟷ｳ蝮・・譚･鬮・5譌･)", f"{int(r.get('avg_vol', 0)):,}譬ｪ")
            html_buy = f"""
            <div style="background: rgba(255, 215, 0, 0.05); padding: 0.5rem; border-radius: 8px; border: 1px solid rgba(255, 215, 0, 0.2); text-align: center;">
                <div style="font-size: 13px; color: rgba(250, 250, 250, 0.6); margin-bottom: 2px;">識 蜊雁､謚ｼ縺・雋ｷ蛟､逶ｮ讓・/div>
                <div style="font-size: 1.8rem; font-weight: bold; color: #FFD700;">{int(r.get('target_buy', 0)):,}<span style="font-size: 14px; margin-left:2px;">蜀・/span></div>
            </div>"""
            m_cols[4].markdown(html_buy, unsafe_allow_html=True)
            st.caption(f"召 {r.get('Market','荳肴・')} ・・少 {r.get('Sector','荳肴・')}")

with tab2:
    st.markdown('<h3 style="font-size: clamp(14px, 4.5vw, 24px); margin-bottom: 1rem;">笞｡ 縲仙ｼｷ隘ｲ縲賎C蛻晏虚繝ｬ繝ｼ繝繝ｼ</h3>', unsafe_allow_html=True)
    if 'tab2_scan_results' not in st.session_state: st.session_state.tab2_scan_results = None
    col_t2_1, col_t2_2 = st.columns(2)
    rsi_limit = col_t2_1.number_input("RSI荳企剞・磯℃辭ｱ諢溘・雜ｳ蛻・ｊ・・, step=5, key="tab2_rsi_limit", on_change=save_settings)
    vol_limit = col_t2_2.number_input("譛菴主・譚･鬮假ｼ・譌･蟷ｳ蝮・ｼ・, step=5000, key="tab2_vol_limit", on_change=save_settings)
    
    run_scan_t2 = st.button("噫 蜈ｨ霆宏C蛻晏虚繧ｹ繧ｭ繝｣繝ｳ髢句ｧ・, key="btn_assault_scan")
    exclude_ipo_flag = st.sidebar.checkbox("IPO驫俶氛繧帝勁螟・(蠑ｷ隘ｲ)", key="tab2_ipo_filter", on_change=save_settings)
    exclude_etf_flag_t2 = st.sidebar.checkbox("ETF繝ｻREIT繧帝勁螟・(蠑ｷ隘ｲ)", key="tab2_etf_filter", on_change=save_settings)

    if run_scan_t2:
        st.toast("泙 蠑ｷ隘ｲ繝医Μ繧ｬ繝ｼ繧堤｢ｺ隱阪らｴ｢謨ｵ髢句ｧ具ｼ・, icon="噫")
        with st.spinner("蜈ｨ驫俶氛縺ｮ豕｢蠖｢縺九ｉGC蛻晏虚蛟呵｣懊ｒ謚ｽ蜃ｺ荳ｭ..."):
            raw = get_hist_data_cached()
            if not raw:
                st.error("繝・・繧ｿ縺ｮ蜿門ｾ励↓螟ｱ謨励＠縺溘・)
            else:
                df = clean_df(pd.DataFrame(raw)).dropna(subset=['AdjC', 'AdjH', 'AdjL']).sort_values(['Code', 'Date'])
                v_col = next((col for col in df.columns if col in ['Volume', 'AdjVo', 'Vo', 'AdjustmentVolume']), None)
                if v_col:
                    df[v_col] = pd.to_numeric(df[v_col], errors='coerce').fillna(0)
                    avg_vols = df.groupby('Code').tail(5).groupby('Code')[v_col].mean()
                else: avg_vols = pd.Series(0, index=df['Code'].unique())

                # 圷 蜷梧悄繝代ャ繝・ｼ壺蔵 萓｡譬ｼ荳贋ｸ矩剞繝輔ぅ繝ｫ繧ｿ繝ｼ縺ｮ驕ｩ逕ｨ
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

                # 圷 蜷梧悄繝代ャ繝・ｼ壺側 IPO・井ｸ雁ｴ1蟷ｴ譛ｪ貅・蛾勁螟悶ヵ繧｣繝ｫ繧ｿ繝ｼ
                if f5_ipo and not df.empty:
                    oldest_global_date = df['Date'].min()
                    stock_min_dates = df.groupby('Code')['Date'].min()
                    threshold_date = oldest_global_date + pd.Timedelta(days=15)
                    valid_seasoned_codes = stock_min_dates[stock_min_dates <= threshold_date].index
                    df = df[df['Code'].isin(valid_seasoned_codes)]

                # 圷 蜷梧悄繝代ャ繝・ｼ壺即 ETF繝ｻREIT遲峨ｒ髯､螟・
                if exclude_etf_flag_t2 and not master_df.empty:
                    invalid_mask = master_df['Market'].astype(str).str.contains('ETF|REIT', case=False, na=False) | master_df['Sector'].astype(str).str.contains('ETF|REIT|謚穂ｿ｡', case=False, na=False)
                    df = df[df['Code'].isin(master_df[~invalid_mask]['Code'].unique())]

                # 圷 蜷梧悄繝代ャ繝・ｼ壺息 蛹ｻ阮ｬ蜩・繝舌う繧ｪ)繧帝勁螟・
                if f8_ex_bio and not master_df.empty:
                    df = df[df['Code'].isin(master_df[~master_df['Sector'].astype(str).str.contains('蛹ｻ阮ｬ蜩・, case=False, na=False)]['Code'].unique())]

                # 圷 蜷梧悄繝代ャ繝・ｼ壼ｯｾ雎｡蟶ょｴ・亥､ｧ蝙・荳ｭ蟆丞梛・峨・驕ｩ逕ｨ
                if not master_df.empty:
                    if "螟ｧ蝙区ｪ" in st.session_state.preset_target: m_mask = master_df['Market'].astype(str).str.contains('繝励Λ繧､繝|荳驛ｨ', na=False)
                    else: m_mask = master_df['Market'].astype(str).str.contains('繧ｹ繧ｿ繝ｳ繝繝ｼ繝榎繧ｰ繝ｭ繝ｼ繧ｹ|譁ｰ闊・繝槭じ繝ｼ繧ｺ|JASDAQ|莠碁Κ', na=False)
                    df = df[df['Code'].isin(master_df[m_mask]['Code'].unique())]

                # 圷 蜷梧悄繝代ャ繝・ｼ壺則 逍醍ｾｩ豕ｨ險倬釜譟・勁螟厄ｼ医ヶ繝ｩ繝・け繝ｪ繧ｹ繝磯←逕ｨ・・
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
                    
                    # 圷 菫ｮ豁｣・壼ｼｷ隘ｲ繝ｭ繧ｸ繝・け逕ｨ ATR縺翫ｈ縺ｳ14譌･鬮伜､縺ｮ邂怜・
                    if len(adjh_vals) >= 14:
                        h14 = adjh_vals[-14:].max()
                        # 邁｡譏鄭TR(14d)縺ｮ邂怜・
                        h_v = adjh_vals[-14:]; l_v = adjl_vals[-14:]; c_prev_v = adjc_vals[-15:-1]
                        tr = np.maximum(h_v - l_v, np.maximum(abs(h_v - c_prev_v), abs(l_v - c_prev_v)))
                        atr_val = tr.mean()
                    else:
                        h14 = lc; atr_val = lc * 0.03 # 莠亥ｙ險育ｮ・

                    latest_ma25 = sum(adjc_vals[-25:]) / 25 if len(adjc_vals) >= 25 else 0
                    if latest_ma25 > 0 and lc < (latest_ma25 * 0.95): continue

                    dummy_df = pd.DataFrame([{'MA5': 0, 'MA25': latest_ma25, 'MA75': 0, 'Volume': 0}])
                    t_rank, t_color, t_score, t_macd = get_assault_triage_info(gc_days, lc, rsi, dummy_df, is_strict=False)
                        
                    m_info = master_dict.get(code, {})
                    c_name = m_info.get('CompanyName', f"驫俶氛 {code[:4]}")
                    c_market = m_info.get('Market', '荳肴・'); c_sector = m_info.get('Sector', '荳肴・')
                    scale_val = str(m_info.get('Scale', ''))
                    c_scale = "召 螟ｧ蝙・荳ｭ蝙・ if any(x in scale_val for x in ["Core30", "Large70", "Mid400"]) else "噫 蟆丞梛/譁ｰ闊・

                    results.append({'Code': code, 'Name': c_name, 'Sector': c_sector, 'Market': c_market, 'Scale': c_scale, 'lc': lc, 'RSI': rsi, 'avg_vol': avg_vol, 'h14': h14, 'atr': atr_val, 'T_Rank': t_rank, 'T_Color': t_color, 'T_Score': t_score, 'GC_Days': gc_days})
                        
                if not results:
                    st.warning("迴ｾ蝨ｨ縲；C蛻晏虚譚｡莉ｶ繧呈ｺ縺溘☆繧ｿ繝ｼ繧ｲ繝・ヨ縺ｯ蟄伜惠縺励↑縺・・)
                    st.session_state.tab2_scan_results = []
                else:
                    st.session_state.tab2_scan_results = sorted(results, key=lambda x: (-x['T_Score'], x['GC_Days'], x['RSI']))[:30]
                import gc; gc.collect()

    if st.session_state.tab2_scan_results:
        light_results = st.session_state.tab2_scan_results
        st.success(f"笞｡ 蠑ｷ隘ｲ繝ｭ繝・け繧ｪ繝ｳ: GC蛻晏虚(3譌･莉･蜀・ 荳贋ｽ・{len(light_results)} 驫俶氛繧堤｢ｺ隱阪・)
        sab_codes = " ".join([str(r.get('Code', ''))[:4] for r in light_results if str(r.get('T_Rank', '')).startswith(('S', 'A', 'B'))])
        
        st.info("搭 莉･荳九・繧ｳ繝ｼ繝峨ｒ繧ｳ繝斐・縺励※縲∫・貅厄ｼ・AB3・峨↓繝壹・繧ｹ繝亥庄閭ｽ縺縲・)
        if sab_codes:
            st.markdown("**識 蜆ｪ蜈亥ｺｦ S繝ｻA繝ｻB (荳ｻ蜉帶ｨ咏噪)**")
            st.code(sab_codes, language="text")
        
        for r in light_results:
            st.divider()
            lc_val = r.get('lc', 0); h14_val = r.get('h14', 0); atr_v = r.get('atr', 0)
            
            # 圷 蜍慕噪繝ｭ繧ｸ繝・け驕ｩ逕ｨ・壹ヨ繝ｪ繧ｬ繝ｼ縺ｨ髦ｲ陦帷ｷ・
            t_price = max(h14_val, lc_val + (atr_v * 0.5))
            d_price = t_price - atr_v

            triage_badge = f'<span style="background-color: {r.get("T_Color", "#616161")}; color: #ffffff; padding: 0.2rem 0.6rem; border-radius: 4px; font-size: 13px; display: inline-block; font-weight: bold; margin-left: 0.5rem;">識 蜆ｪ蜈亥ｺｦ: {r.get("T_Rank")}</span>'
            
            st.markdown(f"""
                <div style="margin-bottom: 0.8rem;">
                    <h3 style="font-size: 24px; font-weight: bold; margin: 0 0 0.3rem 0;">({str(r['Code'])[:4]}) {r['Name']}</h3>
                    <div style="display: flex; gap: 4px; align-items: center;">
                        {triage_badge}
                        <span style="background-color: rgba(237, 108, 2, 0.15); border: 1px solid #ed6c02; color: #ed6c02; padding: 0.1rem 0.5rem; border-radius: 4px; font-size: 12px;">GC蠕・{r.get('GC_Days')}譌･逶ｮ</span>
                    </div>
                </div>
            """, unsafe_allow_html=True)
            
            m_cols = st.columns([1, 1, 1, 1.2, 1.5])
            m_cols[0].metric("譛譁ｰ邨ょ､", f"{int(lc_val):,}蜀・)
            m_cols[1].metric("RSI", f"{r.get('RSI', 50):.1f}%")
            m_cols[2].metric("ATR(14d)", f"{int(atr_v):,}蜀・)
            
            html_sl = f"""<div style="background: rgba(239, 83, 80, 0.05); padding: 0.5rem; border-radius: 8px; border: 1px solid rgba(239, 83, 80, 0.3); text-align: center;">
                <div style="font-size: 13px; color: rgba(250, 250, 250, 0.6); margin-bottom: 2px;">孱・・蜍慕噪髦ｲ陦帷ｷ・(-1.0 ATR)</div>
                <div style="font-size: 1.6rem; font-weight: bold; color: #ef5350;">{int(d_price):,}<span style="font-size: 14px; margin-left:2px;">蜀・/span></div></div>"""
            m_cols[3].markdown(html_sl, unsafe_allow_html=True)

            html_buy_assault = f"""<div style="background: rgba(255, 215, 0, 0.05); padding: 0.5rem; border-radius: 8px; border: 1px solid rgba(255, 215, 0, 0.2); text-align: center;">
                <div style="font-size: 13px; color: rgba(250, 250, 250, 0.6); margin-bottom: 2px;">識 蠑ｷ隘ｲ繝医Μ繧ｬ繝ｼ (14d鬮伜､蝓ｺ貅・</div>
                <div style="font-size: 1.6rem; font-weight: bold; color: #FFD700;">{int(t_price):,}<span style="font-size: 14px; margin-left:2px;">蜀・/span></div></div>"""
            m_cols[4].markdown(html_buy_assault, unsafe_allow_html=True)

with tab3:
    st.markdown('<h3 style="font-size: clamp(14px, 4.5vw, 24px); margin-bottom: 1rem;">識 縲千・貅悶醍ｲｾ蟇・せ繧ｳ繝ｼ繝暦ｼ域姶陦灘挨繝ｻ迢ｬ遶狗ｴ｢謨ｵ・・/h3>', unsafe_allow_html=True)
    
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
        scope_mode = st.radio("識 隗｣譫舌Δ繝ｼ繝峨ｒ驕ｸ謚・, ["倹 縲仙ｾ・ｼ上・謚ｼ縺礼岼繝ｻ騾・ｼｵ繧・, "笞｡ 縲仙ｼｷ隘ｲ縲・繝医Ξ繝ｳ繝峨・鬆・ｼｵ繧・], key="t3_scope_mode", on_change=save_settings)
        is_ambush = "蠕・ｼ・ in scope_mode
        st.markdown("---")
        if is_ambush:
            watch_in = st.text_area("倹 縲仙ｾ・ｼ上台ｸｻ蜉帷屮隕夜Κ髫・, value=st.session_state.t3_am_watch, height=120)
            daily_in = st.text_area("倹 縲仙ｾ・ｼ上第悽譌･譁ｰ隕城Κ髫・, value=st.session_state.t3_am_daily, height=120)
        else:
            watch_in = st.text_area("笞｡ 縲仙ｼｷ隘ｲ縲台ｸｻ蜉帷屮隕夜Κ髫・, value=st.session_state.t3_as_watch, height=120)
            daily_in = st.text_area("笞｡ 縲仙ｼｷ隘ｲ縲第悽譌･譁ｰ隕城Κ髫・, value=st.session_state.t3_as_daily, height=120)
        run_scope = st.button("鉢 陦ｨ遉ｺ荳ｭ縺ｮ驛ｨ髫翫ｒ邊ｾ蟇・せ繧ｭ繝｣繝ｳ", use_container_width=True, type="primary")
        
    with col_s2:
        st.markdown("#### 剥 邏｢謨ｵ繧ｹ繝・・繧ｿ繧ｹ")
        if is_ambush: st.info("繝ｻ縲仙ｾ・ｼ丞ｰら畑縲大濠蛟､謚ｼ縺励・鮟・≡豈斐〒縺ｮ霑取茶蛻､螳・)
        else: st.warning("繝ｻ縲仙ｼｷ隘ｲ蟆ら畑縲羨TR/14譌･鬮伜､繝吶・繧ｹ縺ｮ蜍慕噪繝悶Ξ繧､繧ｯ繧｢繧ｦ繝亥愛螳・)

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
        
        if not t_codes:
            st.warning("譛牙柑縺ｪ驫俶氛繧ｳ繝ｼ繝峨′遒ｺ隱阪〒縺阪∪縺帙ｓ縲・)
        else:
            with st.spinner(f"蜈ｨ {len(t_codes)} 驫俶氛繧堤ｲｾ蟇・ｨ育ｮ嶺ｸｭ..."):
                scope_results = []
                for c in t_codes:
                    api_code = c if len(c) == 5 else c + "0"
                    raw_s = get_single_data(api_code, 1)
                    if not raw_s: continue
                    df_s = clean_df(pd.DataFrame(raw_s.get("bars", [])))
                    if len(df_s) < 30: continue
                        
                    # 圷 菫ｮ豁｣・夐Κ蛻・ｸ閾ｴ(contains)繧貞ｻ・ｭ｢縺励∝ｮ悟・荳閾ｴ(==)縺ｾ縺溘・isin縺ｧ遒ｺ螳溘↓迚ｹ螳・
                    c_short = c[:4]
                    if not master_df.empty:
                        # 4譯√〒繧・譯√〒繧ら｢ｺ螳溘↓繝槭ャ繝√☆繧句ｮ悟・荳閾ｴ讀懃ｴ｢
                        m_row = master_df[master_df['Code'].astype(str).isin([c_short, c_short + "0", api_code])]
                    else:
                        m_row = pd.DataFrame()
                    
                    if not m_row.empty:
                        # 遒ｺ螳溘↓譛蛻昴・1莉ｶ縺ｮ繝・・繧ｿ繧貞叙蠕・
                        c_name = str(m_row.iloc[0]['CompanyName'])
                        c_market = str(m_row.iloc[0]['Market'])
                        # 讌ｭ遞ｮ(Sector)縺檎ｩｺ縲√∪縺溘・NaN縺ｮ蝣ｴ蜷医↓縲御ｸ肴・縲阪ｒ蝗樣∩
                        raw_sector = m_row.iloc[0].get('Sector', '荳肴・')
                        c_sector = str(raw_sector) if pd.notna(raw_sector) and raw_sector != "" else "諠・ｱ繝ｻ騾壻ｿ｡讌ｭ" # 6580遲峨・謨第ｸ域蒔鄂ｮ
                    else:
                        c_name = f"驫俶氛 {c_short}"; c_market = "荳肴・"; c_sector = "荳肴・"

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
                        rank, bg, score, macd_t = get_triage_info(latest.get('MACD_Hist', 0), prev.get('MACD_Hist', 0), rsi_v, lc, bt_val, mode="蠕・ｼ・)
                        reach_val = ((h14 - lc) / (h14 - bt_val) * 100) if (h14 - bt_val) > 0 else 0
                    else:
                        bt_val = int(max(h14, lc + (atr_val * 0.5)))
                        hist_vals = df_chart['MACD_Hist'].tail(5).values
                        if hist_vals[-2] < 0 and hist_vals[-1] >= 0: gc_days = 1
                        elif hist_vals[-3] < 0 and hist_vals[-2] >= 0 and hist_vals[-1] >= 0: gc_days = 2
                        elif hist_vals[-4] < 0 and hist_vals[-3] >= 0 and hist_vals[-2] >= 0 and hist_vals[-1] >= 0: gc_days = 3
                        rank, bg, score, macd_t = get_assault_triage_info(gc_days, lc, rsi_v, df_chart, is_strict=True)
                        reach_val = 100 - rsi_v

                    scope_results.append({
                        'code': c, 'name': c_name, 'market': c_market, 'sector': c_sector,
                        'lc': lc, 'h14': h14, 'l14': l14, 'ur': ur, 
                        'bt_val': bt_val, 'is_bt_broken': is_bt_broken, 'is_trend_broken': is_trend_broken, 
                        'is_dt': is_dt, 'is_hs': is_hs, 'is_db': is_db, 'gc_days': gc_days, 'rank': rank, 'bg': bg, 'score': score, 
                        'reach_val': reach_val, 'atr_val': atr_val, 'rsi': rsi_v, 'df_chart': df_chart,
                        'source': "孱・・逶｣隕・ if c in watch_in else "噫 譁ｰ隕・
                    })
                
                scope_results = sorted(scope_results, key=lambda x: (x['score'], x['reach_val']), reverse=True)
                
                # --- 陦ｨ遉ｺ繝ｫ繝ｼ繝・---
                for r in scope_results:
                    st.divider()
                    source_color = "#42a5f5" if "逶｣隕・ in r['source'] else "#ffa726"
                    m_lower = str(r['market']).lower()
                    
                    if '繝励Λ繧､繝' in m_lower or '荳驛ｨ' in m_lower: 
                        badge_html = '<span style="background-color: #1a237e; color: #ffffff; padding: 0.2rem 0.6rem; border-radius: 4px; font-size: 11px; font-weight: bold;">召 繝励Λ繧､繝/螟ｧ蝙・/span>'
                    elif '繧ｰ繝ｭ繝ｼ繧ｹ' in m_lower or '繝槭じ繝ｼ繧ｺ' in m_lower: 
                        badge_html = '<span style="background-color: #1b5e20; color: #ffffff; padding: 0.2rem 0.6rem; border-radius: 4px; font-size: 11px; font-weight: bold;">噫 繧ｰ繝ｭ繝ｼ繧ｹ/譁ｰ闊・/span>'
                    else: 
                        badge_html = f'<span style="background-color: #455a64; color: #ffffff; padding: 0.2rem 0.6rem; border-radius: 4px; font-size: 11px; font-weight: bold;">{r["market"]}</span>'

                    s_badge = f"<span style='background-color:{source_color}; color:white; padding:2px 6px; border-radius:4px; font-size:12px;'>{r['source']}</span>"
                    t_badge = f"<span style='background-color:{r['bg']}; color:white; padding:2px 8px; border-radius:4px; margin-left:10px; font-weight:bold;'>識 蜆ｪ蜈亥ｺｦ: {r['rank']}</span>"
                    
                    st.markdown(f"""
                        <div style="margin-bottom: 0.8rem;">
                            <h3 style="font-size: clamp(18px, 5vw, 28px); font-weight: bold; margin: 0 0 0.3rem 0;">{s_badge} ({r['code'][:4]}) {r['name']}</h3>
                            <div style="display: flex; flex-wrap: wrap; gap: 6px; align-items: center;">
                                {badge_html}{t_badge}
                                <span style="background-color: rgba(38, 166, 154, 0.15); border: 1px solid #26a69a; color: #26a69a; padding: 0.1rem 0.5rem; border-radius: 4px; font-size: 12px;">RSI: {r['rsi']:.1f}%</span>
                                <span style="background-color: rgba(255, 215, 0, 0.1); border: 1px solid #FFD700; color: #FFD700; padding: 0.1rem 0.5rem; border-radius: 4px; font-size: 12px;">蛻ｰ驕泌ｺｦ: {r['reach_val']:.1f}%</span>
                            </div>
                        </div>
                    """, unsafe_allow_html=True)
                    
                    if r['is_dt'] or r['is_hs']: st.error("圷 縲占ｭｦ蜻翫醍嶌蝣ｴ霆｢謠帙・蜊ｱ髯ｺ豕｢蠖｢・井ｸ牙ｰ・W繝医ャ繝暦ｼ峨ｒ讀懃衍縲よ彫騾繧呈耳螂ｨ縲・)
                    if not is_ambush and r['gc_days'] > 0: st.success(f"櫨 縲触C逋ｺ蜍輔閃ACD繧ｴ繝ｼ繝ｫ繝・Φ繧ｯ繝ｭ繧ｹ縺九ｉ {r['gc_days']}譌･逶ｮ")
                    
                    c_base = r['bt_val'] if is_ambush else r['lc']
                    sc_left, sc_mid, sc_right = st.columns([2.5, 3.5, 5.0])
                    
                    with sc_left:
                        # 圷 霑ｽ蜉・哂TR蛟､縺ｮ險育ｮ励→繝懊Λ繝・ぅ繝ｪ繝・ぅ縺ｮ邂怜・
                        atr_v = r.get('atr_val', 0)
                        # 荳・′荳ATR縺悟叙蠕励〒縺阪↑縺・ｴ蜷医・螳牙・陬・ｽｮ・育ｵょ､縺ｮ5%・・
                        if atr_v == 0: atr_v = r.get('lc', 0) * 0.05 
                        atr_pct = (atr_v / r.get('lc', 1)) * 100 if r.get('lc', 0) > 0 else 0

                        # 譌｢蟄倥・險亥勣鄒､・育ｶｭ謖・ｼ・
                        c_m1, c_m2 = st.columns(2)
                        c_m1.metric("逶ｴ霑鷹ｫ伜､", f"{int(r['h14']):,}蜀・)
                        c_m2.metric("逶ｴ霑大ｮ牙､", f"{int(r['l14']):,}蜀・)
                        
                        c_m3, c_m4 = st.columns(2)
                        c_m3.metric("荳頑・蟷・, f"{int(r['ur']):,}蜀・)
                        c_m4.metric("譛譁ｰ邨ょ､", f"{int(r['lc']):,}蜀・)
                        
                        # 圷 霑ｽ蜉・哂TR・磯｢ｨ騾溯ｨ茨ｼ峨ｒ迢ｬ遶九＠縺溷､ｧ縺阪↑險亥勣縺ｨ縺励※驟咲ｽｮ
                        st.metric("謙・・1ATR (1譌･縺ｮ蟷ｳ蝮・､蟷・", f"{int(atr_v):,}蜀・, f"繝懊Λ繝・ぅ繝ｪ繝・ぅ: {atr_pct:.1f}%", delta_color="off")
                        
                        st.caption(f"少 讌ｭ遞ｮ: {r.get('sector','荳肴・')}")
                    with sc_mid:
                        if is_ambush:
                            html_box = f"<div style='background:rgba(255,215,0,0.05); padding:1rem; border-radius:8px; border:1px solid rgba(255,215,0,0.3); text-align:center;'><div style='font-size:14px;'>識 雋ｷ蛟､逶ｮ讓・/div><div style='font-size:2.4rem; font-weight:bold; color:#FFD700;'>{int(r['bt_val']):,}蜀・/div></div>"
                        else:
                            t_p = r['bt_val']; e_p = int(t_p + (r['atr_val'] * 0.2)); d_p = int(t_p - r['atr_val'])
                            html_box = f"""<div style='background:rgba(255,215,0,0.05); padding:1rem; border-radius:8px; border:1px solid rgba(255,215,0,0.3);'>
                                <div style='font-size:13px; text-align:center;'>識 繝医Μ繧ｬ繝ｼ (14d鬮伜､蝓ｺ貅・</div>
                                <div style='font-size:2.2rem; font-weight:bold; color:#FFD700; text-align:center;'>{int(t_p):,}蜀・/div>
                                <div style='border-top:1px dashed #444; margin:8px 0;'></div>
                                <div style='display:flex; justify-content:space-between;'><span>笞費ｸ・蝓ｷ陦・+0.2ATR)</span><span style='color:#FFD700; font-weight:bold;'>{int(e_p):,}蜀・/span></div>
                                <div style='display:flex; justify-content:space-between;'><span>孱・・髦ｲ陦・-1.0ATR)</span><span style='color:#ef5350; font-weight:bold;'>{int(d_p):,}蜀・/span></div></div>"""
                        st.markdown(html_box, unsafe_allow_html=True)

                    with sc_right:
                        c_target = r['bt_val'] if is_ambush else r['bt_val']
                        atr_v = r.get('atr_val', 0)
                        if atr_v == 0: atr_v = c_target * 0.05 # 莠亥ｙ險育ｮ・
                        
                        # 圷 譁ｰ繝ｭ繧ｸ繝・け・壼崋螳夲ｼ・ｒ蟒・ｭ｢縺励、TR縺ｮ蛟肴焚・医・繝ｫ繝√・繝ｫ・峨〒繧ｿ繝ｼ繧ｲ繝・ヨ繧堤函謌・
                        tp_multipliers = [0.5, 1.0, 2.0, 3.0]
                        sl_multipliers = [0.5, 1.0, 2.0]

                        # 蛻､螳壹↓蠢懊§縺滓耳螂ｨ繧ｿ繝ｼ繧ｲ繝・ヨ縺ｮ閾ｪ蜍暮∈謚・
                        is_aggressive = any(mark in r['rank'] for mark in ["笞｡", "櫨", "S"])
                        rec_tps = [2.0, 3.0] if is_aggressive else [0.5, 1.0]

                        html_matrix = f"<div style='background:rgba(255,255,255,0.05); padding:1.2rem; border-radius:8px; border-left:5px solid #FFD700;'><div style='font-size:14px; color:#aaa; margin-bottom:12px; border-bottom:1px solid #444; padding-bottom:4px;'>投 蜍慕噪ATR繝槭ヨ繝ｪ繧ｯ繧ｹ (蝓ｺ貅・{int(c_target):,}蜀・| 1ATR:{int(atr_v):,}蜀・</div><div style='display:flex; gap:30px;'>"
                        
                        # 縲仙茜遒ｺ蛻励・
                        html_matrix += "<div style='flex:1;'><div style='color:#26a69a; border-bottom:2px solid #26a69a; margin-bottom:8px;'>縲仙茜遒ｺ逶ｮ螳峨・/div>"
                        for m in tp_multipliers:
                            p_val = int(c_target + (atr_v * m))
                            pct_val = ((p_val / c_target) - 1) * 100 if c_target > 0 else 0
                            
                            if m in rec_tps:
                                # 識 謗ｨ螂ｨ蛟､縺ｮ繝上う繝ｩ繧､繝・I
                                html_matrix += f"<div style='display:flex; justify-content:space-between; margin-bottom:4px; background:rgba(38,166,154,0.15); border:1px solid #26a69a; border-radius:4px; padding:2px 6px;'><span style='color:#80cbc4; font-weight:bold;'>+{m}ATR <span style='font-size:10px;'>({pct_val:.1f}%)</span> <span style='font-size:10px; background:#26a69a; color:white; padding:1px 4px; border-radius:2px; margin-left:2px;'>謗ｨ螂ｨ</span></span><b style='font-size:1.1rem; color:#fff;'>{p_val:,}</b></div>"
                            else:
                                html_matrix += f"<div style='display:flex; justify-content:space-between; margin-bottom:4px; padding:3px 6px;'><span>+{m}ATR <span style='font-size:10px; color:#888;'>({pct_val:.1f}%)</span></span><b style='font-size:1.1rem;'>{p_val:,}</b></div>"
                        html_matrix += "</div>"

                        # 縲先錐蛻・・縲・
                        html_matrix += "<div style='flex:1;'><div style='color:#ef5350; border-bottom:2px solid #ef5350; margin-bottom:8px;'>縲宣亟陦帷岼螳峨・/div>"
                        for m in sl_multipliers:
                            l_val = int(c_target - (atr_v * m))
                            pct_val = (1 - (l_val / c_target)) * 100 if c_target > 0 else 0
                            
                            if m == 1.0:
                                # 孱・・邨ｶ蟇ｾ髦ｲ陦帷ｷ夲ｼ・1.0 ATR・峨・蝗ｺ螳壹ワ繧､繝ｩ繧､繝・I
                                html_matrix += f"<div style='display:flex; justify-content:space-between; margin-bottom:4px; background:rgba(239,83,80,0.15); border:1px solid #ef5350; border-radius:4px; padding:2px 6px;'><span style='color:#ef9a9a; font-weight:bold;'>-{m}ATR <span style='font-size:10px;'>({pct_val:.1f}%)</span> <span style='font-size:10px; background:#ef5350; color:white; padding:1px 4px; border-radius:2px; margin-left:2px;'>驩・援</span></span><b style='font-size:1.1rem; color:#fff;'>{l_val:,}</b></div>"
                            else:
                                html_matrix += f"<div style='display:flex; justify-content:space-between; margin-bottom:4px; padding:3px 6px;'><span>-{m}ATR <span style='font-size:10px; color:#888;'>({pct_val:.1f}%)</span></span><b style='font-size:1.1rem;'>{l_val:,}</b></div>"
                        html_matrix += "</div></div></div>"
                        
                        st.markdown(html_matrix, unsafe_allow_html=True)
                        
                        # 圷 霑ｽ蜉・壹・繝医Μ繧ｯ繧ｹ縺ｮ逶ｴ荳九↓髢矩哩蠑上・蜃｡萓具ｼ医ぎ繧､繝会ｼ峨ｒ險ｭ鄂ｮ
                        with st.expander("邃ｹ・・ATR繝槭ヨ繝ｪ繧ｯ繧ｹ 蜃｡萓具ｼ亥推逶ｮ螳峨・謌ｦ陦鍋噪諢丞袖・・):
                            st.markdown("""
                            <div style="font-size: 13px; color: #ccc;">
                            <strong>縲仙茜遒ｺ縺ｮ逶ｮ螳峨・/strong><br>
                            <span style="color: #80cbc4;">+0.5ATR・・/span> 雜・洒譛溘せ繧ｭ繝｣繝ｫ繝斐Φ繧ｰ縲ゅヮ繧､繧ｺ繧・ｰ丞渚逋ｺ縺ｧ遒ｺ螳溘↓繧ゅ℃蜿悶ｋ縲・br>
                            <span style="color: #80cbc4;">+1.0ATR・・/span> 繝・う繝医Ξ縲・豕翫・譌･蛻・・讓呎ｺ也噪縺ｪ豕｢繧呈拷縺医ｋ蝣・ｮ溘↑繝ｩ繧､繝ｳ縲・br>
                            <span style="color: #80cbc4;">+2.0ATR・・/span> 繧ｹ繧､繝ｳ繧ｰ・域焚譌･・峨ゅヨ繝ｬ繝ｳ繝臥ｶ咏ｶ壽凾縺ｮ讓呎ｺ悶ょ享邇・→蛻ｩ逶翫・鮟・≡豈斐・br>
                            <span style="color: #80cbc4;">+3.0ATR・・/span> 蠑ｷ繝医Ξ繝ｳ繝峨・讌ｵ縺ｿ縲ら洒譛溽噪縺ｪ縲碁℃辭ｱ・郁ｲｷ繧上ｌ縺吶℃・峨阪・髯千阜轤ｹ縲・br><br>
                            <strong>縲宣亟陦帙・逶ｮ螳峨・/strong><br>
                            <span style="color: #ef9a9a;">-0.5ATR・・/span> 讌ｵ蟆上Μ繧ｹ繧ｯ縲ゅ◆縺縺玲律荳ｭ縺ｮ繝弱う繧ｺ縺ｧ迢ｩ繧峨ｌ繧具ｼ郁ｪ､逋ｺ轣ｫ・臥｢ｺ邇・′鬮倥＞縲・br>
                            <span style="color: #ef9a9a;">-1.0ATR・・/span> <strong>讓呎ｺ夜亟陦帷ｷ壹・/strong>繝悶Ξ繧､繧ｯ繧｢繧ｦ繝医′譏守｢ｺ縺ｫ螟ｱ謨励＠縺溘→蛻､譁ｭ縺吶ｋ謦､騾轤ｹ縲・br>
                            <span style="color: #ef9a9a;">-2.0ATR・・/span> 繧ｹ繧､繝ｳ繧ｰ逕ｨ縲よｷｱ繧√・謚ｼ縺礼岼繧定ｨｱ螳ｹ縺吶ｋ縺後∝牡繧後ｌ縺ｰ繝医Ξ繝ｳ繝牙ｮ悟・蟠ｩ螢翫・
                            </div>
                            """, unsafe_allow_html=True)
                        
with tab4:
    st.markdown('<h3 style="font-size: clamp(14px, 4.5vw, 24px); margin-bottom: 1rem;">笞呻ｸ・謌ｦ陦薙す繝溘Η繝ｬ繝ｼ繧ｿ (2蟷ｴ髢薙・繝舌ャ繧ｯ繝・せ繝・</h3>', unsafe_allow_html=True)
    
    # --- 圷 繧ｻ繝ｼ繝輔ユ繧｣繝ｻ繧ｬ繝ｼ繝会ｼ壼・譛溷､縺ｨ繝｢繝ｼ繝牙・譖ｿ譎ゅ・謖吝虚蛻ｶ蠕｡ ---
    if "bt_mode_sim_v2" not in st.session_state:
        st.session_state.bt_mode_sim_v2 = "倹 縲仙ｾ・ｼ上鷹延縺ｮ謗・(謚ｼ縺礼岼迢呎茶)"

    current_mode = st.session_state.bt_mode_sim_v2
    if "prev_mode_for_defaults" not in st.session_state:
        st.session_state.prev_mode_for_defaults = current_mode

    # 繝｢繝ｼ繝牙・譖ｿ譎ゅ・縲瑚ｲｷ縺・悄髯舌埼｣蜍包ｼ亥ｼｷ隘ｲ=3譌･ / 蠕・ｼ・4譌･・・
    if st.session_state.prev_mode_for_defaults != current_mode:
        if "蠕・ｼ・ in current_mode:
            st.session_state.sim_sell_d_val = 10
            st.session_state.sim_limit_d_val = 4
        else:
            st.session_state.sim_sell_d_val = 5
            st.session_state.sim_limit_d_val = 3
        st.session_state.prev_mode_for_defaults = current_mode

    # JSON縺ｫ縲・縲阪′菫晏ｭ倥＆繧後※縺励∪縺｣縺溷ｴ蜷医・閾ｪ蜍穂ｿｮ蠕ｩ・医Μ繧ｫ繝舌Μ繝ｼ・・
    if st.session_state.get("sim_tp_val", 0) == 0: st.session_state.sim_tp_val = 10
    if st.session_state.get("sim_sl_val", 0) == 0: st.session_state.sim_sl_val = 8
    if st.session_state.get("sim_limit_d_val", 0) == 0: st.session_state.sim_limit_d_val = 4
    if st.session_state.get("sim_sell_d_val", 0) == 0: st.session_state.sim_sell_d_val = 10
    if st.session_state.get("sim_push_r_val", 0) == 0: st.session_state.sim_push_r_val = st.session_state.get("push_r", 50.0)
    if st.session_state.get("sim_pass_req_val", 0) == 0: st.session_state.sim_pass_req_val = 7
    if st.session_state.get("sim_rsi_lim_ambush_val", 0) == 0: st.session_state.sim_rsi_lim_ambush_val = 45
    if st.session_state.get("sim_rsi_lim_assault_val", 0) == 0: st.session_state.sim_rsi_lim_assault_val = 70
    if st.session_state.get("sim_time_risk_val", 0) == 0: st.session_state.sim_time_risk_val = 5
    
    # 繝励Μ繧ｻ繝・ヨ・医し繧､繝峨ヰ繝ｼ・峨・螟画峩繧呈､懃衍縺励※騾｣蜍・
    current_sidebar_push_r = st.session_state.get("push_r", 50.0)
    if "last_sidebar_push_r" not in st.session_state or st.session_state.last_sidebar_push_r != current_sidebar_push_r:
        st.session_state.sim_push_r_val = current_sidebar_push_r
        st.session_state.last_sidebar_push_r = current_sidebar_push_r

    # 圷 蜿梧婿蜷大酔譛滓ｩ滓ｧ具ｼ售tore(螳溘ョ繝ｼ繧ｿ) -> UI逕ｨKey 縺ｸ蛟､繧貞ｼｷ蛻ｶ繧ｻ繝・ヨ (騾｣蜍募撫鬘後・螳悟・隗｣豎ｺ)
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
        st.markdown("剥 **讀懆ｨｼ謌ｦ陦・*")
        st.radio("謌ｦ陦薙Δ繝ｼ繝・, ["倹 縲仙ｾ・ｼ上鷹延縺ｮ謗・(謚ｼ縺礼岼迢呎茶)", "笞｡ 縲仙ｼｷ隘ｲ縲賎C繝悶Ξ繧､繧ｯ繧｢繧ｦ繝・(鬆・ｼｵ繧・"], key="bt_mode_sim_v2")
        bt_c_in = st.text_area("驫俶氛繧ｳ繝ｼ繝・, value=default_t4, height=100, key="bt_codes_sim_v2")
        run_bt = st.button("櫨 莉ｮ諠ｳ螳溷ｼｾ繝・せ繝亥ｮ溯｡・, use_container_width=True)
        optimize_bt = st.button("噫 謌ｦ陦薙・鮟・≡豈皮紫繧呈歓蜃ｺ (譛驕ｩ蛹・", use_container_width=True)
        
    with col_b2:
        st.markdown("#### 笞呻ｸ・謌ｦ陦薙ヱ繝ｩ繝｡繝ｼ繧ｿ繝ｼ・域ｼ皮ｿ堤畑繝√Η繝ｼ繝九Φ繧ｰ・・)
        st.info("窶ｻ 謌ｦ陦灘・譖ｿ譎ゅ∝｣ｲ繧頑悄髯舌・閾ｪ蜍輔〒縲悟ｾ・ｼ・10譌･ / 蠑ｷ隘ｲ:5譌･縲阪↓蜀崎｣・｡ｫ縺輔ｌ縺ｾ縺吶・)
        cp1, cp2, cp3, cp4 = st.columns(4)
        
        # 圷 UI -> Store 縺ｸ縺ｮ蜷梧悄繧ｳ繝ｼ繝ｫ繝舌ャ繧ｯ (value螻樊ｧ繧貞炎髯､縺励∫ｴ皮ｲ九↓key縺ｧ迥ｶ諷九ｒ邂｡逅・
        def sync_param(ui_key, store_key):
            st.session_state[store_key] = st.session_state[ui_key]
            save_settings()

        cp1.number_input("識 蛻ｩ遒ｺ逶ｮ讓・%)", step=1, key="_ui_tp", on_change=sync_param, args=("_ui_tp", "sim_tp_val"))
        cp2.number_input("孱・・謳榊・逶ｮ螳・%)", step=1, key="_ui_sl", on_change=sync_param, args=("_ui_sl", "sim_sl_val"))
        cp3.number_input("竢ｳ 雋ｷ縺・悄髯・譌･)", step=1, key="_ui_lim", on_change=sync_param, args=("_ui_lim", "sim_limit_d_val"))
        cp4.number_input("竢ｳ 螢ｲ繧頑悄髯・譌･)", step=1, key="_ui_sell", on_change=sync_param, args=("_ui_sell", "sim_sell_d_val"))
        
        st.divider()
        if "蠕・ｼ・ in st.session_state.bt_mode_sim_v2:
            st.markdown("##### 倹 縲仙ｾ・ｼ上代す繝溘Η繝ｬ繝ｼ繧ｿ蝗ｺ譛芽ｨｭ螳・)
            ct1, ct2, ct3 = st.columns(3)
            ct1.number_input("悼 謚ｼ縺礼岼蠕・■(%)", step=0.1, format="%.1f", key="_ui_push", on_change=sync_param, args=("_ui_push", "sim_push_r_val"))
            ct2.number_input("謗溘け繝ｪ繧｢隕∵ｱよ焚", step=1, max_value=9, min_value=1, key="_ui_req", on_change=sync_param, args=("_ui_req", "sim_pass_req_val"))
            ct3.number_input("RSI荳企剞 (驕守・諢・", step=5, key="_ui_rsi_am", on_change=sync_param, args=("_ui_rsi_am", "sim_rsi_lim_ambush_val"))
        else:
            st.markdown("##### 笞｡ 縲仙ｼｷ隘ｲ縲代す繝溘Η繝ｬ繝ｼ繧ｿ蝗ｺ譛芽ｨｭ螳・)
            ct1, ct2 = st.columns(2)
            ct1.number_input("RSI荳企剞 (驕守・諢・", step=5, key="_ui_rsi_as", on_change=sync_param, args=("_ui_rsi_as", "sim_rsi_lim_assault_val"))
            ct2.number_input("譎る俣繝ｪ繧ｹ繧ｯ荳企剞・亥芦驕比ｺ域Φ譌･謨ｰ・・, step=1, key="_ui_risk", on_change=sync_param, args=("_ui_risk", "sim_time_risk_val"))

    if (run_bt or optimize_bt) and bt_c_in:
        with open(T4_FILE, "w", encoding="utf-8") as f: f.write(bt_c_in)
        t_codes = list(dict.fromkeys([c.upper() for c in re.findall(r'(?<![a-zA-Z0-9])[a-zA-Z0-9]{4}(?![a-zA-Z0-9])', bt_c_in)]))
        
        if not t_codes: st.warning("譛牙柑縺ｪ繧ｳ繝ｼ繝峨′隕九▽縺九ｊ縺ｾ縺帙ｓ縲・)
        else:
            sim_tp = float(st.session_state.sim_tp_val)
            sim_sl_i = float(st.session_state.sim_sl_val)
            sim_limit_d = int(st.session_state.sim_limit_d_val)
            sim_sell_d = int(st.session_state.sim_sell_d_val)
            sim_push_r = float(st.session_state.sim_push_r_val)

            is_ambush = "蠕・ｼ・ in st.session_state.bt_mode_sim_v2
            if is_ambush:
                sim_pass_req = int(st.session_state.sim_pass_req_val)
                sim_rsi_lim_ambush = int(st.session_state.sim_rsi_lim_ambush_val)
                p1_range = range(25, 66, 5) if optimize_bt else [sim_push_r]
                p2_range = range(5, 10, 1) if optimize_bt else [sim_pass_req]
                p1_name, p2_name = "Push邇・%)", "隕∵ｱ４core"
            else:
                sim_rsi_lim_assault = int(st.session_state.sim_rsi_lim_assault_val)
                sim_time_risk = int(st.session_state.sim_time_risk_val)
                p1_range = range(30, 85, 5) if optimize_bt else [sim_rsi_lim_assault]
                p2_range = range(3, 16, 1) if optimize_bt else [int(sim_tp)]
                p1_name, p2_name = "RSI荳企剞(%)", "蛻ｩ遒ｺ逶ｮ讓・%)"
            
            with st.spinner("繝・・繧ｿ繧偵・繝ｪ繝ｭ繝ｼ繝我ｸｭ・磯ｫ倬溷喧蜃ｦ逅・ｼ・.."):
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
                st.error("隗｣譫仙庄閭ｽ縺ｪ繝・・繧ｿ縺悟叙蠕励〒縺阪∪縺帙ｓ縺ｧ縺励◆縲・)
                st.stop()
                
            opt_results = []
            total_iterations = len(p1_range) * len(p2_range)
            current_iter = 0
            p_bar = st.progress(0, f"謌ｦ陦捺怙驕ｩ蛹悶・邱丞ｽ薙◆繧頑､懆ｨｼ荳ｭ... ({p1_name} ﾃ・{p2_name})")

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
                                                # 圷 譁ｰ繝ｭ繧ｸ繝・け・壼崋螳・%繧貞ｻ・ｭ｢縺励・4譌･鬮伜､ or ATR蝓ｺ貅悶・蜍慕噪繝悶Ξ繧､繧ｯ縺ｫ螟画峩
                                                eval_h14 = df.iloc[max(0, idx_eval-14):idx_eval]['AdjH'].max()
                                                eval_atr = df.iloc[idx_eval].get('ATR', 0)
                                                eval_c = df.iloc[idx_eval]['AdjC']
                                                # 鬮伜､繧呈栢縺代ｋ縺九∵里縺ｫ鬮伜､蝨上↑繧陰TR縺ｮ蜊雁・繧剃ｸ頑栢縺代◆菴咲ｽｮ繧偵ヨ繝ｪ繧ｬ繝ｼ縺ｨ縺吶ｋ
                                                trigger_price = eval_h14 if eval_h14 > eval_c else eval_c + (eval_atr * 0.5)
                                                break
                                    
                                    if gc_triggered and rsi_prev <= t_p1 and exp_days < sim_time_risk:
                                        if td['AdjH'] >= trigger_price:
                                            # 圷 譁ｰ繝ｭ繧ｸ繝・け・壼濤陦悟､縺ｮ荳企剞繧・Trigger + (ATR * 0.2) 縺ｨ縺吶ｋ
                                            exec_limit = trigger_price + (atr_prev * 0.2)
                                            exec_p = min(max(td['AdjO'], trigger_price), exec_limit)
                                            pos = {'b_i': i, 'b_d': td['Date'], 'b_p': exec_p, 'entry_atr': atr_prev, 'trigger': trigger_price}
                                            
                            else:
                                bp = pos['b_p']; held = i - pos['b_i']; sp = 0
                                current_tp = sim_tp if is_ambush else t_p2
                                e_atr = pos.get('entry_atr', prev.get('ATR', 0))
                                t_price = pos.get('trigger', bp)
                                
                                # 圷 譁ｰ繝ｭ繧ｸ繝・け・夐亟陦帷ｷ・謳榊・)繧但TR繝吶・繧ｹ・医ヨ繝ｪ繧ｬ繝ｼ縺九ｉ -1.0 ATR・峨↓謠幄｣・
                                sl_val = t_price - (e_atr * 1.0)
                                tp_val = bp * (1 + (current_tp / 100.0)) # 蛻ｩ遒ｺ縺ｯ蠕捺擂縺ｮ%譛驕ｩ蛹也岼讓吶ｒ邯ｭ謖・
                                
                                if td['AdjL'] <= sl_val: sp = min(td['AdjO'], sl_val)
                                elif td['AdjH'] >= tp_val: sp = max(td['AdjO'], tp_val)
                                elif held >= sim_sell_d: sp = td['AdjC']
                                
                                if sp > 0:
                                    sp = round(sp, 1); p_pct = round(((sp / bp) - 1) * 100, 2)
                                    p_amt = int((sp - bp) * st.session_state.bt_lot)
                                    all_t.append({'驫俶氛': c, '雉ｼ蜈･譌･': pos['b_d'], '豎ｺ貂域律': td['Date'], '菫晄怏譌･謨ｰ': held, '雋ｷ蛟､(蜀・': int(bp), '螢ｲ蛟､(蜀・': int(sp), '謳咲寢(%)': p_pct, '謳咲寢鬘・蜀・': p_amt})
                                    pos = None
                                    
                    if all_t:
                        p_df = pd.DataFrame(all_t)
                        total_p = p_df['謳咲寢鬘・蜀・'].sum()
                        win_r = len(p_df[p_df['謳咲寢鬘・蜀・'] > 0]) / len(p_df)
                        opt_results.append({p1_name: t_p1, p2_name: t_p2, '邱丞粋蛻ｩ逶・蜀・': total_p, '蜍晉紫': win_r, '蜿門ｼ募屓謨ｰ': len(all_t)})
                    p_bar.progress(current_iter / total_iterations)
            
            # 圷 菫ｮ豁｣・壹・繝ｭ繧ｰ繝ｬ繧ｹ繝舌・豸亥悉縺ｨ邨先棡蜃ｺ蜉帙・繧､繝ｳ繝・Φ繝医ｒ繝ｫ繝ｼ繝励・縲悟､悶阪∈螳悟・遘ｻ蜍・
            p_bar.empty()

            if optimize_bt and opt_results:
                st.markdown(f"### 醇 {st.session_state.bt_mode_sim_v2.split()[1]}繝ｻ譛驕ｩ蛹悶Ξ繝昴・繝・)
                opt_df = pd.DataFrame(opt_results).sort_values('邱丞粋蛻ｩ逶・蜀・', ascending=False)
                best = opt_df.iloc[0]
                c1, c2, c3 = st.columns(3)
                c1.metric(f"謗ｨ螂ｨ {p1_name}", f"{int(best[p1_name])} " + ("%" if is_ambush else ""))
                c2.metric(f"謗ｨ螂ｨ {p2_name}", f"{int(best[p2_name])} " + ("轤ｹ" if is_ambush else "%"))
                c3.metric("譛溷ｾ・享邇・, f"{round(best['蜍晉紫']*100, 1)} %")
                st.write("#### 投 繝代Λ繝｡繝ｼ繧ｿ繝ｼ蛻･蜿守寢繝偵・繝医・繝・・・井ｸ贋ｽ・0驕ｸ・・)
                st.dataframe(opt_df.head(10).style.format({'邱丞粋蛻ｩ逶・蜀・': '{:,}', '蜍晉紫': '{:.2%}'}), use_container_width=True, hide_index=True)
                if is_ambush: st.info(f"庁 縲先耳螂ｨ謌ｦ陦薙醍樟蝨ｨ縺ｮ蝨ｰ蜷医＞縺ｧ縺ｯ縲・ｫ伜､縺九ｉ {int(best[p1_name])}% 縺ｮ謚ｼ縺礼岼菴咲ｽｮ縺ｫ謖・､繧貞ｱ暮幕縺励∵次繧ｹ繧ｳ繧｢ {int(best[p2_name])}轤ｹ 莉･荳翫〒霑取茶縺吶ｋ縺ｮ縺梧怙繧よ悄蠕・､縺碁ｫ倥＞縺ｨ隗｣譫舌＆繧後∪縺吶・)
            elif run_bt:
                if not opt_results: st.warning("謖・ｮ壹＆繧後◆譛滄俣繝ｻ譚｡莉ｶ縺ｧ繧ｷ繧ｰ繝翫Ν轤ｹ轣ｯ・育ｴ・ｮ夲ｼ峨・遒ｺ隱阪〒縺阪∪縺帙ｓ縺ｧ縺励◆縲・)
                else:
                    tdf = pd.DataFrame(all_t).sort_values('豎ｺ貂域律').reset_index(drop=True)
                    tdf['邏ｯ遨肴錐逶・蜀・'] = tdf['謳咲寢鬘・蜀・'].cumsum()
                    st.success("識 繝舌ャ繧ｯ繝・せ繝亥ｮ御ｺ・・)
                    import plotly.express as px
                    fig_eq = px.line(tdf, x='豎ｺ貂域律', y='邏ｯ遨肴錐逶・蜀・', markers=True, title="腸 莉ｮ諠ｳ雉・肇謗ｨ遘ｻ (Equity Curve)", color_discrete_sequence=["#FFD700"])
                    fig_eq.update_layout(paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0.1)', margin=dict(l=20, r=20, t=40, b=20))
                    st.plotly_chart(fig_eq, use_container_width=True)
                    
                    n_prof = tdf['謳咲寢鬘・蜀・'].sum()
                    prof_color = "#26a69a" if n_prof > 0 else "#ef5350"
                    st.markdown(f'<h3 style="color: {prof_color};">邱丞粋蛻ｩ逶企｡・ {n_prof:,} 蜀・/h3>', unsafe_allow_html=True)
                    
                    m1, m2, m3, m4 = st.columns(4)
                    tot = len(tdf); wins = len(tdf[tdf['謳咲寢鬘・蜀・'] > 0])
                    m1.metric("繝医Ξ繝ｼ繝牙屓謨ｰ", f"{tot} 蝗・)
                    m2.metric("蜍晉紫", f"{round((wins/tot)*100,1)} %")
                    m3.metric("蟷ｳ蝮・錐逶企｡・, f"{int(n_prof/tot):,} 蜀・ if tot > 0 else "0 蜀・)
                    sloss = abs(tdf[tdf['謳咲寢鬘・蜀・'] <= 0]['謳咲寢鬘・蜀・'].sum())
                    m4.metric("PF", round(tdf[tdf['謳咲寢鬘・蜀・'] > 0]['謳咲寢鬘・蜀・'].sum() / sloss, 2) if sloss > 0 else 'inf')
                    
                    def color_pnl_tab4(val):
                        if isinstance(val, (int, float)):
                            color = '#26a69a' if val > 0 else '#ef5350' if val < 0 else 'white'
                            return f'color: {color}; font-weight: bold;'
                        return ''
                    
                    styled_tdf = tdf.drop(columns=['邏ｯ遨肴錐逶・蜀・']).style.map(color_pnl_tab4, subset=['謳咲寢鬘・蜀・', '謳咲寢(%)']).format({'雋ｷ蛟､(蜀・': '{:,}', '螢ｲ蛟､(蜀・': '{:,}', '謳咲寢鬘・蜀・': '{:,}', '謳咲寢(%)': '{:.2f}'})
                    st.dataframe(styled_tdf, use_container_width=True, hide_index=True)

with tab5:
    st.markdown('<h3 style="font-size: clamp(14px, 4.5vw, 24px); margin-bottom: 1rem;">藤 莠､謌ｦ繝｢繝九ち繝ｼ (蜈ｨ霆咲函蟄伜恟繝ｬ繝ｼ繝繝ｼ)</h3>', unsafe_allow_html=True)
    st.caption("窶ｻ 螻暮幕荳ｭ縺ｮ蜈ｨ驛ｨ髫奇ｼ医・繧ｸ繧ｷ繝ｧ繝ｳ・峨・迴ｾ蝨ｨ蝨ｰ縺ｨ髦ｲ陦帷ｷ壹ｒ荳隕ｧ陦ｨ遉ｺ縺励∵姶螻繧剃ｿｯ迸ｰ縺励∪縺吶・)

    FRONTLINE_FILE = f"saved_frontline_{user_id}.csv"

    if 'frontline_df' not in st.session_state:
        if os.path.exists(FRONTLINE_FILE):
            try:
                temp_df = pd.read_csv(FRONTLINE_FILE)
                if "驫俶氛" in temp_df.columns:
                    temp_df["驫俶氛"] = temp_df["驫俶氛"].astype(str)
                for col in ["雋ｷ蛟､", "隨ｬ1蛻ｩ遒ｺ", "隨ｬ2蛻ｩ遒ｺ", "謳榊・", "迴ｾ蝨ｨ蛟､"]:
                    if col in temp_df.columns:
                        temp_df[col] = pd.to_numeric(temp_df[col], errors='coerce')
                st.session_state.frontline_df = temp_df
            except:
                st.session_state.frontline_df = pd.DataFrame([
                    {"驫俶氛": "4259", "雋ｷ蛟､": 650.0, "隨ｬ1蛻ｩ遒ｺ": 688.0, "隨ｬ2蛻ｩ遒ｺ": 714.0, "謳榊・": 627.0, "迴ｾ蝨ｨ蛟､": 670.0},
                    {"驫俶氛": "4691", "雋ｷ蛟､": 1588.0, "隨ｬ1蛻ｩ遒ｺ": 1635.0, "隨ｬ2蛻ｩ遒ｺ": 1635.0, "謳榊・": 1508.0, "迴ｾ蝨ｨ蛟､": 1600.0},
                    {"驫俶氛": "3137", "雋ｷ蛟､": 267.0, "隨ｬ1蛻ｩ遒ｺ": 260.0, "隨ｬ2蛻ｩ遒ｺ": 267.0, "謳榊・": 248.0, "迴ｾ蝨ｨ蛟､": 254.0}
                ])
        else:
            st.session_state.frontline_df = pd.DataFrame([
                {"驫俶氛": "4259", "雋ｷ蛟､": 650.0, "隨ｬ1蛻ｩ遒ｺ": 688.0, "隨ｬ2蛻ｩ遒ｺ": 714.0, "謳榊・": 627.0, "迴ｾ蝨ｨ蛟､": 670.0},
                {"驫俶氛": "4691", "雋ｷ蛟､": 1588.0, "隨ｬ1蛻ｩ遒ｺ": 1635.0, "隨ｬ2蛻ｩ遒ｺ": 1635.0, "謳榊・": 1508.0, "迴ｾ蝨ｨ蛟､": 1600.0},
                {"驫俶氛": "3137", "雋ｷ蛟､": 267.0, "隨ｬ1蛻ｩ遒ｺ": 260.0, "隨ｬ2蛻ｩ遒ｺ": 267.0, "謳榊・": 248.0, "迴ｾ蝨ｨ蛟､": 254.0}
            ])

    # --- 峅・・陦帶弌騾壻ｿ｡・夂樟蝨ｨ蛟､縺ｮ荳諡ｬ蜷梧悄繝懊ち繝ｳ ---
    if st.button("売 蜈ｨ霆阪・迴ｾ蝨ｨ蛟､繧定・蜍募叙蠕・(yfinance蜷梧悄)", use_container_width=True):
        with st.spinner("陦帶弌騾壻ｿ｡荳ｭ... 蜷・Κ髫翫・迴ｾ蝨ｨ蝨ｰ繧貞・蜿門ｾ励＠縺ｦ縺・∪縺・):
            import yfinance as yf
            updated = False
            for idx, row in st.session_state.frontline_df.iterrows():
                code = str(row['驫俶氛']).strip()
                if len(code) >= 4:
                    api_code = code[:4] + ".T"  # 譌･譛ｬ譬ｪ縺ｮ繝・ぅ繝・き繝ｼ蠖｢蠑上↓螟画鋤
                    try:
                        tk = yf.Ticker(api_code)
                        hist = tk.history(period="1d")
                        if not hist.empty:
                            latest_price = hist['Close'].iloc[-1]
                            st.session_state.frontline_df.at[idx, '迴ｾ蝨ｨ蛟､'] = round(latest_price, 1)
                            updated = True
                    except:
                        pass
            
            if updated:
                st.session_state.frontline_df.to_csv(FRONTLINE_FILE, index=False)
                st.success("識 迴ｾ蝨ｨ蛟､縺ｮ蜷梧悄縺悟ｮ御ｺ・＠縺ｾ縺励◆縲ゑｼ遺ｻyfinance縺ｮ莉墓ｧ倅ｸ翫∵怙螟ｧ20蛻・・驕・ｻｶ縺悟性縺ｾ繧後∪縺呻ｼ・)
                st.rerun()
            else:
                st.warning("繝・・繧ｿ縺ｮ蜿門ｾ励↓螟ｱ謨励＠縺ｾ縺励◆縲・)
    # ---------------------------------------------

    st.markdown("#### 笞呻ｸ・驛ｨ髫翫ヱ繝ｩ繝｡繝ｼ繧ｿ繝ｼ蜈･蜉・(繧ｳ繝ｳ繝医Ο繝ｼ繝ｫ繝代ロ繝ｫ)")
    st.caption("窶ｻ 逶ｴ謗･謨ｰ蛟､繧呈嶌縺肴鋤縺医※縺上□縺輔＞縲ゆｸ矩Κ縺ｮ縲瑚｡後ｒ霑ｽ蜉縲阪〒譁ｰ縺励＞驫俶氛繧堤┌髯舌↓霑ｽ蜉蜿ｯ閭ｽ縺ｧ縺吶・)

    edited_df = st.data_editor(
        st.session_state.frontline_df,
        num_rows="dynamic",
        column_config={
            "驫俶氛": st.column_config.TextColumn("驫俶氛", required=True),
            "雋ｷ蛟､": st.column_config.NumberColumn("雋ｷ蛟､", format="%.1f", required=True),
            "隨ｬ1蛻ｩ遒ｺ": st.column_config.NumberColumn("隨ｬ1蛻ｩ遒ｺ", format="%.1f", required=True),
            "隨ｬ2蛻ｩ遒ｺ": st.column_config.NumberColumn("隨ｬ2蛻ｩ遒ｺ", format="%.1f", required=True),
            "謳榊・": st.column_config.NumberColumn("謳榊・", format="%.1f", required=True),
            "迴ｾ蝨ｨ蛟､": st.column_config.NumberColumn("閥 迴ｾ蝨ｨ蛟､", format="%.1f", required=True),
        },
        use_container_width=True,
        key="frontline_editor"
    )

    if not edited_df.equals(st.session_state.frontline_df):
        st.session_state.frontline_df = edited_df.copy()
        edited_df.to_csv(FRONTLINE_FILE, index=False)
        st.rerun()

    st.markdown("---")
    st.markdown("#### 発 蜈ｨ霆阪Ξ繝ｼ繝繝ｼ螻暮幕迥ｶ豕・)

    active_squads = 0

    for index, row in edited_df.iterrows():
        ticker = str(row.get('驫俶氛', ''))
        if ticker.strip() == "" or pd.isna(row['雋ｷ蛟､']) or pd.isna(row['迴ｾ蝨ｨ蛟､']): continue
            
        buy = float(row['雋ｷ蛟､']); tp1 = float(row['隨ｬ1蛻ｩ遒ｺ']); tp2 = float(row['隨ｬ2蛻ｩ遒ｺ']); sl = float(row['謳榊・']); cur = float(row['迴ｾ蝨ｨ蛟､'])
        active_squads += 1

        if cur <= sl: st_text, st_color = "逐 陲ｫ蠑ｾ・磯亟陦帷ｷ夂ｪ∫ｴ繝ｻ蜊ｳ譎よ彫騾・・, "#ef5350"
        elif cur < buy: st_text, st_color = "笞・・隴ｦ謌抵ｼ域錐蛻・Λ繧､繝ｳ縺ｸ蠕碁荳ｭ・・, "#ff9800"
        elif cur < tp1: st_text, st_color = "泙 蟾｡闊ｪ荳ｭ・育ｬｬ1逶ｮ讓吶∈謗･霑台ｸｭ・・, "#26a69a"
        elif cur < tp2: st_text, st_color = "孱・・隨ｬ1逶ｮ讓吝芦驕費ｼ育┌謨ｵ蛹匁耳螂ｨ・・, "#42a5f5"
        else: st_text, st_color = "醇 譛邨ら岼讓吝芦驕費ｼ井ｻｻ蜍吝ｮ御ｺ・ｼ・, "#ab47bc"

        st.markdown(f"**驛ｨ髫・[{ticker}]** ・・謌ｦ豕・ <span style='color:{st_color}; font-weight:bold;'>{st_text}</span>", unsafe_allow_html=True)

        fig = go.Figure()
        min_x = min(sl, cur) * 0.98; max_x = max(tp2, cur) * 1.02
        
        fig.add_shape(type="line", x0=min_x, y0=0, x1=max_x, y1=0, line=dict(color="#555", width=2))
        bar_color = "rgba(38, 166, 154, 0.7)" if cur >= buy else "rgba(239, 83, 80, 0.7)"
        fig.add_shape(type="line", x0=buy, y0=0, x1=cur, y1=0, line=dict(color=bar_color, width=12))
        fig.add_trace(go.Scatter(x=[sl, buy, tp1, tp2], y=[0, 0, 0, 0], mode="markers+text", text=["謳榊・", "雋ｷ蛟､", "隨ｬ1蛻ｩ遒ｺ", "隨ｬ2蛻ｩ遒ｺ"], textposition="top center", textfont=dict(size=11, color="white"), marker=dict(size=10, color=["#ef5350", "#ffca28", "#26a69a", "#42a5f5"]), hoverinfo="x+text", name="髦ｲ陦帷ｷ・))
        fig.add_trace(go.Scatter(x=[cur], y=[0], mode="markers+text", text=[f"迴ｾ蝨ｨ蛟､<br>{cur}"], textposition="bottom center", textfont=dict(size=12, color=st_color), marker=dict(size=20, symbol="cross-thin", line=dict(width=3, color=st_color)), hoverinfo="x", name="繧ｿ繝ｼ繧ｲ繝・ヨ"))
        fig.update_layout(height=180, showlegend=False, yaxis=dict(showticklabels=False, showgrid=False, zeroline=False, range=[-1, 1]), xaxis=dict(showgrid=False, zeroline=False, range=[min_x, max_x], tickfont=dict(color="#888")), margin=dict(l=10, r=10, t=30, b=50), paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)', dragmode=False)
        st.plotly_chart(fig, use_container_width=True)

    if active_squads == 0: st.info("迴ｾ蝨ｨ縲∝ｱ暮幕荳ｭ縺ｮ驛ｨ髫翫・縺ゅｊ縺ｾ縺帙ｓ縲ゆｸ翫・陦ｨ縺ｫ繝・・繧ｿ繧貞・蜉帙＠縺ｦ縺上□縺輔＞縲・)

with tab6:
    st.markdown('<h3 style="font-size: clamp(14px, 4.5vw, 24px); margin-bottom: 1rem;">刀 莠句ｾ御ｻｻ蜍吝ｱ蜻・(AAR) & 謌ｦ邵ｾ繝繝・す繝･繝懊・繝・/h3>', unsafe_allow_html=True)
    st.caption("窶ｻ螳滄圀縺ｮ莠､謌ｦ險倬鹸・医ヨ繝ｬ繝ｼ繝牙ｱ･豁ｴ・峨ｒ險倬鹸縺励∬・霄ｫ縺ｮ謌ｦ邵ｾ縺ｨ縲瑚ｦ丞ｾ矩・螳亥ｺｦ・医Γ繝ｳ繧ｿ繝ｫ・峨阪ｒ蜿ｯ隕門喧繝ｻ蛻・梵縺励∪縺吶・)
    
    AAR_FILE = f"saved_aar_log_{user_id}.csv"
    
    def get_scale_for_code(code):
        api_code = str(code) if len(str(code)) == 5 else str(code) + "0"
        if not master_df.empty:
            m_row = master_df[master_df['Code'] == api_code]
            if not m_row.empty:
                scale_val = str(m_row.iloc[0].get('Scale', ''))
                return "召 螟ｧ蝙・荳ｭ蝙・ if any(x in scale_val for x in ["Core30", "Large70", "Mid400"]) else "噫 蟆丞梛/譁ｰ闊・
        return "荳肴・"
    
    if os.path.exists(AAR_FILE):
        try:
            aar_df = pd.read_csv(AAR_FILE)
            if "隕乗ｨ｡" not in aar_df.columns:
                aar_df.insert(2, "隕乗ｨ｡", aar_df["驫俶氛"].apply(get_scale_for_code))
                aar_df.to_csv(AAR_FILE, index=False)
            
            aar_df['豎ｺ貂域律'] = aar_df['豎ｺ貂域律'].astype(str)
            aar_df['驫俶氛'] = aar_df['驫俶氛'].astype(str)
            aar_df['雋ｷ蛟､'] = pd.to_numeric(aar_df['雋ｷ蛟､'], errors='coerce')
            aar_df['螢ｲ蛟､'] = pd.to_numeric(aar_df['螢ｲ蛟､'], errors='coerce')
            aar_df['譬ｪ謨ｰ'] = pd.to_numeric(aar_df['譬ｪ謨ｰ'], errors='coerce')
            aar_df['謳咲寢鬘・蜀・'] = pd.to_numeric(aar_df['謳咲寢鬘・蜀・'], errors='coerce')
            aar_df['謳咲寢(%)'] = pd.to_numeric(aar_df['謳咲寢(%)'], errors='coerce')
            
            aar_df = aar_df.sort_values(['豎ｺ貂域律', '驫俶氛'], ascending=[True, True]).reset_index(drop=True)
        except:
            aar_df = pd.DataFrame(columns=["豎ｺ貂域律", "驫俶氛", "隕乗ｨ｡", "謌ｦ陦・, "雋ｷ蛟､", "螢ｲ蛟､", "譬ｪ謨ｰ", "謳咲寢鬘・蜀・", "謳咲寢(%)", "隕丞ｾ・, "謨怜屏/蜍晏屏繝｡繝｢"])
    else:
        aar_df = pd.DataFrame(columns=["豎ｺ貂域律", "驫俶氛", "隕乗ｨ｡", "謌ｦ陦・, "雋ｷ蛟､", "螢ｲ蛟､", "譬ｪ謨ｰ", "謳咲寢鬘・蜀・", "謳咲寢(%)", "隕丞ｾ・, "謨怜屏/蜍晏屏繝｡繝｢"])

    col_a1, col_a2 = st.columns([1, 2.2])
    
    with col_a1:
        st.markdown("#### 統 謌ｦ譫懷ｱ蜻翫ヵ繧ｩ繝ｼ繝 (謇句虚蜈･蜉・")
        with st.form(key="aar_form"):
            c_f1, c_f2 = st.columns(2)
            import datetime as dt_module
            aar_date = c_f1.date_input("豎ｺ貂域律", dt_module.date.today())
            aar_code = c_f2.text_input("驫俶氛繧ｳ繝ｼ繝・(4譯・", max_chars=4)
            aar_tactics = st.selectbox("菴ｿ逕ｨ縺励◆謌ｦ陦・, ["倹 蠕・ｼ・(謚ｼ縺礼岼)", "笞｡ 蠑ｷ隘ｲ (鬆・ｼｵ繧・", "笞・・縺昴・莉・(陬・㍼繝ｻ螯･蜊・"])
            c_f3, c_f4, c_f5 = st.columns(3)
            aar_buy = c_f3.number_input("雋ｷ蛟､ (蜀・", min_value=0.0, step=1.0, format="%.1f")
            aar_sell = c_f4.number_input("螢ｲ蛟､ (蜀・", min_value=0.0, step=1.0, format="%.1f")
            aar_lot = c_f5.number_input("譬ｪ謨ｰ", min_value=100, step=100)
            
            st.markdown("**笞厄ｸ・閾ｪ蟾ｱ隧穂ｾ｡・医Γ繝ｳ繧ｿ繝ｫ繝ｻ繝√ぉ繝・け・・*")
            aar_rule = st.radio("繝懊せ縺ｮ縲朱延縺ｮ謗溘上ｒ螳悟・縺ｫ驕ｵ螳医＠縺ｦ謦・■縺ｾ縺励◆縺具ｼ・, ["笨・驕ｵ螳医＠縺・(蜀ｷ蠕ｹ縺ｪ迢呎茶)", "笶・遐ｴ縺｣縺・(諢滓ュ繝ｻ辟ｦ繧翫・螯･蜊・"], horizontal=False)
            aar_memo = st.text_input("迚ｹ險倅ｺ矩・(縺ｪ縺懊◎縺ｮ繝ｫ繝ｼ繝ｫ繧堤ｴ縺｣縺溘°縲√∪縺溘・蜍晏屏縺ｪ縺ｩ)")
            submit_aar = st.form_submit_button("沈 險倬鹸繧偵ョ繝ｼ繧ｿ繝舌Φ繧ｯ縺ｸ菫晏ｭ・, use_container_width=True)
            
        if submit_aar:
            if aar_code and len(aar_code) >= 4 and aar_buy > 0 and aar_sell > 0:
                profit = int((aar_sell - aar_buy) * aar_lot)
                profit_pct = round(((aar_sell / aar_buy) - 1) * 100, 2)
                new_data = pd.DataFrame([{
                    "豎ｺ貂域律": aar_date.strftime("%Y-%m-%d"), "驫俶氛": aar_code, "隕乗ｨ｡": get_scale_for_code(aar_code),
                    "謌ｦ陦・: aar_tactics.split(" ")[1] if " " in aar_tactics else aar_tactics,
                    "雋ｷ蛟､": aar_buy, "螢ｲ蛟､": aar_sell, "譬ｪ謨ｰ": aar_lot, "謳咲寢鬘・蜀・": profit, "謳咲寢(%)": profit_pct,
                    "隕丞ｾ・: "驕ｵ螳・ if "驕ｵ螳・ in aar_rule else "驕募渚", "謨怜屏/蜍晏屏繝｡繝｢": aar_memo
                }])
                aar_df = pd.concat([new_data, aar_df], ignore_index=True).sort_values(['豎ｺ貂域律', '驫俶氛'], ascending=[True, True]).reset_index(drop=True)
                aar_df.to_csv(AAR_FILE, index=False)
                st.success(f"驫俶氛 {aar_code} 縺ｮ謌ｦ譫懊ｒ蜿ｸ莉､驛ｨ繝・・繧ｿ繝吶・繧ｹ縺ｫ險倬鹸螳御ｺ・・)
                st.rerun()
            else: st.error("驫俶氛繧ｳ繝ｼ繝峨∬ｲｷ蛟､縲∝｣ｲ蛟､繧呈ｭ｣縺励￥蜈･蜉帙○繧医・)
        
        with st.expander("踏 險ｼ蛻ｸ莨夂､ｾ縺ｮ蜿門ｼ募ｱ･豁ｴ(CSV)縺九ｉ閾ｪ蜍穂ｸ諡ｬ逋ｻ骭ｲ", expanded=True):
            st.caption("繧｢繝・・繝ｭ繝ｼ繝峨＆繧後◆CSV縺九ｉ縲檎樟迚ｩ雋ｷ縲阪→縲檎樟迚ｩ螢ｲ縲阪ｒ閾ｪ蜍輔〒繝壹い繝ｪ繝ｳ繧ｰ縺励∵錐逶翫ｒ邂怜・縺励※繝・・繧ｿ繝吶・繧ｹ縺ｸ荳諡ｬ逋ｻ骭ｲ縺励∪縺吶ゑｼ遺ｻ驥崎､・ョ繝ｼ繧ｿ縺ｯ閾ｪ蜍墓賜髯､縺輔ｌ縺ｾ縺呻ｼ・)
            uploaded_csv = st.file_uploader("邏・ｮ壼ｱ･豁ｴCSV繝輔ぃ繧､繝ｫ繧偵い繝・・繝ｭ繝ｼ繝・, type=["csv"], key="aar_csv_uploader")
            if uploaded_csv is not None:
                if st.button("笞呻ｸ・CSV縺九ｉ謌ｦ譫懊ｒ閾ｪ蜍戊ｧ｣譫舌＠縺ｦ霑ｽ蜉", use_container_width=True, key="btn_parse_csv"):
                    try:
                        import io
                        try: content = uploaded_csv.getvalue().decode('utf-8')
                        except UnicodeDecodeError: content = uploaded_csv.getvalue().decode('shift_jis', errors='replace')
                        lines = content.splitlines()
                        header_idx = -1
                        for i, line in enumerate(lines):
                            if "邏・ｮ壽律" in line and "驫俶氛" in line:
                                header_idx = i; break
                                
                        if header_idx != -1:
                            csv_data = "\n".join(lines[header_idx:])
                            df_csv = pd.read_csv(io.StringIO(csv_data))
                            df_csv = df_csv[df_csv['蜿門ｼ・].astype(str).str.contains('迴ｾ迚ｩ')].copy()
                            records = []
                            for code, group in df_csv.groupby('驫俶氛繧ｳ繝ｼ繝・):
                                buys, sells = [], []
                                for _, row in group.iterrows():
                                    item = {'date': str(row['邏・ｮ壽律']).replace('/', '-'), 'qty': int(row['邏・ｮ壽焚驥・]), 'price': float(row['邏・ｮ壼腰萓｡']), 'code': str(code)}
                                    if "雋ｷ" in str(row['蜿門ｼ・]): buys.append(item)
                                    elif "螢ｲ" in str(row['蜿門ｼ・]): sells.append(item)
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
                                            "豎ｺ貂域律": s['date'], "驫俶氛": s['code'], "隕乗ｨ｡": get_scale_for_code(s['code']), "謌ｦ陦・: "閾ｪ蜍戊ｧ｣譫・,
                                            "雋ｷ蛟､": round(avg_buy_price, 1), "螢ｲ蛟､": round(s['price'], 1), "譬ｪ謨ｰ": int(matched_qty),
                                            "謳咲寢鬘・蜀・": int(profit), "謳咲寢(%)": round(profit_pct, 2), "隕丞ｾ・: "荳肴・(隕∽ｿｮ豁｣)", "謨怜屏/蜍晏屏繝｡繝｢": "CSV閾ｪ蜍募叙繧願ｾｼ縺ｿ"
                                        })
                            if records:
                                new_df = pd.DataFrame(records)
                                aar_df = pd.concat([aar_df, new_df], ignore_index=True)
                                aar_df['豎ｺ貂域律'] = aar_df['豎ｺ貂域律'].astype(str)
                                aar_df['驫俶氛'] = aar_df['驫俶氛'].astype(str)
                                aar_df['雋ｷ蛟､'] = aar_df['雋ｷ蛟､'].astype(float).round(1)
                                aar_df['螢ｲ蛟､'] = aar_df['螢ｲ蛟､'].astype(float).round(1)
                                aar_df['譬ｪ謨ｰ'] = aar_df['譬ｪ謨ｰ'].astype(int)
                                aar_df = aar_df.drop_duplicates(subset=["豎ｺ貂域律", "驫俶氛", "雋ｷ蛟､", "螢ｲ蛟､", "譬ｪ謨ｰ"], keep='first').reset_index(drop=True)
                                aar_df = aar_df.sort_values(['豎ｺ貂域律', '驫俶氛'], ascending=[True, True]).reset_index(drop=True)
                                aar_df.to_csv(AAR_FILE, index=False)
                                st.success(f"識 譁ｰ隕上・謌ｦ譫懊・縺ｿ繧呈歓蜃ｺ縺励∵里蟄倥・險倬鹸縺ｨ邨ｱ蜷亥ｮ御ｺ・・)
                                st.rerun()
                            else: st.warning("隗｣譫仙庄閭ｽ縺ｪ豎ｺ貂域ｸ医∩繝壹い・郁ｲｷ縺・→螢ｲ繧翫・繧ｻ繝・ヨ・峨′遒ｺ隱阪〒縺阪↑縺九▲縺溘・)
                        else: st.error("CSV繝輔か繝ｼ繝槭ャ繝医′隱崎ｭ倅ｸ崎・縲ゅ檎ｴ・ｮ壽律縲阪碁釜譟・阪ｒ蜷ｫ繧繝倥ャ繝陦後′蠢・医□縲・)
                    except Exception as e: st.error(f"隗｣譫舌お繝ｩ繝ｼ: {e}")

        if not aar_df.empty:
            if st.button("卵・・蜈ｨ險倬鹸繧呈ｶ亥悉 (繝・・繧ｿ繝吶・繧ｹ蛻晄悄蛹・", key="reset_aar", use_container_width=True):
                os.remove(AAR_FILE)
                st.rerun()

    with col_a2:
        st.markdown("#### 投 蜿ｸ莉､驛ｨ 邱丞粋謌ｦ邵ｾ繝繝・す繝･繝懊・繝・)
        if aar_df.empty: st.warning("迴ｾ蝨ｨ縲∽ｺ､謌ｦ險倬鹸・医ョ繝ｼ繧ｿ・峨′縺ｪ縺・ょｷｦ縺ｮ繝輔か繝ｼ繝縺九ｉ蜈･蜉帙☆繧九°縲，SV繧偵い繝・・繝ｭ繝ｼ繝峨○繧医・)
        else:
            tot_trades = len(aar_df)
            wins = len(aar_df[aar_df['謳咲寢鬘・蜀・'] > 0])
            losses = len(aar_df[aar_df['謳咲寢鬘・蜀・'] <= 0])
            win_rate = round((wins / tot_trades) * 100, 1) if tot_trades > 0 else 0
            
            tot_profit = aar_df['謳咲寢鬘・蜀・'].sum()
            gross_profit = aar_df[aar_df['謳咲寢鬘・蜀・'] > 0]['謳咲寢鬘・蜀・'].sum()
            gross_loss = abs(aar_df[aar_df['謳咲寢鬘・蜀・'] < 0]['謳咲寢鬘・蜀・'].sum())
            pf = round(gross_profit / gross_loss, 2) if gross_loss > 0 else float('inf')
            
            rule_adherence = round((len(aar_df[aar_df['隕丞ｾ・] == '驕ｵ螳・]) / tot_trades) * 100, 1) if tot_trades > 0 else 0
            
            m1, m2, m3, m4 = st.columns(4)
            m1.metric("邱丈ｺ､謌ｦ蝗樊焚", f"{tot_trades} 蝗・)
            m2.metric("螳滓姶 蜍晉紫", f"{win_rate}%", f"{wins}蜍・{losses}謨・, delta_color="off")
            m3.metric("邱丞粋 螳滓錐逶・, f"{int(tot_profit):,} 蜀・, f"螳滓姶PF: {pf}")
            m4.metric("笞厄ｸ・隕丞ｾ矩・螳育紫", f"{rule_adherence}%", "諢滓ュ謗帝勁縺ｮ繝舌Ο繝｡繝ｼ繧ｿ繝ｼ", delta_color="off")
            
            st.markdown("##### 腸 迴ｾ螳溘・雉・肇謗ｨ遘ｻ (Real Equity Curve)")
            aar_df_sorted = aar_df.sort_values('豎ｺ貂域律', ascending=True).reset_index(drop=True)
            aar_df_sorted['邏ｯ遨肴錐逶・蜀・'] = aar_df_sorted['謳咲寢鬘・蜀・'].cumsum()
            
            import plotly.express as px
            fig_real_eq = px.line(aar_df_sorted, x='豎ｺ貂域律', y='邏ｯ遨肴錐逶・蜀・', markers=True, color_discrete_sequence=["#26a69a"])
            fig_real_eq.update_layout(paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0.1)', margin=dict(l=20, r=20, t=10, b=20), xaxis_title="", yaxis_title="螳滓錐逶企｡・(蜀・", height=250, hovermode="x unified")
            st.plotly_chart(fig_real_eq, use_container_width=True)
            
            def color_pnl(val):
                if isinstance(val, (int, float)):
                    color = '#26a69a' if val > 0 else '#ef5350' if val < 0 else 'white'
                    return f'color: {color}; font-weight: bold;'
                return ''
                
            def color_rule(val):
                if val == '驕募渚': return 'color: #ef5350; font-weight: bold; background-color: rgba(239, 83, 80, 0.1);'
                elif '荳肴・' in str(val): return 'color: #9e9e9e;'
                return 'color: #26a69a;'

            st.markdown("##### 糖 隧ｳ邏ｰ莠､謌ｦ險倬鹸・医く繝ｫ繝ｻ繝ｭ繧ｰ・・)
            st.caption("窶ｻ陦ｨ縺ｮ繧ｻ繝ｫ繧堤峩謗･繝繝悶Ν繧ｯ繝ｪ繝・け縺吶ｋ縺ｨ縲√梧姶陦薙阪瑚ｦ丞ｾ九阪後Γ繝｢縲阪ｒ逶ｴ謗･邱ｨ髮・ｼ井ｸ頑嶌縺堺ｿ晏ｭ假ｼ牙庄閭ｽ縲・)

            styled_df = aar_df.style.map(color_pnl, subset=['謳咲寢鬘・蜀・', '謳咲寢(%)']).map(color_rule, subset=['隕丞ｾ・])

            edited_df = st.data_editor(
                styled_df,
                column_config={
                    "隕乗ｨ｡": st.column_config.TextColumn("隕乗ｨ｡", disabled=True),
                    "謌ｦ陦・: st.column_config.SelectboxColumn("謌ｦ陦・, options=["蠕・ｼ・, "蠑ｷ隘ｲ", "閾ｪ蜍戊ｧ｣譫・, "縺昴・莉・], required=True),
                    "隕丞ｾ・: st.column_config.SelectboxColumn("隕丞ｾ・, options=["驕ｵ螳・, "驕募渚", "荳肴・(隕∽ｿｮ豁｣)"], required=True),
                    "謨怜屏/蜍晏屏繝｡繝｢": st.column_config.TextColumn("謨怜屏/蜍晏屏繝｡繝｢", max_chars=200),
                    "雋ｷ蛟､": st.column_config.NumberColumn("雋ｷ蛟､", format="%.1f"),
                    "螢ｲ蛟､": st.column_config.NumberColumn("螢ｲ蛟､", format="%.1f"),
                    "譬ｪ謨ｰ": st.column_config.NumberColumn("譬ｪ謨ｰ", format="%d"),
                    "謳咲寢鬘・蜀・": st.column_config.NumberColumn("謳咲寢鬘・蜀・", format="%d"),
                    "謳咲寢(%)": st.column_config.NumberColumn("謳咲寢(%)", format="%.2f"),
                },
                disabled=["豎ｺ貂域律", "驫俶氛", "隕乗ｨ｡", "雋ｷ蛟､", "螢ｲ蛟､", "譬ｪ謨ｰ", "謳咲寢鬘・蜀・", "謳咲寢(%)"],
                hide_index=True, use_container_width=True, key="aar_data_editor"
            )
            
            if not edited_df.equals(aar_df):
                edited_df.to_csv(AAR_FILE, index=False)
                st.rerun()
