from playwright.sync_api import sync_playwright


def main() -> None:
    output = "state.json"
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=False)
        context = browser.new_context()
        page = context.new_page()
        page.goto("https://www.threads.net", wait_until="domcontentloaded")
        print("브라우저에서 Threads 로그인 후, 터미널로 돌아와 Enter를 누르세요.")
        input()
        context.storage_state(path=output)
        print(f"저장 완료: {output}")
        browser.close()


if __name__ == "__main__":
    main()
