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
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# ==========================================
# 0. システム設定 & UI初期化
# ==========================================
st.set_page_config(page_title="Project AEGIS v2.0", page_icon="🛡️", layout="wide", initial_sidebar_state="expanded")

# --- st.metric文字切れ防止パッチ ---
st.markdown("""
    <style>
    [data-testid="stMetricValue"] > div { text-overflow: clip !important; overflow: visible !important; white-space: nowrap !important; }
    [data-testid="stMetricValue"] { font-size: 1.4rem !important; }
    </style>
""", unsafe_allow_html=True)

# ==========================================
# 1. API通信モジュール (セッション永続化＆限界スロットル対応)
# ==========================================
HEADERS = lambda api_key: {"x-api-key": api_key}
API_DELAY = 1.05  # Lightプランの安全マージン

def get_session():
    """TCPハンドシェイクを省略し、通信ラグをゼロにする永続セッション（自動リトライ機構付き）"""
    if "api_session" not in st.session_state:
        session = requests.Session()
        retry = Retry(total=5, backoff_factor=1, status_forcelist=[429, 500, 502, 503, 504], allowed_methods=["GET"])
        adapter = HTTPAdapter(pool_connections=10, pool_maxsize=10, max_retries=retry)
        session.mount("https://", adapter)
        st.session_state["api_session"] = session
    return st.session_state["api_session"]

@st.cache_data(ttl=86400)
def fetch_jquants_master(api_key: str) -> pd.DataFrame:
    url = "https://api.jquants.com/v2/equities/master"
    try:
        res = get_session().get(url, headers=HEADERS(api_key), timeout=20)
        if res.status_code == 200:
            return pd.DataFrame(res.json().get("data", []))
        else:
            st.error(f"【J-Quants API 拒否応答】 Status Code: {res.status_code}")
            return pd.DataFrame()
    except requests.exceptions.RetryError:
        st.error("【システム・アラート】短期間のアクセス集中により、J-Quants APIの呼び出し上限（Lightプラン：60回/分）に到達しました。")
        st.warning("⏳ サーバーから一時的に遮断されています。約2〜3分間、何も操作せずに待機してから画面を更新してください。")
        return pd.DataFrame()
    except Exception as e:
        st.error(f"マスターデータ通信エラー: {e}")
        return pd.DataFrame()

def fetch_jquants_daily_data(api_key: str, ticker: str) -> pd.DataFrame:
    url = f"https://api.jquants.com/v2/equities/bars/daily?code={ticker}"
    try:
        res = get_session().get(url, headers=HEADERS(api_key), timeout=10)
        if res.status_code == 200:
            df = pd.DataFrame(res.json().get("data", []))
            if not df.empty:
                df['Date'] = pd.to_datetime(df['Date'])
                df.set_index('Date', inplace=True, drop=False)
                cols = ['O', 'H', 'L', 'C', 'Vo', 'AdjO', 'AdjH', 'AdjL', 'AdjC', 'AdjVo']
                for c in cols:
                    if c in df.columns:
                        df[c] = df[c].astype(float)
                return df
    except Exception:
        pass
    return pd.DataFrame()

@st.cache_data(ttl=21600)
def fetch_earnings_calendar(api_key: str) -> Dict[str, str]:
    url = "https://api.jquants.com/v2/equities/earnings-calendar"
    try:
        res = get_session().get(url, headers=HEADERS(api_key), timeout=10)
        earnings_dict = {}
        if res.status_code == 200:
            for item in res.json().get("data", []):
                if item.get("Code") and item.get("Date"):
                    earnings_dict[item["Code"]] = item["Date"]
        return earnings_dict
    except Exception:
        return {}

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
def auto_pair_snipe_engine_grouped(df_dict: Dict[str, pd.DataFrame], tickers: List[str]) -> Dict[str, List[Dict]]:
    pairs = list(itertools.combinations(tickers, 2))
    grouped_results = {}
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
                short_data = {"銘柄コード": tk_a, "方向": "🔴 売り (Short)", "Entry": f"{entry_short:.1f}", "TP1": f"{entry_short - (risk_amt_a * 2.0):.1f}", "TP2": f"{entry_short - (risk_amt_a * 3.0):.1f}", "SL": f"{sl_short:.1f}", "条件": f"割高側"}
                long_data = {"銘柄コード": tk_b, "方向": "🟢 買い (Long)", "Entry": f"{rd_long['Entry']:.1f}", "TP1": f"{rd_long['TP1']:.1f}", "TP2": f"{rd_long['TP2']:.1f}", "SL": f"{rd_long['SL']:.1f}", "条件": f"割安側 (Corr: {corr:.2f})"}
                if tk_a not in grouped_results: grouped_results[tk_a] = {"hub": short_data, "targets": []}
                grouped_results[tk_a]["targets"].append(long_data)
    return grouped_results

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
            if rd: results.append({"戦術": "深淵の底引き", "銘柄コード": ticker, "方向": "🟢 逆張り (Long)", "Entry": f"{rd['Entry']:.1f}", "TP1": f"{rd['TP1']:.1f}", "TP2": f"{rd['TP2']:.1f}", "SL": f"{rd['SL']:.1f}", "RR": rd['RR']})
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
            if rd: results.append({"戦術": "事後確信", "銘柄コード": ticker, "方向": "🟢 押し目買い (Long)","Entry": f"{rd['Entry']:.1f}", "TP1": f"{rd['TP1']:.1f}", "TP2": f"{rd['TP2']:.1f}", "SL": f"{rd['SL']:.1f}", "RR": rd['RR']})
    return results

# ==========================================
# 4. Streamlit UI (AEGIS v2.0)
# ==========================================
def main():
    st.title("🛡️ Project AEGIS v2.0 - Orchestration Dashboard")
    
    if "authenticated" not in st.session_state:
        st.session_state["authenticated"] = False
        st.session_state["api_key"] = ""
        st.session_state["data_pool"] = {}

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
    st.sidebar.info(f"🧠 Data Pool: {len(st.session_state['data_pool'])} tickers cached.")
    
    with st.spinner("Fetching Market Master Data..."):
        df_master = fetch_jquants_master(api_key)
        if df_master.empty: st.stop()
            
    sector_col = None
    sectors = []
    for col in ["S33Nm", "S17Nm"]:
        if col in df_master.columns:
            valid_sectors = df_master[col].replace('-', np.nan).dropna().unique()
            valid_sectors = [s for s in valid_sectors if str(s).strip() != '']
            if len(valid_sectors) > 0:
                sector_col = col
                sectors = sorted(list(valid_sectors))
                break

    if not sectors:
        st.error("エラー: マスターデータから業種列を特定できませんでした。")
        st.stop()

    if st.sidebar.button("Shutdown / Clear Cache"):
        st.session_state["authenticated"] = False
        st.session_state["data_pool"] = {}
        st.rerun()

    st.markdown("### モジュール選択")
    tab1, tab2, tab3 = st.tabs(["[M1] Pair Snipe", "[M2] Abyss Scan", "[M3] Earnings Assault"])

    def fetch_data_for_tickers(tickers: List[str]) -> Dict[str, pd.DataFrame]:
        df_dict = {}
        missing_tickers = [tk for tk in tickers if tk not in st.session_state["data_pool"]]
        
        # 取得済みのものはプールから即時展開 (空のDFも含む)
        for tk in tickers:
            if tk in st.session_state["data_pool"]:
                cached_df = st.session_state["data_pool"][tk]
                if not cached_df.empty:
                    df_dict[tk] = cached_df
                
        if not missing_tickers:
            st.toast(f"⚡ キャッシュ・ヒット: 対象 {len(tickers)} 銘柄を 0.01秒 で展開。", icon="⚡")
            return df_dict

        progress_bar = st.progress(0)
        status_text = st.empty()
        rate_limit_lock = threading.Lock()
        
        # 🎯 【修正】100銘柄以上の場合のみ「全市場一括（バルク）」を発動。
        if len(missing_tickers) >= 100:
            status_text.text("🔥 超高速バルク・フェッチ起動中 (対象多数のため全市場データを一括ダウンロード)...")
            
            rep_ticker = df_master['Code'].iloc[0]
            with rate_limit_lock: time.sleep(API_DELAY)
            rep_df = fetch_jquants_daily_data(api_key, rep_ticker)
            
            if not rep_df.empty:
                dates = rep_df['Date'].dt.strftime('%Y%m%d').tolist()[-60:]
                total_dates = len(dates)
                completed_dates = 0
                
                bulk_records = []
                session = get_session()
                headers = HEADERS(api_key)
                
                def _fetch_date(dt_str):
                    with rate_limit_lock: time.sleep(API_DELAY)
                    url = f"https://api.jquants.com/v2/equities/bars/daily?date={dt_str}"
                    all_data = []
                    while url:
                        try:
                            res = session.get(url, headers=headers, timeout=10)
                            if res.status_code == 200:
                                j = res.json()
                                all_data.extend(j.get("data", []))
                                pag_key = j.get("pagination_key")
                                url = f"https://api.jquants.com/v2/equities/bars/daily?date={dt_str}&pagination_key={pag_key}" if pag_key else None
                            else:
                                break
                        except Exception:
                            break
                    return all_data

                with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
                    future_to_dt = {executor.submit(_fetch_date, dt): dt for dt in dates}
                    for future in concurrent.futures.as_completed(future_to_dt):
                        try:
                            bulk_records.extend(future.result())
                        except Exception: pass
                        completed_dates += 1
                        progress_bar.progress(completed_dates / total_dates)
                        
                        # ⏳ 【修正】予想残り時間の表示 (バルク用)
                        eta_sec = int((total_dates - completed_dates) * API_DELAY)
                        status_text.text(f"🔥 全市場一括取得中 ({completed_dates}/{total_dates} 日分完了) | ⏳ 残り約 {eta_sec} 秒")
                
                status_text.text("⚙️ 巨大データをメモリに展開中... (数秒お待ちください)")
                if bulk_records:
                    bulk_df = pd.DataFrame(bulk_records)
                    bulk_df['Date'] = pd.to_datetime(bulk_df['Date'])
                    cols = ['O', 'H', 'L', 'C', 'Vo', 'AdjO', 'AdjH', 'AdjL', 'AdjC', 'AdjVo']
                    for c in cols:
                        if c in bulk_df.columns:
                            bulk_df[c] = pd.to_numeric(bulk_df[c], errors='coerce')
                            
                    grouped = bulk_df.groupby('Code')
                    for tk, group in grouped:
                        g_df = group.sort_values('Date').set_index('Date', drop=False)
                        st.session_state["data_pool"][tk] = g_df
                        if tk in tickers:
                            df_dict[tk] = g_df
                            
                for tk in missing_tickers:
                    if tk not in st.session_state["data_pool"]:
                        st.session_state["data_pool"][tk] = pd.DataFrame()
                            
                status_text.text("🚀 全市場データのメモリ同期に成功しました。")
                time.sleep(1) 
                progress_bar.empty()
                status_text.empty()
                return df_dict

        # 100銘柄未満の場合は、従来通りの個別取得モードを実行
        total_missing = len(missing_tickers)
        completed = 0
        def _fetch_task(tk):
            with rate_limit_lock: time.sleep(API_DELAY) 
            df = fetch_jquants_daily_data(api_key, tk)
            return tk, df

        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
            future_to_tk = {executor.submit(_fetch_task, tk): tk for tk in missing_tickers}
            for future in concurrent.futures.as_completed(future_to_tk):
                tk = future_to_tk[future]
                try:
                    tk_res, df = future.result()
                    if not df.empty:
                        df_dict[tk_res] = df
                        st.session_state["data_pool"][tk_res] = df
                    else:
                        st.session_state["data_pool"][tk_res] = pd.DataFrame() 
                except Exception: 
                    st.session_state["data_pool"][tk] = pd.DataFrame()
                    
                completed += 1
                progress_bar.progress(completed / total_missing)
                
                # ⏳ 【修正】予想残り時間の表示 (個別取得用)
                eta_sec = int((total_missing - completed) * API_DELAY)
                status_text.text(f"個別データ取得中: {tk} ({completed}/{total_missing}) | ⏳ 残り約 {eta_sec} 秒")
                
        status_text.text("✅ データの取得が完了しました。")
        time.sleep(1)
        progress_bar.empty()
        status_text.empty()
        return df_dict

    # --- M1 UI ---
    with tab1:
        st.markdown("### 🎯 M1: 裁定狙撃 (テーマ / セクター別)")
        scan_mode = st.radio("スキャン・モード", ["セクター指定", "テーマ指定（カスタム銘柄リスト）"], horizontal=True)
        target_tickers = []
        
        if scan_mode == "セクター指定":
            selected_sector_m1 = st.selectbox("ターゲット・セクターを選択", sectors, key="m1_sec")
            target_tickers = df_master[df_master[sector_col] == selected_sector_m1]['Code'].tolist()
        else:
            custom_list = st.text_input("銘柄コードをカンマ区切りで入力 (例: 7203, 7267, 7201)")
            if custom_list: target_tickers = [tk.strip() for tk in custom_list.split(",") if tk.strip()]

        if st.button("Execute M1 Scan"):
            if not target_tickers:
                st.warning("スキャン対象の銘柄が存在しません。")
            else:
                df_dict_m1 = fetch_data_for_tickers(target_tickers)
                grouped_results = auto_pair_snipe_engine_grouped(df_dict_m1, target_tickers)
                
                if grouped_results:
                    st.success(f"{len(grouped_results)} 件のハブ銘柄（異常点）を検知。")
                    for i, (hub_tk, data) in enumerate(grouped_results.items()):
                        hub_info = data["hub"]
                        targets = data["targets"]
                        with st.expander(f"🔥 HUB ALERT: {hub_tk} (対象 {len(targets)} 銘柄に対して割高)", expanded=True):
                            st.markdown("#### ▼ 割高ハブ銘柄 (Short候補)")
                            st.dataframe(pd.DataFrame([hub_info]), use_container_width=True)
                            st.plotly_chart(plot_interactive_chart(df_dict_m1[hub_tk], hub_tk, hub_info.get("Entry"), hub_info.get("SL"), hub_info.get("TP1")), use_container_width=True, key=f"m1_hub_{hub_tk}_{i}")
                            st.markdown(f"#### ▼ サヤ抜き対象 (Long候補) - 全 {len(targets)} 銘柄")
                            st.dataframe(pd.DataFrame(targets), use_container_width=True)
                            for j, target_info in enumerate(targets):
                                tgt_tk = target_info["銘柄コード"]
                                with st.expander(f"📊 チャート確認: {tgt_tk}"):
                                    st.plotly_chart(plot_interactive_chart(df_dict_m1[tgt_tk], tgt_tk, target_info.get("Entry"), target_info.get("SL"), target_info.get("TP1")), use_container_width=True, key=f"m1_tgt_{hub_tk}_{tgt_tk}_{j}")
                else:
                    st.info("指定範囲内に優位性のある歪みは存在しません。")

    # --- M2 UI ---
    with tab2:
        st.markdown("### 🕳️ M2: 深淵の底引き")
        scan_mode_m2 = st.radio("スキャン・モード (M2)", ["全市場一括スキャン", "セクター指定", "テーマ指定（カスタム銘柄リスト）"], horizontal=True, key="m2_mode")
        target_tickers_m2 = []
        
        if scan_mode_m2 == "全市場一括スキャン":
            target_tickers_m2 = df_master['Code'].tolist()
        elif scan_mode_m2 == "セクター指定":
            selected_sector_m2 = st.selectbox("ターゲット・セクターを選択", sectors, key="m2_sec")
            target_tickers_m2 = df_master[df_master[sector_col] == selected_sector_m2]['Code'].tolist()
        else:
            custom_list_m2 = st.text_input("銘柄コードをカンマ区切りで入力 (M2用)", key="m2_custom")
            if custom_list_m2: target_tickers_m2 = [tk.strip() for tk in custom_list_m2.split(",") if tk.strip()]
            
        if st.button("Execute M2 Scan"):
            if not target_tickers_m2: st.warning("対象がありません。")
            else:
                df_dict_m2 = fetch_data_for_tickers(target_tickers_m2)
                results_m2 = auto_abyss_engine(df_dict_m2)
                if results_m2:
                    st.success(f"{len(results_m2)} 件の極限反発ポイントを検知。")
                    st.dataframe(pd.DataFrame(results_m2), use_container_width=True)
                    for i, res in enumerate(results_m2):
                        tk = res["銘柄コード"]
                        with st.expander(f"📊 チャート: [{tk}]"):
                            st.plotly_chart(plot_interactive_chart(df_dict_m2[tk], tk, res.get("Entry"), res.get("SL"), res.get("TP1")), use_container_width=True, key=f"m2_chart_{tk}_{i}")
                else:
                    st.info("条件に合致する銘柄は検知されませんでした。")

    # --- M3 UI ---
    with tab3:
        st.markdown("### 🚀 M3: 事後確信 (決算資金流入スキャン)")
        col1, col2 = st.columns(2)
        start_date = col1.date_input("開始日", datetime.date.today() - datetime.timedelta(days=3))
        end_date = col2.date_input("終了日", datetime.date.today())
        
        if st.button("Execute M3 Scan"):
            with st.spinner("決算カレンダーを取得中..."):
                earnings_cal = fetch_earnings_calendar(api_key)
                
            start_dt_str = start_date.strftime('%Y-%m-%d')
            end_dt_str = end_date.strftime('%Y-%m-%d')
            target_tickers_m3 = [tk for tk, dt in earnings_cal.items() if start_dt_str <= dt <= end_dt_str]
            
            if not target_tickers_m3:
                st.info("指定期間に決算発表を行う銘柄は見つかりません。")
            else:
                df_dict_m3 = fetch_data_for_tickers(target_tickers_m3)
                results_m3 = auto_post_assault_engine(df_dict_m3, earnings_cal, start_dt_str, end_dt_str)
                if results_m3:
                    st.success(f"{len(results_m3)} 件の資金流入トレンドを検知。")
                    st.dataframe(pd.DataFrame(results_m3), use_container_width=True)
                    for i, res in enumerate(results_m3):
                        tk = res["銘柄コード"]
                        with st.expander(f"📊 チャート: [{tk}]"):
                            st.plotly_chart(plot_interactive_chart(df_dict_m3[tk], tk, res.get("Entry"), res.get("SL"), res.get("TP1")), use_container_width=True, key=f"m3_chart_{tk}_{i}")
                else:
                    st.info("条件を満たす資金流入銘柄は存在しません。")

if __name__ == "__main__":
    main()
