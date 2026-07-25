---
name: setup
description: 기획 사수(PM 데일리 브리핑)를 처음 쓰기 위한 설정을 클로드가 대화로 끝까지 안내한다. "기획 사수 설정 / 셋업 / 처음 사용 / 브리핑 설정 / 설정 계속" 등에 사용. 비개발자도 파일이나 JSON을 직접 건드리지 않고 채팅만으로 설정을 끝낼 수 있게 한다.
---

> **작업 흐름(항상):** 기존 컨텍스트(자료·채널·채팅) 점검 + 리서치 → 기획 → 시각화 → 스킬 호출/실행. 자세히 [[method]].

# 기획 사수 첫 설정 — 클로드가 대신 다 해준다

## 절대 원칙
1. **사용자는 파일·JSON·터미널을 직접 건드리지 않는다.** 값은 네가 채팅으로 묻고, 받은 값을 `set_config.py`로 저장한다. 컨텍스트 문서는 네가 대신 써 준다.
2. **한 번에 하나씩, 아주 쉬운 말로.** "웹훅", "커넥터", "크론" 같은 용어는 풀어서 설명한다.
3. 어려운 단계는 언제든 **"지금은 건너뛰기"** 를 제안한다. 나중에 이어서 할 수 있다.
4. **프라이버시**: 팀원 현황(누가 뭘 했는지)은 **오직 '나만 보는 곳'** 으로만 간다. 이 점을 설정 중에 분명히 안내한다.

## 너의 도구
```bash
python3 "$CLAUDE_PLUGIN_ROOT/scripts/doctor.py"                          # 지금 상태 확인
python3 "$CLAUDE_PLUGIN_ROOT/scripts/set_config.py" me.name="홍길동"      # 값 저장(여러 개 한 번에)
python3 "$CLAUDE_PLUGIN_ROOT/scripts/schedule_brief.py"                  # 예약 등록 문구 보기
```
웹훅·토큰 같은 민감값도 `set_config.py`로 저장하면 화면에는 가려져 표시된다.
설정과 데이터는 **`~/.pm-copilot/`** 에 저장되어 플러그인을 업데이트/재설치해도 유지된다.

> **⚡ 빠른 길:** 사용자가 슬랙 웹훅을 이미 가지고 있으면 아래 한 줄로 config 생성·검증·테스트 발송까지 끝난다. 이후 컨텍스트만 채우면 된다.
> ```bash
> python3 "$CLAUDE_PLUGIN_ROOT/scripts/quicksetup.py" --private "<나만보기 웹훅>" [--team "<팀 웹훅>"] --name "이름" --product "제품명"
> ```

## 진행 순서

### 0단계. 인사 + 큰 그림
먼저 `doctor.py`로 상태를 보고, 이 플러그인이 뭘 해주는지 한 문장으로 설명한다:
> "매일 아침 ①우리 프로덕트/프로젝트 현황 피드백 ②경쟁사·업계·테크뉴스 리서치+메일 정리 ③팀원별 한일/할일(**이건 대표님만 보임**) ④오늘 뭘 챙겨야 하는지 인사이트 — 이걸 슬랙으로 딱 정리해 드려요. 5분이면 설정 끝나요."

동작 방식도 한 문장 덧붙인다:
> "제가 대신 초안을 만들고, 대표님은 **검토·수정만** 하시면 돼요(반자동). 주고받으며 같이 다듬는 방식이라, 그대로 나가는 게 아니에요."

### 1단계. 나 + 프로덕트 (제일 쉬움, 항상 먼저)
채팅으로 물어 저장한다: 이름 / 역할 / 프로덕트 이름 / 한 줄 소개 / 현재 단계 / 핵심 지표.
```bash
python3 "$CLAUDE_PLUGIN_ROOT/scripts/set_config.py" \
  me.name="홍길동" me.role="프로덕트 기획자" \
  product.name="우리서비스" product.one_liner="직장인용 일정관리 앱" \
  product.stage="MVP 출시 직후" product.north_star="주간 활성 사용자(WAU)"
```
잘 모르면 "나중에 채워도 돼요" 하고 넘어간다.

### 2단계. 어디로 받고 무엇을 읽을지 — 커넥터 연결이 제일 쉬움
슬랙 웹훅은 사용자가 직접 만들어야 해서 번거롭고 **내가 대신 못 눌러준다.** **claude.ai 커넥터**로 연결하면 **클릭 한 번**이니 이걸 먼저 권한다:
1. `claude.ai → 설정 → 커넥터(Connectors)` 에서 **Slack** 연결(OAuth). 팀 활동·컨텍스트를 읽히려면 **Notion·Jira** 도 연결.
2. **어느 채널로 보낼지**만 묻는다: 나만 보기용 채널/DM(필수) + 팀 공유용 채널(선택). (팀원 소스는 커넥터에서 **자동 탐색**하므로 매핑 안 시킨다.)
3. 저장:
   ```bash
   python3 "$CLAUDE_PLUGIN_ROOT/scripts/set_config.py" \
     delivery.private.enabled=true delivery.private.slack_channel="#나만보는채널" \
     delivery.team.enabled=false   delivery.team.slack_channel="#팀채널"
   ```
- 커넥터 연결(OAuth)은 **이 세션에서 대신 못 눌러준다** — 사용자가 claude.ai에서 직접.
- **🔒 팀원 현황(③)은 나만 보기 채널로만** — 팀 채널로 절대 안 나감. 반드시 안내.
- **매일 아침 자동(맥 꺼져도)** 을 원하면 커넥터가 필수다 — 클라우드 루틴은 로컬 config·웹훅을 못 보고 **GitHub 저장소 + 계정 커넥터**로만 돈다(5단계).

**(폴백) 커넥터를 못 쓰면** 슬랙 Incoming Webhook: `api.slack.com/apps → Create App → Incoming Webhooks On → Add to channel → URL 복사` → `set_config delivery.<team|private>.slack_webhook="URL"`.

**⚠️ 슬랙 앱 생성이 막히면:** 회사 워크스페이스는 커스텀 앱 설치에 관리자 승인이 필요할 수 있다. 막히면 (a) 관리자에게 "Incoming Webhook 앱 승인"을 요청하도록 안내하고, (b) 그동안은 전송 없이 **채팅으로 브리핑 미리보기만** 받는 경로로 진행한다(설정 완료를 막지 않는다).

**✅ 전송 검증(꼭 한다):** 웹훅 2개는 URL이 거의 똑같아 팀/개인을 뒤바꿔 붙이기 쉽다(그러면 팀원 현황이 팀에 노출됨). 저장 직후 각 웹훅으로 라벨 테스트를 보내고, 사용자가 슬랙에서 맞는 채널에 왔는지 눈으로 확인하게 한다:
```bash
python3 "$CLAUDE_PLUGIN_ROOT/scripts/post_slack.py" --to team    --title "설정확인" --text "이 채널은 [팀 공유]입니다."
python3 "$CLAUDE_PLUGIN_ROOT/scripts/post_slack.py" --to private --title "설정확인" --text "이 채널은 [나만 보기]입니다."
```
"팀 채널엔 [팀 공유]가, 개인 채널엔 [나만 보기]가 도착했다"고 확인한 뒤에만 진행한다. 뒤바뀌었으면 두 웹훅을 서로 바꿔 다시 저장한다.

### 3단계. 무엇을 읽게 할지 (리서치·소스)
브리핑이 참고할 소스를 고른다.
- **웹 리서치**(경쟁사·테크뉴스): 기본 켬. `sources.use_web=true`
- **업무 메일 분석**: 켜려면 `sources.use_email=true`. 단, **메일을 읽으려면 Gmail을 claude.ai 계정 커넥터로 연결**해야 한다(뒤 '커넥터 안내' 참고).
- **노션(프로젝트/태스크)**: `sources.use_notion=true` + 노션 커넥터 연결.
```bash
python3 "$CLAUDE_PLUGIN_ROOT/scripts/set_config.py" sources.use_web=true sources.use_email=false sources.use_notion=false
```
> **커넥터 안내(꼭 설명):** 메일·노션 읽기는 **claude.ai 로그인 → 설정 → 커넥터(Connectors)** 에서 한 번 연결해두면, 예약 자동 실행에서도 클로드가 읽을 수 있다. **이 채팅 세션에서는 대신 로그인해 줄 수 없으니**, 사용자가 claude.ai에서 직접 연결하도록 안내한다. 연결 안 해도 **웹 리서치 + 아래 컨텍스트 문서**만으로 브리핑은 돌아간다.

> **데이터 경계(중요):** 회사 데이터를 AI에 함부로 넣지 않는다. 이 플러그인은 **회사가 승인한 커넥터**를 통해서만 내부 데이터를 읽고, 민감한 컨텍스트는 이 컴퓨터의 `data/context.md`(git 제외)에 로컬로만 둔다. 웹 리서치 검색어에 회사 기밀·미공개 코드명을 넣지 않는다. 애매하면 조직 정책·보안팀 기준을 우선한다.

### 4단계. 컨텍스트 문서 채우기 (브리핑 품질의 핵심)
프로덕트 현황·경쟁사·로드맵·팀원 명단을 적어두는 문서를 만든다. **네가 대신 만들고 채운다.**
1. 템플릿을 복사:
   ```bash
   mkdir -p ~/.pm-copilot/data && cp "$CLAUDE_PLUGIN_ROOT/templates/context.example.md" ~/.pm-copilot/data/context.md
   ```
2. 사용자에게 대화로 물어(현재 집중 과제, 최근 지표, 경쟁사 2~3곳, 이번 분기 목표, 팀원 이름/역할/그 사람들 업데이트가 어디 쌓이는지) **네가 `data/context.md`를 직접 편집**해 채운다.
3. 한 번에 다 못 채워도 된다. "일단 아는 것만" 채우고 넘어간다. 나중에 "컨텍스트 업데이트하자"로 이어서.

> 팀원 명단은 이 문서의 **## 팀** 섹션에 적는다(이름·역할·업데이트 위치). 팀원 현황(③)은 여기 적힌 사람들 기준으로 만든다.

### 5단계. 매일 언제 받을지 (예약)
```bash
python3 "$CLAUDE_PLUGIN_ROOT/scripts/set_config.py" brief.schedule="0 9 * * 1-5"   # 평일 오전 9시
python3 "$CLAUDE_PLUGIN_ROOT/scripts/schedule_brief.py"                            # 등록 문구 출력
```
출력된 안내대로 **`/schedule`** 로 등록하거나 `claude.ai/code/routines`에서 루틴을 만든다. (자동 등록을 원하면, 이 세션의 스케줄 기능으로 "평일 오전 9시에 기획 사수 데일리 브리핑 실행"을 등록해 주겠다고 제안한다.)

### 마무리
1. 위 **전송 검증**(라벨 테스트가 맞는 채널에 도착)이 끝났는지 확인한다. 안 끝났으면 `setup.completed`를 켜지 않는다.
2. 팀원 현황(③)을 쓸 거면 **한 번만** 안내한다:
   > "팀원 현황은 대표님만 보지만, 팀원 업무기록을 요약하는 기능이에요. 팀에 사용 사실을 알리고, 개인정보·근로 감시 관련 사내 정책을 확인한 뒤 쓰시는 걸 권장해요. 성과 평가·징계용은 아니에요."
3. `doctor.py`로 ✅ 확인 후 저장:
```bash
python3 "$CLAUDE_PLUGIN_ROOT/scripts/set_config.py" setup.completed=true
```
그리고 제안한다:
> "설정 끝났어요! **지금 첫 브리핑을 한 번 미리 돌려볼까요?** '오늘 브리핑 미리 돌려줘'라고 해보세요 — 실제 전송 전에 초안을 먼저 보여드릴게요."
```
