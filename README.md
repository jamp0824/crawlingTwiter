# Threads 크롤링 서비스

`https://www.threads.com/@freainer` 같은 프로필의 게시물을 최대한 수집해서 API 응답(JSON)으로 바로 반환하는 FastAPI 서비스입니다.

## 1) 설치

```bash
python -m venv .venv
source .venv/bin/activate
which python
python -V
pip install -r requirements.txt
python -m playwright install
```

`which python` 결과가 프로젝트의 `.venv/bin/python` 이어야 합니다.

## 2) 실행

```bash
python -m uvicorn app:app --host 0.0.0.0 --port 8000
```

버전 확인:

```bash
curl -s http://127.0.0.1:8000/health
```

## 3) 사용

아래 JSON 블록은 **실행 명령이 아니라 응답 예시**입니다.  
터미널에는 `curl` 명령만 입력해야 합니다.

```bash
curl -X POST http://127.0.0.1:8000/crawl \
  -H "Content-Type: application/json" \
  -d '{
    "profile_url": "https://www.threads.com/@freainer",
    "max_scrolls": 40,
    "max_posts": 1000,
    "batch_size": 25,
    "headless": true,
    "save_text_file": true,
    "storage_state_path": null,
    "include_replies": true,
    "include_reposts": true
  }'
```

`jq`가 있으면 결과를 보기 좋게 출력할 수 있습니다.

```bash
curl -s -X POST http://127.0.0.1:8000/crawl \
  -H "Content-Type: application/json" \
  -d '{"profile_url":"https://www.threads.com/@freainer","max_scrolls":120,"max_posts":2000,"batch_size":25,"headless":true,"save_text_file":true,"storage_state_path":null,"include_replies":true,"include_reposts":true}' | jq .
```

결과를 파일로 보관하고 싶으면(선택):

```bash
curl -s -X POST http://127.0.0.1:8000/crawl \
  -H "Content-Type: application/json" \
  -d '{"profile_url":"https://www.threads.com/@freainer","max_scrolls":80,"max_posts":1000,"batch_size":25,"headless":true,"save_text_file":true}' > result.json
```

응답 예시(일부):

```json
{
  "service_version": "2026-04-03-sections-v7",
  "run_id": "20260403T101000Z-2fa13d2a",
  "profile_url": "https://www.threads.com/@freainer",
  "total_posts": 128,
  "saved_text_path": "data/threads_20260403T101000Z-2fa13d2a.txt",
  "storage_state_loaded": true,
  "posts": [
    {
      "url": "https://www.threads.com/@freainer/post/xxxx",
      "title": "....",
      "content": "....",
      "published_at": "2026-04-03T10:00:00.000Z",
      "images": []
    }
  ]
}
```

`save_text_file=true`로 실행하면 전체 크롤링 결과가 `data/threads_<run_id>.txt` 파일에 저장됩니다.

## 10개만 수집될 때 (중요)

Threads는 비로그인 상태에서 오래된 글 로딩이 제한되는 경우가 많고, 기본 프로필 탭에는 최신 글 일부만 보일 수 있습니다.

1) `max_scrolls`를 120~200으로 늘리고  
2) 가능하면 로그인 세션(storage_state)을 사용하고  
3) `include_replies=true`, `include_reposts=true`로 다른 탭까지 합쳐서 수집하세요.

### 1) 로그인 `state.json` 만들기

```bash
python scripts/create_storage_state.py
```

브라우저가 열리면 Threads에 직접 로그인하고, 터미널에서 Enter를 누르면 `state.json`이 저장됩니다.

### 2) 크롤러에서 `state.json` 사용하기

예시:

```bash
curl -s -X POST http://127.0.0.1:8000/crawl \
  -H "Content-Type: application/json" \
  -d '{"profile_url":"https://www.threads.com/@freainer","max_scrolls":160,"max_posts":3000,"batch_size":30,"headless":true,"save_text_file":true,"storage_state_path":"./state.json","include_replies":true,"include_reposts":true}' | jq .
```

응답의 `storage_state_loaded`가 `true`인지 꼭 확인하세요.

참고: 게시글 URL은 `https://www.threads.com/@아이디/post/...` 형태여야 정상입니다.

## 주의사항

- Threads는 동적 로딩/접근 제한/로그인 상태에 따라 수집량이 달라질 수 있습니다.
- 모든 게시물 수집이 보장되지는 않으므로 `max_scrolls`를 충분히 크게 설정하세요.
- 사이트 정책(robots, 약관, 법적 제한)을 확인하고 준수해야 합니다.

## 실행 중 `Executable doesn't exist` 에러가 날 때

아래처럼 **같은 Python 환경**에서 다시 설치하세요.

```bash
source .venv/bin/activate
which python
python -m playwright install
python -m uvicorn app:app --host 0.0.0.0 --port 8000
```

## URL이 `https://www.threads.com@...` 형태로 나오면

이 경우는 보통 **이전 서버 프로세스(구버전 코드)가 계속 실행 중**인 상태입니다.

```bash
# 서버 중지 (실행 중 터미널에서 Ctrl+C)
git pull
source .venv/bin/activate
python -m uvicorn app:app --host 0.0.0.0 --port 8000
```

그리고 현재 코드 버전 확인:

```bash
git log -1 --oneline
```
