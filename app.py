import streamlit as st
import requests
import pandas as pd
import os
import re
import json
import datetime
from datetime import datetime, timedeltaF
from io import BytesIO
import plotly.graph_objects as go
import numpy as np
import concurrent.futures
import streamlit.components.v1 as components
import gc
import pytz
import time 

# 🚨 新規配備：通信セッションの永続化とリトライ機構（Connection Pooling）
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

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

import streamlit as st
import streamlit.components.v1 as components

# 【重要】認証スクリプトを一度だけ注入するためのコンテナ
if "js_injected" not in st.session_state:
    st.session_state.js_injected = False

# ==========================================
# ⚡ 全銘柄現在値・一括取得エンジン（J-Quants V2 正式仕様）
# ==========================================
@st.cache_data(ttl=3600, show_spinner=False)
def get_all_latest_prices_bulk():
    """直近の営業日データを1回のリクエストで全銘柄分取得する防弾エンジン"""
    import datetime
    import pandas as pd
    import time

    base_time = datetime.datetime.utcnow() + datetime.timedelta(hours=9)

    for i in range(1, 10): 
        dt_str = (base_time - datetime.timedelta(days=i)).strftime('%Y%m%d')
        # 🚨 V2の正式エンドポイントに完全修正！
        url = f"{BASE_URL}/equities/bars/daily?date={dt_str}"
        
        try:
            time.sleep(1.05) # Lightプラン制限対策
            r = api_session.get(url, timeout=15.0)
            
            if r.status_code == 200:
                raw_json = r.json()
                # 🚨 V1/V2のキー名揺れを完全吸収
                data = raw_json.get("daily_quotes") or raw_json.get("data") or raw_json.get("results") or []
                if data:
                    df = pd.DataFrame(data)
                    prices_map = {}
                    for _, row in df.iterrows():
                        code_4digit = str(row['Code'])[:4]
                        val = row.get('Close') or row.get('C') or row.get('AdjC')
                        if pd.notna(val):
                            prices_map[code_4digit] = float(val)
                    return prices_map
            elif r.status_code == 429:
                time.sleep(2.0) 
        except Exception:
            pass 
            
    return {}

# ==========================================
# 📊 【新・爆速版】ローカルDBからのファンダメンタルズ読込エンジン
# ==========================================
import pickle
import os

@st.cache_resource(ttl=3600*24) # 1日キャッシュしてメモリに常駐させる
def load_local_fundamentals_db():
    """19時にBotが集めたデータを一瞬でメモリにロードする"""
    db_path = os.path.join(os.path.dirname(__file__), "fundamentals_db.pkl")
    if os.path.exists(db_path):
        with open(db_path, "rb") as f:
            return pickle.load(f)
    return {}

def get_historical_statements(code):
    """API通信を一切行わず、ロード済みのローカルDBからデータを返すだけ"""
    db = load_local_fundamentals_db()
    
    if not db:
        return None
        
    api_code = str(code) if len(str(code)) >= 5 else str(code) + "0"
    return db.get(api_code, None)

# ==========================================
# 🧠 ファンダメンタルズ解析エンジン（直近2四半期連続 YoY対応版）
# ==========================================
def analyze_fundamental_momentum(df, mode="buy", sales_req=7.0, ord_req=15.0):
    import streamlit as st
    import pandas as pd

    try:
        if df is None or len(df) < 1:
            return False, ""

        # V2の真のカラム名を指定
        c_sales = 'Sales'
        c_op = 'OP'
        c_ord = 'OdP'
        c_eps = 'EPS'
        c_profit = 'NP'
        c_type = 'CurPerType'

        # 安全のため、カラムが存在しない場合は0で埋める
        std_df = df.copy()
        for col in [c_sales, c_op, c_ord, c_eps, c_profit, c_type]:
            if col not in std_df.columns:
                std_df[col] = 0.0 if col != c_type else ""

        def to_float(val):
            try:
                if pd.isna(val) or str(val).strip() == '': return 0.0
                return float(str(val).replace(',', ''))
            except:
                return 0.0

        # 💡 累計決算を「四半期単体」に分解する
        for i in range(1, len(df)):
            try:
                curr_sales = to_float(df[c_sales].iloc[i])
                prev_sales = to_float(df[c_sales].iloc[i-1])
            except:
                curr_sales, prev_sales = 0.0, 0.0
                
            curr_type = str(df[c_type].iloc[i])
            
            is_q1 = False
            if '1Q' in curr_type or 'Q1' in curr_type:
                is_q1 = True
            elif curr_sales < prev_sales and prev_sales > 0:
                is_q1 = True
                
            if not is_q1:
                # 2Q〜4Qの場合、前回の累計を引いて単体にする
                for col in [c_sales, c_op, c_ord, c_eps, c_profit]:
                    try:
                        c_val = to_float(df[col].iloc[i])
                        p_val = to_float(df[col].iloc[i-1])
                        col_idx = std_df.columns.get_loc(col)
                        std_df.iat[i, col_idx] = c_val - p_val
                    except Exception:
                        pass

        # 🚨 2四半期連続でYoYを計算するためには最低6四半期分の単体データが必要
        if len(std_df) < 6:
            return False, ""

        # 🎯 データの抽出
        q0 = std_df.iloc[-1] # 最新四半期
        y0 = std_df.iloc[-5] # 最新の前年同期 (4つ前)

        q1 = std_df.iloc[-2] # 1つ前の四半期
        y1 = std_df.iloc[-6] # 1つ前の前年同期 (1つ前の4つ前)

        def get_val(row, primary_col, fallback_col=None):
            v = to_float(row.get(primary_col, 0.0))
            if v == 0.0 and fallback_col:
                v = to_float(row.get(fallback_col, 0.0))
            return v

        def calc_gr(c, p):
            if p <= 0:
                return 999.0 if c > 0 else -999.0
            return ((c - p) / abs(p)) * 100.0

        # 最新四半期 (q0) のYoY成長率
        s_q0 = calc_gr(get_val(q0, c_sales), get_val(y0, c_sales))
        op_q0 = calc_gr(get_val(q0, c_op), get_val(y0, c_op))
        or_q0 = calc_gr(get_val(q0, c_ord), get_val(y0, c_ord))
        ep_q0 = calc_gr(get_val(q0, c_eps, c_profit), get_val(y0, c_eps, c_profit))

        # 1つ前の四半期 (q1) のYoY成長率
        s_q1 = calc_gr(get_val(q1, c_sales), get_val(y1, c_sales))
        op_q1 = calc_gr(get_val(q1, c_op), get_val(y1, c_op))
        or_q1 = calc_gr(get_val(q1, c_ord), get_val(y1, c_ord))
        ep_q1 = calc_gr(get_val(q1, c_eps, c_profit), get_val(y1, c_eps, c_profit))

        # --- 📈 TAB1 (買い) ロジック ---
        if mode == "buy":
            # 1. 最新(q0) と 1つ前(q1) の両方が A級基準（売上7%以上、利益15%以上）をクリアしているか
            pass_a_q0 = (s_q0 >= sales_req and op_q0 >= 15.0 and or_q0 >= ord_req and ep_q0 >= 15.0)
            pass_a_q1 = (s_q1 >= sales_req and op_q1 >= 15.0 and or_q1 >= ord_req and ep_q1 >= 15.0)

            if not (pass_a_q0 and pass_a_q1):
                return False, "" # 2期連続でクリアできなければ不合格

            # 2. 最新(q0) と 1つ前(q1) の両方が S級基準（売上10%以上、利益20%以上）をクリアしているか
            pass_s_q0 = (s_q0 >= 10.0 and op_q0 >= 20.0 and or_q0 >= 20.0 and ep_q0 >= 20.0)
            pass_s_q1 = (s_q1 >= 10.0 and op_q1 >= 20.0 and or_q1 >= 20.0 and ep_q1 >= 20.0)

            if pass_s_q0 and pass_s_q1:
                return True, "S級🎯"

            return True, "A級🟢"
            
        # --- 📉 TAB2 (売り) ロジック ---
        elif mode == "sell":
            pass_sell_q0 = (s_q0 < 5.0 and op_q0 < 10.0 and or_q0 < 5.0 and ep_q0 < 10.0)
            pass_sell_q1 = (s_q1 < 5.0 and op_q1 < 10.0 and or_q1 < 5.0 and ep_q1 < 10.0)

            if not (pass_sell_q0 and pass_sell_q1):
                return False, ""
            
            if s_q0 < 0 and op_q0 < 0 and or_q0 < 0 and ep_q0 < 0:
                return True, "S級💀"
            return True, "A級📉"
            
    except Exception:
        pass
    return False, ""
    
def inject_auth_script():
    if not st.session_state.js_injected:
        container = st.empty()
        with container:
            components.html(
                """
                <script>
                const doc = window.parent.document;
                window.loginTriggered = window.loginTriggered || false;

                function tryAutoLogin() {
                    if (window.loginTriggered) return true;
                    
                    const input = doc.querySelector('input[type="password"]');
                    
                    // 値が入っており、かつ空でない場合
                    if (input && input.value.length > 0) {
                        window.loginTriggered = true; 
                        input.blur();
                        
                        // 💡 重要：Enterキーイベントを強制的に発生させる
                        const enterEvent = new KeyboardEvent('keydown', {
                            bubbles: true,
                            cancelable: true,
                            key: 'Enter',
                            code: 'Enter',
                            keyCode: 13,
                            which: 13
                        });
                        input.dispatchEvent(enterEvent);
                        
                        // 念のため少し遅れてボタンクリックも併用（保険）
                        const buttons = Array.from(doc.querySelectorAll('button')).filter(b => b.innerText.includes("認証"));
                        if (buttons.length > 0) {
                            setTimeout(() => { buttons[0].click(); }, 100);
                        }
                        
                        return true;
                    }
                    return false;
                }

                // 監視開始
                const monitor = setInterval(() => {
                    if (tryAutoLogin()) clearInterval(monitor);
                }, 200);

                // 入力イベント検知
                doc.addEventListener('input', (e) => {
                    if (e.target.type === 'password') tryAutoLogin();
                });
                </script>
                """,
                height=0,
            )
        st.session_state.js_injected = True

def check_password():
    # 認証スクリプトの注入（初回のみ）
    inject_auth_script()
    
    if "password_correct" not in st.session_state:
        st.session_state["password_correct"] = False
        
    if not st.session_state["password_correct"]:
        st.markdown('<h1 style="text-align: center; color: #2e7d32; margin-top: 10vh;">🎯 戦術スコープ『鉄の掟』</h1>', unsafe_allow_html=True)
        
        col1, col2, col3 = st.columns([1, 2, 1])
        with col2:
            acc_code = st.text_input(
                "Access Code", type="password", 
                label_visibility="collapsed", 
                placeholder="アクセスコード",
                key="input_access_code"
            )
            
            submitted = st.button("認証 (ENTER)", use_container_width=True)
            
            if submitted:
                if acc_code in ALLOWED_PASSWORDS:
                    st.session_state["password_correct"] = True
                    st.session_state["current_user"] = acc_code
                    st.rerun()
                elif acc_code != "":
                    st.error("🚨 認証失敗：コードが違います。")
        return False
    return True

if not check_password(): st.stop()

# --- 🚀 物理配線：19:00自動パージ用キャッシュキー生成（矛盾排除・完全統合版） ---
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

cache_key = get_cache_key()

# =========================================================
# 🛡️ 【絶対防壁】19時キャッシュクリア時の強制復旧フック
# =========================================================
def force_load_saved_settings():
    """パージの瞬間に SETTINGS_FILE から設定と除外銘柄を強制救出する"""
    try:
        if os.path.exists(SETTINGS_FILE): 
            with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
                saved_data = json.load(f)
                
                # 1. 保存されていた全ての設定をセッションに叩き込む
                for k, v in saved_data.items():
                    st.session_state[k] = v  
                    
                # 2. 除外銘柄（gigi_input）をリスト化してシステム内部変数にも完全同期
                if "gigi_input" in saved_data and saved_data["gigi_input"]:
                    raw_str = saved_data["gigi_input"].replace('、', ',').replace(' ', ',').replace('　', ',')
                    codes = [c.strip() for c in raw_str.split(',') if c.strip()]
                    st.session_state.exclude_codes = codes
                    st.session_state.gigi_codes = codes
    except Exception as e:
        pass

current_sys_cache_key = get_cache_key()
if st.session_state.get("last_sys_cache_key") != current_sys_cache_key:
    st.session_state.last_sys_cache_key = current_sys_cache_key
    force_load_saved_settings()
# =========================================================

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

    // 🎯 開発参謀パッチ：ステルス（ホバー透過）機能の追加
    btn.style.opacity = '0.15'; // 普段は透明度15%で背景を透過させ、邪魔にならないようにする
    btn.style.transition = 'opacity 0.3s ease'; // ふわっと表示させるアニメーション

    // カーソルが近付いた（乗った）らハッキリ見えるようにする
    btn.onmouseenter = function() {
        this.style.opacity = '1.0';
    };
    // カーソルが離れたら再び気配を消す
    btn.onmouseleave = function() {
        this.style.opacity = '0.15';
    };

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

# --- 2. 認証・通信設定（Connection Poolingの導入） ---
user_id = st.session_state.get("current_user", "UNKNOWN")
st.markdown(f'<h1 style="font-size: clamp(24px, 7vw, 42px); font-weight: 900; border-bottom: 2px solid #2e7d32; padding-bottom: 0.5rem; margin-bottom: 1rem;">🎯 戦術スコープ『鉄の掟』 <span style="font-size: 16px; font-weight: normal; color: #888;">(ID: {user_id[:4]}***)</span></h1>', unsafe_allow_html=True)

# ==========================================
# ☁️ 究極永続化ストレージ（Google Sheets 直結仕様）
# ==========================================
import gspread
from google.oauth2.service_account import Credentials
import pandas as pd

# 👇 【重要】ここにスプレッドシートIDを貼り付けてください 👇
SPREADSHEET_ID = "1PZZwhGvUgTHd0ptY2g9AmLloZoB9qZpr-VIx6DrYIdw"

@st.cache_resource
# キャッシュを解除し、リアルタイムに接続診断を行う仕様に換装
def init_gspread():
    try:
        if "gcp_service_account" not in st.secrets:
            st.sidebar.error("❌ 金庫(Secrets)の中に 'gcp_service_account' が見つかりません。")
            return None
            
        scopes = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
        
        # ▼▼▼ 開発参謀パッチ：鍵の改行コード(\n)を本物の改行に強制翻訳 ▼▼▼
        gcp_credentials = dict(st.secrets["gcp_service_account"])
        gcp_credentials["private_key"] = gcp_credentials["private_key"].replace('\\n', '\n')
        # ▲▲▲ ここまで ▲▲▲
        
        creds = Credentials.from_service_account_info(gcp_credentials, scopes=scopes)
        return gspread.authorize(creds)
    except Exception as e:
        st.sidebar.error(f"🚨 Google認証エラー: {e}")
        return None

g_client = init_gspread()

try:
    if g_client:
        db_sheet = g_client.open_by_key(SPREADSHEET_ID)
        st.sidebar.success(f"🔌 DB接続成功: {db_sheet.title}")
    else:
        db_sheet = None
except Exception as e:
    db_sheet = None
    st.sidebar.error(f"🚨 シート取得エラー: {e}")

def get_or_create_worksheet(sheet_name):
    if not db_sheet: return None
    try:
        return db_sheet.worksheet(sheet_name)
    except gspread.exceptions.WorksheetNotFound:
        try:
            return db_sheet.add_worksheet(title=sheet_name, rows="1000", cols="20")
        except Exception as e:
            st.sidebar.error(f"🚨 シート作成エラー: {e}")
            return None

# ユーザーごとに完全独立したシートを自動生成・使用する
WS_EXCLUDE = f"除外コード_{user_id}"
WS_FRONTLINE = f"交戦モニター_{user_id}"
WS_AAR = f"交戦DB_{user_id}"

# --- 1. サイドバー：除外銘柄コードの自動復旧 ---
def load_exclude_codes():
    ws = get_or_create_worksheet(WS_EXCLUDE)
    if ws:
        try:
            val = ws.col_values(1)
            return val[0] if val else ""
        except: pass
    return ""

def save_exclude_codes_to_file():
    ws = get_or_create_worksheet(WS_EXCLUDE)
    if ws:
        current_val = str(st.session_state.get("gigi_input", "")).strip()
        try:
            try: ws.update(values=[[current_val]], range_name="A1")
            except TypeError: ws.update("A1", [[current_val]])
        except Exception as e:
            st.sidebar.error(f"🚨 [除外コード] 書込エラー: {e}")

# --- 2. データベース汎用保存・読込関数 ---
def save_frontline_db(df):
    ws = get_or_create_worksheet(WS_FRONTLINE)
    if ws:
        ws.clear()
        # カラムが空の場合はデフォルトヘッダーを用意してエラーを防ぐ
        if df.empty and len(df.columns) == 0:
            data = [["銘柄", "株数", "買値", "現在値", "損切", "第1利確", "第2利確", "atr"]]
        else:
            data = [list(df.columns)] + df.fillna("").astype(str).values.tolist()
        
        try:
            try: ws.update(values=data, range_name="A1")
            except TypeError: ws.update("A1", data)
            st.sidebar.success("✅ [交戦モニター] Google DBへ書き込み完了")
        except Exception as e:
            st.sidebar.error(f"🚨 [交戦モニター] 書込エラー: {e}")

def save_aar_db(df):
    ws = get_or_create_worksheet(WS_AAR)
    if ws:
        ws.clear()
        if df.empty and len(df.columns) == 0:
            data = [["決済日", "銘柄", "規模", "戦術", "買値", "売値", "株数", "損益額(円)", "損益(%)", "規律", "敗因/勝因メモ"]]
        else:
            data = [list(df.columns)] + df.fillna("").astype(str).values.tolist()
            
        try:
            try: ws.update(values=data, range_name="A1")
            except TypeError: ws.update("A1", data)
            st.sidebar.success("✅ [戦績DB] Google DBへ書き込み完了")
        except Exception as e:
            st.sidebar.error(f"🚨 [戦績DB] 書込エラー: {e}")

def load_db_to_df(sheet_name, default_cols):
    ws = get_or_create_worksheet(sheet_name)
    if ws:
        try:
            data = ws.get_all_records()
            if data: return pd.DataFrame(data)
        except: pass
    return pd.DataFrame(columns=default_cols)

# --- 3. 強制同期フック ---
def extended_save_settings():
    save_exclude_codes_to_file()
    try:
        if "frontline_df" in st.session_state: 
            save_frontline_db(st.session_state.frontline_df)
        if "aar_df_stable" in st.session_state: 
            save_aar_db(st.session_state.aar_df_stable)
    except Exception as e:
        st.sidebar.error(f"🚨 [同期フック] エラー: {e}")
        
    try:
        if 'save_settings' in globals(): save_settings()
    except Exception: pass

# =========================================================
# 🚨 ここが欠損しているか、場所がずれている可能性が高いです！
# 必ずセッション構築の「上」に以下の2行を配置してください。
# =========================================================
API_KEY = st.secrets.get("JQUANTS_API_KEY", "").strip()
BASE_URL = "https://api.jquants.com/v2"

# 🚨 通信セッションの永続化とリトライバッファの構築
if "api_session" not in st.session_state:
    session = requests.Session()
    session.headers.update({"x-api-key": API_KEY})  # ← ここでエラーが起きていました
    
    # 🚨 修正：429（レート制限）を自動リトライから外し、カスタム冷却ループに制御を完全委譲
    retry_strategy = Retry(
        total=3,
        backoff_factor=0.5,
        status_forcelist=[500, 502, 503, 504]
    )
    adapter = HTTPAdapter(pool_connections=20, pool_maxsize=20, max_retries=retry_strategy)
    session.mount("https://", adapter)
    st.session_state.api_session = session

api_session = st.session_state.api_session

if "login_time" not in st.session_state:
    st.session_state.login_time = time.time()

st.write(f"⏱ 経過時間: {time.time() - st.session_state.login_time:.2f}秒")

def compress_memory(df):
    """データフレームのメモリサイズを強制的に半減させる極限圧縮処理"""
    if df is None or df.empty:
        return df
        
    # 浮動小数点の圧縮 (float64 -> float32)
    float_cols = df.select_dtypes(include=['float64']).columns
    df[float_cols] = df[float_cols].astype('float32')
    
    # 整数の圧縮 (int64 -> int32)
    int_cols = df.select_dtypes(include=['int64']).columns
    df[int_cols] = df[int_cols].astype('int32')
    
    # 🚨 開発参謀パッチ：システムの中核列（日付やコード）はカテゴリ圧縮から除外する
    exclude_cols = ['Date', 'Code', 'Date_Str', 'Date_x', 'Date_y'] 
    
    # オブジェクト型（文字列等）で種類が少ないものをカテゴリ化
    for col in df.select_dtypes(include=['object']).columns:
        if col not in exclude_cols: # 🚨 除外リストにない列だけを圧縮対象とする
            if df[col].nunique() / len(df) < 0.5:
                df[col] = df[col].astype('category')
            
    return df

# ==========================================
# ⚙️ 設定の永続化（完全統合・決定版・物理結線済）
# ==========================================
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
        "gigi_input": "2134, 3350, 6172, 6740, 7647, 8783, 8836, 8925, 9318",
        "f_vol_min_slider": 0.5,
        "f_max_stocks_slider": 30
    }
    
    saved_data = {}
    if os.path.exists(SETTINGS_FILE):
        try:
            with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
                saved_data = json.load(f)
        except: 
            pass

    for k, v in defaults.items():
        target_val = saved_data.get(k, v)
        if k not in st.session_state:
            st.session_state[k] = target_val

def save_settings():
    keys_to_save = [
        "preset_market", "preset_push_r", "sidebar_tactics", "push_r", "limit_d", "bt_lot", "bt_tp", "bt_sl_i", "bt_sl_c", "bt_sell_d", 
        "f1_min", "f1_max", "f2_m30", "f3_drop", "f5_ipo", "f6_risk", "f7_ex_etf", "f8_ex_bio", 
        "f9_min14", "f9_max14", "f10_ex_knife", "f11_ex_wave3", "f12_ex_overvalued",
        "tab2_rsi_limit", "tab2_vol_limit", "t3_scope_mode", "gigi_input",
        "f_vol_min_slider", "f_max_stocks_slider"
    ]
    
    current_settings = {k: st.session_state[k] for k in keys_to_save if k in st.session_state}
    try:
        with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
            json.dump(current_settings, f, ensure_ascii=False, indent=4)
    except: 
        pass

def apply_presets():
    if "preset_push_r" in st.session_state:
        try:
            val_str = st.session_state["preset_push_r"]
            st.session_state["push_r"] = float(val_str.replace("%", "").strip())
        except:
            pass
    save_settings()

load_settings()

# --- 🌪️ 1. マクロ気象レーダー（J-Quantsハイブリッド・早朝ロールバック完全防衛版） ---
@st.cache_data(ttl=600, show_spinner=False)  # 🚨 参謀追記：APIの過剰なリクエストを防ぐためキャッシュを推奨します
def get_macro_weather():
    try:
        import yfinance as yf
        tk = yf.Ticker("^N225")
        df_raw = tk.history(period="3mo")
        if not df_raw.empty:
            if df_raw.index.tz is not None:
                df_raw.index = df_raw.index.tz_localize(None)
            
            df_ni = df_raw.reset_index()
            df_ni.rename(columns={df_ni.columns[0]: 'Date'}, inplace=True)
            
            # 🚨 修正：動的カラム取得で「Close」依存を破壊
            close_col = next((c for c in ['Close', 'close', 'C', 'c'] if c in df_ni.columns), 'Close')
            df_ni = df_ni.dropna(subset=[close_col])
            
            if len(df_ni) >= 2:
                tz_jst = pytz.timezone('Asia/Tokyo')
                now_jst = datetime.now(tz_jst)
                today_date = now_jst.date()
                yf_latest_date = df_ni['Date'].dt.date.max()
                
                if (now_jst.hour < 9 or (now_jst.hour == 9 and now_jst.minute < 30)) and (today_date - yf_latest_date).days >= 2:
                    f_d = (now_jst - timedelta(days=7)).strftime('%Y%m%d')
                    t_d = now_jst.strftime('%Y%m%d')
                    
                    url = f"{BASE_URL}/equities/bars/daily?code=13060&from={f_d}&to={t_d}" 
                    try:
                        r = api_session.get(url, timeout=3.0)
                        if r.status_code == 200:
                            data = r.json().get("daily_quotes") or r.json().get("data") or []
                            if data:
                                jq_latest = sorted(data, key=lambda x: x['Date'])[-1]
                                jq_date_str = jq_latest.get("Date")
                                jq_date = datetime.strptime(jq_date_str, "%Y-%m-%d").date() if "-" in jq_date_str else datetime.strptime(jq_date_str, "%Y%m%d").date()
                                
                                if jq_date > yf_latest_date:
                                    # 🚨 修正：API側データの値取得も安全に
                                    val = jq_latest.get("Close") or jq_latest.get("C") or jq_latest.get("AdjC") or jq_latest.get("c")
                                    # 🚨 J-Quants特有の「空文字("")」が紛れ込んだ際の ValueError を物理的に防ぐ
                                    if val is not None and str(val).strip() != "":
                                        new_row = df_ni.iloc[-1].copy()
                                        new_row['Date'] = pd.to_datetime(jq_date)
                                        
                                        if "1001" in url or float(val) > 30000:
                                            new_row[close_col] = float(val)
                                        else:
                                            jq_prev = sorted(data, key=lambda x: x['Date'])[-2]
                                            jq_prev_val = jq_prev.get("Close") or jq_prev.get("C") or jq_prev.get("AdjC") or jq_prev.get("c")
                                            pct_change = (float(val) / float(jq_prev_val))
                                            new_row[close_col] = df_ni.iloc[-1][close_col] * pct_change
                                        
                                        df_ni = pd.concat([df_ni, pd.DataFrame([new_row])], ignore_index=True)
                    except:
                        pass

                latest, prev = df_ni.iloc[-1], df_ni.iloc[-2]
                return {
                    "nikkei": {
                        "price": float(latest[close_col]),
                        "diff": float(latest[close_col] - prev[close_col]),
                        "pct": ((float(latest[close_col]) / float(prev[close_col])) - 1) * 100,
                        "df": df_ni,
                        "date": latest['Date'].strftime('%m/%d')
                    }
                }
    except:
        pass
    return None

def fetch_current_prices_fast(codes):
    results = {}
    tz_jst = pytz.timezone('Asia/Tokyo')
    base = datetime.now(tz_jst)
    f_d, t_d = (base - timedelta(days=7)).strftime('%Y%m%d'), base.strftime('%Y%m%d')
    def fetch_single(code):
        clean_code = str(code).replace('.0', '').strip()
        
        # 🌟 追加：yfinanceで日中の最新価格を取得
        try:
            import yfinance as yf
            tk = yf.Ticker(f"{clean_code}.T")
            df_today = tk.history(period="1d")
            if not df_today.empty:
                current_price = df_today['Close'].iloc[-1]
                if pd.notna(current_price):
                    return code, float(current_price)
        except:
            pass

        # 既存：取得できなかった場合のJ-Quants（5桁・大引け後用）
        api_code = clean_code if len(clean_code) >= 5 else clean_code + "0"
        url = f"{BASE_URL}/equities/bars/daily?code={api_code}&from={f_d}&to={t_d}"
        try:
            r = api_session.get(url, timeout=3.0)
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
weather = get_macro_weather()
nikkei_pct_api = weather['nikkei']['pct'] if weather and 'nikkei' in weather else 0.0

def render_macro_board():
    data = get_macro_weather()
    if data and "nikkei" in data:
        ni = data["nikkei"]
        df = ni["df"].copy()
        
        # 🚨 防弾処理: インデックスに隠れた日付（Date）を取り出し、クラッシュ原因のTZを消去
        if 'Date' not in df.columns:
            df = df.reset_index()
            if 'index' in df.columns and 'Date' not in df.columns:
                df.rename(columns={'index': 'Date'}, inplace=True)
        if pd.api.types.is_datetime64_any_dtype(df['Date']):
            df['Date'] = df['Date'].dt.tz_localize(None)

        close_col = next((c for c in ['AdjC', 'Close', 'close', 'Adj Close', 'C'] if c in df.columns), None)
        if not close_col:
            return

        # 🚨 スナイパー仕様：18日線と50日線を計算
        df['MA18'] = df[close_col].rolling(window=18).mean()
        df['MA50'] = df[close_col].rolling(window=50).mean()
        
        color = "#26a69a" if ni['diff'] >= 0 else "#ef5350" 
        sign = "+" if ni['diff'] >= 0 else ""
        
        c1, c2 = st.columns([1, 4]) 
        
        with c1:
            st.markdown(f"""
                <div style="background: rgba(20, 20, 20, 0.6); padding: 1.2rem; border-radius: 8px; border-left: 4px solid {color}; height: 100%; display: flex; flex-direction: column; justify-content: center;">
                    <div style="font-size: 14px; color: #aaa; margin-bottom: 8px;">🌪️ 戦場の天候 (日経: {ni.get("date", "")})</div>
                    <div style="font-size: 26px; font-weight: bold; color: {color}; margin-bottom: 4px;">{ni.get("price", 0):,.0f} 円</div>
                    <div style="font-size: 16px; color: {color};">({sign}{ni.get("diff", 0):,.0f} / {sign}{ni.get("pct", 0):.2f}%)</div>
                </div>
            """, unsafe_allow_html=True)
            
        with c2:
            import plotly.graph_objects as go
            fig = go.Figure()
            
            # 日経平均（現在値）の線
            fig.add_trace(go.Scatter(
                x=df['Date'], y=df[close_col], name='日経平均', mode='lines', 
                line=dict(color='#FFD700', width=2), hovertemplate='日経平均: ¥%{y:,.0f}<extra></extra>'
            ))
            
            # 🚨 18日線（短期トレンド）の追加
            fig.add_trace(go.Scatter(
                x=df['Date'], y=df['MA18'], name='18日線', mode='lines', 
                line=dict(color='#26a69a', width=1.5, dash='dot'), hovertemplate='18日線: ¥%{y:,.0f}<extra></extra>'
            ))
            
            # 🚨 50日線（中期トレンド）の追加
            fig.add_trace(go.Scatter(
                x=df['Date'], y=df['MA50'], name='50日線', mode='lines', 
                line=dict(color='#ff9800', width=1.5, dash='dash'), hovertemplate='50日線: ¥%{y:,.0f}<extra></extra>'
            ))
            
            y_min, y_max = df[close_col].min(), df[close_col].max()
            fig.update_layout(
                height=220, margin=dict(l=0, r=40, t=15, b=10), xaxis_rangeslider_visible=False, 
                paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)', showlegend=False, hovermode="x unified", 
                yaxis=dict(side="right", tickformat=",.0f", gridcolor='rgba(255,255,255,0.05)', autorange=True, range=[y_min * 0.98, y_max * 1.05], fixedrange=True), 
                xaxis=dict(type='date', tickformat='%m/%d', gridcolor='rgba(255,255,255,0.05)', range=[df['Date'].min(), df['Date'].max() + pd.Timedelta(hours=24)], fixedrange=True)
            )
            st.plotly_chart(fig, use_container_width=True, config={'displayModeBar': False, 'staticPlot': False})
            
        st.markdown("<div style='margin-bottom: 1.5rem;'></div>", unsafe_allow_html=True)

# --- 3. 共通関数 & 演算エンジン ---
def execute_chunked_scan(codes_or_groups, process_func, *args, max_workers=3, chunk_size=200):
    """
    OOM（メモリ枯渇）を回避するためのマイクロバッチ実行エンジン。
    引数のリストをchunk_sizeごとに分割し、1チャンク終わるごとに強制GCを発動する。
    """
    all_results = []
    
    # codes_or_groups は [code1, code2...] または [(code, group), ...] のリストを想定
    for i in range(0, len(codes_or_groups), chunk_size):
        chunk = codes_or_groups[i:i + chunk_size]
        
        with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
            if isinstance(chunk[0], tuple): # (code, group) の場合 (TAB2, TAB3など)
                futs = [executor.submit(process_func, c, g, *args) for c, g in chunk]
            else: # code 単体の場合
                futs = [executor.submit(process_func, c, *args) for c in chunk]
                
            for f in concurrent.futures.as_completed(futs):
                try:
                    res = f.result()
                    if res:
                        if isinstance(res, list):
                            all_results.extend(res)
                        else:
                            all_results.append(res)
                except Exception:
                    pass
                    
        # 🚨 チャンクごとに役目を終えた一時メモリを強制焼却（ガベージコレクション）
        gc.collect()
        
    return all_results
    
def clean_df(df):
    if df is None or df.empty: 
        return pd.DataFrame()
    
    # 🚨 補修：小文字の 'code' を強制的に大文字の 'Code' に統一
    if 'code' in df.columns and 'Code' not in df.columns:
        df = df.rename(columns={'code': 'Code'})

    # 🚨 出来高の欠損を防ぐ柔軟な抽出
    vol_candidates = ['AdjustmentVolume', 'Volume', 'volume', 'Vol', 'Vo']
    for c in vol_candidates:
        if c in df.columns and c != 'AdjustmentVolume':
            df = df.rename(columns={c: 'AdjustmentVolume'})
            break

    # 🚨 重複リネームによる2次元化(DataFrame化)を完全に防ぐ
    if 'AdjustmentClose' in df.columns:
        p_map = {
            'AdjustmentOpen': 'AdjO', 'AdjustmentHigh': 'AdjH', 
            'AdjustmentLow': 'AdjL', 'AdjustmentClose': 'AdjC'
        }
    else:
        p_map = {
            'Open': 'AdjO', 'High': 'AdjH', 'Low': 'AdjL', 'Close': 'AdjC',
            'O': 'AdjO', 'H': 'AdjH', 'L': 'AdjL', 'C': 'AdjC'
        }
        
    df = df.rename(columns=p_map)

    # 🛡️ 万が一重複列が発生していても「最初の1列」だけを残す
    df = df.loc[:, ~df.columns.duplicated(keep='first')]

    keep = ['Code', 'Date', 'AdjO', 'AdjH', 'AdjL', 'AdjC', 'AdjustmentVolume']
    df = df[[c for c in keep if c in df.columns]].copy()
    
    if 'Date' in df.columns:
        df['Date'] = pd.to_datetime(df['Date'])
        
    for col in ['AdjO', 'AdjH', 'AdjL', 'AdjC', 'AdjustmentVolume']:
        if col in df.columns:
            # 1次元データ(Series)としてfloat32キャスト
            df[col] = pd.to_numeric(df[col], errors='coerce').astype('float32')
            
    if 'Code' in df.columns:
        df['Code'] = df['Code'].astype('category')
        
    # 🚨 最終防壁：データ内に 'Code' 列が存在しない場合でもエラーで落ちないように動的ソート
    sort_keys = [k for k in ['Code', 'Date'] if k in df.columns]
    
    return df.dropna(subset=['AdjC']).sort_values(sort_keys).reset_index(drop=True)

# --- 3. 共通関数 & 演算エンジン ---
def calc_vector_indicators(df):
    """完全ベクトル化されたテクニカル指標計算（14日Wilder式・実数ATR完全換装版）"""
    if df is None or df.empty or len(df) < 2:
        return df

    # 動的な列名取得（すれ違い防止回路）
    close_col = 'AdjC' if 'AdjC' in df.columns else 'Close'
    high_col = 'AdjH' if 'AdjH' in df.columns else 'High'
    low_col = 'AdjL' if 'AdjL' in df.columns else 'Low'
    
    if close_col not in df.columns:
        return df

    # 1. 移動平均線 (float32で計算結果を保持)
    df['SMA25'] = df[close_col].rolling(window=25, min_periods=1).mean().astype('float32')
    df['SMA75'] = df[close_col].rolling(window=75, min_periods=1).mean().astype('float32')

    # ====================================================================
    # 🎯 2. 【完全浄化】14日Wilder式 実数ATR計算（ハイブリッド安全装置）
    # ====================================================================
    if high_col in df.columns and low_col in df.columns:
        c_prev = df[close_col].shift(1)
        tr1 = df[high_col] - df[low_col]
        tr2 = (df[high_col] - c_prev).abs()
        tr3 = (df[low_col] - c_prev).abs()
        
        # True Rangeの算出
        tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
        
        # 🛡️ Wilder式ATR（RMA: 修正移動平均 = alpha 1/14 の指数平滑）
        if len(df) >= 14:
            df['ATR_Standard'] = tr.ewm(alpha=1/14, adjust=False, min_periods=1).mean().astype('float32')
        else:
            # 14日未満の場合は単純平均で代用
            df['ATR_Standard'] = tr.rolling(window=len(df), min_periods=1).mean().astype('float32')
        
        del c_prev, tr1, tr2, tr3, tr
    else:
        # 究極のフェイルセーフ（High/Lowが存在しない等の異常時のみ）
        df['ATR_Standard'] = (df[close_col] * 0.05).astype('float32')
        
    # 互換性のため、小文字の 'atr' 列にも同じ実数値をセット
    df['atr'] = df['ATR_Standard']
    df['ATR'] = df['ATR_Standard']
    # ====================================================================

    # 3. RSIの完全ベクトル化計算
    delta = df[close_col].diff()
    gain = delta.where(delta > 0, 0.0).rolling(window=14, min_periods=1).mean()
    loss = (-delta.where(delta < 0, 0.0)).rolling(window=14, min_periods=1).mean()
    
    # ゼロ除算回避とRSI算出
    rs = gain / loss.replace(0, 1e-10) 
    df['RSI'] = (100 - (100 / (1 + rs))).astype('float32')

    del delta, gain, loss, rs
    return df

def check_event_mines(code, event_data=None):
    alerts = []
    c = str(code)[:4]
    tz_jst = pytz.timezone('Asia/Tokyo')
    today = datetime.now(tz_jst).date()
    
    if not event_data or not isinstance(event_data, dict):
        return []

    div_list = event_data.get("dividend", [])
    for d in div_list:
        if str(d.get("Code", ""))[:4] != c: continue
        d_str_raw = d.get("Date") or d.get("DisclosedDate")
        if not d_str_raw: continue
        
        try:
            target_date = None
            d_val = str(d_str_raw).strip()
            
            if d_val.isdigit() and len(d_val) >= 10:
                target_date = datetime.fromtimestamp(int(d_val), tz_jst).date()
            else:
                clean_d = d_val.replace("-", "").replace("/", "")[:8]
                target_date = datetime.strptime(clean_d, "%Y%m%d").date()
            
            if target_date:
                diff = (target_date - today).days
                if 0 <= diff <= 14:
                    day_label = "本日！" if diff == 0 else f"残り {diff} 日"
                    alerts.append(f"💰 【配当】{day_label} ({target_date.strftime('%m/%d')})")
                    break
        except: continue

    earnings_list = event_data.get("earnings", [])
    for item in earnings_list:
        if str(item.get("Code", ""))[:4] != c: continue
        d_str_raw = item.get("Date") or item.get("DisclosedDate")
        if not d_str_raw: continue
        
        try:
            target_date = None
            d_val = str(d_str_raw).strip()
            
            if d_val.isdigit() and len(d_val) >= 10:
                target_date = datetime.fromtimestamp(int(d_val), tz_jst).date()
            else:
                clean_d = d_val.replace("-", "").replace("/", "")[:8]
                target_date = datetime.strptime(clean_d, "%Y%m%d").date()
            
            if target_date:
                diff = (target_date - today).days
                if 0 <= diff <= 14:
                    day_label = "本日！" if diff == 0 else f"残り {diff} 日"
                    alerts.append(f"🔥 【決算】{day_label} ({target_date.strftime('%m/%d')})")
                    break
        except: continue
            
    return alerts

def detect_sakata_patterns(df):
    """
    酒田五法のフォーメーションを検知する防弾仕様の精密レーダー。
    データ構造の不整合を自動修復し、いかなる場合もクラッシュを許さない。
    """
    if df is None or len(df) < 5: 
        return []
        
    # 必須カラムチェック（データ欠損によるクラッシュを物理的に封殺）
    required = ['AdjO', 'AdjH', 'AdjL', 'AdjC', 'Date']
    if not all(col in df.columns for col in required):
        return []

    patterns = []
    
    # メモリ効率化のため、列のコピーとnumpy配列への展開
    df_work = df.copy()
    c = df_work['AdjC'].values
    o = df_work['AdjO'].values
    h = df_work['AdjH'].values
    l = df_work['AdjL'].values
    d = df_work['Date'].values
    
    # RSIの安全取得（存在しない場合は中立の50として扱う）
    rsi = df_work['RSI'].values if 'RSI' in df_work.columns else np.full(len(df), 50.0)
    
    # スイング判定用の期間高値安値計算
    h14_max = df_work['AdjH'].tail(15).iloc[:-1].max()
    l14_min = df_work['AdjL'].tail(15).iloc[:-1].min()
    rng = h14_max - l14_min
    
    pos = (c[-1] - l14_min) / rng if rng > 0 else 0.5
    
    is_high_zone = pos > 0.7 or rsi[-1] > 65
    is_low_zone = pos < 0.3 or rsi[-1] < 35

    # 頂点検知ロジック（効率化のためtail(30)のAdjHを参照）
    tail_30 = df_work.tail(30)
    h30 = tail_30['AdjH'].values
    peaks = []
    for i in range(1, len(h30)-1):
        if h30[i] > h30[i-1] and h30[i] > h30[i+1]:
            peaks.append({"val": h30[i], "idx": i})
    
    # --- パターン検知ロジック (論理構造は維持) ---
    if len(peaks) >= 3 and is_high_zone:
        if peaks[-2]['val'] > peaks[-3]['val'] and peaks[-2]['val'] > peaks[-1]['val']:
            patterns.append({"date": d[-1], "label": "【酒田・三尊】", "text": "🔴 【酒田・三尊】天井圏での最終警戒形態。三つの仏、崩落の予兆。即時撤退。", "color": "#ef5350", "type": "bear"})
        else:
            patterns.append({"date": d[-1], "label": "【酒田・三山】", "text": "🔴 【酒田・三山】高値圏での三連ピーク。買い勢力の限界露呈。利確の急所。", "color": "#ef5350", "type": "bear"})

    if check_double_top(df.tail(31)) and is_high_zone:
        if not any(p['label'] == "【酒田・三尊】" for p in patterns):
            patterns.append({"date": d[-1], "label": "【酒田・二重天井】", "text": "🔴 【酒田・二重天井】天井圏での双峰。上昇エネルギーの枯渇。崩落へのカウントダウン。", "color": "#ef5350", "type": "bear"})

    # 赤三兵/黒三兵・三空の判定（インデックスアクセスを整理）
    if is_high_zone:
        if all(c[i] > o[i] for i in range(-3, 0)) and all(c[i] > c[i-1] for i in range(-2, 0)):
            patterns.append({"date": d[-1], "label": "【酒田・赤三先】", "text": "🔴 【酒田・赤三先】高値圏での三連陽。買い枯れの兆候。新規買いは罠。", "color": "#ef5350", "type": "bear"})
        if all(c[i] < o[i] for i in range(-3, 0)) and all(c[i] < c[i-1] for i in range(-2, 0)):
            patterns.append({"date": d[-1], "label": "【酒田・黒三兵】", "text": "🔴 【酒田・黒三兵】高値圏での崩壊合図。暴落の狼煙。即時撤退。", "color": "#ef5350", "type": "bear"})
        
        # 厳格検知：3回連続で「当日の高値」が「前日の安値」を下回る（完全な下落窓）
        if all(h[i] < l[i-1] for i in range(-3, 0)):
            patterns.append({"date": d[-1], "label": "【酒田・売三空】", "text": "🟢 【酒田・売り三空】三度の窓。売り枯れの極み。反転狙撃好機。", "color": "#26a69a", "type": "bull"})

    if is_low_zone:
        if check_oversold_ultimate(df):
            patterns.append({"date": d[-1], "label": "【酒田・陰の極み】", "text": "🟢 【酒田・陰の極み】底打ち最終波形。売り枯れの果て。反転攻勢の急所。狙撃準備。", "color": "#26a69a", "type": "bull"})
        if all(c[i] > o[i] for i in range(-3, 0)) and all(c[i] > c[i-1] for i in range(-2, 0)):
            patterns.append({"date": d[-1], "label": "【酒田・赤三兵】", "text": "🟢 【酒田・赤三兵】安値圏からの狼煙。底打ち反転。追撃準備。", "color": "#26a69a", "type": "bull"})
            
        # 厳格検知：3回連続で「当日の安値」が「前日の高値」を上回る（完全な上昇窓）
        if all(l[i] > h[i-1] for i in range(-3, 0)):
            patterns.append({"date": d[-1], "label": "【酒田・買三空】", "text": "🔴 【酒田・買い三空】最終噴出。過熱の極致。利確の急所。", "color": "#ef5350", "type": "bear"})

    if check_double_bottom(df.tail(31)) and is_low_zone:
        patterns.append({"date": d[-1], "label": "【酒田・二重底】", "text": "🟢 【酒田・二重底】底堅い反転波形を確認。底打ちの最終局面。狙撃準備。", "color": "#26a69a", "type": "bull"})
    
    # たくり線（下ヒゲ）の検知
    body_v = abs(c[-1] - o[-1])
    shadow_l = min(c[-1], o[-1]) - l[-1]
    full_rng = h[-1] - l[-1]
    if full_rng > 0 and shadow_l > (body_v * 2.5) and (shadow_l / full_rng) > 0.6 and is_low_zone:
        patterns.append({"date": d[-1], "label": "【酒田・たくり】", "text": "🟢 【酒田・たくり線】大底圏での強烈な反発。絶好の買場。攻勢の起点。", "color": "#26a69a", "type": "bull"})

    return patterns

def render_technical_radar(df, target_p, tp_target):
    try:
        if df is None or len(df) < 5:
            return '<div style="color:#ef5350; font-size:12px;">⚠️ レーダー解析不能：データ不足</div>'
        
        latest = df.iloc[-1]
        prev = df.iloc[-2]
        rsi_val = float(latest.get('RSI', 50))
        m1 = float(latest.get('MACD_Hist', 0))
        m2 = float(prev.get('MACD_Hist', 0))
        
        score_mom = 50 + (m1 * 10)
        if m1 > m2: score_mom += 20
        score_mom = max(0, min(100, score_mom))
        
        c = float(latest['AdjC'])
        ma25 = float(latest.get('MA25', c))
        score_trend = max(0, min(100, 50 + (((c / ma25) - 1) * 500)))
        
        atr = float(latest.get('ATR', c * 0.03))
        score_vol = max(0, min(100, (atr / c) * 2000))
        
        h14 = float(df.tail(14)['AdjH'].max())
        l14 = float(df.tail(14)['AdjL'].min())
        score_pos = max(0, min(100, ((c - l14) / (h14 - l14) * 100))) if (h14 - l14) > 0 else 50
        
        total_score = (rsi_val + score_mom + score_trend + score_vol + score_pos) / 5.0

        import math
        angles = [math.radians(a) for a in [0, 72, 144, 216, 288]]
        scores = [rsi_val, score_mom, score_trend, score_vol, score_pos]
        
        pts = []
        for angle, score in zip(angles, scores):
            r_val = (score / 100.0) * 65 
            px = 100 + r_val * math.sin(angle)
            py = 100 - r_val * math.cos(angle)
            pts.append(str(round(px, 1)) + "," + str(round(py, 1)))
        polygon_pts = " ".join(pts)

        axis_lines = ""
        for a in angles:
            ax2 = 100 + 65 * math.sin(a)
            ay2 = 100 - 65 * math.cos(a)
            axis_lines += '<line x1="100" y1="100" x2="' + str(ax2) + '" y2="' + str(ay2) + '" stroke="#444" stroke-width="0.5"/>'

        h = '<div style="background:rgba(255,255,255,0.02); border-radius:10px; padding:10px; border:1px solid rgba(255,255,255,0.05); margin-bottom:10px;">'
        h += '<div style="display:flex; align-items:center; justify-content:space-between;">'
        h += '<div style="flex:1; text-align:center;">'
        h += '<svg width="180" height="180" viewBox="0 0 200 200">'
        h += '<circle cx="100" cy="100" r="65" fill="none" stroke="#444" stroke-width="0.5" stroke-dasharray="2,2" />'
        h += '<circle cx="100" cy="100" r="32.5" fill="none" stroke="#444" stroke-width="0.5" stroke-dasharray="2,2" />'
        h += axis_lines
        h += '<polygon points="' + polygon_pts + '" fill="rgba(38,166,154,0.4)" stroke="#26a69a" stroke-width="2" />'
        
        h += '<text x="100" y="22" text-anchor="middle" fill="#aaa" font-size="11" font-weight="bold">勢力</text>'
        h += '<text x="175" y="85" text-anchor="start" fill="#aaa" font-size="11" font-weight="bold">加速</text>'
        h += '<text x="145" y="182" text-anchor="middle" fill="#aaa" font-size="11" font-weight="bold">傾向</text>'
        h += '<text x="55" y="182" text-anchor="middle" fill="#aaa" font-size="11" font-weight="bold">波高</text>'
        h += '<text x="25" y="85" text-anchor="end" fill="#aaa" font-size="11" font-weight="bold">位置</text></svg></div>'
        
        h += '<div style="flex:1.2; padding-left:20px;">'
        h += '<div style="font-size:13px; color:#888; margin-bottom:5px;">📊 索敵テクニカル総合スコア</div>'
        h += '<div style="font-size:2.8rem; font-weight:bold; color:#26a69a;">' + "{:.1f}".format(total_score) + '<span style="font-size:1rem; margin-left:5px;">pts</span></div>'
        h += '<div style="margin-top:10px; border-top:1px solid #333; padding-top:5px;">'
        h += '<div style="display:flex; justify-content:space-between; font-size:11px;">'
        h += '<span style="color:#666;">勢力(RSI): ' + "{:.1f}".format(rsi_val) + '</span>'
        h += '<span style="color:#666;">位置: ' + "{:.1f}".format(score_pos) + '%</span>'
        h += '</div></div></div></div></div>'
        
        return h
    except Exception as e:
        err_msg = "⚠️ レーダー演算エラー: " + str(e)
        return '<div style="color:#ef5350; font-size:12px;">' + err_msg + '</div>'

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
    res = None
    
    # 後半の計算で確実に参照するため、スコープのトップで変数を初期化
    eps = None
    bps = None
    shares = None
    
    # 🛡️ 内部防衛関数：空文字("")やNoneを安全に弾く
    def safe_float(val):
        try:
            return float(val) if val not in [None, ""] else None
        except (ValueError, TypeError):
            return None

    try:
        r = api_session.get(url, timeout=3.0)
        if r.status_code == 200:
            data = r.json().get("statements", [])
            if data:
                # 💡 J-Quants APIは昇順データのため、末尾[-1]が最新の決算データとなります
                latest = data[-1]
                
                # 🚨 V2とV1のフィールド名（キー名）の揺れを両方とも吸収
                op = latest.get("OPnumber", latest.get("OperatingProfit"))
                np_val = latest.get("NPnumber", latest.get("NetIncome"))
                eq = latest.get("Eqnumber", latest.get("Equity"))
                eq_ratio = latest.get("EqARnumber", latest.get("EquityRatio"))
                eps = latest.get("EPSnumber", latest.get("EarningsPerShare"))
                bps = latest.get("BPSnumber", latest.get("BookValuePerShare"))
                shares = latest.get("ShOutFYnumber", latest.get("NumberOfIssuedAndOutstandingSharesAtTheEndOfPeriod"))
                
                # ベースとなる辞書を生成（ここでの "roe": None は正しい型枠です）
                res = {
                    "op": op,
                    "er": eq_ratio,
                    "shares": shares,
                    "roe": None,
                    "per": latest.get("PER"),
                    "pbr": latest.get("PBR"),
                    "cap": latest.get("MarketCapitalization")
                }
                
                # 爆発しないように安全な数値に変換
                f_np = safe_float(np_val)
                f_eq = safe_float(eq)
                f_eps = safe_float(eps)
                f_bps = safe_float(bps)
                
                # ROEの計算 (当期純利益 ÷ 自己資本)
                if f_np is not None and f_eq is not None and f_eq != 0:
                    res["roe"] = (f_np / f_eq) * 100
                elif f_eps is not None and f_bps is not None and f_bps != 0:
                    res["roe"] = (f_eps / f_bps) * 100
    except:
        pass

    # 🚨 通信エラー等でベースが作れなかった場合でもフォールバックの枠を死守
    if res is None:
        res = {"op": None, "er": None, "shares": None, "roe": None, "per": None, "pbr": None, "cap": None}

    # 🚨 yfinance（Yahooファイナンス）に突入し、時価総額・ROE等をリアルタイム計算・補完
    try:
        import yfinance as yf
        tk = yf.Ticker(f"{code}.T")
        info = tk.info
        
        # yfinanceから直接取れる場合はそれを最優先で上書き
        if info.get("trailingPE") or info.get("forwardPE"):
            res["per"] = info.get("trailingPE", info.get("forwardPE"))
        if info.get("priceToBook"):
            res["pbr"] = info.get("priceToBook")
        if info.get("marketCap"):
            res["cap"] = info.get("marketCap")
            
        # 🎯 【追加】yfinanceの強力なROE補完ロジック（小数をパーセンテージに変換）
        if info.get("returnOnEquity"):
            res["roe"] = info.get("returnOnEquity") * 100
        
        cur_price = info.get("currentPrice", info.get("regularMarketPrice", info.get("previousClose")))
        
        # 直接データが引けなかった場合は、J-Quantsの財務情報と株価から自力で掛け算を行う
        if cur_price:
            f_eps = safe_float(eps)
            f_bps = safe_float(bps)
            f_shares = safe_float(shares)
            
            if res.get("per") is None and f_eps and f_eps > 0:
                res["per"] = float(cur_price) / f_eps
            if res.get("pbr") is None and f_bps and f_bps > 0:
                res["pbr"] = float(cur_price) / f_bps
            if res.get("cap") is None and f_shares and f_shares > 0:
                res["cap"] = float(cur_price) * f_shares
    except:
        pass # 通信障害時も前段のJ-Quantsデータを死守して返す
        
    return res

# =========================================================
# 🛡️ 【共通関数】年間イベント（決算・権利落ち）の絶対検知ロジック
# =========================================================
def get_upcoming_event_alerts(code_str):
    alerts = []
    try:
        tz = pytz.timezone('Asia/Tokyo')
        today = datetime.now(tz).date()
        
        f_data = get_fundamentals(str(code_str)[:4])
        if not f_data:
            return alerts
            
        earnings_date_str = f_data.get("earnings_date") or f_data.get("next_div_date") 
        if earnings_date_str:
            e_date = datetime.strptime(str(earnings_date_str).strip()[:10], "%Y-%m-%d").date()
            days_to_earnings = (e_date - today).days
            if 0 <= days_to_earnings <= 14:
                alerts.append(f"📅 決算発表まであと {days_to_earnings} 日 ({e_date.strftime('%m/%d')})")
                
        ex_div_date_str = f_data.get("ex_dividend_date")
        if ex_div_date_str:
            d_date = datetime.strptime(str(ex_div_date_str).strip()[:10], "%Y-%m-%d").date()
            days_to_div = (d_date - today).days
            if 0 <= days_to_div <= 14:
                alerts.append(f"🍇 権利落ち（配当・優待）まであと {days_to_div} 日 ({d_date.strftime('%m/%d')})")
                
    except:
        pass 
        
    return alerts

@st.cache_data(ttl=86400)
def load_master():
    try:
        r1 = requests.get("https://www.jpx.co.jp/markets/statistics-equities/misc/01.html", headers={'User-Agent': 'Mozilla/5.0'}, timeout=10)
        m = re.search(r'href="([^"]+data_j\.xls)"', r1.text)
        if m:
            r2 = requests.get("https://www.jpx.co.jp" + m.group(1), headers={'User-Agent': 'Mozilla/5.0'}, timeout=15)
            df = pd.read_excel(BytesIO(r2.content), engine='xlrd')[['コード', '銘柄名', '33業種区分', '市場・商品区分']]
            df.columns = ['Code', 'CompanyName', 'Sector', 'Market']
            df['Code'] = df['Code'].astype(str).apply(lambda x: x if len(x) >= 5 else x + "0")
            return df
    except: pass
    return pd.DataFrame()

# ==========================================
# 📊 個別銘柄データ取得 (Lightプラン完全対応・防弾仕様)
# ==========================================
@st.cache_data(ttl=3600, show_spinner=False)
def get_single_data(code, yrs=1):
    import time
    import threading
    
    # ⚡ グローバル空間に交通整理用のロックを配備（未定義の場合）
    if 'jquants_api_lock' not in st.session_state:
        st.session_state.jquants_api_lock = threading.Lock()
        st.session_state.last_api_time = 0.0

    base = datetime.utcnow() + timedelta(hours=9)
    # 🚨 改修1：確実な営業日（兵站）を確保するため、365日ではなく「400日」を基準にする
    f_d = (base - timedelta(days=400*yrs)).strftime('%Y%m%d')
    t_d = base.strftime('%Y%m%d')
    result = {"bars": [], "events": {"dividend": [], "earnings": []}}
    
    try:
        # 🚨 改修2：過去の「.0混入バグ（ゾンビ）」を完全に粉砕し、安全に5桁化
        clean_code = str(code).replace('.0', '').strip()
        api_code = clean_code if len(clean_code) >= 5 else clean_code + "0"
        
        # --- 🛡️ 内部ヘルパー関数：Lightプラン専用の安全通信 ---
        def safe_fetch(url, t_out=5.0):
            for attempt in range(3):
                with st.session_state.jquants_api_lock:
                    now = time.time()
                    elapsed = now - st.session_state.last_api_time
                    if elapsed < 1.05: # 60回/分を厳守（1.05秒間隔）
                        time.sleep(1.05 - elapsed)
                    try:
                        r = api_session.get(url, timeout=t_out)
                        st.session_state.last_api_time = time.time()
                        if r.status_code == 200:
                            return r.json()
                        elif r.status_code == 429: # 制限に引っかかったらペナルティ待機
                            time.sleep(2.0)
                            continue
                    except Exception:
                        st.session_state.last_api_time = time.time()
                        pass
            return {}

        # 1. 株価データの取得
        url_bars = f"{BASE_URL}/equities/bars/daily?code={api_code}&from={f_d}&to={t_d}"
        bars_data = safe_fetch(url_bars, 10.0)
        result["bars"] = bars_data.get("daily_quotes") or bars_data.get("data") or []
        
        # 2. 決算発表予定日の取得
        url_earn = f"{BASE_URL}/fins/announcement?code={api_code}"
        earn_data = safe_fetch(url_earn, 5.0)
        result["events"]["earnings"] = earn_data.get("announcement", [])
        
        # 3. 配当情報の取得
        url_div = f"{BASE_URL}/fins/dividend?code={api_code}"
        div_data = safe_fetch(url_div, 5.0)
        result["events"]["dividend"] = div_data.get("dividend", [])
        
    except Exception as e: 
        pass
        
    return result

def get_nikkei_macro_status():
    """完全防弾仕様：列名不一致によるシステム停止を根絶した単一エンジン（18日/50日仕様）"""
    w = get_macro_weather()
    if not w or "nikkei" not in w:
        return {"status": "取得不可", "div_rate": 0.0, "close": 0, "ma18": 0, "ma50": 0, "icon": "⚪", "color": "#888"}
    
    df = w["nikkei"]["df"].copy()
    if len(df) < 50: # 🚨 50日線を計算するため足切りを50に変更
        price = w["nikkei"].get("price", 0)
        return {"status": "データ不足", "div_rate": 0.0, "close": price, "ma18": 0, "ma50": 0, "icon": "⚪", "color": "#888"}
        
    close_col = next((c for c in ['AdjC', 'Close', 'close', 'C', 'c'] if c in df.columns), None)
    
    if not close_col:
        return {"status": "列名異常", "div_rate": 0.0, "close": w["nikkei"]["price"], "ma18": 0, "ma50": 0, "icon": "⚪", "color": "#888"}

    s = df[close_col]
    if isinstance(s, pd.DataFrame):
        s = s.iloc[:, 0]
        
    df['MA18'] = pd.to_numeric(s, errors='coerce').rolling(window=18).mean()
    df['MA50'] = pd.to_numeric(s, errors='coerce').rolling(window=50).mean()
    price = w["nikkei"]["price"]
    ma18 = df['MA18'].iloc[-1]
    ma50 = df['MA50'].iloc[-1]
    
    # 🚨 乖離率の算出（短期トレンド基準として18日線を使用）
    if pd.notna(ma18) and ma18 > 0:
        div_rate = ((price / ma18) - 1) * 100
    else:
        div_rate = 0.0
        
    if div_rate >= 5.0:
        return {"status": "地合い警戒", "div_rate": div_rate, "close": price, "ma18": ma18, "ma50": ma50, "icon": "🔥", "color": "#ef5350"}
    elif div_rate <= -5.0:
        return {"status": "地合いチャンス", "div_rate": div_rate, "close": price, "ma18": ma18, "ma50": ma50, "icon": "🚨", "color": "#ef5350"}
    else:
        return {"status": "地合いニュートラル", "div_rate": div_rate, "close": price, "ma18": ma18, "ma50": ma50, "icon": "🚢", "color": "#26a69a"}

# =========================================================
# 🚀 共通エンジン：進捗バー・件数表示 完全復旧版
# =========================================================
@st.cache_data(ttl=86400, max_entries=1, show_spinner=False, persist="disk") # 🚨 ディスク退避をON
def get_hist_data_cached(key):
    progress_bar = st.progress(0)
    status_text = st.empty()
    
    base = datetime.now(pytz.timezone('Asia/Tokyo'))
    dates, days = [], 0
    while len(dates) < 260:
        d = base - timedelta(days=days)
        if d.weekday() < 5: dates.append(d.strftime('%Y%m%d'))
        days += 1
        if days > 400: break

    dfs = []
    # 🚨 OOMを回避するため、並列数を「2」に抑制し、メモリの過剰な同時展開を防ぐ
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as exe:
        futs = {exe.submit(fetch_and_compress_single_day, dt): dt for dt in dates}
        for i, f in enumerate(concurrent.futures.as_completed(futs)):
            res = f.result()
            if isinstance(res, pd.DataFrame):
                dfs.append(res)
            
            p_val = (i + 1) / len(dates)
            progress_bar.progress(min(p_val, 1.0))
            status_text.text(f"📡 索敵中: {i+1}/{len(dates)}日完了")

    progress_bar.empty()
    status_text.empty()

    if not dfs:
        raise ValueError("🚨 兵站断絶: データ取得失敗")

    full_df = pd.concat(dfs, ignore_index=True)
    full_df['Code'] = full_df['Code'].astype(str).apply(lambda x: x if len(x) >= 5 else x + "0")
    
    # 🚨 結合直後の巨大データフレームを強制圧縮（ここでRAM消費を半減させます）
    full_df = compress_memory(full_df)
    
    gc.collect()
    return full_df.dropna(subset=['AdjC']).sort_values(['Code', 'Date']).reset_index(drop=True)

def fetch_and_compress_single_day(dt):
    # 🚨 開発参謀パッチ適用：無条件突撃から「GC息継ぎ型の戦術巡航」へ移行
    for attempt in range(4):
        try:
            r = api_session.get(f"{BASE_URL}/equities/bars/daily?date={dt}", timeout=20.0)
            if r.status_code == 200:
                raw_json = r.json()
                data = raw_json.get("daily_quotes") or raw_json.get("data") or raw_json.get("results") or []
                if not data: return None
                
                # 🚨 パッチ3：個別のチャンク（1日分）の段階で即座にメモリ極限圧縮をかける
                df_chunk = pd.DataFrame(data)
                df_chunk = compress_memory(df_chunk)
                
                # 🚨 パッチ3：ガベージコレクション（メモリ掃除）に息継ぎの隙間を与える微小ウェイト
                time.sleep(0.05) 
                return df_chunk
            
            elif r.status_code == 429:
                # 🚨 オートブレーキ機構：壁に激突（制限到達）した時だけ5秒間息を潜める
                time.sleep(5.0)
            else:
                return None
        except:
            time.sleep(2.0)
            continue
    return None

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
    tactics = st.session_state.get("sidebar_tactics", "⚖️ バランス (掟達成率 ＞ 到達度)")
    is_assault_mode = "狙撃優先" in tactics
    sl_limit_pct = float(st.session_state.get("bt_sl_c", 8.0))
    
    if macd_hist > 0 and macd_hist_prev <= 0: macd_t = "GC直後"
    elif macd_hist > macd_hist_prev: macd_t = "上昇拡大"
    elif macd_hist < 0 and macd_hist < macd_hist_prev: macd_t = "下落継続"
    else: macd_t = "減衰"
    
    if mode == "強襲":
        if gc_days <= 0:
            if macd_hist < 0 and (macd_hist_prev < macd_hist) and (-macd_hist <= (macd_hist - macd_hist_prev)) and rsi < 75:
                return "S+🎯", "#ff5252", 6, "明日GC見込(激熱)"
            return "圏外🚫", "#ef5350", 0, macd_t

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

def get_assault_triage_info(gc_days, lc, h14, l14, atr, df_chart, sl_limit_pct=8.0, is_strict=False):
    """
    【強襲モード専用】狙撃手仕様トリアージ判定エンジン
    勝率70%・RR1:2を厳守し、高値掴みの遅行性欠陥をパージした完全改修版。
    """
    # データ整合性チェック
    if df_chart is None or df_chart.empty:
        return "圏外 💀", "#424242", 0, "<div>データ不足による判定不可</div>"

    msg_html = ""
    score = 0
    rejection_reasons = []

    # ==============================================================================
    # 1. 資金管理・リスクリワード算出 (RR 1:2)
    # ==============================================================================
    ep = float(h14)  # エントリー価格：直近高値（ブレイクポイント）
    sl = float(l14)  # 損切りライン：起点安値
    risk = ep - sl

    # 異常値の除外（リスク0以下は算出不能として即時パージ）
    if risk <= 0:
        return "圏外 💀", "#424242", 0, "<div>⚠️ リスク算出不可（スイングハイ・ロウのデータ異常）</div>"

    tp2 = ep + (risk * 2.0)  # 利確目標(TP2)：リスク1に対してリターン2
    sl_pct = (risk / ep) * 100.0 if ep > 0 else 100.0

    # ==============================================================================
    # 2. 絶対遵守ルール（鉄の掟）による厳格な棄却フィルタリング
    # ==============================================================================

    # ① 【GCタイミングの厳格化】
    # 発生当日(0)または明日確定見込み(-1以下)のみ許可。1日以上経過は全て「遅行性」として棄却。
    if gc_days > 0:
        rejection_reasons.append(f"GCタイミング遅延（発生から {gc_days} 日経過）")

    # ② 【ボラティリティ未発散フィルター】
    # 現在の価格から起点安値までの上昇幅が1ATRを超過している場合は、既に発散済み（高値掴み）として棄却。
    rise_width = float(lc) - sl
    if rise_width > float(atr):
        rejection_reasons.append(f"ボラティリティ発散済（上昇幅 {rise_width:,.1f}円 ＞ 1ATR {atr:,.1f}円）")

    # ③ 【SL最大損失率の制限】
    # 算出されたSLが許容限度（デフォルト8.0%）を超える場合は、資金管理ルール違反として強制棄却。
    if sl_pct > sl_limit_pct:
        rejection_reasons.append(f"資金管理ルール違反（SL幅 -{sl_pct:.1f}% ＞ 許容限度 -{sl_limit_pct:.1f}%）")

    # ④ 【酒田五法・危険シグナルの除外】
    # 天井圏や警戒を示すシグナルが1つでも点灯していれば即座に無効化。
    try:
        sakata_patterns = detect_sakata_patterns(df_chart)
        danger_keywords = ['三山', '三尊', '黒三兵', '三空', '天井', '警戒', '下落', '包み線', 'はらみ線', '三羽烏']
        danger_signals = [p for p in sakata_patterns if any(k in p for k in danger_keywords)]
        if danger_signals:
            rejection_reasons.append(f"危険シグナル点灯（{', '.join(danger_signals)}）")
    except Exception as e:
        # レーダー異常時はいかなる場合もクラッシュを許さず、安全側に倒して圏外とする。
        rejection_reasons.append("酒田五法レーダー解析エラー（安全装置作動）")

    # ==============================================================================
    # 3. 判定結果のステータス割り当てとUI出力生成
    # ==============================================================================
    if rejection_reasons:
        # 1つでも棄却条件に抵触した場合は強制的に「圏外💀」
        status = "圏外 💀"
        color = "#424242"
        score = 0
        
        # 棄却理由のリストHTML生成
        reasons_li = "".join([f"<li style='margin-bottom: 3px;'>{r}</li>" for r in rejection_reasons])
        
        msg_html = f"""
        <div style='background-color: #2a1e1e; padding: 10px; border-radius: 5px; border-left: 4px solid #ff4b4b; font-size: 0.9em; margin-top: 5px;'>
            <b style='color: #ff4b4b;'>🛡️ 強襲シグナル強制棄却（スナイパールール抵触）</b>
            <ul style='color: #e0e0e0; margin-top: 5px; margin-bottom: 0; padding-left: 20px;'>
                {reasons_li}
            </ul>
        </div>
        """
    else:
        # 全てのフィルタを通過（狙撃条件クリア）
        status = "S級⚡ (強襲)" if gc_days == 0 else "A級🔥 (狙撃待機)"
        color = "#ffd700" if gc_days == 0 else "#ff8c00"
        score = 80 if gc_days == 0 else 65

        msg_html = f"""
        <div style='background-color: #1e2a1e; padding: 10px; border-radius: 5px; border-left: 4px solid #00ff00; margin-bottom: 10px; font-size: 0.9em;'>
            <b style='color: #00ff00;'>🎯 強襲スナイパー・ロックオン</b><br>
            <span style='color: #e0e0e0;'>
            ・GCステータス: {'本日発生 (0日目)' if gc_days == 0 else '明日確定水準 (-1日目)'}<br>
            ・ボラティリティ: 未発散（上昇幅 {rise_width:,.1f}円 ≦ 1ATR {atr:,.1f}円）
            </span>
        </div>
        <div style='background-color: #1c1c28; padding: 10px; border-radius: 5px; border-left: 4px solid #4da6ff; font-size: 0.9em;'>
            <b style='color: #4da6ff;'>📐 資金管理・リスクリワード (RR 1:2)</b>
            <table style='width: 100%; text-align: left; margin-top: 8px; border-collapse: collapse;'>
                <tr style='border-bottom: 1px solid #333;'>
                    <th style='padding: 4px; color: #a0a0a0;'>エントリー (EP)</th>
                    <td style='padding: 4px; color: #ffffff; text-align: right;'><b>{ep:,.0f} 円</b></td>
                    <td style='padding: 4px; color: #a0a0a0; font-size: 0.85em;'>(高値ブレイク)</td>
                </tr>
                <tr style='border-bottom: 1px solid #333;'>
                    <th style='padding: 4px; color: #a0a0a0;'>損切ライン (SL)</th>
                    <td style='padding: 4px; color: #ff4b4b; text-align: right;'><b>{sl:,.0f} 円</b></td>
                    <td style='padding: 4px; color: #ff4b4b; font-size: 0.85em;'>(-{sl_pct:.1f}%)</td>
                </tr>
                <tr>
                    <th style='padding: 4px; color: #a0a0a0;'>利確目標 (TP2)</th>
                    <td style='padding: 4px; color: #00ff00; text-align: right;'><b>{tp2:,.0f} 円</b></td>
                    <td style='padding: 4px; color: #00ff00; font-size: 0.85em;'>(+{sl_pct*2:.1f}%)</td>
                </tr>
            </table>
        </div>
        """

    return status, color, score, msg_html

# ==============================================================================
# 🎯 1. 新・待伏せトリアージ判定エンジン（MACD完全排除・ATR価格アクション特化）
# ==============================================================================

def get_ambush_triage_info(lc, buy_target, atr, df_chart=None):
    """
    買目標値と14日ATRを用いた精密位置判定 ＋ 酒田五法（底打ちサイン）のハイブリッドレーダー
    ※ クジラの資金流入検知（出来高）および RR1:2 / SL8% フィルター搭載版
    """
    # 0. 兵站（データ）不足の防衛機構
    if df_chart is None or df_chart.empty or len(df_chart) < 6:
        return "圏外 💀", "#424242", 0, "兵站不足（データ欠損）"

    # ========================================================
    # 【追加要件3】RR1:2 / 損失固定ルール（SL -8.0%）の強制審査
    # ========================================================
    # サイドバーの「現在損切(%)」から限界値を取得（デフォルト8.0%）
    sl_limit_pct = float(st.session_state.get("bt_sl_c", 8.0)) 
    
    # 基準となるリスク/リワードの自動算出（TAB4ベースに同期。SL=1ATR, TP=2ATRを基準とする）
    sl_price = lc - atr
    tp_price = lc + (atr * 2.0)
    
    risk = lc - sl_price
    reward = tp_price - lc
    rr_ratio = reward / risk if risk > 0 else 0
    sl_pct = (risk / lc) * 100 if lc > 0 else 100

    # 物理排除（パージ）ロジック
    if sl_pct > sl_limit_pct:
        return "圏外 💀", "#424242", 0, f"強制パージ: SL限界超過 ({sl_pct:.1f}% > {sl_limit_pct}%)"
    if rr_ratio < 2.0:
        return "圏外 💀", "#424242", 0, f"強制パージ: RR要件未達 (1:{rr_ratio:.1f})"

    # ========================================================
    # 【追加要件1】出来高（クジラの資金流入）による裏付け判定
    # ========================================================
    recent_vol = df_chart['Volume'].iloc[-1]
    vol_5d_avg = df_chart['Volume'].iloc[-6:-1].mean()
    is_whale_active = recent_vol >= (vol_5d_avg * 1.5)

    # 1. 酒田五法の底打ちサイン検知（防弾仕様）
    has_bottom_signal = False
    sakata_msg = ""
    is_s_class = False

    # ※ ここに既存の酒田五法判定ロジック（たくり線・二重底などのTrue/False判定）が入ります。
    # 例: has_bottom_signal = check_sakata_patterns(df_chart)

    # シグナル点灯時のS級格上げ審査（クジラ判定のAND条件）
    if has_bottom_signal:
        if is_whale_active:
            is_s_class = True
            sakata_msg = "🔥 クジラ流入伴うS級底打ちサイン"
        else:
            is_s_class = False
            sakata_msg = "⚠️ ダマシ警戒（サイン点灯も出来高不足）"

    # 最終トリアージ出力
    if is_s_class:
        return "S級 🔥", "#FF4B4B", 12, sakata_msg
    elif has_bottom_signal:
        return "A級 💎", "#00D2FF", 8, sakata_msg
    else:
        return "B級 🛡️", "#FFD166", 5, "監視継続・反転待ち"

# ==============================================================================
# 🎯 2. 精密スコープ ロジック演算・描画エンジン（完全展開版）
# ==============================================================================

def render_tab3_scope_logic(df, code, company_name, event_data=None):
    if df is None or df.empty:
        return None
    
    # 1. 絶対価格データの取得（スイングハイ・スイングロウ）
    p_high = df['AdjH'].max()
    p_low = df['AdjL'].min()
    current_p = df.iloc[-1]['AdjC']
    
    # 2. ボラティリティ（14日ATR）の完全算出
    df_atr = df.copy()
    df_atr['PrevClose'] = df_atr['AdjC'].shift(1).fillna(df_atr['AdjC'])
    df_atr['tr0'] = abs(df_atr['AdjH'] - df_atr['AdjL'])
    df_atr['tr1'] = abs(df_atr['AdjH'] - df_atr['PrevClose'])
    df_atr['tr2'] = abs(df_atr['AdjL'] - df_atr['PrevClose'])
    df_atr['tr'] = df_atr[['tr0', 'tr1', 'tr2']].max(axis=1)
    
    # データ数が14日未満の場合のエラー回避用フォールバック
    if len(df_atr) >= 14:
        atr_val = df_atr['tr'].rolling(window=14).mean().iloc[-1]
    else:
        atr_val = df_atr['tr'].mean()
        
    if pd.isna(atr_val) or atr_val == 0:
        atr_val = 1.0 # ゼロ除算等の回避
    
    # 3. 買目標値の算出（スイングハイからのフィボナッチ50%押し基準）
    bt_target = p_high - ((p_high - p_low) * 0.5)
    
    # 4. 新・待伏せトリアージの実行（酒田シグナル検知・直結版）
    triage_status, triage_color = get_ambush_triage_info(current_p, bt_target, atr_val, df)
    
    # 5. 基礎指標計算（RSIは遅行指標ではないオシレーターとして維持）
    diff = df['AdjC'].diff()
    gain = diff.where(diff > 0, 0.0).rolling(window=14).mean()
    loss = -diff.where(diff < 0, 0.0).rolling(window=14).mean()
    rs = gain / loss
    rsi = 100 - (100 / (1 + rs)).iloc[-1]
    if pd.isna(rsi):
        rsi = 50.0

    # 6. アラート文字列の生成（イベント検知・エラー回避版）
    alerts = []
    if event_data:
        if "earnings" in event_data and event_data["earnings"]:
            alerts.append("決算接近")
        if "dividend" in event_data and event_data["dividend"]:
            alerts.append("配当権利日")
    alerts_str = " / ".join(alerts) if alerts else "特になし"

    # --- UI内包描画ブロック ---
    st.markdown(f"### 🎯 [{code}] {company_name}")
    
    col1, col2, col3 = st.columns(3)
    col1.metric("最新終値", f"{int(current_p):,} 円")
    col2.metric("システム買目標値", f"{int(bt_target):,} 円")
    col3.metric("1ATR (14日)", f"{int(atr_val):,} 円")
    
    st.markdown(
        f"<div style='padding: 12px; border-radius: 5px; border: 2px solid {triage_color}; "
        f"background-color: {triage_color}15; color: {triage_color}; font-weight: bold; font-size: 1.15em; margin-bottom: 20px;'>"
        f"現在の戦況：{triage_status}</div>", 
        unsafe_allow_html=True
    )
    
    # 7. 結果辞書の構築（エクスポート・上位処理用）
    vr = {
        'code': code,
        'name': company_name,
        'lc': current_p,
        'h14': p_high,
        'l14': p_low,
        'atr_val': atr_val,
        'bt_target': bt_target,
        'rsi': rsi,
        'triage_status': triage_status,
        'rank': triage_status.split('】')[0].replace('【', ''),
        'score': 0,
        'alerts_str': alerts_str
    }
    
    return vr

def get_triage_info(macd_hist, macd_hist_prev, rsi, lc=0, bt=0, mode="待伏", gc_days=0):
    tactics = st.session_state.get("sidebar_tactics", "⚖️ バランス (掟達成率 ＞ 到達度)")
    is_assault_mode = "狙撃優先" in tactics
    sl_limit_pct = float(st.session_state.get("bt_sl_c", 8.0))

def get_assault_triage_info(gc_days, lc, rsi_v, df_chart, is_strict=False):
    if df_chart is None or df_chart.empty:
        return "圏外 💀", "#424242", 0, ""

def scan_unit_new_rules_parallel(group_df, c, cfg, macro_alert_text):
    """
    【新・迎撃／爆撃ルール】3日間反転フォーメーション ＋ ファンダ・地合い判定
    """
    try:
        # データ不足、または上場直後の銘柄は弾く（エラー防止）
        if group_df is None or len(group_df) < 5:
            return None
        df = group_df.copy()

        lc = df['Close'].iloc[-1]
        min_p = cfg.get("f1_min", 0)
        max_p = cfg.get("f1_max", 99999)

        if not (min_p <= lc <= max_p):
            return None

        # ==========================================
        # 1. テクニカル判定（3日間の反転フォーメーション）
        # ==========================================
        # --- ラリー・ウィリアムズ完全再現（ヒゲを含む厳格な高値・安値の突破） ---
        buy_day1 = df['Close'].iloc[-3] < df['Low'].iloc[-4]
        buy_day2 = df['Close'].iloc[-2] > df['High'].iloc[-3]
        buy_day3 = df['Close'].iloc[-1] > df['Close'].iloc[-2]
        is_buy_tech = buy_day1 and buy_day2 and buy_day3

        short_day1 = df['Close'].iloc[-3] > df['High'].iloc[-4]
        short_day2 = df['Close'].iloc[-2] < df['Low'].iloc[-3]
        short_day3 = df['Close'].iloc[-1] < df['Close'].iloc[-2]
        is_short_tech = short_day1 and short_day2 and short_day3

        # テクニカル条件未達なら即時パージ（通信リソースの節約）
        if not (is_buy_tech or is_short_tech):
            return None

        # ==========================================
        # 2. マクロ地合い判定（空売り用）
        # ==========================================
        is_macro_downtrend = False
        if "警戒" in macro_alert_text or "下落" in macro_alert_text or "-" in macro_alert_text:
            is_macro_downtrend = True

        # ==========================================
        # 3. ファンダメンタルズ判定（ファジー・スコアリング）
        # ==========================================
        buy_funda_ok = False
        short_funda_ok = False
        funda_msg = "条件未達"

        try:
            # 厳格なテクニカルを通過した少数精鋭のみAPIでファンダ確認
            import yfinance as yf
            tk = yf.Ticker(f"{c}.T")
            info = tk.info
            rev_growth = info.get('revenueGrowth', 0)
            earn_growth = info.get('earningsGrowth', 0)

            if rev_growth is None: rev_growth = 0
            if earn_growth is None: earn_growth = 0

            # ＜買いルール＞ 売上7%, 利益20%付近
            if is_buy_tech:
                score = 0
                if rev_growth >= 0.07: score += 2
                elif rev_growth >= 0.05: score += 1  # 5%以上なら「だいたい近い」として加点

                if earn_growth >= 0.20: score += 2
                elif earn_growth >= 0.15: score += 1 # 15%以上なら「だいたい近い」として加点

                if score >= 3:
                    buy_funda_ok = True
                    funda_msg = f"🔥 買S級 (売上:{rev_growth*100:.1f}% 益:{earn_growth*100:.1f}%)"
                elif score >= 1:
                    buy_funda_ok = True
                    funda_msg = f"🟢 買A級 (売上:{rev_growth*100:.1f}% 益:{earn_growth*100:.1f}%)"

            # ＜空売りルール＞ 利益5%未満付近、または地合い悪化
            if is_short_tech:
                if is_macro_downtrend:
                    short_funda_ok = True
                    funda_msg = f"📉 空S級 (マクロ地合い連動: 下げ相場)"
                else:
                    score = 0
                    if earn_growth < 0.05: score += 2
                    elif earn_growth < 0.08: score += 1 # 8%未満なら「だいたい近い」として加点

                    if score >= 2:
                        short_funda_ok = True
                        funda_msg = f"⚠️ 空S級 (益:{earn_growth*100:.1f}% 減速)"
                    elif score >= 1:
                        short_funda_ok = True
                        funda_msg = f"🟡 空A級 (益:{earn_growth*100:.1f}% 減速傾向)"

        except Exception as e:
            funda_msg = "ファンダ情報取得不能(技術的承認)"
            # APIエラー時はテクニカルの優位性を信じて強制パス（機会損失の防止）
            if is_buy_tech: buy_funda_ok = True
            if is_short_tech: short_funda_ok = True

        # 最終承認チェック
        is_final_buy = is_buy_tech and buy_funda_ok
        is_final_short = is_short_tech and short_funda_ok

        if not (is_final_buy or is_final_short):
            return None

        signal_type = "🔵 買いシグナル" if is_final_buy else "🔴 空売りシグナル"

        return {
            "Code": c,
            "Close": lc,
            "Signal": signal_type,
            "Funda": funda_msg,
            "Volume": df['Volume'].iloc[-1]
        }

    except Exception as e:
        return None

def draw_chart(df, targ_p, sakata=[], chart_key=None):
    if df is None or df.empty:
        return

    # ==========================================
    # 🎯 1. 1年分（約250営業日）のデータを裏側に完全装填
    # ==========================================
    df_plot = df.copy()
    df_plot = df_plot.tail(250).reset_index(drop=True) 
    
    # 🚨 スナイパー仕様：MAを18日と50日に完全換装
    if 'MA18' not in df_plot.columns: df_plot['MA18'] = df_plot['AdjC'].rolling(18).mean()
    if 'MA50' not in df_plot.columns: df_plot['MA50'] = df_plot['AdjC'].rolling(50).mean()

    df_plot['arrow'] = df_plot['AdjC'].diff().apply(lambda x: " ▲" if x > 0 else " ▼" if x < 0 else "")

    ma18_str = df_plot['MA18'].apply(lambda x: f"{x:,.0f}" if pd.notna(x) else "-")
    ma50_str = df_plot['MA50'].apply(lambda x: f"{x:,.0f}" if pd.notna(x) else "-")

    # ホバーテキスト用のカスタムデータ配列を再構築
    customdata = np.column_stack((df_plot['arrow'], ma18_str, ma50_str))

    fig = go.Figure()

    fig.add_trace(go.Candlestick(
        x=df_plot['Date'],
        open=df_plot['AdjO'], high=df_plot['AdjH'],
        low=df_plot['AdjL'], close=df_plot['AdjC'],
        name='価格',
        customdata=customdata,
        hovertemplate=(
            "始値：%{open:,.0f}<br>"
            "終値：%{close:,.0f}%{customdata[0]}<br>"
            "高値：%{high:,.0f}<br>"
            "安値：%{low:,.0f}<br>"
            "MA18：%{customdata[1]}<br>"
            "MA50：%{customdata[2]}<br>"
            "<extra></extra>"
        ),
        increasing_line_color='#26a69a', 
        decreasing_line_color='#ef5350'
    ))

    # 🚨 描画する移動平均線を18日（緑系）と50日（オレンジ系）に設定
    ma_configs = [('MA18', '#26a69a', '18日線'), ('MA50', '#ff9800', '50日線')]
    for col, color, label in ma_configs:
        if col in df_plot.columns:
            fig.add_trace(go.Scatter(
                x=df_plot['Date'], y=df_plot[col], 
                name=label,
                line=dict(color=color, width=1.5),
                connectgaps=True,
                hoverinfo='skip'
            ))

    fig.add_trace(go.Scatter(
        x=df_plot['Date'], 
        y=[targ_p] * len(df_plot),
        name='目標：',
        line=dict(color="#FFD700", width=2, dash="dash"),
        mode='lines',
        hovertemplate=f"目標：{targ_p:,.0f}<extra></extra>"
    ))

    date_str_series = df_plot['Date'].astype(str).str[:10]
    for i, p in enumerate(sakata):
        try:
            s_date, s_type, s_label, s_color = p.get('date'), p.get('type', 'bull'), p.get('label', 'Sign'), p.get('color', '#FFFFFF')
            if not s_date: continue
            is_bear = (s_type == 'bear')
            offset_ay = -60 - (i * 30) if is_bear else 60 + (i * 30)
            target_date_str = str(s_date)[:10]
            match_row = df_plot[date_str_series == target_date_str]
            price_ref = match_row['AdjH' if is_bear else 'AdjL'].values[0] if not match_row.empty else df_plot['AdjC'].iloc[-1]

            fig.add_annotation(
                x=s_date, y=price_ref, text=s_label, showarrow=True, arrowhead=2, arrowcolor=s_color,
                ax=0, ay=offset_ay, bgcolor="rgba(10,10,10,0.85)", bordercolor=s_color, borderwidth=1, font=dict(color=s_color, size=11)
            )
        except Exception:
            continue

    # ==========================================
    # 🎯 2. 初期表示（直近65日間）の最適Y軸スケール計算
    # ==========================================
    view_start_date = df_plot['Date'].max() - timedelta(days=65)
    df_recent = df_plot[df_plot['Date'] >= view_start_date]

    focus_y_range = None
    if not df_recent.empty:
        y_min = df_recent['AdjL'].min()
        y_max = df_recent['AdjH'].max()

        if targ_p and not pd.isna(targ_p) and targ_p > 0:
            y_min = min(y_min, targ_p)
            y_max = max(y_max, targ_p)

        # 🚨 スケール計算用の判定軸も18日・50日に変更
        for col in ['MA18', 'MA50']:
            if col in df_recent.columns:
                ma_min = df_recent[col].min()
                ma_max = df_recent[col].max()
                if pd.notna(ma_min): y_min = min(y_min, ma_min)
                if pd.notna(ma_max): y_max = max(y_max, ma_max)

        y_margin = (y_max - y_min) * 0.1
        if y_margin == 0: y_margin = y_max * 0.1
        focus_y_range = [y_min - y_margin, y_max + y_margin]

    # ==========================================
    # 🎯 3. レイアウトおよび「白背景・黒文字スイッチ」の配備
    # ==========================================
    fig.update_layout(
        template='plotly_dark', height=650, margin=dict(l=0, r=0, t=40, b=80),
        paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)', 
        hovermode="x unified",
        dragmode='pan', 
        hoverlabel=dict(bgcolor="rgba(20, 20, 20, 0.95)", font_size=13, font_family="Consolas"),
        xaxis_rangeslider_visible=False, 
        yaxis=dict(side="right", tickformat=",.0f", gridcolor='rgba(255,255,255,0.05)', range=focus_y_range, fixedrange=False, zeroline=False),
        xaxis=dict(showgrid=True, gridcolor='rgba(255,255,255,0.05)', range=[view_start_date, df_plot['Date'].max() + timedelta(days=2)]),
        legend=dict(orientation="h", yanchor="top", y=-0.32, xanchor="center", x=0.5, font=dict(color="#eee", size=11)),
        
        # 🚨 スイッチの色彩仕様を変更（背景：白 ✕ 文字：漆黒）
        updatemenus=[
            dict(
                type="buttons",
                direction="right", 
                active=0,
                x=0.01,
                y=1.08,
                xanchor="left",
                yanchor="top",
                pad=dict(t=0, r=0, b=0, l=0),
                bgcolor="rgba(255, 255, 255, 0.95)",  # 🚨 視認性の高いクリアホワイトに換装
                bordercolor="rgba(0, 0, 0, 0.4)",      # 枠線も黒系で縁取り
                font=dict(color="#111111", size=12),   # 🚨 文字盤を漆黒（白以外）にロック
                buttons=[
                    dict(label="✋ 左右移動（過去に遡る）", method="relayout", args=[{"dragmode": "pan"}]),
                    dict(label="🔍 範囲選択（囲んで拡大）", method="relayout", args=[{"dragmode": "zoom"}])
                ]
            )
        ]
    )

    st.plotly_chart(
        fig, 
        use_container_width=True, 
        config={
            'displayModeBar': True,        
            'modeBarButtonsToRemove': ['lasso2d', 'select2d'], 
            'responsive': True, 
            'scrollZoom': True
        }, 
        key=f"{chart_key}_{int(time.time()*1000)}"
    )

# --- 司令官が先ほど追加した共通マスタ定義 ---
master_df = load_master()
master_map = {}
if master_df is not None and not master_df.empty:
    m_df_tmp = master_df[['Code', 'CompanyName', 'Market', 'Sector']].copy()
    m_df_tmp['Code'] = m_df_tmp['Code'].astype(str).apply(lambda x: x if len(x) >= 5 else x + "0")
    master_map = m_df_tmp.set_index('Code').to_dict('index')
    del m_df_tmp

master_map_t1 = master_map
master_map_t2 = master_map
tactics_mode = st.session_state.get('sidebar_tactics', "⚖️ バランス (掟達成率 ＞ 到達度)")

# ==========================================
# 🎯 2026年式：戦略テーマ・ハイブリッド辞書
# ==========================================
PRESET_THEMES = {
    "🤖 AI・DX統合": [
        "8035", "6857", "6723", "6758", "9432", "9984", 
        "4393", "4488", "4475", "9553", "3993", "4011", "5574", "5595", "3655"
    ],
    "⚡ データセンター/電力/銅": [
        "3778", "9501", "9508", "6501", "5803", "5802", "9502", "9503",
        "6255", "6617", "1407", "9519", "3853", "9338"
    ],
    "🏗️ 半導体/次世代装置": [
        "6146", "6920", "7735", "6315", "6871", "4063",
        "6227", "6323", "3498", "6627", "6525"
    ],
    "🚀 防衛/宇宙/セキュリティ": [
        "7011", "7012", "7013", "6503",
        "4274", "5597", "2326", "4493"
    ]
}

def apply_price_filter(df, price_col='AdjC'):
    """ 全軍共通：価格上限・下限フィルター適用関数 """
    if df is None or df.empty:
        return df
    min_price = float(st.session_state.get("f1_min", 200))
    max_price = float(st.session_state.get("f1_max", 3000))
    filtered_df = df[(df[price_col] >= min_price) & (df[price_col] <= max_price)]
    return filtered_df
    
def get_latest_macro_sync():
    """全タブ共通で使う、常に最新の日経平均と乖離率を算出する単一エンジン"""
    w = get_macro_weather()
    if not w or "nikkei" not in w:
        return {"status": "取得失敗", "div_rate": 0.0}
    
    df = w["nikkei"]["df"].copy()
    if len(df) < 25:
        return {"status": "データ不足", "div_rate": 0.0}
        
    close_col = next((c for c in ['AdjC', 'Close', 'close', 'C', 'c'] if c in df.columns), None)
    if close_col:
        s = df[close_col]
        if isinstance(s, pd.DataFrame):
            s = s.iloc[:, 0]
        df['MA25'] = pd.to_numeric(s, errors='coerce').rolling(window=25).mean()
    else:
        return {"status": "データ異常", "div_rate": 0.0}
        
    price = w["nikkei"]["price"]
    ma25 = df['MA25'].iloc[-1]
    div_rate = ((price / ma25) - 1) * 100
    
    if div_rate >= 5.0: 
        return {"status": "地合い警戒", "div_rate": div_rate}
    elif div_rate <= -5.0: 
        return {"status": "地合いチャンス", "div_rate": div_rate}
    else: 
        return {"status": "地合いニュートラル", "div_rate": div_rate}

# ==========================================
# 🚨 UI展開・サイドバー処理（関数の外に配置します）
# ==========================================
use_macro = True  # 🚨 参謀パッチ：NameErrorを完全に防ぐため、明示的に定義（常時有効化）

if use_macro:
    # 🚨 weather変数の未定義エラーも同時に防ぐため、関数から直接安全に取得
    _weather_data = get_macro_weather() 
    api_nikkei_pct = _weather_data['nikkei']['pct'] if _weather_data and 'nikkei' in _weather_data else 0.0
    
    manual_pct = st.sidebar.number_input(
        "日経騰落率（API値自動入力 %）", 
        value=float(api_nikkei_pct), 
        step=0.1, 
        format="%.2f",
        help="暴落シミュレーションをする場合は数値を書き換えてください。"
    )

    prefix = ""
    if manual_pct <= -2.0:
        st.session_state.push_penalty = 0.10  
        st.session_state.rsi_penalty = 20     
        prefix = f"🔴 厳戒態勢(前日比 {manual_pct:+.2f}%) ｜ "
    elif manual_pct <= -1.0:
        st.session_state.push_penalty = 0.05  
        st.session_state.rsi_penalty = 10     
        prefix = f"🟠 警戒態勢(前日比 {manual_pct:+.2f}%) ｜ "

    macro = get_latest_macro_sync()
    div_v = macro['div_rate']
    
    base_alert = f"🌐【{macro['status']}】日経乖離率 {div_v:+.2f}%。"
    if macro['status'] == "地合い警戒": 
        base_alert += "天井掴みに注意。"
    elif macro['status'] == "地合いチャンス": 
        base_alert += "押し目買い好機。"
    else: 
        base_alert += "個別銘柄の動きを重視。"

    st.session_state.macro_alert = prefix + base_alert

st.sidebar.divider()

# ==========================================
# 2. 🎯 戦略テーマ選別
# ==========================================
st.sidebar.header("🎯 戦略テーマ選別")

selected_themes = st.sidebar.multiselect(
    "注目テーマ（複数選択可）",
    options=list(PRESET_THEMES.keys()) if 'PRESET_THEMES' in locals() else [],
    default=[],
    help="選択したテーマの銘柄のみを抽出します。"
)

custom_theme_input = st.sidebar.text_input(
    "手動コード追加 (例: 9501, 3778)",
    value="",
    help="リストにない期待銘柄を即座に追加できます。"
)

target_theme_codes = set()
if 'PRESET_THEMES' in locals():
    for t in selected_themes:
        target_theme_codes.update(PRESET_THEMES[t])

if custom_theme_input:
    custom_list = [c.strip() for c in custom_theme_input.split(",") if c.strip()]
    target_theme_codes.update(custom_list)

st.sidebar.divider()

# ==========================================
# 3. 📂 戦略的セクター制御
# ==========================================
st.sidebar.header("📂 戦略的セクター制御")

st.session_state.f_max_stocks_per_sector = st.sidebar.slider(
    "1セクターあたりの最大表示数",
    1, 30,
    key="f_max_stocks_slider",
    help="特定セクターへの集中度を調整します。"
)

if 'master_df' in globals() and master_df is not None and not master_df.empty:
    all_sectors = sorted(master_df['Sector'].unique().tolist())
    if "f_selected_sectors" not in st.session_state:
        st.session_state.f_selected_sectors = all_sectors

    with st.sidebar.expander("業種別フィルター設定", expanded=False):
        col_all, col_none = st.columns(2)
        
        if col_all.button("全選択", key="btn_sec_all", use_container_width=True):
            for s in all_sectors:
                st.session_state[f"cb_sec_{s}"] = True 
            st.session_state.f_selected_sectors = all_sectors
            st.rerun()

        if col_none.button("全解除", key="btn_sec_none", use_container_width=True):
            for s in all_sectors:
                st.session_state[f"cb_sec_{s}"] = False 
            st.session_state.f_selected_sectors = []
            st.rerun()

        selected_list = []
        for s in all_sectors:
            if st.checkbox(s, value=st.session_state.get(f"cb_sec_{s}", True), key=f"cb_sec_{s}"):
                selected_list.append(s)
        st.session_state.f_selected_sectors = selected_list
else:
    st.sidebar.warning("⚠️ 業種マスタの読み込みを待機中...")

st.sidebar.divider()

# ==========================================
# 4. 📍 ターゲット選別
# ==========================================
st.sidebar.header("📍 ターゲット選別")

# --- 1. 市場ターゲット ---
market_options = ["🏢 大型株 (プライム・一部)", "🚀 中小型株 (スタンダード・グロース)"]
if "preset_market" not in st.session_state:
    st.session_state.preset_market = market_options[1]
st.sidebar.selectbox(
    "市場ターゲット", 
    options=market_options, 
    key="preset_market", 
    on_change=extended_save_settings
)

# --- 2. 押し目プリセット ---
push_r_options = ["25.0%", "50.0%", "61.8%"]
if "preset_push_r" not in st.session_state:
    st.session_state.preset_push_r = push_r_options[1]
st.sidebar.selectbox(
    "押し目プリセット", 
    options=push_r_options, 
    key="preset_push_r", 
    on_change=apply_presets
)

# --- 3. 戦術アルゴリズム ---
tactics_options = ["⚖️ バランス (掟達成率 ＞ 到達度)", "🎯 狙撃優先 (到達度 ＞ 掟達成率)"]
if "sidebar_tactics" not in st.session_state:
    st.session_state.sidebar_tactics = tactics_options[0]
st.sidebar.selectbox(
    "戦術アルゴリズム", 
    options=tactics_options, 
    key="sidebar_tactics", 
    on_change=extended_save_settings
)

st.sidebar.divider()

# ==========================================
# 5. 🌪️ ボラティリティ審査
# ==========================================
st.sidebar.header("🌪️ ボラティリティ審査")
st.session_state.f_vol_min = st.sidebar.slider(
    "最小ボラ率 (ATR/価格 %)", 
    0.0, 2.0, step=0.1, 
    help="1ATRが株価の何%以上かを判定。0.5%未満はTAB1/2の検索結果から排除されます。",
    key="f_vol_min_slider"
)

st.sidebar.divider()

# ==========================================
# 6. 🔍 全軍共通足切りルール（特殊除外フィルター統合版）
# ==========================================
st.sidebar.header("🔍 全軍共通足切りルール")

c1, c2 = st.sidebar.columns(2)
with c1:
    st.number_input("価格下限(円)", step=100, key="f1_min", on_change=extended_save_settings)
with c2:
    st.number_input("価格上限(円)", step=100, key="f1_max", on_change=extended_save_settings)

st.sidebar.markdown("<div style='margin-top: 10px;'></div>", unsafe_allow_html=True)
st.sidebar.markdown("#### 🛡️ 特殊個体・自動パージ")

st.sidebar.checkbox("🚀 IPO除外(上場1年未満)", key="f5_ipo", on_change=extended_save_settings)
st.sidebar.checkbox("⚠️ 疑義注記・信用リスク銘柄除外", key="f6_risk", on_change=extended_save_settings)
st.sidebar.checkbox("🌊 上昇第3波終了銘柄を除外", key="f11_ex_wave3", on_change=extended_save_settings)
st.sidebar.checkbox("💸 非常に割高・赤字銘柄を除外", key="f12_ex_overvalued", on_change=extended_save_settings)
st.sidebar.checkbox("🏢 ETF・REIT等を除外", key="f7_ex_etf", on_change=extended_save_settings)
st.sidebar.checkbox("💊 医薬品(バイオ)を除外", key="f8_ex_bio", on_change=extended_save_settings)
st.sidebar.checkbox("🔪 落ちるナイフ除外(暴落直後)", key="f10_ex_knife", on_change=extended_save_settings)

# --- 🛡️ アプリ起動時にGoogle DBから除外コードを復元する ---
# gigi_inputが存在するかどうかではなく、確実に1回だけDBから読み込むためのフラグを使う
if "db_exclude_loaded" not in st.session_state:
    st.session_state.gigi_input = load_exclude_codes()
    st.session_state.db_exclude_loaded = True
    
st.sidebar.text_area(
    "除外銘柄コード (カンマ区切り)", 
    key="gigi_input", 
    on_change=extended_save_settings,
    help="手動でスキャンから除外したいコードを入力（例: 9984, 7203）"
)

st.sidebar.divider()

# ==========================================
# (2) メイン画面の描画スタート
# ==========================================

# --- 📍 マクロ気象局アラートの表示 ---
_macro_fallback = get_macro_weather()
if _macro_fallback and "nikkei" in _macro_fallback:
    _ni_fb = _macro_fallback["nikkei"]
    _df_fb = _ni_fb["df"].copy()
    
    if not _df_fb.empty and len(_df_fb) >= 25:
        # 🚨 モグラ駆逐パッチ：日経平均の終値カラムを安全に取得
        _close_col_fb = next((c for c in ['AdjC', 'Close', 'close', 'C', 'c'] if c in _df_fb.columns), None)
        
        if _close_col_fb:
            _s_fb = _df_fb[_close_col_fb]
            if isinstance(_s_fb, pd.DataFrame):
                _s_fb = _s_fb.iloc[:, 0]
            _df_fb['MA25'] = pd.to_numeric(_s_fb, errors='coerce').rolling(window=25).mean()
            _price_fb = _ni_fb["price"]
            _ma25_fb = _df_fb['MA25'].iloc[-1]
            
            if pd.notna(_ma25_fb) and _ma25_fb > 0:
                _div_fb = ((_price_fb / _ma25_fb) - 1) * 100
                
                # 🚨 ステータス判定用アイコンと色の決定
                if _div_fb >= 5.0:
                    _icon, _color = "🔥", "#ef5350"
                elif _div_fb <= -5.0:
                    _icon, _color = "🚨", "#ef5350"
                else:
                    _icon, _color = "🚢", "#26a69a"
                
                # 🚨 枠内から「アラート文（🌐…）」を完全撤去し、データ観測に特化
                st.markdown(f"""
                <div style="background-color: rgba(30, 30, 30, 0.5); padding: 10px; border-radius: 5px; border: 1px solid #444; margin-bottom: 15px;">
                    <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 5px;">
                        <span style="font-size: 14px; color: #aaa;">📡 マクロ気象観測：日経平均25日乖離率</span>
                        <span style="font-size: 18px; color: {_color};">{_icon}</span>
                    </div>
                    <div style="display: flex; gap: 20px;">
                        <div><span style="font-size: 12px; color: #888;">日経現在値:</span> <b style="font-size: 16px;">{_price_fb:,.0f}円</b></div>
                        <div><span style="font-size: 12px; color: #888;">25日移動平均:</span> <b style="font-size: 16px;">{_ma25_fb:,.0f}円</b></div>
                        <div><span style="font-size: 12px; color: #888;">乖離率:</span> <b style="font-size: 20px; color: {_color};">{_div_fb:+.2f}%</b></div>
                    </div>
                </div>
                """, unsafe_allow_html=True)

# --- 5. タブ構成（原本UI ＆ NameError物理根絶配置） ---
render_macro_board()
# ==========================================
# 🎯 タブ定義（新構成：TAB1, TAB2, TAB7のみ）
# ==========================================
tab1, tab2, tab3, tab7 = st.tabs([
    "📈 TAB1: 買い", 
    "📉 TAB2: 空売り", 
    "🎯 TAB3: 精密スコープ", 
    "📁 TAB7: 戦績"
])

# ==========================================
# 🌐 TAB1: 買い銘柄広域スキャン (Growth / Standard / Prime)
# ==========================================
with tab1:
    st.markdown('### 🌐 買い銘柄広域スキャン', unsafe_allow_html=True)
    st.caption("※直近2四半期の売上・利益成長率をベースに、大化け候補（S級・A級）を広域索敵します。")
    
    # 1. フォームの定義（入力項目とスキャン実行ボタン）
    with st.form("tab1_buy_scan_form", clear_on_submit=False):
        col1_1, col1_2, col1_3 = st.columns(3)
        t1_period = col1_1.selectbox("期間フィルタ (高値判定基準)", ["52週", "2年", "6か月", "3か月"], index=0)
        t1_sales_r = col1_2.selectbox("直近四半期 売上増収率 (%)", [7, 5, 3], index=0)
        t1_ord_r = col1_3.selectbox("直近四半期 経常利益増益率 (%)", [15, 13, 10], index=0)
        
        col1_4, col1_5, col1_6 = st.columns(3)
        t1_p_min = col1_4.number_input("価格下限 (円)", value=100, step=100, key="t1_p_min")
        t1_p_max = col1_5.number_input("価格上限 (円)", value=10000, step=100, key="t1_p_max")
        
        st.markdown("**(固定スキャン条件: 直近2四半期連続クリア)** \n"
                    f"・売上: 前四半期比 `{t1_sales_r}%`以上  \n"
                    f"・営業利益: 前四半期比 `15%`以上 (20%以上でS級🎯)  \n"
                    f"・経常利益: 前四半期比 `{t1_ord_r}%`以上 (20%以上でS級🎯)  \n"
                    f"・一株利益: 前四半期比 `15%`以上 (20%以上でS級🎯)")
        
        btn_scan_t1 = st.form_submit_button("🚀 買い銘柄 スキャン実行", use_container_width=True, type="primary")

    # 2. スキャン実行処理（完全直列・防弾仕様）
    if btn_scan_t1:
        import time
        st.write("---")
        
        with st.status("📡 買い広域レーダー稼働中...", expanded=True) as status:
            t_start_total = time.time()
            
            # === Phase 1: 価格フィルタ ===
            st.write("#### 🔄 [Phase 1/2] 価格帯フィルタ一括足切り")
            p1_msg = st.empty()
            p1_msg.info("⏳ J-Quantsサーバーから全銘柄の最新価格データを一括取得中...")
            t_start_p1 = time.time()
            
            all_codes = []
            try:
                # 🎯 修正：辞書(dict)仕様に合わせた抽出ロジック
                prices_map = get_all_latest_prices_bulk()
                if prices_map:
                    for c_code, c_price in prices_map.items():
                        # 指定価格帯で足切り
                        if float(t1_p_min) <= float(c_price) <= float(t1_p_max):
                            all_codes.append(str(c_code))
                else:
                    p1_msg.error("❌ J-Quantsからの株価取得に失敗しました（APIペナルティ中）。数分待ってから再度お試しください。")
                    st.stop()
            except Exception as e:
                p1_msg.error(f"❌ 株価取得エラー: {e}")
                st.stop()
                
            p_filtered_codes = [str(code).replace('.0', '').strip()[:4] for code in all_codes]
            time_p1 = time.time() - t_start_p1
            p1_msg.success(f"✅ Phase 1 完了: 適合 {len(p_filtered_codes)} 銘柄 ➔ Phase 2 へパスしました。")
            
            # === Phase 2: ファンダ解析（完全直列・防弾スロットル版） ===
            st.write("#### 🔄 [Phase 2/2] ファンダメンタルズ直列解析")
            p2_msg = st.empty()
            p2_bar = st.progress(0)
            
            t_start_p2 = time.time()
            hit_codes_s = []
            hit_codes_a = []

            total_p2 = len(p_filtered_codes)
            processed_p2 = 0
            
            if total_p2 > 0:
                for idx, code in enumerate(p_filtered_codes):
                    processed_p2 += 1
                    
                    # 5件に1回更新（UI負荷軽減）
                    if processed_p2 % 5 == 0 or processed_p2 == total_p2:
                        progress_pct = int((processed_p2 / total_p2) * 100)
                        p2_bar.progress(processed_p2 / total_p2)
                        p2_msg.info(f"📡 索敵中: {processed_p2} / {total_p2} 銘柄完了... ({progress_pct}%) [標的: {code}]")

                    try:
                        df_fins = get_historical_statements(code)
                        if df_fins is not None and not df_fins.empty:
                            is_hit, rank = analyze_fundamental_momentum(
                                df_fins, mode="buy", sales_req=float(t1_sales_r), ord_req=float(t1_ord_r)
                            )
                            if is_hit:
                                if "S級" in rank:
                                    hit_codes_s.append(str(code))
                                else:
                                    hit_codes_a.append(str(code))
                    except Exception:
                        pass
                
                time_p2 = time.time() - t_start_p2
                p2_bar.progress(1.0)
                p2_msg.success(f"✅ Phase 2 完了: すべての解析が終了しました。")
                
                all_hits = hit_codes_s + hit_codes_a
                time_total = time.time() - t_start_total
                status.update(label=f"🎯 スキャン完了！ 計 {len(all_hits)} 銘柄を捕捉しました。 (総計: {time_total:.2f}秒)", state="complete", expanded=False)
                
                st.divider()
                st.write("### 🎯 スキャン結果")
                st.write(f"**【S級】条件完全突破銘柄:** {len(hit_codes_s)} 件")
                if hit_codes_s:
                    st.code(", ".join(hit_codes_s))
                else:
                    st.info("S級条件に合致する銘柄はありませんでした。")
                    
                st.write(f"**【A級】条件突破銘柄:** {len(hit_codes_a)} 件")
                if hit_codes_a:
                    st.code(", ".join(hit_codes_a))
                else:
                    st.info("A級条件に合致する銘柄はありませんでした。")
                    
                st.caption(f"⏱️ **処理時間** ➔ [1. 価格足切り]: `{time_p1:.2f}秒` | [2. ファンダ解析]: `{time_p2:.2f}秒` | 🟢 **[総計]**: `{time_total:.2f}秒`")
                st.markdown("#### 📋 TAB3 (詳細分析) 貼り付け用コード")
                st.info("以下のコードをコピーし、次フェーズの分析へ移行してください。")
                st.code(", ".join(all_hits) if all_hits else "条件に合致する銘柄はありませんでした。", language="text")

            else:
                p2_msg.warning("⚠️ Phase 1 を通過した銘柄が0件のため、解析をスキップします。")
                status.update(label="⚠️ スキャン中断：対象銘柄なし", state="complete")

    # ==========================================
    # 🛠️ 【参謀用】ファンダメンタルズ生レスポンスX線検査装置
    # ==========================================
    st.divider()
    with st.expander("🛠️ 【参謀用】J-Quants V2 生レスポンス直視デバッグ", expanded=False):
        test_code = st.text_input("透視する銘柄コード (例: 7203)", "7203", key="debug_code_xray")
        if st.button("X線検査を実行", key="debug_btn_xray"):
            api_code = str(test_code) if len(str(test_code)) >= 5 else str(test_code) + "0"
            url = f"{BASE_URL}/fins/summary?code={api_code}"
            st.write(f"📡 接続先URL: `{url}`")
            
            try:
                r = api_session.get(url, timeout=10.0)
                st.write(f"📊 HTTPステータスコード: `{r.status_code}`")
                if r.status_code == 200:
                    raw_json = r.json()
                    st.success("✅ HTTP 200 応答成功！")
                    st.json(raw_json)
                else:
                    st.error(f"❌ サーバーから拒絶されました (HTTP {r.status_code})")
                    st.text(r.text)
            except Exception as e:
                st.error(f"🚨 通信例外が発生しました: {str(e)}")

# ==========================================
# 📉 TAB2: 売り銘柄広域スキャン (Growth / Standard / Prime)
# ==========================================
with tab2:
    st.markdown('### 📉 売り（空売り）銘柄広域スキャン', unsafe_allow_html=True)
    st.caption("※直近2四半期の売上・利益の成長鈍化・衰退をベースに、空売り候補（S級・A級）を広域索敵します。")
    
    # 1. フォームの定義（TAB2専用のKeyを設定）
    with st.form("tab2_sell_scan_form", clear_on_submit=False):
        col2_1, col2_2, col2_3 = st.columns(3)
        # TAB2独自の期間フィルタ（デフォルト6ヶ月）
        t2_period = col2_1.selectbox("期間フィルタ (安値判定基準)", ["6か月", "3か月"], index=0)
        
        col2_4, col2_5, col2_6 = st.columns(3)
        t2_p_min = col2_4.number_input("価格下限 (円)", value=100, step=100, key="t2_p_min")
        t2_p_max = col2_5.number_input("価格上限 (円)", value=10000, step=100, key="t2_p_max")
        
        st.markdown("**(固定スキャン条件: 直近2四半期連続で以下の衰退条件に合致)** \n"
                    "・売上: 前四半期比 `5%`未満  \n"
                    "・営業利益: 前四半期比 `10%`未満  \n"
                    "・経常利益: 前四半期比 `5%`未満  \n"
                    "・一株利益: 前四半期比 `10%`未満  \n"
                    "*(※ 全てマイナス成長（赤字転落・大幅減益）の場合は S級💀)*")
        
        btn_scan_t2 = st.form_submit_button("🚀 売り銘柄 スキャン実行", use_container_width=True, type="primary")

    # 2. スキャン実行処理（完全直列・防弾仕様）
    if btn_scan_t2:
        import time
        st.write("---")
        
        with st.status("📡 売り広域レーダー稼働中...", expanded=True) as status:
            t_start_total = time.time()
            
            # === Phase 1: 価格フィルタ ===
            st.write("#### 🔄 [Phase 1/2] 価格帯フィルタ一括足切り")
            p1_msg_t2 = st.empty()
            p1_msg_t2.info("⏳ J-Quantsサーバーから全銘柄の最新価格データを一括取得中...")
            t_start_p1 = time.time()
            
            all_codes = []
            try:
                # 🎯 修正：辞書(dict)仕様に合わせた抽出ロジック
                prices_map = get_all_latest_prices_bulk()
                if prices_map:
                    for c_code, c_price in prices_map.items():
                        # 指定価格帯で足切り
                        if float(t2_p_min) <= float(c_price) <= float(t2_p_max):
                            all_codes.append(str(c_code))
                else:
                    p1_msg_t2.error("❌ J-Quantsからの株価取得に失敗しました（APIペナルティ中）。数分待ってから再度お試しください。")
                    st.stop()
            except Exception as e:
                p1_msg_t2.error(f"❌ 株価取得エラー: {e}")
                st.stop()
                
            p_filtered_codes = [str(code).replace('.0', '').strip()[:4] for code in all_codes]
            time_p1 = time.time() - t_start_p1
            p1_msg_t2.success(f"✅ Phase 1 完了: 適合 {len(p_filtered_codes)} 銘柄 ➔ Phase 2 へパスしました。")
            
            # === Phase 2: ファンダ解析（完全直列・防弾スロットル版） ===
            st.write("#### 🔄 [Phase 2/2] ファンダメンタルズ直列解析")
            p2_msg_t2 = st.empty()
            p2_bar_t2 = st.progress(0)
            
            t_start_p2 = time.time()
            hit_codes_s = []
            hit_codes_a = []

            total_p2 = len(p_filtered_codes)
            processed_p2 = 0
            
            if total_p2 > 0:
                for idx, code in enumerate(p_filtered_codes):
                    processed_p2 += 1
                    
                    # 5件に1回更新（UI負荷軽減）
                    if processed_p2 % 5 == 0 or processed_p2 == total_p2:
                        progress_pct = int((processed_p2 / total_p2) * 100)
                        p2_bar_t2.progress(processed_p2 / total_p2)
                        p2_msg_t2.info(f"📡 索敵中: {processed_p2} / {total_p2} 銘柄完了... ({progress_pct}%) [標的: {code}]")

                    try:
                        df_fins = get_historical_statements(code)
                        if df_fins is not None and not df_fins.empty:
                            # 🎯 TAB2専用: mode="sell" で呼び出し（閾値は関数内でハードコードされているため引数不要）
                            is_hit, rank = analyze_fundamental_momentum(
                                df_fins, mode="sell"
                            )
                            if is_hit:
                                if "S級" in rank:
                                    hit_codes_s.append(str(code))
                                else:
                                    hit_codes_a.append(str(code))
                    except Exception:
                        pass
                
                time_p2 = time.time() - t_start_p2
                p2_bar_t2.progress(1.0)
                p2_msg_t2.success(f"✅ Phase 2 完了: すべての解析が終了しました。")
                
                all_hits = hit_codes_s + hit_codes_a
                time_total = time.time() - t_start_total
                status.update(label=f"🎯 スキャン完了！ 計 {len(all_hits)} 銘柄を捕捉しました。 (総計: {time_total:.2f}秒)", state="complete", expanded=False)
                
                st.divider()
                st.write("### 🎯 スキャン結果")
                st.write(f"**【S級】条件完全突破銘柄:** {len(hit_codes_s)} 件")
                if hit_codes_s:
                    st.code(", ".join(hit_codes_s))
                else:
                    st.info("S級条件に合致する銘柄はありませんでした。")
                    
                st.write(f"**【A級】条件突破銘柄:** {len(hit_codes_a)} 件")
                if hit_codes_a:
                    st.code(", ".join(hit_codes_a))
                else:
                    st.info("A級条件に合致する銘柄はありませんでした。")
                    
                st.caption(f"⏱️ **処理時間** ➔ [1. 価格足切り]: `{time_p1:.2f}秒` | [2. ファンダ解析]: `{time_p2:.2f}秒` | 🟢 **[総計]**: `{time_total:.2f}秒`")
                st.markdown("#### 📋 TAB3 (詳細分析) 貼り付け用コード")
                st.info("以下のコードをコピーし、次フェーズの分析へ移行してください。")
                st.code(", ".join(all_hits) if all_hits else "条件に合致する銘柄はありませんでした。", language="text")

            else:
                p2_msg_t2.warning("⚠️ Phase 1 を通過した銘柄が0件のため、解析をスキップします。")
                status.update(label="⚠️ スキャン中断：対象銘柄なし", state="complete")

    # ==========================================
    # 🛠️ 【参謀用】ファンダメンタルズ生レスポンスX線検査装置 (TAB2専用Key版)
    # ==========================================
    st.divider()
    with st.expander("🛠️ 【参謀用】J-Quants V2 生レスポンス直視デバッグ (TAB2)", expanded=False):
        test_code_t2 = st.text_input("透視する銘柄コード (例: 7203)", "7203", key="debug_code_xray_t2")
        if st.button("X線検査を実行", key="debug_btn_xray_t2"):
            api_code = str(test_code_t2) if len(str(test_code_t2)) >= 5 else str(test_code_t2) + "0"
            url = f"{BASE_URL}/fins/summary?code={api_code}"
            st.write(f"📡 接続先URL: `{url}`")
            
            try:
                r = api_session.get(url, timeout=10.0)
                st.write(f"📊 HTTPステータスコード: `{r.status_code}`")
                if r.status_code == 200:
                    raw_json = r.json()
                    st.success("✅ HTTP 200 応答成功！")
                    st.json(raw_json)
                else:
                    st.error(f"❌ サーバーから拒絶されました (HTTP {r.status_code})")
                    st.text(r.text)
            except Exception as e:
                st.error(f"🚨 通信例外が発生しました: {str(e)}")

# ==========================================
# 🧠 TAB3：精密スキャンエンジン＆詳細分析（真の爆速・一括ロード版）
# ==========================================

def analyze_formation_history(df):
    """過去3ヶ月分のデータから、買い/空売りフォーメーションの出現箇所を探知する"""
    import pandas as pd
    buy_signals = []
    sell_signals = []
    
    if df is None or len(df) < 4:
        return buy_signals, sell_signals
        
    cols = [str(c).lower() for c in df.columns]
    def get_c(*names):
        for n in names:
            if n.lower() in cols: return df.columns[cols.index(n.lower())]
        return None

    c_h, c_l, c_c = get_c('high', 'h'), get_c('low', 'l'), get_c('close', 'adjc', 'c')
    c_d = get_c('date', 'd')
    if not all([c_h, c_l, c_c, c_d]): return [], []

    # 🚨 ルール②判定用に18日移動平均線を算出
    df_calc = df.copy()
    if 'MA18' not in df_calc.columns:
        df_calc['MA18'] = df_calc[c_c].rolling(window=18).mean()

    scan_len = min(len(df_calc), 65)
    df_recent = df_calc.tail(scan_len).reset_index(drop=True)
    
    for i in range(3, len(df_recent)):
        try:
            m3_h, m3_l = float(df_recent.loc[i-3, c_h]), float(df_recent.loc[i-3, c_l])
            m2_h, m2_l, m2_c = float(df_recent.loc[i-2, c_h]), float(df_recent.loc[i-2, c_l]), float(df_recent.loc[i-2, c_c])
            m1_h, m1_l, m1_c = float(df_recent.loc[i-1, c_h]), float(df_recent.loc[i-1, c_l]), float(df_recent.loc[i-1, c_c])
            q0_h, q0_l, q0_c = float(df_recent.loc[i, c_h]), float(df_recent.loc[i, c_l]), float(df_recent.loc[i, c_c])
            
            ma18_m2 = float(df_recent.loc[i-2, 'MA18'])
            ma18_m1 = float(df_recent.loc[i-1, 'MA18'])
            ma18_q0 = float(df_recent.loc[i, 'MA18'])
            curr_date = df_recent.loc[i, c_d]

            buy_hit = False
            sell_hit = False

            # --- ルール①（3日間反転陣形） ---
            if (m2_c < m3_l) and (m1_c > m2_h) and (q0_c > m1_c):
                buy_hit = True
            if (m2_c > m3_h) and (m1_c < m2_l) and (q0_c < m1_c):
                sell_hit = True

            # --- ルール②（18日線 支持/拒絶） ---
            # ※チャートがマーカーだらけになるのを防ぐため、2日前は条件外だった「初動」のみチャートに打つ
            if pd.notna(ma18_q0) and pd.notna(ma18_m1) and pd.notna(ma18_m2):
                if (q0_l > ma18_q0) and (m1_l > ma18_m1) and (m2_l <= ma18_m2):
                    buy_hit = True
                if (q0_h < ma18_q0) and (m1_h < ma18_m1) and (m2_h >= ma18_m2):
                    sell_hit = True

            if buy_hit: buy_signals.append(curr_date)
            if sell_hit: sell_signals.append(curr_date)
        except Exception:
            pass
            
    return list(dict.fromkeys(buy_signals)), list(dict.fromkeys(sell_signals))

def fetch_fundamental_history_local(code, local_db):
    """【通信完全ゼロ】ローカルDBから四半期推移・通年業績を抽出・計算する（防弾仕様）"""
    import pandas as pd
    try:
        if local_db is None or len(local_db) == 0: return None

        str_code = str(code).strip()[:4]
        c_code_col = 'Code' if 'Code' in local_db.columns else ('code' if 'code' in local_db.columns else None)
        if not c_code_col: return None

        mask = local_db[c_code_col].astype(str).str.startswith(str_code)
        df_target = local_db[mask].copy().reset_index(drop=True)

        if len(df_target) == 0: return None

        cols = [str(c).lower() for c in df_target.columns]
        def find_c(*names):
            for n in names:
                if n.lower() in cols: return df_target.columns[cols.index(n.lower())]
            return None

        c_sales = find_c('Sales', 'NetSales', 'net_sales')
        c_op = find_c('OP', 'OperatingProfit', 'operating_profit')
        c_ord = find_c('OdP', 'OrdinaryProfit', 'ordinary_profit')
        c_eps = find_c('EPS', 'EarningsPerShare', 'eps')
        c_profit = find_c('NP', 'Profit', 'netincome')
        c_type = find_c('CurPerType', 'TypeOfCurrentPeriod')
        c_date = find_c('DiscDate', 'DisclosedDate', 'Date')

        def to_flt(v):
            try: return float(str(v).replace(',', '').strip())
            except: return 0.0

        actual_mask = df_target[c_sales].apply(to_flt) > 0 if c_sales else pd.Series([True]*len(df_target))
        actual_df = df_target[actual_mask].copy().reset_index(drop=True)

        if len(actual_df) < 2: return None

        std_df = actual_df.copy()
        for i in range(1, len(actual_df)):
            curr_type = str(actual_df[c_type].iloc[i]) if c_type else ""
            c_s = to_flt(actual_df[c_sales].iloc[i]) if c_sales else 0.0
            p_s = to_flt(actual_df[c_sales].iloc[i-1]) if c_sales else 0.0
            is_q1 = ('1Q' in curr_type or 'Q1' in curr_type) or (c_s < p_s and p_s > 0)

            if not is_q1:
                for col in [c_sales, c_op, c_ord, c_eps, c_profit]:
                    if col and col in std_df.columns:
                        try: std_df.iat[i, std_df.columns.get_loc(col)] = to_flt(actual_df[col].iloc[i]) - to_flt(actual_df[col].iloc[i-1])
                        except: pass

        def calc_yoy(c, p):
            if p <= 0: return 999.0 if c > 0 else -999.0
            return ((c - p) / abs(p)) * 100.0

        def get_v(row, primary, fallback=None):
            v = to_flt(row.get(primary, 0.0)) if primary else 0.0
            if v == 0.0 and fallback and fallback in row.index:
                v = to_flt(row.get(fallback, 0.0))
            return v

        results = []
        for i in range(1, 5):
            if len(std_df) < i + 4:
                if len(std_df) >= i:
                    q_cur = std_df.iloc[-i]
                    dis_date = str(q_cur.get(c_date, '-')) if c_date else '-'
                    results.append({"期間": f"直近 Q{i}", "開示日": dis_date, "売上(%)": "-", "営業益(%)": "-", "経常益(%)": "-", "EPS(%)": "-"})
                continue
                
            q_cur = std_df.iloc[-i]
            q_prv = std_df.iloc[-(i+4)]
            dis_date = str(q_cur.get(c_date, '-')) if c_date else '-'
            results.append({
                "期間": f"直近 Q{i}", "開示日": dis_date,
                "売上(%)": calc_yoy(get_v(q_cur, c_sales), get_v(q_prv, c_sales)),
                "営業益(%)": calc_yoy(get_v(q_cur, c_op), get_v(q_prv, c_op)),
                "経常益(%)": calc_yoy(get_v(q_cur, c_ord), get_v(q_prv, c_ord)),
                "EPS(%)": calc_yoy(get_v(q_cur, c_eps, c_profit), get_v(q_prv, c_eps, c_profit)),
            })

        if len(std_df) >= 8:
            y_cur = std_df.iloc[-4:].apply(pd.to_numeric, errors='coerce').sum(numeric_only=True)
            y_prv = std_df.iloc[-8:-4].apply(pd.to_numeric, errors='coerce').sum(numeric_only=True)
            results.append({
                "期間": "🌟 通年(直近1年)", "開示日": "-",
                "売上(%)": calc_yoy(get_v(y_cur, c_sales), get_v(y_prv, c_sales)),
                "営業益(%)": calc_yoy(get_v(y_cur, c_op), get_v(y_prv, c_op)),
                "経常益(%)": calc_yoy(get_v(y_cur, c_ord), get_v(y_prv, c_ord)),
                "EPS(%)": calc_yoy(get_v(y_cur, c_eps, c_profit), get_v(y_prv, c_eps, c_profit)),
            })
        else:
            results.append({"期間": "🌟 通年(直近1年)", "開示日": "-", "売上(%)": "-", "営業益(%)": "-", "経常益(%)": "-", "EPS(%)": "-"})

        return pd.DataFrame(results[::-1])
    except:
        return None

def analyze_tab3_precision_scope(df, mode="buy", nikkei_div_rate=0.0):
    """3日間フォーメーション＆18日線ブレイク判定エンジン"""
    try:
        if df is None or len(df) < 4: return False, ""

        cols = [str(c).lower() for c in df.columns]
        def get_col(*names):
            for n in names:
                if n.lower() in cols: return df.columns[cols.index(n.lower())]
            return None

        c_h, c_l, c_c = get_col('high', 'h'), get_col('low', 'l'), get_col('close', 'adjc', 'c')
        if not all([c_h, c_l, c_c]): return False, ""

        # 🚨 ルール②判定用に18日移動平均線を算出
        df_calc = df.copy()
        if 'MA18' not in df_calc.columns:
            df_calc['MA18'] = df_calc[c_c].rolling(window=18).mean()

        m3 = df_calc.iloc[-4]; m2 = df_calc.iloc[-3]; m1 = df_calc.iloc[-2]; q0 = df_calc.iloc[-1]

        def safe_flt(val):
            try: return float(val)
            except: return 0.0

        m3_h, m3_l = safe_flt(m3[c_h]), safe_flt(m3[c_l])
        m2_h, m2_l, m2_c = safe_flt(m2[c_h]), safe_flt(m2[c_l]), safe_flt(m2[c_c])
        m1_h, m1_l, m1_c = safe_flt(m1[c_h]), safe_flt(m1[c_l]), safe_flt(m1[c_c])
        q0_h, q0_l, q0_c = safe_flt(q0[c_h]), safe_flt(q0[c_l]), safe_flt(q0[c_c])
        
        ma18_q0 = safe_flt(q0['MA18'])
        ma18_m1 = safe_flt(m1['MA18'])

        hit_msgs = []
        is_hit = False

        if mode == "buy":
            # ルール①：反転上昇陣形
            if (m2_c < m3_l) and (m1_c > m2_h) and (q0_c > m1_c):
                is_hit = True
                hit_msgs.append("S級🎯【反転上昇陣形①】")
            
            # ルール②：18日線支持
            if (ma18_q0 > 0) and (q0_l > ma18_q0) and (m1_l > ma18_m1):
                is_hit = True
                trig_p = max(q0_h, m1_h)
                hit_msgs.append(f"A級🎯【18日線支持②】目標買値:{trig_p:,.0f}円")

            if is_hit:
                return True, " ＋ ".join(hit_msgs)
            return False, ""

        elif mode == "sell":
            if nikkei_div_rate >= 0.0: return False, ""
            
            # ルール①：奈落崩壊陣形
            if (m2_c > m3_h) and (m1_c < m2_l) and (q0_c < m1_c):
                is_hit = True
                hit_msgs.append("S級💀【奈落崩壊陣形①】")
            
            # ルール②：18日線拒絶
            if (ma18_q0 > 0) and (q0_h < ma18_q0) and (m1_h < ma18_m1):
                is_hit = True
                trig_p = min(q0_l, m1_l)
                hit_msgs.append(f"A級💀【18日線拒絶②】目標売値:{trig_p:,.0f}円")

            if is_hit:
                return True, " ＋ ".join(hit_msgs)
            return False, ""
            
    except Exception:
        return False, ""

# ==========================================
# 🎯 TAB3 UI構築 ＆ スキャン実行ブロック
# ==========================================
with tab3:
    st.markdown("### 🎯 【照準】精密スコープ＆詳細分析")
    st.info("TAB1・TAB2で抽出されたファンダ強者に対し、陣形の判定および詳細な個別チャート・業績推移を完全ローカルデータから出力します。")

    tab3_mode = st.radio("スキャンモードを選択してください", ["モード1：買い（反転上昇）", "モード2：空売り（奈落崩壊）"], horizontal=True)
    scan_mode = "buy" if "買い" in tab3_mode else "sell"

    # 🔗 要件7: TAB1/2のスキャン結果自動連携 ＆ 要件6: モード別銘柄コード保持
    default_codes = []
    for t_res in [st.session_state.get('tab1_scan_results', []), st.session_state.get('tab2_scan_results', [])]:
        if t_res:
            for r in t_res:
                if isinstance(r, dict):
                    c = r.get('Code') or r.get('code')
                    if c: default_codes.append(str(c)[:4])
                else:
                    default_codes.append(str(r)[:4])
    
    default_codes_str = ",".join(list(dict.fromkeys(default_codes)))

    # セッションステート初期化
    if "tab3_codes_buy" not in st.session_state:
        st.session_state["tab3_codes_buy"] = default_codes_str
    if "tab3_codes_sell" not in st.session_state:
        st.session_state["tab3_codes_sell"] = default_codes_str
    if "tab3_last_default" not in st.session_state:
        st.session_state["tab3_last_default"] = default_codes_str

    # TAB1/2で新たな結果が出た場合のみバッファを強制上書き
    if st.session_state["tab3_last_default"] != default_codes_str:
        st.session_state["tab3_codes_buy"] = default_codes_str
        st.session_state["tab3_codes_sell"] = default_codes_str
        st.session_state["tab3_last_default"] = default_codes_str

    text_key = f"tab3_codes_{scan_mode}"

    st.markdown("#### 📡 分析対象銘柄（最大30件まで強制表示）")
    target_codes_input = st.text_area(
        "銘柄コード（カンマ区切り）。TAB1・TAB2の突破銘柄が自動入力されています。",
        key=text_key,
        height=100
    )

    if st.button("🚀 TAB3 精密スキャン＆一斉分析", key="btn_scan_tab3"):
        if not target_codes_input.strip():
            st.warning("⚠️ 銘柄コードが入力されていません。")
        else:
            p_bar = st.progress(0, text="🚀 システム初期化・全軍データロード中...")

            raw_codes = [c.strip() for c in target_codes_input.split(",") if c.strip()]
            target_codes = []
            for c in raw_codes:
                try: target_codes.append(int(c[:4]))
                except: pass
            target_codes = list(dict.fromkeys(target_codes))
            target_str_codes = [str(c) for c in target_codes]

            st.write(f"📡 実行対象: {len(target_codes)} 銘柄を一斉解析中...")

            # 💡 【真理のアーキテクチャ1】ループに入る前に全軍データを「1回だけ」一括ロードする
            c_key = get_cache_key() if 'get_cache_key' in globals() else cache_key
            raw_all_data = get_hist_data_cached(c_key)

            if raw_all_data is None or raw_all_data.empty:
                st.error("⚠️ 全軍データ（キャッシュ）が見つかりません。先にTAB1かTAB2でデータ取得（索敵）を実行してください。")
            else:
                # 💡 【真理のアーキテクチャ2】一括ロードしたデータから、対象銘柄だけを抽出
                c_code_raw = 'Code' if 'Code' in raw_all_data.columns else ('code' if 'code' in raw_all_data.columns else None)
                if not c_code_raw:
                    st.error("⚠️ キャッシュデータに銘柄コード列が見つかりません。")
                else:
                    mask = raw_all_data[c_code_raw].astype(str).str[:4].isin(target_str_codes)
                    df_targets = raw_all_data[mask].copy()

                    current_div_rate = 0.0
                    analyzed_data = {}
                    total_cnt = len(target_codes)
                    completed_cnt = 0

                    # 💡 【真理のアーキテクチャ3】通信もファイル読み込みも無いので、直列で瞬時に終わる
                    for code_str, group in df_targets.groupby(c_code_raw):
                        code_int = int(str(code_str)[:4])
                        completed_cnt += 1
                        p_bar.progress(completed_cnt / total_cnt, text=f"🚀 フェーズ1：インメモリ陣形判定中... ({completed_cnt}/{total_cnt} 完了)")
                        
                        # 直近1年分（約260日）にスライスして処理
                        df = group.tail(260).reset_index(drop=True)
                        if df.empty or len(df) < 4: continue

                        turnover = 0.0
                        try:
                            q0 = df.iloc[-1]
                            v_col = 'Volume' if 'Volume' in df.columns else ('Vo' if 'Vo' in df.columns else None)
                            c_col = 'AdjC' if 'AdjC' in df.columns else ('Close' if 'Close' in df.columns else None)
                            if v_col and c_col: turnover = float(q0[v_col]) * float(q0[c_col])
                        except: pass

                        res_hit = analyze_tab3_precision_scope(df, mode=scan_mode, nikkei_div_rate=current_div_rate)
                        is_hit = res_hit[0] if isinstance(res_hit, tuple) else res_hit
                        rank = res_hit[1] if isinstance(res_hit, tuple) else ("🎯 陣形検知" if is_hit else "")

                        analyzed_data[code_int] = {"df": df, "is_hit": is_hit, "rank": rank, "turnover": turnover}

                    # ==========================================
                    # 📊 最強の30件選出 ＆ フェーズ2（重い分析処理）
                    # ==========================================
                    p_bar.progress(1.0, text="⚙️ データベースをマウント中（フェーズ2準備）...")
                    
                    # 🔗 要件3: 判定結果の高い順で上位から並べる
                    def get_rank_score(r_str):
                        if "S級" in r_str: return 2
                        if "A級" in r_str: return 1
                        return 0
                        
                    sortable_results = [{"code": k, **v} for k, v in analyzed_data.items()]
                    sortable_results.sort(key=lambda x: (x['is_hit'], get_rank_score(x['rank']), x['turnover']), reverse=True)
                    
                    display_targets = sortable_results[:30]

                    name_map = {}
                    try:
                        m_df = load_master()
                        name_map = dict(zip(m_df['Code'].astype(str).str[:4], m_df['CompanyName']))
                    except: pass

                    try: local_fund_db = load_local_fundamentals_db()
                    except: local_fund_db = None
                    
                    for i, data in enumerate(display_targets):
                        p_bar.progress((i + 1) / len(display_targets), text=f"⚙️ フェーズ2：上位30件の詳細分析（ファンダ・シグナル履歴）を実行中... ({i+1}/{len(display_targets)})")
                        code = data['code']
                        df = data['df']
                        b_sigs, s_sigs = analyze_formation_history(df)
                        fund_df = fetch_fundamental_history_local(code, local_fund_db)
                        data['buy_sigs'] = b_sigs
                        data['sell_sigs'] = s_sigs
                        data['fund'] = fund_df

                    p_bar.empty()
                    st.divider()

                    import plotly.graph_objects as go
                    
                    hit_count = sum(1 for d in sortable_results if d["is_hit"])
                    if hit_count > 0:
                        st.success(f"🎯 陣形合致銘柄: {hit_count}件 確認！ （上位最大30件の分析ダッシュボードを表示します）")
                    else:
                        st.error("📉 条件に合致する陣形を形成した銘柄はありませんでした。流動性上位の分析データを表示します。")

                    for data in display_targets:
                        code = data['code']
                        df = data["df"]
                        c_name = name_map.get(str(code)[:4], "名称不明")
                        
                        # 💡 どちらのルールで合致したかを詳細表示（目標価格も自動出力）
                        hit_badge = data["rank"] if data["is_hit"] else "⬜ 待機"
                        st.markdown(f"### 📦 {code} {c_name} | {hit_badge}")
                        
                        q0 = df.iloc[-1]
                        c_o = q0.get('Open', q0.get('AdjO', 0))
                        c_h = q0.get('High', q0.get('AdjH', 0))
                        c_l = q0.get('Low', q0.get('AdjL', 0))
                        c_c = q0.get('Close', q0.get('AdjC', 0))
                        
                        c1, c2, c3, c4 = st.columns(4)
                        c1.metric("始値", f"{c_o:,.1f}円")
                        c2.metric("高値", f"{c_h:,.1f}円")
                        c3.metric("安値", f"{c_l:,.1f}円")
                        c4.metric("終値", f"{c_c:,.1f}円")
                        
                        if len(df) > 0:
                            df_c = df.copy()
                            c_col = 'AdjC' if 'AdjC' in df_c.columns else 'Close'
                            if 'MA18' not in df_c.columns: df_c['MA18'] = df_c[c_col].rolling(18).mean()
                            if 'MA50' not in df_c.columns: df_c['MA50'] = df_c[c_col].rolling(50).mean()
                            
                            fig = go.Figure()
                            date_col = 'Date' if 'Date' in df_c.columns else df_c.columns[0]
                            
                            fig.add_trace(go.Candlestick(
                                x=df_c[date_col], open=df_c.get('AdjO', df_c.get('Open')), 
                                high=df_c.get('AdjH', df_c.get('High')), low=df_c.get('AdjL', df_c.get('Low')), 
                                close=df_c[c_col], name='価格'
                            ))
                            fig.add_trace(go.Scatter(x=df_c[date_col], y=df_c['MA18'], mode='lines', line=dict(color='orange', width=1.5), name='18日線'))
                            fig.add_trace(go.Scatter(x=df_c[date_col], y=df_c['MA50'], mode='lines', line=dict(color='cyan', width=1.5), name='50日線'))
                            
                            # 🔗 要件1 & 2: モードによって表示するシグナルを完全に分離
                            if scan_mode == "buy" and data.get("buy_sigs"):
                                sig_df = df_c[df_c[date_col].isin(data["buy_sigs"])]
                                if not sig_df.empty: fig.add_trace(go.Scatter(x=sig_df[date_col], y=sig_df[c_col] * 0.95, mode='markers', marker=dict(symbol='triangle-up', color='magenta', size=12), name='買陣形'))
                            
                            if scan_mode == "sell" and data.get("sell_sigs"):
                                sig_df = df_c[df_c[date_col].isin(data["sell_sigs"])]
                                if not sig_df.empty: fig.add_trace(go.Scatter(x=sig_df[date_col], y=sig_df[c_col] * 1.05, mode='markers', marker=dict(symbol='triangle-down', color='yellow', size=12), name='空売陣形'))

                            # 🔗 要件5: 1年分のデータを持たせつつ初期表示のフォーカスを直近3ヶ月に
                            x_min = df_c[date_col].iloc[-65] if len(df_c) > 65 else df_c[date_col].iloc[0]
                            x_max = df_c[date_col].iloc[-1]
                            fig.update_layout(
                                height=400, 
                                margin=dict(l=0, r=0, t=30, b=0),
                                xaxis=dict(range=[x_min, x_max], rangeslider=dict(visible=False))
                            )
                            fig.update_yaxes(autorange=True, fixedrange=False)
                            st.plotly_chart(fig, use_container_width=True)

                        # 🔗 要件4: ファンダ情報エラーの防護（落ちないように処理）
                        if data.get("fund") is not None and not data["fund"].empty:
                            st.markdown("##### 📊 業績成長率（四半期・通年）")
                            try:
                                st.dataframe(data["fund"].style.format({
                                    "売上(%)": lambda x: f"{x:.1f}%" if isinstance(x, (int, float)) else x,
                                    "営業益(%)": lambda x: f"{x:.1f}%" if isinstance(x, (int, float)) else x,
                                    "経常益(%)": lambda x: f"{x:.1f}%" if isinstance(x, (int, float)) else x,
                                    "EPS(%)": lambda x: f"{x:.1f}%" if isinstance(x, (int, float)) else x
                                }), use_container_width=True)
                            except Exception:
                                st.dataframe(data["fund"], use_container_width=True)
                        else:
                            st.info("ℹ️ 業績データがローカルDBに存在しない、または計算要件に満たないため表示をスキップしました。")
                            
                        st.divider()

                    results_tab3 = [{"Code": d["code"], "Rank": d["rank"], "Mode": scan_mode} for d in sortable_results if d["is_hit"]]
                    if results_tab3:
                        hit_codes_str = ",".join([str(r["Code"]) for r in results_tab3])
                        st.text_area("📋 最終突破銘柄（コピペ用・全件）", value=hit_codes_str, height=70)
                        
                    st.session_state['tab3_results'] = results_tab3
                    
# ==========================================
# 📁 TAB7: 戦績ダッシュボード (既存のコードをそのまま配置)
# ==========================================
with tab7:
    import datetime as dt_module
    st.markdown('<h3 style="font-size: clamp(14px, 4.5vw, 24px); margin-bottom: 1rem;">📁 事後任務報告 (AAR) & 戦績ダッシュボード</h3>', unsafe_allow_html=True)
    st.caption("※ 記録の編集は下部の『🛠️ 戦績編集コンソール』で行ってください。")
    
    def get_scale_for_code(code):
        api_code = str(code) if len(str(code)) >= 5 else str(code) + "0"
        if not master_df.empty:
            m_row = master_df[master_df['Code'].astype(str) == api_code]
            if not m_row.empty:
                scale_val = str(m_row.iloc[0].get('Scale', ''))
                return "🏢 大型/中型" if any(x in scale_val for x in ["Core30", "Large70", "Mid400"]) else "🚀 小型/新興"
        return "不明"

    if 'aar_df_stable' not in st.session_state:
        df_l = load_db_to_df(WS_AAR, ["決済日", "銘柄", "規模", "戦術", "買値", "売値", "株数", "損益額(円)", "損益(%)", "規律", "敗因/勝因メモ"])
        if not df_l.empty:
            df_l['決済日'] = df_l['決済日'].astype(str)
            df_l['銘柄'] = df_l['銘柄'].astype(str).str.replace(r'\.0$', '', regex=True)
            for c in ['買値', '売値', '株数', '損益額(円)', '損益(%)']:
                if c in df_l.columns:
                    df_l[c] = pd.to_numeric(df_l[c], errors='coerce').fillna(0)
            st.session_state.aar_df_stable = df_l.sort_values(['決済日', '銘柄'], ascending=[False, True]).reset_index(drop=True)
        else:
            st.session_state.aar_df_stable = df_l

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
                    save_aar_db(st.session_state.aar_df_stable)
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
                                # ▼▼▼ 開発参謀パッチ：重複削除（drop_duplicates）を撤廃し、ダブり記録を全容認 ▼▼▼
                                st.session_state.aar_df_stable = pd.concat([st.session_state.aar_df_stable, pd.DataFrame(records)], ignore_index=True).sort_values(['決済日', '銘柄'], ascending=[False, True]).reset_index(drop=True)
                                save_aar_db(st.session_state.aar_df_stable); st.rerun()
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
        
        # ▼▼▼ 開発参謀パッチ：フォーム（防爆障壁）の展開 ▼▼▼
        # エディタをフォームに隔離し、入力中の画面更新とカーソル飛びを完全に防止します
        with st.form(key="aar_editor_form_fixed", clear_on_submit=False):
            working_log_df = st.data_editor(
                st.session_state.aar_df_stable, 
                column_config={
                    "規模": st.column_config.TextColumn("規模", disabled=True),
                    "戦術": st.column_config.SelectboxColumn("戦術", options=["待伏", "強襲", "挟撃", "自動解析", "その他"], required=True),
                    "規律": st.column_config.SelectboxColumn("規律", options=["遵守", "違反", "不明"], required=True),
                    "買値": st.column_config.NumberColumn("買値", format="%d"),
                    "売値": st.column_config.NumberColumn("売値", format="%d"),
                },
                hide_index=True, use_container_width=True, key="aar_editor_maintenance_fixed"
            )

            # 保存ボタンをフォーム専用のボタンに変更
            save_aar_btn = st.form_submit_button("💾 戦績の変更を確定し、Google DBへ同期", use_container_width=True, type="primary")
        # ▲▲▲ フォーム隔離ここまで ▲▲▲

        if save_aar_btn:
            st.session_state.aar_df_stable = working_log_df.copy()
            for col in ["買値", "売値", "株数", "損益額(円)"]:
                st.session_state.aar_df_stable[col] = pd.to_numeric(st.session_state.aar_df_stable[col], errors='coerce').fillna(0).astype(int)
            save_aar_db(st.session_state.aar_df_stable)
            st.success("✅ Google Sheetsへの完全同期・色彩規律の再適用を完了しました。")
            st.rerun()

        # ▼▼▼ 開発参謀パッチ：Google DB連動 一括全削除セクション（防爆ロック付） ▼▼▼
        st.divider()
        st.markdown("##### 🗑️ 全戦績データの一括全削除")
        st.caption("※ Google DB（Google Sheets）上のすべての戦績ログを消去・初期化します。")
        col_del1, col_del2 = st.columns([2, 1])
        confirm_delete = col_del1.checkbox("⚠️ 全データ削除を了解し、防衛ロックを解除する", key="confirm_aar_delete")
        if col_del2.button("🔥 全戦績データを一括削除", use_container_width=True, disabled=not confirm_delete):
            cols = ["決済日", "銘柄", "規模", "戦術", "買値", "売値", "株数", "損益額(円)", "損益(%)", "規律", "敗因/勝因メモ"]
            st.session_state.aar_df_stable = pd.DataFrame(columns=cols)
            save_aar_db(st.session_state.aar_df_stable)
            st.success("💥 全交戦記録を消去し、Google DBを初期化（完全同期）しました。")
            st.rerun()

# ==========================================
# 🚀 最終メモリ解放パージ（OOMクラッシュ回避）
# ==========================================
import gc
gc.collect()
