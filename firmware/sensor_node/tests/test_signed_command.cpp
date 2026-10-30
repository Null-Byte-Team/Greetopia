#include <cassert>
#include <cstdio>
#include <cstring>
#include "../signed_command.h"
using namespace greetopia;

static void hex(const uint8_t* d, int n, char* out) { for (int i = 0; i < n; i++) snprintf(out + 2 * i, 3, "%02x", d[i]); }

int main() {
  // RFC 4231 test case 1 and 2 for HMAC-SHA256
  uint8_t key1[20]; memset(key1, 0x0b, 20); uint8_t out[32]; char h[65];
  hmacSha256(key1, 20, (const uint8_t*)"Hi There", 8, out); hex(out, 32, h);
  assert(strcmp(h, "b0344c61d8db38535ca8afceaf0bf12b881dc200c9833da726e9376c2e32cff7") == 0);
  hmacSha256((const uint8_t*)"Jefe", 4, (const uint8_t*)"what do ya want for nothing?", 28, out); hex(out, 32, h);
  assert(strcmp(h, "5bdcc146bf60754e6a042426089575c75a003f089d2739839dec58b964ec3843") == 0);
  // SHA-256("abc")
  Sha256 s; s.init(); s.update((const uint8_t*)"abc", 3); s.final(out); hex(out, 32, h);
  assert(strcmp(h, "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad") == 0);

  // Vector produced by the BACKEND implementation (Python): key = 'k'*32, "plant01|7|1767225600"
  const uint8_t key[32] = {'k','k','k','k','k','k','k','k','k','k','k','k','k','k','k','k','k','k','k','k','k','k','k','k','k','k','k','k','k','k','k','k'};
  const char* good = "ON:7:1767225600:a8d2e9d5d6260ae1";
  uint32_t sec = 0, ctr = 0;
  assert(verifySigned(good, strlen(good), "plant01", key, 32, 0, &sec, &ctr) == AuthResult::Ok && sec == 7 && ctr == 1767225600u);
  assert(verifySigned(good, strlen(good), "plant01", key, 32, 1767225600u, &sec, &ctr) == AuthResult::Replay);   // same counter
  assert(verifySigned(good, strlen(good), "plant01", key, 32, 1767225601u, &sec, &ctr) == AuthResult::Replay);   // older counter
  assert(verifySigned(good, strlen(good), "plant02", key, 32, 0, &sec, &ctr) == AuthResult::BadMac);             // other plant
  const uint8_t bad[32] = {1};
  assert(verifySigned(good, strlen(good), "plant01", bad, 32, 0, &sec, &ctr) == AuthResult::BadMac);
  char tampered[64]; strcpy(tampered, good); tampered[3] = '9';                                                 // 7 -> 9 seconds
  assert(verifySigned(tampered, strlen(tampered), "plant01", key, 32, 0, &sec, &ctr) == AuthResult::BadMac);
  const char* bads[] = {"", "ON", "ON:7", "ON:7:5", "ON:7:5:short", "ON:x:5:0123456789abcdef", "ON:7:99999999999:0123456789abcdef", "OFF:7:5:0123456789abcdef", "ON:12345:5:0123456789abcdef"};
  for (const char* b : bads) assert(verifySigned(b, strlen(b), "plant01", key, 32, 0, &sec, &ctr) == AuthResult::BadFormat);
  std::puts("signed command tests: all passed");
  return 0;
}
