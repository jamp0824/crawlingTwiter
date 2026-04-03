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

## 3) 사용

```bash
curl -X POST http://127.0.0.1:8000/crawl \
  -H "Content-Type: application/json" \
  -d '{
    "profile_url": "https://www.threads.com/@freainer",
    "max_scrolls": 40,
    "headless": true
  }'
```

응답 예시(일부):

```json
{
  "run_id": "20260403T101000Z-2fa13d2a",
  "profile_url": "https://www.threads.com/@freainer",
  "total_posts": 128,
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
