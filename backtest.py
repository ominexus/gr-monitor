import json
import os
import pandas as pd
import yfinance as yf
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional
from etf_monitor import fetch_realtime_etf_data, US_WATCH_LIST

HISTORY_FILE = "notified_disclosures.json"

def get_name_to_ticker_map() -> Dict[str, str]:
    """한국 ETF 이름과 미국 티커를 yfinance 코드(예: 069500.KS, TSLA)로 매핑합니다."""
    mapping = {}
    
    # 1. 한국 ETF 데이터 가져와 매핑 (이름 -> 코드.KS)
    print("[*] 한국 ETF 이름-코드 매핑 데이터 수집 중...")
    etf_list = fetch_realtime_etf_data()
    for item in etf_list:
        mapping[item['name']] = f"{item['code']}.KS"
        
    # 2. 미국 주식 매핑 (티커 -> 티커)
    for symbol in US_WATCH_LIST:
        mapping[symbol] = symbol
        
    return mapping

def load_history() -> List[Dict[str, str]]:
    """notified_disclosures.json 파일을 읽어 분석 대상을 추출합니다."""
    if not os.path.exists(HISTORY_FILE):
        print(f"[-] {HISTORY_FILE} 파일이 없습니다.")
        return []
        
    try:
        with open(HISTORY_FILE, "r", encoding="utf-8") as f:
            history = json.load(f)
    except Exception as e:
        print(f"[-] 히스토리 파일 로드 실패: {e}")
        return []
        
    results = []
    for key, date_str in history.items():
        if key.startswith("SUMMARY_"):
            continue
            
        # key format: "Name_YYYY-MM-DD"
        # name에 '_'가 포함될 수 있으므로 오른쪽에서 첫 번째 '_'를 기준으로 분리
        if "_" not in key:
            continue
            
        name = key.rsplit("_", 1)[0]
        results.append({
            "name": name,
            "date": date_str
        })
        
    return results

def run_backtest():
    """백테스트 메인 로직"""
    history = load_history()
    if not history:
        print("[-] 분석할 알림 이력이 없습니다.")
        return
        
    name_to_ticker = get_name_to_ticker_map()
    
    backtest_data = []
    
    print(f"[*] 총 {len(history)}건의 알림 이력 분석 시작...")
    
    for entry in history:
        name = entry['name']
        alert_date = entry['date']
        ticker_symbol = name_to_ticker.get(name)
        
        if not ticker_symbol:
            # 매핑에 없는 경우(예: 수동 추가 혹은 이름 변경) 티커 자체라고 가정해봄
            ticker_symbol = name
            
        try:
            # 알림 당일 및 이후 주가 조회를 위해 시작일을 조금 앞당김
            start_date = datetime.strptime(alert_date, '%Y-%m-%d')
            # 넉넉하게 오늘까지 데이터를 가져옴
            ticker = yf.Ticker(ticker_symbol)
            df = ticker.history(start=start_date, end=datetime.now() + timedelta(days=1))
            
            if df.empty:
                print(f"  [-] {name} ({ticker_symbol}) 데이터를 찾을 수 없습니다.")
                continue
                
            # 알림 발생 당일(혹은 가장 가까운 개장일) 종가 찾기
            entry_price = df.iloc[0]['Close']
            actual_entry_date = df.index[0].strftime('%Y-%m-%d')
            
            row = {
                "Alert Name": name,
                "Ticker": ticker_symbol,
                "Alert Date": alert_date,
                "Actual Entry Date": actual_entry_date,
                "Entry Price": round(entry_price, 2)
            }
            
            # T+N일 수익률 계산 (T+1, T+3, T+5, T+10, T+20, T+60)
            intervals = [1, 3, 5, 10, 20, 60]
            for n in intervals:
                if len(df) > n:
                    future_price = df.iloc[n]['Close']
                    ret = round(((future_price - entry_price) / entry_price) * 100, 2)
                    row[f"T+{n} (%)"] = ret
                else:
                    row[f"T+{n} (%)"] = None
                    
            backtest_data.append(row)
            print(f"  [+] {name} ({alert_date}) 분석 완료")
            
        except Exception as e:
            print(f"  [-] {name} 분석 에러: {e}")
            
    if not backtest_data:
        print("[-] 유효한 분석 데이터가 생성되지 않았습니다.")
        return
        
    # 결과 요약 (Pandas DataFrame)
    results_df = pd.DataFrame(backtest_data)
    
    print("\n" + "="*80)
    print("📈 [ETF 모니터 알림 성과 백테스트 결과]")
    print("="*80)
    print(results_df.to_string(index=False))
    print("="*80)
    
    # CSV 저장
    csv_file = "backtest_results.csv"
    results_df.to_csv(csv_file, index=False, encoding='utf-8-sig')
    print(f"\n[*] 상세 결과가 {csv_file} 파일로 저장되었습니다.")

if __name__ == "__main__":
    run_backtest()
