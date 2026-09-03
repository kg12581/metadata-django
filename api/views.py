"""对外 REST 接口视图层。

当前实现复用 common.views(内部业务逻辑), 接口契约与路由统一收敛在 api 包,
便于后续把对外视图逐个拆到本模块。
"""
from common.views import *  # noqa: F401,F403
