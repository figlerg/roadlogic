
% #include <incmode>.



#program base.

holds(F,0) :- init(F).


#program step(t).
%% Generate


% NOTE: I did some refactoring to make this clearer.
%			I marked anything to do with longitudinal distance and segments
%			with "lon" for longitudinal - so the dimension which cares about variables S, for segments.
%			All the lane change stuff is marked with "lat" for lateral, with variables L for lanes.


% Our 'action' is change_dynamics(Vehicle, Delta_Velocity_lon, Velocity_lat) which specifies how the dynamics of each vehicle change at each step.
% NOTE: Delta_Velocity_lon is relative to Velocity_lon from the previous step

% exactly one action per car per time
{ occurs(change_dynamics(V, Delta_Vel_lon, Vel_lat), t) : acceleration_lon(Delta_Vel_lon), velocity_lat(Vel_lat)}
			= 1 :- vehicle(V).

% force each vehicle to have a position at each time TODO it felt like this decreased solve speed by about 70%
:- vehicle(V), holds(state(V,_,_), t-1), not holds(state(V,_,_), t). % the t-1 part is just for optimization - smaller search space maybe


%% Define
holds(state(V,loc(S,L),dyn(Vel_lon,Vel_lat)), t) :-
		holds(state(V,loc(S_prev,L_prev),dyn(Vel_lon_prev, Vel_lat_prev)), t-1),
		occurs(change_dynamics(V, Delta_Vel_lon, Vel_lat), t),
		L = L_prev + Vel_lat_prev,
		S = S_prev + Vel_lon_prev,
		Vel_lon = Vel_lon_prev + Delta_Vel_lon,
		velocity_lon(Vel_lon).

%% one major assumption: cars are moving
% :- holds(state(_, loc(_,_), dyn(Vel_lon,_)), t), Vel_lon=0, t!=0.
%% TODO lifted this experimentally for the static obstacle experiment!


%%% block lane changes for a while after one happened. Experiments indicate that this is usually around 6-7 seconds (for scenic)
block_duration(1..change_dur).
stay(V, t) :- holds(state(V, loc(_, _), dyn(_, Vel_lat)), T), Vel_lat != 0, block_duration(D), t = T + D.

% make sure that there are no lane changes during the blocked times
:- holds(state(V, loc(_,_), dyn(_,Vel_lat)), T), stay(V, T), Vel_lat != 0.


% TODO experimental: make sure that the speed remains constant during blocked segments
% :- holds(state(V, loc(_,_), dyn(Vel_lon,_)), T), stay(V, T, t), not holds(state(V, loc(_,_), dyn(Vel_lon,_)), T+1).


%% Test
:- holds(state(_,loc(_,_),dyn(Vel_lon,_)),t), not velocity_lon(Vel_lon).                % min/max_velocity_allowed constraint
:- holds(state(_,loc(_,L),dyn(_,Vel_lat)),t), not lane(L+Vel_lat).                     	% stay_on_road constraint w.r.t. lanes, i.e. road width
:- holds(state(_,loc(S,_),dyn(Vel_lon,_)),t), not segment(S+Vel_lon).                  	% stay_on_road constraint w.r.t. segments, i.e. road length
:- holds(state(V1,loc(S,L),dyn(_,_)),t), holds(state(V2,loc(S1,L),dyn(_,_)),t),
   |S1 - S| - 1 < safety_distance, V1 != V2.                                            % safe distance constraint



% For all segments S_mid between S1 and S2, check that no other vehicle occupies it at t
:- holds(state(V1, loc(S1, L), dyn(_, _)), t-1),
   holds(state(V1, loc(S2, L), dyn(_, _)), t),
   holds(state(V2, loc(S_mid, L), dyn(_, _)), t),
   vehicle(V1), vehicle(V2),
   segment(S1), segment(S2), segment(S_mid), lane(L), time(t-1),
   V1 != V2,
   S1 < S_mid, S_mid < S2.

% left change version (note that this is just an approximation due to the discrete lanes: same principle as above but moved by one lane)
:- holds(state(V1, loc(S1, 		L), 	dyn(_,_)), t-1),
   holds(state(V1, loc(S2, 		L-1), 	dyn(_, _)), t),
   holds(state(V2, loc(S_mid, 	L-1), 	dyn(_,_)), t),
   vehicle(V1), vehicle(V2),
   segment(S1), segment(S2), segment(S_mid), lane(L), lane(L-1), time(t-1),
   V1 != V2,
   S1 - safety_distance_back < S_mid, S_mid < S2.

% right change version (note that this is just an approximation due to the discrete lanes: same principle as above but moved by one lane)
:- holds(state(V1, loc(S1, 		L), 	dyn(_,_)), t-1),
   holds(state(V1, loc(S2, 		L+1), 	dyn(_, _)), t),
   holds(state(V2, loc(S_mid, 	L+1), 	dyn(_,_)), t),
   vehicle(V1), vehicle(V2),
   segment(S1), segment(S2), segment(S_mid), lane(L), lane(L+1), time(t-1),
   V1 != V2,
   S1 - safety_distance_back < S_mid, S_mid < S2.


