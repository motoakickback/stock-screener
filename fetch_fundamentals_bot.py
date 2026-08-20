import time
import requests
import pandas as pd
import pickle
import os
from datetime import datetime

# ==========================================
# ⚙️ J-Quants V2 API 設定（全方位・自動適応版）
# ==========================================
JQUANTS_API_KEY = os.getenv("JQUANTS_API_KEY", "").strip()
BASE_URL = "https://api.jquants.com/v2"

print(f"[{datetime.now()}] 🌙 兵站部隊（ファンダメンタルズ収集・V2自動適応版）出撃...")

if not JQUANTS_API_KEY:
    print("❌ エラー: JQUANTS_API_KEY が設定されていません。GitHub Secretsを確認してください。")
    exit(1)

headers = {'x-api-key': JQUANTS_API_KEY}
session = requests.Session()
session.headers.update(headers)

# 1. 全銘柄コードの取得
try:
    print("📡 J-Quants V2 サーバーへ接続中（銘柄マスター取得）...")
    r_info = session.get(f"{BASE_URL}/equities/master", timeout=10.0)
    r_info.raise_for_status()
    
    res_json = r_info.json()
    info_data = res_json.get("equities") or res_json.get("data") or res_json.get("info") or []
    
    all_codes = []
    for d in info_data:
        code = str(d.get("Code") or d.get("code") or "")
        if code:
            all_codes.append(code)
            
    print(f"✅ 接続成功！ 上場銘柄 {len(all_codes)} 件のリストを取得")
except Exception as e:
    print(f"❌ 接続・銘柄リスト取得失敗: {e}")
    if 'r_info' in locals() and hasattr(r_info, 'text'):
        print(f"📝 サーバー応答: {r_info.text}")
    exit(1)

# 2. 1.1秒の絶対防弾行進で全件取得（全方位キー自動適応型）
fundamentals_db = {}
total = len(all_codes)
start_time = time.time()
success_count = 0

print(f"🚀 全 {total} 銘柄のファンダメンタルズ強襲索敵を開始します...")

for i, code in enumerate(all_codes):
    api_code = code if len(code) >= 5 else code + "0"
    url = f"{BASE_URL}/fins/summary?code={api_code}"
    
    time.sleep(1.1) # 🛡️ 1.1秒の絶対待機
    
    try:
        r = session.get(url, timeout=10.0)
        if r.status_code == 200:
            res_data = r.json()
            # 💡 レスポンスのキー名（summary, statements, data, fins 等）のどれであっても自動キャッチ
            data = (
                res_data.get("summary") or 
                res_data.get("statements") or 
                res_data.get("data") or 
                res_data.get("fins") or []
            )
            
            if data:
                success_count += 1
                df = pd.DataFrame(data[-8:])
                for col in df.columns:
                    if col not in ['Date', 'DisclosedDate', 'LocalCode']:
                        df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)
                fundamentals_db[api_code] = df
                
        elif r.status_code == 429:
            print(f"⚠️ [429検知] サーバー負荷警報。10秒間、息を潜めます...", flush=True)
            time.sleep(10.0)
            
        elapsed = time.time() - start_time
        percent = ((i + 1) / total) * 100
        
        # 100銘柄ごと、または最初の数銘柄で状況を可視化
        if (i + 1) <= 5 or (i + 1) % 100 == 0:
            print(f"📡 [{i + 1}/{total}] ({percent:.1f}%) 銘柄: {api_code} 確保完了 (有効データ: {success_count}件, 経過: {elapsed:.1f}秒)", flush=True)
            
    except Exception as e:
        continue

# 3. ローカルDBとして保存
db_path = os.path.join(os.path.dirname(__file__), "fundamentals_db.pkl")
with open(db_path, "wb") as f:
    pickle.dump(fundamentals_db, f)

print(f"[{datetime.now()}] ✅ 全ミッション完了！ 総合計 {len(fundamentals_db)} 件の決算データを焼き付けました。")
