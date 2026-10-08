import os
import time
from playwright.sync_api import sync_playwright

STATE_FILE_PATH = "credentials/state.json"
LOGIN_URL = "https://toho-ss.jp/es/login/next"
SEARCH_URL = "https://toho-ss.jp/estate/customers?_cond=1"

def clear_input_field(locator):
    if locator.count() > 0:
        locator.focus()
        locator.press("Control+A")
        locator.press("Backspace")
        locator.fill("")

def count_real_customer_rows(page):
    link_rows = page.locator("table tbody tr a[href*='/customers/detail/'], table tbody tr a[href*='/estate/customers/']").count()
    if link_rows > 0:
        return link_rows

    action_rows = page.locator("table tbody tr button, table tbody tr .btn").count()
    if action_rows > 0:
        return action_rows

    content = page.content()
    if "検索結果がありませんでした" in content or "該当なし" in content or "0件" in content:
        return 0

    rows = page.locator("table tbody tr")
    real_count = 0
    for i in range(rows.count()):
        row = rows.nth(i)
        if row.locator("td").count() >= 4 and row.is_visible():
            real_count += 1
    return real_count

def run_toho_ss_search(email: str, name: str, user: str = "okuyama", password: str = "nextokuyama", max_wait: int = 120):
    """
    添付の app_phase2.py と同一の挙動を行う顧客検索関数
    - state.json が無い場合: ブラウザを表示してログイン・2段階認証を待機して保存
    - state.json が有る場合: 裏側(Headless)で高速自動検索を実行
    """
    os.makedirs("credentials", exist_ok=True)
    has_session = os.path.exists(STATE_FILE_PATH)
    
    # セッションが無ければ初回認証用にブラウザを表示(headless=False)、有れば裏側(headless=True)で実行
    is_headless = True if has_session else False
    
    status = "SS未検出"
    logs = []

    with sync_playwright() as p:
        logs.append(f"🌐 Playwright ブラウザエンジンを起動中... (裏側実行: {is_headless})")
        browser = p.chromium.launch(headless=is_headless, slow_mo=100)

        if has_session:
            logs.append("💾 保存済みのログインセッション（state.json）を読み込みました。")
            context = browser.new_context(storage_state=STATE_FILE_PATH)
        else:
            logs.append("🆕 保存セッションが無いため、ブラウザ画面を開いて新規ログインを実行します。")
            context = browser.new_context()

        page = context.new_page()
        logs.append(f"🔗 ページへアクセス: {LOGIN_URL}")
        page.goto(LOGIN_URL, wait_until="domcontentloaded")

        # ログイン画面の場合のID/パスワード入力
        if "login" in page.url:
            if user and password:
                logs.append("🔐 ID/パスワードを入力中...")
                id_field = page.locator("input[type='text'], input[type='email'], input[name*='user'], input[name*='id']").first
                pw_field = page.locator("input[type='password']").first
                
                if id_field.count() > 0:
                    id_field.fill(user)
                if pw_field.count() > 0:
                    pw_field.fill(password)
                
                login_btn = page.locator("button[type='submit'], input[type='submit'], button:has-text('ログイン')").first
                if login_btn.count() > 0:
                    login_btn.click()

        logs.append("⚡ ログイン（2段階認証）完了を監視中...")
        start_time = time.time()
        is_logged_in = False

        while time.time() - start_time < max_wait:
            if "login" not in page.url and "estate" in page.url and "mfa" not in page.url:
                if page.locator("a[href*='/estate/customers']").count() > 0 or page.locator("text='顧客検索'").count() > 0:
                    is_logged_in = True
                    logs.append("⚡ ログイン完了・ヘッダー描画を確認しました！")
                    context.storage_state(path=STATE_FILE_PATH)
                    logs.append("💾 ログイン認証情報を `credentials/state.json` に保存しました。")
                    break
            page.wait_for_timeout(500)

        if is_logged_in:
            logs.append("🚀 『顧客検索』画面へ切り替え中...")
            page.wait_for_timeout(500)

            try:
                page.evaluate("() => { const el = document.querySelector(\"a[href*='/estate/customers']\"); if(el) el.click(); }")
            except Exception:
                pass

            page.wait_for_timeout(1000)

            if "customers" not in page.url and page.locator("#email").count() == 0:
                try:
                    page.goto(SEARCH_URL, wait_until="domcontentloaded")
                except Exception:
                    pass

            search_ready = False
            for _ in range(15):
                if page.locator("#email").count() > 0 or page.locator("input[name='email']").count() > 0:
                    search_ready = True
                    break
                page.wait_for_timeout(500)

            if search_ready:
                logs.append("🎯 顧客検索画面に到達！自動検索を開始します。")

                reset_btn = page.locator("a:has-text('リセット'), button:has-text('リセット')").first
                if reset_btn.count() > 0:
                    try:
                        reset_btn.click()
                        page.wait_for_timeout(200)
                    except Exception:
                        pass

                email_input = page.locator("#email, input[name='email']").first
                name_input = page.locator("input[name='name'], #name, tr:has-text('氏名') input").first

                logs.append(f"🔍 [一次検索] メールアドレス `{email}` を入力中...")
                clear_input_field(email_input)
                clear_input_field(name_input)

                if email_input.count() > 0:
                    email_input.fill(email)

                search_btn = page.locator("button:has-text('検索'), .btn-primary:has-text('検索')").first
                if search_btn.count() > 0:
                    search_btn.click()
                elif email_input.count() > 0:
                    email_input.press("Enter")

                page.wait_for_timeout(1500)
                row_count = count_real_customer_rows(page)

                if row_count == 1:
                    status = "成功 (一次検索)"
                    logs.append("✅ [一次検索成功] 顧客データが『1件』特定されました！")
                elif row_count > 1:
                    logs.append(f"⚠️ 候補が {row_count} 件検出されました。予備検索へ移行します...")
                else:
                    logs.append("⚠️ 宛先メールアドレスで未ヒット。予備検索（氏名）へ移行します...")

                # 予備検索
                if not status.startswith("成功"):
                    if reset_btn.count() > 0:
                        try:
                            reset_btn.click()
                            page.wait_for_timeout(200)
                        except Exception:
                            pass

                    clear_input_field(email_input)
                    clear_input_field(name_input)

                    clean_name = name.replace(" ", "").replace(" ", "")
                    logs.append(f"🔍 [予備検索] 氏名 `{name}` を入力して検索中...")

                    if name_input.count() > 0:
                        name_input.fill(name)

                    if search_btn.count() > 0:
                        search_btn.click()
                    elif name_input.count() > 0:
                        name_input.press("Enter")

                    page.wait_for_timeout(1500)
                    row_count_sub = count_real_customer_rows(page)

                    if row_count_sub == 1:
                        status = "成功 (予備検索)"
                        logs.append("✅ [予備検索成功] 顧客氏名での検索により『1件』特定されました！")
                    else:
                        logs.append(f"🔍 [予備検索再試行] スペースなし `{clean_name}` で再検索中...")
                        if reset_btn.count() > 0:
                            try:
                                reset_btn.click()
                                page.wait_for_timeout(200)
                            except Exception:
                                pass

                        clear_input_field(email_input)
                        clear_input_field(name_input)

                        if name_input.count() > 0:
                            name_input.fill(clean_name)

                        if search_btn.count() > 0:
                            search_btn.click()
                        elif name_input.count() > 0:
                            name_input.press("Enter")

                        page.wait_for_timeout(1500)
                        row_count_sub2 = count_real_customer_rows(page)

                        if row_count_sub2 == 1:
                            status = "成功 (予備検索)"
                            logs.append("✅ [予備検索成功] 顧客氏名（スペースなし）により『1件』特定されました！")
                        elif row_count_sub2 > 1:
                            status = "SS複数検出エラー"
                            logs.append(f"❌ [エラー] 該当する顧客データが {row_count_sub2} 件存在します。")
                        else:
                            status = "SS未検出"
                            logs.append("❌ [失敗] 予備検索でも顧客データが検出されませんでした。")

        browser.close()
        return status, logs

if __name__ == '__main__':
    # 単体テスト実行
    res_status, res_logs = run_toho_ss_search(email="okuyama@toho-next.com", name="奥山由佳")
    print("\n--- 実行ログ ---")
    for log in res_logs:
        print(log)
    print(f"\n最終結果ステータス: {res_status}")