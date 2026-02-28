import streamlit as st
import requests
import pandas as pd
import time
import os
import re
from datetime import datetime, timedelta
from io import BytesIO
import plotly.graph_objects as go
import numpy as np
import concurrent.futures

# --- 1. ページ設定 ---
st.set_page_config(page_title="株式投資戦略本部", layout="wide")

st.markdown('<h1 style="font-size: clamp(20px, 6.5vw, 40px); font-weight: bold; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; padding-top: 1rem; padding-bottom: 1rem;">🛡️ 株式投資戦略本部</h1>', unsafe_allow_html=True)

# --- 2. 認証・通信設定 ---
API_KEY = st.secrets.get("JQUANTS_API_KEY", "").strip()
headers = {"x-api-key": API_KEY}
BASE_URL = "https://api.jquants.com/v2"

# --- 3. 共通関数 ---
def clean_df(df):
    r_cols = {
        'AdjustmentOpen': 'AdjO', 'AdjustmentHigh': 'AdjH',
        'AdjustmentLow': 'AdjL', 'AdjustmentClose': 'AdjC',
        'Open': 'AdjO', 'High': 'AdjH', 'Low': 'AdjL', 'Close': 'AdjC'
    }
    df = df.rename(columns=r_cols)
    for c in ['AdjO', 'AdjH', 'AdjL', 'AdjC']:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors='coerce')
    if 'Date' in df.columns:
        df['Date'] = pd.to_datetime(df['Date'])
        df = df.sort_values('Date').reset_index(drop=True)
    return df

@st.cache_data(ttl=86400)
def load_master():
    try:
        h = {'User-Agent': 'Mozilla/5.0'}
        u1 = "https://www.jpx.co.jp/markets/statistics-equities/misc/01.html"
        r1 = requests.get(u1, headers=h, timeout=10)
        m = re.search(r'href="([^"]+data_j\.xls)"', r1.text)
        if m:
            u2 = "https://www.jpx.co.jp" + m.group(1)
            r2 = requests.get(u2, headers=h, timeout=15)
            df = pd.read_excel(BytesIO(r2.content), engine='xlrd')
            df = df[['コード', '銘柄名', '33業種区分', '市場・商品区分']]
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
                u = f"https://api.jquants.com/{v}/listed/info?date={d}"
                r = requests.get(u, headers=headers, timeout=10)
                if r.status_code == 200 and r.json().get("info"):
                    return pd.DataFrame(r.json()["info"])['Code'].astype(str).tolist()
            except: pass
    return []

@st.cache_data(ttl=3600)
def get_single_data(code, yrs=3):
    base = datetime.utcnow() + timedelta(hours=9)
    f_d = (base - timedelta(days=365*yrs)).strftime('%Y%m%d')
    t_d = base.strftime('%Y%m%d')
    try:
        u = f"{BASE_URL}/equities/bars/daily?code={code}&from={f_d}&to={t_d}"
        r = requests.get(u, headers=headers, timeout=15)
        if r.status_code == 200: return r.json().get("data", [])
    except: pass
    return []

@st.cache_data(ttl=3600, show_spinner=False)
def get_hist_data_cached():
    base = datetime.utcnow() + timedelta(hours=9)
    dates = []
    days = 0
    while len(dates) < 30:
        d = base - timedelta(days=days)
        if d.weekday() < 5: dates.append(d.strftime('%Y%m%d'))
        days += 1
    
    d_h = base - timedelta(days=180)
    while d_h.weekday() >= 5: d_h -= timedelta(days=1)
    dates.append(d_h.strftime('%Y%m%d'))
    
    d_y = base - timedelta(days=365)
    while d_y.weekday() >= 5: d_y -= timedelta(days=1)
    dates.append(d_y.strftime('%Y%m%d'))
    
    rows = []
    def fetch(dt):
        try:
            u = f"{BASE_URL}/equities/bars/daily?date={dt}"
            r = requests.get(u, headers=headers, timeout=10)
            if r.status_code == 200: return r.json().get("data", [])
        except: pass
        return []
        
    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as exe:
        futs = [exe.submit(fetch, dt) for dt in dates]
        for f in concurrent.futures.as_completed(futs):
            res = f.result()
            if res: rows.extend(res)
    return rows

def draw_chart(df, targ_p, tp3=None, tp5=None, tp8=None):
    fig = go.Figure()
    fig.add_trace(go.Candlestick(
        x=df['Date'], open=df['AdjO'], high=df['AdjH'],
        low=df['AdjL'], close=df['AdjC'], name='株価',
        increasing_line_color='#ef5350', decreasing_line_color='#26a69a'
    ))
    
    fig.add_trace(go.Scatter(
        x=df['Date'], y=[targ_p]*len(df), mode='lines',
        name='買い目標', line=dict(color='#FFD700', width=2, dash='dash')
    ))
    
    if tp3 and tp5 and tp8:
        fig.add_trace(go.Scatter(x=df['Date'], y=[tp3]*len(df), mode='lines', name='売(3%)', line=dict(color='rgba(76, 175, 80, 0.5)', width=1, dash='dot')))
        fig.add_trace(go.Scatter(x=df['Date'], y=[tp5]*len(df), mode='lines', name='売(5%)', line=dict(color='rgba(76, 175, 80, 0.7)', width=1, dash='dot')))
        fig.add_trace(go.Scatter(x=df['Date'], y=[tp8]*len(df), mode='lines', name='売(8%)', line=dict(color='rgba(76, 175, 80, 0.9)', width=1.5, dash='dot')))
    
    fig.update_layout(
        height=350, 
        margin=dict(l=0, r=0, t=10, b=10),
        xaxis_rangeslider_visible=False, 
        paper_bgcolor='rgba(0,0,0,0)',
        plot_bgcolor='rgba(0,0,0,0)', 
        hovermode="x unified",
        legend=dict(
            orientation="h",
            yanchor="top",
            y=-0.1,
            xanchor="center",
            x=0.5
        )
    )
    st.plotly_chart(fig, use_container_width=True)

# ==========================================
# 4. UI構築
# ==========================================
st.sidebar.header("🔍 ピックアップルール")
f1_min = st.sidebar.number_input("① 株価下限(円)", value=200, step=100)
f2_m30 = st.sidebar.number_input("② 1ヶ月暴騰上限(倍)", value=2.0, step=0.1)
f3_drop = st.sidebar.number_input("③ 半年〜1年下落除外(%)", value=-30, step=5)
f4_mlong = st.sidebar.number_input("④ 上げ切り除外(倍)", value=3.0, step=0.5)
f5_ipo = st.sidebar.checkbox("⑤ IPO除外", value=True)
f6_risk = st.sidebar.checkbox("⑥ 疑義注記銘柄除外", value=True)

c_f7_1, c_f7_2 = st.sidebar.columns(2)
f7_min14 = c_f7_1.number_input("⑦下限(倍)", value=1.3, step=0.1)
f7_max14 = c_f7_2.number_input("⑦上限(倍)", value=2.0, step=0.1)

st.sidebar.header("🎯 買いルール")
push_r = st.sidebar.number_input("① 押し目(%)", value=45, step=5)
limit_d = st.sidebar.number_input("② 買い期限(日)", value=4, step=1)

# ==========================================
# メイン画面（3タブ構成）
# ==========================================
tab1, tab2, tab3 = st.tabs(["🚀 実戦（全軍）", "🔫 局地戦（個別）", "🔬 訓練（検証）"])
master_df = load_master()

# ----------------------------------------
# タブ1：全軍スキャン
# ----------------------------------------
with tab1:
    st.markdown('<h3 style="font-size: clamp(14px, 4.5vw, 24px); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; margin-bottom: 1rem;">🌐 ボスの「鉄の掟」全軍スキャン</h3>', unsafe_allow_html=True)
    run_scan = st.button("🚀 最新データで全軍スキャン開始")

    if run_scan:
        with st.spinner("神速モードで相場データを並列取得中..."):
            raw = get_hist_data_cached()
            
        if not raw:
            st.error("データの取得に失敗しました。")
        else:
            with st.spinner("全4000銘柄に鉄の掟を一括執行中..."):
                d_raw = pd.DataFrame(raw)
                df = clean_df(d_raw)
                df = df.dropna(subset=['AdjC', 'AdjH', 'AdjL']).sort_values(['Code', 'Date'])
                
                df_30 = df.groupby('Code').tail(30)
                df_14 = df_30.groupby('Code').tail(14)
                
                counts = df_14.groupby('Code').size()
                valid = counts[counts == 14].index
                
                if valid.empty:
                    st.warning("条件を満たす銘柄データが存在しません。")
                    st.stop()
                
                df_14 = df_14[df_14['Code'].isin(valid)]
                df_30 = df_30[df_30['Code'].isin(valid)]
                df_past = df[~df.index.isin(df_30.index)]
                df_past = df_past[df_past['Code'].isin(valid)]
                
                agg_14 = df_14.groupby('Code').agg(lc=('AdjC', 'last'), h14=('AdjH', 'max'), l14=('AdjL', 'min'))
                
                idx_max = df_14.groupby('Code')['AdjH'].idxmax()
                h_dates = df_14.loc[idx_max, ['Code', 'Date']].rename(columns={'Date': 'h_date'})
                df_14_m = df_14.merge(h_dates, on='Code')
                cond_d = df_14_m['Date'] > df_14_m['h_date']
                d_high = df_14_m[cond_d].groupby('Code').size().rename('d_high')
                
                agg_30 = df_30.groupby('Code').agg(l30=('AdjL', 'min'))
                agg_p = df_past.groupby('Code').agg(omax=('AdjH', 'max'), omin=('AdjL', 'min'))
                
                sum_df = agg_14.join(d_high, how='left').fillna({'d_high': 0})
                sum_df = sum_df.join(agg_30).join(agg_p).reset_index()
                
                ur = sum_df['h14'] - sum_df['l14']
                sum_df['bt'] = sum_df['h14'] - (ur * (push_r / 100.0))
                
                sum_df['half_push'] = sum_df['h14'] - (ur * 0.50)
                sum_df['tp3'] = sum_df['half_push'] * 1.03
                sum_df['tp5'] = sum_df['half_push'] * 1.05
                sum_df['tp8'] = sum_df['half_push'] * 1.08
                
                denom = sum_df['h14'] - sum_df['bt']
                sum_df['reach_pct'] = np.where(denom > 0, (sum_df['h14'] - sum_df['lc']) / denom * 100, 0)
                
                sum_df['r14'] = np.where(sum_df['l14'] > 0, sum_df['h14'] / sum_df['l14'], 0)
                sum_df['r30'] = np.where(sum_df['l30'] > 0, sum_df['lc'] / sum_df['l30'], 0)
                
                c_omax = (sum_df['omax'].notna()) & (sum_df['omax'] > 0)
                sum_df['ldrop'] = np.where(c_omax, ((sum_df['lc'] / sum_df['omax']) - 1) * 100, 0)
                
                c_omin = (sum_df['omin'].notna()) & (sum_df['omin'] > 0)
                sum_df['lrise'] = np.where(c_omin, sum_df['lc'] / sum_df['omin'], 0)
                
                if not master_df.empty:
                    sum_df = pd.merge(sum_df, master_df, on='Code', how='left')
                
                sum_df = sum_df[sum_df['lc'] >= f1_min]
                sum_df = sum_df[sum_df['r30'] <= f2_m30]
                sum_df = sum_df[sum_df['ldrop'] >= f3_drop]
                
                c_rise = (sum_df['lrise'] <= f4_mlong) | (sum_df['lrise'] == 0)
                sum_df = sum_df[c_rise]
                
                if f5_ipo:
                    old_c = get_old_codes()
                    if old_c: sum_df = sum_df[sum_df['Code'].isin(old_c)]
                        
                if f6_risk and 'CompanyName' in sum_df.columns:
                    c_risk = ~sum_df['CompanyName'].astype(str).str.contains("疑義|重要事象", na=False)
                    sum_df = sum_df[c_risk]
                
                sum_df = sum_df[sum_df['r14'] >= f7_min14]
                sum_df = sum_df[sum_df['r14'] <= f7_max14]
                sum_df = sum_df[sum_df['d_high'] <= limit_d]
                sum_df = sum_df[sum_df['lc'] <= (sum_df['bt'] * 1.05)]
                
                res = sum_df.sort_values('reach_pct', ascending=False).head(30)
                
            if res.empty: 
                st.warning("現在の相場に、標的は存在しません。")
            else:
                st.success(f"🎯 スキャン完了: {len(res)} 銘柄クリア")
                for _, r in res.iterrows():
                    st.divider()
                    c = str(r['Code'])
                    n = r['CompanyName'] if not pd.isna(r.get('CompanyName')) else f"銘柄 {c[:-1]}"
                    
                    st.markdown(f'<h3 style="font-size: clamp(16px, 5vw, 26px); font-weight: bold; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; margin-bottom: 0.5rem;">{n} ({c[:-1]})</h3>', unsafe_allow_html=True)
                    
                    cc1, cc2, cc3, cc4 = st.columns([1, 1, 1.2, 1])
                    cc1.metric("最新終値", f"{int(r['lc'])}円")
                    cc2.metric("🎯 買い目標", f"{int(r['bt'])}円")
                    
                    html_sell_targets = f"""
                    <div style="font-family: sans-serif; padding-top: 0.2rem;">
                      <div style="font-size: 14px; color: rgba(250, 250, 250, 0.6); padding-bottom: 0.1rem;">🎯 売り目標</div>
                      <div style="font-size: 16px;">
                        <span style="display: inline-block; width: 2.5em;">3%</span> {int(r['tp3']):,}円<br>
                        <span style="display: inline-block; width: 2.5em;">5%</span> {int(r['tp5']):,}円<br>
                        <span style="display: inline-block; width: 2.5em;">8%</span> {int(r['tp8']):,}円
                      </div>
                    </div>
                    """
                    cc3.markdown(html_sell_targets, unsafe_allow_html=True)
                    cc4.metric("到達度", f"{r['reach_pct']:.1f}%")
                    
                    # 【追加】市場と業種をキャプションに統合
                    mkt = r['Market'] if not pd.isna(r.get('Market')) else "不明"
                    sct = r['Sector'] if not pd.isna(r.get('Sector')) else "不明"
                    st.caption(f"🏢 {mkt} ｜ 🏭 {sct} ｜ ⏱️ 高値からの経過日数: {int(r['d_high'])}日")
                    
                    hist = df[df['Code'] == c].sort_values('Date').tail(14)
                    if not hist.empty:
                        draw_chart(hist, r['bt'], r['tp3'], r['tp5'], r['tp8'])

# ----------------------------------------
# タブ2：局地戦（個別狙撃・掟ハイブリッド）
# ----------------------------------------
with tab2:
    st.markdown('<h3 style="font-size: clamp(14px, 4.5vw, 24px); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; margin-bottom: 1rem;">🎯 局地戦（複数・個別スキャン）</h3>', unsafe_allow_html=True)
    st.caption("※指定された銘柄すべての押し目ラインを計算し、「鉄の掟の達成率」と「買値への到達度」を算出して、条件が良い順に並び替えます。")
    
    col_s1, col_s2 = st.columns([1, 2])
    with col_s1:
        target_codes_str = st.text_area("標的コード（複数可）", value="7203\n9984", height=100)
        run_single = st.button("🔫 指定銘柄 一斉スキャン")
    with col_s2:
        st.caption("改行やカンマ区切りで複数の4桁コードを入力してください。結果は「掟達成率」と「到達度」が高い順に自動で並び替えて表示されます。")

    if run_single and target_codes_str:
        t_codes = list(dict.fromkeys(re.findall(r'\b\d{4}\b', target_codes_str)))
        
        if not t_codes:
            st.warning("4桁の有効な銘柄コードが見つかりません。")
        else:
            with st.spinner(f"指定された {len(t_codes)} 銘柄の軌道と掟達成率を計算中..."):
                results = []
                charts_data = {}
                
                for c in t_codes:
                    raw_single = get_single_data(c + "0", 1) 
                    if raw_single:
                        df_s = clean_df(pd.DataFrame(raw_single))
                        if not df_s.empty and len(df_s) >= 14:
                            df_30 = df_s.tail(30)
                            df_14 = df_s.tail(14)
                            df_past = df_s[~df_s.index.isin(df_30.index)]
                            
                            h14 = df_14['AdjH'].max()
                            l14 = df_14['AdjL'].min()
                            lc = df_s['AdjC'].iloc[-1]
                            
                            idxmax = df_14['AdjH'].idxmax()
                            h_date = df_14.loc[idxmax, 'Date']
                            d_high = len(df_14[df_14['Date'] > h_date])
                            
                            l30 = df_30['AdjL'].min() if not df_30.empty else np.nan
                            omax = df_past['AdjH'].max() if not df_past.empty else np.nan
                            omin = df_past['AdjL'].min() if not df_past.empty else np.nan
                            
                            bt_single = h14 - ((h14 - l14) * (push_r / 100.0))
                            
                            half_push_s = h14 - ((h14 - l14) * 0.50)
                            tp3_s = half_push_s * 1.03
                            tp5_s = half_push_s * 1.05
                            tp8_s = half_push_s * 1.08
                            
                            denom_s = h14 - bt_single
                            reach_s = ((h14 - lc) / denom_s * 100) if denom_s > 0 else 0
                            
                            r14 = h14 / l14 if l14 > 0 else 0
                            r30 = lc / l30 if pd.notna(l30) and l30 > 0 else 0
                            ldrop = ((lc / omax) - 1) * 100 if pd.notna(omax) and omax > 0 else 0
                            lrise = lc / omin if pd.notna(omin) and omin > 0 else 0
                            
                            c_name = f"銘柄 {c}"
                            c_market = "不明"
                            c_sector = "不明"
                            if not master_df.empty:
                                m_row = master_df[master_df['Code'] == c + "0"]
                                if not m_row.empty:
                                    c_name = m_row.iloc[0]['CompanyName']
                                    c_market = m_row.iloc[0]['Market']
                                    c_sector = m_row.iloc[0]['Sector']
                            
                            score_list = [
                                lc >= f1_min,
                                r30 <= f2_m30,
                                ldrop >= f3_drop,
                                (lrise <= f4_mlong) or (lrise == 0),
                                (f7_min14 <= r14 <= f7_max14),
                                d_high <= limit_d,
                                lc <= (bt_single * 1.05)
                            ]
                            if f5_ipo:
                                old_c = get_old_codes()
                                if old_c: score_list.append((c + "0") in old_c)
                            if f6_risk:
                                score_list.append(not bool(re.search("疑義|重要事象", str(c_name))))
                            
                            rule_pct = (sum(score_list) / len(score_list)) * 100
                            
                            results.append({
                                'Code': c,
                                'Name': c_name,
                                'Market': c_market,
                                'Sector': c_sector,
                                'lc': lc,
                                'bt': bt_single,
                                'tp3': tp3_s,
                                'tp5': tp5_s,
                                'tp8': tp8_s,
                                'h14': h14,
                                'reach_pct': reach_s,
                                'rule_pct': rule_pct,
                                'passed': sum(score_list),
                                'total': len(score_list)
                            })
                            charts_data[c] = (df_14, bt_single, tp3_s, tp5_s, tp8_s)
                
                if results:
                    res_df = pd.DataFrame(results).sort_values(['rule_pct', 'reach_pct'], ascending=[False, False])
                    st.success(f"🎯 {len(res_df)} 銘柄の局地戦スキャン完了（掟達成率 ＞ 到達度順）")
                    
                    for _, r in res_df.iterrows():
                        st.divider()
                        st.markdown(f'<h3 style="font-size: clamp(16px, 5vw, 26px); font-weight: bold; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; margin-bottom: 0.5rem;">{r["Name"]} ({r["Code"]})</h3>', unsafe_allow_html=True)
                        
                        sc1, sc2, sc3, sc4, sc5 = st.columns([1, 1, 1.2, 1, 1])
                        sc1.metric("最新終値", f"{int(r['lc'])}円")
                        sc2.metric(f"🎯 買い目標", f"{int(r['bt'])}円")
                        
                        html_sell_targets_s = f"""
                        <div style="font-family: sans-serif; padding-top: 0.2rem;">
                          <div style="font-size: 14px; color: rgba(250, 250, 250, 0.6); padding-bottom: 0.1rem;">🎯 売り目標</div>
                          <div style="font-size: 16px;">
                            <span style="display: inline-block; width: 2.5em;">3%</span> {int(r['tp3']):,}円<br>
                            <span style="display: inline-block; width: 2.5em;">5%</span> {int(r['tp5']):,}円<br>
                            <span style="display: inline-block; width: 2.5em;">8%</span> {int(r['tp8']):,}円
                          </div>
                        </div>
                        """
                        sc3.markdown(html_sell_targets_s, unsafe_allow_html=True)
                        sc4.metric("到達度", f"{r['reach_pct']:.1f}%")
                        sc5.metric("掟達成率", f"{r['rule_pct']:.0f}%")
                        
                        # 【追加】市場と業種をキャプションに統合
                        st.caption(f"🏢 {r['Market']} ｜ 🏭 {r['Sector']} ｜ ⏱️ 直近14日高値: {int(r['h14'])}円 ｜ 🛡️ 掟クリア状況: {r['passed']} / {r['total']} 条件")
                        
                        df_chart, bt_chart, tp3_c, tp5_c, tp8_c = charts_data[r['Code']]
                        draw_chart(df_chart, bt_chart, tp3_c, tp5_c, tp8_c)
                else:
                    st.error("データの取得に失敗しました。上場廃止やコード誤りの可能性があります。")

# ----------------------------------------
# タブ3：訓練（バックテスト）
# ----------------------------------------
with tab3:
    st.markdown('<h3 style="font-size: clamp(14px, 4.5vw, 24px); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; margin-bottom: 1rem;">📉 鉄の掟：一括バックテスト</h3>', unsafe_allow_html=True)
    
    col_1, col_2 = st.columns([1, 2])
    with col_1:
        bt_c_in = st.text_area("銘柄コード（複数可）", value="6614, 3997, 4935", height=100)
        run_bt = st.button("🔥 一括バックテスト")
    with col_2:
        st.caption("⚙️ パラメーター")
        cc_1, cc_2 = st.columns(2)
        bt_push = cc_1.number_input("① 押し目 (%)", value=45, step=5)
        bt_buy_d = cc_1.number_input("② 買い期限 (日)", value=4, step=1)
        bt_tp = cc_1.number_input("③ 利確 (+%)", value=8, step=1)
        bt_lot = cc_1.number_input("⑦ 株数(基本100)", value=100, step=100)
        bt_sl_i = cc_2.number_input("④ 損切/ザラ場(-%)", value=10, step=1)
        bt_sl_c = cc_2.number_input("⑤ 損切/終値(-%)", value=8, step=1)
        bt_sell_d = cc_2.number_input("⑥ 売り期限 (日)", value=5, step=1)

    if run_bt and bt_c_in:
        t_codes = list(dict.fromkeys(re.findall(r'\b\d{4}\b', bt_c_in)))
        if not t_codes:
            st.warning("有効なコードが見つかりません。")
        else:
            all_t = []
            b_bar = st.progress(0, "仮想売買中...")
            for idx, c in enumerate(t_codes):
                raw = get_single_data(c + "0", 3)
                if raw:
                    df = clean_df(pd.DataFrame(raw))
                    pos = None
                    for i in range(14, len(df)):
                        td = df.iloc[i]
                        if pos is None:
                            win = df.iloc[i-14:i]
                            rh = win['AdjH'].max()
                            rl = win['AdjL'].min()
                            if pd.isna(rh) or pd.isna(rl):
                                continue
                                
                            idxmax = win['AdjH'].idxmax()
                            h_d = len(win[win['Date'] > win.loc[idxmax, 'Date']])
                            r14 = rh / rl if rl > 0 else 0
                            
                            if (1.3 <= r14 <= 2.0) and (h_d <= bt_buy_d):
                                targ = rh - ((rh - rl) * (bt_push / 100))
                                if td['AdjL'] <= targ:
                                    exec_p = min(td['AdjO'], targ)
                                    pos = {'b_i': i, 'b_d': td['Date'], 'b_p': exec_p, 'h': rh}
                        else:
                            bp = round(pos['b_p'], 1)
                            held = i - pos['b_i']
                            sp = 0
                            rsn = ""
                            
                            sl_i = bp * (1 - (bt_sl_i / 100))
                            tp = bp * (1 + (bt_tp / 100))
                            sl_c = bp * (1 - (bt_sl_c / 100))
                            
                            if td['AdjL'] <= sl_i:
                                sp = min(td['AdjO'], sl_i)
                                rsn = f"損切(ザ場-{bt_sl_i}%)"
                            elif td['AdjH'] >= tp:
                                sp = max(td['AdjO'], tp)
                                rsn = f"利確(+{bt_tp}%)"
                            elif td['AdjC'] <= sl_c:
                                sp = td['AdjC']
                                rsn = f"損切(終値-{bt_sl_c}%)"
                            elif held >= bt_sell_d:
                                sp = td['AdjC']
                                rsn = f"時間切れ({bt_sell_d}日)"
                                
                            if rsn:
                                sp = round(sp, 1)
                                p_pct = round(((sp / bp) - 1) * 100, 2)
                                p_amt = int((sp - bp) * bt_lot)
                                
                                all_t.append({
                                    '銘柄': c, '購入日': pos['b_d'].strftime('%Y-%m-%d'),
                                    '決済日': td['Date'].strftime('%Y-%m-%d'), '保有日数': held,
                                    '買値(円)': bp, '売値(円)': sp, '損益(%)': p_pct,
                                    '損益額(円)': p_amt, '決済理由': rsn
                                })
                                pos = None
                                
                b_bar.progress((idx + 1) / len(t_codes))
                time.sleep(0.5)
                
            b_bar.empty()
            st.success("シミュレーション完了")
            
            if not all_t:
                st.warning("シグナル点灯はありませんでした。")
            else:
                tdf = pd.DataFrame(all_t)
                tot = len(tdf)
                wins = len(tdf[tdf['損益額(円)'] > 0])
                n_prof = tdf['損益額(円)'].sum()
                sprof = tdf[tdf['損益額(円)'] > 0]['損益額(円)'].sum()
                sloss = abs(tdf[tdf['損益額(円)'] <= 0]['損益額(円)'].sum())
                
                pf = round(sprof / sloss, 2) if sloss > 0 else 'inf'
                
                st.markdown(f'<h3 style="font-size: clamp(16px, 5vw, 26px); font-weight: bold; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; margin-bottom: 1rem;">💰 総合利益額: {n_prof:,} 円</h3>', unsafe_allow_html=True)
                
                m1, m2, m3, m4 = st.columns(4)
                m1.metric("トレード回数", f"{tot} 回")
                m2.metric("勝率", f"{round((wins/tot)*100,1)} %")
                m3.metric("平均損益額", f"{int(n_prof/tot):,} 円")
                m4.metric("PF", f"{pf}")
                st.dataframe(tdf, use_container_width=True)
