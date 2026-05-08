import os
import re
import time
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout

username = os.environ.get("ACL_USERNAME", "")
password = os.environ.get("ACL_PASSWORD", "")

def log(msg):
    print(f"[INFO] {msg}")

def parse_expires_minutes(text):
    """
    解析剩余时间为分钟数
    支持格式：'4h 46min' / '1h 30min' / '45min' / '2h'
    """
    hours = re.search(r'(\d+)\s*h', text)
    mins  = re.search(r'(\d+)\s*min', text)
    total = 0
    if hours:
        total += int(hours.group(1)) * 60
    if mins:
        total += int(mins.group(1))
    return total

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page()

    # ============ 1. 登录 ============
    log("正在打开登录页...")
    page.goto("https://dash.aclclouds.com/login", wait_until="networkidle")
    page.screenshot(path="00_before_login.png")

    # 填写邮箱和密码
    page.fill('input[type="email"]', username)
    page.fill('input[type="password"]', password)

    # 点击自定义 checkbox
    checkbox = page.locator('div.auth-captcha-inner[role="checkbox"]')
    checkbox.click()
    time.sleep(1)

    # 等待勾选状态出现
    page.wait_for_selector('div.auth-captcha-checkbox.checked', timeout=5000)
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
        try:
            expires_el = page.locator('text=Expires in').locator('xpath=following-sibling::*[1]')
            expires_text = expires_el.inner_text()
            remaining = parse_expires_minutes(expires_text)
            log(f"剩余时间: {expires_text} ({remaining} 分钟)")
        except Exception as e:
            log(f"无法读取剩余时间: {e}，跳过此项目")
            page.screenshot(path=f"project_{idx+1}_error.png")
            continue

        # --- 续期（仅剩余 ≤120 分钟时） ---
        if remaining <= 120:
            log("剩余时间不足2h，尝试续期...")
            try:
                renew_btn = page.locator('button:has-text("Renew")')
                if renew_btn.is_visible():
                    renew_btn.click()
                    time.sleep(2)
                    confirm = page.locator('button:has-text("Confirm")')
                    if confirm.is_visible():
                        confirm.click()
                        time.sleep(2)
                    log("续期成功")
                else:
                    log("续期按钮不可见，跳过")
            except PlaywrightTimeout:
                log("续期操作超时")
            page.screenshot(path=f"project_{idx+1}_02_after_renew.png")
        else:
            log(f"剩余时间充足（{remaining}min），无需续期")

        # --- 开机（无论是否续期都检查） ---
        try:
            start_btn = page.locator('button:has-text("Start")')
            if start_btn.is_visible():
                start_btn.click()
                time.sleep(2)
                confirm = page.locator('button:has-text("Confirm")')
                if confirm.is_visible():
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
