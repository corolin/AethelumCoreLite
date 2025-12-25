"""
输出轴突工作器

基于标准Python threading.Thread实现的工作器线程，负责传递神经信号。
"""
class ResponseSinkAxonWorker(AxonWorker):
