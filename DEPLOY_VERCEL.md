# 배포 가이드 (Vercel)

> **참고**: 이 가이드는 이 세션의 샌드박스 환경에서 `api.vercel.com`으로의 아웃바운드 접근이
> 정책상 막혀 있어 실제 배포로 검증하지 못했습니다. 처음 배포 시 오류가 나면 알려주시면
> 바로 고쳐드리겠습니다.

## 구조

프론트엔드(Next.js, `web/`)와 백엔드(FastAPI, `api/` + `app/`)를 **별도의 Vercel
프로젝트 2개**로 배포합니다. 하나의 프로젝트에 억지로 합치는 것보다 훨씬 단순하고,
지난번 논의했던 OCR 등 "별도 서비스로 뺄 수 있는 부분은 뺀다" 방향과도 일치합니다.

```
acc1109/                 (저장소 루트)
├── app/                 Python 백엔드 도메인 로직 (기존 Streamlit 앱과 공유)
├── api/index.py         FastAPI Vercel 함수 엔트리포인트
├── requirements.txt     백엔드 프로젝트가 사용
├── vercel.json          백엔드 프로젝트 설정 (maxDuration 등)
└── web/                 Next.js 프론트엔드 (별도 Vercel 프로젝트로 배포)
```

## 1. 백엔드 프로젝트 (FastAPI, 저장소 루트 기준)

1. Vercel 대시보드 → New Project → 이 저장소 Import
2. **Root Directory는 비워두고(=저장소 루트) 그대로 Import** - `api/index.py`를
   Vercel이 자동으로 Python 함수로 인식합니다.
3. Environment Variables:
   | 변수 | 값 | 비고 |
   |---|---|---|
   | `DATABASE_URL` | Supabase **Transaction Pooler** 연결 문자열 (포트 6543) | 기존 Session pooler(5432)가 아니라 Transaction pooler를 써야 서버리스 다중 인스턴스에서 커넥션이 안 터집니다 |
   | `GOOGLE_VISION_API_KEY` | Google Cloud Vision API 키 | 미설정 시 OCR 자체가 비활성화됩니다 (Vercel엔 Tesseract 바이너리를 못 깔기 때문) |
   | `CORS_ALLOWED_ORIGINS` | 프론트엔드 프로젝트의 배포 URL (예: `https://your-frontend.vercel.app`) | 콤마로 여러 개 가능 |
   | `RIOT_API_KEY` | (선택) Riot 개발자 키 | 아래 "알려진 제약" 참고 |
   | `CURRENT_SEASON_LABEL` | (선택) 예: `2025-S2` | |
   | `SESSION_SECRET` | **필수.** 충분히 긴 무작위 문자열 (아래 명령으로 생성) | 접속 토큰 서명 키. 미설정 시 로그인 자체가 막힙니다. 바꾸면 전원 로그아웃됩니다 |
   | `SERVER_CREATION_CODE` | (선택) 새 서버를 만들 때 필요한 코드 | **미설정 시 Vercel에서는 새 서버 생성이 비활성화됩니다** - 외부인이 자기 서버를 만들어 OCR 등 유료 API를 쓰는 걸 막기 위함 |

   `SESSION_SECRET` 값 생성:
   ```bash
   python -c "import secrets; print(secrets.token_urlsafe(48))"
   ```
4. Deploy. 완료되면 `https://<백엔드 프로젝트>.vercel.app`이 API 베이스 URL입니다
   (`/health`로 확인 가능).

## 2. 프론트엔드 프로젝트 (Next.js, `web/`)

1. Vercel 대시보드 → New Project → 같은 저장소를 **다시** Import (별도 프로젝트로)
2. **Root Directory를 `web`으로 설정** - Next.js가 자동으로 감지됩니다.
3. Environment Variables:
   | 변수 | 값 |
   |---|---|
   | `NEXT_PUBLIC_API_BASE_URL` | 1단계에서 나온 백엔드 프로젝트 URL |
4. Deploy.

## 3. 입장 코드 / 관리자 PIN 도입 후 최초 1회 작업

모든 서버 API는 이제 접속 토큰이 있어야 호출됩니다. 토큰은 **서버 입장 코드**(전원)와
**개인 PIN**(Owner/Server Admin만)을 확인한 뒤 발급됩니다.

1. 운영 DB에 컬럼 추가 (재실행해도 안전):
   ```bash
   python scripts/migrate_2026_access_codes.py "<DATABASE_URL>"
   ```
2. 백엔드에 `SESSION_SECRET`을 설정하고 재배포합니다.
3. **배포 직후 Owner가 가장 먼저 입장**해서 PIN을 정합니다. 기존 관리자는 PIN이 없어서,
   처음 입장하는 사람이 입력한 PIN이 그대로 설정되기 때문입니다.
4. 서버 관리 → **입장 코드**를 설정하고, 멤버들에게 공유합니다. 설정 전까지는 코드 없이
   누구나 입장할 수 있습니다 (서버 관리 페이지에 경고가 뜹니다).
5. 다른 Server Admin들에게도 바로 입장해서 PIN을 정하라고 알립니다.

- 관리자가 PIN을 잊으면: Owner가 서버 관리 → 관리자 PIN 초기화
- Owner가 PIN을 잊으면: `python scripts/reset_member_pin.py <server_id> "<이름>" "<DATABASE_URL>"`
  실행 후 바로 다시 입장해서 새 PIN을 정합니다.

## 알려진 제약 / 후속 작업

- **일반 참가자끼리는 이름 사칭이 가능함**: 입장 코드를 아는 멤버는 다른 일반 참가자의
  이름으로 입장할 수 있습니다 (관리자 이름은 PIN 때문에 불가). 일반 참가자 권한은
  MVP 투표 정도라 영향이 작지만, 투표 조작이 문제가 되면 일반 참가자에게도 PIN을
  적용해야 합니다.

- **Riot API 키 임시 갱신 UX가 사라짐**: 기존 Streamlit 사이드바의 "새 키 붙여넣기"는
  같은 프로세스가 계속 떠 있다는 전제(in-memory override)로 동작했는데, 서버리스
  함수는 매 호출마다 새 프로세스일 수 있어 이 방식이 그대로는 안 통합니다. 지금은
  `RIOT_API_KEY` 환경변수를 Vercel 프로젝트 설정에서 직접 갱신 후 재배포하는 방식만
  됩니다 - 키가 24시간마다 만료되는 걸 감안하면 운영상 불편하므로, 나중에 DB에 저장된
  값을 우선 사용하도록 바꾸는 게 좋습니다.
- Next.js 프론트엔드는 Streamlit의 6개 페이지(참가자 관리/팀 생성/경기 기록(OCR 포함)/
  MVP 투표/통계/서버 관리)를 모두 구현했습니다.
