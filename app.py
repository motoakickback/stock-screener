import streamlit as st
import pandas as pd
import numpy as np
import datetime
import itertools
from typing import List, Dict, Tuple, Optional
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import requests
import time
import concurrent.futures
import threading

# ==========================================
# 0. システム設定 & UI初期化
# ==========================================
st.set_page_config(page_title="Project AEGIS | Quant Dashboard", page_icon="🛡️", layout="wide", initial_sidebar_state="expanded")

# ==========================================
# 1. API通信モジュール (Lightプラン: 60リクエスト/分 対応)
# ==========================================
HEADERS = lambda api_key: {"x-api-key": api_key}
API_DELAY = 1.05  # 1秒間に1リクエストの制限を守るための安全マージン

@st.cache_data(ttl=86400) # 1日キャッシュ
def fetch_jquants_master(api_key: str) -> pd.DataFrame:
    """全上場銘柄の一覧とセクター情報を取得"""
    url = "https://api.jquants.com/v2/equities/master"
    res = requests.get(url, headers=HEADERS(api_key))
    if res.status_code == 200:
        data = res.json().get("data", [])
        return pd.DataFrame(data)
    return pd.DataFrame()

@st.cache_data(ttl=3600) # 1時間キャッシュ
def fetch_jquants_daily_data(api_key: str, ticker: str) -> pd.DataFrame:
    """単一銘柄の株価四本値を過去分取得 (Lightプランの制約によりSleepを強制)"""
    time.sleep(API_DELAY) # レートリミット回避の絶対条件
    
    url = f"https://api.jquants.com/v2/equities/bars/daily?code={ticker}"
    res = requests.get(url, headers=HEADERS(api_key))
    if res.status_code == 200:
        data = res.json().get("data", [])
        df = pd.DataFrame(data)
        if not df.empty:
            df['Date'] = pd.to_datetime(df['Date'])
            df.set_index('Date', inplace=True, drop=False)
            
            # 必要なカラムをfloat型へキャスト
            cols = ['O', 'H', 'L', 'C', 'Vo', 'AdjO', 'AdjH', 'AdjL', 'AdjC', 'AdjVo']
            for c in cols:
                if c in df.columns:
                    df[c] = df[c].astype(float)
            return df
    return pd.DataFrame()

@st.cache_data(ttl=21600) # 6時間キャッシュ
def fetch_earnings_calendar(api_key: str) -> Dict[str, str]:
    """決算発表予定日の取得"""
    url = "https://api.jquants.com/v2/equities/earnings-calendar"
    res = requests.get(url, headers=HEADERS(api_key))
    earnings_dict = {}
    if res.status_code == 200:
        data = res.json().get("data", [])
        for item in data:
            if item.get("Code") and item.get("Date"):
                earnings_dict[item["Code"]] = item["Date"]
    return earnings_dict

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
    fig = make_subplots(rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.03, row_heights=[0.7, 0.3])
    fig.add_trace(go.Candlestick(x=df['Date'], open=df['AdjO'], high=df['AdjH'], low=df['AdjL'], close=df['AdjC'], name="Price"), row=1, col=1)
    
    sma = df['AdjC'].rolling(20).mean()
    fig.add_trace(go.Scatter(x=df['Date'], y=sma, line=dict(color='orange', width=1), name="SMA20"), row=1, col=1)
    
    colors = ['green' if df['AdjC'].iloc[i] >= df['AdjO'].iloc[i] else 'red' for i in range(len(df))]
    fig.add_trace(go.Bar(x=df['Date'], y=df['AdjVo'], marker_color=colors, name="Volume"), row=2, col=1)

    if entry and entry != "-": fig.add_hline(y=float(entry), line_dash="dot", line_color="cyan", annotation_text="Entry", row=1, col=1)
    if sl and sl != "-": fig.add_hline(y=float(sl), line_dash="dash", line_color="red", annotation_text="SL", row=1, col=1)
    if tp1 and tp1 != "-": fig.add_hline(y=float(tp1), line_dash="dash", line_color="green", annotation_text="TP1", row=1, col=1)

    fig.update_layout(title=f"Advanced Chart: {ticker}", template="plotly_dark", xaxis_rangeslider_visible=False, height=500, margin=dict(l=20, r=20, t=40, b=20))
    return fig

# ==========================================
# 3. スクリーニング・モジュール
# ==========================================
def auto_pair_snipe_engine(df_dict: Dict[str, pd.DataFrame], tickers: List[str]) -> List[Dict]:
    pairs = list(itertools.combinations(tickers, 2))
    results = []
    
    for tk_a, tk_b in pairs:
        if tk_a not in df_dict or tk_b not in df_dict: continue
        df_a, df_b = df_dict[tk_a], df_dict[tk_b]
        if len(df_a) < 60 or len(df_b) < 60: continue
        
        corr = df_a['AdjC'].tail(60).corr(df_b['AdjC'].tail(60))
        if corr < 0.8: continue
            
        spread = df_a['AdjC'] / df_b['AdjC']
        mean, std = spread.rolling(20).mean(), spread.rolling(20).std()
        
        if spread.iloc[-1] > mean.iloc[-1] + (2 * std.iloc[-1]):
            atr_b = calculate_atr(df_b, 14).iloc[-1]
            rd_long = apply_core_risk_management(df_b['AdjC'].iloc[-1], df_b['AdjL'].iloc[-1], atr_b)
            
            atr_a = calculate_atr(df_a, 14).iloc[-1]
            entry_short = df_a['AdjC'].iloc[-1]
            sl_short = df_a['AdjH'].iloc[-1] + (atr_a * 0.5)
            risk_amt_a = sl_short - entry_short
            
            if rd_long and risk_amt_a > 0 and (risk_amt_a / entry_short) <= 0.08:
                results.append({"戦術": "裁定狙撃", "銘柄コード": tk_b, "方向": "🟢 買い (Long)", "Entry": f"{rd_long['Entry']:.1f}", "TP1": f"{rd_long['TP1']:.1f}", "TP2": f"{rd_long['TP2']:.1f}", "SL": f"{rd_long['SL']:.1f}", "条件": f"割安側 (Corr: {corr:.2f})"})
                results.append({"戦術": "裁定狙撃", "銘柄コード": tk_a, "方向": "🔴 売り (Short)", "Entry": f"{entry_short:.1f}", "TP1": f"{entry_short - (risk_amt_a * 2.0):.1f}", "TP2": f"{entry_short - (risk_amt_a * 3.0):.1f}", "SL": f"{sl_short:.1f}", "条件": f"割高側 (Corr: {corr:.2f})"})
    return results

def auto_abyss_engine(df_dict: Dict[str, pd.DataFrame]) -> List[Dict]:
    results = []
    for ticker, df_orig in df_dict.items():
        if len(df_orig) < 50: continue
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
                results.append({"戦術": "深淵の底引き", "銘柄コード": ticker, "方向": "🟢 逆張り (Long)", "Entry": f"{rd['Entry']:.1f}", "TP1": f"{rd['TP1']:.1f}", "TP2": f"{rd['TP2']:.1f}", "SL": f"{rd['SL']:.1f}", "RR": rd['RR']})
    return results

def auto_post_assault_engine(df_dict: Dict[str, pd.DataFrame], earnings_cal: Dict[str, str], start_dt: str, end_dt: str) -> List[Dict]:
    results = []
    target_tickers = [tk for tk, dt in earnings_cal.items() if start_dt <= dt <= end_dt]
    
    for ticker in target_tickers:
        if ticker not in df_dict: continue
        df = df_dict[ticker].copy()
        if len(df) < 60: continue
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
                results.append({"戦術": "事後確信", "銘柄コード": ticker, "方向": "🟢 押し目買い (Long)","Entry": f"{rd['Entry']:.1f}", "TP1": f"{rd['TP1']:.1f}", "TP2": f"{rd['TP2']:.1f}", "SL": f"{rd['SL']:.1f}", "RR": rd['RR']})
    return results

# ==========================================
# 4. Streamlit UI
# ==========================================
def main():
    st.title("🛡️ Project AEGIS - Live Operations (Light Plan)")
    
    # 認証フェーズ
    if "authenticated" not in st.session_state:
        st.session_state["authenticated"] = False
        st.session_state["api_key"] = ""

    if not st.session_state["authenticated"]:
        st.info("System Locked. Enter J-Quants API Key to initialize.")
        api_key = st.text_input("J-Quants API Key (x-api-key)", type="password")
        if st.button("Initialize System"):
            if api_key:
                st.session_state["api_key"] = api_key
                st.session_state["authenticated"] = True
                st.rerun()
            else:
                st.error("API Key is required.")
        return

    api_key = st.session_state["api_key"]
    st.sidebar.success("🟢 API Connected")
    
    # 銘柄マスターの取得（初回のみ少し時間がかかる）
    with st.spinner("Fetching Market Master Data..."):
        df_master = fetch_jquants_master(api_key)
        if df_master.empty:
            st.error("マスターデータの取得に失敗しました。APIキーを確認してください。")
            st.stop()
            
    # 【新パッチ1: 業種マスターの完全解析と修復】
    sector_col = None
    sectors = []
    
    # V2のあらゆるカラム名の可能性をスキャン
    for col in ["Sector33CodeName", "Sector17CodeName", "17SectorName", "33SectorName"]:
        if col in df_master.columns:
            # ETF/REIT等の無効な業種（ハイフン等）を除外し、純粋なセクターのみを抽出
            valid_sectors = df_master[col].replace('-', np.nan).dropna().unique()
            valid_sectors = [s for s in valid_sectors if str(s).strip() != '']
            if len(valid_sectors) > 0:
                sector_col = col
                sectors = sorted(list(valid_sectors))
                break

    if not sectors:
        st.error("エラー: マスターデータから業種列を特定できませんでした。APIの仕様変更が疑われます。")
        st.stop()
            
    # 決定したカラム名でドロップダウン用のリストを生成
    sectors = sorted(df_master[sector_col].dropna().unique().tolist())
    
    st.sidebar.markdown(f"**Total Tickers:** {len(df_master)}")
    st.sidebar.markdown(f"**Rate Limit:** 60 req/min (1.05s delay)")
    if st.sidebar.button("Shutdown System"):
        st.session_state["authenticated"] = False
        st.rerun()

    st.markdown("### モジュール選択")
    tab1, tab2, tab3 = st.tabs(["[M1] Pair Snipe", "[M2] Abyss Scan", "[M3] Earnings Assault"])

    # 【新パッチ2: 限界スロットル・非同期フェッチエンジン】
    def fetch_data_for_tickers(tickers: List[str]) -> Dict[str, pd.DataFrame]:
        df_dict = {}
        progress_bar = st.progress(0)
        status_text = st.empty()
        total = len(tickers)
        completed = 0
        
        # 4並列で動かしつつ、APIへの攻撃を防ぐ（1.05秒間隔を絶対維持する）ためのロック機構
        rate_limit_lock = threading.Lock()
        
        def _fetch_task(tk):
            # API制限の壁（排他制御）: ここで全スレッドが整列し、必ず1.05秒に1回だけ通過する
            with rate_limit_lock:
                time.sleep(API_DELAY)
            
            # 通信（ネットワークI/O）自体は並列で進行し、ラグを吸収する
            df = fetch_jquants_daily_data(api_key, tk)
            return tk, df

        # 最大4スレッドで非同期実行
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
            future_to_tk = {executor.submit(_fetch_task, tk): tk for tk in tickers}
            
            for future in concurrent.futures.as_completed(future_to_tk):
                tk = future_to_tk[future]
                try:
                    tk_res, df = future.result()
                    if not df.empty:
                        df_dict[tk_res] = df
                except Exception as e:
                    pass # エラー時は無視して次へ
                
                completed += 1
                progress_bar.progress(completed / total)
                status_text.text(f"Fetching data: {tk} ({completed}/{total}) - 4-Thread Async I/O Active")
                
        status_text.text("Data fetching complete.")
        return df_dict

    # --- M1 UI ---
    with tab1:
        st.markdown("### 🎯 M1: セクター別 サヤ抜きスキャン")
        selected_sector_m1 = st.selectbox("ターゲット・セクターを選択 (M1)", sectors, key="m1_sec")
        
        if st.button("Execute M1 Scan"):
            target_tickers = df_master[df_master[sector_col] == selected_sector_m1]['Code'].tolist()
            st.warning(f"対象 {len(target_tickers)} 銘柄のデータを取得します。完了まで約 {len(target_tickers) * API_DELAY:.1f} 秒かかります。")
            
            df_dict_m1 = fetch_data_for_tickers(target_tickers)
            results_m1 = auto_pair_snipe_engine(df_dict_m1, target_tickers)
            
            if results_m1:
                st.success(f"{len(results_m1)//2} ペアの異常乖離を検知。")
                st.dataframe(pd.DataFrame(results_m1), use_container_width=True)
                for res in results_m1:
                    tk = res["銘柄コード"]
                    direction = res.get("方向", "")
                    with st.expander(f"📊 チャート: {direction} [{tk}]"):
                        st.plotly_chart(plot_interactive_chart(df_dict_m1[tk], tk, res.get("Entry"), res.get("SL"), res.get("TP1")), use_container_width=True)
            else:
                st.info("指定セクター内に優位性のある歪みは存在しません。")

    # --- M2 UI ---
    with tab2:
        st.markdown("### 🕳️ M2: セクター別 セリング・クライマックス検知")
        st.write("※Lightプランの制約上、全市場の一括スキャンは行えません。セクターを指定してください。")
        selected_sector_m2 = st.selectbox("ターゲット・セクターを選択 (M2)", sectors, key="m2_sec")
        
        if st.button("Execute M2 Scan"):
            target_tickers = df_master[df_master[sector_col] == selected_sector_m2]['Code'].tolist()
            st.warning(f"対象 {len(target_tickers)} 銘柄のデータを取得します。完了まで約 {len(target_tickers) * API_DELAY:.1f} 秒かかります。")
            
            df_dict_m2 = fetch_data_for_tickers(target_tickers)
            results_m2 = auto_abyss_engine(df_dict_m2)
            
            if results_m2:
                st.success(f"{len(results_m2)} 件の極限反発ポイントを検知。")
                st.dataframe(pd.DataFrame(results_m2), use_container_width=True)
                for res in results_m2:
                    tk = res["銘柄コード"]
                    with st.expander(f"📊 チャート: [{tk}]"):
                        st.plotly_chart(plot_interactive_chart(df_dict_m2[tk], tk, res.get("Entry"), res.get("SL"), res.get("TP1")), use_container_width=True)
            else:
                st.info("条件に合致する銘柄は検知されませんでした。")

    # --- M3 UI ---
    with tab3:
        st.markdown("### 🚀 M3: 決算資金流入スキャン")
        col1, col2 = st.columns(2)
        start_date = col1.date_input("開始日", datetime.date.today() - datetime.timedelta(days=3))
        end_date = col2.date_input("終了日", datetime.date.today())
        
        if st.button("Execute M3 Scan"):
            with st.spinner("決算カレンダーを取得中..."):
                earnings_cal = fetch_earnings_calendar(api_key)
                
            start_dt_str = start_date.strftime('%Y-%m-%d')
            end_dt_str = end_date.strftime('%Y-%m-%d')
            target_tickers = [tk for tk, dt in earnings_cal.items() if start_dt_str <= dt <= end_dt_str]
            
            if not target_tickers:
                st.info("指定期間に決算発表を行う銘柄は見つかりません。")
            else:
                st.warning(f"対象 {len(target_tickers)} 銘柄のデータを取得します。完了まで約 {len(target_tickers) * API_DELAY:.1f} 秒かかります。")
                df_dict_m3 = fetch_data_for_tickers(target_tickers)
                results_m3 = auto_post_assault_engine(df_dict_m3, earnings_cal, start_dt_str, end_dt_str)
                
                if results_m3:
                    st.success(f"{len(results_m3)} 件の資金流入トレンドを検知。")
                    st.dataframe(pd.DataFrame(results_m3), use_container_width=True)
                    for res in results_m3:
                        tk = res["銘柄コード"]
                        with st.expander(f"📊 チャート: [{tk}]"):
                            st.plotly_chart(plot_interactive_chart(df_dict_m3[tk], tk, res.get("Entry"), res.get("SL"), res.get("TP1")), use_container_width=True)
                else:
                    st.info("条件を満たす資金流入銘柄は存在しません。")

if __name__ == "__main__":
    main()
