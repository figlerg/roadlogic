#program base.

%%%%%%
%% Varied parameters
%%%%%%
#const change_dur = 1.
#const init_distance = 11.
init(state(car1, loc(init_distance,0), dyn(1, 0))).

#const max_acceleration_while_turning = 1.
#const max_braking_speed_while_turning = 3.
#const max_change_speed = 8.
#const max_lane = 1.
#const max_segment = 300.
#const min_change_speed = 6.
#const safety_distance = -1.

%%%%%%
%% Default parameters
%%%%%%
#const max_velocity_change_lon = 8.
#const max_velocity_lat = 1.
#const max_velocity_lon = 12.
#const safety_distance_back = 3.
