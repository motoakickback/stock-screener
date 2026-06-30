import pandas as pd
import numpy as np
from typing import List, Dict, Tuple, Optional

# ==========================================
# コア・ロジック（絶対遵守事項）
# ==========================================

def calculate_atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    """14日ATRを算出（J-Quants V2 カラム仕様）"""
    high = df['AdjH']
    low = df['AdjL']
    close_prev = df['AdjC'].shift(1)
    
    tr1 = high - low
    tr2 = (high - close_prev).abs()
    tr3 = (low - close_prev).abs()
    
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    return tr.rolling(window=period).mean()

def apply_core_risk_management(entry_price: float, support_price: float, atr: float) -> Optional[Dict]:
    """
    いかなるシグナル点灯時も自動計算されるリスク管理モジュール
    - SLはサポート直下に配置
    - 最大許容リスク：-8.0%以内
    - リスクリワード (RR) 最低1:2の確保
    """
    # ノイズ幅（ATR）を考慮してサポートの少し下にSLを置く（ここではATRの0.5倍とする）
    sl_price = support_price - (atr * 0.5)
    
    # 最大許容リスクのチェック（-8.0%以内）
    risk_pct = (entry_price - sl_price) / entry_price
    if risk_pct > 0.08 or risk_pct <= 0:
        return None # Drop（除外）
    
    risk_amount = entry_price - sl_price
    
    # RR = 1:2 となるようにTPを算出
    tp1_price = entry_price + (risk_amount * 2.0)
    tp2_price = entry_price + (risk_amount * 3.0) # TP2はRR 1:3に設定
    
    return {
        "Entry": entry_price,
        "TP1": tp1_price,
        "TP2": tp2_price,
        "SL": sl_price,
        "RR": "1:2+"
    }

# ==========================================
# モジュール1：裁定狙撃（ペア・スナイプ）エンジン
# ==========================================

def pair_snipe_engine(df_dict: Dict[str, pd.DataFrame], sector_pairs: List[Tuple[str, str]]) -> List[Dict]:
    """
    同一セクター内の資金の歪みを検知
    """
    results = []
    
    for ticker_a, ticker_b in sector_pairs:
        if ticker_a not in df_dict or ticker_b not in df_dict:
            continue
            
        df_a = df_dict[ticker_a].tail(60).copy()
        df_b = df_dict[ticker_b].tail(60).copy()
        
        if len(df_a) < 60 or len(df_b) < 60:
            continue
            
        # 過去60日間の相関係数
        corr = df_a['AdjC'].corr(df_b['AdjC'])
        if corr < 0.8:
            continue
            
        # スプレッド（価格比率）とその移動平均（20日）・標準偏差の算出
        spread = df_a['AdjC'] / df_b['AdjC']
        spread_mean = spread.rolling(20).mean()
        spread_std = spread.rolling(20).std()
        
        latest_spread = spread.iloc[-1]
        latest_mean = spread_mean.iloc[-1]
        latest_std = spread_std.iloc[-1]
        
        # +2σ超えの乖離検知
        if latest_spread > latest_mean + (2 * latest_std):
            results.append({
                "モジュール名(戦術)": "裁定狙撃 (ペア・スナイプ)",
                "銘柄コード": f"Short:{ticker_a} / Long:{ticker_b}",
                "エントリー価格/条件": f"スプレッド +2σ乖離 (Corr: {corr:.2f})",
                "TP1": "-", "TP2": "-", "SL": "-", "RR": "1:2+" # ペアトレード特有の管理のため表示はプレースホルダ
            })
            
    return results

# ==========================================
# モジュール2：深淵の底引き（アビス）検知エンジン
# ==========================================

def abyss_engine(ticker: str, df: pd.DataFrame) -> Optional[Dict]:
    """
    セリング・クライマックスの数学的証明
    """
    if len(df) < 50:
        return None
        
    # 指標計算
    df['ATR'] = calculate_atr(df, 14)
    
    # RSI(14)
    delta = df['AdjC'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
    rs = gain / loss
    df['RSI'] = 100 - (100 / (1 + rs))
    
    # Bollinger Bands (20, -3σ)
    df['SMA20'] = df['AdjC'].rolling(20).mean()
    df['STD20'] = df['AdjC'].rolling(20).std()
    df['BB_minus3'] = df['SMA20'] - (3 * df['STD20'])
    
    # Volume 50-day average
    df['Vol_SMA50'] = df['AdjVo'].rolling(50).mean()
    
    latest = df.iloc[-1]
    prev = df.iloc[-2]
    
    # ロジック判定
    cond1 = latest['RSI'] <= 20
    cond2 = (latest['AdjL'] <= latest['BB_minus3']) or (latest['AdjC'] <= latest['BB_minus3'])
    cond3 = latest['AdjVo'] >= latest['Vol_SMA50'] * 5.0
    
    # ローソク足形状判定
    body = abs(latest['AdjC'] - latest['AdjO'])
    lower_wick = min(latest['AdjO'], latest['AdjC']) - latest['AdjL']
    upper_wick = latest['AdjH'] - max(latest['AdjO'], latest['AdjC'])
    
    is_takuri = (lower_wick >= body * 2.0) and (lower_wick > upper_wick)
    
    prev_body_is_red = prev['AdjC'] < prev['AdjO']
    curr_body_is_green = latest['AdjC'] > latest['AdjO']
    is_engulfing = prev_body_is_red and curr_body_is_green and (latest['AdjC'] >= prev['AdjO']) and (latest['AdjO'] <= prev['AdjC'])
    
    cond4 = is_takuri or is_engulfing
    
    if cond1 and cond2 and cond3 and cond4:
        # リスク管理適用
        entry = latest['AdjC']
        support = latest['AdjL'] # 底値をサポートとする
        risk_data = apply_core_risk_management(entry, support, latest['ATR'])
        
        if risk_data:
            return {
                "モジュール名(戦術)": "深淵の底引き (アビス)",
                "銘柄コード": ticker,
                "エントリー価格/条件": f"{risk_data['Entry']:.1f} (RSI<=20, 出来高5倍急増)",
                "TP1": f"{risk_data['TP1']:.1f}",
                "TP2": f"{risk_data['TP2']:.1f}",
                "SL": f"{risk_data['SL']:.1f}",
                "RR": risk_data['RR']
            }
    return None

# ==========================================
# モジュール3：事後確信（ポスト・アサルト）検知エンジン
# ==========================================

def post_assault_engine(ticker: str, df: pd.DataFrame, earnings_dates: List[str]) -> Optional[Dict]:
    """
    決算直後の機関投資家の本気の資金流入にのみ追従
    """
    if len(df) < 60:
        return None
        
    df['ATR'] = calculate_atr(df, 14)
    latest = df.iloc[-1]
    prev = df.iloc[-2]
    
    latest_date_str = latest.name.strftime('%Y-%m-%d') if isinstance(latest.name, pd.Timestamp) else str(latest['Date'])
    prev_date_str = prev.name.strftime('%Y-%m-%d') if isinstance(prev.name, pd.Timestamp) else str(prev['Date'])
    
    # 決算発表判定
    cond1 = (latest_date_str in earnings_dates) or (prev_date_str in earnings_dates)
    
    # Gap Up判定 (+5%以上)
    gap_pct = (latest['AdjO'] - prev['AdjC']) / prev['AdjC']
    cond2 = gap_pct >= 0.05
    
    # Volume判定 (過去60日間で最大)
    vol_max_60 = df['AdjVo'].tail(60).max()
    cond3 = latest['AdjVo'] == vol_max_60
    
    # 大陽線判定 (ストップ高含む)
    cond4 = latest['AdjC'] > latest['AdjO']
    
    if cond1 and cond2 and cond3 and cond4:
        # エントリーゾーン算出（高値から半値戻し）
        entry_high = latest['AdjH']
        entry_low_zone = (latest['AdjH'] + latest['AdjL']) / 2.0
        entry_target = entry_low_zone # 押し目で待つ
        
        support = latest['AdjL'] # 今日の安値を割れたら撤退
        risk_data = apply_core_risk_management(entry_target, support, latest['ATR'])
        
        if risk_data:
            return {
                "モジュール名(戦術)": "事後確信 (ポスト・アサルト)",
                "銘柄コード": ticker,
                "エントリー価格/条件": f"{entry_target:.1f} - {entry_high:.1f} (半値戻し待機)",
                "TP1": f"{risk_data['TP1']:.1f}",
                "TP2": f"{risk_data['TP2']:.1f}",
                "SL": f"{risk_data['SL']:.1f}",
                "RR": risk_data['RR']
            }
    return None

# ==========================================
# 出力フォーマッター
# ==========================================

def format_to_markdown(results: List[Dict]) -> str:
    """検知結果をMarkdown Table形式で出力"""
    if not results:
        return "検知された銘柄はありません。システムは待機状態を維持します。"
        
    headers = ["モジュール名(戦術)", "銘柄コード", "エントリー価格/条件", "TP1", "TP2", "SL", "RR"]
    md_table = "| " + " | ".join(headers) + " |\n"
    md_table += "|-" + "-|-".join(["-" * len(h) for h in headers]) + "-|\n"
    
    for row in results:
        md_table += "| " + " | ".join(str(row.get(h, "")) for h in headers) + " |\n"
        
    return md_table

# ==========================================
# メイン実行ブロック（シミュレーション・モック）
# ==========================================
if __name__ == "__main__":
    # 実運用時は、J-Quants API V2 /v2/equities/bars/daily 等からデータを取得しDataFrameに変換します。
    # 決算発表日は /v2/equities/earnings-calendar から取得します。
    print("Project AEGIS Screening Started...\n")
    
    # モックデータ生成（動作確認用）
    # ... データ取得フェーズ ...
    
    # 出力例（実データが注入された場合のフォーマッター呼び出し結果）
    # print(format_to_markdown(final_results))
