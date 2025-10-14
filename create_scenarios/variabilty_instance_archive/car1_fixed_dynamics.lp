% simplest version of fixing car1. all versions in create_scenarios/variabilty_instance_archive/car1_fixed_dynamics_history.lp


#program step(t).

:- occurs(change_dynamics(V,_,VLAT),t), V=car1, VLAT != 0.




