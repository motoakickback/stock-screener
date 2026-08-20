import time
import requests
import pandas as pd
import pickle
import os
from datetime import datetime

# ==========================================
# ⚙️ J-Quants V2 API 設定（APIキー方式・完全修正版）
# ==========================================
JQUANTS_API_KEY = os.getenv("JQUANTS_API_KEY", "").strip()
BASE_URL = "https://api.jquants.com/v2"

print(f"[{datetime.now()}] 🌙 兵站部隊（ファンダメンタルズ収集・V2）出撃...")

if not JQUANTS_API_KEY:
    print("❌ エラー: JQUANTS_API_KEY が設定されていません。GitHub Secretsを確認してください。")
    exit(1)

headers = {'x-api-key': JQUANTS_API_KEY}
session = requests.Session()
session.headers.update(headers)

# 1. 全銘柄コードの取得（V2正しいエンドポイント: /v2/equities/master）
try:
    print("📡 J-Quants V2 サーバーへ接続中（銘柄マスター取得）...")
    r_info = session.get(f"{BASE_URL}/equities/master", timeout=10.0)
    r_info.raise_for_status()
    
    res_json = r_info.json()
    # V2のレスポンス構造（equities または data キーに対応）
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

# 2. 1.1秒の絶対防弾行進で全件取得
fundamentals_db = {}
total = len(all_codes)

for i, code in enumerate(all_codes):
    api_code = code if len(code) >= 5 else code + "0"
    url = f"{BASE_URL}/fins/summary?code={api_code}"
    
    time.sleep(1.1) # 🛡️ 1.1秒の絶対待機
    
    try:
        r = session.get(url, timeout=10.0)
        if r.status_code == 200:
            data = r.json().get("summary", [])
            if data:
                df = pd.DataFrame(data[-8:])
                for col in df.columns:
                    if col not in ['Date', 'DisclosedDate', 'LocalCode']:
                        df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)
                fundamentals_db[api_code] = df
        elif r.status_code == 429:
            print(f"⚠️ 429エラー検知。5秒待機します...")
            time.sleep(5.0)
            
        if (i + 1) % 100 == 0:
            print(f"📡 進捗: {i + 1} / {total} 銘柄完了...")
            
    except Exception:
        continue

# 3. ローカルDBとして保存
db_path = os.path.join(os.path.dirname(__file__), "fundamentals_db.pkl")
with open(db_path, "wb") as f:
    pickle.dump(fundamentals_db, f)

print(f"[{datetime.now()}] ✅ 全ミッション完了！ {len(fundamentals_db)} 件の決算データを焼き付けました。")
