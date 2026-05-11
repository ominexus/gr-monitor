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
import db_manager

# GitHub Secrets에서 환경 변수 불러오기
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
GOOGLE_SERVICE_ACCOUNT = os.getenv("GOOGLE_SERVICE_ACCOUNT") # JSON 스트링
GOOGLE_SHEET_ID = os.getenv("GOOGLE_SHEET_ID")
# -----------------

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

def calculate_indicators(ticker_symbol: str) -> Optional[Dict[str, Any]]:
    """주어진 티커의 RSI, MACD, MA 지표를 계산합니다."""
    try:
        ticker = yf.Ticker(ticker_symbol)
        df = ticker.history(period="3mo", interval="1d")
        
        if len(df) < 30:
            return None
            
        # 1. RSI (14)
        period = 14
        close = df['Close']
        delta = close.diff()
        gain = delta.where(delta > 0, 0)
        loss = -delta.where(delta < 0, 0)
        avg_gain = gain.ewm(alpha=1/period, min_periods=period, adjust=False).mean()
        avg_loss = loss.ewm(alpha=1/period, min_periods=period, adjust=False).mean()
        rs = avg_gain / avg_loss
        df['rsi'] = 100 - (100 / (1 + rs))
        
        # 2. MACD (12, 26, 9)
        exp1 = close.ewm(span=12, adjust=False).mean()
        exp2 = close.ewm(span=26, adjust=False).mean()
        df['macd'] = exp1 - exp2
        df['signal'] = df['macd'].ewm(span=9, adjust=False).mean()
        df['macd_hist'] = df['macd'] - df['signal']
        
        # 3. Moving Averages (5, 20)
        df['ma5'] = close.rolling(window=5).mean()
        df['ma20'] = close.rolling(window=20).mean()
        
        latest = df.iloc[-1]
        prev = df.iloc[-2]
        
        return {
            "rsi": round(float(latest['rsi']), 2),
            "macd": round(float(latest['macd']), 3),
            "signal": round(float(latest['signal']), 3),
            "macd_hist": round(float(latest['macd_hist']), 3),
            "macd_cross": (prev['macd'] < prev['signal']) and (latest['macd'] >= latest['signal']), # 골든크로스
            "ma5": round(float(latest['ma5']), 2),
            "ma20": round(float(latest['ma20']), 2),
            "ma_bullish": latest['ma5'] > latest['ma20'] # 정배열 초기
        }
        
    except Exception as e:
        print(f"[-] 지표 계산 실패 ({ticker_symbol}): {e}")
        return None

def filter_by_indicators(candidates: List[Dict[str, Any]], is_boom: bool) -> List[Dict[str, Any]]:
    """후보 종목들에 대해 복합 지표(RSI, MACD, MA) 필터링을 수행합니다."""
    if not candidates:
        return []

    print(f"[*] {len(candidates)}개 후보 종목에 대해 복합 지표 필터링 시작 (Boom: {is_boom})...")
    filtered: List[Dict[str, Any]] = []
    
    for item in candidates:
        ticker = item['code']
        if item.get('market') == 'KOR':
            ticker = f"{ticker}.KS"
            
        inds = calculate_indicators(ticker)
        if inds is None:
            continue
            
        item.update(inds)
        rsi = inds['rsi']
        
        if is_boom:
            # 급등/고평가: RSI 과매수(70+)
            if rsi >= 70:
                filtered.append(item)
                print(f"  [+] {item['name']} 통과 (RSI: {rsi})")
        else:
            # 급락/저평가: RSI 과매도(35 이하) + (MACD 골든크로스 OR RSI 극심한 과매도 25 이하)
            # 단순히 떨어지는 칼날을 잡는 게 아니라, 반등의 신호가 보일 때 알림
            if rsi <= 35:
                if inds['macd_cross'] or rsi <= 25 or inds['ma_bullish']:
                    filtered.append(item)
                    status = "GoldenCross" if inds['macd_cross'] else ("Extreme" if rsi <= 25 else "MA_Bullish")
                    print(f"  [+] {item['name']} 통과 (RSI: {rsi}, Signal: {status})")
                
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
    """트리거된 종목을 DB 대기열에 추가합니다."""
    # 중복 방지 (이름, 날짜, 시간 기준)는 db_manager 또는 호출부에서 처리 가능
    # 여기서는 기존 로직 유지를 위해 hour 추가
    now = datetime.now()
    if 'hour' not in item:
        item['hour'] = now.hour
    if 'timestamp' not in item:
        item['timestamp'] = now.strftime('%Y-%m-%d %H:%M:%S')
        
    db_manager.add_to_queue(item)

def get_pending_queue() -> List[Dict[str, Any]]:
    """대기열 데이터를 가져옵니다."""
    return db_manager.get_queue()

def clear_pending_queue() -> None:
    """대기열을 비웁니다."""
    db_manager.clear_queue()

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

def send_daily_report() -> bool:
    """당일 발생한 모든 알림을 요약하여 리포트로 발송합니다."""
    today_str = datetime.now().strftime('%Y-%m-%d')
    history = db_manager.get_all_history()
    
    # 오늘 데이터만 필터링
    today_data = [h for h in history if h.get('alert_date') == today_str]
    
    if not today_data:
        return send_telegram(f"📅 *[{today_str} 일일 요약]*\n\n오늘은 감지된 특이 종목이 없습니다. 평온한 하루였네요! ☕")

    # 통계 계산
    kor_count = len([h for h in today_data if h.get('market') == 'KOR'])
    usa_count = len([h for h in today_data if h.get('market') == 'USA'])
    avg_rsi = sum([h.get('rsi', 0) for h in today_data if h.get('rsi')]) / len([h for h in today_data if h.get('rsi')]) if today_data else 0

    report_msg = f"📊 *[ETF Monitor 일일 리포트 - {today_str}]*\n\n"
    report_msg += f"✅ *오늘의 요약*\n"
    report_msg += f"• 총 알림: `{len(today_data)}건` (🇰🇷 {kor_count} / 🇺🇸 {usa_count})\n"
    report_msg += f"• 평균 RSI: `{avg_rsi:.2f}`\n\n"

    # 시장별 주요 종목 (최대 3개씩)
    for m_code, m_name in [("KOR", "🇰🇷 한국 ETF"), ("USA", "🇺🇸 미국 주식")]:
        m_items = [h for h in today_data if h.get('market') == m_code]
        if m_items:
            report_msg += f"*{m_name} 주요 포착*\n"
            # 가격 변동폭이나 RSI 기준으로 정렬할 수 있으나 여기선 최신순 3개
            for h in m_items[:3]:
                signal = "🔥" if h.get('rsi', 50) > 70 else "❄️"
                report_msg += f"{signal} {h['name']} ({h['ticker']})\n"
                report_msg += f"   └ RSI: `{h.get('rsi', 'N/A')}` | MACD: `{h.get('macd_hist', 'N/A')}`\n"
            report_msg += "\n"

    report_msg += f"💡 _더 자세한 분석은 웹 대시보드에서 확인하세요!_\n"
    if GOOGLE_SHEET_ID:
        report_msg += f"🔗 [구글 시트 바로가기](https://docs.google.com/spreadsheets/d/{GOOGLE_SHEET_ID})"

    return send_telegram(report_msg)

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
    # 0. DB 초기화 및 마이그레이션
    db_manager.init_db()
    db_manager.migrate_from_json()
    
    state_changed = False

    # 1. 텔레그램 명령어 처리 (장 상태와 관계없이 실행)
    if TELEGRAM_TOKEN:
        # DB에서 last_update_id 가져오기
        last_id = int(db_manager.get_state("last_update_id", 0))
        temp_state = {"last_update_id": last_id}
        if handle_telegram_commands(TELEGRAM_TOKEN, temp_state):
            db_manager.set_state("last_update_id", temp_state["last_update_id"])
            state_changed = True

    # 2. 장 상태 확인
    market, kst_time = get_market_status()

    if market == "CLOSED":
        print(f"[-] 시장 마감: 명령어 확인 후 종료합니다.")
        return

    now = datetime.now()
    today_str = now.strftime('%Y-%m-%d')
    history_tag = f"SUMMARY_{today_str}"

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

    boom_candidates: List[Dict[str, Any]] = []
    crash_candidates: List[Dict[str, Any]] = []

    for item in all_items:
        item_id = f"{item['name']}_{item['date']}"
        
        # 이미 알림을 보낸 종목은 제외 (DB 조회)
        if db_manager.has_history(item_id):
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

    # 복합 지표(RSI, MACD, MA) 필터링 적용 (2차 필터)
    filtered_boom = filter_by_indicators(boom_candidates, is_boom=True)
    filtered_crash = filter_by_indicators(crash_candidates, is_boom=False)

    for item in filtered_boom + filtered_crash:
        # 뉴스 가져오기 (알림 대상 종목에 대해서만)
        ticker = item['code']
        if item.get('market') == 'KOR':
            ticker = f"{ticker}.KS"
        
        item['news'] = fetch_latest_news(ticker)
        
        # 대기열에 추가 및 히스토리에 기록 (DB)
        add_to_pending_queue(item)
        db_manager.add_history(item)

    # 시간 변경 감지 및 요약 발송 로직 추가
    current_hour = now.hour
    last_summary_hour = int(db_manager.get_state("last_summary_hour", -1))

    if current_hour != last_summary_hour:
        if send_hourly_summary(current_hour):
            db_manager.set_state("last_summary_hour", current_hour)
            state_changed = True

    # 한국 장 마감 요약 (기존)
    if market == "KOR" and 1540 <= kst_time <= 1555 and not db_manager.get_state(history_tag):
        sorted_items = sorted(all_items, key=lambda x: x['rate'])[:5]
        if sorted_items:
            summary_msg = f"📝 *[장 마감 ETF 저평가 요약]*\n📅 {today_str}\n\n"
            for i, itm in enumerate(sorted_items, 1):
                summary_msg += f"{i}. *{itm['name']}*\n    └ 괴리율: `{itm['rate']}%` | 거래량: {itm['volume']:,}주\n"
            if send_telegram(summary_msg):
                db_manager.set_state(history_tag, today_str)

    # 일일 종합 리포트 (추가)
    daily_report_tag = f"DAILY_REPORT_{today_str}"
    if 1630 <= kst_time <= 1700 and not db_manager.get_state(daily_report_tag):
        if send_daily_report():
            db_manager.set_state(daily_report_tag, today_str)

if __name__ == "__main__":
    main()
