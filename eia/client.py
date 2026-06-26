import os
import subprocess
from typing import Any

import requests
from dotenv import load_dotenv

load_dotenv()

BASE_URL = "https://api.eia.gov/v2"
_KEYCHAIN_ACCOUNT = "eia"
_KEYCHAIN_SERVICE = "eia-api-key"


class EIAError(Exception):
    pass


def _keychain_get() -> str | None:
    try:
        result = subprocess.run(
            ["security", "find-generic-password", "-a", _KEYCHAIN_ACCOUNT, "-s", _KEYCHAIN_SERVICE, "-w"],
            capture_output=True, text=True, timeout=5,
        )
        return result.stdout.strip() if result.returncode == 0 else None
    except Exception:
        return None


class EIAClient:
    def __init__(self, api_key: str | None = None):
        self.api_key = api_key or _keychain_get() or os.environ.get("EIA_API_KEY")
        if not self.api_key:
            raise EIAError(
                "No EIA API key found. Checked: macOS Keychain, EIA_API_KEY env var, .env file.\n"
                "To store in Keychain: security add-generic-password -a eia -s eia-api-key -w YOUR_KEY\n"
                "Register at: https://www.eia.gov/opendata/register.php"
            )
        self._session = requests.Session()

    def get(self, path: str = "", **params: Any) -> dict:
        url = f"{BASE_URL}/{path.strip('/')}" if path else BASE_URL
        params["api_key"] = self.api_key
        try:
            resp = self._session.get(url, params=params, timeout=30)
            resp.raise_for_status()
        except requests.HTTPError as e:
            raise EIAError(f"HTTP {resp.status_code}: {resp.text[:200]}") from e
        except requests.RequestException as e:
            raise EIAError(f"Request failed: {e}") from e

        body = resp.json()
        # v2 API wraps payload in {"response": {...}}
        return body.get("response", body)
