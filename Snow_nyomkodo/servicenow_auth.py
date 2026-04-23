from playwright.sync_api import sync_playwright

SERVICE_NOW_BASE = "https://tshuservicedeskdev2.service-now.com"

with sync_playwright() as p:
    browser = p.chromium.launch(headless=False)
    context = browser.new_context(ignore_https_errors=True)
    page = context.new_page()

    # Login oldal megnyitása
    page.goto(SERVICE_NOW_BASE + "/login.do")

    print("👉 Jelentkezz be manuálisan a ServiceNow felületen...")
    input("Ha sikeresen beléptél és betöltött a kezdőoldal, nyomj ENTER-t...")

    # Session mentése
    context.storage_state(path="servicenow_auth.json")
    print("✅ ServiceNow session elmentve: servicenow_auth.json")

    browser.close()
