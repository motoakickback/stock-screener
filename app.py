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
        
    for col in df.columns:
        col_type = df[col].dtype
        
        if col_type == 'float64':
            df[col] = df[col].astype('float32')
        elif col_type == 'int64':
            df[col] = df[col].astype('int32')
            
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
                                    if val is not None:
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
nikkei_pct_api = weather['nikkei']['pct'] if weather else 0.0

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

        df['MA25'] = df[close_col].rolling(window=25).mean()
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
            
            fig.add_trace(go.Scatter(
                x=df['Date'], y=df[close_col], name='日経平均', mode='lines', 
                line=dict(color='#FFD700', width=2), hovertemplate='日経平均: ¥%{y:,.0f}<extra></extra>'
            ))
            fig.add_trace(go.Scatter(
                x=df['Date'], y=df['MA25'], name='25日線', mode='lines', 
                line=dict(color='rgba(255, 255, 255, 0.5)', width=1.5, dash='dot'), hovertemplate='25日線: ¥%{y:,.0f}<extra></extra>'
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
        
        gaps = [o[i] - c[i-1] if o[i] > c[i-1] else c[i-1] - o[i] for i in range(-3, 0)]
        if all(g > 0 for g in gaps) and c[-1] > c[-4]:
            patterns.append({"date": d[-1], "label": "【酒田・買三空】", "text": "🔴 【酒田・買い三空】最終噴出。過熱の極致。利確の急所。", "color": "#ef5350", "type": "bear"})

    if is_low_zone:
        if check_oversold_ultimate(df):
            patterns.append({"date": d[-1], "label": "【酒田・陰の極み】", "text": "🟢 【酒田・陰の極み】底打ち最終波形。売り枯れの果て。反転攻勢の急所。狙撃準備。", "color": "#26a69a", "type": "bull"})
        if all(c[i] > o[i] for i in range(-3, 0)) and all(c[i] > c[i-1] for i in range(-2, 0)):
            patterns.append({"date": d[-1], "label": "【酒田・赤三兵】", "text": "🟢 【酒田・赤三兵】安値圏からの狼煙。底打ち反転。追撃準備。", "color": "#26a69a", "type": "bull"})
            
        gaps = [o[i] - c[i-1] if o[i] > c[i-1] else c[i-1] - o[i] for i in range(-3, 0)]
        if all(g > 0 for g in gaps) and c[-1] < c[-4]:
            patterns.append({"date": d[-1], "label": "【酒田・売三空】", "text": "🟢 【酒田・売り三空】三度の窓。売り枯れの極み。反転狙撃好機。", "color": "#26a69a", "type": "bull"})

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
    try:
        r = api_session.get(url, timeout=3.0)
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

    # 🚨 V2とV1のフィールド名（キー名）の揺れを両方とも吸収
    op = latest.get("OPnumber", latest.get("OperatingProfit"))
    np_val = latest.get("NPnumber", latest.get("NetIncome"))
    eq = latest.get("Eqnumber", latest.get("Equity"))
    eq_ratio = latest.get("EqARnumber", latest.get("EquityRatio"))
    eps = latest.get("EPSnumber", latest.get("EarningsPerShare"))
    bps = latest.get("BPSnumber", latest.get("BookValuePerShare"))
    shares = latest.get("ShOutFYnumber", latest.get("NumberOfIssuedAndOutstandingSharesAtTheEndOfFiscalYearIncludingTreasuryStock"))
    
    res = {
        "op": op, "cap": latest.get("MarketCapitalization"), 
        "er": eq_ratio, "roe": None, "per": None, "pbr": None
    }
    
    # ROEの計算 (当期純利益 ÷ 自己資本)
    if np_val is not None and eq is not None and float(eq) != 0:
        res["roe"] = (float(np_val) / float(eq)) * 100
    elif eps is not None and bps is not None and float(bps) != 0:
        res["roe"] = (float(eps) / float(bps)) * 100

    # 🚨 yfinanceで最新株価を取得し、PER / PBR / 時価総額をリアルタイム計算
    try:
        import yfinance as yf
        tk = yf.Ticker(f"{code}.T")
        info = tk.info
        
        # yfinanceから直接取れる場合はそれを優先
        res["per"] = info.get("trailingPE", info.get("forwardPE"))
        res["pbr"] = info.get("priceToBook")
        res["cap"] = info.get("marketCap", res.get("cap"))
        
        cur_price = info.get("currentPrice", info.get("regularMarketPrice", info.get("previousClose")))
        
        # 直接取れなかった場合は、J-Quantsの財務情報と株価から自力で計算する
        if cur_price:
            if res["per"] is None and eps and float(eps) > 0:
                res["per"] = float(cur_price) / float(eps)
            if res["pbr"] is None and bps and float(bps) > 0:
                res["pbr"] = float(cur_price) / float(bps)
            if res["cap"] is None and shares and float(shares) > 0:
                res["cap"] = float(cur_price) * float(shares)
    except:
        pass # yfinanceの通信が失敗しても、ROE等の基本データは死守して返す
        
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

@st.cache_data(ttl=3600, show_spinner=False)
def get_single_data(code, yrs=1):
    base = datetime.utcnow() + timedelta(hours=9)
    f_d = (base - timedelta(days=365*yrs)).strftime('%Y%m%d')
    t_d = base.strftime('%Y%m%d')
    result = {"bars": [], "events": {"dividend": [], "earnings": []}}
    try:
        api_code = str(code) if len(str(code)) >= 5 else str(code) + "0"
        
        url_bars = f"{BASE_URL}/equities/bars/daily?code={api_code}&from={f_d}&to={t_d}"
        r_bars = api_session.get(url_bars, timeout=10.0)
        if r_bars.status_code == 200: 
            result["bars"] = r_bars.json().get("daily_quotes") or r_bars.json().get("data") or []
            
        url_earn = f"{BASE_URL}/fins/announcement?code={api_code}"
        r_earn = api_session.get(url_earn, timeout=5.0)
        if r_earn.status_code == 200:
            result["events"]["earnings"] = r_earn.json().get("announcement", [])
            
        url_div = f"{BASE_URL}/fins/dividend?code={api_code}"
        r_div = api_session.get(url_div, timeout=5.0)
        if r_div.status_code == 200:
            result["events"]["dividend"] = r_div.json().get("dividend", [])
            
    except Exception as e: 
        pass
        
    return result

def get_nikkei_macro_status():
    """完全防弾仕様：列名不一致によるシステム停止を根絶した単一エンジン"""
    w = get_macro_weather()
    if not w or "nikkei" not in w:
        return {"status": "取得不可", "div_rate": 0.0, "close": 0, "ma25": 0, "icon": "⚪", "color": "#888"}
    
    df = w["nikkei"]["df"].copy()
    if len(df) < 25:
        # 価格が取得できれば、それを返す
        price = w["nikkei"].get("price", 0)
        return {"status": "データ不足", "div_rate": 0.0, "close": price, "ma25": 0, "icon": "⚪", "color": "#888"}
        
    # 🚨 最終モグラ駆逐パッチ：終値カラムを安全に動的取得
    close_col = next((c for c in ['AdjC', 'Close', 'close', 'C', 'c'] if c in df.columns), None)
    
    if not close_col:
        return {"status": "列名異常", "div_rate": 0.0, "close": w["nikkei"]["price"], "ma25": 0, "icon": "⚪", "color": "#888"}

    # 1次元Seriesとして安全に抽出
    s = df[close_col]
    if isinstance(s, pd.DataFrame):
        s = s.iloc[:, 0]
        
    df['MA25'] = pd.to_numeric(s, errors='coerce').rolling(window=25).mean()
    price = w["nikkei"]["price"]
    ma25 = df['MA25'].iloc[-1]
    
    # 🚨 乖離率の算出
    if pd.notna(ma25) and ma25 > 0:
        div_rate = ((price / ma25) - 1) * 100
    else:
        div_rate = 0.0
        
    if div_rate >= 5.0:
        return {"status": "地合い警戒", "div_rate": div_rate, "close": price, "ma25": ma25, "icon": "🔥", "color": "#ef5350"}
    elif div_rate <= -5.0:
        return {"status": "地合いチャンス", "div_rate": div_rate, "close": price, "ma25": ma25, "icon": "🚨", "color": "#ef5350"}
    else:
        return {"status": "地合いニュートラル", "div_rate": div_rate, "close": price, "ma25": ma25, "icon": "🚢", "color": "#26a69a"}

# =========================================================
# 🚀 共通エンジン：進捗バー・件数表示 完全復旧版
# =========================================================
@st.cache_data(ttl=86400, max_entries=1, show_spinner=False)
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
    # 🚨 ボスの要求：4部隊で突撃
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as exe:
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
    # ここで元のコード同様、シンプルに処理
    full_df['Code'] = full_df['Code'].astype(str).apply(lambda x: x if len(x) >= 5 else x + "0")
    
    gc.collect()
    # 🚨 以前と同じ条件でDrop。これでAdjCが正しく存在すれば必ずヒットします
    return full_df.dropna(subset=['AdjC']).sort_values(['Code', 'Date']).reset_index(drop=True)

def fetch_and_compress_single_day(dt):
    # 🚨 巡航ブレーキ
    time.sleep(0.5)
    
    for attempt in range(3):
        try:
            r = api_session.get(f"{BASE_URL}/equities/bars/daily?date={dt}", timeout=20.0)
            if r.status_code == 200:
                raw_json = r.json()
                # 🚨 探索：ヒットしていた頃のシンプルな抽出
                data = raw_json.get("daily_quotes") or raw_json.get("data") or raw_json.get("results") or []
                if not data: return None
                
                temp_df = pd.DataFrame(data)
                
                # 🚨 以前の「動的なカラム名対応」ロジックを保持
                # 'AdjC' が無ければ 'Close' 等から探す冗長な変換を避け、
                # APIが返すキー名をそのまま活かします
                return temp_df
            
            elif r.status_code == 429:
                time.sleep(1.0)
            else:
                return None
        except:
            time.sleep(0.5)
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

def get_assault_triage_info(gc_days, lc, rsi_v, df_chart, is_strict=False):
    if df_chart is None or df_chart.empty:
        return "圏外 💀", "#424242", 0, ""

    has_top_trap = False
    try:
        sakata_s = detect_sakata_patterns(df_chart)
        sakata_texts = "".join([p.get('text', '') for p in sakata_s])
        if any(x in sakata_texts for x in ["三山", "三尊", "二重天井", "買い三空", "二重頂", "三尊天井"]):
            has_top_trap = True
    except Exception:
        pass

    if has_top_trap:
        return "圏外 💀", "#424242", 0, "天井地雷検知(排除)"

    tactics = st.session_state.get("sidebar_tactics", "⚖️ バランス (掟達成率 ＞ 到達度)")
    is_assault_mode = "狙撃優先" in tactics
    
    row = df_chart.iloc[-1]
    ma5, ma25 = 0.0, 0.0
    
    for k in ['MA5', 'ma5', 'MA_5', 'ma_5', 'SMA5', 'sma5']:
        if k in row and pd.notna(row[k]):
            ma5 = float(row[k])
            break
            
    for k in ['MA25', 'ma25', 'MA_25', 'ma_25', 'SMA25', 'sma25']:
        if k in row and pd.notna(row[k]):
            ma25 = float(row[k])
            break

    if gc_days > 0 and ma5 > 0 and ma25 > 0 and (ma5 < ma25):
        gc_days = 0

    if gc_days <= 0:
        if len(df_chart) >= 2 and ma5 > 0 and ma25 > 0:
            prev_row = df_chart.iloc[-2]
            prev_ma5 = 0.0
            
            for k in ['MA5', 'ma5', 'MA_5', 'ma_5', 'SMA5', 'sma5']:
                if k in prev_row and pd.notna(prev_row[k]):
                    prev_ma5 = float(prev_row[k])
                    break
            
            dist_pct = ((ma5 / ma25) - 1) * 100
            
            is_pre_gc = (
                (ma5 < ma25) and                         
                (lc > ma5) and (lc > ma25) and           
                (-2.0 <= dist_pct < 0.0) and             
                (ma5 > prev_ma5)                         
            )
            
            if is_pre_gc:
                return "S+🎯", "#ff5252", 95, "明日GC見込(激熱)"
                
        return "圏外 💀", "#424242", 0, ""

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

# ==============================================================================
# 🎯 1. 新・待伏せトリアージ判定エンジン（MACD完全排除・ATR価格アクション特化）
# ==============================================================================

def get_ambush_triage_info(lc, buy_target, atr):
    """
    買目標値と14日ATRを用いた精密位置判定（遅行指標一切不使用）
    """
    # 条件A：現在値が目標値 + 1ATRより高い（目標まで距離あり）
    if lc > (buy_target + atr):
        return "🟡【未達・監視】目標地点まで距離あり。到達を待つ。", "#FFC107"
    
    # 条件B：目標値±1ATRの範囲内（迎撃準備）
    elif (buy_target - atr) <= lc <= (buy_target + atr):
        return "🟢【迎撃圏内】目標地点に到達。反転シグナル（ローソク足等）に注視し狙撃準備。", "#4CAF50"
    
    # 条件C：目標値 - 1ATRより低い（底割れ）
    else:
        return "💀【底割れ・撤退】サポートライン完全崩壊。待ち伏せ失敗。", "#F44336"


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
    
    # 4. 新・待伏せトリアージの実行（MACD関連変数は完全消去済）
    triage_status, triage_color = get_ambush_triage_info(current_p, bt_target, atr_val)
    
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

def analyze_stealth_scope_tab3(df: pd.DataFrame, code: str, company_name: str) -> dict:
    """
    【TAB3精密スコープ用】潜伏（Stealth）銘柄専用の分析パイプライン
    """
    df_sub = df.copy()
    
    if len(df_sub) < 25:
        return {
            "rank": "圏外💀", 
            "alerts": ["⚠️ データ不足による解析不能"], 
            "entry_trigger": 0, "stop_loss": 0, "take_profit": 0, "risk_pct": 0.0
        }

    c_col = 'AdjC' if 'AdjC' in df_sub.columns else 'Close'
    o_col = 'AdjO' if 'AdjO' in df_sub.columns else 'Open'
    h_col = 'AdjH' if 'AdjH' in df_sub.columns else 'High'
    l_col = 'AdjL' if 'AdjL' in df_sub.columns else 'Low'

    # 【事前計算】ATR（14日）およびMA25の算出
    df_sub['prev_C'] = df_sub[c_col].shift(1)
    df_sub['TR'] = np.maximum(
        df_sub[h_col] - df_sub[l_col],
        np.maximum(
            abs(df_sub[h_col] - df_sub['prev_C']),
            abs(df_sub[l_col] - df_sub['prev_C'])
        )
    )
    df_sub['ATR14'] = df_sub['TR'].rolling(window=14).mean()
    df_sub['MA25'] = df_sub[c_col].rolling(window=25).mean()

    latest = df_sub.iloc[-1]
    prev = df_sub.iloc[-2]

    c_val = latest[c_col]
    o_val = latest[o_col]
    h_val = latest[h_col]
    l_val = latest[l_col]
    prev_c_val = prev[c_col]
    atr14_val = latest['ATR14']
    ma25_val = latest['MA25']

    alerts = []
    rank = "A級💎"

    # 1. 潜伏特有のシグナル・アラート検知
    body_size = abs(c_val - o_val)
    day_range = h_val - l_val
    if day_range > 0 and body_size <= (day_range * 0.10):
        alerts.append("🟢【極小十字線】煮詰まりの極致")

    if o_val <= (prev_c_val - atr14_val):
        alerts.append("💀【偽潜伏・パニック警戒】ギャップダウンによるトレンド崩壊")
        rank = "圏外💀"

    # 2. 潜伏専用トレードセットアップ（売買ライン）の自動算出
    high_3d = df_sub[h_col].iloc[-3:].max()
    entry_trigger = int(round(high_3d + 1))
    stop_loss = int(round(ma25_val - (atr14_val * 0.5)))
    take_profit = int(round(entry_trigger + ((entry_trigger - stop_loss) * 2)))

    # 3. 資金管理（リスク幅）の適格性ジャッジ
    if entry_trigger > 0:
        risk_pct = (entry_trigger - stop_loss) / entry_trigger
    else:
        risk_pct = 1.0

    if risk_pct > 0.08:
        alerts.append("⚠️ 【リスク超過】損切り幅が8%を超えています。ロットを縮小するか見送りを推奨")

    result_payload = {
        "code": code,
        "company_name": company_name,
        "mode": "Stealth",
        "rank": rank,
        "alerts": alerts,
        "current_price": int(round(c_val)),
        "ma25": int(round(ma25_val)),
        "atr14": round(atr14_val, 2),
        "entry_trigger": entry_trigger,
        "stop_loss": stop_loss,
        "take_profit": take_profit,
        "risk_pct": round(risk_pct * 100, 2)
    }

    return result_payload

def draw_chart(df, targ_p, sakata=[], chart_key=None):
    import plotly.graph_objects as go
    from datetime import timedelta
    import pandas as pd
    import numpy as np
    import time

    if df is None or df.empty:
        return

    df_plot = df.copy()
    
    if 'MA5' not in df_plot.columns: df_plot['MA5'] = df_plot['AdjC'].rolling(5).mean()
    if 'MA25' not in df_plot.columns: df_plot['MA25'] = df_plot['AdjC'].rolling(25).mean()
    if 'MA75' not in df_plot.columns: df_plot['MA75'] = df_plot['AdjC'].rolling(75).mean()

    df_plot['arrow'] = df_plot['AdjC'].diff().apply(lambda x: " ▲" if x > 0 else " ▼" if x < 0 else "")

    ma5_str = df_plot['MA5'].apply(lambda x: f"{x:,.0f}" if pd.notna(x) else "-")
    ma25_str = df_plot['MA25'].apply(lambda x: f"{x:,.0f}" if pd.notna(x) else "-")
    ma75_str = df_plot['MA75'].apply(lambda x: f"{x:,.0f}" if pd.notna(x) else "-")

    customdata = np.column_stack((df_plot['arrow'], ma5_str, ma25_str, ma75_str))

    fig = go.Figure()

    fig.add_trace(go.Candlestick(
        x=df_plot['Date'],
        open=df_plot['AdjO'], high=df_plot['AdjH'],
        low=df_plot['AdjL'], close=df_plot['AdjC'],
        name='価格',
        customdata=customdata,
        hovertemplate=(
            "価格：<br>"
            "始値：%{open:,.0f}<br>"
            "終値：%{close:,.0f}%{customdata[0]}<br>"
            "高値：%{high:,.0f}<br>"
            "安値：%{low:,.0f}<br>"
            "MA5 ：%{customdata[1]}<br>"
            "MA25：%{customdata[2]}<br>"
            "MA75：%{customdata[3]}<br>"
            "<extra></extra>"
        ),
        increasing_line_color='#26a69a', 
        decreasing_line_color='#ef5350'
    ))

    ma_configs = [('MA5', '#ffd700', 'MA5'), ('MA25', '#42a5f5', 'MA25'), ('MA75', '#ab47bc', 'MA75')]
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

    fig.update_layout(
        template='plotly_dark', height=550, margin=dict(l=0, r=0, t=30, b=80),
        paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)', hovermode="x unified",
        hoverlabel=dict(bgcolor="rgba(20, 20, 20, 0.95)", font_size=13, font_family="Consolas"),
        xaxis_rangeslider_visible=True, xaxis_rangeslider_thickness=0.04,
        yaxis=dict(side="right", tickformat=",.0f", gridcolor='rgba(255,255,255,0.05)', autorange=True, fixedrange=False),
        xaxis=dict(showgrid=True, gridcolor='rgba(255,255,255,0.05)', range=[df_plot['Date'].max() - timedelta(days=65), df_plot['Date'].max() + timedelta(days=2)]),
        legend=dict(orientation="h", yanchor="top", y=-0.32, xanchor="center", x=0.5, font=dict(color="#eee", size=11))
    )

    st.plotly_chart(fig, use_container_width=True, config={'displayModeBar': False, 'responsive': True}, key=f"{chart_key}_{int(time.time()*1000)}")

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

# ==========================================
# 🛡️ 0. 除外銘柄コードのローカルファイル永続化シールド
# ==========================================
EXCLUDE_FILE = "exclude_codes.txt"

if "gigi_input" not in st.session_state:
    if os.path.exists(EXCLUDE_FILE):
        try:
            with open(EXCLUDE_FILE, "r", encoding="utf-8") as f:
                st.session_state.gigi_input = f.read().strip()
        except:
            st.session_state.gigi_input = ""
    else:
        st.session_state.gigi_input = ""

def save_exclude_codes_to_file():
    try:
        current_input = st.session_state.get("gigi_input", "")
        with open(EXCLUDE_FILE, "w", encoding="utf-8") as f:
            f.write(str(current_input).strip())
    except:
        pass

def extended_save_settings():
    save_exclude_codes_to_file()
    save_settings()

# --- 4. サイドバー UI 展開 ---
st.sidebar.title("🛠️ 戦術コンソール")

# --- 🌪️ ボラティリティ・フィルターの設定 ---
st.sidebar.markdown("### 🌪️ ボラティリティ審査")
st.session_state.f_vol_min = st.sidebar.slider(
    "最小ボラ率 (ATR/価格 %)", 
    0.0, 2.0, float(st.session_state.get("f_vol_min_slider", 0.5)), 0.1, 
    help="1ATRが株価の何%以上かを判定。0.5%未満はTAB1/2の検索結果から排除されます。",
    key="f_vol_min_slider"
)

st.sidebar.markdown("---")

# --- 🌐 マクロ地合い連動システム (完全同期・単一エンジン版) ---
st.sidebar.markdown("### 🌐 マクロ地合い連動")
use_macro = st.sidebar.toggle("地合い連動を有効化", value=True)

st.session_state.push_penalty = 0.0
st.session_state.rsi_penalty = 0
st.session_state.macro_alert = "🟢 平時（通常ロジック稼働）"

def get_latest_macro_sync():
    """全タブ共通で使う、常に最新の日経平均と乖離率を算出する単一エンジン"""
    w = get_macro_weather()
    if not w or "nikkei" not in w:
        return {"status": "取得失敗", "div_rate": 0.0}
    
    df = w["nikkei"]["df"].copy()
    if len(df) < 25:
        return {"status": "データ不足", "div_rate": 0.0}
        
    # 🚨 モグラ駆逐パッチ：日経平均データの終値カラムを安全に取得
    close_col = next((c for c in ['AdjC', 'Close', 'close', 'C', 'c'] if c in df.columns), None)
    
    if close_col:
        # 万が一DataFrame化(重複)していても最初の1列だけを抽出し、確実に数値化
        s = df[close_col]
        if isinstance(s, pd.DataFrame):
            s = s.iloc[:, 0]
        df['MA25'] = pd.to_numeric(s, errors='coerce').rolling(window=25).mean()
    else:
        # 終値が見つからない場合の緊急回避
        return {"status": "データ異常", "div_rate": 0.0}
        
    price = w["nikkei"]["price"]
    ma25 = df['MA25'].iloc[-1]
    div_rate = ((price / ma25) - 1) * 100
    
    if div_rate >= 5.0: return {"status": "地合い警戒", "div_rate": div_rate}
    elif div_rate <= -5.0: return {"status": "地合いチャンス", "div_rate": div_rate}
    else: return {"status": "地合いニュートラル", "div_rate": div_rate}

# 🚨 ここから下のブロックが消えていたため復旧しました！
if use_macro:
    api_nikkei_pct = weather['nikkei']['pct'] if 'weather' in locals() and weather else 0.0
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

    # 🚨 常に最新のMA25乖離率を取得してアラート文を構築
    macro = get_latest_macro_sync()
    div_v = macro['div_rate']
    
    base_alert = f"🌐【{macro['status']}】日経乖離率 {div_v:+.2f}%。"
    if macro['status'] == "地合い警戒": base_alert += "天井掴みに注意。"
    elif macro['status'] == "地合いチャンス": base_alert += "押し目買い好機。"
    else: base_alert += "個別銘柄の動きを重視。"

    st.session_state.macro_alert = prefix + base_alert

st.sidebar.divider()

# ==========================================
# 📂 1.5. 戦略的セクター制御（新兵装追加）
# ==========================================
st.sidebar.header("📂 戦略的セクター制御")

current_f_max = st.session_state.get("f_max_stocks_slider", 30)
st.session_state.f_max_stocks_per_sector = st.sidebar.slider(
    "1セクターあたりの最大表示数",
    1, 30, int(current_f_max),
    key="f_max_stocks_slider",
    help="特定セクターへの集中度を調整します。"
)

st.sidebar.divider()
st.sidebar.header("🎯 戦略テーマ選別")

selected_themes = st.sidebar.multiselect(
    "注目テーマ（複数選択可）",
    options=list(PRESET_THEMES.keys()),
    default=[],
    help="選択したテーマの銘柄のみを抽出します。"
)

custom_theme_input = st.sidebar.text_input(
    "手動コード追加 (例: 9501, 3778)",
    value="",
    help="リストにない期待銘柄を即座に追加できます。"
)

target_theme_codes = set()
for t in selected_themes:
    target_theme_codes.update(PRESET_THEMES[t])

if custom_theme_input:
    custom_list = [c.strip() for c in custom_theme_input.split(",") if c.strip()]
    target_theme_codes.update(custom_list)

st.sidebar.divider()

if master_df is not None and not master_df.empty:
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
# 📍 2. ターゲット選別（原本 100% 維持）
# ==========================================
st.sidebar.header("📍 ターゲット選別")
market_options = ["🏢 大型株 (プライム・一部)", "🚀 中小型株 (スタンダード・グロース)"]
st.sidebar.selectbox("市場ターゲット", options=market_options, index=market_options.index(st.session_state.preset_market) if st.session_state.preset_market in market_options else 1, key="preset_market", on_change=extended_save_settings)

push_r_options = ["25.0%", "50.0%", "61.8%"]
st.sidebar.selectbox("押し目プリセット", options=push_r_options, index=push_r_options.index(st.session_state.preset_push_r) if st.session_state.preset_push_r in push_r_options else 1, key="preset_push_r", on_change=apply_presets)

tactics_options = ["⚖️ バランス (掟達成率 ＞ 到達度)", "🎯 狙撃優先 (到達度 ＞ 掟達成率)"]
st.sidebar.selectbox("戦術アルゴリズム", options=tactics_options, index=tactics_options.index(st.session_state.sidebar_tactics) if st.session_state.sidebar_tactics in tactics_options else 0, key="sidebar_tactics", on_change=extended_save_settings)

st.sidebar.divider()

# ==========================================
# 🔍 3. ピックアップルール（原本 100% 維持）
# ==========================================
st.sidebar.header("🔍 ピックアップルール")
c1, c2 = st.sidebar.columns(2)
with c1:
    st.number_input("価格下限(円)", value=int(st.session_state.f1_min), step=100, key="f1_min", on_change=extended_save_settings)
with c2:
    st.number_input("価格上限(円)", value=int(st.session_state.f1_max), step=100, key="f1_max", on_change=extended_save_settings)

st.sidebar.number_input("1ヶ月暴騰上限(倍)", value=float(st.session_state.f2_m30), step=0.1, key="f2_m30", on_change=extended_save_settings)
st.sidebar.number_input("1年最高値からの下落除外(%)", value=float(st.session_state.f3_drop), step=5.0, max_value=0.0, key="f3_drop", on_change=extended_save_settings)

c3, c4 = st.sidebar.columns(2)
with c3:
    st.number_input("波高下限(倍)", value=float(st.session_state.f9_min14), step=0.1, key="f9_min14", on_change=extended_save_settings)
with c4:
    st.number_input("波高上限(倍)", value=float(st.session_state.f9_max14), step=0.1, key="f9_max14", on_change=extended_save_settings)

st.sidebar.checkbox("🚀 IPO除外(上場1年未満)", value=bool(st.session_state.f5_ipo), key="f5_ipo", on_change=extended_save_settings)
st.sidebar.checkbox("疑義注記・信用リスク銘柄除外", value=bool(st.session_state.f6_risk), key="f6_risk", on_change=extended_save_settings)
st.sidebar.checkbox("上昇第3波終了銘柄を除外", value=bool(st.session_state.f11_ex_wave3), key="f11_ex_wave3", on_change=extended_save_settings)
st.sidebar.checkbox("非常に割高・赤字銘柄を除外", value=bool(st.session_state.f12_ex_overvalued), key="f12_ex_overvalued", on_change=extended_save_settings)

st.sidebar.divider()

# ==========================================
# 🎯 4. 買い/売りルール（原本 100% 維持）
# ==========================================
st.sidebar.header("🎯 買いルール")
st.sidebar.number_input("購入ロット(株)", value=int(st.session_state.bt_lot), step=100, key="bt_lot", on_change=extended_save_settings)
st.sidebar.number_input("猶予期限(日)", value=int(st.session_state.limit_d), step=1, key="limit_d", on_change=extended_save_settings)

st.sidebar.header("💰 売りルール")
st.sidebar.number_input("利確目標(%)", value=int(st.session_state.bt_tp), step=1, key="bt_tp", on_change=extended_save_settings)

c_sl1, c_sl2 = st.sidebar.columns(2)
with c_sl1:
    st.number_input("初期損切(%)", value=int(st.session_state.bt_sl_i), step=1, key="bt_sl_i", on_change=extended_save_settings)
with c_sl2:
    st.number_input("現在損切(%)", value=int(st.session_state.bt_sl_c), step=1, key="bt_sl_c", on_change=extended_save_settings)

st.sidebar.number_input("最大保持期間(日)", value=int(st.session_state.bt_sell_d), step=1, key="bt_sell_d", on_change=extended_save_settings)

st.sidebar.divider()

# ==========================================
# 🚫 5. 特殊除外フィルター（原本 100% 維持）
# ==========================================
st.sidebar.header("🚫 特殊除外フィルター")
st.sidebar.checkbox("ETF・REIT等を除外", value=bool(st.session_state.f7_ex_etf), key="f7_ex_etf", on_change=extended_save_settings)
st.sidebar.checkbox("医薬品(バイオ)を除外", value=bool(st.session_state.f8_ex_bio), key="f8_ex_bio", on_change=extended_save_settings)
st.sidebar.checkbox("落ちるナイフ除外(暴落直後)", value=bool(st.session_state.f10_ex_knife), key="f10_ex_knife", on_change=extended_save_settings)

st.sidebar.text_area(
    "除外銘柄コード", 
    value=str(st.session_state.gigi_input), 
    key="gigi_input", 
    on_change=extended_save_settings
)

st.sidebar.divider()

# --- システムボタン ---
if st.sidebar.button("🔴 キャッシュ強制パージ", use_container_width=True):
    save_exclude_codes_to_file()
    st.cache_data.clear()
    st.session_state.tab1_scan_results = None
    st.session_state.tab2_scan_results = None
    st.rerun()

if st.sidebar.button("💾 設定を保存", use_container_width=True):
    extended_save_settings()
    st.toast("全設定および除外コードを永久保存した。")

st.sidebar.caption(f"KEY: {cache_key}")

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
tab1, tab2, tab3, tab4, tab5, tab6, tab7 = st.tabs([
    "🌐 【待伏】広域レーダー", 
    "⚡ 【強襲】広域レーダー", 
    "💎 【潜伏】広域レーダー", 
    "🎯 【照準】精密スコープ", 
    "⚙️ 【演習】戦術シミュレータ", 
    "⛺ 【戦線】交戦モニター", 
    "📁 【戦歴】交戦データベース"
])

# --- 6. タブコンテンツ (TAB1: 待伏レーダー) ---
with tab1:
    st.markdown(f'<h3 style="font-size: 24px;">🎯 【待伏】2026式・マクロ連動スキャン</h3>', unsafe_allow_html=True)
    st.info(f"現在の地合い連動：{st.session_state.get('macro_alert', '未設定')}")
    
    if 'tab1_scan_results' not in st.session_state: st.session_state.tab1_scan_results = None
    
    run_scan_t1 = st.button("🚀 索敵開始", key="btn_scan_t1_macro")

    if run_scan_t1:
        st.session_state.tab1_scan_results = None
        # 🚨 物理初期化
        st.session_state.tab1_time_log = []
        gc.collect() 
        t_global_start = time.time()
        
        with st.status("🚀 索敵スキャンを実行中...", expanded=True) as status:
            st.write("📡 第1段階：280日分のデータを取得・解析中...")
            full_df = get_hist_data_cached(cache_key)

            if full_df is not None and not full_df.empty:
                t_fetch = time.time()
                msg1 = f"✔️ 第1段階完了：兵站確保 [{t_fetch - t_global_start:.2f}秒]"
                st.write(msg1)
                st.session_state.tab1_time_log.append(msg1)

                # コードの形式を統一
                full_df['Code'] = full_df['Code'].astype(str).apply(lambda x: x if len(x) >= 5 else x + "0")
                
                # ==========================================
                # 🎯 開発参謀パッチ：潜伏モード時の波高自動ハッキング
                # ==========================================
                # 現在のタブ（モード）が「潜伏」かどうかを判定（変数名は環境に合わせてください）
                # ※もしタブの判定がis_stealth等で定義されている場合は、そちらを使用してください
                is_stealth_mode = st.session_state.get("t3_scope_mode", "") == "💎 【潜伏】 大爆発前夜ハント"  # ←ここをご自身のUI文言に合わせて調整

                # 潜伏の時は下限を0.0に強制オーバーライド。それ以外はサイドバーの設定値を採用。
                effective_min14 = 0.0 if is_stealth_mode else float(st.session_state.f9_min14)
                
                # 上限は「サイドバーの値」か「潜伏専用の最低限（1.3等）」の緩い方を採用
                effective_max14 = max(float(st.session_state.f9_max14), 1.3) if is_stealth_mode else float(st.session_state.f9_max14)
                # ==========================================

                config_t1 = {
                    "f1_min": float(st.session_state.f1_min), "f1_max": float(st.session_state.f1_max),
                    "f2_m30": float(st.session_state.f2_m30), "f3_drop": float(st.session_state.f3_drop),
                    "push_r": float(st.session_state.push_r), "push_penalty": st.session_state.get('push_penalty', 0.0),
                    
                    # 🚨 修正：直接st.session_stateからではなく、ハッキング済みの変数を渡す
                    "f9_min14": effective_min14, 
                    "f9_max14": effective_max14, 
                    
                    "limit_d": int(st.session_state.limit_d), "f12_ex_overvalued": st.session_state.f12_ex_overvalued,
                    "f5_ipo": st.session_state.f5_ipo, "f11_ex_wave3": st.session_state.f11_ex_wave3,
                    "f6_risk": st.session_state.f6_risk,
                    "gigi_codes": [c.strip() for c in str(st.session_state.gigi_input).split(",") if c.strip()],
                    "sl_c": float(st.session_state.get("bt_sl_c", 8.0)),
                    "f_vol_min": float(st.session_state.get('f_vol_min', 0.5))
                }

                # 🚨 防弾パッチ：日付型の統一と必須カラムチェック
                full_df['Date'] = pd.to_datetime(full_df['Date'], errors='coerce')
                
                # 必須カラムの生存確認
                if not all(col in full_df.columns for col in ['Date', 'AdjC', 'Code']):
                    debug_logs.append("⚠️ フィルター実行失敗：必須株価データ(Date, AdjC, Code)が欠損しています")
                    valid_codes = set()
                elif full_df.empty:
                    valid_codes = set()
                else:
                    # 🚨 最終防壁：AdjCを数値型に強制変換（文字列混入対策）
                    full_df['AdjC'] = pd.to_numeric(full_df['AdjC'], errors='coerce')
                    
                    latest_date = full_df['Date'].max()
                    m_mode = "大型" if "大型株" in st.session_state.preset_market else "中小型"
                    target_keywords = ['プライム','一部'] if m_mode=="大型" else ['スタンダード','グロース','新興','JASDAQ']
                    m_targets = [c for c, m in master_map_t1.items() if any(k in str(m['Market']) for k in target_keywords)]
                    
                    # マスク処理（安全な型比較）
                    mask = (full_df['Date'] == latest_date) & \
                           (full_df['AdjC'] >= config_t1["f1_min"]) & \
                           (full_df['AdjC'] <= config_t1["f1_max"])
                    
                    valid_codes = set(full_df[mask]['Code']).intersection(set(m_targets))
                
                if not valid_codes:
                    st.error("⚠️ 市場フィルター・価格帯フィルターを通過した銘柄が0件です。")
                    st.stop()

                v_candidates = [c for c in full_df.columns if 'Volume' in c or 'Vo' in c]
                v_col = v_candidates[0] if v_candidates else full_df.columns[-1]
                avg_vols = full_df.groupby('Code').tail(5).groupby('Code')[v_col].mean()
                
                df = full_df[full_df['Code'].isin(valid_codes)]
                t_clean = time.time()
                msg2 = f"✔️ 第2段階完了：ターゲット抽出 [{t_clean - t_fetch:.2f}秒]"
                st.write(msg2)
                st.session_state.tab1_time_log.append(msg2)
                st.write("⚙️ 第3段階：並列演算・物理抽出エンジン稼働中...")

                def scan_unit_t1_parallel(code, group, cfg, v_avg, l_date):
                    # 🚨 OOM対策パッチ：計算に必要な直近30日分のみに絞り込み、メモリ爆発を完全に阻止
                    group_df = group.tail(30)
                    if group_df.empty: return None

                    # 絞り込んだデータから値を抽出
                    c_vals = group_df['AdjC'].values
                    h_vals = group_df['AdjH'].values
                    l_vals = group_df['AdjL'].values
                    lc = float(c_vals[-1])

                    # 🚨 以降、以前のロジックを1文字も変えずに実行
                    if cfg["f6_risk"] and (str(code)[:4] in cfg["gigi_codes"]): return None
                    
                    # 安全な指標計算
                    rsi, atr_v, _, _ = get_fast_indicators(c_vals)
                    vol_pct = (atr_v / lc * 100) if lc > 0 else 0
                    if vol_pct < cfg["f_vol_min"]: return None
                    
                    h14 = float(h_vals[-14:].max()) if len(h_vals) >= 14 else float(h_vals.max())
                    l14 = float(l_vals[-14:].min()) if len(l_vals) >= 14 else float(l_vals.min())
                    if l14 <= 0 or h14 <= l14: return None
                    
                    wh = h14 / l14
                    if not (cfg["f9_min14"] <= wh <= cfg["f9_max14"]): return None
                    
                    base_push = (h14 - l14) * (cfg["push_r"] / 100.0)
                    target_buy = h14 - base_push
                    target_buy = target_buy * (1.0 - cfg["push_penalty"]) 
                    
                    dist_pct = ((lc / target_buy) - 1) * 100 if target_buy > 0 else 0
                    if dist_pct < -cfg["sl_c"]: return None

                    rank, bg, t_score = ("S🔥", "#26a69a", 5.5) if dist_pct <= 2.0 else ("A⚡", "#ed6c02", 4.5)
                    
                    return {
                        'Code': code, 'lc': lc, 'RSI': float(rsi), 
                        'target_buy': float(target_buy),
                        'reach_rate': float((target_buy / lc) * 100) if lc > 0 else 0,
                        'triage_rank': rank, 'triage_bg': bg, 't_score': t_score, 
                        'score': 4, 'high_4d': float(h14), 'low_14d': float(l14), 
                        'avg_vol': int(v_avg), 'vol_pct': float(vol_pct)
                    }

                results = []
                with concurrent.futures.ThreadPoolExecutor(max_workers=3) as exe:
                    futures = {exe.submit(scan_unit_t1_parallel, c, g, config_t1, avg_vols.get(c, 0), latest_date): c for c, g in df.groupby('Code')}
                    for f in concurrent.futures.as_completed(futures):
                        try:
                            res = f.result()
                            if res: results.append(res)
                        except: pass

                # 🚨 【作戦1：診断コード】演算直後の生データを確認する
                st.write(f"🔍 診断確認: エンジン出力件数 = {len(results)}")
                if results:
                    st.write("🔍 診断確認: 最初の3件のデータ構造:")
                    st.json(results[:3])
                else:
                    st.error("🔍 診断確認: スキャン結果が空です。scan_unit_t1_parallel のフィルターが厳しすぎます。")
                # --------------------------------------------------------
        
                sorted_raw = sorted(results, key=lambda x: (x['t_score'], x['score']), reverse=True)
                
                max_per_sector = st.session_state.get("f_max_stocks_per_sector", 3)
                selected_sectors = st.session_state.get("f_selected_sectors", [])
                
                filtered_results = []
                sector_counts = {}
                for r in sorted_raw:
                    sector = master_map_t1.get(str(r['Code']), {}).get('Sector', '不明')
                    if sector not in selected_sectors: continue
                    if sector_counts.get(sector, 0) < max_per_sector:
                        filtered_results.append(r)
                        sector_counts[sector] = sector_counts.get(sector, 0) + 1
                    if len(filtered_results) >= 30: break

                st.session_state.tab1_scan_results = filtered_results
                
                t_calc = time.time()
                msg3 = f"✔️ 第3段階完了：並列演算・抽出完了 [{t_calc - t_clean:.2f}秒]"
                st.session_state.tab1_time_log.append(msg3)
                msg4 = f"⏱️ 物理総計索敵時間: {t_calc - t_global_start:.2f}秒"
                st.session_state.tab1_time_log.append(msg4)
                
                status.update(label=f"🎯 スキャン完了！ {len(filtered_results)}銘柄着弾", state="complete", expanded=False)
                st.rerun()

            else:
                st.error("🚨 エラー：ヒストリカルデータが取得できませんでした。")

    if st.session_state.tab1_scan_results is not None:
        if "tab1_time_log" in st.session_state and st.session_state.tab1_time_log:
            with st.expander(f"🎯 索敵完了！（候補 {len(st.session_state.tab1_scan_results)} 銘柄確保）", expanded=False):
                for log in st.session_state.tab1_time_log:
                    st.write(log)

        light_results = st.session_state.tab1_scan_results
        
        if not light_results:
            st.warning("⚠️ **本日の掟に合致する銘柄は、現在のフィルター条件では 0 件です。**")
            with st.expander("🔍 索敵報告（なぜ表示されないのか？）"):
                st.write("※上の「🔍 診断確認」ログで、計算エンジンから何件出力されたかを確認してください。")
        else:
            st.success(f"🎯 **待伏ロックオン: {len(light_results)} 銘柄**")

            sab_codes = " ".join([str(r.get('Code', ''))[:4] for r in light_results if str(r.get('triage_rank', '')).startswith(('S', 'A', 'B'))])
            if sab_codes:
                st.info("📋 以下のコードをコピーして、照準（TAB3）にペースト可能だ。")
                st.code(sab_codes, language="text")
        
            # 描画ループ：すべての辞書アクセスを安全化
            for r in light_results:
                st.divider()
                
                def safe_int(x):
                    try: return int(float(x)) if not pd.isna(x) else 0
                    except: return 0
                
                c_code = str(r.get('Code', '不明'))
                m_info = master_map_t1.get(c_code, {})
                m_lower = str(m_info.get('Market', '')).lower()
                
                if 'プライム' in m_lower or '一部' in m_lower: badge_html = '<span style="background-color: #1a237e; color: #ffffff; padding: 0.2rem 0.6rem; border-radius: 4px; font-size: 11px; font-weight: bold;">🏢 プライム/大型</span>'
                elif 'グロース' in m_lower or 'マザーズ' in m_lower: badge_html = '<span style="background-color: #1b5e20; color: #ffffff; padding: 0.2rem 0.6rem; border-radius: 4px; font-size: 11px; font-weight: bold;">🚀 グロース/新興</span>'
                else: badge_html = f'<span style="background-color: #455a64; color: #ffffff; padding: 0.2rem 0.6rem; border-radius: 4px; font-size: 11px; font-weight: bold;">{m_info.get("Market","不明")}</span>'
                
                u_badge = '<span style="background-color: #26a69a; color: #ffffff; padding: 0.2rem 0.6rem; border-radius: 4px; font-size: 13px; font-weight: bold; margin-left: 0.5rem; box-shadow: 0 0 10px rgba(38,166,154,0.5);">💎 陰の極み</span>' if r.get('ultimate') else ""
                t_badge = f'<span style="background-color: {r.get("triage_bg", "#666")}; color: #ffffff; padding: 0.2rem 0.6rem; border-radius: 4px; font-size: 13px; font-weight: bold; margin-left: 0.5rem;">🎯 優先度: {r.get("triage_rank", "不明")}</span>'
                
                score_val = safe_int(r.get("score", 0))
                score_color = "#26a69a" if score_val >= 8 else "#ff5722"
                score_bg = "rgba(38, 166, 154, 0.15)" if score_val >= 8 else "rgba(255, 87, 34, 0.15)"
                score_badge = f'<span style="background-color: {score_bg}; border: 1px solid {score_color}; color: {score_color}; padding: 0.2rem 0.6rem; border-radius: 4px; font-size: 12px; font-weight: bold; margin-left: 0.5rem;">🎖️ 掟スコア: {score_val}/9</span>'
                sector_badge = f'<span style="background-color: #607d8b; color: #ffffff; padding: 0.1rem 0.5rem; border-radius: 4px; font-size: 12px; margin-left: 0.5rem;">🏭 {m_info.get("Sector", "不明")}</span>'
                vol_badge = f'<span style="background-color: rgba(38, 166, 154, 0.1); border: 1px solid #26a69a; color: #26a69a; padding: 0.1rem 0.5rem; border-radius: 4px; font-size: 12px; margin-left: 0.5rem;">🌪️ ボラ: {r.get("vol_pct", 0.0):.2f}%</span>'
                
                st.markdown(f"""
                    <div style="margin-bottom: 0.8rem;">
                        <h3 style="font-size: clamp(18px, 5vw, 28px); font-weight: bold; margin: 0 0 0.3rem 0;">({c_code[:4]}) {m_info.get('CompanyName', '不明')}</h3>
                        <div style="display: flex; flex-wrap: wrap; gap: 6px; align-items: center;">
                            {badge_html}{u_badge}{t_badge}{score_badge}{sector_badge}{vol_badge}
                            <span style="background-color: rgba(38, 166, 154, 0.15); border: 1px solid #26a69a; color: #26a69a; padding: 0.1rem 0.5rem; border-radius: 4px; font-size: 12px;">RSI: {r.get("RSI", 0.0):.1f}%</span>
                            <span style="background-color: rgba(255, 215, 0, 0.1); border: 1px solid #FFD700; color: #FFD700; padding: 0.1rem 0.5rem; border-radius: 4px; font-size: 12px;">到達度: {r.get('reach_rate', 0.0):.1f}%</span>
                        </div>
                    </div>
                """, unsafe_allow_html=True)
                
                m_cols = st.columns([1, 1, 1, 1.2, 1.5])
                m_cols[0].metric("直近高値", f"{safe_int(r.get('high_4d', 0)):,}円")
                m_cols[1].metric("起点安値", f"{safe_int(r.get('low_14d', 0)):,}円")
                m_cols[2].metric("最新終値", f"{safe_int(r.get('lc', 0)):,}円")
                m_cols[3].metric("平均出来高", f"{safe_int(r.get('avg_vol', 0)):,}株")
                m_cols[4].markdown(f"""<div style="background: rgba(255, 215, 0, 0.05); padding: 0.5rem; border-radius: 8px; border: 1px solid rgba(255, 215, 0, 0.2); text-align: center;"><div style="font-size: 13px; color: rgba(250, 250, 250, 0.6); margin-bottom: 2px;">🎯 買値目標(連動済)</div><div style="font-size: 1.8rem; font-weight: bold; color: #FFD700;">{safe_int(r.get('target_buy', 0)):,}<span style="font-size: 14px; margin-left:2px;">円</span></div></div>""", unsafe_allow_html=True)

# --- 7. タブコンテンツ (TAB2: 強襲レーダー) ---
with tab2:
    st.markdown('<h3 style="font-size: 24px;">⚡ 【強襲】2026式・マクロ連動スキャン</h3>', unsafe_allow_html=True)
    st.info(f"現在の地合い連動：{st.session_state.get('macro_alert', '未設定')}")

    st.markdown("#### ⚙️ 強襲パラメータ設定（5連装フィルター連動）")

    col_t2_1, col_t2_2, col_t2_3 = st.columns(3)
    rsi_lim = col_t2_1.number_input("RSI上限（足切り）", value=int(st.session_state.get('tab2_rsi_limit', 70)), step=5, key="tab2_rsi_limit")
    vol_lim = col_t2_2.number_input("最低出来高（5日平均）", value=int(st.session_state.get('tab2_vol_limit', 50000)), step=5000, key="tab2_vol_limit")
    trading_val_min = col_t2_3.number_input("大口流動性バリア（億円）", value=float(st.session_state.get('f_trading_val_min', 3.0)), step=0.5, format="%.1f", key="f_trading_val_min")

    col_t2_4, col_t2_5, col_t2_6 = st.columns(3)
    p_high_prox = col_t2_4.number_input("直近高値への肉薄幅 (%)", value=float(st.session_state.get('tab2_high_prox', 3.0)), step=0.5, format="%.1f", key="tab2_high_prox")
    p_vol_spike = col_t2_5.number_input("出来高急増スパイク (倍)", value=float(st.session_state.get('tab2_vol_spike', 1.5)), step=0.1, format="%.1f", key="tab2_vol_spike")
    p_body_ratio = col_t2_6.number_input("ローソク足実体比率 (%)", value=float(st.session_state.get('tab2_body_ratio', 70.0)), step=5.0, format="%.1f", key="tab2_body_ratio")

    if st.button("🚀 強襲開始", key="btn_scan_t2_macro_physical_lock", type="primary"):
        try: save_settings() 
        except NameError: pass

        st.session_state.tab2_scan_results_raw = None
        st.session_state.tab2_time_log = [] # 🚨 進捗ログ保存配列を初期化
        gc.collect()
        t_global_start = time.time()

        with st.status("🚀 索敵スキャンを実行中... 強襲ルートを計算しています", expanded=True) as status:
            try:
                raw = get_hist_data_cached(cache_key) if 'cache_key' in locals() or 'cache_key' in globals() else []
                t_fetch = time.time()
                msg1 = f"✔️ 第1段階完了：兵站確保 [{t_fetch - t_global_start:.2f}秒]"
                st.write(msg1)
                st.session_state.tab2_time_log.append(msg1)

                if raw is None or len(raw) == 0:
                    st.error("J-Quants APIからの応答が途絶。")
                else:
                    full_df = clean_df(pd.DataFrame(raw))
                    full_df['Code'] = full_df['Code'].astype(str).apply(lambda x: x if len(x) >= 5 else x + "0")
                    for col in ['AdjC', 'AdjH', 'AdjL']:
                        if col in full_df.columns: full_df[col] = full_df[col].astype('float32')

                    rsi_penalty = st.session_state.get('rsi_penalty', 0)
                    effective_rsi_limit = float(rsi_lim) - rsi_penalty

                    config_t2 = {
                        "f1_min": float(st.session_state.get("f1_min", 0)), "f1_max": float(st.session_state.get("f1_max", 99999)),
                        "f2_m30": 999.0, "f3_drop": -999.0,        
                        "rsi_lim": effective_rsi_limit, "vol_lim": float(vol_lim),
                        "f5_ipo": st.session_state.get("f5_ipo", False), "f11_ex_wave3": st.session_state.get("f11_ex_wave3", False),
                        "f6_risk": st.session_state.get("f6_risk", False),
                        "gigi_codes": [c.strip() for c in str(st.session_state.get("gigi_input", "")).split(",") if c.strip()],
                        "f12_ex_overvalued": st.session_state.get("f12_ex_overvalued", False),
                        "tactics": st.session_state.get("sidebar_tactics", "⚖️ バランス (掟達成率 ＞ 到達度)"),
                        "f_vol_min": -1.0, "sl_c": float(st.session_state.get("bt_sl_c", 8.0)),
                        "val_min_raw": float(trading_val_min) * 100_000_000,            
                        "high_prox_ratio": 1.0 - (float(p_high_prox) / 100.0),          
                        "vol_spike": float(p_vol_spike),                                
                        "body_ratio": float(p_body_ratio) / 100.0                       
                    }

                    m_mode = "大型" if "大型株" in st.session_state.get("preset_market", "") else "中小型"
                    target_keywords = ['プライム','一部'] if m_mode=="大型" else ['スタンダード','グロース','新興','JASDAQ']

                    m_map = globals().get('master_map_t2', globals().get('master_map', {}))
                    m_targets = [c for c, m in m_map.items() if any(k in str(m.get('Market', '')) for k in target_keywords)] if m_map else full_df['Code'].unique()

                    # 🚨 防弾パッチ：日付型の統一、必須カラム確認、設定値の不整合修正
                full_df['Date'] = pd.to_datetime(full_df['Date'], errors='coerce')
                
                # 必須カラムチェック（これが欠けている場合は即時終了）
                if not all(col in full_df.columns for col in ['Date', 'AdjC', 'Code']):
                    debug_logs.append("⚠️ TAB2フィルターエラー：必須株価データ(Date, AdjC, Code)が欠損")
                    valid_codes = set()
                else:
                    latest_date = full_df['Date'].max()
                    m_mode = "大型" if "大型株" in st.session_state.preset_market else "中小型"
                    target_keywords = ['プライム','一部'] if m_mode=="大型" else ['スタンダード','グロース','新興','JASDAQ']
                    m_targets = [c for c, m in master_map_t1.items() if any(k in str(m['Market']) for k in target_keywords)]
                    
                    # 🚨 修正：config_t2で統一
                    mask = (full_df['Date'] == latest_date) & \
                           (full_df['AdjC'] >= config_t2["f1_min"]) & \
                           (full_df['AdjC'] <= config_t2["f1_max"])
                    
                    valid_codes = set(full_df[mask]['Code']).intersection(set(m_targets))

                    v_candidates = [c for c in full_df.columns if 'Volume' in c or 'Vo' in c]
                    v_col = v_candidates[0] if v_candidates else full_df.columns[-1]

                    full_df[v_col] = pd.to_numeric(full_df[v_col], errors='coerce').fillna(0).astype('float32')
                    avg_vols_series = full_df.groupby('Code').tail(5).groupby('Code')[v_col].mean()

                    df = full_df[full_df['Code'].isin(valid_codes)]
                    t_clean = time.time()
                    msg2 = f"✔️ 第2段階完了：ターゲット抽出 [{t_clean - t_fetch:.2f}秒]"
                    st.write(msg2)
                    st.session_state.tab2_time_log.append(msg2)

                    def scan_unit_t2_parallel(code, group, cfg, v_avg, l_date):
                        import pandas as pd
                        c_str = str(code)[:4]
                        c_vals = group['AdjC'].values
                        lc = float(c_vals[-1])

                        if cfg.get("f6_risk") and (c_str in cfg.get("gigi_codes", [])): return None
                        if cfg.get("f5_ipo"):
                            first_date = group['Date'].min()
                            if (l_date - first_date).days < 350: return None
                        if cfg.get("f11_ex_wave3"):
                            if lc > (float(c_vals.min()) * 3.0): return None

                        # 🚨 エンジン強制起動！（実数ATRの生成）
                        group_df = group.tail(30).copy().ffill().bfill()
                        group_df = calc_vector_indicators(group_df)
                        
                        # 🚨 浄化された実数ATRの取得
                        if 'ATR_Standard' in group_df.columns and pd.notna(group_df['ATR_Standard'].iloc[-1]):
                            real_atr = float(group_df['ATR_Standard'].iloc[-1])
                        else:
                            real_atr = float(lc * 0.05)

                        rsi, _dummy_atr, _, hist = get_fast_indicators(c_vals)
                        
                        # 🚨 実数ATRを用いた正確なボラティリティ計算
                        vol_pct = (real_atr / lc * 100) if lc > 0 else 0
                        
                        if vol_pct < cfg.get("f_vol_min", -1.0): return None
                        if rsi > cfg.get("rsi_lim", 70): return None

                        if len(group) < 25: return None

                        if cfg.get("f12_ex_overvalued"):
                            f_data = get_fundamentals(c_str)
                            if f_data and (f_data.get("op", 0) or 0) < 0: return None

                        v_col_name = next((c for c in ['AdjustmentVolume', 'Volume', 'volume', 'Vol', 'Vo'] if c in group_df.columns), 'Volume')
                        if v_col_name not in group_df.columns: return None
                        
                        group_df['daily_value'] = group_df[v_col_name] * group_df['AdjC']
                        group_df['avg_value_5'] = group_df['daily_value'].rolling(window=5, min_periods=1).mean()
                        if group_df['avg_value_5'].iloc[-1] < cfg.get("val_min_raw", 0): return None

                        group_df['recent_high'] = group_df['AdjH'].shift(1).rolling(window=20, min_periods=1).max()
                        rec_high = group_df['recent_high'].iloc[-1]
                        if pd.isna(rec_high) or lc < (rec_high * cfg.get("high_prox_ratio", 1.0)): return None

                        group_df['avg_volume_5'] = group_df[v_col_name].shift(1).rolling(window=5, min_periods=1).mean()
                        avg_vol_5 = group_df['avg_volume_5'].iloc[-1]
                        curr_vol = group_df[v_col_name].iloc[-1]
                        if pd.isna(avg_vol_5) or avg_vol_5 <= 0 or curr_vol <= (avg_vol_5 * cfg.get("vol_spike", 1.0)): return None

                        group_df['candle_range'] = group_df['AdjH'] - group_df['AdjL']
                        group_df['body_range'] = group_df['AdjC'] - group_df['AdjL']
                        c_range = group_df['candle_range'].iloc[-1]
                        b_range = group_df['body_range'].iloc[-1]

                        if c_range > 0:
                            if (b_range / c_range) < cfg.get("body_ratio", 0): return None
                        elif c_range < 0:
                            return None

                        t_rank, t_color, t_score, t_desc = "S+🎯", "#ff5252", 100, "鉄壁5連装条件クリア"
                        gc_days = 0 
                        h_vals = group_df['AdjH'].values if 'AdjH' in group_df.columns else c_vals
                        h14 = float(h_vals[-14:].max())

                        return {
                            'Code': code, 'lc': float(lc), 'RSI': float(rsi), 
                            'T_Rank': t_rank, 'T_Color': t_color, 'T_Score': t_score, 
                            'GC_Days': gc_days, 'h14': h14, 
                            'ATR_Standard': real_atr,  # 🚨 TAB4マトリクス用
                            'atr': real_atr,           # 🚨 TAB4マトリクス互換用
                            'avg_vol': int(v_avg), 'vol_pct': float(vol_pct),
                            'T_Desc': t_desc
                        }

                    results = []
                    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
                        futures = [executor.submit(scan_unit_t2_parallel, c, g, config_t2, avg_vols_series.get(c, 0), latest_date) for c, g in df.groupby('Code')]
                        for f in concurrent.futures.as_completed(futures):
                            try:
                                res = f.result()
                                if res: results.append(res)
                            except: pass

                    sorted_raw = sorted(results, key=lambda x: (-x.get('T_Score', 0), x.get('GC_Days', 0)))
                    st.session_state.tab2_scan_results_raw = sorted_raw[:300]

                    t_calc = time.time()
                    msg3 = f"✔️ 第3段階完了：並列演算・抽出完了 [{t_calc - t_clean:.2f}秒]"
                    st.write(msg3)
                    st.session_state.tab2_time_log.append(msg3)

                    msg4 = f"⏱️ 物理総計索敵時間: {t_calc - t_global_start:.2f}秒"
                    st.write(msg4)
                    st.session_state.tab2_time_log.append(msg4)

                    status.update(label=f"🎯 索敵完了！（候補 {len(st.session_state.tab2_scan_results_raw)} 銘柄確保）", state="complete", expanded=False)
                    st.rerun()

            except Exception as e:
                st.error(f"🚨 スキャン中に内部エラーが発生しました。\n詳細: {str(e)}")
                status.update(label="🚨 エラー発生により中断", state="error")

    # --- 🔥 強襲モード 抽出結果描画ブロック ---
    st.divider()
    raw_hits_t2 = st.session_state.get("tab2_scan_results_raw")
    if raw_hits_t2 is not None:
        # 🚨 進捗ログのエキスパンダー表示を完全保護
        if "tab2_time_log" in st.session_state and st.session_state.tab2_time_log:
            with st.expander(f"🎯 索敵完了！（候補 {len(raw_hits_t2)} 銘柄確保）", expanded=False):
                for log in st.session_state.tab2_time_log: 
                    st.write(log)

        max_p_s = st.session_state.get("f_max_stocks_per_sector", 3)
        sel_sects = st.session_state.get("f_selected_sectors", [])
        curr_market = st.session_state.get("preset_market", "")

        try: target_theme_codes_safe = target_theme_codes
        except NameError: target_theme_codes_safe = []

        light_results_t2 = []
        sector_counts_t2 = {}

        m_map = globals().get('master_map_t2', globals().get('master_map', {}))

        for r in raw_hits_t2:
            c_code = str(r.get('Code', ''))
            m_info = m_map.get(c_code, {}) if m_map else {}
            m_actual = str(m_info.get('Market', ''))
            sector = str(m_info.get('Sector', '不明')).strip()

            is_prime = any(k in m_actual for k in ['プライム', '一部', '東証1部', 'Prime'])
            if "大型株" in curr_market and "中小型株" not in curr_market:
                if not is_prime: continue
            if "中小型株" in curr_market and "大型株" not in curr_market:
                if is_prime: continue
            if target_theme_codes_safe and c_code[:4] not in target_theme_codes_safe: continue
            if sel_sects and sector not in sel_sects: continue

            if sector_counts_t2.get(sector, 0) < max_p_s:
                r_display = r.copy()
                r_display['銘柄名'] = m_info.get('CompanyName', '不明')
                r_display['セクター'] = sector
                light_results_t2.append(r_display)
                sector_counts_t2[sector] = sector_counts_t2.get(sector, 0) + 1

            if len(light_results_t2) >= 30: break

        if not light_results_t2:
            st.warning("⚠️ **強襲条件およびセクター/テーマ制約に合致する銘柄は 0 件です。**")
        else:
            st.success(f"🎯 **強襲ロックオン: {len(light_results_t2)} 銘柄捕捉** (上位30件表示)")

            # 📋 コピペ用コード一覧（A判定以上等）の完全保護
            a_rank_codes = [str(r.get('Code', ''))[:4] for r in light_results_t2 if r.get('T_Score', 0) >= 60 or "S" in r.get('T_Rank', '') or "A" in r.get('T_Rank', '')]
            if not a_rank_codes: 
                a_rank_codes = [str(r.get('Code', ''))[:4] for r in light_results_t2]

            # 🎯 物理結線：右上に全コピボタンが出る黒枠ボックス
            st.markdown("#### 📋 抽出銘柄 一括コピー（A判定以上等）")
            st.code(",".join(a_rank_codes), language="text")

            for r in light_results_t2:
                st.divider()
                c_code = str(r.get('Code', '不明'))
                m_info = m_map.get(c_code, {})
                m_lower = str(m_info.get('Market', '')).lower()

                if 'プライム' in m_lower or '一部' in m_lower: badge_html = '<span style="background-color: #1a237e; color: #ffffff; padding: 0.2rem 0.6rem; border-radius: 4px; font-size: 11px; font-weight: bold;">🏢 プライム/大型</span>'
                elif 'グロース' in m_lower or 'マザーズ' in m_lower: badge_html = '<span style="background-color: #1b5e20; color: #ffffff; padding: 0.2rem 0.6rem; border-radius: 4px; font-size: 11px; font-weight: bold;">🚀 グロース/新興</span>'
                else: badge_html = f'<span style="background-color: #455a64; color: #ffffff; padding: 0.2rem 0.6rem; border-radius: 4px; font-size: 11px; font-weight: bold;">{m_info.get("Market","不明")}</span>'

                t_badge = f'<span style="background-color: {r.get("T_Color", "#666")}; color: #ffffff; padding: 0.2rem 0.6rem; border-radius: 4px; font-size: 13px; font-weight: bold; margin-left: 0.5rem;">🎯 優先度: {r.get("T_Rank", "不明")}</span>'
                sector_badge = f'<span style="background-color: #607d8b; color: #ffffff; padding: 0.1rem 0.5rem; border-radius: 4px; font-size: 12px; margin-left: 0.5rem;">🏭 {m_info.get("Sector", "不明")}</span>'
                vol_badge = f'<span style="background-color: rgba(38, 166, 154, 0.1); border: 1px solid #26a69a; color: #26a69a; padding: 0.1rem 0.5rem; border-radius: 4px; font-size: 12px; margin-left: 0.5rem;">🌪️ ボラ: {r.get("vol_pct", 0.0):.2f}%</span>'

                gc_days = r.get('GC_Days', 0)
                if gc_days <= 0: status_badge_html = f'<span style="background-color: rgba(239, 83, 80, 0.15); border: 1px solid #ef5350; color: #ef5350; padding: 0.1rem 0.5rem; border-radius: 4px; font-size: 12px;">{r.get("T_Desc", "明日GC見込(激熱)")}</span>'
                else: status_badge_html = f'<span style="background-color: rgba(237, 108, 2, 0.15); border: 1px solid #ed6c02; color: #ed6c02; padding: 0.1rem 0.5rem; border-radius: 4px; font-size: 12px;">GC発動 {gc_days}日目</span>'

                rsi_val = r.get('RSI', 0.0)

                st.markdown(f"""
                    <div style="margin-bottom: 0.8rem;">
                        <h3 style="font-size: 24px; font-weight: bold; margin: 0 0 0.3rem 0;">({c_code[:4]}) {m_info.get('CompanyName', '不明')}</h3>
                        <div style="display: flex; flex-wrap: wrap; gap: 6px; align-items: center;">
                            {badge_html}{t_badge}{sector_badge}{vol_badge}{status_badge_html}
                            <span style="background-color: rgba(38, 166, 154, 0.15); border: 1px solid #26a69a; color: #26a69a; padding: 0.1rem 0.5rem; border-radius: 4px; font-size: 12px;">RSI: {rsi_val:.1f}%</span>
                        </div>
                    </div>
                """, unsafe_allow_html=True)

                def safe_int_local(val):
                    try: return int(float(val))
                    except (ValueError, TypeError): return 0

                lc_v, h14_v, atr_v = safe_int_local(r.get('lc', 0)), safe_int_local(r.get('h14', 0)), safe_int_local(r.get('atr', 0))
                t_price = max(h14_v, lc_v + int(atr_v * 0.5)); d_price = t_price - atr_v

                m_cols = st.columns([1, 1, 1, 1.2, 1.5])
                m_cols[0].metric("最新終値", f"{lc_v:,}円")
                m_cols[1].metric("RSI", f"{rsi_val:.1f}%")
                m_cols[2].metric("ボラ(推定)", f"{atr_v:,}円")
                m_cols[3].markdown(f'<div style="background: rgba(239, 83, 80, 0.05); padding: 0.5rem; border-radius: 8px; border: 1px solid rgba(239, 83, 80, 0.3); text-align: center;"><div style="font-size: 13px; color: rgba(250, 250, 250, 0.6); margin-bottom: 2px;">🛡️ 防衛線</div><div style="font-size: 1.6rem; font-weight: bold; color: #ef5350;">{d_price:,}円</div></div>', unsafe_allow_html=True)
                m_cols[4].markdown(f'<div style="background: rgba(255, 215, 0, 0.05); padding: 0.5rem; border-radius: 8px; border: 1px solid rgba(255, 215, 0, 0.2); text-align: center;"><div style="font-size: 13px; color: rgba(250, 250, 250, 0.6); margin-bottom: 2px;">🎯 トリガー</div><div style="font-size: 1.6rem; font-weight: bold; color: #FFD700;">{t_price:,}円</div></div>', unsafe_allow_html=True)

# ==============================================================================
    # モードB：💎 潜伏（Stealth）モード
    # ==============================================================================


# --- 7.5. タブコンテンツ (TAB3: 潜伏) ---
with tab3:
    st.markdown('<h3 style="font-size: 24px;">💎 【潜伏】2026式・マクロ連動スキャン</h3>', unsafe_allow_html=True)
    st.info(f"現在の地合い連動：{st.session_state.get('macro_alert', '未設定')}")

    st.markdown("#### 💎 潜伏（Stealth）パラメータ設定")

    col_s1, col_s2 = st.columns(2)
    st_val_min = col_s1.number_input("最低売買代金 (億円)", value=3.0, step=0.5, key="st_val_min")
    st_vol_ratio = col_s2.number_input("出来高過疎化 (倍未満)", value=0.8, step=0.1, key="st_vol_ratio")

    col_s3, col_s4 = st.columns(2)
    st_atr_ratio = col_s3.number_input("値幅収縮率 (ATR倍未満)", value=0.6, step=0.1, key="st_atr_ratio")
    st_ma_prox = col_s4.number_input("MA25上方乖離限界 (%)", value=3.0, step=0.5, key="st_ma_prox")

    if st.button("🚀 潜伏索敵開始", key="btn_scan_t2_stealth", type="primary"):
        try: save_settings()
        except NameError: pass

        st.session_state.tab2_scan_results_stealth = None
        st.session_state.tab2_time_log_stealth = [] 
        gc.collect()
        t_global_start = time.time()

        cfg_stealth = {
            "val_min": float(st_val_min), "vol_ratio": float(st_vol_ratio),
            "atr_ratio": float(st_atr_ratio), "ma_prox": float(st_ma_prox)
        }

        def scan_unit_stealth_parallel(code, group, l_date, cfg):
            import pandas as pd
            # 🚨 OOM回避＆爆速化パッチ：計算に必要な直近30日分のみを抽出
            group_df = group.tail(30).copy().ffill().bfill()
            if len(group_df) < 26: return None

            # 🚨 【完全浄化】大元の計算エンジンを強制起動し、純度100%のWilder式実数ATRを付与
            group_df = calc_vector_indicators(group_df)

            v_candidates = [c for c in group_df.columns if 'Volume' in c or 'Vo' in c]
            v_col_name = v_candidates[0] if v_candidates else group_df.columns[-1]

            group_df['AdjC'] = group_df['AdjC'].astype(float)
            group_df['AdjH'] = group_df['AdjH'].astype(float)
            group_df['AdjL'] = group_df['AdjL'].astype(float)
            group_df[v_col_name] = group_df[v_col_name].astype(float)

            # ma25の互換性維持（calc_vector_indicatorsが生成するSMA25を使用）
            if 'SMA25' in group_df.columns:
                group_df['ma25'] = group_df['SMA25']
            elif 'ma25' not in group_df.columns: 
                group_df['ma25'] = group_df['AdjC'].rolling(window=25, min_periods=1).mean()
            
            # 🚨 以前ここにあった自前の単純平均ATR計算（tr.rolling...）は完全に撤去しました

            group_df['daily_value'] = group_df[v_col_name] * group_df['AdjC']
            group_df['avg_value_5'] = group_df['daily_value'].rolling(window=5, min_periods=1).mean()
            group_df['avg_volume_5_prev'] = group_df[v_col_name].shift(1).rolling(window=5, min_periods=1).mean()
            group_df['day_range'] = group_df['AdjH'] - group_df['AdjL']

            today = group_df.iloc[-1]

            # 🚨 浄化された実数ATRの抽出
            if 'ATR_Standard' in today and pd.notna(today['ATR_Standard']):
                real_atr = float(today['ATR_Standard'])
            else:
                real_atr = float(today['AdjC'] * 0.05)

            # --- デバッグ用出力 ---
            # フィルターを通る直前の数値を確認する
            if today['avg_value_5'] < (cfg["val_min"] * 100_000_000):
                # ここで弾かれた場合は件数として無視するが、もし1件も通過しないならここが原因
                pass 
            else:
                import streamlit as st
                st.write(f"DEBUG: 銘柄 {code} は売買代金フィルター通過: {today['avg_value_5'] / 100_000_000:.1f}億円")
                if today[v_col_name] < (today['avg_volume_5_prev'] * cfg["vol_ratio"]):
                    st.write(f"DEBUG: 銘柄 {code} は出来高フィルター通過: {today[v_col_name]} vs {today['avg_volume_5_prev'] * cfg['vol_ratio']:.1f}")
            # --------------------

            if pd.isna(today['avg_value_5']) or today['avg_value_5'] < (cfg["val_min"] * 100_000_000): return None
            if pd.isna(today['avg_volume_5_prev']) or today['avg_volume_5_prev'] <= 0 or today[v_col_name] >= (today['avg_volume_5_prev'] * cfg["vol_ratio"]): return None
            
            # 🚨 修正：判定にも「実数ATR」を厳格に適用
            if pd.isna(real_atr) or real_atr <= 0 or today['day_range'] >= (real_atr * cfg["atr_ratio"]): return None
            if pd.isna(today['ma25']) or today['AdjC'] < today['ma25'] or today['AdjC'] > (today['ma25'] * (1.0 + cfg["ma_prox"] / 100.0)): return None

            return {
                'Code': code, 'lc': float(today['AdjC']), 'ma25': float(today['ma25']),
                'ATR_Standard': real_atr,  # 🚨 TAB4マトリクス用（絶対必須）
                'atr': real_atr,           # 🚨 TAB4マトリクス互換用
                'day_range': float(today['day_range']),
                'avg_value_5': float(today['avg_value_5']), 'curr_vol': float(today[v_col_name]),
                'avg_vol_prev': float(today['avg_volume_5_prev']),
                'T_Rank': 'Stealth💎', 'T_Color': '#00bcd4', 'T_Desc': '大爆発前夜(嵐の前の静けさ)'
            }

        with st.status("🚀 潜伏スキャンを実行中...", expanded=True) as status:
            try:
                raw = get_hist_data_cached(cache_key) if 'cache_key' in locals() or 'cache_key' in globals() else []
                t_fetch = time.time()
                s_msg1 = f"✔️ 第1段階完了：兵站確保 [{t_fetch - t_global_start:.2f}秒]"
                st.write(s_msg1)
                st.session_state.tab2_time_log_stealth.append(s_msg1)

                full_df = clean_df(pd.DataFrame(raw))
                full_df['Code'] = full_df['Code'].astype(str).apply(lambda x: x if len(x) >= 5 else x + "0")

                m_mode = "大型" if "大型株" in st.session_state.get("preset_market", "") else "中小型"
                target_keywords = ['プライム','一部'] if m_mode=="大型" else ['スタンダード','グロース','新興','JASDAQ']
                m_map = globals().get('master_map_t2', globals().get('master_map', {}))
                m_targets = [c for c, m in m_map.items() if any(k in str(m.get('Market', '')) for k in target_keywords)] if m_map else full_df['Code'].unique()

                # 🚨 防弾パッチ：日付型の強制統一と、コピーの明示で警告を回避
                full_df['Date'] = pd.to_datetime(full_df['Date'], errors='coerce')
                latest_date = full_df['Date'].max()
                
                # 抽出ロジック（高速・確実）
                mask = (full_df['Date'] == latest_date) & (full_df['AdjC'] > 0)
                valid_codes = set(full_df[mask]['Code']).intersection(set(m_targets))
                
                # copy() を追加し、後続の編集で警告が出ないように確定
                df = full_df[full_df['Code'].isin(valid_codes)].copy()
                t_clean = time.time()
                s_msg2 = f"✔️ 第2段階完了：ターゲット抽出 [{t_clean - t_fetch:.2f}秒]"
                st.write(s_msg2)
                st.session_state.tab2_time_log_stealth.append(s_msg2)

                results = []
                with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
                    futures = [executor.submit(scan_unit_stealth_parallel, c, g, latest_date, cfg_stealth) for c, g in df.groupby('Code')]
                    for f in concurrent.futures.as_completed(futures):
                        try:
                            res = f.result()
                            if res: results.append(res)
                        except: pass

                st.session_state.tab2_scan_results_stealth = sorted(results, key=lambda x: -x.get('avg_value_5', 0))[:300]

                t_calc = time.time()
                s_msg3 = f"✔️ 第3段階完了：並列演算・抽出完了 [{t_calc - t_clean:.2f}秒]"
                st.write(s_msg3)
                st.session_state.tab2_time_log_stealth.append(s_msg3)

                s_msg4 = f"⏱️ 物理総計索敵時間: {t_calc - t_global_start:.2f}秒"
                st.write(s_msg4)
                st.session_state.tab2_time_log_stealth.append(s_msg4)

                status.update(label=f"🎯 索敵完了！（候補 {len(st.session_state.tab2_scan_results_stealth)} 銘柄確保）", state="complete", expanded=False)
                st.rerun()
            except Exception as e:
                st.error(f"🚨 スキャンエラー: {str(e)}")
                status.update(label="🚨 エラー発生", state="error")

    # --- 💎 潜伏モード 抽出結果描画ブロック ---
    st.divider()
    raw_hits_stealth = st.session_state.get("tab2_scan_results_stealth")
    if raw_hits_stealth is not None:
        # 🚨 潜伏モードの進捗ログのエキスパンダー表示を完全保護
        if "tab2_time_log_stealth" in st.session_state and st.session_state.tab2_time_log_stealth:
            with st.expander(f"🎯 索敵完了！（候補 {len(raw_hits_stealth)} 銘柄確保）", expanded=False):
                for log in st.session_state.tab2_time_log_stealth: 
                    st.write(log)

        if not raw_hits_stealth:
            st.warning("⚠️ **潜伏条件に合致する銘柄は 0 件です。現在、嵐の気配はありません。**")
        else:
            st.success(f"💎 **潜伏（Stealth）ロックオン: {len(raw_hits_stealth)} 銘柄捕捉**")

            # 📋 潜伏モード コピペ用銘柄一覧の完全保護
            copy_codes_stealth = [str(r.get('Code', ''))[:4] for r in raw_hits_stealth]

            # 🎯 物理結線：右上に全コピボタンが出る黒枠ボックス
            st.markdown("#### 📋 抽出銘柄 一括コピー（Stealthターゲット）")
            st.code(",".join(copy_codes_stealth), language="text")

            m_map = globals().get('master_map_t2', globals().get('master_map', {}))
            for r in raw_hits_stealth:
                st.divider()
                c_code = str(r.get('Code', '不明'))
                m_info = m_map.get(c_code, {}) if m_map else {}
                m_lower = str(m_info.get('Market', '')).lower()

                if 'プライム' in m_lower or '一部' in m_lower: badge_html = '<span style="background-color: #1a237e; color: #ffffff; padding: 0.2rem 0.6rem; border-radius: 4px; font-size: 11px; font-weight: bold;">🏢 プライム/大型</span>'
                elif 'グロース' in m_lower or 'マザーズ' in m_lower: badge_html = '<span style="background-color: #1b5e20; color: #ffffff; padding: 0.2rem 0.6rem; border-radius: 4px; font-size: 11px; font-weight: bold;">🚀 グロース/新興</span>'
                else: badge_html = f'<span style="background-color: #455a64; color: #ffffff; padding: 0.2rem 0.6rem; border-radius: 4px; font-size: 11px; font-weight: bold;">{m_info.get("Market","不明")}</span>'

                t_badge = f'<span style="background-color: {r.get("T_Color", "#00bcd4")}; color: #ffffff; padding: 0.2rem 0.6rem; border-radius: 4px; font-size: 13px; font-weight: bold; margin-left: 0.5rem;">💎 {r.get("T_Rank", "Stealth")}</span>'
                sector_badge = f'<span style="background-color: #607d8b; color: #ffffff; padding: 0.1rem 0.5rem; border-radius: 4px; font-size: 12px; margin-left: 0.5rem;">🏭 {m_info.get("Sector", "不明")}</span>'

                vol_ratio = (r.get("curr_vol", 0) / r.get("avg_vol_prev", 1)) * 100
                vol_badge = f'<span style="background-color: rgba(0, 188, 212, 0.1); border: 1px solid #00bcd4; color: #00bcd4; padding: 0.1rem 0.5rem; border-radius: 4px; font-size: 12px; margin-left: 0.5rem;">📉 出来高過疎: {vol_ratio:.0f}%</span>'
                status_badge_html = f'<span style="background-color: rgba(0, 188, 212, 0.15); border: 1px solid #00bcd4; color: #00bcd4; padding: 0.1rem 0.5rem; border-radius: 4px; font-size: 12px; margin-left: 0.5rem;">{r.get("T_Desc", "嵐の前の静けさ")}</span>'

                st.markdown(f"""
                    <div style="margin-bottom: 0.8rem;">
                        <h3 style="font-size: 24px; font-weight: bold; margin: 0 0 0.3rem 0;">({c_code[:4]}) {m_info.get('CompanyName', '不明')}</h3>
                        <div style="display: flex; flex-wrap: wrap; gap: 6px; align-items: center;">
                            {badge_html}{t_badge}{sector_badge}{vol_badge}{status_badge_html}
                        </div>
                    </div>
                """, unsafe_allow_html=True)

                # 🚨 物理消滅していた残りのUI描画約30行分を、強襲モードに準拠した最高品質のインデントで完全縫合
                col_d1, col_d2, col_d3 = st.columns(3)
                col_d1.metric("最新終値", f"{int(r.get('lc', 0)):,}円")

                atr_val = r.get('atr', 1)
                atr_val = atr_val if atr_val > 0 else 1 
                contraction = r.get('day_range', 0) / atr_val

                col_d2.metric("値幅収縮率 (値幅/ATR)", f"{contraction:.2f}倍")
                col_d3.metric("5日平均売買代金", f"{int(r.get('avg_value_5', 0) / 100_000_000)}億円")


# --- 8. タブコンテンツ (TAB4: 精密スコープ) ---
with tab4:
    st.markdown('<h3 style="font-size: clamp(14px, 4.5vw, 24px); margin-bottom: 1rem;">🎯 【照準】精密スコープ（戦術ウェイト・UI完全復元版）</h3>', unsafe_allow_html=True)
    
    # セーブファイル定義（ボスの資産）
    T3_AM_WATCH_FILE = f"saved_t3_am_watch_{user_id}.txt"
    T3_AM_DAILY_FILE = f"saved_t3_am_daily_{user_id}.txt"
    T3_AS_WATCH_FILE = f"saved_t3_as_watch_{user_id}.txt"
    T3_AS_DAILY_FILE = f"saved_t3_as_daily_{user_id}.txt"
    T3_ST_WATCH_FILE = f"saved_t3_st_watch_{user_id}.txt" # 💎 潜伏用セーブファイル追加
    T3_ST_DAILY_FILE = f"saved_t3_st_daily_{user_id}.txt" # 💎 潜伏用セーブファイル追加

    def load_t3_text(file_path):
        if os.path.exists(file_path):
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    content = f.read()
                    return content
            except Exception:
                return ""
        return ""

    # 🚨 修正1：永続バッファ（buf）の初期化。非表示になってもここから復元するため絶対に蒸発しません。
    if "t3_am_watch_buf" not in st.session_state: st.session_state.t3_am_watch_buf = load_t3_text(T3_AM_WATCH_FILE)
    if "t3_am_daily_buf" not in st.session_state: st.session_state.t3_am_daily_buf = load_t3_text(T3_AM_DAILY_FILE)
    if "t3_as_watch_buf" not in st.session_state: st.session_state.t3_as_watch_buf = load_t3_text(T3_AS_WATCH_FILE)
    if "t3_as_daily_buf" not in st.session_state: st.session_state.t3_as_daily_buf = load_t3_text(T3_AS_DAILY_FILE)
    if "t3_st_watch_buf" not in st.session_state: st.session_state.t3_st_watch_buf = load_t3_text(T3_ST_WATCH_FILE) # 💎
    if "t3_st_daily_buf" not in st.session_state: st.session_state.t3_st_daily_buf = load_t3_text(T3_ST_DAILY_FILE) # 💎

    col_s1, col_s2 = st.columns([1.2, 1.8])
    with col_s1:
        # 💎 潜伏（Stealth）モードをラジオボタンに追加
        scope_mode = st.radio("🎯 解析モードを選択", ["🌐 【待伏】 押し目・逆張り", "⚡ 【強襲】 トレンド・順張り", "💎 【潜伏】 収縮・上放れ狙い"], key="t3_scope_mode_absolute_lock_v2026")
        is_ambush = "待伏" in scope_mode
        is_stealth = "潜伏" in scope_mode # 💎 潜伏フラグ
        st.markdown("---")
        
        # 🚨 修正2：【相互補完型・永続バッファ同期システム】
        if is_ambush:
            if "t3_am_watch_widget" not in st.session_state: st.session_state.t3_am_watch_widget = st.session_state.t3_am_watch_buf
            if "t3_am_daily_widget" not in st.session_state: st.session_state.t3_am_daily_widget = st.session_state.t3_am_daily_buf
            watch_in = st.text_area("🌐 【待伏】主力監視部隊", key="t3_am_watch_widget", height=120)
            daily_in = st.text_area("🌐 【待伏】本日新規部隊", key="t3_am_daily_widget", height=120)
            st.session_state.t3_am_watch_buf = watch_in
            st.session_state.t3_am_daily_buf = daily_in
        elif is_stealth:
            # 💎 潜伏モード用UIバッファ処理
            if "t3_st_watch_widget" not in st.session_state: st.session_state.t3_st_watch_widget = st.session_state.t3_st_watch_buf
            if "t3_st_daily_widget" not in st.session_state: st.session_state.t3_st_daily_widget = st.session_state.t3_st_daily_buf
            watch_in = st.text_area("💎 【潜伏】主力監視部隊", key="t3_st_watch_widget", height=120)
            daily_in = st.text_area("💎 【潜伏】本日新規部隊", key="t3_st_daily_widget", height=120)
            st.session_state.t3_st_watch_buf = watch_in
            st.session_state.t3_st_daily_buf = daily_in
        else:
            if "t3_as_watch_widget" not in st.session_state: st.session_state.t3_as_watch_widget = st.session_state.t3_as_watch_buf
            if "t3_as_daily_widget" not in st.session_state: st.session_state.t3_as_daily_widget = st.session_state.t3_as_daily_buf
            watch_in = st.text_area("⚡ 【強襲】主力監視部隊", key="t3_as_watch_widget", height=120)
            daily_in = st.text_area("⚡ 【強襲】本日新規部隊", key="t3_as_daily_widget", height=120)
            st.session_state.t3_as_watch_buf = watch_in
            st.session_state.t3_as_daily_buf = daily_in
            
        run_scope = st.button("🔫 表示中の部隊を精密スキャン", use_container_width=True, type="primary", key=f"t3_run_btn_vfinal_{cache_key}")
        
    with col_s2:
        st.markdown("#### 🔍 索敵ステータス ＆ 行動指針")
        if is_ambush:
            st.info("""**🌐 【待伏】モード（押し目・逆張り）**
底打ち反転の迎撃戦。安値圏での「陰の極み」「二重底」を検知。
            
**【🚨 市場連動バフ稼働中】**
日経平均25日乖離率が冷え込んでいる（-5%〜-8%以下）場合、パニック売りによる底値圏と判断し、**スコアをボーナス加点(+3〜+5pts)** します。

**【PTS評価軸】**
- **12点以上 (S級🔥)** 全力買い：複数の酒田サイン（陰の極み・二重底等）が重複、勝率・値幅共に期待値最大
- **8〜11点 (A級💎)** 買い：トリアージ（ATR/RSI）が反転を示唆、PBR等の割安背景も良好
- **5〜7点 (B級🛡️)** 様子見：底打ちの兆候はあるが引き金（シグナル）不足、監視を継続
- **5点未満 (圏外💀)** 見送り：兵站（データ）不足、または下落トレンドの真っ立ち中、手を出すべきではない""")
        elif is_stealth:
            # 💎 潜伏モードの行動指針
            st.info("""**💎 【潜伏】モード（収縮・上放れ狙い）**
ボラティリティ収縮からのレンジブレイク初動を狙うハントモード。

**【セットアップ基準】**
- 🟢 **煮詰まり検知：** 当日の実体が値幅の10%以下の「極小十字線」
- 💀 **防衛機構：** 前日終値から1ATR以上のギャップダウンで「強制撤退（圏外）」
- 🎯 **自動ターゲット：** 過去3日高値突破でエントリー、防衛線はMA25を基準にリスク幅を自動算出（8%超過で警告）
- 🌟 **潜伏スコア加点：** 極限の収縮(+5)、売り枯れ(+3)、MA25上昇(+5)でS級昇格を判定""")
        else:
            st.info("""**⚡ 【強襲】モード（トレンド・順張り）**
トレンド初動の电击戦。14日高値突破とGCを監視。

**【🚨 市場連動デバフ稼働中】**
日経平均25日乖離率が過熱（+5%〜+8%超）している場合、天井掴みを防ぐため**スコアを強制的にデグレード(-20〜-35pts)** します。
            
**【PTS評価軸】**
- **80点以上 (S級⚡)** 即・強襲：GC直後かつ、ROE10%以上の優良ファンダが裏打ち
- **60〜79点 (A級🔥)** 追撃買い：GCから数日経過、勢いは維持されているが、高値掴みに注意しつつエントリー
- **40〜59点 (B級📈)** 様子見：トレンド初動を逃したか勢いが鈍化のため、調整を待つのが賢明
- **40点未満 (圏外💀)** 撤退/見送り：天井圏の罠（三尊・三山等）を検知、またはトレンドが未発生""")

    if run_scope:
        # 🚨 修正3：重複コードを完全パージし、バッファからファイルへ確実な書き込みを実行
        if is_ambush:
            for f, d in [(T3_AM_WATCH_FILE, st.session_state.t3_am_watch_buf), (T3_AM_DAILY_FILE, st.session_state.t3_am_daily_buf)]:
                with open(f, "w", encoding="utf-8") as file: file.write(d)
        elif is_stealth:
            for f, d in [(T3_ST_WATCH_FILE, st.session_state.t3_st_watch_buf), (T3_ST_DAILY_FILE, st.session_state.t3_st_daily_buf)]:
                with open(f, "w", encoding="utf-8") as file: file.write(d)
        else:
            for f, d in [(T3_AS_WATCH_FILE, st.session_state.t3_as_watch_buf), (T3_AS_DAILY_FILE, st.session_state.t3_as_daily_buf)]:
                with open(f, "w", encoding="utf-8") as file: file.write(d)

        # 🚨 物理結線：市場地合い（乖離率）の事前取得（NameError防止 ＆ 演算同期）
        n225_m_data = get_nikkei_macro_status()
        n225_div_rate = n225_m_data['div_rate'] if n225_m_data else 0.0

        import unicodedata
        import re
        import time
        import numpy as np
        raw_all_text = watch_in + " " + daily_in
        all_text = unicodedata.normalize('NFKC', raw_all_text).upper()
        t_codes = list(dict.fromkeys([c for c in re.findall(r'(?<![A-Z0-9])[0-9]{3}[0-9A-Z][0-9]?(?![A-Z0-9])', all_text)]))
        
        if not t_codes:
            st.warning("有効な銘柄コードが確認できません。")
        else:
            t_global_start = time.time()
            with st.status(f"🚀 全 {len(t_codes)} 銘柄を精密スキャン中...", expanded=True) as status:
                st.write("📡 第1段階：並列データ収集（三重フォールバック）を実行中...")
                
                def fetch_parallel_t3(c):
                    try:
                        c_str = str(c).upper().strip()
                        api_code = c_str if len(c_str) >= 5 else c_str + "0"
                        events = {"dividend": [], "earnings": []}
                        
                        # 1. API取得試行
                        data = get_single_data(api_code, 3)
                        if data and isinstance(data.get("events"), dict):
                            api_ev = data.get("events", {})
                            if api_ev.get("earnings"): 
                                events["earnings"].extend(api_ev["earnings"])
                            if api_ev.get("dividend"): 
                                events["dividend"].extend(api_ev["dividend"])
                        
                        # 2. データ不足時のフォールバック (yfinance)
                        if not data or not isinstance(data.get("bars"), list) or len(data.get("bars", [])) < 60:
                            try:
                                import yfinance as yf
                                tk = yf.Ticker(c_str + ".T")
                                hist = tk.history(period="6mo") 
                                
                                if not hist.empty:
                                    bars = []
                                    for dt, row in hist.iterrows():
                                        bars.append({
                                            'Code': api_code, 
                                            'Date': dt.strftime('%Y-%m-%d'),
                                            'AdjO': float(row.get('Open', 0)), 
                                            'AdjH': float(row.get('High', 0)),
                                            'AdjL': float(row.get('Low', 0)), 
                                            'AdjC': float(row.get('Close', 0)),
                                            'AdjustmentVolume': float(row.get('Volume', 0))
                                        })
                                    data = {"bars": bars}
                            except Exception:
                                pass # フォールバック失敗時はdata=Noneのまま進行
                        
                        # 3. 決算イベントの補完取得
                        if not events["earnings"]:
                            try:
                                import yfinance as yf
                                tk_ev = yf.Ticker(c_str + ".T")
                                info_ev = tk_ev.info
                                e_date = info_ev.get('earningsAnnouncement') or info_ev.get('nextEarningsDate') or info_ev.get('earningsTimestamp')
                                if e_date:
                                    if isinstance(e_date, list) and len(e_date) > 0: e_date = e_date[0]
                                    events["earnings"].append({"Code": api_code, "Date": str(e_date)})
                            except Exception:
                                pass
                        
                        # 4. 財務情報取得と初期化
                        f_data = get_fundamentals(c_str)
                        r_per, r_pbr, r_mcap, r_roe = None, None, None, None
                        
                        if f_data:
                            if f_data.get('per'): r_per = f_data.get('per')
                            if r_per is None and f_data.get('PER'): r_per = f_data.get('PER')
                            if r_per is None and f_data.get('trailingPE'): r_per = f_data.get('trailingPE')
                            if r_per is None and f_data.get('forwardPE'): r_per = f_data.get('forwardPE')
                            
                            if f_data.get('pbr'): r_pbr = f_data.get('pbr')
                            if r_pbr is None and f_data.get('PBR'): r_pbr = f_data.get('PBR')
                            if r_pbr is None and f_data.get('priceToBook'): r_pbr = f_data.get('priceToBook')
                            
                            if f_data.get('cap'): r_mcap = f_data.get('cap')
                            if r_mcap is None and f_data.get('MCAP'): r_mcap = f_data.get('MCAP')
                            if r_mcap is None and f_data.get('marketCap'): r_mcap = f_data.get('marketCap')
                            if r_mcap is None and f_data.get('MarketCapitalization'): r_mcap = f_data.get('MarketCapitalization')
                            
                            if f_data.get('roe'): r_roe = f_data.get('roe')
                            if r_roe is None and f_data.get('ROE'): r_roe = f_data.get('ROE')
                            if r_roe is None and f_data.get('returnOnEquity'): r_roe = f_data.get('returnOnEquity')
                            
                            if r_roe is None:
                                try:
                                    ni = f_data.get("NetIncome")
                                    eq = f_data.get("Equity")
                                    if ni is not None and eq is not None:
                                        ni_f, eq_f = float(ni), float(eq)
                                        r_roe = (ni_f / eq_f) * 100 if eq_f != 0 else 0.0
                                    else:
                                        r_roe = 0.0
                                except Exception:
                                    r_roe = 0.0
                            
                            e_date_f = f_data.get("EarningsDate") or f_data.get("NextEarningsDate") or f_data.get("AnnouncementDate")
                            if e_date_f:
                                events["earnings"].append({"Code": api_code, "Date": str(e_date_f)})

                        if r_per is None or r_pbr is None or r_mcap is None or r_roe is None:
                            try:
                                import yfinance as yf
                                import time
                                time.sleep(0.5)
                                tk_f = yf.Ticker(c_str + ".T")
                                info = tk_f.info
                                if info:
                                    if r_per is None: r_per = info.get('trailingPE') or info.get('forwardPE')
                                    if r_pbr is None: r_pbr = info.get('priceToBook')
                                    if r_mcap is None: r_mcap = info.get('marketCap')
                                    if r_roe is None and info.get('returnOnEquity') is not None:
                                        r_roe = float(info.get('returnOnEquity')) * 100
                            except Exception:
                                pass
                        
                        return c_str, data, r_per, r_pbr, r_mcap, r_roe, events
                    except Exception:
                        return str(c), None, None, None, None, None, {"dividend": [], "earnings": []}

                raw_data_dict = {}
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor(max_workers=3) as exe:
                    futs = [exe.submit(fetch_parallel_t3, c) for c in t_codes]
                    for f in concurrent.futures.as_completed(futs):
                        try:
                            res_c, res_data, r_per, r_pbr, r_mcap, r_roe, res_events = f.result()
                            raw_data_dict[str(res_c)] = {
                                "data": res_data, 
                                "per": r_per, 
                                "pbr": r_pbr, 
                                "mcap": r_mcap, 
                                "roe": r_roe,
                                "events": res_events
                            }
                        except Exception:
                            continue

                t_fetch = time.time()
                st.write(f"✔️ データ収集完了 [{t_fetch - t_global_start:.2f}秒]")
                st.write("⚙️ 第2段階：解析・ボラティリティ審査を実行中...")

                scope_results = []
                for c in t_codes:
                    target_key = str(c).upper().strip()
                    try:
                        raw_s = raw_data_dict.get(target_key, {})
                        api_code = target_key if len(target_key) >= 5 else target_key + "0"
                        c_name, c_sector, c_market = f"銘柄 {target_key}", "不明", "不明"
                        if not master_df.empty:
                            m_row = master_df[master_df['Code'].astype(str).isin([target_key, api_code])]
                            if not m_row.empty:
                                c_name = m_row.iloc[0]['CompanyName']
                                c_sector = m_row.iloc[0]['Sector']
                                c_market = m_row.iloc[0]['Market']

                        res_per, res_pbr, res_roe, raw_mcap = raw_s.get('per'), raw_s.get('pbr'), raw_s.get('roe'), raw_s.get('mcap')
                        
                        if res_roe is not None:
                            try:
                                res_roe_f = float(res_roe)
                                if 0 < abs(res_roe_f) < 1.0:
                                    res_roe = res_roe_f * 100
                                else:
                                    res_roe = res_roe_f
                            except Exception:
                                res_roe = None

                        res_mcap_str = "-"
                        if raw_mcap is not None:
                            try:
                                rmc = float(raw_mcap)
                                if rmc >= 1e12:
                                    res_mcap_str = f"{rmc / 1e12:.2f}兆円"
                                elif rmc >= 1e8:
                                    res_mcap_str = f"{rmc / 1e8:.0f}億円"
                                elif rmc >= 1e4:
                                    res_mcap_str = f"{rmc / 1e4:.0f}万円"
                                else:
                                    res_mcap_str = f"{int(rmc):,}円"
                            except Exception:
                                res_mcap_str = "-"

                        # 🚨 修正：TAB4にも不沈艦フォールバック（fetch_parallel_t3）を接続
                        bars = raw_s.get("data", {}).get("bars", []) if raw_s.get("data") else []
                        
                        if not bars or len(bars) < 20:
                            f_data, _ = fetch_parallel_t3(target_key)
                            if f_data and "bars" in f_data:
                                bars = f_data["bars"]

                        # 最終チェック
                        if not bars or len(bars) < 20:
                            scope_results.append({
                                'code': target_key, 'name': c_name, 'lc': 0, 'h14': 0, 'l14': 0, 'ur': 0, 'bt_val': 0, 'atr_val': 0, 'rsi': 50,
                                'rank': '圏外💀', 'bg': '#616161', 'score': 0, 'reach_val': 0, 'gc_days': 0, 'df_chart': pd.DataFrame(),
                                'per': res_per, 'pbr': res_pbr, 'roe': res_roe, 'mcap': res_mcap_str, 'source': "🛡️ 監視" if target_key in watch_in else "🚀 新規", 
                                'sector': c_sector, 'market': c_market, 'alerts': ["⚠️ 兵站データ不足"], 'error': True, 'is_deep': False,
                                'events': curr_events, 'stealth_data': {}
                            })
                            continue

                        if st.session_state.get('f5_ipo', False):
                            try:
                                m_row = master_df[master_df['Code'].astype(str).isin([target_key, api_code])]
                                if not m_row.empty:
                                    ld_col = [col for col in m_row.columns if 'Listing' in col]
                                    if ld_col:
                                        target_val = m_row.iloc[0][ld_col[0]]
                                        if pd.notna(target_val):
                                            target_dt = pd.to_datetime(target_val).replace(tzinfo=None)
                                            now_dt = datetime.now().replace(tzinfo=None)
                                            if (now_dt - target_dt).days < 365:
                                                continue 
                            except Exception:
                                pass

                        curr_events = raw_s.get("events", {"dividend": [], "earnings": []})

                        if not bars or len(bars) < 20:
                            scope_results.append({
                                'code': target_key, 'name': c_name, 'lc': 0, 'h14': 0, 'l14': 0, 'ur': 0, 'bt_val': 0, 'atr_val': 0, 'rsi': 50,
                                'rank': '圏外💀', 'bg': '#616161', 'score': 0, 'reach_val': 0, 'gc_days': 0, 'df_chart': pd.DataFrame(),
                                'per': res_per, 'pbr': res_pbr, 'roe': res_roe, 'mcap': res_mcap_str, 'source': "🛡️ 監視" if target_key in watch_in else "🚀 新規", 
                                'sector': c_sector, 'market': c_market, 'alerts': ["⚠️ 兵站データ不足"], 'error': True, 'is_deep': False,
                                'events': curr_events, 'stealth_data': {} # 💎
                            })
                            continue

                        df_raw = pd.DataFrame(bars)
                        if 'Code' not in df_raw.columns:
                            df_raw['Code'] = api_code
                        
                        df_s = clean_df(df_raw)
                        
                        if df_s.empty or len(df_s) < 20:
                            scope_results.append({
                                'code': target_key, 'name': c_name,
                                'lc': 0, 'h14': 0, 'l14': 0, 'ur': 0, 'bt_val': 0, 'atr_val': 0, 'rsi': 50,
                                'rank': '圏外💀', 'bg': '#616161', 'score': 0, 'reach_val': 0, 'gc_days': 0,
                                'df_chart': pd.DataFrame(),
                                'per': res_per, 'pbr': res_pbr, 'roe': res_roe, 'mcap': res_mcap_str,
                                'source': "🛡️ 監視" if target_key in watch_in else "🚀 新規", 
                                'sector': c_sector, 'market': c_market,
                                'alerts': ["⚠️ 兵站データ破損（有効期間不足）"],
                                'error': True, 'is_deep': False,
                                'events': curr_events, 'stealth_data': {} # 💎
                            })
                            continue

                        # テクニカル演算
                        try:
                            df_chart_full = calc_technicals(df_s.copy())
                        except Exception:
                            df_chart_full = df_s.copy()
                            
                        t_latest = df_chart_full.iloc[-1]
                        t_prev = df_chart_full.iloc[-2]
                        t_pprev = df_chart_full.iloc[-3]
                        
                        lc = float(t_latest['AdjC'])
                        lo = float(t_latest['AdjO'])
                        lh = float(t_latest['AdjH'])
                        ll = float(t_latest['AdjL'])
                        
                        h14 = float(df_chart_full.tail(15).iloc[:-1]['AdjH'].max())
                        l14 = float(df_chart_full.tail(15).iloc[:-1]['AdjL'].min())
                        ur_v = (h14 - l14)
                        
                        # 🚨 修正: RSIを正しく取得。欠損時は計算するフォールバック
                        if 'RSI' in df_chart_full.columns and pd.notna(t_latest['RSI']):
                            rsi_v = float(t_latest['RSI'])
                        else:
                            try:
                                delta = df_chart_full['AdjC'].diff()
                                gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
                                loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
                                rs = gain / loss
                                rsi_series = 100 - (100 / (1 + rs))
                                rsi_v = float(rsi_series.iloc[-1])
                                df_chart_full['RSI'] = rsi_series # DataFrameにもセット
                            except Exception:
                                rsi_v = 50.0

                        if 'ATR' in df_chart_full.columns and pd.notna(t_latest['ATR']):
                            atr_v = float(t_latest['ATR'])
                        else:
                            atr_v = lc * 0.05
                            
                        df_mini = df_chart_full.tail(260).copy()
                        
                        score = 0
                        alerts = []
                        gc_days = 0
                        is_deep = False
                        stealth_payload = {} # 💎

                        vol_pct = 0
                        if lc > 0:
                            vol_pct = (atr_v / lc * 100)
                        
                        if vol_pct < 0.5:
                            alerts.append(f"⚠️ 【超低ボラ】ボラ率 {vol_pct:.2f}%。資金効率低下の恐れあり。")

                        t_events = (raw_s.get("data") or {}).get("events")
                        alerts.extend(check_event_mines(target_key, raw_s.get("events", {})))
                        
                        try:
                            import pytz
                            from datetime import datetime
                            tz = pytz.timezone('Asia/Tokyo')
                            today_d = datetime.now(tz_jst).date() if 'tz_jst' in locals() else datetime.now(tz).date()
                            ev_data = raw_s.get("events", {})
                            
                            def parse_and_check(date_val, event_name, icon):
                                d_str = str(date_val).strip()
                                if not d_str or d_str == "None": return
                                try:
                                    if d_str.isdigit() and len(d_str) >= 10:
                                        d_obj = datetime.fromtimestamp(int(d_str[:10]), tz).date()
                                    else:
                                        d_obj = datetime.strptime(d_str[:10], "%Y-%m-%d").date()
                                    
                                    days_diff = (d_obj - today_d).days
                                    if 0 <= days_diff <= 14:
                                        msg = f"{icon} 【{event_name}接近】あと {days_diff} 日 ({d_obj.strftime('%m/%d')})"
                                        if not any(event_name in a for a in alerts):
                                            alerts.append(msg)
                                except Exception:
                                    pass

                            for e in ev_data.get("earnings", []):
                                parse_and_check(e.get("Date"), "決算", "📅")
                            for d in ev_data.get("dividend", []):
                                parse_and_check(d.get("Date"), "権利落ち", "🍇")
                        except Exception:
                            pass
                        
                        s_results = detect_sakata_patterns(df_chart_full)
                        for p in s_results:
                            alerts.append(p['text'])

                        has_top_trap_t3 = any(x in "".join(alerts) for x in ["三山", "三尊", "二重天井", "買い三空", "二重頂", "三尊天井"])

                        # =========================================================================
                        # 💎 潜伏（Stealth）モードの完全独立処理ブロック
                        # =========================================================================
                        if is_stealth:
                            df_sub = df_chart_full.copy()
                            
                            if len(df_sub) < 25:
                                rank = "圏外💀"
                                bg_c = "#616161"
                                alerts.append("⚠️ データ不足による潜伏解析不能")
                                bt_val = lc
                                reach_rate = 0
                            else:
                                c_col = 'AdjC'
                                o_col = 'AdjO'
                                h_col = 'AdjH'
                                l_col = 'AdjL'

                                df_sub['prev_C'] = df_sub[c_col].shift(1)
                                df_sub['TR'] = np.maximum(
                                    df_sub[h_col] - df_sub[l_col],
                                    np.maximum(
                                        abs(df_sub[h_col] - df_sub['prev_C']),
                                        abs(df_sub[l_col] - df_sub['prev_C'])
                                    )
                                )
                                df_sub['ATR14'] = df_sub['TR'].rolling(window=14).mean()
                                df_sub['MA25'] = df_sub[c_col].rolling(window=25).mean()

                                s_latest = df_sub.iloc[-1]
                                s_prev = df_sub.iloc[-2]

                                c_val = s_latest[c_col]
                                o_val = s_latest[o_col]
                                h_val = s_latest[h_col]
                                l_val = s_latest[l_col]
                                prev_c_val = s_prev[c_col]
                                atr14_val = s_latest['ATR14']
                                ma25_val = s_latest['MA25']

                                rank = "A級💎"
                                bg_c = "#2e7d32"
                                score = 10 # 💎 潜伏時の基本スコア

                                body_size = abs(c_val - o_val)
                                day_range = h_val - l_val
                                
                                # 🚨 追加: 潜伏スコア加点ロジック
                                if day_range > 0:
                                    if body_size <= (day_range * 0.05):
                                        score += 5
                                        alerts.append("🟢【極小十字線】極限の煮詰まりを検知（+5pts）")
                                    elif body_size <= (day_range * 0.10):
                                        alerts.append("🟢【極小十字線】煮詰まりの極致")

                                # 🚨 修正: 枯渇ボーナス (Volumeキーエラー対策の堅牢化)
                                vol_col = 'Volume' if 'Volume' in df_sub.columns else ('volume' if 'volume' in df_sub.columns else None)
                                if vol_col and len(df_sub) >= 6:
                                    vol_5d_avg = df_sub[vol_col].iloc[-6:-1].mean()
                                    curr_vol = s_latest[vol_col]
                                    if pd.notna(vol_5d_avg) and vol_5d_avg > 0 and pd.notna(curr_vol) and curr_vol < (vol_5d_avg * 0.5):
                                        score += 3
                                        alerts.append("💎【売り枯れ】出来高が直近平均の50%未満へ急減（+3pts）")

                                # トレンド同調ボーナス
                                prev_ma25_val = s_prev['MA25']
                                if pd.notna(ma25_val) and pd.notna(prev_ma25_val) and ma25_val > prev_ma25_val:
                                    score += 5
                                    alerts.append("🔥【上昇同調】MA25上向き。順張り方向の潜伏（+5pts）")

                                if o_val <= (prev_c_val - atr14_val):
                                    alerts.append("💀【偽潜伏・パニック警戒】ギャップダウンによるトレンド崩壊")
                                    rank = "圏外💀"
                                    bg_c = "#616161"
                                    score = 0
                                elif score >= 18:
                                    rank = "S級潜伏🔥"
                                    bg_c = "#1b5e20"

                                high_3d = df_sub[h_col].iloc[-3:].max()
                                entry_trigger = int(round(high_3d + 1))
                                stop_loss = int(round(ma25_val - (atr14_val * 0.5)))
                                take_profit = int(round(entry_trigger + ((entry_trigger - stop_loss) * 2)))

                                if entry_trigger > 0:
                                    risk_pct = (entry_trigger - stop_loss) / entry_trigger
                                else:
                                    risk_pct = 1.0

                                if risk_pct > 0.08:
                                    alerts.append("⚠️ 【リスク超過】損切り幅が8%を超えています。ロットを縮小するか見送りを推奨")

                                stealth_payload = {
                                    "entry_trigger": entry_trigger,
                                    "stop_loss": stop_loss,
                                    "take_profit": take_profit,
                                    "risk_pct": round(risk_pct * 100, 2)
                                }
                                
                                bt_val = entry_trigger
                                reach_rate = 100.0 if rank != "圏外💀" else 0.0

                        # =========================================================================
                        # 🌐 待伏（Ambush）モード処理ブロック
                        # =========================================================================
                        elif is_ambush:
                            score = 4

                            if n225_div_rate <= -8.0:
                                score += 5
                                alerts.append(f"💎 【待伏好機】日経乖離率 {n225_div_rate:+.2f}%。パニック売り局面、反転期待値を最大加点。")
                            elif n225_div_rate <= -5.0:
                                score += 3
                                alerts.append(f"⚓ 【地合い支援】日経乖離率 {n225_div_rate:+.2f}%。安値圏、迎撃成功率を上方修正。")
                            elif n225_div_rate >= 8.0:
                                score -= 5
                                alerts.append(f"⚠️ 【地合い逆風】日経乖離率 {n225_div_rate:+.2f}%。市場全体が天井圏につき、偽の押し目に警戒。")
                            elif n225_div_rate >= 5.0:
                                score -= 3
                                alerts.append(f"🌐 【地合い警戒】日経乖離率 {n225_div_rate:+.2f}%。高値圏につき、慎重なエントリーを。")

                            # 🚨 修正: 待伏せモードでのRSI加点ロジック実装
                            if rsi_v <= 20:
                                score += 5
                                alerts.append(f"🔥 【極度売られすぎ】RSI {rsi_v:.1f}%。強烈な反発エネルギーを内包。")
                            elif rsi_v <= 30:
                                score += 3
                                alerts.append(f"⚡ 【売られすぎ】RSI {rsi_v:.1f}%。オシレーターが底値圏を示唆。")

                            base_push_r = st.session_state.push_r / 100.0
                            bt_val_standard = h14 - (ur_v * base_push_r)
                            bt_val_deep = h14 - (ur_v * 0.618)
                            
                            if lc < (bt_val_standard * 0.95):
                                bt_val = int(bt_val_deep)
                                is_deep = True
                                if not any("深海" in a for a in alerts):
                                    alerts.append("💎 【深海待伏】目標地点より5%以上乖離。61.8%押しへ補正。")
                            else:
                                bt_val = int(bt_val_standard)

                            # 🚨 MACD完全排除：ATRベースの価格アクショントリアージエンジン
                            triage_score = 0
                            if lc > (bt_val + atr_v):
                                alerts.append("🟡 【未達・監視】買目標まで距離あり。引き付け継続。")
                            elif (bt_val - atr_v) <= lc <= (bt_val + atr_v):
                                alerts.append("🟢 【迎撃圏内】買目標の±1ATR圏内に突入。反転兆候を注視。")
                                triage_score = 4
                            else:
                                alerts.append("💀 【底割れ警戒】買目標を下抜け。パニック売りに警戒。")
                                triage_score = -2
                            
                            score += triage_score
                            
                            if res_pbr is not None:
                                if res_pbr <= 5.0:
                                    score += 2
                            
                            if any("二重底" in a for a in alerts): score += 3
                            if any("たくり" in a for a in alerts): score += 5
                            if any("陰の極み" in a for a in alerts): score += 7

                            reach_rate = 0
                            if (h14 - bt_val) > 0:
                                reach_rate = ((h14 - lc) / (h14 - bt_val) * 100)
                            
                            if score >= 12:
                                rank = "S級待伏🔥"
                                bg_c = "#1b5e20"
                            elif score >= 8:
                                rank = "A級待伏💎"
                                bg_c = "#2e7d32"
                            elif score >= 5:
                                rank = "B級待伏🛡️"
                                bg_c = "#4caf50"
                            else:
                                rank = "圏外💀"
                                bg_c = "#616161"

                        # =========================================================================
                        # ⚡ 強襲（Assault）モード処理ブロック
                        # =========================================================================
                        else:
                            bt_val = int(max(h14, lc + (atr_v * 0.5)))
                            
                            c_vals_t3 = df_mini['AdjC'].values
                            if len(c_vals_t3) >= 25:
                                s_c_t3 = pd.Series(c_vals_t3)
                                ma5_s_t3 = s_c_t3.rolling(5).mean().values
                                ma25_s_t3 = s_c_t3.rolling(25).mean().values
                                
                                ma5_t3 = ma5_s_t3[-1]
                                ma25_t3 = ma25_s_t3[-1]
                                prev_ma5_t3 = ma5_s_t3[-2]
                            else:
                                ma5_t3, ma25_t3, prev_ma5_t3 = 0, 0, 0
                                
                            gc_days = 0
                            gc_score = 5
                            is_pre_gc_t3 = False
                            
                            if ma5_t3 > 0 and ma25_t3 > 0 and prev_ma5_t3 > 0:
                                if ma5_t3 >= ma25_t3:
                                    for d in range(1, 4): 
                                        if ma5_s_t3[-d] >= ma25_s_t3[-d] and ma5_s_t3[-(d+1)] < ma25_s_t3[-(d+1)]:
                                            gc_days = d
                                            break
                                    if gc_days == 1: gc_score = 60
                                    elif gc_days == 2: gc_score = 40
                                else:
                                    dist_pct_t3 = ((ma5_t3 / ma25_t3) - 1) * 100
                                    if (lc > ma5_t3) and (lc > ma25_t3) and (-2.0 <= dist_pct_t3 < 0.0) and (ma5_t3 > prev_ma5_t3):
                                        is_pre_gc_t3 = True
                                        gc_score = 95
                                
                            score = gc_score + (10 if (res_roe is not None and res_roe >= 10.0) else 0)

                            # 🚨 修正: 強襲モードでのRSI加減点ロジック実装
                            if rsi_v >= 80:
                                score -= 10
                                alerts.append(f"⚠️ 【高値掴み警戒】RSI {rsi_v:.1f}%。過熱しすぎの兆候。")
                            elif 50 <= rsi_v <= 70:
                                score += 5
                                alerts.append(f"🔥 【トレンド初動】RSI {rsi_v:.1f}%。モメンタム加速圏内。")

                            _macro_t3 = get_macro_weather()
                            if _macro_t3 and "nikkei" in _macro_t3:
                                _df_m = _macro_t3["nikkei"]["df"]
                                if not _df_m.empty and len(_df_m) >= 25:
                                    # 🚨 モグラ駆逐パッチ：ここも安全な動的カラム取得と強制1次元化に書き換え
                                    _close_col_m = next((c for c in ['AdjC', 'Close', 'close', 'C', 'c'] if c in _df_m.columns), None)
                                    
                                    if _close_col_m:
                                        _s_m = _df_m[_close_col_m]
                                        if isinstance(_s_m, pd.DataFrame):
                                            _s_m = _s_m.iloc[:, 0]
                                        
                                        _ma25_m = pd.to_numeric(_s_m, errors='coerce').rolling(window=25).mean().iloc[-1]
                                        _price_m = _macro_t3["nikkei"]["price"]
                                        
                                        if pd.notna(_ma25_m) and _ma25_m > 0:
                                            n225_div_rate = ((_price_m / _ma25_m) - 1) * 100

                            if n225_div_rate <= -8.0:
                                score += 5
                                alerts.append(f"💎 【待伏好機】日経乖離率 {n225_div_rate:+.2f}%。パニック売り局面、反転期待値を最大加点。")
                            elif n225_div_rate <= -5.0:
                                score += 3
                                alerts.append(f"⚓ 【地合い支援】日経乖離率 {n225_div_rate:+.2f}%。安値圏、迎撃成功率を上方修正。")
                            elif n225_div_rate >= 8.0:
                                score -= 5
                                alerts.append(f"⚠️ 【地合い逆風】日経乖離率 {n225_div_rate:+.2f}%。市場全体が天井圏につき、偽の押し目に警戒。")
                            elif n225_div_rate >= 5.0:
                                score -= 3
                                alerts.append(f"🌐 【地合い警戒】日経乖離率 {n225_div_rate:+.2f}%。高値圏につき、慎重なエントリーを。")

                            if any(x in "".join(alerts) for x in ["三尊", "二重天井", "三山", "赤三先"]):
                                score -= 25
                                
                            reach_rate = 0
                            if h14 > 0:
                                reach_rate = (lc / h14) * 100
                                
                            if has_top_trap_t3:
                                rank = "圏外💀"
                                bg_c = "#ef5350"
                                score = 0
                                
                                if is_pre_gc_t3:
                                    alerts.append("🔴 【絶対排除】明日GC予測（初初動）のモメンタムを検知しましたが、酒田の天井シグナル（限界値）を同時検知。往復ビンタ回避のためS+資格を完全剥奪。")
                                else:
                                    alerts.append(f"🔴 【天井地雷】高値圏での致命的な天井転換サイン（三山・買い三空等）を検知。強襲を強制停止し、即時撤退・利確を推奨。")
                            else:
                                if is_pre_gc_t3:
                                    rank = "S+🎯"
                                    bg_c = "#ff5252"
                                    alerts.append("🎯 【強襲初動】明日大引けでゴールデンクロスを達成する、本物の超直前モメンタムを補足。")
                                else:
                                    if gc_days == 0 and not is_pre_gc_t3:
                                        rank = "圏外💀"
                                        bg_c = "#616161"
                                        score = 0
                                    elif score >= 80:
                                        rank = "S級強襲⚡"
                                        bg_c = "#1b5e20"
                                    elif score >= 60:
                                        rank = "A級強襲🔥"
                                        bg_c = "#2e7d32"
                                    elif score >= 40:
                                        rank = "B級強襲📈"
                                        bg_c = "#4caf50"
                                    else:
                                        rank = "圏外💀"
                                        bg_c = "#616161"

                        # 🤝 【原本100%同期】ボスの既存の美しいパッキング構造を1文字の狂いもなく完全無傷で保持
                        scope_results.append({
                            'code': target_key,
                            'name': c_name,
                            'lc': lc,
                            'h14': h14,
                            'l14': l14,
                            'ur': ur_v,
                            'bt_val': bt_val,
                            'atr_val': atr_v,
                            'rsi': rsi_v,
                            'rank': rank,
                            'bg': bg_c,
                            'score': score, # 🚨 修正: 算出されたscoreを格納
                            'reach_val': reach_rate,
                            'gc_days': gc_days,
                            'df_chart': df_mini, 
                            'per': res_per,
                            'pbr': res_pbr,
                            'roe': res_roe,
                            'mcap': res_mcap_str,
                            'source': "🛡️ 監視" if target_key in watch_in else "🚀 新規", 
                            'sector': c_sector,
                            'market': c_market, 
                            'alerts': alerts,
                            'sakata_patterns': s_results,
                            'error': False,
                            'is_deep': is_deep,
                            'events': raw_s.get('events', {}) if isinstance(raw_s, dict) else {},
                            'stealth_data': stealth_payload # 💎 潜伏用の拡張コンテナ
                        })
                                    
                    except Exception as e:
                        scope_results.append({
                            'code': target_key,
                            'name': f"銘柄 {target_key}",
                            'rank': '圏外💀',
                            'bg': '#616161',
                            'alerts': [f"⚠️ 演算エラー: {str(e)}"],
                            'error': True,
                            'df_chart': pd.DataFrame(),
                            'stealth_data': {},
                            'score': 0 # 🚨 修正: エラー時もキーが存在するように
                        })

                rank_order = {"S+": 5, "S": 4, "A": 3, "B": 2, "圏外": 0}
                for res in scope_results:
                    r_raw_str = res.get('rank', '圏外')
                    r_clean_str = re.sub(r'[^S\+ABC圏外]', '', r_raw_str)
                    res['r_val'] = rank_order.get(r_clean_str, 0)
                
                # ソート実行（ランク > スコア > 到達率）
                scope_results = sorted(
                    scope_results, 
                    key=lambda x: (x.get('r_val', 0), x.get('score', 0), x.get('reach_val', 0)), 
                    reverse=True
                )
                
                t_calc = time.time()
                st.write(f"✔️ 解析完了・色彩同期済み [{t_calc - t_fetch:.2f}秒]")
                status.update(label=f"🎯 全 {len(t_codes)} 銘柄のスキャン完遂", state="complete", expanded=False)

        # --- 🛡️ ユーティリティ関数のスコープ前方配置（NameErrorの完全根滅） ---
        def safe_int(x):
            try: return int(float(x)) if not pd.isna(x) else 0
            except Exception: return 0
        def safe_float(x):
            try: return float(x) if not pd.isna(x) else None
            except Exception: return None

        valid_results = [x for x in scope_results if not x.get('error')]
        if not is_stealth:
            valid_results = [x for x in valid_results if x.get('r_val', 0) >= 3]

        if valid_results:
            export_texts = []
            current_date_str = datetime.now().strftime("%Y/%m/%d") + " 大引け後"
            
            n225_close_val = "取得不可"
            n225_div_rate_val = "計算不可"
            
            # 🚨 修正: マクロ気象観測からの日経平均データ取得の確実化
            _macro_fallback = get_macro_weather()
            if _macro_fallback and "nikkei" in _macro_fallback:
                _ni_fb = _macro_fallback["nikkei"]
                _price_fb = _ni_fb.get("price")
                
                if _price_fb is not None:
                    n225_close_val = f"{int(_price_fb):,}円"
                    
                _df_fb = _ni_fb.get("df")
                if _df_fb is not None and not _df_fb.empty:
                    _df_fb_c = _df_fb.copy()
                    
                    # 🚨 モグラ駆逐パッチ：安全な動的カラム取得と強制1次元化
                    _close_col_fb = next((c for c in ['AdjC', 'Close', 'close', 'C', 'c'] if c in _df_fb_c.columns), None)
                    
                    if _close_col_fb:
                        _s_fb = _df_fb_c[_close_col_fb]
                        if isinstance(_s_fb, pd.DataFrame):
                            _s_fb = _s_fb.iloc[:, 0]
                        
                        _df_fb_c['MA25'] = pd.to_numeric(_s_fb, errors='coerce').rolling(window=25).mean()
                        
                        if 'MA25' in _df_fb_c.columns and not pd.isna(_df_fb_c['MA25'].iloc[-1]):
                            _ma25_fb = _df_fb_c['MA25'].iloc[-1]
                            if _price_fb is not None and _ma25_fb > 0:
                                _div_fb = ((_price_fb / _ma25_fb) - 1) * 100
                                n225_div_rate_val = f"{_div_fb:+.2f}%"
                            
                                if _div_fb >= 5.0:
                                    st.session_state['macro_alert'] = f"🌐【地合い警戒】日経乖離率 {_div_fb:+.2f}%。天井掴みに注意。"
                                elif _div_fb <= -5.0:
                                    st.session_state['macro_alert'] = f"🌐【地合いチャンス】日経乖離率 {_div_fb:+.2f}%。押し目買い好機。"
                                else:
                                    st.session_state['macro_alert'] = f"🌐【地合いニュートラル】日経乖離率 {_div_fb:+.2f}%。個別銘柄の動きを重視。"
            else:
                if 'n225_m_data' in locals() and n225_m_data and n225_m_data.get('close'):
                    n225_close_val = f"{int(safe_float(n225_m_data.get('close'))):,}円"
                if 'n225_div_rate' in locals() or 'n225_div_rate' in globals():
                    try: 
                        n225_div_rate_val = f"{n225_div_rate:+.2f}%"
                        if n225_div_rate >= 5.0:
                            st.session_state['macro_alert'] = f"🌐【地合い警戒】日経乖離率 {n225_div_rate:+.2f}%。天井掴みに注意。"
                        elif n225_div_rate <= -5.0:
                            st.session_state['macro_alert'] = f"🌐【地合いチャンス】日経乖離率 {n225_div_rate:+.2f}%。押し目買い好機。"
                        else:
                            st.session_state['macro_alert'] = f"🌐【地合いニュートラル】日経乖離率 {n225_div_rate:+.2f}%。個別銘柄の動きを重視。"
                    except: pass

            try:
                current_date_str = datetime.now(pytz.timezone('Asia/Tokyo')).strftime('%Y/%m/%d %H:%M')
            except Exception:
                pass

            for vr in scope_results:
                if vr.get('error'):
                    continue
                
                rank_str = str(vr.get('rank', ''))
                
                # 🚨 動的フィルター：待伏せ・強襲モードは S/A級「以外」ならスキップ（＝潜伏は全件通過する）
                if not is_stealth and not ("S" in rank_str or "A" in rank_str):
                    continue

                clean_alerts = []
                for al in vr.get('alerts', []):
                    if isinstance(al, str):
                        clean_text = re.sub(r'<[^>]*>', '', al).strip()
                        if clean_text:
                            clean_alerts.append(clean_text)
                alerts_str = "、".join(clean_alerts) if clean_alerts else "特記事項なし"
                
                v_roe = safe_float(vr.get('roe'))
                v_per = safe_float(vr.get('per'))
                v_pbr = safe_float(vr.get('pbr'))
                g_count = 0
                if v_roe is not None and v_roe >= 10.0: g_count += 1
                if v_per is not None and v_per <= 20.0: g_count += 1
                if v_pbr is not None and v_pbr <= 5.0: g_count += 1
                fund_status = f"{g_count}/3グリーン"
                
                v_df_chart = vr.get('df_chart', pd.DataFrame())
                v_ma25 = None
                if not v_df_chart.empty:
                    last_row = v_df_chart.iloc[-1]
                    for k in ['MA25', 'ma25', 'MA_25', 'ma_25', 'SMA25', 'sma25']:
                        if k in last_row and pd.notna(last_row[k]):
                            v_ma25 = safe_float(last_row[k])
                            break
                    if v_ma25 is None and 'AdjC' in v_df_chart.columns and len(v_df_chart) >= 25:
                        try:
                            v_ma25 = safe_float(v_df_chart['AdjC'].rolling(25).mean().iloc[-1])
                        except:
                            v_ma25 = None
                ma25_str = f"{int(v_ma25):,}円" if v_ma25 is not None else "計算期間不足"
                
                if is_ambush:
                    bt_label = "61.8%押し" if vr.get('is_deep') else f"{st.session_state.push_r}%押し"
                    bt_target_str = f"{bt_label} {int(vr.get('bt_val', 0)):,}円"
                elif is_stealth: # 💎 潜伏モード用のテキスト出力
                    st_data = vr.get('stealth_data', {})
                    sl_val = st_data.get('stop_loss', 0)
                    tp_val = st_data.get('take_profit', 0)
                    bt_target_str = f"買トリガー(突破) {int(vr.get('bt_val', 0)):,}円 / 損切線 {sl_val:,}円 / 目標TP {tp_val:,}円"
                else:
                    stop_p = int(vr.get('bt_val', 0) + ((safe_float(vr.get('atr_val')) or 0.0) * 0.1))
                    bt_target_str = f"トリガー目安 {int(vr.get('bt_val', 0)):,}円 / 逆指値目安 {stop_p:,}円"

                # ※テンプレート代入前に、以下の変数を取得・フォーマットしておく必要があります
                # tactics_mode = "待伏" # または "強襲", "潜伏" など現在のモードを取得
                # market_cap_str = vr.get('market_cap', 'N/A') # 時価総額の取得（必要に応じて億単位などでフォーマット）

                text_template = f"""■銘柄基本情報
・銘柄コード：{vr.get('code')}
・データ抽出日時：{current_date_str}
■マクロ環境（地合い）
・日経平均終値：{n225_close_val}
・日経平均MA25乖離率：{n225_div_rate_val}
■システム判定ステータス
・戦術モード：{tactics_mode}
・総合判定：{vr.get('rank')}
・点灯シグナル・アラート：{alerts_str}
• テクニカルスコア：{vr.get('score', 0)} pts
・RSI：{safe_float(vr.get('rsi', 50)):.1f}%
・ファンダメンタルズ判定：{fund_status} / 時価総額：{market_cap_str}
■絶対価格データ（確値）
・最新終値：{int(vr.get('lc', 0)):,}円
・MA25（25日移動平均線）：{ma25_str}
・直近高値（スイングハイ）：{int(vr.get('h14', 0)):,}円
・起点安値（スイングロウ）：{int(vr.get('l14', 0)):,}円
■ボラティリティ・ターゲットデータ
・1ATR（14日）：{int(safe_float(vr.get('atr_val', 0)) or 0):,}円
・システム算出 買目標値：{bt_target_str}"""

                export_texts.append(text_template)
            
                final_copypaste_text = "\n\n========================================\n\n".join(export_texts)
            
            st.markdown("<div style='margin-top:1rem;'></div>", unsafe_allow_html=True)
            
            expander_title = "📋 【一括コピー】作戦参謀への分析依頼データ"
            expander_title += "（S/A級限定抽出）" if not is_stealth else "（全件抽出）"
            expander_desc = "※右上のアイコンをクリックすることで、S級およびA級判定のみに自動トリアージされたスキャン結果を一撃でコピーできます。" if not is_stealth else "※右上のアイコンをクリックすることで、スキャン結果を全件一撃でコピーできます。"
            
            with st.expander(expander_title, expanded=True):
                st.markdown(f"<p style='font-size:12px; color:#888; margin-bottom:0.5rem;'>{expander_desc}</p>", unsafe_allow_html=True)
                if final_copypaste_text.strip():
                    st.code(final_copypaste_text, language="text")
                else:
                    st.info("※現在表示できるテキストデータがありません。（待伏モードで該当銘柄なし等）")

        for index, r in enumerate(scope_results):
            st.divider()
            if r.get('error'):
                st.error(f"銘柄 {r['code']}: {', '.join(r['alerts'])}")
                continue
            
            has_chart = not (r.get('df_chart') is None or r['df_chart'].empty)

            event_badges = ""
            for alert in r.get('alerts', []):
                if "残り" in alert:
                    color = "#ef5350" if any(x in alert for x in ["決算", "地雷", "警戒"]) else "#ffca28"
                    label = alert.split("】")[1] if "】" in alert else alert
                    event_badges += f'<span style="background:{color}; color:white; padding:2px 8px; border-radius:4px; font-size:12px; margin-left:8px; font-weight:bold;">{label}</span>'

            source_color = "#42a5f5" if "監視" in r['source'] else "#ffa726"
            
            m_lower = str(r['market']).lower()
            if 'プライム' in m_lower or '一部' in m_lower:
                m_badge = '<span style="background-color: #1a237e; color: #ffffff; padding: 0.2rem 0.6rem; border-radius: 4px; font-size: 11px; font-weight: bold; border: 1px solid #303f9f;">🏢 プライム/大型</span>'
            elif 'グロース' in m_lower or 'マザーズ' in m_lower:
                m_badge = '<span style="background-color: #1b5e20; color: #ffffff; padding: 0.2rem 0.6rem; border-radius: 4px; font-size: 11px; font-weight: bold; border: 1px solid #2e7d32;">🚀 グロース/新興</span>'
            elif 'スタンダード' in m_lower or '二部' in m_lower:
                m_badge = '<span style="background-color: #ef6c00; color: #ffffff; padding: 0.2rem 0.6rem; border-radius: 4px; font-size: 11px; font-weight: bold; border: 1px solid #f57c00;">⚖️ スタンダード/中堅</span>'
            else:
                m_badge = f'<span style="background-color: #455a64; color: #ffffff; padding: 0.2rem 0.6rem; border-radius: 4px; font-size: 11px; font-weight: bold; border: 1px solid #546e7a;">{r["market"]}</span>'
            
            gc_badge = ""
            if r.get('gc_days', 0) > 0:
                gc_badge = f"<span style='background-color: #1b5e20; color: #ffffff; padding: 2px 10px; border-radius: 4px; font-size: 13px; font-weight: bold; margin-left: 10px; border: 1px solid #81c784; box-shadow: 0 2px 4px rgba(0,0,0,0.3);'>⚡ GC発動 {r.get('gc_days')}日目</span>"
            elif "S+" in str(r.get('rank', '')):
                gc_badge = f"<span style='background-color: #ff5252; color: #ffffff; padding: 2px 10px; border-radius: 4px; font-size: 13px; font-weight: bold; margin-left: 10px; border: 1px solid #ff8a80; box-shadow: 0 2px 4px rgba(0,0,0,0.3);'>🎯 明日GC見込(激熱)</span>"
            elif "圏外💀" in str(r.get('rank', '')) and any(x in "".join(r.get('alerts', [])) for x in ["絶対排除"]):
                gc_badge = f"<span style='background-color: #ef5350; color: #ffffff; padding: 2px 10px; border-radius: 4px; font-size: 13px; font-weight: bold; margin-left: 10px; border: 1px solid #b71c1c; box-shadow: 0 2px 4px rgba(0,0,0,0.3);'>⚠️ 天井地雷検知</span>"

            st.markdown(f"""
            <div style="margin-bottom: 0.8rem;">
            <h3 style="font-size: clamp(18px, 5vw, 28px); font-weight: bold; margin: 0 0 0.3rem 0;">
            <span style="background:{source_color}; color:white; padding:2px 6px; border-radius:4px; font-size:12px; vertical-align:middle; box-shadow: 0 1px 2px rgba(0,0,0,0.2);">{r['source']}</span> ({r['code']}) {r['name']} {event_badges}</h3>
            <div style="display: flex; flex-wrap: wrap; gap: 8px; align-items: center;">
            <span style='background:{r['bg']}; color:white; padding:2px 10px; border-radius:4px; font-weight:bold; box-shadow: 0 2px 4px rgba(0,0,0,0.2);'>🎯 {r['rank']}</span>
            {m_badge}{gc_badge}
            <span style="background-color: #607d8b; color: #ffffff; padding: 0.1rem 0.6rem; border-radius: 4px; font-size: 12px; border: 1px solid #78909c;">🏭 {r['sector']}</span>
            <span style="background: rgba(38,166,154,0.05); border: 1px solid #26a69a; color: #26a69a; padding: 0.1rem 0.6rem; border-radius: 4px; font-size: 12px; font-weight: bold;">RSI: {safe_float(r['rsi']) or 0:.1f}%</span>
            </div></div>""", unsafe_allow_html=True)
            
            if r.get('alerts'):
                for alert in r['alerts']:
                    if any(m in alert for m in ["🟢", "⚡", "🔥", "💎", "赤三兵", "二重底", "たくり", "明星", "狙撃", "売り三空", "陰の極み", "好機", "支援"]):
                        st.success(alert)
                    elif any(m in alert for m in ["🔴", "💀", "💣", "⚠️", "黒三兵", "三尊", "三山", "二重天井", "赤三先", "買い三空", "撤退", "罠", "停止", "逆風", "絶対排除"]):
                        st.error(alert)
                    else:
                        st.warning(alert)

            sc_left, sc_mid, sc_right = st.columns([2.5, 3.5, 5.0])
            
            with sc_left:
                def safe_int_local(x):
                    try: return int(float(x)) if not pd.isna(x) else 0
                    except Exception: return 0
                
                h14_v = safe_int_local(r['h14'])
                l14_v = safe_int_local(r['l14'])
                ur_v = safe_int_local(r['ur'])
                lc_v = safe_int_local(r['lc'])
                atr_v_val = safe_float(r['atr_val']) or 0.0
                
                c1, c2 = st.columns(2); c1.metric("直近高値", f"{h14_v:,}円"); c2.metric("起点安値", f"{l14_v:,}円")
                c3, c4 = st.columns(2); c3.metric("波高(14d)", f"{ur_v:,}円"); c4.metric("最新終値", f"{lc_v:,}円")
                
                st.metric("🌪️ 1ATR", f"{safe_int_local(atr_v_val):,}円", f"ボラ: {(atr_v_val/lc_v*100) if lc_v>0 else 0:.1f}%", delta_color="off")

            with sc_mid:
                roe_v = safe_float(r['roe'])
                per_v = safe_float(r['per'])
                pbr_v = safe_float(r['pbr'])
                
                roe_s, roe_c = (f"{roe_v:.1f}%", "#26a69a") if roe_v is not None and roe_v >= 10.0 else (f"{roe_v:.1f}%" if roe_v is not None else "-", "#ef5350")
                per_s, per_c = (f"{per_v:.1f}倍", "#26a69a") if per_v is not None and per_v <= 20.0 else (f"{per_v:.1f}倍" if per_v is not None else "-", "#ef5350")
                pbr_s, pbr_c = (f"{pbr_v:.2f}倍", "#26a69a") if pbr_v is not None and pbr_v <= 5.0 else (f"{pbr_v:.2f}倍" if pbr_v is not None else "-", "#ef5350")
                
                if is_ambush:
                    box_title = "💎 深海買値(61.8%)" if r.get('is_deep') else "🎯 買値目標"
                    box_val = f"{safe_int(r['bt_val']):,}円"
                elif is_stealth: # 💎 潜伏モード用のメトリクス表示
                    st_data = r.get('stealth_data', {})
                    sl_val = st_data.get('stop_loss', 0)
                    tp_val = st_data.get('take_profit', 0)
                    box_title = f"🎯 買目安 / 🛡️ SL / 💰 TP"
                    box_val = f"<span style='font-size:1.1rem;'>買</span> {safe_int(r['bt_val']):,} <span style='font-size:1.1rem; color:#ef5350;'>防</span> {sl_val:,} <span style='font-size:1.1rem; color:#26a69a;'>利</span> {tp_val:,}"
                else:
                    box_title = "🎯 トリガー / 逆指値目安"
                    stop_p = safe_int(r['bt_val'] + (atr_v_val * 0.1))
                    box_val = f"{safe_int(r['bt_val']):,}円 / {stop_p:,}円"

                e_html = ""
                c_code_4 = str(r['code'])[:4] 

                e_alerts = check_event_mines(c_code_4, r.get('events', {}))

                for a in e_alerts:
                    b_col = "#ef5350"
                    e_html += f'<span style="background:{b_col}; color:white; padding:2px 6px; border-radius:4px; font-size:10px; margin-left:6px; font-weight:bold; vertical-align:middle; box-shadow:0 1px 2px rgba(0,0,0,0.3);">{a}</span>'

                st.markdown(f"""
                <div style='background:rgba(255,215,0,0.05); padding:1.2rem; border-radius:10px; border:1px solid rgba(255,215,0,0.3); text-align:center; box-shadow: inset 0 0 15px rgba(255,215,0,0.1);'>
                <div style='font-size:14px; color: #eee; margin-bottom: 0.4rem;'>{box_title}{e_html}</div>
                <div style='font-size: clamp(1.4rem, 4vw, 2.2rem); font-weight:bold; color:#FFD700; margin: 0.2rem 0; text-shadow: 0 2px 4px rgba(0,0,0,0.5);'>{box_val}</div>
                <div style='display:flex; justify-content:space-around; margin-top:10px; border-top:1px dashed rgba(255,255,255,0.2); padding-top:10px;'>
                <div style='flex:1;'><div style='color:#888; font-size:10px;'>PER</div><div style='color:{per_c}; font-weight:bold; font-size:1.1rem;'>{per_s}</div></div>
                <div style='flex:1;'><div style='color:#888; font-size:10px;'>PBR</div><div style='color:{pbr_c}; font-weight:bold; font-size:1.1rem;'>{pbr_s}</div></div>
                <div style='flex:1;'><div style='color:#888; font-size:10px;'>ROE</div><div style='color:{roe_c}; font-weight:bold; font-size:1.1rem;'>{roe_s}</div></div>
                </div>
                <div style='margin-top:8px; border-top:1px solid rgba(255,255,255,0.05); padding-top:5px;'>
                <span style='color:#888; font-size:11px;'>時価総額: </span><span style='color:#fff; font-size:11px; font-weight:bold;'>{r.get('mcap', '-')}</span>
                </div></div>""", unsafe_allow_html=True)

            with sc_right:
                c_target = safe_int(r['bt_val'])
                rec_tps = [2.0, 3.0] if any(mark in r['rank'] for mark in ["⚡", "🔥", "S"]) else [0.5, 1.0]
                
                html_matrix = f"<div style='background:rgba(255,255,255,0.05); padding:1.2rem; border-radius:8px; border-left:5px solid #FFD700; min-height: 125px;'><div style='font-size:14px; color:#aaa; margin-bottom:12px; border-bottom:1px solid #444; padding-bottom:4px;'>📊 動的ATRマトリクス (基準:{c_target:,}円)</div><div style='display:flex; gap:30px;'><div style='flex:1;'><div style='color:#26a69a; border-bottom:2px solid #26a69a; margin-bottom:8px;'>【利確目安】</div>"
                
                for m in [0.5, 1.0, 2.0, 3.0]:
                    val = int(c_target + (atr_v_val * m))
                    pct_v = ((val / c_target) - 1) * 100 if c_target > 0 else 0
                    style = "background:rgba(38,166,154,0.15); border:1px solid #26a69a; border-radius:4px; padding:2px 6px;" if m in rec_tps else "padding:3px 6px;"
                    label = "<span style='font-size:10px; background:#26a69a; color:white; padding:1px 4px; border-radius:2px; margin-left:2px;'>推奨</span>" if m in rec_tps else ""
                    html_matrix += f"<div style='display:flex; justify-content:space-between; margin-bottom:4px; {style}'><span>+{m}ATR <span style='font-size:10px; color:#888;'>({pct_v:+.1f}%)</span>{label}</span><b style='font-size:1.1rem;'>{val:,}</b></div>"
                
                html_matrix += "</div><div style='flex:1;'><div style='color:#ef5350; border-bottom:2px solid #ef5350; margin-bottom:8px;'>【防衛目安】</div>"
                
                for m in [0.5, 1.0, 2.0]:
                    val = int(c_target - (atr_v_val * m))
                    pct_v = (1 - (val / c_target)) * 100 if c_target > 0 else 0
                    style = "background:rgba(239,83,80,0.15); border:1px solid #ef5350; border-radius:4px; padding:2px 6px;" if m == 1.0 else "padding:3px 6px;"
                    label = "<span style='font-size:10px; background:#ef5350; color:white; padding:1px 4px; border-radius:2px; margin-left:2px;'>鉄則</span>" if m == 1.0 else ""
                    html_matrix += f"<div style='display:flex; justify-content:space-between; margin-bottom:4px; {style}'><span>-{m}ATR <span style='font-size:10px; color:#888;'>({pct_v:.1f}%)</span>{label}</span><b style='font-size:1.1rem;'>{val:,}</b></div>"
                
                st.markdown(html_matrix + "</div></div></div>", unsafe_allow_html=True)

            if has_chart:
                try:
                    st.markdown("<div style='margin-top:1.2rem;'></div>", unsafe_allow_html=True)
                    st.markdown(render_technical_radar(r['df_chart'], c_target, st.session_state.bt_tp), unsafe_allow_html=True)
                    st.markdown("---")
                    u_key = f"t3_chart_final_{r['code']}_{index}_{cache_key}_{int(time.time()*1000)}"
                    draw_chart(r['df_chart'], c_target, sakata=r.get('sakata_patterns', []), chart_key=u_key)
                    st.markdown("<div style='margin-bottom:1.5rem;'></div>", unsafe_allow_html=True)
                except Exception as e:
                    st.error(f"⚠️ チャート描画物理エラー: {str(e)}")
                    
# --- 9. タブコンテンツ (TAB5: 戦術シミュレータ) ---
with tab5:
    st.markdown('<h3 style="font-size: clamp(14px, 4.5vw, 24px); margin-bottom: 1rem;">⚙️ 戦術シミュレータ (2年間のバックテスト)</h3>', unsafe_allow_html=True)
    
    # --- 🛡️ 状態初期化・物理ロック回路 ---
    tab4_defaults = {
        "bt_mode_sim_v2": "🌐 【待伏】鉄の掟 (押し目狙撃)",
        "sim_tp_val": 10, "sim_sl_val": 8, "sim_limit_d_val": 4, "sim_sell_d_val": 10,
        "sim_push_r_val": 50.0,
        "sim_pass_req_val": 7, 
        "sim_rsi_lim_ambush_val": 45,
        "sim_rsi_lim_assault_val": 70, 
        "sim_time_risk_val": 5,
        "sim_stealth_vol_val": 10,
        "sim_rsi_lim_stealth_val": 65
    }

    for k, v in tab4_defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v

    current_mode = st.session_state.bt_mode_sim_v2
    if "prev_mode_for_sync" not in st.session_state:
        st.session_state.prev_mode_for_sync = current_mode

    # 🚨 兵站補給パッチ：モード切り替えを検知した瞬間、対象モードの固有デフォルト値を強制再装填する
    if st.session_state.prev_mode_for_sync != current_mode:
        if "待伏" in current_mode:
            st.session_state.sim_limit_d_val = 4
            st.session_state.sim_sell_d_val = 10
            st.session_state.sim_push_r_val = 50.0
            st.session_state.sim_pass_req_val = 7
            st.session_state.sim_rsi_lim_ambush_val = 45
        elif "潜伏" in current_mode:
            st.session_state.sim_limit_d_val = 5
            st.session_state.sim_sell_d_val = 15
            st.session_state.sim_stealth_vol_val = 10
            st.session_state.sim_rsi_lim_stealth_val = 65
        else: # 強襲
            st.session_state.sim_limit_d_val = 3
            st.session_state.sim_sell_d_val = 5
            st.session_state.sim_rsi_lim_assault_val = 70
            st.session_state.sim_time_risk_val = 5
        st.session_state.prev_mode_for_sync = current_mode
        try: save_settings()
        except: pass

    current_sidebar_push = st.session_state.get("push_r", 50.0)
    if "last_known_sidebar_push" not in st.session_state:
        st.session_state.last_known_sidebar_push = current_sidebar_push

    if st.session_state.last_known_sidebar_push != current_sidebar_push:
        st.session_state.sim_push_r_val = current_sidebar_push
        st.session_state.last_known_sidebar_push = current_sidebar_push
        try: save_settings()
        except: pass

    col_b1, col_b2 = st.columns([1, 1.8])
    T4_FILE = f"saved_t4_codes_{user_id}.txt"
    default_t4 = "7839\n6614"
    if os.path.exists(T4_FILE):
        try:
            with open(T4_FILE, "r", encoding="utf-8") as f: default_t4 = f.read()
        except: pass

    with col_b1: 
        st.markdown("🔍 **検証戦術**")
        st.radio("戦術モード", [
            "🌐 【待伏】鉄の掟 (押し目狙撃)", 
            "⚡ 【強襲】GCブレイクアウト (順張り)", 
            "💎 【潜伏】大爆発前夜ハント (ブレイク狙撃)"
        ], key="bt_mode_sim_v2")
        bt_c_in = st.text_area("銘柄コード", value=default_t4, height=100, key="bt_codes_sim_v2")
        run_bt = st.button("🔥 仮想実弾テスト実行", use_container_width=True)
        optimize_bt = st.button("🚀 戦術の黄金比率を抽出 (最適化)", use_container_width=True)
        
    with col_b2:
        st.markdown("#### ⚙️ 戦術パラメーター（演習用チューニング）")
        st.info("※ 戦術切替時、買い・売り期限および各固有値は自動で最適デフォルト値に同期されます。")
        cp1, cp2, cp3, cp4 = st.columns(4)
        
        # 🚨 各入力ボックスに value 引数を明示し、セッション値の揮発を完全に防御
        cp1.number_input("🎯 利確目標(%)", min_value=1, value=int(st.session_state.get('sim_tp_val', 10)), key="sim_tp_val")
        cp2.number_input("🛡️ 損切目安(%)", min_value=1, value=int(st.session_state.get('sim_sl_val', 8)), key="sim_sl_val")
        cp3.number_input("⏳ 買い期限(日)", min_value=1, value=int(st.session_state.get('sim_limit_d_val', 4)), key="sim_limit_d_val")
        cp4.number_input("⏳ 売り期限(日)", min_value=1, value=int(st.session_state.get('sim_sell_d_val', 10)), key="sim_sell_d_val")
        
        st.divider()
        if "待伏" in st.session_state.bt_mode_sim_v2:
            st.markdown("##### 🌐 【待伏}シミュレータ固有設定")
            ct1, ct2, ct3 = st.columns(3)
            ct1.number_input("📉 押し目待ち(%)", min_value=0.0, max_value=100.0, value=float(st.session_state.get('sim_push_r_val', 50.0)), step=0.1, format="%.1f", key="sim_push_r_val")
            ct2.number_input("掟クリア要求数", min_value=1, max_value=9, value=int(st.session_state.get('sim_pass_req_val', 7)), step=1, key="sim_pass_req_val")
            ct3.number_input("RSI上限 (過熱感)", min_value=1, max_value=100, value=int(st.session_state.get('sim_rsi_lim_ambush_val', 45)), step=5, key="sim_rsi_lim_ambush_val")
        elif "潜伏" in st.session_state.bt_mode_sim_v2:
            st.markdown("##### 💎 【潜伏】シミュレータ固有設定")
            ct1, ct2 = st.columns(2)
            ct1.number_input("ボラティリティ収縮率上限(%)", min_value=1, max_value=100, value=int(st.session_state.get('sim_stealth_vol_val', 10)), step=1, key="sim_stealth_vol_val")
            ct2.number_input("RSI上限 (過熱感)", min_value=1, max_value=100, value=int(st.session_state.get('sim_rsi_lim_stealth_val', 65)), step=5, key="sim_rsi_lim_stealth_val")
        else:
            st.markdown("##### ⚡ 【強襲】シミュレータ固有設定")
            ct1, ct2 = st.columns(2)
            ct1.number_input("RSI上限 (過熱感)", min_value=1, max_value=100, value=int(st.session_state.get('sim_rsi_lim_assault_val', 70)), step=5, key="sim_rsi_lim_assault_val")
            ct2.number_input("時間リスク上限（到達予想日数）", min_value=1, max_value=100, value=int(st.session_state.get('sim_time_risk_val', 5)), step=1, key="sim_time_risk_val")

    if (run_bt or optimize_bt) and bt_c_in:
        with open(T4_FILE, "w", encoding="utf-8") as f: f.write(bt_c_in)
        t_codes = list(dict.fromkeys([c.upper() for c in re.findall(r'(?<![a-zA-Z0-9])[a-zA-Z0-9]{4}(?![a-zA-Z0-9])', bt_c_in)]))
        
        if not t_codes: 
            st.warning("有効なコードが見つかりません。")
        else:
            sim_tp = float(st.session_state.sim_tp_val)
            sim_sl_i = float(st.session_state.sim_sl_val)
            sim_limit_d = int(st.session_state.sim_limit_d_val)
            sim_sell_d = int(st.session_state.sim_sell_d_val)
            sim_push_r = float(st.session_state.sim_push_r_val)

            # 🚨 3モードの判定
            is_ambush = "待伏" in st.session_state.bt_mode_sim_v2
            is_stealth = "潜伏" in st.session_state.bt_mode_sim_v2
            
            if is_ambush:
                sim_pass_req = int(st.session_state.sim_pass_req_val)
                sim_rsi_lim_ambush = int(st.session_state.sim_rsi_lim_ambush_val)
                p1_range = range(25, 66, 5) if optimize_bt else [sim_push_r]
                p2_range = range(5, 10, 1) if optimize_bt else [sim_pass_req]
                p1_name, p2_name = "Push率(%)", "要求Score"
            # 🚨 潜伏モード時の最適化範囲設定
            elif is_stealth:
                sim_stealth_vol = int(st.session_state.sim_stealth_vol_val)
                sim_rsi_lim_stealth = int(st.session_state.sim_rsi_lim_stealth_val)
                p1_range = range(5, 20, 2) if optimize_bt else [sim_stealth_vol]
                p2_range = range(3, 16, 1) if optimize_bt else [int(sim_tp)]
                p1_name, p2_name = "収縮率上限(%)", "利確目標(%)"
            else:
                sim_rsi_lim_assault = int(st.session_state.sim_rsi_lim_assault_val)
                sim_time_risk = int(st.session_state.sim_time_risk_val)
                p1_range = range(30, 85, 5) if optimize_bt else [sim_rsi_lim_assault]
                p2_range = range(3, 16, 1) if optimize_bt else [int(sim_tp)]
                p1_name, p2_name = "RSI上限(%)", "利確目標(%)"
            
            with st.spinner("データをプリロード中（メモリ極限圧縮＆完全クリーンアップ中）..."):
                preloaded_data = {}
                debug_logs = [] 

                for c in t_codes:
                    api_code = c if len(c) >= 5 else c + "0"
                    try: 
                        raw = get_single_data(api_code, 2)
                        if not raw: continue
                        bars_data = raw.get('bars') or raw.get('daily_quotes')
                        if not bars_data: continue

                        df = pd.DataFrame(bars_data)
                        if df.empty: continue

                        # 1. マルチインデックスの破壊（yfinance対策）
                        if isinstance(df.columns, pd.MultiIndex):
                            df.columns = df.columns.get_level_values(0)
                        df.columns = [str(col[0]) if isinstance(col, (tuple, list)) else str(col) for col in df.columns]

                        # 2. カラム名の正規化とマッピング
                        norm_cols = {col: str(col).lower().replace(" ", "").replace("_", "") for col in df.columns}
                        df = df.rename(columns=norm_cols)

                        col_map = {
                            'date': 'Date', 'o': 'Open', 'open': 'Open', 'h': 'High', 'high': 'High', 
                            'l': 'Low', 'low': 'Low', 'c': 'Close', 'close': 'Close', 'vo': 'Volume', 'volume': 'Volume',
                            'adjo': 'AdjO', 'adjustmentopen': 'AdjO', 'adjh': 'AdjH', 'adjustmenthigh': 'AdjH',
                            'adjl': 'AdjL', 'adjustmentlow': 'AdjL', 'adjc': 'AdjC', 'adjustmentclose': 'AdjC', 'adjclose': 'AdjC',
                            'adjvo': 'AdjVo', 'adjustmentvolume': 'AdjVo'
                        }
                        df = df.rename(columns=col_map)

                        # 3. 重複カラムの完全排除
                        df = df.loc[:, ~df.columns.duplicated(keep='first')]

                        # 4. 🚨【最重要・メモリ保護】文字型を数値型(float32)に強制キャストし、計算エンジンの爆発を防ぐ！
                        # float64ではなく、司令官の設計思想である float32 を厳守します。
                        numeric_cols = ['Open', 'High', 'Low', 'Close', 'Volume', 'AdjO', 'AdjH', 'AdjL', 'AdjC', 'AdjVo']
                        for col in numeric_cols:
                            if col in df.columns:
                                df[col] = pd.to_numeric(df[col], errors='coerce').astype('float32')

                        if 'Close' not in df.columns and 'AdjC' not in df.columns:
                            debug_logs.append(f"[{c}] ❌ 株価カラム(Close/AdjC)が存在しません")
                            continue

                        # 5. 司令官の浄化処理を実行
                        clean_data = clean_df(df)
                        
                        # 万が一の重複排除（保険）
                        clean_data = clean_data.loc[:, ~clean_data.columns.duplicated(keep='first')]

                        # 🚨 無意味になった if 'AdjC' not in ... の冗長な変換ブロックを完全焼却！
                        
                        # 必須カラムが揃っているかどうかの最終チェックだけ残す
                        target_cols = ['AdjO', 'AdjH', 'AdjL', 'AdjC']
                        if not all(col in clean_data.columns for col in target_cols):
                            debug_logs.append(f"[{c}] ❌ 必須株価データが欠損しています")
                            continue

                        clean_data = clean_data.dropna(subset=target_cols).reset_index(drop=True)

                        # 6. 🚨【最終防壁】クレンジング後も念のため float32 を再保証
                        for col in target_cols:
                            clean_data[col] = clean_data[col].astype('float32')
                        
                        if len(clean_data) < 35: 
                            debug_logs.append(f"[{c}] ❌ 稼働日数が不足しています（現在 {len(clean_data)}日）")
                            continue

                        # 7. 計算エンジンへ投入（float32の純粋な1次元データのみが到達）
                        processed_df = calc_vector_indicators(clean_data)
                        
                        if processed_df is not None and isinstance(processed_df, pd.DataFrame):
                            preloaded_data[c] = processed_df
                        else:
                            debug_logs.append(f"[{c}] ❌ テクニカル計算エラー")
                            
                    except Exception as e: 
                        debug_logs.append(f"[{c}] ❌ 内部処理中に致命的エラー: {e}")
                        continue
            # ====================================================================

            # 🚨 物理修正箇所：データがゼロだった場合、「なぜゼロになったのか」を大々的に画面に表示する
            if not preloaded_data:
                st.error("🚨 兵站エラー：解析可能なデータが取得できませんでした。以下のデバッグレポートを確認してください。")
                with st.expander("🛠️ 【参謀用デバッグレポート】 なぜデータが棄却されたのか？", expanded=True):
                    if not debug_logs:
                        st.warning("⚠️ 銘柄コード欄から有効なコードが抽出されていません。（入力形式を確認してください）")
                    else:
                        for log in debug_logs:
                            st.info(log)
            else:
                # 🚨 全体を try-except で囲み、エラー発生時の完全クラッシュを防ぐ防波堤
                try:
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
                                            
                                            if rsi_prev > sim_rsi_lim_ambush: continue

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
                                                    
                                        # 🚨 潜伏モードのバックテスト判定ロジック
                                        elif is_stealth:
                                            rsi_prev = prev.get('RSI', 50)
                                            volatility_pct = ((h14 - l14) / l14) * 100
                                            
                                            # 指定したボラティリティ収縮率(%)以下かつRSI上限以下の場合のみ狙撃
                                            if volatility_pct <= t_p1 and rsi_prev <= sim_rsi_lim_stealth:
                                                trigger_price = h14 + (atr_prev * 0.1) # 14日高値を僅かに超えたらブレイク判定
                                                if td['AdjH'] >= trigger_price:
                                                    exec_limit = trigger_price + (atr_prev * 0.5)
                                                    exec_p = min(max(td['AdjO'], trigger_price), exec_limit)
                                                    pos = {'b_i': i, 'b_d': td['Date'], 'b_p': exec_p, 'entry_atr': atr_prev, 'trigger': trigger_price}
                                        
                                        else: # 強襲モード
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
                                                    
                                    else: # ポジション保有中の決済ロジック
                                        bp = pos['b_p']; held = i - pos['b_i']; sp = 0
                                        current_tp = sim_tp if is_ambush else t_p2 # 強襲・潜伏の場合は t_p2 が利確目標として機能する
                                        e_atr = pos.get('entry_atr', prev.get('ATR', 0))
                                        t_price = pos.get('trigger', bp)
                                        
                                        sl_val = t_price - (e_atr * 1.0)
                                        tp_val = bp * (1 + (current_tp / 100.0))
                                        
                                        if td['AdjL'] <= sl_val: sp = min(td['AdjO'], sl_val)
                                        elif td['AdjH'] >= tp_val: sp = max(td['AdjO'], tp_val)
                                        elif held >= sim_sell_d: sp = td['AdjC']
                                        
                                        if sp > 0:
                                            sp = round(sp, 1); p_pct = round(((sp / bp) - 1) * 100, 2)
                                            p_amt = int((sp - bp) * st.session_state.get('bt_lot', 100))
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
                        c1.metric(f"推奨 {p1_name}", f"{int(best[p1_name])} " + ("%" if is_ambush or is_stealth else ""))
                        c2.metric(f"推奨 {p2_name}", f"{int(best[p2_name])} " + ("点" if is_ambush else "%"))
                        c3.metric("期待勝率", f"{round(best['勝率']*100, 1)} %")
                        st.write("#### 📊 パラメーター別収益ヒートマップ（上位10選）")
                        st.dataframe(opt_df.head(10).style.format({'総合利益(円)': '{:,}', '勝率': '{:.2%}'}), use_container_width=True, hide_index=True)
                        
                        if is_ambush: 
                            st.info(f"💡 【推奨戦術】高値から {int(best[p1_name])}% の押し目位置に指値を展開し、掟スコア {int(best[p2_name])}点 以上で迎撃するのが最も期待値が高いと解析されます。")
                        elif is_stealth:
                            st.info(f"💡 【推奨戦術】ボラティリティ収縮率 {int(best[p1_name])}% 以下の煮詰まり銘柄に対し、利確目標 {int(best[p2_name])}% でブレイクアウトを狙うのが最も期待値が高いと解析されます。")
                        else:
                            st.info(f"💡 【推奨戦術】RSI上限 {int(best[p1_name])}% 以下で、利確目標 {int(best[p2_name])}% の強襲ブレイクアウトが最も期待値が高いと解析されます。")

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
                
                #except Exception as e:
                    # 🚨 解析・演算中に想定外のエラーが起きた場合の防波堤
                    #st.error(f"🚨 兵站エラー：データに異常があるか、シミュレーション演算中にエラーが発生しました。詳細: {e}")

                except Exception as e: 
                        import traceback
                        st.error(f"🚨 エラー発生座標特定ログ:\n\n" + traceback.format_exc())
                        st.stop() # breakの代わりに、確実にシステムを一時停止するコマンドを使用

# --- 10. タブコンテンツ (TAB6: 交戦モニター) ---
with tab6:
    st.markdown('<h3 style="font-size: clamp(14px, 4.5vw, 24px); margin-bottom: 1rem;">📡 交戦モニター (全軍生存圏レーダー)</h3>', unsafe_allow_html=True)
    st.caption("※ 銘柄コードと株数を入力し、確定（Enter）後に『🔄 全軍同期』を押してください。")

    components.html(
        """
        <script>
        const doc = window.parent.document;
        const sniperEntryPatch = () => {
            const editors = doc.querySelectorAll('div[data-testid="stDataEditor"]');
            editors.forEach(editor => {
                if (editor.dataset.sniperPatched === 'true') return;
                
                editor.addEventListener('keydown', (e) => {
                    if (e.key === 'Enter') {
                        e.stopPropagation();
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
                }, true); 
                
                editor.dataset.sniperPatched = 'true';
            });
        };
        const observer = new MutationObserver(sniperEntryPatch);
        observer.observe(doc.body, { childList: true, subtree: true });
        sniperEntryPatch();
        </script>
        """,
        height=0,
    )

    FRONTLINE_FILE = f"saved_frontline_{user_id}.csv"
    target_cols = ["銘柄", "株数", "買値", "現在値", "損切", "第1利確", "第2利確", "atr"]

    if 'frontline_df' not in st.session_state:
        if os.path.exists(FRONTLINE_FILE):
            try:
                temp_df = pd.read_csv(FRONTLINE_FILE)
                rename_map = {'code': '銘柄', 'price': '現在値', 'buy': '買値', 'target': '第1利確', 'stop': '損切', 'lot': '株数'}
                temp_df = temp_df.rename(columns=rename_map).reindex(columns=target_cols)
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
with tab7:
    import datetime as dt_module
    st.markdown('<h3 style="font-size: clamp(14px, 4.5vw, 24px); margin-bottom: 1rem;">📁 事後任務報告 (AAR) & 戦績ダッシュボード</h3>', unsafe_allow_html=True)
    st.caption("※ 記録の編集は下部の『🛠️ 戦績編集コンソール』で行ってください。")
    
    AAR_FILE = f"saved_aar_log_{user_id}.csv"
    
    def get_scale_for_code(code):
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
        working_log_df = st.data_editor(
            st.session_state.aar_df_stable, 
            column_config={
                "規模": st.column_config.TextColumn("規模", disabled=True),
                "戦術": st.column_config.SelectboxColumn("戦術", options=["待伏", "強襲", "潜伏", "自動解析", "その他"], required=True),
                "規律": st.column_config.SelectboxColumn("規律", options=["遵守", "違反", "不明"], required=True),
                "買値": st.column_config.NumberColumn("買値", format="%d"),
                "売値": st.column_config.NumberColumn("売値", format="%d"),
            },
            hide_index=True, use_container_width=True, key="aar_editor_maintenance_v10"
        )

        if st.button("💾 戦績の変更を確定し、色彩を同期", use_container_width=True, type="primary"):
            st.session_state.aar_df_stable = working_log_df.copy()
            for col in ["買値", "売値", "株数", "損益額(円)"]:
                st.session_state.aar_df_stable[col] = pd.to_numeric(st.session_state.aar_df_stable[col], errors='coerce').fillna(0).astype(int)
            st.session_state.aar_df_stable.to_csv(AAR_FILE, index=False)
            st.success("✅ 整数化完了。色彩規律を再適用しました。")
            st.rerun()

# ==========================================
# 🚀 最終メモリ解放パージ（OOMクラッシュ回避）
# ==========================================
import gc
gc.collect()
