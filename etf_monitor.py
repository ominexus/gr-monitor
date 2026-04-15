import os
import requests
from datetime import datetime, timedelta
import json
import yfinance as yf
from google.oauth2 import service_account
from googleapiclient.discovery import build

# GitHub Secrets에서 환경 변수 불러오기
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
GOOGLE_SERVICE_ACCOUNT = os.getenv("GOOGLE_SERVICE_ACCOUNT") # JSON 스트링
GOOGLE_SHEET_ID = os.getenv("GOOGLE_SHEET_ID")
# -----------------

def log_to_google_sheets(items):
    """구글 시트에 데이터를 기록합니다. (중복 방지 적용)"""
    if not GOOGLE_SERVICE_ACCOUNT or not GOOGLE_SHEET_ID:
        print("[-] 구글 시트 설정(GOOGLE_SERVICE_ACCOUNT, GOOGLE_SHEET_ID)이 없습니다. 건너뜁니다.")
        return

    try:
        # 서비스 계정 인증
        info = json.loads(GOOGLE_SERVICE_ACCOUNT)
        credentials = service_account.Credentials.from_service_account_info(info)
        service = build('sheets', 'v4', credentials=credentials)
        sheet = service.spreadsheets()

        # 현재 시트 데이터 가져오기 (중복 체크용 ID 열 조회)
        range_name = '시트1!A:A'
        result = sheet.values().get(spreadsheetId=GOOGLE_SHEET_ID, range=range_name).execute()
        existing_ids = [row[0] for row in result.get('values', [])] if result.get('values') else []

        new_rows = []
        for item in items:
            # 고유 ID 생성 (날짜_종목코드_시장)
            item_id = f"{item['date']}_{item['code']}_{item['market']}"
            if item_id not in existing_ids:
                # [ID, 일시, 종목명, 코드, 시장, 괴리율, 가격, 거래량]
                new_rows.append([
                    item_id,
                    datetime.now().strftime('%Y-%m-%d %H:%M'),
                    item['name'],
                    item['code'],
                    item['market'],
                    item['rate'],
                    item['price'],
                    item.get('volume', 0)
                ])

        if new_rows:
            body = {'values': new_rows}
            sheet.values().append(
                spreadsheetId=GOOGLE_SHEET_ID, range='시트1!A1',
                valueInputOption='RAW', insertDataOption='INSERT_ROWS', body=body
            ).execute()
            print(f"[+] 구글 시트 {len(new_rows)}건 기록 완료")
    except Exception as e:
        print(f"[-] 구글 시트 기록 에러: {e}")

# --- 설정 구간 ---
NORMAL_THRESHOLD = -3.0      # 한국 평시 알림 기준 (%)
OPENING_THRESHOLD = -5.0     # 한국 시초가 특별 감시 (%)
US_CRASH_THRESHOLD = -10.0    # 미국 "역대급 폭탄" 감지 기준 (%)
MIN_VOLUME = 5000            # 한국 ETF 최소 거래량
RETENTION_DAYS = 30          # 기록 보관 기간
# -----------------

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
            results.append({
                "name": name, "code": code, "rate": discrepancy, 
                "price": now_val, "nav": nav, "volume": volume, 
                "date": today, "market": "KOR"
            })
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

def handle_telegram_commands(token):
    """텔레그램 명령어를 확인하고 응답합니다."""
    state_file = "bot_state.json"
    last_id = 0
    one_hour_ago = int((datetime.utcnow() - timedelta(hours=1)).timestamp())

    if os.path.exists(state_file):
        with open(state_file, "r") as f:
            try:
                data = json.load(f)
                last_id = data.get("last_update_id", 0)
            except: last_id = 0

    url = f"https://api.telegram.org/bot{token}/getUpdates"
    params = {"offset": last_id + 1, "timeout": 10}
    
    try:
        res = requests.get(url, params=params).json()
        if not res.get("ok"): return
        
        updates = res.get("result", [])
        if not updates: return 

        new_last_id = last_id
        for update in updates:
            msg = update.get("message", {})
            text = msg.get("text", "")
            chat_id = msg.get("chat", {}).get("id")
            update_id = update.get("update_id")
            msg_date = msg.get("date", 0)
            
            new_last_id = max(new_last_id, update_id)

            if str(chat_id) != str(CHAT_ID): continue
            if msg_date < one_hour_ago: continue 
            if not text: continue

            if text.startswith("/help") or text.startswith("/시작") or text.startswith("/start"):
                send_telegram("🤖 *사용 가능한 명령어*\n\n/help - 도움말 확인")

        with open(state_file, "w") as f:
            json.dump({"last_update_id": new_last_id}, f)
            
    except Exception as e:
        print(f"텔레그램 명령어 처리 에러: {e}")

def main():
    # 1. 텔레그램 명령어 처리 (장 상태와 관계없이 실행)
    if TELEGRAM_TOKEN:
        handle_telegram_commands(TELEGRAM_TOKEN)

    # 2. 장 상태 확인
    market, kst_time = get_market_status()

    if market == "CLOSED":
        print(f"[-] 시장 마감: 명령어 확인 후 종료합니다.")
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

    # 괴리율 공시 기준(절대값 1.0% 이상)을 넘는 모든 아이템을 시트에 기록
    items_to_log = [itm for itm in all_items if abs(itm['rate']) >= 1.0]
    if items_to_log:
        log_to_google_sheets(items_to_log)

    new_notified = False
    for item in all_items:
        item_id = f"{item['name']}_{item['date']}"
        
        # 텔레그램 알림용 필터링 (거래량 및 임계값 기준)
        is_high_volume = item.get('volume', 0) >= MIN_VOLUME
        if item['rate'] <= threshold and item_id not in history_data and is_high_volume:
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
