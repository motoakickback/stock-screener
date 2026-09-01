import time
import requests
import pickle
import os
from datetime import datetime, timedelta
import gzip

JQUANTS_API_KEY = os.getenv("JQUANTS_API_KEY", "").strip()
BASE_URL = "https://api.jquants.com/v2"

print(f"[{datetime.now()}] 📈 株価データ（日足）一括収集開始...")

if not JQUANTS_API_KEY:
    print("❌ エラー: JQUANTS_API_KEY が設定されていません。")
    exit(1)

session = requests.Session()
session.headers.update({'x-api-key': JQUANTS_API_KEY})

prices_db = {}
base_date_jst = datetime.utcnow() + timedelta(hours=9)
days_to_fetch = 400
fetched_days = 0

for i in range(days_to_fetch):
    target_date = base_date_jst - timedelta(days=i)
    if target_date.weekday() >= 5:
        continue
        
    dt_str = target_date.strftime('%Y%m%d')
    url = f"{BASE_URL}/equities/bars/daily?date={dt_str}"
    time.sleep(1.1)
    
    try:
        r = session.get(url, timeout=10.0)
        if r.status_code == 200:
            data = r.json().get("daily_quotes") or r.json().get("data") or []
            if data:
                prices_db[dt_str] = data
                fetched_days += 1
                if fetched_days % 20 == 0:
                    print(f"📡 株価進捗: {fetched_days} 営業日分を取得完了...")
        elif r.status_code == 429:
            time.sleep(10.0)
    except Exception:
        continue

prices_db_path = os.path.join(os.path.dirname(__file__), "prices_db.pkl.gz")
with gzip.open(prices_db_path, "wb") as f:
    pickle.dump(prices_db, f)

print(f"[{datetime.now()}] ✅ 株価データ取得完了。({fetched_days}日分)")