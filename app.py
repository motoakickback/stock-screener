import streamlit as st
import yfinance as yf
import pandas as pd
import datetime
import os

# --- 設定ファイル ---
TICKER_FILE = "tickers.txt"

def load_tickers():
    if os.path.exists(TICKER_FILE):
        with open(TICKER_FILE, "r") as f:
            return f.read()
    return "6327\n402A\n7885\n7318"

def save_tickers(tickers_str):
    with open(TICKER_FILE, "w") as f:
        f.write(tickers_str)

st.set_page_config(page_title="暴騰銘柄スクリーニング", layout="wide")
st.title("📈 暴騰銘柄・半値押しスクリーニング")

# --- ここから追加：レスポンシブCSSの定義 ---
st.markdown("""
<style>
.responsive-text {
    font-weight: bold;
    margin-bottom: 0.5rem;
}
/* スマホ用（画面幅768px以下） */
@media (max-width: 768px) {
    .responsive-text {
        font-size: 1.1rem;
    }
    /* タイトルや見出しを縮小 */
    h1 { font-size: 1.5rem !important; }
    h2 { font-size: 1.3rem !important; }
    h3 { font-size: 1.1rem !important; }
    
    /* 数値表示（55%押し、最高値、現在値）のブロックを縮小 */
    [data-testid="stMetricValue"] * { font-size: 1.4rem !important; }
    [data-testid="stMetricLabel"] * { font-size: 0.85rem !important; }
}
/* PC用（画面幅769px以上） */
@media (min-width: 769px) {
    .responsive-text {
        font-size: 1.5rem;
    }
}
</style>
""", unsafe_allow_html=True)
# --- ここまで追加 ---

# Step 2: 出力部分のタグ変更
# --- サイドバー設定 ---
st.sidebar.header("⚙️ システム設定")

# 監視銘柄入力（改行区切り＆自動保存）
tickers_input = st.sidebar.text_area("監視銘柄リスト（改行で入力）", value=load_tickers(), height=200)
save_tickers(tickers_input)

# ブラックリスト
blacklist_input = st.sidebar.text_input("除外ブラックリスト", value="3350")
blacklist = [t.strip() for t in blacklist_input.split(',')] if blacklist_input else []

st.sidebar.subheader("🛡️ フィルター設定 (ONで除外)")
min_price_limit = st.sidebar.selectbox(
    "⬇️ 株価下限フィルター",
    options=[0, 200, 1000, 2000, 3000],
    format_func=lambda x: "制限なし" if x == 0 else f"{x}円以下を除外",
    index=1
)
filter_ipo = st.sidebar.checkbox("IPO(上場1年以内)を除外", value=True)
filter_2x_1m = st.sidebar.checkbox("1ヶ月で2倍以上の暴騰を除外", value=True)
filter_3x_1y = st.sidebar.checkbox("1年で3倍以上(第3波終了)を除外", value=True)
filter_crash = st.sidebar.checkbox("中長期チャートで暴落後を除外", value=True)

ticker_list = [t.strip() for t in tickers_input.split('\n') if t.strip()]

if st.sidebar.button("▶ スクリーニング実行"):
    st.info(f"🔍 {len(ticker_list)}銘柄のデータを解析中...")
    
    end_date = datetime.date.today()
    start_date = end_date - datetime.timedelta(days=400) # 約1年強のデータ取得
    
    # --- 変更ここから ---
    hit_count = 0
    results = [] # フィルターを通過した銘柄を貯めるリスト
    
    for ticker_code in ticker_list:
        if ticker_code in blacklist:
            continue
            
        ticker_symbol = ticker_code + ".T"
        try:
            # 時差バグを排除し、直近2年分のデータを取得（IPOフィルター正常化のため）
            df = yf.download(ticker_symbol, period="2y", progress=False)
            
            if len(df) < 250:
                continue # IPO除外
                
            current_price = float(df['Close'].iloc[-1])
            recent_high = float(df['High'].tail(14).max())
            drop_55_price = recent_high * 0.45
            
            # フィルター：指定株価以下を除外
            if current_price <= min_price_limit:
                continue
                
            # 全てのフィルターを通過した銘柄の「下落率」を計算してリストへ保存
            drop_ratio = current_price / recent_high
            latest_date = df.index[-1].strftime('%m/%d')
            
            results.append({
                'code': ticker_code,
                'current_price': current_price,
                'recent_high': recent_high,
                'drop_55_price': drop_55_price,
                'drop_ratio': drop_ratio,
                'latest_date': latest_date
            })
            
            hit_count += 1
            
        except Exception:
            continue

    # --- 貯め込んだリストを「下落率が高い順（現在値/最高値 が小さい順）」にソート ---
    results_sorted = sorted(results, key=lambda x: x['drop_ratio'])
  
    # --- ソート済みの結果を画面に一括出力 ---
    for item in results_sorted:
        st.divider()
        st.subheader(f"{item['code']} （最高値: {int(item['recent_high'])}円）")
        
        col1, col2, col3 = st.columns(3)
        col1.metric("🎯 55%押し(買値目安)", f"{int(item['drop_55_price'])}円")
        # 下落率をパーセンテージで表示
        col2.metric("📉 現在水準", f"{int(item['drop_ratio'] * 100)}%") 
        col3.metric(f"最新値 ({item['latest_date']} 終値)", f"{int(item['current_price'])}円")
        
        # --- 売値目標と損切り線の動的計算（新ロジック対応） ---
        base_50_price = item['recent_high'] * 0.50
        drop_55_price = item['drop_55_price']
        
        target_3 = int(base_50_price * 1.03)
        target_5 = int(base_50_price * 1.05)
        target_8 = int(base_50_price * 1.08)
        
        loss_10 = int(drop_55_price * 0.90)
        loss_8 = int(drop_55_price * 0.92)
        
        st.markdown(f"<div class='responsive-text'>💰 売値目標: [+3%] <span style='color:#ff4b4b'>{target_3}円</span> / [+5%] {target_5}円 / [+8%] {target_8}円</div>", unsafe_allow_html=True)
        st.markdown(f"<div class='responsive-text'>🛡️ 損切り線: ザラ場(-10%) <span style='color:#00fa9a'>{loss_10}円</span> / 終値(-8%) {loss_8}円</div>", unsafe_allow_html=True)
   
    st.success(f"✅ スクリーニング完了: 条件合致【 {hit_count} 件 】")
