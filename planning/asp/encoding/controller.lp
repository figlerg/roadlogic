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
        holds(state(V, loc(_,_), dyn(Vel_lon2, _)), t-1),
        Vel_lat!=0, Vel_lon2 - Vel_lon > max_braking_speed_while_turning. 

    % turning and accelerating together should be limited
    :- holds(state(V, loc(_,_), dyn(Vel_lon, Vel_lat)), t), 
        holds(state(V, loc(_,_), dyn(Vel_lon2, _)), t-1),
        Vel_lat!=0, Vel_lon2 - Vel_lon < max_acceleration_while_turning. 