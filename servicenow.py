from playwright.sync_api import sync_playwright
import time

TARGET_ORDER_ID = "260423-E00000007"
SERVICE_NOW_URL = "https://tshuservicedeskdev2.service-now.com"
query = (
    f"u_order_id%3D{TARGET_ORDER_ID}"
    "%5Estate!%3D3"
    "%5Eshort_description!%3DManual%20error%20resolution%20-%20work%20order%20task%20/%20CREATE"
)
ORDER_LIST_URL = f"{SERVICE_NOW_URL}/wm_order_list.do?sysparm_query={query}&sysparm_first_row=1&sysparm_view="
SOLVED_BY_VALUE = "0"
RESPONSIBILITY_VALUE = "0"
RESOLUTION_CODE_VALUE = "0"
RESOLUTION_NOTES = "Automata teszt futtatás"


def safe_click(page, selector):
    """Biztonságos kattintás, ha az elem létezik és látható"""
    loc = page.locator(selector)
    if loc.count() > 0:
        el = loc.first
        el.wait_for(state="visible", timeout=5000)
        el.scroll_into_view_if_needed()
        el.click(force=True)
        page.wait_for_timeout(500)
        return True
    return False


def process_single_task(page, task_href):
    """Egyetlen task feldolgozása: állapotváltások, megoldás, zárás"""
    page.goto(f"{SERVICE_NOW_URL}/{task_href}")
    page.wait_for_load_state("networkidle")

    # Első lépések: accepted, assigned, active
    for btn in [
        "#tsm_set_accepted",
        "#sysverb_update_and_stay",
        "#tsm_set_assigned",
        "#sysverb_update_and_stay",
        "#tsm_set_active",
        "#sysverb_update_and_stay",
    ]:
        safe_click(page, btn)

    # Set Resolved és adatok kitöltése
    if safe_click(page, "#tsm_set_resolved"):
        # Resolver idő beállítása
        resolved_btn = page.locator(
            "button.btn-ref.date_time_trigger#wm_task\\.u_resolved_time\\.ui_policy_sensitive"
        )
        if resolved_btn.count() > 0:
            resolved_btn.first.click(force=True)
            page.wait_for_selector("#GwtDateTimePicker_ok", timeout=5000)
            page.click("#GwtDateTimePicker_ok")

        # Dropdown mezők kitöltése
        page.select_option("select#wm_task\\.u_solved_by", SOLVED_BY_VALUE)
        page.select_option("select#wm_task\\.u_responsibility", RESPONSIBILITY_VALUE)
        page.select_option("select#wm_task\\.u_resolution_code", RESOLUTION_CODE_VALUE)

        notes = page.locator("#wm_task\\.close_notes")
        if notes.count() > 0:
            notes.first.fill(RESOLUTION_NOTES)

        # Mentés resolved állapotban
        safe_click(page, "#sysverb_update_and_stay")

    # Set Closed és mentés
    if safe_click(page, "#tsm_set_closed"):
        safe_click(page, "#sysverb_update_and_stay")


def process_tasks(page):
    """Az aktuális order összes task-jának feldolgozása"""
    container = page.locator("div#wm_order\\.wm_task\\.parent")
    container.wait_for(state="visible", timeout=15000)

    rows = container.locator("tr.list_row")
    for i in range(rows.count()):
        row = rows.nth(i)
        task_link = row.locator("td.vt a.linked.formlink")
        if task_link.count() == 0:
            continue

        task_text = task_link.first.inner_text().strip()
        false_value = row.locator("td").nth(4).inner_text().strip()
        if task_text.startswith("WOT") and false_value.lower() == "true":
            task_href = task_link.first.get_attribute("href")
            if task_href:
                process_single_task(page, task_href)
                page.go_back()
                page.wait_for_load_state("networkidle")


def main_loop():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        context = browser.new_context(
            storage_state="servicenow_auth.json",
            ignore_https_errors=True,
        )
        page = context.new_page()

        while True:
            page.goto(ORDER_LIST_URL)
            page.wait_for_load_state("networkidle")

            rows = page.locator("table#wm_order_table tbody tr.list_row")
            for i in range(rows.count()):
                row = rows.nth(i)
                order_id = row.locator("td").nth(7).inner_text().strip()
                state = row.locator("td").nth(4).inner_text().strip()

                # Csak a Work In Progress order-eket dolgozzuk fel
                if order_id == TARGET_ORDER_ID and state == "Work In Progress":
                    number_link = row.locator("td.vt a.linked.formlink").first
                    if number_link.count() > 0:
                        href = number_link.get_attribute("href")
                        if href:
                            page.goto(f"{SERVICE_NOW_URL}/{href}")
                            page.wait_for_load_state("networkidle")
                            process_tasks(page)
                            break

            # Várakozás a következő iterációig
            time.sleep(5)


if __name__ == "__main__":
    main_loop()
