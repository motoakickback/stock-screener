import streamlit as st
import requests
import pandas as pd
import time
import plotly.graph_objects as go
from datetime import datetime, timedelta

# --- 1. ページ設定 ---
st.set_page_config(page_title="J-Quants 戦略スクリーナー (V8.2)", layout="wide")
st.title("🛡️ J-Quants 戦略アドバイザー (V8.2)")

# --- 2. 認証情報の取得 ---
API_KEY = st.secrets["JQUANTS_API_KEY"].strip()
headers = {"x-api-key": API_KEY}
BASE_URL = "https://api.jquants.com/v2"

# --- 3. 案A: 銘柄マスター (全銘柄対応版) ---
@st.cache_data
def load_brand_master():
    try:
        # GitHub上の brands.csv を読み込む
        master = pd.read_csv("brands.csv")
        master['Code'] = master['Code'].astype(str)
        return master
    except:
        # 万が一のフォールバック
        return pd.DataFrame([{"Code": "81050", "CompanyName": "堀田丸正", "Sector": "卸売業", "ListingDate": "1990-01-01"}])

# --- 4. サイドバー設定（鉄の掟） ---
st.sidebar.header("🔍 鉄の掟（フィルター）")
min_price = st.sidebar.number_input("① 株価下限 (円)", value=200, step=100)
exclude_short_spike = st.sidebar.checkbox("② 短期2倍急騰を除外", value=True)
exclude_long_peak = st.sidebar.checkbox("③ 3倍以上上げ切りを除外", value=True)
exclude_ipo = st.sidebar.checkbox("④ IPO除外 (上場1年未満)", value=True)
exclude_risk = st.sidebar.checkbox("⑤ 疑義注記銘柄を除外", value=True)

st.sidebar.divider()
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
    
    with st.spinner("ボスの全規律 ＆ 4,000銘柄を解析中..."):
        raw_data = get_historical_data()
        
        if not raw_data:
            st.error("データの取得に失敗しました。")
        else:
            df = pd.DataFrame(raw_data)
            # 数値変換とカラムクリーニング
            for col in ['AdjC', 'AdjH', 'AdjL', 'Volume', 'AdjV']:
                if col in df.columns:
                    df[col] = pd.to_numeric(df[col], errors='coerce')
            
            # 銘柄ごとに集計
            summary = df.groupby('Code').agg(
                latest_close=('AdjC', 'last'),
                recent_high=('AdjH', 'max'),
                recent_low=('AdjL', 'min')
            ).reset_index()
            
            # マスター紐付け
            summary = pd.merge(summary, master_df, on='Code', how='left')
            
            # --- 鉄の掟（全フィルター）適用 ---
            summary = summary[summary['latest_close'] >= min_price] # ①
            
            if exclude_short_spike: # ②
                summary = summary[summary['latest_close'] < (summary['recent_low'] * 2.0)]
                
            if exclude_long_peak: # ④
                summary = summary[summary['latest_close'] < (summary['recent_low'] * 3.0)]
            
            if exclude_ipo and 'ListingDate' in summary.columns: # ⑤
                one_year_ago = (datetime(2025, 11, 28) - timedelta(days=365)).strftime('%Y-%m-%d')
                summary = summary[summary['ListingDate'] <= one_year_ago]
            
            if exclude_risk and 'CompanyName' in summary.columns: # ⑥
                summary = summary[~summary['CompanyName'].str.contains("疑義|重要事象", na=False)]
            
            summary['current_ratio'] = summary['latest_close'] / summary['recent_high']
            if only_buy_signal:
                summary = summary[summary['current_ratio'] <= 0.50]
            
            results = summary.sort_values('current_ratio').head(30)
            st.success(f"審査完了: {len(results)} 銘柄が規律をクリアしました。")
            
            for _, row in results.iterrows():
                st.divider()
                code = str(row['Code'])
                name = row['CompanyName'] if not pd.isna(row['CompanyName']) else f"銘柄 {code[:-1]}"
                st.subheader(f"{name} ({code[:-1]})")
                st.caption(f"業種: {row.get('Sector', '-')} | 市場: {row.get('Market', '-')}")
                
                c1, c2, c3 = st.columns(3)
                ratio_pct = int(row['current_ratio'] * 100)
                c1.metric("📉 現在水準", f"{ratio_pct}%", delta=f"{ratio_pct-50}%", delta_color="inverse")
                c2.metric("最新終値", f"{int(row['latest_close'])}円")
                target_50 = int(row['recent_high'] * 0.50)
                c3.metric("🎯 買値目安(50%)", f"{target_50}円")

                # 案C: 高機能チャート (Plotly)
                hist = df[df['Code'] == row['Code']].sort_values('Date')
                if not hist.empty:
                    fig = go.Figure()
                    # 株価推移 (青)
                    fig.add_trace(go.Scatter(x=hist['Date'], y=hist['AdjC'], name='実績株価', line=dict(color='#1f77b4', width=3)))
                    # 目標ライン (赤・破線)
                    fig.add_trace(go.Scatter(x=hist['Date'], y=[target_50]*len(hist), name='目標(50%)', line=dict(color='#d62728', dash='dash')))
                    
                    fig.update_layout(height=300, margin=dict(l=0, r=0, t=0, b=0), showlegend=True,
                                      xaxis_tickformat='%m/%d', hovermode="x unified")
                    st.plotly_chart(fig, use_container_width=True)
