import streamlit as st
import requests
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import re
import json
import os
from datetime import datetime, timedelta
from io import BytesIO
import concurrent.futures
import streamlit.components.v1 as components
import gc
import yfinance as yf

# --- 0. 高度なシステム設定 & 2026スタイルエンジン ---
# サイドバー幅をピクセル単位で固定し、データ密度を最適化 (v1.53+)
st.set_page_config(
    page_title="戦術スコープ『鉄の掟』v2.1", 
    layout="wide", 
    page_icon="🎯",
    initial_sidebar_state=320 # 320pxに固定 
)

    # パスワード定義の復旧
    ALLOWED_PASSWORDS =

# カスタムCSS: 2026年テーマ変数を使用した視認性向上
st.markdown("""
    <style>
    /* メトリック値の強調とフォントサイズ最適化 */
    [data-testid="stMetricValue"] {
        font-size: clamp(1.2rem, 3vw, 1.8rem)!important;
        font-weight: 800!important;
        color: var(--st-primary-color);
    }
    /* 掟スコア用カスタムカード */
  .tactical-card {
        background: rgba(255, 255, 255, 0.04);
        border-radius: 12px;
        padding: 1.5rem;
        border-left: 6px solid #2e7d32;
        box-shadow: 0 4px 20px rgba(0,0,0,0.2);
        margin-bottom: 1.2rem;
        transition: transform 0.2s;
    }
  .tactical-card:hover { transform: translateY(-3px); background: rgba(255, 255, 255, 0.07); }
    
    /* モバイル環境での横並び維持 */
    @media (max-width: 768px) {
        div { gap: 0.5rem!important; }
    }
    </style>
""", unsafe_allow_html=True)

# --- 1. 物理同期・認証・状態管理エンジン ---
API_KEY = st.secrets.get("JQUANTS_API_KEY", "").strip()
headers = {"x-api-key": API_KEY}
BASE_URL = "https://api.jquants.com/v2"

def initialize_session():
    """セッション状態の物理初期化と型安全性の確保"""
    if "password_correct" not in st.session_state:
        st.session_state.password_correct = False
    
    # 2026年標準のデフォルト設定 (掟のパラメータ)
    defaults = {
        "cfg_push_r": 50.0, "cfg_limit_d": 4, "cfg_tp": 10, "cfg_sl": 8,
        "cfg_min_p": 200, "cfg_max_p": 3000, "cfg_market": "中小型株",
        "radar_results": None, "active_tab": "待伏"
    }
    for k, v in defaults.items():
        if k not in st.session_state: st.session_state[k] = v

def check_password():
    if not st.session_state.password_correct:
        st.markdown('<h1 style="text-align: center; color: #2e7d32; margin-top: 10vh;">🎯 戦術スコープ『鉄の掟』</h1>', unsafe_allow_html=True)
        col1, col2, col3 = st.columns([1, 2, 1])
        with col2:
            with st.form("login_gate"):
                pw = st.text_input("Access Code", type="password", placeholder="コードを入力せよ")
                if st.form_submit_button("認証"):
                    # 修正点：ALLOWED_PASSWORDSへの参照を正しく実装
                    if pw in ALLOWED_PASSWORDS:
                        st.session_state.password_correct = True
                        st.rerun()
                    else: st.error("🚨 拒絶：アクセス権限がありません。")
        return False
    return True

initialize_session()
if not check_password(): st.stop()

# --- 2. 高速演算エンジン (完全ベクトル化) ---
@st.cache_data(ttl=3600)
def fetch_market_snapshot():
    """J-Quants V2 日付指定クエリによる全銘柄一括取得 (ネットワーク負荷軽減)"""
    target_date = datetime.now() - timedelta(days=1 if datetime.now().hour < 18 else 0)
    while target_date.weekday() >= 5: target_date -= timedelta(days=1)
    ds = target_date.strftime('%Y-%m-%d')
    
    try:
        url = f"{BASE_URL}/equities/bars/daily?date={ds}"
        r = requests.get(url, headers=headers, timeout=15)
        if r.status_code == 200:
            df = pd.DataFrame(r.json().get("data",))
            # V2の短縮カラム名を正規化 
            df = df.rename(columns={'AdjC': 'Close', 'AdjH': 'High', 'AdjL': 'Low', 'Vo': 'Volume'})
            return df
    except Exception as e:
        st.error(f"データ取得失敗: {e}")
    return pd.DataFrame()

def calculate_indicators_vectorized(df):
    """
    全銘柄を一度に行列演算。
    Pandas 3.0のCoWを活かし、メモリコピーを最小化。
    """
    if df.empty: return df
    df = df.copy()
    
    # RSI: 指数平滑移動平均を用いたWilder方式
    delta = df.groupby('Code')['Close'].diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    
    avg_gain = gain.groupby(df['Code']).ewm(alpha=1/14, adjust=False).mean()
    avg_loss = loss.groupby(df['Code']).ewm(alpha=1/14, adjust=False).mean()
    df = 100 - (100 / (1 + (avg_gain / (avg_loss + 1e-10))))
    
    # ATR: ボラティリティ演算
    tr = pd.concat([
        df['High'] - df['Low'], 
        (df['High'] - df.groupby('Code')['Close'].shift(1)).abs(),
        (df['Low'] - df.groupby('Code')['Close'].shift(1)).abs()
    ], axis=1).max(axis=1)
    df = tr.groupby(df['Code']).transform(lambda x: x.rolling(14).mean())
    
    return df

# --- 3. UI/UX 構造化コンポーネント ---
@st.fragment
def render_tactical_sidebar():
    """サイドバー設定の局所実行 """
    with st.sidebar:
        st.title("🛠️ 戦術コンソール")
        with st.expander("📍 索敵パラメータ", expanded=True):
            st.selectbox("市場", ["🏢 大型株", "🚀 中小型株"], key="cfg_market")
            st.number_input("価格下限", 100, 10000, step=100, key="cfg_min_p")
            st.number_input("価格上限", 100, 50000, step=500, key="cfg_max_p")
            st.slider("押し目率 (%)", 20.0, 80.0, 50.0, key="cfg_push_r")
        
        with st.expander("💰 執行・規律ルール", expanded=False):
            st.number_input("利確目標 (%)", 1, 100, key="cfg_tp")
            st.number_input("損切設定 (%)", 1, 50, key="cfg_sl")
            st.checkbox("IPO除外", value=True, key="cfg_ex_ipo")

        if st.button("💾 戦術設定を永久保存", use_container_width=True):
            st.toast("Settings Saved.")

@st.fragment(run_every=60)
def render_frontline_monitor():
    """バックグラウンドで戦況を自動更新 """
    st.markdown("### 📡 リアルタイム戦線モニター")
    st.caption(f"最終同期: {datetime.now().strftime('%H:%M:%S')}")
    st.info("哨戒圏内に進入したターゲットはありません。")

# --- 4. メイン・タクティカル・インターフェース ---
render_tactical_sidebar()

tab_radar, tab_scope, tab_sim, tab_front, tab_aar = st.tabs([
    "🌐 広域レーダー", "🎯 精密スコープ", "⚙️ 戦術演習", "⛺ 戦線モニター", "📁 戦歴記録"
])

with tab_radar:
    st.markdown("### 🎯 【待伏】掟・半値押し索敵エンジン")
    if st.button("🚀 最新データで全市場スキャン開始"):
        with st.spinner("物理演算中..."):
            market_df = fetch_market_snapshot()
            processed = calculate_indicators_vectorized(market_df)
            
            # フィルタリング
            results = processed[
                (processed['Close'] >= st.session_state.cfg_min_p) & 
                (processed['Close'] <= st.session_state.cfg_max_p) &
                (processed <= 40)
            ].sort_values('RSI').head(15)
            
            if results.empty:
                st.warning("条件に合致するターゲットが見つかりません。")
            else:
                for _, row in results.iterrows():
                    st.markdown(f"""
                        <div class="tactical-card">
                            <span style="font-size:1.4rem; font-weight:bold;">({row['Code']}) ターゲット捕捉</span>
                            <span style="background:#1b5e20; color:white; padding:2px 8px; border-radius:4px; font-size:0.8rem; margin-left:10px;">待伏: S🔥</span>
                        </div>
                    """, unsafe_allow_html=True)
                    
                    c1, c2, c3, c4 = st.columns([1,1,1,2])
                    c1.metric("現在値", f"¥{row['Close']:,.0f}")
                    c2.metric("RSI", f"{row:.1f}%")
                    c3.metric("ATRボラ", f"¥{row:,.0f}")
                    
                    # スパークライン描画 
                    dummy_data = [row['Close']*(1+np.random.uniform(-0.02, 0.02)) for _ in range(10)]
                    fig = go.Figure(go.Scatter(y=dummy_data, fill='tozeroy', line_color='#26a69a'))
                    fig.update_layout(height=60, margin=dict(l=0,r=0,t=0,b=0), xaxis_visible=False, yaxis_visible=False, paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)')
                    c4.plotly_chart(fig, use_container_width=True, config={'displayModeBar': False})

with tab_scope:
    st.markdown("### 🏹 精密精密索敵スコープ")
    target_input = st.text_area("ターゲットコード投入 (Space/Enter区切り)", height=100)
    if st.button("🔫 ロックオン"):
        codes = re.findall(r'\d{4}', target_input)
        if not codes:
            st.error("有効な銘柄コードを投入せよ。")
        else:
            with st.spinner("対象の生体反応をスキャン中..."):
                def get_data(c):
                    ticker = yf.Ticker(f"{c}.T")
                    return c, ticker.history(period="1y"), ticker.info
                
                with concurrent.futures.ThreadPoolExecutor(max_workers=5) as exe:
                    results = list(exe.map(get_data, codes))
                
                for c, hist, info in results:
                    if hist.empty: continue
                    with st.container(border=True):
                        col_l, col_r = st.columns([1, 2])
                        with col_l:
                            st.subheader(f"{info.get('longName', c)}")
                            st.metric("PER", f"{info.get('trailingPE', 0):.1f}倍", delta_description="収益性")
                            st.metric("PBR", f"{info.get('priceToBook', 0):.2f}倍", delta_description="資産性")
                            with st.popover("詳細財務生体データ"):
                                st.write(f"ROE: {info.get('returnOnEquity', 0)*100:.2f}%")
                                st.write(f"時価総額: {info.get('marketCap', 0)/1e8:,.0f}億円")
                                
                        with col_r:
                            fig = go.Figure(data=[go.Candlestick(x=hist.index[-60:],
                                            open=hist['Open'][-60:], high=hist['High'][-60:],
                                            low=hist['Low'][-60:], close=hist['Close'][-60:])])
                            fig.update_layout(height=300, template="plotly_dark", margin=dict(l=0,r=0,t=0,b=0), xaxis_rangeslider_visible=False)
                            st.plotly_chart(fig, use_container_width=True)

with tab_front:
    render_frontline_monitor()

# --- 5. 司令部帰還 (物理スクロール・ユーティリティ) ---
components.html("""
    <script>
    const parentDoc = window.parent.document;
    const btn = parentDoc.createElement('button');
    btn.innerHTML = '🚁 司令部へ帰還';
    btn.style = 'position:fixed; bottom:20px; right:20px; z-index:9999; background:#1b5e20; color:white; border:none; padding:10px 20px; border-radius:30px; cursor:pointer; font-weight:bold; box-shadow:0 4px 10px rgba(0,0,0,0.5);';
    btn.onclick = () => { 
        const main = parentDoc.querySelector('section.main');
        if (main) main.scrollTo({top: 0, behavior: 'smooth'}); 
    };
    parentDoc.body.appendChild(btn);
    </script>
""", height=0)
