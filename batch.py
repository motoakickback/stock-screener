import os
import requests
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import concurrent.futures
import re
from io import BytesIO
import time

# --- 1. 環境変数 ---
API_KEY = os.getenv("JQUANTS_API_KEY", os.getenv("JQ", "")).strip()
raw_webhooks = os.getenv("DISCORD_WEBHOOK", os.getenv("DW", ""))
DISCORD_WEBHOOKS = [url.strip() for url in raw_webhooks.split(",") if url.strip()]

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
        df = df.sort_values(['Code', 'Date']).dropna(subset=['AdjC']).reset_index(drop=True)
    return df

# 💎 改造ポイント：32日分ではなく「連続300営業日」を取得するように変更
def get_continuous_hist_data(days_to_fetch=300):
    print(f"📡 連続 {days_to_fetch} 営業日のデータを取得開始...")
    base = datetime.utcnow() + timedelta(hours=9)
    dates = []
    days_back = 0
    while len(dates) < days_to_fetch:
        d = base - timedelta(days=days_back)
        if d.weekday() < 5: # 土日除外
            dates.append(d.strftime('%Y%m%d'))
        days_back += 1
    
    rows = []
    def fetch(dt):
        try:
            r = requests.get(f"{BASE_URL}/equities/bars/daily?date={dt}", headers=headers, timeout=10)
            if r.status_code == 200: return r.json().get("data", [])
        except: pass
        return []
        
    # 通信負荷を考慮し、スレッド数を調整
    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as exe:
        futs = [exe.submit(fetch, dt) for dt in dates]
        for f in concurrent.futures.as_completed(futs):
            res = f.result()
            if res: rows.extend(res)
    return rows

def save_market_archive(df):
    """ 💎 アプリ（Streamlit）が読み込むための弾薬庫を更新 """
    file_path = "market_data_continuous.feather"
    # Feather形式で爆速保存（アプリ側での読み込みがコンマ秒になります）
    df.to_feather(file_path)
    print(f"✅ 【システムログ】弾薬庫（{file_path}）を連続データで更新しました。")

def send_discord_notify(message):
    for url in DISCORD_WEBHOOKS:
        try: requests.post(url, json={"content": message}, timeout=10)
        except: pass

# --- 3. メインロジック ---
def main():
    print("🚀 ミッション開始：全銘柄1年分データの集約と保存")
    
    # 1. データの「線（連続300日）」での一括取得
    raw = get_continuous_hist_data(days_to_fetch=300)
    if not raw:
        print("🚨 データの取得に失敗しました。")
        return
        
    # 2. クレンジング（カラム名の正規化）
    full_df = clean_df(pd.DataFrame(raw))
    
    # 3. アプリ用の弾薬庫（Featherファイル）を生成・上書き保存
    # ※ Feather形式で保存することで、アプリ側の読込をコンマ秒にする
    file_path = "market_data_continuous.feather"
    full_df.to_feather(file_path)
    print(f"✅ 【システムログ】弾薬庫（{file_path}）を連続データで更新しました。")
    
    # 4. Discord速報用の処理（ボスの既存ロジックを継続）
    # ※ここから下は、以前から動いているDiscord送信用の計算処理をそのまま繋いでください
    print("📬 Discord速報の配信準備を開始します...")
    # ...（以下、既存の判定・送信ロジック）...
    
    send_discord_notify(f"✅ 本日の弾薬補充完了（全 {len(full_df)} 行）\nスキャナーの1年フィルターが使用可能になりました。")

# 実行トリガー：必ず関数の外、一番最後に配置
if __name__ == "__main__":
    main()
