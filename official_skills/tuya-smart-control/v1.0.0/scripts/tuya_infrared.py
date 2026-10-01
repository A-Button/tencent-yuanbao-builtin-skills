"""Infrared operations mixed into TuyaAPI; use the shared credentials and endpoint."""
from typing import Any, Dict, Optional
import urllib.parse


class InfraredMixin:
    """Code-library lookup, remote management and infrared dispatch."""

    @staticmethod
    def _segment(value: str) -> str:
        return urllib.parse.quote(str(value), safe="")

    def _device_path(self, device_id: str) -> str:
        return f"/v1.0/end-user/devices/{self._segment(device_id)}/infrareds"

    def get_categories(self, device_id: str) -> Any:
        return self._infrared_request("GET", f"{self._device_path(device_id)}/categories")

    def get_remotes(self, device_id: str) -> Any:
        """Return virtual remotes configured under an infrared gateway."""
        return self._infrared_request("GET", f"{self._device_path(device_id)}/remotes")

    def get_remote_keys(self, device_id: str, remote_id: str) -> Any:
        """Return keys and parameter ranges supported by one virtual remote."""
        return self._infrared_request(
            "GET",
            f"{self._device_path(device_id)}/remotes/{self._segment(remote_id)}/keys",
        )

    def get_remote_rules(
        self, device_id: str, category_id: int, brand_id: int, remote_index: int
    ) -> Any:
        """Return underlying infrared code rules for a code-library remote."""
        return self._infrared_request(
            "GET",
            f"{self._device_path(device_id)}/categories/{category_id}/brands/"
            f"{brand_id}/remotes/{remote_index}/rules",
        )

    def get_remote_brands(
        self,
        device_id: str,
        category_id: int,
        remote_index: int,
        country_code: Optional[str] = None,
    ) -> Any:
        """Return candidate brands for a code-library remote index."""
        return self._infrared_request(
            "GET",
            f"{self._device_path(device_id)}/categories/{category_id}/remotes/"
            f"{remote_index}/brands",
            query={"countryCode": country_code} if country_code else None,
        )

    def get_brands(
        self, device_id: str, category_id: int, country_code: Optional[str] = "CN"
    ) -> Any:
        return self._infrared_request(
            "GET",
            f"{self._device_path(device_id)}/categories/{category_id}/brands",
            query={"countryCode": country_code},
        )

    def get_remote_indexes(
        self,
        device_id: str,
        category_id: int,
        brand_id: int,
        country_code: Optional[str] = "CN",
        mode: Optional[str] = None,
        page: int = 1,
        size: int = 100,
    ) -> Any:
        if not isinstance(page, int) or isinstance(page, bool) or page < 1:
            raise ValueError("page must be a positive integer")
        if not isinstance(size, int) or isinstance(size, bool) or not 1 <= size <= 1000:
            raise ValueError("size must be an integer between 1 and 1000")
        return self._infrared_request(
            "GET",
            f"{self._device_path(device_id)}/categories/{category_id}/brands/{brand_id}/remote-indexs",
            query={
                "countryCode": country_code,
                "mode": mode,
                "page": page,
                "size": size,
            },
        )

    def add_remote(
        self,
        device_id: str,
        category_id: int,
        remote_index: int,
        remote_name: str,
        brand_id: Optional[int] = None,
        brand_name: Optional[str] = None,
    ) -> str:
        return self._infrared_request(
            "POST",
            f"{self._device_path(device_id)}/remotes",
            body={
                "category_id": category_id,
                "brand_id": brand_id,
                "brand_name": brand_name,
                "remote_index": remote_index,
                "remote_name": remote_name,
            },
        )

    def delete_remote(self, device_id: str, remote_id: str) -> bool:
        return self._infrared_request(
            "DELETE",
            f"{self._device_path(device_id)}/remotes/{self._segment(remote_id)}",
        )

    def rename_remote(self, device_id: str, remote_id: str, remote_name: str) -> bool:
        return self._infrared_request(
            "PUT",
            f"{self._device_path(device_id)}/remotes/{self._segment(remote_id)}",
            body={"remoteName": remote_name},
        )

    def test_standard_command(
        self,
        device_id: str,
        category_id: int,
        key: str,
        remote_index: Optional[int] = None,
    ) -> bool:
        return self._infrared_request(
            "POST",
            f"{self._device_path(device_id)}/testing/command",
            body={
                "category_id": category_id,
                "remote_index": remote_index,
                "key": key,
            },
        )

    def test_raw_command(
        self,
        device_id: str,
        category_id: int,
        remote_index: Optional[int] = None,
        key: Optional[str] = None,
        key_id: Optional[int] = None,
    ) -> bool:
        body = self._raw_body(category_id, remote_index, key, key_id)
        return self._infrared_request(
            "POST", f"{self._device_path(device_id)}/testing/raw/command", body=body
        )

    def send_standard_command(
        self,
        device_id: str,
        remote_id: str,
        category_id: int,
        key: str,
        remote_index: Optional[int] = None,
    ) -> bool:
        return self._infrared_request(
            "POST",
            f"{self._device_path(device_id)}/remotes/{self._segment(remote_id)}/command",
            body={
                "category_id": category_id,
                "remote_index": remote_index,
                "key": key,
            },
        )

    def send_raw_command(
        self,
        device_id: str,
        remote_id: str,
        category_id: int,
        remote_index: Optional[int] = None,
        key: Optional[str] = None,
        key_id: Optional[int] = None,
    ) -> bool:
        body = self._raw_body(category_id, remote_index, key, key_id)
        return self._infrared_request(
            "POST",
            f"{self._device_path(device_id)}/remotes/{self._segment(remote_id)}/raw/command",
            body=body,
        )

    @staticmethod
    def _raw_body(
        category_id: int,
        remote_index: Optional[int],
        key: Optional[str],
        key_id: Optional[int],
    ) -> Dict[str, Any]:
        if not key and key_id is None:
            raise ValueError("原始按键指令必须提供 key 或 key_id")
        return {
            "category_id": category_id,
            "remote_index": remote_index,
            "key": key,
            "key_id": key_id,
        }
