# New since the HSCC 2026 paper

What has been added for the journal version.

- **Invariants with `keep`.** A scenario can say that something must hold throughout, either for
  the whole scenario or only while one part of it runs. For example, a car stays in its lane, keeps
  its speed within a range, or stays within some distance of another car. The standard's shorthands `keep_lane()` and
  `keep_speed()` work as well. Not yet supported: soft `default` keeps, and checking invariants
  in simulation.

- **Inconsistency detection.** When the requirements of a scenario contradict each other, the
  planner reports that no plan exists instead of producing one. This covers direct contradictions,
  conflicts between parts that run in parallel, and conflicts that only show up over time, the cases
  the OpenSCENARIO standard describes but gives no way to detect.

- **Speed.** A scenario can set a car's speed at the start or end of a phase, keep it within a
  range, or require one car to be faster or slower than another.

- **Choices and parallel parts are planned completely.** A scenario that offers alternatives
  (`one_of`) used to be planned along its first alternative only, and a scenario with parts running
  in parallel along one order in which those parts end. Now every alternative and every order is
  planned, and the plans are taken from them in turn. Before, a scenario whose first alternative was
  impossible was wrongly reported as having no plan. The first plan comes as fast as before, because
  the alternatives are solved side by side rather than one after another.

- **No long searches for plans that do not exist.** Asking for more plans than a scenario has used
  to search up to the longest plan length allowed. Now the search for more plans stops shortly after
  the first one. The search for a first plan is unchanged, so a scenario reported as having no plan
  still has none.

- **Duration.** The duration written in a scenario, for the whole scenario or for one part of it, is
  now respected. Before, it was ignored. This rules out plans that are too short or too long, and
  detects timings that cannot fit together.

- **Faster planning.** Every plan used to run two extra steps after its goals were met. Plans now
  end when the goals are met, which is 2 to 8 times faster on the benchmarks. Simulated scenarios
  complete just as before. The old behaviour is one switch away, for reproducing the paper.

- **Checking the simulation, not just the plan.** The monitor used to check only that the cars
  reached their goals in order. It now also checks the invariants and the durations against the
  finished simulation, so a run that meets every goal but breaks a `keep` on the way, or takes too
  long or too short for one of its parts, is reported as a failure.

- **Clocks in the monitor.** A duration on a part of the scenario that starts partway through needs
  to know when that part began. The monitor now keeps a clock per possible run, started when a part
  begins and checked when it ends. Without it, a car could pass a speed requirement by meeting it for
  a single moment.

- **Units.** Values are given in m, s and mps, and are used exactly as written. Other units are
  rejected instead of being silently misread.

- **Reliability.** Several bugs fixed that made the planner silently ignore parts of a scenario or
  reject valid ones. Tests for each new feature, and a regression suite over the paper's benchmarks.
