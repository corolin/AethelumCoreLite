# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

AethelumCoreLite (灵壤精核) is a tree-neural-inspired communication framework for building AI agent systems. It provides two parallel architectures:

1. **Thread-based Architecture** (Original): `SynapticQueue`, `NeuralSomaRouter`, `AxonWorker`
2. **AsyncIO Architecture** (New, 2026-01-27): `AsyncSynapticQueue`, `AsyncNeuralSomaRouter`, `AsyncAxonWorker`

Both architectures share the same core concepts but are optimized for different scenarios:
- **Thread-based**: CPU-bound tasks, legacy codebases
- **AsyncIO**: I/O-bound tasks (AI API calls, database operations), higher concurrency (1000+ agents vs 100)

## Common Development Commands

### Testing
```bash
# Run all tests
pytest tests/

# Run specific test file
pytest tests/test_concurrency_safety.py

# Run async tests
pytest tests/test_async_components.py

# Run with verbose output
pytest tests/ -v

# Run performance benchmarks
pytest tests/test_performance_benchmark.py
```

### Code Quality
```bash
# Format code
black aethelum_core_lite/

# Type checking
mypy aethelum_core_lite/

# Linting
flake8 aethelum_core_lite/
```

### Installation
```bash
# Base installation
pip install -e .

# With all dependencies
pip install -e ".[all]"

# With specific dependency groups
pip install -e ".[dev,performance]"  # Development tools + msgpack
pip install -e ".[monitoring]"       # Prometheus + OpenTelemetry
pip install -e ".[api]"              # FastAPI + uvicorn
```

### Running Examples
```bash
# Interactive example menu
python -m aethelum_core_lite.examples.main

# AsyncIO example
python examples/async_example.py

# Basic example
python examples/basic_example.py

# Performance demo
python examples/performance_demo.py
```

## Architecture

### Core Concepts

**NeuralImpulse** ([core/message.py](aethelum_core_lite/core/message.py))
- Message packet passed between neurons
- Contains: `session_id`, `action_intent` (routing target), `source_agent`, `content`, `metadata`
- Supports ProtoBuf serialization (optional)

**Two Parallel Architectures**

1. **Thread-based Architecture** (in `core/`)
   - `SynapticQueue` - Thread-safe priority queue with WAL persistence
   - `AxonWorker` - Thread-based message processor
   - `NeuralSomaRouter` - Main controller managing queues and workers
   - `WorkerScheduler` - Round-robin load balancing
   - `WorkerMonitor` - Health monitoring and alerting

2. **AsyncIO Architecture** (in `core/async_*.py`)
   - `AsyncSynapticQueue` - Async queue with priority support
   - `AsyncAxonWorker` - Async worker for I/O-bound tasks
   - `AsyncNeuralSomaRouter` - Async router
   - Optimized for AI API calls, vector DB queries, file I/O

### Data Flow

```
Producer → NeuralImpulse → SynapticQueue → AxonWorker → Business Logic → Response
                                  ↓
                            WAL Persistence (log1.msgpack)
                                  ↓
                            Consumer → WAL (log2.msgpack) → Cleanup
```

**WAL (Write-Ahead Log) Architecture**
- **log1.msgpack**: Message input log (append-only)
- **log2.msgpack**: Message consumption log (append-only)
- Background thread writes asynchronously, non-blocking for producers/consumers
- Performance impact: Only 7% with msgpack (vs 56% with sync WAL)
- Auto-cleanup: Removes processed messages periodically

### Thread Safety

All core components use `threading.RLock` for thread safety:
- **SynapticQueue**: Protects internal queue state and metrics
- **AxonWorker**: Protects statistics
- **WorkerMonitor**: Uses separate locks for metrics (`_metrics_lock`) and alerts (`_alerts_lock`)
- **NeuralSomaRouter**: Protects performance metrics

**Critical**: Always return copies of internal state, never references:
```python
# Correct
def get_stats(self):
    with self._lock:
        return QueueStats(total_messages=self._stats.total_messages)

# Wrong
def get_stats(self):
    return self._stats  # External code can modify internal state
```

### Configuration System

Located in `config/`, uses TOML format:

**Config Classes**:
- `SystemConfig` - Worker mode, max workers, queue size
- `MonitoringConfig` - Prometheus, tracing, metrics API
- `APIConfig` - Metrics API server settings, API key authentication
- `PerformanceConfig` - AsyncIO concurrency, hook timeouts

**Usage**:
```python
from aethelum_core_lite.config import ConfigLoader

config = ConfigLoader.load_from_file("config.toml")
monitoring_config = ConfigLoader.get_monitoring_config(config)
```

### Monitoring and Observability

**Prometheus Metrics** (`monitoring/metrics_exporter.py`):
- Counter, Gauge, Histogram metrics
- HTTP server on port 8000 (default)
- Reads from in-memory metrics storage

**OpenTelemetry Tracing** (`monitoring/tracing.py`):
- Jaeger integration
- Configurable sample rate (default 10%)
- Batch span processing

**Metrics API** (`api/metrics_api.py`):
- Single `/api/v1/metrics` endpoint
- Optional Bearer Token authentication (set `api_key` in config)
- Health check at `/api/v1/health`
- Auto-generated Swagger UI at `/docs`

### Hook System

Hooks allow custom code execution at different processing stages:
- **Pre-Hooks**: Before message processing
- **Post-Hooks**: After successful processing
- **Error-Hooks**: On processing failure

Hooks can be synchronous or asynchronous (AsyncIO components only).

### Persistence

**WAL Writer** (`utils/wal_writer.py`):
- `AsyncWALWriter` - Async WAL writer with batch optimization
- Supports msgpack (recommended) and JSON formats
- Dual-log architecture: log1 (input) + log2 (consumed)
- Default batch size: 100 messages, flush interval: 1 second

**Important**: Always call `queue.start()` and `queue.stop()` to properly initialize/ shutdown WAL writer.

## Key Design Decisions

### Why Two Architectures?

The codebase maintains both thread-based and AsyncIO architectures because:
1. **Migration Path**: Project is in development phase, allows gradual migration
2. **Different Use Cases**: Thread-based for CPU-bound, AsyncIO for I/O-bound
3. **User Choice**: Users can choose based on their requirements

### Memory Metrics Storage

All components store metrics in memory (not in Prometheus directly):
- Components update metrics in-memory
- Prometheus exporter periodically reads and syncs to Prometheus
- Avoids Prometheus Counter accumulation issues

### Optional Dependencies

Most features are optional to keep core lightweight:
- `msgpack`: Performance optimization for WAL (3-5x faster than JSON)
- `prometheus-client`, `opentelemetry-*`: Monitoring features
- `fastapi`, `uvicorn`: Metrics API
- All fall back gracefully if not installed

## Common Patterns

### Creating a Simple Router

```python
from aethelum_core_lite import NeuralSomaRouter, NeuralImpulse

router = NeuralSomaRouter()

def business_handler(impulse, source_queue):
    impulse.set_text_content(f"Processed: {impulse.get_text_content()}")
    impulse.reroute_to("Q_RESPONSE_SINK")
    return impulse

router.auto_setup(business_handler=business_handler)

impulse = NeuralImpulse(
    content="Hello",
    action_intent="Q_PROCESS_INPUT"
)
router.inject_input(impulse)
```

### Using AsyncIO Architecture

```python
import asyncio
from aethelum_core_lite.core.async_queue import AsyncSynapticQueue
from aethelum_core_lite.core.async_worker import AsyncAxonWorker
from aethelum_core_lite.core.async_router import AsyncNeuralSomaRouter

async def main():
    router = AsyncNeuralSomaRouter("my_router")
    queue = AsyncSynapticQueue("my_queue", enable_wal=True)
    worker = AsyncAxonWorker("my_worker", input_queue=queue)

    router.register_queue(queue)
    router.register_worker(worker)

    await router.start()
    await router.route_message({"data": "test"}, "pattern")
    await asyncio.sleep(1)
    await router.stop()

asyncio.run(main())
```

## Important Notes

### Performance Optimization

1. **Install msgpack**: 3-5x faster serialization for WAL
2. **Use AsyncIO for I/O-bound**: 10x higher concurrency (1000+ vs 100 agents)
3. **Adjust WAL batch size**: Default 100, increase for high throughput
4. **Monitor lock contention**: Use fine-grained locks, minimize critical section time

### Security

- **API Authentication**: Metrics API has optional Bearer Token authentication
  - Set `api_key` in `[api]` section of config.toml
  - Default: No authentication (relies on localhost-only binding)
  - Production: Always set `api_key`
- **Don't expose APIs**: Default binding to 127.0.0.1, never change to 0.0.0.0

### Testing Philosophy

- **Concurrency Safety**: `test_concurrency_safety.py` - Comprehensive thread safety tests
- **Performance**: `test_performance_benchmark.py` - Validates WAL performance impact
- **AsyncIO**: `test_async_components.py` - Tests async components with pytest-asyncio
- **Quick Verification**: `test_quick_verification.py` - Fast smoke tests

### When to Use Which Architecture

**Use Thread-based** (`SynapticQueue`, `AxonWorker`):
- CPU-bound tasks
- Existing synchronous codebases
- Need thread-level parallelism

**Use AsyncIO** (`AsyncSynapticQueue`, `AsyncAxonWorker`):
- I/O-bound tasks (AI API calls, database queries, file operations)
- Need high concurrency (1000+ agents)
- Integrating with async libraries (LangChain, async OpenAI SDK)

## File Organization

```
aethelum_core_lite/
├── core/               # Core components (queue, worker, router, message)
│   ├── queue.py        # Thread-based SynapticQueue
│   ├── worker.py       # Thread-based AxonWorker
│   ├── router.py       # Thread-based NeuralSomaRouter
│   ├── async_queue.py  # AsyncIO AsyncSynapticQueue
│   ├── async_worker.py # AsyncIO AsyncAxonWorker
│   ├── async_router.py # AsyncIO AsyncNeuralSomaRouter
│   ├── message.py      # NeuralImpulse message class
│   └── worker_monitor.py # Health monitoring system
├── config/             # Configuration management (TOML)
├── monitoring/         # Prometheus + OpenTelemetry
├── api/                # Metrics API (FastAPI)
├── utils/              # WAL writer, utilities
├── hooks/              # Hook system
├── examples/           # Example programs
└── tests/              # Unit tests
```

## Troubleshooting

### WAL Performance Issues

If WAL is too slow:
1. Verify msgpack is installed: `python -c "import msgpack"`
2. Increase batch size in `AsyncWALWriter` initialization
3. Check disk I/O performance

### Concurrency Bugs

Common symptoms:
- Data loss or inconsistency
- `RuntimeError: dictionary changed size during iteration`

Solutions:
- Add locks to all shared state
- Return copies instead of references
- Use snapshots when iterating

### Import Errors

- `ImportError: No module named 'xxx'`: Install missing dependencies
- ProtoBuf issues: Run `protoc --python_out=. protobuf_schema.proto` in `core/` directory
- AsyncIO tests failing: Install `pytest-asyncio`
