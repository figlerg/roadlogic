% INITIAL SETUP FACTS:

#program base.

init(state(ego,loc(0,0),dyn(1,0))).
1 { init(state(car1, loc(S1, L1), dyn(1,0))) : segment(S1),lane(L1), -20 <= (S2 - S1) <= -10, L2 = L1 } 1 
	:- init(state(ego, loc(S2, L2), dyn(1,0))).

vehicle(car1).
vehicle(ego).


#program check(t).

% GOAL RULES:

goal1(t) :- holds(state(ego,loc(S1,L1),dyn(_,_)), t),holds(state(car1,loc(S2,L2),dyn(_,_)), t), L1 < L2.
goal2(t) :- holds(state(ego,loc(S1,L1),dyn(_,_)), t),holds(state(car1,loc(S2,L2),dyn(_,_)), t), 1 <= (S1 - S2) <= 10.
goal3(t) :- holds(state(ego,loc(S1,L1),dyn(_,_)), t),holds(state(car1,loc(S2,L2),dyn(_,_)), t), 5 <= (S1 - S2) <= 10, L1 = L2.


 % GOAL ASSERTION:
goal(T1,T2,T3,t) :-  goal1(T1),goal2(T2),goal3(T3), 0 <= T1<=T2<=T3 <= t, t >= T3, t>8.
:- query(t), not goal(_,_,_,t).
