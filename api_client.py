"""PM Surya Ghar vendor API client.

IMPORTANT: The portal's request field is encrypted. This module does not
pretend that changing district names inside an encrypted payload works.
Provide a legitimate, working request-builder for each state/district before
using fetch_vendors(). Do not commit credentials to GitHub.
"""
from __future__ import annotations

import os
from typing import Any, Callable, Mapping

import requests

API_URL = (
    "https://pmsuryaghar.gov.in/authenticate/api/verifyAccess/website/"
    "api/registeredVendor/getVendorByStateDistrict"
)


class VendorAPIError(RuntimeError):
    """Raised when the API request fails or has an unexpected response."""


# The builder must return the CURRENT encrypted request value and any
# dynamic headers required by the portal, e.g. x-ts. It must generate a
# DIFFERENT valid payload when the state/district selection changes.
RequestBuilder = Callable[[str, str], tuple[str, Mapping[str, str]]]


class VendorAPIClient:
    def __init__(
        self,
        token: str | None = None,
        request_builder: RequestBuilder | None = None,
        timeout: int = 30,
        session: requests.Session | None = None,
    ) -> None:
        self.token = (token or os.getenv("PMS_TOKEN", "")).strip()
        self.request_builder = request_builder
        self.timeout = timeout
        self.session = session or requests.Session()

    def fetch_vendors(self, state: str, district: str) -> Any:
        """Fetch live response; requires a verified portal request builder.

        Returns decoded JSON without guessing the server's response schema.
        """
        if not state.strip() or not district.strip():
            raise ValueError("Both state and district are required")
        if not self.token:
            raise VendorAPIError("Missing PMS_TOKEN (set it in environment/secrets)")
        if self.request_builder is None:
            raise VendorAPIError(
                "Live fetching is not configured: the portal requires an "
                "encrypted request payload. Supply a verified request_builder "
                "that generates the encrypted payload for each state/district."
            )

        encrypted_request, dynamic_headers = self.request_builder(state, district)
        if not isinstance(encrypted_request, str) or not encrypted_request:
            raise VendorAPIError("request_builder returned no encrypted request")

        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.token}",
            "x-encrypted": "true",
        }
        # Only accept expected dynamic headers; never allow overwriting auth.
        for key, value in dynamic_headers.items():
            if key.lower() not in {"x-ts"}:
                raise VendorAPIError(f"Unexpected dynamic header: {key}")
            headers[key] = str(value)

        try:
            response = self.session.post(
                API_URL,
                json={"request": encrypted_request},
                headers=headers,
                timeout=self.timeout,
            )
            response.raise_for_status()
            return response.json()
        except requests.RequestException as exc:
            raise VendorAPIError(f"Vendor API request failed: {exc}") from exc
        except ValueError as exc:
            raise VendorAPIError("Vendor API returned non-JSON content") from exc


if __name__ == "__main__":
    # Safe smoke test: explains what must be configured; no fake sample data.
    try:
        print(VendorAPIClient().fetch_vendors("Andhra Pradesh", "Eluru"))
    except VendorAPIError as exc:
        print(f"Not ready for live extraction: {exc}")
