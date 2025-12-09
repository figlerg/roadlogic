In here we make two plots of the same ASP plan.

- The original planning and simulation is done in paper/exp_002_e. It takes long because of tough parameters.
- The plan itself is pickled in paper/predicates.pkl. This plan is directly visualized via model_vis.py and the files are in model_vis_plots
- The translated CommonRoad problem is also in paper/exp_002_e, and the relevant files for simulation are copied to paper/scenario.xml and paper/executed_scenario.xml. These two files are used in paper/plot_working_example.py to the picture paper/working-example-new.png. here we visualize the actual simulation, not the plan

NOTE: I put everything into folders for clarity