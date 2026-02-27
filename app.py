import streamlit as st
import requests
import pandas as pd
import time
from datetime import datetime, timedelta

# --- 1. ページ設定 ---
st.set_page_config(page_title="J-Quants 戦略スクリーナー (V7.4)", layout="wide")
st.title("🛡️ J-Quants 戦略アドバイザー (V7.4)")

# --- 2. 認証情報の取得 ---
API_KEY = st.secrets["JQUANTS_API_KEY"].strip()
headers = {"x-api-key": API_KEY}
BASE_URL = "https://api.jquants.com/v2"

# --- 3. 案A: 主要銘柄マスター ---
BRAND_MASTER = {
    "81050": {"name": "堀田丸正", "sector": "卸売業", "market": "スタンダード"},
    "91010": {"name": "日本郵船", "sector": "海運業", "market": "プライム"},
    "72030": {"name": "トヨタ自動車", "sector": "輸送用機器", "market": "プライム"},
}

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
    with st.spinner("ボスの規律 ＆ 全銘柄を多角分析中..."):
        raw_data = get_historical_data()
        
        if not raw_data:
            st.error("データの取得に失敗しました。")
        else:
            df = pd.DataFrame(raw_data)
            
            # 【エラー回避】存在するカラムだけを数値変換
            cols_to_convert = ['AdjC', 'AdjH', 'AdjL', 'AdjV', 'Volume']
            for col in cols_to_convert:
                if col in df.columns:
                    df[col] = pd.to_numeric(df[col], errors='coerce')
            
            # 出来高カラムの特定
            vol_col = 'Volume' if 'Volume' in df.columns else 'AdjV' if 'AdjV' in df.columns else None
            
            # 銘柄ごとに多角分析
            agg_dict = {
                'AdjC': ['last'],
                'AdjH': ['max'],
                'AdjL': ['min']
            }
            if vol_col:
                agg_dict[vol_col] = ['last', 'mean']
            
            summary = df.groupby('Code').agg(agg_dict).reset_index()
            summary.columns = ['Code', 'latest_close', 'recent_high', 'recent_low'] + (['latest_vol', 'avg_vol'] if vol_col else [])
            
            # フィルター適用
            summary = summary[summary['latest_close'] >= min_price]
            if exclude_short_spike:
                summary = summary[summary['latest_close'] < (summary['recent_low'] * 2.0)]
            
            summary['current_ratio'] = summary['latest_close'] / summary['recent_high']
            if vol_col:
                summary['vol_ratio'] = summary['latest_vol'] / summary['avg_vol']
            
            if only_buy_signal:
                summary = summary[summary['current_ratio'] <= 0.50]
            
            results = summary.sort_values('current_ratio').head(30)
            st.success(f"審査完了: {len(results)} 銘柄を表示")
            
            for _, row in results.iterrows():
                st.divider()
                code = row['Code']
                info = BRAND_MASTER.get(code, {"name": f"銘柄 {code[:-1]}", "sector": "-", "market": "-"})
                
                st.subheader(f"{info['name']} ({code[:-1]})")
                
                c1, c2, c3 = st.columns(3)
                ratio_pct = int(row['current_ratio'] * 100)
                c1.metric("📉 現在水準", f"{ratio_pct}%", delta=f"{ratio_pct-50}%" if ratio_pct > 50 else "🎯 SIGNAL", delta_color="inverse")
                
                # 案B: 出来高表示
                vol_ratio = row.get('vol_ratio', 1.0)
                c2.metric("最新終値", f"{int(row['latest_close'])}円", delta=f"出来高 {vol_ratio:.1f}倍" if vol_ratio > 1.5 else None)
                
                c3.metric("🎯 買値目安(50%)", f"{int(row['recent_high'] * 0.50)}円")

                # 案C: 簡易チャート（過去推移）
                history_df = df[df['Code'] == code].sort_values('Date')
                if not history_df.empty:
                    st.line_chart(history_df.set_index('Date')['AdjC'])
