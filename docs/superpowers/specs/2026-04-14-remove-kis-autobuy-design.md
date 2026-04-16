# Design: Remove KIS Auto-buy Functionality

**Date:** 2026-04-14
**Topic:** Remove KIS (Korea Investment & Securities) automatic buy/sell logic from the ETF monitor.

## 1. Overview
The goal is to remove all code related to automatic trading (buying/selling) via the KIS API while preserving the monitoring, reporting, and Telegram alerting capabilities.

## 2. Scope of Changes

### 2.1 `etf_monitor.py`
- **Constants:** Remove `BUY_UNIT_AMT`.
- **Functions to Delete:**
    - `get_kis_balance(token)`
    - `get_kis_holdings(token)`
    - `sell_order_kor(token, code, qty)`
    - `place_order_kor(token, code, price, qty=1)`
- **Logic to Modify:**
    - `handle_telegram_commands`: Remove commands related to trading (`/잔고`, `/balance`, `/보유`, `/holdings`, `/수익`, `/profit`).
    - `main`: Remove the KIS auto-buy logic (balance checks, asset replacement strategy, and order placement) within the monitoring loop.
    - Note: Keep `get_kis_access_token` and `check_korean_holiday` as they might still be used for holiday checks or other read-only API calls (though `check_korean_holiday` uses KIS API, it's not "auto-buy"). If holiday check is also not needed, we can remove it, but for now, I'll keep it as it's part of the monitor's schedule logic.

### 2.2 `.github/workflows/etf_alert.yml`
- Remove KIS-related environment variables from the `Run ETF Monitor Script` step (`KIS_APPKEY`, `KIS_SECRET`, `KIS_CANO`, `KIS_ACNT_PRDT_CD`, `KIS_URL_BASE`).

### 2.3 `.env.example`
- Remove KIS-related environment variables to reflect the current state of the project.

## 3. Architecture & Data Flow
- The application will continue to fetch ETF data from Naver Finance and US TOP 30 from Yahoo Finance.
- If thresholds are met, it will send a Telegram alert.
- It will no longer attempt to call KIS order APIs.

## 4. Verification Plan
- **Static Analysis:** Ensure no calls to deleted functions remain.
- **Manual Test:** Run `etf_monitor.py` (with dummy environment variables) to ensure it still fetches data and constructs messages correctly without crashing.
- **Git Push:** Push changes to the repository as requested.
