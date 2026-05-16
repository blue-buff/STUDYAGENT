#!/usr/bin/env python3
"""
组卷网登录脚本
启动 headless 浏览器，保存二维码供用户扫码，登录成功后保存 storage-state.json
"""

import asyncio
import sys
import time
from pathlib import Path

from playwright.async_api import async_playwright

SHARED_DIR = Path("/Users/song/project/STUDYAGENT/get from web/shared")
STORAGE_STATE = SHARED_DIR / "storage-state.json"
QR_PATH = SHARED_DIR / "login-qr.png"
LOGIN_URL = "https://zujuan.xkw.com"


async def login(timeout_seconds=120):
    """启动浏览器，展示二维码，等待用户扫码登录"""
    print("=" * 60)
    print("组卷网登录工具")
    print("=" * 60)

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-dev-shm-usage"],
        )
        context = await browser.new_context(viewport={"width": 1920, "height": 1080})
        page = await context.new_page()

        try:
            # 访问首页
            print("\n[1/4] 访问组卷网首页...")
            await page.goto(LOGIN_URL, wait_until="domcontentloaded")
            await page.wait_for_timeout(2000)

            # 检查是否已登录
            login_btn = await page.query_selector("a.login-btn")
            if login_btn is None:
                print("✓ 检测到已有登录状态（Cookie 有效）")
                await context.storage_state(path=str(STORAGE_STATE))
                print(f"✓ storage-state 已保存到: {STORAGE_STATE}")
                return True

            # 移除遮罩层并触发登录
            print("[2/4] 触发扫码登录...")
            overlay = await page.query_selector("div.ai-search-guide-panel")
            if overlay:
                await overlay.evaluate("el => el.style.display = 'none'")
                await page.wait_for_timeout(500)

            await page.evaluate("() => { if (typeof logindiv === 'function') logindiv(); }")
            await page.wait_for_timeout(3000)

            # 等待二维码出现
            try:
                await page.wait_for_selector("#qrcode canvas", timeout=10000)
            except Exception:
                qr_img = await page.query_selector("#qrcode img")
                if not qr_img:
                    # 尝试备用选择器
                    await page.wait_for_timeout(3000)
                    qr_img = await page.query_selector("#qrcode img")
                    if not qr_img:
                        print("✗ 错误：未找到二维码元素，请检查页面")
                        debug_html = SHARED_DIR / "login_debug.html"
                        debug_html.write_text(await page.content(), encoding="utf-8")
                        print(f"  调试页面已保存到: {debug_html}")
                        return False

            # 截取二维码
            qrcode_el = await page.query_selector("#qrcode")
            if qrcode_el:
                await qrcode_el.screenshot(path=str(QR_PATH))
                print(f"\n[3/4] 二维码已保存到: {QR_PATH}")
                print(f"       请用微信扫码登录（{timeout_seconds}秒内）...\n")

            # 等待登录
            print("[4/4] 等待扫码...")
            start = time.time()
            last_check_url = ""

            while time.time() - start < timeout_seconds:
                await page.wait_for_timeout(2000)

                try:
                    current_url = page.url
                    if current_url != last_check_url:
                        elapsed = int(time.time() - start)
                        print(f"  [{elapsed}s] 当前 URL: {current_url[:80]}")
                        last_check_url = current_url
                except Exception:
                    pass

                # 用新页面检查登录状态
                try:
                    check_page = await context.new_page()
                    await check_page.goto(LOGIN_URL, wait_until="domcontentloaded", timeout=15000)
                    await check_page.wait_for_timeout(1000)
                    login_btn = await check_page.query_selector("a.login-btn")
                    await check_page.close()

                    if login_btn is None:
                        elapsed = int(time.time() - start)
                        print(f"\n✓ 扫码成功！（耗时 {elapsed} 秒）")
                        await context.storage_state(path=str(STORAGE_STATE))
                        print(f"✓ storage-state 已保存到: {STORAGE_STATE}")
                        return True
                except Exception:
                    pass

            print(f"\n✗ 登录超时（{timeout_seconds} 秒）")
            return False

        finally:
            await browser.close()


async def main():
    timeout = int(sys.argv[1]) if len(sys.argv) > 1 else 120
    success = await login(timeout_seconds=timeout)
    if success:
        print("\n登录成功！可以运行 scrape.py 抓取题目了。")
        sys.exit(0)
    else:
        print("\n登录失败。请重试或使用 --cookie 方式登录。")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
