import http.server
import socketserver
import requests
import re
import json
import base64
import threading

from http import HTTPStatus
from bs4 import BeautifulSoup
from urllib.parse import urlparse
from urllib.parse import parse_qs
from dataclasses import dataclass, field
from typing import List

from requests.adapters import HTTPAdapter
from urllib3.util import Retry


# Config default values
@dataclass
class DictConfig:
    port: int = 8771
    language: str = "zh"

    def set(self, config):
        self.__init__(**config)


_config = DictConfig()


class Dict:

    def __init__(self, config=_config):
        self.config = config
        self._set_session()

    def _set_session(self):

        retry_strategy = Retry(
            total=3,
            backoff_factor=1,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["HEAD", "GET", "OPTIONS"],
        )
        adapter = HTTPAdapter(max_retries=retry_strategy)
        self.session = requests.Session()
        self.session.mount("https://", adapter)
        self.session.mount("http://", adapter)
        # Use my personal user agent to try to avoid scraping detection
        self.session.headers.update(
            {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/105.0.0.0 Safari/537.36 Edg/105.0.1343.27",
                "Accept-Language": "en-US,en;q=0.5",
            }
        )

    def _get(self, path):

        url = "https://" + self.config.language + ".thefreedictionary.com" + path

        print(url)
        try:
            return self.session.get(url, timeout=10).text

        except Exception:
            self._set_session()
            return self.session.get(url, timeout=10).text

    def word(self, w):
        """
        Scrape forvo's word page for audio sources
        """
        w = w.strip()
        if len(w) == 0:
            return []
        path = "/" + w
        html = self._get(path)
        soup = BeautifulSoup(html, features="html.parser")

        # Locate the specific element
        # class = "i snd-icon-plain" is the element that contains the audio URL
        span_element = soup.find("span", {"class": "snd2"})

        if span_element is None:
            return []

        # Extract the 'onclick' attribute value
        data_value = span_element["data-snd"]

        import re

        # Extract the URL from the 'onclick' attribute value
        url = "img2.tfd.com/pron/mp3/" + data_value + ".mp3"
        url = "https://" + url

        return {"url": url}


class DictHandler(http.server.SimpleHTTPRequestHandler):
    dict = Dict(config=_config)

    # By default, SimpleHTTPRequestHandler logs to stderr
    # This would cause Anki to show an error, even on successful requests
    # log_error is still a useful function though, so replace it with the inherited log_message
    # Make log_message do nothing
    def log_error(self, *args, **kwargs):
        super().log_message(*args, **kwargs)

    def log_message(self, *args):
        pass

    def do_GET(self):
        print("GET request,\nPath: %s\nHeaders:\n%s\n", str(self.path), str(self.headers))
        # Extract 'term' and 'reading' query parameters
        query_components = parse_qs(urlparse(self.path).query)
        term = query_components["term"][0] if "term" in query_components else ""

        # Yomichan used to use "expression" but renamed to term. Still support "expression" for older versions
        expression = query_components["expression"][0] if "expression" in query_components else ""
        if term == "":
            term = expression

        # Allow overriding the language
        self.dict.config.language = query_components.get("language", [self.dict.config.language])[0]

        # Try looking for word sources for 'term' first
        audio_source = self.dict.word(term)

        resp = {"type": "audioSourceList", "audioSources": [audio_source]}

        # Writing the JSON contents with UTF-8
        payload = bytes(json.dumps(resp), "utf8")
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-type", "application/json")
        self.send_header("Content-length", str(len(payload)))
        self.end_headers()
        try:
            self.wfile.write(payload)
        except BrokenPipeError:
            self.log_error("BrokenPipe when sending reply")

        return


# MAIN
"""
from aqt import mw

_config.set(mw.addonManager.getConfig(__name__))
httpd = http.server.ThreadingHTTPServer(("localhost", _config.port), DictHandler)
server_thread = threading.Thread(target=httpd.serve_forever)
server_thread.daemon = True
server_thread.start()
"""
print("Running in debug mode...")
httpd = socketserver.TCPServer(("localhost", 8771), DictHandler)
httpd.serve_forever()
