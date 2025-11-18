
%%% CONSTANTS & SETUP  $$$




#program base.

% grid size
#const max_lane = 1.
#const max_segment = 300.

% actor constraints
#const max_velocity_change_lon = 8.
#const max_velocity_lon = 12.
#const max_velocity_lat = 1.
#const safety_distance = 4.
#const safety_distance_back = 6.  

% controller specific constants
#const change_dur = 3. 
#const min_change_speed = 6.
#const max_change_speed = 9.
#const max_braking_speed_while_turning = 4. 
#const max_acceleration_while_turning = 1. 