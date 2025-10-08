%%%   TEST INPUT OVERTAKE   %%%
holds(on(ego,0,0), 0).
:- not same_lane(ego, car1, 0).
:- not ahead_of(car1, ego, 0).


%% ORIGINAL GOAL WITHOUT INTERMEDIATES
%goal :- same_lane(ego,car1,T), ahead_of(ego,car1,T).
%:- not goal.

% these fire only for one time point each
1 {time_goal1(T) : time(T)} 1.
1 {time_goal2(T) : time(T)} 1.
1 {time_goal3(T) : time(T)} 1.

% they are in the correct order
T1 <= T2 :- time_goal1(T1), time_goal2(T2).
T2 <= T3 :- time_goal2(T2), time_goal3(T3).

% last goal coincides with chosen plan_length
T1 == T2 :- time_goal3(T1), chosen_plan_length(T2).

% goal definition
% not that T1, T2,... is just for the reader, by itself this variable is not linked to other occurrences of T{i}.
%  that is done by the predicates 'time_goal'.
goal1 :- left_of(ego,car1,T1), time_goal1(T1).
%goal2 :- left_of(ego,car1,T2), ahead_of(ego,car1,T2), time_goal2(T2).
%goal3 :- same_lane(ego,car1,T3), ahead_of(ego,car1,T3), time_goal3(T3). # TODO this was just a small test, actually I need rules like below. This is done in the automated version
goal2 :- left_of(ego,car1,T2), holds(on(ego,_,S),T2),holds(on(car1,_,S2),T2), S - S2 <= -10, S - S2 >= -20.
goal3:- ...


% these two get me the 'standard' overtake maneuver instead of all the weird ones. TODO not sure how to get the fast lane change working in scenic
%goal3 :- same_lane(ego,car1,T3), ahead_of(ego,car1,T3), time_goal3(T3), holds(on(ego,0,_), T3). % for debugging, should be possible
%1 {holds(on(car1,0,S), T) : segment(S)} 1 :- time(T).

goal :- goal1, goal2, goal3.

:- not goal.
