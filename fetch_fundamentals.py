import time
import requests
import pandas as pd
import pickle
import os
from datetime import datetime
import gzip

RED = "\033[91m"
RESET = "\033[0m"

JQUANTS_API_KEY = os.getenv("JQUANTS_API_KEY", "").strip()
BASE_URL = "https://api.jquants.com/v2"

print(f"{RED}[{datetime.now()}] 🌙 兵站部隊（ファンダメンタルズ専任）出撃...{RESET}")

if not JQUANTS_API_KEY:
    print(f"{RED}❌ エラー: JQUANTS_API_KEY が設定されていません。{RESET}")
    exit(1)

headers = {'x-api-key': JQUANTS_API_KEY}
session = requests.Session()
session.headers.update(headers)

try:
    print(f"{RED}📡 J-Quants V2 サーバーへ接続中（銘柄マスター取得）...{RESET}")
    r_info = session.get(f"{BASE_URL}/equities/master", timeout=10.0)
    r_info.raise_for_status()
    res_json = r_info.json()
    info_data = res_json.get("equities") or res_json.get("data") or res_json.get("info") or []
    
    all_codes = [str(d.get("Code") or d.get("code") or "") for d in info_data if d.get("Code") or d.get("code")]
    print(f"{RED}✅ 上場銘柄 {len(all_codes)} 件のリストを取得{RESET}")
except Exception as e:
    print(f"{RED}❌ 接続・銘柄リスト取得失敗: {e}{RESET}")
    exit(1)

fundamentals_db = {}
total = len(all_codes)
start_time = time.time()
success_count = 0

for i, code in enumerate(all_codes):
    api_code = code if len(code) >= 5 else code + "0"
    url = f"{BASE_URL}/fins/summary?code={api_code}"
    
    while True:
        time.sleep(1.1)
        try:
            r = session.get(url, timeout=10.0)
            if r.status_code == 200:
                res_data = r.json()
                data = res_data.get("summary") or res_data.get("statements") or res_data.get("data") or res_data.get("fins") or []
                
                if data:
                    success_count += 1
                    df = pd.DataFrame(data[-40:])
                    for col in df.columns:
                        if col not in ['Date', 'DisclosedDate', 'LocalCode']:
                            df[col] = pd.to_numeric(df[col], errors='coerce')
                    fundamentals_db[api_code] = df
                break
            elif r.status_code == 429:
                print(f"{RED}⚠️ [429検知] {api_code} ファンダ取得中。10秒待機してリトライします...{RESET}", flush=True)
                time.sleep(10.0)
                continue
            else:
                break
        except Exception:
            break

    elapsed = time.time() - start_time
    if (i + 1) <= 5 or (i + 1) % 100 == 0:
        percent = ((i + 1) / total) * 100
        print(f"{RED}📡 [{i + 1}/{total}] ({percent:.1f}%) 銘柄: {api_code} 確保完了 (有効データ: {success_count}件, 経過: {elapsed:.1f}秒){RESET}", flush=True)

db_path = os.path.join(os.path.dirname(__file__), "fundamentals_db.pkl.gz")
with gzip.open(db_path, "wb") as f:
    pickle.dump(fundamentals_db, f)

print(f"{RED}[{datetime.now()}] ✅ ファンダメンタルズ完了！ 総合計 {len(fundamentals_db)} 件のデータを圧縮して焼き付けました。{RESET}")
