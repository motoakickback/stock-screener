import streamlit as st, requests, pandas as pd, time, os, re
from datetime import datetime, timedelta
from io import BytesIO
import plotly.graph_objects as go
import numpy as np
import concurrent.futures # 【V12.0 追加】マルチスレッド並列処理用

# --- 1. ページ設定 ---
st.set_page_config(page_title="J-Quants 戦略アドバイザー (V12.0)", layout="wide")
st.title("🛡️ J-Quants 戦略アドバイザー (V12.0 神速版)")

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
    """V12.0: マルチスレッドによる相場データの並列爆撃取得"""
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
    bar = st.progress(0, "最新の相場データを並列取得中 (神速モード)...")
    
    def fetch(d):
        try:
            r = requests.get(f"{BASE_URL}/equities/bars/daily?date={d}", headers=headers, timeout=10)
            time.sleep(0.1) # API制限回避の微細なディレイ
            if r.status_code == 200: return r.json().get("data", [])
        except: pass
        return []

    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as exe:
        futs = {exe.submit(fetch, d): d for d in dates}
        comp = 0
        for f in concurrent.futures.as_completed(futs):
            res = f.result()
            if res: rows.extend(res)
            comp += 1
            bar.progress(comp/len(dates))
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
            with st.spinner("全4000銘柄に鉄の掟を一括執行中 (ベクトル演算)..."):
                # V12.0: 圧倒的高速化のためのPandasベクトル一括演算
                df = clean_df(pd.DataFrame(raw))
                df = df.dropna(subset=['AdjC', 'AdjH', 'AdjL']).sort_values(['Code', 'Date'])
                
                df_30 = df.groupby('Code').tail(30)
                df_14 = df_30.groupby('Code').tail(14)
                
                counts = df_14.groupby('Code').size()
                valid = counts[counts == 14].index
                
                df_14 = df_14[df_14['Code'].isin(valid)]
                df_30 = df_30[df_30['Code'].isin(valid)]
                df_past = df[~df.index.isin(df_30.index)]
                df_past = df_past[df_past['Code'].isin(valid)]
                
                agg_14 = df_14.groupby('Code').agg(lc=('AdjC', 'last'), h14=('AdjH', 'max'), l14=('AdjL', 'min'))
                
                idx_max = df_14.groupby('Code')['AdjH'].idxmax()
                high_dates = df_14.loc[idx_max].set_index('Code')['Date'].rename('h_date')
                df_14_m = df_14.merge(high_dates, on='Code')
                d_high = df_14_m[df_14_m['Date'] > df_14_m['h_date']].groupby('Code').size().rename('d_high')
                
                agg_30 = df_30.groupby('Code').agg(l30=('AdjL', 'min'))
                agg_past = df_past.groupby('Code').agg(omax=('AdjH', 'max'), omin=('AdjL', 'min'))
                
                sum_df = agg_14.join(d_high, how='left').fillna({'d_high': 0}).join(agg_30).join(agg_past).reset_index()
                
                sum_df['u_range'] = sum_df['h14'] - sum_df['l14']
                sum_df['bt'] = sum_df['h14'] - (sum_df['u_range'] * (push_r / 100.0))
                sum_df['r14'] = np.where(sum_df['l14']>0, sum_df['h14']/sum_df['l14'], 0)
                sum_df['r30'] = np.where(sum_df['l30']>0, sum_df['lc']/sum_df['l30'], 0)
                sum_df['ldrop'] = np.where((sum_df['omax'].notna()) & (sum_df['omax']>0), ((sum_df['lc']/sum_df['omax'])-1)*100, 0)
                sum_df['lrise'] = np.where((sum_df['omin'].notna()) & (sum_df['omin']>0), sum_df['lc']/sum_df['omin'], 0)
                
                if not master_df.empty: sum_df = pd.merge(sum_df, master_df, on='Code', how='left')
                
                # ルール執行
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
                
            if res.empty: st.warning("現在の相場に、標的は存在しません。")
            else:
                st.success(f"超高速スキャン完了: {len(res)} 銘柄クリア")
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
    st.markdown("### 📉 鉄の掟：複数銘柄 一括検証 ＆ 損益算出")
    c1, c2 = st.columns([1, 2])
    with c1:
        bt_codes = st.text_area("銘柄コード（複数可）", value="6614, 3997, 4935", height=100)
        run_bt = st.button("🔥 一括バックテスト")
    with c2:
        st.caption("⚙️ パラメーター")
        cc1, cc2 = st.columns(2)
        bt_push = cc1.number_input("① 上げ幅に対する押し目 (%)", value=50, step=5)
        bt_buy_d = cc1.number_input("② 買い期限 (日)", value=4, step=1)
        bt_tp = cc1.number_input("③ 利確 (+%)", value=8, step=1)
        bt_lot = cc1.number_input("⑦ 株数 (基本100)", value=100, step=100)
        bt_sl_i = cc2.number_input("④ 損切/ザラ場 (-%)", value=10, step=1)
        bt_sl_c = cc2.number_input("⑤ 損切/終値 (-%)", value=8, step=1)
        bt_sell_d = cc2.number_input("⑥ 売り期限 (日)", value=5, step=1)

    if run_bt and bt_codes:
        t_codes = list(dict.fromkeys(re.findall(r'\b\d{4}\b', bt_codes)))
        if not t_codes: st.warning("有効なコードなし")
        else:
            all_t = []
            b_bar = st.progress(0, "仮想売買中...")
            for idx, c in enumerate(t_codes):
                raw = get_single_data(c+"0", 3)
                if raw:
                    df = clean_df(pd.DataFrame(raw))
                    pos = None
                    for i in range(14, len(df)):
                        td = df.iloc[i]
                        if pos is None:
                            win = df.iloc[i-14:i]
                            rh = win['AdjH'].max(); rl = win['AdjL'].min()
                            if pd.isna(rh) or pd.isna(rl): continue
                            h_d = len(win[win['Date'] > win.loc[win['AdjH'].idxmax(), 'Date']])
                            r14 = rh/rl if rl>0 else 0
                            if (1.3 <= r14 <= 2.0) and (h_d <= bt_buy_d):
                                bt_targ = rh - ((rh-rl)*(bt_push/100))
                                if td['AdjL'] <= bt_targ:
                                    pos = {'b_i':i, 'b_d':td['Date'], 'b_p':min(td['AdjO'], bt_targ), 'h':rh}
                        else:
                            bp = round(pos['b_p'], 1); held = i - pos['b_i']
                            sp = 0; rsn = ""
                            sl_i = bp*(1-(bt_sl_i/100)); tp = bp*(1+(bt_tp/100)); sl_c = bp*(1-(bt_sl_c/100))
                            if td['AdjL'] <= sl_i: sp = min(td['AdjO'], sl_i); rsn = f"損切(ザ場 -{bt_sl_i}%)"
                            elif td['AdjH'] >= tp: sp = max(td['AdjO'], tp); rsn = f"利確(+{bt_tp}%)"
                            elif td['AdjC'] <= sl_c: sp = td['AdjC']; rsn = f"損切(終値 -{bt_sl_c}%)"
                            elif held >= bt_sell_d: sp = td['AdjC']; rsn = f"時間切れ({bt_sell_d}日)"
                            if rsn:
                                sp = round(sp, 1); p_amt = int((sp-bp)*bt_lot)
                                all_t.append({'銘柄':c, '購入日':pos['b_d'].strftime('%Y-%m-%d'), '決済日':td['Date'].strftime('%Y-%m-%d'), '保有日数':held, '買値(円)':bp, '売値(円)':sp, '損益(%)':round(((sp/bp)-1)*100,2), '損益額(円)':p_amt, '決済理由':rsn})
                                pos = None
                b_bar.progress((idx+1)/len(t_codes))
                time.sleep(0.5)
            b_bar.empty()
            st.success("シミュレーション完了")
            if not all_t: st.warning("シグナル点灯なし")
            else:
                tdf = pd.DataFrame(all_t)
                tot = len(tdf); wins = len(tdf[tdf['損益額(円)']>0])
                n_prof = tdf['損益額(円)'].sum()
                sprof = tdf[tdf['損益額(円)']>0]['損益額(円)'].sum(); sloss = abs(tdf[tdf['損益額(円)']<=0]['損益額(円)'].sum())
                
                st.markdown(f"### 💰 総合結果：差し引き利益額 **{n_prof:,} 円**")
                m1, m2, m3, m4 = st.columns(4)
                m1.metric("トレード回数", f"{tot} 回")
                m2.metric("勝率", f"{round((wins/tot)*100,1)} %")
                m3.metric("平均損益額", f"{int(n_prof/tot):,} 円")
                m4.metric("PF", f"{round(sprof/sloss,2) if sloss>0 else 'inf'}")
                st.dataframe(tdf, use_container_width=True)
