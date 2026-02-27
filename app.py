import streamlit as st, requests, pandas as pd, time, os, re
from datetime import datetime, timedelta
from io import BytesIO
import plotly.graph_objects as go
import numpy as np

# --- 1. ページ設定 ---
st.set_page_config(page_title="J-Quants 戦略アドバイザー (V11.8)", layout="wide")
st.title("🛡️ J-Quants 戦略アドバイザー (V11.8)")

API_KEY = st.secrets["JQUANTS_API_KEY"].strip()
headers = {"x-api-key": API_KEY}
BASE_URL = "https://api.jquants.com/v2"

def clean_df(df):
    rename_cols = {'AdjustmentOpen': 'AdjO', 'AdjustmentHigh': 'AdjH', 'AdjustmentLow': 'AdjL', 'AdjustmentClose': 'AdjC', 'Open': 'AdjO', 'High': 'AdjH', 'Low': 'AdjL', 'Close': 'AdjC'}
    df = df.rename(columns=rename_cols)
    for c in ['AdjO', 'AdjH', 'AdjL', 'AdjC']:
        if c in df.columns: df[c] = pd.to_numeric(df[c], errors='coerce')
    if 'Date' in df.columns: df['Date'] = pd.to_datetime(df['Date']); df = df.sort_values('Date').reset_index(drop=True)
    return df

@st.cache_data(ttl=86400)
def load_master():
    try:
        req_headers = {'User-Agent': 'Mozilla/5.0'}
        res = requests.get("https://www.jpx.co.jp/markets/statistics-equities/misc/01.html", headers=req_headers, timeout=10)
        match = re.search(r'href="([^"]+data_j\.xls)"', res.text)
        if match:
            res2 = requests.get("https://www.jpx.co.jp" + match.group(1), headers=req_headers, timeout=15)
            df = pd.read_excel(BytesIO(res2.content), engine='xlrd')[['コード', '銘柄名', '33業種区分', '市場・商品区分']]
            df.columns = ['Code', 'CompanyName', 'Sector', 'Market']
            df['Code'] = df['Code'].astype(str) + "0"
            return df
    except: pass
    return pd.DataFrame()

@st.cache_data(ttl=86400)
def get_old_codes():
    base = datetime.utcnow() + timedelta(hours=9) - timedelta(days=365)
    for i in range(7):
        d = (base - timedelta(days=i)).strftime('%Y%m%d')
        for v in ["v2", "v1"]:
            try:
                r = requests.get(f"https://api.jquants.com/{v}/listed/info?date={d}", headers=headers, timeout=10)
                if r.status_code == 200 and r.json().get("info"): return pd.DataFrame(r.json()["info"])['Code'].astype(str).tolist()
            except: pass
    return []

@st.cache_data(ttl=3600)
def get_single_data(code, yrs=3):
    base = datetime.utcnow() + timedelta(hours=9)
    f_d, t_d = (base - timedelta(days=365*yrs)).strftime('%Y%m%d'), base.strftime('%Y%m%d')
    try:
        r = requests.get(f"{BASE_URL}/equities/bars/daily?code={code}&from={f_d}&to={t_d}", headers=headers, timeout=15)
        if r.status_code == 200: return r.json().get("data", [])
    except: pass
    return []

@st.cache_data(ttl=3600)
def get_hist_data():
    base = datetime.utcnow() + timedelta(hours=9)
    dates = []
    days = 0
    while len(dates) < 30:
        d = base - timedelta(days=days)
        if d.weekday() < 5: dates.append(d.strftime('%Y%m%d'))
        days += 1
    d_half = base - timedelta(days=180)
    while d_half.weekday() >= 5: d_half -= timedelta(days=1)
    dates.append(d_half.strftime('%Y%m%d'))
    d_year = base - timedelta(days=365)
    while d_year.weekday() >= 5: d_year -= timedelta(days=1)
    dates.append(d_year.strftime('%Y%m%d'))
    
    rows = []
    bar = st.progress(0, "データ取得中...")
    for i, d in enumerate(dates):
        try:
            r = requests.get(f"{BASE_URL}/equities/bars/daily?date={d}", headers=headers, timeout=10)
            if r.status_code == 200: rows.extend(r.json().get("data", []))
        except: pass
        bar.progress((i+1)/len(dates))
        time.sleep(0.5)
    bar.empty()
    return rows

def draw_chart(df, target_p):
    fig = go.Figure()
    fig.add_trace(go.Candlestick(x=df['Date'], open=df['AdjO'], high=df['AdjH'], low=df['AdjL'], close=df['AdjC'], name='株価', increasing_line_color='#ef5350', decreasing_line_color='#26a69a'))
    fig.add_trace(go.Scatter(x=df['Date'], y=[target_p]*len(df), mode='lines', name='目標(指定%押)', line=dict(color='#FFD700', width=2, dash='dash')))
    fig.update_layout(height=320, margin=dict(l=0, r=0, t=10, b=0), xaxis_rangeslider_visible=False, paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)', hovermode="x unified")
    st.plotly_chart(fig, use_container_width=True)

tab1, tab2 = st.tabs(["🚀 実戦（スクリーナー）", "🔬 訓練（一括バックテスト）"])
master_df = load_master()

with tab1:
    st.markdown("### 🌐 ボスの「鉄の掟」全銘柄スクリーニング")
    run_scan = st.button("🚀 最新データで全軍スキャン開始")
    
    st.sidebar.header("🔍 ピックアップルール (①〜⑦)")
    f1_min = st.sidebar.number_input("① 株価下限 (円)", value=200, step=100)
    f2_max30 = st.sidebar.number_input("② 1ヶ月暴騰上限 (倍)", value=2.0, step=0.1)
    f3_drop = st.sidebar.number_input("③ 半年〜1年下落除外 (基準%)", value=-30, step=5)
    f4_max_long = st.sidebar.number_input("④ 上げ切り除外 (過去からの上昇倍率)", value=3.0, step=0.5)
    f5_ipo = st.sidebar.checkbox("⑤ IPO除外 (上場1年未満)", value=True)
    f6_risk = st.sidebar.checkbox("⑥ 疑義注記銘柄を除外", value=True)
    
    st.sidebar.caption("⑦ 14日以内の初動暴騰条件")
    c1, c2 = st.sidebar.columns(2)
    f7_min14 = c1.number_input("下限 (倍)", value=1.3, step=0.1)
    f7_max14 = c2.number_input("上限 (倍)", value=2.0, step=0.1)

    st.sidebar.header("🎯 買いルール")
    push_r = st.sidebar.number_input("① 上げ幅に対する押し目 (%)", value=50, step=5)
    limit_d = st.sidebar.number_input("② 買い期限 (高値から何日以内)", value=4, step=1)

    if run_scan:
        raw = get_hist_data()
        if not raw: st.error("取得失敗")
        else:
            df = clean_df(pd.DataFrame(raw))
            def calc_m(g):
                emp = pd.Series({'lc':np.nan, 'h14':np.nan, 'l14':np.nan, 'l30':np.nan, 'bt':np.nan, 'd_high':np.nan, 'r14':np.nan, 'r30':np.nan, 'ldrop':np.nan, 'lrise':np.nan})
                g = g.dropna(subset=['AdjC', 'AdjH', 'AdjL']).sort_values('Date')
                if len(g) < 14: return emp
                r30 = g.tail(30); r14 = r30.tail(14)
                idx_max = r14['AdjH'].idxmax()
                if pd.isna(idx_max): return emp
                past = g.iloc[:-len(r30)] if len(g) > len(r30) else pd.DataFrame()
                
                lc = r14['AdjC'].iloc[-1]
                h14 = r14['AdjH'].max(); l14 = r14['AdjL'].min(); l30 = r30['AdjL'].min()
                d_high = len(r14[r14['Date'] > r14.loc[idx_max, 'Date']])
                bt = h14 - ((h14 - l14) * (push_r / 100))
                
                ldrop = lrise = 0
                if len(past)>0:
                    omax = past['AdjH'].max(); omin = past['AdjL'].min()
                    if pd.notna(omax) and omax>0: ldrop = ((lc/omax)-1)*100
                    if pd.notna(omin) and omin>0: lrise = lc/omin
                return pd.Series({'lc':lc, 'h14':h14, 'l14':l14, 'l30':l30, 'bt':bt, 'd_high':d_high, 'r14':h14/l14 if l14>0 else 0, 'r30':lc/l30 if l30>0 else 0, 'ldrop':ldrop, 'lrise':lrise})

            with st.spinner("全4000銘柄に鉄の掟を執行中..."):
                sum_df = df.groupby('Code').apply(calc_m).reset_index()
                if 'lc' in sum_df.columns: sum_df = sum_df.dropna(subset=['lc'])
                else: st.error("有効データなし"); st.stop()
                if not master_df.empty: sum_df = pd.merge(sum_df, master_df, on='Code', how='left')
                
                sum_df = sum_df[sum_df['lc'] >= f1_min]
                sum_df = sum_df[sum_df['r30'] <= f2_max30]
                sum_df = sum_df[sum_df['ldrop'] >= f3_drop]
                sum_df = sum_df[(sum_df['lrise'] <= f4_max_long) | (sum_df['lrise'] == 0)]
                if f5_ipo:
                    old_c = get_old_codes()
                    if old_c: sum_df = sum_df[sum_df['Code'].isin(old_c)]
                if f6_risk and 'CompanyName' in sum_df.columns:
                    sum_df = sum_df[~sum_df['CompanyName'].astype(str).str.contains("疑義|重要事象", na=False)]
                
                sum_df = sum_df[(sum_df['r14'] >= f7_min14) & (sum_df['r14'] <= f7_max14)]
                sum_df = sum_df[sum_df['d_high'] <= limit_d]
                sum_df = sum_df[sum_df['lc'] <= (sum_df['bt'] * 1.05)]
                
                res = sum_df.sort_values('lc', ascending=False).head(30)
                
            if res.empty: st.warning("標的は存在しません。")
            else:
                st.success(f"審査完了: {len(res)} 銘柄クリア")
                for _, r in res.iterrows():
                    st.divider()
                    c = str(r['Code']); n = r['CompanyName'] if not pd.isna(r.get('CompanyName')) else f"銘柄 {c[:-1]}"
                    st.subheader(f"{n} ({c[:-1]})")
                    c1, c2, c3 = st.columns(3)
                    c1.metric("最新終値", f"{int(r['lc'])}円")
                    c2.metric("🎯 買値目標", f"{int(r['bt'])}円")
                    c3.metric("高値から日数", f"{int(r['d_high'])}日")
                    hist = df[df['Code']==r['Code']].sort_values('Date').tail(14)
                    if not hist.empty: draw_chart(hist, r['bt'])

with tab2:
    st.markdown("### 📉 鉄の掟：複数銘柄 一括検証 ＆ 損益
