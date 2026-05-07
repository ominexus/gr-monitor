# ETF Monitor Improvements Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Improve code quality of `etf_monitor.py` by refining deduplication, exception handling, file I/O safety, and adding type hints.

**Architecture:** 
- Implement an `atomic_write_json` helper function to ensure data integrity.
- Refactor `add_to_pending_queue` for better deduplication efficiency.
- Standardize exception handling across all JSON operations and network calls.
- Apply PEP 484 type hints to all function signatures.

**Tech Stack:** Python 3, `os`, `json`, `datetime`, `tempfile`.

---

### Task 1: Add Helper for Atomic JSON Writes

**Files:**
- Modify: `C:\Users\user\Documents\gr-monitor\.worktrees\hourly-alerts\etf_monitor.py`

- [ ] **Step 1: Define `atomic_write_json` function**

Add this helper to the top of the file (after imports).

```python
import tempfile

def atomic_write_json(file_path: str, data: any) -> None:
    """Writes JSON data to a file atomically using a temporary file."""
    fd, temp_path = tempfile.mkstemp(dir=os.path.dirname(file_path), text=True)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        os.replace(temp_path, file_path)
    except Exception:
        if os.path.exists(temp_path):
            os.remove(temp_path)
        raise
```

- [ ] **Step 2: Commit**

```bash
git add etf_monitor.py
git commit -m "refactor: add atomic_write_json helper"
```

### Task 2: Improve Deduplication and Exception Handling in Queue Functions

**Files:**
- Modify: `C:\Users\user\Documents\gr-monitor\.worktrees\hourly-alerts\etf_monitor.py`

- [ ] **Step 1: Update `add_to_pending_queue`**
- Capture `now` once.
- Refine exception handling.
- Use `atomic_write_json`.
- Add type hints.

```python
def add_to_pending_queue(item: dict) -> None:
    """트리거된 종목을 대기열 파일에 추가합니다."""
    queue = []
    if os.path.exists(PENDING_ALERTS_FILE):
        try:
            with open(PENDING_ALERTS_FILE, "r", encoding="utf-8") as f:
                queue = json.load(f)
        except (json.JSONDecodeError, FileNotFoundError):
            queue = []
    
    now = datetime.now()
    current_hour = now.hour
    # Add timestamp to item for better tracking
    if 'timestamp' not in item:
        item['timestamp'] = now.strftime('%Y-%m-%d %H:%M:%S')
        item['hour'] = current_hour

    item_id = f"{item['name']}_{item['date']}_{current_hour}"
    
    if not any(f"{i['name']}_{i['date']}_{i.get('hour', -1)}" == item_id for i in queue):
        queue.append(item)
        atomic_write_json(PENDING_ALERTS_FILE, queue)
```

- [ ] **Step 2: Update `get_pending_queue`**
- Add type hints.
- Refine exception handling.
- Use `atomic_write_json`.

```python
from typing import List

def get_pending_queue() -> List[dict]:
    """대기열 데이터를 가져오고 파일을 비웁니다."""
    if not os.path.exists(PENDING_ALERTS_FILE):
        return []
    
    queue = []
    try:
        with open(PENDING_ALERTS_FILE, "r", encoding="utf-8") as f:
            queue = json.load(f)
    except (json.JSONDecodeError, FileNotFoundError):
        queue = []
    
    # 발송 준비를 위해 파일 초기화
    atomic_write_json(PENDING_ALERTS_FILE, [])
    return queue
```

- [ ] **Step 3: Commit**

```bash
git add etf_monitor.py
git commit -m "refactor: improve deduplication and exception handling in queue functions"
```

### Task 3: Standardize Exception Handling and Type Hints in Data Fetching

**Files:**
- Modify: `C:\Users\user\Documents\gr-monitor\.worktrees\hourly-alerts\etf_monitor.py`

- [ ] **Step 1: Update `fetch_realtime_etf_data`**
- Add type hints.
- Catch specific exceptions.

```python
def fetch_realtime_etf_data() -> List[dict]:
    """한국 ETF 데이터를 가져옵니다."""
    url = "https://finance.naver.com/api/sise/etfItemList.nhn"
    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        data = response.json()
        items = data.get("result", {}).get("etfItemList", [])
        results = []
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
```

- [ ] **Step 2: Update `fetch_us_opening_data`**
- Add type hints.

```python
def fetch_us_opening_data() -> List[dict]:
    # ... existing implementation with added type hint ...
```

- [ ] **Step 3: Update `get_market_status`**
- Add type hints.

```python
from typing import Tuple

def get_market_status() -> Tuple[str, int]:
    # ... existing implementation with added type hint ...
```

- [ ] **Step 4: Commit**

```bash
git add etf_monitor.py
git commit -m "refactor: add type hints and refine exception handling in fetch functions"
```

### Task 4: Final Refactoring of `main`, `handle_telegram_commands`, and `log_to_google_sheets`

**Files:**
- Modify: `C:\Users\user\Documents\gr-monitor\.worktrees\hourly-alerts\etf_monitor.py`

- [ ] **Step 1: Update `log_to_google_sheets`, `send_telegram`, and `handle_telegram_commands`**
- Add type hints.
- Use `atomic_write_json` for `bot_state.json`.

- [ ] **Step 2: Update `main`**
- Add type hints.
- Refine history loading/saving with `atomic_write_json`.

- [ ] **Step 3: Commit**

```bash
git add etf_monitor.py
git commit -m "refactor: apply remaining improvements and type hints"
```

### Task 5: Verification

- [ ] **Step 1: Check syntax and basic execution**

Run: `python -m py_compile etf_monitor.py`
Expected: No errors.

- [ ] **Step 2: Verify atomic writes**

Check if files are correctly updated after a mock run.

- [ ] **Step 3: Final Commit**

```bash
git commit -m "chore: final verification of code quality improvements"
```
