import time
import requests
import pandas as pd
import pickle
import os
from datetime import datetime
import pytz
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

# 1. 既存DBのマウントと自己診断
db_path = os.path.join(os.path.dirname(__file__), "fundamentals_db.pkl.gz")
fundamentals_db = {}
is_initial_build = True

if os.path.exists(db_path):
    try:
        with gzip.open(db_path, "rb") as f:
            fundamentals_db = pickle.load(f)
        if len(fundamentals_db) > 3000:
            is_initial_build = False
            print(f"{RED}✅ 既存DBロード完了 (収録数: {len(fundamentals_db)}件) ➔ 【差分更新モード】へ移行{RESET}")
        else:
            print(f"{RED}⚠️ 既存DBが不完全です ({len(fundamentals_db)}件) ➔ 【初回構築/補完モード】へ移行{RESET}")
    except Exception as e:
        print(f"{RED}⚠️ DB読み込みエラー: {e} ➔ 【初回構築モード】へ移行{RESET}")

# 2. 銘柄マスターの取得
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

start_time = time.time()
success_count = 0

if is_initial_build:
    # ---------------------------------------------------------
    # 【モード1】初回構築・欠損補完（スロットル制御）
    # ---------------------------------------------------------
    missing_codes = [c for c in all_codes if (c if len(c) >= 5 else c + "0") not in fundamentals_db]
    total = len(missing_codes)
    print(f"{RED}⏳ 不足している {total} 銘柄をスロットル制御 (1分40回ペース) で取得します...{RESET}")
    
    for i, code in enumerate(missing_codes):
        api_code = code if len(code) >= 5 else code + "0"
        url = f"{BASE_URL}/fins/summary?code={api_code}"
        
        while True:
            time.sleep(1.5)
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
                    print(f"{RED}⚠️ [429検知] {api_code} 制限到達。15秒待機してリトライ...{RESET}", flush=True)
                    time.sleep(15.0)
                    continue
                else:
                    break
            except Exception:
                break

        elapsed = time.time() - start_time
        if (i + 1) <= 5 or (i + 1) % 100 == 0 or (i + 1) == total:
            percent = ((i + 1) / total) * 100
            print(f"{RED}📡 [{i + 1}/{total}] ({percent:.1f}%) 銘柄: {api_code} 確保 (経過: {elapsed:.1f}秒){RESET}", flush=True)

else:
    # ---------------------------------------------------------
    # 【モード2】差分更新アーキテクチャ（ページング対応）
    # ---------------------------------------------------------
    tz = pytz.timezone('Asia/Tokyo')
    today_str = datetime.now(tz).strftime("%Y-%m-%d")
    print(f"{RED}🚀 差分更新実行: {today_str} に発表された決算データのみを抽出・マージします...{RESET}")
    
    url = f"{BASE_URL}/fins/summary?date={today_str}"
    
    while url:
        time.sleep(1.5)
        try:
            r = session.get(url, timeout=10.0)
            if r.status_code == 200:
                res_data = r.json()
                data = res_data.get("summary") or res_data.get("statements") or res_data.get("data") or res_data.get("fins") or []
                
                if data:
                    updates_by_code = {}
                    for row in data:
                        code_val = row.get("LocalCode") or row.get("Code") or row.get("code")
                        if not code_val: continue
                        api_code = str(code_val) if len(str(code_val)) >= 5 else str(code_val) + "0"
                        if api_code not in updates_by_code:
                            updates_by_code[api_code] = []
                        updates_by_code[api_code].append(row)
                        
                    for api_code, rows in updates_by_code.items():
                        new_df = pd.DataFrame(rows)
                        for col in new_df.columns:
                            if col not in ['Date', 'DisclosedDate', 'LocalCode']:
                                new_df[col] = pd.to_numeric(new_df[col], errors='coerce')
                        
                        if api_code in fundamentals_db:
                            combined = pd.concat([fundamentals_db[api_code], new_df], ignore_index=True)
                            if 'DisclosedDate' in combined.columns:
                                combined = combined.drop_duplicates(subset=['DisclosedDate'], keep='last')
                            fundamentals_db[api_code] = combined.tail(40).reset_index(drop=True)
                        else:
                            fundamentals_db[api_code] = new_df.tail(40).reset_index(drop=True)
                        
                        success_count += 1
                        print(f"{RED}🔄 差分マージ完了: {api_code}{RESET}")

                pagination_key = res_data.get("pagination_key")
                if pagination_key:
                    print(f"{RED}⏭️ 次のページ（Pagination）を取得中...{RESET}")
                    url = f"{BASE_URL}/fins/summary?date={today_str}&pagination_key={pagination_key}"
                else:
                    url = None
                    break
            elif r.status_code == 429:
                print(f"{RED}⚠️ [429検知] 制限到達。15秒待機してリトライ...{RESET}", flush=True)
                time.sleep(15.0)
                continue
            else:
                print(f"{RED}⚠️ 通信エラー: {r.status_code}{RESET}")
                break
        except Exception as e:
            print(f"{RED}❌ 差分取得エラー: {e}{RESET}")
            break

# 3. 最終データの焼き付け
with gzip.open(db_path, "wb") as f:
    pickle.dump(fundamentals_db, f)

print(f"{RED}[{datetime.now()}] ✅ 任務完了！ 総合計 {len(fundamentals_db)} 件のデータを圧縮・永続化しました。{RESET}")
