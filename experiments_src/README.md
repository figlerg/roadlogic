different specs are in 
- 1 follow (both switch lane)
- 2 overtake
- 3 overtake with 3rd unconstrained actor
- 4 overtake with fixed lane
- 5 overtake, but there is a static obstacle on the road
- 6 two cares, one changes to left lane
- 7 deprecated, moved to 1d
- 8 drive past static obstacle

explanations to the naming:
- no suffix means that we run the vanilla pipeline. I take low N because the plans don't vary at all here 
- the suffix "b" means that I run the partitioning experiment
- the suffix "c" means that I run the partitioning experiment with the rule injection for car1. I leave out those experiments where car1 absolutely needs to change lane. this makes exp_004 a bit obsolete, I just leave it here to have also the vanilla case + fixed lane
- the suffix "d" means that I use the heuristic BASIC during creation to increase diversity