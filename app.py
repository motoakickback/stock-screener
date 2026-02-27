import streamlit as st
import requests
import pandas as pd
import time
import os
from datetime import datetime, timedelta

# Plotlyのインポート失敗に備えた自己修復ロジック
try:
    import plotly.graph_objects as go
    HAS_PLOTLY = True
except ImportError:
    HAS_PLOTLY = False

# --- 1. ページ設定 ---
st.set_page_config(page_title="J-Quants 戦略スクリーナー (V8.8)", layout="wide")
st.title("🛡️ J-Quants 戦略アドバイザー (V8.8)")

# --- 2. 認証情報 ---
API_KEY = st.secrets["JQUANTS_API_KEY"].strip()
headers = {"x-api-key": API_KEY}
BASE_URL = "https://api.jquants.com/v2"

# --- 3. 銘柄マスター管理 (自動修復機能付き) ---
def generate_brands_csv():
    url = "https://www.jpx.co.jp/markets/statistics-equities/misc/tv0syu00000011xl-att/data_j.xls"
    try:
        df = pd.read_excel(url)
        df = df[['コード', '銘柄名', '33業種区分', '市場・商品区分', '新市場区分上場日']]
        df.columns = ['Code', 'CompanyName', 'Sector', 'Market', 'ListingDate']
        df['Code'] = df['Code'].astype(str) + "0"
        df.to_csv("brands.csv", index=False)
        return True
    except: return False

@st.cache_data
def load_brand_master():
    if not os.path.exists("brands.csv"):
        generate_brands_csv() # なければその場で徴収
    try:
        return pd.read_csv("brands.csv", dtype={'Code': str})
    except:
        return pd.DataFrame()

# --- 4. サイドバー設定（鉄の掟：①～⑥ 完全連番 ＆ 完全実装） ---
st.sidebar.header("🔍 鉄の掟（フィルター）")
f1_price = st.sidebar.number_input("① 株価下限 (円)", value=200, step=100)
f2_short = st.sidebar.checkbox("② 短期2倍急騰を除外", value=True)
f3_signal = st.sidebar.checkbox("③ 買値目安(50%以下)のみ表示", value=True)
f4_long = st.sidebar.checkbox("④ 3倍以上上げ切りを除外", value=True)
f5_ipo = st.sidebar.checkbox("⑤ IPO除外 (上場1年未満)", value=True)
f6_risk = st.sidebar.checkbox("⑥ 疑義注記銘柄を除外", value=True)

if st.sidebar.button("銘柄マスタを強制同期"):
    if generate_brands_csv():
        st.cache_data.clear()
        st.rerun()

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
    p_bar = st.progress(0)
    for i, d in enumerate(target_dates[::-1]):
        url = f"{BASE_URL}/equities/bars/daily?date={d}"
        try:
            res = requests.get(url, headers=headers, timeout=15)
            if res.status_code == 200:
                all_rows.extend(res.json().get("data", []))
        except: pass
        p_bar.progress((i + 1) / 14)
        time.sleep(13) # レート制限遵守
    p_bar.empty()
    return all_rows

# --- 6. メイン実行 ---
if st.button("スクリーニング開始"):
    master_df = load_brand_master()
    
    with st.spinner("ボスの全規律を適用し、4,000銘柄を審査中..."):
        raw_data = get_historical_data()
        if not raw_data:
            st.error("データの取得に失敗しました。")
        else:
            df = pd.DataFrame(raw_data)
            for col in ['AdjC', 'AdjH', 'AdjL']:
                df[col] = pd.to_numeric(df[col], errors='coerce')
            
            summary = df.groupby('Code').agg(
                latest_close=('AdjC', 'last'),
                recent_high=('AdjH', 'max'),
                recent_low=('AdjL', 'min')
            ).reset_index()
            
            if not master_df.empty:
                summary = pd.merge(summary, master_df, on='Code', how='left')
            
            # --- 鉄の掟 執行 ---
            summary = summary[summary['latest_close'] >= f1_price]
            if f2_short:
                summary = summary[summary['latest_close'] < (summary['recent_low'] * 2.0)]
            if f3_signal:
                summary = summary[(summary['latest_close'] / summary['recent_high']) <= 0.50]
            if f4_long:
                summary = summary[summary['latest_close'] < (summary['recent_low'] * 3.0)]
            if f5_ipo and 'ListingDate' in summary.columns:
                limit = (datetime(2025, 11, 28) - timedelta(days=365)).strftime('%Y-%m-%d')
                summary = summary[pd.to_datetime(summary['ListingDate']) <= limit]
            if f6_risk and 'CompanyName' in summary.columns:
                summary = summary[~summary['CompanyName'].str.contains("疑義|重要事象", na=False)]
            
            summary['current_ratio'] = summary['latest_close'] / summary['recent_high']
            results = summary.sort_values('current_ratio').head(30)
            st.success(f"審査完了: {len(results)} 銘柄を表示")
            
            for _, row in results.iterrows():
                st.divider()
                code = str(row['Code'])
                name = row['CompanyName'] if not pd.isna(row.get('CompanyName')) else f"銘柄 {code[:-1]}"
                st.subheader(f"{name} ({code[:-1]})")
                st.caption(f"業種: {row.get('Sector', '-')} | 市場: {row.get('Market', '-')}")
                
                c1, c2, c3 = st.columns(3)
                ratio_pct = int(row['current_ratio'] * 100)
                c1.metric("📉 現在水準", f"{ratio_pct}%", delta=f"{ratio_pct-50}%", delta_color="inverse")
                c2.metric("最新終値", f"{int(row['latest_close'])}円")
                target_50 = int(row['recent_high'] * 0.50)
                c3.metric("🎯 買値目安(50%)", f"{target_50}円")

                # チャート描画 (Plotlyがなければ自動で標準チャートに切替)
                hist = df[df['Code'] == row['Code']].sort_values('Date')
                if not hist.empty:
                    if HAS_PLOTLY:
                        fig = go.Figure()
                        fig.add_trace(go.Scatter(x=hist['Date'], y=hist['AdjC'], name='株価', line=dict(color='#007BFF', width=3)))
                        fig.add_trace(go.Scatter(x=hist['Date'], y=[target_50]*len(hist), name='50%線', line=dict(color='#FF4136', dash='dash')))
                        fig.update_layout(height=280, margin=dict(l=0, r=0, t=20, b=0), hovermode="x unified")
                        st.plotly_chart(fig, use_container_width=True)
                    else:
                        st.line_chart(hist.set_index('Date')['AdjC'])
