
%%% CONSTANTS & SETUP  $$$




#program base.
%#show holds/2.


#const max_lane = 1.
#const max_segment = 300.
#const max_velocity_change_lon = 8.
#const max_velocity_lon = 12.
#const max_velocity_lat = 1.
#const safety_distance = 3.


% controller specific constants
#const change_dur = 6. % for CARLA this was around 4s, in CR I just keep it low for now
#const min_change_speed = 6.
#const max_change_speed = 9.
#const max_braking_speed_while_turning = 4. 
#const max_acceleration_while_turning = 1. 
#const safety_distance_back = 7.  % this is after observing that many problems arise from cars changing lane too close to a car behind them 