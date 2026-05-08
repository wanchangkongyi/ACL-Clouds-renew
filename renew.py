import os
import re
import time
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout

username = os.environ.get("ACL_USERNAME", "")
password = os.environ.get("ACL_PASSWORD", "")

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

with sync_playwright() as p:
    # 关闭 headless，配合 xvfb 运行
    browser = p.chromium.launch(headless=False)
    page = browser.new_page()

    # ============ 1. 登录 ============
    log("正在打开登录页...")
    page.goto("https://dash.aclclouds.com/login", wait_until="networkidle")
    page.screenshot(path="00_before_login.png")

    inputs = page.locator('input')
    inputs.nth(0).fill(username)
    inputs.nth(1).fill(password)

    # 点击自定义 checkbox
    checkbox = page.locator('div.auth-captcha-inner[role="checkbox"]')
    checkbox.click()
    time.sleep(2)
    page.screenshot(path="00_checkbox.png")
    log("验证勾选完成")

    # 点击登录按钮
    page.click('button[type="submit"]')
    page.wait_for_load_state("networkidle")
    page.screenshot(path="01_after_login.png")
    log("登录完成")

    # ============ 2. 进入项目页面，收集链接 ============
    log("正在进入项目页面...")
    page.goto("https://dash.aclclouds.com/projects", wait_until="networkidle")
    page.screenshot(path="02_projects.png")

    project_links = page.locator('a[href*="/projects/"]').all()
    hrefs = []
    for link in project_links:
        href = link.get_attribute("href")
        if href and href not in hrefs:
            hrefs.append(href)
    log(f"找到 {len(hrefs)} 个项目")

    if len(hrefs) == 0:
        log("未找到任何项目，请检查登录状态或选择器")
        page.screenshot(path="error_no_projects.png")
        browser.close()
        exit(1)

    # ============ 3. 逐个处理项目 ============
    for idx, href in enumerate(hrefs):
        url = href if href.startswith("http") else f"https://dash.aclclouds.com{href}"
        log(f"--- 处理第 {idx+1} 个项目: {url} ---")

        page.goto(url, wait_until="networkidle")
        page.screenshot(path=f"project_{idx+1}_01_enter.png")

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
                    log("续期按钮不可见，可能尚未到续期窗口期")
            except PlaywrightTimeout:
                log("续期操作超时")
            page.screenshot(path=f"project_{idx+1}_02_after_renew.png")
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

        page.screenshot(path=f"project_{idx+1}_03_final.png")
        time.sleep(2)

    log("全部项目处理完成")
    browser.close()
