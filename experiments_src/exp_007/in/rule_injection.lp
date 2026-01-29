#program step(t).

:- holds(state(obstacle, loc(_,_), dyn(VLON,_)),t), VLON !=0.


#program base.
init(state(obstacle,loc(20,2),dyn(0,0))).

