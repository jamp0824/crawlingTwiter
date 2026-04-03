from __future__ import annotations

import asyncio
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlparse
from uuid import uuid4

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from playwright.async_api import Browser, Error as PlaywrightError, Page, async_playwright


THREAD_LINK_RE = re.compile(r"^/?@[^/]+/post/[A-Za-z0-9_-]+$")
THREADS_BASE_URL = "https://www.threads.com"
SERVICE_VERSION = "2026-04-03-sections-v7"
OUTPUT_DIR = Path("data")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


class CrawlRequest(BaseModel):
    profile_url: str = Field(
        default="https://www.threads.com/@freainer",
        description="Threads 프로필 URL",
    )
    max_scrolls: int = Field(default=30, ge=1, le=200)
    max_posts: int = Field(default=500, ge=1, le=5000)
    batch_size: int = Field(default=20, ge=1, le=200)
    headless: bool = Field(default=True)
    save_text_file: bool = Field(default=True)
    storage_state_path: str | None = Field(
        default=None,
        description="로그인 storage_state(JSON) 경로. 로그인 상태로 더 많은 피드 접근 가능",
    )
    include_replies: bool = Field(default=True, description="답글 탭도 함께 수집")
    include_reposts: bool = Field(default=True, description="리포스트 탭도 함께 수집")


class CrawlResponse(BaseModel):
    service_version: str
    run_id: str
    profile_url: str
    total_posts: int
    posts: list[dict[str, Any]]
    saved_text_path: str | None = None
    storage_state_loaded: bool = False


app = FastAPI(title="Threads Crawler Service", version="1.0.0")


async def _scroll_and_collect_post_links(page: Page, max_scrolls: int) -> list[str]:
    seen_links: set[str] = set()
    stable_rounds = 0
    stable_threshold = 12

    for _ in range(max_scrolls):
        hrefs: list[str] = await page.eval_on_selector_all(
            "a[href*='/post/']",
            "elements => elements.map(el => el.getAttribute('href'))",
        )

        for href in hrefs:
            normalized = _normalize_post_url(href)
            if normalized:
                seen_links.add(normalized)

        before = len(seen_links)
        await page.mouse.wheel(0, 15000)
        await page.keyboard.press("End")
        await page.evaluate("window.scrollBy(0, document.body.scrollHeight)")
        await page.wait_for_timeout(1200)

        hrefs_after: list[str] = await page.eval_on_selector_all(
            "a[href*='/post/']",
            "elements => elements.map(el => el.getAttribute('href'))",
        )
        for href in hrefs_after:
            normalized = _normalize_post_url(href)
            if normalized:
                seen_links.add(normalized)

        if len(seen_links) == before:
            stable_rounds += 1
            if stable_rounds >= stable_threshold:
                break
        else:
            stable_rounds = 0

    return sorted(seen_links)


def _normalize_post_url(href: str | None) -> str | None:
    if not href:
        return None

    href = href.strip()
    if not href:
        return None

    malformed_prefix = f"{THREADS_BASE_URL}@"
    if href.startswith(malformed_prefix):
        # 예: https://www.threads.com@freainer/post/xxxx  -> https://www.threads.com/@freainer/post/xxxx
        href = href.replace(malformed_prefix, f"{THREADS_BASE_URL}/@", 1)

    if href.startswith(THREADS_BASE_URL):
        parsed = urlparse(href)
        if parsed.netloc != "www.threads.com":
            return None
        candidate_path = parsed.path.lstrip("/")
        if not THREAD_LINK_RE.match(candidate_path):
            return None
        absolute_url = f"{THREADS_BASE_URL}/{candidate_path}"
    elif THREAD_LINK_RE.match(href):
        relative = href if href.startswith("/") else f"/{href}"
        absolute_url = urljoin(THREADS_BASE_URL, relative)
    else:
        return None

    return absolute_url.split("?")[0].rstrip("/")


async def _extract_post(page: Page, post_url: str) -> dict[str, Any]:
    safe_post_url = _normalize_post_url(post_url) or post_url
    await page.goto(safe_post_url, wait_until="domcontentloaded")
    await page.wait_for_timeout(1000)

    title = await page.title()

    text_candidates = await page.eval_on_selector_all(
        "div[role='button'] span, article span, article div[dir='auto']",
        "els => els.map(el => (el.innerText || '').trim()).filter(Boolean)",
    )

    content = "\n".join(dict.fromkeys(text_candidates[:20]))

    timestamp = await page.eval_on_selector(
        "time",
        "el => el ? el.getAttribute('datetime') : null",
    )

    image_urls = await page.eval_on_selector_all(
        "article img",
        "els => els.map(el => el.getAttribute('src')).filter(Boolean)",
    )

    return {
        "url": safe_post_url,
        "title": title,
        "content": content,
        "published_at": timestamp,
        "images": image_urls,
        "collected_at": datetime.now(timezone.utc).isoformat(),
    }


async def _run_crawl(
    profile_url: str,
    max_scrolls: int,
    max_posts: int,
    batch_size: int,
    storage_state_path: str | None,
    include_replies: bool,
    include_reposts: bool,
    headless: bool,
) -> tuple[list[dict[str, Any]], str, bool]:
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid4().hex[:8]

    async with async_playwright() as pw:
        try:
            browser: Browser = await pw.chromium.launch(headless=headless)
        except PlaywrightError as exc:
            message = str(exc)
            if "Executable doesn't exist" in message or "playwright install" in message:
                raise RuntimeError(
                    "Playwright 브라우저 실행 파일이 없습니다. "
                    "현재 활성화된 동일한 Python 환경에서 "
                    "`python -m playwright install` 을 다시 실행하세요."
                ) from exc
            raise
        context_kwargs: dict[str, Any] = {"locale": "ko-KR"}
        storage_state_loaded = False
        if storage_state_path:
            state_path = Path(storage_state_path)
            if state_path.exists():
                context_kwargs["storage_state"] = str(state_path)
                storage_state_loaded = True
        context = await browser.new_context(**context_kwargs)
        page = await context.new_page()

        section_urls = [profile_url]
        if include_replies:
            section_urls.append(profile_url.rstrip("/") + "/replies")
        if include_reposts:
            section_urls.append(profile_url.rstrip("/") + "/reposts")

        discovered_links: set[str] = set()
        for section_url in section_urls:
            try:
                await page.goto(section_url, wait_until="domcontentloaded")
                await page.wait_for_timeout(1500)
                section_links = await _scroll_and_collect_post_links(page, max_scrolls=max_scrolls)
                discovered_links.update(section_links)
            except Exception:
                continue

        post_links = sorted(discovered_links)[:max_posts]

        posts: list[dict[str, Any]] = []
        for start_idx in range(0, len(post_links), batch_size):
            batch_links = post_links[start_idx : start_idx + batch_size]
            for link in batch_links:
                normalized_link = _normalize_post_url(link) or link
                try:
                    post = await _extract_post(page, normalized_link)
                    posts.append(post)
                except Exception as exc:  # noqa: BLE001
                    posts.append(
                        {
                            "url": normalized_link,
                            "error": str(exc),
                            "collected_at": datetime.now(timezone.utc).isoformat(),
                        }
                    )
                await asyncio.sleep(0.3)

        await context.close()
        await browser.close()

    return posts, run_id, storage_state_loaded


def _save_posts_as_text_file(run_id: str, profile_url: str, posts: list[dict[str, Any]]) -> Path:
    out_path = OUTPUT_DIR / f"threads_{run_id}.txt"
    lines: list[str] = [
        f"Threads Crawl Export - {run_id}",
        f"Profile: {profile_url}",
        f"Total Posts: {len(posts)}",
        "",
        "=" * 80,
        "",
    ]

    for idx, post in enumerate(posts, start=1):
        lines.append(f"[{idx}] {post.get('url', '')}")
        lines.append(f"published_at: {post.get('published_at', '')}")
        if post.get("error"):
            lines.append(f"error: {post['error']}")
        else:
            title = (post.get("title") or "").strip()
            content = (post.get("content") or "").strip()
            lines.append(f"title: {title}")
            lines.append("content:")
            lines.append(content)
        lines.append("")
        lines.append("-" * 80)
        lines.append("")

    out_path.write_text("\n".join(lines), encoding="utf-8")
    return out_path


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "service_version": SERVICE_VERSION}


@app.post("/crawl", response_model=CrawlResponse)
async def crawl_threads(request: CrawlRequest) -> CrawlResponse:
    if "threads.com" not in request.profile_url:
        raise HTTPException(status_code=400, detail="profile_url must be a threads.com URL")

    if request.storage_state_path:
        state_path = Path(request.storage_state_path)
        if not state_path.exists():
            raise HTTPException(
                status_code=400,
                detail=f"storage_state_path 파일을 찾을 수 없습니다: {request.storage_state_path}",
            )

    try:
        posts, run_id, storage_state_loaded = await _run_crawl(
            profile_url=request.profile_url,
            max_scrolls=request.max_scrolls,
            max_posts=request.max_posts,
            batch_size=request.batch_size,
            storage_state_path=request.storage_state_path,
            include_replies=request.include_replies,
            include_reposts=request.include_reposts,
            headless=request.headless,
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    if not posts:
        raise HTTPException(status_code=404, detail="게시글을 수집하지 못했습니다. 로그인/접근 권한을 확인하세요.")

    saved_text_path: str | None = None
    if request.save_text_file:
        saved_text_path = str(_save_posts_as_text_file(run_id, request.profile_url, posts))

    return CrawlResponse(
        service_version=SERVICE_VERSION,
        run_id=run_id,
        profile_url=request.profile_url,
        total_posts=len(posts),
        posts=posts,
        saved_text_path=saved_text_path,
        storage_state_loaded=storage_state_loaded,
    )
