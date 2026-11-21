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

# ==========================================
# ☁️ 究極永続化ストレージ（Google Sheets 直結・マルチテナント基盤）
# ==========================================
import gspread
from google.oauth2.service_account import Credentials

SPREADSHEET_ID = "1PZZwhGvUgTHd0ptY2g9AmLloZoB9qZpr-VIx6DrYIdw"
WS_AUTH_MASTER = "AUTH_MASTER"
AUTH_MASTER_HEADERS = ["access_code", "status", "role", "memo"]
AUTH_MASTER_DEFAULTS = [
    ["sniper", "active", "admin", ""],
    ["senyu001", "active", "user", ""],
    ["senyu002", "active", "user", ""],
]
SCAN_STATE_KEYS = [
    "tab1_filters",
    "tab1_results",
    "tab2_filters",
    "tab2_results",
    "tab3_state",
]

def get_now_jst_str():
    try:
        tz = pytz.timezone('Asia/Tokyo')
        return datetime.now(tz).strftime('%Y-%m-%d %H:%M:%S JST')
    except Exception:
        return (datetime.utcnow() + timedelta(hours=9)).strftime('%Y-%m-%d %H:%M:%S JST')

@st.cache_resource
def init_gspread():
    if "gcp_service_account" not in st.secrets:
        return None
    scopes = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
    gcp_credentials = dict(st.secrets["gcp_service_account"])
    gcp_credentials["private_key"] = gcp_credentials["private_key"].replace('\\n', '\n')
    creds = Credentials.from_service_account_info(gcp_credentials, scopes=scopes)
    return gspread.authorize(creds)

def get_db_sheet():
    try:
        client = init_gspread()
        if not client:
            return None
        return client.open_by_key(SPREADSHEET_ID)
    except Exception as e:
        print(f"Google Sheets接続エラー: {e}")
        return None

def _ws_update_compat(ws, range_name, values):
    try:
        ws.update(values=values, range_name=range_name)
    except TypeError:
        ws.update(range_name, values)

def load_auth_master():
    """AUTH_MASTERを文字列ベースで厳密取得する。未存在時は初期レコードで自動作成。通信障害時はNoneを返す（案A：全ログインブロック）。"""
    sheet = get_db_sheet()
    if not sheet:
        return None, "🚨 Google Sheets との接続に失敗しました。安全のためログインをブロックしています。"

    try:
        try:
            ws = sheet.worksheet(WS_AUTH_MASTER)
        except gspread.exceptions.WorksheetNotFound:
            ws = sheet.add_worksheet(title=WS_AUTH_MASTER, rows="100", cols="10")
            init_rows = [AUTH_MASTER_HEADERS] + AUTH_MASTER_DEFAULTS
            _ws_update_compat(ws, "A1:D4", init_rows)

        all_values = ws.get_all_values()
        if not all_values:
            init_rows = [AUTH_MASTER_HEADERS] + AUTH_MASTER_DEFAULTS
            _ws_update_compat(ws, "A1:D4", init_rows)
            all_values = init_rows

        headers = [str(h).strip().lower() for h in all_values[0]]
        idx_code = headers.index("access_code") if "access_code" in headers else 0
        idx_status = headers.index("status") if "status" in headers else 1
        idx_role = headers.index("role") if "role" in headers else 2
        idx_memo = headers.index("memo") if "memo" in headers else 3

        auth_map = {}
        for row in all_values[1:]:
            code = str(row[idx_code]).strip() if len(row) > idx_code else ""
            if not code:
                continue
            status = str(row[idx_status]).strip().lower() if len(row) > idx_status else ""
            role = str(row[idx_role]).strip().lower() if len(row) > idx_role else "user"
            memo = str(row[idx_memo]).strip() if len(row) > idx_memo else ""
            auth_map[code] = {
                "status": status,
                "role": role if role else "user",
                "memo": memo,
            }
        return auth_map, ""
    except Exception as e:
        print(f"AUTH_MASTER取得エラー: {e}")
        return None, "🚨 認証マスタ（AUTH_MASTER）の読み込みに失敗しました。安全のためログインをブロックしています。"

def clear_user_session_state():
    """ユーザー切替・ログイン完了時にTAB1〜TAB3・TAB7のセッション残留を完全にクリアする。"""
    exact_keys = [
        "user_scan_state",
        "scan_state_loaded_user",
        "tab1_scan_results",
        "tab1_scan_updated_at",
        "tab2_scan_results",
        "tab2_scan_updated_at",
        "tab3_results",
        "tab3_updated_at",
        "tab3_last_mode",
        "tab3_store_buy",
        "tab3_store_sell",
        "tab3_manual_codes",
        "tab3_last_t1_id",
        "tab3_last_t2_id",
        "tab3_last_t1_str",
        "tab3_last_t2_str",
        "tab3_mode_radio",
        "t1_period",
        "t1_sales_r",
        "t1_ord_r",
        "t1_mcap",
        "t1_p_min",
        "t1_p_max",
        "t1_sec_all",
        "t2_period",
        "t2_ord_r",
        "t2_mcap",
        "t2_vol",
        "t2_p_min",
        "t2_p_max",
        "t2_sec_all",
        "aar_df_stable",
        "aar_loaded_user",
        "aar_start_date",
        "aar_end_date",
        "aar_editor_maintenance_fixed",
        "confirm_aar_delete",
        "system_data_error",
        "system_error_message",
    ]
    for k in exact_keys:
        st.session_state.pop(k, None)
    for k in list(st.session_state.keys()):
        if k.startswith("t1_sec_") or k.startswith("t2_sec_"):
            st.session_state.pop(k, None)

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
                cleaned_code = acc_code.strip()
                if cleaned_code != "":
                    auth_map, err_msg = load_auth_master()
                    if auth_map is None:
                        st.error(err_msg)
                    elif cleaned_code in auth_map:
                        user_info = auth_map[cleaned_code]
                        if user_info.get("status") == "active":
                            clear_user_session_state()
                            st.session_state["password_correct"] = True
                            st.session_state["current_user"] = cleaned_code
                            st.session_state["current_user_role"] = user_info.get("role", "user")
                            st.session_state["current_user_memo"] = user_info.get("memo", "")
                            st.rerun()
                        else:
                            st.error("🚨 認証失敗：このアクセスコードは現在停止されています。")
                    else:
                        st.error("🚨 認証失敗：コードが違います。")
        return False
    return True

if not check_password(): st.stop()

def _get_db_file_fingerprint(*filenames):
    """対象DBファイルの更新時刻（ns）とファイルサイズから極小コストで指紋文字列を生成する。"""
    base_dir = os.path.dirname(__file__)
    for fname in filenames:
        fpath = os.path.join(base_dir, fname)
        if os.path.exists(fpath):
            try:
                st_info = os.stat(fpath)
                return f"{fname}_{st_info.st_mtime_ns}_{st_info.st_size}"
            except Exception:
                continue
    return "missing"

def get_cache_key():
    from datetime import datetime as _dt, timedelta as _td
    file_sig = _get_db_file_fingerprint("prices_db.pkl.gz")
    try:
        tz = pytz.timezone('Asia/Tokyo')
        now = _dt.now(tz)
        if now.hour < 19:
            reset_base = (now - _td(days=1)).replace(hour=19, minute=0, second=0, microsecond=0)
        else:
            reset_base = now.replace(hour=19, minute=0, second=0, microsecond=0)
        return f"iron_rule_v2026_{reset_base.strftime('%Y%m%d_%H')}_{file_sig}"
    except Exception:
        return f"{_dt.now().strftime('%Y%m%d_%H')}_{file_sig}"

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
user_memo = st.session_state.get("current_user_memo", "").strip()
display_user_label = f"({user_memo} / ID: {user_id})" if user_memo else f"(ID: {user_id})"
st.markdown(f'<h1 style="font-size: clamp(24px, 7vw, 42px); font-weight: 900; border-bottom: 2px solid #2e7d32; padding-bottom: 0.5rem; margin-bottom: 1rem;">🎯 戦術スコープ『鉄の掟』 <span style="font-size: 16px; font-weight: normal; color: #888;">{display_user_label}</span></h1>', unsafe_allow_html=True)

# 🚨 先日の「API通信エラーによるシステム白画面化」を防ぐ完全防弾処理
db_sheet = get_db_sheet()

def get_or_create_worksheet(sheet_name, rows="1000", cols="20"):
    if not db_sheet: return None
    try: return db_sheet.worksheet(sheet_name)
    except gspread.exceptions.WorksheetNotFound:
        try: return db_sheet.add_worksheet(title=sheet_name, rows=str(rows), cols=str(cols))
        except Exception as e:
            if not st.session_state.get('system_data_error', False):
                st.session_state['system_data_error'] = True
                st.session_state['system_error_message'] = "Google Sheets API 通信障害（シート作成失敗）。現在の表示データは不完全です。"
                st.rerun()
            return None
    except Exception as e:
        # 🚨 無言で空データを返すフェイルセーフを撤廃。エラーを捕捉しシステムロックフラグを発火させる。
        if not st.session_state.get('system_data_error', False):
            st.session_state['system_data_error'] = True
            st.session_state['system_error_message'] = "Google Sheets / J-Quants API 等の通信障害。データが不完全です。"
            st.rerun() # UI最下部で発火した場合に備え、直ちにリロードして上部の物理ロックを適用
        return None

# 🚨 マルチテナント（戦友分離）の核心：認証されたアクセスコードをシート名に強制バインド
_active_user = st.session_state.get("current_user", "Guest")
WS_AAR = f"交戦DB_{_active_user}"
WS_SCAN_STATE = f"SCAN_STATE_{_active_user}"

def _default_scan_state_dict():
    return {k: {} for k in SCAN_STATE_KEYS}

def _build_scan_state_rows(state_dict, updated_map):
    rows = [["key", "payload_json", "updated_at"]]
    for k in SCAN_STATE_KEYS:
        payload_obj = state_dict.get(k, {})
        payload_str = json.dumps(payload_obj, ensure_ascii=False, separators=(",", ":"))
        if len(payload_str) > 49000:
            payload_str = "{}"
        rows.append([k, payload_str, updated_map.get(k, "")])
    return rows

def ensure_user_scan_state_loaded():
    """ログイン直後に1回だけ SCAN_STATE_{ID} を一括ロードし、st.session_stateへ展開する（429対策）。"""
    uid = st.session_state.get("current_user", "Guest")
    if st.session_state.get("scan_state_loaded_user") == uid and "user_scan_state" in st.session_state:
        return st.session_state["user_scan_state"]

    state_dict = _default_scan_state_dict()
    updated_map = {k: "" for k in SCAN_STATE_KEYS}
    ws = get_or_create_worksheet(f"SCAN_STATE_{uid}", rows="10", cols="5")
    if ws:
        try:
            all_values = ws.get_all_values()
            if not all_values:
                _ws_update_compat(ws, "A1:C6", _build_scan_state_rows(state_dict, updated_map))
            else:
                for row in all_values[1:]:
                    if len(row) < 1:
                        continue
                    k = str(row[0]).strip()
                    if k in state_dict:
                        raw_json = row[1] if len(row) > 1 else "{}"
                        upd = row[2] if len(row) > 2 else ""
                        try:
                            parsed = json.loads(raw_json) if raw_json else {}
                            if isinstance(parsed, dict):
                                state_dict[k] = parsed
                        except Exception:
                            state_dict[k] = {}
                        updated_map[k] = str(upd)
        except Exception as e:
            print(f"SCAN_STATE読み込みエラー({uid}): {e}")

    st.session_state["user_scan_state"] = state_dict
    st.session_state["user_scan_state_updated"] = updated_map
    st.session_state["scan_state_loaded_user"] = uid

    # TAB1〜TAB3 結果をセッションへ初回展開
    t1_res_block = state_dict.get("tab1_results", {})
    if isinstance(t1_res_block.get("results"), list):
        st.session_state["tab1_scan_results"] = t1_res_block["results"]
        st.session_state["tab1_scan_updated_at"] = t1_res_block.get("updated_at", updated_map.get("tab1_results", ""))

    t2_res_block = state_dict.get("tab2_results", {})
    if isinstance(t2_res_block.get("results"), list):
        st.session_state["tab2_scan_results"] = t2_res_block["results"]
        st.session_state["tab2_scan_updated_at"] = t2_res_block.get("updated_at", updated_map.get("tab2_results", ""))

    t3_block = state_dict.get("tab3_state", {})
    if isinstance(t3_block.get("results"), list):
        st.session_state["tab3_results"] = t3_block["results"]
        st.session_state["tab3_updated_at"] = t3_block.get("updated_at", updated_map.get("tab3_state", ""))
        st.session_state["tab3_last_mode"] = t3_block.get("mode", "buy")

    return state_dict

def save_user_scan_state(updates_dict):
    """指定されたキー群をメモリキャッシュと SCAN_STATE_{ID}（固定6行 A1:C6）へ1回のAPIコールで完全上書き保存する。"""
    uid = st.session_state.get("current_user", "Guest")
    state_dict = ensure_user_scan_state_loaded()
    updated_map = st.session_state.get("user_scan_state_updated", {k: "" for k in SCAN_STATE_KEYS})
    now_str = get_now_jst_str()

    for k, v in updates_dict.items():
        if k in SCAN_STATE_KEYS:
            state_dict[k] = v
            updated_map[k] = now_str

    st.session_state["user_scan_state"] = state_dict
    st.session_state["user_scan_state_updated"] = updated_map

    ws = get_or_create_worksheet(f"SCAN_STATE_{uid}", rows="10", cols="5")
    if ws:
        try:
            rows = _build_scan_state_rows(state_dict, updated_map)
            _ws_update_compat(ws, "A1:C6", rows)
        except Exception as e:
            print(f"SCAN_STATE書き込みエラー({uid}): {e}")

# ログイン直後に該当ユーザーの状態を一括ロード
ensure_user_scan_state_loaded()

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
            _ws_update_compat(ws, "A1", data)
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
WS_MACRO_CACHE = "MACRO_CACHE"

def _get_macro_cache_ws():
    """st.session_state / st.rerun に一切依存せず MACRO_CACHE シートを取得・自動作成する防弾関数。"""
    try:
        sheet = get_db_sheet() if "get_db_sheet" in globals() else None
        if sheet is None and "init_gspread" in globals():
            client = init_gspread()
            if client:
                sheet = client.open_by_key(SPREADSHEET_ID)
        if not sheet:
            return None
        try:
            return sheet.worksheet(WS_MACRO_CACHE)
        except gspread.exceptions.WorksheetNotFound:
            return sheet.add_worksheet(title=WS_MACRO_CACHE, rows="10", cols="5")
    except Exception as e:
        print(f"MACRO_CACHEシート接続エラー: {e}")
        return None

def _load_macro_cache_from_sheets():
    """Google Sheets（MACRO_CACHE）から保存済みの日経平均確定日足辞書 {YYYY-MM-DD: float} を読み込む。"""
    ws = _get_macro_cache_ws()
    if not ws:
        return {}
    try:
        all_values = ws.get_all_values()
        for row in all_values[1:]:
            if len(row) >= 3 and str(row[0]).strip() == "nikkei_daily":
                raw_json = str(row[2]).strip()
                if not raw_json:
                    return {}
                parsed = json.loads(raw_json)
                if isinstance(parsed, dict):
                    clean_map = {}
                    for k, v in parsed.items():
                        d_str = str(k).strip()[:10]
                        try:
                            fv = float(v)
                            if len(d_str) == 10 and pd.notna(fv) and fv > 0:
                                clean_map[d_str] = fv
                        except Exception:
                            pass
                    return clean_map
    except Exception as e:
        print(f"MACRO_CACHE読み込みエラー: {e}")
    return {}

def _save_macro_cache_to_sheets(price_map):
    """日経平均確定日足辞書を固定2行（A1:D2）で完全上書き保存する（容量増加ゼロ）。"""
    ws = _get_macro_cache_ws()
    if not ws or not price_map:
        return
    try:
        from datetime import datetime as _dt, timedelta as _td
        sorted_items = sorted(price_map.items())[-550:]
        trimmed_map = {k: round(float(v), 2) for k, v in sorted_items}
        latest_d = sorted_items[-1][0]
        payload_str = json.dumps(trimmed_map, ensure_ascii=False, separators=(",", ":"))
        if len(payload_str) > 49000:
            sorted_items = sorted_items[-400:]
            trimmed_map = {k: round(float(v), 2) for k, v in sorted_items}
            payload_str = json.dumps(trimmed_map, ensure_ascii=False, separators=(",", ":"))

        try:
            now_jst = _dt.now(pytz.timezone('Asia/Tokyo')).strftime('%Y-%m-%d %H:%M:%S JST')
        except Exception:
            now_jst = (_dt.utcnow() + _td(hours=9)).strftime('%Y-%m-%d %H:%M:%S JST')

        rows = [
            ["key", "latest_date", "payload_json", "updated_at"],
            ["nikkei_daily", latest_d, payload_str, now_jst],
        ]
        try:
            ws.update(values=rows, range_name="A1:D2")
        except TypeError:
            ws.update("A1:D2", rows)
    except Exception as e:
        print(f"MACRO_CACHE書き込みエラー: {e}")

@st.cache_data(ttl=600, show_spinner=False)
def get_macro_weather():
    try:
        import yfinance as yf
        from datetime import datetime as _dt, timedelta as _td

        try:
            today_jst_str = _dt.now(pytz.timezone('Asia/Tokyo')).strftime('%Y-%m-%d')
        except Exception:
            today_jst_str = (_dt.utcnow() + _td(hours=9)).strftime('%Y-%m-%d')

        fetched_map = {}
        tk = yf.Ticker("^N225")

        # 1. 日足データ取得（1年表示＋MA50計算バッファ確保のため2年分取得）
        try:
            df_raw = tk.history(period="2y")
            if df_raw is not None and not df_raw.empty:
                idx = df_raw.index
                if idx.tz is not None:
                    idx = idx.tz_convert('Asia/Tokyo').tz_localize(None)
                df_tmp = df_raw.copy()
                df_tmp.index = idx
                close_col = next((c for c in ['Close', 'close', 'C', 'c'] if c in df_tmp.columns), None)
                if close_col:
                    s_close = pd.to_numeric(df_tmp[close_col], errors='coerce').dropna()
                    for dt_idx, val in s_close.items():
                        fv = float(val)
                        d_str = pd.Timestamp(dt_idx).strftime('%Y-%m-%d')
                        if fv > 0 and d_str <= today_jst_str:
                            fetched_map[d_str] = fv
        except Exception as e:
            print(f"日経日足取得エラー: {e}")

        # 2. 第1層防衛：yfinance時間足（1h）による最新営業日欠落の補完（実約定値のみ採用）
        try:
            df_intra = tk.history(period="5d", interval="1h")
            if df_intra is not None and not df_intra.empty:
                idx_i = df_intra.index
                if idx_i.tz is not None:
                    idx_i = idx_i.tz_convert('Asia/Tokyo').tz_localize(None)
                df_i = df_intra.copy()
                df_i.index = idx_i
                close_col_i = next((c for c in ['Close', 'close', 'C', 'c'] if c in df_i.columns), None)
                if close_col_i:
                    s_intra = pd.to_numeric(df_i[close_col_i], errors='coerce').dropna()
                    s_intra = s_intra[s_intra > 0].sort_index()
                    if not s_intra.empty:
                        intra_last_d = pd.Timestamp(s_intra.index[-1]).strftime('%Y-%m-%d')
                        intra_last_v = float(s_intra.iloc[-1])
                        latest_daily_d = max(fetched_map.keys()) if fetched_map else ""
                        if intra_last_d <= today_jst_str and (not latest_daily_d or intra_last_d > latest_daily_d):
                            fetched_map[intra_last_d] = intra_last_v
        except Exception as e:
            print(f"日経時間足補完エラー: {e}")

        # 3. 第3層防衛：Google Sheets（MACRO_CACHE）とのマージによる巻き戻り物理ブロック
        cached_map = _load_macro_cache_from_sheets()
        merged_map = dict(cached_map)
        for d_str, val in fetched_map.items():
            merged_map[d_str] = val

        if not merged_map:
            return None

        # 変化検知時のみ上書き保存（API消費最小化）
        need_save = False
        if not cached_map:
            need_save = True
        else:
            c_max_d = max(cached_map.keys())
            m_max_d = max(merged_map.keys())
            if m_max_d > c_max_d:
                need_save = True
            elif m_max_d == c_max_d and abs(merged_map[m_max_d] - cached_map[c_max_d]) >= 0.01:
                need_save = True
            elif len(merged_map) > len(cached_map):
                need_save = True

        if need_save:
            _save_macro_cache_to_sheets(merged_map)

        sorted_items = sorted(merged_map.items())
        df_ni = pd.DataFrame(sorted_items, columns=['Date', 'Close'])
        df_ni['Date'] = pd.to_datetime(df_ni['Date'], errors='coerce')
        df_ni['Close'] = pd.to_numeric(df_ni['Close'], errors='coerce')
        df_ni = df_ni.dropna(subset=['Date', 'Close']).sort_values('Date').reset_index(drop=True)

        if len(df_ni) >= 2:
            # 🚨 戦術B: 推測合成ロジック（13060 ETFからの算出等）を完全パージ。遅延時は事実のみを出力する。
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
    except Exception as e:
        print(f"マクロ気象レーダー処理エラー: {e}")
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
        df['Date'] = pd.to_datetime(df['Date'], errors='coerce')
        df = df.dropna(subset=['Date']).sort_values('Date').reset_index(drop=True)
        if pd.api.types.is_datetime64_any_dtype(df['Date']) and df['Date'].dt.tz is not None:
            df['Date'] = df['Date'].dt.tz_localize(None)

        close_col = next((c for c in ['AdjC', 'Close', 'close', 'Adj Close', 'C'] if c in df.columns), None)
        if not close_col or df.empty: return

        # 2年分の全データに対して先にMA18・MA50を算出（左端欠損を完全にゼロ化）
        df['MA18'] = df[close_col].rolling(window=18).mean()
        df['MA50'] = df[close_col].rolling(window=50).mean()

        # 描画直前に最新営業日からカレンダー1年分へスライス
        latest_dt = df['Date'].max()
        cutoff_dt = latest_dt - pd.DateOffset(years=1)
        df_plot = df[df['Date'] >= cutoff_dt].copy()
        if df_plot.empty:
            df_plot = df.copy()
        
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
            fig.add_trace(go.Scatter(x=df_plot['Date'], y=df_plot[close_col], name='日経平均', mode='lines', line=dict(color='#FFD700', width=2), hovertemplate='日経平均: ¥%{y:,.0f}<extra></extra>'))
            fig.add_trace(go.Scatter(x=df_plot['Date'], y=df_plot['MA18'], name='18日線', mode='lines', line=dict(color='#26a69a', width=1.5, dash='dot'), hovertemplate='18日線: ¥%{y:,.0f}<extra></extra>'))
            fig.add_trace(go.Scatter(x=df_plot['Date'], y=df_plot['MA50'], name='50日線', mode='lines', line=dict(color='#ff9800', width=1.5, dash='dash'), hovertemplate='50日線: ¥%{y:,.0f}<extra></extra>'))
            y_vals = pd.concat([df_plot[close_col], df_plot['MA18'], df_plot['MA50']]).dropna()
            y_min, y_max = float(y_vals.min()), float(y_vals.max())
            fig.update_layout(
                height=220, margin=dict(l=0, r=40, t=15, b=10), xaxis_rangeslider_visible=False, 
                paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)', showlegend=False, hovermode="x unified", 
                yaxis=dict(side="right", tickformat=",.0f", gridcolor='rgba(255,255,255,0.05)', autorange=True, range=[y_min * 0.98, y_max * 1.05], fixedrange=True), 
                xaxis=dict(type='date', tickformat='%y/%m', hoverformat='%Y/%m/%d', gridcolor='rgba(255,255,255,0.05)', range=[df_plot['Date'].min(), df_plot['Date'].max() + pd.Timedelta(hours=24)], fixedrange=True)
            )
            import uuid
            st.plotly_chart(fig, use_container_width=True, config={'displayModeBar': False, 'staticPlot': False}, key=f"macro_weather_{uuid.uuid4().hex[:8]}")
            
        st.markdown("<div style='margin-bottom: 1.5rem;'></div>", unsafe_allow_html=True)

# ==========================================
# 📺 メインUI：レイアウト
# ==========================================
render_macro_board()

# 🚨 致命的データ欠落を検知した場合、全タブ共通で警告を強制出力
if st.session_state.get('system_data_error', False):
    st.error(f"🚨 【重大な警告】 {st.session_state.get('system_error_message', 'データ基盤に通信障害が発生しています。')}")
    st.warning("誤った分析（誤射）を防ぐため、スキャンシステムを物理的にロック（停止）しています。時間をおいて再実行してください。")

# --- 🏭 セクター一覧の取得 (TAB1/2 フィルタ用) ---
try: 
    master_for_sector = load_master()
    available_sectors = sorted([s for s in master_for_sector['Sector'].unique() if str(s) not in ["nan", "不明", "業種不明"]])
except:
    available_sectors = ["水産・農林業", "鉱業", "建設業", "食料品", "繊維製品", "パルプ・紙", "化学", "医薬品", "石油・石炭製品", "ゴム製品", "ガラス・土石製品", "鉄鋼", "非鉄金属", "金属製品", "機械", "電気機器", "輸送用機器", "精密機器", "その他製品", "電気・ガス業", "陸運業", "海運業", "空運業", "倉庫・運輸関連業", "情報・通信業", "卸売業", "小売業", "銀行業", "証券、商品先物取引業", "保険業", "その他金融業", "不動産業", "サービス業"]

tab1, tab2, tab3, tab7 = st.tabs(["📈 TAB1: 買い", "📉 TAB2: 空売り", "🎯 TAB3: 精密スコープ", "📁 TAB7: 戦績"])

# ==========================================
# ⚡ 全銘柄現在値・一括取得エンジン（完全ローカルDB参照版）
# ==========================================
@st.cache_data(ttl=3600, max_entries=1, show_spinner=False)
def _get_all_latest_prices_bulk_cached(file_sig):
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

def get_all_latest_prices_bulk():
    file_sig = _get_db_file_fingerprint("prices_db.pkl.gz", "prices_db.pkl")
    return _get_all_latest_prices_bulk_cached(file_sig)

@st.cache_resource(ttl=3600*24, max_entries=1)
def _load_local_fundamentals_db_cached(file_sig):
    import pickle, gzip
    db_path = os.path.join(os.path.dirname(__file__), "fundamentals_db.pkl.gz")
    if os.path.exists(db_path):
        with gzip.open(db_path, "rb") as f: return pickle.load(f)
    return {}

def load_local_fundamentals_db():
    file_sig = _get_db_file_fingerprint("fundamentals_db.pkl.gz")
    return _load_local_fundamentals_db_cached(file_sig)

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

@st.cache_data(ttl=86400, show_spinner=False)
def _load_master_v6_core():
    # 🚨 J-Quants V2 APIの正規仕様へ完全同期（推測を排除し、S33Nm, MktNm を直指定）
    try:
        import pandas as pd
        req_params = {}
        all_data = []
        
        while True:
            r = api_session.get(f"{BASE_URL}/equities/master", params=req_params, timeout=10.0)
            if r.status_code == 200:
                res_json = r.json()
                page_data = res_json.get("data", [])
                if page_data:
                    all_data.extend(page_data)
                
                pagination_key = res_json.get("pagination_key")
                if not pagination_key:
                    break
                req_params['pagination_key'] = pagination_key
            else:
                break
                
        if all_data:
            df = pd.DataFrame(all_data)
            
            # 🚨 ボスが提示したV2仕様に基づく完全指定マッピング
            c_code = 'Code' if 'Code' in df.columns else 'code'
            c_name = 'CoName' if 'CoName' in df.columns else 'CompanyName'
            c_sector = 'S33Nm' if 'S33Nm' in df.columns else 'Sector33CodeName'
            c_market = 'MktNm' if 'MktNm' in df.columns else 'MarketCodeName'
            
            for col in [c_code, c_name, c_sector, c_market]:
                if col not in df.columns: df[col] = "不明"
                    
            df = df[[c_code, c_name, c_sector, c_market]].copy()
            df.columns = ['Code', 'CompanyName', 'Sector', 'Market']
            df['Code'] = df['Code'].astype(str).apply(lambda x: x if len(x) >= 5 else x + "0")
            return df
    except: pass

    # 🚨 APIダウン時のフェイルセーフ（JPX公式Excel 完全対応版）
    try:
        import re, requests
        import pandas as pd
        from io import BytesIO
        r1 = requests.get("https://www.jpx.co.jp/markets/statistics-equities/misc/01.html", headers={'User-Agent': 'Mozilla/5.0'}, timeout=10)
        m = re.search(r'href="([^"]+data_j\.xlsx?)"', r1.text)
        if m:
            r2 = requests.get("https://www.jpx.co.jp" + m.group(1), headers={'User-Agent': 'Mozilla/5.0'}, timeout=15)
            try: df = pd.read_excel(BytesIO(r2.content), engine='openpyxl')
            except: df = pd.read_excel(BytesIO(r2.content), engine='xlrd')
            
            def find_col_jpx(*candidates):
                cols_lower = {str(c).lower(): c for c in df.columns}
                for cand in candidates:
                    if cand.lower() in cols_lower: return cols_lower[cand.lower()]
                for c in df.columns:
                    c_lower = str(c).lower()
                    for cand in candidates:
                        if cand.lower() in c_lower: return c
                return None
                
            c_code = find_col_jpx('コード', '銘柄コード', 'Code')
            c_name = find_col_jpx('銘柄名', '会社名', 'CompanyName', 'Name')
            c_sector = find_col_jpx('33業種区分', '業種', 'Sector')
            c_market = find_col_jpx('市場・商品区分', '市場', 'Market')
            
            if c_code and c_name:
                if not c_sector: c_sector = 'Sector'; df[c_sector] = '業種不明'
                if not c_market: c_market = 'Market'; df[c_market] = '市場不明'
                
                df = df[[c_code, c_name, c_sector, c_market]].copy()
                df.columns = ['Code', 'CompanyName', 'Sector', 'Market']
                df['Code'] = df['Code'].astype(str).apply(lambda x: x if len(x) >= 5 else x + "0")
                return df
    except: pass
    
    return pd.DataFrame()

def load_master():
    # 🚨 異常キャッシュを完全に切り離すステルスラッパー (v6へ移行)
    return _load_master_v6_core()

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
    # 🚨 修正：単なる日付リストではなく、{日付: 規定価格} の辞書として保持
    buy_signals = {}
    sell_signals = {}
    
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
    
    if not all([c_o, c_h, c_l, c_c, c_d]): return {}, {}

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
            # 🚨 修正：18日ルール時は「今日と昨日の高い方の高値」、それ以外（3日）は本日の終値を買い価格とする
            buy_price = max(day1_h, day2_h) if buy_cond2 else day2_c
            buy_signals[curr_date] = buy_price
            
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
            if is_macro_downtrend:
                # 🚨 修正：18日ルール時は「今日と昨日の安い方の安値」、それ以外（3日）は本日の終値を売り価格とする
                sell_price = min(day1_l, day2_l) if sell_cond2 else day2_c
                sell_signals[curr_date] = sell_price
            
    return buy_signals, sell_signals

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

        # 🚨 1. 日付ハッキング: DiscNo（文書番号）から真の開示日を抽出
        c_disc_no = find_c('DiscNo', 'discno')
        c_date = find_c('DiscDate', 'DisclosedDate', 'Date')
        
        real_dates = []
        for i in range(len(df_target)):
            dt = pd.NaT
            if c_disc_no:
                val = str(df_target[c_disc_no].iloc[i]).strip()
                if len(val) >= 8 and val[:8].isdigit():
                    dt = pd.to_datetime(val[:8], errors='coerce')
            if pd.isna(dt) and c_date:
                dt = pd.to_datetime(df_target[c_date].iloc[i], errors='coerce')
            real_dates.append(dt)
        df_target['RealDate'] = real_dates

        df_target = df_target.sort_values(by='RealDate').reset_index(drop=True)

        def to_flt(v):
            try: 
                if pd.isna(v) or str(v).strip() == '': return 0.0
                return float(str(v).replace(',', '').strip())
            except: return 0.0

        all_target_cols = []
        for c_group in [sales_candidates, op_candidates, ord_candidates, profit_candidates, eps_candidates]:
            for c in c_group:
                actual_c = find_c(c)
                if actual_c and actual_c not in all_target_cols:
                    all_target_cols.append(actual_c)

        # 2. 配当予想などの「全項目が空欄の幽霊行」をパージ
        has_actuals = pd.Series([False]*len(df_target))
        profit_check_cols = []
        for c_group in [op_candidates, ord_candidates, profit_candidates]:
            c = next((find_c(x) for x in c_group if find_c(x)), None)
            if c: profit_check_cols.append(c)
        if profit_check_cols:
            for col in profit_check_cols:
                has_actuals = has_actuals | (df_target[col].apply(to_flt) != 0.0)
        else:
            has_actuals = pd.Series([True]*len(df_target))

        actual_df = df_target[has_actuals].copy().reset_index(drop=True)

        # 3. フラッシュ（速報）とファイナル（確報）の「数値完全一致」による重複パージ
        cols_to_check = []
        for c_group in [sales_candidates, op_candidates, ord_candidates, profit_candidates]:
            c = next((find_c(x) for x in c_group if find_c(x)), None)
            if c: cols_to_check.append(c)
        if cols_to_check:
            actual_df = actual_df.drop_duplicates(subset=cols_to_check, keep='last').reset_index(drop=True)

        if len(actual_df) < 2: return None

        # 🚨 4. 【業績修正のパージ】年度ごとにグループ化し、余分な行（修正行）を消して「Q1～Q4」の4行だけに純化する
        def get_best_v(row, candidates):
            if row is None or len(row) == 0: return 0.0
            for c in candidates:
                ac = next((col for col in row.index if str(col).lower() == c.lower()), None)
                if ac:
                    v = to_flt(row.get(ac, 0.0))
                    if v != 0.0: return v
            return 0.0

        is_q1 = pd.Series([False]*len(actual_df))
        if len(actual_df) > 0: is_q1.iloc[0] = True
        
        for i in range(1, len(actual_df)):
            c_s = get_best_v(actual_df.iloc[i], sales_candidates)
            p_s = get_best_v(actual_df.iloc[i-1], sales_candidates)
            if c_s < p_s and p_s > 0:
                is_q1.iloc[i] = True
            elif c_s == 0.0 and p_s == 0.0:
                c_o = get_best_v(actual_df.iloc[i], ord_candidates)
                p_o = get_best_v(actual_df.iloc[i-1], ord_candidates)
                if c_o < p_o and p_o > 0:
                    is_q1.iloc[i] = True

        fy_groups = []
        current_group = []
        for i in range(len(actual_df)):
            if is_q1.iloc[i] and len(current_group) > 0:
                fy_groups.append(current_group)
                current_group = []
            current_group.append(i)
        if current_group:
            fy_groups.append(current_group)
            
        cleaned_indices = []
        for g in fy_groups:
            if len(g) <= 4:
                cleaned_indices.extend(g)
            else:
                # 1年に5つ以上データがある場合、間にある修正を捨てて「Q1, Q2, Q3, 本決算」だけを残す
                cleaned_indices.extend([g[0], g[1], g[2], g[-1]])
                
        std_df = actual_df.iloc[cleaned_indices].copy().reset_index(drop=True)
        is_q1_clean = is_q1.iloc[cleaned_indices].copy().reset_index(drop=True)

        # 5. 累積値からの引き算（四半期単独値化）
        for i in range(1, len(std_df)):
            if not is_q1_clean.iloc[i]:
                for col in all_target_cols:
                    if col in std_df.columns:
                        try: 
                            val_c = to_flt(actual_df.iloc[cleaned_indices[i]][col])
                            val_p = to_flt(actual_df.iloc[cleaned_indices[i-1]][col])
                            std_df.iat[i, std_df.columns.get_loc(col)] = val_c - val_p
                        except: pass

        def calc_yoy(c, p):
            if p == 0.0 or pd.isna(p) or p is None: return "-"
            if c == 0.0 and p != 0.0: return "-"
            if pd.isna(c): return "-"
            return round(((c - p) / abs(p)) * 100.0, 1)

        results = []
        
        # 6. YoY計算（タイムレーダー）
        for i in range(1, 5):
            cur_idx = len(std_df) - i
            if cur_idx < 0:
                results.append({"期間": f"直近 Q{i}", "開示日": "-", "売上(%)": "-", "営業益(%)": "-", "経常益(%)": "-", "純利益(%)": "-", "EPS(%)": "-"})
                continue
                
            q_cur = std_df.iloc[cur_idx]
            q_yoy = None
            
            curr_date_val = q_cur.get('RealDate', pd.NaT)
            if pd.notna(curr_date_val):
                for j in range(cur_idx - 1, -1, -1):
                    p_date_val = std_df.iloc[j].get('RealDate', pd.NaT)
                    if pd.notna(p_date_val):
                        days_diff = (curr_date_val - p_date_val).days
                        if 300 <= days_diff <= 430:
                            q_yoy = std_df.iloc[j]
                            break
            
            # レーダー空振り時の安全なフォールバック
            if q_yoy is None and cur_idx >= 4:
                q_yoy = std_df.iloc[cur_idx - 4]
                
            if q_yoy is None:
                q_yoy = pd.Series(dtype=float)

            dis_date = q_cur.get('RealDate', pd.NaT)
            if pd.notna(dis_date): dis_date = dis_date.strftime('%Y-%m-%d')
            else: dis_date = "-"

            v_sales_c = get_best_v(q_cur, sales_candidates)
            v_sales_p = get_best_v(q_yoy, sales_candidates)
            v_op_c = get_best_v(q_cur, op_candidates)
            v_op_p = get_best_v(q_yoy, op_candidates)
            v_ord_c = get_best_v(q_cur, ord_candidates)
            v_ord_p = get_best_v(q_yoy, ord_candidates)
            
            # 金融銘柄専用のプロキシ処理
            if v_op_c == 0.0 and v_ord_c != 0.0: v_op_c = v_ord_c
            if v_op_p == 0.0 and v_ord_p != 0.0: v_op_p = v_ord_p
            if v_sales_c == 0.0 and v_ord_c != 0.0: v_sales_c = v_ord_c
            if v_sales_p == 0.0 and v_ord_p != 0.0: v_sales_p = v_ord_p
            
            v_profit_c = get_best_v(q_cur, profit_candidates)
            v_profit_p = get_best_v(q_yoy, profit_candidates)
            v_eps_c = get_best_v(q_cur, eps_candidates)
            v_eps_p = get_best_v(q_yoy, eps_candidates)
                
            results.append({
                "期間": f"直近 Q{i}", "開示日": str(dis_date),
                "売上(%)": calc_yoy(v_sales_c, v_sales_p),
                "営業益(%)": calc_yoy(v_op_c, v_op_p),
                "経常益(%)": calc_yoy(v_ord_c, v_ord_p),
                "純利益(%)": calc_yoy(v_profit_c, v_profit_p),
                "EPS(%)": calc_yoy(v_eps_c, v_eps_p),
            })

        # 通年データの計算（1年分のデータが揃っている場合のみ）
        if len(std_df) >= 8:
            y_cur = std_df.iloc[-4:].apply(lambda x: pd.to_numeric(x, errors='coerce')).sum(numeric_only=True)
            y_prv = std_df.iloc[-8:-4].apply(lambda x: pd.to_numeric(x, errors='coerce')).sum(numeric_only=True)
            
            y_sales_c = get_best_v(y_cur, sales_candidates)
            y_sales_p = get_best_v(y_prv, sales_candidates)
            y_op_c = get_best_v(y_cur, op_candidates)
            y_op_p = get_best_v(y_prv, op_candidates)
            y_ord_c = get_best_v(y_cur, ord_candidates)
            y_ord_p = get_best_v(y_prv, ord_candidates)
            
            if y_op_c == 0.0 and y_ord_c != 0.0: y_op_c = y_ord_c
            if y_op_p == 0.0 and y_ord_p != 0.0: y_op_p = y_ord_p
            if y_sales_c == 0.0 and y_ord_c != 0.0: y_sales_c = y_ord_c
            if y_sales_p == 0.0 and y_ord_p != 0.0: y_sales_p = y_ord_p
            
            y_profit_c = get_best_v(y_cur, profit_candidates)
            y_profit_p = get_best_v(y_prv, profit_candidates)
            y_eps_c = get_best_v(y_cur, eps_candidates)
            y_eps_p = get_best_v(y_prv, eps_candidates)

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

def build_kagi_chart(df_plot, date_col, close_col, reversal_mode="ATR(14)", atr_val=0.0):
    """直近1年分の終値からカギ足（Kagi）Plotly Figureを生成する。陽線(#26a69a)・陰線(#ef5350)は同一線幅。"""
    if df_plot is None or df_plot.empty or date_col not in df_plot.columns or close_col not in df_plot.columns:
        return None, ""

    df_k = df_plot[[date_col, close_col]].copy()
    df_k[close_col] = pd.to_numeric(df_k[close_col], errors='coerce')
    df_k = df_k.dropna(subset=[date_col, close_col])
    df_k = df_k[df_k[close_col] > 0].reset_index(drop=True)
    if len(df_k) < 2:
        return None, ""

    dates = df_k[date_col].tolist()
    closes = [float(v) for v in df_k[close_col].tolist()]

    # 転換幅パラメータ確定（ATR14は一律円幅適用、%モードは比率適用）
    is_pct_mode = False
    rev_pct = 0.0
    rev_abs = 0.0
    if reversal_mode == "ATR(14)":
        if atr_val is not None and float(atr_val) > 0:
            rev_abs = float(atr_val)
            rev_label = f"ATR(14) = {rev_abs:,.1f}円"
        else:
            is_pct_mode = True
            rev_pct = 0.03
            rev_label = "3%（ATR算出不可のため自動代替）"
    else:
        is_pct_mode = True
        try:
            rev_pct = float(str(reversal_mode).replace("%", "").strip()) / 100.0
        except Exception:
            rev_pct = 0.03
        rev_label = f"{rev_pct * 100:.0f}%"

    def _is_reversed(curr_dir, extreme_p, price):
        if is_pct_mode:
            if curr_dir == 1:
                return price <= extreme_p * (1.0 - rev_pct)
            return price >= extreme_p * (1.0 + rev_pct)
        else:
            if curr_dir == 1:
                return price <= extreme_p - rev_abs
            return price >= extreme_p + rev_abs

    # 初期方向決定
    p0 = closes[0]
    d0 = dates[0]
    init_dir = 0
    start_idx = 1
    for i in range(1, len(closes)):
        p = closes[i]
        if is_pct_mode:
            if p >= p0 * (1.0 + rev_pct):
                init_dir = 1
                start_idx = i
                break
            elif p <= p0 * (1.0 - rev_pct):
                init_dir = -1
                start_idx = i
                break
        else:
            if p >= p0 + rev_abs:
                init_dir = 1
                start_idx = i
                break
            elif p <= p0 - rev_abs:
                init_dir = -1
                start_idx = i
                break

    # 1年間で一度も転換幅に到達しなかった場合のフェイルセーフ
    if init_dir == 0:
        fallback_dir = 1 if closes[-1] >= p0 else -1
        cols_data = [{
            "x": 0,
            "start_p": p0,
            "end_p": closes[-1],
            "dir": fallback_dir,
            "start_date": d0,
            "end_date": dates[-1],
        }]
    else:
        cols_data = [{
            "x": 0,
            "start_p": p0,
            "end_p": closes[start_idx],
            "dir": init_dir,
            "start_date": d0,
            "end_date": dates[start_idx],
        }]
        for i in range(start_idx + 1, len(closes)):
            p = closes[i]
            d = dates[i]
            cur = cols_data[-1]
            if cur["dir"] == 1:
                if p > cur["end_p"]:
                    cur["end_p"] = p
                    cur["end_date"] = d
                elif _is_reversed(1, cur["end_p"], p):
                    cols_data.append({
                        "x": cur["x"] + 1,
                        "start_p": cur["end_p"],
                        "end_p": p,
                        "dir": -1,
                        "start_date": d,
                        "end_date": d,
                    })
            else:
                if p < cur["end_p"]:
                    cur["end_p"] = p
                    cur["end_date"] = d
                elif _is_reversed(-1, cur["end_p"], p):
                    cols_data.append({
                        "x": cur["x"] + 1,
                        "start_p": cur["end_p"],
                        "end_p": p,
                        "dir": 1,
                        "start_date": d,
                        "end_date": d,
                    })

    # 陽線(#26a69a)・陰線(#ef5350)セグメント構築（肩突破で陽転、腰割れで陰転）
    yang_x, yang_y = [], []
    yin_x, yin_y = [], []
    hover_x, hover_y, hover_text = [], [], []

    def _add_seg(is_yang_state, x1, y1, x2, y2):
        if is_yang_state:
            yang_x.extend([x1, x2, None])
            yang_y.extend([y1, y2, None])
        else:
            yin_x.extend([x1, x2, None])
            yin_y.extend([y1, y2, None])

    is_yang = (cols_data[0]["dir"] == 1)
    last_shoulder = None
    last_waist = None

    # 始点ホバー登録
    d0_str = pd.Timestamp(cols_data[0]["start_date"]).strftime('%Y/%m/%d')
    hover_x.append(0)
    hover_y.append(cols_data[0]["start_p"])
    hover_text.append(
        f"・日付：{d0_str}<br>・価格：{cols_data[0]['start_p']:,.1f}円<br>・種別：起点<br>・状態：{'陽線' if is_yang else '陰線'}"
    )

    for idx_c, col in enumerate(cols_data):
        cx = col["x"]
        sp = col["start_p"]
        ep = col["end_p"]
        cdir = col["dir"]

        if idx_c > 0:
            prev_col = cols_data[idx_c - 1]
            # 肩・腰の水平連結線（現在状態で描画）
            _add_seg(is_yang, cx - 1, sp, cx, sp)
            if prev_col["dir"] == 1:
                last_shoulder = prev_col["end_p"]
            else:
                last_waist = prev_col["end_p"]

        # 縦線描画と陽転・陰転の交差分割
        if cdir == 1 and (not is_yang) and (last_shoulder is not None) and (ep > last_shoulder):
            if sp < last_shoulder:
                _add_seg(False, cx, sp, cx, last_shoulder)
                _add_seg(True, cx, last_shoulder, cx, ep)
            else:
                _add_seg(True, cx, sp, cx, ep)
            is_yang = True
        elif cdir == -1 and is_yang and (last_waist is not None) and (ep < last_waist):
            if sp > last_waist:
                _add_seg(True, cx, sp, cx, last_waist)
                _add_seg(False, cx, last_waist, cx, ep)
            else:
                _add_seg(False, cx, sp, cx, ep)
            is_yang = False
        else:
            _add_seg(is_yang, cx, sp, cx, ep)

        # 転換点（肩・腰・最新終値）ホバー登録
        ed_str = pd.Timestamp(col["end_date"]).strftime('%Y/%m/%d')
        if idx_c == len(cols_data) - 1:
            pt_kind = "最新終値"
        else:
            pt_kind = "肩（高値転換）" if cdir == 1 else "腰（安値転換）"
        hover_x.append(cx)
        hover_y.append(ep)
        hover_text.append(
            f"・日付：{ed_str}<br>・価格：{ep:,.1f}円<br>・種別：{pt_kind}<br>・状態：{'陽線' if is_yang else '陰線'}"
        )

    fig_kagi = go.Figure()

    # 陽線・陰線ともに同一の線幅（width=2.5）で描画
    fig_kagi.add_trace(go.Scatter(
        x=yang_x,
        y=yang_y,
        mode='lines',
        name='陽線（買い優勢）',
        line=dict(color='#26a69a', width=2.5),
        hoverinfo='skip'
    ))
    fig_kagi.add_trace(go.Scatter(
        x=yin_x,
        y=yin_y,
        mode='lines',
        name='陰線（売り優勢）',
        line=dict(color='#ef5350', width=2.5),
        hoverinfo='skip'
    ))
    fig_kagi.add_trace(go.Scatter(
        x=hover_x,
        y=hover_y,
        mode='markers',
        name='転換点',
        showlegend=False,
        marker=dict(size=9, color='rgba(255,255,255,0.01)'),
        text=hover_text,
        hovertemplate='%{text}<extra></extra>'
    ))

    # 非時系列X軸へ転換日付の代表目盛りを配置
    total_cols = len(cols_data)
    step_tick = max(1, total_cols // 8)
    tick_vals = list(range(0, total_cols, step_tick))
    if (total_cols - 1) not in tick_vals:
        tick_vals.append(total_cols - 1)
    tick_texts = [pd.Timestamp(cols_data[i]["end_date"]).strftime('%y/%m/%d') for i in tick_vals]

    fig_kagi.update_layout(
        height=400,
        margin=dict(l=0, r=40, t=40, b=20),
        paper_bgcolor='rgba(0,0,0,0)',
        plot_bgcolor='rgba(0,0,0,0)',
        dragmode='pan',
        hovermode='closest',
        hoverlabel=dict(bgcolor="rgba(0,0,0,0.85)", font_size=13, font_family="sans-serif", align="left"),
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.02,
            xanchor="center",
            x=0.5,
            bgcolor="rgba(0,0,0,0)"
        ),
        xaxis=dict(
            tickmode='array',
            tickvals=tick_vals,
            ticktext=tick_texts,
            showgrid=True,
            gridcolor='rgba(255,255,255,0.05)',
            fixedrange=False,
            range=[-0.5, max(total_cols - 0.5, 0.5)]
        ),
        yaxis=dict(
            side='right',
            tickformat=',.0f',
            autorange=True,
            fixedrange=False,
            gridcolor='rgba(255,255,255,0.05)'
        )
    )

    info_text = f"転換幅: {rev_label} | 転換回数: {max(total_cols - 1, 0)}回 | 状態: {'🟢 陽線' if is_yang else '🔴 陰線'}"
    return fig_kagi, info_text

# ==========================================
# 🌐 TAB1: 買い銘柄広域スキャン (Growth / Standard / Prime)
# ==========================================
with tab1:
    user_scan_state_t1 = ensure_user_scan_state_loaded()
    saved_t1_filters = user_scan_state_t1.get("tab1_filters", {}) if isinstance(user_scan_state_t1, dict) else {}

    t1_period_opts = ["52週", "3か月", "6か月", "2年"]
    t1_sales_opts = [7, 3, 5]
    t1_ord_opts = [15, 10, 13, 20]
    t1_mcap_opts = [500, 300, 1000]

    def _safe_idx(opts, val, default_idx=0):
        try:
            return opts.index(val)
        except ValueError:
            return default_idx

    t1_def_period_idx = _safe_idx(t1_period_opts, saved_t1_filters.get("period", "52週"), 0)
    t1_def_sales_idx = _safe_idx(t1_sales_opts, saved_t1_filters.get("sales_r", 7), 0)
    t1_def_ord_idx = _safe_idx(t1_ord_opts, saved_t1_filters.get("ord_r", 15), 0)
    t1_def_mcap_idx = _safe_idx(t1_mcap_opts, saved_t1_filters.get("mcap", 500), 0)
    t1_def_p_min = int(saved_t1_filters.get("p_min", 800))
    t1_def_p_max = int(saved_t1_filters.get("p_max", 4000))
    t1_def_sec_all = bool(saved_t1_filters.get("sec_all", True))
    t1_def_selected_secs = saved_t1_filters.get("selected_sectors", [])
    if not isinstance(t1_def_selected_secs, list):
        t1_def_selected_secs = []

    st.markdown('### 🌐 買い銘柄広域スキャン', unsafe_allow_html=True)
    st.caption("※直近2四半期の売上・利益のYoY（前年同期比）成長率をベースに、大化け候補（S級・A級）を広域索敵します。")
    
    with st.form("tab1_buy_scan_form", clear_on_submit=False):
        col1_1, col1_2, col1_3 = st.columns(3)
        t1_period = col1_1.selectbox("期間フィルタ (高値判定基準)", t1_period_opts, index=t1_def_period_idx, key="t1_period")
        t1_sales_r = col1_2.selectbox("直近四半期 売上増収率 (%)", t1_sales_opts, index=t1_def_sales_idx, key="t1_sales_r")
        t1_ord_r = col1_3.selectbox("直近四半期 経常利益増益率 (%)", t1_ord_opts, index=t1_def_ord_idx, key="t1_ord_r")
        
        col1_4, col1_5, col1_6 = st.columns(3)
        t1_mcap = col1_4.selectbox("時価総額フィルタ (億円以上)", t1_mcap_opts, index=t1_def_mcap_idx, key="t1_mcap")
        t1_p_min = col1_5.number_input("価格下限 (円)", value=t1_def_p_min, step=100, key="t1_p_min")
        t1_p_max = col1_6.number_input("価格上限 (円)", value=t1_def_p_max, step=100, key="t1_p_max")
        
        with st.expander("🏭 セクター絞り込み", expanded=False):
            t1_sec_all = st.checkbox("✅ 全セクターを対象とする", value=t1_def_sec_all, key="t1_sec_all")
            st.caption("※個別に絞り込む場合は、上のチェックを外して以下を選択してください。")
            sec_cols = st.columns(4)
            selected_sectors_t1 = []
            for i, sec in enumerate(available_sectors):
                if sec_cols[i % 4].checkbox(sec, value=(sec in t1_def_selected_secs), key=f"t1_sec_{i}"):
                    selected_sectors_t1.append(sec)

        st.markdown(f"**(固定スキャン条件: 直近2四半期連続 YoY S級/A級クリア)** \n"
                    f"・直近1つ目の四半期は売上 {t1_sales_r}% 以上、他利益 {t1_ord_r}% 以上で完全クリア必須。\n"
                    f"・直近2つ目の四半期も完全クリアでS級🎯、1つだけ下回ればA級🟢。")
        
        # 🚨 致命的データ欠落時、スキャンボタンを無効化（ロック）
        btn_scan_t1 = st.form_submit_button("🚀 買い銘柄 スキャン実行", use_container_width=True, type="primary", disabled=st.session_state.get('system_data_error', False))

    # 🚨 修正：スキャン実行時以外（リロード直後等）にユーザー固有のクラウド保存結果を画面へ復元表示する
    if not btn_scan_t1 and st.session_state.get('tab1_scan_results'):
        cached_hits = [r.get("Code", "") for r in st.session_state['tab1_scan_results']]
        t1_upd_str = st.session_state.get('tab1_scan_updated_at', '')
        t1_upd_suffix = f" （実行日時: {t1_upd_str}）" if t1_upd_str else ""
        st.info(f"💾 【クラウド復元】前回スキャンした突破銘柄（アクセスコード別保存）{t1_upd_suffix}")
        st.code(", ".join(cached_hits) if cached_hits else "条件に合致する銘柄はありませんでした。", language="text")

    if btn_scan_t1:
        import time
        t1_filters_payload = {
            "period": t1_period,
            "sales_r": int(t1_sales_r),
            "ord_r": int(t1_ord_r),
            "mcap": int(t1_mcap),
            "p_min": int(t1_p_min),
            "p_max": int(t1_p_max),
            "sec_all": bool(t1_sec_all),
            "selected_sectors": list(selected_sectors_t1),
        }
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
                
                try: m_df_local = load_master()
                except: m_df_local = None
                
                sector_map = {}
                if m_df_local is not None and not m_df_local.empty:
                    sector_map = dict(zip(m_df_local['Code'].astype(str).str[:4], m_df_local['Sector']))

                if prices_map:
                    for c_code, c_price in prices_map.items():
                        if float(t1_p_min) <= float(c_price) <= float(t1_p_max):
                            # 🚨 セクターフィルタ判定（論理全選択方式）
                            c_sec = sector_map.get(str(c_code)[:4], "不明")
                            if not t1_sec_all and selected_sectors_t1 and c_sec not in selected_sectors_t1:
                                continue
                            
                            c_mcap = float(mcap_map.get(str(c_code), 0))
                            if c_mcap >= float(t1_mcap): 
                                all_codes.append(str(c_code))
                            elif c_mcap == 0 and m_df_local is not None and not m_df_local.empty:
                                m_row = m_df_local[m_df_local['Code'].astype(str).str.startswith(str(c_code)[:4])]
                                if not m_row.empty:
                                    market_val = str(m_row.iloc[0].get('Market', ''))
                                    if "プライム" in market_val or "Prime" in market_val or "スタンダード" in market_val or "Standard" in market_val:
                                        all_codes.append(str(c_code))
                else:
                    p1_msg.error("❌ 株価データの取得に失敗しました。")
                    st.stop()
            except Exception as e:
                p1_msg.error(f"❌ フィルタ取得エラー: {e}")
                st.stop()
                
            import unicodedata
            # 🚨 修正：取得コードの全角を半角に強制統一し、重複を完全に排除
            raw_filtered_codes = [unicodedata.normalize('NFKC', str(code).replace('.0', '').strip())[:4] for code in all_codes]
            p_filtered_codes = list(dict.fromkeys(raw_filtered_codes))
            
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
                                
                                if (q1_op is None or q1_op == 0.0) and q1_ord is not None: q1_op = q1_ord
                                if (q2_op is None or q2_op == 0.0) and q2_ord is not None: q2_op = q2_ord
                                if (q1_s is None or q1_s == 0.0) and q1_ord is not None: q1_s = q1_ord
                                if (q2_s is None or q2_s == 0.0) and q2_ord is not None: q2_s = q2_ord

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
                
                # 🚨 スキャン完了と同時にアクセスコード別 Google Sheets（SCAN_STATE_{ID}）へ上書き永続化
                final_results = [{"Code": c, "Rank": "S級"} for c in hit_codes_s] + [{"Code": c, "Rank": "A級"} for c in hit_codes_a]
                now_jst_t1 = get_now_jst_str()
                st.session_state['tab1_scan_results'] = final_results
                st.session_state['tab1_scan_updated_at'] = now_jst_t1
                save_user_scan_state({
                    "tab1_filters": t1_filters_payload,
                    "tab1_results": {"results": final_results, "updated_at": now_jst_t1},
                })
            else:
                now_jst_t1 = get_now_jst_str()
                st.session_state['tab1_scan_results'] = []
                st.session_state['tab1_scan_updated_at'] = now_jst_t1
                save_user_scan_state({
                    "tab1_filters": t1_filters_payload,
                    "tab1_results": {"results": [], "updated_at": now_jst_t1},
                })
                p2_msg.warning("⚠️ Phase 1 を通過した銘柄が0件のため、解析をスキップします。")
                status.update(label="⚠️ スキャン中断：対象銘柄なし", state="complete")

# ==========================================
# 📉 TAB2: 売り（空売り）銘柄広域スキャン (Growth / Standard / Prime)
# ==========================================
with tab2:
    user_scan_state_t2 = ensure_user_scan_state_loaded()
    saved_t2_filters = user_scan_state_t2.get("tab2_filters", {}) if isinstance(user_scan_state_t2, dict) else {}

    t2_period_opts = ["6か月", "3か月"]
    t2_ord_opts = [8, 5, 10]
    t2_mcap_opts = [500, 300, 1000]
    t2_vol_opts = [3, 1, 2]

    def _safe_idx_t2(opts, val, default_idx=0):
        try:
            return opts.index(val)
        except ValueError:
            return default_idx

    t2_def_period_idx = _safe_idx_t2(t2_period_opts, saved_t2_filters.get("period", "6か月"), 0)
    t2_def_ord_idx = _safe_idx_t2(t2_ord_opts, saved_t2_filters.get("ord_r", 8), 0)
    t2_def_mcap_idx = _safe_idx_t2(t2_mcap_opts, saved_t2_filters.get("mcap", 500), 0)
    t2_def_vol_idx = _safe_idx_t2(t2_vol_opts, saved_t2_filters.get("vol", 3), 0)
    t2_def_p_min = int(saved_t2_filters.get("p_min", 400))
    t2_def_p_max = int(saved_t2_filters.get("p_max", 3000))
    t2_def_sec_all = bool(saved_t2_filters.get("sec_all", True))
    t2_def_selected_secs = saved_t2_filters.get("selected_sectors", [])
    if not isinstance(t2_def_selected_secs, list):
        t2_def_selected_secs = []

    st.markdown('### 📉 売り（空売り）銘柄広域スキャン', unsafe_allow_html=True)
    st.caption("※直近2四半期の業績鈍化・衰退（YoY 8%未満等）をベースに、空売り候補（S級・A級）を広域索敵します。")
    
    with st.form("tab2_sell_scan_form", clear_on_submit=False):
        col2_1, col2_2, col2_3 = st.columns(3)
        t2_period = col2_1.selectbox("期間フィルタ (安値判定基準)", t2_period_opts, index=t2_def_period_idx, key="t2_period")
        t2_ord_r = col2_2.selectbox("直近四半期 利益成長率フィルタ (%)", t2_ord_opts, index=t2_def_ord_idx, key="t2_ord_r")
        t2_mcap = col2_3.selectbox("時価総額フィルタ (億円以上)", t2_mcap_opts, index=t2_def_mcap_idx, key="t2_mcap")
        
        col2_4, col2_5, col2_6 = st.columns(3)
        t2_vol = col2_4.selectbox("売買代金フィルタ (億円以上)", t2_vol_opts, index=t2_def_vol_idx, key="t2_vol")
        t2_p_min = col2_5.number_input("価格下限 (円)", value=t2_def_p_min, step=100, key="t2_p_min")
        t2_p_max = col2_6.number_input("価格上限 (円)", value=t2_def_p_max, step=100, key="t2_p_max")
        
        with st.expander("🏭 セクター絞り込み", expanded=False):
            t2_sec_all = st.checkbox("✅ 全セクターを対象とする", value=t2_def_sec_all, key="t2_sec_all")
            st.caption("※個別に絞り込む場合は、上のチェックを外して以下を選択してください。")
            sec_cols_t2 = st.columns(4)
            selected_sectors_t2 = []
            for i, sec in enumerate(available_sectors):
                if sec_cols_t2[i % 4].checkbox(sec, value=(sec in t2_def_selected_secs), key=f"t2_sec_{i}"):
                    selected_sectors_t2.append(sec)

        st.markdown(f"**(固定スキャン条件: 直近2四半期連続 利益鈍化)** \n"
                    f"・営業利益・経常利益・純利益・一株利益の全8項目が 5%未満 でS級💀 \n"
                    f"・1つだけ {t2_ord_r}%未満（他5%未満）でA級📉")
        
        # 🚨 致命的データ欠落時、スキャンボタンを無効化（ロック）
        btn_scan_t2 = st.form_submit_button("🚀 売り銘柄 スキャン実行", use_container_width=True, type="primary", disabled=st.session_state.get('system_data_error', False))

    # 🚨 修正：スキャン実行時以外（リロード直後等）にユーザー固有のクラウド保存結果を画面へ復元表示する
    if not btn_scan_t2 and st.session_state.get('tab2_scan_results'):
        cached_hits = [r.get("Code", "") for r in st.session_state['tab2_scan_results']]
        t2_upd_str = st.session_state.get('tab2_scan_updated_at', '')
        t2_upd_suffix = f" （実行日時: {t2_upd_str}）" if t2_upd_str else ""
        st.info(f"💾 【クラウド復元】前回スキャンした突破銘柄（アクセスコード別保存）{t2_upd_suffix}")
        st.code(", ".join(cached_hits) if cached_hits else "条件に合致する銘柄はありませんでした。", language="text")

    if btn_scan_t2:
        import time
        t2_filters_payload = {
            "period": t2_period,
            "ord_r": int(t2_ord_r),
            "mcap": int(t2_mcap),
            "vol": int(t2_vol),
            "p_min": int(t2_p_min),
            "p_max": int(t2_p_max),
            "sec_all": bool(t2_sec_all),
            "selected_sectors": list(selected_sectors_t2),
        }
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
                
                # 🚨 J-Quantsの欠損バグ救済用マスターロード
                try: m_df_local = load_master()
                except: m_df_local = None
                
                sector_map_t2 = {}
                if m_df_local is not None and not m_df_local.empty:
                    sector_map_t2 = dict(zip(m_df_local['Code'].astype(str).str[:4], m_df_local['Sector']))
                
                if prices_map:
                    for c_code, c_price in prices_map.items():
                        if float(t2_p_min) <= float(c_price) <= float(t2_p_max):
                            # 🚨 セクターフィルタ判定（論理全選択方式）
                            c_sec_t2 = sector_map_t2.get(str(c_code)[:4], "不明")
                            if not t2_sec_all and selected_sectors_t2 and c_sec_t2 not in selected_sectors_t2:
                                continue

                            c_vol = float(vol_map.get(str(c_code), 0))
                            if c_vol >= float(t2_vol):
                                c_mcap = float(mcap_map.get(str(c_code), 0))
                                if c_mcap >= float(t2_mcap): 
                                    all_codes.append(str(c_code))
                                elif c_mcap == 0 and m_df_local is not None and not m_df_local.empty:
                                    # 🚨 金融銘柄救済ルート：時価総額欠損でもプライム/スタンダードなら通過
                                    m_row = m_df_local[m_df_local['Code'].astype(str).str.startswith(str(c_code)[:4])]
                                    if not m_row.empty:
                                        market_val = str(m_row.iloc[0].get('Market', ''))
                                        if "プライム" in market_val or "Prime" in market_val or "スタンダード" in market_val or "Standard" in market_val:
                                            all_codes.append(str(c_code))
                else:
                    p1_msg_t2.error("❌ 株価データの取得に失敗しました。")
                    st.stop()
            except Exception as e:
                p1_msg_t2.error(f"❌ フィルタ取得エラー: {e}")
                st.stop()
                
            import unicodedata
            # 🚨 修正：取得コードの全角を半角に強制統一
            p_filtered_codes = [unicodedata.normalize('NFKC', str(code).replace('.0', '').strip())[:4] for code in all_codes]
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
                                
                                # 🚨 金融業対策: 営業益が欠損（Noneまたは0）かつ経常益が存在する場合、経常益をプロキシとして代入する
                                if (q1_op is None or q1_op == 0.0) and q1_ord is not None: q1_op = q1_ord
                                if (q2_op is None or q2_op == 0.0) and q2_ord is not None: q2_op = q2_ord
                                
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
                
                # 🚨 スキャン完了と同時にアクセスコード別 Google Sheets（SCAN_STATE_{ID}）へ上書き永続化
                final_results_t2 = [{"Code": c, "Rank": "S級"} for c in hit_codes_s] + [{"Code": c, "Rank": "A級"} for c in hit_codes_a]
                now_jst_t2 = get_now_jst_str()
                st.session_state['tab2_scan_results'] = final_results_t2
                st.session_state['tab2_scan_updated_at'] = now_jst_t2
                save_user_scan_state({
                    "tab2_filters": t2_filters_payload,
                    "tab2_results": {"results": final_results_t2, "updated_at": now_jst_t2},
                })
            else:
                now_jst_t2 = get_now_jst_str()
                st.session_state['tab2_scan_results'] = []
                st.session_state['tab2_scan_updated_at'] = now_jst_t2
                save_user_scan_state({
                    "tab2_filters": t2_filters_payload,
                    "tab2_results": {"results": [], "updated_at": now_jst_t2},
                })
                p2_msg_t2.warning("⚠️ Phase 1 を通過した銘柄が0件のため、解析をスキップします。")
                status.update(label="⚠️ スキャン中断：対象銘柄なし", state="complete")

# ==========================================
# 🎯 TAB3: 精密スコープ
# ==========================================
with tab3:
    user_scan_state_t3 = ensure_user_scan_state_loaded()
    saved_t3_state = user_scan_state_t3.get("tab3_state", {}) if isinstance(user_scan_state_t3, dict) else {}
    saved_t3_mode = saved_t3_state.get("mode", "buy")
    t3_mode_def_idx = 0 if saved_t3_mode != "sell" else 1

    st.markdown("### 🎯 【照準】精密スコープ＆詳細分析")
    st.info("TAB1・TAB2で抽出されたファンダ強者に対し、陣形の判定および詳細な個別チャート・業績推移を完全ローカルデータから出力します。")

    tab3_mode = st.radio(
        "スキャンモードを選択してください",
        ["モード1：買い（反転上昇）", "モード2：空売り（奈落崩壊）"],
        index=t3_mode_def_idx,
        horizontal=True,
        key="tab3_mode_radio",
    )
    scan_mode = "buy" if "買い" in tab3_mode else "sell"

    # TAB1/TAB2の結果オブジェクトを直接取得し、オブジェクトID（再スキャン検知）を取得
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

    # 内部Storeの初期化（クラウド保存済みのTAB3入力枠を優先復元）
    if "tab3_store_buy" not in st.session_state:
        saved_buy = saved_t3_state.get("store_buy", "")
        st.session_state["tab3_store_buy"] = saved_buy if saved_buy != "" else t1_codes_str
    if "tab3_store_sell" not in st.session_state:
        saved_sell = saved_t3_state.get("store_sell", "")
        st.session_state["tab3_store_sell"] = saved_sell if saved_sell != "" else t2_codes_str
    if "tab3_manual_codes" not in st.session_state:
        st.session_state["tab3_manual_codes"] = str(saved_t3_state.get("manual_codes", ""))
        
    if "tab3_last_t1_id" not in st.session_state:
        st.session_state["tab3_last_t1_id"] = t1_id
    if "tab3_last_t2_id" not in st.session_state:
        st.session_state["tab3_last_t2_id"] = t2_id
        
    if "tab3_last_t1_str" not in st.session_state:
        st.session_state["tab3_last_t1_str"] = t1_codes_str
    if "tab3_last_t2_str" not in st.session_state:
        st.session_state["tab3_last_t2_str"] = t2_codes_str

    # TAB1/TAB2でスキャン結果が更新された瞬間のみStoreを強制上書き
    if st.session_state["tab3_last_t1_id"] != t1_id or st.session_state["tab3_last_t1_str"] != t1_codes_str:
        st.session_state["tab3_store_buy"] = t1_codes_str
        st.session_state["tab3_last_t1_id"] = t1_id
        st.session_state["tab3_last_t1_str"] = t1_codes_str

    if st.session_state["tab3_last_t2_id"] != t2_id or st.session_state["tab3_last_t2_str"] != t2_codes_str:
        st.session_state["tab3_store_sell"] = t2_codes_str
        st.session_state["tab3_last_t2_id"] = t2_id
        st.session_state["tab3_last_t2_str"] = t2_codes_str

    store_key = "tab3_store_buy" if scan_mode == "buy" else "tab3_store_sell"

    st.markdown("#### 📡 分析対象銘柄")
    
    target_codes_input = st.text_area(
        "【正規スキャン枠】（TAB1・TAB2突破銘柄が自動入力。※厳格条件に完全合致した銘柄のみ抽出）",
        value=st.session_state.get(store_key, ""),
        height=100
    )
    
    # 🚨 追加：手動入力による強制出力枠
    manual_codes_input = st.text_input(
        "【強行偵察枠】（手動入力。※条件に関わらず分析チャート・業績を強制出力します。カンマ区切り）",
        value=st.session_state.get("tab3_manual_codes", "")
    )
    
    st.session_state[store_key] = target_codes_input
    st.session_state["tab3_manual_codes"] = manual_codes_input

    kagi_rev_mode = st.selectbox(
        "📐 カギ足 転換幅設定（終値・1年分）",
        ["ATR(14)", "3%", "4%", "5%"],
        index=0,
        key="tab3_kagi_reversal",
    )

    btn_scan_t3 = st.button("🚀 TAB3 精密スキャン＆一斉分析", key="btn_scan_tab3")

    # 案A：リロード・再ログイン時（ボタン未押下時）は保存済みの前回抽出サマリーを高速復元表示する
    if not btn_scan_t3 and st.session_state.get('tab3_results'):
        prev_t3_results = st.session_state.get('tab3_results', [])
        prev_t3_upd = st.session_state.get('tab3_updated_at', '')
        prev_t3_mode_raw = st.session_state.get('tab3_last_mode', saved_t3_mode)
        prev_t3_mode_label = "買い（反転上昇）" if prev_t3_mode_raw != "sell" else "空売り（奈落崩壊）"
        upd_txt = f" | 実行日時: {prev_t3_upd}" if prev_t3_upd else ""
        st.info(f"💾 【クラウド復元】前回TAB3抽出結果（モード: {prev_t3_mode_label}{upd_txt} / 計 {len(prev_t3_results)}件）\n\n※チャート・業績表を再描画するには上の『🚀 TAB3 精密スキャン＆一斉分析』を押下してください。")
        summary_df = pd.DataFrame([
            {"銘柄コード": str(r.get("Code", "")), "判定ランク": str(r.get("Rank", "")), "モード": "買い" if r.get("Mode") != "sell" else "空売り"}
            for r in prev_t3_results
        ])
        if not summary_df.empty:
            st.dataframe(summary_df, hide_index=True, use_container_width=True)
            prev_codes_str = ",".join([str(r.get("Code", "")) for r in prev_t3_results if r.get("Code")])
            st.text_area(f"📋 前回抽出銘柄（コピペ用・計 {len(prev_t3_results)}件）", value=prev_codes_str, height=70, key="tab3_restored_codes_copy")

    if btn_scan_t3:
        if not target_codes_input.strip() and not manual_codes_input.strip():
            st.warning("⚠️ 銘柄コードが入力されていません。")
        else:
            p_bar = st.progress(0, text="🚀 システム初期化・全軍データロード中...")
            display_targets = []
            scan_succeeded = False

            import unicodedata
            
            # 正規スキャン枠のパース
            normalized_input = unicodedata.normalize('NFKC', target_codes_input)
            normalized_input = normalized_input.replace(" ", ",").replace("\n", ",")
            raw_codes = [c.strip() for c in normalized_input.split(",") if c.strip()]
            
            # 強行偵察枠のパース
            normalized_manual = unicodedata.normalize('NFKC', manual_codes_input)
            normalized_manual = normalized_manual.replace(" ", ",").replace("\n", ",")
            raw_manual = [c.strip() for c in normalized_manual.split(",") if c.strip()]
                        
            target_codes = []
            for c in raw_codes:
                if len(c) >= 4:
                    target_codes.append(str(c)[:4])
                    
            manual_codes = []
            for c in raw_manual:
                if len(c) >= 4:
                    manual_codes.append(str(c)[:4])
                    
            target_str_codes = list(dict.fromkeys(target_codes + manual_codes))

            st.write(f"📡 実行対象: {len(target_str_codes)} 銘柄を解析中...（正規: {len(target_codes)} / 強行偵察: {len(manual_codes)}）")

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
                    scan_succeeded = True
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
                        code_val = str(code_str)[:4]
                        completed_cnt += 1
                        
                        prog_val = min(completed_cnt / total_cnt, 1.0)
                        p_bar.progress(prog_val, text=f"🚀 フェーズ1：インメモリ陣形判定中... ({completed_cnt}/{total_cnt} 完了)")
                        
                        df = group.reset_index(drop=True)
                        if df.empty or len(df) < 4: continue
                        
                        # 🚨 修正：V2 APIカラムをV1形式へ強制置換（外部関数 analyze_formation_history の互換性維持のため）
                        v2_to_v1_map = {
                            'O': 'Open', 'H': 'High', 'L': 'Low', 'C': 'Close', 'Vo': 'Volume',
                            'AdjO': 'AdjustmentOpen', 'AdjH': 'AdjustmentHigh', 'AdjL': 'AdjustmentLow', 
                            'AdjC': 'AdjustmentClose', 'AdjVo': 'AdjustmentVolume'
                        }
                        df = df.rename(columns=v2_to_v1_map)

                        turnover = 0.0
                        try:
                            q0 = df.iloc[-1]
                            v_col = 'Volume' if 'Volume' in df.columns else ('Vo' if 'Vo' in df.columns else None)
                            c_col = 'AdjustmentClose' if 'AdjustmentClose' in df.columns else ('Close' if 'Close' in df.columns else None)
                            if v_col and c_col: turnover = float(q0[v_col]) * float(q0[c_col])
                        except: pass

                        # 🚨 修正：is_macro_downtrendのハードコードを撤廃し、動的変数を引き渡す
                        b_sigs, s_sigs = analyze_formation_history(df, is_macro_downtrend=is_macro_downtrend)
                        
                        is_hit = False
                        rank_str = ""
                        rank_funda = "対象外"
                        rank_signal = "対象外"

                        date_col = 'Date' if 'Date' in df.columns else df.columns[0]
                        df_dates = df[date_col].dt.date.tolist() if pd.api.types.is_datetime64_any_dtype(df[date_col]) else pd.to_datetime(df[date_col]).dt.date.tolist()
                        
                        if scan_mode == "buy" and b_sigs:
                            b_sig_dates = [pd.to_datetime(d).date() for d in b_sigs if pd.notna(d)]
                            sig_indices = [i for i, d in enumerate(df_dates) if d in b_sig_dates]
                            if sig_indices:
                                days_ago = (len(df_dates) - 1) - max(sig_indices)
                                # 🚨 修正：新規格に基づく日数判定に完全同期（当日 = days_ago: 0）
                                if days_ago <= 2: rank_signal = "S"
                                elif days_ago <= 3: rank_signal = "A"
                                elif days_ago <= 4: rank_signal = "B"
                        
                        elif scan_mode == "sell" and s_sigs:
                            s_sig_dates = [pd.to_datetime(d).date() for d in s_sigs if pd.notna(d)]
                            sig_indices = [i for i, d in enumerate(df_dates) if d in s_sig_dates]
                            if sig_indices:
                                days_ago = (len(df_dates) - 1) - max(sig_indices)
                                # 🚨 修正：新規格に基づく日数判定に完全同期
                                if days_ago == 0: rank_signal = "S"
                                elif days_ago <= 1: rank_signal = "A"
                                elif days_ago <= 3: rank_signal = "B"

                        f_df = fetch_fundamental_history_local(code_val, local_fund_db)
                        latest_ord_pct = -9999.0
                        
                        if f_df is not None and not f_df.empty:
                            q1_row = f_df[f_df["期間"] == "直近 Q1"]
                            q2_row = f_df[f_df["期間"] == "直近 Q2"]
                            
                            def get_val(r, col):
                                if r.empty: return None
                                v = r[col].iloc[0]
                                if isinstance(v, str) and v == "-": return None
                                try: return float(v)
                                except: return None

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
                                
                                # 🛡️ 金融銘柄プロキシ処理（TAB1と完全同期）
                                if (q1_op is None or q1_op == 0.0) and q1_ord is not None: q1_op = q1_ord
                                if (q2_op is None or q2_op == 0.0) and q2_ord is not None: q2_op = q2_ord
                                if (q1_s is None or q1_s == 0.0) and q1_ord is not None: q1_s = q1_ord
                                if (q2_s is None or q2_s == 0.0) and q2_ord is not None: q2_s = q2_ord
                                
                                def count_misses(s, op, ord_p, np_p, eps):
                                    if None in [s, op, ord_p, np_p, eps]: return 99 # 🛡️ 厳格なペナルティによる防壁
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
                                    
                                    # 🛡️ 金融銘柄プロキシ処理（TAB1と完全同期）
                                    if (q1_op is None or q1_op == 0.0) and q1_ord is not None: q1_op = q1_ord
                                    if (q2_op is None or q2_op == 0.0) and q2_ord is not None: q2_op = q2_ord

                                    vals = [q1_op, q1_ord, q1_np, q1_eps, q2_op, q2_ord, q2_np, q2_eps]
                                    if None not in vals: # 🛡️ 厳格なペナルティによる防壁
                                        lt_5 = sum(1 for v in vals if v < 5.0)
                                        lt_8 = sum(1 for v in vals if v < 8.0)
                                        
                                        if lt_8 == 8:
                                            if lt_5 == 8: rank_funda = "S"
                                            elif lt_5 == 7: rank_funda = "A"
                                            elif lt_5 == 6: rank_funda = "B"

                        if scan_mode == "buy":
                            if rank_funda != "対象外" and rank_signal != "対象外":
                                is_hit = True
                            rank_str = f"🎯業績:{rank_funda}級 / 陣形:{rank_signal}級"
                        elif scan_mode == "sell":
                            if rank_funda != "対象外" and rank_signal != "対象外":
                                is_hit = True
                            rank_str = f"💀業績:{rank_funda}級 / 陣形:{rank_signal}級"

                        analyzed_data[code_val] = {
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
                        
                        is_both = data.get("is_hit", False)
                        
                        return (is_both, score, data.get("latest_ord_pct", -9999.0), data.get("turnover", 0.0))
                        
                    sortable_results = [{"code": k, **v} for k, v in analyzed_data.items()]
                    sortable_results.sort(key=get_rank_score, reverse=True)
                    
                    # 🚨 修正：強行偵察枠（manual_codes）は is_hit == False (条件未達) でも強制抽出
                    display_targets = [d for d in sortable_results if d.get("is_hit", False) or d["code"] in manual_codes]

                    # 🚨 修正ポイント：市場・業種区分・決算予定日データの取得用辞書構築
                    name_map = {}
                    market_map = {}
                    sector_map = {}
                    earnings_map = {}
                    try:
                        m_df = load_master()
                        name_map = dict(zip(m_df['Code'].astype(str).str[:4], m_df['CompanyName']))
                        market_map = dict(zip(m_df['Code'].astype(str).str[:4], m_df['Market']))
                        sector_map = dict(zip(m_df['Code'].astype(str).str[:4], m_df['Sector']))
                    except: pass
                    
                    # Streamlit環境とバッチ環境のディレクトリズレを完全吸収するマルチパス検索
                    earn_paths = [
                        "earnings_db.pkl.gz",
                        os.path.join(os.path.dirname(__file__), "earnings_db.pkl.gz"),
                        os.path.join(os.getcwd(), "earnings_db.pkl.gz"),
                        os.path.join(os.path.dirname(os.path.dirname(__file__)), "earnings_db.pkl.gz")
                    ]
                    for path in earn_paths:
                        if os.path.exists(path):
                            try:
                                import gzip, pickle
                                with gzip.open(path, "rb") as f:
                                    earnings_map = pickle.load(f)
                                break
                            except: pass
                    
                    p_bar.empty()
                    st.divider()

                    import plotly.graph_objects as go
                    import numpy as np
                    import datetime as dt_mod
                    
                    now_jst = dt_mod.datetime.utcnow() + dt_mod.timedelta(hours=9)
                    today_date = now_jst.date()
                    
                    hit_count = len(display_targets)
                    if hit_count > 0:
                        st.success(f"🎯 抽出完了: 計 {hit_count} 件のチャート・業績データを出力します。")
                    else:
                        st.warning("📉 表示対象となる銘柄はありませんでした。")

                    for idx, data in enumerate(display_targets):
                        code = data['code']
                        df = data["df"]
                        c_name = name_map.get(str(code)[:4], "名称不明")
                        raw_market = str(market_map.get(str(code)[:4], ""))
                        c_sector = sector_map.get(str(code)[:4], "業種不明")
                        
                        market_badge = "❓ 市場不明"
                        if "プライム" in raw_market or "Prime" in raw_market: market_badge = "👑 プライム"
                        elif "スタンダード" in raw_market or "Standard" in raw_market: market_badge = "🏢 スタンダード"
                        elif "グロース" in raw_market or "Growth" in raw_market: market_badge = "🚀 グロース"
                        
                        hit_badge = data["rank"]
                        # 🚨 ボスの指示により、「🚨 強行偵察(条件未達)」の文言表示を完全撤廃
                        
                        # 🚨 カウントダウンバッジ判定ロジック
                        c_earn_data = earnings_map.get(str(code)[:4] + "0", earnings_map.get(str(code)[:4], []))
                        countdown_badge = " | 📅 次回決算: 未定(未公表)"
                        
                        if isinstance(c_earn_data, dict) and "data" in c_earn_data:
                            c_earn_data = c_earn_data["data"]
                        elif isinstance(c_earn_data, dict):
                            c_earn_data = [c_earn_data]
                            
                        if c_earn_data and isinstance(c_earn_data, list):
                            future_dates = []
                            for row in c_earn_data:
                                if not isinstance(row, dict): continue
                                
                                row_lower = {str(k).lower(): v for k, v in row.items()}
                                v = None
                                for target_key in ["date", "scheduleddate", "schdate", "announcementdate", "discloseddate"]:
                                    if target_key in row_lower:
                                        v = row_lower[target_key]
                                        break
                                        
                                if v and str(v).strip() != "":
                                    try:
                                        # 🚨 空文字や無効値によるNaTクラッシュを完全に回避
                                        d_obj = pd.to_datetime(v)
                                        if pd.notna(d_obj):
                                            d_date = d_obj.date()
                                            if d_date >= today_date:
                                                future_dates.append(d_date)
                                    except: pass
                                    
                            if future_dates:
                                future_dates.sort()
                                next_date = future_dates[0]
                                days_left = (next_date - today_date).days
                                
                                if 0 <= days_left <= 14:
                                    countdown_badge = f" | :red[⚠️ 決算まであと {days_left}日 ({next_date.strftime('%Y-%m-%d')})]"
                                else:
                                    countdown_badge = f" | 📅 次回決算: {next_date.strftime('%Y-%m-%d')}"

                        # バッジの結合と出力
                        st.markdown(f"### 📦 {code} {c_name} | {c_sector} | {market_badge} | {hit_badge}{countdown_badge}")
                        
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
                                    
                            date_col = 'Date' if 'Date' in df_c.columns else df_c.columns[0]
                            df_c[date_col] = pd.to_datetime(df_c[date_col], errors='coerce')
                            df_c = df_c.dropna(subset=[date_col]).sort_values(date_col).reset_index(drop=True)

                            df_c['MA18'] = df_c[c_c_col].rolling(18).mean()
                            df_c['MA50'] = df_c[c_c_col].rolling(50).mean()
                            
                            delta = df_c[c_c_col].diff()
                            gain = delta.clip(lower=0).ewm(alpha=1/14, adjust=False).mean()
                            loss = (-delta.clip(upper=0)).ewm(alpha=1/14, adjust=False).mean()
                            rs = gain / loss.replace(0, 1e-10)
                            df_c['RSI14'] = 100 - (100 / (1 + rs))
                            
                            df_c['RSI14'] = df_c['RSI14'].replace([np.inf, -np.inf], 50.0).fillna(50.0)

                            # カギ足用 ATR(14) を全履歴からWilder RMA（TradingView標準）で算出
                            prev_c_tr = df_c[c_c_col].shift(1)
                            tr_series = pd.concat([
                                (df_c[c_h_col] - df_c[c_l_col]).abs(),
                                (df_c[c_h_col] - prev_c_tr).abs(),
                                (df_c[c_l_col] - prev_c_tr).abs()
                            ], axis=1).max(axis=1)
                            df_c['ATR14'] = tr_series.ewm(alpha=1/14, adjust=False).mean()

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
                            atr14_val = safe_float(q0.get('ATR14', 0.0))
                            
                            c1, c2, c3, c4, c5 = st.columns(5)
                            c1.metric("始値", f"{c_o:,.1f}円")
                            c2.metric("高値", f"{c_h:,.1f}円")
                            c3.metric("安値", f"{c_l:,.1f}円")
                            c4.metric("終値", f"{c_c:,.1f}円")
                            c5.metric("RSI(14日)", f"{rsi_val:.1f}%")
                            
                            # 全履歴でMA18・MA50・RSI14を算出済みの状態から、描画用データのみカレンダー1年分へスライス
                            latest_dt_c = df_c[date_col].max()
                            cutoff_dt_c = latest_dt_c - pd.DateOffset(years=1)
                            df_c_1y = df_c[df_c[date_col] >= cutoff_dt_c].copy()
                            if not df_c_1y.empty:
                                df_c = df_c_1y

                            fig = go.Figure()
                            
                            fig.add_trace(go.Candlestick(
                                x=df_c[date_col], 
                                open=df_c[c_o_col], 
                                high=df_c[c_h_col], 
                                low=df_c[c_l_col], 
                                close=df_c[c_c_col], 
                                name='価格',
                                hovertemplate='・始値：%{open:,.2~f}<br>・高値：%{high:,.2~f}<br>・安値：%{low:,.2~f}<br>・終値：%{close:,.2~f}<extra></extra>',
                                increasing_line_color='#26a69a', increasing_fillcolor='#26a69a',
                                decreasing_line_color='#ef5350', decreasing_fillcolor='#ef5350'
                            ))
                            # 🚨 修正：凡例に名前を表示しつつ、ホバー横の不要なバッジを <extra></extra> で物理遮断
                            fig.add_trace(go.Scatter(x=df_c[date_col], y=df_c['MA18'], mode='lines', line=dict(color='orange', width=1.5), name='18日線', hovertemplate='・18MA：%{y:,.2~f}<extra></extra>'))
                            fig.add_trace(go.Scatter(x=df_c[date_col], y=df_c['MA50'], mode='lines', line=dict(color='cyan', width=1.5), name='50日線', hovertemplate='・50MA：%{y:,.2~f}<extra></extra>'))
                            
                            if scan_mode == "buy" and data.get("buy_sigs"):
                                sig_dates = [pd.to_datetime(d).date() for d in data["buy_sigs"] if pd.notna(d)]
                                sig_df = df_c[df_c[date_col].dt.date.isin(sig_dates)].copy()
                                if not sig_df.empty: 
                                    prices = []
                                    for d in sig_df[date_col]:
                                        p = data["buy_sigs"].get(d)
                                        if p is None: # Timestamp不一致へのフェイルセーフ
                                            p = next((v for k, v in data["buy_sigs"].items() if pd.to_datetime(k).date() == pd.to_datetime(d).date()), 0)
                                        prices.append(p)
                                    # 🚨 修正：y座標(描画位置)は維持しつつ、customdataに計算された本来の価格を注入しホバーへ出力
                                    fig.add_trace(go.Scatter(x=sig_df[date_col], y=sig_df[c_c_col] * 0.95, mode='markers', marker=dict(symbol='triangle-up', color='magenta', size=12), name='買陣形', customdata=prices, hovertemplate='・買陣形：%{customdata:,.2~f}<extra></extra>'))
                            
                            if scan_mode == "sell" and data.get("sell_sigs"):
                                sig_dates = [pd.to_datetime(d).date() for d in data["sell_sigs"] if pd.notna(d)]
                                sig_df = df_c[df_c[date_col].dt.date.isin(sig_dates)].copy()
                                if not sig_df.empty: 
                                    prices = []
                                    for d in sig_df[date_col]:
                                        p = data["sell_sigs"].get(d)
                                        if p is None:
                                            p = next((v for k, v in data["sell_sigs"].items() if pd.to_datetime(k).date() == pd.to_datetime(d).date()), 0)
                                        prices.append(p)
                                    fig.add_trace(go.Scatter(x=sig_df[date_col], y=sig_df[c_c_col] * 1.05, mode='markers', marker=dict(symbol='triangle-down', color='yellow', size=12), name='空売陣形', customdata=prices, hovertemplate='・空売陣形：%{customdata:,.2~f}<extra></extra>'))

                            v_colors = ['#26a69a' if c >= o else '#ef5350' for c, o in zip(df_c[c_c_col], df_c[c_o_col])]
                            fig.add_trace(go.Bar(
                                x=df_c[date_col], 
                                y=df_c[c_v_col], 
                                name='出来高', 
                                hovertemplate='・出来高：%{y:,.0f}<extra></extra>',
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
                                hoverformat='・日付：%Y/%m/%d',
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
                                'margin': dict(l=0, r=40, t=60, b=10),
                                'xaxis': xaxis_config,
                                'dragmode': 'pan',
                                'hovermode': 'x unified',
                                'hoverlabel': dict(bgcolor="rgba(0,0,0,0.8)", font_size=13, font_family="sans-serif", align="left"),
                                'legend': dict(
                                    orientation="h",
                                    yanchor="bottom",
                                    y=1.02,
                                    xanchor="center",
                                    x=0.5,
                                    bgcolor="rgba(0,0,0,0)"
                                )
                            }
                            
                            if y_min and y_max:
                                layout_args['yaxis'] = dict(domain=[0.20, 1.0], range=[y_min, y_max], autorange=False, fixedrange=False, side='right')
                            else:
                                layout_args['yaxis'] = dict(domain=[0.20, 1.0], autorange=True, fixedrange=False, side='right')

                            layout_args['yaxis2'] = dict(domain=[0.0, 0.30], rangemode='tozero', autorange=True, fixedrange=False, showticklabels=False, showgrid=False, side='right')
                                
                            fig.update_layout(**layout_args)
                            
                            st.caption("💡 **狙撃手マニュアル**: 初期表示は直近3ヶ月にオートフォーカスしています。過去に遡ってローソク足が見切れた場合は、右側の価格軸（Y軸の数字）を直接上下にドラッグするか、チャート内で **ダブルクリック** するとY軸が自動追従（オートフィット）します。")
                            st.plotly_chart(fig, use_container_width=True, config={'scrollZoom': True, 'displayModeBar': True}, key=f"tab3_chart_{code}_{scan_mode}_{idx}")

                            with st.expander(f"📐 カギ足チャートを比較表示（終値・1年 / {kagi_rev_mode}）", expanded=False):
                                fig_kagi, kagi_info = build_kagi_chart(
                                    df_c,
                                    date_col=date_col,
                                    close_col=c_c_col,
                                    reversal_mode=kagi_rev_mode,
                                    atr_val=atr14_val,
                                )
                                if fig_kagi is not None:
                                    st.caption(f"📐 **カギ足設定**: {kagi_info}（※各転換点へカーソルを合わせると日付・価格・状態を表示）")
                                    st.plotly_chart(fig_kagi, use_container_width=True, config={'scrollZoom': True, 'displayModeBar': True}, key=f"tab3_kagi_{code}_{scan_mode}_{idx}")
                                else:
                                    st.info("ℹ️ カギ足を描画するための価格データが不足しています。")

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

            if scan_succeeded:
                results_tab3 = [{"Code": d["code"], "Rank": d["rank"], "Mode": scan_mode} for d in display_targets]
                if results_tab3:
                    hit_codes_str = ",".join([str(r["Code"]) for r in results_tab3])
                    st.text_area(f"📋 分析完了銘柄（コピペ用・計 {len(results_tab3)}件）", value=hit_codes_str, height=70)

                now_jst_t3 = get_now_jst_str()
                st.session_state['tab3_results'] = results_tab3
                st.session_state['tab3_updated_at'] = now_jst_t3
                st.session_state['tab3_last_mode'] = scan_mode
                save_user_scan_state({
                    "tab3_state": {
                        "mode": scan_mode,
                        "store_buy": st.session_state.get("tab3_store_buy", ""),
                        "store_sell": st.session_state.get("tab3_store_sell", ""),
                        "manual_codes": st.session_state.get("tab3_manual_codes", ""),
                        "results": results_tab3,
                        "updated_at": now_jst_t3,
                    }
                })

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

    with st.expander("📥 CSV一括登録 (約定履歴の自動取り込み)"):
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
                        
                        records = []
                        c_col = '銘柄コード' if '銘柄コード' in df_csv.columns else '銘柄'
                        for code, group in df_csv.groupby(c_col):
                            all_trades = []
                            for _, row in group.iterrows():
                                t_type = str(row['取引']) if '取引' in df_csv.columns else ""
                                item = {'date': str(row['約定日']).replace('/', '-'), 'qty': int(row['約定数量']), 'price': float(row['約定単価']), 'code': str(code).strip(), 'type': t_type}
                                all_trades.append(item)
                            all_trades.sort(key=lambda x: x['date'])
                            
                            long_pos, short_pos = [], []
                            for t in all_trades:
                                qty, price = t['qty'], t['price']
                                if "買" in t['type']:
                                    m_qty, m_amt = 0, 0
                                    while qty > 0 and len(short_pos) > 0:
                                        sp = short_pos[0]
                                        if sp['qty'] <= qty:
                                            m_qty += sp['qty']; m_amt += sp['price'] * sp['qty']; qty -= sp['qty']; short_pos.pop(0)
                                        else:
                                            m_qty += qty; m_amt += sp['price'] * qty; sp['qty'] -= qty; qty = 0
                                    if m_qty > 0:
                                        avg_sell = m_amt / m_qty
                                        records.append({"決済日": t['date'], "銘柄": t['code'], "規模": get_scale_for_code(t['code']), "戦術": "空売", "買値": int(price), "売値": int(avg_sell), "株数": int(m_qty), "損益額(円)": int((avg_sell-price)*m_qty), "損益(%)": round(((avg_sell/price)-1)*100, 2), "規律": "不明", "敗因/勝因メモ": "CSV自動(空売)"})
                                    if qty > 0: long_pos.append({'date': t['date'], 'qty': qty, 'price': price})
                                elif "売" in t['type']:
                                    m_qty, m_amt = 0, 0
                                    while qty > 0 and len(long_pos) > 0:
                                        lp = long_pos[0]
                                        if lp['qty'] <= qty:
                                            m_qty += lp['qty']; m_amt += lp['price'] * lp['qty']; qty -= lp['qty']; long_pos.pop(0)
                                        else:
                                            m_qty += qty; m_amt += lp['price'] * qty; lp['qty'] -= qty; qty = 0
                                    if m_qty > 0:
                                        avg_buy = m_amt / m_qty
                                        records.append({"決済日": t['date'], "銘柄": t['code'], "規模": get_scale_for_code(t['code']), "戦術": "買", "買値": int(avg_buy), "売値": int(price), "株数": int(m_qty), "損益額(円)": int((price-avg_buy)*m_qty), "損益(%)": round(((price/avg_buy)-1)*100, 2), "規律": "不明", "敗因/勝因メモ": "CSV自動(買)"})
                                    if qty > 0: short_pos.append({'date': t['date'], 'qty': qty, 'price': price})

                        if records:
                            st.session_state.aar_df_stable = pd.concat([st.session_state.aar_df_stable, pd.DataFrame(records)], ignore_index=True).sort_values(['決済日', '銘柄'], ascending=[False, True]).reset_index(drop=True)
                            save_aar_db(st.session_state.aar_df_stable); st.rerun()
                except Exception as e: st.error(f"エラー: {e}")

    st.markdown("#### 📊 司令部 総合戦績")
    w_df = st.session_state.aar_df_stable.copy()
    
    if not w_df.empty:
        min_date = pd.to_datetime(w_df['決済日']).min().date()
        max_date = pd.to_datetime(w_df['決済日']).max().date()
        
        d_col1, d_col2 = st.columns(2)
        start_d = d_col1.date_input("🗓️ 抽出開始日", value=min_date, min_value=min_date, max_value=max_date, key="aar_start_date")
        end_d = d_col2.date_input("🗓️ 抽出終了日", value=max_date, min_value=min_date, max_value=max_date, key="aar_end_date")
        
        # 指定された範囲内でデータフレームをフィルタリング
        w_df = w_df[(pd.to_datetime(w_df['決済日']).dt.date >= start_d) & (pd.to_datetime(w_df['決済日']).dt.date <= end_d)]
    
    if not w_df.empty:
        m1, m2, m3, m4 = st.columns(4)
        tot_p = w_df['損益額(円)'].sum()
        w_rate = (len(w_df[w_df['損益額(円)'] > 0]) / len(w_df)) * 100
        loss_sum = abs(w_df[w_df['損益額(円)'] < 0]['損益額(円)'].sum())
        pf = round(w_df[w_df['損益額(円)'] > 0]['損益額(円)'].sum() / loss_sum, 2) if loss_sum > 0 else 9.9
        
        m1.metric("総交戦数", f"{len(w_df)}回")
        m2.metric("勝率", f"{w_rate:.1f}%")
        m3.metric("損益額", f"{int(tot_p):,}円")
        m4.metric("PF", f"{pf}")
        
        import plotly.express as px
        df_curv = w_df.sort_values('決済日', ascending=True).copy()
        df_curv['累積'] = df_curv['損益額(円)'].cumsum()
        fig = px.line(df_curv, x='決済日', y='累積', markers=True, color_discrete_sequence=["#26a69a"])
        fig.update_layout(paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0.1)', height=350, margin=dict(l=10, r=10, t=10, b=10))
        st.plotly_chart(fig, use_container_width=True)
    elif 'start_d' in locals():
        st.warning("選択された期間に交戦記録はありません。")

    st.divider()
    st.markdown("##### 📜 詳細交戦記録 (キル・ログ)")
    
    display_df = w_df.copy()
    
    try:
        master_df = load_master()
        name_map = dict(zip(master_df['Code'].astype(str).str[:4], master_df['CompanyName']))
        if '銘柄' in display_df.columns:
            display_df.insert(display_df.columns.get_loc('銘柄') + 1, '企業名', display_df['銘柄'].astype(str).str[:4].map(name_map).fillna("名称不明"))
    except Exception:
        if '銘柄' in display_df.columns:
            display_df.insert(display_df.columns.get_loc('銘柄') + 1, '企業名', "名称不明")
            
    if '戦術' in display_df.columns:
        display_df = display_df.drop(columns=['戦術'])
    if '規律' in display_df.columns:
        display_df = display_df.drop(columns=['規律'])
    
    def apply_performance_colors(val):
        try:
            v = float(val)
            if v >= 1.0: return 'color: #26a69a; font-weight: bold;'
            elif v <= -1.0: return 'color: #ef5350; font-weight: bold;'
            else: return 'color: #ffffff;'
        except: return 'color: #ffffff;'

    styled_view = display_df.style.map(apply_performance_colors, subset=['損益額(円)', '損益(%)'])
    
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
                    "戦術": None,
                    "規律": None,
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

# ==========================================
# 🛠️ 参謀直通デバッグターミナル（生データCSV抽出）
# ==========================================
if st.session_state.get("current_user_role", "user") == "admin":
    st.markdown("---")
    with st.expander("🛠️ 参謀直通デバッグターミナル（生データCSV抽出）", expanded=False):
        debug_code = st.text_input("抽出する銘柄コードを入力（例: 8627）", value="8628")
        if st.button("📡 生データを抽出してCSV生成"):
            if debug_code.strip():
                try:
                    db = load_local_fundamentals_db()
                    df_debug = None
                    code_str = debug_code.strip()[:4]
                    
                    if isinstance(db, dict):
                        df_debug = db.get(code_str + "0")
                        if df_debug is None:  
                            df_debug = db.get(code_str)
                    elif isinstance(db, pd.DataFrame):
                        c_col = 'Code' if 'Code' in db.columns else ('code' if 'code' in db.columns else None)
                        if c_col:
                            df_debug = db[db[c_col].astype(str).str.startswith(code_str)]
                    
                    if df_debug is not None and (isinstance(df_debug, pd.DataFrame) and not df_debug.empty):
                        st.write(f"✅ **抽出成功: {code_str} 生データ**")
                        csv_text = df_debug.tail(16).to_csv(index=False)
                        st.text_area("📋 【ここをクリックして Ctrl+A で全選択し、コピーしてください】", value=csv_text, height=300)
                    else:
                        st.warning(f"⚠️ {code_str} のデータが見つかりません。")
                except Exception as e:
                    st.error(f"🚨 抽出エラー: {e}")
