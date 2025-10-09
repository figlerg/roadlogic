% INITIAL SETUP FACTS:

#program base.

%% Define

segment(-5..max_segment).
velocity_lon(0..max_velocity_lon).
velocity_lat(0).
acceleration_lon(-max_velocity_change_lon..max_velocity_change_lon).

#show holds/2.


#const max_segment = 300.
#const max_velocity_change_lon = 10.
#const max_velocity_lon = 15.
#const safety_distance = 3.
#const change_dur = 5.


init(state(ego,loc(0,0),dyn(15,0))).
init(state(car1,loc(5,0),dyn(1,0))).
%1 { init(state(car1, loc(S1, L1), dyn(1,0))) : segment(S1),lane(L1), L2 = L1, -20 <= (S2 - S1) <= -10 } 1
%	:- init(state(ego, loc(S2, L2), dyn(1,0))).

vehicle(car1).
vehicle(ego).


#program check(t).

% GOAL RULES:
time(t).

% check whether ego can get past car1
%lane(0..1).  % ... on 2 lanes (should be possible)
lane(0).      % ... on 1 lane (should not be possible)
goal1(t) :- time(t), holds(state(car1,loc(S1,L),dyn(_,_)), t),holds(state(ego,loc(S2,L),dyn(_,_)), t), S2 > S1.


 % GOAL ASSERTION:
goal(t) :- goal1(T1), 5 <= T1 <= t.
:- query(t), not goal(t).
