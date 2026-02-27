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

# --- 1. ページ設定 ---
st.set_page_config(page_title="J-Quants 戦略スクリーナー (V11.6)", layout="wide")
st.title("🛡️ J-Quants 戦略アドバイザー (V11.6)")

# --- 2. 認証情報 ---
API_KEY = st.secrets["JQUANTS_API_KEY"].strip()
headers = {"x-api-key": API_KEY}
BASE_URL = "https://api.jquants.com/v2"

# --- 3. 共通関数群 ---
def clean_dataframe(df):
    rename_cols = {
        'AdjustmentOpen': 'AdjO', 'AdjustmentHigh': 'AdjH',
        'AdjustmentLow': 'AdjL', 'AdjustmentClose': 'AdjC',
        'Open': 'AdjO', 'High': 'AdjH', 'Low': 'AdjL', 'Close': 'AdjC'
    }
    df = df.rename(columns=rename_cols)
    for col in ['AdjO', 'AdjH', 'AdjL', 'AdjC']:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors='coerce')
    if 'Date' in df.columns:
        df['Date'] = pd.to_datetime(df['Date'])
        df = df.sort_values('Date').reset_index(drop=True)
    return df

@st.cache_data(ttl=86400)
def load_brand_master():
    try:
        req_headers = {'User-Agent': 'Mozilla/5.0'}
        page_url = "https://www.jpx.co.jp/markets/statistics-equities/misc/01.html"
        page_res = requests.get(page_url, headers=req_headers, timeout=10)
        match = re.search(r'href="([^"]+data_j\.xls)"', page_res.text)
        if match:
            excel_url = "https://www.jpx.co.jp" + match.group(1)
            res = requests.get(excel_url, headers=req_headers, timeout=15)
            df = pd.read_excel(BytesIO(res.content), engine='xlrd')
            df = df[['コード', '銘柄名', '33業種区分', '市場・商品区分']]
            df.columns = ['Code', 'CompanyName', 'Sector', 'Market']
            df['Code'] = df['Code'].astype(str) + "0"
            return df
    except: pass
    return pd.DataFrame()

@st.cache_data(ttl=86400)
def get_old_codes():
    base_date = datetime.utcnow() + timedelta(hours=9) - timedelta(days=365)
    for i in range(7):
        target_date = (base_date - timedelta(days=i)).strftime('%Y%m%d')
        for version in ["v2", "v1"]:
            try:
                res = requests.get(f"https://api.jquants.com/{version}/listed/info?date={target_date}", headers=headers, timeout=10)
                if res.status_code == 200:
                    data = res.json().get("info", [])
                    if data: return pd.DataFrame(data)['Code'].astype(str).tolist()
            except: pass
    return []

@st.cache_data(ttl=3600)
def get_single_stock_data(code, years=3):
    base_date = datetime.utcnow() + timedelta(hours=9)
    from_date = (base_date - timedelta(days=365 * years)).strftime('%Y%m%d')
    to_date = base_date.strftime('%Y%m%d')
    url = f"{BASE_URL}/equities/bars/daily?code={code}&from={from_date}&to={to_date}"
    try:
        res = requests.get(url, headers=headers, timeout=15)
        if res.status_code == 200: return res.json().get("data", [])
    except: pass
    return []

@st.cache_data(ttl=3600)
def get_historical_data_for_screening():
    base_date = datetime.utcnow() + timedelta(hours=9)
    target_dates = []
    days_count = 0
    while len(target_dates) < 30:
        d = base_date - timedelta(days=days_count)
        if d.weekday() < 5: target_dates.append(d.strftime('%Y%m%d'))
        days_count += 1
    
    d_half = base_date - timedelta(days=180)
    while d_half.weekday() >= 5: d_half -= timedelta(days=1)
    target_dates.append(d_half.strftime('%Y%m%d'))
    
    d_year = base_date - timedelta(days=365)
    while d_year.weekday() >= 5: d_year -= timedelta(days=1)
    target_dates.append(d_year.strftime('%Y%m%d'))
    
    all_rows = []
    p_bar = st.progress(0, text="最新の相場データを取得中...")
    for i, d in enumerate(target_dates):
        url = f"{BASE_URL}/equities/bars/daily?date={d}"
        try:
            res = requests.get(url, headers=headers, timeout=10)
            if res.status_code == 200: all_rows.extend(res.json().get("data", []))
        except: pass
        p_bar.progress((i + 1) / len(target_dates))
        time.sleep(0.5)
    p_bar.empty()
    return all_rows

def draw_candlestick(df, target_price):
    fig = go.Figure()
    fig.add_trace(go.Candlestick(
        x=df['Date'], open=df['AdjO'], high=df['AdjH'], low=df['AdjL'], close=df['AdjC'],
        name='株価', increasing_line_color='#ef5350', decreasing_line_color='#26a69a'
    ))
    fig.add_trace(go.Scatter(
        x=df['Date'], y=[target_price]*len(df),
        mode='lines', name='買値目標(指定%押)', line=dict(color='#FFD700', width=2, dash='dash')
    ))
    fig.update_layout(
        height=320, margin=dict(l=0, r=0, t=10, b=0), xaxis_rangeslider_visible=False,
        paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)', hovermode="x unified"
    )
    st.plotly_chart(fig, use_container_width=True)

# --- 4. UI構築 ---
tab1, tab2 = st.tabs(["🚀 実戦（スクリーナー）", "🔬 訓練（一括バックテスト）"])
master_df = load_brand_master()

# ==========================================
# タブ1: 実戦（スクリーナー）
# ==========================================
with tab1:
    st.markdown("### 🌐 ボスの「鉄の掟」全銘柄スクリーニング")
    run_full_scan = st.button("🚀 最新データで全軍スキャン開始")
    
    st.sidebar.header("🔍 ピックアップルール (①〜⑦)")
    f1_min_price = st.sidebar.number_input("① 株価下限 (円)", value=200, step=100)
    f2_max_30d_ratio = st.sidebar.number_input("② 1ヶ月以内の暴騰上限 (倍)", value=2.0, step=0.1)
    f3_drop_rate = st.sidebar.number_input("③ 半年〜1年の下落除外 (基準%)", value=-30, step=5)
    f4_max_long_ratio = st.sidebar.number_input("④ 上げ切り除外 (過去からの上昇倍率)", value=3.0, step=0.5)
    f5_ipo = st.sidebar.checkbox("⑤ IPO除外 (上場1年未満)", value=True)
    f6_risk = st.sidebar.checkbox("⑥ 疑義注記銘柄を除外", value=True)
    
    st.sidebar.caption("⑦ 14日以内の初動暴騰条件")
    c_f7_1, c_f7_2 = st.sidebar.columns(2)
    with c_f7_1:
        f7_min_14d_ratio = st.number_input("下限 (倍)", value=1.3, step=0.1)
    with c_f7_2:
        f7_max_14d_ratio = st.number_input("上限 (倍)", value=2.0, step=0.1)

    st.sidebar.header("🎯 買いルール")
    scr_push_rate = st.sidebar.number_input("① 上げ幅に対する押し目 (%)", value=50, step=5)
    scr_buy_limit_days = st.sidebar.number_input("② 買い期限 (高値から何日以内)", value=4, step=1)

    if run_full_scan:
        raw_data = get_historical_data_for_screening()
        if not raw_data:
            st.error("データの取得に失敗しました。")
        else:
            df = clean_dataframe(pd.DataFrame(raw_data))
            
            def calc_metrics(g):
                # 【V11.6 修正】 エラー回避用の空の雛形を定義
                empty_res = pd.Series({
                    'latest_close': np.nan, 'recent_14_high': np.nan,
                    'recent_14_low': np.nan, 'recent_30_low': np.nan,
                    'buy_target': np.nan, 'days_since_high': np.nan,
                    'ratio_14d': np.nan, 'ratio_30d': np.nan,
                    'long_term_drop': np.nan, 'long_term_rise': np.nan
                })
                
                g = g.dropna(subset=['AdjC', 'AdjH', 'AdjL']).sort_values('Date')
                if len(g) < 14: return empty_res
                
                recent_30 = g.tail(30)
                recent_14 = recent_30.tail(14)
                
                idx_max = recent_14['AdjH'].idxmax()
                if pd.isna(idx_max): return empty_res
                
                past_dates = g.iloc[:-len(recent_30)] if len(g) > len(recent_30) else pd.DataFrame()
                
                latest_close = recent_14['AdjC'].iloc[-1]
                recent_14_high = recent_14['AdjH'].max()
                recent_14_low = recent_14['AdjL'].min()
                recent_30_low = recent_30['AdjL'].min()
                
                high_date = recent_14.loc[idx_max, 'Date']
                days_since_high = len(recent_14[recent_14['Date'] > high_date])
                
                upward_range = recent_14_high - recent_14_low
                buy_target = recent_14_high - (upward_range * (scr_push_rate / 100))
                
                long_term_drop = 0
                long_term_rise = 0
                if len(past_dates) > 0:
                    old_max = past_dates['AdjH'].max()
                    old_min = past_dates['AdjL'].min()
                    if pd.notna(old_max) and old_max > 0: long_term_drop = ((latest_close / old_max) - 1) * 100
                    if pd.notna(old_min) and old_min > 0: long_term_rise = latest_close / old_min
                
                return pd.Series({
                    'latest_close': latest_close, 'recent_14_high': recent_14_high,
                    'recent_14_low': recent_14_low, 'recent_30_low': recent_30_low,
                    'buy_target': buy_target, 'days_since_high': days_since_high,
                    'ratio_14d': recent_14_high / recent_14_low if recent_14_low > 0 else 0,
                    'ratio_30d': latest_close / recent_30_low if recent_30_low > 0 else 0,
                    'long_term_drop': long_term_drop, 'long_term_rise': long_term_rise
                })

            with st.spinner("全4000銘柄に鉄の掟を執行中..."):
                summary = df.groupby('Code').apply(calc_metrics).reset_index()
                
                # 安全なパージ処理
                if 'latest_close' in summary.columns:
                    summary = summary.dropna(subset=['latest_close'])
                else:
                    st.error("有効なデータを持つ銘柄が一つも見つかりませんでした。")
                    st.stop()
                
                if not master_df.empty: summary = pd.merge(summary, master_df, on='Code', how='left')
                
                # --- ピックアップルール執行 ---
                summary = summary[summary['latest_close'] >= f1_min_price] # ①
                summary = summary[summary['ratio_30d'] <= f2_max_30d_ratio] # ②
                summary = summary[summary['long_term_drop'] >= f3_drop_rate] # ③ (-30%より大きく下落しているものを除外)
                summary = summary[(summary['long_term_rise'] <= f4_max_long_ratio) | (summary['long_term_rise'] == 0)] # ④
                
                if f5_ipo: # ⑤
                    old_codes = get_old_codes()
                    if old_codes: summary = summary[summary['Code'].isin(old_codes)]
                if f6_risk and 'CompanyName' in summary.columns: # ⑥
                    summary = summary[~summary['CompanyName'].astype(str).str.contains("疑義|重要事象", na=False)]
                
                # ⑦ 14日以内の安値から指定倍率の暴騰
                summary = summary[(summary['ratio_14d'] >= f7_min_14d_ratio) & (summary['ratio_14d'] <= f7_max_14d_ratio)]
                
                # --- 買いルール執行 ---
                summary = summary[summary['days_since_high'] <= scr_buy_limit_days]
                summary = summary[summary['latest_close'] <= (summary['buy_target'] * 1.05)]
                
                results = summary.sort_values('latest_close', ascending=False).head(30)
                
            if results.empty:
                st.warning("現在の相場に、ボスの全規律を満たす標的は存在しません。")
            else:
                st.success(f"審査完了: {len(results)} 銘柄が鉄の掟をクリアしました。")
                for _, row in results.iterrows():
                    st.divider()
                    code = str(row['Code'])
                    name = row['CompanyName'] if not pd.isna(row.get('CompanyName')) else f"銘柄 {code[:-1]}"
                    st.subheader(f"{name} ({code[:-1]})")
                    c1, c2, c3 = st.columns(3)
                    c1.metric("最新終値", f"{int(row['latest_close'])}円")
                    c2.metric("🎯 買値目標(指定%押)", f"{int(row['buy_target'])}円")
                    c3.metric("高値からの日数", f"{int(row['days_since_high'])}日")
                    hist = df[df['Code'] == row['Code']].sort_values('Date').tail(14)
                    if not hist.empty: draw_candlestick(hist, row['buy_target'])

# ==========================================
# タブ2: 訓練（バックテストエンジン V11.6）
# ==========================================
with tab2:
    st.markdown("### 📉 鉄の掟：複数銘柄 一括検証 ＆ 損益算出")
    col1, col2 = st.columns([1, 2])
    with col1:
        bt_codes_input = st.text_area(
            "検証する銘柄コード（複数入力可：カンマやスペース、改行で区切る）", 
            value="6614, 3997, 4935", 
            height=100
        )
        run_bt = st.button("🔥 一括バックテストを実行")
        
    with col2:
        st.caption("⚙️ 買いルール / 売りルール パラメーター")
        c2_1, c2_2 = st.columns(2)
        with c2_1:
            push_rate = st.number_input("① 上げ幅に対する押し目 (%)", value=50, step=5)
            buy_limit_days = st.number_input("② 買い期限 (高値から何日以内)", value=4, step=1)
            tp_rate = st.number_input("③ 利益確定 (買値からの上昇率 %)", value=8, step=1)
            trade_lot = st.number_input("⑦ 1トレードの株数 (基本100株)", value=100, step=100)
        with c2_2:
            sl_intra_rate = st.number_input("④ 損切/ザラ場 (買値から下落 %)", value=10, step=1)
            sl_close_rate = st.number_input("⑤ 損切/終値 (買値から下落 %)", value=8, step=1)
            sell_limit_days = st.number_input("⑥ 売り期限 (購入から何日経過)", value=5, step=1
