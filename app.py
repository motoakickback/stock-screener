import streamlit as st
import requests
import pandas as pd
import time
import os
import re
from datetime import datetime, timedelta
from io import BytesIO
import plotly.graph_objects as go

# --- 1. ページ設定 ---
st.set_page_config(page_title="J-Quants 戦略スクリーナー (V11.2)", layout="wide")
st.title("🛡️ J-Quants 戦略アドバイザー (V11.2)")

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
    """直近30営業日 ＋ 半年前 ＋ 1年前のデータを高速取得"""
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
        time.sleep(0.5) # Lightプラン用の高速通信
    p_bar.empty()
    return all_rows

# --- 4. 描画モジュール ---
def draw_candlestick(df, target_price):
    fig = go.Figure()
    fig.add_trace(go.Candlestick(
        x=df['Date'], open=df['AdjO'], high=df['AdjH'], low=df['AdjL'], close=df['AdjC'],
        name='株価', increasing_line_color='#ef5350', decreasing_line_color='#26a69a'
    ))
    fig.add_trace(go.Scatter(
        x=df['Date'], y=[target_price]*len(df),
        mode='lines', name='買値目標(55%押)', line=dict(color='#FFD700', width=2, dash='dash')
    ))
    fig.update_layout(
        height=320, margin=dict(l=0, r=0, t=10, b=0), xaxis_rangeslider_visible=False,
        paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)', hovermode="x unified"
    )
    st.plotly_chart(fig, use_container_width=True)


# --- 5. UI構築 ---
tab1, tab2 = st.tabs(["🚀 実戦（スクリーナー）", "🔬 訓練（バックテスト）"])

master_df = load_brand_master()

with tab1:
    st.markdown("### 🌐 ボスの「鉄の掟」全銘柄スクリーニング")
    run_full_scan = st.button("🚀 最新データで全軍スキャン開始")
    
    st.sidebar.header("🔍 スクリーニング条件調整")
    f3_drop_rate = st.sidebar.number_input("③ 半年〜1年の下落除外 (基準%)", value=-30, step=5)
    f4_long_peak = st.sidebar.checkbox("④ 3波上げ切り除外 (今回は⑦の2倍上限で担保)", value=True)
    f5_ipo = st.sidebar.checkbox("⑤ IPO除外 (上場1年未満)", value=True)
    f6_risk = st.sidebar.checkbox("⑥ 疑義注記銘柄を除外", value=True)

    if run_full_scan:
        raw_data = get_historical_data_for_screening()
        if not raw_data:
            st.error("データの取得に失敗しました。")
        else:
            df = clean_dataframe(pd.DataFrame(raw_data))
            
            def calc_metrics(g):
                g = g.sort_values('Date')
                # 過去の特定日データ（半年・1年前）
                past_dates = g.head(2) 
                # 直近30営業日
                recent_30 = g.tail(30)
                recent_14 = recent_30.tail(14)
                
                if len(recent_14) == 0: return pd.Series(dtype=float)
                
                latest_close = recent_14['AdjC'].iloc[-1]
                recent_14_high = recent_14['AdjH'].max()
                recent_14_low = recent_14['AdjL'].min()
                recent_30_low = recent_30['AdjL'].min()
                
                # 高値からの経過日数
                high_date = recent_14.loc[recent_14['AdjH'].idxmax(), 'Date']
                days_since_high = len(recent_14[recent_14['Date'] > high_date])
                
                # 上げ幅の55%押し
                upward_range = recent_14_high - recent_14_low
                buy_target = recent_14_high - (upward_range * 0.55)
                
                # 長期下落判定（1年前・半年前からの下落率）
                long_term_drop = 0
                if len(past_dates) > 0:
                    old_max = past_dates['AdjH'].max()
                    if old_max > 0: long_term_drop = ((latest_close / old_max) - 1) * 100
                
                return pd.Series({
                    'latest_close': latest_close,
                    'recent_14_high': recent_14_high,
                    'recent_14_low': recent_14_low,
                    'recent_30_low': recent_30_low,
                    'buy_target': buy_target,
                    'days_since_high': days_since_high,
                    'ratio_14d': recent_14_high / recent_14_low if recent_14_low > 0 else 0,
                    'ratio_30d': latest_close / recent_30_low if recent_30_low > 0 else 0,
                    'long_term_drop': long_term_drop
                })

            with st.spinner("全4000銘柄に鉄の掟を執行中..."):
                summary = df.groupby('Code').apply(calc_metrics).reset_index()
                if not master_df.empty: summary = pd.merge(summary, master_df, on='Code', how='left')
                
                # --- ピックアップルール執行 ---
                summary = summary[summary['latest_close'] >= 200] # ① 200円未満除外
                summary = summary[summary['ratio_30d'] < 2.0] # ② 1ヶ月2倍暴騰除外
                summary = summary[summary['long_term_drop'] > f3_drop_rate] # ③ 長期大幅下落を除外
                
                if f5_ipo: # ⑤ IPO除外
                    old_codes = get_old_codes()
                    if old_codes: summary = summary[summary['Code'].isin(old_codes)]
                
                if f6_risk and 'CompanyName' in summary.columns: # ⑥ 疑義注記除外
                    summary = summary[~summary['CompanyName'].astype(str).str.contains("疑義|重要事象", na=False)]
                
                # ⑦ 14日以内の安値から1.3～2倍暴騰
                summary = summary[(summary['ratio_14d'] >= 1.3) & (summary['ratio_14d'] <= 2.0)]
                
                # 買いルール②：高値から4日以内
                summary = summary[summary['days_since_high'] <= 4]
                
                # 現在値が買値ターゲット付近（+5%以内）まで落ちているものを抽出
                summary = summary[summary['latest_close'] <= (summary['buy_target'] * 1.05)]
                
                results = summary.sort_values('latest_close', ascending=False).head(30)
                
            if results.empty:
                st.warning("現在の相場に、ボスの全規律を満たす標的（ターゲット）は存在しません。")
            else:
                st.success(f"審査完了: {len(results)} 銘柄が鉄の掟をクリアしました。")
                for _, row in results.iterrows():
                    st.divider()
                    code = str(row['Code'])
                    name = row['CompanyName'] if not pd.isna(row.get('CompanyName')) else f"銘柄 {code[:-1]}"
                    st.subheader(f"{name} ({code[:-1]})")
                    
                    c1, c2, c3 = st.columns(3)
                    c1.metric("最新終値", f"{int(row['latest_close'])}円")
                    c2.metric("🎯 買値目標(55%押)", f"{int(row['buy_target'])}円")
                    c3.metric("高値からの日数", f"{int(row['days_since_high'])}日")

                    hist = df[df['Code'] == row['Code']].sort_values('Date').tail(14)
                    if not hist.empty: draw_candlestick(hist, row['buy_target'])

# ==========================================
# タブ2: 訓練（バックテストエンジン V11.2）
# ==========================================
with tab2:
    st.markdown("### 📉 鉄の掟：3年間 完全一致シミュレーション")
    col1, col2 = st.columns([1, 2])
    with col1:
        bt_code = st.text_input("検証する銘柄コード（4桁）", value="6614", max_chars=4, key="bt_code")
        run_bt = st.button("🔥 バックテストを実行")
        
    with col2:
        st.caption("⚙️ 買いルール / 売りルール パラメーター")
        c2_1, c2_2 = st.columns(2)
        with c2_1:
            push_rate = st.number_input("① 上げ幅に対する押し目 (%)", value=55, step=5)
            buy_limit_days = st.number_input("② 買い期限 (高値から何日以内)", value=4, step=1)
            tp_rate = st.number_input("③ 利益確定 (買値からの上昇率 %)", value=8, step=1)
        with c2_2:
            sl_intra_rate = st.number_input("④ 損切/ザラ場 (買値から下落 %)", value=10, step=1)
            sl_close_rate = st.number_input("⑤ 損切/終値 (買値から下落 %)", value=8, step=1)
            sell_limit_days = st.number_input("⑥ 売り期限 (購入から何日経過)", value=5, step=1)

    if run_bt and bt_code:
        code_with_suffix = bt_code + "0"
        with st.spinner(f"銘柄 {bt_code} の過去3年分のデータを抽出し、仮想売買を実行中..."):
            raw_data = get_single_stock_data(code_with_suffix, years=3)
            
            if not raw_data:
                st.error("データの取得に失敗しました。")
            else:
                df = clean_dataframe(pd.DataFrame(raw_data))
                trades = []
                position = None
                
                for i in range(14, len(df)):
                    today_data = df.iloc[i]
                    
                    if position is None:
                        # --- 買いの判定 ---
                        window = df.iloc[i-14 : i] 
                        recent_high = window['AdjH'].max()
                        recent_low = window['AdjL'].min()
                        high_date = window.loc[window['AdjH'].idxmax(), 'Date']
                        days_since_high = len(window[window['Date'] > high_date])
                        
                        # ピックアップ⑦: 1.3〜2倍の暴騰確認
                        ratio_14d = recent_high / recent_low if recent_low > 0 else 0
                        
                        if (1.3 <= ratio_14d <= 2.0) and (days_since_high <= buy_limit_days):
                            # 真の掟: 上げ幅の55%押し
                            upward_range = recent_high - recent_low
                            buy_target = recent_high - (upward_range * (push_rate / 100))
                            
                            if today_data['AdjL'] <= buy_target:
                                exec_price = min(today_data['AdjO'], buy_target)
                                position = {
                                    'buy_idx': i,
                                    'buy_date': today_data['Date'],
                                    'buy_price': exec_price,
                                    'high_ref': recent_high
                                }
                    else:
                        # --- 売りの判定 ---
                        buy_price = position['buy_price']
                        days_held = i - position['buy_idx']
                        sell_price, reason = 0, ""
                        
                        sl_intraday = buy_price * (1 - (sl_intra_rate / 100))
                        tp_target = buy_price * (1 + (tp_rate / 100))
                        sl_close = buy_price * (1 - (sl_close_rate / 100))
                        
                        if today_data['AdjL'] <= sl_intraday:
                            sell_price = min(today_data['AdjO'], sl_intraday)
                            reason = f"損切(ザラ場 -{sl_intra_rate}%)"
                        elif today_data['AdjH'] >= tp_target:
                            sell_price = max(today_data['AdjO'], tp_target)
                            reason = f"利確(+{tp_rate}%)"
                        elif today_data['AdjC'] <= sl_close:
                            sell_price = today_data['AdjC']
                            reason = f"損切(終値 -{sl_close_rate}%)"
                        elif days_held >= sell_limit_days:
                            sell_price = today_data['AdjC']
                            reason = f"時間切れ({sell_limit_days}日経過)"
                            
                        if reason != "":
                            profit_pct = (sell_price / buy_price) - 1
                            trades.append({
                                '購入日': position['buy_date'].strftime('%Y-%m-%d'),
                                '決済日': today_data['Date'].strftime('%Y-%m-%d'),
                                '保有日数': days_held,
                                '買値': round(buy_price, 1),
                                '売値': round(sell_price, 1),
                                '損益(%)': round(profit_pct * 100, 2),
                                '決済理由': reason
                            })
                            position = None 
                
                st.success("仮想売買シミュレーション完了")
                if len(trades) == 0:
                    st.warning(f"指定された厳格な条件では、過去3年間で銘柄 {bt_code} にシグナルは点灯しませんでした。")
                else:
                    tdf = pd.DataFrame(trades)
                    total_trades = len(tdf)
                    wins = len(tdf[tdf['損益(%)'] > 0])
                    win_rate = (wins / total_trades) * 100
                    sum_profit = tdf[tdf['損益(%)'] > 0]['損益(%)'].sum()
                    sum_loss = abs(tdf[tdf['損益(%)'] <= 0]['損益(%)'].sum())
                    pf = (sum_profit / sum_loss) if sum_loss > 0 else float('inf')
                    
                    m1, m2, m3, m4 = st.columns(4)
                    m1.metric("総トレード回数", f"{total_trades} 回")
                    m2.metric("勝率", f"{round(win_rate, 1)} %")
                    m3.metric("平均損益", f"{round(tdf['損益(%)'].mean(), 2)} %")
                    m4.metric("ﾌﾟﾛﾌｨｯﾄﾌｧｸﾀｰ", f"{round(pf, 2)}")
                    
                    st.divider()
                    st.markdown("#### 📜 全取引履歴")
                    st.dataframe(tdf, use_container_width=True)
