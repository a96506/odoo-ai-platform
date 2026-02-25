"""
Odoo XML-RPC client for programmatic access to all Odoo models.
Handles authentication, CRUD operations, and method execution.
"""

import ssl
import xmlrpc.client
from typing import Any
from contextlib import contextmanager

import structlog
from tenacity import retry, stop_after_attempt, wait_exponential

from app.config import get_settings

logger = structlog.get_logger()


def _make_ssl_context() -> ssl.SSLContext:
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    return ctx


class OdooClient:
    def __init__(
        self,
        url: str | None = None,
        db: str | None = None,
        username: str | None = None,
        password: str | None = None,
    ):
        settings = get_settings()
        self.url = url or settings.odoo_url
        self.db = db or settings.odoo_db
        self.username = username or settings.odoo_username
        self.password = password or settings.odoo_auth
        self._uid: int | None = None
        self._common: xmlrpc.client.ServerProxy | None = None
        self._object: xmlrpc.client.ServerProxy | None = None
        self._ssl_context = _make_ssl_context() if self.url.startswith("https") else None

    @property
    def common(self) -> xmlrpc.client.ServerProxy:
        if self._common is None:
            self._common = xmlrpc.client.ServerProxy(
                f"{self.url}/xmlrpc/2/common",
                allow_none=True,
                context=self._ssl_context,
            )
        return self._common

    @property
    def object(self) -> xmlrpc.client.ServerProxy:
        if self._object is None:
            self._object = xmlrpc.client.ServerProxy(
                f"{self.url}/xmlrpc/2/object",
                allow_none=True,
                context=self._ssl_context,
            )
        return self._object

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=10))
    def authenticate(self) -> int:
        if self._uid is not None:
            return self._uid
        self._uid = self.common.authenticate(
            self.db, self.username, self.password, {}
        )
        if not self._uid:
            raise ConnectionError(
                f"Failed to authenticate with Odoo at {self.url}"
            )
        logger.info("odoo_authenticated", uid=self._uid, url=self.url)
        return self._uid

    @property
    def uid(self) -> int:
        if self._uid is None:
            self.authenticate()
        return self._uid  # type: ignore

    def _execute(
        self, model: str, method: str, *args: Any, **kwargs: Any
    ) -> Any:
        return self.object.execute_kw(
            self.db, self.uid, self.password, model, method, args, kwargs
        )

    def search(
        self,
        model: str,
        domain: list,
        offset: int = 0,
        limit: int | None = None,
        order: str | None = None,
    ) -> list[int]:
        kwargs: dict[str, Any] = {"offset": offset}
        if limit is not None:
            kwargs["limit"] = limit
        if order is not None:
            kwargs["order"] = order
        return self._execute(model, "search", domain, **kwargs)

    def read(
        self, model: str, ids: list[int], fields: list[str] | None = None
    ) -> list[dict]:
        kwargs = {}
        if fields:
            kwargs["fields"] = fields
        return self._execute(model, "read", ids, **kwargs)

    def search_read(
        self,
        model: str,
        domain: list,
        fields: list[str] | None = None,
        offset: int = 0,
        limit: int | None = None,
        order: str | None = None,
    ) -> list[dict]:
        kwargs: dict[str, Any] = {"offset": offset}
        if fields:
            kwargs["fields"] = fields
        if limit is not None:
            kwargs["limit"] = limit
        if order is not None:
            kwargs["order"] = order
        return self._execute(model, "search_read", domain, **kwargs)

    def create(self, model: str, values: dict) -> int:
        result = self._execute(model, "create", values)
        logger.info("odoo_record_created", model=model, record_id=result)
        return result

    def write(self, model: str, ids: list[int], values: dict) -> bool:
        result = self._execute(model, "write", ids, values)
        logger.info("odoo_record_updated", model=model, ids=ids)
        return result

    def unlink(self, model: str, ids: list[int]) -> bool:
        result = self._execute(model, "unlink", ids)
        logger.info("odoo_record_deleted", model=model, ids=ids)
        return result

    def search_count(self, model: str, domain: list) -> int:
        return self._execute(model, "search_count", domain)

    def fields_get(
        self, model: str, attributes: list[str] | None = None
    ) -> dict:
        kwargs = {}
        if attributes:
            kwargs["attributes"] = attributes
        return self._execute(model, "fields_get", **kwargs)

    def execute_method(
        self, model: str, method: str, record_ids: list[int], *args: Any
    ) -> Any:
        """Call any arbitrary method on an Odoo model."""
        return self._execute(model, method, record_ids, *args)

    def get_record(
        self, model: str, record_id: int, fields: list[str] | None = None
    ) -> dict | None:
        records = self.read(model, [record_id], fields)
        return records[0] if records else None

    def version(self) -> dict:
        return self.common.version()


_client: OdooClient | None = None


def get_odoo_client() -> OdooClient:
    global _client
    if _client is None:
        _client = OdooClient()
        _client.authenticate()
    return _client
