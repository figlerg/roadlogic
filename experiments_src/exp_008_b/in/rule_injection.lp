#program step(t).

:- holds(state(obstacle, loc(_,_), dyn(VLON,_)),t), VLON !=0.

% this is now also varied in the parameter variation
% #program base.
% init(state(obstacle,loc(20,0),dyn(0,0))).

