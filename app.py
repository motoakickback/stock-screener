import streamlit as st
import requests
import pandas as pd
import time
from datetime import datetime, timedelta

# --- 1. ページ設定 ---
st.set_page_config(page_title="J-Quants 戦略スクリーナー (V7.0)", layout="wide")
st.title("🛡️ J-Quants 戦略アドバイザー (V7.0)")

# --- 2. 認証情報の取得 ---
API_KEY = st.secrets["JQUANTS_API_KEY"].strip()
headers = {"x-api-key": API_KEY}
BASE_URL = "https://api.jquants.com/v2"

# --- 3. サイドバー設定 ---
st.sidebar.header("🔍 鉄の掟（フィルター）")
min_price = st.sidebar.number_input("① 株価下限 (円)", value=200, step=100)
exclude_short_spike = st.sidebar.checkbox("② 短期2倍急騰を除外", value=True)
exclude_long_peak = st.sidebar.checkbox("④ 3倍以上上げ切りを除外", value=True)
only_buy_signal = st.sidebar.checkbox("買値目安(50%以下)のみ表示", value=True)

st.sidebar.info("Freeプラン制限のため、14日分の取得には約3分かかります。")

# --- 4. 株価データ取得 (このAPIは403が出にくい) ---
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
    status_text = st.empty()
    
    for i, d in enumerate(target_dates[::-1]):
        status_text.text(f"📥 株価データ取得中: {d} ({i+1}/14)")
        url = f"{BASE_URL}/equities/bars/daily?date={d}"
        try:
            res = requests.get(url, headers=headers, timeout=15)
            if res.status_code == 200:
                all_rows.extend(res.json().get("data", []))
            elif res.status_code == 429:
                st.error("❌ レート制限超過。1分待機してください。")
                return []
            else:
                st.warning(f"⚠️ {d} の取得に失敗(HTTP {res.status_code})。スキップします。")
        except: pass
        
        progress_bar.progress((i + 1) / 14)
        time.sleep(13) # Freeプラン13秒ルール
        
    status_text.empty()
    progress_bar.empty()
    return all_rows

# --- 5. メイン実行 ---
if st.button("スクリーニング開始"):
    with st.spinner("株価データのみで厳格に審査中..."):
        raw_data = get_historical_data()
        
        if not raw_data:
            st.error("データの取得に失敗しました。API Keyが無効な可能性があります。")
        else:
            df = pd.DataFrame(raw_data)
            for col in ['AdjC', 'AdjH', 'AdjL']:
                df[col] = pd.to_numeric(df[col], errors='coerce')
            
            # 銘柄ごとに集計
            summary = df.groupby('Code').agg(
                latest_close=('AdjC', 'last'),
                recent_high=('AdjH', 'max'),
                recent_low=('AdjL', 'min')
            ).reset_index()
            
            # --- 鉄の掟（フィルター）適用 ---
            summary = summary[summary['latest_close'] >= min_price]
            if exclude_short_spike:
                summary = summary[summary['latest_close'] < (summary['recent_low'] * 2.0)]
            if exclude_long_peak:
                summary = summary[summary['latest_close'] < (summary['recent_low'] * 3.0)]
            
            summary['current_ratio'] = summary['latest_close'] / summary['recent_high']
            if only_buy_signal:
                summary = summary[summary['current_ratio'] <= 0.50]
            
            results = summary.sort_values('current_ratio').head(30)
            st.success(f"審査完了: {len(results)} 銘柄が規律をクリアしました。")
            
            for _, row in results.iterrows():
                st.divider()
                st.subheader(f"銘柄コード: {row['Code'][:-1]}") # 銘柄名は出せませんがコードは確実に出ます
                
                c1, c2, c3 = st.columns(3)
                ratio_pct = int(row['current_ratio'] * 100)
                delta_val = ratio_pct - 50
                c1.metric("📉 現在水準", f"{ratio_pct}%", delta=f"{delta_val}%" if ratio_pct > 50 else "🎯 SIGNAL", delta_color="inverse")
                c2.metric("最新終値", f"{int(row['latest_close'])}円")
                c3.metric("🎯 買値目安(50%)", f"{int(row['recent_high'] * 0.50)}円")
