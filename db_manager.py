import sqlite3
import json
import os
import shutil
from typing import List, Dict, Any, Optional

DB_PATH = "monitor.db"

def get_connection():
    """데이터베이스 연결을 반환합니다."""
    return sqlite3.connect(DB_PATH)

def init_db():
    """데이터베이스와 테이블을 초기화합니다."""
    with get_connection() as conn:
        cursor = conn.cursor()
        
        # 1. 봇 상태 테이블
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS bot_state (
                key TEXT PRIMARY KEY,
                value TEXT
            )
        """)
        
        # 2. 대기열 테이블
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS pending_queue (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                item_data TEXT
            )
        """)
        
        # 3. 알림 이력 테이블 (상세 정보 포함)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS history (
                item_id TEXT PRIMARY KEY,
                name TEXT,
                ticker TEXT,
                market TEXT,
                alert_date TEXT,
                price REAL,
                rsi REAL,
                macd REAL,
                macd_hist REAL,
                macd_cross INTEGER,
                ma5 REAL,
                ma20 REAL,
                ma_bullish INTEGER,
                vol_ratio REAL,
                vol_spike INTEGER,
                extra_data TEXT
            )
        """)
        
        # 컬럼 추가 (기존 DB 마이그레이션 대응)
        try:
            cursor.execute("ALTER TABLE history ADD COLUMN macd REAL")
        except: pass
        try:
            cursor.execute("ALTER TABLE history ADD COLUMN macd_hist REAL")
        except: pass
        try:
            cursor.execute("ALTER TABLE history ADD COLUMN macd_cross INTEGER")
        except: pass
        try:
            cursor.execute("ALTER TABLE history ADD COLUMN ma5 REAL")
        except: pass
        try:
            cursor.execute("ALTER TABLE history ADD COLUMN ma20 REAL")
        except: pass
        try:
            cursor.execute("ALTER TABLE history ADD COLUMN ma_bullish INTEGER")
        except: pass
        try:
            cursor.execute("ALTER TABLE history ADD COLUMN vol_ratio REAL")
        except: pass
        try:
            cursor.execute("ALTER TABLE history ADD COLUMN vol_spike INTEGER")
        except: pass
            
        conn.commit()

def migrate_from_json():
    """기존 JSON 파일에서 데이터를 DB로 마이그레이션합니다."""
    
    # 1. bot_state.json
    if os.path.exists("bot_state.json"):
        try:
            with open("bot_state.json", "r") as f:
                data = json.load(f)
                for k, v in data.items():
                    set_state(k, str(v))
            shutil.move("bot_state.json", "bot_state.json.bak")
            print("[+] bot_state.json 마이그레이션 완료 및 백업 생성")
        except Exception as e:
            print(f"[-] bot_state.json 마이그레이션 실패: {e}")

    # 2. pending_alerts.json
    if os.path.exists("pending_alerts.json"):
        try:
            with open("pending_alerts.json", "r", encoding="utf-8") as f:
                queue = json.load(f)
                for item in queue:
                    add_to_queue(item)
            shutil.move("pending_alerts.json", "pending_alerts.json.bak")
            print("[+] pending_alerts.json 마이그레이션 완료 및 백업 생성")
        except Exception as e:
            print(f"[-] pending_alerts.json 마이그레이션 실패: {e}")

    # 3. notified_disclosures.json
    if os.path.exists("notified_disclosures.json"):
        try:
            with open("notified_disclosures.json", "r", encoding="utf-8") as f:
                history = json.load(f)
                with get_connection() as conn:
                    cursor = conn.cursor()
                    for key, date_str in history.items():
                        if key.startswith("SUMMARY_"):
                            # 요약 로그는 state에 저장하거나 무시
                            continue
                        # 기존 포맷은 item_id만 있었으므로 최소 데이터로 삽입
                        cursor.execute("""
                            INSERT OR IGNORE INTO history (item_id, alert_date)
                            VALUES (?, ?)
                        """, (key, date_str))
                    conn.commit()
            shutil.move("notified_disclosures.json", "notified_disclosures.json.bak")
            print("[+] notified_disclosures.json 마이그레이션 완료 및 백업 생성")
        except Exception as e:
            print(f"[-] notified_disclosures.json 마이그레이션 실패: {e}")

# --- Helper Functions ---

def get_state(key: str, default: Any = None) -> Optional[str]:
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT value FROM bot_state WHERE key = ?", (key,))
        row = cursor.fetchone()
        return row[0] if row else default

def set_state(key: str, value: Any):
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT OR REPLACE INTO bot_state (key, value) VALUES (?, ?)
        """, (key, str(value)))
        conn.commit()

def add_to_queue(item: Dict[str, Any]):
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("INSERT INTO pending_queue (item_data) VALUES (?)", (json.dumps(item, ensure_ascii=False),))
        conn.commit()

def get_queue() -> List[Dict[str, Any]]:
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT item_data FROM pending_queue")
        rows = cursor.fetchall()
        return [json.loads(row[0]) for row in rows]

def clear_queue():
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM pending_queue")
        conn.commit()

def add_history(item: Dict[str, Any]):
    """상세 정보를 포함하여 히스토리를 추가합니다."""
    item_id = f"{item['name']}_{item['date']}"
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT OR REPLACE INTO history 
            (item_id, name, ticker, market, alert_date, price, rsi, 
             macd, macd_hist, macd_cross, ma5, ma20, ma_bullish, vol_ratio, vol_spike)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            item_id,
            item.get('name'),
            item.get('code'),
            item.get('market'),
            item.get('date'),
            item.get('price'),
            item.get('rsi'),
            item.get('macd'),
            item.get('macd_hist'),
            item.get('macd_cross'),
            item.get('ma5'),
            item.get('ma20'),
            item.get('ma_bullish'),
            item.get('vol_ratio'),
            item.get('vol_spike')
        ))
        conn.commit()

def has_history(item_id: str) -> bool:
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT 1 FROM history WHERE item_id = ?", (item_id,))
        return cursor.fetchone() is not None

def get_all_history() -> List[Dict[str, Any]]:
    with get_connection() as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM history")
        rows = cursor.fetchall()
        return [dict(row) for row in rows]
