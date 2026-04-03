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
    "save_text_file": true
  }'
```

`jq`가 있으면 결과를 보기 좋게 출력할 수 있습니다.

```bash
curl -s -X POST http://127.0.0.1:8000/crawl \
  -H "Content-Type: application/json" \
  -d '{"profile_url":"https://www.threads.com/@freainer","max_scrolls":80,"max_posts":1000,"batch_size":25,"headless":true,"save_text_file":true}' | jq .
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
  "service_version": "2026-04-03-batch-text-export-v5",
  "run_id": "20260403T101000Z-2fa13d2a",
  "profile_url": "https://www.threads.com/@freainer",
  "total_posts": 128,
  "saved_text_path": "data/threads_20260403T101000Z-2fa13d2a.txt",
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
