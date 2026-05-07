# Design Spec: Hourly Alert Integration for ETF Monitor

## 1. 개요 (Overview)
현재 10분마다 실행되는 알림 시스템이 대량의 개별 메시지를 전송하여 발생하는 정보 과부하 문제를 해결하기 위해, 1시간 단위로 알림을 통합하여 발송하는 시스템을 설계함.

## 2. 목표 (Goals)
- 텔레그램 알림 빈도를 1/6로 감소 (10분 -> 1시간).
- 다수의 알림을 하나의 구조화된 메시지로 통합하여 가독성 향상.
- 실시간 데이터 기록(구글 시트)은 유지하여 데이터 손실 방지.

## 3. 상세 설계 (Detailed Design)

### 3.1 대기열 관리 (`pending_alerts.json`)
- 10분마다 실행되는 크론 잡에서 발견된 알림 대상 종목들을 즉시 발송하지 않고 `pending_alerts.json`에 저장함.
- 저장 데이터 구조:
  ```json
  [
    {
      "market": "KOR",
      "type": "CRASH",
      "name": "KODEX 200",
      "code": "069500",
      "rate": -3.5,
      "price": 32500,
      "volume": 1200000,
      "timestamp": "2026-05-06 10:10"
    },
    ...
  ]
  ```

### 3.2 시간 단위 발송 트리거
- `bot_state.json`에 `last_summary_hour` 필드를 추가하여 마지막 발송 시간을 추적함.
- 매 실행 시 `현재 시간(hour)`과 `last_summary_hour`를 비교.
- 시간이 변경되었을 경우(예: 10 -> 11) 통합 알림을 발송하고 대기열을 초기화함.

### 3.3 메시지 구성 및 포맷
- **그룹화:** 시장(한국/미국) 및 상태(급등/급락)별로 그룹핑.
- **필터링:** 각 그룹 내에서 변동폭(절대값)이 큰 상위 5개 종목만 상세 정보를 노출.
- **요약:** 상위 5개 외의 종목은 "그 외 N건"으로 요약 표시.
- **형식:** 텔레그램 MarkdownV2 또는 HTML 형식을 사용하여 깔끔하게 포맷팅.

### 3.4 데이터 흐름 (Data Flow)
1. `fetch_data` -> 2. `identify_triggers` -> 3. `log_to_sheets` (즉시) -> 4. `add_to_pending_queue` -> 5. `check_hour_change` -> 6. `send_summary_if_needed` -> 7. `clear_queue_and_update_state`.

## 4. 예외 처리 (Error Handling)
- `pending_alerts.json` 파일이 없거나 손상된 경우 자동으로 새로 생성함.
- 텔레그램 전송 실패 시 대기열을 유지하고 다음 실행 때 재시도하도록 설계.

## 5. 테스트 계획 (Testing)
- 단위 테스트: 특정 데이터 셋이 주어졌을 때 올바른 요약 메시지가 생성되는지 확인.
- 통합 테스트: 가상 시간 변경을 시뮬레이션하여 1시간 주기로 발송되는지 확인.
