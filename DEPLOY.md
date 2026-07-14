# 배포 가이드 (Streamlit Community Cloud)

## 1. 무료 Postgres DB 만들기 (Supabase)

1. https://supabase.com 에서 무료 계정 생성 → 새 프로젝트 생성.
2. 프로젝트 생성 후 **Project Settings → Database → Connection string** 에서
   URI 복사 (`postgresql://postgres:[password]@...supabase.co:5432/postgres` 형태).
   `[password]`는 프로젝트 생성 시 설정한 DB 비밀번호로 직접 채워넣어야 합니다.

## 2. 기존 로컬 데이터 옮기기 (선택, 하지만 강력 추천)

지금까지 등록한 20명의 실제 선수 데이터/Seed Rating 이력을 새 DB로 그대로 옮깁니다.
로컬 PC에서 한 번만 실행:

```
python scripts/migrate_sqlite_to_postgres.py "위에서 복사한 postgresql://... 주소"
```

## 3. GitHub에 코드 올리기

로컬 git 저장소는 이미 준비되어 있습니다 (`git log`로 확인 가능). GitHub에서 새
저장소를 만든 뒤 (Public 또는 Private 상관없음, Streamlit Cloud는 둘 다 지원):

```
git remote add origin <GitHub 저장소 URL>
git branch -M main
git push -u origin main
```

## 4. Streamlit Community Cloud에 배포

1. https://share.streamlit.io 접속 → GitHub 계정으로 로그인.
2. "New app" → 방금 만든 저장소/브랜치 선택, **Main file path: `main.py`**.
3. "Advanced settings" → **Secrets**에 아래 입력:
   ```
   DATABASE_URL = "postgresql://postgres:[password]@...supabase.co:5432/postgres"
   ```
   (Riot API 키는 앱 사이드바에서 직접 입력하는 UI가 있으니 여기 넣지 않아도 됩니다 -
   다만 매번 새로 배포/재시작될 때마다 다시 입력해야 하는 건 그대로입니다.)
4. Deploy 클릭. 빌드가 끝나면 `https://<앱이름>.streamlit.app` 형태의 상시 접속 URL이 생깁니다.

## 참고

- **인증 없음**: 현재 "내 계정" 선택창은 비밀번호 없이 아무 이름이나 골라 그 사람 권한을
  그대로 가질 수 있습니다 (소규모 신뢰 그룹이라 지금은 그대로 배포하기로 결정함 - 나중에
  필요하면 간단한 PIN 게이트나 Streamlit Cloud의 이메일 초대 기능 추가 가능).
- **easyocr 의존성**: 무료 티어 리소스(RAM/CPU) 제한 때문에 빌드가 느리거나 실패할 수
  있습니다. 문제가 생기면 알려주세요 - OCR 기능을 지연 로딩하거나 선택적 의존성으로
  분리하는 방법이 있습니다.
- **데이터 지속성**: `DATABASE_URL`이 설정되어 있으면 앱은 자동으로 Postgres를 쓰고,
  로컬에서 그냥 실행하면 (`DATABASE_URL` 미설정) 여전히 로컬 SQLite(`data/app.db`)를
  씁니다 - 로컬 개발 워크플로우는 전혀 바뀌지 않습니다.
