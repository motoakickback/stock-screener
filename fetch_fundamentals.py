import time
import requests
import pandas as pd
import pickle
import os
from datetime import datetime, timedelta
import gzip

# ターミナル出力用 赤色エスケープシーケンス
RED = "\033[91m"
RESET = "\033[0m"

# ==========================================
# ⚙️ J-Quants V2 API 設定（全方位・自動適応・防弾版）
# ==========================================
JQUANTS_API_KEY = os.getenv("JQUANTS_API_KEY", "").strip()
BASE_URL = "https://api.jquants.com/v2"

print(f"{RED}[{datetime.now()}] 🌙 兵站部隊（統合バッチ・完全防弾仕様）出撃...{RESET}")

if not JQUANTS_API_KEY:
    print(f"{RED}❌ エラー: JQUANTS_API_KEY が設定されていません。GitHub Secretsを確認してください。{RESET}")
    exit(1)

headers = {'x-api-key': JQUANTS_API_KEY}
session = requests.Session()
session.headers.update(headers)

# ==========================================
# 1. 全銘柄コードの取得 (/v2/equities/master)
# ==========================================
try:
    print(f"{RED}📡 J-Quants V2 サーバーへ接続中（銘柄マスター取得）...{RESET}")
    r_info = session.get(f"{BASE_URL}/equities/master", timeout=10.0)
    r_info.raise_for_status()
    
    res_json = r_info.json()
    info_data = res_json.get("equities") or res_json.get("data") or res_json.get("info") or []
    
    all_codes = []
    for d in info_data:
        code = str(d.get("Code") or d.get("code") or "")
        if code:
            all_codes.append(code)
            
    print(f"{RED}✅ 接続成功！ 上場銘柄 {len(all_codes)} 件のリストを取得{RESET}")
except Exception as e:
    print(f"{RED}❌ 接続・銘柄リスト取得失敗: {e}{RESET}")
    if 'r_info' in locals() and hasattr(r_info, 'text'):
        print(f"{RED}📝 サーバー応答: {r_info.text}{RESET}")
    exit(1)

# ==========================================
# 2. 1.1秒の絶対防弾行進で全件取得（ファンダメンタルズ専任）
# ==========================================
fundamentals_db = {}
total = len(all_codes)
start_time = time.time()
success_count = 0

print(f"{RED}🚀 全 {total} 銘柄のファンダメンタルズ強襲索敵を開始します...{RESET}")

for i, code in enumerate(all_codes):
    api_code = code if len(code) >= 5 else code + "0"
    url = f"{BASE_URL}/fins/summary?code={api_code}"
    
    while True:
        time.sleep(1.1) # 🛡️ 1.1秒の絶対待機
        try:
            r = session.get(url, timeout=10.0)
            if r.status_code == 200:
                res_data = r.json()
                data = (
                    res_data.get("summary") or 
                    res_data.get("statements") or 
                    res_data.get("data") or 
                    res_data.get("fins") or []
                )
                
                if data:
                    success_count += 1
                    df = pd.DataFrame(data[-40:])
                    for col in df.columns:
                        if col not in ['Date', 'DisclosedDate', 'LocalCode']:
                            df[col] = pd.to_numeric(df[col], errors='coerce')
                    fundamentals_db[api_code] = df
                break # 取得成功のためリトライループを抜ける
                
            elif r.status_code == 429:
                print(f"{RED}⚠️ [429検知] {api_code} ファンダ取得中。10秒待機してリトライします...{RESET}", flush=True)
                time.sleep(10.0)
                continue # リトライ実行
                
            else:
                break # 400系エラー等の場合はスキップして次へ
        except Exception as e:
            break

    elapsed = time.time() - start_time
    percent = ((i + 1) / total) * 100
    
    if (i + 1) <= 5 or (i + 1) % 100 == 0:
        print(f"{RED}📡 [{i + 1}/{total}] ({percent:.1f}%) 銘柄: {api_code} 確保完了 (有効データ: {success_count}件, 経過: {elapsed:.1f}秒){RESET}", flush=True)

db_path = os.path.join(os.path.dirname(__file__), "fundamentals_db.pkl.gz")
with gzip.open(db_path, "wb") as f:
    pickle.dump(fundamentals_db, f)

print(f"{RED}[{datetime.now()}] ✅ ファンダメンタルズ完了！ 総合計 {len(fundamentals_db)} 件のデータを圧縮して焼き付けました。{RESET}")

# ==========================================
# 📈 3. 株価データ（過去約400日分）の一括収集（ページング完全対応版）
# ==========================================
print(f"\n{RED}--- 📈 株価データ（日足）一括収集開始 ---{RESET}")
prices_db = {}
base_date_jst = datetime.utcnow() + timedelta(hours=9)
days_to_fetch = 400
fetched_days = 0

for i in range(days_to_fetch):
    target_date = base_date_jst - timedelta(days=i)
    if target_date.weekday() >= 5: # 土日は休場
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
                data = (
                    res_json.get("daily_quotes") or 
                    res_json.get("data") or 
                    res_json.get("results") or []
                )
                if data:
                    daily_data.extend(data)
                
                # 🚨 ページング対応：pagination_keyが存在すれば次ページを取得
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
        except Exception as e:
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

# ==========================================
# 📅 4. 決算発表予定日の一括収集（未来120日間・重複完全排除版）
# ==========================================
print(f"\n{RED}--- 📅 決算発表予定日 一括収集開始 ---{RESET}")
earnings_db = {}
# 🚨 正規APIへ修正
url_calendar = f"{BASE_URL}/fins/earnings-date"
total_records = 0

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
                            # 🚨 重複登録（肥大化）バグを排除し、取得コードのまま単一保存
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
            except Exception as e:
                break
                
        if (i + 1) % 30 == 0:
            print(f"{RED}✅ 決算進捗: {i + 1}日分完了 (累計: {total_records}件確保){RESET}")

except Exception as e:
    print(f"{RED}❌ エラー: {e}{RESET}")

earn_db_path = os.path.join(os.path.dirname(__file__), "earnings_db.pkl.gz")
with gzip.open(earn_db_path, "wb") as f:
    pickle.dump(earnings_db, f)

print(f"{RED}[{datetime.now()}] ✅ 決算カレンダー全件取得完了。総レコード: {total_records}件{RESET}")
print(f"{RED}🚀 全システムの更新を正常に終了しました。{RESET}")
