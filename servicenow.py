import time
import threading
from pymongo import MongoClient
from urllib.parse import quote_plus
from playwright.sync_api import sync_playwright


TARGET_ORDER_ID = "KT20260424135912"

SERVICE_NOW_URL = "https://tshuservicedeskdev2.service-now.com"

SOLVED_BY_VALUE = "0"
RESPONSIBILITY_VALUE = "0"
RESOLUTION_CODE_VALUE = "0"
RESOLUTION_NOTES = "Automata teszt futtatás"


USERNAME = "ictsomldev1"
PASSWORD = quote_plus("nueNySgYn0kZXH1t")

MONGO_URI = (
    f"mongodb://{USERNAME}:{PASSWORD}@localhost:27225/ictsoml?authSource=ictsoml"
)


def get_collection():
    client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=5000)
    client.admin.command("ping")
    db = client["ictsoml"]
    return db["service-order"]


def wait_for_completed(external_id, stop_event, timeout_sec=None, poll_interval=5):
    collection = get_collection()
    start = time.time()

    last_state = None

    while not stop_event.is_set():
        doc = collection.find_one(
            {"externalId": external_id},
            {"state": 1, "_id": 0},
        )

        if doc:
            state = doc.get("state")

            if state != last_state:
                print(f"[SOM] {external_id} state = {state}")
                last_state = state

            if state == "COMPLETED" or state == "FAILED" or state == "HELD":
                stop_event.set()
                return True

        else:
            if last_state != "NOT_FOUND":
                print(f"[SOM] {external_id} not found yet")
                last_state = "NOT_FOUND"

        if timeout_sec is not None and time.time() - start > timeout_sec:
            stop_event.set()
            raise TimeoutError("SOM timeout")

        time.sleep(poll_interval)


def build_order_list_url(order_id: str) -> str:
    query = (
        f"u_order_id%3D{order_id}"
        "%5Estate!%3D3"
        "%5Eshort_description!%3DManual%20error%20resolution%20-%20work%20order%20task%20/%20CREATE"
    )

    return (
        f"{SERVICE_NOW_URL}/wm_order_list.do"
        f"?sysparm_query={query}&sysparm_first_row=1&sysparm_view="
    )


def safe_click(page, selector):
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
    try:
        page.goto(f"{SERVICE_NOW_URL}/{task_href}")
        page.wait_for_load_state("networkidle")

        for btn in [
            "#tsm_set_accepted",
            "#tsm_set_assigned",
            "#tsm_set_active",
        ]:
            safe_click(page, btn)
            safe_click(page, "#sysverb_update_and_stay")

        if safe_click(page, "#tsm_set_resolved"):
            resolver = page.locator(
                "button.btn-ref.date_time_trigger#wm_task\\.u_resolved_time\\.ui_policy_sensitive"
            )

            if resolver.count() > 0:
                resolver.first.click(force=True)
                page.wait_for_selector("#GwtDateTimePicker_ok", timeout=5000)
                page.click("#GwtDateTimePicker_ok")

            page.select_option("select#wm_task\\.u_solved_by", SOLVED_BY_VALUE)
            page.select_option(
                "select#wm_task\\.u_responsibility", RESPONSIBILITY_VALUE
            )
            page.select_option(
                "select#wm_task\\.u_resolution_code", RESOLUTION_CODE_VALUE
            )

            notes = page.locator("#wm_task\\.close_notes")
            if notes.count() > 0:
                notes.first.fill(RESOLUTION_NOTES)

            safe_click(page, "#sysverb_update_and_stay")

        if safe_click(page, "#tsm_set_closed"):
            safe_click(page, "#sysverb_update_and_stay")

    except Exception as e:
        print(f"[TASK ERROR] {e}")


def process_tasks(page):
    try:
        container = page.locator("div#wm_order\\.wm_task\\.parent")
        container.wait_for(state="visible", timeout=15000)

        rows = container.locator("tr.list_row")

        for i in range(rows.count()):
            row = rows.nth(i)

            link = row.locator("td.vt a.linked.formlink")
            if link.count() == 0:
                continue

            task_text = link.first.inner_text().strip()
            flag = row.locator("td").nth(4).inner_text().strip()

            if task_text.startswith("WOT") and flag.lower() == "true":
                href = link.first.get_attribute("href")

                if href:
                    process_single_task(page, href)
                    page.go_back()
                    page.wait_for_load_state("networkidle")

    except Exception as e:
        print(f"[TASKS ERROR] {e}")


def run_snow(stop_event: threading.Event, target_order_id: str):
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        context = browser.new_context(
            storage_state="servicenow_auth.json",
            ignore_https_errors=True,
        )
        page = context.new_page()

        try:
            while not stop_event.is_set():
                page.goto(build_order_list_url(target_order_id))
                page.wait_for_load_state("networkidle")

                rows = page.locator("table#wm_order_table tbody tr.list_row")

                for i in range(rows.count()):
                    row = rows.nth(i)

                    order_id = row.locator("td").nth(7).inner_text().strip()
                    state = row.locator("td").nth(4).inner_text().strip()

                    if order_id == target_order_id and state == "Work In Progress":
                        link = row.locator("td.vt a.linked.formlink").first

                        if link.count() > 0:
                            href = link.get_attribute("href")

                            if href:
                                page.goto(f"{SERVICE_NOW_URL}/{href}")
                                page.wait_for_load_state("networkidle")
                                process_tasks(page)
                                break

                time.sleep(3)

        finally:
            browser.close()


if __name__ == "__main__":
    stop_event = threading.Event()

    t1 = threading.Thread(
        target=run_snow,
        args=(stop_event, TARGET_ORDER_ID),
    )

    t2 = threading.Thread(
        target=wait_for_completed,
        args=(TARGET_ORDER_ID, stop_event),
    )

    t1.start()
    t2.start()

    t1.join()
    t2.join()
