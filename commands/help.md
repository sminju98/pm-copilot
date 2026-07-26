---
description: pm-copilot 사용법 — 무슨 명령/무슨 말로 부르는지 전부 안내
---

아래 내용을 사용자에게 보기 좋게 그대로 정리해서 보여줘. (설정 안 됐으면 마지막에 "설정부터 도와드릴까요?"를 덧붙여)

## 🧭 기획 사수(PM Copilot) 사용법

**① 슬래시 명령 — 자주 쓰는 지름길**
- `/pm-copilot:setup` 첫 설정 · `/pm-copilot:brief` 오늘 브리핑 · `/pm-copilot:worklog` 업무일지🔒
- `/pm-copilot:review <내용>` 검사받기 · `/pm-copilot:spec <아이디어>` 기획서 · `/pm-copilot:weekly` 주간회고
- `/pm-copilot:standup` 팀현황🔒 · `/pm-copilot:learn` 오늘의 배움
- `/pm-copilot:qa` 배포 전 검수 · `/pm-copilot:voc` 고객의 소리 · `/pm-copilot:routine` 매일 자동 예약
- **모든 스킬은 이름 그대로도 됨**: `/pm-copilot:ramp-up`, `/pm-copilot:prioritize`, `/pm-copilot:project`, `/pm-copilot:gantt`, `/pm-copilot:roadmap`, `/pm-copilot:screen-spec`, `/pm-copilot:mockup`, `/pm-copilot:prototype` …

**② 자연어로도 됩니다 (슬래시 몰라도)**
- "오늘 브리핑 돌려줘" / "오늘 할 일 정리해줘" / "이 기획서 검사해줘"
- "우선순위 매겨줘" / "회의 준비해줘 · 회의록 정리해줘" / "이 지표 보고서 써줘"
- "온보딩 도와줘" / "이 문서 다듬어줘" / "A/B 실험 설계해줘"
- "이 결정 기록해줘" / "백로그에 적어둬" / "AI 활용법 알려줘"

**③ 얘가 먼저 챙깁니다 (선제 사수 — 하루 종일 여러 겹)**
- **세션 열면**: 오늘 브리핑·할 일·미결·묵힌 백로그, 예약 안 걸었으면 "예약 걸까요?"
- **요청할 때마다**: 상황 감지 → 맞는 사수 관점 선제 주입(기획엔 '왜'·비목표, 배포엔 QA·롤백 등)
- **작업물 저장할 때마다**: 사수가 즉석 검토 — 빠진 것·'왜' 약한 곳·블라인드스팟 먼저 짚음
- **하루 1~2회 체크인**(예약): 슬랙·노션·지라 등 현재 진도를 훑어 **"이거 이상한데?"** 이상 신호만 알림
- **세션 끝나면**: 오늘 한 일 업무일지 초안 자동 정리(로컬)
- **처음 깔았으면**: 먼저 "설정 도와드릴까요?" · 전부 끄기: `proactive.enabled=false`

**④ 전체 기능(38종)** — "무슨 기능 있어?"라고 물으면 카테고리별로 보여드림.

설정이 안 돼 있으면 → `/pm-copilot:setup` 또는 "기획 사수 설정 시작하자".
