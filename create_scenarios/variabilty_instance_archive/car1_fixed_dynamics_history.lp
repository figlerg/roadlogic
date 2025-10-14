#program base.
% keep_lane(0).
% keep_lane(1).

#program step(t).

% Count each lane change per actor and timestep

%% OPTION 1
% lane_change(V,t) :- holds(state(V, _, dyn(_, Vel_lat)), t), Vel_lat != 0, vehicle(V).
% :- lane_change(V,t), V=car1.

%% OPTION 2 by alessio and me

% be_on_lane(V,L,t) :- holds(state(V, loc(_,L), dyn(_, _)), t).
% keep_lane(t) :- be_on_lane(V,L,t), be_on_lane(V,L,t-1), V=car1, time(t-1).

% :- not keep_lane(t), t>0.
% :- not keep_lane(t), t>1.

%% OPTION 3 by me (disallow dynamics change). NOTE: PROBABLY ALL OF THESE ARE FINE, THE INSTANCE WAS OVERCONSTRAINED ELSEWHERE
% debug(t) :- occurs(change_dynamics(V,_,VLAT),t), V=car1, VLAT != 0.
:- occurs(change_dynamics(V,_,VLAT),t), V=car1, VLAT != 0.




