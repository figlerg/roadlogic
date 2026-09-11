# New since the HSCC 2026 paper

What has been added for the journal version.

- **Invariants with `keep`.** A scenario can say that something must hold throughout, either for
  the whole scenario or only while one part of it runs. For example, a car stays in its lane, keeps
  its speed within a range, or stays within some distance of another car. Not yet supported: the
  `keep_lane()` shorthand, soft `default` keeps, and checking invariants in simulation.

- **Inconsistency detection.** When the requirements of a scenario contradict each other, the
  planner reports that no plan exists instead of producing one. This covers direct contradictions,
  conflicts between parts that run in parallel, and conflicts that only show up over time, the cases
  the OpenSCENARIO standard describes but gives no way to detect.

- **Speed.** A scenario can set a car's speed at the start or end of a phase, keep it within a
  range, or require one car to be faster or slower than another.

- **Duration.** The duration written in a scenario, for the whole scenario or for one part of it, is
  now respected. Before, it was ignored. This rules out plans that are too short or too long, and
  detects timings that cannot fit together.

- **Faster planning.** Every plan used to run two extra steps after its goals were met. Plans now
  end when the goals are met, which is 2 to 8 times faster on the benchmarks. Simulated scenarios
  complete just as before. The old behaviour is one switch away, for reproducing the paper.

- **Units.** Values are given in m, s and mps, and are used exactly as written. Other units are
  rejected instead of being silently misread.

- **Reliability.** Several bugs fixed that made the planner silently ignore parts of a scenario or
  reject valid ones. Tests for each new feature, and a regression suite over the paper's benchmarks.
