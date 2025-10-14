#program base.
%%%%%%
%% Default parameters
%%%%%%
% #const change_dur = 5.
% #const max_acceleration_while_turning = 4.
% #const max_braking_speed_while_turning = 7.
% #const max_change_speed = 8.
% #const max_lane = 1.
% #const max_segment = 300.
% #const max_velocity_change_lon = 10.
% #const max_velocity_lat = 1.
% #const max_velocity_lon = 15.
% #const min_change_speed = 2.
% #const safety_distance = 3.

#program check(t).

% Count each lane change per actor and timestep
lane_change(V,t) :- holds(state(V, _, dyn(_, Vel_lat)), t), Vel_lat != 0, vehicle(V).


lane_change_count(N,t) :- N = #count { V,T : lane_change(V,T), vehicle(V), time(T) }.
:- N != 2, lane_change_count(N,t), query(t).


