#!/usr/bin/env python3
"""
04_login.py — Playwright 登录菁优网并保存 Cookie
打开浏览器窗口，用户手动完成 QQ/微信扫码登录，保存 storage state
"""
import sys, json, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from playwright.sync_api import sync_playwright
from jyeoo.config import get_config
from jyeoo.utils import setup_logging, ensure_dir, logger

AUTH_DIR = Path(__file__).parent.parent / "output" / "auth"
STATE_FILE = AUTH_DIR / "state.json"


def wait_for_login(page, deadline):
    """Wait for user to complete login. Return True if successful."""
    while time.time() < deadline:
        current_url = page.url
        # Success: redirected away from login page back to a content page
        if "login" not in current_url.lower() and "jyeoo.com" in current_url:
            # Double check by trying the search page
            try:
                ctx = page.context
                test = ctx.new_page()
                test.goto("https://www.jyeoo.com/math/ques/search",
                         wait_until="domcontentloaded", timeout=15000)
                test.wait_for_timeout(2000)
                ok = "login" not in test.url.lower()
                test.close()
                if ok:
                    return True
            except Exception:
                pass
        time.sleep(5)
        remaining = int(deadline - time.time())
        if remaining % 15 == 0:
            logger.info(f"  Waiting for login... ({remaining}s remaining)")
    return False


def main():
    setup_logging()
    config = get_config()
    ensure_dir(AUTH_DIR)

    # Clear old failed state
    if STATE_FILE.exists():
        STATE_FILE.unlink()
        logger.info("Removed old state file")

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=False,
            args=["--no-sandbox", "--disable-setuid-sandbox"],
        )
        context = browser.new_context(
            viewport={"width": 1280, "height": 800},
            user_agent=config.user_agent,
        )
        page = context.new_page()

        # Navigate directly to a page that requires login, triggering redirect to login
        logger.info("Opening jyeoo.com (will redirect to login if needed)...")
        page.goto("https://www.jyeoo.com/math/ques/search", wait_until="domcontentloaded", timeout=30000)
        page.wait_for_timeout(3000)

        # We should now be on the login page
        if "login" in page.url.lower():
            logger.info("Login page displayed. Please log in via the browser window.")
        else:
            logger.info("Already logged in or on main page.")

        logger.info("=" * 60)
        logger.info("ACTION REQUIRED: Please log in to jyeoo.com")
        logger.info("  - Use WeChat or QQ to scan the QR code")
        logger.info("  - Or enter account + password + CAPTCHA")
        logger.info("  - Wait for the page to show your username in top-right")
        logger.info("You have 120 seconds.")
        logger.info("=" * 60)

        # Wait for login
        deadline = time.time() + 120
        logged_in = wait_for_login(page, deadline)

        if logged_in:
            context.storage_state(path=str(STATE_FILE))
            logger.info(f"State saved to {STATE_FILE}")

            # Verify
            with open(STATE_FILE) as f:
                state = json.load(f)
            cookies = state.get("cookies", [])
            auth_cookies = [c for c in cookies if c["name"] not in
                           ("HMACCOUNT", "HMACCOUNT_BFESS", "Hm_lvt_2a39e15ac4b0df8a42f6e4f6433f43f4",
                            "Hm_lpvt_2a39e15ac4b0df8a42f6e4f6433f43f4", "gr_user_id",
                            "a8f7777aa0f1f0f8_gr_session_id")]
            logger.info(f"Total cookies: {len(cookies)}, auth cookies: {len(auth_cookies)}")
            for c in auth_cookies:
                logger.info(f"  {c['name']}: domain={c['domain']}")
        else:
            logger.warning("Login timeout. Saving partial state anyway...")
            context.storage_state(path=str(STATE_FILE))

        browser.close()


if __name__ == "__main__":
    main()
