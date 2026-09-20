import os
import time
import subprocess
from pathlib import Path
from typing import Optional
from selenium import webdriver
from selenium.webdriver.chrome.options import Options as ChromeOptions
from selenium.webdriver.edge.options import Options as EdgeOptions

from config.settings import (
    DEFAULT_HEADLESS,
    DEFAULT_PAGE_LOAD_TIMEOUT,
    DEFAULT_USER_AGENT,
    CHROME_PROFILE_DIR,
    EDGE_PROFILE_DIR,
    DATA_DIR
)
from src.utils.logger import logger

ACTIVE_BROWSER_FILE = DATA_DIR / "active_browser.txt"

class BrowserManager:
    """Manages Selenium WebDriver creation with anti-detection, user profile persistence, and crash prevention."""

    @staticmethod
    def get_active_browser() -> str:
        """Returns the browser that was last used or saved for login ('chrome' or 'edge')."""
        try:
            if ACTIVE_BROWSER_FILE.exists():
                name = ACTIVE_BROWSER_FILE.read_text(encoding="utf-8").strip().lower()
                if name in ("chrome", "edge"):
                    return name
        except Exception:
            pass
        return "chrome"

    @staticmethod
    def set_active_browser(browser_name: str):
        """Saves the active browser preference ('chrome' or 'edge')."""
        try:
            ACTIVE_BROWSER_FILE.write_text(browser_name.strip().lower(), encoding="utf-8")
        except Exception:
            pass

    @staticmethod
    def _clean_profile_lock(profile_dir: Path):
        """
        Safely removes stale lockfile and terminates orphaned project processes
        that could prevent Chrome or Edge from launching on Windows.
        """
        if not profile_dir.exists():
            return
        lock_file = profile_dir / "lockfile"
        if lock_file.exists():
            try:
                lock_file.unlink(missing_ok=True)
            except Exception:
                logger.info(f"Lockfile in {profile_dir.name} is in use. Terminating orphaned processes...")
                try:
                    cmd = f'Get-CimInstance Win32_Process | Where-Object {{ $_.CommandLine -like "*{profile_dir.name}*" }} | ForEach-Object {{ Stop-Process -Id $_.ProcessId -Force }}'
                    subprocess.run(["powershell", "-NoProfile", "-Command", cmd], capture_output=True, timeout=6)
                    time.sleep(0.5)
                    lock_file.unlink(missing_ok=True)
                except Exception as e:
                    logger.debug(f"Process cleanup notice: {e}")

    @staticmethod
    def _create_chrome_driver(headless: bool, use_profile: bool) -> webdriver.Remote:
        options = ChromeOptions()
        if headless:
            options.add_argument("--headless=new")
        options.add_argument("--disable-gpu")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--window-size=1920,1080")
        options.add_argument(f"user-agent={DEFAULT_USER_AGENT}")

        # Crash prevention & port conflict resolution
        options.add_argument("--remote-debugging-port=0")
        options.add_argument("--no-first-run")
        options.add_argument("--no-default-browser-check")
        options.add_argument("--disable-background-networking")

        if use_profile:
            CHROME_PROFILE_DIR.mkdir(parents=True, exist_ok=True)
            BrowserManager._clean_profile_lock(CHROME_PROFILE_DIR)
            options.add_argument(f"--user-data-dir={CHROME_PROFILE_DIR.resolve()}")

        # Stealth arguments
        options.add_argument("--disable-blink-features=AutomationControlled")
        options.add_experimental_option("excludeSwitches", ["enable-automation"])
        options.add_experimental_option("useAutomationExtension", False)

        # Suppress logs
        options.add_argument("--log-level=3")
        options.add_argument("--silent")

        driver = webdriver.Chrome(options=options)
        driver.set_page_load_timeout(DEFAULT_PAGE_LOAD_TIMEOUT)
        driver.execute_cdp_cmd(
            "Page.addScriptToEvaluateOnNewDocument",
            {
                "source": """
                    Object.defineProperty(navigator, 'webdriver', {
                        get: () => undefined
                    });
                """
            },
        )
        return driver

    @staticmethod
    def _create_edge_driver(headless: bool, use_profile: bool) -> webdriver.Remote:
        edge_options = EdgeOptions()
        if headless:
            edge_options.add_argument("--headless=new")
        edge_options.add_argument("--disable-gpu")
        edge_options.add_argument("--no-sandbox")
        edge_options.add_argument("--disable-dev-shm-usage")
        edge_options.add_argument("--window-size=1920,1080")
        edge_options.add_argument(f"user-agent={DEFAULT_USER_AGENT}")

        # Crash prevention & port conflict resolution
        edge_options.add_argument("--remote-debugging-port=0")
        edge_options.add_argument("--no-first-run")
        edge_options.add_argument("--no-default-browser-check")

        if use_profile:
            EDGE_PROFILE_DIR.mkdir(parents=True, exist_ok=True)
            BrowserManager._clean_profile_lock(EDGE_PROFILE_DIR)
            edge_options.add_argument(f"--user-data-dir={EDGE_PROFILE_DIR.resolve()}")

        # Stealth arguments
        edge_options.add_argument("--disable-blink-features=AutomationControlled")
        edge_options.add_experimental_option("excludeSwitches", ["enable-automation"])
        edge_options.add_experimental_option("useAutomationExtension", False)

        driver = webdriver.Edge(options=edge_options)
        driver.set_page_load_timeout(DEFAULT_PAGE_LOAD_TIMEOUT)
        return driver

    @classmethod
    def get_driver(
        cls,
        headless: bool = DEFAULT_HEADLESS,
        use_profile: bool = True,
        preferred_browser: Optional[str] = None
    ) -> webdriver.Remote:
        """
        Create and configure a Chrome or Edge WebDriver instance.
        If preferred_browser is specified, tries it first, else checks active_browser setting.
        Falls back seamlessly between Chrome and Edge with persistent profiles.
        """
        choice = preferred_browser or cls.get_active_browser()
        order = ["edge", "chrome"] if choice == "edge" else ["chrome", "edge"]

        errors = []
        for browser_name in order:
            try:
                if browser_name == "chrome":
                    driver = cls._create_chrome_driver(headless=headless, use_profile=use_profile)
                    cls.set_active_browser("chrome")
                    logger.info(f"Initialized Chrome WebDriver successfully (Profile: {use_profile}).")
                    return driver
                else:
                    driver = cls._create_edge_driver(headless=headless, use_profile=use_profile)
                    cls.set_active_browser("edge")
                    logger.info(f"Initialized Edge WebDriver successfully (Profile: {use_profile}).")
                    return driver
            except Exception as e:
                logger.warning(f"Failed to launch {browser_name}: {e}. Trying fallback...")
                errors.append(f"{browser_name}: {e}")

        raise RuntimeError(f"Neither Chrome nor Edge WebDriver could be initialized: {'; '.join(errors)}")

    @classmethod
    def launch_login_window(cls, preferred_browser: Optional[str] = None) -> bool:
        """
        Opens a visible browser window (Chrome or Edge) with persistent profile at https://www.threads.net/login.
        Saves user session permanently and remembers which browser was logged in.
        """
        try:
            logger.info("Opening visible browser for Threads login...")
            driver = cls.get_driver(headless=False, use_profile=True, preferred_browser=preferred_browser)
            driver.get("https://www.threads.net/login")
            return True
        except Exception as e:
            logger.error(f"Error launching login window: {e}")
            return False
