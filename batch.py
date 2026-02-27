import os
import requests
import pandas as pd
import time
import re
from datetime import datetime, timedelta
from io import BytesIO
import numpy as np
import concurrent.futures

# --- 認証・通信設定（極小エイリアスで直結） ---
API_KEY = os.environ.get("JQ", "").strip()
LINE_TOKEN = os.environ.get("LT", "").strip()
LINE_USER_ID = os.environ.get("LI", "").strip()

headers = {"x-api-key": API_KEY}
BASE_URL = "https://api.jquants.com/v2"

def log(msg):
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {msg}")

def send_line(text):
    if not LINE_TOKEN or not LINE_USER_ID:
        log("エラー: LINEキーが未設定です")
        return False
    url = "https://api.line.me/v2/bot/message/push"
    req_headers = {"Content-Type": "application/json", "Authorization": f"Bearer {LINE_TOKEN}"}
    payload = {"to": LINE_USER_ID, "messages": [{"type": "text", "text": text}]}
    try:
        res = requests.post(url, headers=req_headers, json=payload, timeout=10)
        return res.status_code == 200
    except Exception as e:
        log(f"LINE送信エラー: {e}")
        return False

def clean_df(df):
    r_cols = {'AdjustmentOpen': 'AdjO', 'AdjustmentHigh': 'AdjH', 'AdjustmentLow': 'AdjL', 'AdjustmentClose': 'AdjC', 'Open': 'AdjO', 'High': 'AdjH', 'Low': 'AdjL', 'Close': 'AdjC'}
    df = df.rename(columns=r_cols)
    for c in ['AdjO', 'AdjH', 'AdjL', 'AdjC']:
        if c in df.columns: df[c] = pd.to_numeric(df[c], errors='coerce')
    if 'Date' in df.columns: df['Date'] = pd.to_datetime(df['Date']); df = df.sort_values('Date').reset_index(drop=True)
    return df

def load_master():
    try:
        h = {'User-Agent': 'Mozilla/5.0'}
        r1 = requests.get("https://www.jpx.co.jp/markets/statistics-equities/misc/01.html", headers=h, timeout=10)
        m = re.search(r'href="([^"]+data_j\.xls)"', r1.text)
        if m:
            r2 = requests.get("https://www.jpx.co.jp" + m.group(1), headers=h, timeout=15)
            df = pd.read_excel(BytesIO(r2.content), engine='xlrd')[['コード', '銘柄名', '33業種区分', '市場・商品区分']]
            df.columns = ['Code', 'CompanyName', 'Sector', 'Market']
            df['Code'] = df['Code'].astype(str) + "0"
            return df
    except Exception as e: log(f"マスター取得エラー: {e}")
    return pd.DataFrame()

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

def get_hist_data():
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
            r = requests.get(f"{BASE_URL}/equities/bars/daily?date={dt}", headers=headers, timeout=10)
            time.sleep(0.5)
            if r.status_code == 200: 
                return r.json().get("data", [])
            else:
                log(f"APIエラー(日付{dt}): HTTPステータス {r.status_code}")
        except Exception as e: 
            log(f"API通信例外: {e}")
        return []
        
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as exe:
        futs = [exe.submit(fetch, dt) for dt in dates]
        for f in concurrent.futures.as_completed(futs):
            res = f.result()
            if res: rows.extend(res)
    return rows

def main():
    log("=== バッチ処理開始 ===")
    if not API_KEY:
        log("致命的エラー: JQUANTS_API_KEY が取得できていません。")
        return

    f1_min = 200; f2_m30 = 2.0; f3_drop = -30; f4_mlong = 3.0; f5_ipo = True; f6_risk = True; f7_min14 = 1.3; f7_max14 = 2.0
    push_r = 45; limit_d = 4

    master_df = load_master()
    raw = get_hist_data()
    
    if not raw:
        log("エラー: 相場データの取得に失敗しました。")
        return

    log("データ取得完了。分析を開始します...")
    df = clean_df(pd.DataFrame(raw)).dropna(subset=['AdjC', 'AdjH', 'AdjL']).sort_values(['Code', 'Date'])
    
    df_30 = df.groupby('Code').tail(30)
    df_14 = df_30.groupby('Code').tail(14)
    counts = df_14.groupby('Code').size()
    valid = counts[counts == 14].index
    
    if valid.empty:
        log("条件を満たす銘柄データが存在しません。LINE通知はスキップします。")
        return
        
    df_14 = df_14[df_14['Code'].isin(valid)]; df_30 = df_30[df_30['Code'].isin(valid)]
    df_past = df[~df.index.isin(df_30.index)]; df_past = df_past[df_past['Code'].isin(valid)]
    
    agg_14 = df_14.groupby('Code').agg(lc=('AdjC', 'last'), h14=('AdjH', 'max'), l14=('AdjL', 'min'))
    idx_max = df_14.groupby('Code')['AdjH'].idxmax()
    h_dates = df_14.loc[idx_max, ['Code', 'Date']].rename(columns={'Date': 'h_date'})
    df_14_m = df_14.merge(h_dates, on='Code')
    d_high = df_14_m[df_14_m['Date'] > df_14_m['h_date']].groupby('Code').size().rename('d_high')
    
    agg_30 = df_30.groupby('Code').agg(l30=('AdjL', 'min'))
    agg_p = df_past.groupby('Code').agg(omax=('AdjH', 'max'), omin=('AdjL', 'min'))
    
    sum_df = agg_14.join(d_high, how='left').fillna({'d_high': 0}).join(agg_30).join(agg_p).reset_index()
    ur = sum_df['h14'] - sum_df['l14']
    sum_df['bt'] = sum_df['h14'] - (ur * (push_r / 100.0))
    
    # 【追加】到達度（%）の計算
    denom = sum_df['h14'] - sum_df['bt']
    sum_df['reach_pct'] = np.where(denom > 0, (sum_df['h14'] - sum_df['lc']) / denom * 100, 0)
    
    sum_df['r14'] = np.where(sum_df['l14'] > 0, sum_df['h14'] / sum_df['l14'], 0)
    sum_df['r30'] = np.where(sum_df['l30'] > 0, sum_df['lc'] / sum_df['l30'], 0)
    
    sum_df['ldrop'] = np.where((sum_df['omax'].notna()) & (sum_df['omax'] > 0), ((sum_df['lc'] / sum_df['omax']) - 1) * 100, 0)
    sum_df['lrise'] = np.where((sum_df['omin'].notna()) & (sum_df['omin'] > 0), sum_df['lc'] / sum_df['omin'], 0)
    
    if not master_df.empty: sum_df = pd.merge(sum_df, master_df, on='Code', how='left')
    
    sum_df = sum_df[sum_df['lc'] >= f1_min]
    sum_df = sum_df[sum_df['r30'] <= f2_m30]
    sum_df = sum_df[sum_df['ldrop'] >= f3_drop]
    sum_df = sum_df[(sum_df['lrise'] <= f4_mlong) | (sum_df['lrise'] == 0)]
    
    if f5_ipo:
        old_c = get_old_codes()
        if old_c: sum_df = sum_df[sum_df['Code'].isin(old_c)]
    if f6_risk and 'CompanyName' in sum_df.columns:
        sum_df = sum_df[~sum_df['CompanyName'].astype(str).str.contains("疑義|重要事象", na=False)]
    
    sum_df = sum_df[(sum_df['r14'] >= f7_min14) & (sum_df['r14'] <= f7_max14)]
    sum_df = sum_df[sum_df['d_high'] <= limit_d]
    sum_df = sum_df[sum_df['lc'] <= (sum_df['bt'] * 1.05)]
    
    # 【変更】到達度（reach_pct）で降順ソート
    res = sum_df.sort_values('reach_pct', ascending=False).head(30)
    
    if res.empty: 
        log("現在の相場に、標的は存在しません。LINE通知はスキップします。")
    else:
        log(f"{len(res)}銘柄の標的を検出しました。LINEへ送信します。")
        msg = f"🎯 【鉄の掟】標的抽出完了 ({len(res)}銘柄)\n"
        for i, r in res.head(10).iterrows():
            c = str(r['Code'])[:-1]
            n = r['CompanyName'] if not pd.isna(r.get('CompanyName')) else f"銘柄 {c}"
            bp = int(r['bt'])
            # 【変更】LINEメッセージに到達度を追加
            msg += f"\n■ {n} ({c})\n・現在値: {int(r['lc'])}円\n・買値目安: {bp}円 (到達度: {r['reach_pct']:.1f}%)\n・売値: +3%({int(bp*1.03)}) / +5%({int(bp*1.05)}) / +8%({int(bp*1.08)})\n"
        
        if send_line(msg): log("LINE通知 成功")
        else: log("エラー: LINE通知 失敗")

    log("=== バッチ処理終了 ===")

if __name__ == "__main__":
    main()
