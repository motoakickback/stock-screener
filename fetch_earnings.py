import requests
import pickle
import os
from datetime import datetime
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

try:
    r_cal = session.get(url_calendar, timeout=10.0)
    if r_cal.status_code == 200:
        cal_data = r_cal.json().get("data", [])
        for d in cal_data:
            c = str(d.get("Code", ""))
            if c:
                if c not in earnings_db: earnings_db[c] = []
                if c[:4] not in earnings_db: earnings_db[c[:4]] = []
                earnings_db[c].append(d)
                earnings_db[c[:4]].append(d)
        print(f"✅ 決算発表予定日: {len(cal_data)} 件のレコードを取得完了")
    else:
        print(f"⚠️ カレンダー取得失敗: ステータスコード {r_cal.status_code}")
except Exception as e:
    print(f"❌ エラー: {e}")

earn_db_path = os.path.join(os.path.dirname(__file__), "earnings_db.pkl.gz")
with gzip.open(earn_db_path, "wb") as f:
    pickle.dump(earnings_db, f)

print(f"[{datetime.now()}] ✅ 決算カレンダー取得完了。")