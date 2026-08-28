import streamlit as st
import requests
import pandas as pd
import os
import re
import json
import datetime
from datetime import datetime, timedelta
from io import BytesIO
import plotly.graph_objects as go
import numpy as np
import concurrent.futures
import streamlit.components.v1 as components
import gc
import pytz
import time 

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

# リスト形式でカンマ区切りで追加します
ALLOWED_PASSWORDS = ["sniper", "senyu001", "senyu002"]

# 【重要】認証スクリプトを一度だけ注入するためのコンテナ
if "js_injected" not in st.session_state:
    st.session_state.js_injected = False

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
                    
                    if (input && input.value.length > 0) {
                        window.loginTriggered = true; 
                        input.blur();
                        
                        const enterEvent = new KeyboardEvent('keydown', {
                            bubbles: true, cancelable: true,
                            key: 'Enter', code: 'Enter', keyCode: 13, which: 13
                        });
                        input.dispatchEvent(enterEvent);
                        
                        const buttons = Array.from(doc.querySelectorAll('button')).filter(b => b.innerText.includes("認証"));
                        if (buttons.length > 0) {
                            setTimeout(() => { buttons[0].click(); }, 100);
                        }
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
        st.session_state.js_injected = True

def check_password():
    inject_auth_script()
    if "password_correct" not in st.session_state:
        st.session_state["password_correct"] = False
        
    if not st.session_state["password_correct"]:
        st.markdown('<h1 style="text-align: center; color: #2e7d32; margin-top: 10vh;">🎯 戦術スコープ『鉄の掟』</h1>', unsafe_allow_html=True)
        col1, col2, col3 = st.columns([1, 2, 1])
        with col2:
            acc_code = st.text_input("Access Code", type="password", label_visibility="collapsed", placeholder="アクセスコード", key="input_access_code")
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
    btn.style.opacity = '0.15'; 
    btn.style.transition = 'opacity 0.3s ease'; 
    btn.onmouseenter = function() { this.style.opacity = '1.0'; };
    btn.onmouseleave = function() { this.style.opacity = '0.15'; };
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

user_id = st.session_state.get("current_user", "UNKNOWN")
st.markdown(f'<h1 style="font-size: clamp(24px, 7vw, 42px); font-weight: 900; border-bottom: 2px solid #2e7d32; padding-bottom: 0.5rem; margin-bottom: 1rem;">🎯 戦術スコープ『鉄の掟』 <span style="font-size: 16px; font-weight: normal; color: #888;">(ID: {user_id[:4]}***)</span></h1>', unsafe_allow_html=True)

# ==========================================
# ☁️ 究極永続化ストレージ（Google Sheets 直結仕様）
# ==========================================
import gspread
from google.oauth2.service_account import Credentials
import pandas as pd
import streamlit as st

SPREADSHEET_ID = "1PZZwhGvUgTHd0ptY2g9AmLloZoB9qZpr-VIx6DrYIdw"

@st.cache_resource
def init_gspread():
    try:
        if "gcp_service_account" not in st.secrets: return None
        scopes = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
        gcp_credentials = dict(st.secrets["gcp_service_account"])
        gcp_credentials["private_key"] = gcp_credentials["private_key"].replace('\\n', '\n')
        creds = Credentials.from_service_account_info(gcp_credentials, scopes=scopes)
        return gspread.authorize(creds)
    except Exception: return None

g_client = init_gspread()

# 🚨 先日の「API通信エラーによるシステム白画面化」を防ぐ完全防弾処理
try:
    db_sheet = g_client.open_by_key(SPREADSHEET_ID) if g_client else None
except Exception as e:
    print(f"Google Sheets接続エラー（システムは継続稼働）: {e}")
    db_sheet = None

def get_or_create_worksheet(sheet_name):
    if not db_sheet: return None
    try: return db_sheet.worksheet(sheet_name)
    except gspread.exceptions.WorksheetNotFound:
        try: return db_sheet.add_worksheet(title=sheet_name, rows="1000", cols="20")
        except: return None

# 🚨 マルチテナント（戦友分離）の核心：認証されたアクセスコードをシート名に強制バインド
_active_user = st.session_state.get("current_user", "Guest")
WS_AAR = f"交戦DB_{_active_user}"

def save_aar_db(df):
    # ユーザー固有のタブ名（WS_AAR）に保存。他人のタブは絶対に書き換わらない。
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
        except: pass

def load_db_to_df(sheet_name, default_cols):
    # 🚨 動的シート名の強制補正処理
    # UI側が誤って '交戦DB' などの固定文字で呼び出してきた場合でも、ユーザー固有の名前に強制変換する
    _uid = st.session_state.get("current_user", "Guest")
    if f"_{_uid}" not in sheet_name:
        if "_" in sheet_name:
            base = sheet_name.split("_")[0]
            target_sheet_name = f"{base}_{_uid}"
        else:
            target_sheet_name = f"{sheet_name}_{_uid}"
    else:
        target_sheet_name = sheet_name

    ws = get_or_create_worksheet(target_sheet_name)
    if ws:
        try:
            data = ws.get_all_records()
            if data: return pd.DataFrame(data)
        except: pass
    return pd.DataFrame(columns=default_cols)

# ==========================================
# 🚨 API設定・通信セッション
# ==========================================
API_KEY = st.secrets.get("JQUANTS_API_KEY", "").strip()
BASE_URL = "https://api.jquants.com/v2"

if "api_session" not in st.session_state:
    session = requests.Session()
    session.headers.update({"x-api-key": API_KEY})
    retry_strategy = Retry(total=3, backoff_factor=0.5, status_forcelist=[500, 502, 503, 504])
    adapter = HTTPAdapter(pool_connections=20, pool_maxsize=20, max_retries=retry_strategy)
    session.mount("https://", adapter)
    st.session_state.api_session = session

api_session = st.session_state.api_session

# ==========================================
# 🌪️ マクロ気象レーダー（日経平均）
# ==========================================
@st.cache_data(ttl=600, show_spinner=False)
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
                                    val = jq_latest.get("Close") or jq_latest.get("C") or jq_latest.get("AdjC") or jq_latest.get("c")
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
                    except: pass

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
    except: pass
    return None

def render_macro_board():
    data = get_macro_weather()
    if data and "nikkei" in data:
        ni = data["nikkei"]
        df = ni["df"].copy()
        
        if 'Date' not in df.columns:
            df = df.reset_index()
            if 'index' in df.columns and 'Date' not in df.columns:
                df.rename(columns={'index': 'Date'}, inplace=True)
        if pd.api.types.is_datetime64_any_dtype(df['Date']):
            df['Date'] = df['Date'].dt.tz_localize(None)

        close_col = next((c for c in ['AdjC', 'Close', 'close', 'Adj Close', 'C'] if c in df.columns), None)
        if not close_col: return

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
            fig = go.Figure()
            fig.add_trace(go.Scatter(x=df['Date'], y=df[close_col], name='日経平均', mode='lines', line=dict(color='#FFD700', width=2), hovertemplate='日経平均: ¥%{y:,.0f}<extra></extra>'))
            fig.add_trace(go.Scatter(x=df['Date'], y=df['MA18'], name='18日線', mode='lines', line=dict(color='#26a69a', width=1.5, dash='dot'), hovertemplate='18日線: ¥%{y:,.0f}<extra></extra>'))
            fig.add_trace(go.Scatter(x=df['Date'], y=df['MA50'], name='50日線', mode='lines', line=dict(color='#ff9800', width=1.5, dash='dash'), hovertemplate='50日線: ¥%{y:,.0f}<extra></extra>'))
            y_min, y_max = df[close_col].min(), df[close_col].max()
            fig.update_layout(
                height=220, margin=dict(l=0, r=40, t=15, b=10), xaxis_rangeslider_visible=False, 
                paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)', showlegend=False, hovermode="x unified", 
                yaxis=dict(side="right", tickformat=",.0f", gridcolor='rgba(255,255,255,0.05)', autorange=True, range=[y_min * 0.98, y_max * 1.05], fixedrange=True), 
                xaxis=dict(type='date', tickformat='%m/%d', gridcolor='rgba(255,255,255,0.05)', range=[df['Date'].min(), df['Date'].max() + pd.Timedelta(hours=24)], fixedrange=True)
            )
            st.plotly_chart(fig, use_container_width=True, config={'displayModeBar': False, 'staticPlot': False})
            
        st.markdown("<div style='margin-bottom: 1.5rem;'></div>", unsafe_allow_html=True)

# ==========================================
# ⚡ 全銘柄現在値・一括取得エンジン（完全ローカルDB参照版）
# ==========================================
@st.cache_data(ttl=3600, show_spinner=False)
def get_all_latest_prices_bulk():
    """API通信を物理遮断。ローカル株価DB（prices_db.pkl.gz / .pkl）から最新営業日の株価を一括抽出する"""
    import os
    import pickle
    import gzip
    
    db_path_gz = os.path.join(os.path.dirname(__file__), "prices_db.pkl.gz")
    db_path_raw = os.path.join(os.path.dirname(__file__), "prices_db.pkl")
    
    prices_db = None
    try:
        if os.path.exists(db_path_gz):
            with gzip.open(db_path_gz, "rb") as f:
                prices_db = pickle.load(f)
        elif os.path.exists(db_path_raw):
            with open(db_path_raw, "rb") as f:
                prices_db = pickle.load(f)
    except Exception:
        pass
        
    if not prices_db:
        return {}
        
    # 記録されている最新営業日を特定
    latest_date = sorted(prices_db.keys())[-1]
    
    prices_map = {}
    for r in prices_db[latest_date]:
        code_4digit = str(r.get("Code", "")).replace(".0", "")[:4]
        # APIのキー名揺れ（AdjustmentClose, AdjC, Close）を吸収
        val = r.get("AdjustmentClose") or r.get("AdjC") or r.get("Close") or r.get("C")
        
        if val is not None and str(val).strip() != "":
            try:
                prices_map[code_4digit] = float(val)
            except Exception:
                pass
                
    return prices_map

@st.cache_resource(ttl=3600*24)
def load_local_fundamentals_db():
    import pickle, gzip
    db_path = os.path.join(os.path.dirname(__file__), "fundamentals_db.pkl.gz")
    if os.path.exists(db_path):
        with gzip.open(db_path, "rb") as f: return pickle.load(f)
    return {}

def get_historical_statements(code):
    db = load_local_fundamentals_db()
    if not db: return None
    api_code = str(code) if len(str(code)) >= 5 else str(code) + "0"
    return db.get(api_code, None)

def get_all_market_caps_bulk():
    mcap_map = {}
    try:
        prices = get_all_latest_prices_bulk()
        fund_db = load_local_fundamentals_db()
        if prices and fund_db:
            for code, p in prices.items():
                api_code = str(code) if len(str(code)) >= 5 else str(code) + "0"
                df = fund_db.get(api_code)
                if df is not None and not df.empty:
                    shares = 0.0
                    share_cols = ['ShOutFY', 'AvgSh', 'NumberOfIssuedAndOutstandingSharesAtTheEndOfPeriod']
                    for col in share_cols:
                        actual_col = next((c for c in df.columns if str(c).lower() == col.lower()), None)
                        if actual_col:
                            val = df.iloc[-1][actual_col]
                            if pd.notna(val) and float(val) > 0:
                                shares = float(val); break
                    if shares > 0: mcap_map[str(code)] = (float(p) * shares) / 100000000.0
    except: pass
    return mcap_map

# ==========================================
# 🛠️ 売買代金フィルター用 実体エンジン（完全ローカル完結版）
# ==========================================
def get_all_volumes_bulk():
    """ローカルの株価DB(prices_db.pkl.gz / .pkl)から最新日の売買代金(億円)を抽出（API通信一切なし）"""
    import os
    import pickle
    import gzip
    
    vol_map = {}
    db_path_gz = os.path.join(os.path.dirname(__file__), "prices_db.pkl.gz")
    db_path_raw = os.path.join(os.path.dirname(__file__), "prices_db.pkl")
    
    prices_db = None
    try:
        if os.path.exists(db_path_gz):
            with gzip.open(db_path_gz, "rb") as f:
                prices_db = pickle.load(f)
        elif os.path.exists(db_path_raw):
            with open(db_path_raw, "rb") as f:
                prices_db = pickle.load(f)
    except Exception:
        pass
        
    if prices_db:
        try:
            # 記録されている最新営業日のデータを抽出
            latest_date = sorted(prices_db.keys())[-1]
            for d in prices_db[latest_date]:
                code = str(d.get("Code", "")).replace(".0", "")[:4]
                # 🚨 V1 / V2のキー名揺れ（TurnoverValue, Va）を完全吸収
                val = d.get("Va") or d.get("TurnoverValue")
                
                if val is not None and str(val).strip() != "":
                    try:
                        t_val = float(val)
                        if t_val > 0:
                            vol_map[code] = t_val / 100000000.0
                    except Exception:
                        pass
        except Exception:
            pass
            
    return vol_map

# ==========================================
# 🛡️ 絶対無通信・完全ローカル株価ロードエンジン (.pkl.gz対応・OOM回避仕様)
# ==========================================
@st.cache_data(ttl=86400, max_entries=1, show_spinner=False)
def get_hist_data_cached(key):
    """API通信を完全に物理遮断し、圧縮DBを極限の省メモリで読み込む。"""
    import os
    import pickle
    import gzip
    import gc
    import pandas as pd
    import streamlit as st

    db_path = os.path.join(os.path.dirname(__file__), "prices_db.pkl.gz")
    
    # 🚨 1. ファイルが無い場合は警告を出して空データを返す
    if not os.path.exists(db_path):
        st.error("🚨 ローカル株価DB（prices_db.pkl.gz）が見つかりません。先にバッチ処理が完了しているか確認してください。")
        return pd.DataFrame()
        
    # 2. バッチが焼き付けたローカル圧縮DBの読み込み
    try:
        with gzip.open(db_path, "rb") as f:
            prices_db = pickle.load(f)
    except Exception as e:
        st.error(f"🚨 株価DB読み込みエラー: {e}")
        return pd.DataFrame()
        
    if not prices_db:
        return pd.DataFrame()
        
    # 🚨 3. OOM（メモリ溢れクラッシュ）回避のため、抽出と同時に不要メモリを破棄
    all_records = []
    for dt_str, data in prices_db.items():
        if not data: continue
        for r in data:
            # 🚨 修正：J-Quants V1 / V2 両方のキー名揺れを完全吸収し、0円バグを粉砕
            all_records.append({
                "Date": dt_str,
                "Code": str(r.get("Code", "")).replace(".0", "")[:4],
                "AdjO": float(r.get("AdjO") or r.get("AdjustmentOpen") or r.get("O") or r.get("Open") or 0),
                "AdjH": float(r.get("AdjH") or r.get("AdjustmentHigh") or r.get("H") or r.get("High") or 0),
                "AdjL": float(r.get("AdjL") or r.get("AdjustmentLow") or r.get("L") or r.get("Low") or 0),
                "AdjC": float(r.get("AdjC") or r.get("AdjustmentClose") or r.get("C") or r.get("Close") or 0),
                "Volume": float(r.get("AdjVo") or r.get("AdjustmentVolume") or r.get("Vo") or r.get("Volume") or 0)
            })
            
    # 元の巨大辞書をメモリから完全消去し、明示的にガベージコレクションを実行
    del prices_db
    gc.collect()
    
    if not all_records:
        return pd.DataFrame()
        
    # リストをDataFrame化し、直後に元のリストも即破棄
    full_df = pd.DataFrame(all_records)
    del all_records
    gc.collect()
    
    # 🚨 4. 最終的なDataFrameのデータ型を圧縮（ダウンキャスト）し、メモリ消費をさらに約70%削減
    full_df['Date'] = pd.to_datetime(full_df['Date'], errors='coerce')
    full_df['Code'] = full_df['Code'].astype('category')
    for col in ['AdjO', 'AdjH', 'AdjL', 'AdjC', 'Volume']:
        full_df[col] = pd.to_numeric(full_df[col], downcast='float')
        
    # 5. 銘柄コードと日付で綺麗に並び替えて返す
    full_df.sort_values(by=['Code', 'Date'], inplace=True)
    full_df.reset_index(drop=True, inplace=True)
    
    return full_df

# ==========================================
# 🛡️ TAB3専用：完全ローカル株価抽出エンジン（API通信ゼロ）
# ==========================================
@st.cache_data(show_spinner=False)
def get_local_stock_data(code):
    """API通信を物理的に遮断し、バッチが作った prices_db.pkl から指定銘柄の時系列を抽出する"""
    import os, pickle
    import pandas as pd
    
    db_path = os.path.join(os.path.dirname(__file__), "prices_db.pkl")
    if not os.path.exists(db_path):
        return pd.DataFrame()
        
    try:
        with open(db_path, "rb") as f:
            prices_db = pickle.load(f)
            
        all_records = []
        target_code = str(code).replace('.0', '')[:4]
        
        for dt_str, records in prices_db.items():
            for r in records:
                c = str(r.get("Code", "")).replace(".0", "")[:4]
                if c == target_code:
                    # 🚨 修正：J-Quants V1 / V2 両方のキー名揺れを完全吸収し、0円バグを粉砕
                    all_records.append({
                        "Date": pd.to_datetime(dt_str),
                        "Code": c,
                        "AdjO": float(r.get("AdjO") or r.get("AdjustmentOpen") or r.get("O") or r.get("Open") or 0),
                        "AdjH": float(r.get("AdjH") or r.get("AdjustmentHigh") or r.get("H") or r.get("High") or 0),
                        "AdjL": float(r.get("AdjL") or r.get("AdjustmentLow") or r.get("L") or r.get("Low") or 0),
                        "AdjC": float(r.get("AdjC") or r.get("AdjustmentClose") or r.get("C") or r.get("Close") or 0),
                        "Volume": float(r.get("AdjVo") or r.get("AdjustmentVolume") or r.get("Vo") or r.get("Volume") or 0)
                    })
                    break 
        
        if not all_records:
            return pd.DataFrame()
            
        df = pd.DataFrame(all_records)
        df.sort_values(by="Date", inplace=True)
        df.reset_index(drop=True, inplace=True)
        return df
    except Exception:
        return pd.DataFrame()

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
# 🧠 ファンダメンタルズ＆陣形判定ロジック
# ==========================================
def analyze_fundamental_momentum(df, mode="buy", sales_req=7.0, ord_req=15.0, sell_req=8.0):
    try:
        if df is None or len(df) < 5: return False, ""
        cols = [str(c).lower() for c in df.columns]
        def find_c(*names):
            for n in names:
                if n.lower() in cols: return df.columns[cols.index(n.lower())]
            return None

        c_sales = find_c('Sales', 'NetSales', 'net_sales')
        c_op = find_c('OP', 'OperatingProfit', 'operating_profit')
        c_ord = find_c('OdP', 'OrdinaryProfit', 'ordinary_profit')
        c_eps = find_c('EPS', 'EarningsPerShare', 'eps')
        c_profit = find_c('NP', 'Profit', 'netincome')
        c_type = find_c('CurPerType', 'TypeOfCurrentPeriod', 'type')
        
        if not c_sales or not c_ord: return False, ""

        def to_flt(v):
            try:
                if pd.isna(v) or str(v).strip() == '': return 0.0
                return float(str(v).replace(',', ''))
            except: return 0.0

        actual_mask = (df[c_sales].apply(to_flt) > 0) | (df[c_ord].apply(to_flt) > 0)
        actual_df = df[actual_mask].copy().reset_index(drop=True)
        if len(actual_df) < 5: return False, ""
            
        std_df = actual_df.copy()
        for i in range(1, len(actual_df)):
            curr_sales = to_flt(actual_df[c_sales].iloc[i])
            prev_sales = to_flt(actual_df[c_sales].iloc[i-1])
            curr_type = str(actual_df[c_type].iloc[i]) if c_type else ""
            
            is_q1 = False
            if '1Q' in curr_type or 'Q1' in curr_type: is_q1 = True
            elif curr_sales < prev_sales and prev_sales > 0: is_q1 = True
                
            if not is_q1:
                for col in filter(None, [c_sales, c_op, c_ord, c_eps, c_profit]):
                    try:
                        c_val = to_flt(actual_df[col].iloc[i])
                        p_val = to_flt(actual_df[col].iloc[i-1])
                        std_df.iat[i, std_df.columns.get_loc(col)] = c_val - p_val
                    except: pass
                        
        q0 = std_df.iloc[-1] 
        y0 = std_df.iloc[-5]
        
        def get_val(row, primary_col, fallback_col=None):
            v = to_flt(row.get(primary_col, 0.0)) if primary_col else 0.0
            if v == 0.0 and fallback_col: v = to_flt(row.get(fallback_col, 0.0))
            return v

        q0_sales, y0_sales = get_val(q0, c_sales), get_val(y0, c_sales)
        q0_op, y0_op = get_val(q0, c_op), get_val(y0, c_op)
        q0_ord, y0_ord = get_val(q0, c_ord), get_val(y0, c_ord)
        q0_eps, y0_eps = get_val(q0, c_eps, c_profit), get_val(y0, c_eps, c_profit)

        if q0_sales <= 0 or y0_sales <= 0: return False, ""

        def calc_yoy(c, p):
            if p == 0: return 0.0
            return ((c - p) / abs(p)) * 100.0

        s_yoy = calc_yoy(q0_sales, y0_sales)
        op_yoy = calc_yoy(q0_op, y0_op)
        or_yoy = calc_yoy(q0_ord, y0_ord)
        ep_yoy = calc_yoy(q0_eps, y0_eps)
        
        if mode == "buy":
            if q0_op < 0 or q0_ord < 0 or q0_eps < 0: return False, ""
            if not (s_yoy >= sales_req): return False, ""
            if not (op_yoy >= 15.0): return False, ""
            if not (or_yoy >= ord_req): return False, ""
            if not (ep_yoy >= 15.0): return False, ""
            
            if op_yoy >= 20.0 and or_yoy >= 20.0 and ep_yoy >= 20.0: return True, "S級🎯"
            return True, "A級🟢"
            
        elif mode == "sell":
            if not (op_yoy < sell_req): return False, ""
            if not (or_yoy < sell_req): return False, ""
            if not (ep_yoy < sell_req): return False, ""
            
            if op_yoy < 0 and or_yoy < 0 and ep_yoy < 0: return True, "S級💀"
            return True, "A級📉"
            
    except: pass
    return False, ""

def analyze_formation_history(df, is_macro_downtrend=False):
    """過去3ヶ月分のデータから、買い/空売りフォーメーション（3日ルール・18日ルール）を厳格に探知する"""
    import pandas as pd
    buy_signals = []
    sell_signals = []
    
    if df is None or len(df) < 65:
        return buy_signals, sell_signals
        
    cols = [str(c).lower() for c in df.columns]
    def get_c(*names):
        for n in names:
            if n.lower() in cols: return df.columns[cols.index(n.lower())]
        return None

    # 💡 陽線・陰線判定のため、始値（c_o）を検索対象に完全追加
    c_o = get_c('adjo', 'adjustmentopen', 'open', 'o')
    c_h = get_c('adjh', 'adjustmenthigh', 'high', 'h')
    c_l = get_c('adjl', 'adjustmentlow', 'low', 'l')
    c_c = get_c('adjc', 'adjustmentclose', 'close', 'c')
    c_d = get_c('date', 'd', 'datetime')
    
    if not all([c_o, c_h, c_l, c_c, c_d]): return [], []

    df_recent = df.tail(65).reset_index(drop=True)
    
    # 18日ルール用の18日移動平均線
    if 'MA18' not in df_recent.columns:
        df_recent['MA18'] = df_recent[c_c].rolling(18).mean()
    
    for i in range(3, len(df_recent)):
        # 前日(i-3)のデータ（3日ルールにおける前日比較用）
        prev_h = float(df_recent.loc[i-3, c_h])
        prev_l = float(df_recent.loc[i-3, c_l])
        
        # 🚨 ボスの要求定義に基づく日数マッピング
        # 0日目（3日ルールの「1日目」） = 一昨日 (i-2)
        day0_o = float(df_recent.loc[i-2, c_o])
        day0_h = float(df_recent.loc[i-2, c_h])
        day0_l = float(df_recent.loc[i-2, c_l])
        day0_c = float(df_recent.loc[i-2, c_c])
        
        # 1日目（3日ルールの「2日目」） = 昨日 (i-1)
        day1_o = float(df_recent.loc[i-1, c_o])
        day1_h = float(df_recent.loc[i-1, c_h])
        day1_l = float(df_recent.loc[i-1, c_l])
        day1_c = float(df_recent.loc[i-1, c_c])
        day1_ma18 = df_recent.loc[i-1, 'MA18']
        
        # 2日目（3日ルールの「3日目」） = 今日 (i)
        day2_o = float(df_recent.loc[i, c_o])
        day2_h = float(df_recent.loc[i, c_h])
        day2_l = float(df_recent.loc[i, c_l])
        day2_c = float(df_recent.loc[i, c_c])
        day2_ma18 = df_recent.loc[i, 'MA18']
        
        curr_date = df_recent.loc[i, c_d]
        
        # 判定漏れ防止：移動平均線が算出できていない期間（NaN）は安全にスキップ
        if pd.isna(day1_ma18) or pd.isna(day2_ma18):
            continue
            
        day1_ma18 = float(day1_ma18)
        day2_ma18 = float(day2_ma18)

        # ----------------------------------------------------
        # 🔵 買いシグナル①（3日ルール）
        # 1日目: 陰線 で、終値 が前日の安値(prev_l)を下回る
        buy1_day1 = (day0_c < day0_o) and (day0_c < prev_l)
        # 2日目: 陽線 で、終値 が前日の高値(day0_h)を上回る
        buy1_day2 = (day1_c > day1_o) and (day1_c > day0_h)
        # 3日目: 陽線 で、終値 が前日の終値(day1_c)を上回る
        buy1_day3 = (day2_c > day2_o) and (day2_c > day1_c)
        buy_cond1 = buy1_day1 and buy1_day2 and buy1_day3
        
        # 🔵 買いシグナル②（18日ルール）
        # 形状：陰線（0日目）→陽線（1日目）→陽線（2日目）
        # 条件：陽線で2日連続、今日と昨日の安値が18日移動平均線より高い
        buy2_day0 = (day0_c < day0_o) # 0日目: 陰線
        buy2_day1 = (day1_c > day1_o) and (day1_l > day1_ma18) # 1日目: 陽線 AND 安値が18MAより高い
        buy2_day2 = (day2_c > day2_o) and (day2_l > day2_ma18) # 2日目: 陽線 AND 安値が18MAより高い
        buy_cond2 = buy2_day0 and buy2_day1 and buy2_day2
        
        if buy_cond1 or buy_cond2:
            buy_signals.append(curr_date)
            
        # ----------------------------------------------------
        # 🔴 空売りシグナル①（3日ルール）
        # 1日目: 陽線 で、終値 が前日の高値(prev_h)を上回る
        sell1_day1 = (day0_c > day0_o) and (day0_c > prev_h)
        # 2日目: 陰線 で、終値 が前日の安値(day0_l)を下回る
        sell1_day2 = (day1_c < day1_o) and (day1_c < day0_l)
        # 3日目: 陰線 で、終値 が前日の終値(day1_c)を下回る
        sell1_day3 = (day2_c < day2_o) and (day2_c < day1_c)
        sell_cond1 = sell1_day1 and sell1_day2 and sell1_day3
        
        # 🔴 空売りシグナル②（18日ルール）
        # 形状：陽線（0日目）→陰線（1日目）→陰線（2日目）
        # 条件：陰線で2日連続、今日と昨日の高値が18日移動平均線より安い
        sell2_day0 = (day0_c > day0_o) # 0日目: 陽線
        sell2_day1 = (day1_c < day1_o) and (day1_h < day1_ma18) # 1日目: 陰線 AND 高値が18MAより安い
        sell2_day2 = (day2_c < day2_o) and (day2_h < day2_ma18) # 2日目: 陰線 AND 高値が18MAより安い
        sell_cond2 = sell2_day0 and sell2_day1 and sell2_day2
        
        if sell_cond1 or sell_cond2:
            # 空売りの前提「市場が下げ相場である」こと
            if is_macro_downtrend:
                sell_signals.append(curr_date)
            
    return list(set(buy_signals)), list(set(sell_signals))

def fetch_fundamental_history_local(code, local_db):
    import pandas as pd
    try:
        if local_db is None or len(local_db) == 0: return None
        str_code = str(code).strip()[:4]
        df_target = None
        
        if isinstance(local_db, dict):
            api_code = str_code if len(str_code) >= 5 else str_code + "0"
            df_target = local_db.get(api_code)
            if df_target is None: df_target = local_db.get(str_code) 
            if df_target is None or len(df_target) == 0: return None
            df_target = df_target.copy().reset_index(drop=True)
            
        elif isinstance(local_db, pd.DataFrame):
            c_code_col = 'Code' if 'Code' in local_db.columns else ('code' if 'code' in local_db.columns else None)
            if not c_code_col: return None
            mask = local_db[c_code_col].astype(str).str.startswith(str_code)
            df_target = local_db[mask].copy().reset_index(drop=True)

        if df_target is None or len(df_target) == 0: return None

        cols = [str(c).lower() for c in df_target.columns]
        
        sales_candidates = ['sales', 'netsales', 'net_sales', 'operatingrevenues', 'operating_revenues', 'ordinaryrevenues', 'ordinary_revenues']
        op_candidates = ['op', 'operatingprofit', 'operating_profit']
        ord_candidates = ['odp', 'ordinaryprofit', 'ordinary_profit']
        profit_candidates = ['np', 'profit', 'netincome', 'net_income']
        eps_candidates = ['eps', 'earningspershare', 'earnings_per_share']
        
        def find_c(*names):
            for n in names:
                if n.lower() in cols: return df_target.columns[cols.index(n.lower())]
            return None

        c_type = find_c('CurPerType', 'TypeOfCurrentPeriod')
        c_date = find_c('DiscDate', 'DisclosedDate', 'Date')
        c_end_date = find_c('CurrentPeriodEndDate', 'currentperiodenddate')
        c_fy = find_c('FiscalYear', 'fiscalyear')
        c_doc = find_c('TypeOfDocument', 'typeofdocument', 'DocumentType')

        def to_flt(v):
            try: 
                if pd.isna(v) or str(v).strip() == '': return 0.0
                return float(str(v).replace(',', '').strip())
            except: return 0.0

        if c_date:
            df_target[c_date] = pd.to_datetime(df_target[c_date], errors='coerce')
            df_target = df_target.sort_values(by=c_date).reset_index(drop=True)

        all_target_cols = []
        for c_group in [sales_candidates, op_candidates, ord_candidates, profit_candidates, eps_candidates]:
            for c in c_group:
                actual_c = find_c(c)
                if actual_c and actual_c not in all_target_cols:
                    all_target_cols.append(actual_c)

        # 🚨 1. 【ノイズ排除】本物の「決算データ(FinancialStatements)」のみを強制抽出
        if c_doc:
            is_stmt = df_target[c_doc].astype(str).str.contains('FinancialStatements|Earnings|決算', case=False, na=False, regex=True)
            df_target = df_target[is_stmt].copy().reset_index(drop=True)

        # 🚨 2. 実績値ゼロの空行を物理排除
        has_actuals = pd.Series([False]*len(df_target))
        for c in all_target_cols:
            if c in df_target.columns:
                has_actuals = has_actuals | (df_target[c].apply(to_flt) != 0.0)
        df_target = df_target[has_actuals].copy().reset_index(drop=True)

        # 🚨 3. 重複排除
        if c_end_date:
            df_target = df_target.drop_duplicates(subset=[c_end_date], keep='last').reset_index(drop=True)
        elif c_fy and c_type:
            df_target = df_target.drop_duplicates(subset=[c_fy, c_type], keep='last').reset_index(drop=True)

        if len(df_target) < 2: return None

        std_df = df_target.copy()
        
        # 4. 累積値から四半期単独値への変換（引き算）
        for i in range(1, len(df_target)):
            curr_type = str(df_target[c_type].iloc[i]).strip() if c_type else ""
            is_q1 = ('1Q' in curr_type or 'Q1' in curr_type)
            
            if not is_q1:
                metric_col = None
                for c in all_target_cols:
                    if c in df_target.columns and df_target[c].apply(to_flt).sum() != 0:
                        metric_col = c
                        break
                if metric_col:
                    c_val = to_flt(df_target[metric_col].iloc[i])
                    p_val = to_flt(df_target[metric_col].iloc[i-1])
                    if c_val < p_val and p_val > 0:
                        is_q1 = True

            if not is_q1:
                for col in all_target_cols:
                    if col in std_df.columns:
                        try: 
                            val_c = to_flt(df_target[col].iloc[i])
                            val_p = to_flt(df_target[col].iloc[i-1])
                            std_df.iat[i, std_df.columns.get_loc(col)] = val_c - val_p
                        except: pass

        def calc_yoy(c, p):
            if p == 0.0 or p is None: return "-"
            if c == 0.0 and p != 0.0: return "-"
            return ((c - p) / abs(p)) * 100.0

        def get_best_v(row, candidates):
            if row is None: return 0.0
            for c in candidates:
                ac = next((col for col in row.index if str(col).lower() == c.lower()), None)
                if ac:
                    v = to_flt(row.get(ac, 0.0))
                    if v != 0.0: return v
            return 0.0

        results = []
        
        # 🚨 5. 【完全一致検索】YoY計算におけるインデックス崩壊の無効化
        for i in range(1, 5):
            if len(std_df) < i:
                results.append({"期間": f"直近 Q{i}", "開示日": "-", "売上(%)": "-", "営業益(%)": "-", "経常益(%)": "-", "純利益(%)": "-", "EPS(%)": "-"})
                continue
                
            q_cur = std_df.iloc[-i]
            q_cur_type = str(q_cur.get(c_type, "")).strip() if c_type else ""
            
            q_yoy = None
            # 現在の四半期（例：Q2）と同じラベルの行を、過去に向かって逆探知する
            if q_cur_type:
                for j in range(len(std_df) - i - 1, -1, -1):
                    past_row = std_df.iloc[j]
                    if str(past_row.get(c_type, "")).strip() == q_cur_type:
                        q_yoy = past_row
                        break
            
            # 見つからなかった場合の予備措置（従来の4行前参照）
            if q_yoy is None and len(std_df) >= i + 4:
                q_yoy = std_df.iloc[-(i+4)]

            dis_date = q_cur.get(c_date, '-')
            if pd.notna(dis_date) and hasattr(dis_date, 'strftime'): 
                dis_date = dis_date.strftime('%Y-%m-%d')
                if dis_date == '1970-01-01': dis_date = '-'
            else: dis_date = '-'

            v_sales_c = get_best_v(q_cur, sales_candidates)
            v_op_c = get_best_v(q_cur, op_candidates)
            v_ord_c = get_best_v(q_cur, ord_candidates)
            v_profit_c = get_best_v(q_cur, profit_candidates)
            v_eps_c = get_best_v(q_cur, eps_candidates)
            
            v_sales_p = get_best_v(q_yoy, sales_candidates)
            v_op_p = get_best_v(q_yoy, op_candidates)
            v_ord_p = get_best_v(q_yoy, ord_candidates)
            v_profit_p = get_best_v(q_yoy, profit_candidates)
            v_eps_p = get_best_v(q_yoy, eps_candidates)
            
            # 金融銘柄専用の突破プロキシ（売上・営業益が0なら経常益を偽装コピーする）
            if v_op_c == 0.0 and v_ord_c != 0.0: v_op_c = v_ord_c
            if v_op_p == 0.0 and v_ord_p != 0.0: v_op_p = v_ord_p
            if v_sales_c == 0.0 and v_ord_c != 0.0: v_sales_c = v_ord_c
            if v_sales_p == 0.0 and v_ord_p != 0.0: v_sales_p = v_ord_p
            
            results.append({
                "期間": f"直近 Q{i}", "開示日": str(dis_date),
                "売上(%)": calc_yoy(v_sales_c, v_sales_p),
                "営業益(%)": calc_yoy(v_op_c, v_op_p),
                "経常益(%)": calc_yoy(v_ord_c, v_ord_p),
                "純利益(%)": calc_yoy(v_profit_c, v_profit_p),
                "EPS(%)": calc_yoy(v_eps_c, v_eps_p),
            })

        # 6. 通年データの算出（最新の4件＝最新の1年分を安全に合算）
        if len(std_df) >= 4:
            y_cur = std_df.iloc[-4:].apply(lambda x: pd.to_numeric(x, errors='coerce')).sum(numeric_only=True)
            y_prv = std_df.iloc[-8:-4].apply(lambda x: pd.to_numeric(x, errors='coerce')).sum(numeric_only=True) if len(std_df) >= 8 else None
            
            y_sales_c = get_best_v(y_cur, sales_candidates)
            y_op_c = get_best_v(y_cur, op_candidates)
            y_ord_c = get_best_v(y_cur, ord_candidates)
            y_profit_c = get_best_v(y_cur, profit_candidates)
            y_eps_c = get_best_v(y_cur, eps_candidates)
            
            y_sales_p = get_best_v(y_prv, sales_candidates)
            y_op_p = get_best_v(y_prv, op_candidates)
            y_ord_p = get_best_v(y_prv, ord_candidates)
            y_profit_p = get_best_v(y_prv, profit_candidates)
            y_eps_p = get_best_v(y_prv, eps_candidates)

            if y_op_c == 0.0 and y_ord_c != 0.0: y_op_c = y_ord_c
            if y_op_p == 0.0 and y_ord_p != 0.0: y_op_p = y_ord_p
            if y_sales_c == 0.0 and y_ord_c != 0.0: y_sales_c = y_ord_c
            if y_sales_p == 0.0 and y_ord_p != 0.0: y_sales_p = y_ord_p

            results.append({
                "期間": "🌟 通年(直近1年)", "開示日": "-",
                "売上(%)": calc_yoy(y_sales_c, y_sales_p),
                "営業益(%)": calc_yoy(y_op_c, y_op_p),
                "経常益(%)": calc_yoy(y_ord_c, y_ord_p),
                "純利益(%)": calc_yoy(y_profit_c, y_profit_p),
                "EPS(%)": calc_yoy(y_eps_c, y_eps_p),
            })
        else:
            results.append({"期間": "🌟 通年(直近1年)", "開示日": "-", "売上(%)": "-", "営業益(%)": "-", "経常益(%)": "-", "純利益(%)": "-", "EPS(%)": "-"})

        if len(results) == 0: return None
        return pd.DataFrame(results[::-1])
    except Exception as e: 
        return None

# ==========================================
# 📺 メインUI：レイアウト
# ==========================================
render_macro_board()

tab1, tab2, tab3, tab7 = st.tabs(["📈 TAB1: 買い", "📉 TAB2: 空売り", "🎯 TAB3: 精密スコープ", "📁 TAB7: 戦績"])

# ==========================================
# 🌐 TAB1: 買い銘柄広域スキャン (Growth / Standard / Prime)
# ==========================================
with tab1:
    st.markdown('### 🌐 買い銘柄広域スキャン', unsafe_allow_html=True)
    st.caption("※直近2四半期の売上・利益のYoY（前年同期比）成長率をベースに、大化け候補（S級・A級）を広域索敵します。")
    
    with st.form("tab1_buy_scan_form", clear_on_submit=False):
        col1_1, col1_2, col1_3 = st.columns(3)
        t1_period = col1_1.selectbox("期間フィルタ (高値判定基準)", ["52週", "3か月", "6か月", "2年"], index=0)
        t1_sales_r = col1_2.selectbox("直近四半期 売上増収率 (%)", [7, 3, 5], index=0)
        t1_ord_r = col1_3.selectbox("直近四半期 経常利益増益率 (%)", [15, 10, 13, 20], index=0)
        
        col1_4, col1_5, col1_6 = st.columns(3)
        t1_mcap = col1_4.selectbox("時価総額フィルタ (億円以上)", [500, 300, 1000], index=0)
        t1_p_min = col1_5.number_input("価格下限 (円)", value=400, step=100, key="t1_p_min")
        t1_p_max = col1_6.number_input("価格上限 (円)", value=3000, step=100, key="t1_p_max")
        
        st.markdown(f"**(固定スキャン条件: 直近2四半期連続 YoY S級/A級クリア)** \n"
                    f"・直近1つ目の四半期は売上 {t1_sales_r}% 以上、他利益 {t1_ord_r}% 以上で完全クリア必須。\n"
                    f"・直近2つ目の四半期も完全クリアでS級🎯、1つだけ下回ればA級🟢。")
        
        btn_scan_t1 = st.form_submit_button("🚀 買い銘柄 スキャン実行", use_container_width=True, type="primary")

    if btn_scan_t1:
        import time
        st.write("---")
        with st.status("📡 買い広域レーダー稼働中...", expanded=True) as status:
            t_start_total = time.time()
            st.write("#### 🔄 [Phase 1/2] 価格帯・時価総額フィルタ一括足切り")
            p1_msg = st.empty()
            p1_msg.info("⏳ J-Quantsサーバーから全銘柄の最新価格・時価総額データを一括取得中...")
            t_start_p1 = time.time()
            
            all_codes = []
            try:
                prices_map = get_all_latest_prices_bulk() if 'get_all_latest_prices_bulk' in globals() else {}
                mcap_map = get_all_market_caps_bulk() if 'get_all_market_caps_bulk' in globals() else {}
                if prices_map:
                    for c_code, c_price in prices_map.items():
                        if float(t1_p_min) <= float(c_price) <= float(t1_p_max):
                            c_mcap = float(mcap_map.get(str(c_code), 0))
                            if c_mcap >= float(t1_mcap): all_codes.append(str(c_code))
                else:
                    p1_msg.error("❌ 株価データの取得に失敗しました。")
                    st.stop()
            except Exception as e:
                p1_msg.error(f"❌ フィルタ取得エラー: {e}")
                st.stop()
                
            p_filtered_codes = [str(code).replace('.0', '').strip()[:4] for code in all_codes]
            time_p1 = time.time() - t_start_p1
            p1_msg.success(f"✅ Phase 1 完了: 適合 {len(p_filtered_codes)} 銘柄 ➔ Phase 2 へパスしました。")
            
            st.write("#### 🔄 [Phase 2/2] ファンダメンタルズ直列解析 (YoY 2期連続)")
            p2_msg = st.empty()
            p2_bar = st.progress(0)
            t_start_p2 = time.time()
            hit_codes_s, hit_codes_a = [], []
            total_p2 = len(p_filtered_codes)
            processed_p2 = 0
            
            if total_p2 > 0:
                try: local_fund_db = load_local_fundamentals_db()
                except: local_fund_db = None

                req_s = float(t1_sales_r)
                req_o = float(t1_ord_r)

                for code in p_filtered_codes:
                    processed_p2 += 1
                    if processed_p2 % 5 == 0 or processed_p2 == total_p2:
                        p2_bar.progress(processed_p2 / total_p2)
                        p2_msg.info(f"📡 索敵中: {processed_p2} / {total_p2} 銘柄完了... [標的: {code}]")

                    try:
                        f_df = fetch_fundamental_history_local(code, local_fund_db) if 'fetch_fundamental_history_local' in globals() else None
                        if f_df is not None and not f_df.empty:
                            q1_row = f_df[f_df["期間"] == "直近 Q1"]
                            q2_row = f_df[f_df["期間"] == "直近 Q2"]
                            if not q1_row.empty and not q2_row.empty:
                                def get_val(r, col):
                                    v = r[col].iloc[0]
                                    if isinstance(v, str) and v == "-": return None
                                    try: return float(v)
                                    except: return None

                                q1_s, q1_op, q1_ord, q1_np, q1_eps = get_val(q1_row, "売上(%)"), get_val(q1_row, "営業益(%)"), get_val(q1_row, "経常益(%)"), get_val(q1_row, "純利益(%)"), get_val(q1_row, "EPS(%)")
                                q2_s, q2_op, q2_ord, q2_np, q2_eps = get_val(q2_row, "売上(%)"), get_val(q2_row, "営業益(%)"), get_val(q2_row, "経常益(%)"), get_val(q2_row, "純利益(%)"), get_val(q2_row, "EPS(%)")
                                
                                def count_misses(s, op, ord_p, np_p, eps):
                                    if None in [s, op, ord_p, np_p, eps]: return 99 
                                    m = 0
                                    if s < req_s: m += 1
                                    if op < req_o: m += 1
                                    if ord_p < req_o: m += 1
                                    if np_p < req_o: m += 1
                                    if eps < req_o: m += 1
                                    return m
                                    
                                q1_miss = count_misses(q1_s, q1_op, q1_ord, q1_np, q1_eps)
                                q2_miss = count_misses(q2_s, q2_op, q2_ord, q2_np, q2_eps)
                                
                                if q1_miss == 0:
                                    if q2_miss == 0: hit_codes_s.append(str(code))
                                    elif q2_miss == 1: hit_codes_a.append(str(code))
                    except: pass
                
                time_p2 = time.time() - t_start_p2
                p2_bar.progress(1.0)
                p2_msg.success(f"✅ Phase 2 完了: すべての解析が終了しました。")
                
                all_hits = hit_codes_s + hit_codes_a
                time_total = time.time() - t_start_total
                status.update(label=f"🎯 スキャン完了！ 計 {len(all_hits)} 銘柄を捕捉しました。 (総計: {time_total:.2f}秒)", state="complete", expanded=False)
                
                st.divider()
                st.write("### 🎯 スキャン結果")
                st.write(f"**【S級】条件完全突破銘柄:** {len(hit_codes_s)} 件")
                if hit_codes_s: st.code(", ".join(hit_codes_s))
                else: st.info("S級条件に合致する銘柄はありませんでした。")
                    
                st.write(f"**【A級】条件突破銘柄:** {len(hit_codes_a)} 件")
                if hit_codes_a: st.code(", ".join(hit_codes_a))
                else: st.info("A級条件に合致する銘柄はありませんでした。")
                    
                st.caption(f"⏱️ **処理時間** ➔ [1. 価格足切り]: `{time_p1:.2f}秒` | [2. ファンダ解析]: `{time_p2:.2f}秒` | 🟢 **[総計]**: `{time_total:.2f}秒`")
                st.markdown("#### 📋 TAB3 (詳細分析) 貼り付け用コード")
                st.info("以下のコードをコピーし、次フェーズの分析へ移行してください。")
                st.code(", ".join(all_hits) if all_hits else "条件に合致する銘柄はありませんでした。", language="text")
                st.session_state['tab1_scan_results'] = [{"Code": c, "Rank": "S級"} for c in hit_codes_s] + [{"Code": c, "Rank": "A級"} for c in hit_codes_a]
            else:
                p2_msg.warning("⚠️ Phase 1 を通過した銘柄が0件のため、解析をスキップします。")
                status.update(label="⚠️ スキャン中断：対象銘柄なし", state="complete")

# ==========================================
# 📉 TAB2: 売り（空売り）銘柄広域スキャン (Growth / Standard / Prime)
# ==========================================
with tab2:
    st.markdown('### 📉 売り（空売り）銘柄広域スキャン', unsafe_allow_html=True)
    st.caption("※直近2四半期の業績鈍化・衰退（YoY 8%未満等）をベースに、空売り候補（S級・A級）を広域索敵します。")
    
    with st.form("tab2_sell_scan_form", clear_on_submit=False):
        col2_1, col2_2, col2_3 = st.columns(3)
        t2_period = col2_1.selectbox("期間フィルタ (安値判定基準)", ["6か月", "3か月"], index=0, key="t2_period")
        t2_ord_r = col2_2.selectbox("直近四半期 利益成長率フィルタ (%)", [8, 5, 10], index=0, key="t2_ord_r")
        t2_mcap = col2_3.selectbox("時価総額フィルタ (億円以上)", [500, 300, 1000], index=0, key="t2_mcap")
        
        col2_4, col2_5, col2_6 = st.columns(3)
        t2_vol = col2_4.selectbox("売買代金フィルタ (億円以上)", [3, 1, 2], index=0, key="t2_vol")
        t2_p_min = col2_5.number_input("価格下限 (円)", value=400, step=100, key="t2_p_min")
        t2_p_max = col2_6.number_input("価格上限 (円)", value=3000, step=100, key="t2_p_max")
        
        st.markdown(f"**(固定スキャン条件: 直近2四半期連続 利益鈍化)** \n"
                    f"・営業利益・経常利益・純利益・一株利益の全8項目が 5%未満 でS級💀 \n"
                    f"・1つだけ {t2_ord_r}%未満（他5%未満）でA級📉")
        
        btn_scan_t2 = st.form_submit_button("🚀 売り銘柄 スキャン実行", use_container_width=True, type="primary")

    if btn_scan_t2:
        import time
        st.write("---")
        with st.status("📡 売り広域レーダー稼働中...", expanded=True) as status:
            t_start_total = time.time()
            st.write("#### 🔄 [Phase 1/2] 流動性・価格帯フィルタ一括足切り")
            p1_msg_t2 = st.empty()
            p1_msg_t2.info("⏳ J-Quantsサーバーから価格・流動性データを一括取得中...")
            t_start_p1 = time.time()
            
            all_codes = []
            try:
                prices_map = get_all_latest_prices_bulk() if 'get_all_latest_prices_bulk' in globals() else {}
                mcap_map = get_all_market_caps_bulk() if 'get_all_market_caps_bulk' in globals() else {}
                vol_map = get_all_volumes_bulk() if 'get_all_volumes_bulk' in globals() else {}
                
                if prices_map:
                    for c_code, c_price in prices_map.items():
                        if float(t2_p_min) <= float(c_price) <= float(t2_p_max):
                            c_mcap = float(mcap_map.get(str(c_code), 0))
                            if c_mcap >= float(t2_mcap):
                                c_vol = float(vol_map.get(str(c_code), 0))
                                if c_vol >= float(t2_vol): all_codes.append(str(c_code))
                else:
                    p1_msg_t2.error("❌ 株価データの取得に失敗しました。")
                    st.stop()
            except Exception as e:
                p1_msg_t2.error(f"❌ フィルタ取得エラー: {e}")
                st.stop()
                
            p_filtered_codes = [str(code).replace('.0', '').strip()[:4] for code in all_codes]
            time_p1 = time.time() - t_start_p1
            p1_msg_t2.success(f"✅ Phase 1 完了: 適合 {len(p_filtered_codes)} 銘柄 ➔ Phase 2 へパスしました。")
            
            st.write("#### 🔄 [Phase 2/2] ファンダメンタルズ直列解析 (空売り)")
            p2_msg_t2 = st.empty()
            p2_bar_t2 = st.progress(0)
            t_start_p2 = time.time()
            hit_codes_s, hit_codes_a = [], []
            total_p2 = len(p_filtered_codes)
            processed_p2 = 0
            
            if total_p2 > 0:
                try: local_fund_db = load_local_fundamentals_db()
                except: local_fund_db = None

                req_o = float(t2_ord_r)

                for code in p_filtered_codes:
                    processed_p2 += 1
                    if processed_p2 % 5 == 0 or processed_p2 == total_p2:
                        p2_bar_t2.progress(processed_p2 / total_p2)
                        p2_msg_t2.info(f"📡 索敵中: {processed_p2} / {total_p2} 銘柄完了... [標的: {code}]")

                    try:
                        f_df = fetch_fundamental_history_local(code, local_fund_db) if 'fetch_fundamental_history_local' in globals() else None
                        if f_df is not None and not f_df.empty:
                            q1_row = f_df[f_df["期間"] == "直近 Q1"]
                            q2_row = f_df[f_df["期間"] == "直近 Q2"]
                            if not q1_row.empty and not q2_row.empty:
                                def get_val(r, col):
                                    v = r[col].iloc[0]
                                    if isinstance(v, str) and v == "-": return None
                                    try: return float(v)
                                    except: return None

                                q1_op, q1_ord, q1_np, q1_eps = get_val(q1_row, "営業益(%)"), get_val(q1_row, "経常益(%)"), get_val(q1_row, "純利益(%)"), get_val(q1_row, "EPS(%)")
                                q2_op, q2_ord, q2_np, q2_eps = get_val(q2_row, "営業益(%)"), get_val(q2_row, "経常益(%)"), get_val(q2_row, "純利益(%)"), get_val(q2_row, "EPS(%)")
                                
                                vals = [q1_op, q1_ord, q1_np, q1_eps, q2_op, q2_ord, q2_np, q2_eps]
                                if None not in vals:
                                    lt_5 = sum(1 for v in vals if v < 5.0)
                                    lt_req = sum(1 for v in vals if 5.0 <= v < req_o)
                                    ge_req = sum(1 for v in vals if v >= req_o)
                                    
                                    if ge_req == 0:
                                        if lt_5 == 8: hit_codes_s.append(str(code))
                                        elif lt_req == 1 and lt_5 == 7: hit_codes_a.append(str(code))
                    except: pass
                
                time_p2 = time.time() - t_start_p2
                p2_bar_t2.progress(1.0)
                p2_msg_t2.success(f"✅ Phase 2 完了: すべての解析が終了しました。")
                
                all_hits = hit_codes_s + hit_codes_a
                time_total = time.time() - t_start_total
                status.update(label=f"🎯 スキャン完了！ 計 {len(all_hits)} 銘柄を捕捉しました。 (総計: {time_total:.2f}秒)", state="complete", expanded=False)
                
                st.divider()
                st.write("### 🎯 スキャン結果")
                st.write(f"**【S級】条件完全突破銘柄:** {len(hit_codes_s)} 件")
                if hit_codes_s: st.code(", ".join(hit_codes_s))
                else: st.info("S級条件に合致する銘柄はありませんでした。")
                    
                st.write(f"**【A級】条件突破銘柄:** {len(hit_codes_a)} 件")
                if hit_codes_a: st.code(", ".join(hit_codes_a))
                else: st.info("A級条件に合致する銘柄はありませんでした。")
                    
                st.caption(f"⏱️ **処理時間** ➔ [1. 流動性足切り]: `{time_p1:.2f}秒` | [2. ファンダ解析]: `{time_p2:.2f}秒` | 🟢 **[総計]**: `{time_total:.2f}秒`")
                st.markdown("#### 📋 TAB3 (詳細分析) 貼り付け用コード")
                st.info("以下のコードをコピーし、次フェーズの分析へ移行してください。")
                st.code(", ".join(all_hits) if all_hits else "条件に合致する銘柄はありませんでした。", language="text")
                st.session_state['tab2_scan_results'] = [{"Code": c, "Rank": "S級"} for c in hit_codes_s] + [{"Code": c, "Rank": "A級"} for c in hit_codes_a]
            else:
                p2_msg_t2.warning("⚠️ Phase 1 を通過した銘柄が0件のため、解析をスキップします。")
                status.update(label="⚠️ スキャン中断：対象銘柄なし", state="complete")

# ==========================================
# 🎯 TAB3: 精密スコープ
# ==========================================
with tab3:
    st.markdown("### 🎯 【照準】精密スコープ＆詳細分析")
    st.info("TAB1・TAB2で抽出されたファンダ強者に対し、陣形の判定および詳細な個別チャート・業績推移を完全ローカルデータから出力します。")

    tab3_mode = st.radio("スキャンモードを選択してください", ["モード1：買い（反転上昇）", "モード2：空売り（奈落崩壊）"], horizontal=True)
    scan_mode = "buy" if "買い" in tab3_mode else "sell"

    # 🚨 TAB1/TAB2の結果オブジェクトを直接取得し、オブジェクトID（再スキャン検知）を取得
    t1_results = st.session_state.get('tab1_scan_results')
    t1_codes = []
    if t1_results:
        for r in t1_results:
            c = r.get('Code')
            if c: t1_codes.append(str(c)[:4])
    t1_codes_str = ",".join(list(dict.fromkeys(t1_codes)))
    t1_id = id(t1_results) if t1_results is not None else 0

    t2_results = st.session_state.get('tab2_scan_results')
    t2_codes = []
    if t2_results:
        for r in t2_results:
            c = r.get('Code')
            if c: t2_codes.append(str(c)[:4])
    t2_codes_str = ",".join(list(dict.fromkeys(t2_codes)))
    t2_id = id(t2_results) if t2_results is not None else 0

    # 🚨 内部Storeの初期化
    if "tab3_store_buy" not in st.session_state:
        st.session_state["tab3_store_buy"] = t1_codes_str
    if "tab3_store_sell" not in st.session_state:
        st.session_state["tab3_store_sell"] = t2_codes_str
        
    if "tab3_last_t1_id" not in st.session_state:
        st.session_state["tab3_last_t1_id"] = t1_id
    if "tab3_last_t2_id" not in st.session_state:
        st.session_state["tab3_last_t2_id"] = t2_id
        
    if "tab3_last_t1_str" not in st.session_state:
        st.session_state["tab3_last_t1_str"] = t1_codes_str
    if "tab3_last_t2_str" not in st.session_state:
        st.session_state["tab3_last_t2_str"] = t2_codes_str

    # 🚨 TAB1/TAB2でスキャン結果が更新された瞬間のみStoreを強制上書き
    # 文字列が同一でも、再スキャンによってオブジェクトIDが変化すれば強制上書きを発動する
    if st.session_state["tab3_last_t1_id"] != t1_id or st.session_state["tab3_last_t1_str"] != t1_codes_str:
        st.session_state["tab3_store_buy"] = t1_codes_str
        st.session_state["tab3_last_t1_id"] = t1_id
        st.session_state["tab3_last_t1_str"] = t1_codes_str

    if st.session_state["tab3_last_t2_id"] != t2_id or st.session_state["tab3_last_t2_str"] != t2_codes_str:
        st.session_state["tab3_store_sell"] = t2_codes_str
        st.session_state["tab3_last_t2_id"] = t2_id
        st.session_state["tab3_last_t2_str"] = t2_codes_str

    store_key = "tab3_store_buy" if scan_mode == "buy" else "tab3_store_sell"

    st.markdown("#### 📡 分析対象銘柄（最大30件まで強制表示）")
    
    # 🚨 KeyErrorおよび空欄バグの完全粉砕仕様
    target_codes_input = st.text_area(
        "銘柄コード（カンマ区切り）。TAB1・TAB2の突破銘柄が自動入力されています。",
        value=st.session_state.get(store_key, ""),
        height=100
    )
    
    # ユーザーの手入力値は即座にStoreへ反映し、タブ切り替え時の状態喪失を防ぐ
    st.session_state[store_key] = target_codes_input

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

            # 🚨 マクロ地合い（下げ相場）の独立検知（空売り前提条件: 25日MA）
            is_macro_downtrend = False
            try:
                _macro_data = get_macro_weather()
                if _macro_data and "nikkei" in _macro_data:
                    _df_m = _macro_data["nikkei"]["df"].copy()
                    _close_col_m = next((c for c in ['AdjC', 'Close', 'close', 'C', 'c'] if c in _df_m.columns), None)
                    if _close_col_m and len(_df_m) >= 25:
                        _s_m = _df_m[_close_col_m]
                        if isinstance(_s_m, pd.DataFrame): _s_m = _s_m.iloc[:, 0]
                        _ma25_m = pd.to_numeric(_s_m, errors='coerce').rolling(window=25).mean().iloc[-1]
                        _price_m = _macro_data["nikkei"]["price"]
                        if pd.notna(_ma25_m) and _ma25_m > 0:
                            if ((_price_m / _ma25_m) - 1) * 100 < 0:
                                is_macro_downtrend = True
            except: pass

            # 🚨 空売りモード ＆ 上げ相場時の警告メッセージ出力（制限解除版）
            if scan_mode == "sell" and not is_macro_downtrend:
                st.warning("🚨 【絶対交戦規定 警告】現在のマクロ地合いは「上げ相場（現在値が日経25日MA以上）」です。上げ相場での空売りは致命的なリスクを伴うため、待機を強く推奨します。（※参考情報としてシグナル自体は強制表示します）")

            c_key = get_cache_key() if 'get_cache_key' in globals() else cache_key
            raw_all_data = get_hist_data_cached(c_key)

            if raw_all_data is None or raw_all_data.empty:
                st.error("⚠️ 全軍データ（キャッシュ）が見つかりません。先にTAB1かTAB2でデータ取得（索敵）を実行してください。")
            else:
                c_code_raw = 'Code' if 'Code' in raw_all_data.columns else ('code' if 'code' in raw_all_data.columns else None)
                if not c_code_raw:
                    st.error("⚠️ キャッシュデータに銘柄コード列が見つかりません。")
                else:
                    mask = raw_all_data[c_code_raw].astype(str).str[:4].isin(target_str_codes)
                    df_targets = raw_all_data[mask].copy()

                    analyzed_data = {}
                    try: local_fund_db = load_local_fundamentals_db()
                    except: local_fund_db = None

                    total_cnt = df_targets[c_code_raw].nunique() if not df_targets.empty else 1
                    if total_cnt == 0: total_cnt = 1
                    completed_cnt = 0

                    import pandas as pd
                    for code_str, group in df_targets.groupby(c_code_raw):
                        code_int = int(str(code_str)[:4])
                        completed_cnt += 1
                        
                        prog_val = min(completed_cnt / total_cnt, 1.0)
                        p_bar.progress(prog_val, text=f"🚀 フェーズ1：インメモリ陣形判定中... ({completed_cnt}/{total_cnt} 完了)")
                        
                        df = group.tail(260).reset_index(drop=True)
                        if df.empty or len(df) < 4: continue

                        turnover = 0.0
                        try:
                            q0 = df.iloc[-1]
                            v_col = 'Volume' if 'Volume' in df.columns else ('Vo' if 'Vo' in df.columns else None)
                            c_col = 'AdjC' if 'AdjC' in df.columns else ('Close' if 'Close' in df.columns else None)
                            if v_col and c_col: turnover = float(q0[v_col]) * float(q0[c_col])
                        except: pass

                        # 📊 チャート陣形の検知（表示要請により、マクロ地合いに関わらず空売りシグナルを強制抽出するため True 固定）
                        b_sigs, s_sigs = analyze_formation_history(df, is_macro_downtrend=True)
                        
                        # ------------------------------------
                        # 🎯 TAB3 独自の S/A/B 判定ロジック
                        # ------------------------------------
                        is_hit = False
                        rank_str = ""
                        rank_funda = "対象外"
                        rank_signal = "対象外"

                        # ① シグナル発生日（鮮度）判定
                        date_col = 'Date' if 'Date' in df.columns else df.columns[0]
                        df_dates = df[date_col].dt.date.tolist() if pd.api.types.is_datetime64_any_dtype(df[date_col]) else pd.to_datetime(df[date_col]).dt.date.tolist()
                        
                        if scan_mode == "buy" and b_sigs:
                            b_sig_dates = [pd.to_datetime(d).date() for d in b_sigs if pd.notna(d)]
                            sig_indices = [i for i, d in enumerate(df_dates) if d in b_sig_dates]
                            if sig_indices:
                                days_ago = (len(df_dates) - 1) - max(sig_indices)
                                # 🚨 要件適合化：本日を含む3日以内(0,1,2)はS、4日以内(3)はA、5日以内(4)はB
                                if days_ago <= 2: rank_signal = "S"
                                elif days_ago == 3: rank_signal = "A"
                                elif days_ago == 4: rank_signal = "B"
                        
                        elif scan_mode == "sell" and s_sigs:
                            s_sig_dates = [pd.to_datetime(d).date() for d in s_sigs if pd.notna(d)]
                            sig_indices = [i for i, d in enumerate(df_dates) if d in s_sig_dates]
                            if sig_indices:
                                days_ago = (len(df_dates) - 1) - max(sig_indices)
                                if days_ago == 0: rank_signal = "S"
                                elif days_ago == 1: rank_signal = "A"
                                elif days_ago <= 3: rank_signal = "B"

                        # ② ファンダメンタルズ判定
                        f_df = fetch_fundamental_history_local(code_int, local_fund_db)
                        latest_ord_pct = -9999.0  # 第2ソート用の初期値（データ欠損時は最下位へ）
                        
                        if f_df is not None and not f_df.empty:
                            q1_row = f_df[f_df["期間"] == "直近 Q1"]
                            q2_row = f_df[f_df["期間"] == "直近 Q2"]
                            
                            def get_val(r, col):
                                if r.empty: return None
                                v = r[col].iloc[0]
                                if isinstance(v, str) and v == "-": return None
                                try: return float(v)
                                except: return None

                            # 🚨 直近Q1の経常益(%)を取得し、ソート用に保持
                            _tmp_ord = get_val(q1_row, "経常益(%)")
                            if _tmp_ord is not None:
                                latest_ord_pct = _tmp_ord

                            if scan_mode == "buy":
                                q1_s = get_val(q1_row, "売上(%)")
                                q1_op = get_val(q1_row, "営業益(%)")
                                q1_ord = get_val(q1_row, "経常益(%)")
                                q1_np = get_val(q1_row, "純利益(%)")
                                q1_eps = get_val(q1_row, "EPS(%)")
                                
                                q2_s = get_val(q2_row, "売上(%)")
                                q2_op = get_val(q2_row, "営業益(%)")
                                q2_ord = get_val(q2_row, "経常益(%)")
                                q2_np = get_val(q2_row, "純利益(%)")
                                q2_eps = get_val(q2_row, "EPS(%)")
                                
                                def count_misses(s, op, ord_p, np_p, eps):
                                    if None in [s, op, ord_p, np_p, eps]: return 99 
                                    m = 0
                                    if s < 7.0: m += 1
                                    if op < 20.0: m += 1
                                    if ord_p < 20.0: m += 1
                                    if np_p < 20.0: m += 1
                                    if eps < 20.0: m += 1
                                    return m
                                    
                                q1_miss = count_misses(q1_s, q1_op, q1_ord, q1_np, q1_eps)
                                q2_miss = count_misses(q2_s, q2_op, q2_ord, q2_np, q2_eps)
                                
                                if q1_miss == 0:
                                    if q2_miss == 0: rank_funda = "S"
                                    elif q2_miss == 1: rank_funda = "A"
                                    elif 2 <= q2_miss <= 4: rank_funda = "B"
                                
                            elif scan_mode == "sell":
                                if not q1_row.empty and not q2_row.empty:
                                    q1_op = get_val(q1_row, "営業益(%)")
                                    q1_ord = get_val(q1_row, "経常益(%)")
                                    q1_np = get_val(q1_row, "純利益(%)")
                                    q1_eps = get_val(q1_row, "EPS(%)")
                                    
                                    q2_op = get_val(q2_row, "営業益(%)")
                                    q2_ord = get_val(q2_row, "経常益(%)")
                                    q2_np = get_val(q2_row, "純利益(%)")
                                    q2_eps = get_val(q2_row, "EPS(%)")
                                    
                                    vals = [q1_op, q1_ord, q1_np, q1_eps, q2_op, q2_ord, q2_np, q2_eps]
                                    if None not in vals:
                                        lt_5 = sum(1 for v in vals if v < 5.0)
                                        lt_8 = sum(1 for v in vals if v < 8.0)
                                        
                                        if lt_8 == 8:
                                            if lt_5 == 8: rank_funda = "S"
                                            elif lt_5 == 7: rank_funda = "A"
                                            elif lt_5 == 6: rank_funda = "B"

                        # ③ 総合判定の結合
                        if scan_mode == "buy":
                            if rank_funda != "対象外" and rank_signal != "対象外":
                                is_hit = True
                            rank_str = f"🎯業績:{rank_funda}級 / 陣形:{rank_signal}級"
                        elif scan_mode == "sell":
                            if rank_funda != "対象外" and rank_signal != "対象外":
                                is_hit = True
                            rank_str = f"💀業績:{rank_funda}級 / 陣形:{rank_signal}級"

                        analyzed_data[code_int] = {
                            "df": df, "is_hit": is_hit, "rank": rank_str, 
                            "latest_ord_pct": latest_ord_pct, "turnover": turnover,
                            "buy_sigs": b_sigs, "sell_sigs": s_sigs, "fund": f_df
                        }

                    p_bar.progress(1.0, text="⚙️ データベースをマウント中（フェーズ2準備）...")
                    
                    def get_rank_score(data):
                        score = 0
                        r = data["rank"]
                        
                        if "業績:S" in r: score += 300
                        elif "業績:A" in r: score += 200
                        elif "業績:B" in r: score += 100
                        
                        if "陣形:S" in r: score += 300
                        elif "陣形:A" in r: score += 200
                        elif "陣形:B" in r: score += 100
                        
                        return (score, data.get("latest_ord_pct", -9999.0), data.get("turnover", 0.0))
                        
                    sortable_results = [{"code": k, **v} for k, v in analyzed_data.items()]
                    sortable_results.sort(key=get_rank_score, reverse=True)
                    
                    display_targets = sortable_results[:30]

                    name_map = {}
                    try:
                        m_df = load_master()
                        name_map = dict(zip(m_df['Code'].astype(str).str[:4], m_df['CompanyName']))
                    except: pass
                    
                    p_bar.empty()
                    st.divider()

                    import plotly.graph_objects as go
                    import numpy as np
                    
                    hit_count = sum(1 for d in sortable_results if d["is_hit"])
                    if hit_count > 0:
                        st.success(f"🎯 陣形とファンダメンタルズが完全合致した銘柄: {hit_count}件 確認！ （分析対象 上位最大30件を表示します）")
                    else:
                        st.error("📉 条件に完全合致する銘柄はありませんでした。分析データを強制表示します。")

                    for idx, data in enumerate(display_targets):
                        code = data['code']
                        df = data["df"]
                        c_name = name_map.get(str(code)[:4], "名称不明")
                        
                        hit_badge = data["rank"]
                        st.markdown(f"### 📦 {code} {c_name} | {hit_badge}")
                        
                        if len(df) > 0:
                            df_c = df.copy()
                            
                            cols_lower = {str(c).lower(): c for c in df_c.columns}
                            c_o_col = cols_lower.get('adjo', cols_lower.get('adjustmentopen', cols_lower.get('o', cols_lower.get('open', 'Open'))))
                            c_h_col = cols_lower.get('adjh', cols_lower.get('adjustmenthigh', cols_lower.get('h', cols_lower.get('high', 'High'))))
                            c_l_col = cols_lower.get('adjl', cols_lower.get('adjustmentlow', cols_lower.get('l', cols_lower.get('low', 'Low'))))
                            c_c_col = cols_lower.get('adjc', cols_lower.get('adjustmentclose', cols_lower.get('c', cols_lower.get('close', 'Close'))))
                            c_v_col = cols_lower.get('adjv', cols_lower.get('adjustmentvolume', cols_lower.get('v', cols_lower.get('volume', cols_lower.get('vo', 'Volume')))))
                            
                            for col in [c_o_col, c_h_col, c_l_col, c_c_col, c_v_col]:
                                if col not in df_c.columns:
                                    df_c[col] = 0.0
                                else:
                                    df_c[col] = df_c[col].ffill().fillna(0.0)
                                    
                            if 'MA18' not in df_c.columns: df_c['MA18'] = df_c[c_c_col].rolling(18).mean().ffill().fillna(0.0)
                            if 'MA50' not in df_c.columns: df_c['MA50'] = df_c[c_c_col].rolling(50).mean().ffill().fillna(0.0)
                            
                            delta = df_c[c_c_col].diff()
                            gain = delta.clip(lower=0).ewm(alpha=1/14, adjust=False).mean()
                            loss = (-delta.clip(upper=0)).ewm(alpha=1/14, adjust=False).mean()
                            rs = gain / loss.replace(0, 1e-10)
                            df_c['RSI14'] = 100 - (100 / (1 + rs))
                            
                            df_c['RSI14'] = df_c['RSI14'].replace([np.inf, -np.inf], 50.0).fillna(50.0)

                            def safe_float(val):
                                if pd.isna(val) or val is None or str(val).strip() == "": return 0.0
                                try: 
                                    v = float(val)
                                    if np.isnan(v) or np.isinf(v): return 0.0
                                    return v
                                except: return 0.0

                            q0 = df_c.iloc[-1]
                            c_o = safe_float(q0.get(c_o_col, 0))
                            c_h = safe_float(q0.get(c_h_col, 0))
                            c_l = safe_float(q0.get(c_l_col, 0))
                            c_c = safe_float(q0.get(c_c_col, 0))
                            rsi_val = safe_float(q0.get('RSI14', 50.0))
                            
                            c1, c2, c3, c4, c5 = st.columns(5)
                            c1.metric("始値", f"{c_o:,.1f}円")
                            c2.metric("高値", f"{c_h:,.1f}円")
                            c3.metric("安値", f"{c_l:,.1f}円")
                            c4.metric("終値", f"{c_c:,.1f}円")
                            c5.metric("RSI(14日)", f"{rsi_val:.1f}%")
                            
                            fig = go.Figure()
                            date_col = 'Date' if 'Date' in df_c.columns else df_c.columns[0]
                            df_c[date_col] = pd.to_datetime(df_c[date_col], errors='coerce')
                            df_c = df_c.dropna(subset=[date_col]).copy()
                            
                            fig.add_trace(go.Candlestick(
                                x=df_c[date_col], 
                                open=df_c[c_o_col], 
                                high=df_c[c_h_col], 
                                low=df_c[c_l_col], 
                                close=df_c[c_c_col], 
                                name='価格',
                                increasing_line_color='#26a69a', increasing_fillcolor='#26a69a',
                                decreasing_line_color='#ef5350', decreasing_fillcolor='#ef5350'
                            ))
                            fig.add_trace(go.Scatter(x=df_c[date_col], y=df_c['MA18'], mode='lines', line=dict(color='orange', width=1.5), name='18日線', hoverinfo='none'))
                            fig.add_trace(go.Scatter(x=df_c[date_col], y=df_c['MA50'], mode='lines', line=dict(color='cyan', width=1.5), name='50日線', hoverinfo='none'))
                            
                            if scan_mode == "buy" and data.get("buy_sigs"):
                                sig_dates = [pd.to_datetime(d).date() for d in data["buy_sigs"] if pd.notna(d)]
                                sig_df = df_c[df_c[date_col].dt.date.isin(sig_dates)]
                                if not sig_df.empty: fig.add_trace(go.Scatter(x=sig_df[date_col], y=sig_df[c_c_col] * 0.95, mode='markers', marker=dict(symbol='triangle-up', color='magenta', size=12), name='買陣形'))
                            
                            if scan_mode == "sell" and data.get("sell_sigs"):
                                sig_dates = [pd.to_datetime(d).date() for d in data["sell_sigs"] if pd.notna(d)]
                                sig_df = df_c[df_c[date_col].dt.date.isin(sig_dates)]
                                if not sig_df.empty: fig.add_trace(go.Scatter(x=sig_df[date_col], y=sig_df[c_c_col] * 1.05, mode='markers', marker=dict(symbol='triangle-down', color='yellow', size=12), name='空売陣形'))

                            v_colors = ['#26a69a' if c >= o else '#ef5350' for c, o in zip(df_c[c_c_col], df_c[c_o_col])]
                            fig.add_trace(go.Bar(
                                x=df_c[date_col], 
                                y=df_c[c_v_col], 
                                name='出来高', 
                                marker_color=v_colors, 
                                yaxis='y2',
                                opacity=0.5
                            ))

                            if len(df_c) > 65:
                                df_recent = df_c.tail(65)
                                t_min = df_recent[date_col].iloc[0]
                                t_max = df_recent[date_col].iloc[-1] + pd.Timedelta(days=3)
                                
                                max_h = float(df_recent[c_h_col].max())
                                min_l = float(df_recent[c_l_col].min())
                                
                                if pd.isna(max_h) or pd.isna(min_l) or (max_h == 0.0 and min_l == 0.0):
                                    y_min, y_max = None, None
                                elif max_h == min_l:
                                    y_min, y_max = min_l * 0.9, max_h * 1.1
                                else:
                                    y_min = min_l * 0.98
                                    y_max = max_h * 1.05
                            else:
                                t_min = df_c[date_col].iloc[0]
                                t_max = df_c[date_col].iloc[-1] + pd.Timedelta(days=3)
                                y_min, y_max = None, None
                                
                            x_min_str = t_min.strftime('%Y-%m-%d') if pd.notna(t_min) else None
                            x_max_str = t_max.strftime('%Y-%m-%d') if pd.notna(t_max) else None
                            
                            xaxis_config = dict(
                                anchor='y2', 
                                rangeslider=dict(visible=False), 
                                type='date', 
                                fixedrange=False,
                                rangeselector=dict(
                                    buttons=list([
                                        dict(count=1, label="1ヶ月", step="month", stepmode="backward"),
                                        dict(count=3, label="3ヶ月", step="month", stepmode="backward"),
                                        dict(count=6, label="6ヶ月", step="month", stepmode="backward"),
                                        dict(step="all", label="1年")
                                    ]),
                                    bgcolor="rgba(38,166,154,0.2)",
                                    font=dict(color="#26a69a")
                                )
                            )
                            if x_min_str and x_max_str:
                                xaxis_config['range'] = [x_min_str, x_max_str]

                            layout_args = {
                                'height': 600,
                                'margin': dict(l=10, r=50, t=60, b=10),
                                'xaxis': xaxis_config,
                                'dragmode': 'pan',
                                'hovermode': 'x unified',
                                'hoverlabel': dict(bgcolor="rgba(0,0,0,0.8)", font_size=13, font_family="sans-serif", align="left")
                            }
                            
                            if y_min and y_max:
                                layout_args['yaxis'] = dict(domain=[0.20, 1.0], range=[y_min, y_max], autorange=False, fixedrange=False)
                            else:
                                layout_args['yaxis'] = dict(domain=[0.20, 1.0], autorange=True, fixedrange=False)

                            layout_args['yaxis2'] = dict(domain=[0.0, 0.30], rangemode='tozero', autorange=True, fixedrange=False, showticklabels=False, showgrid=False)
                                
                            fig.update_layout(**layout_args)
                            
                            st.caption("💡 **狙撃手マニュアル**: 初期表示は直近3ヶ月にオートフォーカスしています。過去に遡ってローソク足が見切れた場合は、右側の価格軸（Y軸の数字）を直接上下にドラッグするか、チャート内で **ダブルクリック** するとY軸が自動追従（オートフィット）します。")
                            st.plotly_chart(fig, use_container_width=True, config={'scrollZoom': True, 'displayModeBar': True}, key=f"tab3_chart_{code}_{scan_mode}_{idx}")

                        if data.get("fund") is not None and not data["fund"].empty:
                            st.markdown("##### 📊 業績成長率（YoY 前年同期比）")
                            try:
                                def fmt_pct(x):
                                    if pd.isna(x): return "-"
                                    if isinstance(x, str): return x
                                    return f"{x:.1f}%"
                                    
                                pct_cols = [c for c in ["売上(%)", "営業益(%)", "経常益(%)", "純利益(%)", "EPS(%)"] if c in data["fund"].columns]
                                
                                styled_df = data["fund"].style.format({
                                    c: fmt_pct for c in pct_cols
                                }).set_properties(subset=pct_cols, **{'text-align': 'right'})
                                
                                st.dataframe(styled_df, use_container_width=True)
                            except Exception:
                                st.dataframe(data["fund"], use_container_width=True)
                        else:
                            db_status = "ロード済" if local_fund_db is not None else "未取得・空"
                            st.info(f"ℹ️ 業績データが取得できませんでした。（ローカルDB状態: {db_status}）")
                            
                        st.divider()

            results_tab3 = [{"Code": d["code"], "Rank": d["rank"], "Mode": scan_mode} for d in display_targets]
            if results_tab3:
                hit_codes_str = ",".join([str(r["Code"]) for r in results_tab3])
                st.text_area("📋 分析対象銘柄（コピペ用・上位30件）", value=hit_codes_str, height=70)
                
            st.session_state['tab3_results'] = results_tab3

# ==========================================
# 📁 TAB7: 戦績ダッシュボード
# ==========================================
with tab7:
    import datetime as dt_module
    st.markdown('<h3 style="font-size: clamp(14px, 4.5vw, 24px); margin-bottom: 1rem;">📁 事後任務報告 (AAR) & 戦績ダッシュボード</h3>', unsafe_allow_html=True)
    st.caption("※ 記録の編集は下部の『🛠️ 戦績編集コンソール』で行ってください。")
    
    def get_scale_for_code(code):
        master_df = load_master()
        api_code = str(code) if len(str(code)) >= 5 else str(code) + "0"
        if not master_df.empty:
            m_row = master_df[master_df['Code'].astype(str) == api_code]
            if not m_row.empty:
                scale_val = str(m_row.iloc[0].get('Market', ''))
                return "🏢 大型/中型" if any(x in scale_val for x in ["Core30", "Large70", "Mid400", "プライム"]) else "🚀 小型/新興"
        return "不明"

    if 'aar_df_stable' not in st.session_state:
        df_l = load_db_to_df(WS_AAR, ["決済日", "銘柄", "規模", "戦術", "買値", "売値", "株数", "損益額(円)", "損益(%)", "規律", "敗因/勝因メモ"])
        if not df_l.empty:
            df_l['決済日'] = df_l['決済日'].astype(str)
            df_l['銘柄'] = df_l['銘柄'].astype(str).str.replace(r'\.0$', '', regex=True)
            for c in ['買値', '売値', '株数', '損益額(円)', '損益(%)']:
                if c in df_l.columns: df_l[c] = pd.to_numeric(df_l[c], errors='coerce').fillna(0)
            st.session_state.aar_df_stable = df_l.sort_values(['決済日', '銘柄'], ascending=[False, True]).reset_index(drop=True)
        else: st.session_state.aar_df_stable = df_l

    col_a1, col_a2 = st.columns([1, 2.2])
    
    with col_a1:
        st.markdown("#### 📝 戦果報告フォーム")
        with st.form(key="aar_form_v10_final", clear_on_submit=False):
            c_f1, c_f2 = st.columns(2)
            f_date = c_f1.date_input("決済日", value=dt_module.date.today())
            f_code = c_f2.text_input("銘柄コード", max_chars=4)
            f_tactics = st.selectbox("使用した戦術", options=["🌐 待伏 (押し目)", "⚡ 強襲 (順張り)", "⚠️ その他"])
            c_f3, c_f4, c_f5 = st.columns(3)
            f_buy = c_f3.number_input("買値", min_value=0.0, step=1.0, format="%.0f")
            f_sell = c_f4.number_input("売値", min_value=0.0, step=1.0, format="%.0f")
            f_lot = c_f5.number_input("株数", min_value=100, step=100)
            f_rule = st.radio("規律を守ったか？", options=["✅ 遵守した (冷徹な狙撃)", "❌ 破った (感情・焦り・妥協)"])
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
            save_aar_btn = st.form_submit_button("💾 戦績の変更を確定し、Google DBへ同期", use_container_width=True, type="primary")

        if save_aar_btn:
            st.session_state.aar_df_stable = working_log_df.copy()
            for col in ["買値", "売値", "株数", "損益額(円)"]:
                st.session_state.aar_df_stable[col] = pd.to_numeric(st.session_state.aar_df_stable[col], errors='coerce').fillna(0).astype(int)
            save_aar_db(st.session_state.aar_df_stable)
            st.success("✅ Google Sheetsへの完全同期・色彩規律の再適用を完了しました。")
            st.rerun()

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

gc.collect()
