import streamlit as st
import requests
import pandas as pd
import time
from datetime import datetime, timedelta

# --- 1. ページ設定 ---
st.set_page_config(page_title="J-Quants 戦略スクリーナー (V2)", layout="wide")
st.title("🚀 J-Quants 戦略スクリーナー (V2)")

# --- 2. Secrets & Headers ---
API_KEY = st.secrets["JQUANTS_API_KEY"]
headers = {"x-api-key": API_KEY.strip()}

# --- 3. サイドバー設定 ---
min_price_limit = st.sidebar.number_input("株価下限 (円)", value=1000, step=100)
st.sidebar.info("Freeプラン制限回避のため、取得には約3分かかります。")

# --- 4. 複数日データ取得関数 ---
@st.cache_data(ttl=3600)
def get_historical_data():
    base_date = datetime(2025, 11, 28)
    target_dates = []
    days_count = 0
    while len(target_dates) < 14:
        d = base_date - timedelta(days=days_count)
        if d.weekday() < 5:
            target_dates.append(d.strftime('%Y%m%d'))
        days_count += 1
    
    all_rows = []
    progress_bar = st.progress(0)
    status_text = st.empty()
    
    for i, d in enumerate(target_dates[::-1]):
        status_text.text(f"📥 データ取得中: {d} ({i+1}/14)...")
        url = f"https://api.jquants.com/v2/equities/bars/daily?date={d}"
        res = requests.get(url, headers=headers)
        if res.status_code == 200:
            data = res.json().get("data", [])
            all_rows.extend(data)
        
        progress_bar.progress((i + 1) / 14)
        # Freeプラン制限(5回/分)回避のため、13秒待機
        if i < 13: # 最後の日以外は待機
            time.sleep(13)
            
    status_text.empty()
    progress_bar.empty()
    return all_rows

# --- 5. メイン実行 ---
if st.button("スクリーニング開始"):
    with st.spinner("東証全銘柄の過去14日間を分析中..."):
        raw_data = get_historical_data()
        
        if not raw_data:
            st.error("データが取得できませんでした。")
        else:
            df = pd.DataFrame(raw_data)
            df['AdjC'] = pd.to_numeric(df['AdjC'], errors='coerce')
            df['AdjH'] = pd.to_numeric(df['AdjH'], errors='coerce')
            df = df.dropna(subset=['AdjC', 'AdjH'])
            
            # 銘柄ごとに「最新終値」と「14日間最高値」を計算
            summary = df.groupby('Code').agg(
                latest_close=('AdjC', 'last'),
                recent_high=('AdjH', 'max')
            ).reset_index()
            
            # フィルター
            filtered = summary[summary['latest_close'] > min_price_limit].copy()
            filtered['current_ratio'] = filtered['latest_close'] / filtered['recent_high']
            
            # ソート（下落率順）してトップ20
            results = filtered.sort_values('current_ratio').head(20)
            
            st.success(f"解析完了！現在水準が低い（45%に近い）順に表示します。")
            
            for _, row in results.iterrows():
                st.divider()
                st.subheader(f"{row['Code']} (14日最高値: {int(row['recent_high'])}円)")
                
                c1, c2, c3 = st.columns(3)
                ratio_pct = int(row['current_ratio'] * 100)
                c1.metric("📉 現在水準", f"{ratio_pct}%")
                c2.metric("最新終値", f"{int(row['latest_close'])}円")
                c3.metric("🎯 55%押し目安", f"{int(row['recent_high'] * 0.45)}円")
                
                # 利確・損切りライン（省略していたロジックの再実装）
                base_50 = row['recent_high'] * 0.50
                target_3 = int(base_50 * 1.03)
                st.write(f"💰 利確目安(50%基点+3%): {target_3}円")
