#include <cassert>
#include <cstdio>
#include <cstring>
#include "../pump_logic.h"
using namespace greetopia;

static bool parse(const char* s, uint32_t* out) { return parsePumpCommand(s, strlen(s), out); }
static CmdStatus req(PumpController& c, uint32_t now, const char* s, uint32_t* ms) { return c.request(now, s, strlen(s), ms); }

int main() {
  uint32_t v = 0;
  // --- strict parsing
  assert(parse("ON", &v) && v == 5);
  assert(parse("ON:8", &v) && v == 8);
  assert(parse("ON:15", &v) && v == 15);
  assert(parse("ON:60", &v) && v == 15);          // capped, never longer than the hard limit
  assert(parse("ON:9999", &v) && v == 15);
  const char* bad[] = {"", "O", "ONX", "ON:", "ON:0", "ON:-3", "ON:abc", "ON:5x", "on:5", "ON: 5", "OFF", "ON:12345", "ON:1:2", "ON\n", "ONON"};
  for (const char* b : bad) assert(!parse(b, &v));
  assert(!parsePumpCommand(nullptr, 2, &v));

  // --- state machine
  PumpController c; uint32_t ms = 0;
  assert(req(c, 100000, "ON:5", &ms) == CmdStatus::Accepted && ms == 5000 && c.running);
  assert(req(c, 100100, "ON:5", &ms) == CmdStatus::Busy);          // a new command never extends a running pump
  assert(!c.shouldStop(104999) && c.shouldStop(105000));
  c.stopped(105000);
  assert(req(c, 106000, "ON:5", &ms) == CmdStatus::Rest);          // minimum rest
  assert(req(c, 116000, "ON:5", &ms) == CmdStatus::Accepted);
  c.stopped(121000);

  // --- hourly budget (45 s): 5+5 used, then 15*2 = 30 -> 40 ok, next 15 -> 55 > 45 rejected
  assert(req(c, 140000, "ON:15", &ms) == CmdStatus::Accepted); c.stopped(155000);
  assert(req(c, 170000, "ON:15", &ms) == CmdStatus::Accepted); c.stopped(185000);
  assert(req(c, 200000, "ON:15", &ms) == CmdStatus::Budget);
  assert(!c.running);
  assert(req(c, 200000 + BUDGET_WINDOW_MS, "ON:15", &ms) == CmdStatus::Accepted); // window rolled over

  // --- retained-message guard right after subscribing
  PumpController d; d.onSubscribed(5000);
  assert(req(d, 6000, "ON:5", &ms) == CmdStatus::TooEarly);
  assert(req(d, 5000 + RETAINED_GUARD_MS, "ON:5", &ms) == CmdStatus::Accepted);

  // --- millis() rollover (49.7 days)
  PumpController e; uint32_t near = 0xFFFFFF00u;
  assert(req(e, near, "ON:3", &ms) == CmdStatus::Accepted);
  assert(!e.shouldStop(near + 100) && e.shouldStop((uint32_t)(near + 3000)));  // wraps past zero correctly

  // --- soil plausibility
  assert(classifySoil(2500, 4095, 1500) == SoilState::Ok);
  assert(classifySoil(4095, 4095, 1500) == SoilState::Ok);   // truly dry soil must not be flagged as a fault
  assert(classifySoil(1500, 4095, 1500) == SoilState::Ok);
  assert(classifySoil(30, 4095, 1500) == SoilState::Shorted);
  assert(classifySoil(0, 3000, 1200) == SoilState::Shorted);
  assert(classifySoil(4095, 3000, 1200) == SoilState::Open);  // far above the dry calibration => floating/open
  assert(soilPercent(4095, 4095, 1500) == 0 && soilPercent(1500, 4095, 1500) == 100 && soilPercent(2797, 4095, 1500) == 50);
  assert(soilPercent(0, 4095, 1500) == 100 && soilPercent(5000, 4095, 1500) == 0 && soilPercent(5, 7, 7) == 0);

  std::puts("firmware logic tests: all passed");
  return 0;
}
