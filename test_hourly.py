import json
import os
from unittest.mock import patch
from etf_monitor import send_hourly_summary, clear_pending_queue
import db_manager

def test_hourly_summary_integration():
    print("=== Hourly Summary Integration Test Start ===")
    
    # 0. Initialize DB
    db_manager.init_db()
    
    # 1. Clear existing pending alerts
    clear_pending_queue()
    print("[1] Pending queue cleared.")

    # 2. Inject dummy data
    # KOR_CRASH: 6 items (to test "...외 N건")
    # KOR_BOOM: 2 items
    # USA_CRASH: 3 items
    # USA_BOOM: 1 item
    dummy_data = [
        # KOR CRASH (6 items)
        {"name": "KODEX 200", "rate": -3.5, "price": 35000, "market": "KOR", "date": "2026-05-08"},
        {"name": "TIGER 200", "rate": -4.2, "price": 34500, "market": "KOR", "date": "2026-05-08"},
        {"name": "KODEX 레버리지", "rate": -5.1, "price": 18000, "market": "KOR", "date": "2026-05-08"},
        {"name": "TIGER 미국나스닥100", "rate": -3.2, "price": 12000, "market": "KOR", "date": "2026-05-08"},
        {"name": "KODEX 삼성그룹", "rate": -3.8, "price": 9500, "market": "KOR", "date": "2026-05-08"},
        {"name": "TIGER 차이나전기차", "rate": -6.5, "price": 11000, "market": "KOR", "date": "2026-05-08"},
        
        # KOR BOOM (2 items)
        {"name": "KODEX 200선물인버스2X", "rate": 3.5, "price": 2500, "market": "KOR", "date": "2026-05-08"},
        {"name": "TIGER 인버스", "rate": 3.1, "price": 4500, "market": "KOR", "date": "2026-05-08"},
        
        # USA CRASH (3 items)
        {"name": "TSLA", "rate": -12.5, "price": 165.20, "market": "USA", "date": "2026-05-08"},
        {"name": "NVDA", "rate": -10.2, "price": 850.50, "market": "USA", "date": "2026-05-08"},
        {"name": "SOXL", "rate": -15.8, "price": 42.30, "market": "USA", "date": "2026-05-08"},
        
        # USA BOOM (1 item)
        {"name": "TQQQ", "rate": 11.2, "price": 58.40, "market": "USA", "date": "2026-05-08"}
    ]
    
    for item in dummy_data:
        db_manager.add_to_queue(item)
    print(f"[2] Injected {len(dummy_data)} dummy items into SQLite pending_queue.")

    # 3. Mock send_telegram and call send_hourly_summary
    print("[3] Calling send_hourly_summary(14)...")
    with patch('etf_monitor.send_telegram') as mock_send:
        mock_send.return_value = True
        
        success = send_hourly_summary(14)
        
        if success:
            print("[+] send_hourly_summary returned True.")
            if mock_send.called:
                sent_message = mock_send.call_args[0][0]
                print("\n--- SENT MESSAGE START ---\n")
                print(sent_message)
                print("\n--- SENT MESSAGE END ---\n")
                
                # Basic assertions on message content
                assert "14시" in sent_message
                assert "🇰🇷 한국 ETF 🚨 급락/저평가 (6건)" in sent_message
                assert "...외 1건" in sent_message
                assert "🇺🇸 미국 주식 🚨 급락/저평가 (3건)" in sent_message
                assert "🇺🇸 미국 주식 🚀 급등/고평가 (1건)" in sent_message
                assert "TSLA" in sent_message
                assert "KODEX 200" in sent_message
                print("[+] Message content verification passed.")
            else:
                print("[-] Error: send_telegram was NOT called.")
        else:
            print("[-] Error: send_hourly_summary returned False.")

    # 4. Verify queue is cleared
    queue = db_manager.get_queue()
    if not queue:
        print("[4] Pending queue verified as cleared after successful send.")
    else:
        print("[-] Error: Pending queue was NOT cleared.")

    print("=== Integration Test Completed ===")

if __name__ == "__main__":
    test_hourly_summary_integration()
