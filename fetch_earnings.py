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

print(f"{RED}[{datetime.now()}] 🌙 兵站部隊（決算発表予定日専任）出撃...{RESET}")

if not JQUANTS_API_KEY:
    print(f"{RED}❌ エラー: JQUANTS_API_KEY が設定されていません。{RESET}")
    exit(1)

headers = {'x-api-key': JQUANTS_API_KEY}
session = requests.Session()
session.headers.update(headers)

earnings_db = {}
url_calendar = f"{BASE_URL}/fins/earnings-date"
total_records = 0
base_date_jst = datetime.utcnow() + timedelta(hours=9)

try:
    print(f"{RED}📡 J-Quants 決算発表予定日サーバーへ接続中（未来120日間スキャン）...{RESET}")
    
    for i in range(120):
        target_date = base_date_jst + timedelta(days=i)
        dt_str = target_date.strftime('%Y%m%d')
        req_params = {'scheduled_date': dt_str}
        
        while True:
            time.sleep(1.1)
            try:
                r_cal = session.get(url_calendar, params=req_params, timeout=10.0)
                if r_cal.status_code == 200:
                    res_json = r_cal.json()
                    cal_data = res_json.get("data", [])
                    
                    for d in cal_data:
                        c = str(d.get("Code", ""))
                        if c:
                            if c not in earnings_db: earnings_db[c] = []
                            earnings_db[c].append(d)
                            total_records += 1
                            
                    pagination_key = res_json.get("pagination_key")
                    if not pagination_key:
                        break
                    
                    req_params['pagination_key'] = pagination_key
                elif r_cal.status_code == 429:
                    print(f"{RED}⚠️ [429検知] 決算取得中({dt_str})。10秒待機してリトライ...{RESET}", flush=True)
                    time.sleep(10.0)
                    continue
                else:
                    break
            except Exception:
                break
                
        if (i + 1) % 30 == 0:
            print(f"{RED}✅ 決算進捗: {i + 1}日分完了 (累計: {total_records}件確保){RESET}")

except Exception as e:
    print(f"{RED}❌ エラー: {e}{RESET}")

earn_db_path = os.path.join(os.path.dirname(__file__), "earnings_db.pkl.gz")
with gzip.open(earn_db_path, "wb") as f:
    pickle.dump(earnings_db, f)

print(f"{RED}[{datetime.now()}] ✅ 決算カレンダー全件取得完了。総レコード: {total_records}件{RESET}")
