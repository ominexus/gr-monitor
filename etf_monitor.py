import os
import requests
from datetime import datetime, timedelta
import json
import yfinance as yf
import pandas as pd
from google.oauth2 import service_account
from googleapiclient.discovery import build
import tempfile
from typing import List, Tuple, Dict, Any, Optional

# GitHub Secrets에서 환경 변수 불러오기
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
GOOGLE_SERVICE_ACCOUNT = os.getenv("GOOGLE_SERVICE_ACCOUNT") # JSON 스트링
GOOGLE_SHEET_ID = os.getenv("GOOGLE_SHEET_ID")
# -----------------

def atomic_write_json(file_path: str, data: Any) -> None:
    """Writes JSON data to a file atomically using a temporary file."""
    dir_name = os.path.dirname(file_path)
    if not dir_name:
        dir_name = "."
    fd, temp_path = tempfile.mkstemp(dir=dir_name, text=True)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        os.replace(temp_path, file_path)
    except Exception:
        if os.path.exists(temp_path):
            os.remove(temp_path)
        raise

def log_to_google_sheets(items: List[Dict[str, Any]]) -> None:
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
BOOM_THRESHOLD = 3.0         # 한국 급등 알림 기준 (%)
US_CRASH_THRESHOLD = -10.0    # 미국 "역대급 폭탄" 감지 기준 (%)
US_BOOM_THRESHOLD = 10.0      # 미국 폭등 감지 기준 (%)
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
PENDING_ALERTS_FILE = "pending_alerts.json"
# -----------------

def calculate_rsi(ticker_symbol: str, period: int = 14) -> Optional[float]:
    """주어진 티커의 RSI(상대강도지수)를 계산합니다."""
    try:
        # yfinance는 pandas 객체를 반환하므로 내부적으로 pandas가 필요합니다.
        ticker = yf.Ticker(ticker_symbol)
        # RSI 14를 안정적으로 계산하기 위해 약 2달치 데이터를 가져옴
        df = ticker.history(period="2mo", interval="1d")
        
        if len(df) < period + 1:
            return None
            
        close = df['Close']
        delta = close.diff()
        
        gain = delta.copy()
        loss = delta.copy()
        gain[gain < 0] = 0
        loss[loss > 0] = 0
        loss = abs(loss)
        
        # Wilder's smoothing (RSI 표준 계산 방식)
        avg_gain = gain.ewm(alpha=1/period, min_periods=period, adjust=False).mean()
        avg_loss = loss.ewm(alpha=1/period, min_periods=period, adjust=False).mean()
        
        rs = avg_gain / avg_loss
        rsi = 100 - (100 / (1 + rs))
        
        latest_rsi = rsi.iloc[-1]
        if pd.isna(latest_rsi):
            return None
            
        return round(float(latest_rsi), 2)
        
    except Exception as e:
        print(f"[-] RSI 계산 실패 ({ticker_symbol}): {e}")
        return None

def filter_by_rsi(candidates: List[Dict[str, Any]], is_boom: bool) -> List[Dict[str, Any]]:
    """후보 종목들에 대해 RSI 필터링을 수행합니다."""
    if not candidates:
        return []

    print(f"[*] {len(candidates)}개 후보 종목에 대해 RSI 필터링 시작 (Boom: {is_boom})...")
    filtered: List[Dict[str, Any]] = []
    
    for item in candidates:
        # 한국 마켓이면 .KS 접미사 추가
        ticker = item['code']
        if item.get('market') == 'KOR':
            ticker = f"{ticker}.KS"
            
        rsi = calculate_rsi(ticker)
        if rsi is None:
            # RSI 계산 실패 시 안전하게 제외 (또는 포함할지 선택 가능, 여기서는 제외)
            continue
            
        item['rsi'] = rsi
        
        if is_boom:
            if rsi >= 70:
                filtered.append(item)
                print(f"  [+] {item['name']} 통과 (RSI: {rsi})")
        else:
            if rsi <= 30:
                filtered.append(item)
                print(f"  [+] {item['name']} 통과 (RSI: {rsi})")
                
    return filtered

def fetch_latest_news(ticker_symbol: str) -> Optional[Dict[str, str]]:
    """yfinance를 사용하여 해당 종목의 최신 뉴스 1건을 가져옵니다."""
    try:
        ticker = yf.Ticker(ticker_symbol)
        news = ticker.news
        if not news:
            return None
        
        # 가장 최근 뉴스 1건 추출
        latest = news[0]
        return {
            "title": latest.get("title", "No Title"),
            "link": latest.get("link", "#")
        }
    except Exception as e:
        print(f"[-] 뉴스 가져오기 실패 ({ticker_symbol}): {e}")
        return None

def send_telegram(message: str) -> bool:
    if not TELEGRAM_TOKEN or not CHAT_ID:
        print("에러: TELEGRAM_TOKEN 또는 CHAT_ID 설정 필요")
        return False
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {"chat_id": CHAT_ID, "text": message, "parse_mode": "Markdown", "disable_web_page_preview": True}
    try:
        requests.post(url, json=payload, timeout=10).raise_for_status()
        return True
    except Exception as e:
        print(f"텔레그램 전송 에러: {e}")
        return False

def add_to_pending_queue(item: Dict[str, Any]) -> None:
    """트리거된 종목을 대기열 파일에 추가합니다."""
    queue: List[Dict[str, Any]] = []
    if os.path.exists(PENDING_ALERTS_FILE):
        try:
            with open(PENDING_ALERTS_FILE, "r", encoding="utf-8") as f:
                queue = json.load(f)
        except (json.JSONDecodeError, FileNotFoundError, PermissionError):
            queue = []
    
    now = datetime.now()
    current_hour = now.hour
    
    # Add timestamp/hour to item for better tracking and deduplication
    if 'hour' not in item:
        item['hour'] = current_hour
    if 'timestamp' not in item:
        item['timestamp'] = now.strftime('%Y-%m-%d %H:%M:%S')
    
    # 중복 방지 (이름, 날짜, 시간 기준)
    item_id = f"{item['name']}_{item['date']}_{current_hour}"
    if not any(f"{i['name']}_{i['date']}_{i.get('hour', -1)}" == item_id for i in queue):
        queue.append(item)
        try:
            atomic_write_json(PENDING_ALERTS_FILE, queue)
        except Exception as e:
            print(f"[-] 대기열 파일 쓰기 에러: {e}")

def get_pending_queue() -> List[Dict[str, Any]]:
    """대기열 데이터를 가져옵니다."""
    if not os.path.exists(PENDING_ALERTS_FILE):
        return []
    
    queue: List[Dict[str, Any]] = []
    try:
        with open(PENDING_ALERTS_FILE, "r", encoding="utf-8") as f:
            queue = json.load(f)
    except (json.JSONDecodeError, FileNotFoundError, PermissionError):
        queue = []
        
    return queue

def clear_pending_queue() -> None:
    """대기열 파일을 비웁니다."""
    try:
        atomic_write_json(PENDING_ALERTS_FILE, [])
    except Exception as e:
        print(f"[-] 대기열 파일 초기화 에러: {e}")

def send_hourly_summary(current_hour: int) -> bool:
    """대기열에 쌓인 데이터를 통합하여 발송합니다."""
    queue = get_pending_queue()
    if not queue:
        return True # 처리할 게 없으면 성공으로 간주 (시간 업데이트를 위해)

    # 시장별/유형별 그룹화
    categories: Dict[str, List[Dict[str, Any]]] = {
        "KOR_BOOM": [], "KOR_CRASH": [],
        "USA_BOOM": [], "USA_CRASH": []
    }
    
    for item in queue:
        m = item.get("market", "KOR")
        # 기존 로직 기반 유형 판단
        is_boom = False
        if m == "KOR":
            is_boom = item.get('change_rate', 0) >= BOOM_THRESHOLD or item['rate'] >= BOOM_THRESHOLD
        else:
            is_boom = item['rate'] >= US_BOOM_THRESHOLD
            
        cat_key = f"{m}_{'BOOM' if is_boom else 'CRASH'}"
        if cat_key in categories:
            categories[cat_key].append(item)

    summary_msg = f"🕒 *[시간별 변동성 통합 요약 - {current_hour}시]*\n\n"
    has_content = False

    for key, items in categories.items():
        if not items: continue
        has_content = True
        
        market_label = "🇰🇷 한국 ETF" if "KOR" in key else "🇺🇸 미국 주식"
        type_label = "🚀 급등/고평가" if "BOOM" in key else "🚨 급락/저평가"
        
        summary_msg += f"*{market_label} {type_label} ({len(items)}건)*\n"
        
        # 변동폭 기준 정렬 (절대값 큰 순)
        sorted_items = sorted(items, key=lambda x: abs(x['rate']), reverse=True)
        top_items = sorted_items[:5]
        
        for itm in top_items:
            rsi_val = itm.get('rsi', 'N/A')
            if "KOR" in key:
                summary_msg += f"• {itm['name']}: `{itm['rate']}%` (RSI: {rsi_val}) ({itm['price']:,}원)\n"
            else:
                summary_msg += f"• {itm['name']}: `{itm['rate']}%` (RSI: {rsi_val}) ({itm['price']:,.2f} USD)\n"
            
            # 뉴스 정보가 있으면 추가
            news = itm.get('news')
            if news:
                summary_msg += f"  📰 [{news['title']}]({news['link']})\n"
        
        if len(items) > 5:
            summary_msg += f"  ...외 {len(items) - 5}건\n"
        summary_msg += "\n"

    if has_content:
        if GOOGLE_SHEET_ID:
            summary_msg += f"🔗 [상세 데이터(구글 시트) 확인](https://docs.google.com/spreadsheets/d/{GOOGLE_SHEET_ID})"
        
        if send_telegram(summary_msg):
            clear_pending_queue()
            return True
        else:
            return False
    
    return True

def fetch_realtime_etf_data() -> List[Dict[str, Any]]:
    """한국 ETF 데이터를 가져옵니다."""
    url = "https://finance.naver.com/api/sise/etfItemList.nhn"
    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        data = response.json()
        items = data.get("result", {}).get("etfItemList", [])
        results: List[Dict[str, Any]] = []
        today = datetime.now().strftime('%Y-%m-%d')
        for item in items:
            name, code, now_val, nav, volume, change_rate = item.get("itemname"), item.get("itemcode"), item.get("nowVal"), item.get("nav"), item.get("quant"), item.get("changeRate")
            if not nav or nav == 0: continue
            discrepancy = round(((now_val - nav) / nav) * 100, 2)
            results.append({
                "name": name, "code": code, "rate": discrepancy, "change_rate": change_rate,
                "price": now_val, "nav": nav, "volume": volume, 
                "date": today, "market": "KOR"
            })
        return results
    except Exception as e:
        print(f"[-] 한국 ETF 데이터 가져오기 실패: {e}")
        return []

def fetch_us_opening_data() -> List[Dict[str, Any]]:
    """미국 TOP 30 데이터를 가져와 급변동(폭락/폭등) 종목을 찾습니다."""
    results: List[Dict[str, Any]] = []
    today = datetime.now().strftime('%Y-%m-%d')
    print(f"미국 TOP 30 정밀 감시 시작: (기준 폭락 {US_CRASH_THRESHOLD}%, 폭등 {US_BOOM_THRESHOLD}%)")
    
    for symbol in US_WATCH_LIST:
        try:
            ticker = yf.Ticker(symbol)
            info = ticker.fast_info
            # 실시간 주가와 전일 종가 비교 (추정 괴리율)
            prev_close = info.get('previous_close')
            current_price = info.get('last_price')
            
            if not prev_close or not current_price: continue
            
            change_rate = round(((current_price - prev_close) / prev_close) * 100, 2)
            
            # 기록적인 폭락/폭등 발생 시 수집
            if change_rate <= US_CRASH_THRESHOLD or change_rate >= US_BOOM_THRESHOLD:
                results.append({
                    "name": symbol, "code": symbol, "rate": change_rate,
                    "price": current_price, "prev": prev_close,
                    "date": today, "market": "USA"
                })
        except Exception as e:
            print(f"US Error ({symbol}): {e}")
            
    return results

def get_market_status() -> Tuple[str, int]:
    now_utc = datetime.utcnow()
    now_kst = now_utc + timedelta(hours=9)
    weekday = now_kst.weekday()
    now_time = int(now_kst.strftime("%H%M"))
    
    if weekday <= 4 and (850 <= now_time <= 1600): return "KOR", now_time
    if weekday <= 4 and (2230 <= now_time <= 2359): return "USA_OPEN", now_time
    return "CLOSED", now_time

def handle_telegram_commands(token: str, state: Dict[str, Any]) -> bool:
    """텔레그램 명령어를 확인하고 응답합니다."""
    last_id = state.get("last_update_id", 0)
    one_hour_ago = int((datetime.utcnow() - timedelta(hours=1)).timestamp())

    url = f"https://api.telegram.org/bot{token}/getUpdates"
    params = {"offset": last_id + 1, "timeout": 10}
    
    try:
        res = requests.get(url, params=params, timeout=15).json()
        if not res.get("ok"): return False
        
        updates = res.get("result", [])
        if not updates: return False

        new_last_id = last_id
        changed = False
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
                changed = True

        if new_last_id != last_id:
            state["last_update_id"] = new_last_id
            changed = True
            
        return changed
            
    except Exception as e:
        print(f"텔레그램 명령어 처리 에러: {e}")
        return False

def main() -> None:
    # 0. 상태 파일 로드
    state_file = "bot_state.json"
    bot_state: Dict[str, Any] = {}
    if os.path.exists(state_file):
        try:
            with open(state_file, "r") as f:
                bot_state = json.load(f)
        except (json.JSONDecodeError, FileNotFoundError, PermissionError):
            bot_state = {}
    
    state_changed = False

    # 1. 텔레그램 명령어 처리 (장 상태와 관계없이 실행)
    if TELEGRAM_TOKEN:
        if handle_telegram_commands(TELEGRAM_TOKEN, bot_state):
            state_changed = True

    # 2. 장 상태 확인
    market, kst_time = get_market_status()

    if market == "CLOSED":
        if state_changed:
            try:
                atomic_write_json(state_file, bot_state)
            except Exception as e:
                print(f"[-] 봇 상태 파일 쓰기 에러: {e}")
        print(f"[-] 시장 마감: 명령어 확인 후 종료합니다.")
        return

    now = datetime.now()
    today_str = now.strftime('%Y-%m-%d')
    history_file = "notified_disclosures.json"
    history_data: Dict[str, Any] = {}
    if os.path.exists(history_file):
        try:
            with open(history_file, "r", encoding="utf-8") as f:
                history_data = json.load(f)
        except (json.JSONDecodeError, FileNotFoundError, PermissionError):
            history_data = {}

    all_items: List[Dict[str, Any]] = []
    if market == "KOR":
        all_items = fetch_realtime_etf_data()
        prefix = "🚨 *[ETF 실시간 저평가 알림]*"
        threshold = OPENING_THRESHOLD if (900 <= kst_time <= 910) else NORMAL_THRESHOLD
    elif market == "USA_OPEN":
        all_items = fetch_us_opening_data()
        prefix = "💣 *[미국장 역대급 폭탄 감지]*"
        threshold = US_CRASH_THRESHOLD

    if not all_items:
        if state_changed:
            try:
                atomic_write_json(state_file, bot_state)
            except Exception as e:
                print(f"[-] 봇 상태 파일 쓰기 에러: {e}")
        return

    # 괴리율 1.0% 이상 또는 급등 기준을 넘는 아이템을 시트에 기록
    items_to_log: List[Dict[str, Any]] = []
    for itm in all_items:
        if market == "KOR":
            if abs(itm['rate']) >= 1.0 or abs(itm.get('change_rate', 0)) >= BOOM_THRESHOLD:
                items_to_log.append(itm)
        elif market == "USA_OPEN":
            # 미국은 fetch 단계에서 이미 걸러져서 들어옴
            items_to_log.append(itm)
            
    if items_to_log:
        log_to_google_sheets(items_to_log)

    history_changed = False
    boom_candidates: List[Dict[str, Any]] = []
    crash_candidates: List[Dict[str, Any]] = []

    for item in all_items:
        item_id = f"{item['name']}_{item['date']}"
        
        # 이미 알림을 보낸 종목은 제외
        if item_id in history_data:
            continue

        # 텔레그램 알림용 필터링 (거래량 기준)
        is_high_volume = item.get('volume', 0) >= MIN_VOLUME if market == "KOR" else True
        if not is_high_volume:
            continue
        
        is_boom = False
        is_crash = False
        
        if market == "KOR":
            is_boom = item.get('change_rate', 0) >= BOOM_THRESHOLD or item['rate'] >= BOOM_THRESHOLD
            is_crash = item['rate'] <= threshold
        elif market == "USA_OPEN":
            is_boom = item['rate'] >= US_BOOM_THRESHOLD
            is_crash = item['rate'] <= US_CRASH_THRESHOLD

        if is_boom:
            boom_candidates.append(item)
        elif is_crash:
            crash_candidates.append(item)

    # RSI 필터링 적용 (2차 필터)
    filtered_boom = filter_by_rsi(boom_candidates, is_boom=True)
    filtered_crash = filter_by_rsi(crash_candidates, is_boom=False)

    for item in filtered_boom + filtered_crash:
        # 뉴스 가져오기 (알림 대상 종목에 대해서만)
        ticker = item['code']
        if item.get('market') == 'KOR':
            ticker = f"{ticker}.KS"
        
        item['news'] = fetch_latest_news(ticker)
        
        item_id = f"{item['name']}_{item['date']}"
        add_to_pending_queue(item)
        history_data[item_id] = item['date']
        history_changed = True

    # 시간 변경 감지 및 요약 발송 로직 추가
    current_hour = now.hour
    last_summary_hour = bot_state.get("last_summary_hour", -1)

    if current_hour != last_summary_hour:
        if send_hourly_summary(current_hour):
            bot_state["last_summary_hour"] = current_hour
            state_changed = True

    # 한국 장 마감 요약
    if market == "KOR" and 1540 <= kst_time <= 1555 and f"SUMMARY_{today_str}" not in history_data:
        sorted_items = sorted(all_items, key=lambda x: x['rate'])[:5]
        if sorted_items:
            summary_msg = f"📝 *[장 마감 ETF 저평가 요약]*\n📅 {today_str}\n\n"
            for i, itm in enumerate(sorted_items, 1):
                summary_msg += f"{i}. *{itm['name']}*\n    └ 괴리율: `{itm['rate']}%` | 거래량: {itm['volume']:,}주\n"
            if send_telegram(summary_msg):
                history_data[f"SUMMARY_{today_str}"] = today_str
                history_changed = True

    if history_changed:
        try:
            atomic_write_json(history_file, history_data)
        except Exception as e:
            print(f"[-] 히스토리 파일 쓰기 에러: {e}")
            
    if state_changed:
        try:
            atomic_write_json(state_file, bot_state)
        except Exception as e:
            print(f"[-] 봇 상태 파일 쓰기 에러: {e}")

if __name__ == "__main__":
    main()
