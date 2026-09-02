"""运营埋点中间件: 记录 API/页面请求到 AnalyticsEvent。"""
from __future__ import annotations

import time


class AnalyticsMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        start = time.time()
        response = self.get_response(request)
        duration_ms = int((time.time() - start) * 1000)
        path = request.path or ""
        try:
            if path.startswith(("/api/", "/admin/")) or (
                not path.startswith(("/static/", "/favicon.ico"))
                and not path.endswith((".js", ".css", ".png", ".ico"))
            ):
                from .models import AnalyticsEvent

                AnalyticsEvent.objects.create(
                    event_type="request",
                    method=request.method or "",
                    path=path,
                    status_code=response.status_code,
                    duration_ms=duration_ms,
                    username=(request.user.username if request.user.is_authenticated else ""),
                    ip=getattr(request, "META", {}).get("REMOTE_ADDR", "") or "",
                )
        except Exception:
            pass  # 埋点失败不影响业务
        return response
