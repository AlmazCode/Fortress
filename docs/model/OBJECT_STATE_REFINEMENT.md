# Refining object states and false alarms on the existing sources

The user authorized further local training and assistant annotation on the same
videos. Original source bytes and clip verdicts remain immutable. The benchmark
still uses36 development sources,16 families,the same4 outer/3 inner folds,and
seeds42/137/2026. Four previously observed internal holdout sources never train
or select a model. Repeated research on these cameras is not an independent test.

The new review covers240 exact source snapshots from20 development videos. It
appends green_bag_visible and screen_bright_content to the18 existing states.
Sixteen illuminated dark-blue screen images correct earlier assistant labels
that incorrectly treated dark imagery as an unlit display. The old annotation
file is preserved; corrections and new labels live in a separate hashed review.
Closed,occluded and back-facing displays remain unknown. Human approval is false.
Bright content is an appearance class and does not establish OS lock state.

Position/color inputs retain the frozen MobileNetV3-Small448px workspace maps:
4×4 pooled576-channel features plus14×14 RGB means,spreads and edge magnitudes,
10588 values per source frame. Source PTS and2fps sampling are unchanged. The
first comparison uses source-balanced weighted ridge state heads,hard negatives,
train-family contrast pairs and regularized clip readouts. Its failed quality
result is preserved rather than replacing the earlier candidate.

Object ROI comparisons retain original exact-training spatial context for
actions,operator and person,while learning safe/laptop boxes and object state
heads separately. A missing object in an inner training fold disables dependent
states and probes; it never supplies a fabricated negative or positive.
The first ROI run stopped on this condition; its partial fits and source snapshot
are retained separately. The repaired run has its own protocol and output folder.

The final local-object comparison uses camera geometry anchors learned only from
provided training boxes. Source identifiers are not inference inputs. Background
color layout in the first three sampled frames selects a training geometry
anchor; median training boxes provide the ROI. This initializes camera geometry
from roughly the first second and does not claim streaming causality for that
initialization. The reused GRU remains causal. Safe state crops expand leftwards
to include the moving door. A19-value color/chroma descriptor makes bag presence
translation invariant. Explicit known-negative pixels are sampled across the
whole workspace. The exact-training positional door head is reused; other
validated software context paths remain unchanged. All recognizers remain
experimentally evaluated rather than human accepted.

Fixed ridge parameters:state alpha10 in the first comparison; object appearance
alpha1; bag pixel alpha1; bag-color presence alpha.1. Hard negatives receive2×
weight for states and3× for bag patches. Normalization,source weighting,support,
geometry anchors,classifiers and thresholds are fitted on their own training
sources. Unlabeled frames do not become negatives.

Before each parent ROI comparison completed,and before this stage evaluated the
internal holdout,a17-candidate state-only/GRU comparison was preregistered. It
compares the original uniform-GRU control,states and persistent probes,and fixed
equal-weight ensembles. Readout alpha is.1/1/10; the same inner selection rank
maximizes min(accuracy,balanced accuracy,macro-F1),then those metrics and lower
BCE. A missing final all-development fit is created in a separate directory.
Completed parent fits,thresholds and reports are preserved. Ridge heads are
deterministic; only the frozen reference GRU varies by seed in these ensembles.
Equal deterministic results are not independent stochastic confirmations.

A real-source check identified a semantic departure defect:constant uncertain
operator scores could satisfy a soft absence term without an observed departure.
A separately preregistered correction requires a fall in presence evidence and
distinguishes object-state change from its initial appearance. Three alternatives
are compared:the transition probes,their equal mean with the exact-training
uniform GRU,and that GRU control. Object heads remain frozen. Internal-control
results from the preceding comparison do not select this correction;those
controls were already observed in earlier stages and remain non-independent.
No new target verdict is introduced.

The new probes exclude the unvalidated ImageNet cup prior. A reference GRU still
has its original trained metadata; this is explicit in the package. The final
bag probe requires visible bag evidence and observed operator/person departure;
it does not assert ownership,contents or a legal violation. The real tri-state
engine retains unknown until recognizer validation,visibility,interval
completeness,relations,exceptions and applicable policy are established.

The local package includes the entire single CNN,single GRU,context heads,ROI
heads,anchors,normalization and readout. The budget is12,000,000 tensor bytes;
training checkpoints and serialization overhead are reported separately.
Export clones tensor views into compact storage. An earlier export correctly
failed the serialized-size guard because a sliced head retained a larger backing
storage;that failed artifact is preserved and never promoted. Tensor values and
all training decisions remain unchanged. File length and SHA are checked on load.
State scores are ranking scores rather than calibrated probabilities. Object
ROIs and candidate event intervals are not human-validated evidence of a rule.
The production loader/default weights/model-ready gate are unchanged.

```powershell
python -B -m ml.object_state_infer export --experiment <completed-consensus-directory> --output <new-local-bundle>
python -B -m ml.object_state_infer infer --bundle <local-bundle> --video <local-mov> --device cuda
```

`--device cpu` selects CPU inference. Runtime needs the code and exported bundle;
it does not load annotation files or dataset caches. New output directories are
not silently overwritten. Aggregate measurements and quality limitations belong
in [OBJECT_STATE_REFINEMENT_RESULTS.json](OBJECT_STATE_REFINEMENT_RESULTS.json).
