import os
import requests
from datetime import datetime, timedelta
import json

# GitHub Secrets에서 환경 변수 불러오기
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

# --- 설정 구간 ---
NORMAL_THRESHOLD = -3.0      # 평시 알림 기준 괴리율 (%)
OPENING_THRESHOLD = -5.0     # 시초가 특별 감시 기준 괴리율 (%)
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

    # 1. 실시간 알림 로직 (시초가 모드 vs 일반 모드)
    # 시초가 특별 감시 (09:00 ~ 09:10)
    is_opening_session = (900 <= kst_time <= 910)
    current_threshold = OPENING_THRESHOLD if is_opening_session else NORMAL_THRESHOLD
    alert_prefix = "⚡ *[시초가 괴리율 폭탄 감지]*" if is_opening_session else "🚨 *[ETF 실시간 저평가 알림]*"

    for item in all_items:
        item_id = f"{item['name']}_{item['date']}"
        # 해당 시간대의 기준(Threshold)에 따라 필터링
        if item['rate'] <= current_threshold and item_id not in filtered_history:
            naver_link = f"https://m.stock.naver.com/domestic/stock/{item['code']}/total"
            msg = (
                f"{alert_prefix}\n\n"
                f"📌 *종목:* {item['name']} ({item['code']})\n"
                f"📉 *괴리율:* `{item['rate']}%` (심각한 저평가)\n"
                f"💰 *현재가:* {item['price']:,}원\n"
                f"📊 *거래량:* {item['volume']:,}주\n\n"
                f"🔗 [네이버 증권 바로가기]({naver_link})\n"
                f"⚠️ 일시적 가격 왜곡일 가능성이 높습니다."
            )
            send_telegram(msg)
            print(f"알림 발송: {item['name']} ({item['rate']}%)")
            filtered_history[item_id] = item['date']
            new_notified = True

    # 2. 장 마감 요약 브리핑 (15:40 ~ 15:55)
    summary_id = f"SUMMARY_{today_str}"
    if 1540 <= kst_time <= 1555 and summary_id not in filtered_history:
        sorted_items = sorted(all_items, key=lambda x: x['rate'])[:5]
        if sorted_items:
            summary_msg = f"📝 *[장 마감 ETF 저평가 요약]*\n📅 {today_str}\n\n"
            for i, item in enumerate(sorted_items, 1):
                summary_msg += f"{i}. *{item['name']}*\n    └ 괴리율: `{item['rate']}%` | 거래량: {item['volume']:,}주\n"
            summary_msg += "\n*오늘 하루도 수고하셨습니다!*"
            send_telegram(summary_msg)
            filtered_history[summary_id] = today_str
            new_notified = True

    if new_notified or len(history_data) != len(filtered_history):
        with open(history_file, "w", encoding="utf-8") as f:
            json.dump(filtered_history, f, ensure_ascii=False, indent=2)
        print("기록 업데이트 완료.")

if __name__ == "__main__":
    main()
