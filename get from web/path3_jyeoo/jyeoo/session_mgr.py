import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from .config import get_config
from .utils import logger


class SessionManager:
    def __init__(self):
        config = get_config()
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": config.user_agent,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            "Accept-Encoding": "gzip, deflate, br",
            "Connection": "keep-alive",
            "Cache-Control": "max-age=0",
            "Upgrade-Insecure-Requests": "1",
        })
        retry_strategy = Retry(
            total=config.max_retries,
            backoff_factor=1,
            status_forcelist=[429, 500, 502, 503, 504],
        )
        adapter = HTTPAdapter(max_retries=retry_strategy, pool_connections=5, pool_maxsize=5)
        self.session.mount("https://", adapter)
        self.session.mount("http://", adapter)
        self._timeout = config.timeout

    def get(self, url: str, referer: str | None = None, **kwargs) -> requests.Response | None:
        headers = {}
        if referer:
            headers["Referer"] = referer
        try:
            logger.debug(f"GET {url}")
            resp = self.session.get(url, headers=headers, timeout=self._timeout, **kwargs)
            resp.raise_for_status()
            return resp
        except requests.RequestException as e:
            logger.warning(f"Request failed: {url} - {e}")
            return None

    def post(self, url: str, data: dict | None = None, json: dict | None = None,
             referer: str | None = None, **kwargs) -> requests.Response | None:
        headers = {}
        if referer:
            headers["Referer"] = referer
        try:
            logger.debug(f"POST {url}")
            resp = self.session.post(url, data=data, json=json, headers=headers,
                                     timeout=self._timeout, **kwargs)
            resp.raise_for_status()
            return resp
        except requests.RequestException as e:
            logger.warning(f"Request failed: {url} - {e}")
            return None

    def save_cookies(self, path: str):
        import pickle
        with open(path, "wb") as f:
            pickle.dump(self.session.cookies, f)
        logger.info(f"Cookies saved to {path}")

    def load_cookies(self, path: str):
        import pickle
        try:
            with open(path, "rb") as f:
                self.session.cookies.update(pickle.load(f))
            logger.info(f"Cookies loaded from {path}")
            return True
        except FileNotFoundError:
            logger.warning(f"Cookie file not found: {path}")
            return False
