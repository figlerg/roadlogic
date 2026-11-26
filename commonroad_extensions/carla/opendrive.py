"""The CommonRoad road as an OpenDRIVE road for CARLA (client.generate_opendrive_world).

One straight road along +x with one right-hand driving lane per lanelet, in the CommonRoad x, y coordinates:
the reference line runs along the left edge of the left lane, the lanes lie to its right (negative ids).
Assumes side by side lanelets of equal width along x, as in threelanes.xml. The road is extended at both
ends, so cars can keep driving after the plan.

CARLA's world is left-handed: a point (x, y) of OpenDRIVE and CommonRoad is (x, -y) in CARLA, and a
heading h is -h. carla_drive.py converts.
"""
import numpy as np

TEMPLATE = """<?xml version="1.0" standalone="yes"?>
<OpenDRIVE>
  <header revMajor="1" revMinor="4" name="roadlogic" version="1.00"/>
  <road name="roadlogic" length="{length:.3f}" id="1" junction="-1">
    <link/>
    <planView>
      <geometry s="0.0" x="{x0:.3f}" y="{y0:.3f}" hdg="0.0" length="{length:.3f}"><line/></geometry>
    </planView>
    <elevationProfile/>
    <lateralProfile/>
    <lanes>
      <laneSection s="0.0">
        <center>
          <lane id="0" type="none" level="false"><link/><roadMark sOffset="0.0" type="solid" weight="standard" color="standard" width="0.15"/></lane>
        </center>
        <right>
{lanes}
        </right>
      </laneSection>
    </lanes>
  </road>
</OpenDRIVE>
"""
LANE = """          <lane id="{id}" type="driving" level="false"><link/>
            <width sOffset="0.0" a="{width:.3f}" b="0.0" c="0.0" d="0.0"/>
            <roadMark sOffset="0.0" type="{mark}" weight="standard" color="standard" width="0.15"/>
          </lane>"""


def road_xodr(scenario, before=50.0, after=300.0):
    """OpenDRIVE text for a CommonRoad scenario's lanelets, extended by before/after metres."""
    lanelets = sorted(scenario.lanelet_network.lanelets, key=lambda l: -l.center_vertices[0][1])   # left to right
    left_edge = lanelets[0].left_vertices
    x0, x1 = float(left_edge[0][0]) - before, float(left_edge[-1][0]) + after
    widths = [float(np.linalg.norm(l.left_vertices[0] - l.right_vertices[0])) for l in lanelets]
    lanes = "\n".join(LANE.format(id=-(k + 1), width=w, mark="solid" if k == len(lanelets) - 1 else "broken")
                      for k, w in enumerate(widths))
    return TEMPLATE.format(length=x1 - x0, x0=x0, y0=float(left_edge[0][1]), lanes=lanes)
