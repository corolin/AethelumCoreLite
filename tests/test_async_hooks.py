"""
异步Hook系统测试

测试异步Hook的基础功能、注册、执行和错误处理。
"""

import pytest
import asyncio
from aethelum_core_lite.core.async_hooks import (
    AsyncHookType,
    AsyncBaseHook,
    AsyncPreHook,
    AsyncPostHook,
    AsyncErrorHook,
    AsyncFilterHook,
    create_async_pre_hook,
    create_async_post_hook,
    wrap_sync_hook_as_async
)
from aethelum_core_lite.core.message import NeuralImpulse


class TestAsyncHookBase:
    """测试AsyncBaseHook基础功能"""

    @pytest.mark.asyncio
    async def test_hook_enable_disable(self):
        """测试Hook启用和禁用"""

        class TestHook(AsyncPreHook):
            async def process_async(self, impulse, source_queue):
                impulse.content = "processed"
                return impulse

        hook = TestHook("test_hook")

        # 默认启用
        assert hook.enabled is True

        # 禁用
        hook.disable()
        assert hook.enabled is False

        # 启用
        hook.enable()
        assert hook.enabled is True

    @pytest.mark.asyncio
    async def test_hook_stats(self):
        """测试Hook统计信息"""

        class TestHook(AsyncPreHook):
            async def process_async(self, impulse, source_queue):
                return impulse

        hook = TestHook("test_hook")
        impulse = NeuralImpulse(content="test", action_intent="test")

        # 执行Hook
        await hook.execute_async(impulse, "test_queue")

        # 获取统计信息
        stats = await hook.get_stats()
        assert stats['total_processed'] == 1
        assert stats['total_errors'] == 0
        assert stats['execution_count'] == 1
        assert stats['avg_processing_time'] >= 0


class TestAsyncHookTypes:
    """测试不同类型的异步Hook"""

    @pytest.mark.asyncio
    async def test_pre_hook(self):
        """测试前置Hook"""

        class MyPreHook(AsyncPreHook):
            async def process_async(self, impulse, source_queue):
                impulse.metadata['pre_processed'] = True
                return impulse

        hook = MyPreHook("pre_test")
        impulse = NeuralImpulse(content="test", action_intent="test")

        result = await hook.execute_async(impulse, "test_queue")
        assert result.metadata['pre_processed'] is True
        assert hook.hook_type == "pre_process"

    @pytest.mark.asyncio
    async def test_post_hook(self):
        """测试后置Hook"""

        class MyPostHook(AsyncPostHook):
            async def process_async(self, impulse, source_queue):
                impulse.metadata['post_processed'] = True
                return impulse

        hook = MyPostHook("post_test")
        impulse = NeuralImpulse(content="test", action_intent="test")

        result = await hook.execute_async(impulse, "test_queue")
        assert result.metadata['post_processed'] is True
        assert hook.hook_type == "post_process"

    @pytest.mark.asyncio
    async def test_error_hook(self):
        """测试错误Hook"""

        class MyErrorHook(AsyncErrorHook):
            async def process_async(self, impulse, source_queue):
                impulse.metadata['error_handled'] = True
                return impulse

        hook = MyErrorHook("error_test")
        impulse = NeuralImpulse(content="test", action_intent="test")

        result = await hook.execute_async(impulse, "test_queue")
        assert result.metadata['error_handled'] is True
        assert hook.hook_type == "error_handler"

    @pytest.mark.asyncio
    async def test_filter_hook_pass(self):
        """测试过滤Hook - 通过消息"""

        class MyFilterHook(AsyncFilterHook):
            async def should_process(self, impulse, source_queue):
                # 只处理包含"allow"的消息
                return "allow" in impulse.content

        hook = MyFilterHook("filter_test")

        # 应该通过
        impulse1 = NeuralImpulse(content="allow this", action_intent="test")
        result1 = await hook.execute_async(impulse1, "test_queue")
        assert result1 is not None

        # 应该被过滤
        impulse2 = NeuralImpulse(content="deny this", action_intent="test")
        result2 = await hook.execute_async(impulse2, "test_queue")
        assert result2 is None


class TestConvenienceFunctions:
    """测试便捷创建函数"""

    @pytest.mark.asyncio
    async def test_create_async_pre_hook(self):
        """测试创建异步PreHook"""

        async def my_pre_hook(impulse, source_queue):
            impulse.metadata['custom'] = True
            return impulse

        hook = create_async_pre_hook(my_pre_hook)
        impulse = NeuralImpulse(content="test", action_intent="test")

        result = await hook.execute_async(impulse, "test_queue")
        assert result.metadata['custom'] is True
        assert isinstance(hook, AsyncPreHook)

    @pytest.mark.asyncio
    async def test_create_async_post_hook(self):
        """测试创建异步PostHook"""

        async def my_post_hook(impulse, source_queue):
            impulse.metadata['custom'] = True
            return impulse

        hook = create_async_post_hook(my_post_hook)
        impulse = NeuralImpulse(content="test", action_intent="test")

        result = await hook.execute_async(impulse, "test_queue")
        assert result.metadata['custom'] is True
        assert isinstance(hook, AsyncPostHook)

    @pytest.mark.asyncio
    async def test_wrap_sync_hook(self):
        """测试包装同步Hook为异步Hook"""

        def my_sync_hook(impulse, source_queue):
            impulse.content = "sync_processed"
            return impulse

        async_hook = wrap_sync_hook_as_async(my_sync_hook)
        impulse = NeuralImpulse(content="test", action_intent="test")

        result = await async_hook.execute_async(impulse, "test_queue")
        assert result.content == "sync_processed"


class TestHookErrorHandling:
    """测试Hook错误处理"""

    @pytest.mark.asyncio
    async def test_hook_exception(self):
        """测试Hook执行异常时的处理"""

        class FailingHook(AsyncPreHook):
            async def process_async(self, impulse, source_queue):
                raise ValueError("Test error")

        hook = FailingHook("failing_hook")
        impulse = NeuralImpulse(content="test", action_intent="test")

        # 执行应该捕获异常，不会抛出
        result = await hook.execute_async(impulse, "test_queue")

        # 检查错误被记录到metadata
        assert 'hook_error_failing_hook' in result.metadata
        assert result.metadata['hook_error_failing_hook']['error'] == "Test error"

        # 检查统计信息
        stats = await hook.get_stats()
        assert stats['total_errors'] == 1

    @pytest.mark.asyncio
    async def test_hook_disabled_skip(self):
        """测试禁用的Hook被跳过"""

        class TestHook(AsyncPreHook):
            async def process_async(self, impulse, source_queue):
                impulse.metadata['executed'] = True
                return impulse

        hook = TestHook("test_hook")
        hook.disable()

        impulse = NeuralImpulse(content="test", action_intent="test")
        result = await hook.execute_async(impulse, "test_queue")

        # Hook被跳过，metadata不应该有'executed'
        assert 'executed' not in result.metadata

        # 检查统计信息
        stats = await hook.get_stats()
        assert stats['total_skipped'] == 1


class TestRouterHookIntegration:
    """测试Router的Hook集成"""

    @pytest.mark.asyncio
    async def test_hook_registration(self):
        """测试Hook注册"""
        from aethelum_core_lite.core.async_router import AsyncNeuralSomaRouter
        from aethelum_core_lite.core.async_queue import AsyncSynapticQueue

        router = AsyncNeuralSomaRouter("test_router")
        queue = AsyncSynapticQueue("test_queue", enable_wal=False)
        router.register_queue(queue)

        # 创建Hook
        async def test_hook(impulse, source_queue):
            impulse.metadata['hook_executed'] = True
            return impulse

        # 注册Hook
        await router.register_hook(
            "test_queue",
            test_hook,
            AsyncHookType.PRE_PROCESS
        )

        # 验证Hook已注册
        hooks = router.get_hooks("test_queue", AsyncHookType.PRE_PROCESS)
        assert len(hooks) == 1

    @pytest.mark.asyncio
    async def test_hook_execution(self):
        """测试Hook执行"""
        from aethelum_core_lite.core.async_router import AsyncNeuralSomaRouter
        from aethelum_core_lite.core.async_queue import AsyncSynapticQueue

        router = AsyncNeuralSomaRouter("test_router")
        queue = AsyncSynapticQueue("test_queue", enable_wal=False)
        router.register_queue(queue)

        # 创建Hook
        async def test_hook(impulse, source_queue):
            impulse.metadata['pre_executed'] = True
            return impulse

        # 注册Hook
        await router.register_hook(
            "test_queue",
            test_hook,
            AsyncHookType.PRE_PROCESS
        )

        # 执行Hook
        impulse = NeuralImpulse(content="test", action_intent="test")
        result = await router.execute_hooks(
            impulse,
            "test_queue",
            AsyncHookType.PRE_PROCESS
        )

        assert result.metadata['pre_executed'] is True

    @pytest.mark.asyncio
    async def test_multiple_hooks_parallel_execution(self):
        """测试多个Hook并行执行"""
        from aethelum_core_lite.core.async_router import AsyncNeuralSomaRouter
        from aethelum_core_lite.core.async_queue import AsyncSynapticQueue
        import time

        router = AsyncNeuralSomaRouter("test_router")
        queue = AsyncSynapticQueue("test_queue", enable_wal=False)
        router.register_queue(queue)

        # 创建多个Hook
        execution_order = []

        async def hook1(impulse, source_queue):
            execution_order.append(1)
            await asyncio.sleep(0.1)
            execution_order.append(1)
            return impulse

        async def hook2(impulse, source_queue):
            execution_order.append(2)
            await asyncio.sleep(0.05)
            execution_order.append(2)
            return impulse

        async def hook3(impulse, source_queue):
            execution_order.append(3)
            await asyncio.sleep(0.01)
            execution_order.append(3)
            return impulse

        # 注册Hooks
        await router.register_hook("test_queue", hook1, AsyncHookType.PRE_PROCESS)
        await router.register_hook("test_queue", hook2, AsyncHookType.PRE_PROCESS)
        await router.register_hook("test_queue", hook3, AsyncHookType.PRE_PROCESS)

        # 执行Hooks
        impulse = NeuralImpulse(content="test", action_intent="test")
        await router.execute_hooks(impulse, "test_queue", AsyncHookType.PRE_PROCESS)

        # 验证并行执行（启动顺序可能是1,2,3，但完成顺序是3,2,1）
        assert len(execution_order) == 6
        # 启动顺序
        assert execution_order[:3] == [1, 2, 3]
        # 完成顺序（由于sleep时间不同）
        assert execution_order[3:] == [3, 2, 1]

    @pytest.mark.asyncio
    async def test_hook_error_isolation(self):
        """测试Hook错误隔离"""
        from aethelum_core_lite.core.async_router import AsyncNeuralSomaRouter
        from aethelum_core_lite.core.async_queue import AsyncSynapticQueue

        router = AsyncNeuralSomaRouter("test_router")
        queue = AsyncSynapticQueue("test_queue", enable_wal=False)
        router.register_queue(queue)

        # 创建多个Hook，其中第二个会失败
        async def hook1(impulse, source_queue):
            impulse.metadata['hook1'] = True
            return impulse

        async def hook2(impulse, source_queue):
            raise ValueError("Hook2 failed")

        async def hook3(impulse, source_queue):
            impulse.metadata['hook3'] = True
            return impulse

        # 注册Hooks
        await router.register_hook("test_queue", hook1, AsyncHookType.PRE_PROCESS)
        await router.register_hook("test_queue", hook2, AsyncHookType.PRE_PROCESS)
        await router.register_hook("test_queue", hook3, AsyncHookType.PRE_PROCESS)

        # 执行Hooks
        impulse = NeuralImpulse(content="test", action_intent="test")
        result = await router.execute_hooks(impulse, "test_queue", AsyncHookType.PRE_PROCESS)

        # 验证错误被隔离，其他Hook仍然执行
        assert result.metadata.get('hook1') is True
        assert result.metadata.get('hook3') is True

        # 检查性能指标中的错误计数
        perf = router._performance_metrics
        assert perf['total_hook_errors'] >= 1

    @pytest.mark.asyncio
    async def test_sync_hook_compatibility(self):
        """测试同步Hook兼容性"""
        from aethelum_core_lite.core.async_router import AsyncNeuralSomaRouter
        from aethelum_core_lite.core.async_queue import AsyncSynapticQueue

        router = AsyncNeuralSomaRouter("test_router")
        queue = AsyncSynapticQueue("test_queue", enable_wal=False)
        router.register_queue(queue)

        # 创建同步Hook
        def sync_hook(impulse, source_queue):
            impulse.metadata['sync_hook_executed'] = True
            return impulse

        # 注册同步Hook
        await router.register_hook("test_queue", sync_hook, AsyncHookType.PRE_PROCESS)

        # 执行Hook
        impulse = NeuralImpulse(content="test", action_intent="test")
        result = await router.execute_hooks(impulse, "test_queue", AsyncHookType.PRE_PROCESS)

        assert result.metadata['sync_hook_executed'] is True


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
