# Remove KIS Auto-buy Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remove KIS automatic buy/sell functionality from the ETF monitor script and associated infrastructure while maintaining monitoring and alerting.

**Architecture:** Surgical removal of trading functions and conditional logic in `etf_monitor.py`. Cleanup of CI/CD and example configuration.

**Tech Stack:** Python, GitHub Actions

---

### Task 1: Clean up `etf_monitor.py` - Constants and Functions

**Files:**
- Modify: `etf_monitor.py`

- [ ] **Step 1: Remove `BUY_UNIT_AMT` constant.**
- [ ] **Step 2: Delete functions `get_kis_balance`, `get_kis_holdings`, `sell_order_kor`, `place_order_kor`.**
- [ ] **Step 3: Commit.**

```bash
git add etf_monitor.py
git commit -m "refactor: remove KIS trading constants and functions"
```

### Task 2: Clean up `etf_monitor.py` - Logic

**Files:**
- Modify: `etf_monitor.py`

- [ ] **Step 1: Modify `handle_telegram_commands` to remove trading commands (/잔고, /보유, /수익).**
- [ ] **Step 2: Modify `main` to remove the auto-buy/sell block.**
- [ ] **Step 3: Commit.**

```bash
git add etf_monitor.py
git commit -m "refactor: remove KIS trading logic from main loop and telegram commands"
```

### Task 3: Clean up Infrastructure and Documentation

**Files:**
- Modify: `.github/workflows/etf_alert.yml`
- Modify: `.env.example`

- [ ] **Step 1: Remove KIS secrets from `.github/workflows/etf_alert.yml`.**
- [ ] **Step 2: Remove KIS variables from `.env.example`.**
- [ ] **Step 3: Commit.**

```bash
git add .github/workflows/etf_alert.yml .env.example
git commit -m "chore: remove KIS trading environment variables"
```

### Task 4: Verification and Push

**Files:**
- [ ] **Step 1: Run `python etf_monitor.py` (dry run).**
Verify it doesn't crash and correctly identifies "CLOSED" or "KOR" status (with mock env vars if needed).
- [ ] **Step 2: Push to remote.**

```bash
git push
```

### Task 5: Final KIS Decoupling (Bug Fix)

**Files:**
- Modify: `etf_monitor.py`

- [ ] **Step 1: Remove `check_korean_holiday`, `get_portfolio_profit`, and `get_kis_access_token` functions.**
- [ ] **Step 2: Remove KIS-related logic from `main` and `handle_telegram_commands`.**
- [ ] **Step 3: Commit.**

```bash
git add etf_monitor.py
git commit -m "refactor: completely decouple from KIS API"
```
