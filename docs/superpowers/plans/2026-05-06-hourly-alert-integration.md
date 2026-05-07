# Hourly Alert Integration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** ETF 및 미국 주식 변동성 알림을 10분마다 개별 발송하던 방식에서 1시간 단위로 통합 발송하는 방식으로 변경하여 알림 과부하 해결.

**Architecture:** 
1. `pending_alerts.json` 파일을 사용하여 10분 단위의 트리거 데이터를 임시 저장.
2. `bot_state.json`의 `last_summary_hour`를 확인하여 매 시 정각(또는 시간 변경 시)에 통합 메시지 발송.
3. 실시간 구글 시트 기록은 유지하여 데이터 보존성 확보.

**Tech Stack:** Python 3.10, Telegram Bot API, JSON storage.

---

### Task 1: 전역 변수 및 유틸리티 함수 추가

**Files:**
- Modify: `etf_monitor.py`

- [ ] **Step 1: 파일 경로 상수 및 큐 관리 함수 추가**

```python
PENDING_ALERTS_FILE = "pending_alerts.json"

def add_to_pending_queue(item):
    """트리거된 종목을 대기열 파일에 추가합니다."""
    queue = []
    if os.path.exists(PENDING_ALERTS_FILE):
        with open(PENDING_ALERTS_FILE, "r", encoding="utf-8") as f:
            try: queue = json.load(f)
            except: queue = []
    
    # 중복 방지 (이름과 날짜/시간 기준)
    item_id = f"{item['name']}_{item['date']}_{datetime.now().hour}"
    if not any(f"{i['name']}_{i['date']}_{datetime.now().hour}" == item_id for i in queue):
        queue.append(item)
        with open(PENDING_ALERTS_FILE, "w", encoding="utf-8") as f:
            json.dump(queue, f, ensure_ascii=False, indent=2)

def get_pending_queue():
    """대기열 데이터를 가져오고 파일을 비웁니다."""
    if not os.path.exists(PENDING_ALERTS_FILE):
        return []
    with open(PENDING_ALERTS_FILE, "r", encoding="utf-8") as f:
        try: queue = json.load(f)
        except: queue = []
    
    # 발송 준비를 위해 파일 초기화
    with open(PENDING_ALERTS_FILE, "w", encoding="utf-8") as f:
        json.dump([], f)
    return queue
```

- [ ] **Step 2: 커밋**

```bash
git add etf_monitor.py
git commit -m "feat: add pending queue utility functions"
```

---

### Task 2: 알림 통합 발송 로직 구현

**Files:**
- Modify: `etf_monitor.py`

- [ ] **Step 1: `send_hourly_summary` 함수 구현**

```python
def send_hourly_summary(market, current_hour):
    """대기열에 쌓인 데이터를 통합하여 발송합니다."""
    queue = get_pending_queue()
    if not queue:
        return

    # 시장별/유형별 그룹화
    categories = {
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
            summary_msg += f"• {itm['name']}: `{itm['rate']}%` ({itm['price']:,}원/USD)\n"
        
        if len(items) > 5:
            summary_msg += f"  ...외 {len(items) - 5}건\n"
        summary_msg += "\n"

    if has_content:
        summary_msg += f"🔗 [상세 데이터(구글 시트) 확인](https://docs.google.com/spreadsheets/d/{GOOGLE_SHEET_ID})"
        send_telegram(summary_msg)
```

- [ ] **Step 2: 커밋**

```bash
git add etf_monitor.py
git commit -m "feat: implement hourly summary formatting and sending"
```

---

### Task 3: 메인 루프 수정 및 통합

**Files:**
- Modify: `etf_monitor.py`

- [ ] **Step 1: `main()` 함수에서 개별 알림 대신 큐에 추가하도록 수정**

기존 `send_telegram(msg)` 호출 부분을 `add_to_pending_queue(item)`으로 대체합니다.

- [ ] **Step 2: 시간 변경 감지 및 요약 발송 로직 추가**

```python
    # main() 함수 내 장 상태 확인 이후
    current_hour = now.hour
    last_summary_hour = history_data.get("last_summary_hour", -1)

    if current_hour != last_summary_hour:
        send_hourly_summary(market, current_hour)
        history_data["last_summary_hour"] = current_hour
        new_notified = True
```

- [ ] **Step 3: 커밋**

```bash
git add etf_monitor.py
git commit -m "feat: integrate hourly summary logic into main loop"
```

---

### Task 4: 검증 및 테스트

- [ ] **Step 1: 더미 데이터를 이용한 통합 테스트 스크립트 작성 및 실행**

`test_hourly.py`를 작성하여 `pending_alerts.json`에 가짜 데이터를 넣고 `send_hourly_summary`를 강제 호출해 봅니다.

- [ ] **Step 2: 결과 확인**

텔레그램 메시지가 그룹화되어 예쁘게 오는지 확인합니다.

- [ ] **Step 3: 커밋 및 정리**

```bash
git add test_hourly.py
git commit -m "test: add integration test for hourly summary"
```
