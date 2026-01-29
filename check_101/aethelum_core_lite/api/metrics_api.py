"""
指标查询API

提供简化的指标查询接口，支持API密钥认证。
"""

from fastapi import FastAPI, HTTPException, Security, status, Depends
from typing import Dict, Any, Optional
import time
import uvicorn
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials


class MetricsAPI:
    """指标查询API封装类

    将全局状态封装到类中，支持多实例部署。
    """

    def __init__(self, router=None, api_key: Optional[str] = None):
        """初始化API

        Args:
            router: Router实例
            api_key: API密钥（必填，安全要求）

        Raises:
            ValueError: 如果未提供api_key
        """
        if api_key is None:
            raise ValueError(
                "必须设置api_key（安全要求：禁止无认证访问）"
            )

        self._router = router
        self._api_key = api_key
        # 强制要求认证
        self._require_auth = True
        self._security = HTTPBearer(auto_error=False)
        self.app = FastAPI(
            title="AethelumCoreLite Metrics API",
            version="2.0.0",
            description="AethelumCoreLite指标查询API，强制要求API密钥认证"
        )

        # 注册路由
        self._setup_routes()

    def _setup_routes(self):
        """设置API路由"""
        self.app.get("/api/v1/health")(self._health_check_wrapper)
        self.app.get("/api/v1/metrics")(self._get_metrics_wrapper)

    def set_router(self, router):
        """设置Router实例"""
        self._router = router

    def set_api_key(self, api_key: Optional[str]):
        """设置API密钥"""
        self._api_key = api_key
        self._require_auth = api_key is not None

    async def verify_api_key(
        self,
        credentials: Optional[HTTPAuthorizationCredentials] = None
    ):
        """
        验证API密钥

        **安全要求**：必须设置api_key，禁止无认证访问。

        - 必须在配置文件中设置api_key
        - 所有API请求都必须提供有效的Bearer Token
        - 生产环境强制要求认证
        """
        if self._require_auth and credentials is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="API密钥缺失",
                headers={"WWW-Authenticate": "Bearer"},
            )

        # 安全要求：必须设置 api_key
        if not self._require_auth:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="必须设置api_key（安全要求：禁止无认证访问）"
            )

        # 验证密钥
        if credentials.credentials != self._api_key:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="无效的API密钥"
            )

        return True

    async def _health_check_wrapper(self, credentials: HTTPAuthorizationCredentials = Security(self._security)):
        """健康检查包装器（处理认证）"""
        await self.verify_api_key(credentials)
        return await self.health_check()

    async def _get_metrics_wrapper(self, credentials: HTTPAuthorizationCredentials = Security(self._security)):
        """获取指标包装器（处理认证）"""
        await self.verify_api_key(credentials)
        return await self.get_metrics()

    async def health_check(self):
        """健康检查"""
        return {
            "status": "healthy",
            "timestamp": time.time(),
            "service": "aethelum-core-lite",
            "authenticated": self._require_auth
        }

    async def get_metrics(self) -> Dict[str, Any]:
        """
        获取所有指标数据

        说明：
        - 返回所有队列、Worker、Router的指标
        - 复杂查询和过滤使用Prometheus完成
        - Prometheus地址：http://127.0.0.1:8000/metrics
        - 需要API密钥认证（如果已配置）
        """
        if not self._router:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Router not initialized"
            )

        return self._router.get_metrics()


class MetricsAPIServer:
    """指标查询API服务器

    安全要求：必须提供api_key参数
    """

    def __init__(self,
                 host: str = "127.0.0.1",
                 port: int = 8080,
                 router=None,
                 api_key: Optional[str] = None):
        """初始化API服务器

        Args:
            host: 监听地址
            port: 监听端口
            router: Router实例
            api_key: API密钥（必填，安全要求）

        Raises:
            ValueError: 如果未提供api_key
        """
        if api_key is None:
            raise ValueError(
                "必须设置api_key（安全要求：禁止无认证访问）"
            )

        self.host = host
        self.port = port

        # 使用新的 MetricsAPI 类
        self.metrics_api = MetricsAPI(router=router, api_key=api_key)

    def start(self):
        """启动API服务器"""
        uvicorn.run(
            self.metrics_api.app,
            host=self.host,
            port=self.port,
            log_level="info"
        )

    def get_app(self):
        """获取 FastAPI 应用实例（用于测试）"""
        return self.metrics_api.app
