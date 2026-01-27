"""
OpenTelemetry分布式追踪管理器

提供分布式追踪功能，集成Jaeger。
"""

import logging
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.exporter.jaeger.thrift import JaegerExporter
from opentelemetry.sdk.resources import Resource

logger = logging.getLogger(__name__)


class TracingManager:
    """分布式追踪管理器"""

    def __init__(self,
                 service_name: str = "aethelum-core-lite",
                 jaeger_host: str = "localhost",
                 jaeger_port: int = 6831,
                 sample_rate: float = 0.1):
        self.sample_rate = sample_rate
        self.service_name = service_name

        # 配置资源
        resource = Resource(attributes={
            "service.name": service_name,
            "service.version": "1.0.0"
        })

        # 配置TracerProvider
        provider = TracerProvider(resource=resource)
        trace.set_tracer_provider(provider)

        # 配置Jaeger导出器
        try:
            jaeger_exporter = JaegerExporter(
                agent_host_name=jaeger_host,
                agent_port=jaeger_port,
            )

            # 使用批量处理器提升性能
            provider.add_span_processor(
                BatchSpanProcessor(jaeger_exporter)
            )

            logger.info(f"[Tracing] OpenTelemetry initialized with Jaeger at {jaeger_host}:{jaeger_port}")
            logger.info(f"[Tracing] Sample rate: {sample_rate * 100}%")
            logger.info(f"[Tracing] Jaeger UI: http://{jaeger_host}:16686")

        except Exception as e:
            logger.error(f"[Tracing] Failed to initialize Jaeger exporter: {e}")
            logger.warning(f"[Tracing] Tracing will be disabled")

        self.tracer = trace.get_tracer(__name__)

    def start_span(self, name: str, **attributes):
        """启动一个span"""
        span = self.tracer.start_span(name)
        for key, value in attributes.items():
            span.set_attribute(key, value)
        return span

    def is_enabled(self) -> bool:
        """判断是否启用追踪

        统一边界条件：sample_rate > 0 时启用
        """
        return self.sample_rate > 0

    def should_sample(self) -> bool:
        """判断是否采样

        统一边界条件：
        - sample_rate <= 0: 永不采样
        - sample_rate >= 1.0: 始终采样
        - 其他: 概率采样
        """
        if self.sample_rate <= 0:
            return False
        if self.sample_rate >= 1.0:
            return True

        import random
        return random.random() < self.sample_rate
