import streamlit as st
import requests
import pandas as pd
import time
from datetime import datetime, timedelta

# --- 1. ページ設定 ---
st.set_page_config(page_title="J-Quants 戦略スクリーナー (V8.1)", layout="wide")
st.title("🛡️ J-Quants 戦略アドバイザー (V8.1)")

# --- 2. 認証情報 ---
API_KEY = st.secrets["JQUANTS_API_KEY"].strip()
headers = {"x-api-key": API_KEY}
BASE_URL = "https://api.jquants.com/v2"

# --- 3. 銘柄マスター (CSV優先 + 強固な予備データ) ---
@st.cache_data
def load_brand_master():
    try:
        master = pd.read_csv("brands.csv")
        master['Code'] = master['Code'].astype(str)
        return master
    except:
        # CSVがない場合の予備（ボスが注目する銘柄を網羅）
        fallback = [
            {"Code": "81050", "CompanyName": "堀田丸正", "Sector": "卸売業"},
            {"Code": "91010", "CompanyName": "日本郵船", "Sector": "海運業"},
            {"Code": "72030", "CompanyName": "トヨタ自動車", "Sector": "輸送用機器"},
            {"Code": "99840", "CompanyName": "ソフトバンクG", "Sector": "情報・通信業"}
        ]
        return pd.DataFrame(fallback)

# --- 4. サイドバー設定（全フィルター復元） ---
st.sidebar.header("🔍 鉄の掟（フィルター）")
min_price = st.sidebar.number_input("① 株価下限 (円)", value=200, step=100)
exclude_short_spike = st.sidebar.checkbox("② 短期2倍急騰を除外", value=True)
exclude_long_peak = st.sidebar.checkbox("③ 3倍以上上げ切りを除外", value=True)
exclude_ipo = st.sidebar.checkbox("④ IPO除外 (上場1年未満)", value=True)
exclude_going_concern = st.sidebar.checkbox("⑤ 疑義注記銘柄を除外", value=True)

st.sidebar.divider()
only_buy_signal = st.sidebar.checkbox("買値目安(50%以下)のみ表示", value=True)
target_sector = st.sidebar.multiselect("業種絞り込み", ["卸売業", "情報・通信業", "サービス業", "電気機器", "小売業", "不動産業", "機械"])

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
    
    with st.spinner("全フィルター ＆ 50%ライン解析を実行中..."):
        raw_data = get_historical_data()
        
        if not raw_data:
            st.error("データの取得に失敗しました。")
        else:
            df = pd.DataFrame(raw_data)
            # 数値変換（エラー回避）
            for col in ['AdjC', 'AdjH', 'AdjL']:
                if col in df.columns:
                    df[col] = pd.to_numeric(df[col], errors='coerce')
            
            # 銘柄ごとに集計
            summary = df.groupby('Code').agg({
                'AdjC': 'last',
                'AdjH': 'max',
                'AdjL': 'min'
            }).reset_index()
            summary.columns = ['Code', 'latest_close', 'recent_high', 'recent_low']
            
            # マスター紐付け
            summary = pd.merge(summary, master_df, on='Code', how='left')
            
            # --- 鉄の掟（フィルター）適用 ---
            summary = summary[summary['latest_close'] >= min_price] # ①
            
            if exclude_short_spike: # ②
                summary = summary[summary['latest_close'] < (summary['recent_low'] * 2.0)]
                
            if exclude_long_peak: # ④
                summary = summary[summary['latest_close'] < (summary['recent_low'] * 3.0)]
            
            if exclude_ipo and 'ListingDate' in summary.columns: # ⑤
                one_year_ago = (datetime(2025, 11, 28) - timedelta(days=365)).strftime('%Y-%m-%d')
                summary = summary[summary['ListingDate'] <= one_year_ago]
            
            if exclude_going_concern and 'CompanyName' in summary.columns: # ⑥
                summary = summary[~summary['CompanyName'].str.contains("疑義|重要事象", na=False)]
                
            if target_sector:
                summary = summary[summary['Sector'].isin(target_sector)]
            
            # 水準計算
            summary['current_ratio'] = summary['latest_close'] / summary['recent_high']
            if only_buy_signal:
                summary = summary[summary['current_ratio'] <= 0.50]
            
            results = summary.sort_values('current_ratio').head(30)
            st.success(f"審査完了: {len(results)} 銘柄が規律をクリア")
            
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

                # チャート（推移と目標ラインを分離して表示）
                history_df = df[df['Code'] == row['Code']].sort_values('Date')
                if not history_df.empty:
                    chart_data = history_df.set_index('Date')[['AdjC']].rename(columns={'AdjC': '実績株価'})
                    chart_data['目標ライン(50%)'] = target_50
                    st.line_chart(chart_data)
