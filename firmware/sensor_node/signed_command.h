// Verification of "ON:<seconds>:<counter>:<mac16>" (see backend/app/services/command_signing.py). Pure logic, PC-testable.
#pragma once
#include <stdint.h>
#include <stddef.h>
#include <stdio.h>
#include <string.h>
#include "sha256.h"

namespace greetopia {

enum class AuthResult : uint8_t { Ok, BadFormat, BadMac, Replay };

inline bool constantTimeEq(const char* a, const char* b, size_t n) {
  uint8_t d = 0; for (size_t i = 0; i < n; i++) d |= (uint8_t)(a[i] ^ b[i]); return d == 0;
}

// On Ok: *secondsOut and *counterOut are set. The caller must persist *counterOut only after the command is actually accepted.
inline AuthResult verifySigned(const char* p, size_t len, const char* plantId, const uint8_t* key, size_t keyLen, uint32_t lastCounter,
                               uint32_t* secondsOut, uint32_t* counterOut) {
  if (!p || len < 10 || len > 48 || p[0] != 'O' || p[1] != 'N' || p[2] != ':') return AuthResult::BadFormat;
  size_t i = 3; uint32_t seconds = 0, counter = 0; size_t nd = 0;
  while (i < len && p[i] >= '0' && p[i] <= '9' && nd < 4) { seconds = seconds * 10 + (p[i] - '0'); i++; nd++; }
  if (nd == 0 || i >= len || p[i] != ':') return AuthResult::BadFormat;
  i++; nd = 0;
  uint64_t c64 = 0;
  while (i < len && p[i] >= '0' && p[i] <= '9' && nd < 10) { c64 = c64 * 10 + (p[i] - '0'); i++; nd++; }
  if (nd == 0 || i >= len || p[i] != ':' || c64 > 0xFFFFFFFFULL) return AuthResult::BadFormat;
  counter = (uint32_t)c64; i++;
  if (len - i != 16) return AuthResult::BadFormat;
  char msg[64]; int n = snprintf(msg, sizeof(msg), "%s|%lu|%lu", plantId, (unsigned long)seconds, (unsigned long)counter);
  if (n <= 0 || (size_t)n >= sizeof(msg)) return AuthResult::BadFormat;
  uint8_t mac[32]; hmacSha256(key, keyLen, (const uint8_t*)msg, (size_t)n, mac);
  char hex[17]; for (int j = 0; j < 8; j++) snprintf(hex + 2 * j, 3, "%02x", mac[j]);
  if (!constantTimeEq(hex, p + i, 16)) return AuthResult::BadMac;   // check the signature BEFORE revealing replay state
  if (counter <= lastCounter) return AuthResult::Replay;
  *secondsOut = seconds; *counterOut = counter;
  return AuthResult::Ok;
}

}  // namespace greetopia
