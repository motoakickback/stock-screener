import streamlit as st
import requests
import pandas as pd
import time
import numpy as np
from datetime import datetime, timedelta

# --- 1. ページ設定 ---
st.set_page_config(page_title="J-Quants 戦略スクリーナー (V8.0)", layout="wide")
st.title("🛡️ J-Quants 戦略アドバイザー (V8.0)")

# --- 2. 認証情報の取得 ---
API_KEY = st.secrets["JQUANTS_API_KEY"].strip()
headers = {"x-api-key": API_KEY}
BASE_URL = "https://api.jquants.com/v2"

# --- 3. 案A: 全銘柄マスターの読み込み (CSV版) ---
@st.cache_data
def load_brand_master():
    try:
        # 同階層に配置した brands.csv を読み込む
        master = pd.read_csv("brands.csv")
        master['Code'] = master['Code'].astype(str)
        return master
    except:
        # ファイルがない場合は最小限の辞書を返す
        return pd.DataFrame([{"Code": "81050", "CompanyName": "堀田丸正", "Sector": "卸売業", "Market": "スタンダード"}])

# --- 4. サイドバー設定 ---
st.sidebar.header("🔍 鉄の掟（フィルター）")
min_price = st.sidebar.number_input("① 株価下限 (円)", value=200, step=100)
exclude_short_spike = st.sidebar.checkbox("② 短期2倍急騰を除外", value=True)
only_buy_signal = st.sidebar.checkbox("買値目安(50%以下)のみ表示", value=True)

# --- 5. 株価データ取得 ---
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
        url = f"{BASE_URL}/equities/bars/daily?date={d}"
        try:
            res = requests.get(url, headers=headers, timeout=15)
            if res.status_code == 200:
                all_rows.extend(res.json().get("data", []))
        except: pass
        progress_bar.progress((i + 1) / 14)
        time.sleep(13)
    progress_bar.empty()
    return all_rows

# --- 6. メイン実行 ---
if st.button("スクリーニング開始"):
    master_df = load_brand_master()
    
    with st.spinner("全銘柄のマスター照合 ＆ 50%ライン解析を実行中..."):
        raw_data = get_historical_data()
        
        if not raw_data:
            st.error("データの取得に失敗しました。")
        else:
            df = pd.DataFrame(raw_data)
            
            # 数値変換
            cols_to_convert = ['AdjC', 'AdjH', 'AdjL', 'AdjV', 'Volume']
            for col in cols_to_convert:
                if col in df.columns:
                    df[col] = pd.to_numeric(df[col], errors='coerce')
            
            # 銘柄ごとに集計
            summary = df.groupby('Code').agg({
                'AdjC': 'last',
                'AdjH': 'max',
                'AdjL': 'min'
            }).reset_index()
            summary.columns = ['Code', 'latest_close', 'recent_high', 'recent_low']
            
            # マスターデータと紐付け (案A)
            summary = pd.merge(summary, master_df, on='Code', how='left')
            
            # フィルター適用
            summary = summary[summary['latest_close'] >= min_price]
            if exclude_short_spike:
                summary = summary[summary['latest_close'] < (summary['recent_low'] * 2.0)]
            
            summary['current_ratio'] = summary['latest_close'] / summary['recent_high']
            if only_buy_signal:
                summary = summary[summary['current_ratio'] <= 0.50]
            
            results = summary.sort_values('current_ratio').head(30)
            st.success(f"審査完了: {len(results)} 銘柄が規律をクリア")
            
            for _, row in results.iterrows():
                st.divider()
                code = str(row['Code'])
                name = row['CompanyName'] if not pd.isna(row['CompanyName']) else f"銘柄 {code[:-1]}"
                sector = row['Sector'] if not pd.isna(row['Sector']) else "-"
                
                st.subheader(f"{name} ({code[:-1]})")
                st.caption(f"業種: {sector} | 市場: {row.get('Market', '-')}")
                
                c1, c2, c3 = st.columns(3)
                ratio_pct = int(row['current_ratio'] * 100)
                c1.metric("📉 現在水準", f"{ratio_pct}%", delta=f"{ratio_pct-50}%", delta_color="inverse")
                c2.metric("最新終値", f"{int(row['latest_close'])}円")
                target_50 = int(row['recent_high'] * 0.50)
                c3.metric("🎯 買値目安(50%)", f"{target_50}円")

                # 案C: 50%ライン付きチャート
                history_df = df[df['Code'] == row['Code']].sort_values('Date')
                if not history_df.empty:
                    chart_data = history_df.set_index('Date')[['AdjC']]
                    chart_data['買値目安(50%)'] = target_50 # 50%ラインをグラフに追加
                    st.line_chart(chart_data)
