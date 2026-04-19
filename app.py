import streamlit as st
import requests
import pandas as pd
import os
import re
import json
from datetime import datetime, timedelta, timezone
from io import BytesIO
import plotly.graph_objects as go
import numpy as np
import concurrent.futures
import streamlit.components.v1 as components
import gc
import pytz
import time

# --- 🚀 0. 神聖UIパッチ：文字切れ（...）防止 ＆ 物理装飾 ---
st.markdown("""
    <style>
    /* st.metric の文字切れを物理的に阻止 */
    [data-testid="stMetricValue"] > div { 
        text-overflow: clip !important; 
        overflow: visible !important; 
        white-space: nowrap !important; 
    }
    [data-testid="stMetricValue"] { font-size: 1.4rem !important; }
    
    /* タブの視認性向上 */
    .stTabs [data-baseweb="tab-list"] { gap: 8px; }
    .stTabs [data-baseweb="tab"] { 
        background-color: rgba(255,255,255,0.05); 
        border-radius: 4px 4px 0 0; 
        padding: 8px 16px;
        font-weight: bold;
    }
    </style>
""", unsafe_allow_html=True)

# --- 1. ページ設定 ＆ ゲートキーパー（セキュリティ） ---
st.set_page_config(page_title="戦術スコープ『鉄の掟』", layout="wide", page_icon="🎯")

ALLOWED_PASSWORDS = [p.strip() for p in st.secrets.get("APP_PASSWORD", "sniper2026").split(",")]

def check_password():
    """ボスの資産を保護するゲートキーパー。自動ログインパッチを内蔵"""
    if "password_correct" not in st.session_state:
        st.session_state["password_correct"] = False
        st.session_state["current_user"] = "" 
        
    if not st.session_state["password_correct"]:
        st.markdown('<h1 style="text-align: center; color: #2e7d32; margin-top: 10vh;">🎯 戦術スコープ『鉄の掟』</h1>', unsafe_allow_html=True)
        col1, col2, col3 = st.columns([1, 2, 1])
        with col2:
            # ブラウザのパスワード保存機能を叩き起こすJSパッチ
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
                doc.addEventListener('input', (e) => { if (e.target.type === 'password') tryAutoLogin(); });
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

# --- 2. 兵站管理：キャッシュ ＆ 認証設定 ---

def get_cache_key():
    """JST 19:00を境界線とする物理キャッシュパージキー"""
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

cache_key = get_cache_key()
user_id = st.session_state["current_user"]
API_KEY = st.secrets.get("JQUANTS_API_KEY", "").strip()
headers = {"x-api-key": API_KEY}
BASE_URL = "https://api.jquants.com/v2"

# --- 3. 設定の永続化エンジン（サイドバー物理同期） ---
SETTINGS_FILE = f"saved_settings_{user_id}.json"

def load_settings():
    """ボスの戦術設定を物理ファイルから復元"""
    defaults = {
        "preset_market": "🚀 中小型株 (スタンダード・グロース)", 
        "preset_push_r": "50.0%",
        "sidebar_tactics": "⚖️ バランス (掟達成率 ＞ 到達度)",
        "push_r": 50.0, "limit_d": 4, "bt_lot": 100, "bt_tp": 10, "bt_sl_i": 8, "bt_sl_c": 8, "bt_sell_d": 10,
        "f1_min": 200, "f1_max": 3000, "f2_m30": 2.0, "f3_drop": -50.0,
        "f5_ipo": True, "f6_risk": True, "f7_ex_etf": True, "f8_ex_bio": True,
        "f9_min14": 1.1, "f9_max14": 2.0, "f10_ex_knife": True,
        "f11_ex_wave3": True, "f12_ex_overvalued": True,
        "tab2_rsi_limit": 75, "tab2_vol_limit": 15000, 
        "gigi_input": "2134, 3350, 6172, 6740, 7647, 8783, 8836, 8925, 9318"
    }
    saved_data = {}
    if os.path.exists(SETTINGS_FILE):
        try:
            with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
                saved_data = json.load(f)
        except: pass
    for k, v in defaults.items():
        if k not in st.session_state: st.session_state[k] = saved_data.get(k, v)

def save_settings():
    """ボスの指示を1クリックで永続化"""
    keys_to_save = [
        "preset_market", "preset_push_r", "sidebar_tactics", "push_r", "limit_d", "bt_lot", "bt_tp", "bt_sl_i", "bt_sl_c", "bt_sell_d", 
        "f1_min", "f1_max", "f2_m30", "f3_drop", "f5_ipo", "f6_risk", "f7_ex_etf", "f8_ex_bio", 
        "f9_min14", "f9_max14", "f10_ex_knife", "f11_ex_wave3", "f12_ex_overvalued",
        "tab2_rsi_limit", "tab2_vol_limit", "gigi_input"
    ]
    current_settings = {k: st.session_state[k] for k in keys_to_save if k in st.session_state}
    try:
        with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
            json.dump(current_settings, f, ensure_ascii=False, indent=4)
    except: pass

def apply_presets():
    """押し目プリセットの即時反映ロジック"""
    p_rate = st.session_state.get("preset_push_r", "50.0%")
    if p_rate == "25.0%": st.session_state.push_r = 25.0
    elif p_rate == "50.0%": st.session_state.push_r = 50.0
    elif p_rate == "61.8%": st.session_state.push_r = 61.8
    save_settings()

load_settings()

# --- 4. マクロ気象レーダー（日経平均同期） ---
@st.cache_data(ttl=600, show_spinner=False)
def get_macro_weather():
    """地合い連動フィルタのためのマクロ気象観測"""
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
                        "date": latest['Date'].strftime('%m/%d')
                    }
                }
    except: pass
    return None

weather = get_macro_weather()

# --- 4. 共通演算エンジン（型の物理解毒 ＆ 物理統一） ---

def clean_df(df):
    """
    英字入りコード（523A等）を物理的に許容し、5桁規格へ統一。
    不純物（欠損値）を排除し、戦術計算が可能な状態へ洗浄する。
    """
    # カラム名の揺れを物理吸収
    r_cols = {
        'AdjustmentOpen': 'AdjO', 'AdjustmentHigh': 'AdjH', 
        'AdjustmentLow': 'AdjL', 'AdjustmentClose': 'AdjC', 
        'Open': 'AdjO', 'High': 'AdjH', 'Low': 'AdjL', 'Close': 'AdjC', 
        'AdjustmentVolume': 'Volume', 'Volume': 'Volume'
    }
    df = df.rename(columns=r_cols)
    
    # 数値型の強制変換（float32でメモリ効率を確保）
    for c in ['AdjO', 'AdjH', 'AdjL', 'AdjC', 'Volume']:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors='coerce').astype('float32')
    
    if 'Date' in df.columns:
        df['Date'] = pd.to_datetime(df['Date'])
        if 'Code' in df.columns:
            # 🚨 英字コード対応：4文字なら末尾に0を付与、それ以外（5桁等）は維持
            df['Code'] = df['Code'].astype(str).apply(lambda x: x if len(x) >= 5 else x + "0")
        
        # ソート ＆ 欠損行の物理パージ
        df = df.sort_values(['Code', 'Date']).dropna(subset=['AdjO', 'AdjH', 'AdjL', 'AdjC']).reset_index(drop=True)
    return df

def calc_vector_indicators(df):
    """
    テクニカル指標の一括ベクトル演算。
    Pandasのベクトル演算により、数千銘柄の指標を瞬時に生成。
    """
    df = df.copy()
    if df.empty: return df
    
    # RSI (14日)
    delta = df.groupby('Code')['AdjC'].diff()
    gain = delta.where(delta > 0, 0); loss = -delta.where(delta < 0, 0)
    avg_gain = gain.groupby(df['Code']).ewm(alpha=1/14, adjust=False).mean().reset_index(level=0, drop=True)
    avg_loss = loss.groupby(df['Code']).ewm(alpha=1/14, adjust=False).mean().reset_index(level=0, drop=True)
    df['RSI'] = (100 - (100 / (1 + (avg_gain / (avg_loss + 1e-10))))).astype('float32')
    
    # MACD (12, 26, 9)
    ema12 = df.groupby('Code')['AdjC'].ewm(span=12, adjust=False).mean().reset_index(level=0, drop=True)
    ema26 = df.groupby('Code')['AdjC'].ewm(span=26, adjust=False).mean().reset_index(level=0, drop=True)
    macd = ema12 - ema26
    signal = macd.groupby(df['Code']).ewm(span=9, adjust=False).mean().reset_index(level=0, drop=True)
    df['MACD_Hist'] = (macd - signal).astype('float32')
    
    # 移動平均線 (5, 25, 75)
    df['MA5'] = df.groupby('Code')['AdjC'].transform(lambda x: x.rolling(5).mean()).astype('float32')
    df['MA25'] = df.groupby('Code')['AdjC'].transform(lambda x: x.rolling(25).mean()).astype('float32')
    df['MA75'] = df.groupby('Code')['AdjC'].transform(lambda x: x.rolling(75).mean()).astype('float32')
    
    # ATR (14日：ボラティリティ測定の核心)
    tr = pd.concat([
        df['AdjH'] - df['AdjL'], 
        (df['AdjH'] - df.groupby('Code')['AdjC'].shift(1)).abs(), 
        (df['AdjL'] - df.groupby('Code')['AdjC'].shift(1)).abs()
    ], axis=1).max(axis=1)
    df['ATR'] = tr.groupby(df['Code']).transform(lambda x: x.rolling(14).mean()).astype('float32')
    return df

def calc_technicals(df): 
    """上位互換用エイリアス"""
    return calc_vector_indicators(df)

# --- 5. 位相解析 ＆ パターン検知（ボスの資産：完全配線） ---

def analyze_context(group_260):
    """
    260日データから価格位置（0-100%）を算出し、戦術メッセージを生成。
    高値圏か安値圏かによって、サインの重みを反転させる。
    """
    if group_260.empty or len(group_260) < 20: 
        return {"pos": 50, "msgs": ["⚠️ データ不足：位相解析不能"]}
    
    lc = group_260['AdjC'].iloc[-1]
    h260 = group_260['AdjH'].max()
    l260 = group_260['AdjL'].min()
    
    # 現在の価格位置（エネルギー）の算出
    pos = ((lc - l260) / (h260 - l260) * 100) if (h260 - l260) > 0 else 50
    
    msgs = []
    if pos >= 80:
        msgs.append("⚠️ 【警戒】現在値は年足最高値圏。三尊等の反転波形は強力な売りシグナル（首吊り線警戒）。")
    elif pos <= 20:
        msgs.append("🔥 【期待】現在値は年足最安値圏。たくり足等の反転波形は大底打ち・反撃の急所。")
    else:
        msgs.append(f"⚖️ 【巡航】現在値はレンジ中間圏 ({pos:.1f}%)。テクニカル通りの推移を注視。")
        
    return {"pos": pos, "msgs": msgs}

def check_double_top(df_sub):
    """ダブルトップ検知ロジック"""
    try:
        v = df_sub['AdjH'].values; c = df_sub['AdjC'].values; l = df_sub['AdjL'].values
        if len(v) < 6: return False
        peaks = []
        for i in range(1, len(v)-1):
            if v[i] == max(v[i-1:i+2]):
                if not peaks or (i - peaks[-1][0] > 1): peaks.append((i, v[i]))
        if len(peaks) >= 2:
            p2_idx, p2_val = peaks[-1]; p1_idx, p1_val = peaks[-2]
            if abs(p2_val - p1_val) / max(p2_val, p1_val) < 0.05:
                valley = min(l[p1_idx:p2_idx+1]) if p2_idx > p1_idx else p1_val
                if valley < min(p1_val, p2_val) * 0.95 and c[-1] < p2_val * 0.97: return True
        return False
    except: return False

def check_head_shoulders(df_sub):
    """三尊（ヘッドアンドショルダー）検知ロジック"""
    try:
        v = df_sub['AdjH'].values; c = df_sub['AdjC'].values
        if len(v) < 8: return False
        peaks = []
        for i in range(1, len(v)-1):
            if v[i] == max(v[i-1:i+2]):
                if not peaks or (i - peaks[-1][0] > 1): peaks.append((i, v[i]))
        if len(peaks) >= 3:
            p3_idx, p3_val = peaks[-1]; p2_idx, p2_val = peaks[-2]; p1_idx, p1_val = peaks[-3]
            # 中央の山が左右より高く、左右の山の高さが概ね一致しているか
            if p2_val > p1_val and p2_val > p3_val and abs(p3_val - p1_val) / max(p3_val, p1_val) < 0.10 and c[-1] < p3_val * 0.97: return True
        return False
    except: return False

def check_double_bottom(df_sub):
    """ダブルボトム検知ロジック"""
    try:
        l = df_sub['AdjL'].values; c = df_sub['AdjC'].values; h = df_sub['AdjH'].values
        if len(l) < 6: return False
        valleys = []
        for i in range(1, len(l)-1):
            if l[i] == min(l[i-1:i+2]):
                if not valleys or (i - valleys[-1][0] > 1): valleys.append((i, l[i]))
        if len(valleys) >= 2:
            v2_idx, v2_val = valleys[-1]; v1_idx, v1_val = valleys[-2]
            if abs(v2_val - v1_val) / min(v2_val, v1_val) < 0.05:
                peak = max(h[v1_idx:v2_idx+1]) if v2_idx > v1_idx else v1_val
                if peak > max(v1_val, v2_val) * 1.04 and c[-1] > v2_val * 1.01: return True
        return False
    except: return False

# --- 6. 兵站管理：マスタ ＆ 先行フィルタ（ボスの資産：完全復元） ---

@st.cache_data(ttl=86400)
def load_master():
    """
    JPX公式から東証全銘柄リスト(Excel)を物理取得。
    英字入り銘柄(523A等)も破壊せず5桁規格へ統一して格納。
    """
    try:
        # JPXの統計資料ページから最新のエクセルURLを動的抽出
        r1 = requests.get("https://www.jpx.co.jp/markets/statistics-equities/misc/01.html", headers={'User-Agent': 'Mozilla/5.0'}, timeout=10)
        m = re.search(r'href="([^"]+data_j\.xls)"', r1.text)
        if m:
            r2 = requests.get("https://www.jpx.co.jp" + m.group(1), headers={'User-Agent': 'Mozilla/5.0'}, timeout=15)
            # xlrdエンジンを使用してメモリ展開
            df = pd.read_excel(BytesIO(r2.content), engine='xlrd')[['コード', '銘柄名', '33業種区分', '市場・商品区分']]
            df.columns = ['Code', 'CompanyName', 'Sector', 'Market']
            
            # 🚨 物理同期：4文字なら末尾0付与、それ以外は維持
            df['Code'] = df['Code'].astype(str).apply(lambda x: x if len(x) >= 5 else x + "0")
            return df
    except Exception as e:
        st.error(f"📡 マスタ兵站の確保に失敗：{e}")
    return pd.DataFrame()

def load_master_filtered():
    """
    サイドバーの設定を最上流で反映し、スキャン対象を物理的に絞り込む。
    IPO、ETF、バイオ、信用リスク銘柄をここで「足切り」し、演算速度をブースト。
    """
    m_df = load_master()
    if m_df.empty: return m_df
    
    # f7: ETF/REIT/投資法人/受益証券の物理排除
    if st.session_state.get('f7_ex_etf', True):
        etf_keywords = ['ETF', 'REIT', '投資法人', '受益証券', 'カントリーファンド', 'インフラファンド', '優先出資']
        m_df = m_df[~m_df['Market'].str.contains('|'.join(etf_keywords), na=False)]
        m_df = m_df[~m_df['CompanyName'].str.contains('|'.join(etf_keywords), na=False)]
    
    # f8: 医薬品(バイオ)セクターの排除
    if st.session_state.get('f8_ex_bio', True):
        m_df = m_df[m_df['Sector'] != '医薬品']
        
    # f6: 信用リスク（疑義注記・監理銘柄）の排除。gigi_inputに入力されたコードを対象とする
    if st.session_state.get('f6_risk', True):
        gigi = str(st.session_state.get('gigi_input', ""))
        # カンマ、スペース、改行で分割し、5桁規格へ
        risk_codes = [c.strip() + "0" if len(c.strip())==4 else c.strip() for c in re.split(r'[, \n]+', gigi) if len(c.strip()) >= 4]
        if risk_codes:
            m_df = m_df[~m_df['Code'].isin(risk_codes)]
            
    return m_df

# --- 7. 財務情報 ＆ 個別銘柄取得路 ---

@st.cache_data(ttl=3600, show_spinner=False, max_entries=200)
def get_fundamentals(code):
    """
    J-Quants APIから最新の財務諸表(statements)を取得。
    ROE, PER, PBRの算出基盤となる。
    """
    api_code = str(code) if len(str(code)) >= 5 else str(code) + "0"
    url = f"{BASE_URL}/fins/statements?code={api_code}"
    try:
        r = requests.get(url, headers=headers, timeout=5.0)
        if r.status_code == 200:
            data = r.json().get("statements", [])
            if not data: return None
            latest = data[0]
            
            # ボスの資産：ROE計算ロジック
            res = {
                "op": latest.get("OperatingProfit"),
                "cap": latest.get("MarketCapitalization"),
                "er": latest.get("EquityRatio"),
                "per": latest.get("PER"),
                "pbr": latest.get("PBR"),
                "roe": None
            }
            ni, eq = latest.get("NetIncome"), latest.get("Equity")
            if ni is not None and eq is not None:
                try: res["roe"] = (float(ni) / float(eq)) * 100
                except: res["roe"] = 0.0
            return res
    except: pass
    return None

@st.cache_data(ttl=3600, show_spinner=False, max_entries=200)
def get_single_data(code, yrs=1):
    """
    個別銘柄のヒストリカルデータを取得（TAB3、TAB4用）。
    J-Quantsを主とし、不足時はTAB3内でyfinance補完を行う。
    """
    base = datetime.now(pytz.timezone('Asia/Tokyo'))
    f_d, t_d = (base - timedelta(days=365*yrs)).strftime('%Y%m%d'), base.strftime('%Y%m%d')
    result = {"bars": []}
    try:
        api_code = str(code) if len(str(code)) >= 5 else str(code) + "0"
        url = f"{BASE_URL}/equities/bars/daily?code={api_code}&from={f_d}&to={t_d}"
        r = requests.get(url, headers=headers, timeout=10)
        if r.status_code == 200:
            result["bars"] = r.json().get("daily_quotes") or r.json().get("data") or []
    except: pass
    return result

# --- 8. バルクデータ取得エンジン（19時リセット同期） ---

@st.cache_data(ttl=86400, show_spinner=False)
def get_hist_data_cached(cache_key_str):
    """
    全銘柄の260日分データをバルク取得。
    cache_key_str（19時リセットキー）の変化により物理パージをトリガー。
    """
    base = datetime.now(pytz.timezone('Asia/Tokyo'))
    dates, days = [], 0
    # 土日を除いた「260営業日」分のリストを物理生成
    while len(dates) < 260:
        d = base - timedelta(days=days)
        if d.weekday() < 5:
            dates.append(d.strftime('%Y%m%d'))
        days += 1
        if days > 400: break # 無限ループ防止
        
    rows = []
    def fetch_day(dt):
        try:
            r = requests.get(f"{BASE_URL}/equities/bars/daily?date={dt}", headers=headers, timeout=15)
            if r.status_code == 200:
                return r.json().get("data", [])
        except: pass
        return []
        
    # スレッド並列化による超速兵站確保
    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as exe:
        futs = [exe.submit(fetch_day, dt) for dt in dates]
        for f in concurrent.futures.as_completed(futs):
            res = f.result()
            if res: rows.extend(res)
            
    # メモリ管理：不要な参照を物理破棄
    gc.collect()
    return rows

# --- 9. Triage（戦術階層判定）エンジン：銘柄の「生死」と「格」を物理判定 ---

def get_triage_info(macd_hist, macd_hist_prev, rsi, lc=0, bt=0, mode="待伏", gc_days=0):
    """
    【鉄の掟】の心臓部。サイドバーの「戦術アルゴリズム」と物理同期し、
    各銘柄にS/A/B/Cの階層を付与する。
    """
    tactics = st.session_state.get("sidebar_tactics", "⚖️ バランス (掟達成率 ＞ 到達度)")
    is_assault_mode = "狙撃優先" in tactics
    sl_limit_pct = float(st.session_state.get("bt_sl_c", 8.0))

    # MACDトレンドの状態を物理定義
    if macd_hist > 0 and macd_hist_prev <= 0: macd_t = "GC直後"
    elif macd_hist > macd_hist_prev: macd_t = "上昇拡大"
    elif macd_hist < 0 and macd_hist < macd_hist_prev: macd_t = "下落継続"
    else: macd_t = "減衰"

    # --- 強襲（トレンド追随）判定 ---
    if mode == "強襲":
        # 下落継続中、またはRSIが過熱（75超）している場合は即座に「圏外」
        if macd_t == "下落継続" or rsi >= 75: 
            return "圏外🚫", "#ef5350", 0, macd_t
            
        if is_assault_mode:
            # 狙撃優先：GCの鮮度を最重視
            if gc_days == 1: return "S🔥", "#26a69a", 5, "GC直後(1日目)"
            return "A⚡", "#ed6c02", 4, f"GC継続({gc_days}日目)"
        else:
            # バランス：RSIの過熱度でランクを分岐
            if gc_days == 1: 
                return ("S🔥", "#26a69a", 5, "GC直後") if rsi <= 50 else ("A⚡", "#ed6c02", 4, "GC直後")
            return "B📈", "#0288d1", 3, f"GC継続({gc_days}日目)"

    # --- 待伏（逆張り・押し目）判定 ---
    if bt == 0 or lc == 0: 
        return "C👁️", "#616161", 1, macd_t

    # 目標買値（bt）からの物理乖離率
    dist_pct = ((lc / bt) - 1) * 100 
    
    # 🚨 物理損切：設定された損切許容幅を超えた場合は「圏外」として排除
    if dist_pct < -sl_limit_pct: 
        return "圏外💀", "#ef5350", 0, f"損切突破({dist_pct:.1f}%)"

    if is_assault_mode:
        # 狙撃優先：より広い範囲（10%圏内）をS〜Bに収容
        if dist_pct <= 2.0: return "S🔥", "#26a69a", 5.5, macd_t
        elif dist_pct <= 6.0: return "A⚡", "#ed6c02", 4.5, macd_t
        elif dist_pct <= 10.0: return "B📈", "#0288d1", 3.5, macd_t
    else:
        # バランス：2%以内のみをS級、5%以内をA級とする厳格判定
        if dist_pct <= 2.0: 
            return ("S🔥", "#26a69a", 5, macd_t) if rsi <= 45 else ("A⚡", "#ed6c02", 4.5, macd_t) 
        elif dist_pct <= 5.0: 
            return ("A🪤", "#0288d1", 4.0, macd_t) if rsi <= 50 else ("B📈", "#0288d1", 3, macd_t)

    return "C👁️", "#616161", 1, macd_t

def get_assault_triage_info(gc_days, lc, rsi_v, df_chart, is_strict=False):
    """強襲モード専用：25日線との距離、RSI、鮮度を複合した精密スコアリング"""
    if gc_days <= 0 or df_chart is None or df_chart.empty: 
        return "圏外 💀", "#424242", 0, ""

    row = df_chart.iloc[-1]
    ma25 = row.get('MA25', 0)
    score = 50 

    # 25日線（生命線）との位置関係を物理評価
    if ma25 > 0:
        if lc >= ma25 * 0.95: score += 10
        if lc >= ma25: score += 10
    
    # RSIによる「熱量」の判定
    if 50 <= rsi_v <= 70: score += 15 # 適温
    elif rsi_v > 75: score -= 25      # 過熱

    # 鮮度（GC発生日からの経過）による減点
    score -= (gc_days - 1) * 5

    if score >= 80: rank, bg = "S🔥", "#26a69a"
    elif score >= 60: rank, bg = "A⚡", "#ed6c02"
    elif score >= 40: rank, bg = "B📈", "#0288d1"
    else: rank, bg = "C 💀", "#424242"

    return rank, bg, score, f"GC {gc_days}日目"

# --- 10. 実戦同期エンジン：英字コード対応・バルク現在値取得 ---

@st.cache_data(ttl=60, show_spinner=False)
def fetch_current_prices_fast(codes):
    """
    全監視銘柄の現在値を一括同期。
    J-Quants Quotesを最優先し、取得不能時はyfinanceで物理補完。
    """
    results = {}
    if not codes: return results
    
    # J-Quants 5桁規格への物理変換
    api_codes = [str(c) + "0" if len(str(c)) == 4 else str(c) for c in codes]
    
    try:
        # 本日の全銘柄時価(Quotes)をバルク取得
        url = f"{BASE_URL}/equities/quotes"
        r = requests.get(url, headers=headers, timeout=10)
        if r.status_code == 200:
            data = r.json().get("quotes", [])
            price_map = {q['Code']: q['Close'] for q in data if q.get('Close')}
            for c in codes:
                target = str(c) + "0" if len(str(c)) == 4 else str(c)
                if target in price_map:
                    results[str(c)] = price_map[target]
    except: pass
    
    # 未取得分（ザラ場中や特殊銘柄）を yfinance で補完
    missing = [c for c in codes if str(c) not in results]
    if missing:
        def fetch_yf(c):
            try:
                import yfinance as yf
                ticker_str = f"{c}.T"
                tk = yf.Ticker(ticker_str)
                h = tk.history(period="1d")
                if not h.empty: return str(c), h['Close'].iloc[-1]
            except: pass
            return str(c), None

        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as exe:
            f_res = list(exe.map(fetch_yf, missing))
            for c_code, c_price in f_res:
                if c_price: results[c_code] = c_price
                
    return results

# --- 11. 最上流フィルタ実行 ＆ システム・イニシャライズ ---

# 兵站（マスタ）の読み込み。サイドバーの足切り設定（IPO等）を最速適用。
master_df = load_master_filtered()

if master_df.empty:
    st.error("🚨 JPX銘柄マスタの確保に失敗しました。補給線を確認してください。")
    st.stop()

# --- 12. 物理ユーティリティ ＆ 型の最終防衛線 ---

def safe_int(val):
    """
    TAB3/TAB5のメトリクス表示における最終防衛線。
    None, NaN, Inf を物理的に0へ置換し、描画クラッシュを阻止する。
    """
    try:
        if val is None or (isinstance(val, float) and (np.isnan(val) or np.isinf(val))):
            return 0
        return int(float(val))
    except:
        return 0

# --- 13. 高速テクニカル演算ユニット (TAB1 索敵用) ---

def get_fast_indicators(prices):
    """
    数千銘柄の広域スキャンをミリ秒単位で完遂するための高速演算エンジン。
    NumPy配列を直叩きし、メモリ消費を極限まで抑制。
    """
    if len(prices) < 26: 
        return 50.0, 0.0, 0.0, np.zeros(5)
    
    p = np.array(prices, dtype='float32')
    
    # RSI (直近14日)
    diff = np.diff(p[-15:])
    gain = np.sum(np.maximum(diff, 0))
    loss = np.sum(np.abs(np.minimum(diff, 0)))
    rsi = 100 - (100 / (1 + (gain / (loss + 1e-10))))
    
    # MACD演算 (12, 26, 9)
    # 高速化のため、ここではベクトル演算による簡易指数移動平均を使用
    def ema(data, span):
        alpha = 2 / (span + 1)
        return pd.Series(data).ewm(alpha=alpha, adjust=False).mean().values
        
    ema12 = ema(p, 12)
    ema26 = ema(p, 26)
    macd_line = ema12 - ema26
    signal_line = ema(macd_line, 9)
    hist = macd_line - signal_line
    
    # 最新ヒスト、前日ヒスト、直近5日のトレンドを返却
    return float(rsi), float(hist[-1]), float(hist[-2]), hist[-5:]

# --- 14. 神聖UI描画エンジン (バッジ ＆ レーダー) ---

def render_technical_radar(df, buy_p, tp_pct):
    """
    ボスの1pxのこだわりを物理実装。
    各タブ共通で、テクニカルの状態をバッジ形式で可視化する。
    """
    if df.empty or len(df) < 2: return ""
    
    latest = df.iloc[-1]
    prev = df.iloc[-2]
    
    rsi = float(latest.get('RSI', 50))
    macd_h = float(latest.get('MACD_Hist', 0))
    macd_h_prev = float(prev.get('MACD_Hist', 0))
    atr = float(latest.get('ATR', 0))
    
    # RSIの色分け
    rsi_color = "#26a69a" if rsi <= 45 else "#ef5350" if rsi >= 75 else "#888"
    
    # MACDトレンドの文言化
    if macd_h > 0 and macd_h_prev <= 0: macd_t, macd_c = "GC直後", "#26a69a"
    elif macd_h > macd_h_prev: macd_t, macd_c = "上昇拡大", "#26a69a"
    elif macd_h < 0 and macd_h < macd_h_prev: macd_t, macd_c = "下落継続", "#ef5350"
    else: macd_t, macd_c = "減衰", "#888"

    return f"""
    <div style="background: rgba(255, 255, 255, 0.05); padding: 0.8rem; border-radius: 4px; margin: 1rem 0; border-left: 4px solid #FFD700;">
        <div style="display: flex; gap: 20px; align-items: center;">
            <div style="font-size: 14px; color: #aaa;">📡 リアルタイム計器盤:</div>
            <div style="font-size: 14px; color: #fff;">RSI: <strong style="color: {rsi_color};">{rsi:.1f}%</strong></div>
            <div style="font-size: 14px; color: #fff;">MACD: <strong style="color: {macd_c};">{macd_t}</strong></div>
            <div style="font-size: 14px; color: #fff;">1ATR: <strong style="color: #bbb;">¥{atr:.1f}</strong></div>
        </div>
    </div>
    """

# --- 15. Plotly精密描画エンジン (ボスの資産：100%完全復元) ---

def draw_chart(df, targ_p, chart_key=None):
    """
    ホバー8項目、ズーム機能、右余白ゼロ。
    ボスの指定した『最強のチャートレイアウト』を物理描画する。
    """
    if df.empty:
        st.warning("表示可能なチャートデータがありません。")
        return

    fig = go.Figure()

    # 1. ローソク足
    fig.add_trace(go.Candlestick(
        x=df['Date'], open=df['AdjO'], high=df['AdjH'], low=df['AdjL'], close=df['AdjC'],
        name='株価', increasing_line_color='#26a69a', decreasing_line_color='#ef5350'
    ))

    # 2. 掟・目標買値ライン
    fig.add_trace(go.Scatter(
        x=df['Date'], y=[targ_p]*len(df),
        name='目標買値', line=dict(color='#FFD700', width=2, dash='dash')
    ))

    # 3. 移動平均線 (5, 25, 75)
    for col, name, color in [('MA5', '5日線', '#ffca28'), ('MA25', '25日線', '#42a5f5'), ('MA75', '75日線', '#ab47bc')]:
        if col in df.columns:
            fig.add_trace(go.Scatter(
                x=df['Date'], y=df[col], name=name,
                line=dict(color=color, width=1.5), opacity=0.8
            ))

    # レイアウト設定 (ボスの1pxパッチを適用)
    fig.update_layout(
        height=550,
        margin=dict(l=0, r=0, t=30, b=40),
        paper_bgcolor='rgba(0,0,0,0)',
        plot_bgcolor='rgba(0,0,0,0)',
        hovermode="x unified",
        showlegend=True,
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        xaxis=dict(
            type="date",
            gridcolor='rgba(255,255,255,0.05)',
            rangeslider=dict(visible=False),
            title=""
        ),
        yaxis=dict(
            side="right",
            gridcolor='rgba(255,255,255,0.05)',
            tickformat=",.0f",
            title=""
        )
    )

    st.plotly_chart(fig, use_container_width=True, key=chart_key or f"chart_{time.time()}")

# --- 16. システム・イニシャライズ ---

# 🚨 最上流でのマスタ確保。ここで523A等の英字銘柄 ＆ 物理足切りを確定。
master_df = load_master_filtered()

if master_df.empty:
    st.error("🚨 致命的エラー：JPX銘柄マスタの兵站確保に失敗しました。")
    st.stop()

# ==========================================
# 🚨 物理復元：神聖サイドバー ＆ 司令部 (The Control Room)
# ==========================================

# サイドバータイトル（神聖HTML装飾）
st.sidebar.markdown("""
    <div style='background-color: #1b5e20; padding: 1.2rem; border-radius: 10px; border: 1px solid #81c784; margin-bottom: 20px;'>
        <h1 style='text-align: center; color: #ffffff; font-size: 22px; margin: 0; font-weight: 900; letter-spacing: 2px;'>🛠️ TACTICAL CONSOLE</h1>
        <div style='text-align: center; color: #a5d6a7; font-size: 10px; margin-top: 5px;'>IRON RULE SYSTEM Ver. 2026.4</div>
    </div>
""", unsafe_allow_html=True)

# --- 1. 地合い連動・マクロ気象アラート ---
st.sidebar.markdown("<h3 style='font-size: 16px; border-left: 4px solid #2e7d32; padding-left: 8px; color: #eee;'>🌪️ マクロ気象連動</h3>", unsafe_allow_html=True)
use_macro = st.sidebar.toggle("地合い連動フィルタを有効化", value=True, help="日経平均の暴落時に自動で防衛ラインを厳格化します。")

# 地合い変数の物理初期化（システム・ステート同期）
st.session_state.push_penalty = 0.0
st.session_state.rsi_penalty = 0
st.session_state.macro_alert = "🟢 平時 (Normal)"

if use_macro and weather:
    n_pct = weather['nikkei']['pct']
    if n_pct <= -2.0:
        st.session_state.push_penalty = 0.10
        st.session_state.rsi_penalty = 20
        st.session_state.macro_alert = "🔴 厳戒 (Crisis)"
        st.sidebar.error(f"【警報】日経平均急落 ({n_pct:+.2f}%)。防衛ラインを10%引き下げ、RSI閾値を厳格化します。")
    elif n_pct <= -1.0:
        st.session_state.push_penalty = 0.05
        st.session_state.rsi_penalty = 10
        st.session_state.macro_alert = "🟠 警戒 (Caution)"
        st.sidebar.warning(f"【注意】地合い悪化 ({n_pct:+.2f}%)。防衛ラインを5%引き下げます。")
    else:
        st.sidebar.success(f"【巡航】地合い安定 ({n_pct:+.2f}%)。")
else:
    st.sidebar.info("地合い連動：OFF (Manual Mode)")

st.sidebar.markdown("<div style='margin: 15px 0;'></div>", unsafe_allow_html=True)

# --- 2. ターゲット設定 ＆ プリセット ---
st.sidebar.markdown("<h3 style='font-size: 16px; border-left: 4px solid #2e7d32; padding-left: 8px; color: #eee;'>📍 ターゲット設定</h3>", unsafe_allow_html=True)

st.sidebar.selectbox(
    "市場ターゲット", 
    ["🏢 大型株 (プライム・一部)", "🚀 中小型株 (スタンダード・グロース)"], 
    key="preset_market", 
    on_change=save_settings
)

st.sidebar.selectbox(
    "押し目プリセット (Fibonacci)", 
    ["25.0%", "50.0%", "61.8%"], 
    key="preset_push_r", 
    on_change=apply_presets
)

st.sidebar.selectbox(
    "戦術アルゴリズム", 
    ["⚖️ バランス (掟達成率 ＞ 到達度)", "🎯 狙撃優先 (到達度 ＞ 掟達成率)"], 
    key="sidebar_tactics", 
    on_change=save_settings
)

st.sidebar.markdown("<div style='margin: 15px 0;'></div>", unsafe_allow_html=True)

# --- 3. スキャンルール（物理足切り設定） ---
st.sidebar.markdown("<h3 style='font-size: 16px; border-left: 4px solid #2e7d32; padding-left: 8px; color: #eee;'>🔍 スキャンルール</h3>", unsafe_allow_html=True)

# 2カラム構成の維持
col_f1, col_f2 = st.sidebar.columns(2)
with col_f1:
    st.number_input("価格下限 (Min)", value=int(st.session_state.f1_min), step=100, key="f1_min", on_change=save_settings)
with col_f2:
    st.number_input("価格上限 (Max)", value=int(st.session_state.f1_max), step=100, key="f1_max", on_change=save_settings)

st.sidebar.number_input("1ヶ月暴騰上限 (f2/m30)", value=float(st.session_state.f2_m30), step=0.1, key="f2_m30", on_change=save_settings)
st.sidebar.number_input("波高下限 (f9/Volatility)", value=float(st.session_state.f9_min14), step=0.05, key="f9_min14", on_change=save_settings)

# 足切りフラグの物理配線
st.sidebar.checkbox("🚀 IPO除外 (上場1年/200日未満)", key="f5_ipo", on_change=save_settings)
st.sidebar.checkbox("📉 非常に割高・赤字銘柄を除外", key="f12_ex_overvalued", on_change=save_settings)

st.sidebar.markdown("<div style='margin: 15px 0;'></div>", unsafe_allow_html=True)

# --- 4. 物理排除リスト（gigiコード） ---
st.sidebar.markdown("<h3 style='font-size: 16px; border-left: 4px solid #ef5350; padding-left: 8px; color: #ef5350;'>🚫 物理排除リスト</h3>", unsafe_allow_html=True)
st.sidebar.text_area(
    "信用リスク・疑義銘柄コード", 
    key="gigi_input", 
    placeholder="例: 2134, 3350, 6172...",
    help="ここに入力された銘柄はスキャン・解析から永久に抹殺されます。",
    on_change=save_settings
)

# 兵站ステータス
st.sidebar.markdown(f"""
    <div style='background: rgba(0,0,0,0.3); padding: 10px; border-radius: 5px; margin-top: 20px;'>
        <div style='font-size: 10px; color: #888;'>兵站同期ステータス</div>
        <div style='font-size: 11px; color: #26a69a; font-family: monospace;'>KEY: {cache_key}</div>
    </div>
""", unsafe_allow_html=True)

# ==========================================
# 🚨 生命線：タブの物理定義（Engine ↔ UI Bridge）
# ==========================================
tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs([
    "🌐 待伏 (Ambush)", 
    "⚡ 強襲 (Assault)", 
    "🎯 照準 (Scope)", 
    "⚙️ 演習 (Sim)", 
    "⛺ 戦線 (Front)", 
    "📁 戦歴 (History)"
])

# この直後に with tab1: 等の各タブコンテンツを結合せよ
# --- 12. タブコンテンツ (TAB1: 待伏レーダー) ---
with tab1:
    st.markdown(f'<h3 style="font-size: 24px;">🎯 【待伏】2026式・マクロ連動スキャン</h3>', unsafe_allow_html=True)
    st.info(f"現在の地合い連動：{st.session_state.get('macro_alert', '未設定')}")
    
    # 機関部でロード済みの filtered_master を使用
    master_map_t1 = {}
    if not master_df.empty:
        master_map_t1 = master_df.set_index('Code').to_dict('index')

    if 'tab1_scan_results' not in st.session_state: st.session_state.tab1_scan_results = None
    
    run_scan_t1 = st.button("🚀 索敵開始", key="btn_scan_t1_ultimate_v1")

    if run_scan_t1:
        st.session_state.tab1_scan_results = None
        gc.collect() 
        
        t_global_start = time.time()
        
        with st.spinner("260日戦歴データの解析 ＆ 先行フィルタを適用中..."):
            # 🚨 19時リセットキャッシュキーによる物理取得
            raw = get_hist_data_cached(cache_key) 
            t_fetch = time.time()
            
            if not raw:
                st.error("J-Quants APIからの応答が途絶。通信圏外です。")
            else:
                full_df = clean_df(pd.DataFrame(raw))
                # 4桁コードを5桁化（物理統一）
                full_df['Code'] = full_df['Code'].astype(str).str.replace(r'^(\d{4})$', r'\10', regex=True)
                
                push_penalty = st.session_state.get('push_penalty', 0.0)
                
                config_t1 = {
                    "f1_min": float(st.session_state.f1_min), "f1_max": float(st.session_state.f1_max),
                    "f2_m30": float(st.session_state.f2_m30), "f3_drop": float(st.session_state.f3_drop),
                    "push_r": float(st.session_state.push_r), "push_penalty": push_penalty,
                    "f9_min14": float(st.session_state.f9_min14), "f9_max14": float(st.session_state.f9_max14),
                    "limit_d": int(st.session_state.limit_d), "f12_ex_overvalued": st.session_state.f12_ex_overvalued,
                    "tactics": st.session_state.get("sidebar_tactics", "⚖️ バランス"), "sl_c": float(st.session_state.get("bt_sl_c", 8.0))
                }

                # 市場ターゲット絞り込み（先行フィルタ適用済みマスターとの論理積）
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

                def scan_unit_t1_parallel(code, group, cfg, v_avg):
                    c_vals = group['AdjC'].values
                    lc = c_vals[-1]
                    
                    # 🚨 【修正】IPOフィルター（上場1年未満/200営業日未満）の物理配線
                    if cfg.get("f5_ipo", True) and len(group) < 200:
                        return None
                    
                    # 🚨 【修正】f2_m30：直近22営業日の安値基準
                    recent_22 = group.tail(22)
                    low_22 = recent_22['AdjL'].min()
                    if low_22 > 0 and (lc / low_22) > cfg["f2_m30"]: return None
                    
                    # 波形・テクニカル解析
                    r4h = h_vals[-4:]; h4 = r4h.max()
                    g_max_idx = len(h_vals) - 4 + r4h.argmax()
                    l14 = l_vals[max(0, g_max_idx - 14) : g_max_idx + 1].min()

                    if l14 <= 0 or h4 <= l14: return None
                    wh = h4 / l14
                    if not (cfg["f9_min14"] <= wh <= cfg["f9_max14"]): return None
                    
                    # 割安・赤字除外 (f12)
                    if cfg["f12_ex_overvalued"]:
                        f_data = get_fundamentals(code[:4])
                        if f_data and ((f_data.get("op", 0) or 0) < 0): return None
                    
                    rsi, m_hist, m_prev, _ = get_fast_indicators(c_vals)
                    base_push = (h4 - l14) * (cfg["push_r"] / 100.0)
                    target_buy = h4 - base_push
                    target_buy = target_buy * (1.0 - cfg["push_penalty"]) 
                    
                    # 階層判定（Triage）
                    _, _, t_score, _ = get_triage_info(m_hist, m_prev, rsi, lc, target_buy, mode="待伏")
                    
                    # 掟スコアリング
                    score = 4
                    if 1.3 <= wh <= 2.0: score += 1
                    if (len(h_vals) - 1 - g_max_idx) <= cfg["limit_d"]: score += 1
                    if not check_double_top(group.tail(31).iloc[:-1]): score += 1
                    if target_buy * 0.85 <= lc <= target_buy * 1.35: score += 1
                    
                    dist_pct = ((lc / target_buy) - 1) * 100
                    if dist_pct < -cfg["sl_c"]: rank, bg = "圏外💀", "#ef5350"
                    elif dist_pct <= 2.0: rank, bg = "S🔥", "#26a69a"
                    elif dist_pct <= 6.0: rank, bg = "A⚡", "#ed6c02"
                    else: rank, bg = "B📈", "#0288d1"

                    return {
                        'Code': code, 'lc': float(lc), 'RSI': float(rsi), 'target_buy': float(target_buy), 
                        'reach_rate': float((target_buy / lc) * 100), 'triage_rank': rank, 'triage_bg': bg, 
                        't_score': t_score, 'score': score, 'high_4d': float(h4), 'low_14d': float(l14), 'avg_vol': int(v_avg),
                        'df_context': group.tail(260) # 位相分析用に全行保持
                    }

                results = []
                with concurrent.futures.ThreadPoolExecutor(max_workers=10) as exe:
                    futures = {exe.submit(scan_unit_t1_parallel, c, g, config_t1, avg_vols.get(c, 0)): c for c, g in df.groupby('Code')}
                    for f in concurrent.futures.as_completed(futures):
                        try:
                            res = f.result()
                            if res: results.append(res)
                        except: pass
                
                # スコアソート ＆ セクター分散（1業種最大3銘柄）
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

                # 🚨 プロファイル出力
                st.markdown(f"""
                <div style='background:rgba(0,0,0,0.5); padding:10px; border-radius:5px; border-left:3px solid #888; margin-bottom:10px; font-size:12px; color:#ddd;'>
                    <b>⏱️ スキャンプロファイル (TAB1)</b><br>
                    ・260日兵站確保（データ取得）: {t_fetch - t_global_start:.2f}秒<br>
                    ・データ規格統一 ＆ 先行フィルタ: {t_clean - t_fetch:.2f}秒<br>
                    ・並列演算（文脈解析込）: {t_calc - t_clean:.2f}秒<br>
                    <b>・合計: {t_calc - t_global_start:.2f}秒</b>
                </div>
                """, unsafe_allow_html=True)

    # --- 描画ループ（神聖UI復元） ---
    if st.session_state.tab1_scan_results:
        light_results = st.session_state.tab1_scan_results
        st.success(f"🎯 待伏ロックオン: {len(light_results)} 銘柄（260日戦歴 ＆ セクター分散適用済）")
        
        sab_codes = " ".join([str(r['Code'])[:4] for r in light_results if str(r['triage_rank']).startswith(('S', 'A', 'B'))])
        st.info("📋 以下のコードをコピーして、照準（TAB3）にペースト可能だ。")
        st.code(sab_codes, language="text")
        
        for r in light_results:
            st.divider()
            c_code = str(r['Code']); m_info = master_map_t1.get(c_code, {})
            m_lower = str(m_info.get('Market', '')).lower()
            if 'プライム' in m_lower or '一部' in m_lower: badge_html = '<span style="background-color: #1a237e; color: #ffffff; padding: 0.2rem 0.6rem; border-radius: 4px; font-size: 11px; font-weight: bold;">🏢 プライム/大型</span>'
            elif 'グロース' in m_lower or 'マザーズ' in m_lower: badge_html = '<span style="background-color: #1b5e20; color: #ffffff; padding: 0.2rem 0.6rem; border-radius: 4px; font-size: 11px; font-weight: bold;">🚀 グロース/新興</span>'
            else: badge_html = f'<span style="background-color: #455a64; color: #ffffff; padding: 0.2rem 0.6rem; border-radius: 4px; font-size: 11px; font-weight: bold;">{m_info.get("Market","不明")}</span>'
            
            t_badge = f'<span style="background-color: {r["triage_bg"]}; color: #ffffff; padding: 0.2rem 0.6rem; border-radius: 4px; font-size: 13px; font-weight: bold; margin-left: 0.5rem;">🎯 優先度: {r["triage_rank"]}</span>'
            score_val = r["score"]; score_color = "#26a69a" if score_val >= 8 else "#ff5722"; score_bg = "rgba(38, 166, 154, 0.15)" if score_val >= 8 else "rgba(255, 87, 34, 0.15)"
            score_badge = f'<span style="background-color: {score_bg}; border: 1px solid {score_color}; color: {score_color}; padding: 0.2rem 0.6rem; border-radius: 4px; font-size: 12px; font-weight: bold; margin-left: 0.5rem;">🎖️ 掟スコア: {score_val}/9</span>'
            sector_badge = f'<span style="background-color: #607d8b; color: #ffffff; padding: 0.1rem 0.5rem; border-radius: 4px; font-size: 12px; margin-left: 0.5rem;">🏭 {m_info.get("Sector", "不明")}</span>'
            
            # 位相・戦術メッセージの抽出
            ctx = analyze_context(r['df_context'])
            
            st.markdown(f"""
                <div style="margin-bottom: 0.8rem;">
                    <h3 style="font-size: clamp(18px, 5vw, 28px); font-weight: bold; margin: 0 0 0.3rem 0;">({c_code[:4]}) {m_info.get('CompanyName', '不明')}</h3>
                    <div style="display: flex; flex-wrap: wrap; gap: 6px; align-items: center;">
                        {badge_html}{t_badge}{score_badge}{sector_badge}
                        <span style="background-color: rgba(38, 166, 154, 0.15); border: 1px solid #26a69a; color: #26a69a; padding: 0.1rem 0.5rem; border-radius: 4px; font-size: 12px;">RSI: {r["RSI"]:.1f}%</span>
                        <span style="background-color: rgba(255, 215, 0, 0.1); border: 1px solid #FFD700; color: #FFD700; padding: 0.1rem 0.5rem; border-radius: 4px; font-size: 12px;">到達度: {r['reach_rate']:.1f}%</span>
                    </div>
                </div>
            """, unsafe_allow_html=True)
            
            # 戦術文脈メッセージの表示
            for msg in ctx['msgs']:
                if "警戒" in msg: st.error(msg)
                else: st.success(msg)
            
            m_cols = st.columns([1, 1, 1, 1.2, 1.5])
            m_cols[0].metric("直近高値", f"{int(r['high_4d']):,}円")
            m_cols[1].metric("起点安値", f"{int(r['low_14d']):,}円")
            m_cols[2].metric("最新終値", f"{int(r['lc']):,}円")
            m_cols[3].metric("平均出来高", f"{int(r['avg_vol']):,}株")
            m_cols[4].markdown(f"""<div style="background: rgba(255, 215, 0, 0.05); padding: 0.5rem; border-radius: 8px; border: 1px solid rgba(255, 215, 0, 0.2); text-align: center;"><div style="font-size: 13px; color: rgba(250, 250, 250, 0.6); margin-bottom: 2px;">🎯 買値目標(連動済)</div><div style="font-size: 1.8rem; font-weight: bold; color: #FFD700;">{int(r['target_buy']):,}<span style="font-size: 14px; margin-left:2px;">円</span></div></div>""", unsafe_allow_html=True)

# --- 13. タブコンテンツ (TAB2: 強襲レーダー) ---
with tab2:
    st.markdown('<h3 style="font-size: 24px;">⚡ 【強襲】2026式・マクロ連動スキャン</h3>', unsafe_allow_html=True)
    st.info(f"現在の地合い連動：{st.session_state.get('macro_alert', '未設定')}")
    
    if 'tab2_scan_results' not in st.session_state: st.session_state.tab2_scan_results = None
    
    # 機関部でロード済みの filtered_master を使用
    master_map_t2 = {}
    if not master_df.empty:
        master_map_t2 = master_df.set_index('Code').to_dict('index')

    col_t2_1, col_t2_2 = st.columns(2)
    # デフォルト値の物理保証
    if 'tab2_rsi_limit' not in st.session_state: st.session_state.tab2_rsi_limit = 70
    if 'tab2_vol_limit' not in st.session_state: st.session_state.tab2_vol_limit = 50000
    
    rsi_lim = col_t2_1.number_input("RSI上限（過熱感の足切り）", value=int(st.session_state.tab2_rsi_limit), step=5, key="t2_rsi_v2026_final")
    vol_lim = col_t2_2.number_input("最低出来高（5日平均）", value=int(st.session_state.tab2_vol_limit), step=5000, key="t2_vol_v2026_final")

    if st.button("🚀 強襲開始", key="btn_scan_t2_macro_v1"):
        st.session_state.tab2_scan_results = None
        gc.collect()

        t_global_start = time.time()

        with st.spinner("地合いと260日戦歴を同期中..."):
            # 🚨 19時リセットキャッシュキーによる物理取得
            raw = get_hist_data_cached(cache_key)
            t_fetch = time.time()
            
            if not raw:
                st.error("J-Quants APIからの応答が途絶。")
            else:
                full_df = clean_df(pd.DataFrame(raw))
                # 4桁コードを5桁化
                full_df['Code'] = full_df['Code'].astype(str).str.replace(r'^(\d{4})$', r'\10', regex=True)
                
                rsi_penalty = st.session_state.get('rsi_penalty', 0)
                effective_rsi_limit = float(rsi_lim) - rsi_penalty
                
                config_t2 = {
                    "f1_min": float(st.session_state.f1_min), "f1_max": float(st.session_state.f1_max),
                    "rsi_lim": effective_rsi_limit, "vol_lim": float(vol_lim),
                    "f12_ex_overvalued": st.session_state.f12_ex_overvalued,
                    "tactics": st.session_state.get("sidebar_tactics", "⚖️ バランス")
                }
                
                v_col = next((col for col in full_df.columns if col in ['Volume', 'AdjVo', 'Vo']), 'Volume')
                avg_vols_series = full_df.groupby('Code').tail(5).groupby('Code')[v_col].mean().fillna(0).astype(int)
                
                # 市場ターゲット絞り込み（先行フィルタ適用済みマスターとの論理積）
                m_mode = "大型" if "大型株" in st.session_state.preset_market else "中小型"
                target_keywords = ['プライム','一部'] if m_mode=="大型" else ['スタンダード','グロース','新興','マザーズ','JASDAQ','二部']
                m_targets = [c for c, m in master_map_t2.items() if any(k in str(m['Market']) for k in target_keywords)]
                
                latest_date = full_df['Date'].max()
                mask = (full_df['Date'] == latest_date) & (full_df['AdjC'] >= config_t2["f1_min"]) & (full_df['AdjC'] <= config_t2["f1_max"])
                valid_codes = set(full_df[mask]['Code']).intersection(set(m_targets)).intersection(set(avg_vols_series[avg_vols_series >= config_t2["vol_lim"]].index))
                
                df = full_df[full_df['Code'].isin(valid_codes)]
                t_clean = time.time()

                def scan_unit_t2_parallel(code, group, cfg, v_avg):
                    c_vals = group['AdjC'].values
                    lc = c_vals[-1]
                    rsi, _, _, hist = get_fast_indicators(c_vals)
                    
                    # RSI足切り（マクロ連動済）
                    if rsi > cfg["rsi_lim"]: return None
                    
                    # GC鮮度判定（3日以内）
                    gc_days = 0
                    if len(hist) >= 4:
                        if hist[-2] < 0 and hist[-1] >= 0: gc_days = 1
                        elif hist[-3] < 0 and hist[-1] >= 0: gc_days = 2
                        elif hist[-4] < 0 and hist[-1] >= 0: gc_days = 3
                    if gc_days == 0: return None

                    # 割安・赤字判定
                    if cfg["f12_ex_overvalued"]:
                        f_data = get_fundamentals(code[:4])
                        if f_data and (f_data.get("op", 0) or 0) < 0: return None
                    
                    is_assault = "狙撃優先" in cfg["tactics"]
                    t_rank, t_color, t_score, _ = get_assault_triage_info(gc_days, lc, rsi, group, is_strict=is_assault)
                    
                    h_vals = group['AdjH'].values
                    h14 = h_vals[-14:].max()
                    atr = h14 * 0.03 # 簡易ATR
                    
                    return {
                        'Code': code, 'lc': float(lc), 'RSI': float(rsi), 'T_Rank': t_rank, 'T_Color': t_color, 
                        'T_Score': t_score, 'GC_Days': gc_days, 'h14': float(h14), 'atr': float(atr), 'avg_vol': int(v_avg),
                        'df_context': group.tail(260) # 位相分析用に保持
                    }

                results = []
                with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
                    futures = [executor.submit(scan_unit_t2_parallel, c, g, config_t2, avg_vols_series.get(c, 0)) for c, g in df.groupby('Code')]
                    for f in concurrent.futures.as_completed(futures):
                        try:
                            res = f.result()
                            if res: results.append(res)
                        except: pass
                
                # スコア順ソート ＆ セクター分散（1業種3銘柄まで）
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
                
                # 🚨 プロファイル出力
                st.markdown(f"""
                <div style='background:rgba(0,0,0,0.5); padding:10px; border-radius:5px; border-left:3px solid #888; margin-bottom:10px; font-size:12px; color:#ddd;'>
                    <b>⏱️ スキャンプロファイル (TAB2)</b><br>
                    ・260日兵站確保: {t_fetch - t_global_start:.2f}秒<br>
                    ・データ規格統一 ＆ 先行フィルタ: {t_clean - t_fetch:.2f}秒<br>
                    ・並列GCスキャン: {t_calc - t_clean:.2f}秒<br>
                    <b>・合計: {t_calc - t_global_start:.2f}秒</b>
                </div>
                """, unsafe_allow_html=True)

    if st.session_state.tab2_scan_results:
        res_list = st.session_state.tab2_scan_results
        st.success(f"⚡ 強襲ロックオン: GC発動(3日以内) 上位 {len(res_list)} 銘柄（260日戦歴 ＆ セクター分散済）")
        
        sab_codes = " ".join([str(r['Code'])[:4] for r in res_list if str(r['T_Rank']).startswith(('S', 'A', 'B'))])
        st.info("📋 以下のコードをコピーして、照準（TAB3）にペースト可能だ。")
        st.code(sab_codes, language="text")

        for r in res_list:
            st.divider()
            c_code = str(r['Code']); m_info = master_map_t2.get(c_code, {})
            m_lower = str(m_info.get('Market', '')).lower()
            if 'プライム' in m_lower or '一部' in m_lower: badge_html = '<span style="background-color: #1a237e; color: #ffffff; padding: 0.2rem 0.6rem; border-radius: 4px; font-size: 11px; font-weight: bold;">🏢 プライム/大型</span>'
            elif 'グロース' in m_lower or 'マザーズ' in m_lower: badge_html = '<span style="background-color: #1b5e20; color: #ffffff; padding: 0.2rem 0.6rem; border-radius: 4px; font-size: 11px; font-weight: bold;">🚀 グロース/新興</span>'
            else: badge_html = f'<span style="background-color: #455a64; color: #ffffff; padding: 0.2rem 0.6rem; border-radius: 4px; font-size: 11px; font-weight: bold;">{m_info.get("Market","不明")}</span>'
            
            t_badge = f'<span style="background-color: {r["T_Color"]}; color: #ffffff; padding: 0.2rem 0.6rem; border-radius: 4px; font-size: 13px; font-weight: bold; margin-left: 0.5rem;">🎯 優先度: {r["T_Rank"]}</span>'
            sector_badge = f'<span style="background-color: #607d8b; color: #ffffff; padding: 0.1rem 0.5rem; border-radius: 4px; font-size: 12px; margin-left: 0.5rem;">🏭 {m_info.get("Sector", "不明")}</span>'
            
            # 位相・戦術メッセージ（Context）の物理抽出
            ctx = analyze_context(r['df_context'])
            
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
            
            # 位相・戦術メッセージの射出
            for msg in ctx['msgs']:
                if "警戒" in msg: st.error(msg)
                else: st.success(msg)
            
            lc_v, h14_v, atr_v = r.get('lc', 0), r.get('h14', 0), r.get('atr', 0)
            t_price = max(h14_v, lc_v + (atr_v * 0.5))
            d_price = t_price - atr_v
            
            m_cols = st.columns([1, 1, 1, 1.2, 1.5])
            m_cols[0].metric("最新終値", f"{int(lc_v):,}円")
            m_cols[1].metric("RSI", f"{r['RSI']:.1f}%")
            m_cols[2].metric("ボラ(推定)", f"{int(atr_v):,}円")
            m_cols[3].markdown(f'<div style="background: rgba(239, 83, 80, 0.05); padding: 0.5rem; border-radius: 8px; border: 1px solid rgba(239, 83, 80, 0.3); text-align: center;"><div style="font-size: 13px; color: rgba(250, 250, 250, 0.6); margin-bottom: 2px;">🛡️ 防衛線</div><div style="font-size: 1.6rem; font-weight: bold; color: #ef5350;">{int(d_price):,}円</div></div>', unsafe_allow_html=True)
            m_cols[4].markdown(f'<div style="background: rgba(255, 215, 0, 0.05); padding: 0.5rem; border-radius: 8px; border: 1px solid rgba(255, 215, 0, 0.2); text-align: center;"><div style="font-size: 13px; color: rgba(250, 250, 250, 0.6); margin-bottom: 2px;">🎯 トリガー</div><div style="font-size: 1.6rem; font-weight: bold; color: #FFD700;">{int(t_price):,}円</div></div>', unsafe_allow_html=True)
            
# --- 14. タブコンテンツ (TAB3: 精密スコープ) ---
with tab3:
    st.markdown('<h3 style="font-size: clamp(14px, 4.5vw, 24px); margin-bottom: 1rem;">🎯 【照準】精密スコープ（酒田五法・位相連動型 ＆ UI完全統合版）</h3>', unsafe_allow_html=True)
    
    # --- 🛡️ 1. 兵站管理：ファイルパスの物理定義 ---
    T3_AM_WATCH_FILE = f"saved_t3_am_watch_{user_id}.txt"
    T3_AM_DAILY_FILE = f"saved_t3_am_daily_{user_id}.txt"
    T3_AS_WATCH_FILE = f"saved_t3_as_watch_{user_id}.txt"
    T3_AS_DAILY_FILE = f"saved_t3_as_daily_{user_id}.txt"

    def load_t3_text(file_path):
        if os.path.exists(file_path):
            with open(file_path, "r", encoding="utf-8") as f:
                return f.read()
        return ""

    # --- 🛡️ 2. 通信記録の復元（セッションステート同期） ---
    if "t3_am_watch" not in st.session_state:
        st.session_state.t3_am_watch = load_t3_text(T3_AM_WATCH_FILE)
    if "t3_am_daily" not in st.session_state:
        st.session_state.t3_am_daily = load_t3_text(T3_AM_DAILY_FILE)
    if "t3_as_watch" not in st.session_state:
        st.session_state.t3_as_watch = load_t3_text(T3_AS_WATCH_FILE)
    if "t3_as_daily" not in st.session_state:
        st.session_state.t3_as_daily = load_t3_text(T3_AS_DAILY_FILE)

    col_s1, col_s2 = st.columns([1.2, 1.8])
    with col_s1:
        scope_mode = st.radio(
            "🎯 解析モードを選択", 
            ["🌐 【待伏】 押し目・逆張り", "⚡ 【強襲】 トレンド・順張り"], 
            key="t3_scope_mode_ultimate_fixed_color_v3"
        )
        is_ambush = "待伏" in scope_mode
        st.markdown("---")
        
        if is_ambush:
            watch_in = st.text_area(
                "🌐 【待伏】主力監視部隊", 
                value=st.session_state.t3_am_watch, 
                height=120, 
                key="t3_am_watch_ui"
            )
            daily_in = st.text_area(
                "🌐 【待伏】本日新規部隊", 
                value=st.session_state.t3_am_daily, 
                height=120, 
                key="t3_am_daily_ui"
            )
        else:
            watch_in = st.text_area(
                "⚡ 【強襲】主力監視部隊", 
                value=st.session_state.t3_as_watch, 
                height=120, 
                key="t3_as_watch_ui"
            )
            daily_in = st.text_area(
                "⚡ 【強襲】本日新規部隊", 
                value=st.session_state.t3_as_daily, 
                height=120, 
                key="t3_as_daily_ui"
            )
            
        run_scope = st.button("🔫 表示中の部隊を精密スキャン", use_container_width=True, type="primary")
        
    with col_s2:
        st.markdown("#### 🔍 索敵ステータス")
        if is_ambush:
            st.info("""
                **🛡️ 待伏（アンブッシュ）モード：底打ち反転の迎撃戦**
                - **主戦場**: 260日位相の安値圏（20%以下）。
                - **酒田五法判定**: 「たくり足」「陽の包み足」「はらみ足」を位相連動で精密検知。
                - **財務安全装置**: PBR 1.5倍以下をポジティブ（緑）評価。
            """)
        else:
            st.info("""
                **⚡ 強襲（アサルト）モード：トレンド初動の電撃戦**
                - **主戦場**: MACD GC直後の上昇加速局面。
                - **酒田五法判定**: 高値圏での「三尊」「首吊り線」等のダマシを位相解析で警告。
                - **品質保証**: ROE 10.0%以上の「稼ぐ力」を条件に攻撃続行。
            """)

    # --- 🛡️ 3. 解析・描画実行エンジン ---
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
        t_codes = list(dict.fromkeys([c for c in re.findall(r'(?<![A-Z0-9])[0-9]{3}[0-9A-Z](?![A-Z0-9])', all_text)]))
        
        if not t_codes:
            st.warning("有効な銘柄コードが確認できません。")
        else:
            t_global_start = time.time()
            with st.spinner(f"全 {len(t_codes)} 銘柄を酒田五法 ＆ 位相解析中..."):
                raw_data_dict = {}

                def fetch_parallel_t3(c):
                    try:
                        c_str = str(c); api_code = c_str + "0"
                        data = get_single_data(api_code, 1)
                        
                        if not data or not isinstance(data.get("bars"), list) or len(data.get("bars", [])) < 30:
                            try:
                                import yfinance as yf
                                tk = yf.Ticker(c_str + ".T")
                                hist = tk.history(period="1y")
                                if not hist.empty:
                                    bars = [{'Code': api_code, 'Date': dt.strftime('%Y-%m-%d'), 
                                             'AdjO': float(row['Open']), 'AdjH': float(row['High']), 
                                             'AdjL': float(row['Low']), 'AdjC': float(row['Close']), 
                                             'Volume': float(row['Volume'])} for dt, row in hist.iterrows()]
                                    data = {"bars": bars}
                            except: pass

                        f_data = get_fundamentals(c_str)
                        r_per, r_pbr, r_mcap, r_roe = None, None, None, None
                        
                        if f_data:
                            r_per = f_data.get('per') or f_data.get('PER') or f_data.get('trailingPE')
                            r_pbr = f_data.get('pbr') or f_data.get('PBR') or f_data.get('priceToBook')
                            r_mcap = f_data.get('mcap') or f_data.get('MCAP') or f_data.get('marketCap')
                            r_roe = f_data.get('roe') or f_data.get('ROE') or f_data.get('returnOnEquity')
                            
                            if r_roe is None:
                                ni, eq = f_data.get("NetIncome"), f_data.get("Equity")
                                if ni is not None and eq is not None:
                                    try: r_roe = (float(ni) / float(eq)) * 100
                                    except: pass

                        if any(v is None for v in [r_per, r_pbr, r_mcap, r_roe]):
                            try:
                                import yfinance as yf
                                tk = yf.Ticker(c_str + ".T")
                                info = tk.info
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

                with concurrent.futures.ThreadPoolExecutor(max_workers=5) as exe:
                    futs = [exe.submit(fetch_parallel_t3, c) for c in t_codes]
                    for f in concurrent.futures.as_completed(futs):
                        try:
                            res_c, res_data, r_per, r_pbr, r_mcap, r_roe = f.result()
                            if res_data:
                                raw_data_dict[str(res_c)] = {
                                    "data": res_data, "per": r_per, "pbr": r_pbr, "mcap": r_mcap, "roe": r_roe
                                }
                        except Exception: continue

                t_fetch = time.time()

                # --- ⚙️ 5. 解析計算ループ（酒田五法・戦術文脈解析 統合） ---
                scope_results = []
                for c in t_codes:
                    try:
                        target_key = str(c)
                        raw_s = raw_data_dict.get(target_key)
                        
                        api_code = target_key + "0"
                        c_name, c_sector, c_market = f"銘柄 {c}", "不明", "不明"
                        if not master_df.empty:
                            m_row = master_df[master_df['Code'].astype(str) == api_code]
                            if not m_row.empty:
                                c_name, c_sector, c_market = m_row.iloc[0]['CompanyName'], m_row.iloc[0]['Sector'], m_row.iloc[0]['Market']

                        bars = raw_s.get("data", {}).get("bars", []) if raw_s else []
                        
                        # 🚨 【修正】エラー表示の詳細化 ＆ IPO判定
                        if not bars or len(bars) < 30:
                            reason = "⚠️ 営業日数不足（上場直後の可能性）" if (bars and len(bars) < 200) else "⚠️ API取得エラー"
                            scope_results.append({
                                'code': target_key, 'name': c_name, 'lc': 0, 'h14': 0, 'l14': 0, 'ur': 0, 'bt_val': 0, 'atr_val': 0, 'rsi': 50,
                                'rank': '圏外💀', 'bg': '#616161', 'score': 0, 'reach_val': 0, 'gc_days': 0, 'df_chart': pd.DataFrame(),
                                'per': None, 'pbr': None, 'roe': None, 'mcap': "-",
                                'source': "🛡️ 監視" if c in watch_in else "🚀 新規", 'sector': c_sector, 'market': c_market, 
                                'alerts': [reason], 'pos_score': 50, 'error': True
                            })
                            continue

                        df_raw = pd.DataFrame(bars)
                        if 'Code' not in df_raw.columns: df_raw['Code'] = api_code
                        df_s = clean_df(df_raw)
                        df_chart_full = calc_technicals(df_s)
                        
                        # 🚨 【物理復元】酒田五法解析用・生データ抽出
                        t_latest, t_prev, t_pprev = df_chart_full.iloc[-1], df_chart_full.iloc[-2], df_chart_full.iloc[-3]
                        lc, lo, lh, ll = float(t_latest['AdjC']), float(t_latest['AdjO']), float(t_latest['AdjH']), float(t_latest['AdjL'])
                        pc, po, ph, pl = float(t_prev['AdjC']), float(t_prev['AdjO']), float(t_prev['AdjH']), float(t_prev['AdjL'])
                        ppc, ppo, pph = float(t_pprev['AdjC']), float(t_pprev['AdjO']), float(t_pprev['AdjH'])
                        
                        rsi_v, atr_v = float(t_latest.get('RSI', 50)), float(t_latest.get('ATR', lc * 0.05))
                        h14 = float(df_chart_full.tail(15).iloc[:-1]['AdjH'].max())
                        l14 = float(df_chart_full.tail(15).iloc[:-1]['AdjL'].min())
                        ur_v = h14 - l14
                        
                        df_mini = df_chart_full.tail(260).copy()
                        ctx = analyze_context(df_mini)
                        pos_score = ctx['pos']

                        score, alerts, gc_days = 0, [], 0
                        
                        if is_ambush:
                            score = 4
                            bt_val = int(h14 - (ur_v * (st.session_state.push_r / 100.0)))
                            m1, m2 = float(t_latest.get('MACD_Hist', 0)), float(t_prev.get('MACD_Hist', 0))
                            _, _, t_score, _ = get_triage_info(m1, m2, rsi_v, lc, bt_val, mode="待伏")
                            score += t_score
                            if res_pbr is not None and res_pbr <= 1.5: score += 2
                            
                            is_low_zone = pos_score < 30
                            
                            # 🚨 【詳細改修】酒田五法・戦術文脈解析
                            # 1. たくり足
                            body_v, shad_l, full_rng = abs(lc - lo), min(lc, lo) - ll, lh - ll
                            if full_rng > 0 and shad_l > (body_v * 2.5) and (shadow_l / full_rng) > 0.6:
                                if is_low_zone:
                                    alerts.append("🔥 【酒田・たくり線】下位での強力な買い支え。売り方の最終攻勢を押し戻した『逆転』の兆候。")
                                    score += 5
                                else:
                                    alerts.append("🟢 【酒田・たくり線】一時的な買い支えを確認。押し目候補として監視。")
                                    score += 2

                            # 2. 陽の包み足 (Bullish Engulfing)
                            if lc > lo and pc < po and lc >= po and lo <= pc:
                                if is_low_zone:
                                    alerts.append("🔥 【酒田・包み足】前日の絶望を強気が完全に飲み込んだ。主導権が買い方に移転した『反撃開始』の狼煙。")
                                    score += 4
                                else:
                                    alerts.append("🟢 【酒田・包み足】強気への転換を示唆。直近高値突破を注視。")
                                    score += 1

                            # 3. 陽のはらみ足 (Bullish Harami)
                            if pc > po and lc > lo and lc < po and lo > pc:
                                if is_low_zone:
                                    alerts.append("🔥 【酒田・はらみ足】下落エネルギーが収束し、内部に『反転の芽』を孕んだ。膠着から上放れを狙う局面。")
                                    score += 3
                                else:
                                    alerts.append("🟢 【酒田・はらみ足】売り枯れを確認。均衡が崩れる方向を注視。")
                                    score += 1

                            reach_rate = ((h14 - lc) / (h14 - bt_val) * 100) if (h14 - bt_val) > 0 else 0
                            rank, bg_c = ("S級待伏🔥", "#1b5e20") if score >= 12 else ("A級待伏💎", "#2e7d32") if score >= 8 else ("B級待伏🛡️", "#4caf50") if score >= 5 else ("圏外💀", "#616161")
                        else:
                            # 強襲モード
                            bt_val = int(max(h14, lc + (atr_v * 0.5)))
                            hist_vals = df_mini['MACD_Hist'].tail(5).values
                            gc_score, gc_days = 0, 0
                            if len(hist_vals) >= 2:
                                if hist_vals[-2] < 0 and hist_vals[-1] >= 0: gc_days, gc_score = 1, 60
                                elif len(hist_vals) >= 3 and hist_vals[-3] < 0 and hist_vals[-1] >= 0: gc_days, gc_score = 2, 40
                                else: gc_score = 5
                            
                            is_high_zone = pos_score > 75
                            # 高値圏の警戒シグナル
                            if is_high_zone:
                                # 三尊
                                if pph > ph and lh > ph and abs(pph - lh) < (pph * 0.02) and rsi_v > 70:
                                    alerts.append("🚨 【酒田・三尊】高値圏での三転突破失敗。天井形成の恐れ大。戦術的撤退を検討せよ。")
                                # 首吊り線
                                if full_rng > 0 and shad_l > (body_v * 2.5) and (shadow_l / full_rng) > 0.6:
                                    alerts.append("🚨 【酒田・首吊り線】高値圏でのたくり。買い方の最終エネルギー枯渇を示唆。暴落に備えよ。")
                            
                            if res_roe and res_roe >= 10.0: gc_score += 15
                            score = gc_score
                            reach_rate = (lc / h14) * 100 if h14 > 0 else 0
                            rank, bg_c = ("S級強襲⚡", "#1b5e20") if score >= 80 else ("A級強襲🔥", "#2e7d32") if score >= 60 else ("B級強襲📈", "#4caf50") if score >= 40 else ("圏外💀", "#616161")

                        scope_results.append({
                            'code': target_key, 'name': c_name, 'lc': lc, 'h14': h14, 'l14': l14, 'ur': ur_v, 'bt_val': bt_val, 'atr_val': atr_v, 'rsi': rsi_v,
                            'rank': rank, 'bg': bg_c, 'score': score, 'reach_val': reach_rate, 'gc_days': gc_days, 'df_chart': df_mini, 
                            'per': res_per, 'pbr': res_pbr, 'roe': res_roe, 'mcap': res_mcap_str,
                            'source': "🛡️ 監視" if target_key in watch_in else "🚀 新規", 'sector': c_sector, 'market': c_market, 
                            'alerts': alerts + ctx['msgs'], 'pos_score': pos_score, 'error': False
                        })
                    except: continue

                rank_order = {"S": 4, "A": 3, "B": 2, "C": 1, "圏外": 0}
                for res in scope_results:
                    clean_rank = re.sub(r'[^SABC圏外]', '', res['rank'])
                    res['r_val'] = rank_order.get(clean_rank, 0)
                scope_results = sorted(scope_results, key=lambda x: (x['r_val'], x['score'], x['reach_val']), reverse=True)
                
                t_calc = time.time()

                # --- 🚨 UI描画部は変更なし（中略死罪のため全行出力） ---
                for index, r in enumerate(scope_results):
                    st.divider()
                    source_color = "#42a5f5" if "監視" in r['source'] else "#ffa726"
                    m_lower = str(r['market']).lower()
                    if 'プライム' in m_lower or '一部' in m_lower: 
                        m_badge = '<span style="background-color: #1a237e; color: #ffffff; padding: 0.2rem 0.6rem; border-radius: 4px; font-size: 11px; font-weight: bold;">🏢 プライム/大型</span>'
                    elif 'グロース' in m_lower or 'マザーズ' in m_lower: 
                        m_badge = '<span style="background-color: #1b5e20; color: #ffffff; padding: 0.2rem 0.6rem; border-radius: 4px; font-size: 11px; font-weight: bold;">🚀 グロース/新興</span>'
                    else: 
                        m_badge = f'<span style="background-color: #455a64; color: #ffffff; padding: 0.2rem 0.6rem; border-radius: 4px; font-size: 11px; font-weight: bold;">{r["market"]}</span>'
                    
                    s_badge = f"<span style='background-color:{source_color}; color:white; padding:2px 6px; border-radius:4px; font-size:12px;'>{r['source']}</span>"
                    t_badge = f"<span style='background-color:{r['bg']}; color:white; padding:2px 8px; border-radius:4px; margin-left:10px; font-weight:bold;'>🎯 優先度: {r['rank']}</span>"
                    gc_badge = f"<span style='background-color: #1b5e20; color: #ffffff; padding: 2px 10px; border-radius: 4px; font-size: 13px; font-weight: bold; margin-left: 10px; border: 1px solid #81c784;'>⚡ GC {r['gc_days']}日目</span>" if r.get('gc_days', 0) > 0 else ""

                    st.markdown(f"""<div style="margin-bottom: 0.8rem;"><h3 style="font-size: clamp(18px, 5vw, 28px); font-weight: bold; margin: 0 0 0.3rem 0;">{s_badge} ({r['code']}) {r['name']}</h3><div style="display: flex; flex-wrap: wrap; gap: 6px; align-items: center;">{m_badge}{t_badge}{gc_badge}<span style="background-color: rgba(38, 166, 154, 0.15); border: 1px solid #26a69a; color: #26a69a; padding: 0.1rem 0.5rem; border-radius: 4px; font-size: 12px;">RSI: {r['rsi']:.1f}%</span><span style="background-color: rgba(255,255,255,0.1); padding: 2px 8px; border-radius:4px; font-size:12px; color:#aaa;">位相: {r['pos_score']:.1f}%</span></div></div>""", unsafe_allow_html=True)
                    
                    if r.get('alerts'):
                        for alert in r['alerts']:
                            if any(mark in alert for mark in ["🟢", "⚡", "🔥", "反撃", "期待"]): st.success(alert)
                            else: st.error(alert)

                    if r.get('error'):
                        st.warning("⚠️ データの取得に失敗しました。")
                        continue
                    
                    sc_left, sc_mid, sc_right = st.columns([2.5, 3.5, 5.0])
                    with sc_left:
                        def safe_int(val):
                            try:
                                if val is None or pd.isna(val) or np.isinf(val): return 0
                                return int(val)
                            except: return 0
                        h14_v, l14_v, ur_v, lc_v = safe_int(r['h14']), safe_int(r['l14']), safe_int(r['ur']), safe_int(r['lc'])
                        atr_v = r.get('atr_val', 0); atr_pct = (atr_v / lc_v * 100) if lc_v > 0 else 0
                        c_m1, c_m2 = st.columns(2); c_m1.metric("直近高値", f"{h14_v:,}円"); c_m2.metric("直近安値", f"{l14_v:,}円")
                        c_m3, c_m4 = st.columns(2); c_m3.metric("上昇幅", f"{ur_v:,}円"); c_m4.metric("最新終値", f"{lc_v:,}円")
                        st.metric("🌪️ 1ATR", f"{safe_int(atr_v):,}円", f"ボラ: {atr_pct:.1f}%", delta_color="off")
                    
                    with sc_mid:
                        roe_v, per_v, pbr_v = r.get('roe'), r.get('per'), r.get('pbr')
                        per_s = f"{per_v:.1f}倍" if per_v is not None else "-"
                        per_c = "#26a69a" if (per_v is not None and per_v <= 20.0) else "#ef5350" if per_v is not None else "#888"
                        pbr_s = f"{pbr_v:.2f}倍" if pbr_v is not None else "-"
                        pbr_c = "#26a69a" if (pbr_v is not None and pbr_v <= 1.5) else "#ef5350" if pbr_v is not None else "#888"
                        roe_s = f"{roe_v:.1f}%" if roe_v is not None else "-"
                        roe_c = "#26a69a" if (roe_v and roe_v >= 10.0) else "#ef5350" if roe_v is not None else "#888"
                        box_title = "🎯 買値目標" if is_ambush else "🎯 トリガー"
                        
                        st.markdown(f"""
                            <div style='background:rgba(255,215,0,0.05); padding:1.2rem; border-radius:10px; border:1px solid rgba(255,215,0,0.3); text-align:center;'>
                                <div style='font-size:14px; color: #eee; margin-bottom: 0.4rem;'>{box_title}</div>
                                <div style='font-size:2.4rem; font-weight:bold; color:#FFD700; margin: 0.2rem 0;'>{int(r['bt_val']):,}円</div>
                                <div style='display:flex; justify-content:space-around; margin-top:10px; font-size:12px; border-top:1px dashed #444; padding-top:10px;'>
                                    <div style='flex:1;'><div style='color:#888; font-size:10px;'>PER</div><div style='color:{per_c}; font-weight:bold; font-size:1.1rem;'>{per_s}</div></div>
                                    <div style='flex:1;'><div style='color:#888; font-size:10px;'>PBR</div><div style='color:{pbr_c}; font-weight:bold; font-size:1.1rem;'>{pbr_s}</div></div>
                                    <div style='flex:1;'><div style='color:#888; font-size:10px;'>ROE</div><div style='color:{roe_c}; font-weight:bold; font-size:1.1rem;'>{roe_s}</div></div>
                                </div>
                                <div style='margin-top:5px; border-top:1px solid rgba(255,255,255,0.05); padding-top:5px;'>
                                    <span style='color:#888; font-size:11px;'>時価総額: </span><span style='color:#fff; font-size:11px; font-weight:bold;'>{r['mcap']}</span>
                                </div>
                            </div>
                        """, unsafe_allow_html=True)

                    with sc_right:
                        c_target = r['bt_val']; rec_tps = [2.0, 3.0] if any(m in r['rank'] for m in ["⚡", "🔥", "S"]) else [0.5, 1.0]
                        html_matrix = f"<div style='background:rgba(255,255,255,0.05); padding:1.2rem; border-radius:8px; border-left:5px solid #FFD700; min-height: 125px;'><div style='font-size:14px; color:#aaa; margin-bottom:12px; border-bottom:1px solid #444; padding-bottom:4px;'>📊 動的ATRマトリクス (基準:{int(c_target):,}円)</div><div style='display:flex; gap:30px;'><div style='flex:1;'><div style='color:#26a69a; border-bottom:2px solid #26a69a; margin-bottom:8px;'>【利確目安】</div>"
                        for m in [0.5, 1.0, 2.0, 3.0]:
                            val = int(c_target + (atr_v * m)); pct = ((val / c_target) - 1) * 100 if c_target > 0 else 0
                            style = "background:rgba(38,166,154,0.15); border:1px solid #26a69a; border-radius:4px; padding:2px 6px;" if m in rec_tps else "padding:3px 6px;"
                            html_matrix += f"<div style='display:flex; justify-content:space-between; margin-bottom:4px; {style}'><span>+{m}ATR <span style='font-size:10px; color:#888;'>({pct:+.1f}%)</span></span><b style='font-size:1.1rem;'>{val:,}</b></div>"
                        html_matrix += "</div><div style='flex:1;'><div style='color:#ef5350; border-bottom:2px solid #ef5350; margin-bottom:8px;'>【防衛目安】</div>"
                        for m in [0.5, 1.0, 2.0]:
                            val = int(c_target - (atr_v * m)); pct = (1 - (val / c_target)) * 100 if c_target > 0 else 0
                            style = "background:rgba(239,83,80,0.15); border:1px solid #ef5350; border-radius:4px; padding:2px 6px;" if m == 1.0 else "padding:3px 6px;"
                            html_matrix += f"<div style='display:flex; justify-content:space-between; margin-bottom:4px; {style}'><span>-{m}ATR <span style='font-size:10px; color:#888;'>({pct:.1f}%)</span></span><b style='font-size:1.1rem;'>{val:,}</b></div>"
                        st.markdown(html_matrix + "</div></div></div>", unsafe_allow_html=True)

                    st.markdown(render_technical_radar(r['df_chart'], r['bt_val'], st.session_state.bt_tp), unsafe_allow_html=True)
                    st.markdown("---")
                    draw_chart(r['df_chart'], r['bt_val'], chart_key=f"t3_chart_ultimate_v3_final_{r['code']}_{index}")
                    
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

# --- 9. タブコンテンツ (TAB5: 交戦モニター) ---
with tab5:
    st.markdown('<h3 style="font-size: clamp(14px, 4.5vw, 24px); margin-bottom: 1rem;">📡 交戦モニター (全軍生存圏レーダー)</h3>', unsafe_allow_html=True)
    st.caption("※ 銘柄コードと株数を入力し、確定（Enter）後に『🔄 全軍同期』を押してください。")

    # 🚨 【物理パッチ】Enterで直下移動 ＆ トップへの跳ね返り防止スクリプト
    components.html(
        """
        <script>
        const doc = window.parent.document;
        const patchDataEditor = () => {
            const editors = doc.querySelectorAll('div[data-testid="stDataEditor"]');
            editors.forEach(editor => {
                editor.addEventListener('keydown', (e) => {
                    if (e.key === 'Enter') {
                        const downArrowEvent = new KeyboardEvent('keydown', {
                            key: 'ArrowDown',
                            code: 'ArrowDown',
                            keyCode: 40,
                            which: 40,
                            bubbles: true
                        });
                        e.target.dispatchEvent(downArrowEvent);
                    }
                }, true);
            });
        };
        const observer = new MutationObserver(patchDataEditor);
        observer.observe(doc.body, { childList: true, subtree: true });
        patchDataEditor();
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
                temp_df['銘柄'] = temp_df['銘銘柄'] = temp_df['銘柄'].astype(str).str.replace(r'\.0$', '', regex=True).replace('nan', '')
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
                            working_df.loc[working_df['銘柄'].astype(str).str.replace(r'\.0$', '', regex=True) == str(c_code), '現在値'] = c_price
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
        name_map = dict(zip(master_df['Code'].astype(str), master_df['CompanyName']))

    for index, row in working_df.iterrows():
        ticker_raw = str(row.get('銘柄', '')).replace('.0', '').strip()
        if not ticker_raw or ticker_raw in ["nan", "None", ""]: continue
        
        ticker_search = ticker_raw + "0" if len(ticker_raw) == 4 else ticker_raw
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
        # 🚨 損切の％を赤表示にするため delta_color="normal" へ修正（マイナス値＝赤）
        m_cols[0].metric("損切目安", f"¥{final_sl:,}", f"{sl_pct:+.1f}%" if sl_pct != 0 else None, delta_color="normal")
        m_cols[1].metric("買値", f"¥{buy:,}")
        
        with m_cols[2]:
            # 🚨 順序を「現在値 / 騰落率」に変更し、フォントサイズを13pxへ拡大
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
                hovertemplate=f"部隊: {company_name}<br>現在地: ¥%{{x:,.0f}}<br>損益: ¥{profit_amt:+,}<extra></extra>"
            ))
            
            fig.update_layout(
                height=70, showlegend=False, 
                yaxis=dict(showticklabels=False, range=[-1,1], fixedrange=True), 
                xaxis=dict(showgrid=False, range=[mi, mx], tickformat=",.0f", fixedrange=True), 
                margin=dict(l=10,r=10,t=5,b=5), paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)', dragmode=False
            )
            st.plotly_chart(fig, use_container_width=True, key=f"bar_{ticker_raw}_{index}", config={'displayModeBar': False})
        
        st.markdown("<div style='margin-bottom: 20px;'></div>", unsafe_allow_html=True)

    if active_squads == 0:
        st.info("部隊未展開。有効な銘柄コードがないか、保存されていません。")
        
with tab6:
    import datetime as dt_module
    st.markdown('<h3 style="font-size: clamp(14px, 4.5vw, 24px); margin-bottom: 1rem;">📁 事後任務報告 (AAR) & 戦績ダッシュボード</h3>', unsafe_allow_html=True)
    st.caption("※ 記録の編集は下部の『🛠️ 戦績編集コンソール』で行ってください。")
    
    AAR_FILE = f"saved_aar_log_{user_id}.csv"
    
    # --- 🛡️ 1. 物理初期化回路 ---
    def get_scale_for_code(code):
        api_code = str(code) if len(str(code)) == 5 else str(code) + "0"
        if not master_df.empty:
            m_row = master_df[master_df['Code'] == api_code]
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
