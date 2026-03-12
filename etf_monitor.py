import os
import requests
from datetime import datetime
import json

# GitHub Secrets에서 환경 변수 불러오기
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

def send_telegram(message):
    if not TELEGRAM_TOKEN or not CHAT_ID:
        print("에러: TELEGRAM_TOKEN 또는 CHAT_ID 환경 변수가 설정되지 않았습니다.")
        return
    
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {
        "chat_id": CHAT_ID, 
        "text": message, 
        "parse_mode": "Markdown"
    }
    try:
        response = requests.post(url, json=payload)
        response.raise_for_status()
    except Exception as e:
        print(f"텔레그램 전송 중 에러 발생: {e}")

def fetch_kind_etf_data():
    """
    KIND(한국거래소) 공시 데이터를 검색하는 로직 (기본 예시)
    실제 운영 시에는 KIND의 검색 API 또는 크롤링을 통해 데이터를 수집합니다.
    """
    # 3월 실제 발생 사례 데이터 (테스트용)
    # 실제 연동 시 requests를 사용하여 KIND 페이지의 JSON 데이터를 파싱하도록 고도화 가능합니다.
    mock_data = [
        {"name": "ACE 글로벌AI맞춤형반도체", "rate": -3.54, "date": "2026-03-09"},
        {"name": "KIWOOM 글로벌AI반도체", "rate": -2.80, "date": "2026-03-09"},
        {"name": "SOL 미국AI반도체칩메이커", "rate": -2.15, "date": "2026-03-12"}
    ]
    return mock_data

def main():
    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    print(f"[{now}] ETF 괴리율 모니터링 시작...")
    
    items = fetch_kind_etf_data()
    found_any = False

    for item in items:
        # 마이너스 괴리율만 필터링 (예: -1.0% 이하)
        if item['rate'] <= -1.0:
            msg = (
                f"📉 *[ETF 마이너스 괴리율 알림]*\n\n"
                f"📌 *종목명:* {item['name']}\n"
                f"📊 *괴리율:* `{item['rate']}%` (저평가)\n"
                f"📅 *발생일:* {item['date']}\n\n"
                f"⚠️ 실제 가치(iNAV)보다 저렴하게 거래 중입니다.\n"
                f"현지 시장의 급등락을 확인하세요."
            )
            send_telegram(msg)
            print(f"알림 발송: {item['name']} ({item['rate']}%)")
            found_any = True
    
    if not found_any:
        print("조건에 맞는 마이너스 괴리율 종목이 없습니다.")

if __name__ == "__main__":
    main()
