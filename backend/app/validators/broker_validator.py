import time
from dataclasses import dataclass

from selenium import webdriver
from selenium.common.exceptions import NoSuchElementException, StaleElementReferenceException, TimeoutException
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import Select, WebDriverWait

from app.core.common import build_result


VWORLD_BROKER_URL = "https://www.vworld.kr/dtld/broker/dtld_list_s001.do"


@dataclass
class BrokerSearchInput:
    sido: str
    sigungu: str
    registration_number: str


def build_search_debug(search_input: BrokerSearchInput) -> dict:
    return {
        "sido": search_input.sido,
        "sigungu": search_input.sigungu,
        "registration_number": search_input.registration_number,
    }


def create_driver() -> webdriver.Chrome:
    options = webdriver.ChromeOptions()
    options.add_argument("--headless=new")
    options.add_argument("--window-size=1920,1080")
    options.add_argument("--disable-gpu")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    return webdriver.Chrome(options=options)


def is_retryable_dom_error(error: Exception) -> bool:
    return isinstance(error, (NoSuchElementException, StaleElementReferenceException, TimeoutException))


def wait_until_sigungu_loaded(driver, target_sigungu: str, timeout: float = 10.0):
    end_time = time.time() + timeout

    while time.time() < end_time:
        try:
            sigungu_select = driver.find_element(By.ID, "sigunguCd")
            options = sigungu_select.find_elements(By.TAG_NAME, "option")
            texts = [opt.text.strip() for opt in options]

            if target_sigungu in texts:
                return
        except (NoSuchElementException, StaleElementReferenceException):
            pass

        time.sleep(0.2)

    raise TimeoutException(f"시군구 옵션 로딩 실패: {target_sigungu}")


def select_sido(driver, sido_name: str):
    select_option_by_text(driver, "sidoCd", sido_name)


def select_sigungu(driver, sigungu_name: str):
    select_option_by_text(driver, "sigunguCd", sigungu_name)


def select_option_by_text(driver, select_id: str, visible_text: str, timeout: float = 10.0):
    end_time = time.time() + timeout

    while time.time() < end_time:
        try:
            select_element = WebDriverWait(driver, 2).until(
                EC.presence_of_element_located((By.ID, select_id))
            )
            select_box = Select(select_element)
            option_texts = [option.text.strip() for option in select_box.options]

            if visible_text not in option_texts:
                time.sleep(0.2)
                continue

            select_box.select_by_visible_text(visible_text)
            return
        except (NoSuchElementException, StaleElementReferenceException):
            time.sleep(0.2)

    raise TimeoutException(f"선택 옵션 로딩 실패: {select_id}={visible_text}")


def input_registration_number(driver, registration_number: str):
    end_time = time.time() + 10.0

    while time.time() < end_time:
        try:
            reg_input = WebDriverWait(driver, 2).until(
                EC.presence_of_element_located((By.ID, "v_ra_regno"))
            )
            reg_input.clear()
            reg_input.send_keys(registration_number)
            return
        except (NoSuchElementException, StaleElementReferenceException):
            time.sleep(0.2)

    raise TimeoutException("등록번호 입력 필드를 안정적으로 찾지 못했습니다.")


def wait_for_loading_to_finish(driver, timeout: float = 10.0):
    end_time = time.time() + timeout

    while time.time() < end_time:
        try:
            loading_elements = driver.find_elements(By.CSS_SELECTOR, "div.loading")
            visible_loading = []
            for element in loading_elements:
                try:
                    if element.is_displayed():
                        visible_loading.append(element)
                except StaleElementReferenceException:
                    visible_loading.append(element)

            if not visible_loading:
                return
        except StaleElementReferenceException:
            pass
        time.sleep(0.2)

    raise TimeoutException("로딩 오버레이가 사라지지 않았습니다.")


def submit_search(driver):
    wait_for_loading_to_finish(driver)
    driver.execute_script("fnSearch();")


def wait_for_result_render(driver, timeout: float = 10.0):
    WebDriverWait(driver, timeout).until(
        EC.presence_of_element_located(
            (By.XPATH, "//table[caption[contains(., '부동산중개업 조회결과')]]")
        )
    )
    wait_for_loading_to_finish(driver, timeout=timeout)


def parse_result_from_dom(driver) -> dict:
    end_time = time.time() + 10.0

    while time.time() < end_time:
        try:
            table = driver.find_element(
                By.XPATH,
                "//table[caption[contains(., '부동산중개업 조회결과')]]"
            )
            tbody = table.find_element(By.TAG_NAME, "tbody")
            rows = tbody.find_elements(By.TAG_NAME, "tr")

            if not rows:
                return build_result(
                    status="query_failed",
                    error_code="RESULT_ROW_NOT_FOUND",
                    error_message="조회결과 행을 찾지 못했습니다."
                )

            first_row = rows[0]
            row_text = first_row.text.strip()

            if "검색된 결과가 없습니다" in row_text:
                return build_result(status="not_found")

            cells = first_row.find_elements(By.TAG_NAME, "td")
            values = [cell.text.strip() for cell in cells]

            if len(values) < 5:
                return build_result(
                    status="query_failed",
                    error_code="ROW_PARSE_FAILED",
                    error_message=f"조회결과 행 파싱 실패. cell_count={len(values)}",
                    debug={"row_values": values}
                )

            parsed = {
                "no": values[0] if len(values) > 0 else None,
                "registration_number": values[1] if len(values) > 1 else None,
                "office_name": values[2] if len(values) > 2 else None,
                "office_address": values[3] if len(values) > 3 else None,
                "representative_name": values[4] if len(values) > 4 else None,
                "registration_date": values[5] if len(values) > 5 else None,
                "status_text": values[6] if len(values) > 6 else None,
                "start_date": values[7] if len(values) > 7 else None,
                "end_date": values[8] if len(values) > 8 else None,
            }

            return build_result(status="success", data=parsed)
        except (NoSuchElementException, StaleElementReferenceException):
            time.sleep(0.2)

    return build_result(
        status="query_failed",
        error_code="RESULT_TABLE_NOT_FOUND",
        error_message="조회결과 테이블을 안정적으로 읽지 못했습니다."
    )


def perform_broker_search(driver, search_input: BrokerSearchInput) -> dict:
    driver.get(VWORLD_BROKER_URL)

    WebDriverWait(driver, 10).until(
        EC.presence_of_element_located((By.ID, "sidoCd"))
    )

    select_sido(driver, search_input.sido)
    wait_until_sigungu_loaded(driver, search_input.sigungu)
    select_sigungu(driver, search_input.sigungu)
    input_registration_number(driver, search_input.registration_number)
    submit_search(driver)
    wait_for_result_render(driver)

    result = parse_result_from_dom(driver)
    result["debug"].update(build_search_debug(search_input))
    result["debug"]["current_url"] = driver.current_url
    return result


def search_broker(search_input: BrokerSearchInput) -> dict:
    last_error: Exception | None = None

    for attempt in range(1, 4):
        driver = create_driver()
        debug = build_search_debug(search_input)
        debug["attempt"] = attempt
        try:
            return perform_broker_search(driver, search_input)
        except TimeoutException as error:
            last_error = error
            if attempt == 3:
                return build_result(
                    status="query_failed",
                    error_code="TIMEOUT",
                    error_message=str(error),
                    debug=debug,
                )
        except Exception as error:
            last_error = error
            if not is_retryable_dom_error(error) or attempt == 3:
                return build_result(
                    status="query_failed",
                    error_code="UNEXPECTED_ERROR",
                    error_message=str(error),
                    debug=debug,
                )
            time.sleep(0.5)
        finally:
            driver.quit()

    return build_result(
        status="query_failed",
        error_code="UNEXPECTED_ERROR",
        error_message=str(last_error) if last_error else "알 수 없는 오류가 발생했습니다.",
        debug=build_search_debug(search_input),
    )
