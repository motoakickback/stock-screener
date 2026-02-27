import streamlit as st
import requests
import pandas as pd
import time
from datetime import datetime, timedelta

# --- 1. ページ設定 ---
st.set_page_config(page_title="J-Quants 戦略スクリーナー (V5.7)", layout="wide")
st.title("⚔️ J-Quants 戦略アドバイザー (V5.7)")

# --- 2. 認証情報の厳密な取得 ---
if "JQUANTS_API_KEY" not in st.secrets:
    st.error("Secretsに 'JQUANTS_API_KEY' が見つかりません。")
    st.stop()

API_KEY = st.secrets["JQUANTS_API_KEY"].strip()
headers = {"x-api-key": API_KEY}

# --- 3. サイドバー設定（鉄の掟） ---
st.sidebar.header("🔍 鉄の掟（フィルター）")
min_price = st.sidebar.number_input("① 株価下限 (円)", value=200, step=100)
exclude_ipo = st.sidebar.checkbox("⑤ IPO除外 (上場1年未満)", value=True)
only_buy_signal = st.sidebar.checkbox("買値目安(50%以下)のみ表示", value=True)

# --- 4. 銘柄詳細取得 (最も安定するV2エンドポイント) ---
@st.cache_data(ttl=86400)
def get_brand_info():
    # Freeプランで確実に動く日付指定付きエンドポイント
    url = "https://api.jquants.com/v2/listed/info?date=20251128"
    try:
        res = requests.get(url, headers=headers, timeout=20)
        if res.status_code == 200:
            return pd.DataFrame(res.json().get("info", []))
        else:
            # 画面に詳細なエラー理由を表示
            st.error(f"❌ 銘柄情報取得失敗: HTTP {res.status_code}")
            st.code(res.text) # サーバーからの生の返答を表示
            return pd.DataFrame()
    except Exception as e:
        st.error(f"❌ 通信エラー: {e}")
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
        
        progress_bar.progress((i + 1) / 14)
        time.sleep(13) # Freeプラン1分間5回制限対策
        
    progress_bar.empty()
    return all_rows

# --- 6. メイン実行 ---
if st.button("スクリーニング開始"):
    info_df = get_brand_info()
    
    if info_df.empty:
        st.stop()
        
    with st.spinner("ボスの規律に基づき解析中..."):
        raw_data = get_historical_data()
        
        if not raw_data:
            st.error("株価データの取得に失敗しました。")
        else:
            df = pd.DataFrame(raw_data)
            for col in ['AdjC', 'AdjH', 'AdjL']:
                df[col] = pd.to_numeric(df[col], errors='coerce')
            
            summary = df.groupby('Code').agg(
                latest_close=('AdjC', 'last'),
                recent_high=('AdjH', 'max'),
                recent_low=('AdjL', 'min')
            ).reset_index()
            
            final_df = pd.merge(summary, info_df, on='Code', how='inner')
            final_df['MarketCapitalization'] = pd.to_numeric(final_df['MarketCapitalization'], errors='coerce')
            
            # --- フィルター適用 ---
            final_df = final_df[final_df['latest_close'] >= min_price]
            if exclude_ipo:
                one_year_ago = (datetime(2025, 11, 28) - timedelta(days=365)).strftime('%Y-%m-%d')
                final_df = final_df[final_df['ListingDate'] <= one_year_ago]
                
            final_df['current_ratio'] = final_df['latest_close'] / final_df['recent_high']
            if only_buy_signal:
                final_df = final_df[final_df['current_ratio'] <= 0.50]
            
            results = final_df.sort_values('current_ratio').head(30)
            st.success(f"審査完了: {len(results)} 銘柄を表示")
            
            for _, row in results.iterrows():
                st.divider()
                st.subheader(f"{row['CompanyName']} ({row['Code'][:-1]})")
                m_cap = int(row['MarketCapitalization'] / 100000000) if not pd.isna(row['MarketCapitalization']) else "-"
                st.caption(f"業種: {row['Sector17CodeName']} | 時価総額: {m_cap}億円")
                
                c1, c2, c3 = st.columns(3)
                ratio_pct = int(row['current_ratio'] * 100)
                c1.metric("📉 現在水準", f"{ratio_pct}%", delta=f"{ratio_pct-50}%" if ratio_pct > 50 else "🎯 SIGNAL", delta_color="inverse")
                c2.metric("最新終値", f"{int(row['latest_close'])}円")
                c3.metric("🎯 買値目安(50%)", f"{int(row['recent_high'] * 0.50)}円")
