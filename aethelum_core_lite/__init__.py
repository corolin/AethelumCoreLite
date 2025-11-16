"""
AethelumCoreLite - 灵壤精核 - 高性能Python内存异步通信骨架

一个开源、轻量级的Python异步通信框架，专为快速构建AI助理系统而设计。
"""

__version__ = "1.0.0"
__author__ = "Aethelum Team"
__description__ = "高性能Python内存异步通信骨架"

# 延迟导入，避免依赖检查问题
def _import_core():
    """延迟导入核心模块"""
    from .core.router import NeuralSomaRouter
    from .core.queue import SynapticQueue
    from .core.message import NeuralImpulse
    return NeuralSomaRouter, SynapticQueue, NeuralImpulse

# 通过属性访问时才导入
def __getattr__(name):
    if name in ["NeuralSomaRouter", "SynapticQueue", "NeuralImpulse"]:
        NeuralSomaRouter, SynapticQueue, NeuralImpulse = _import_core()
        globals()[name] = locals()[name]
        return globals()[name]
    raise AttributeError(f"module '{__name__}' has no attribute '{name}'")

__all__ = [
    "NeuralSomaRouter",
    "SynapticQueue",
    "NeuralImpulse"
]