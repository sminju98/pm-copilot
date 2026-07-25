---
name: weekly-review
description: 한 주를 회고하는 주간 브리핑을 만든다. 이번 주 한 것/못 한 것/배운 것과 다음 주 계획, 반복되는 패턴까지 정리한다. "주간 회고 / 위클리 리뷰 / 이번 주 정리 / 주간 브리핑" 요청 시, 또는 금요일 예약 실행.
---

# 주간 회고 브리핑 (반자동)

데일리가 매일의 리듬이라면, 위클리는 한 발 물러나 **패턴**을 본다.

## 1. 재료 모으기
```bash
ls "${PM_COPILOT_HOME:-$HOME/.pm-copilot}/data/briefs/" 2>/dev/null            # 이번 주 데일리 브리핑들
cat "${PM_COPILOT_HOME:-$HOME/.pm-copilot}/data/context.md" 2>/dev/null        # 목표·로드맵
python3 "$CLAUDE_PLUGIN_ROOT/scripts/journal.py" --log decision --list --since 7   # 이번 주 결정
```
커넥터(노션/Jira)가 있으면 이번 주 완료/이동 티켓도 읽는다. 없으면 위 로컬 자료로.

## 2. 출력 구조 (각 항목에 '왜')
1. **한 주 한 줄 요약** — 이번 주는 결국 무엇에 관한 주였나.
2. **한 일 (계획 대비)** — 완료/진척. 계획했는데 못 한 것은 **왜 어긋났는지** 짚는다(추측 금지, 사실+가정 구분).
3. **지표 변화** — 확인된 것만. 없으면 "확인 필요".
4. **배운 것 / 인사이트** — 이번 주 새로 알게 된 것.
5. **🔁 반복되는 패턴(코칭)** — 여러 날에 걸쳐 반복된 블로커·미룬 결정·놓친 습관. **다음 주에 바꿀 한 가지.**
6. **다음 주 계획** — 우선순위 Top 3 + 그 이유. 미룬 것 중 이제 할 것.

## 3. 전송
- 기본 **개인본(private)**. 팀 공유가 필요하면 민감내용(팀원 개별 평가 등) 빼고 team으로.
```bash
# 연결된 Slack 커넥터로 delivery.private.slack_channel 에 게시(우선). 폴백:
python3 "$CLAUDE_PLUGIN_ROOT/scripts/post_slack.py" --to private --title "주간 회고: <기간>" --file <초안> --dry-run
```
- 대화형이면 초안 확인 후 전송, 예약(금요일)이면 바로 전송(`common.is_scheduled()`).

## 원칙
근거·출처 · 반자동(사람 검토) · 왜를 항상 설명 · 회고는 자책이 아니라 **다음 주 개선**으로 연결.
