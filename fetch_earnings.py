import requests
import pickle
import os
from datetime import datetime, timedelta
import time
import gzip

JQUANTS_API_KEY = os.getenv("JQUANTS_API_KEY", "").strip()
BASE_URL = "https://api.jquants.com/v2"

print(f"[{datetime.now()}] 📅 決算発表予定日収集開始（新API・未来120日間スキャン）...")

if not JQUANTS_API_KEY:
    print("❌ エラー: JQUANTS_API_KEY が設定されていません。")
    exit(1)

session = requests.Session()
session.headers.update({'x-api-key': JQUANTS_API_KEY})

earnings_db = {}
url_calendar = f"{BASE_URL}/fins/earnings-date"
total_records = 0

try:
    print("📡 J-Quants 決算発表予定日サーバーへ接続中（未来120日間スキャン）...")
    base_date_jst = datetime.utcnow() + timedelta(hours=9)
    
    # 新API仕様：scheduled_dateを必須パラメータとして未来120日分をスキャン
    for i in range(120):
        target_date = base_date_jst + timedelta(days=i)
        dt_str = target_date.strftime('%Y%m%d')
        req_params = {'scheduled_date': dt_str}
        
        while True:
            r_cal = session.get(url_calendar, params=req_params, timeout=10.0)
            
            if r_cal.status_code == 200:
                res_json = r_cal.json()
                cal_data = res_json.get("data", [])
                
                for d in cal_data:
                    c = str(d.get("Code", ""))
                    if c:
                        if c not in earnings_db: earnings_db[c] = []
                        if c[:4] not in earnings_db: earnings_db[c[:4]] = []
                        earnings_db[c].append(d)
                        earnings_db[c[:4]].append(d)
                        total_records += 1
                        
                pagination_key = res_json.get("pagination_key")
                if not pagination_key:
                    break
                
                req_params['pagination_key'] = pagination_key
                time.sleep(1.1)
            elif r_cal.status_code == 429:
                time.sleep(10.0)
                continue
            else:
                break
                
        if (i + 1) % 30 == 0:
            print(f"✅ 進捗: {i + 1}日分完了 (累計: {total_records}件確保)")
        time.sleep(1.1)

except Exception as e:
    print(f"❌ エラー: {e}")

earn_db_path = os.path.join(os.path.dirname(__file__), "earnings_db.pkl.gz")
with gzip.open(earn_db_path, "wb") as f:
    pickle.dump(earnings_db, f)

print(f"[{datetime.now()}] ✅ 決算カレンダー全件取得完了。総レコード: {total_records}件")
