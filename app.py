import streamlit as st
import pandas as pd
import numpy as np
import datetime
import itertools
from typing import List, Dict, Tuple, Optional
import plotly.graph_objects as go
from plotly.subplots import make_subplots

# ==========================================
# 0. システム設定 & UI初期化
# ==========================================
st.set_page_config(page_title="Project AEGIS | Quant Dashboard", page_icon="🛡️", layout="wide", initial_sidebar_state="expanded")

# ==========================================
# 1. 銘柄マスター＆モックデータ生成 (API連携までの代替)
# ==========================================
# 実運用時はAPIから全上場銘柄リスト（/v2/equities/master）を取得します
MOCK_SECTORS = ["電気機器", "輸送用機器", "情報・通信業", "銀行業", "小売業"]
MOCK_TICKERS = {
    "電気機器": ["6501", "6502", "6752", "6758", "6861"],
    "輸送用機器": ["7201", "7203", "7267", "7269"],
    "情報・通信業": ["9432", "9433", "9434", "9984"],
    "銀行業": ["8306", "8316", "8411"],
    "小売業": ["8267", "9983", "7453"]
}
ALL_TICKERS = [t for sublist in MOCK_TICKERS.values() for t in sublist]

@st.cache_data
def generate_market_data() -> Dict[str, pd.DataFrame]:
    """全銘柄の日足ダミーデータを一括生成（実際のAPI通信処理に置き換わる部分）"""
    np.random.seed(42)
    dates = pd.date_range(end=datetime.date.today(), periods=60)
    market_data = {}
    
    # セクターごとのトレンドを生成（M1の相関用）
    sector_trends = {sec: np.cumsum(np.random.normal(0, 5, 60)) for sec in MOCK_SECTORS}
    
    for sector, tickers in MOCK_TICKERS.items():
        for i, ticker in enumerate(tickers):
            df = pd.DataFrame(index=dates)
            df['Date'] = dates.strftime('%Y-%m-%d')
            base_price = np.random.randint(500, 5000)
            
            # セクタートレンド + 個別ノイズ
            trend = sector_trends[sector] + np.cumsum(np.random.normal(0, 2, 60))
            df['AdjC'] = base_price + trend
            df['AdjO'] = df['AdjC'].shift(1).fillna(base_price) + np.random.normal(0, 5, 60)
            df['AdjH'] = df[['AdjO', 'AdjC']].max(axis=1) + np.random.uniform(2, 15, 60)
            df['AdjL'] = df[['AdjO', 'AdjC']].min(axis=1) - np.random.uniform(2, 15, 60)
            df['AdjVo'] = np.random.randint(100000, 1000000, 60)
            
            # --- 意図的なシグナル発生（デモ用） ---
            # M1: 特定ペアの乖離 (7201 と 7203)
            if ticker == "7201":
                df.iloc[-1, df.columns.get_loc('AdjC')] *= 0.85 
            # M2: アビス条件 (9984)
            if ticker == "9984":
                df.iloc[-2, df.columns.get_loc('AdjC')] = df['AdjO'].iloc[-2] * 0.90 # 大陰線
                df.iloc[-1, df.columns.get_loc('AdjO')] = df['AdjC'].iloc[-2] * 0.98
                df.iloc[-1, df.columns.get_loc('AdjC')] = df['AdjO'].iloc[-1] * 1.01
                df.iloc[-1, df.columns.get_loc('AdjL')] = df['AdjC'].iloc[-1] * 0.85 # たくり線
                df.iloc[-1, df.columns.get_loc('AdjVo')] *= 6 # 出来高急増
            # M3: ポスト・アサルト条件 (6861)
            if ticker == "6861":
                df.iloc[-1, df.columns.get_loc('AdjO')] = df['AdjC'].iloc[-2] * 1.06 # +6% Gap Up
                df.iloc[-1, df.columns.get_loc('AdjC')] = df['AdjO'].iloc[-1] * 1.04 # 大陽線
                df.iloc[-1, df.columns.get_loc('AdjH')] = df['AdjC'].iloc[-1] * 1.01
                df.iloc[-1, df.columns.get_loc('AdjL')] = df['AdjO'].iloc[-1] * 0.99
                df.iloc[-1, df.columns.get_loc('AdjVo')] = df['AdjVo'].max() * 2 # 最大出来高

            market_data[ticker] = df.ffill().bfill()
            
    return market_data

@st.cache_data
def generate_earnings_calendar() -> Dict[str, str]:
    """モック用の決算カレンダー (Ticker: Date)"""
    today_str = datetime.date.today().strftime('%Y-%m-%d')
    return {"6861": today_str, "6501": today_str}

# ==========================================
# 2. 共通ロジック＆描画エンジン
# ==========================================
def calculate_atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    tr = pd.concat([
        df['AdjH'] - df['AdjL'],
        (df['AdjH'] - df['AdjC'].shift(1)).abs(),
        (df['AdjL'] - df['AdjC'].shift(1)).abs()
    ], axis=1).max(axis=1)
    return tr.rolling(window=period).mean()

def apply_core_risk_management(entry: float, support: float, atr: float) -> Optional[Dict]:
    sl = support - (atr * 0.5)
    risk_pct = (entry - sl) / entry
    if risk_pct > 0.08 or risk_pct <= 0: return None
    risk_amt = entry - sl
    return {"Entry": entry, "TP1": entry + (risk_amt * 2.0), "TP2": entry + (risk_amt * 3.0), "SL": sl, "RR": "1:2+"}

def plot_interactive_chart(df: pd.DataFrame, ticker: str, entry: float=None, sl: float=None, tp1: float=None):
    """Plotlyによるインタラクティブなローソク足チャートの描画"""
    fig = make_subplots(rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.03, row_heights=[0.7, 0.3])
    
    # ローソク足
    fig.add_trace(go.Candlestick(x=df['Date'], open=df['AdjO'], high=df['AdjH'], low=df['AdjL'], close=df['AdjC'], name="Price"), row=1, col=1)
    
    # ボリンジャーバンド等の追加（M2等の分析用）
    sma = df['AdjC'].rolling(20).mean()
    fig.add_trace(go.Scatter(x=df['Date'], y=sma, line=dict(color='orange', width=1), name="SMA20"), row=1, col=1)
    
    # 出来高
    colors = ['green' if df['AdjC'].iloc[i] >= df['AdjO'].iloc[i] else 'red' for i in range(len(df))]
    fig.add_trace(go.Bar(x=df['Date'], y=df['AdjVo'], marker_color=colors, name="Volume"), row=2, col=1)

    # ライン描画（エントリー、SL、TP）
    if entry and entry != "-":
        fig.add_hline(y=float(entry), line_dash="dot", line_color="cyan", annotation_text="Entry", row=1, col=1)
    if sl and sl != "-":
        fig.add_hline(y=float(sl), line_dash="dash", line_color="red", annotation_text="SL", row=1, col=1)
    if tp1 and tp1 != "-":
        fig.add_hline(y=float(tp1), line_dash="dash", line_color="green", annotation_text="TP1", row=1, col=1)

    fig.update_layout(
        title=f"Advanced Chart: {ticker}",
        template="plotly_dark",
        xaxis_rangeslider_visible=False,
        height=500,
        margin=dict(l=20, r=20, t=40, b=20)
    )
    return fig

# ==========================================
# 3. スクリーニング・モジュール (自動スキャン対応)
# ==========================================
def auto_pair_snipe_engine(df_dict: Dict[str, pd.DataFrame], sector: str) -> List[Dict]:
    """モジュール1改修版：Long/Shortの方向とRRパラメーターの完全可視化"""
    tickers = MOCK_TICKERS.get(sector, [])
    pairs = list(itertools.combinations(tickers, 2))
    results = []
    
    for tk_a, tk_b in pairs:
        df_a = df_dict[tk_a].copy()
        df_b = df_dict[tk_b].copy()
        
        corr = df_a['AdjC'].corr(df_b['AdjC'])
        if corr < 0.8: continue
            
        # スプレッド = A / B
        spread = df_a['AdjC'] / df_b['AdjC']
        mean, std = spread.rolling(20).mean(), spread.rolling(20).std()
        
        latest_spread = spread.iloc[-1]
        upper_band = mean.iloc[-1] + (2 * std.iloc[-1])
        
        # Aが割高、Bが割安 (+2σ乖離) の場合
        if latest_spread > upper_band:
            # --- Long側 (B銘柄) の算出 ---
            atr_b = calculate_atr(df_b, 14).iloc[-1]
            rd_long = apply_core_risk_management(df_b['AdjC'].iloc[-1], df_b['AdjL'].iloc[-1], atr_b)
            
            # --- Short側 (A銘柄) の算出 ---
            # 空売りのため、SLは直近高値の「上」に置く
            atr_a = calculate_atr(df_a, 14).iloc[-1]
            entry_short = df_a['AdjC'].iloc[-1]
            sl_short = df_a['AdjH'].iloc[-1] + (atr_a * 0.5)
            risk_amt_a = sl_short - entry_short
            
            # リスクが適正(-8.0%以内)なら算出
            if rd_long and risk_amt_a > 0 and (risk_amt_a / entry_short) <= 0.08:
                tp1_short = entry_short - (risk_amt_a * 2.0)
                tp2_short = entry_short - (risk_amt_a * 3.0)
                
                # Long出力を追加
                results.append({
                    "戦術": "裁定狙撃", "銘柄コード": tk_b, "方向": "🟢 買い (Long)",
                    "Entry": f"{rd_long['Entry']:.1f}", "TP1": f"{rd_long['TP1']:.1f}", 
                    "TP2": f"{rd_long['TP2']:.1f}", "SL": f"{rd_long['SL']:.1f}", "条件": f"割安側 (Corr: {corr:.2f})"
                })
                # Short出力を追加
                results.append({
                    "戦術": "裁定狙撃", "銘柄コード": tk_a, "方向": "🔴 売り (Short)",
                    "Entry": f"{entry_short:.1f}", "TP1": f"{tp1_short:.1f}", 
                    "TP2": f"{tp2_short:.1f}", "SL": f"{sl_short:.1f}", "条件": f"割高側 (Corr: {corr:.2f})"
                })
    return results

def auto_abyss_engine(df_dict: Dict[str, pd.DataFrame]) -> List[Dict]:
    results = []
    for ticker, df_orig in df_dict.items():
        df = df_orig.copy()
        df['ATR'] = calculate_atr(df, 14)
        
        delta = df['AdjC'].diff()
        rs = (delta.clip(lower=0).rolling(14).mean()) / (-delta.clip(upper=0).rolling(14).mean())
        df['RSI'] = 100 - (100 / (1 + rs))
        
        std20 = df['AdjC'].rolling(20).std()
        df['BB_minus3'] = df['AdjC'].rolling(20).mean() - (3 * std20)
        df['Vol_SMA50'] = df['AdjVo'].rolling(50).mean()
        
        latest, prev = df.iloc[-1], df.iloc[-2]
        
        cond1 = latest['RSI'] <= 20
        cond2 = (latest['AdjL'] <= latest['BB_minus3']) or (latest['AdjC'] <= latest['BB_minus3'])
        cond3 = latest['AdjVo'] >= latest['Vol_SMA50'] * 5.0
        
        body = abs(latest['AdjC'] - latest['AdjO'])
        l_wick = min(latest['AdjO'], latest['AdjC']) - latest['AdjL']
        u_wick = latest['AdjH'] - max(latest['AdjO'], latest['AdjC'])
        
        is_takuri = (l_wick >= body * 2.0) and (l_wick > u_wick)
        is_engulf = (prev['AdjC'] < prev['AdjO']) and (latest['AdjC'] > latest['AdjO']) and (latest['AdjC'] >= prev['AdjO']) and (latest['AdjO'] <= prev['AdjC'])
        
        if cond1 and cond2 and cond3 and (is_takuri or is_engulf):
            rd = apply_core_risk_management(latest['AdjC'], latest['AdjL'], latest['ATR'])
            if rd:
                results.append({
                    "戦術": "深淵の底引き", "銘柄コード": ticker, "条件": f"RSI<=20, 出来高5倍",
                    "Entry": f"{rd['Entry']:.1f}", "TP1": f"{rd['TP1']:.1f}", "TP2": f"{rd['TP2']:.1f}", "SL": f"{rd['SL']:.1f}", "RR": rd['RR']
                })
    return results

def auto_post_assault_engine(df_dict: Dict[str, pd.DataFrame], earnings_cal: Dict[str, str], start_dt: str, end_dt: str) -> List[Dict]:
    results = []
    target_tickers = [tk for tk, dt in earnings_cal.items() if start_dt <= dt <= end_dt]
    
    for ticker in target_tickers:
        if ticker not in df_dict: continue
        df = df_dict[ticker].copy()
        df['ATR'] = calculate_atr(df, 14)
        latest, prev = df.iloc[-1], df.iloc[-2]
        
        gap_pct = (latest['AdjO'] - prev['AdjC']) / prev['AdjC'] if prev['AdjC'] != 0 else 0
        cond_gap = gap_pct >= 0.05
        cond_vol = latest['AdjVo'] == df['AdjVo'].tail(60).max()
        cond_bull = latest['AdjC'] > latest['AdjO']
        
        if cond_gap and cond_vol and cond_bull:
            entry_target = (latest['AdjH'] + latest['AdjL']) / 2.0
            rd = apply_core_risk_management(entry_target, latest['AdjL'], latest['ATR'])
            if rd:
                results.append({
                    "戦術": "事後確信", "銘柄コード": ticker, "条件": f"GapUp+5%, 最大出来高",
                    "Entry": f"{rd['Entry']:.1f}", "TP1": f"{rd['TP1']:.1f}", "TP2": f"{rd['TP2']:.1f}", "SL": f"{rd['SL']:.1f}", "RR": rd['RR']
                })
    return results

# ==========================================
# 4. Streamlit UI (ダッシュボード)
# ==========================================
def main():
    st.title("🛡️ Project AEGIS - Automated Tactical Dashboard")
    
    # 認証フェーズ
    if "authenticated" not in st.session_state:
        st.session_state["authenticated"] = False

    if not st.session_state["authenticated"]:
        st.info("System Locked. Enter API Key to initialize core engines.")
        api_key = st.text_input("J-Quants API Key", type="password")
        if st.button("Initialize System"):
            if api_key:
                st.session_state["authenticated"] = True
                st.rerun()
            else:
                st.error("API Key is required.")
        return

    # データロード
    with st.spinner("Loading Market Data..."):
        df_dict = generate_market_data()
        earnings_cal = generate_earnings_calendar()

    st.sidebar.success("🟢 Core Engines Online")
    if st.sidebar.button("Shutdown System"):
        st.session_state["authenticated"] = False
        st.rerun()
    st.sidebar.markdown("---")
    
    # タブ構成
    tab1, tab2, tab3 = st.tabs(["[M1] Sector Pair Snipe", "[M2] Global Abyss Scan", "[M3] Earnings Assault Scan"])

    # --- M1 UI ---
    # --- M1 UI ---
    with tab1:
        st.markdown("### 🎯 モジュール1: セクター全自動サヤ抜きスキャン")
        selected_sector = st.selectbox("ターゲット・セクターを選択", MOCK_SECTORS)
        
        if st.button("Scan Sector (M1)"):
            with st.spinner(f"{selected_sector}セクターの全ペアをスキャン中..."):
                results = auto_pair_snipe_engine(df_dict, selected_sector)
                if results:
                    # 2行で1ペア（Long/Short）となるため、件数表示を調整
                    st.success(f"{len(results)//2} ペア（計 {len(results)} 件のオーダー）を検知。")
                    st.dataframe(pd.DataFrame(results), use_container_width=True)
                    
                    # 詳細情報の展開（チャート）
                    for res in results:
                        ticker = res["銘柄コード"]
                        direction = res.get("方向", "")
                        
                        with st.expander(f"📊 チャート分析: {direction} [{ticker}]"):
                            # パラメーターが存在する場合のみチャートにラインを描画
                            entry_val = res["Entry"] if res["Entry"] != "-" else None
                            sl_val = res["SL"] if res["SL"] != "-" else None
                            tp1_val = res["TP1"] if res["TP1"] != "-" else None
                            
                            st.plotly_chart(plot_interactive_chart(
                                df_dict[ticker], 
                                ticker,
                                entry=entry_val,
                                sl=sl_val,
                                tp1=tp1_val
                            ), use_container_width=True)
                else:
                    st.info("現在、指定セクター内に統計的優位性のある歪みは存在しません。")

    # --- M2 UI ---
    with tab2:
        st.markdown("### 🕳️ モジュール2: 全市場セリング・クライマックス検知")
        st.write("ボタン一つで全銘柄（現在モックの全リスト）からパニック売りの底値をスキャンします。")
        
        if st.button("Execute Global Scan (M2)"):
            with st.spinner("全銘柄のボラティリティ及びRSIを解析中..."):
                results = auto_abyss_engine(df_dict)
                if results:
                    st.success(f"{len(results)} 件の極限反発ポイントを検知。")
                    st.dataframe(pd.DataFrame(results), use_container_width=True)
                    
                    for res in results:
                        ticker = res["銘柄コード"]
                        with st.expander(f"📊 戦術詳細 & チャート: {ticker}"):
                            st.plotly_chart(plot_interactive_chart(df_dict[ticker], ticker, res["Entry"], res["SL"], res["TP1"]), use_container_width=True)
                else:
                    st.info("条件に合致する銘柄は検知されませんでした。")

    # --- M3 UI ---
    with tab3:
        st.markdown("### 🚀 モジュール3: 決算資金流入スキャン")
        st.write("指定した期間内に決算を発表した全銘柄から、機関投資家の本気の買いを検知します。")
        
        col1, col2 = st.columns(2)
        start_date = col1.date_input("開始日", datetime.date.today() - datetime.timedelta(days=7))
        end_date = col2.date_input("終了日", datetime.date.today())
        
        if st.button("Scan Earnings (M3)"):
            with st.spinner("指定期間の決算銘柄のプライスアクションを解析中..."):
                start_dt_str = start_date.strftime('%Y-%m-%d')
                end_dt_str = end_date.strftime('%Y-%m-%d')
                results = auto_post_assault_engine(df_dict, earnings_cal, start_dt_str, end_dt_str)
                
                if results:
                    st.success(f"{len(results)} 件の資金流入トレンドを検知。")
                    st.dataframe(pd.DataFrame(results), use_container_width=True)
                    
                    for res in results:
                        ticker = res["銘柄コード"]
                        with st.expander(f"📊 戦術詳細 & チャート: {ticker}"):
                            st.plotly_chart(plot_interactive_chart(df_dict[ticker], ticker, res["Entry"], res["SL"], res["TP1"]), use_container_width=True)
                else:
                    st.info("指定期間内に条件を満たす決算銘柄は存在しません。")

if __name__ == "__main__":
    main()
