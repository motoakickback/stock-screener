import time
import requests
import pandas as pd
import pickle
import os
from datetime import datetime

# ==========================================
# ⚙️ J-Quants API 設定（GitHub Secrets完全連動版）
# ==========================================
# GitHub Actionsから渡された環境変数を確実に取得する
JQUANTS_MAIL = os.getenv("JQUANTS_MAIL", "").strip()
JQUANTS_PASS = os.getenv("JQUANTS_PASS", "").strip()
BASE_URL = "https://api.jquants.com/v2"

print(f"[{datetime.now()}] 🌙 兵站部隊（ファンダメンタルズ収集）出撃...")

if not JQUANTS_MAIL or not JQUANTS_PASS:
    print("❌ エラー: 認証情報が設定されていません。GitHub Secretsの「JQUANTS_MAIL」「JQUANTS_PASS」を確認してください。")
    print(f"DEBUG: MAIL length={len(JQUANTS_MAIL)}, PASS length={len(JQUANTS_PASS)}")
    exit(1)

# 1. トークン取得
try:
    print(f"📡 認証開始... ユーザー: {JQUANTS_MAIL[:3]}***")
    r_refresh = requests.post(f"{BASE_URL}/mailauth", json={"mailaddress": JQUANTS_MAIL, "password": JQUANTS_PASS})
    r_refresh.raise_for_status() # エラーがあればここで落とす
    refresh_token = r_refresh.json()["refreshToken"]
    
    r_id = requests.post(f"{BASE_URL}/token/auth_refresh?refreshToken={refresh_token}")
    r_id.raise_for_status()
    id_token = r_id.json()["idToken"]
    
    headers = {'Authorization': f'Bearer {id_token}'}
    print("✅ APIトークン取得成功！")
except Exception as e:
    print(f"❌ トークン取得失敗: {e}")
    # さらに詳しいエラー理由を出力
    if 'r_refresh' in locals() and hasattr(r_refresh, 'text'):
        print(f"📝 サーバー応答: {r_refresh.text}")
    exit(1)

session = requests.Session()
session.headers.update(headers)

# 2. 全銘柄コードの取得
try:
    r_info = session.get(f"{BASE_URL}/listed/info")
    r_info.raise_for_status()
    info_data = r_info.json().get("info", [])
    all_codes = [str(d["Code"]) for d in info_data]
    print(f"✅ 上場銘柄 {len(all_codes)} 件のリストを取得")
except Exception as e:
    print(f"❌ 銘柄リスト取得失敗: {e}")
    exit(1)

# 3. 1.1秒の絶対防弾行進で全件取得
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

# 4. ローカルDBとして保存
db_path = os.path.join(os.path.dirname(__file__), "fundamentals_db.pkl")
with open(db_path, "wb") as f:
    pickle.dump(fundamentals_db, f)

print(f"[{datetime.now()}] ✅ 全ミッション完了！ {len(fundamentals_db)} 件の決算データを焼き付けました。")
