import os
import requests
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import concurrent.futures
import re
from io import BytesIO

# --- 1. 環境変数（超高感度センサー搭載） ---
API_KEY = os.getenv("JQUANTS_API_KEY", os.getenv("JQ", "")).strip()
LINE_TOKEN = os.getenv("LINE_NOTIFY_TOKEN", os.getenv("LT", "")).strip()

# どちらの鍵が欠落しているかを明確にログに出力する
print(f"【システムログ】JQセンサー反応: {bool(API_KEY)} / LTセンサー反応: {bool(LINE_TOKEN)}")

if not API_KEY or not LINE_TOKEN:
    print("🚨 【緊急警告】V15.5: 必要な暗号鍵が欠落しています！")
    if not API_KEY:
        print("👉 J-Quants APIキー (JQ) を取得できませんでした。GitHubのSecretsを確認してください。")
    if not LINE_TOKEN:
        print("👉 LINE Notify トークン (LT) を取得できませんでした。GitHubのSecretsを確認してください。")
    exit(1)

headers = {"x-api-key": API_KEY}
BASE_URL = "https://api.jquants.com/v2"

# --- 2. 共通関数 ---
def clean_df(df):
    r_cols = {'AdjustmentOpen': 'AdjO', 'AdjustmentHigh': 'AdjH', 'AdjustmentLow': 'AdjL', 'AdjustmentClose': 'AdjC', 'Open': 'AdjO', 'High': 'AdjH', 'Low': 'AdjL', 'Close': 'AdjC'}
    df = df.rename(columns=r_cols)
    for c in ['AdjO', 'AdjH', 'AdjL', 'AdjC']:
        if c in df.columns: df[c] = pd.to_numeric(df[c], errors='coerce')
    if 'Date' in df.columns:
        df['Date'] = pd.to_datetime(df['Date'])
        df = df.sort_values('Date').dropna(subset=['AdjO', 'AdjH', 'AdjL', 'AdjC']).reset_index(drop=True)
    return df

def load_master():
    try:
        h = {'User-Agent': 'Mozilla/5.0'}
        r1 = requests.get("https://www.jpx.co.jp/markets/statistics-equities/misc/01.html", headers=h, timeout=10)
        m = re.search(r'href="([^"]+data_j\.xls)"', r1.text)
        if m:
            r2 = requests.get("https://www.jpx.co.jp" + m.group(1), headers=h, timeout=15)
            df = pd.read_excel(BytesIO(r2.content), engine='xlrd')[['コード', '銘柄名', '33業種区分', '市場・商品区分', '規模区分']]
            df.columns = ['Code', 'CompanyName', 'Sector', 'Market', 'Scale']
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
            if r.status_code == 200: return r.json().get("data", [])
        except: pass
        return []
        
    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as exe:
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

def send_line_notify(message):
    headers = {"Authorization": f"Bearer {LINE_TOKEN}"}
    data = {"message": message}
    requests.post("https://notify-api.line.me/api/notify", headers=headers, data=data)

# --- 3. メインロジック ---
def main():
    print("データ取得開始...")
    master_df = load_master()
    old_codes = get_old_codes()
    raw = get_hist_data()
    
    if not raw:
        send_line_notify("\n🚨 データの取得に失敗しました。")
        return
        
    d_raw = pd.DataFrame(raw)
    df = clean_df(d_raw).dropna(subset=['AdjC', 'AdjH', 'AdjL']).sort_values(['Code', 'Date'])
    
    df_30 = df.groupby('Code').tail(30)
    df_14 = df_30.groupby('Code').tail(14)
    counts = df_14.groupby('Code').size()
    valid = counts[counts == 14].index
    
    if valid.empty:
        send_line_notify("\n🚨 条件を満たすデータが存在しません。")
        return

    df_14 = df_14[df_14['Code'].isin(valid)]
    df_30 = df_30[df_30['Code'].isin(valid)]
    df_past = df[~df.index.isin(df_30.index)]; df_past = df_past[df_past['Code'].isin(valid)]
    
    agg_14 = df_14.groupby('Code').agg(
        lc=('AdjC', 'last'), 
        prev_c=('AdjC', lambda x: x.iloc[-2] if len(x) > 1 else np.nan),
        c_3days_ago=('AdjC', lambda x: x.iloc[-4] if len(x) > 3 else np.nan),
        h14=('AdjH', 'max'), 
        l14=('AdjL', 'min')
    )
    
    idx_max = df_14.groupby('Code')['AdjH'].idxmax()
    h_dates = df_14.loc[idx_max, ['Code', 'Date']].rename(columns={'Date': 'h_date'})
    df_14_m = df_14.merge(h_dates, on='Code')
    d_high = df_14_m[df_14_m['Date'] > df_14_m['h_date']].groupby('Code').size().rename('d_high')
    
    agg_30 = df_30.groupby('Code').agg(l30=('AdjL', 'min'))
    agg_p = df_past.groupby('Code').agg(omax=('AdjH', 'max'), omin=('AdjL', 'min'))
    sum_df = agg_14.join(d_high, how='left').fillna({'d_high': 0}).join(agg_30).join(agg_p).reset_index()
    
    # --- パラメーター（中小型株の黄金比プリセットを適用） ---
    push_r = 50
    limit_d = 4
    sl_i = 8 # 損切8%
    
    ur = sum_df['h14'] - sum_df['l14']
    sum_df['bt'] = sum_df['h14'] - (ur * (push_r / 100.0))
    sum_df['tp5'] = sum_df['bt'] * 1.05; sum_df['tp10'] = sum_df['bt'] * 1.10; sum_df['tp15'] = sum_df['bt'] * 1.15; sum_df['tp20'] = sum_df['bt'] * 1.20
    
    denom = sum_df['h14'] - sum_df['bt']
    sum_df['reach_pct'] = np.where(denom > 0, (sum_df['h14'] - sum_df['lc']) / denom * 100, 0)
    sum_df['r14'] = np.where(sum_df['l14'] > 0, sum_df['h14'] / sum_df['l14'], 0)
    sum_df['r30'] = np.where(sum_df['l30'] > 0, sum_df['lc'] / sum_df['l30'], 0)
    sum_df['ldrop'] = np.where((sum_df['omax'].notna()) & (sum_df['omax'] > 0), ((sum_df['lc'] / sum_df['omax']) - 1) * 100, 0)
    sum_df['lrise'] = np.where((sum_df['omin'].notna()) & (sum_df['omin'] > 0), sum_df['lc'] / sum_df['omin'], 0)
    
    sum_df['daily_pct'] = np.where(sum_df['prev_c'] > 0, (sum_df['lc'] / sum_df['prev_c']) - 1, 0)
    sum_df['pct_3days'] = np.where(sum_df['c_3days_ago'] > 0, (sum_df['lc'] / sum_df['c_3days_ago']) - 1, 0)
    
    dt_s = df_30.groupby('Code').apply(check_double_top).rename('is_dt')
    hs_s = df_30.groupby('Code').apply(check_head_shoulders).rename('is_hs')
    db_s = df_30.groupby('Code').apply(check_double_bottom).rename('is_db')
    sum_df = sum_df.merge(dt_s, on='Code', how='left').merge(hs_s, on='Code', how='left').merge(db_s, on='Code', how='left')
    sum_df = sum_df.fillna({'is_dt': False, 'is_hs': False, 'is_db': False})
    
    sum_df['is_defense'] = (~sum_df['is_dt']) & (~sum_df['is_hs']) & (sum_df['lc'] <= (sum_df['l14'] * 1.03))
    
    if not master_df.empty: sum_df = pd.merge(sum_df, master_df, on='Code', how='left')
    
    # 1. 基礎フィルター
    sum_df = sum_df[sum_df['lc'] >= 200]
    sum_df = sum_df[sum_df['r30'] <= 2.0]
    sum_df = sum_df[sum_df['ldrop'] >= -30]
    sum_df = sum_df[(sum_df['lrise'] <= 3.0) | (sum_df['lrise'] == 0)]
    
    # 2. 波形・高値フィルター
    sum_df = sum_df[(~sum_df['is_dt']) & (~sum_df['is_hs'])]
    sum_df = sum_df[(sum_df['r14'] >= 1.3) & (sum_df['r14'] <= 2.0)]
    sum_df = sum_df[sum_df['d_high'] <= limit_d]
    
    # 3. 疑義注記除外
    if 'CompanyName' in sum_df.columns:
        sum_df = sum_df[~sum_df['CompanyName'].astype(str).str.contains("疑義|重要事象", na=False)]
        
    # 4. イージス防壁（ETF・REIT・マクロ除外）
    if 'Sector' in sum_df.columns:
        sum_df = sum_df[sum_df['Sector'].notna()] 
        sum_df = sum_df[sum_df['Sector'] != '-']
        sum_df = sum_df[~sum_df['CompanyName'].astype(str).str.contains("ETF|投信|ブル|ベア|REIT|ﾘｰﾄ", na=False, flags=re.IGNORECASE)]
    
    # 5. イージス防壁（バイオ株除外）
    if 'Sector' in sum_df.columns:
        sum_df = sum_df[sum_df['Sector'] != '医薬品']

    # 6. イージス防壁（IPO・英字コード除外）
    if old_codes: sum_df = sum_df[sum_df['Code'].isin(old_codes)]
    sum_df = sum_df[~sum_df['Code'].astype(str).str.contains(r'[a-zA-Z]')]

    # 7. イージス防壁（距離感の適正化 ＆ 落ちるナイフ除外 V15.5完全版）
    sum_df = sum_df[(sum_df['lc'] <= (sum_df['bt'] * 1.05)) & (sum_df['lc'] >= (sum_df['bt'] * 0.85))]
    
    sl_ratio_daily = - (sl_i / 100.0)
    three_days_sl = sl_ratio_daily * 1.5
    sum_df = sum_df[(sum_df['daily_pct'] >= sl_ratio_daily) & (sum_df['pct_3days'] >= three_days_sl)]
    
    # --- ソート（到達度順）---
    res = sum_df.sort_values('reach_pct', ascending=False).head(10)
    
    # --- LINEメッセージ生成 ---
    if res.empty:
        msg = "\n📊 本日の全軍スキャン結果\n\n🎯 標的：なし\n全てのノイズと危険波形を排除しました。本日は待ち伏せを継続します。"
    else:
        msg = f"\n📊 本日の全軍スキャン結果\n\n🎯 標的：{len(res)} 銘柄捕捉\n"
        for _, r in res.iterrows():
            c = str(r['Code'])[:-1]
            n = str(r['CompanyName'])[:8] if 'CompanyName' in r else "不明"
            lc = int(r['lc'])
            bt = int(r['bt'])
            reach = round(r['reach_pct'], 1)
            
            dpct = r['daily_pct'] * 100
            sign = "+" if dpct >= 0 else ""
            dpct_str = f"{sign}{dpct:.1f}%"
            
            sig = ""
            if r['is_db']: sig = " 🔥三川底打ち"
            if r['is_defense']: sig = " 🛡️鉄壁"
            
            msg += f"\n🏢 {n}({c}){sig}\n"
            msg += f"  現在: {lc}円 ({dpct_str})\n"
            msg += f"  目標: {bt}円\n"
            
            tp20 = int(r['tp20'])
            tp15 = int(r['tp15'])
            tp10 = int(r['tp10'])
            tp5 = int(r['tp5'])
            sl5 = int(bt * 0.95)
            sl8 = int(bt * 0.92)
            sl15 = int(bt * 0.85)
            
            msg += f"  [利確] 20%:{tp20} / 15%:{tp15}\n"
            msg += f"  [損切] -5%:{sl5} / -8%:{sl8}\n"
            msg += f"  到達度: {reach}%\n"

    send_line_notify(msg)
    print("LINE通知完了")

if __name__ == "__main__":
    main()
