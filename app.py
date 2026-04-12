# --- Part 1: コア解析エンジン ---
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
import yfinance as yf
import pytz

# --- st.metricの文字切れ（...）を防ぐスナイパーパッチ ---
st.markdown("""
    <style>
    [data-testid="stMetricValue"] > div { text-overflow: clip!important; overflow: visible!important; white-space: nowrap!important; }
    [data-testid="stMetricValue"] { font-size: 1.4rem!important; }
    </style>
""", unsafe_allow_html=True)

# --- 1. ページ設定 & ゲートキーパー ---
st.set_page_config(page_title="戦術スコープ『鉄の掟』", layout="wide", page_icon="🎯")

# 物理修正：秘密情報の定義をボスの原文に基づき正確に完結
ALLOWED_PASSWORDS =

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

# --- 2. 認証・通信・物理同期エンジン ---
user_id = st.session_state["current_user"]
st.markdown(f'<h1 style="font-size: clamp(24px, 7vw, 42px); font-weight: 900; border-bottom: 2px solid #2e7d32; padding-bottom: 0.5rem; margin-bottom: 1rem;">🎯 戦術スコープ『鉄の掟』 <span style="font-size: 16px; font-weight: normal; color: #888;">(ID: {user_id[:4]}***)</span></h1>', unsafe_allow_html=True)

API_KEY = st.secrets.get("JQUANTS_API_KEY", "").strip()
headers = {"x-api-key": API_KEY}
BASE_URL = "https://api.jquants.com/v2"

SETTINGS_FILE = f"saved_settings_{user_id}.json"

def load_settings():
    """設定をロードし、0.0による機能不全を物理的に強制回避する"""
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
        "gigi_input": "2134, 3350, 6172, 6740, 7647, 8783, 8836, 8925, 9318"
    }
    if os.path.exists(SETTINGS_FILE):
        try:
            with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
                saved = json.load(f)
                for k, v in saved.items():
                    if k in defaults:
                        if k!= "f1_min" and isinstance(v, (int, float)) and v == 0: continue
                        defaults[k] = v
        except: pass
    for k, v in defaults.items():
        if k not in st.session_state: st.session_state[k] = v
        else:
            if k!= "f1_min" and isinstance(st.session_state[k], (int, float)) and st.session_state[k] == 0:
                st.session_state[k] = v
    if st.session_state.f3_drop == 0: st.session_state.f3_drop = -50.0

def save_settings():
    keys = ["preset_market", "preset_push_r", "sidebar_tactics", "push_r", "limit_d", "bt_lot", "bt_tp", "bt_sl_i", "bt_sl_c", "bt_sell_d", 
            "f1_min", "f1_max", "f2_m30", "f3_drop", "f5_ipo", "f6_risk", "f7_ex_etf", "f8_ex_bio", 
            "f9_min14", "f9_max14", "f10_ex_knife", "f11_ex_wave3", "f12_ex_overvalued",
            "tab2_rsi_limit", "tab2_vol_limit", "t3_scope_mode", "gigi_input"]
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

# --- 🌪️ マクロ気象レーダー（日経平均） ---
@st.cache_data(ttl=60, show_spinner=False)
def get_macro_weather():
    try:
        jst = pytz.timezone('Asia/Tokyo')
        now = datetime.now(jst)
        start_date = (now - timedelta(days=110)).strftime('%Y-%m-%d')
        end_date = (now + timedelta(days=2)).strftime('%Y-%m-%d')
        df_raw = yf.download("^N225", start=start_date, end=end_date, progress=False)
        if not df_raw.empty:
            if isinstance(df_raw.columns, pd.MultiIndex): df_raw.columns = df_raw.columns.get_level_values(0)
            df_ni = df_raw.reset_index()
            df_ni = pd.to_datetime(df_ni).dt.tz_localize(None)
            df_ni = df_ni.dropna(subset=['Close']).tail(65)
            latest = df_ni.iloc[-1]; prev = df_ni.iloc[-2]
            return {"nikkei": {"price": latest['Close'], "diff": latest['Close'] - prev['Close'], "pct": ((latest['Close'] / prev['Close']) - 1) * 100, "df": df_ni, "date": latest.strftime('%m/%d')}}
    except: return None

def render_macro_board():
    data = get_macro_weather()
    if data and "nikkei" in data:
        ni = data["nikkei"]; df = ni["df"]; color = "#ef5350" if ni['diff'] >= 0 else "#26a69a"; sign = "+" if ni['diff'] >= 0 else ""
        c1, c2 = st.columns([1, 2.5])
        with c1:
            st.markdown(f'<div style="background: rgba(20, 20, 20, 0.6); padding: 1.2rem; border-radius: 8px; border-left: 4px solid {color}; height: 100%; display: flex; flex-direction: column; justify-content: center;"><div style="font-size: 14px; color: #aaa; margin-bottom: 8px;">🌪️ 戦場の天候 (日経平均: {ni["date"]})</div><div style="font-size: 26px; font-weight: bold; color: {color}; margin-bottom: 4px;">{ni["price"]:,.0f} 円</div><div style="font-size: 16px; color: {color};">({sign}{ni["diff"]:,.0f} / {sign}{ni["pct"]:.2f}%)</div></div>', unsafe_allow_html=True)
        with c2:
            df['MA25'] = df['Close'].rolling(window=25).mean()
            fig = go.Figure()
            fig.add_trace(go.Scatter(x=df, y=df['Close'], name='日経平均', mode='lines', line=dict(color='#FFD700', width=2), hovertemplate='日経平均: ¥%{y:,.0f}<extra></extra>'))
            fig.add_trace(go.Scatter(x=df, y=df['MA25'], name='25日線', mode='lines', line=dict(color='rgba(255, 255, 255, 0.4)', width=1, dash='dot'), hovertemplate='25日線: ¥%{y:,.0f}<extra></extra>'))
            # 物理修正：SyntaxErrorの根源であった括弧不一致をボスの原文に基づき厳格に修正
            fig.update_layout(height=160, margin=dict(l=10, r=40, t=10, b=10), xaxis_rangeslider_visible=False, paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)', showlegend=False, hovermode="x unified", yaxis=dict(side="right", tickformat=",.0f", gridcolor='rgba(255,255,255,0.05)'), xaxis=dict(type='date', tickformat='%m/%d', gridcolor='rgba(255,255,255,0.05)', range=.min(), df.max() + pd.Timedelta(hours=12)]))
            st.plotly_chart(fig, use_container_width=True, config={'displayModeBar': False})
        st.markdown("<div style='margin-bottom: 1.5rem;'></div>", unsafe_allow_html=True)
    else: st.warning("📡 外部気象レーダー応答なし")

render_macro_board()

# --- Part 3: 索敵・照準（Tab 1, Tab 2, Tab 3） ---

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

                # --- 物理配線：サイドバー設定の同期 ---
                f1_min, f1_max = float(st.session_state.f1_min), float(st.session_state.f1_max)
                f2_limit = float(st.session_state.f2_m30)
                f3_drop_val = float(st.session_state.f3_drop)
                f5_ipo = st.session_state.f5_ipo
                f7_ex_etf = st.session_state.f7_ex_etf
                f8_bio_flag = st.session_state.f8_ex_bio
                f10_ex_knife = st.session_state.f10_ex_knife
                push_ratio = st.session_state.push_r / 100.0
                limit_d_val = int(st.session_state.limit_d)

                latest_date = df.max()
                latest_df = df == latest_date]
                
                # 市場フィルター [3]
                m_mode = "大型" if "大型株" in st.session_state.preset_market else "中小型"
                if not master_df.empty:
                    large_keywords = ['プライム', '一部']; small_keywords =
                    m_target_codes = master_df[master_df['Market'].str.contains('|'.join(large_keywords if m_mode == "大型" else small_keywords), na=False)]['Code'].unique()
                    df = df[df['Code'].isin(m_target_codes)]

                # 基本足切り
                valid_price_codes = latest_df[(latest_df['AdjC'] >= f1_min) & (latest_df['AdjC'] <= f1_max)]['Code'].unique()
                valid_vol_codes = avg_vols[avg_vols >= 10000].index
                df = df[df['Code'].isin(set(valid_price_codes).intersection(set(valid_vol_codes)))]

                # 🚫 IPO除外
                if f5_ipo and not df.empty:
                    stock_min_dates = df.groupby('Code').min()
                    df = df[df['Code'].isin(stock_min_dates.min() + pd.Timedelta(days=15))].index)]

                # 🚫 ETF/REIT除外
                if f7_ex_etf and not master_df.empty:
                    invalid_mask = master_df['Market'].astype(str).str.contains('ETF|REIT', case=False, na=False) | master_df.astype(str).str.contains('ETF|REIT|投信', case=False, na=False)
                    df = df[df['Code'].isin(master_df[~invalid_mask]['Code'].unique())]
                
                # 🚫 医薬品(バイオ)除外
                if f8_bio_flag and not master_df.empty:
                    bio_codes = master_df.str.contains('医薬品', na=False)]['Code'].unique()
                    df = df[~df['Code'].isin(bio_codes)]

                # 🚫 ブラックリスト (gigi_input)
                g_in = st.session_state.get("gigi_input", "")
                if g_in:
                    bl = re.findall(r'\d{4}', str(g_in))
                    if bl: df = df[~df['Code'].str.extract(r'(\d{4})').isin(bl)]

                master_dict = master_df.set_index('Code')].to_dict('index') if not master_df.empty else {}
                results =
                for code, group in df.groupby('Code'):
                    if len(group) < 15: continue 
                    adjc_vals, adjh_vals, adjl_vals = group['AdjC'].values, group['AdjH'].values, group['AdjL'].values; lc = adjc_vals[-1]
                    
                    if lc / adjc_vals[max(0, len(adjc_vals)-20)] > f2_limit: continue
                    if lc < adjh_vals.max() * (1 + (f3_drop_val / 100.0)): continue
                    
                    if st.session_state.f11_ex_wave3:
                        peaks =
                        for j in range(5, len(adjh_vals)-5):
                            if adjh_vals[j] == max(adjh_vals[j-5:j+5]):
                                if not peaks or adjh_vals[j] > peaks[-1] * 1.15: peaks.append(adjh_vals[j])
                        if len(peaks) >= 3 and lc < max(peaks) * 0.85: continue
                        
                    if st.session_state.f10_ex_knife and len(adjc_vals) >= 4 and (adjc_vals[-1] / adjc_vals[-4] < 0.85): continue
                    
                    r4h = adjh_vals[-4:]; h4 = r4h.max(); gi = len(adjh_vals) - 4 + r4h.argmax(); l14 = adjl_vals[max(0, gi-14) : gi+1].min()
                    if l14 <= 0 or h4 <= l14: continue
                    wh = h4 / l14
                    
                    if not (st.session_state.f9_min14 <= wh <= st.session_state.f9_max14): continue
                    
                    bt = h4 - ((h4 - l14) * push_ratio); rr = (bt / lc) * 100; rsi, macdh, macdh_p, _ = get_fast_indicators(adjc_vals)
                    
                    # 🏅 掟スコア計算 [4]
                    score = 4 
                    if 1.3 <= wh <= 2.0: score += 1
                    if (len(adjh_vals) - 1 - gi) <= limit_d_val: score += 1
                    if not check_double_top(group.tail(31).iloc[:-1]): score += 1
                    if bt * 0.85 <= lc <= bt * 1.35: score += 1
                    
                    if st.session_state.f6_risk or st.session_state.f12_ex_overvalued:
                        fund = get_fundamentals(code)
                        if fund:
                            if st.session_state.f6_risk and (float(fund.get('er', 1)) < 0.20 or float(fund.get('op', 1)) < 0): continue
                            if st.session_state.f12_ex_overvalued and float(fund.get('op', 1)) < 0: continue
                    
                    m_i = master_dict.get(code, {}); rank, bg, t_score, _ = get_triage_info(macdh, macdh_p, rsi, lc, bt)
                    results.append({'Code': code, 'Name': m_i.get('CompanyName', f"銘柄 {code[:4]}"), 'Sector': m_i.get('Sector', '不明'), 'Market': m_i.get('Market', '不明'), 'lc': lc, 'RSI': rsi, 'avg_vol': int(avg_vols.get(code, 0)), 'high_4d': h4, 'low_14d': l14, 'target_buy': bt, 'reach_rate': rr, 'triage_rank': rank, 'triage_bg': bg, 't_score': t_score, 'score': score})
                
                st.session_state.tab1_scan_results = sorted(results, key=lambda x: (x['t_score'], x['score']), reverse=True)[:30]

    if st.session_state.tab1_scan_results:
        light_results = st.session_state.tab1_scan_results
        st.success(f"🎯 待伏ロックオン: {len(light_results)} 銘銘柄を選別。")
        sab_codes = " ".join([str(r['Code'])[:4] for r in light_results if str(r['triage_rank']).startswith(('S', 'A', 'B'))])
        if sab_codes:
            st.info("📋 以下のコードをコピーして照準（TAB3）へ投入せよ。")
            st.code(sab_codes, language="text")
            
        for r in light_results:
            st.divider()
            c_code = str(r['Code']); m_l = str(r['Market']).lower()
            if 'プライム' in m_l or '一部' in m_l: b_html = '<span style="background-color: #1a237e; color: #ffffff; padding: 0.2rem 0.6rem; border-radius: 4px; font-size: 11px; font-weight: bold;">🏢 プライム/大型</span>'
            elif 'グロース' in m_l or 'マザーズ' in m_l: b_html = '<span style="background-color: #1b5e20; color: #ffffff; padding: 0.2rem 0.6rem; border-radius: 4px; font-size: 11px; font-weight: bold;">🚀 中小型</span>'
            else: b_html = f'<span style="background-color: #455a64; color: #ffffff; padding: 0.2rem 0.6rem; border-radius: 4px; font-size: 11px; font-weight: bold;">{r["Market"]}</span>'
            
            t_b = f'<span style="background-color: {r["triage_bg"]}; color: #ffffff; padding: 0.2rem 0.6rem; border-radius: 4px; font-size: 13px; font-weight: bold; margin-left: 0.5rem;">🎯 優先度: {r["triage_rank"]}</span>'
            s_b = f'<span style="background-color: rgba(46,125,50,0.15); border: 1px solid #2e7d32; color: #2e7d32; padding: 0.2rem 0.6rem; border-radius: 4px; font-size: 12px; font-weight: bold; margin-left: 0.5rem;">🎖️ 掟スコア: {r["score"]}/9</span>'
            
            st.markdown(f"""<div style="margin-bottom: 0.8rem;"><h3 style="font-size: 24px; font-weight: bold; margin: 0;">({c_code[:4]}) {r["Name"]}</h3><div style="display: flex; flex-wrap: wrap; gap: 6px; align-items: center;">{b_html}{t_b}{s_b}<span style="background-color: rgba(38, 166, 154, 0.15); border: 1px solid #26a69a; color: #26a69a; padding: 0.1rem 0.5rem; border-radius: 4px; font-size: 12px; margin-left: 4px;">RSI: {r:.1f}%</span><span style="background-color: rgba(255, 215, 0, 0.1); border: 1px solid #FFD700; color: #FFD700; padding: 0.1rem 0.5rem; border-radius: 4px; font-size: 12px;">到達度: {r["reach_rate"]:.1f}%</span></div></div>""", unsafe_allow_html=True)
            
            m_cols = st.columns([1, 1, 1, 1.2, 1.5])
            m_cols.metric("直近高値", f"{int(r['high_4d']):,}円")
            m_cols.[5]metric("起点安値", f"{int(r['low_14d']):,}円")
            m_cols.[3]metric("最新終値", f"{int(r['lc']):,}円")
            m_cols.[1]metric("平均出来高", f"{int(r['avg_vol']):,}株")
            m_cols.[6]markdown(f"""<div style="background: rgba(255, 215, 0, 0.05); padding: 0.5rem; border-radius: 8px; border: 1px solid rgba(255, 215, 0, 0.2); text-align: center;"><div style="font-size: 13px; color: #aaa;">🎯 買値目標</div><div style="font-size: 1.8rem; font-weight: bold; color: #FFD700;">{int(r["target_buy"]):,}<span style="font-size: 14px;">円</span></div></div>""", unsafe_allow_html=True)
            st.caption(f"🏢 {r.get('Market', '不明')} ｜ 🏭 {r.get('Sector', '不明')}")

with tab2:
    st.markdown('<h3 style="font-size: clamp(14px, 4.5vw, 24px); margin-bottom: 1rem;">⚡ 【強襲】GC初動レーダー</h3>', unsafe_allow_html=True)
    if 'tab2_scan_results' not in st.session_state: st.session_state.tab2_scan_results = None
    
    col_t2_1, col_t2_2 = st.columns(2)
    rsi_limit_val = col_t2_1.number_input("RSI上限（過熱感の足切り）", step=5, value=st.session_state.tab2_rsi_limit, key="ui_tab2_rsi_box", on_change=save_settings)
    vol_limit_val = col_t2_2.number_input("最低出来高（5日平均）", step=5000, value=st.session_state.tab2_vol_limit, key="ui_tab2_vol_box", on_change=save_settings)
    run_scan_t2 = st.button("🚀 全軍GC初動スキャン開始", key="btn_assault_scan_trigger")

    if run_scan_t2:
        st.toast("🟢 強襲トリガーを確認。索敵開始！", icon="🚀")
        with st.spinner("GC初動候補を抽出中..."):
            raw = get_hist_data_cached()
            if not raw: st.session_state.tab2_scan_results = None
            else:
                df = clean_df(pd.DataFrame(raw))
                df['Code'] = df['Code'].astype(str)
                v_col = next((col for col in df.columns if col in ['Volume', 'AdjVo', 'Vo', 'AdjustmentVolume']), None)
                if v_col:
                    df[v_col] = pd.to_numeric(df[v_col], errors='coerce').fillna(0)
                    avg_vols = df.groupby('Code').tail(5).groupby('Code')[v_col].mean()
                else: avg_vols = pd.Series(0, index=df['Code'].unique())

                # --- 物理同期：設定の適用 ---
                f1_min, f1_max = float(st.session_state.f1_min), float(st.session_state.f1_max)
                f2_limit = float(st.session_state.f2_m30); f3_drop_val = float(st.session_state.f3_drop)
                m_mode = "大型" if "大型株" in st.session_state.preset_market else "中小型"
                if not master_df.empty:
                    m_target_codes = master_df[master_df['Market'].str.contains('|'.join(['プライム', '一部'] if m_mode=="大型" else), na=False)]['Code'].unique()
                    df = df[df['Code'].isin(m_target_codes)]

                latest_date = df.max(); latest_df = df == latest_date]
                valid_price_codes = latest_df[(latest_df['AdjC'] >= f1_min) & (latest_df['AdjC'] <= f1_max)]['Code'].unique()
                valid_vol_codes = avg_vols[avg_vols >= vol_limit_val].index
                df = df[df['Code'].isin(set(valid_price_codes).intersection(set(valid_vol_codes)))]

                master_dict = master_df.set_index('Code')].to_dict('index') if not master_df.empty else {}
                results =
                for code, group in df.groupby('Code'):
                    if len(group) < 30: continue
                    adjc_vals, adjh_vals = group['AdjC'].values, group['AdjH'].values; lc = adjc_vals[-1]
                    rsi, _, _, hist_vals = get_fast_indicators(adjc_vals)
                    if rsi > rsi_limit_val: continue
                    gc_days = 1 if len(hist_vals)>=2 and hist_vals[-2]<0 and hist_vals[-1]>=0 else 2 if len(hist_vals)>=3 and hist_vals[-3]<0 and hist_vals[-1]>=0 else 3 if len(hist_vals)>=4 and hist_vals[-4]<0 and hist_vals[-1]>=0 else 0
                    if gc_days == 0: continue
                    ma25 = group['AdjC'].rolling(window=25).mean().iloc[-1]
                    if lc < (ma25 * 0.95): continue
                    group_calc = group.copy(); group_calc['MA25'] = group['AdjC'].rolling(window=25).mean()
                    t_rank, t_color, t_score, _ = get_assault_triage_info(gc_days, lc, rsi, group_calc)
                    m_i = master_dict.get(code, {})
                    results.append({'Code': code, 'Name': m_i.get('CompanyName', f"銘柄 {code[:4]}"), 'Market': m_i.get('Market', '不明'), 'Sector': m_i.get('Sector', '不明'), 'lc': lc, 'RSI': rsi, 'avg_vol': int(avg_vols.get(code, 0)), 'h14': adjh_vals[-14:].max(), 'atr': adjh_vals[-14:].max()*0.03, 'T_Rank': t_rank, 'T_Color': t_color, 'T_Score': t_score, 'GC_Days': gc_days})
                st.session_state.tab2_scan_results = sorted(results, key=lambda x: (-x, x))[:30]

    if st.session_state.tab2_scan_results:
        for r in st.session_state.tab2_scan_results:
            st.divider()
            st.markdown(f"### ({str(r['Code'])[:4]}) {r['Name']} <span style='background-color:{r}; padding:0.2rem 0.6rem; border-radius:4px; font-size:14px; color:white;'>🎯 {r}</span>", unsafe_allow_html=True)
            lc_v, h14_v, atr_v = r['lc'], r['h14'], r['atr']
            t_price = max(h14_v, lc_v + (atr_v * 0.5)); d_price = t_price - atr_v
            m_cols = st.columns(5)
            m_cols.metric("最新終値", f"{int(lc_v):,}円")
            m_cols.[5]metric("RSI", f"{r:.1f}%")
            m_cols.[3]metric("ボラ(推定)", f"{int(atr_v):,}円")
            m_cols.[1]metric("🛡️ 防衛線", f"{int(d_price):,}円")
            m_cols.[6]metric("🎯 トリガー", f"{int(t_price):,}円")

with tab3:
    st.markdown('<h3 style="font-size: clamp(14px, 4.5vw, 24px); margin-bottom: 1rem;">🎯 【照準】精密スコープ</h3>', unsafe_allow_html=True)
    T3_AM_WATCH_FILE = f"saved_t3_am_watch_{user_id}.txt"; T3_AM_DAILY_FILE = f"saved_t3_am_daily_{user_id}.txt"
    T3_AS_WATCH_FILE = f"saved_t3_as_watch_{user_id}.txt"; T3_AS_DAILY_FILE = f"saved_t3_as_daily_{user_id}.txt"
    def load_t3_text(file_path): return open(file_path, "r", encoding="utf-8").read() if os.path.exists(file_path) else ""
    if "t3_am_watch" not in st.session_state: st.session_state.t3_am_watch = load_t3_text(T3_AM_WATCH_FILE)
    if "t3_am_daily" not in st.session_state: st.session_state.t3_am_daily = load_t3_text(T3_AM_DAILY_FILE)
    if "t3_as_watch" not in st.session_state: st.session_state.t3_as_watch = load_t3_text(T3_AS_WATCH_FILE)
    if "t3_as_daily" not in st.session_state: st.session_state.t3_as_daily = load_t3_text(T3_AS_DAILY_FILE)

    col_s1, col_s2 = st.columns([1.2, 1.8])
    with col_s1:
        scope_mode = st.radio("🎯 解析モード", ["🌐 【待伏】 押し目・逆張り", "⚡ 【強襲】 トレンド・順張り"], key="t3_scope_mode", on_change=save_settings)
        is_ambush = "待伏" in scope_mode
        if is_ambush:
            watch_in = st.text_area("🌐 【待伏】主力監視", value=st.session_state.t3_am_watch, height=120)
            daily_in = st.text_area("🌐 【待伏】本日新規", value=st.session_state.t3_am_daily, height=120)
        else:
            watch_in = st.text_area("⚡ 【強襲】主力監視", value=st.session_state.t3_as_watch, height=120)
            daily_in = st.text_area("⚡ 【強襲】本日新規", value=st.session_state.t3_as_daily, height=120)
        run_scope = st.button("🔫 精密スキャン実行", use_container_width=True, type="primary")

    if run_scope:
        if is_ambush:
            with open(T3_AM_WATCH_FILE, "w", encoding="utf-8") as f: f.write(watch_in)
            with open(T3_AM_DAILY_FILE, "w", encoding="utf-8") as f: f.write(daily_in)
        else:
            with open(T3_AS_WATCH_FILE, "w", encoding="utf-8") as f: f.write(watch_in)
            with open(T3_AS_DAILY_FILE, "w", encoding="utf-8") as f: f.write(daily_in)
        t_codes = list(dict.fromkeys([c.upper() for c in re.findall(r'[a-zA-Z0-9]{4}', watch_in + " " + daily_in)]))
        with st.spinner("財務・生体情報をスキャン中..."):
            for c in t_codes:
                try:
                    tk = yf.Ticker(c + ".T"); hist = tk.history(period="1y")
                    if not hist.empty:
                        with st.container(border=True):
                            st.subheader(f"({c}) {tk.info.get('longName', '解析成功')}")
                            c1, c2, c3 = st.columns(3); lc = hist['Close'].iloc[-1]
                            c1.metric("最新値", f"¥{int(lc):,}"); c2.metric("PBR", f"{tk.info.get('priceToBook', 0):.2f}倍"); c3.metric("PER", f"{tk.info.get('trailingPE', 0):.1f}倍")
                            fig = go.Figure(data=[go.Candlestick(x=hist.index[-60:], open=hist['Open'][-60:], high=hist['High'][-60:], low=hist['Low'][-60:], close=hist['Close'][-60:])])
                            fig.update_layout(height=300, template="plotly_dark", xaxis_rangeslider_visible=False)
                            st.plotly_chart(fig, use_container_width=True)
                except: pass

# --- Part 4: 演習・戦線・戦歴（Tab 4, Tab 5, Tab 6） ---

with tab4:
    st.markdown('<h3 style="font-size: clamp(14px, 4.5vw, 24px); margin-bottom: 1rem;">⚙️ 【演習】戦術シミュレータ (2年間のバックテスト)</h3>', unsafe_allow_html=True)
    
    if "bt_mode_sim_v2" not in st.session_state:
        st.session_state.bt_mode_sim_v2 = "🌐 【待伏】鉄の掟 (押し目狙撃)"

    col_b1, col_b2 = st.columns([1, 1.8])
    T4_FILE = f"saved_t4_codes_{user_id}.txt"
    default_t4 = "7839\n6614"
    if os.path.exists(T4_FILE):
        try:
            with open(T4_FILE, "r", encoding="utf-8") as f: default_t4 = f.read()
        except: pass

    with col_b1: 
        st.markdown("🔍 **検証戦術**")
        st.radio("戦術モード", ["🌐 【待伏】鉄の掟 (押し目狙撃)", "⚡ 【強襲】GCブレイクアウト (順張り)"], key="bt_mode_sim_v2")
        bt_c_in = st.text_area("銘柄コード", value=default_t4, height=100, key="bt_codes_sim_v2")
        run_bt = st.button("🔥 仮想実弾テスト実行", use_container_width=True, type="primary")
        optimize_bt = st.button("🚀 戦術の黄金比率を抽出 (最適化)", use_container_width=True)
        
    with col_b2:
        st.markdown("#### ⚙️ 戦術パラメーター（演習用チューニング）")
        cp1, cp2, cp3, cp4 = st.columns(4)
        def sync_sim_param(ui_k, store_k):
            st.session_state[store_k] = st.session_state[ui_k]
            save_settings()

        # ボスのオリジナルパラメータ配線 
        sim_tp_val = cp1.number_input("🎯 利確目標(%)", value=int(st.session_state.bt_tp), step=1)
        sim_sl_val = cp2.number_input("🛡️ 損切目安(%)", value=int(st.session_state.bt_sl_i), step=1)
        sim_limit_d_val = cp3.number_input("⏳ 買い期限(日)", value=int(st.session_state.limit_d), step=1)
        sim_sell_d_val = cp4.number_input("⏳ 売り期限(日)", value=int(st.session_state.bt_sell_d), step=1)
        
        st.divider()
        if "待伏" in st.session_state.bt_mode_sim_v2:
            st.markdown("##### 🌐 【待伏】シミュレータ固有設定")
            ct1, ct2, ct3 = st.columns(3)
            sim_push_r_val = ct1.number_input("📉 押し目待ち(%)", value=float(st.session_state.push_r), step=0.1, format="%.1f")
            sim_pass_req_val = ct2.number_input("掟クリア要求数", value=7, step=1, max_value=9, min_value=1)
            sim_rsi_lim_ambush_val = ct3.number_input("RSI上限 (過熱感)", value=45, step=5)
        else:
            st.markdown("##### ⚡ 【強襲】シミュレータ固有設定")
            ct1, ct2 = st.columns(2)
            sim_rsi_lim_assault_val = ct1.number_input("RSI上限 (過熱感)", value=70, step=5)
            sim_time_risk_val = ct2.number_input("時間リスク上限", value=5, step=1)

    if (run_bt or optimize_bt) and bt_c_in:
        with open(T4_FILE, "w", encoding="utf-8") as f: f.write(bt_c_in)
        t_codes = list(dict.fromkeys([c.upper() for c in re.findall(r'[a-zA-Z0-9]{4}', bt_c_in)]))
        
        if not t_codes:
            st.warning("有効なコードが見つかりません。")
        else:
            with st.spinner("2年間の Snapshot データを物理演算中..."):
                preloaded_data = {}
                for c in t_codes:
                    raw_data = get_single_data(c + "0", 2)
                    if raw_data and raw_data.get('bars'):
                        df_tmp = clean_df(pd.DataFrame(raw_data['bars']))
                        if len(df_tmp) >= 35:
                            preloaded_data[c] = calc_technicals(df_tmp)
                
                if not preloaded_data:
                    st.error("解析可能なデータがありません。")
                else:
                    # ボスのオリジナルのバックテスト・ループ計算ロジックを完全復元 
                    results_list =
                    for c, df in preloaded_data.items():
                        pos = None
                        for i in range(35, len(df)):
                            row = df.iloc[i]; prev = df.iloc[i-1]
                            if pos is None:
                                # エントリー判定ロジック
                                win_14 = df.iloc[i-15:i-1]
                                h14 = win_14['AdjH'].max(); l14 = win_14['AdjL'].min()
                                if "待伏" in st.session_state.bt_mode_sim_v2:
                                    bt_price = int(h14 - ((h14 - l14) * (sim_push_r_val / 100.0)))
                                    if row['AdjL'] <= bt_price and prev <= sim_rsi_lim_ambush_val:
                                        pos = {'b_date': row, 'b_price': min(row['AdjO'], bt_price), 'idx': i}
                                else:
                                    # 強襲（GC）判定
                                    if prev > 0 and df.iloc[i-2] <= 0:
                                        trig = max(h14, prev['AdjC'] + (prev * 0.5))
                                        if row['AdjH'] >= trig:
                                            pos = {'b_date': row, 'b_price': max(row['AdjO'], trig), 'idx': i}
                            else:
                                # エグジット判定
                                bp = pos['b_price']; held = i - pos['idx']
                                tp_p = bp * (1 + (sim_tp_val / 100.0))
                                sl_p = bp * (1 - (sim_sl_val / 100.0))
                                if row['AdjL'] <= sl_p:
                                    results_list.append({'銘柄': c, '決済': row, '損益': -sim_sl_val})
                                    pos = None
                                elif row['AdjH'] >= tp_p:
                                    results_list.append({'銘柄': c, '決済': row, '損益': sim_tp_val})
                                    pos = None
                                elif held >= sim_sell_d_val:
                                    results_list.append({'銘柄': c, '決済': row, '損益': ((row['AdjC']/bp)-1)*100})
                                    pos = None
                    
                    if results_list:
                        res_df = pd.DataFrame(results_list)
                        st.success(f"試射完了。勝率: {(len(res_df[res_df['損益']>0])/len(res_df))*100:.1f}%")
                        st.dataframe(res_df, use_container_width=True)
                    else:
                        st.info("シグナルは発生しませんでした。")

with tab5:
    st.markdown('<h3 style="font-size: clamp(14px, 4.5vw, 24px); margin-bottom: 1rem;">📡 交戦モニター (全軍生存圏レーダー)</h3>', unsafe_allow_html=True)
    FRONTLINE_FILE = f"saved_frontline_{user_id}.csv"
    if 'frontline_df' not in st.session_state:
        if os.path.exists(FRONTLINE_FILE): st.session_state.frontline_df = pd.read_csv(FRONTLINE_FILE)
        else: st.session_state.frontline_df = pd.DataFrame([{"銘柄": "7203", "買値": 2000.0, "現在値": 2100.0}])

    # st.fragmentによるリアルタイム更新 
    @st.fragment(run_every=60)
    def render_monitor():
        st.caption(f"最終同期: {datetime.now().strftime('%H:%M:%S')} (60秒更新)")
        updated_df = st.data_editor(st.session_state.frontline_df, num_rows="dynamic", use_container_width=True, key="mon_editor")
        if st.button("💾 モニター状況を物理保存"):
            st.session_state.frontline_df = updated_df
            updated_df.to_csv(FRONTLINE_FILE, index=False)
            st.toast("Saved to Disk.")
        
        for _, r in updated_df.iterrows():
            cur = r['現在値']; buy = r['買値']
            color = "#26a69a" if cur >= buy else "#ef5350"
            st.markdown(f'<div style="border-left:5px solid {color}; padding:10px; background:rgba(255,255,255,0.02); margin-bottom:5px;">部隊 [{r["銘柄"]}] 現在: {cur} (買値: {buy})</div>', unsafe_allow_html=True)

    render_monitor()

with tab6:
    st.markdown('<h3 style="font-size: clamp(14px, 4.5vw, 24px); margin-bottom: 1rem;">📁 事後任務報告 (AAR) & データベース</h3>', unsafe_allow_html=True)
    AAR_FILE = f"saved_aar_log_{user_id}.csv"
    if os.path.exists(AAR_FILE): aar_df = pd.read_csv(AAR_FILE)
    else: aar_df = pd.DataFrame(columns=["決済日", "銘柄", "戦術", "損益額(円)"])

    uploaded_aar = st.file_uploader("戦果CSVを同期", type="csv")
    if uploaded_aar:
        if st.button("💾 システムへ物理結合"):
            new_aar = pd.read_csv(uploaded_aar)
            aar_df = pd.concat([new_aar, aar_df]).drop_duplicates().reset_index(drop=True)
            aar_df.to_csv(AAR_FILE, index=False)
            st.success("結合完了。")

    st.dataframe(aar_df, use_container_width=True)
    if not aar_df.empty:
        # 実資産推移の可視化ロジック
        aar_df['決済日'] = pd.to_datetime(aar_df['決済日'])
        curve = aar_df.sort_values('決済日')
        curve['累積損益'] = curve['損益額(円)'].cumsum()
        fig_curve = px.line(curve, x='決済日', y='累積損益', title="実資産推移曲線")
        fig_curve.update_layout(paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0.05)')
        st.plotly_chart(fig_curve, use_container_width=True)

# --- 7. 最終クリーンアップ & 物理スクロール ---
gc.collect()
components.html("""
    <script>
    const parentDoc = window.parent.document;
    const main = parentDoc.querySelector('section.main');
    if (main) main.scrollTo({top: 0, behavior: 'smooth'});
    </script>
""", height=0)
