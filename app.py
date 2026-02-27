import streamlit as st
import requests
import pandas as pd
import time
from datetime import datetime, timedelta

# --- 1. ページ設定 ---
st.set_page_config(page_title="J-Quants 戦略スクリーナー (V3)", layout="wide")
st.title("🛡️ J-Quants 戦略アドバイザー (V3)")

# --- 2. Secrets & Headers ---
API_KEY = st.secrets["JQUANTS_API_KEY"]
headers = {"x-api-key": API_KEY.strip()}

# --- 3. サイドバー設定（フィルター群） ---
st.sidebar.header("🔍 抽出条件")
min_price = st.sidebar.number_input("株価下限 (円)", value=1000, step=100)
exclude_ipo = st.sidebar.checkbox("IPO除外 (上場1年未満)", value=True)
only_buy_signal = st.sidebar.checkbox("買値目安(45%以下)のみ表示", value=False)
st.sidebar.info("Freeプラン制限回避のため、取得には約3分かかります。")

# --- 4. 銘柄詳細（名前・業種・上場日）取得 ---
@st.cache_data(ttl=86400)
def get_brand_info():
    url = "https://api.jquants.com/v2/listed/info"
    res = requests.get(url, headers=headers)
    if res.status_code == 200:
        df_info = pd.DataFrame(res.json().get("info", []))
        # 銘柄名(CompanyName)、業種(Sector17CodeName)、上場日(ListingDate)を抽出
        return df_info[['Code', 'CompanyName', 'Sector17CodeName', 'ListingDate']]
    return pd.DataFrame()

# --- 5. 複数日データ取得関数 ---
@st.cache_data(ttl=3600)
def get_historical_data():
    base_date = datetime(2025, 11, 28) # Freeプラン基準日
    target_dates = []
    days_count = 0
    while len(target_dates) < 14:
        d = base_date - timedelta(days=days_count)
        if d.weekday() < 5: target_dates.append(d.strftime('%Y%m%d'))
        days_count += 1
    
    all_rows = []
    progress_bar = st.progress(0)
    for i, d in enumerate(target_dates[::-1]):
        url = f"https://api.jquants.com/v2/equities/bars/daily?date={d}"
        res = requests.get(url, headers=headers)
        if res.status_code == 200:
            all_rows.extend(res.json().get("data", []))
        if i < 13: time.sleep(13)
        progress_bar.progress((i + 1) / 14)
    progress_bar.empty()
    return all_rows

# --- 6. メイン実行 ---
if st.button("スクリーニング開始"):
    with st.spinner("全銘柄の多角分析を実行中..."):
        # データの取得
        info_df = get_brand_info()
        raw_data = get_historical_data()
        
        if not raw_data or info_df.empty:
            st.error("データの取得に失敗しました。")
        else:
            df = pd.DataFrame(raw_data)
            df['AdjC'] = pd.to_numeric(df['AdjC'], errors='coerce')
            df['AdjH'] = pd.to_numeric(df['AdjH'], errors='coerce')
            df = df.dropna(subset=['AdjC', 'AdjH'])
            
            # 銘柄集計
            summary = df.groupby('Code').agg(latest_close=('AdjC', 'last'), recent_high=('AdjH', 'max')).reset_index()
            
            # 銘柄情報マージ
            final_df = pd.merge(summary, info_df, on='Code', how='inner')
            
            # --- フィルター適用 ---
            # 1. 株価下限
            final_df = final_df[final_df['latest_close'] > min_price]
            # 2. IPO除外 (上場から365日経過しているか)
            if exclude_ipo:
                one_year_ago = (datetime(2025, 11, 28) - timedelta(days=365)).strftime('%Y-%m-%d')
                final_df = final_df[final_df['ListingDate'] <= one_year_ago]
            # 3. 買値目安到達のみ
            final_df['current_ratio'] = final_df['latest_close'] / final_df['recent_high']
            if only_buy_signal:
                final_df = final_df[final_df['current_ratio'] <= 0.45]
            
            # ソート
            results = final_df.sort_values('current_ratio').head(30)
            
            st.success(f"解析完了！対象: {len(results)} 銘柄")
            
            for _, row in results.iterrows():
                st.divider()
                st.subheader(f"{row['CompanyName']} ({row['Code'][:-1]})") # 5桁目をカットして表示
                st.caption(f"業種: {row['Sector17CodeName']} | 上場日: {row['ListingDate']}")
                
                c1, c2, c3 = st.columns(3)
                ratio_pct = int(row['current_ratio'] * 100)
                c1.metric("📉 現在水準", f"{ratio_pct}%", delta=f"{ratio_pct-45}%" if ratio_pct > 45 else "SIGNAL")
                c2.metric("最新終値", f"{int(row['latest_close'])}円")
                c3.metric("🎯 買値目安(45%)", f"{int(row['recent_high'] * 0.45)}円")
                
                # リスク管理ライン
                base_50 = row['recent_high'] * 0.50
                target_3 = int(base_50 * 1.03)
                st.write(f"💰 利確目安: {target_3}円 (+3%) | 損切目安: {int(row['recent_high']*0.45*0.9)}円")
