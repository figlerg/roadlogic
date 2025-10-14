# I load the scenario and create a list of goals

from commonroad.planning.goal import GoalRegion
from commonroad.common.util import Interval, AngleInterval
from commonroad.scenario.state import CustomState, ExtendedPMState, PMState, InitialState
from commonroad.geometry.shape import Rectangle
from commonroad.planning.planning_problem import PlanningProblem, PlanningProblemSet
from commonroad.common.file_writer import CommonRoadFileWriter,OverwriteExistingFile
from commonroad.common.file_reader import CommonRoadFileReader
from commonroad.visualization.mp_renderer import MPRenderer
from commonroad_extensions.plan_execution.id_hash import encode
import matplotlib.pyplot as plt
import numpy as np


""" TODO: just like in multi_goals_synch, but now we make a functioning overtake maneuver.
            As a base we take the "threelanes.xml" map and then take a couple goals which 
            are easily drivable and obviously do an overtake.
            e.g. force car 1 on the right lane and let ego do two lane changes
"""


file_path = "scenarios_old/threelanes.xml" # straight lanes for this one
scenario, planning_problem_set = CommonRoadFileReader(file_path).open()

def draw():
    plt.figure(figsize=(25, 10))
    rnd = MPRenderer()
    scenario.draw(rnd)
    planning_problem_set.draw(rnd)
    rnd.render(show=True)
    plt.show()

# draw()

# fetch one of the original planning problems
original_planning_problem = planning_problem_set.planning_problem_dict[3]
x0 = original_planning_problem.initial_state
x0.velocity = 1
x0_2 = InitialState(position=np.asarray((12,0)), orientation=x0.orientation, velocity=x0.velocity, acceleration=x0.acceleration,yaw_rate=x0.yaw_rate,slip_angle=x0.slip_angle, time_step=x0.time_step)

# ego: (0,0), (25,3), (50,3), (80,0)

# goal points
x1 = np.asarray((25,3))
x2 = np.asarray((50,3))
x3 = np.asarray((68,0))

# rectangles (I don't care about orientation for now)
R1 = Rectangle(5.,3.,x1,0)
R2 = Rectangle(5.,3.,x2,0)
R3 = Rectangle(5.,3.,x3,0)

# timing constraints
I1 = Interval(100, 110) # TODO check if realistic
I2 = Interval(140, 150) 
I3 = Interval(180, 190) 

V1 = None  
V2 = None
V3 = None

# I found this class in the commonroad files. I think they are used for goal regions in the planning problems. 
goal_state_1 = ExtendedPMState(time_step=I1, position=R1, velocity=V1)
goal_state_2 = ExtendedPMState(time_step=I2, position=R2, velocity=V2)
goal_state_3 = ExtendedPMState(time_step=I3, position=R3, velocity=V3)

new_planning_problem = PlanningProblem(encode('ego'),x0,GoalRegion([goal_state_1,goal_state_2,goal_state_3]))


#### NOW WE BUILD ANOTHER PLANNING PROBLEM FOR 2ND ACTOR
# car1: (15,0), (30,0), (45,0), (60,0)


# goal points
x1_2 = np.asarray((30,0))
x2_2 = np.asarray((45,0))
x3_2 = np.asarray((60,0))

# rectangles (I don't care about orientation for now)
R1_2 = Rectangle(5.,3.,x1_2,0)
R2_2 = Rectangle(5.,3.,x2_2,0)
R3_2 = Rectangle(5.,3.,x3_2,0)

# V3 = Interval(1,70)
V1_2 = None
V2_2 = None  
V3_2 = None

# I found this class in the commonroad files. I think they are used for goal regions in the planning problems. 
goal_state_1_2 = ExtendedPMState(time_step=I1, position=R1_2, velocity=V1_2)
goal_state_2_2 = ExtendedPMState(time_step=I2, position=R2_2, velocity=V2_2)
goal_state_3_2 = ExtendedPMState(time_step=I3, position=R3_2, velocity=V3_2)

new_planning_problem_2 = PlanningProblem(encode('car1'),x0_2,GoalRegion([goal_state_1_2,goal_state_2_2,goal_state_3_2]))

planning_problem_set = PlanningProblemSet([new_planning_problem,new_planning_problem_2])

draw()

fw = CommonRoadFileWriter(scenario,planning_problem_set, "Felix Gigler", "AIT")

fw.write_to_file('scenarios_old/positive_overtake.xml', OverwriteExistingFile.ALWAYS)