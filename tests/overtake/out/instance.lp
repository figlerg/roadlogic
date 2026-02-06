% INITIAL SETUP FACTS:

#program base.

1 { init(state(car1, loc(S1, L1), dyn(1,0))) : segment(S1),lane(L1), 10 <= (S1 - S2) <= 20, L1 = L2 } 1 
	:- init(state(ego, loc(S2, L2), dyn(1,0))).
init(state(ego,loc(0,2),dyn(1,0))).

vehicle(car1).
vehicle(ego).


#program check(t).

% GOAL RULES:
time(t).

goal1(t) :- time(t), holds(state(car1,loc(S1,L1),dyn(_,_)), t),holds(state(ego,loc(S2,L2),dyn(_,_)), t), L2 < L1.
goal2(t) :- time(t), holds(state(car1,loc(S1,L1),dyn(_,_)), t),holds(state(ego,loc(S2,L2),dyn(_,_)), t), 1 <= (S2 - S1) <= 10.
goal3(t) :- time(t), holds(state(car1,loc(S1,L1),dyn(_,_)), t),holds(state(ego,loc(S2,L2),dyn(_,_)), t), L2 = L1, 5 <= (S2 - S1) <= 10.


 % GOAL ASSERTION:
goal(T1,T2,T3,t) :-  goal1(T1),goal2(T2),goal3(T3), 0 <= T1<=T2<=T3 <= t, t > T3 + 1.
:- query(t), not goal(_,_,_,t).
