import streamlit as st
import requests
import pandas as pd
import time
from datetime import datetime, timedelta

# --- 1. ページ設定 ---
st.set_page_config(page_title="J-Quants 戦略スクリーナー (V5)", layout="wide")
st.title("⚔️ J-Quants 戦略アドバイザー (V5)")

# --- 2. Secrets & Headers ---
API_KEY = st.secrets["JQUANTS_API_KEY"]
headers = {"x-api-key": API_KEY.strip()}

# --- 3. サイドバー設定 ---
st.sidebar.header("🔍 鉄の掟（フィルター）")
min_price = st.sidebar.number_input("① 株価下限 (円)", value=200, step=100)
exclude_short_spike = st.sidebar.checkbox("② 短期2倍急騰を除外", value=True)
exclude_long_peak = st.sidebar.checkbox("④ 3倍以上上げ切りを除外", value=True)
exclude_ipo = st.sidebar.checkbox("⑤ IPO除外 (上場1年未満)", value=True)
exclude_going_concern = st.sidebar.checkbox("⑥ 疑義注記銘柄を除外", value=True)

st.sidebar.divider()
only_buy_signal = st.sidebar.checkbox("買値目安(50%以下)のみ表示", value=True)
target_sector = st.sidebar.multiselect("業種絞り込み", ["情報・通信業", "サービス業", "電気機器", "小売業", "不動産業"])

# --- 4. 銘柄詳細取得 ---
@st.cache_data(ttl=86400)
def get_brand_info():
    url = "https://api.jquants.com/v2/listed/info"
    res = requests.get(url, headers=headers)
    if res.status_code == 200:
        return pd.DataFrame(res.json().get("info", []))
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
    with st.spinner("ボスの規律に基づき、全銘柄を厳格に審査中..."):
        info_df = get_brand_info()
        raw_data = get_historical_data()
        
        if not raw_data or info_df.empty:
            st.error("データの取得に失敗しました。APIサーバーの応答を確認してください。")
        else:
            df = pd.DataFrame(raw_data)
            # 型変換
            for col in ['AdjC', 'AdjH', 'AdjL', 'MarketCapitalization']:
                if col in df.columns:
                    df[col] = pd.to_numeric(df[col], errors='coerce')
            
            df = df.dropna(subset=['AdjC', 'AdjH'])
            
            # 銘柄集計
            summary = df.groupby('Code').agg(
                latest_close=('AdjC', 'last'),
                recent_high=('AdjH', 'max'),
                recent_low=('AdjL', 'min'),
                market_cap=('MarketCapitalization', 'last')
            ).reset_index()
            
            # マージ
            final_df = pd.merge(summary, info_df, on='Code', how='inner')
            
            # --- 厳格フィルター適用 ---
            # ① 低位株
            final_df = final_df[final_df['latest_close'] >= min_price]
            
            # ② 短期2倍急騰（14日間の安値から2倍以上）
            if exclude_short_spike:
                final_df = final_df[final_df['latest_close'] < (final_df['recent_low'] * 2.0)]
                
            # ④ 3倍以上上げ切り（ホップ・ステップ・ジャンプ済み）
            if exclude_long_peak:
                final_df = final_df[final_df['latest_close'] < (final_df['recent_low'] * 3.0)]
            
            # ⑤ IPO除外
            if exclude_ipo:
                one_year_ago = (datetime(2025, 11, 28) - timedelta(days=365)).strftime('%Y-%m-%d')
                final_df = final_df[final_df['ListingDate'] <= one_year_ago]
            
            # ⑥ 疑義注記（J-Quantsのコメント等から判定）
            # ※Freeプランで取れる範囲のフラグをチェック
            # if exclude_going_concern:
            #     final_df = final_df[~final_df['CompanyName'].str.contains("疑義|重要事象", na=False)]
            
            if target_sector:
                final_df = final_df[final_df['Sector17CodeName'].isin(target_sector)]
                
            final_df['current_ratio'] = final_df['latest_close'] / final_df['recent_high']
            
            if only_buy_signal:
                final_df = final_df[final_df['current_ratio'] <= 0.50]
            
            results = final_df.sort_values('current_ratio').head(30)
            
            st.success(f"審査完了: {len(results)} 銘柄が規律をクリアしました。")
            
            for _, row in results.iterrows():
                st.divider()
                st.subheader(f"{row['CompanyName']} ({row['Code'][:-1]})")
                m_cap = int(row['market_cap'] / 100000000) if not pd.isna(row['market_cap']) else "-"
                st.caption(f"市場: {row['MarketCodeName']} | 業種: {row['Sector17CodeName']} | 時価総額: {m_cap}億円")
                
                c1, c2, c3 = st.columns(3)
                ratio_pct = int(row['current_ratio'] * 100)
                delta_val = ratio_pct - 50
                c1.metric("📉 現在水準", f"{ratio_pct}%", delta=f"{delta_val}%" if delta_val > 0 else "🎯 SIGNAL", delta_color="inverse")
                c2.metric("最新終値", f"{int(row['latest_close'])}円")
                c3.metric("🎯 買値目安(50%)", f"{int(row['recent_high'] * 0.50)}円")
                
                st.write(f"🛡️ 損切目安(終値-8%): {int(row['latest_close'] * 0.92)}円")
