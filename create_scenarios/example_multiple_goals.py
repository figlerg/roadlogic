# I load the scenario and create a list of goals

from commonroad.planning.goal import GoalRegion
from commonroad.common.util import Interval, AngleInterval
from commonroad.scenario.state import CustomState, ExtendedPMState, PMState, InitialState
from commonroad.geometry.shape import Rectangle
from commonroad.planning.planning_problem import PlanningProblem, PlanningProblemSet
from commonroad.common.file_writer import CommonRoadFileWriter,OverwriteExistingFile
from commonroad.common.file_reader import CommonRoadFileReader
from commonroad.visualization.mp_renderer import MPRenderer

import matplotlib.pyplot as plt
import numpy as np

file_path = "scenarios/scenario.xml"
scenario, planning_problem_set = CommonRoadFileReader(file_path).open()

def draw():
    plt.figure(figsize=(25, 10))
    rnd = MPRenderer()
    scenario.draw(rnd)
    planning_problem_set.draw(rnd)
    rnd.render(show=True)
    plt.show()

# fetch one of the original planning problems
original_planning_problem = planning_problem_set.planning_problem_dict[1012]
x0 = original_planning_problem.initial_state

# goal points
x1 = np.asarray((100, -83.1 ))
x2 = np.asarray((150, -119.2))
x3 = np.asarray((175, -159.1))

# rectangles (I don't care about orientation for now)
R1 = Rectangle(5.,3.,x1,-np.pi/4)
R2 = Rectangle(5.,3.,x2,-np.pi/4)
R3 = Rectangle(5.,3.,x3,-np.pi/4)

# timing constraints
I1 = Interval(150, 151) # Since we are using 1/10 s and the distances are ~170m, a time of 30=3s would mean some absurd 200kph speed. I try something more sensible
I2 = Interval(275, 276) 
I3 = Interval(340, 341) 

# # velocity constraints. I am not sure about the units here, so I leave these broad
# V1 = Interval(1,70)  # dist is about 170 distance units. to reach goal in 30 time units we need about 6 distaceunits/timeunits
# V2 = Interval(1,70)  
# V3 = Interval(1,70)
V1 = None
V2 = None  
V3 = None

# I found this class in the commonroad files. I think they are used for goal regions in the planning problems. 
goal_state_1 = ExtendedPMState(time_step=I1, position=R1, velocity=V1)
goal_state_2 = ExtendedPMState(time_step=I2, position=R2, velocity=V2)
goal_state_3 = ExtendedPMState(time_step=I3, position=R3, velocity=V3)

# I can wrap them in a goal region
# goal_region_1 = GoalRegion(goal_state_1)
# goal_region_2 = GoalRegion(goal_state_2)
# goal_region_3 = GoalRegion(goal_state_3)

# these can then be used to define a planning problem, but I need the initial state for that
# planning_problem = PlanningProblem(42, initial_state=x0, goal_region=goal_region_1,...)

# goals = [goal_region_1,goal_region_2,goal_region_3]
new_planning_problem = PlanningProblem(42,x0,GoalRegion([goal_state_1,goal_state_2,goal_state_3]))

# new_planning_problem_set = planning_problem_set
planning_problem_set = dict()
planning_problem_set = PlanningProblemSet([new_planning_problem,])

# draw()

fw = CommonRoadFileWriter(scenario,planning_problem_set, "Felix Gigler", "AIT")

fw.write_to_file('scenarios/multigoals.xml', OverwriteExistingFile.ALWAYS)