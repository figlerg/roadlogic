

% INITIAL SETUP FACTS:

#program base.

init(state(ego,loc(0,0),dyn(1,0))).
1 { init(state(car1, loc(S1, L1), dyn(1,0))) : segment(S1),lane(L1), -20 <= (S2 - S1) <= -10, L2 = L1 } 1 
	:- init(state(ego, loc(S2, L2), dyn(1,0))).

vehicle(car1).
vehicle(ego).




#program check(t). % GOAL ASSERTION: :- query(t), not goal3(t).


goal1(t) :- goal1(t-1). 
goal1(t) :- holds(state(ego, loc(_,L1), dyn(_,_)), t), holds(state(car1, loc(_,L2), dyn(_,_)), t), L1 < L2. 
goal2(t) :- goal2(t-1). 
goal2(t) :- goal1(t), holds(state(ego, loc(S1,_), dyn(_,_)), t), holds(state(car1, loc(S2,_), dyn(_,_)), t), 1 <= (S1 - S2) <= 10. 
goal3(t) :- goal2(t), holds(state(ego, loc(S1,L1), dyn(_,_)), t), holds(state(car1, loc(S2,L2), dyn(_,_)), t), 5 <= (S1 - S2) <= 10, L1 = L2, t>8.


 % GOAL ASSERTION:
:- query(t), not goal3(t).