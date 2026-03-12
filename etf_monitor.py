import os
import requests
from datetime import datetime, timedelta
import json

# GitHub Secrets에서 환경 변수 불러오기
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

# --- 설정 구간 ---
DISCREPANCY_THRESHOLD = -3.0  # 개별 알림 기준 괴리율 (%)
MIN_VOLUME = 5000            # 최소 거래량 (유동성 보장)
RETENTION_DAYS = 30          # 알림 기록 보관 기간 (일)
# -----------------

def send_telegram(message):
    if not TELEGRAM_TOKEN or not CHAT_ID:
        print("에러: TELEGRAM_TOKEN 또는 CHAT_ID 설정이 필요합니다.")
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {"chat_id": CHAT_ID, "text": message, "parse_mode": "Markdown", "disable_web_page_preview": True}
    try:
        requests.post(url, json=payload).raise_for_status()
    except Exception as e:
        print(f"텔레그램 전송 에러: {e}")

def fetch_realtime_etf_data():
    url = "https://finance.naver.com/api/sise/etfItemList.nhn"
    try:
        response = requests.get(url)
        data = response.json()
        items = data.get("result", {}).get("etfItemList", [])
        
        results = []
        today = datetime.now().strftime('%Y-%m-%d')
        
        for item in items:
            name = item.get("itemname")
            code = item.get("itemcode")
            now_val = item.get("nowVal")
            nav = item.get("nav")
            volume = item.get("quant")
            
            if not nav or nav == 0: continue
            
            discrepancy = round(((now_val - nav) / nav) * 100, 2)
            
            # 모든 유효 거래량 종목 수집 (이후 필터링)
            if volume >= MIN_VOLUME:
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
    now_utc = datetime.utcnow()
    now_kst = now_utc + timedelta(hours=9)
    weekday = now_kst.weekday()
    if weekday > 4: return False, "주말", 0
    now_time = int(now_kst.strftime("%H%M"))
    if not (850 <= now_time <= 1600):
        return False, "장외 시간", now_time
    return True, "운영 시간", now_time

def main():
    is_open, reason, kst_time = is_market_open()
    if not is_open:
        print(f"[-] 모니터링 건너뜀: {reason}")
        return

    now = datetime.now()
    today_str = now.strftime('%Y-%m-%d')
    history_file = "notified_disclosures.json"
    history_data = {}
    
    if os.path.exists(history_file):
        with open(history_file, "r", encoding="utf-8") as f:
            try: history_data = json.load(f)
            except: history_data = {}

    cutoff_date = (now - timedelta(days=RETENTION_DAYS)).strftime('%Y-%m-%d')
    filtered_history = {k: v for k, v in history_data.items() if v >= cutoff_date}

    all_items = fetch_realtime_etf_data()
    new_notified = False

    # 1. 개별 실시간 알림 (-3.0% 이하)
    for item in all_items:
        item_id = f"{item['name']}_{item['date']}"
        if item['rate'] <= DISCREPANCY_THRESHOLD and item_id not in filtered_history:
            naver_link = f"https://m.stock.naver.com/domestic/stock/{item['code']}/total"
            msg = (
                f"🚨 *[ETF 실시간 저평가 알림]*\n\n"
                f"📌 *종목:* {item['name']} ({item['code']})\n"
                f"📉 *괴리율:* `{item['rate']}%` (저평가)\n"
                f"💰 *현재가:* {item['price']:,}원\n"
                f"📊 *거래량:* {item['volume']:,}주\n\n"
                f"🔗 [네이버 증권 바로가기]({naver_link})"
            )
            send_telegram(msg)
            filtered_history[item_id] = item['date']
            new_notified = True

    # 2. 장 마감 요약 브리핑 (15:40 ~ 15:55 사이 실행 시)
    summary_id = f"SUMMARY_{today_str}"
    if 1540 <= kst_time <= 1555 and summary_id not in filtered_history:
        # 괴리율이 낮은(가장 저평가된) 순으로 정렬
        sorted_items = sorted(all_items, key=lambda x: x['rate'])[:5]
        
        if sorted_items:
            summary_msg = f"📝 *[장 마감 ETF 저평가 요약]*\n📅 {today_str}\n\n"
            for i, item in enumerate(sorted_items, 1):
                summary_msg += f"{i}. *{item['name']}*\n    └ 괴리율: `{item['rate']}%` | 거래량: {item['volume']:,}주\n"
            
            summary_msg += "\n*오늘 하루도 수고하셨습니다!*"
            send_telegram(summary_msg)
            filtered_history[summary_id] = today_str
            new_notified = True
            print("장 마감 요약 브리핑 발송 완료.")

    if new_notified or len(history_data) != len(filtered_history):
        with open(history_file, "w", encoding="utf-8") as f:
            json.dump(filtered_history, f, ensure_ascii=False, indent=2)
        print("기록 업데이트 완료.")

if __name__ == "__main__":
    main()
