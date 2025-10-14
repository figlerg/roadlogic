# Third-Party Notices

This project includes third-party components under distinct open-source licenses.  
All other source files are © The RoadLogic Developers and released under the **BSD 3-Clause License**.

---

## Vendored Code

### OpenSCENARIO 2.1 Grammar (MPL-2.0)
- **Files:**  
  - `planning/parse/openscenario2.g4`  
  - `planning/parse/generated/` (ANTLR-generated Python files)
- **License:** Mozilla Public License 2.0  
- **Notes:** The grammar and any generated files containing embedded actions remain under MPL-2.0.  
  See `planning/parse/LICENSE.MPL` for details.

---

## External Libraries (runtime dependencies)

These libraries are required but not bundled.  
Refer to their respective package metadata for full license terms.

- **antlr4-python3-runtime** — Apache 2.0  
- **NetworkX** — BSD  
- **CommonRoad** — BSD  
- **Frenetix Motion Planner** — LGPL-3.0 (copied verbatim)