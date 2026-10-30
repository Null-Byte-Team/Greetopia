# ISEF methodology (template: fill in with YOUR real data; nothing here is a result)

**Research question:** Does a three-depth, safety-bounded adaptive irrigation controller use less water and/or keep root-zone moisture closer to a plant's target than a fixed schedule?

**Hypothesis (edit):** <state the expected direction and the reasoning, before collecting data>.

**Variables:** independent = controller (adaptive vs fixed_schedule); dependent = water used (measured if a flow sensor is added, else estimated), time root moisture below target, stress integral, moisture stability, growth proxy; controlled = species, pot/soil, light, camera position, pump and tubing, plant age.

**Design:** randomised assignment with a stored seed (docs/EXPERIMENTS.md); >= 4 plants per arm recommended for any inference (3 is the minimum for a p-value); both arms share the same safety limits; record start/end and any disturbance.

**Procedure:** calibrate probes in your soil (CALIBRATION_MODE), measure pump flow into a cylinder, run `docs/BENCH_TEST.md`, create and start the experiment, do not intervene except for logged safety reasons, stop at the planned end, export the data pack.

**Analysis:** the plan stored with the experiment (Mann-Whitney U, effect size, bootstrap CI). Report n, ties, exact vs approximate p, and the intervals, not only p.

**Safety and ethics:** low-voltage, fused pump supply, relay pull-up so the pump is off during resets, 15 s hardware cutoff, hourly runtime budget, signed commands on a private broker; no animals or people are involved; water use is the only consumable. Photos are of plants only.

**Data provenance:** device readings and irrigation events from the Greetopia database with server receive time (the nodes send no timestamps); every number is labelled measured / estimated / derived / simulated.

**Limitations (edit honestly):** small n, one location and season, resistive-probe drift, camera proxy rather than biomass, no flow sensor unless added, model results depend on the data collected.

**Reproduce:** `docs/EXPERIMENTS.md` export pack + the exact git commit + the seed.
