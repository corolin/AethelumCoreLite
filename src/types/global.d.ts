/**
 * 集中的全局类型声明
 */

/** 全局日志函数（由应用层注入） */
declare global {
  var logRaw: ((message: string) => void) | undefined;
}

export {};
