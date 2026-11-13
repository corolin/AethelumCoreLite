/**
 * SQLite Runtime — Bun-native binding
 *
 * AethelumCoreLite requires Bun >=1.0.0 as its runtime.
 * bun:sqlite is available natively; no compatibility shim needed.
 */
export { Database } from 'bun:sqlite';
