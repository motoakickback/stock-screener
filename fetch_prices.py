import time
import requests
import pickle
import os
from datetime import datetime, timedelta
import gzip

RED = "\033[91m"
RESET = "\033[0m"

JQUANTS_API_KEY = os.getenv("JQUANTS_API_KEY", "").strip()
BASE_URL = "https://api.jquants.com/v2"

print(f"{RED}[{datetime.now()}] 🌙 兵站部隊（株価データ専任）出撃...{RESET}")

if not JQUANTS_API_KEY:
    print(f"{RED}❌ エラー: JQUANTS_API_KEY が設定されていません。{RESET}")
    exit(1)

headers = {'x-api-key': JQUANTS_API_KEY}
session = requests.Session()
session.headers.update(headers)

prices_db = {}
base_date_jst = datetime.utcnow() + timedelta(hours=9)
days_to_fetch = 400
fetched_days = 0

for i in range(days_to_fetch):
    target_date = base_date_jst - timedelta(days=i)
    if target_date.weekday() >= 5:
        continue
        
    dt_str = target_date.strftime('%Y%m%d')
    req_params = {'date': dt_str}
    daily_data = []
    
    while True:
        time.sleep(1.1)
        try:
            r = session.get(f"{BASE_URL}/equities/bars/daily", params=req_params, timeout=10.0)
            if r.status_code == 200:
                res_json = r.json()
                data = res_json.get("daily_quotes") or res_json.get("data") or res_json.get("results") or []
                if data:
                    daily_data.extend(data)
                
                pagination_key = res_json.get("pagination_key")
                if not pagination_key:
                    break
                req_params['pagination_key'] = pagination_key
                
            elif r.status_code == 429:
                print(f"{RED}⚠️ [429検知] 株価取得中({dt_str})。10秒待機してリトライします...{RESET}", flush=True)
                time.sleep(10.0)
                continue
            else:
                break
        except Exception:
            break
            
    if daily_data:
        prices_db[dt_str] = daily_data
        fetched_days += 1
        if fetched_days % 20 == 0:
            print(f"{RED}📡 株価進捗: {fetched_days} 営業日分を取得完了...{RESET}", flush=True)

prices_db_path = os.path.join(os.path.dirname(__file__), "prices_db.pkl.gz")
with gzip.open(prices_db_path, "wb") as f:
    pickle.dump(prices_db, f)

print(f"{RED}[{datetime.now()}] ✅ 株価データ完了！ {fetched_days}営業日分を圧縮して焼き付けました。{RESET}")
