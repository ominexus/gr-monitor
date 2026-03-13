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
        range_name = 'Sheet1!A:A'
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
                spreadsheetId=GOOGLE_SHEET_ID, range='Sheet1!A1',
                valueInputOption='RAW', insertDataOption='INSERT_ROWS', body=body
            ).execute()
            print(f"[+] 구글 시트 {len(new_rows)}건 기록 완료")
    except Exception as e:
        print(f"[-] 구글 시트 기록 에러: {e}")

# --- KIS API 설정 ---
KIS_APP_KEY = os.getenv("KIS_APPKEY")
KIS_APP_SECRET = os.getenv("KIS_SECRET")
KIS_CANO = os.getenv("KIS_CANO")        # 계좌번호 앞 8자리
KIS_PRDT_NO = os.getenv("KIS_ACNT_PRDT_CD", "01")  # 계좌번호 뒤 2자리 (보통 01)
KIS_URL_BASE = os.getenv("KIS_URL_BASE", "https://openapi.koreainvestment.com:9443") # 실전투자

# --- 설정 구간 ---
NORMAL_THRESHOLD = -3.0      # 한국 평시 알림 기준 (%)
OPENING_THRESHOLD = -5.0     # 한국 시초가 특별 감시 (%)
US_CRASH_THRESHOLD = -10.0    # 미국 "역대급 폭탄" 감지 기준 (%)
MIN_VOLUME = 5000            # 한국 ETF 최소 거래량
RETENTION_DAYS = 30          # 기록 보관 기간
BUY_UNIT_AMT = 100000        # 1회 매수 시 목표 금액 (10만 원)
# -----------------

def check_korean_holiday(token):
    """오늘이 한국 시장 휴장일인지 확인합니다."""
    if not token: return False
    url = f"{KIS_URL_BASE}/uapi/domestic-stock/v1/quotations/chk-holiday"
    headers = {
        "content-type": "application/json",
        "authorization": f"Bearer {token}",
        "appkey": KIS_APP_KEY,
        "appsecret": KIS_APP_SECRET,
        "tr_id": "CTCA0903R",
        "custtype": "P",
    }
    params = {"BASS_DT": datetime.now().strftime("%Y%m%d"), "CTX_AREA_NK": "", "CTX_AREA_FK": ""}
    try:
        res = requests.get(url, headers=headers, params=params).json()
        if res.get('rt_cd') == '0':
            return res.get('output', [{}])[0].get('opnd_yn') == 'N'
        return False
    except: return False

def get_portfolio_profit(token):
    """계좌 전체 수익률 현황 조회"""
    url = f"{KIS_URL_BASE}/uapi/domestic-stock/v1/trading/inquire-balance"
    is_mock = "openapivts" in KIS_URL_BASE
    tr_id = "VTTC8434R" if is_mock else "TTTC8434R"
    headers = {
        "content-type": "application/json", "authorization": f"Bearer {token}",
        "appkey": KIS_APP_KEY, "appsecret": KIS_APP_SECRET, "tr_id": tr_id, "custtype": "P",
    }
    params = {
        "CANO": KIS_CANO, "ACNT_PRDT_CD": KIS_PRDT_NO,
        "AFHR_FLPR_YN": "N", "OVAL_DVSN": "01", "PRCS_DVSN": "01",
        "CTX_AREA_FK100": "", "CTX_AREA_NK100": ""
    }
    try:
        res = requests.get(url, headers=headers, params=params).json()
        if res.get('rt_cd') == '0':
            summary = res.get('output2', [{}])[0]
            total_val = summary.get('tot_evlu_amt', '0')
            total_profit = summary.get('evlu_pfit_amt_smtl', '0')
            total_rate = summary.get('evlu_pfit_rt', '0')
            return f"💰 *[계좌 전체 수익 현황]*\n\n- 총 평가금액: `{int(float(total_val)):,}`원\n- 총 평가손익: `{int(float(total_profit)):,}`원\n- 현재 수익률: `{total_rate}%`"
        return "[-] 수익률 조회 실패"
    except Exception as e: return f"[-] 에러: {e}"

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

def get_kis_access_token():
    if not all([KIS_APP_KEY, KIS_APP_SECRET]):
        print("에러: KIS_APP_KEY, KIS_APP_SECRET 설정 필요")
        return None
    url = f"{KIS_URL_BASE}/oauth2/tokenP"
    headers = {"content-type": "application/json"}
    body = {
        "grant_type": "client_credentials",
        "appkey": KIS_APP_KEY,
        "appsecret": KIS_APP_SECRET
    }
    try:
        res = requests.post(url, headers=headers, json=body)
        res.raise_for_status()
        return res.json().get("access_token")
    except Exception as e:
        print(f"KIS 토큰 발급 에러: {e}")
        return None

def get_kis_balance(token):
    """한국투자증권 주식 매수 가능 금액 조회"""
    if not all([KIS_CANO, KIS_PRDT_NO, token]):
        return 0
        
    url = f"{KIS_URL_BASE}/uapi/domestic-stock/v1/trading/inquire-psbl-order"
    
    # tr_id: 실전(TTTC8908R), 모의(VTTC8908R)
    is_mock = "openapivts" in KIS_URL_BASE
    tr_id = "VTTC8908R" if is_mock else "TTTC8908R"
    
    headers = {
        "content-type": "application/json",
        "authorization": f"Bearer {token}",
        "appkey": KIS_APP_KEY,
        "appsecret": KIS_APP_SECRET,
        "tr_id": tr_id,
        "custtype": "P",
    }
    
    params = {
        "CANO": KIS_CANO,
        "ACNT_PRDT_CD": KIS_PRDT_NO,
        "PDNO": "005930", # 종목별 매수 가능 금액이 다를 수 있어 삼성전자(005930)를 기준으로 조회
        "ORD_UNPR": "0",
        "ORD_DVSN": "01", # 시장가 기준
        "CMA_EVLU_AMT_ICLD_YN": "N",
        "OVRS_ICLD_YN": "N"
    }
    
    try:
        res = requests.get(url, headers=headers, params=params)
        res_data = res.json()
        if res_data.get('rt_cd') == '0':
            # nrcz_buy_amt: 주문 가능 현금 (예수금)
            return int(res_data.get('output', {}).get('nrcz_buy_amt', 0))
        else:
            print(f"잔고 조회 실패: {res_data.get('msg1')}")
            return 0
    except Exception as e:
        print(f"잔고 조회 에러: {e}")
        return 0

def get_kis_holdings(token):
    """현재 보유 종목 및 수익률 조회"""
    if not all([KIS_CANO, KIS_PRDT_NO, token]):
        return []
        
    url = f"{KIS_URL_BASE}/uapi/domestic-stock/v1/trading/inquire-balance"
    
    is_mock = "openapivts" in KIS_URL_BASE
    tr_id = "VTTC8434R" if is_mock else "TTTC8434R"
    
    headers = {
        "content-type": "application/json",
        "authorization": f"Bearer {token}",
        "appkey": KIS_APP_KEY,
        "appsecret": KIS_APP_SECRET,
        "tr_id": tr_id,
        "custtype": "P",
    }
    
    params = {
        "CANO": KIS_CANO,
        "ACNT_PRDT_CD": KIS_PRDT_NO,
        "AFHR_FLPR_YN": "N",
        "OVAL_DVSN": "01",
        "PRCS_DVSN": "01",
        "CTX_AREA_FK100": "",
        "CTX_AREA_NK100": ""
    }
    
    try:
        res = requests.get(url, headers=headers, params=params)
        res_data = res.json()
        holdings = []
        if res_data.get('rt_cd') == '0':
            for stock in res_data.get('output1', []):
                if int(stock['hldg_qty']) > 0:
                    holdings.append({
                        "code": stock['pdno'],
                        "name": stock['prdt_name'],
                        "qty": int(stock['hldg_qty']),
                        "profit_rate": float(stock['evlu_pfit_rt'])
                    })
            return holdings
        return []
    except Exception as e:
        print(f"보유 종목 조회 에러: {e}")
        return []

def sell_order_kor(token, code, qty):
    """한국투자증권 주식 매도 주문 (시장가)"""
    url = f"{KIS_URL_BASE}/uapi/domestic-stock/v1/trading/order-cash"
    
    is_mock = "openapivts" in KIS_URL_BASE
    tr_id = "VTTC0801U" if is_mock else "TTTC0801U" # 0801U가 매도
    
    headers = {
        "content-type": "application/json",
        "authorization": f"Bearer {token}",
        "appkey": KIS_APP_KEY,
        "appsecret": KIS_APP_SECRET,
        "tr_id": tr_id,
        "custtype": "P",
    }
    
    body = {
        "CANO": KIS_CANO,
        "ACNT_PRDT_CD": KIS_PRDT_NO,
        "PDNO": code,
        "ORD_DVSN": "01",  # 01: 시장가
        "ORD_QTY": str(qty),
        "ORD_UNPR": "0",
    }
    
    try:
        res = requests.post(url, headers=headers, json=body)
        return res.json().get('rt_cd') == '0', res.json().get('msg1')
    except Exception as e:
        return False, str(e)

def place_order_kor(token, code, price, qty=1):
    """한국투자증권 주식 매수 주문 (시장가)"""
    if not all([KIS_CANO, KIS_PRDT_NO, token]):
        return False, "계좌번호 또는 토큰 누락"

    url = f"{KIS_URL_BASE}/uapi/domestic-stock/v1/trading/order-cash"

    # 주소에 'vts'가 포함되어 있으면 모의투자 환경으로 판단
    is_mock = "openapivts" in KIS_URL_BASE
    tr_id = "VTTC0802U" if is_mock else "TTTC0802U"

    headers = {
        "content-type": "application/json",
        "authorization": f"Bearer {token}",
        "appkey": KIS_APP_KEY,
        "appsecret": KIS_APP_SECRET,
        "tr_id": tr_id,
        "custtype": "P",
    }

    body = {
        "CANO": KIS_CANO,
        "ACNT_PRDT_CD": KIS_PRDT_NO,
        "PDNO": code,
        "ORD_DVSN": "01",  # 01: 시장가 (체결 우선)
        "ORD_QTY": str(qty),
        "ORD_UNPR": "0",   # 시장가는 0으로 설정
    }

    try:
        res = requests.post(url, headers=headers, json=body)
        res_data = res.json()
        if res_data.get('rt_cd') == '0':
            return True, f"주문 성공 (번호: {res_data.get('output', {}).get('ODNO')})"
        else:
            return False, res_data.get('msg1', '알 수 없는 오류')
    except Exception as e:
        return False, str(e)


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

def handle_telegram_commands(token, kis_token):
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

            if text.startswith("/잔고") or text.startswith("/balance"):
                balance = get_kis_balance(kis_token)
                send_telegram(f"💰 *[현재 잔고 리포트]*\n\n주문 가능 금액: `{balance:,}원`")
            
            elif text.startswith("/보유") or text.startswith("/holdings"):
                holdings = get_kis_holdings(kis_token)
                if not holdings:
                    send_telegram("📦 *[보유 종목 리포트]*\n\n현재 보유 중인 종목이 없습니다.")
                else:
                    report = "📦 *[보유 종목 리포트]*\n\n"
                    for h in holdings:
                        report += f"🔹 *{h['name']}* ({h['code']})\n    └ 수량: `{h['qty']}주` | 수익률: `{h['profit_rate']}%` \n"
                    send_telegram(report)

            elif text.startswith("/수익") or text.startswith("/profit"):
                report = get_portfolio_profit(kis_token)
                send_telegram(report)
            
            elif text.startswith("/help") or text.startswith("/시작") or text.startswith("/start"):
                send_telegram("🤖 *사용 가능한 명령어*\n\n/잔고 - 계좌 예수금 확인\n/보유 - 현재 보유 종목 확인\n/수익 - 전체 계좌 수익률 확인")

        with open(state_file, "w") as f:
            json.dump({"last_update_id": new_last_id}, f)
            
    except Exception as e:
        print(f"텔레그램 명령어 처리 에러: {e}")

def main():
    # 1. KIS 토큰 받아오기
    kis_token = get_kis_access_token()
    if not kis_token:
        send_telegram("🚨 *[시스템 에러]*\n\nKIS API 토큰 발급에 실패했습니다. 키 설정을 확인해 주세요.")
        return
    
    # 2. 텔레그램 명령어 처리 (장 상태와 관계없이 실행)
    if TELEGRAM_TOKEN:
        handle_telegram_commands(TELEGRAM_TOKEN, kis_token)

    # 3. 휴장일 체크 (KOR 시장 감시 시에만)
    market, kst_time = get_market_status()
    if market == "KOR" and check_korean_holiday(kis_token):
        print(f"[-] 오늘은 한국 시장 휴장일입니다. 감시를 중단합니다.")
        return

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
            
            # KIS 자동매수 로직 (KOR 시장인 경우)
            if market == "KOR":
                # 금액 기준 수량 계산 (예: 10만 원 / 현재가)
                qty = max(1, BUY_UNIT_AMT // item['price'])
                
                balance = get_kis_balance(kis_token)
                
                # 잔고 부족 시 교체 매매 전략
                if balance < (item['price'] * qty):
                    holdings = get_kis_holdings(kis_token)
                    if holdings:
                        best_stock = sorted(holdings, key=lambda x: x['profit_rate'], reverse=True)[0]
                        sell_success, sell_msg = sell_order_kor(kis_token, best_stock['code'], best_stock['qty'])
                        if sell_success:
                            msg += f"\n\n🔄 *자산 교체 실행*\n└ 매도: `{best_stock['name']}`\n└ 사유: `현금 확보 (단가: {item['price']:,}원 x {qty}주 매수용)`"
                            balance = get_kis_balance(kis_token)
                        else:
                            msg += f"\n\n❌ *자산 교체 실패*\n└ 사유: `{sell_msg}`"

                # 최종 매수 시도
                if balance >= (item['price'] * qty):
                    success, result_msg = place_order_kor(kis_token, item['code'], item['price'], qty=qty)
                    if success:
                        msg += f"\n\n✅ *자동매수 완료*\n└ 결과: `{qty}주 매수 성공 ({result_msg})`"
                    else:
                        msg += f"\n\n❌ *자동매수 실패*\n└ 사유: `{result_msg}`"
                else:
                    msg += f"\n\n⚠️ *자동매수 건너뜀*\n└ 사유: `최종 잔고 부족 (필요: {(item['price']*qty):,}원)`"

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
