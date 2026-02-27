import streamlit as st
import requests
import pandas as pd
import time
from datetime import datetime, timedelta

# --- 1. ページ設定 ---
st.set_page_config(page_title="J-Quants 戦略スクリーナー (V7.1)", layout="wide")
st.title("🛡️ J-Quants 戦略アドバイザー (V7.1)")

# --- 2. 認証情報の取得 ---
API_KEY = st.secrets["JQUANTS_API_KEY"].strip()
headers = {"x-api-key": API_KEY}
BASE_URL = "https://api.jquants.com/v2"

# --- 3. サイドバー設定（鉄の掟） ---
st.sidebar.header("🔍 鉄の掟（フィルター）")
min_price = st.sidebar.number_input("① 株価下限 (円)", value=200, step=100)
exclude_short_spike = st.sidebar.checkbox("② 短期2倍急騰を除外", value=True)
exclude_long_peak = st.sidebar.checkbox("④ 3倍以上上げ切りを除外", value=True)
only_buy_signal = st.sidebar.checkbox("買値目安(50%以下)のみ表示", value=True)

# 案A: 業種絞り込み（マスターデータから抽出）
target_sector = st.sidebar.multiselect("業種絞り込み", ["情報・通信業", "サービス業", "電気機器", "小売業", "不動産業", "卸売業", "機械", "化学", "医薬品"])

# --- 4. 銘柄マスター取得 (API回避策：JPX公式サイトのデータを活用) ---
@st.cache_data
def get_brand_master():
    # JPXの銘柄一覧URL（2025年11月末時点の統計データ）
    # APIが403のため、公開されているマスターデータを直接参照する
    url = "https://www.jpx.co.jp/markets/statistics-equities/misc/tv0syu00000011xl-att/data_j.xls"
    try:
        # Excelファイルを読み込み（銘柄コード、名称、業種などを抽出）
        master = pd.read_excel(url)
        master = master[['コード', '銘柄名', '市場・商品区分', '33業種区分', '時価総額（円）']]
        master.columns = ['Code', 'CompanyName', 'Market', 'Sector', 'MarketCap']
        # コードをJ-Quants形式 (例: 81050) に変換
        master['Code'] = master['Code'].astype(str) + "0"
        return master
    except:
        st.error("銘柄マスターの取得に失敗しました。")
        return pd.DataFrame()

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
    status_text = st.empty()
    
    for i, d in enumerate(target_dates[::-1]):
        status_text.text(f"📥 株価データ取得中: {d} ({i+1}/14)")
        url = f"{BASE_URL}/equities/bars/daily?date={d}"
        try:
            res = requests.get(url, headers=headers, timeout=15)
            if res.status_code == 200:
                all_rows.extend(res.json().get("data", []))
        except: pass
        progress_bar.progress((i + 1) / 14)
        time.sleep(13)
        
    status_text.empty()
    progress_bar.empty()
    return all_rows

# --- 6. メイン実行 ---
if st.button("スクリーニング開始"):
    master_df = get_brand_master()
    
    with st.spinner("ボスの規律に基づき解析中..."):
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
            
            # マスターデータとマージ
            if not master_df.empty:
                summary = pd.merge(summary, master_df, on='Code', how='left')
            
            # --- 鉄の掟（フィルター）適用 ---
            summary = summary[summary['latest_close'] >= min_price]
            if exclude_short_spike:
                summary = summary[summary['latest_close'] < (summary['recent_low'] * 2.0)]
            if exclude_long_peak:
                summary = summary[summary['latest_close'] < (summary['recent_low'] * 3.0)]
            if target_sector:
                summary = summary[summary['Sector'].isin(target_sector)]
            
            summary['current_ratio'] = summary['latest_close'] / summary['recent_high']
            if only_buy_signal:
                summary = summary[summary['current_ratio'] <= 0.50]
            
            results = summary.sort_values('current_ratio').head(30)
            st.success(f"審査完了: {len(results)} 銘柄を表示")
            
            for _, row in results.iterrows():
                st.divider()
                name = row['CompanyName'] if not pd.isna(row['CompanyName']) else "不明"
                st.subheader(f"{name} ({row['Code'][:-1]})")
                
                sector = row['Sector'] if not pd.isna(row['Sector']) else "-"
                market = row['Market'] if not pd.isna(row['Market']) else "-"
                m_cap = f"{int(row['MarketCap']/100000000)}億円" if not pd.isna(row['MarketCap']) else "-"
                st.caption(f"市場: {market} | 業種: {sector} | 時価総額: {m_cap}")
                
                c1, c2, c3 = st.columns(3)
                ratio_pct = int(row['current_ratio'] * 100)
                c1.metric("📉 現在水準", f"{ratio_pct}%", delta=f"{ratio_pct-50}%" if ratio_pct > 50 else "🎯 SIGNAL", delta_color="inverse")
                c2.metric("最新終値", f"{int(row['latest_close'])}円")
                c3.metric("🎯 買値目安(50%)", f"{int(row['recent_high'] * 0.50)}円")
