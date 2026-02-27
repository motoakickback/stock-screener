import streamlit as st
import requests
import pandas as pd
import time
import os
import re
from datetime import datetime, timedelta
from io import BytesIO
import plotly.graph_objects as go

# --- 1. ページ設定 ---
st.set_page_config(page_title="J-Quants 戦略スクリーナー (V11.0)", layout="wide")
st.title("🛡️ J-Quants 戦略アドバイザー (V11.0)")

# --- 2. 認証情報 ---
API_KEY = st.secrets["JQUANTS_API_KEY"].strip()
headers = {"x-api-key": API_KEY}
BASE_URL = "https://api.jquants.com/v2"

# --- 3. 共通関数群 ---
def clean_dataframe(df):
    rename_cols = {
        'AdjustmentOpen': 'AdjO', 'AdjustmentHigh': 'AdjH',
        'AdjustmentLow': 'AdjL', 'AdjustmentClose': 'AdjC',
        'Open': 'AdjO', 'High': 'AdjH', 'Low': 'AdjL', 'Close': 'AdjC'
    }
    df = df.rename(columns=rename_cols)
    for col in ['AdjO', 'AdjH', 'AdjL', 'AdjC']:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors='coerce')
    # 日付でソートしてインデックスをリセット
    if 'Date' in df.columns:
        df = df.sort_values('Date').reset_index(drop=True)
    return df

@st.cache_data(ttl=86400)
def load_brand_master():
    try:
        req_headers = {'User-Agent': 'Mozilla/5.0'}
        page_url = "https://www.jpx.co.jp/markets/statistics-equities/misc/01.html"
        page_res = requests.get(page_url, headers=req_headers, timeout=10)
        match = re.search(r'href="([^"]+data_j\.xls)"', page_res.text)
        if match:
            excel_url = "https://www.jpx.co.jp" + match.group(1)
            res = requests.get(excel_url, headers=req_headers, timeout=15)
            df = pd.read_excel(BytesIO(res.content), engine='xlrd')
            df = df[['コード', '銘柄名', '33業種区分', '市場・商品区分']]
            df.columns = ['Code', 'CompanyName', 'Sector', 'Market']
            df['Code'] = df['Code'].astype(str) + "0"
            return df
    except: pass
    return pd.DataFrame()

def get_single_stock_data(code, years=3):
    base_date = datetime.utcnow() + timedelta(hours=9)
    from_date = (base_date - timedelta(days=365 * years)).strftime('%Y%m%d')
    to_date = base_date.strftime('%Y%m%d')
    url = f"{BASE_URL}/equities/bars/daily?code={code}&from={from_date}&to={to_date}"
    try:
        res = requests.get(url, headers=headers, timeout=15)
        if res.status_code == 200:
            return res.json().get("data", [])
    except: pass
    return []

# --- 4. UI構築（タブ分離） ---
tab1, tab2 = st.tabs(["🚀 実戦（スクリーナー）", "🔬 訓練（バックテスト）"])

# ==========================================
# タブ1: 実戦（スクリーナー） ※V10.3の機能
# ==========================================
with tab1:
    st.markdown("### 🌐 全銘柄スクリーニング（最新14日データ）")
    # ここにV10.3のスクリーニングロジックが入りますが、今回はバックテスト機能の提示に集中するため、
    # 簡略化してUIのみ配置しています（実際にはV10.3のコードを結合します）。
    st.info("※ スクリーニング機能はV10.3のロジックがそのまま稼働します（今回はタブ2の検証にフォーカスします）。")

# ==========================================
# タブ2: 訓練（バックテストエンジン）
# ==========================================
with tab2:
    st.markdown("### 📉 鉄の掟：3年間シミュレーション")
    
    col1, col2 = st.columns([1, 2])
    with col1:
        st.caption("対象銘柄の設定")
        bt_code = st.text_input("検証する銘柄コード（4桁）", value="8105", max_chars=4, key="bt_code")
        run_bt = st.button("🔥 3年間のバックテストを実行")
        
    with col2:
        st.caption("ボスのパラメーター（固定値）")
        st.markdown("""
        * **買値目安**: 過去14日の高値から **55%下落（高値の45%）**
        * **買い期限**: 高値到達から **4営業日以内**
        * **利益確定**: 買値から **+8%上昇**
        * **損切(ザラ場)**: 買値から **-10%下落**（最優先）
        * **損切(終値)**: 買値から **-8%下落**
        * **売り期限**: 購入から **5営業日経過**
        """)

    if run_bt and bt_code:
        code_with_suffix = bt_code + "0"
        with st.spinner(f"銘柄 {bt_code} の過去3年分のデータをAPIから抽出し、仮想売買を実行中..."):
            raw_data = get_single_stock_data(code_with_suffix, years=3)
            
            if not raw_data:
                st.error("データの取得に失敗しました。")
            else:
                df = clean_dataframe(pd.DataFrame(raw_data))
                
                # --- バックテストロジック ---
                trades = []
                position = None
                
                for i in range(14, len(df)):
                    today_data = df.iloc[i]
                    
                    if position is None:
                        # --- 買いの判定 ---
                        window = df.iloc[i-14 : i] # 過去14営業日
                        recent_high = window['AdjH'].max()
                        high_idx = window['AdjH'].idxmax()
                        days_since_high = i - high_idx
                        
                        # ルール: 高値から4日以内
                        if days_since_high <= 4:
                            # ルール: 55%押し（高値の45%）
                            buy_target = recent_high * 0.45 
                            
                            # ザラ場でターゲット価格に触れたか？
                            if today_data['AdjL'] <= buy_target:
                                # 窓を開けて下落して始まった場合は始値で約定
                                exec_price = min(today_data['AdjO'], buy_target)
                                position = {
                                    'buy_idx': i,
                                    'buy_date': today_data['Date'],
                                    'buy_price': exec_price,
                                    'high_ref': recent_high
                                }
                    else:
                        # --- 売りの判定 ---
                        buy_price = position['buy_price']
                        days_held = i - position['buy_idx']
                        
                        sell_price = 0
                        reason = ""
                        
                        # 1. ザラ場損切 (-10%)
                        sl_intraday = buy_price * 0.90
                        # 2. 利益確定 (+8%)
                        tp_target = buy_price * 1.08
                        # 3. 終値損切 (-8%)
                        sl_close = buy_price * 0.92
                        
                        # 悲観的判定：同じ日にTPとSL両方に触れた場合は、SL（損切）が先に発動したとみなす
                        if today_data['AdjL'] <= sl_intraday:
                            sell_price = min(today_data['AdjO'], sl_intraday) # 窓開け考慮
                            reason = "損切(ザラ場-10%)"
                        elif today_data['AdjH'] >= tp_target:
                            sell_price = max(today_data['AdjO'], tp_target) # 窓開け考慮
                            reason = "利確(+8%)"
                        elif today_data['AdjC'] <= sl_close:
                            sell_price = today_data['AdjC']
                            reason = "損切(終値-8%)"
                        elif days_held >= 5:
                            sell_price = today_data['AdjC']
                            reason = "時間切れ(5日経過)"
                            
                        # 決済実行
                        if reason != "":
                            profit_pct = (sell_price / buy_price) - 1
                            trades.append({
                                '購入日': position['buy_date'],
                                '決済日': today_data['Date'],
                                '保有日数': days_held,
                                '買値': round(buy_price, 1),
                                '売値': round(sell_price, 1),
                                '損益(%)': round(profit_pct * 100, 2),
                                '決済理由': reason
                            })
                            position = None # ポジションリセット
                
                # --- 結果の集計と表示 ---
                st.success("仮想売買シミュレーション完了")
                if len(trades) == 0:
                    st.warning(f"過去3年間で、銘柄 {bt_code} にボスの「鉄の掟」が発動した機会は0回でした。")
                else:
                    tdf = pd.DataFrame(trades)
                    total_trades = len(tdf)
                    wins = len(tdf[tdf['損益(%)'] > 0])
                    win_rate = (wins / total_trades) * 100
                    avg_profit = tdf[tdf['損益(%)'] > 0]['損益(%)'].mean() if wins > 0 else 0
                    avg_loss = tdf[tdf['損益(%)'] <= 0]['損益(%)'].mean() if wins < total_trades else 0
                    
                    # プロフィットファクター (総利益 / 総損失の絶対値)
                    sum_profit = tdf[tdf['損益(%)'] > 0]['損益(%)'].sum()
                    sum_loss = abs(tdf[tdf['損益(%)'] <= 0]['損益(%)'].sum())
                    pf = (sum_profit / sum_loss) if sum_loss > 0 else float('inf')
                    
                    m1, m2, m3, m4 = st.columns(4)
                    m1.metric("総トレード回数", f"{total_trades} 回")
                    m2.metric("勝率", f"{round(win_rate, 1)} %")
                    m3.metric("平均損益", f"{round(tdf['損益(%)'].mean(), 2)} %")
                    m4.metric("ﾌﾟﾛﾌｨｯﾄﾌｧｸﾀｰ", f"{round(pf, 2)}")
                    
                    st.divider()
                    st.markdown("#### 📜 全取引履歴")
                    st.dataframe(tdf, use_container_width=True)
