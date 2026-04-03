from __future__ import annotations

import asyncio
import re
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from playwright.async_api import Browser, Page, async_playwright


THREAD_LINK_RE = re.compile(r"^/(@[^/]+/post/[A-Za-z0-9_-]+)")


class CrawlRequest(BaseModel):
    profile_url: str = Field(
        default="https://www.threads.com/@freainer",
        description="Threads 프로필 URL",
    )
    max_scrolls: int = Field(default=30, ge=1, le=200)
    headless: bool = Field(default=True)


class CrawlResponse(BaseModel):
    run_id: str
    profile_url: str
    total_posts: int
    posts: list[dict[str, Any]]


app = FastAPI(title="Threads Crawler Service", version="1.0.0")


async def _scroll_and_collect_post_links(page: Page, max_scrolls: int) -> list[str]:
    seen_links: set[str] = set()
    stable_rounds = 0

    for _ in range(max_scrolls):
        hrefs: list[str] = await page.eval_on_selector_all(
            "a[href*='/post/']",
            "elements => elements.map(el => el.getAttribute('href'))",
        )

        for href in hrefs:
            if not href:
                continue
            match = THREAD_LINK_RE.match(href)
            if match:
                seen_links.add("https://www.threads.com/" + match.group(1))

        before = len(seen_links)
        await page.mouse.wheel(0, 15000)
        await page.wait_for_timeout(1200)

        hrefs_after: list[str] = await page.eval_on_selector_all(
            "a[href*='/post/']",
            "elements => elements.map(el => el.getAttribute('href'))",
        )
        for href in hrefs_after:
            if not href:
                continue
            match = THREAD_LINK_RE.match(href)
            if match:
                seen_links.add("https://www.threads.com/" + match.group(1))

        if len(seen_links) == before:
            stable_rounds += 1
            if stable_rounds >= 4:
                break
        else:
            stable_rounds = 0

    return sorted(seen_links)


async def _extract_post(page: Page, post_url: str) -> dict[str, Any]:
    await page.goto(post_url, wait_until="domcontentloaded")
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
        "url": post_url,
        "title": title,
        "content": content,
        "published_at": timestamp,
        "images": image_urls,
        "collected_at": datetime.now(timezone.utc).isoformat(),
    }


async def _run_crawl(profile_url: str, max_scrolls: int, headless: bool) -> tuple[list[dict[str, Any]], str]:
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid4().hex[:8]

    async with async_playwright() as pw:
        browser: Browser = await pw.chromium.launch(headless=headless)
        context = await browser.new_context(locale="ko-KR")
        page = await context.new_page()

        await page.goto(profile_url, wait_until="domcontentloaded")
        await page.wait_for_timeout(1500)

        post_links = await _scroll_and_collect_post_links(page, max_scrolls=max_scrolls)

        posts: list[dict[str, Any]] = []
        for link in post_links:
            try:
                post = await _extract_post(page, link)
                posts.append(post)
            except Exception as exc:  # noqa: BLE001
                posts.append(
                    {
                        "url": link,
                        "error": str(exc),
                        "collected_at": datetime.now(timezone.utc).isoformat(),
                    }
                )
            await asyncio.sleep(0.3)

        await context.close()
        await browser.close()

    return posts, run_id


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/crawl", response_model=CrawlResponse)
async def crawl_threads(request: CrawlRequest) -> CrawlResponse:
    if "threads.com" not in request.profile_url:
        raise HTTPException(status_code=400, detail="profile_url must be a threads.com URL")

    posts, run_id = await _run_crawl(
        profile_url=request.profile_url,
        max_scrolls=request.max_scrolls,
        headless=request.headless,
    )

    if not posts:
        raise HTTPException(status_code=404, detail="게시글을 수집하지 못했습니다. 로그인/접근 권한을 확인하세요.")

    return CrawlResponse(
        run_id=run_id,
        profile_url=request.profile_url,
        total_posts=len(posts),
        posts=posts,
    )
