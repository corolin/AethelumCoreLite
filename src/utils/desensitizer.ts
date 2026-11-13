/**
 * Data Desensitizer - 敏感数据脱敏工具
 *
 * 用于在日志中屏蔽 API Key、Token 等敏感信息。
 */

const PATTERNS = [
  // OpenAI / Standard sk- patterns
  { pattern: /sk-[a-zA-Z0-9]{32,}/g, replacement: (match: string) => `sk-${match.slice(3, 7)}...${match.slice(-4)}` },
  // Bearer tokens
  { pattern: /Bearer\s+[a-zA-Z0-9._-]{20,}/gi, replacement: (match: string) => `Bearer ${match.slice(7, 12)}...` },
  // GitHub tokens
  { pattern: /ghp_[a-zA-Z0-9]{30,}/g, replacement: (match: string) => `ghp_${match.slice(4, 8)}...${match.slice(-4)}` },
  // Discord tokens/secrets (often 24+ chars)
  { pattern: /discord_[a-zA-Z0-9]{20,}/g, replacement: (match: string) => `discord_${match.slice(8, 12)}...` },
  // Long hex/alphanumeric strings that might be secrets (length >= 32)
  // Be careful not to match UUIDs or hashes that are okay to log
  // This is a conservative approach: match only if it looks like a single word
  { pattern: /\b[a-fA-F0-9]{32,}\b/g, replacement: (match: string) => `${match.slice(0, 4)}...${match.slice(-4)}` },
  // Generic key=value or "key": "value" patterns
  {
    pattern: /(api_key|token|secret|password|auth|key|client_id|client_secret)["\s:=]+([a-zA-Z0-9._-]{12,})/gi,
    replacement: (match: string, key: string, value: string) => `${key}="${value.slice(0, 3)}...${value.slice(-3)}"`,
  },
  // URLs with credentials
  {
    pattern: /([a-z]+:\/\/)([^:]+):([^@]+)(@)/gi,
    replacement: (match: string, proto: string, user: string, _pass: string, at: string) => `${proto}${user}:***${at}`,
  },
];

/**
 * 屏蔽敏感字符串的通用逻辑
 */
function maskSecret(val: string): string {
  if (val.length <= 8) return '***';
  if (val.startsWith('sk-')) {
    return `sk-${val.slice(3, 7)}...${val.slice(-4)}`;
  }
  return `${val.slice(0, 4)}...${val.slice(-4)}`;
}

/**
 * 对字符串进行脱敏处理
 */
export function desensitize(text: string): string {
  if (!text || typeof text !== 'string') return text;

  let result = text;
  for (const { pattern, replacement } of PATTERNS) {
    result = result.replace(pattern, replacement as any);
  }
  return result;
}

/**
 * 对对象进行递归脱敏处理 (主要用于日志 args)
 */
export function desensitizeObject(obj: any): any {
  if (!obj || typeof obj !== 'object' || obj === null) return obj;

  if (Array.isArray(obj)) {
    return obj.map(item => desensitizeObject(item));
  }

  const result: any = {};
  for (const [key, value] of Object.entries(obj)) {
    const lowerKey = key.toLowerCase();
    const isSensitiveKey =
      lowerKey.includes('key') ||
      lowerKey.includes('token') ||
      lowerKey.includes('secret') ||
      lowerKey.includes('password') ||
      lowerKey.includes('api_key') ||
      lowerKey.includes('authorization');

    if (typeof value === 'string') {
      if (isSensitiveKey) {
        result[key] = maskSecret(value);
      } else {
        result[key] = desensitize(value);
      }
    } else if (typeof value === 'object' && value !== null) {
      result[key] = desensitizeObject(value);
    } else {
      result[key] = value;
    }
  }
  return result;
}
