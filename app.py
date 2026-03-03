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

# --- 1. ページ設定 ---
st.set_page_config(page_title="株式投資作戦企画室", layout="wide")
st.markdown('<h1 style="font-size: clamp(24px, 7vw, 42px); font-weight: 900; letter-spacing: 0.05em; border-bottom: 2px solid #2e7d32; padding-bottom: 0.5rem; margin-bottom: 1rem; white-space: nowrap; overflow: hidden; text-overflow: ellipsis;">🎯 株式投資作戦企画室</h1>', unsafe_allow_html=True)

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

def check_double_top(df_sub):
    try:
        v = df_sub['AdjH'].values; c = df_sub['AdjC'].values; l = df_sub['AdjL'].values
        if len(v) < 15: return False
        peaks = []
        for i in range(1, len(v)-1):
            if v[i] == max(v[i-1:i+2]):
                if not peaks or (i - peaks[-1][0] > 3): peaks.append((i, v[i]))
        if len(v) >= 2 and v[-1] > v[-2]:
            if not peaks or (len(v)-1 - peaks[-1][0] > 3): peaks.append((len(v)-1, v[-1]))
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
        if len(v) < 20: return False
        peaks = []
        for i in range(1, len(v)-1):
            if v[i] == max(v[i-1:i+2]):
                if not peaks or (i - peaks[-1][0] > 2): peaks.append((i, v[i]))
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
        if len(l) < 15: return False
        valleys = []
        for i in range(1, len(l)-1):
            if l[i] == min(l[i-1:i+2]):
                if not valleys or (i - valleys[-1][0] > 3): valleys.append((i, l[i]))
        if len(l) >= 3 and l[-2] == min(l[-3:]):
             if not valleys or (len(l)-2 - valleys[-1][0] > 3): valleys.append((len(l)-2, l[-2]))
                
        if len(valleys) >= 2:
            v2_idx, v2_val = valleys[-1]; v1_idx, v1_val = valleys[-2]
            if abs(v2_val - v1_val) / min(v2_val, v1_val) < 0.05:
                peak = max(h[v1_idx:v2_idx+1]) if v2_idx > v1_idx else v1_val
                if peak > max(v1_val, v2_val) * 1.04: 
                    if c[-1] > v2_val * 1.01: return True
        return False
    except: return False

def draw_chart(df, targ_p, tp5=None, tp10=None, tp15=None, tp20=None):
    fig = go.Figure()
    fig.add_trace(go.Candlestick(
        x=df['Date'], open=df['AdjO'], high=df['AdjH'],
        low=df['AdjL'], close=df['AdjC'], name='株価',
        increasing_line_color='#ef5350', decreasing_line_color='#26a69a'
    ))
    fig.add_trace(go.Scatter(x=df['Date'], y=[targ_p]*len(df), mode='lines', name='買値目標', line=dict(color='#FFD700', width=2, dash='dash')))
    if tp5 and tp10 and tp15 and tp20:
        fig.add_trace(go.Scatter(x=df['Date'], y=[tp5]*len(df), mode='lines', name='売値(5%)', line=dict(color='rgba(76, 175, 80, 0.4)', width=1, dash='dot')))
        fig.add_trace(go.Scatter(x=df['Date'], y=[tp10]*len(df), mode='lines', name='売値(10%)', line=dict(color='rgba(76, 175, 80, 0.6)', width=1, dash='dot')))
        fig.add_trace(go.Scatter(x=df['Date'], y=[tp15]*len(df), mode='lines', name='売値(15%)', line=dict(color='rgba(76, 175, 80, 0.8)', width=1.5, dash='dot')))
        fig.add_trace(go.Scatter(x=df['Date'], y=[tp20]*len(df), mode='lines', name='売値(20%)', line=dict(color='rgba(76, 175, 80, 1.0)', width=1.5, dash='dot')))
    
    last_date = df['Date'].max()
    start_date = last_date - timedelta(days=45) if len(df) > 30 else df['Date'].min()
    padding_days = timedelta(days=1)

    visible_df = df[(df['Date'] >= start_date) & (df['Date'] <= last_date)]
    if not visible_df.empty:
        y_max_vals = [visible_df['AdjH'].max(), targ_p]
        y_min_vals = [visible_df['AdjL'].min(), targ_p * 0.85] 
        if tp20: y_max_vals.append(tp20)
        
        y_max = max(y_max_vals)
        y_min = min(y_min_vals)
        margin = (y_max - y_min) * 0.05
        y_range = [y_min - margin, y_max + margin]
    else:
        y_range = None

    layout_args = dict(
        height=450, 
        margin=dict(l=10, r=60, t=20, b=40), 
        xaxis_rangeslider_visible=True,
        xaxis=dict(range=[start_date, last_date + padding_days], type="date"),
        paper_bgcolor='rgba(0,0,0,0)', 
        plot_bgcolor='rgba(0,0,0,0)', 
        hovermode="x unified", 
        legend=dict(orientation="h", yanchor="top", y=-0.1, xanchor="center", x=0.5)
    )
    
    if y_range:
        layout_args['yaxis'] = dict(range=y_range, fixedrange=False)

    fig.update_layout(**layout_args)
    st.plotly_chart(fig, use_container_width=True)

# ==========================================
# 4. UI構築（デュアル・プリセット機構搭載）
# ==========================================

if 'preset_target' not in st.session_state: st.session_state.preset_target = "🚀 中小型株 (黄金比・絶対防衛)"
if 'sidebar_tactics' not in st.session_state: st.session_state.sidebar_tactics = "⚖️ バランス (掟達成率 ＞ 到達度)"
if 'bt_mode_radio' not in st.session_state: st.session_state.bt_mode_radio = "⚖️ バランス (指定%落ちで指値買い)"
if 'push_r' not in st.session_state: st.session_state.push_r = 50
if 'limit_d' not in st.session_state: st.session_state.limit_d = 4
if 'bt_push' not in st.session_state: st.session_state.bt_push = 50
if 'bt_buy_d' not in st.session_state: st.session_state.bt_buy_d = 4
if 'bt_tp' not in st.session_state: st.session_state.bt_tp = 15
if 'bt_sl_i' not in st.session_state: st.session_state.bt_sl_i = 8
if 'bt_sl_c' not in st.session_state: st.session_state.bt_sl_c = 5
if 'bt_sell_d' not in st.session_state: st.session_state.bt_sell_d = 10
if 'bt_lot' not in st.session_state: st.session_state.bt_lot = 100

def apply_market_preset():
    is_large = "大型株" in st.session_state.preset_target
    if is_large:
        if "バランス" in st.session_state.sidebar_tactics:
            st.session_state.push_r = 25
        else:
            st.session_state.push_r = 45
            
        if "バランス" in st.session_state.bt_mode_radio:
            st.session_state.bt_push = 25
            st.session_state.bt_tp = 20
        else:
            st.session_state.bt_push = 45
            st.session_state.bt_tp = 15
        st.session_state.bt_sl_i = 15
    else:
        st.session_state.push_r = 50
        st.session_state.bt_push = 50
        st.session_state.bt_tp = 15
        st.session_state.bt_sl_i = 8
    
    st.session_state.limit_d = 4
    st.session_state.bt_buy_d = 4
    st.session_state.bt_sl_c = 5
    st.session_state.bt_sell_d = 10

st.sidebar.header("🎯 対象市場 (一括換装)")
st.sidebar.radio(
    "プリセット選択",
    ["🚀 中小型株 (黄金比・絶対防衛)", "🏢 大型株 (ノイズ許容・トレンド追従)"],
    key="preset_target",
    on_change=apply_market_preset,
    help="中小型株: グロースや下位銘柄用（50%押し/ザラ場損切8%）。 大型株: プライム等でバランス型なら（25%押し/利確20%）。"
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
f1_min = st.sidebar.number_input("① 株価下限(円)", value=200, step=100)
f2_m30 = st.sidebar.number_input("② 1ヶ月暴騰上限(倍)", value=2.0, step=0.1)
f3_drop = st.sidebar.number_input("③ 半年〜1年下落除外(%)", value=-30, step=5)
f4_mlong = st.sidebar.number_input("④ 上げ切り除外(倍)", value=3.0, step=0.5)
f5_ipo = st.sidebar.checkbox("⑤ IPO除外", value=True)
f6_risk = st.sidebar.checkbox("⑥ 疑義注記銘柄除外", value=True)

# 【追加】マクロ・バイオ除外のUI新設
f7_ex_etf = st.sidebar.checkbox("⑦ ETF・REIT等を除外", value=True, help="1690等のマクロ連動型や不動産投信を弾きます")
f8_ex_bio = st.sidebar.checkbox("⑧ 医薬品(バイオ)を除外", value=True, help="4593等のテクニカルが効かない赤字バイオ株を弾きます")

c_f9_1, c_f9_2 = st.sidebar.columns(2)
f9_min14 = c_f9_1.number_input("⑨ 下限(倍)", value=1.3, step=0.1)
f9_max14 = c_f9_2.number_input("⑨ 上限(倍)", value=2.0, step=0.1)

st.sidebar.header("🎯 買いルール")
push_r = st.sidebar.number_input("① 押し目(%)", step=5, key="push_r")
limit_d = st.sidebar.number_input("② 買い期限(日)", step=1, key="limit_d")

# ==========================================
# メイン画面（3タブ構成）
# ==========================================
tab1, tab2, tab3 = st.tabs(["🚀 実戦（全軍）", "🔫 局地戦（個別）", "🔬 訓練（検証）"])
master_df = load_master()

with tab1:
    st.markdown('<h3 style="font-size: clamp(14px, 4.5vw, 24px); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; margin-bottom: 1rem;">🌐 ボスの「鉄の掟」全軍スキャン</h3>', unsafe_allow_html=True)
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
                df_14 = df_30.groupby('Code').tail(14)
                counts = df_14.groupby('Code').size()
                valid = counts[counts == 14].index
                if valid.empty: st.warning("条件を満たすデータが存在しません。"); st.stop()
                
                df_14 = df_14[df_14['Code'].isin(valid)]
                df_30 = df_30[df_30['Code'].isin(valid)]
                df_past = df[~df.index.isin(df_30.index)]; df_past = df_past[df_past['Code'].isin(valid)]
                
                agg_14 = df_14.groupby('Code').agg(lc=('AdjC', 'last'), h14=('AdjH', 'max'), l14=('AdjL', 'min'))
                idx_max = df_14.groupby('Code')['AdjH'].idxmax()
                h_dates = df_14.loc[idx_max, ['Code', 'Date']].rename(columns={'Date': 'h_date'})
                df_14_m = df_14.merge(h_dates, on='Code')
                d_high = df_14_m[df_14_m['Date'] > df_14_m['h_date']].groupby('Code').size().rename('d_high')
                
                agg_30 = df_30.groupby('Code').agg(l30=('AdjL', 'min'))
                agg_p = df_past.groupby('Code').agg(omax=('AdjH', 'max'), omin=('AdjL', 'min'))
                sum_df = agg_14.join(d_high, how='left').fillna({'d_high': 0}).join(agg_30).join(agg_p).reset_index()
                
                ur = sum_df['h14'] - sum_df['l14']
                sum_df['bt'] = sum_df['h14'] - (ur * (push_r / 100.0))
                sum_df['tp5'] = sum_df['bt'] * 1.05; sum_df['tp10'] = sum_df['bt'] * 1.10; sum_df['tp15'] = sum_df['bt'] * 1.15; sum_df['tp20'] = sum_df['bt'] * 1.20
                
                denom = sum_df['h14'] - sum_df['bt']
                sum_df['reach_pct'] = np.where(denom > 0, (sum_df['h14'] - sum_df['lc']) / denom * 100, 0)
                sum_df['r14'] = np.where(sum_df['l14'] > 0, sum_df['h14'] / sum_df['l14'], 0)
                sum_df['r30'] = np.where(sum_df['l30'] > 0, sum_df['lc'] / sum_df['l30'], 0)
                sum_df['ldrop'] = np.where((sum_df['omax'].notna()) & (sum_df['omax'] > 0), ((sum_df['lc'] / sum_df['omax']) - 1) * 100, 0)
                sum_df['lrise'] = np.where((sum_df['omin'].notna()) & (sum_df['omin'] > 0), sum_df['lc'] / sum_df['omin'], 0)
                
                dt_s = df_30.groupby('Code').apply(check_double_top).rename('is_dt')
                hs_s = df_30.groupby('Code').apply(check_head_shoulders).rename('is_hs')
                db_s = df_30.groupby('Code').apply(check_double_bottom).rename('is_db')
                sum_df = sum_df.merge(dt_s, on='Code', how='left').merge(hs_s, on='Code', how='left').merge(db_s, on='Code', how='left')
                sum_df = sum_df.fillna({'is_dt': False, 'is_hs': False, 'is_db': False})
                
                sum_df['is_defense'] = (~sum_df['is_dt']) & (~sum_df['is_hs']) & (sum_df['lc'] <= (sum_df['l14'] * 1.03))
                
                if not master_df.empty: sum_df = pd.merge(sum_df, master_df, on='Code', how='left')
                
                # 【追加】ETF・バイオ・落ちるナイフの防壁適用
                if f7_ex_etf and 'Sector' in sum_df.columns:
                    sum_df = sum_df[sum_df['Sector'].fillna('') != '-']
                    sum_df = sum_df[~sum_df['CompanyName'].astype(str).str.contains("ETF|投信|ブル|ベア|REIT|ﾘｰﾄ", na=False, flags=re.IGNORECASE)]
                
                if f8_ex_bio and 'Sector' in sum_df.columns:
                    sum_df = sum_df[sum_df['Sector'] != '医薬品']

                sum_df = sum_df[sum_df['lc'] >= f1_min]
                sum_df = sum_df[sum_df['r30'] <= f2_m30]
                sum_df = sum_df[sum_df['ldrop'] >= f3_drop]
                sum_df = sum_df[(sum_df['lrise'] <= f4_mlong) | (sum_df['lrise'] == 0)]
                
                if f5_ipo:
                    old_c = get_old_codes()
                    if old_c: sum_df = sum_df[sum_df['Code'].isin(old_c)]
                if f6_risk and 'CompanyName' in sum_df.columns:
                    sum_df = sum_df[~sum_df['CompanyName'].astype(str).str.contains("疑義|重要事象", na=False)]
                
                sum_df = sum_df[(~sum_df['is_dt']) & (~sum_df['is_hs'])]
                
                sum_df = sum_df[(sum_df['r14'] >= f9_min14) & (sum_df['r14'] <= f9_max14)]
                sum_df = sum_df[sum_df['d_high'] <= limit_d]
                
                # 【修正】落ちるナイフ完全除外（目標値より上、または目標値から最大-15%までしか許容しない）
                sum_df = sum_df[(sum_df['lc'] <= (sum_df['bt'] * 1.05)) & (sum_df['lc'] >= (sum_df['bt'] * 0.85))]
                
                if tactics_mode.startswith("⚔️"):
                    res = sum_df.sort_values(['is_db', 'reach_pct'], ascending=[False, False]).head(30)
                elif tactics_mode.startswith("🛡️"):
                    res = sum_df.sort_values(['is_defense', 'reach_pct'], ascending=[False, False]).head(30)
                else:
                    res = sum_df.sort_values('reach_pct', ascending=False).head(30)
                
            if res.empty: st.warning("現在の相場に、標的は存在しません。")
            else:
                st.success(f"🎯 スキャン完了: {len(res)} 銘柄クリア")
                for _, r in res.iterrows():
                    st.divider()
                    c = str(r['Code']); n = r['CompanyName'] if not pd.isna(r.get('CompanyName')) else f"銘柄 {c[:-1]}"
                    
                    scale_val = str(r.get('Scale', ''))
                    if any(x in scale_val for x in ["Core30", "Large70", "Mid400"]):
                        badge = '<span style="background-color: #0d47a1; color: #ffffff; padding: 0.2rem 0.6rem; border-radius: 4px; font-size: 14px; margin-left: 10px; vertical-align: middle;">🏢 大型/中型 (推奨: 25%押し)</span>'
                    else:
                        badge = '<span style="background-color: #b71c1c; color: #ffffff; padding: 0.2rem 0.6rem; border-radius: 4px; font-size: 14px; margin-left: 10px; vertical-align: middle;">🚀 小型/新興 (推奨: 50%押し)</span>'
                    
                    st.markdown(f'<div style="display: flex; align-items: center; margin-bottom: 0.5rem;"><h3 style="font-size: clamp(16px, 5vw, 26px); font-weight: bold; margin: 0; white-space: nowrap; overflow: hidden; text-overflow: ellipsis;">{n} ({c[:-1]})</h3>{badge}</div>', unsafe_allow_html=True)
                    
                    if r['is_db']: st.success("🔥 【激熱(攻め)】三川（ダブルボトム）底打ち反転波形を検知！")
                    if r['is_defense']: st.info("🛡️ 【鉄壁(守り)】下値支持線(サポート)に極接近。損切りリスクが極小の安全圏です。")
                        
                    cc1, cc2, cc3, cc4 = st.columns([1, 1, 1.8, 0.8])
                    cc1.metric("最新終値", f"{int(r['lc'])}円")
                    cc2.metric("🎯 買値目標", f"{int(r['bt'])}円")
                    
                    sl5 = int(r['bt'] * 0.95); sl8 = int(r['bt'] * 0.92); sl15 = int(r['bt'] * 0.85)
                    html_sell = f"""<div style="font-family: sans-serif; padding-top: 0.2rem;">
                        <div style="font-size: 14px; color: rgba(250, 250, 250, 0.6); padding-bottom: 0.1rem;">🎯 売値目標 ＆ 🛡️ 損切目安</div>
                        <div style="font-size: 16px;">
                            <span style="display: inline-block; width: 2.5em;">20%</span> {int(r['tp20']):,}円<br>
                            <span style="display: inline-block; width: 2.5em;">15%</span> {int(r['tp15']):,}円 <span style="color: rgba(250, 250, 250, 0.3); margin: 0 4px;">|</span> <span style="display: inline-block; width: 2.8em; color: #ef5350;">-5%</span> <span style="color: #ef5350;">{sl5:,}円</span><br>
                            <span style="display: inline-block; width: 2.5em;">10%</span> {int(r['tp10']):,}円 <span style="color: rgba(250, 250, 250, 0.3); margin: 0 4px;">|</span> <span style="display: inline-block; width: 2.8em; color: #ef5350;">-8%</span> <span style="color: #ef5350;">{sl8:,}円</span><br>
                            <span style="display: inline-block; width: 2.5em;">5%</span> {int(r['tp5']):,}円 <span style="color: rgba(250, 250, 250, 0.3); margin: 0 4px;">|</span> <span style="display: inline-block; width: 2.8em; color: #ef5350;">-15%</span> <span style="color: #ef5350;">{sl15:,}円</span>
                        </div>
                    </div>"""
                    cc3.markdown(html_sell, unsafe_allow_html=True)
                    cc4.metric("到達度", f"{r['reach_pct']:.1f}%")
                    
                    st.caption(f"🏢 {r.get('Market','不明')} ｜ 🏭 {r.get('Sector','不明')} ｜ ⏱️ 高値からの経過日数: {int(r['d_high'])}日")
                    
                    raw_s = get_single_data(c, 1)
                    if raw_s:
                        hist = clean_df(pd.DataFrame(raw_s))
                        draw_chart(hist, r['bt'], r['tp5'], r['tp10'], r['tp15'], r['tp20'])
                    else:
                        hist = df[df['Code'] == c].sort_values('Date').tail(30)
                        if not hist.empty: draw_chart(hist, r['bt'], r['tp5'], r['tp10'], r['tp15'], r['tp20'])

with tab2:
    st.markdown('<h3 style="font-size: clamp(14px, 4.5vw, 24px); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; margin-bottom: 1rem;">🎯 局地戦（複数・個別スキャン）</h3>', unsafe_allow_html=True)
    st.caption("※指定された銘柄すべての押し目ラインを計算し、戦術モードに応じてソートします。")
    col_s1, col_s2 = st.columns([1, 2])
    
    T2_FILE = "saved_t2_codes.txt"
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
                        if not df_s.empty and len(df_s) >= 14:
                            df_30 = df_s.tail(30); df_14 = df_s.tail(14); df_past = df_s[~df_s.index.isin(df_30.index)]
                            h14 = df_14['AdjH'].max(); l14 = df_14['AdjL'].min(); lc = df_s['AdjC'].iloc[-1]
                            idxmax = df_14['AdjH'].idxmax(); h_date = df_14.loc[idxmax, 'Date']
                            d_high = len(df_14[df_14['Date'] > h_date])
                            l30 = df_30['AdjL'].min() if not df_30.empty else np.nan
                            omax = df_past['AdjH'].max() if not df_past.empty else np.nan
                            omin = df_past['AdjL'].min() if not df_past.empty else np.nan
                            
                            bt_single = h14 - ((h14 - l14) * (push_r / 100.0))
                            tp5_s = bt_single * 1.05; tp10_s = bt_single * 1.10; tp15_s = bt_single * 1.15; tp20_s = bt_single * 1.20
                            
                            denom_s = h14 - bt_single
                            reach_s = ((h14 - lc) / denom_s * 100) if denom_s > 0 else 0
                            
                            r14 = h14 / l14 if l14 > 0 else 0
                            r30 = lc / l30 if pd.notna(l30) and l30 > 0 else 0
                            ldrop = ((lc / omax) - 1) * 100 if pd.notna(omax) and omax > 0 else 0
                            lrise = lc / omin if pd.notna(omin) and omin > 0 else 0
                            
                            is_dt = check_double_top(df_30)
                            is_hs = check_head_shoulders(df_30)
                            is_db = check_double_bottom(df_30)
                            is_defense = (not is_dt) and (not is_hs) and (lc <= (l14 * 1.03))
                            
                            c_name = f"銘柄 {c}"; c_market = "不明"; c_sector = "不明"; c_scale = ""
                            if not master_df.empty:
                                m_row = master_df[master_df['Code'] == c + "0"]
                                if not m_row.empty:
                                    c_name = m_row.iloc[0]['CompanyName']; c_market = m_row.iloc[0]['Market']; c_sector = m_row.iloc[0]['Sector']; c_scale = m_row.iloc[0].get('Scale', '')
                            
                            score_list = [
                                lc >= f1_min, r30 <= f2_m30, ldrop >= f3_drop,
                                (lrise <= f4_mlong) or (lrise == 0),
                                (f9_min14 <= r14 <= f9_max14), d_high <= limit_d, 
                                (lc <= (bt_single * 1.05)) and (lc >= (bt_single * 0.85)) # 下限バリアの追加
                            ]
                            if f5_ipo:
                                old_c = get_old_codes()
                                if old_c: score_list.append((c + "0") in old_c)
                            if f6_risk: score_list.append(not bool(re.search("疑義|重要事象", str(c_name))))
                            
                            if f7_ex_etf:
                                is_etf = (c_sector == '-') or bool(re.search("ETF|投信|ブル|ベア|REIT|ﾘｰﾄ", str(c_name), re.IGNORECASE))
                                score_list.append(not is_etf)
                            if f8_ex_bio:
                                score_list.append(c_sector != '医薬品')
                                
                            score_list.append(not is_dt and not is_hs)
                            
                            rule_pct = (sum(score_list) / len(score_list)) * 100
                            results.append({'Code': c, 'Name': c_name, 'Market': c_market, 'Sector': c_sector, 'Scale': c_scale, 'lc': lc, 'bt': bt_single, 'tp5': tp5_s, 'tp10': tp10_s, 'tp15': tp15_s, 'tp20': tp20_s, 'h14': h14, 'reach_pct': reach_s, 'rule_pct': rule_pct, 'passed': sum(score_list), 'total': len(score_list), 'is_dt': is_dt, 'is_hs': is_hs, 'is_db': is_db, 'is_defense': is_defense})
                            charts_data[c] = (df_s, bt_single, tp5_s, tp10_s, tp15_s, tp20_s)
                
                if results:
                    res_df = pd.DataFrame(results)
                    if tactics_mode.startswith("⚔️"):
                        res_df = res_df.sort_values(['is_db', 'rule_pct', 'reach_pct'], ascending=[False, False, False])
                    elif tactics_mode.startswith("🛡️"):
                        res_df = res_df.sort_values(['is_defense', 'rule_pct', 'reach_pct'], ascending=[False, False, False])
                    else:
                        res_df = res_df.sort_values(['rule_pct', 'reach_pct'], ascending=[False, False])
                        
                    st.success(f"🎯 {len(res_df)} 銘柄の局地戦スキャン完了（モード: {tactics_mode.split()[0]}）")
                    for _, r in res_df.iterrows():
                        st.divider()
                        
                        scale_val = str(r.get('Scale', ''))
                        if any(x in scale_val for x in ["Core30", "Large70", "Mid400"]):
                            badge = '<span style="background-color: #0d47a1; color: #ffffff; padding: 0.2rem 0.6rem; border-radius: 4px; font-size: 14px; margin-left: 10px; vertical-align: middle;">🏢 大型/中型 (推奨: 25%押し)</span>'
                        else:
                            badge = '<span style="background-color: #b71c1c; color: #ffffff; padding: 0.2rem 0.6rem; border-radius: 4px; font-size: 14px; margin-left: 10px; vertical-align: middle;">🚀 小型/新興 (推奨: 50%押し)</span>'
                        
                        st.markdown(f'<div style="display: flex; align-items: center; margin-bottom: 0.5rem;"><h3 style="font-size: clamp(16px, 5vw, 26px); font-weight: bold; margin: 0; white-space: nowrap; overflow: hidden; text-overflow: ellipsis;">{r["Name"]} ({r["Code"]})</h3>{badge}</div>', unsafe_allow_html=True)
                        
                        if r['is_dt'] or r['is_hs']: st.error("🚨 【警告】相場転換の危険波形（三尊/Wトップ）を検知！ 撤退推奨。")
                        if r['is_db']: st.success("🔥 【激熱(攻め)】三川（ダブルボトム）底打ち反転波形を検知！")
                        if r['is_defense']: st.info("🛡️ 【鉄壁(守り)】下値支持線(サポート)に極接近。損切りリスクが極小の安全圏です。")
                            
                        sc1, sc2, sc3, sc4, sc5 = st.columns([1, 1, 1.8, 0.8, 0.8])
                        sc1.metric("最新終値", f"{int(r['lc'])}円")
                        sc2.metric(f"🎯 買値目標", f"{int(r['bt'])}円")
                        
                        sl5 = int(r['bt'] * 0.95); sl8 = int(r['bt'] * 0.92); sl15 = int(r['bt'] * 0.85)
                        html_sell = f"""<div style="font-family: sans-serif; padding-top: 0.2rem;">
                            <div style="font-size: 14px; color: rgba(250, 250, 250, 0.6); padding-bottom: 0.1rem;">🎯 売値目標 ＆ 🛡️ 損切目安</div>
                            <div style="font-size: 16px;">
                                <span style="display: inline-block; width: 2.5em;">20%</span> {int(r['tp20']):,}円<br>
                                <span style="display: inline-block; width: 2.5em;">15%</span> {int(r['tp15']):,}円 <span style="color: rgba(250, 250, 250, 0.3); margin: 0 4px;">|</span> <span style="display: inline-block; width: 2.8em; color: #ef5350;">-5%</span> <span style="color: #ef5350;">{sl5:,}円</span><br>
                                <span style="display: inline-block; width: 2.5em;">10%</span> {int(r['tp10']):,}円 <span style="color: rgba(250, 250, 250, 0.3); margin: 0 4px;">|</span> <span style="display: inline-block; width: 2.8em; color: #ef5350;">-8%</span> <span style="color: #ef5350;">{sl8:,}円</span><br>
                                <span style="display: inline-block; width: 2.5em;">5%</span> {int(r['tp5']):,}円 <span style="color: rgba(250, 250, 250, 0.3); margin: 0 4px;">|</span> <span style="display: inline-block; width: 2.8em; color: #ef5350;">-15%</span> <span style="color: #ef5350;">{sl15:,}円</span>
                            </div>
                        </div>"""
                        sc3.markdown(html_sell, unsafe_allow_html=True)
                        sc4.metric("到達度", f"{r['reach_pct']:.1f}%")
                        sc5.metric("掟達成率", f"{r['rule_pct']:.0f}%")
                        
                        st.caption(f"🏢 {r['Market']} ｜ 🏭 {r['Sector']} ｜ ⏱️ 直近14日高値: {int(r['h14'])}円 ｜ 🛡️ 掟クリア状況: {r['passed']} / {r['total']} 条件")
                        df_chart, bt_chart, tp5_c, tp10_c, tp15_c, tp20_c = charts_data[r['Code']]
                        draw_chart(df_chart, bt_chart, tp5_c, tp10_c, tp15_c, tp20_c)

with tab3:
    st.markdown('<h3 style="font-size: clamp(14px, 4.5vw, 24px); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; margin-bottom: 1rem;">📉 鉄の掟：一括バックテスト</h3>', unsafe_allow_html=True)
    col_1, col_2 = st.columns([1, 2])
    
    T3_FILE = "saved_t3_codes.txt"
    default_t3 = "6614, 3997, 4935"
    if os.path.exists(T3_FILE):
        with open(T3_FILE, "r", encoding="utf-8") as f:
            default_t3 = f.read()

    with col_1: 
        bt_c_in = st.text_area("銘柄コード（複数可）", value=default_t3, height=100)
        run_bt = st.button("🔥 一括バックテスト")
        
    with col_2:
        st.caption("⚙️ パラメーター")
        
        bt_mode = st.radio(
            "戦術モード (波形認識)", 
            ["⚖️ バランス (指定%落ちで指値買い)", "⚔️ 攻め重視 (三川・反発確認で成行買い)"], 
            key="bt_mode_radio",
            on_change=apply_market_preset,
            help="戦術モードを切り替えた際も、左サイドバーで選択中の「対象市場プリセット」へパラメーターが自動復元されます。"
        )
        
        cc_1, cc_2 = st.columns(2)
        bt_push = cc_1.number_input("① 押し目 (%)", step=5, key="bt_push")
        bt_buy_d = cc_1.number_input("② 買い期限 (日)", step=1, key="bt_buy_d")
        bt_tp = cc_1.number_input("③ 利確 (+%)", step=1, key="bt_tp")
        bt_lot = cc_1.number_input("⑦ 株数(基本100)", step=100, key="bt_lot")
        
        bt_sl_i = cc_2.number_input("④ 損切/ザラ場(-%)", step=1, key="bt_sl_i")
        bt_sl_c = cc_2.number_input("⑤ 損切/終値(-%)", step=1, key="bt_sl_c")
        bt_sell_d = cc_2.number_input("⑥ 売り期限 (日)", step=1, key="bt_sell_d")

    if run_bt and bt_c_in:
        with open(T3_FILE, "w", encoding="utf-8") as f:
            f.write(bt_c_in)
            
        t_codes = list(dict.fromkeys([c.upper() for c in re.findall(r'(?<![a-zA-Z0-9])[a-zA-Z0-9]{4}(?![a-zA-Z0-9])', bt_c_in)]))
        
        if not t_codes: st.warning("有効なコードが見つかりません。")
        else:
            all_t = []; b_bar = st.progress(0, "仮想売買中...")
            for idx, c in enumerate(t_codes):
                raw = get_single_data(c + "0", 1)
                if raw:
                    df = clean_df(pd.DataFrame(raw)).dropna(subset=['AdjO', 'AdjH', 'AdjL', 'AdjC']).reset_index(drop=True)
                    pos = None
                    for i in range(30, len(df)):
                        td = df.iloc[i]
                        if pos is None:
                            win_14 = df.iloc[i-14:i]
                            win_30 = df.iloc[i-30:i]
                            rh = win_14['AdjH'].max(); rl = win_14['AdjL'].min()
                            
                            if pd.isna(rh) or pd.isna(rl) or rl == 0: continue
                            
                            idxmax = win_14['AdjH'].idxmax()
                            h_d = len(win_14[win_14['Date'] > win_14.loc[idxmax, 'Date']])
                            r14 = rh / rl if rl > 0 else 0
                            
                            if (1.3 <= r14 <= 2.0) and (h_d <= bt_buy_d):
                                is_dt = check_double_top(win_30)
                                is_hs = check_head_shoulders(win_30)
                                if is_dt or is_hs:
                                    continue 
                                
                                if "攻め" in bt_mode:
                                    is_db = check_double_bottom(win_30)
                                    if is_db:
                                        exec_p = td['AdjO']
                                        pos = {'b_i': i, 'b_d': td['Date'], 'b_p': exec_p, 'h': rh}
                                else:
                                    targ = rh - ((rh - rl) * (bt_push / 100))
                                    if td['AdjL'] <= targ:
                                        exec_p = min(td['AdjO'], targ)
                                        pos = {'b_i': i, 'b_d': td['Date'], 'b_p': exec_p, 'h': rh}
                        else:
                            bp = round(pos['b_p'], 1); held = i - pos['b_i']; sp = 0; rsn = ""
                            sl_i = bp * (1 - (bt_sl_i / 100)); tp = bp * (1 + (bt_tp / 100)); sl_c = bp * (1 - (bt_sl_c / 100))
                            
                            if td['AdjL'] <= sl_i: sp = min(td['AdjO'], sl_i); rsn = f"損切(ザ場-{bt_sl_i}%)"
                            elif td['AdjH'] >= tp: sp = max(td['AdjO'], tp); rsn = f"利確(+{bt_tp}%)"
                            elif td['AdjC'] <= sl_c: sp = td['AdjC']; rsn = f"損切(終値-{bt_sl_c}%)"
                            elif held >= bt_sell_d: sp = td['AdjC']; rsn = f"時間切れ({bt_sell_d}日)"
                            
                            if rsn:
                                sp = round(sp, 1); p_pct = round(((sp / bp) - 1) * 100, 2); p_amt = int((sp - bp) * bt_lot)
                                all_t.append({'銘柄': c, '購入日': pos['b_d'].strftime('%Y-%m-%d'), '決済日': td['Date'].strftime('%Y-%m-%d'), '保有日数': held, '買値(円)': bp, '売値(円)': sp, '損益(%)': p_pct, '損益額(円)': p_amt, '決済理由': rsn})
                                pos = None
                b_bar.progress((idx + 1) / len(t_codes)); time.sleep(0.5)
            b_bar.empty(); st.success("シミュレーション完了")
            if not all_t: st.warning("シグナル点灯はありませんでした。")
            else:
                tdf = pd.DataFrame(all_t); tot = len(tdf); wins = len(tdf[tdf['損益額(円)'] > 0])
                n_prof = tdf['損益額(円)'].sum(); sprof = tdf[tdf['損益額(円)'] > 0]['損益額(円)'].sum(); sloss = abs(tdf[tdf['損益額(円)'] <= 0]['損益額(円)'].sum())
                pf = round(sprof / sloss, 2) if sloss > 0 else 'inf'
                st.markdown(f'<h3 style="font-size: clamp(16px, 5vw, 26px); font-weight: bold; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; margin-bottom: 1rem;">💰 総合利益額: {n_prof:,} 円</h3>', unsafe_allow_html=True)
                m1, m2, m3, m4 = st.columns(4)
                m1.metric("トレード回数", f"{tot} 回"); m2.metric("勝率", f"{round((wins/tot)*100,1)} %")
                m3.metric("平均損益額", f"{int(n_prof/tot):,} 円"); m4.metric("PF", f"{pf}")
                st.dataframe(tdf, use_container_width=True)
