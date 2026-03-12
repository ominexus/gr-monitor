import os
import requests
from datetime import datetime, timedelta
import json
import yfinance as yf

# GitHub Secrets에서 환경 변수 불러오기
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

# --- 설정 구간 ---
NORMAL_THRESHOLD = -3.0      # 평시 알림 기준 괴리율 (%)
OPENING_THRESHOLD = -5.0     # 시초가 특별 감시 기준 괴리율 (%)
MIN_VOLUME = 5000            # 최소 거래량 (유동성 보장)
RETENTION_DAYS = 30          # 알림 기록 보관 기간 (일)

# 감시할 미국 주요 ETF 리스트
US_WATCH_LIST = ["SPY", "QQQ", "DIA", "TQQQ", "SOXL", "TSLL"]
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
    """한국 ETF 데이터를 네이버 금융에서 가져옵니다."""
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
    """미국 ETF 데이터를 Yahoo Finance에서 가져와 추정 괴리율을 산출합니다."""
    results = []
    today = datetime.now().strftime('%Y-%m-%d')
    print(f"미국 시장 데이터 수집 시작: {US_WATCH_LIST}")
    
    for symbol in US_WATCH_LIST:
        try:
            ticker = yf.Ticker(symbol)
            info = ticker.fast_info
            prev_nav = info.get('previous_close') # 미국은 실시간 NAV가 유료이므로 전일 종가 NAV로 추정
            current_price = info.get('last_price')
            volume = info.get('last_volume')
            
            if not prev_nav or not current_price: continue
            
            # 추정 괴리율 계산
            discrepancy = round(((current_price - prev_nav) / prev_nav) * 100, 2)
            
            # 미국은 변동성이 크므로 -4% 이상일 때만 알림
            if discrepancy <= -4.0:
                results.append({
                    "name": symbol, "code": symbol, "rate": discrepancy,
                    "price": current_price, "nav": prev_nav, "volume": volume,
                    "date": today, "market": "USA"
                })
        except Exception as e:
            print(f"US Data Error ({symbol}): {e}")
            
    return results

def get_market_status():
    now_utc = datetime.utcnow()
    now_kst = now_utc + timedelta(hours=9)
    weekday = now_kst.weekday()
    now_time = int(now_kst.strftime("%H%M"))
    
    # 1. 한국 시장 운영 시간 (08:50 ~ 16:00)
    if weekday <= 4 and (850 <= now_time <= 1600):
        return "KOR", now_time
    
    # 2. 미국 시장 시작 시간 (22:30 ~ 24:00)
    # 서머타임에 따라 22:30 또는 23:30에 시작하므로 범위를 넉넉하게 잡습니다.
    if weekday <= 4 and (2230 <= now_time <= 2359):
        return "USA_OPEN", now_time
    
    return "CLOSED", now_time

def main():
    market, kst_time = get_market_status()
    if market == "CLOSED":
        print(f"[-] 시장 마감: (KST {kst_time}) 건너뜁니다.")
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
        if 900 <= kst_time <= 910:
            prefix = "⚡ *[시초가 괴리율 폭탄 감지]*"
            threshold = OPENING_THRESHOLD
        else:
            threshold = NORMAL_THRESHOLD
    elif market == "USA_OPEN":
        all_items = fetch_us_opening_data()
        prefix = "🇺🇸 *[미국장 오프닝 벨 알림]*"
        threshold = -4.0  # 미국 기본 기준

    if not all_items: return

    new_notified = False
    for item in all_items:
        item_id = f"{item['name']}_{item['date']}"
        if item['rate'] <= threshold and item_id not in history_data:
            link = f"https://m.stock.naver.com/domestic/stock/{item['code']}/total" if market == "KOR" else f"https://finance.yahoo.com/quote/{item['code']}"
            msg = (
                f"{prefix}\n\n"
                f"📌 *종목:* {item['name']} ({item['code']})\n"
                f"📉 *괴리율:* `{item['rate']}%` (추정치)\n"
                f"💰 *현재가:* {item['price']:,}원\n"
                f"🔗 [상세 정보 확인하기]({link})"
            )
            send_telegram(msg)
            history_data[item_id] = item['date']
            new_notified = True

    # 장 마감 요약 (한국 전용)
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
