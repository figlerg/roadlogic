#program base.

:- holds(state(car1, loc(S,0), dyn(1, 0)), 0), S > 13.
:- holds(state(car1, loc(S,0), dyn(1, 0)), 0), S < 10.

%%%%%%
%% Default parameters
%%%%%%
#const change_dur = 5.
#const max_acceleration_while_turning = 4.
#const max_braking_speed_while_turning = 7.
#const max_change_speed = 8.
#const max_lane = 1.
#const max_segment = 300.
#const max_velocity_change_lon = 10.
#const max_velocity_lat = 1.
#const max_velocity_lon = 15.
#const min_change_speed = 2.
#const safety_distance = 3.