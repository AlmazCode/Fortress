# Workspace crops and action-first training

User-authorized local research following the action-refinement experiment. This
experiment keeps the single MobileNetV3-Small ImageNet1K_V1 and single causal
GRU256. It does not provide a trained production event/rules release.

All36 development videos now have assistant snapshot observations:1537 inspected
source frames, the original11 action/state classes and4 additional visible states
(laptop lid open, illuminated screen, glass door open, two people at the counter).
The first11 observations on the previous15 sources are preserved. Screen lighting
does not establish OS lock; closed storage does not establish a locked safe.
Evidence, source PTS, hashes, local paths and original verdict conflicts remain
bound to their source. Unknowns contribute no loss and are not interpolated.
Annotations, images, source videos and weights remain outside Git.

The fixed displayed-image crop is x=[0,1],y=[.18,.67], before the existing224 RGB
letterbox/ImageNet normalization. It keeps the workstation and storage while
reducing foreground floor/table pixels. Actual indexed source PTS are sampled at
4fps; existing2fps PTS must be an exact subset. Frozen CNN prefixes include base,
.85 and1.15 brightness variants; variants are used only in training. Held-out
features always use the unmodified image. Caches bind preprocessing, source,
partition, encoder and byte hashes and never contain reserved sources.

Six arms are declared before fitting:

| Arm | Input | Training |
| --- | --- | --- |
| global_joint | Existing averaged full/top/bottom2fps | Verdict + action/object auxiliary losses |
| roi_joint | Workspace2fps | Same joint objective |
| roi_pretrain | Workspace2fps | Action/object clip pretraining, then joint training |
| roi_action_bottleneck | Workspace2fps | Action pretraining; freeze GRU/action heads; verdict uses predicted action/object temporal statistics only |
| roi_finetune_pair | Workspace2fps | Last2 CNN blocks trained on action/object frames; action clip pretraining; joint verdict with training-family pair loss |
| roi4_finetune_pair | Workspace4fps | Same stages, doubled temporal sampling |

One fixed configuration avoids a large hyperparameter search:60 verdict epochs,
AdamW lr.0003,dropout.5,weight decay.05;40 clip-pretraining epochs at lr.001;
6 CNN adaptation epochs at lr.0001 with BatchNorm statistics frozen. CNN frame
pretraining never sees video verdicts. Clip windows contain32frames at2fps or64
at4fps, selected within individual training sources; no video verdict is copied
to clips. Half of windows preferentially include a known positive action.
The first7 action classes have unit auxiliary weight; visible-state classes have
.25 weight. Joint video/action/object/pair weights are1/.3/.15/.2. Pair loss
compares opposite verdicts only inside the same training family. Unsupported
auxiliary classes are disabled using training support alone.

The original4 outer/3 inner family folds and three seeds42/137/2026 are fixed.
Primary seed42;163 fits including final model. Normalization, class weights,
pretraining, CNN adaptation and thresholds use training/inner folds only. Inner
selection maximizes min(accuracy,balanced_accuracy,macro-F1), then accuracy,BA,F1,
then lower BCE. The primary estimate is nested selection across outer folds;
individual best-arm results are also reported with selection bias disclosed.
The final decision is frozen on36 development sources before the4 previously
observed internal holdout videos are decoded. This is exploratory same-camera
evaluation, not a new independent test. Reaching29/36 accuracy alone does not
establish80% across all product metrics or95% production performance.

Entry points: `python -m ml.action_focus_inputs`, `python -m ml.action_focus
prepare`, `run`, `evaluate-reserved`. Required paths and weights are supplied
explicitly. Protocols and checkpoints are immutable once fitted; changes require
a new experiment directory. Production readiness gates and default model are
unchanged.

The separate `python -m ml.action_focus_infer export` command creates an experimental
bundle containing only the selected CNN features, GRU/heads and normalization,
with source/protocol/fit hashes. An adapted suffix is folded into the single CNN;
the unused ImageNet classifier and training data are omitted. The bundle checks
its byte hash and remains below12MiB of model tensors. Run it without the dataset:

```powershell
python -m ml.action_focus_infer infer --bundle <local-bundle> --video <local.mov>
```

The JSON contains the clip score, threshold, source PTS, supported action scores
and elapsed analysis time. Unknown/unsupported action classes are null. Scores
do not claim validated event intervals or a production-ready normative verdict.
