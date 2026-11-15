% create_scenarios/controller.lp with the two constants the paper's variability experiments sample
% turned into choices, made once per plan: braking and acceleration while turning, over the same values
% create_variability_instances.py draws from (default -2 .. default +1). The start gap is already a
% choice in every instance. So one clingo Control covers the whole space the paper sampled, and the
% diversity methods in diverse.py can move through it without restarting.

#program base.
1 { brake_turn(B) : B = 2..5 } 1.
1 { accel_turn(A) : A = 0..2 } 1.

% this file is a manually created file encoding various rules which depend on the controller (in this case Commonroad)



#program check(t).

    % this stops low velocity lane changes as they are known to cause problems (if an actor cannot make the sharp turn, it dies)
    :- holds(state(_, loc(_,_), dyn(Vel_lon, Vel_lat)), t), 
        Vel_lat!=0, Vel_lon < min_change_speed.

    % big values are also problematic
    :- holds(state(_, loc(_,_), dyn(Vel_lon, Vel_lat)), t), 
        Vel_lat!=0, Vel_lon > max_change_speed.

    % turning and braking together should be limited
    :- holds(state(V, loc(_,_), dyn(Vel_lon, Vel_lat)), t), 
        holds(state(V, loc(_,_), dyn(Vel_lon2, _)), t-1), time(t-1),
        Vel_lat!=0, brake_turn(B), Vel_lon2 - Vel_lon > B. 

    % turning and accelerating together should be limited
    :- holds(state(V, loc(_,_), dyn(Vel_lon, Vel_lat)), t), 
        holds(state(V, loc(_,_), dyn(Vel_lon2, _)), t-1), time(t-1),
        Vel_lat!=0, accel_turn(A), Vel_lon2 - Vel_lon < A. 