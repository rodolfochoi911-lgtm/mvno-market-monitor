# 모니터링 외부 예약 실행

GitHub의 `schedule` 이벤트 생성 지연을 우회하고 기존 `workflow_dispatch`를 호출한다.
크롤링과 기존 알림은 GitHub Actions에서 실행한다. 서버 대기와 크롤링 시간까지
없어지는 것은 아니며, 지정 시각은 수집 시작 목표다.

| 작업 | 한국 시간 | UTC |
|---|---|---|
| 시장 조사 | 매일 06:00 | 전날 21:00 |
| 경쟁사 프로모션 | 매일 06:07 / 15:12 | 전날 21:07 / 당일 06:12 |
| DC 행사 알림 | 매시 03/13/23/33/43/53분 | 동일한 분 |

## 배포와 전환

운영 환경은 `ENABLED=true`다. 새 계정에서 처음 구성할 때에는 먼저 설정 파일의
`ENABLED`를 문자열 `"false"`로 바꿔 비활성 상태로 배포한다.
기존 GitHub 예약은 저장소 변수 설정 전까지 계속 작동한다.

1. Cloudflare 계정으로 로그인한다: `npx wrangler login`.
2. GitHub에서 두 저장소 `mvno-market-monitor`, `competitor-monitor`만 선택한
   fine-grained token을 만든다. 저장소 권한은 **Actions: Read and write**다.
   만료일을 기록하고 만료 전 교체한다. 토큰을 파일이나 채팅에 붙이지 않는다.
3. 이 폴더에서 `npm test`, `npx wrangler deploy`로 비활성 Worker를 배포한다.
4. `npx wrangler secret put GITHUB_TOKEN`의 비공개 입력창에 토큰을 입력한다.
5. 이 폴더의 `wrangler.jsonc`에서 `ENABLED`를 문자열 `"true"`로 바꿔 재배포한다.
   Cron 설정 전파에는 최대 15분이 걸릴 수 있음을 고려한다.
6. `npx wrangler tail`에서 `accepted:true`를 확인하고 Actions에서 `workflow_dispatch`
   실행과 성공 여부를 확인한다. 실행 중인 같은 회차의 작업은 완료시킨다.
7. 외부 호출이 정상임을 확인한 다음 GitHub 두 저장소의 Settings → Secrets and
   variables → Actions → Variables에 `EXTERNAL_SCHEDULER_ENABLED=true`를 설정한다.
   이 변수는 GitHub 자체 예약만 건너뛰게 하며 수동/외부 호출은 허용한다.
   일일 실행 요약에 Cloudflare 예정/진단 시각이 표시된다.

전환 직전 같은 회차가 이미 실행됐거나 대기 중이면 중복 실행을 피하도록 그 회차
완료 후 다음 예약 전에 활성화한다. 동시 실행 그룹은 기존 값을 유지한다.

## 장애와 되돌리기

- HTTP 401/403: 토큰 만료, 저장소 선택, Actions 쓰기 권한을 확인한다.
- HTTP 422: 기본 브랜치의 workflow_dispatch 및 입력 이름을 확인한다.
- 네트워크 오류 뒤에는 POST 수신 여부가 불명확하므로 자동으로 다시 보내지 않는다.
  Actions에 실행이 생성됐는지 확인한 뒤 수동 실행한다.
- 5분 넘게 늦게 도착한 Cloudflare 이벤트는 밀린 실행을 다시 만들지 않고 실패한다.
- 원복은 Worker `ENABLED=false` 배포 후 두 저장소 변수를 `false`로 바꾼다.
  기존 상태 브랜치와 수집 데이터는 그대로 유지한다.
- 공개 HTTP 트리거는 제공하지 않는다. GitHub 토큰/응답 본문을 로그로 출력하지 않는다.
- Cloudflare 호출 성공은 실행 접수 확인이다. 수집 완료나 알림 도착 확인은 아니다.

검증: `npm test`. 모의 GitHub 응답만 사용하며 실제 알림을 보내지 않는다.

공식 문서:
- https://developers.cloudflare.com/workers/configuration/cron-triggers/
- https://developers.cloudflare.com/workers/configuration/secrets/
- https://docs.github.com/en/rest/actions/workflows#create-a-workflow-dispatch-event
