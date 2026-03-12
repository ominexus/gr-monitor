import os
import requests
from datetime import datetime, timedelta
import json
import yfinance as yf

# GitHub Secrets에서 환경 변수 불러오기
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

# --- 설정 구간 ---
NORMAL_THRESHOLD = -3.0      # 한국 평시 알림 기준 (%)
OPENING_THRESHOLD = -5.0     # 한국 시초가 특별 감시 (%)
US_CRASH_THRESHOLD = -10.0    # 미국 "역대급 폭탄" 감지 기준 (%)
MIN_VOLUME = 5000            # 한국 ETF 최소 거래량
RETENTION_DAYS = 30          # 기록 보관 기간

# 🇺🇸 서학개미 TOP 30 감시 리스트
US_WATCH_LIST = [
    "TSLA", "NVDA", "AAPL", "TQQQ", "MSFT", 
    "SOXL", "QQQ", "AMZN", "GOOGL", "SCHD",
    "TSLL", "SOXS", "JEPI", "SQQQ", "TLT", 
    "META", "SPY", "VOO", "NVDL", "AMD",
    "AVGO", "NFLX", "BRK-B", "LULU", "COIN",
    "TMF", "BITO", "LLY", "SMH", "ARKK"
]
# -----------------

def send_telegram(message):
    if not TELEGRAM_TOKEN or not CHAT_ID:
        print("에러: TELEGRAM_TOKEN 또는 CHAT_ID 설정 필요")
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {"chat_id": CHAT_ID, "text": message, "parse_mode": "Markdown", "disable_web_page_preview": True}
    try:
        requests.post(url, json=payload).raise_for_status()
    except Exception as e:
        print(f"텔레그램 전송 에러: {e}")

def fetch_realtime_etf_data():
    """한국 ETF 데이터를 가져옵니다."""
    url = "https://finance.naver.com/api/sise/etfItemList.nhn"
    try:
        response = requests.get(url)
        data = response.json()
        items = data.get("result", {}).get("etfItemList", [])
        results = []
        today = datetime.now().strftime('%Y-%m-%d')
        for item in items:
            name, code, now_val, nav, volume = item.get("itemname"), item.get("itemcode"), item.get("nowVal"), item.get("nav"), item.get("quant")
            if not nav or nav == 0: continue
            discrepancy = round(((now_val - nav) / nav) * 100, 2)
            if volume >= MIN_VOLUME:
                results.append({"name": name, "code": code, "rate": discrepancy, "price": now_val, "nav": nav, "volume": volume, "date": today, "market": "KOR"})
        return results
    except: return []

def fetch_us_opening_data():
    """미국 TOP 30 데이터를 가져와 -10% 이상 대폭락 종목을 찾습니다."""
    results = []
    today = datetime.now().strftime('%Y-%m-%d')
    print(f"미국 TOP 30 정밀 감시 시작: (기준 {US_CRASH_THRESHOLD}%)")
    
    for symbol in US_WATCH_LIST:
        try:
            ticker = yf.Ticker(symbol)
            info = ticker.fast_info
            # 실시간 주가와 전일 종가 비교 (추정 괴리율)
            prev_close = info.get('previous_close')
            current_price = info.get('last_price')
            
            if not prev_close or not current_price: continue
            
            change_rate = round(((current_price - prev_close) / prev_close) * 100, 2)
            
            # -10% 이상의 기록적인 폭락/괴리 발생 시만 수집
            if change_rate <= US_CRASH_THRESHOLD:
                results.append({
                    "name": symbol, "code": symbol, "rate": change_rate,
                    "price": current_price, "prev": prev_close,
                    "date": today, "market": "USA"
                })
        except Exception as e:
            print(f"US Error ({symbol}): {e}")
            
    return results

def get_market_status():
    now_utc = datetime.utcnow()
    now_kst = now_utc + timedelta(hours=9)
    weekday = now_kst.weekday()
    now_time = int(now_kst.strftime("%H%M"))
    
    if weekday <= 4 and (850 <= now_time <= 1600): return "KOR", now_time
    if weekday <= 4 and (2230 <= now_time <= 2359): return "USA_OPEN", now_time
    return "CLOSED", now_time

def main():
    market, kst_time = get_market_status()
    if market == "CLOSED":
        print(f"[-] 시장 마감: 건너뜁니다.")
        return

    now = datetime.now()
    today_str = now.strftime('%Y-%m-%d')
    history_file = "notified_disclosures.json"
    history_data = {}
    if os.path.exists(history_file):
        with open(history_file, "r", encoding="utf-8") as f:
            try: history_data = json.load(f)
            except: history_data = {}

    all_items = []
    if market == "KOR":
        all_items = fetch_realtime_etf_data()
        prefix = "🚨 *[ETF 실시간 저평가 알림]*"
        threshold = OPENING_THRESHOLD if (900 <= kst_time <= 910) else NORMAL_THRESHOLD
    elif market == "USA_OPEN":
        all_items = fetch_us_opening_data()
        prefix = "💣 *[미국장 역대급 폭탄 감지]*"
        threshold = US_CRASH_THRESHOLD

    if not all_items: return

    new_notified = False
    for item in all_items:
        item_id = f"{item['name']}_{item['date']}"
        if item['rate'] <= threshold and item_id not in history_data:
            link = f"https://m.stock.naver.com/domestic/stock/{item['code']}/total" if market == "KOR" else f"https://finance.yahoo.com/quote/{item['code']}"
            msg = (
                f"{prefix}\n\n"
                f"📌 *종목:* {item['name']} ({item['code']})\n"
                f"📉 *변동률/괴리율:* `{item['rate']}%` (비정상 급락)\n"
                f"💰 *현재가:* {item['price']:,}원 (USD)\n"
                f"🔗 [상세 페이지 바로가기]({link})\n"
                f"⚠️ 평소보다 훨씬 큰 변동성이 감지되었습니다!"
            )
            send_telegram(msg)
            print(f"알림 발송: {item['name']} ({item['rate']}%)")
            history_data[item_id] = item['date']
            new_notified = True

    # 한국 장 마감 요약
    if market == "KOR" and 1540 <= kst_time <= 1555 and f"SUMMARY_{today_str}" not in history_data:
        sorted_items = sorted(all_items, key=lambda x: x['rate'])[:5]
        if sorted_items:
            summary_msg = f"📝 *[장 마감 ETF 저평가 요약]*\n📅 {today_str}\n\n"
            for i, itm in enumerate(sorted_items, 1):
                summary_msg += f"{i}. *{itm['name']}*\n    └ 괴리율: `{itm['rate']}%` | 거래량: {itm['volume']:,}주\n"
            send_telegram(summary_msg)
            history_data[f"SUMMARY_{today_str}"] = today_str
            new_notified = True

    if new_notified:
        with open(history_file, "w", encoding="utf-8") as f:
            json.dump(history_data, f, ensure_ascii=False, indent=2)

if __name__ == "__main__":
    main()
