Trials per task per arm: 10. Cells show passes/trials (rate) [95% Wilson interval].

### Held-out tests (headline: the agent never sees these)

| Task | Baseline (one shot) | Python harness | Swift harness |
|---|---|---|---|
| add-function (dev) | 10/10 (100%) [72%-100%] | 10/10 (100%) [72%-100%] | 6/10 (60%) [31%-83%] |
| create-roman (fresh) | 10/10 (100%) [72%-100%] | 10/10 (100%) [72%-100%] | 9/10 (90%) [60%-98%] |
| create-slugify (dev) | 1/10 (10%) [2%-40%] | 1/10 (10%) [2%-40%] | 0/10 (0%) [0%-28%] |
| fix-chunk (fresh) | 10/10 (100%) [72%-100%] | 10/10 (100%) [72%-100%] | 10/10 (100%) [72%-100%] |
| fix-large (scale) | 0/10 (0%) [0%-28%] | 7/10 (70%) [40%-89%] | 7/10 (70%) [40%-89%] |
| fix-one-bug (dev) | 10/10 (100%) [72%-100%] | 9/10 (90%) [60%-98%] | 10/10 (100%) [72%-100%] |
| fix-stats (dev) | 10/10 (100%) [72%-100%] | 10/10 (100%) [72%-100%] | 10/10 (100%) [72%-100%] |
| fizzbuzz (dev) | 8/10 (80%) [49%-94%] | 10/10 (100%) [72%-100%] | 10/10 (100%) [72%-100%] |
| Dev tasks (harness was tuned on these) | 39/50 (78%) [65%-87%] | 40/50 (80%) [67%-89%] | 36/50 (72%) [58%-83%] |
| Fresh tasks (written after tuning, never used to tune) | 20/20 (100%) [84%-100%] | 20/20 (100%) [84%-100%] | 19/20 (95%) [76%-99%] |
| Scale task (file too big for a one-shot rewrite) | 0/10 (0%) [0%-28%] | 7/10 (70%) [40%-89%] | 7/10 (70%) [40%-89%] |
| All small tasks (everything except scale) | 59/70 (84%) [74%-91%] | 60/70 (86%) [76%-92%] | 55/70 (79%) [68%-87%] |
| **All tasks** | **59/80 (74%) [63%-82%]** | **67/80 (84%) [74%-90%]** | **62/80 (78%) [67%-85%]** |

### Visible check (the tests the agent is given and optimizes against)

| Task | Baseline (one shot) | Python harness | Swift harness |
|---|---|---|---|
| add-function (dev) | 10/10 (100%) [72%-100%] | 10/10 (100%) [72%-100%] | 6/10 (60%) [31%-83%] |
| create-roman (fresh) | 10/10 (100%) [72%-100%] | 10/10 (100%) [72%-100%] | 9/10 (90%) [60%-98%] |
| create-slugify (dev) | 9/10 (90%) [60%-98%] | 10/10 (100%) [72%-100%] | 8/10 (80%) [49%-94%] |
| fix-chunk (fresh) | 10/10 (100%) [72%-100%] | 10/10 (100%) [72%-100%] | 10/10 (100%) [72%-100%] |
| fix-large (scale) | 0/10 (0%) [0%-28%] | 10/10 (100%) [72%-100%] | 8/10 (80%) [49%-94%] |
| fix-one-bug (dev) | 10/10 (100%) [72%-100%] | 10/10 (100%) [72%-100%] | 10/10 (100%) [72%-100%] |
| fix-stats (dev) | 10/10 (100%) [72%-100%] | 10/10 (100%) [72%-100%] | 10/10 (100%) [72%-100%] |
| fizzbuzz (dev) | 8/10 (80%) [49%-94%] | 10/10 (100%) [72%-100%] | 10/10 (100%) [72%-100%] |
| Dev tasks (harness was tuned on these) | 47/50 (94%) [84%-98%] | 50/50 (100%) [93%-100%] | 44/50 (88%) [76%-94%] |
| Fresh tasks (written after tuning, never used to tune) | 20/20 (100%) [84%-100%] | 20/20 (100%) [84%-100%] | 19/20 (95%) [76%-99%] |
| Scale task (file too big for a one-shot rewrite) | 0/10 (0%) [0%-28%] | 10/10 (100%) [72%-100%] | 8/10 (80%) [49%-94%] |
| All small tasks (everything except scale) | 67/70 (96%) [88%-99%] | 70/70 (100%) [95%-100%] | 63/70 (90%) [81%-95%] |
| **All tasks** | **67/80 (84%) [74%-90%]** | **80/80 (100%) [95%-100%]** | **71/80 (89%) [80%-94%]** |

### Cost and failure modes

| Arm | Median time / trial | Median tool calls | Timeouts | Pass visible, fail hidden |
|---|---|---|---|---|
| Baseline (one shot) | 3s | 1 | 0/80 | 8/80 |
| Python harness | 6s | 2 | 0/80 | 13/80 |
| Swift harness | 7s | 3 | 7/80 | 9/80 |

Environment: Apple M2 Pro, 16 GB, macOS 27.0.1, Python 3.14.2, Apple Swift version 6.4 (swiftlang-6.4.0.34.1 clang-2100.3.34.1). Run date: 2026-10-24.
