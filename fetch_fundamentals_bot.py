import time
import requests
import pandas as pd
import pickle
import os
from datetime import datetime
import gzip

JQUANTS_API_KEY = os.getenv("JQUANTS_API_KEY", "").strip()
BASE_URL = "https://api.jquants.com/v2"

print(f"[{datetime.now()}] 🌙 兵站部隊（ファンダメンタルズ収集）出撃...")

if not JQUANTS_API_KEY:
    print("❌ エラー: JQUANTS_API_KEY が設定されていません。")
    exit(1)

session = requests.Session()
session.headers.update({'x-api-key': JQUANTS_API_KEY})

try:
    r_info = session.get(f"{BASE_URL}/equities/master", timeout=10.0)
    r_info.raise_for_status()
    info_data = r_info.json().get("equities", [])
    all_codes = [str(d.get("Code", "")) for d in info_data if d.get("Code")]
except Exception as e:
    print(f"❌ 銘柄マスター取得失敗: {e}")
    exit(1)

fundamentals_db = {}
total = len(all_codes)
start_time = time.time()
success_count = 0

for i, code in enumerate(all_codes):
    api_code = code if len(code) >= 5 else code + "0"
    url = f"{BASE_URL}/fins/summary?code={api_code}"
    time.sleep(1.1)
    
    try:
        r = session.get(url, timeout=10.0)
        if r.status_code == 200:
            data = r.json().get("summary") or r.json().get("data") or []
            if data:
                success_count += 1
                df = pd.DataFrame(data[-40:])
                for col in df.columns:
                    if col not in ['Date', 'DisclosedDate', 'LocalCode']:
                        df[col] = pd.to_numeric(df[col], errors='coerce')
                fundamentals_db[api_code] = df
        elif r.status_code == 429:
            time.sleep(10.0)
    except Exception:
        continue

    if (i + 1) <= 5 or (i + 1) % 100 == 0:
        elapsed = time.time() - start_time
        print(f"📡 [{i + 1}/{total}] 銘柄: {api_code} (有効: {success_count}件, 経過: {elapsed:.1f}秒)")

db_path = os.path.join(os.path.dirname(__file__), "fundamentals_db.pkl.gz")
with gzip.open(db_path, "wb") as f:
    pickle.dump(fundamentals_db, f)

print(f"[{datetime.now()}] ✅ ファンダメンタルズ取得完了。")
