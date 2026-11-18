# misc
This folder is used for cleanup, storing extra files that are not referenced in main code base. Example files that go into this folder are: extra documentation, brainstorm notes, discussions, legacy static files. 

misc/
├── demo_eval_examples/
│   ├── demo_generations.jsonl : legacy code generation examples NOTE: consider for deletion.
│   └── demo_results.csv : legacy evaluation results by running run_eval.py. NOTE: consider for deletion.
├── run_eval.py : deprecated qc_eval package component used for evaluating code with static checks. 
├── FRAGMENT_EXPERIMENT.md : brainstorm notes for researching fragmented code generation vs entire algorithm.
└── prompts.jsonl : legacy prompts for code templates, 25 prompts. NOTE: consider for deletion.