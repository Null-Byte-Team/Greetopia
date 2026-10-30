// Greetopia sensor node - pure logic (no Arduino dependencies) so it can be unit-tested on a PC:
//   g++ -std=c++17 -Wall -Wextra -o /tmp/t tests/test_pump_logic.cpp && /tmp/t
#pragma once
#include <stdint.h>
#include <stddef.h>

namespace greetopia {

constexpr uint32_t MAX_PUMP_RUN_S      = 15;       // hard per-command limit (same as the original firmware)
constexpr uint32_t DEFAULT_ON_SECONDS  = 5;        // plain "ON" (the backend always sends ON:<n>)
constexpr uint32_t MIN_REST_MS         = 10000;    // rest between two runs
constexpr uint32_t HOURLY_BUDGET_MS    = 45000;    // defence in depth against spoofed/looping commands
constexpr uint32_t BUDGET_WINDOW_MS    = 3600000UL;
constexpr uint32_t RETAINED_GUARD_MS   = 2500;     // commands arriving right after subscribe may be retained leftovers

enum class CmdStatus : uint8_t { Accepted, Invalid, Busy, Rest, Budget, TooEarly };

// Accepts exactly "ON" or "ON:<1..4 digits>". Anything else (trailing junk, "ONX", "ON:", "ON:-3", "ON:0") is invalid.
// Values above 15 are capped to 15 (original behaviour); 0 is invalid.
inline bool parsePumpCommand(const char* p, size_t len, uint32_t* secondsOut) {
  if (!p || !secondsOut || len < 2 || len > 7) return false;
  if (p[0] != 'O' || p[1] != 'N') return false;
  if (len == 2) { *secondsOut = DEFAULT_ON_SECONDS; return true; }
  if (p[2] != ':' || len < 4) return false;
  uint32_t v = 0;
  for (size_t i = 3; i < len; i++) {
    if (p[i] < '0' || p[i] > '9') return false;
    v = v * 10 + (uint32_t)(p[i] - '0');
  }
  if (v == 0) return false;
  *secondsOut = v > MAX_PUMP_RUN_S ? MAX_PUMP_RUN_S : v;
  return true;
}

struct PumpController {
  bool running = false;
  bool everRan = false;
  uint32_t startMs = 0, durationMs = 0, lastStopMs = 0;
  uint32_t budgetUsedMs = 0, budgetWindowStartMs = 0;
  uint32_t subscribedAtMs = 0;
  bool subscribed = false;

  void onSubscribed(uint32_t nowMs) { subscribed = true; subscribedAtMs = nowMs; }

  // Decide whether a command may start; on Accepted the pump is marked running and *durationOut is the exact run time.
  CmdStatus request(uint32_t nowMs, const char* payload, size_t len, uint32_t* durationMsOut) {
    if (subscribed && (uint32_t)(nowMs - subscribedAtMs) < RETAINED_GUARD_MS) return CmdStatus::TooEarly;
    uint32_t seconds = 0;
    if (!parsePumpCommand(payload, len, &seconds)) return CmdStatus::Invalid;
    if (running) return CmdStatus::Busy;
    if (everRan && (uint32_t)(nowMs - lastStopMs) < MIN_REST_MS) return CmdStatus::Rest;
    if ((uint32_t)(nowMs - budgetWindowStartMs) >= BUDGET_WINDOW_MS) { budgetWindowStartMs = nowMs; budgetUsedMs = 0; }
    uint32_t ms = seconds * 1000UL;
    if (budgetUsedMs + ms > HOURLY_BUDGET_MS) return CmdStatus::Budget;
    budgetUsedMs += ms;
    running = true; startMs = nowMs; durationMs = ms;
    *durationMsOut = ms;
    return CmdStatus::Accepted;
  }

  bool shouldStop(uint32_t nowMs) const { return running && (uint32_t)(nowMs - startMs) >= durationMs; }
  void stopped(uint32_t nowMs) { running = false; everRan = true; lastStopMs = nowMs; }
};

enum class SoilState : uint8_t { Ok, Shorted, Open };

// Plausibility of a raw ADC reading given this probe's calibration. A reading far outside the calibrated span means a
// shorted/corroded or disconnected probe; publishing it as a percentage would be a lie, so the node reports a fault instead.
inline SoilState classifySoil(int raw, int dry, int wet) {
  int lo = dry < wet ? dry : wet, hi = dry < wet ? wet : dry;
  int span = hi - lo;
  int margin = span / 4;
  int minOk = lo - margin; if (minOk < 60) minOk = 60;      // ~0 V: shorted to ground
  int maxOk = hi + margin; if (maxOk > 4094) maxOk = 4094;  // rail value: open / floating
  if (raw < minOk) return SoilState::Shorted;
  if (raw > maxOk && hi + margin <= 4094) return SoilState::Open;
  return SoilState::Ok;
}

inline int soilPercent(int raw, int dry, int wet) {
  if (dry == wet) return 0;
  long p = (long)(raw - dry) * 100L / (long)(wet - dry);
  return p < 0 ? 0 : (p > 100 ? 100 : (int)p);
}

}  // namespace greetopia
