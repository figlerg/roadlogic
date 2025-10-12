% some rules that I am experimenting with NOT CURRENTLY USED

% this is a stricter rule which says that NO ACTOR can move while anyone's blocked
% I include this because sometimes it happens that our heuristics fail because actors do things at the same time
%  and the ideal world doesn't match the simulation exactly
%:- query(t), holds(state(_, loc(_,_), dyn(_,Vel_y)), T), stay(V, T, t), Vel_y != 0.

%  at low speeds the lane changes take long or do not finish
%:- occurs(change_dynamics(V, Delta_Vel_x, Vel_y), t), Vel_y != 0, Delta_Vel_x < 4.

% experimenting with blocking the lane a car is changing to
%stay(V,T+1,t) :- query(t), holds(state(V, loc(_,_), dyn(_,Vel_y)), T), Vel_y != 0.


%% testing again with simple stuff:
%occurs(change_dynamics(npc1, 0, 0), t).    % car1 is moving all the time straightforward at constant velocity

%:- query(t), holds(state(ego, loc(19,1),dyn(5,0)), t), t=6.

% DEBUG
%#program check(t).
%:- holds(state(car1,loc(19,1),dyn(7,0)),t), t=6.