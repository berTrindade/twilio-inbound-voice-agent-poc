/**
 * AES-256-GCM decryption utilities for PII at rest.
 *
 * Wire format: `enc:v1:<base64(nonce_12 ‖ ciphertext ‖ tag_16)>`
 *
 * When ENCRYPTION_KEY is not set, all functions pass values through unchanged.
 */

import { createDecipheriv } from "crypto";

const PREFIX = "enc:v1:";
const NONCE_LEN = 12;
const TAG_LEN = 16;

function getKey(): Buffer | null {
  const raw = process.env.ENCRYPTION_KEY;
  if (!raw) return null;
  try {
    const key = Buffer.from(raw, "base64");
    if (key.length !== 32) {
      console.error(
        `[Encryption] ENCRYPTION_KEY must be 32 bytes. Got ${key.length} — decryption disabled.`
      );
      return null;
    }
    return key;
  } catch {
    console.error("[Encryption] ENCRYPTION_KEY is not valid base64.");
    return null;
  }
}

/**
 * Decrypt a string value if it carries the `enc:v1:` prefix.
 * Plain-text values are returned as-is (graceful fallback).
 */
export function decrypt(value: string): string {
  if (!value || !value.startsWith(PREFIX)) return value;

  const key = getKey();
  if (!key) return value;

  const payload = Buffer.from(value.slice(PREFIX.length), "base64");
  const nonce = payload.subarray(0, NONCE_LEN);
  const tag = payload.subarray(payload.length - TAG_LEN);
  const ciphertext = payload.subarray(NONCE_LEN, payload.length - TAG_LEN);

  const decipher = createDecipheriv("aes-256-gcm", key, nonce);
  decipher.setAuthTag(tag);

  const decrypted = Buffer.concat([
    decipher.update(ciphertext),
    decipher.final(),
  ]);
  return decrypted.toString("utf8");
}

/**
 * Decrypt a JSONB value that may be encrypted or a plain object.
 *
 * - object/array → returned as-is (legacy unencrypted row)
 * - string with `enc:v1:` prefix → decrypted then JSON.parsed
 * - null/undefined → empty object
 */
// eslint-disable-next-line @typescript-eslint/no-explicit-any
export function decryptJson(value: unknown): Record<string, any> {
  if (value === null || value === undefined) return {};
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  if (typeof value === "object") return value as Record<string, any>;
  if (typeof value === "string") {
    const decrypted = decrypt(value);
    try {
      const parsed = JSON.parse(decrypted);
      return typeof parsed === "object" && parsed !== null ? parsed : {};
    } catch {
      return {};
    }
  }
  return {};
}
