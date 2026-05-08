import os
import re
import time
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout

cookies_str = os.environ.get("ACL_COOKIES", "")

def log(msg):
    print(f"[INFO] {msg}")

def parse_expires_minutes(text):
    hours = re.search(r'(\d+)\s*h', text)
    mins  = re.search(r'(\d+)\s*min', text)
    total = 0
    if hours:
        total += int(hours.group(1)) * 60
    if mins:
        total += int(mins.group(1))
    return total

def parse_cookies(cookie_str):
    cookies = []
    for item in cookie_str.split(";"):
        item = item.strip()
        if "=" in item:
            name, value = item.split("=", 1)
            cookies.append({
                "name": name.strip(),
                "value": value.strip(),
                "domain": "dash.aclclouds.com",
                "path": "/"
            })
    return cookies

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    context = browser.new_context()

    # ============ 1. 注入 Cookie ============
    log("注入 Cookie...")
    context.add_cookies(parse_cookies(cookies_str))
    page = context.new_page()

    # ============ 2. 进入项目列表页 ============
    log("正在进入项目页面...")
    page.goto("https://dash.aclclouds.com/projects", wait_until="networkidle")
    page.screenshot(path="01_projects.png")

    # 收集所有 /server/ 链接
    project_links = page.locator('a[href*="/server/"]').all()
    hrefs = []
    for link in project_links:
        href = link.get_attribute("href")
        if href and href not in hrefs:
            hrefs.append(href)
    log(f"找到 {len(hrefs)} 个服务器")

    if len(hrefs) == 0:
        log("未找到任何服务器，请检查 Cookie 是否有效")
        page.screenshot(path="error_no_projects.png")
        browser.close()
        exit(1)

    # ============ 3. 逐个处理服务器 ============
    for idx, href in enumerate(hrefs):
        url = href if href.startswith("http") else f"https://dash.aclclouds.com{href}"
        log(f"--- 处理第 {idx+1} 个服务器: {url} ---")

        page.goto(url, wait_until="networkidle")
        page.screenshot(path=f"server_{idx+1}_01_enter.png")

        # --- 读取剩余时间 ---
        remaining = None
        try:
            expires_el = page.locator('text=Expires in').locator('xpath=following-sibling::*[1]')
            expires_text = expires_el.inner_text(timeout=5000)
            remaining = parse_expires_minutes(expires_text)
            log(f"剩余时间: {expires_text} ({remaining} 分钟)")
        except Exception as e:
            log(f"无法读取剩余时间: {e}")

        # --- 续期 ---
        should_renew = (remaining is not None and remaining <= 120) or (remaining is None)

        if should_renew:
            log("尝试续期...")
            try:
                renew_btn = page.locator('button:has-text("Renew")')
                if renew_btn.is_visible(timeout=3000):
                    renew_btn.click()
                    time.sleep(2)
                    confirm = page.locator('button:has-text("Confirm")')
                    if confirm.is_visible(timeout=3000):
                        confirm.click()
                        time.sleep(2)
                    log("续期成功")
                else:
                    log("续期按钮不可见，未到续期窗口期")
            except PlaywrightTimeout:
                log("续期操作超时")
            page.screenshot(path=f"server_{idx+1}_02_after_renew.png")
        else:
            log(f"剩余时间充足（{remaining}min），无需续期")

        # --- 开机 ---
        log("检查开机状态...")
        try:
            start_btn = page.locator('button:has-text("Start")')
            if start_btn.is_visible(timeout=3000):
                start_btn.click()
                time.sleep(2)
                confirm = page.locator('button:has-text("Confirm")')
                if confirm.is_visible(timeout=3000):
                    confirm.click()
                    time.sleep(3)
                log("开机成功")
            else:
                log("服务器已在运行，无需开机")
        except PlaywrightTimeout:
            log("开机操作超时")

        page.screenshot(path=f"server_{idx+1}_03_final.png")
        time.sleep(2)

    log("全部服务器处理完成")
    browser.close()
