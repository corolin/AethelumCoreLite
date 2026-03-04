import { getStructuredLogger, LogLevel } from './structured_logger';

export const setupLogger = (
    name: string,
    level: string = "INFO",
    logFormat?: string,
    enableColors: boolean = true,
    logFile?: string
) => {
    return getStructuredLogger(name, {
        level,
        console_colors: enableColors,
        format: logFormat || 'plain',
        file: logFile ? { path: logFile } : undefined
    });
};

export const getLogger = (name: string) => getStructuredLogger(name);

// Predefined loggers mapping from Python source
export const neuralLogger = setupLogger("AsyncNeuralSomaRouter", "INFO");
export const queueLogger = setupLogger("AsyncSynapticQueue", "INFO");
export const workerLogger = setupLogger("AsyncAxonWorker", "INFO");
export const auditLogger = setupLogger("AuditAgent", "INFO");

export const logPerformance = (operationName: string) => {
    return function (target: any, propertyKey: string, descriptor: PropertyDescriptor) {
        const originalMethod = descriptor.value;
        descriptor.value = function (...args: any[]) {
            const logger = getLogger(target.constructor.name);
            const start = Date.now();
            logger.debug(`开始操作: ${operationName} - ${propertyKey}`);
            try {
                const result = originalMethod.apply(this, args);
                if (result instanceof Promise) {
                    return result.then(res => {
                        const duration = (Date.now() - start) / 1000;
                        logger.debug(`操作完成: ${operationName} - ${propertyKey}, 耗时: ${duration}秒`);
                        return res;
                    }).catch(err => {
                        const duration = (Date.now() - start) / 1000;
                        logger.error(`操作失败: ${operationName}, 耗时: ${duration}秒, 错误: ${err}`);
                        throw err;
                    });
                } else {
                    const duration = (Date.now() - start) / 1000;
                    logger.debug(`操作完成: ${operationName} - ${propertyKey}, 耗时: ${duration}秒`);
                    return result;
                }
            } catch (err) {
                const duration = (Date.now() - start) / 1000;
                logger.error(`操作失败: ${operationName}, 耗时: ${duration}秒, 错误: ${err}`);
                throw err;
            }
        };
        return descriptor;
    };
};
