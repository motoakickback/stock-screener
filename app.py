import streamlit as st
import requests
import pandas as pd
from datetime import datetime, timedelta

# --- 1. ページ設定とスタイル ---
st.set_page_config(page_title="J-Quants 高速スクリーナー", layout="wide")
st.title("🚀 J-Quants 戦略スクリーナー (V2)")

# --- 2. SecretsからAPI Keyを取得 ---
API_KEY = st.secrets["JQUANTS_API_KEY"]
headers = {"x-api-key": API_KEY}

# --- 3. サイドバー設定 ---
min_price_limit = st.sidebar.number_input("株価下限 (円)", value=1000, step=100)

# --- 4. データ取得関数 (キャッシュ利用で高速化) ---
@st.cache_data(ttl=3600)
def get_jquants_data(date_str):
    url = f"https://api.jquants.com/v2/equities/bars/daily?date={date_str}"
    res = requests.get(url, headers=headers)
    if res.status_code == 200:
        return res.json().get("data", [])
    return []

# --- 5. メインロジック ---
# Freeプラン用に直近の営業日（2025/11/28等）を自動計算または固定設定
# 本番運用時はここを動的に変更
target_date = "20251128" 

with st.spinner(f"{target_date} の全銘柄データを解析中..."):
    raw_data = get_jquants_data(target_date)
    
    if not raw_data:
        st.error("データの取得に失敗しました。API Keyやプラン、日付を確認してください。")
    else:
        df = pd.DataFrame(raw_data)
        # 型変換とクリーニング
        df['AdjC'] = pd.to_numeric(df['AdjC'], errors='coerce')
        df['AdjH'] = pd.to_numeric(df['AdjH'], errors='coerce')
        df = df.dropna(subset=['AdjC', 'AdjH'])
        
        # 今回は1日分のデータから「当日高値」を暫定最高値として計算
        # ※本来は複数日の最大値を取るが、まずは疎通確認を優先
        df['current_ratio'] = df['AdjC'] / df['AdjH']
        
        # フィルター適用
        filtered = df[df['AdjC'] > min_price_limit].copy()
        
        # 下落率順（現在水準が低い順）にソート
        results = filtered.sort_values('current_ratio').head(20)

        # 結果出力
        st.success(f"解析完了: {len(results)} 銘柄を表示します。")
        
        for _, row in results.iterrows():
            st.divider()
            st.subheader(f"{row['Code']} (最高値: {int(row['AdjH'])}円)")
            
            col1, col2, col3 = st.columns(3)
            # 現在水準をパーセントで表示
            ratio_pct = int(row['current_ratio'] * 100)
            col1.metric("📉 現在水準", f"{ratio_pct}%")
            col2.metric("終値", f"{int(row['AdjC'])}円")
            
            # 55%押し目安の簡易表示
            drop_55 = int(row['AdjH'] * 0.45)
            col3.metric("🎯 55%押し目安", f"{drop_55}円")
