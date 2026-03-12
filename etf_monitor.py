import os
import requests
from datetime import datetime, timedelta
import json

# GitHub Secrets에서 환경 변수 불러오기
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

# --- 설정 구간 ---
DISCREPANCY_THRESHOLD = -3.0  # 알림 기준 괴리율 (%)
MIN_VOLUME = 5000            # 최소 거래량 (유동성 보장)
RETENTION_DAYS = 30          # 알림 기록 보관 기간 (일)
# -----------------

def send_telegram(message):
    if not TELEGRAM_TOKEN or not CHAT_ID:
        print("에러: TELEGRAM_TOKEN 또는 CHAT_ID 설정이 필요합니다.")
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {"chat_id": CHAT_ID, "text": message, "parse_mode": "Markdown", "disable_web_page_preview": False}
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
            code = item.get("itemcode")     # 종목 코드 (6자리)
            now_val = item.get("nowVal")    # 현재가
            nav = item.get("nav")          # 순자산가치(iNAV)
            volume = item.get("quant")     # 거래량
            
            if not nav or nav == 0: continue
            
            # 괴리율 계산
            discrepancy = round(((now_val - nav) / nav) * 100, 2)
            
            # 스마트 필터링
            if discrepancy <= DISCREPANCY_THRESHOLD and volume >= MIN_VOLUME:
                results.append({
                    "name": name,
                    "code": code,
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

def is_market_open():
    """
    한국 시간(KST) 기준으로 장 운영 시간인지 확인합니다.
    평일 08:50 ~ 16:00 (장 시작 전 호가 및 장후 정리 시간 포함)
    """
    # GitHub Actions 서버는 UTC 기준이므로 한국 시간(UTC+9)으로 변환
    now_utc = datetime.utcnow()
    now_kst = now_utc + timedelta(hours=9)
    
    # 요일 확인 (0:월, 1:화, 2:수, 3:목, 4:금, 5:토, 6:일)
    weekday = now_kst.weekday()
    if weekday > 4:  # 토, 일 제외
        return False, "주말입니다."
    
    # 시간 확인 (HHMM 형식)
    now_time = int(now_kst.strftime("%H%M"))
    if not (850 <= now_time <= 1600):
        return False, f"장외 시간입니다. (현재 KST {now_kst.strftime('%H:%M')})"
    
    return True, "장 운영 시간입니다."

def main():
    # 0. 장 운영 시간 체크
    is_open, reason = is_market_open()
    if not is_open:
        print(f"[-] 모니터링을 건너뜁니다: {reason}")
        return

    now = datetime.now()
    now_str = now.strftime('%Y-%m-%d %H:%M:%S')
    today_str = now.strftime('%Y-%m-%d')
    print(f"[{now_str}] ETF 모니터링 가동 (조건: {DISCREPANCY_THRESHOLD}%, {MIN_VOLUME}주)")
    
    # 4번 기능: 알림 내역 로드 및 30일 경과 데이터 삭제
    history_file = "notified_disclosures.json"
    history_data = {} # { "종목명_날짜": "기록일자(YYYY-MM-DD)" }
    
    if os.path.exists(history_file):
        with open(history_file, "r", encoding="utf-8") as f:
            try: history_data = json.load(f)
            except: history_data = {}

    # 유효 기간 계산 (30일 전)
    cutoff_date = (now - timedelta(days=RETENTION_DAYS)).strftime('%Y-%m-%d')
    
    # 오래된 데이터 필터링
    filtered_history = {k: v for k, v in history_data.items() if v >= cutoff_date}
    if len(history_data) != len(filtered_history):
        print(f"기록 정리: {len(history_data) - len(filtered_history)}건의 오래된 기록이 삭제되었습니다.")

    items = fetch_realtime_etf_data()
    new_notified = False

    for item in items:
        item_id = f"{item['name']}_{item['date']}"
        
        if item_id not in filtered_history:
            # 2번 기능: 네이버 증권 상세 페이지 링크 생성
            naver_link = f"https://m.stock.naver.com/domestic/stock/{item['code']}/total"
            
            msg = (
                f"🚨 *[ETF 실시간 저평가 알림]*\n\n"
                f"📌 *종목:* {item['name']} ({item['code']})\n"
                f"📉 *괴리율:* `{item['rate']}%` (저평가)\n"
                f"💰 *현재가:* {item['price']:,}원\n"
                f"💎 *iNAV:* {item['nav']:,}원\n"
                f"📊 *거래량:* {item['volume']:,}주\n\n"
                f"🔗 [네이버 증권에서 확인하기]({naver_link})\n"
                f"⚠️ 거래량이 동반된 확실한 저평가 상태입니다."
            )
            send_telegram(msg)
            print(f"알림 발송: {item['name']} ({item['rate']}%)")
            filtered_history[item_id] = item['date']
            new_notified = True
    
    # 변경사항 저장
    if new_notified or len(history_data) != len(filtered_history):
        with open(history_file, "w", encoding="utf-8") as f:
            json.dump(filtered_history, f, ensure_ascii=False, indent=2)
        print("기록 업데이트 완료.")
    else:
        print("조건에 맞는 신규 종목이 없습니다.")

if __name__ == "__main__":
    main()
