import os
import requests
from datetime import datetime
import json

# GitHub Secrets에서 환경 변수 불러오기
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

# --- 설정 구간 ---
DISCREPANCY_THRESHOLD = -3.0  # 알림 기준 괴리율 (%)
MIN_VOLUME = 5000            # 최소 거래량 (유동성 보장)
# -----------------

def send_telegram(message):
    if not TELEGRAM_TOKEN or not CHAT_ID:
        print("에러: TELEGRAM_TOKEN 또는 CHAT_ID 설정이 필요합니다.")
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {"chat_id": CHAT_ID, "text": message, "parse_mode": "Markdown"}
    try:
        requests.post(url, json=payload).raise_for_status()
    except Exception as e:
        print(f"텔레그램 전송 에러: {e}")

def fetch_realtime_etf_data():
    """
    네이버 금융 실시간 ETF API에서 데이터를 가져옵니다.
    """
    url = "https://finance.naver.com/api/sise/etfItemList.nhn"
    try:
        response = requests.get(url)
        data = response.json()
        items = data.get("result", {}).get("etfItemList", [])
        
        results = []
        today = datetime.now().strftime('%Y-%m-%d')
        
        for item in items:
            name = item.get("itemname")
            now_val = item.get("nowVal")    # 현재가
            nav = item.get("nav")          # 순자산가치(iNAV)
            volume = item.get("quant")     # 거래량
            
            if not nav or nav == 0: continue
            
            # 괴리율 계산: ((현재가 - iNAV) / iNAV) * 100
            discrepancy = round(((now_val - nav) / nav) * 100, 2)
            
            # 3번 기능: 스마트 필터링 (거래량 및 괴리율 기준)
            if discrepancy <= DISCREPANCY_THRESHOLD and volume >= MIN_VOLUME:
                results.append({
                    "name": name,
                    "rate": discrepancy,
                    "price": now_val,
                    "nav": nav,
                    "volume": volume,
                    "date": today
                })
        return results
    except Exception as e:
        print(f"데이터 수집 에러: {e}")
        return []

def main():
    now_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    print(f"[{now_str}] 실시간 ETF 모니터링 시작 (기준: {DISCREPANCY_THRESHOLD}%, 거래량: {MIN_VOLUME}주)")
    
    # 알림 내역 로드 (중복 방지)
    history_file = "notified_disclosures.json"
    notified_list = []
    if os.path.exists(history_file):
        with open(history_file, "r", encoding="utf-8") as f:
            try: notified_list = json.load(f)
            except: notified_list = []

    items = fetch_realtime_etf_data()
    new_notified = False

    for item in items:
        # 알림 메시지 구성 (2번 기능 예고: 네이버 링크 포함)
        item_id = f"{item['name']}_{item['date']}"
        
        if item_id not in notified_list:
            msg = (
                f"🚨 *[ETF 실시간 저평가 알림]*\n\n"
                f"📌 *종목:* {item['name']}\n"
                f"📉 *괴리율:* `{item['rate']}%` (저평가)\n"
                f"💰 *현재가:* {item['price']:,}원\n"
                f"💎 *iNAV:* {item['nav']:,}원\n"
                f"📊 *거래량:* {item['volume']:,}주\n\n"
                f"⚠️ 거래량이 동반된 확실한 저평가 상태입니다."
            )
            send_telegram(msg)
            print(f"알림 발송: {item['name']} ({item['rate']}%)")
            notified_list.append(item_id)
            new_notified = True
    
    if new_notified:
        # 최근 100개 알림만 유지하도록 관리 (파일 크기 조절)
        with open(history_file, "w", encoding="utf-8") as f:
            json.dump(notified_list[-100:], f, ensure_ascii=False, indent=2)
        print("기록 업데이트 완료.")
    else:
        print("조건에 맞는 종목이 없습니다.")

if __name__ == "__main__":
    main()
