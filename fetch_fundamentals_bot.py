import time
import requests
import pandas as pd
import pickle
import os
from datetime import datetime
import gzip

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
                df = pd.DataFrame(data[-40:])
                for col in df.columns:
                    if col not in ['Date', 'DisclosedDate', 'LocalCode']:
                        # 🚨 猛毒であった .fillna(0) を完全排除！ 欠損値(NaN)はそのまま保持する
                        df[col] = pd.to_numeric(df[col], errors='coerce')
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

# 3. ローカルDBとして保存（🚨 gzip圧縮化）
db_path = os.path.join(os.path.dirname(__file__), "fundamentals_db.pkl.gz")
with gzip.open(db_path, "wb") as f:
    pickle.dump(fundamentals_db, f)

print(f"[{datetime.now()}] ✅ 全ミッション完了！ 総合計 {len(fundamentals_db)} 件の決算データを圧縮して焼き付けました。")

# ==========================================
# 📈 4. 株価データ（過去約400日分）の一括収集
# ==========================================
from datetime import timedelta

print("\n--- 📈 株価データ（日足）一括収集開始 ---")
prices_db = {}
base_date_jst = datetime.utcnow() + timedelta(hours=9)
days_to_fetch = 400
fetched_days = 0

for i in range(days_to_fetch):
    target_date = base_date_jst - timedelta(days=i)
    # 土日は市場休場のためスキップ
    if target_date.weekday() >= 5:
        continue
        
    dt_str = target_date.strftime('%Y%m%d')
    # 🎯 指定した1日分の全銘柄データを一括で返すAPIを使用
    url = f"{BASE_URL}/equities/bars/daily?date={dt_str}"
    
    time.sleep(1.1) # 🛡️ 1.1秒の絶対待機
    
    try:
        r = session.get(url, timeout=10.0)
        if r.status_code == 200:
            res_json = r.json()
            data = (
                res_json.get("daily_quotes") or 
                res_json.get("data") or 
                res_json.get("results") or []
            )
            if data:
                prices_db[dt_str] = data
                fetched_days += 1
                
                if fetched_days % 20 == 0:
                    print(f"📡 株価進捗: {fetched_days} 営業日分を取得完了...", flush=True)
        elif r.status_code == 429:
            print(f"⚠️ [429検知] 株価取得中にサーバー負荷警報。10秒間待機...", flush=True)
            time.sleep(10.0)
    except Exception as e:
        continue

# 🚨 株価データもgzip圧縮化して保存
prices_db_path = os.path.join(os.path.dirname(__file__), "prices_db.pkl.gz")
with gzip.open(prices_db_path, "wb") as f:
    pickle.dump(prices_db, f)

print(f"[{datetime.now()}] ✅ 株価データ全ミッション完了！ {fetched_days}営業日分の株価データを圧縮して焼き付けました。")

# ==========================================
# 2. 1.1秒の絶対防弾行進で全件取得（ファンダメンタルズ ＆ 決算発表予定日）
# ==========================================
fundamentals_db = {} # 財務データを保持する辞書
earnings_db = {}     # 決算発表予定日データを保持する辞書
total = len(all_codes)
start_time = time.time()
success_count = 0      # 財務データの取得成功数
earn_success_count = 0 # 決算予定日の取得成功数

print(f"🚀 全 {total} 銘柄のファンダメンタルズおよび決算発表予定日の強襲索敵を開始します...")

for i, code in enumerate(all_codes):
    # APIの仕様に合わせ、4桁コードの場合は末尾に0を追加して5桁のAPIコードにする
    api_code = code if len(code) >= 5 else code + "0"
    
    # ファンダメンタルズ取得APIのエンドポイント
    url_fins = f"{BASE_URL}/fins/summary?code={api_code}"
    # 2026年8月3日リリースの新API：決算発表予定日（全上場銘柄対象）のエンドポイント
    url_earn = f"{BASE_URL}/fins/earnings-date?code={api_code}"
    
    time.sleep(1.1) # 🛡️ サーバー負荷・API制限を回避するための1.1秒の絶対待機
    
    try:
        # 1. 財務情報の取得処理
        r = session.get(url_fins, timeout=10.0)
        if r.status_code == 200:
            res_data = r.json()
            # 取得したJSONから財務データを抽出（複数のキー名候補に安全に対応）
            data = (
                res_data.get("summary") or 
                res_data.get("statements") or 
                res_data.get("data") or 
                res_data.get("fins") or []
            )
            if data:
                success_count += 1
                # 直近40件のデータをDataFrame化
                df = pd.DataFrame(data[-40:])
                for col in df.columns:
                    # 日付系の列以外は数値型へ変換（エラー時はNaNとしてそのまま保持し、欠損値を推測でゼロ埋めしない）
                    if col not in ['Date', 'DisclosedDate', 'LocalCode']:
                        df[col] = pd.to_numeric(df[col], errors='coerce')
                # APIコードをキーとしてDB用辞書へ格納
                fundamentals_db[api_code] = df
                
        # 2. 決算発表予定日の取得処理 (/v2/fins/earnings-date)
        r_earn = session.get(url_earn, timeout=10.0)
        if r_earn.status_code == 200:
            res_earn_json = r_earn.json()
            # J-Quants V2の仕様に基づき、"data"キーの中身を配列として取得
            earn_data = res_earn_json.get("data", [])
            if earn_data:
                earn_success_count += 1
                # アプリ側で4桁・5桁のどちらのコードからでも参照できるように両方をキーとして格納
                earnings_db[api_code] = earn_data
                earnings_db[api_code[:4]] = earn_data
                
        # サーバーからの制限（429 Too Many Requestsエラー）を受けた場合の待機・再開処理
        elif r.status_code == 429 or r_earn.status_code == 429:
            print(f"⚠️ [429検知] サーバー負荷警報。10秒間、息を潜めます...", flush=True)
            time.sleep(10.0)
            
    except Exception as e:
        # 通信エラー等が発生した場合はスキップして次の銘柄へ移行
        continue

    elapsed = time.time() - start_time
    percent = ((i + 1) / total) * 100
    
    # 進行状況の出力（最初の5件、または100件ごとにコンソールへ出力）
    if (i + 1) <= 5 or (i + 1) % 100 == 0:
        print(f"📡 [{i + 1}/{total}] ({percent:.1f}%) 銘柄: {api_code} 確保完了 (財務: {success_count}件, 予定日: {earn_success_count}件, 経過: {elapsed:.1f}秒)", flush=True)

# 3. ローカルDBとして保存（🚨 ディスク容量とロード速度最適化のためgzip圧縮化）
db_path = os.path.join(os.path.dirname(__file__), "fundamentals_db.pkl.gz")
with gzip.open(db_path, "wb") as f:
    pickle.dump(fundamentals_db, f)

earn_db_path = os.path.join(os.path.dirname(__file__), "earnings_db.pkl.gz")
with gzip.open(earn_db_path, "wb") as f:
    pickle.dump(earnings_db, f)

print(f"[{datetime.now()}] ✅ 全ミッション完了！ 総合計 財務:{len(fundamentals_db)}件, 予定日:{len(earnings_db)}件 のデータを圧縮して焼き付けました。")
