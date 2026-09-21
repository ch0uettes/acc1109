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

## 알려진 제약 / 후속 작업

- **Riot API 키 임시 갱신 UX가 사라짐**: 기존 Streamlit 사이드바의 "새 키 붙여넣기"는
  같은 프로세스가 계속 떠 있다는 전제(in-memory override)로 동작했는데, 서버리스
  함수는 매 호출마다 새 프로세스일 수 있어 이 방식이 그대로는 안 통합니다. 지금은
  `RIOT_API_KEY` 환경변수를 Vercel 프로젝트 설정에서 직접 갱신 후 재배포하는 방식만
  됩니다 - 키가 24시간마다 만료되는 걸 감안하면 운영상 불편하므로, 나중에 DB에 저장된
  값을 우선 사용하도록 바꾸는 게 좋습니다.
- **Next.js 프론트엔드는 "참가자 관리" 1개 페이지만 구현됨**: 팀 생성/경기 저장/MVP
  투표/통계/서버 관리 페이지는 아직 없습니다. 백엔드 API(`app/api/routers/*`)는 이
  기능들을 전부 지원하니, UI만 같은 패턴으로 추가하면 됩니다.
- **OCR 스크린샷 업로드 UI 없음**: `POST /ocr/match-result` 등 백엔드 엔드포인트는
  준비돼 있지만, 프론트엔드에 업로드 폼이 아직 없습니다.
