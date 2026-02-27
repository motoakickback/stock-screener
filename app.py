import streamlit as st
import requests
import pandas as pd
import time
from datetime import datetime, timedelta

# --- 1. ページ設定 ---
st.set_page_config(page_title="J-Quants 戦略スクリーナー (V4)", layout="wide")
st.title("🛡️ J-Quants 戦略アドバイザー (V4)")

# --- 2. Secrets & Headers ---
API_KEY = st.secrets["JQUANTS_API_KEY"]
headers = {"x-api-key": API_KEY.strip()}

# --- 3. サイドバー設定 ---
st.sidebar.header("🔍 抽出条件")
min_price = st.sidebar.number_input("株価下限 (円)", value=200, step=100)
exclude_ipo = st.sidebar.checkbox("IPO除外 (上場1年未満)", value=True)
# ボスの指示により基準を50%に変更
only_buy_signal = st.sidebar.checkbox("買値目安(50%以下)のみ表示", value=False)

target_sector = st.sidebar.multiselect("業種で絞り込み", 
    ["情報・通信業", "サービス業", "電気機器", "化学", "機械", "医薬品", "小売業", "不動産業", "卸売業"])

st.sidebar.info("Freeプラン制限回避のため、取得には約3分かかります。")

# --- 4. 銘柄詳細取得 ---
@st.cache_data(ttl=86400)
def get_brand_info():
    # 銘柄一覧API
    url_info = "https://api.jquants.com/v2/listed/info"
    res_info = requests.get(url_info, headers=headers)
    
    if res_info.status_code == 200:
        df_info = pd.DataFrame(res_info.json().get("info", []))
        return df_info[['Code', 'CompanyName', 'Sector17CodeName', 'ListingDate', 'MarketCodeName']]
    return pd.DataFrame()

# --- 5. 複数日データ取得 ---
@st.cache_data(ttl=3600)
def get_historical_data():
    base_date = datetime(2025, 11, 28)
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
        info_df = get_brand_info()
        raw_data = get_historical_data()
        
        if not raw_data or info_df.empty:
            st.error("データの取得に失敗しました。")
        else:
            df = pd.DataFrame(raw_data)
            df['AdjC'] = pd.to_numeric(df['AdjC'], errors='coerce')
            df['AdjH'] = pd.to_numeric(df['AdjH'], errors='coerce')
            # 時価総額（MarketCap）を数値化
            df['MCap'] = pd.to_numeric(df['MarketCap'], errors='coerce')
            df = df.dropna(subset=['AdjC', 'AdjH'])
            
            # 銘柄集計
            summary = df.groupby('Code').agg(
                latest_close=('AdjC', 'last'),
                recent_high=('AdjH', 'max'),
                market_cap=('MCap', 'last') # 最新の時価総額を取得
            ).reset_index()
            
            final_df = pd.merge(summary, info_df, on='Code', how='inner')
            
            # --- フィルター適用 ---
            final_df = final_df[final_df['latest_close'] >= min_price]
            
            if exclude_ipo:
                one_year_ago = (datetime(2025, 11, 28) - timedelta(days=365)).strftime('%Y-%m-%d')
                final_df = final_df[final_df['ListingDate'] <= one_year_ago]
            
            if target_sector:
                final_df = final_df[final_df['Sector17CodeName'].isin(target_sector)]
                
            final_df['current_ratio'] = final_df['latest_close'] / final_df['recent_high']
            
            # 基準を50%に修正
            if only_buy_signal:
                final_df = final_df[final_df['current_ratio'] <= 0.50]
            
            results = final_df.sort_values('current_ratio').head(30)
            st.success(f"解析完了！対象: {len(results)} 銘柄")
            
            for _, row in results.iterrows():
                st.divider()
                st.subheader(f"{row['CompanyName']} ({row['Code'][:-1]})")
                
                # 時価総額を「億円」単位で表示
                m_cap_okuen = int(row['market_cap'] / 100000000) if not pd.isna(row['market_cap']) else "-"
                st.caption(f"市場: {row['MarketCodeName']} | 業種: {row['Sector17CodeName']} | 時価総額: {m_cap_okuen}億円")
                
                c1, c2, c3 = st.columns(3)
                ratio_pct = int(row['current_ratio'] * 100)
                # 買値目安(50%)との乖離を表示
                delta_val = ratio_pct - 50
                c1.metric("📉 現在水準", f"{ratio_pct}%", delta=f"{delta_val}%" if delta_val > 0 else "🎯 SIGNAL", delta_color="inverse")
                c2.metric("最新終値", f"{int(row['latest_close'])}円")
                c3.metric("🎯 買値目安(50%)", f"{int(row['recent_high'] * 0.50)}円")
                
                st.write(f"🛡️ 損切目安(終値-8%): {int(row['latest_close'] * 0.92)}円")
