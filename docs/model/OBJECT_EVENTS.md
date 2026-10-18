# Spatial objects, observable actions and rule probes

Local research authorized by the user after the action-focus stage. Existing
sources, original verdicts and four organizer conflicts are preserved. The same
36 development sources/16 families,4 outer/3 inner folds and seeds42/137/2026
remain fixed. The four previously observed reserved sources do not train or
select anything. Repeated research on this camera is not independent validation.

The existing131 inspected source snapshots now carry30 assistant boxes for green
bags, cups and a loose garment, plus3 appended observable states:cup visible,
cup at mouth,garment on desk. Human approval remains false. Box corrections made
while visually checking coordinate grids are retained as draft review artifacts.
All observations are exact source PTS; no interpolation or verdict changes.
The existing supplied object boxes remain user-reviewed. Their category IDs are
preserved, with descriptive internal names such as cardlike_10/desk_device_4:
neither an ID check nor a machine's successful operation is inferred from a box.

One frozen MobileNetV3-Small ImageNet1K_V1 produces576×14×14 spatial maps from a
448-pixel workspace crop x=[0,1],y=[.18,.67],sampled at the original2fps source PTS.
The experiment explicitly versions this resolution change. The production path
and previous224-pixel experiments are unchanged. Maps are cached as float16 and
loaded as float32 for heads. Brightness1/.85/1.15 and simultaneous featuremap/box
mirroring are train-only augmentations. The baseline semantic classifier exposes
an unvalidated coffee-mug/cup prior. Its1024 hidden neurons are reduced to512 by
publisher-weight norm salience, without dataset labels, to keep the exported
single-CNN/GRU package within the12MiB state budget. It never creates pseudo labels.
Its log-score is centered at the99th percentile of explicitly reviewed cup-negative
training frames and scaled by the99th–90th percentile log gap(min.25). This uses
no validation images or cup-positive labels and remains an unvalidated prior.

Spatial heads learn ten object centers/boxes and18 observable action/state scores.
Object-weighted pooling supplies a576-dimensional frame representation. A small
70→64→576 residual adapter adds predicted object/state/geometry information to
the same single causal GRU256. Spatial training never sees video verdicts; the
subsequent GRU uses action pretraining and verdict/action/pair objectives.
Unsupported action classes remain unknown. Missing classes receive no fabricated
human validation or object-localization metric.

Fixed training:16 spatial epochs at lr.001,40 action-pretraining epochs at lr.001,
80 verdict epochs at lr.0003,dropout.5,weight decay.05. All normalization, support,
class weights, spatial training, action training and thresholds are train/inner
only. Six comparison arms share weights where appropriate:

| Arm | Clip readout |
| --- | --- |
| uniform_gru | Spatial mean plus predicted object metadata,GRU |
| objects_gru | Object-weighted spatial pooling plus metadata,GRU |
| rules_linear | Training-only linear classifier of observable temporal combinations |
| policy_fixed | Maximum of seven predeclared positive visible-condition probes |
| hybrid_linear | Equal mean of object-GRU and rule-linear scores |
| hybrid_fixed | Equal mean of object-GRU and fixed-probe scores |

This yields28 spatial and55 temporal checkpoints,including the final fit; the
linear readout is stored with each temporal fit. Inner selection maximizes
min(accuracy,BA,macro-F1),then accuracy/BA/F1/lower BCE. Primary seed42 and mean of
three seeds are reported with all36 sources. The target is mean accuracy,BA and
macro-F1≥.80; production independence and95% are not established by these data.

Rule probes cover bag/storage/screen after operator departure,cup/mouth,loose
garment,persistent open door,and other temporal combinations. They are scored
experimental observations. The bridge to the real tri-state rule engine keeps
recognizer validation,full visibility,stage completeness,relations and exceptions
unverified. Every normative finding remains unknown. A lit display does not prove
an unlocked OS; a closed safe does not prove locking; an opaque cup does not prove
its contents. No ID/authenticity/posting/key claim is created from missing pixels.

Localization reports top1 box IoU and recall at IoU.5/score.5 on explicitly known
frames,not mAP. State metrics measure agreement with assistant/supplied snapshots,
not dense human event validation. Source-timestamp candidate intervals and rule
diagnostics are experimental and do not bypass the production model-ready gate.

Before the parent experiment finished and before reserved evaluation, a second
readout comparison was preregistered. For weighted BCE with positive weight w,
the ideal conditional optimum satisfies q=wp/(wp+1-p); the inverse is
p=sigmoid(logit(q)-log(w)). This is a mathematical ablation, not proof that a finite
network is calibrated. [PyTorch documents the precision/recall effect of pos_weight](https://docs.pytorch.org/docs/stable/generated/torch.nn.BCEWithLogitsLoss.html).
Four posterior-rule variants are compared with the original six arms,using the
same inner-only selection. Weights are reconstructed from the exact training
action masks; unsupported classes remain unknown. Spatial/GRU weights are reused
unchanged. The corrected linear head uses150 zero-initialized AdamW steps,
lr.01,weight decay1,train-only normalization. A final object-mode neural fit is
created separately only if the parent final mode lacks it. All decisions freeze
before the four previously observed reserved sources are evaluated.
