import streamlit as st
import requests
import pandas as pd
import time
import os
from datetime import datetime, timedelta

# --- 1. ページ設定 ---
st.set_page_config(page_title="J-Quants 戦略スクリーナー (V9.1)", layout="wide")
st.title("🛡️ J-Quants 戦略アドバイザー (V9.1)")

# --- 2. 認証情報 ---
API_KEY = st.secrets["JQUANTS_API_KEY"].strip()
headers = {"x-api-key": API_KEY}
BASE_URL = "https://api.jquants.com/v2"

# --- 3. 銘柄マスター管理 ---
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
        generate_brands_csv()
    if os.path.exists("brands.csv"):
        return pd.read_csv("brands.csv", dtype={'Code': str})
    return pd.DataFrame()

# --- 4. サイドバー設定 ---
st.sidebar.header("🎯 個別狙撃（即時診断）")
target_code = st.sidebar.text_input("銘柄コード（4桁）", max_chars=4, placeholder="例: 8105")
search_single = st.sidebar.button("個別銘柄を解析")

st.sidebar.divider()

st.sidebar.header("🔍 鉄の掟（フィルター）")
f1_price = st.sidebar.number_input("① 株価下限 (円)", value=200, step=100)
f2_short = st.sidebar.checkbox("② 短期2倍急騰を除外", value=True)
f3_signal = st.sidebar.checkbox("③ 買値目安(50%以下)のみ表示", value=True)
f4_long = st.sidebar.checkbox("④ 3倍以上上げ切りを除外", value=True)
f5_ipo = st.sidebar.checkbox("⑤ IPO除外 (上場1年未満)", value=True)
f6_risk = st.sidebar.checkbox("⑥ 疑義注記銘柄を除外", value=True)

if st.sidebar.button("銘柄データを最新に更新"):
    with st.sidebar.spinner("JPXから4000銘柄を徴収中..."):
        if generate_brands_csv():
            st.cache_data.clear()
            st.rerun()

# --- 5. データ取得関数 ---
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
        time.sleep(13)
    p_bar.empty()
    return all_rows

def get_single_stock_data(code):
    base_date = datetime(2025, 11, 28)
    from_date = (base_date - timedelta(days=30)).strftime('%Y%m%d')
    to_date = base_date.strftime('%Y%m%d')
    url = f"{BASE_URL}/equities/bars/daily?code={code}&from={from_date}&to={to_date}"
    try:
        res = requests.get(url, headers=headers, timeout=15)
        if res.status_code == 200:
            data = res.json().get("data", [])
            df = pd.DataFrame(data)
            if not df.empty:
                return df.sort_values('Date', ascending=False).head(14).to_dict('records')
    except: pass
    return []

# --- 6. メイン実行 ---
master_df = load_brand_master()

# ルートA: 個別狙撃モード（数秒で完了）
if search_single and target_code:
    code_with_suffix = target_code + "0"
    with st.spinner(f"コード {target_code} のデータを即時抽出中..."):
        raw_data = get_single_stock_data(code_with_suffix)
        if not raw_data:
            st.error(f"銘柄コード {target_code} のデータが見つかりませんでした。")
        else:
            df = pd.DataFrame(raw_data)
            for col in ['AdjC', 'AdjH', 'AdjL']:
                df[col] = pd.to_numeric(df[col], errors='coerce')
            
            df = df.sort_values('Date')
            latest_close = df['AdjC'].iloc[-1]
            recent_high = df['AdjH'].max()
            current_ratio = latest_close / recent_high if recent_high > 0 else 0
            
            name, sector, market = f"銘柄 {target_code}", "-", "-"
            if not master_df.empty:
                match = master_df[master_df['Code'] == code_with_suffix]
                if not match.empty:
                    name = match.iloc[0]['CompanyName']
                    sector = match.iloc[0]['Sector']
                    market = match.iloc[0]['Market']
            
            st.success(f"即時診断完了: {name}")
            st.divider()
            st.subheader(f"{name} ({target_code})")
            st.caption(f"業種: {sector} | 市場: {market}")
            
            c1, c2, c3 = st.columns(3)
            ratio_pct = int(current_ratio * 100)
            c1.metric("📉 現在水準", f"{ratio_pct}%", delta=f"{ratio_pct-50}%", delta_color="inverse")
            c2.metric("最新終値", f"{int(latest_close)}円")
            target_50 = int(recent_high * 0.50)
            c3.metric("🎯 買値目安(50%)", f"{target_50}円")
            
            chart_data = df.set_index('Date')[['AdjC']].rename(columns={'AdjC': '実績株価'})
            chart_data['目標ライン(50%)'] = target_50
            st.line_chart(chart_data, color=["#007BFF", "#FF4136"])

# ルートB: 全銘柄スクリーニング（約3分）
elif st.button("全銘柄スクリーニング開始"):
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
                summary = summary[pd.to_datetime(summary['ListingDate'], errors='coerce') <= limit]
                
            # 【修正箇所】文法エラーを修正しました
            if f6_risk and 'CompanyName' in summary.columns:
                summary = summary[~summary['CompanyName'].astype(str).str.contains("疑義|重要事象", na=False)]
            
            summary['current_ratio']
