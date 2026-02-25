import logging
import os
import shutil
import subprocess
import tempfile
import time

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
from webdriver_manager.chrome import ChromeDriverManager


logger = logging.getLogger(__name__)


class BrowserAutomationService:
    def automate(self, action_type, **kwargs):
        driver = None
        temp_dir = None
        try:
            try:
                subprocess.run(['pkill', '-f', 'chrome.*--user-data-dir=/tmp/chrome_'], capture_output=True, timeout=3)
                subprocess.run(['pkill', '-f', 'brave.*--user-data-dir=/tmp/chrome_'], capture_output=True, timeout=3)
                time.sleep(1)
                logger.info("Cleaned up previous browser automation instances")
            except Exception as e:
                logger.debug(f"Browser cleanup: {e}")

            brave_paths = [
                '/usr/bin/brave-browser',
                '/usr/bin/brave',
                '/snap/bin/brave',
                '/opt/brave.com/brave/brave-browser',
            ]

            brave_binary = None
            for path in brave_paths:
                if os.path.exists(path):
                    brave_binary = path
                    logger.info(f"Found Brave browser at: {path}")
                    break

            chrome_options = Options()
            temp_dir = tempfile.mkdtemp(prefix="chrome_")
            chrome_options.add_argument(f'--user-data-dir={temp_dir}')
            chrome_options.add_argument('--no-first-run')
            chrome_options.add_argument('--no-default-browser-check')
            chrome_options.add_argument('--no-sandbox')
            chrome_options.add_argument('--disable-dev-shm-usage')
            chrome_options.add_argument('--disable-blink-features=AutomationControlled')
            chrome_options.add_experimental_option('excludeSwitches', ['enable-automation'])
            chrome_options.add_experimental_option('useAutomationExtension', False)

            if brave_binary:
                chrome_options.binary_location = brave_binary
                logger.info("Using Brave browser with ad blocking")

            service = Service(ChromeDriverManager().install())
            driver = webdriver.Chrome(service=service, options=chrome_options)
            driver.set_page_load_timeout(30)

            result = ""

            if action_type == "youtube_play":
                search_query = kwargs.get("query", "")
                driver.get("https://www.youtube.com")
                time.sleep(3)

                try:
                    reject_button = driver.find_element(By.XPATH, "//button[@aria-label='Reject all']")
                    reject_button.click()
                    time.sleep(1)
                except Exception:
                    pass

                try:
                    search_box = WebDriverWait(driver, 10).until(
                        EC.presence_of_element_located((By.NAME, "search_query"))
                    )
                    search_box.send_keys(search_query)
                    search_box.send_keys(Keys.RETURN)
                    time.sleep(5)

                    def try_skip_ad():
                        try:
                            skip_selectors = [
                                "button.ytp-ad-skip-button",
                                "button.ytp-skip-ad-button",
                                ".ytp-ad-skip-button-container button",
                                "button[aria-label*='Skip']",
                            ]
                            for selector in skip_selectors:
                                try:
                                    skip_btn = driver.find_element(By.CSS_SELECTOR, selector)
                                    if skip_btn.is_displayed():
                                        skip_btn.click()
                                        logger.info("Skipped ad successfully")
                                        return True
                                except Exception:
                                    pass
                        except Exception:
                            pass
                        return False

                    video_clicked = False
                    selectors = [
                        "ytd-video-renderer a#video-title",
                        "a#video-title",
                        "ytd-video-renderer .title-and-badge a",
                        "#video-title.yt-simple-endpoint",
                        "ytd-video-renderer h3 a",
                    ]

                    for selector in selectors:
                        try:
                            videos = driver.find_elements(By.CSS_SELECTOR, selector)
                            if videos and len(videos) > 0:
                                first_video = videos[0]
                                driver.execute_script("arguments[0].scrollIntoView({behavior: 'smooth', block: 'center'});", first_video)
                                time.sleep(1)
                                try:
                                    first_video.click()
                                    video_clicked = True
                                    time.sleep(3)
                                    for _ in range(3):
                                        if try_skip_ad():
                                            break
                                        time.sleep(1)
                                    result = f"▶️ Playing: {search_query}"
                                    break
                                except Exception:
                                    driver.execute_script("arguments[0].click();", first_video)
                                    video_clicked = True
                                    time.sleep(3)
                                    for _ in range(3):
                                        if try_skip_ad():
                                            break
                                        time.sleep(1)
                                    result = f"▶️ Playing: {search_query}"
                                    break
                        except Exception as e:
                            logger.info(f"Selector {selector} failed: {e}")
                            continue

                    if not video_clicked:
                        try:
                            videos = driver.find_elements(By.CSS_SELECTOR, "a#video-title")
                            if videos and len(videos) > 0:
                                video_url = videos[0].get_attribute('href')
                                if video_url:
                                    driver.get(video_url)
                                    video_clicked = True
                                    time.sleep(3)
                                    for _ in range(5):
                                        if try_skip_ad():
                                            break
                                        time.sleep(1)
                                    result = f"▶️ Playing: {search_query}"
                        except Exception as e:
                            logger.error(f"Direct navigation failed: {e}")

                    if not video_clicked:
                        result = f"⚠️ Opened YouTube search for: {search_query} (couldn't auto-play, please click manually)"

                except Exception as e:
                    logger.error(f"YouTube automation error: {e}")
                    result = "⚠️ YouTube search opened, manual interaction needed"

            elif action_type == "web_search":
                query = kwargs.get("query", "")
                search_engine = kwargs.get("engine", "google")

                if search_engine == "google":
                    driver.get("https://www.google.com")
                    search_box = WebDriverWait(driver, 10).until(
                        EC.presence_of_element_located((By.NAME, "q"))
                    )
                    search_box.send_keys(query)
                    search_box.send_keys(Keys.RETURN)
                    result = f"🔍 Searched Google for: {query}"

            elif action_type == "open_url":
                url = kwargs.get("url", "")
                driver.get(url)
                result = f"🌐 Opened: {url}"

            elif action_type == "custom":
                instructions = kwargs.get("instructions", "")
                url = kwargs.get("url", "https://google.com")
                driver.get(url)
                result = f"🤖 Automated browser: {instructions}"

            if action_type == "youtube_play":
                try:
                    while True:
                        time.sleep(3600)
                except KeyboardInterrupt:
                    pass
                return result

            time.sleep(30)
            if driver:
                driver.quit()
            if temp_dir:
                shutil.rmtree(temp_dir, ignore_errors=True)
            return result

        except Exception as e:
            logger.error(f"Browser automation error: {e}")
            if driver:
                try:
                    driver.quit()
                except Exception:
                    pass
            if temp_dir:
                shutil.rmtree(temp_dir, ignore_errors=True)
            return f"❌ Browser automation failed: {str(e)}"
