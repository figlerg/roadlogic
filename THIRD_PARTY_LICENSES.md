# Third-Party Notices

This project includes third-party components under distinct open-source licenses.  
Except for the third-party components listed above, all source files are © The RoadLogic Developers and released under the **BSD 3-Clause License**. See `LICENSE` for details.

---

## Vendored Code

### OpenSCENARIO 2.1 Grammar (MPL-2.0)
- **Files:**  
  - `planning/parse/openscenario2.g4`  
  - `planning/parse/generated/` (ANTLR-generated Python files)
- **License:** Mozilla Public License 2.0  
- **Notes:** The grammar and any generated files containing embedded actions remain under MPL-2.0.  
  See `planning/parse/LICENSE.MPL` for details.


### Frenetix Motion Planner (LGPL-3.0)
- **Path:** `Frenetix-Motion-Planner/`
- **License:** GNU Lesser General Public License v3.0
- **Notes:** 
  - This code is included in modified form and remains under LGPL-3.0.
  - The forking point of the shipped code is commit fc6e7708ba384f991c2a0a07b7300ab52276c70f of the repository https://github.com/TUM-AVS/Frenetix-Motion-Planner.git.
  - Source and modification history are provided in this repository as required by the license.
  - See `Frenetix-Motion-Planner/LICENSE` for full text.




---

## External Libraries (runtime dependencies)

These libraries are required but not bundled.  
Refer to their respective package metadata for full license terms.

- **antlr4-python3-runtime** — Apache 2.0  
- **NetworkX** — BSD  
- **CommonRoad** — BSD  
- **Clingo** - MIT
- **NumPy** — BSD  
- **SciPy** — BSD  
- **Matplotlib** — PSF-based (BSD-compatible)  




## Other dependencies

A full dependency license report can be generated via pip-licenses using the provided environment file.