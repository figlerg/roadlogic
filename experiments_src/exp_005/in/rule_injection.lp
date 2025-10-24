#program step(t).

:- holds(state(car2, loc(_,_), dyn(VLON,_)),t), VLON !=0.


#program base.
init(state(car2,loc(20,0),dyn(0,0))).

