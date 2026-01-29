"""
CoreLite核心模块

包含路由器、队列和消息包等核心组件。
"""

# 延迟导入，避免依赖检查问题
def _import_core():
    """延迟导入核心模块"""
    from .router import NeuralSomaRouter
    from .queue import SynapticQueue
    from .message import NeuralImpulse
    from .worker import AxonWorker
    return NeuralSomaRouter, SynapticQueue, NeuralImpulse, AxonWorker

# 通过属性访问时才导入
def __getattr__(name):
    if name in ["NeuralSomaRouter", "SynapticQueue", "NeuralImpulse", "AxonWorker"]:
        NeuralSomaRouter, SynapticQueue, NeuralImpulse, AxonWorker = _import_core()
        globals()[name] = locals()[name]
        return globals()[name]
    raise AttributeError(f"module '{__name__}' has no attribute '{name}'")

__all__ = [
    "NeuralSomaRouter",
    "SynapticQueue",
    "NeuralImpulse",
    "AxonWorker"
]