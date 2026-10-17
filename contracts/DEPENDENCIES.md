# Fixed dependency graph

Plan `d1ca61a5-59c1-48ad-a8e9-c7b4cb337077`: 36 stages, 48 edges. K and O1 are independent roots. K defines all shared interfaces before dependent implementation. Role 4 selects available R/O work sequentially; no artificial dependency is added between these tracks. Only U/E/B are planned helpers for Z. They may start after I and only under the human-authorized visible-chat workflow.

Backend order: K → A1/A2/A3; A1 → A4; A2/A3/A4 → A5 → A. I integrates A/F/M/R/O and all transitive prerequisites. U/E/B verify I; Z integrates the checked final results. No stage may declare an untested prerequisite successful. Missing trained weights are expected; failed mandatory software/network checks block completion.

```json
{
  "O1": {
    "owner": 4,
    "depends": [],
    "helperFor": null
  },
  "K": {
    "owner": 1,
    "depends": [],
    "helperFor": null
  },
  "A1": {
    "owner": 1,
    "depends": [
      "K"
    ],
    "helperFor": null
  },
  "A2": {
    "owner": 1,
    "depends": [
      "K"
    ],
    "helperFor": null
  },
  "A3": {
    "owner": 1,
    "depends": [
      "K"
    ],
    "helperFor": null
  },
  "A4": {
    "owner": 1,
    "depends": [
      "A1"
    ],
    "helperFor": null
  },
  "A5": {
    "owner": 1,
    "depends": [
      "A2",
      "A3",
      "A4"
    ],
    "helperFor": null
  },
  "A": {
    "owner": 1,
    "depends": [
      "A5"
    ],
    "helperFor": null
  },
  "F1": {
    "owner": 2,
    "depends": [
      "K"
    ],
    "helperFor": null
  },
  "F2": {
    "owner": 2,
    "depends": [
      "F1"
    ],
    "helperFor": null
  },
  "F3": {
    "owner": 2,
    "depends": [
      "F1"
    ],
    "helperFor": null
  },
  "F4": {
    "owner": 2,
    "depends": [
      "F1"
    ],
    "helperFor": null
  },
  "F": {
    "owner": 2,
    "depends": [
      "F2",
      "F3",
      "F4"
    ],
    "helperFor": null
  },
  "D1": {
    "owner": 3,
    "depends": [
      "K"
    ],
    "helperFor": null
  },
  "D2": {
    "owner": 3,
    "depends": [
      "K"
    ],
    "helperFor": null
  },
  "D3": {
    "owner": 3,
    "depends": [
      "K"
    ],
    "helperFor": null
  },
  "D4": {
    "owner": 3,
    "depends": [
      "D3"
    ],
    "helperFor": null
  },
  "D5": {
    "owner": 3,
    "depends": [
      "D2",
      "D4"
    ],
    "helperFor": null
  },
  "D": {
    "owner": 3,
    "depends": [
      "D1",
      "D5"
    ],
    "helperFor": null
  },
  "M1": {
    "owner": 3,
    "depends": [
      "D"
    ],
    "helperFor": null
  },
  "M2": {
    "owner": 3,
    "depends": [
      "M1"
    ],
    "helperFor": null
  },
  "M3": {
    "owner": 3,
    "depends": [
      "M2"
    ],
    "helperFor": null
  },
  "M4": {
    "owner": 3,
    "depends": [
      "M3"
    ],
    "helperFor": null
  },
  "M": {
    "owner": 3,
    "depends": [
      "M4"
    ],
    "helperFor": null
  },
  "R1": {
    "owner": 4,
    "depends": [
      "K"
    ],
    "helperFor": null
  },
  "R2": {
    "owner": 4,
    "depends": [
      "K"
    ],
    "helperFor": null
  },
  "R3": {
    "owner": 4,
    "depends": [
      "R1",
      "R2"
    ],
    "helperFor": null
  },
  "R": {
    "owner": 4,
    "depends": [
      "R3"
    ],
    "helperFor": null
  },
  "O2": {
    "owner": 4,
    "depends": [
      "K"
    ],
    "helperFor": null
  },
  "O3": {
    "owner": 4,
    "depends": [
      "O1",
      "O2"
    ],
    "helperFor": null
  },
  "O": {
    "owner": 4,
    "depends": [
      "O3"
    ],
    "helperFor": null
  },
  "I": {
    "owner": 1,
    "depends": [
      "A",
      "F",
      "M",
      "R",
      "O"
    ],
    "helperFor": null
  },
  "U": {
    "owner": 2,
    "depends": [
      "I"
    ],
    "helperFor": "Z"
  },
  "E": {
    "owner": 3,
    "depends": [
      "I"
    ],
    "helperFor": "Z"
  },
  "B": {
    "owner": 4,
    "depends": [
      "I"
    ],
    "helperFor": "Z"
  },
  "Z": {
    "owner": 1,
    "depends": [
      "U",
      "E",
      "B"
    ],
    "helperFor": null
  }
}
```

Shared ports are in `contracts/python_ports.py`. A1 implements JobRepository; A2 validates/saves inputs; A3 authorizes and provides source-bound media; A4 dispatches outbox and runs one worker; A5 enforces deadlines. M4 supplies ReleaseProvider/TimelineProvider; R supplies RuleEngine; I composes AnalysisRunner and AnalysisBundle. UI consumes only protected HTTP endpoints.
