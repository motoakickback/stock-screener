import requests
import pickle
import os
from datetime import datetime
import time
import gzip

JQUANTS_API_KEY = os.getenv("JQUANTS_API_KEY", "").strip()
BASE_URL = "https://api.jquants.com/v2"

print(f"[{datetime.now()}] 📅 決算発表予定日収集開始...")

if not JQUANTS_API_KEY:
    print("❌ エラー: JQUANTS_API_KEY が設定されていません。")
    exit(1)

session = requests.Session()
session.headers.update({'x-api-key': JQUANTS_API_KEY})

earnings_db = {}
url_calendar = f"{BASE_URL}/equities/earnings-calendar"
pagination_key = None
page_count = 1
total_records = 0

try:
    print("📡 J-Quants カレンダーサーバーへ接続中（ページング対応）...")
    while True:
        req_params = {}
        if pagination_key:
            req_params['pagination_key'] = pagination_key
        
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
            print(f"✅ {page_count}ページ目取得完了 (累計: {total_records} 件のレコードを確保)")
            
            if not pagination_key:
                break
            
            page_count += 1
            time.sleep(1.1)
        else:
            print(f"⚠️ カレンダー取得失敗: ステータスコード {r_cal.status_code}")
            break
except Exception as e:
    print(f"❌ エラー: {e}")

earn_db_path = os.path.join(os.path.dirname(__file__), "earnings_db.pkl.gz")
with gzip.open(earn_db_path, "wb") as f:
    pickle.dump(earnings_db, f)

print(f"[{datetime.now()}] ✅ 決算カレンダー全件取得完了。")
