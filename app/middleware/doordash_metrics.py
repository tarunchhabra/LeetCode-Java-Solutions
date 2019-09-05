import time
import platform

from typing import Any, Dict, Optional

from starlette.exceptions import ExceptionMiddleware
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.exceptions import ExceptionMiddleware

from app.commons.context.req_context import get_context_from_req
from app.commons.config.app_config import StatsDConfig
from app.commons.routing import reset_breadcrumbs
from app.commons import tracing
from app.commons.stats import (
    init_statsd_from_config,
    set_service_stats_client,
    set_request_logger,
)

NORMALIZATION_TABLE = str.maketrans("/", "|", "{}")


def normalize_path(path: str):
    return path.translate(NORMALIZATION_TABLE)


class DoorDashMetricsMiddleware(BaseHTTPMiddleware):
    """
    Middleware to track API request level metrics for Superfund.
    These metrics are common across all DoorDash Services.
    """

    def __init__(self, app: ExceptionMiddleware, *, host: str, config: StatsDConfig):
        self.app = app
        self.statsd_client = init_statsd_from_config(
            host, config, additional_tags={"hostname": platform.node()}
        )

    async def dispatch_func(
        self: Any, request: Request, call_next: RequestResponseEndpoint
    ):
        breadcrumbs = reset_breadcrumbs(request._scope)

        context = get_context_from_req(request)

        method = request.method
        start_time = time.perf_counter()

        # make the request logger available to
        # app-level resources
        with set_request_logger(context.log):
            # get the response; the overridden routers
            # will append to the list of breadcrumbs
            response = await call_next(request)

        endpoint = normalize_path("".join(breadcrumbs))
        latency_ms = (time.perf_counter() - start_time) * 1000
        status_type = f"{response.status_code // 100}XX"
        # from the ASGI spec
        # https://github.com/django/asgiref/blob/master/specs/www.rst#L56
        path = request._scope.get("path", "")

        context.log.info(
            "request complete",
            path=path,
            endpoint=endpoint,
            method=method,
            status_code=str(response.status_code),
            latency=round(latency_ms, 3),
        )

        tags = {
            "endpoint": endpoint,
            "method": method,
            "status_code": str(response.status_code),
        }

        self.statsd_client.incr(status_type, 1, tags=tags)
        self.statsd_client.timing("latency", latency_ms, tags=tags)

        return response


class ServiceMetricsMiddleware(BaseHTTPMiddleware):
    """
    Middleware to Service level metrics for Superfund
    """

    def __init__(
        self,
        app: ExceptionMiddleware,
        *,
        app_name: str,
        host: str,
        config: StatsDConfig,
        additional_tags: Optional[Dict[str, str]] = None,
    ):
        self.app = app
        self.app_name = app_name
        self.statsd_client = init_statsd_from_config(
            host, config, additional_tags={"hostname": platform.node()}
        )

    async def dispatch_func(
        self: Any, request: Request, call_next: RequestResponseEndpoint
    ):
        # use the service's client instead of the global statsd client
        with set_service_stats_client(self.statsd_client), tracing.contextvar_as(
            tracing.APPLICATION_NAME, self.app_name
        ):
            response = await call_next(request)
        return response