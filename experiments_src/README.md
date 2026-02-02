different specs are in 
- 1 follow (both switch lane)
- 2 overtake
- 3 overtake with 3rd unconstrained actor
- 4 overtake with fixed lane
- 5 overtake, but there is a static obstacle on the road
- 6 two cares, one changes to left lane
- 7 drive past static obstacle

explanations to the naming:
- no suffix means that we run the vanilla pipeline. I take low N because the plans don't vary at all here. This is the **"base"** variant of the paper.
- the suffix "b" means that I run the partitioning experiment. This is the **"refined"** variant of the paper.