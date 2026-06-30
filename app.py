import streamlit as st
import pandas as pd
import numpy as np
from typing import List, Dict, Tuple, Optional
import datetime

# ==========================================
# 0. システム設定 & UI初期化
# ==========================================
st.set_page_config(page_title="Project AEGIS", page_icon="🛡️", layout="wide")

# ==========================================
# 1. コア・ロジック（絶対遵守事項）
# ==========================================
def calculate_atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    """14日ATRを算出（J-Quants V2 カラム仕様）"""
    high = df['AdjH']
    low = df['AdjL']
    close_prev = df['AdjC'].shift(1)
    
    tr1 = high - low
    tr2 = (high - close_prev).abs()
    tr3 = (low - close_prev).abs()
    
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    return tr.rolling(window=period).mean()

def apply_core_risk_management(entry_price: float, support_price: float, atr: float) -> Optional[Dict]:
    """
    いかなるシグナル点灯時も自動計算されるリスク管理モジュール
    - SLはサポート直下に配置
    - 最大許容リスク：-8.0%以内
    - リスクリワード (RR) 最低1:2の確保
    """
    # ノイズ幅（ATR）を考慮してサポートの少し下にSLを置く（ここではATRの0.5倍とする）
    sl_price = support_price - (atr * 0.5)
    
    # 最大許容リスクのチェック（-8.0%以内）
    risk_pct = (entry_price - sl_price) / entry_price
    if risk_pct > 0.08 or risk_pct <= 0:
        return None # Drop（除外）
    
    risk_amount = entry_price - sl_price
    
    # RR = 1:2 となるようにTPを算出
    tp1_price = entry_price + (risk_amount * 2.0)
    tp2_price = entry_price + (risk_amount * 3.0) # TP2はRR 1:3に設定
    
    return {
        "Entry": entry_price,
        "TP1": tp1_price,
        "TP2": tp2_price,
        "SL": sl_price,
        "RR": "1:2+"
    }

# ==========================================
# 2. スクリーニング・モジュール
# ==========================================
def pair_snipe_engine(df_dict: Dict[str, pd.DataFrame], sector_pairs: List[Tuple[str, str]]) -> List[Dict]:
    """モジュール1：裁定狙撃（ペア・スナイプ）エンジン"""
    results = []
    for ticker_a, ticker_b in sector_pairs:
        if ticker_a not in df_dict or ticker_b not in df_dict:
            continue
            
        df_a = df_dict[ticker_a].tail(60).copy()
        df_b = df_dict[ticker_b].tail(60).copy()
        
        if len(df_a) < 60 or len(df_b) < 60:
            continue
            
        corr = df_a['AdjC'].corr(df_b['AdjC'])
        if corr < 0.8:
            continue
            
        spread = df_a['AdjC'] / df_b['AdjC']
        spread_mean = spread.rolling(20).mean()
        spread_std = spread.rolling(20).std()
        
        latest_spread = spread.iloc[-1]
        latest_mean = spread_mean.iloc[-1]
        latest_std = spread_std.iloc[-1]
        
        if latest_spread > latest_mean + (2 * latest_std):
            results.append({
                "モジュール名(戦術)": "裁定狙撃 (ペア・スナイプ)",
                "銘柄コード": f"Short:{ticker_a} / Long:{ticker_b}",
                "エントリー価格/条件": f"スプレッド +2σ乖離 (Corr: {corr:.2f})",
                "TP1": "-", "TP2": "-", "SL": "-", "RR": "1:2+"
            })
    return results

def abyss_engine(ticker: str, df: pd.DataFrame) -> Optional[Dict]:
    """モジュール2：深淵の底引き（アビス）検知エンジン"""
    if len(df) < 50:
        return None
        
    df = df.copy()
    df['ATR'] = calculate_atr(df, 14)
    
    delta = df['AdjC'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
    rs = gain / loss
    df['RSI'] = 100 - (100 / (1 + rs))
    
    df['SMA20'] = df['AdjC'].rolling(20).mean()
    df['STD20'] = df['AdjC'].rolling(20).std()
    df['BB_minus3'] = df['SMA20'] - (3 * df['STD20'])
    df['Vol_SMA50'] = df['AdjVo'].rolling(50).mean()
    
    latest = df.iloc[-1]
    prev = df.iloc[-2]
    
    cond1 = latest['RSI'] <= 20
    cond2 = (latest['AdjL'] <= latest['BB_minus3']) or (latest['AdjC'] <= latest['BB_minus3'])
    cond3 = latest['AdjVo'] >= latest['Vol_SMA50'] * 5.0
    
    body = abs(latest['AdjC'] - latest['AdjO'])
    lower_wick = min(latest['AdjO'], latest['AdjC']) - latest['AdjL']
    upper_wick = latest['AdjH'] - max(latest['AdjO'], latest['AdjC'])
    
    is_takuri = (lower_wick >= body * 2.0) and (lower_wick > upper_wick)
    prev_body_is_red = prev['AdjC'] < prev['AdjO']
    curr_body_is_green = latest['AdjC'] > latest['AdjO']
    is_engulfing = prev_body_is_red and curr_body_is_green and (latest['AdjC'] >= prev['AdjO']) and (latest['AdjO'] <= prev['AdjC'])
    
    cond4 = is_takuri or is_engulfing
    
    if cond1 and cond2 and cond3 and cond4:
        entry = latest['AdjC']
        support = latest['AdjL']
        risk_data = apply_core_risk_management(entry, support, latest['ATR'])
        
        if risk_data:
            return {
                "モジュール名(戦術)": "深淵の底引き (アビス)",
                "銘柄コード": ticker,
                "エントリー価格/条件": f"{risk_data['Entry']:.1f} (RSI<=20, 出来高5倍)",
                "TP1": f"{risk_data['TP1']:.1f}",
                "TP2": f"{risk_data['TP2']:.1f}",
                "SL": f"{risk_data['SL']:.1f}",
                "RR": risk_data['RR']
            }
    return None

def post_assault_engine(ticker: str, df: pd.DataFrame, earnings_dates: List[str]) -> Optional[Dict]:
    """モジュール3：事後確信（ポスト・アサルト）検知エンジン"""
    if len(df) < 60:
        return None
        
    df = df.copy()
    df['ATR'] = calculate_atr(df, 14)
    latest = df.iloc[-1]
    prev = df.iloc[-2]
    
    latest_date_str = latest.name.strftime('%Y-%m-%d') if isinstance(latest.name, pd.Timestamp) else str(latest.get('Date', ''))
    prev_date_str = prev.name.strftime('%Y-%m-%d') if isinstance(prev.name, pd.Timestamp) else str(prev.get('Date', ''))
    
    cond1 = (latest_date_str in earnings_dates) or (prev_date_str in earnings_dates)
    gap_pct = (latest['AdjO'] - prev['AdjC']) / prev['AdjC'] if prev['AdjC'] != 0 else 0
    cond2 = gap_pct >= 0.05
    
    vol_max_60 = df['AdjVo'].tail(60).max()
    cond3 = latest['AdjVo'] == vol_max_60
    cond4 = latest['AdjC'] > latest['AdjO']
    
    if cond1 and cond2 and cond3 and cond4:
        entry_high = latest['AdjH']
        entry_low_zone = (latest['AdjH'] + latest['AdjL']) / 2.0
        entry_target = entry_low_zone
        
        support = latest['AdjL']
        risk_data = apply_core_risk_management(entry_target, support, latest['ATR'])
        
        if risk_data:
            return {
                "モジュール名(戦術)": "事後確信 (ポスト・アサルト)",
                "銘柄コード": ticker,
                "エントリー価格/条件": f"{entry_target:.1f} - {entry_high:.1f} (半値戻し)",
                "TP1": f"{risk_data['TP1']:.1f}",
                "TP2": f"{risk_data['TP2']:.1f}",
                "SL": f"{risk_data['SL']:.1f}",
                "RR": risk_data['RR']
            }
    return None

# ==========================================
# 3. モックデータ生成（API連携前のテスト用）
# ==========================================
def generate_mock_data(scenario: str) -> pd.DataFrame:
    """UIテスト用に条件を満たすダミーデータを生成する"""
    dates = pd.date_range(end=datetime.date.today(), periods=60)
    df = pd.DataFrame(index=dates)
    df['Date'] = dates.strftime('%Y-%m-%d')
    
    base_price = 1000.0
    df['AdjO'] = np.random.normal(base_price, 10, 60)
    df['AdjC'] = df['AdjO'] + np.random.normal(0, 15, 60)
    df['AdjH'] = df[['AdjO', 'AdjC']].max(axis=1) + np.random.uniform(5, 20, 60)
    df['AdjL'] = df[['AdjO', 'AdjC']].min(axis=1) - np.random.uniform(5, 20, 60)
    df['AdjVo'] = np.random.randint(100000, 500000, 60)
    
    if scenario == "abyss":
        # RSI低下、-3σ到達、出来高5倍、たくり線の偽装
        df.iloc[-2, df.columns.get_loc('AdjC')] = 800  # 前日大陰線
        df.iloc[-2, df.columns.get_loc('AdjO')] = 900
        df.iloc[-1, df.columns.get_loc('AdjO')] = 780
        df.iloc[-1, df.columns.get_loc('AdjC')] = 790
        df.iloc[-1, df.columns.get_loc('AdjL')] = 600  # 長い下髭
        df.iloc[-1, df.columns.get_loc('AdjH')] = 800
        df.iloc[-1, df.columns.get_loc('AdjVo')] = 3000000  # 出来高急増
        
    elif scenario == "post_assault":
        # GapUp、最大出来高、大陽線
        df.iloc[-2, df.columns.get_loc('AdjC')] = 1000
        df.iloc[-1, df.columns.get_loc('AdjO')] = 1060 # +6% Gap Up
        df.iloc[-1, df.columns.get_loc('AdjC')] = 1150 # 大陽線
        df.iloc[-1, df.columns.get_loc('AdjH')] = 1160
        df.iloc[-1, df.columns.get_loc('AdjL')] = 1050
        df.iloc[-1, df.columns.get_loc('AdjVo')] = 5000000 # 最大出来高

    return df

# ==========================================
# 4. Streamlit フロントエンド
# ==========================================
def main():
    st.title("Project AEGIS - Tactical Screening Engine")
    
    # --- 認証（ログイン）フェーズ ---
    if "authenticated" not in st.session_state:
        st.session_state["authenticated"] = False
        st.session_state["api_key"] = ""

    if not st.session_state["authenticated"]:
        st.markdown("### System Authentication")
        st.info("J-Quants API V2 はAPIキー方式を採用している。認証のため、ダッシュボードで発行したAPIキーを入力せよ。")
        
        api_key_input = st.text_input("J-Quants API Key (x-api-key)", type="password")
        
        if st.button("Initialize System (Login)"):
            if api_key_input.strip() == "":
                st.error("エラー: APIキーが入力されていない。")
            else:
                # ここで本来は /v2/equities/master などを叩いてキーの有効性テストを行う
                st.session_state["api_key"] = api_key_input
                st.session_state["authenticated"] = True
                st.rerun()
        return

    # --- メインダッシュボードフェーズ ---
    st.sidebar.success("🟢 System Online")
    st.sidebar.markdown(f"**Active API Key:** `...{st.session_state['api_key'][-4:]}`")
    
    if st.sidebar.button("System Shutdown (Logout)"):
        st.session_state["authenticated"] = False
        st.session_state["api_key"] = ""
        st.rerun()

    st.sidebar.markdown("---")
    st.sidebar.warning("※現在、データソースは内部のモックジェネレーターに接続されている。実運用時は `requests.get` 等を用いてJ-Quants API V2のエンドポイントへ接続を切り替えること。")

    st.markdown("### 実行モジュール選択")
    tab1, tab2, tab3 = st.tabs(["[M1] 裁定狙撃", "[M2] 深淵の底引き", "[M3] 事後確信"])

    # --- モジュール1 UI ---
    with tab1:
        st.subheader("モジュール1：裁定狙撃（ペア・スナイプ）")
        st.write("同一セクター内の相関崩れ（+2σ乖離）を検知し、スプレッドの収束を狙う。")
        col1, col2 = st.columns(2)
        ticker_a = col1.text_input("銘柄A (Short候補)", value="7203")
        ticker_b = col2.text_input("銘柄B (Long候補)", value="7267")
        
        if st.button("Execute M1: Pair Snipe"):
            with st.spinner("スプレッド解析中..."):
                # モックデータ生成
                df_a = generate_mock_data("normal")
                df_b = generate_mock_data("normal")
                # 無理やり相関と乖離を作る（テスト用）
                df_b['AdjC'] = df_a['AdjC'] * 0.95 
                df_b.iloc[-1, df_b.columns.get_loc('AdjC')] = df_a['AdjC'].iloc[-1] * 0.80 # 乖離発生
                
                df_dict = {ticker_a: df_a, ticker_b: df_b}
                results = pair_snipe_engine(df_dict, [(ticker_a, ticker_b)])
                
                if results:
                    st.success("Target Locked.")
                    st.table(pd.DataFrame(results))
                else:
                    st.info("条件に合致するシグナルは検知されなかった。")

    # --- モジュール2 UI ---
    with tab2:
        st.subheader("モジュール2：深淵の底引き（アビス）")
        st.write("大衆のパニック（セリング・クライマックス）を数学的に証明し、逆張りで捕捉する。")
        ticker_abyss = st.text_input("監視対象銘柄コード (M2)", value="9984")
        
        if st.button("Execute M2: Abyss"):
            with st.spinner("RSI及びボリンジャーバンド解析中..."):
                df_abyss = generate_mock_data("abyss")
                result = abyss_engine(ticker_abyss, df_abyss)
                
                if result:
                    st.success("Target Locked.")
                    st.table(pd.DataFrame([result]))
                else:
                    st.info("条件に合致するシグナルは検知されなかった。")

    # --- モジュール3 UI ---
    with tab3:
        st.subheader("モジュール3：事後確信（ポスト・アサルト）")
        st.write("決算発表直後の機関投資家の資金流入（大陽線・最大出来高・Gap Up）に順張りで追従する。")
        ticker_post = st.text_input("監視対象銘柄コード (M3)", value="6861")
        
        # 今日を決算日としてモック設定
        today_str = datetime.date.today().strftime('%Y-%m-%d')
        earnings_date = st.text_input("対象決算日 (YYYY-MM-DD)", value=today_str)
        
        if st.button("Execute M3: Post-Assault"):
            with st.spinner("プライスアクション解析中..."):
                df_post = generate_mock_data("post_assault")
                result = post_assault_engine(ticker_post, df_post, [earnings_date])
                
                if result:
                    st.success("Target Locked.")
                    st.table(pd.DataFrame([result]))
                else:
                    st.info("条件に合致するシグナルは検知されなかった。")

if __name__ == "__main__":
    main()
