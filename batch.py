import os
import requests
import pandas as pd
import time
import re
from datetime import datetime, timedelta
from io import BytesIO
import numpy as np
import concurrent.futures

# --- 認証・通信設定 ---
API_KEY = os.environ.get("JQ", "").strip()
LINE_TOKEN = os.environ.get("LT", "").strip()
LINE_USER_ID = os.environ.get("LI", "").strip()
headers = {"x-api-key": API_KEY}
BASE_URL = "https://api.jquants.com/v2"

def log(msg): print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {msg}")

def send_line(text):
    if not LINE_TOKEN or not LINE_USER_ID: return False
    url = "https://api.line.me/v2/bot/message/push"
    req_headers = {"Content-Type": "application/json", "Authorization": f"Bearer {LINE_TOKEN}"}
    payload = {"to": LINE_USER_ID, "messages": [{"type": "text", "text": text}]}
    try:
        res = requests.post(url, headers=req_headers, json=payload, timeout=10)
        return res.status_code == 200
    except: return False

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
    except: pass
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
            if r.status_code == 200: return r.json().get("data", [])
        except: pass
        return []
        
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as exe:
        futs = [exe.submit(fetch, dt) for dt in dates]
        for f in concurrent.futures.as_completed(futs):
            res = f.result()
            if res: rows.extend(res)
    return rows

def check_double_top(df_sub):
    try:
        v = df_sub['AdjH'].values; c = df_sub['AdjC'].values; l = df_sub['AdjL'].values
        if len(v) < 15: return False
        peaks = []
        for i in range(1, len(v)-1):
            if v[i] == max(v[i-1:i+2]):
                if not peaks or (i - peaks[-1][0] > 3): peaks.append((i, v[i]))
        if len(v) >= 2 and v[-1] > v[-2]:
            if not peaks or (len(v)-1 - peaks[-1][0] > 3): peaks.append((len(v)-1, v[-1]))
        if len(peaks) >= 2:
            p2_idx, p2_val = peaks[-1]; p1_idx, p1_val = peaks[-2]
            if abs(p2_val - p1_val) / max(p2_val, p1_val) < 0.05:
                valley = min(l[p1_idx:p2_idx+1]) if p2_idx > p1_idx else p1_val
                if valley < min(p1_val, p2_val) * 0.95:
                    if c[-1] < p2_val * 0.97: return True
        return False
    except: return False

def check_head_shoulders(df_sub):
    try:
        v = df_sub['AdjH'].values; c = df_sub['AdjC'].values
        if len(v) < 20: return False
        peaks = []
        for i in range(1, len(v)-1):
            if v[i] == max(v[i-1:i+2]):
                if not peaks or (i - peaks[-1][0] > 2): peaks.append((i, v[i]))
        if len(peaks) >= 3:
            p3_idx, p3_val = peaks[-1]; p2_idx, p2_val = peaks[-2]; p1_idx, p1_val = peaks[-3]
            if p2_val > p1_val and p2_val > p3_val:
                if abs(p3_val - p1_val) / max(p3_val, p1_val) < 0.10:
                    if c[-1] < p3_val * 0.97: return True
        return False
    except: return False

def check_double_bottom(df_sub):
    try:
        l = df_sub['AdjL'].values; c = df_sub['AdjC'].values; h = df_sub['AdjH'].values
        if len(l) < 15: return False
        valleys = []
        for i in range(1, len(l)-1):
            if l[i] == min(l[i-1:i+2]):
                if not valleys or (i - valleys[-1][0] > 3): valleys.append((i, l[i]))
        if len(l) >= 3 and l[-2] == min(l[-3:]):
             if not valleys or (len(l)-2 - valleys[-1][0] > 3): valleys.append((len(l)-2, l[-2]))
        if len(valleys) >= 2:
            v2_idx, v2_val = valleys[-1]; v1_idx, v1_val = valleys[-2]
            if abs(v2_val - v1_val) / min(v2_val, v1_val) < 0.05:
                peak = max(h[v1_idx:v2_idx+1]) if v2_idx > v1_idx else v1_val
                if peak > max(v1_val, v2_val) * 1.04: 
                    if c[-1] > v2_val * 1.01: return True
        return False
    except: return False

def main():
    log("=== バッチ処理開始 ===")
    if not API_KEY: log("致命的エラー: APIキーがありません。"); return

    f1_min = 200; f2_m30 = 2.0; f3_drop = -30; f4_mlong = 3.0; f5_ipo = True; f6_risk = True; f7_min14 = 1.3; f7_max14 = 2.0
    push_r = 45; limit_d = 4

    master_df = load_master()
    raw = get_hist_data()
    if not raw: log("エラー: 相場データの取得に失敗しました。"); return

    log("データ取得完了。分析を開始します...")
    df = clean_df(pd.DataFrame(raw)).dropna(subset=['AdjC', 'AdjH', 'AdjL']).sort_values(['Code', 'Date'])
    
    df_30 = df.groupby('Code').tail(30)
    df_14 = df_30.groupby('Code').tail(14)
    counts = df_14.groupby('Code').size()
    valid = counts[counts == 14].index
    
    if valid.empty: log("条件を満たす銘柄データが存在しません。LINE通知はスキップします。"); return
        
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
    sum_df['tp3'] = sum_df['bt'] * 1.03; sum_df['tp5'] = sum_df['bt'] * 1.05; sum_df['tp8'] = sum_df['bt'] * 1.08
    
    denom = sum_df['h14'] - sum_df['bt']
    sum_df['reach_pct'] = np.where(denom > 0, (sum_df['h14'] - sum_df['lc']) / denom * 100, 0)
    
    sum_df['r14'] = np.where(sum_df['l14'] > 0, sum_df['h14'] / sum_df['l14'], 0)
    sum_df['r30'] = np.where(sum_df['l30'] > 0, sum_df['lc'] / sum_df['l30'], 0)
    sum_df['ldrop'] = np.where((sum_df['omax'].notna()) & (sum_df['omax'] > 0), ((sum_df['lc'] / sum_df['omax']) - 1) * 100, 0)
    sum_df['lrise'] = np.where((sum_df['omin'].notna()) & (sum_df['omin'] > 0), sum_df['lc'] / sum_df['omin'], 0)
    
    dt_s = df_30.groupby('Code').apply(check_double_top).rename('is_dt')
    hs_s = df_30.groupby('Code').apply(check_head_shoulders).rename('is_hs')
    db_s = df_30.groupby('Code').apply(check_double_bottom).rename('is_db')
    sum_df = sum_df.merge(dt_s, on='Code', how='left').merge(hs_s, on='Code', how='left').merge(db_s, on='Code', how='left')
    sum_df = sum_df.fillna({'is_dt': False, 'is_hs': False, 'is_db': False})
    
    sum_df['is_defense'] = (~sum_df['is_dt']) & (~sum_df['is_hs']) & (sum_df['lc'] <= (sum_df['l14'] * 1.03))
    
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
        
    # バッチ処理では危険波形を絶対排除
    sum_df = sum_df[(~sum_df['is_dt']) & (~sum_df['is_hs'])]
    
    sum_df = sum_df[(sum_df['r14'] >= f7_min14) & (sum_df['r14'] <= f7_max14)]
    sum_df = sum_df[sum_df['d_high'] <= limit_d]
    sum_df = sum_df[sum_df['lc'] <= (sum_df['bt'] * 1.05)]
    
    # バッチは攻め（三川）を最優先でソート
    res = sum_df.sort_values(['is_db', 'reach_pct'], ascending=[False, False]).head(10)
    
    if res.empty: 
        log("現在の相場に、標的は存在しません。LINE通知はスキップします。")
    else:
        log(f"{len(res)}銘柄の標的を検出しました。LINEへ送信します。")
        msg = f"🎯 【鉄の掟】標的抽出完了 ({len(res)}銘柄)\n"
        for i, r in res.iterrows():
            c = str(r['Code'])[:-1]
            n = r['CompanyName'] if not pd.isna(r.get('CompanyName')) else f"銘柄 {c}"
            bp = int(r['bt'])
            
            # シグナルアイコンの付与
            icon = "🔥" if r['is_db'] else ("🛡️" if r['is_defense'] else "■")
            
            msg += f"\n{icon} {n} ({c})\n・現在値: {int(r['lc'])}円\n・買値目安: {bp}円 (到達度: {r['reach_pct']:.1f}%)\n・売値: +3%({int(r['tp3'])}) / +5%({int(r['tp5'])}) / +8%({int(r['tp8'])})\n"
        
        if send_line(msg): log("LINE通知 成功")
        else: log("エラー: LINE通知 失敗")

    log("=== バッチ処理終了 ===")

if __name__ == "__main__":
    main()
