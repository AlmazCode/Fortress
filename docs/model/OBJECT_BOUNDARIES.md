# Dense object boundary research

This local stage follows the user's instruction to refine safe opening/closing
and bag movement/placement on the same videos,then retrain and evaluate. It does
not replace the production release or its readiness gate.

The assistant reviewed all2464 exact2fps development snapshots and446 additional
fine-window observations near visible transitions. Fine observations may overlap
the2fps observations;they are not446 new independent examples. The separate
hashed overlay supplies safe_open,green_bag_visible,bag_held_or_manipulated and
bag_on_worktop. Original exact operator/person labels are retained with reviewed
departure corrections for the relevant bag/safe clips. Twenty-three observed
transition brackets bind their endpoints to actual source PTS. Their uncertainty
is retained rather than inventing a sub-frame instant. Human approval is false.

Bag handling includes visible carrying,holding and active hand manipulation;it
does not establish instantaneous velocity. Worktop support can overlap handling.
Occluded bag support and movements below the desk remain unknown. A gray safe
door may stay open after reaching ends;open state persists while it remains
visibly open. Closed appearance does not establish locking. A bag remaining
after a customer leaves while the operator stays is distinguished from a bag
remaining after the operator leaves. Neither establishes ownership or a rule.
Original clip verdicts,organizer conflicts,source bytes and earlier overlays
remain immutable. Four previously observed internal controls are never annotated
or trained on in this stage.

Inputs reuse the same frozen448px workspace CNN maps and2fps PTS. Fixed canvas
regions provide2×2 context averages,one right-side safe region and one worktop
region. Color summaries add28 regional features and19 green-bag descriptors:
3503 values per frame. These regions never read supplied validation boxes or
source identifiers at inference. Provided boxes enlarged the review images only.

A32-channel causal convolution block learns six frame states and a clip score.
It uses two left-padded kernel3 layers with dilations1/2;per-frame LayerNorm
does not inspect future frames. Padding is excluded from clip pooling and loss.
Source-balanced training moments,known-state masks,class/source-balanced losses
and3× transition-neighbor weights use training sources only. Unsupported classes
have no auxiliary gradient and retain unknown status. Epoch count220,AdamW
learning rate.003,weight decay.01,dropout.15,feature noise.01,auxiliary loss2×,
same-family opposite-verdict contrast.1× and boundary readout ridge alpha10 are
fixed before evaluation. No outer/control early stopping or threshold tuning.

Five predeclared alternatives share each trained block:its clip head,a ridge
readout of predicted state changes,their separate equal means with the exact
training-source uniform GRU,and the already measured uniform-GRU control.
The original4outer/3inner family partitions and seeds42/137/2026 are unchanged.
Seed42 inner folds choose the alternative and threshold using the existing
min(accuracy,balanced accuracy,macro-F1) rank. Outer seeds measure sensitivity.
Identical control results are not a new gain from object boundaries.

Exploratory frame metrics use threshold.5 on explicitly known observations.
Physical event evaluation requires two consecutive observations to confirm a
state change,records the first changed PTS and confirmation latency,and matches
assistant transition brackets within.5seconds. Predictions adjacent to unknown
coarse states are unscored unless a fine observed bracket supports that event.
Event precision/recall/F1 and unsupported events are reported separately from
clip accuracy. Repeated development on the same small camera dataset is not an
independent test and cannot establish stable95% generalization.

Artifacts,media,evidence,weights and exact source IDs remain outside Git.
Software tests are separate from real training/evaluation. Normative rule
statuses remain unknown until the required recognizer/visibility/relationship/
policy conditions are established.

The first completed temporal comparison is preserved with its negative quality
result. A separate magnified-crop comparison retains the same labels and splits.
It reuses the single frozen CNN for two fixed224px crops in displayed source
coordinates:safe(.50,.27,1,.60),worktop(0,.30,.95,.67). Crops do not use supplied
validation boxes. Each crop supplies576 CNN values and384 RGB grid statistics.
Safe features include change from the first up-to-three observed frames;the
prefix baseline is causal and never reads a later frame. Bag features include
green appearance and geometry. Source-balanced ridge heads learn only frame
labels,with fixed alphas10/.1/10/10. Clip verdict labels do not train these heads.
The original exact-training spatial context supplies operator/person states.
Unsupported context contributes zero features and unknown output.

A separate ridge alpha10 reads predicted state summaries. Three alternatives
are predeclared:that readout,its equal mean with the exact-training uniform GRU,
and the old GRU control. Only GRU seed sensitivity varies;deterministic state
fits are not three independent confirmations. The complete portable package
retains one CNN,one GRU,all reference/object heads and all new state/readout
parameters. Both tensor storage and serialized file length must fit12,000,000
bytes. Source hashes,PTS,code hashes and raw/cache verdict parity are checked.

```powershell
python -B -m ml.boundary_roi_infer export --experiment <completed-directory> --reference-bundle <uniform-reference-bundle> --output <new-bundle>
python -B -m ml.boundary_roi_infer infer --bundle <new-bundle> --video <local-mov> --device cuda
```

The earlier reference has a known CPU/CUDA numerical discrepancy beyond its
fixed.001 score tolerance. CPU execution alone does not establish score parity.
The latest measured limits belong in OBJECT_BOUNDARIES_RESULTS.json;neither
the full42-source training-inclusive accuracy nor software tests replace the
nested family evaluation.
