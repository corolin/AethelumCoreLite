"""
AethelumCoreLite - 灵壤精核 - 高性能Python内存异步通信骨架

一个开源、轻量级的Python异步通信框架，专为快速构建AI助理系统而设计。
"""

__version__ = "1.0.0"
__author__ = "Aethelum Team"
__description__ = "高性能Python内存异步通信骨架"

# 延迟导入缓存
_core_modules = None

def _import_core():
    """延迟导入核心模块"""
    global _core_modules
    if _core_modules is None:
        from .core.router import NeuralSomaRouter
        from .core.queue import SynapticQueue
        from .core.message import NeuralImpulse
        _core_modules = {
            'NeuralSomaRouter': NeuralSomaRouter,
            'SynapticQueue': SynapticQueue,
            'NeuralImpulse': NeuralImpulse
        }
    return _core_modules

# 通过属性访问时才导入
def __getattr__(name):
    if name in ["NeuralSomaRouter", "SynapticQueue", "NeuralImpulse"]:
        modules = _import_core()
        if name not in globals():
            globals()[name] = modules[name]
        return modules[name]
    raise AttributeError(f"module '{__name__}' has no attribute '{name}'")

__all__ = [
    "NeuralSomaRouter",
    "SynapticQueue",
    "NeuralImpulse"
]