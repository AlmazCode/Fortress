"""Weak temporal operation supervision on original development videos only.

Imported intervals describe an operation, not legal violations. Unknown frames
are ignored, uncertain edges are ignored, simultaneous labels share target mass.
All normalizers, class support and thresholds are fitted inside the train fold.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import time

import numpy as np
import torch
from torch import nn
from torch.nn.utils.rnn import pack_padded_sequence, pad_packed_sequence, pad_sequence

from ml.data.annotation_tasks import read_json
from ml.data.deduplicate import stable_hash
from ml.models.encoder import file_sha256
from ml.video_baseline import atomic_checkpoint, atomic_json, metrics
from ml.small_data import summarize
from ml import object_event_inputs as spatial

VERSION = 'temporal-operations-v1'
SEEDS = (42, 137, 2026)
ARMS = ('clip_only', 'temporal_actions')
CONFIG = {'epochs': 80, 'lr': .0005, 'weight_decay': .05, 'dropout': .5, 'hidden': 192}
MAPPING = {
    'cash_exchange': ('receive_cash', 'give_cash'),
    'cash_handling': ('manual_count_cash', 'handle_cash', 'bundle_cash', 'count_cash', 'inspect_rejected_banknotes'),
    'cash_device_operation': ('machine_count_cash', 'load_cash_counter', 'take_cash_from_counter', 'validate_banknotes'),
    'document_exchange': ('receive_id', 'return_id'),
    'document_inspection': ('inspect_id',),
    'safe_opening': ('open_safe',), 'safe_closing': ('close_safe',),
    'storage_transfer': ('store_cash', 'take_cash_from_safe', 'store_journal', 'store_stamp'),
    'bag_handling': ('open_cash_bag', 'remove_cash_from_bag', 'close_cash_bag', 'handle_cash_bag', 'receive_cash_bag'),
    'computer_use': ('use_laptop',),
    'workplace_arrival': ('enter_workplace',), 'workplace_departure': ('leave_workplace',),
}
TAXONOMY = ('other_annotated_operation', *MAPPING)
COARSE = ('flat_item_handling', 'counter_interaction', 'computer_interaction', 'storage_interaction',
          'bag_interaction', 'door_interaction', 'writing', 'operator_at_station', 'person_at_counter',
          'storage_open', 'bag_on_desk', 'laptop_open', 'laptop_screen_lit', 'glass_door_open', 'two_people_at_counter')
DIM = 576*5
MAX_BYTES = 12_000_000


def code_hash():
    return stable_hash({name: hashlib.sha256((Path(__file__).parent/name).read_text(encoding='utf-8-sig').encode()).hexdigest()
                        for name in ('temporal_actions.py', 'object_event_inputs.py', 'data/pts_index.py', 'data/scenes.py')})


def features(maps):
    """No learned spatial heads: frozen ImageNet maps, global and 2x2 pools."""
    if maps.ndim != 4 or maps.shape[1:] != (576,14,14) or not torch.isfinite(maps).all():
        raise ValueError('Invalid frozen source maps')
    return torch.cat((maps.mean((-2,-1)), nn.functional.adaptive_avg_pool2d(maps,(2,2)).flatten(1)),1)


def operation_targets(records, times):
    """Categorical weak labels only inside supplied cashier-operation interiors.

    Outside supplied intervals there is no target. This does not declare every
    other frame a negative. Exact actor IDs are not inputs to the network.
    """
    target = torch.zeros(len(times),len(TAXONOMY))
    reverse = {alias: n for n, aliases in enumerate(MAPPING.values(),1) for alias in aliases}
    for record in records:
        weak = record.get('weak_source_record', {})
        if (weak.get('label_kind') != 'observable_action' or weak.get('actor_role') != 'cashier'
                or weak.get('known') is not True or weak.get('reviewed') is not True):
            continue
        start, end = record['start_sec'], record['end_sec']
        if not 0 <= start < end or not np.isfinite([start,end]).all():raise ValueError('Invalid weak interval')
        # At least one source-sampled interior for short actions, never extrapolate.
        margin = min(float(weak.get('boundary_uncertainty_sec',1.)), (end-start)*.2)
        selected = [n for n,t in enumerate(times) if start+margin <= t <= end-margin]
        c = reverse.get(record['event_type'].removeprefix('action.'),0)
        target[selected,c] = 1.
    mass = target.sum(1,keepdim=True)
    return target/mass.clamp_min(1)


def prepare(root, output):
    root, output = Path(root), Path(output)
    parent = read_json(root/'object-stage-v2/protocol.json')
    marker = read_json(root/'spatial-inputs-v2/inputs.json')
    labels = {v['video_id']:v for v in read_json(root/'prepared/labels.json')['videos']}
    review = read_json(root/'action-review-v2/assistant_focus.v1.json')
    if marker['version'] != spatial.VERSION or marker['code_sha256'] != spatial.code_hash() or review['taxonomy'] != list(COARSE):
        raise ValueError('Frozen features/review lineage changed')
    development = parent['development_ids']
    if set(development) & set(parent['reserved_ids']):raise ValueError('Reserved source in development')
    original = read_json(root/'prepared/actions.json')['records']
    reviews = {v['video_id']:v for v in review['videos']}
    entries = {v['video_id']:v for v in marker['entries']}
    output.mkdir(parents=True,exist_ok=False)
    (output/'inputs').mkdir()
    counts = {}
    for video in development:
        entry, label, inspected = entries[video], labels[video], reviews[video]
        if entry['source_sha256'] != label['source_sha256'] or inspected['source_sha256'] != label['source_sha256']:
            raise ValueError('Source identity changed')
        index = read_json(root/'prepared/indices'/(video+'.json'))
        timing = {f['source_pts']:f['timestamp_sec'] for f in index['frames']}
        times = [timing[p] for p in entry['source_pts']]
        records = [r for r in original if r['video_id']==video]
        if any(r['source_sha256'] != label['source_sha256'] for r in records):raise ValueError('Foreign weak annotation')
        fine = operation_targets(records,times)
        by_pts = {o['source_pts']:o for o in inspected['observations']}
        coarse = torch.full((len(times),len(COARSE)),-1.)
        for n, point in enumerate(entry['source_pts']):
            if point in by_pts:
                if abs(by_pts[point]['timestamp_sec']-times[n])>1e-7:raise ValueError('Review PTS mismatch')
                coarse[n] = torch.tensor(by_pts[point]['values'])
        values = []
        for item in entry['files'][:3]:
            path = root/'spatial-inputs-v2'/item['path']
            if file_sha256(path) != item['sha256']:raise ValueError('Frozen spatial cache changed')
            maps = np.load(path,mmap_mode='r',allow_pickle=False)
            if maps.shape != (len(times),576,14,14) or maps.dtype != np.float16:raise ValueError('Frozen map shape/PTS mismatch')
            values.append(torch.cat([features(torch.from_numpy(np.array(maps[n:n+16],dtype=np.float32)))
                                     for n in range(0,len(maps),16)]))
        payload = {'video_id':video, 'group_id':entry['group_id'], 'source_sha256':label['source_sha256'],
                   'target':entry['target'], 'times':times,
                   'source_pts':entry['source_pts'], 'features':torch.stack(values), 'coarse':coarse, 'fine':fine}
        path = output/'inputs'/(video+'.pt')
        atomic_checkpoint(path,payload)
        counts[video] = {'sha256':file_sha256(path), 'fine_frames':int((fine.sum(1)>0).sum()),
                         'fine_class_frames':(fine>0).sum(0).tolist(),'coarse_known':int((coarse>=0).sum())}
        print(json.dumps({'prepared':video,'fine_frames':counts[video]['fine_frames']}),flush=True)
    reference = read_json(root/'transition-state-stage-v1/cv_report.json')['comparisons']['legacy_uniform']
    control = {k:float(np.mean([reference[str(seed)][k] for seed in SEEDS]))
               for k in ('accuracy','balanced_accuracy','macro_f1')}
    binding = {str(path.relative_to(root)):file_sha256(path) for path in
               (root/'prepared/actions.json',root/'prepared/labels.json',root/'action-review-v2/assistant_focus.v1.json',
                root/'spatial-inputs-v2/inputs.json',root/'transition-state-stage-v1/cv_report.json')}
    plan = {'version':VERSION,'code_sha256':code_hash(),'root':str(root.resolve()),'binding':binding,
            'development_ids':development,'reserved_ids':parent['reserved_ids'],'folds':parent['folds'],'final_inner':parent['final_inner'],
            'taxonomy':list(TAXONOMY),'mapping':MAPPING,'coarse':list(COARSE),'config':CONFIG,'arms':ARMS,'seeds':SEEDS,
            'encoder_weights':marker['encoder_weights'],'encoder_sha256':marker['encoder_sha256'],'inputs':counts,
            'supervision':'assistant coarse exact PTS + imported weak cashier-operation interiors; unknowns ignored; no legal labels',
            'support':'fine class requires >=2 training families and >=3 frames; unsupported classes stay unavailable',
            'selection':'inner clip max min(accuracy,balanced_accuracy,macro_f1), then accuracy,BA,F1; fine thresholds inner-only F1',
            'promotion':'no clip metric regression vs fixed control and positive held-family fine-event agreement; prototype only',
            'control':control,
            'production_ready':False,'independent_external_test':False,'original_verdicts_changed':False}
    plan['protocol_sha256'] = stable_hash(plan)
    atomic_json(output/'protocol.json',plan)


class TemporalOperations(nn.Module):
    """One frozen CNN outside this module and one 192-unit GRU."""
    def __init__(self, dropout=.5):
        super().__init__()
        self.project = nn.Sequential(nn.Linear(DIM,128),nn.GELU(),nn.Dropout(dropout))
        self.motion = nn.Sequential(nn.Linear(256,128),nn.GELU())
        self.gru = nn.GRU(128,192,batch_first=True)
        self.local = nn.Conv1d(192,192,5,padding=2,groups=192)
        self.dropout = nn.Dropout(dropout)
        self.coarse = nn.Linear(192,len(COARSE))
        self.fine = nn.Linear(192,len(TAXONOMY))
        self.video = nn.Sequential(nn.Linear(384+3*len(TAXONOMY),64),nn.GELU(),nn.Dropout(dropout),nn.Linear(64,1))

    def forward(self, x, lengths):
        if x.ndim != 3 or x.shape[-1] != DIM or not torch.isfinite(x).all() or (lengths<1).any() or (lengths>x.shape[1]).any():
            raise ValueError('Invalid temporal operation features')
        z = self.project(x)
        delta = torch.cat((torch.zeros_like(z[:,:1]), z[:,1:]-z[:,:-1]),1)
        z = self.motion(torch.cat((z,delta),-1))
        packed = pack_padded_sequence(z,lengths.cpu(),batch_first=True,enforce_sorted=False)
        hidden,_ = self.gru(packed)
        hidden,_ = pad_packed_sequence(hidden,batch_first=True,total_length=x.shape[1])
        mask = torch.arange(x.shape[1],device=x.device)[None] < lengths.to(x.device)[:,None]
        hidden = (hidden+nn.functional.gelu(self.local(hidden.transpose(1,2)).transpose(1,2)))*mask[...,None]
        coarse, fine = self.coarse(self.dropout(hidden)), self.fine(self.dropout(hidden))
        p = fine.softmax(-1)*mask[...,None]
        half = torch.arange(x.shape[1],device=x.device)[None] < (lengths.to(x.device)[:,None]/2)
        before = (p*half[...,None]).sum(1)/half.sum(1).clamp_min(1)[:,None]
        after_mask = mask & ~half
        after = (p*after_mask[...,None]).sum(1)/after_mask.sum(1).clamp_min(1)[:,None]
        summary = torch.cat((hidden.sum(1)/lengths.to(x.device)[:,None], hidden.masked_fill(~mask[...,None],-torch.inf).amax(1),
                             p.sum(1)/lengths.to(x.device)[:,None], p.amax(1),after-before),1)
        return self.video(summary).squeeze(-1),coarse,fine


def support(rows):
    families = [{r['group_id'] for r in rows if bool((r['fine'][:,c]>0).any())} for c in range(len(TAXONOMY))]
    counts = sum((r['fine']>0).sum(0) for r in rows)
    enabled = torch.tensor([len(f)>=2 for f in families]) & (counts>=3)
    coarse = torch.cat([r['coarse'] for r in rows])
    pos, neg = (coarse==1).sum(0), (coarse==0).sum(0)
    return enabled, (pos>0)&(neg>0), (neg/pos.clamp_min(1)).clamp(.1,10.), counts


def fit(rows, arm, seed, device='cuda', epochs=None):
    if not rows or {r['target'] for r in rows}!={0,1}:raise ValueError('Both train verdict classes required')
    torch.manual_seed(seed);np.random.seed(seed)
    # Equal weight per video when estimating normalization.
    means = torch.stack([r['features'][0].mean(0) for r in rows])
    mean = means.mean(0)
    second = torch.stack([r['features'][0].square().mean(0) for r in rows]).mean(0)
    scale = (second-mean.square()).clamp_min(.0001).sqrt()
    enabled, coarse_enabled, coarse_weight, counts = support(rows)
    class_weight = (counts.sum()/counts.clamp_min(1)).sqrt().clamp(max=10)
    class_weight = class_weight/class_weight.mean()
    lengths = torch.tensor([r['features'].shape[1] for r in rows])
    variants = [pad_sequence([(r['features'][v]-mean)/scale for r in rows],batch_first=True).to(device) for v in range(3)]
    targets = torch.tensor([r['target'] for r in rows],dtype=torch.float32,device=device)
    fine = pad_sequence([r['fine'] for r in rows],batch_first=True).to(device)*enabled.to(device)
    fine = fine/fine.sum(-1,keepdim=True).clamp_min(1)
    fine_known = fine.sum(-1)>0
    coarse = pad_sequence([r['coarse'] for r in rows],batch_first=True,padding_value=-1).to(device,dtype=torch.float32)
    coarse_known = (coarse>=0)&coarse_enabled.to(device)
    model = TemporalOperations().to(device)
    optimizer = torch.optim.AdamW(model.parameters(),lr=CONFIG['lr'],weight_decay=CONFIG['weight_decay'])
    pos_weight = (targets==0).sum()/(targets==1).sum()
    for epoch in range(epochs or CONFIG['epochs']):
        model.train();optimizer.zero_grad(set_to_none=True)
        x = variants[epoch%3]
        # Train-only perturbation; no held-out images or labels are used.
        x = x+torch.randn_like(x)*.02
        video, c, f = model(x,lengths)
        loss = nn.functional.binary_cross_entropy_with_logits(video,targets,pos_weight=pos_weight)
        if arm == 'temporal_actions':
            raw = nn.functional.binary_cross_entropy_with_logits(c,coarse.clamp_min(0),pos_weight=coarse_weight.to(device),reduction='none')
            coarse_loss = ((raw*coarse_known).sum(1)/coarse_known.sum(1).clamp_min(1)).mean()
            raw = -(fine*nn.functional.log_softmax(f,-1)*class_weight.to(device)).sum(-1)
            fine_loss = ((raw*fine_known).sum(1)/fine_known.sum(1).clamp_min(1)).mean()
            loss = loss+.5*coarse_loss+fine_loss
        if not torch.isfinite(loss):raise ValueError('Nonfinite operation training loss')
        loss.backward();nn.utils.clip_grad_norm_(model.parameters(),1.);optimizer.step()
    model.eval()
    return {'model':{k:v.detach().cpu().clone() for k,v in model.state_dict().items()},
            'normalization':{'mean':mean,'scale':scale},'fine_support':enabled,'coarse_support':coarse_enabled,
            'train_ids':sorted(r['video_id'] for r in rows),'seed':seed,'arm':arm}


def predict(checkpoint, rows, device='cuda'):
    model = TemporalOperations().to(device).eval();model.load_state_dict(checkpoint['model'],strict=True)
    norm = checkpoint['normalization'];result=[]
    with torch.inference_mode():
        # Single-video layout is shared with raw inference; no padded-batch parity claim.
        for r in rows:
            x = ((r['features'][0]-norm['mean'])/norm['scale']).to(device)
            v,c,f = model(x[None],torch.tensor([len(x)]))
            fine = f[0].softmax(-1).cpu()
            fine[:,~checkpoint['fine_support']] = 0
            result.append({'video_id':r['video_id'],'truth':bool(r['target']),'score':float(v.sigmoid()[0]),
                           'fine':fine,'coarse':c[0].sigmoid().cpu()})
    return result


def clip_threshold(rows):
    candidates = sorted({0.,1.,*[r['score'] for r in rows]})
    def rank(t):
        m = metrics(rows,t)
        return (min(m['accuracy'],m['balanced_accuracy'],m['macro_f1']),m['accuracy'],m['balanced_accuracy'],m['macro_f1'],-abs(t-.5))
    return max(candidates,key=rank)


def action_thresholds(predictions, lookup):
    thresholds=[]
    for c in range(len(TAXONOMY)):
        y=[];p=[]
        for pred in predictions:
            truth = lookup[pred['video_id']]['fine'];known=truth.sum(-1)>0
            y.extend((truth[known,c]>.0).tolist());p.extend(pred['fine'][known,c].tolist())
        truth=np.asarray(y,dtype=bool);scores=np.asarray(p)
        if c==0 or truth.sum()<3 or (~truth).sum()<3:
            thresholds.append(1.);continue
        best=(0.,1.)
        for t in np.linspace(.15,.9,16):
            positive=scores>=t;tp=int((positive&truth).sum());fp=int((positive&~truth).sum());fn=int((~positive&truth).sum())
            f1=2*tp/max(1,2*tp+fp+fn)
            if (f1,t)>best:best=(f1,float(t))
        thresholds.append(best[1])
    return thresholds


def action_report(predictions, lookup, thresholds):
    classes=[]
    for c,name in enumerate(TAXONOMY[1:],1):
        tp=fp=fn=0;truth_sources=0;predicted=matched=gt_events=0;onsets=[]
        for pred in predictions:
            row=lookup[pred['video_id']];target=row['fine'];known=target.sum(-1)>0
            truth=target[:,c]>0;positive=pred['fine'][:,c]>=thresholds[c]
            tp+=int((positive&truth&known).sum());fp+=int((positive&~truth&known).sum());fn+=int((~positive&truth&known).sum())
            truth_sources+=int(truth.any())
            # Intervals are proxy targets with uncertain edges, not verified events.
            def runs(mask):
                indices=torch.where(mask)[0].tolist();result=[]
                for n in indices:
                    if not result or n>result[-1][-1]+1:result.append([n])
                    else:result[-1].append(n)
                return result
            actual=runs(truth);proposed=runs(positive);predicted+=len(proposed);gt_events+=len(actual);used=set()
            for run in proposed:
                start,end=float(row['times'][run[0]]),float(row['times'][run[-1]])+.5
                options=[]
                for n,gt in enumerate(actual):
                    if n in used:continue
                    a,b=float(row['times'][gt[0]]),float(row['times'][gt[-1]])+.5
                    union=max(end,b)-min(start,a)
                    iou=max(0,min(end,b)-max(start,a))/max(union,1e-6)
                    options.append((iou,n,a))
                if options:
                    iou,n,a=max(options)
                    if iou>=.3:matched+=1;used.add(n);onsets.append(abs(start-a))
        precision=tp/max(1,tp+fp);recall=tp/max(1,tp+fn)
        classes.append({'class':name,'tp':tp,'fp':fp,'fn':fn,'precision':precision,'recall':recall,
                        'f1':2*tp/max(1,2*tp+fp+fn),'truth_sources':truth_sources,'predicted_intervals':predicted,
                        'target_intervals':gt_events,'matched_iou_0_3':matched,
                        'interval_precision_proxy':matched/max(1,predicted),'interval_recall_proxy':matched/max(1,gt_events),
                        'mean_onset_error_matched_sec':float(np.mean(onsets)) if onsets else None})
    return {'role':'agreement_with_incomplete_weak_operation_labels','classes':classes,
            'macro_f1_all_classes':float(np.mean([r['f1'] for r in classes])),
            'unsupported_classes_count_as_zero':True,'independent_external_test':False}


class Experiment:
    def __init__(self, output, device='cuda'):
        self.output=Path(output);self.plan=read_json(self.output/'protocol.json');self.device=device
        if self.plan['code_sha256']!=code_hash() or self.plan['protocol_sha256']!=stable_hash({k:v for k,v in self.plan.items() if k!='protocol_sha256'}):
            raise ValueError('Operation protocol/code changed')
        self.rows={}
        for video,info in self.plan['inputs'].items():
            path=self.output/'inputs'/(video+'.pt')
            if file_sha256(path)!=info['sha256']:raise ValueError('Operation inputs changed')
            self.rows[video]=torch.load(path,weights_only=True)
        (self.output/'fits').mkdir(exist_ok=True)

    def train(self, ids, arm, seed):
        if not set(ids)<=set(self.plan['development_ids']) or len(ids)!=len(set(ids)):raise ValueError('Foreign/duplicate training source')
        identity={'ids':sorted(ids),'arm':arm,'seed':seed,'protocol':self.plan['protocol_sha256']}
        key=stable_hash(identity);path=self.output/'fits'/(key+'.pt')
        if path.exists():
            checkpoint=torch.load(path,weights_only=True)
            if checkpoint['identity']!=identity:raise ValueError('Fit identity changed')
            return checkpoint
        started=time.monotonic()
        checkpoint=fit([self.rows[v] for v in ids],arm,seed,self.device)
        checkpoint['identity']=identity
        atomic_checkpoint(path,checkpoint)
        print(json.dumps({'fit':key[:12],'arm':arm,'sources':len(ids),'seed':seed,'seconds':time.monotonic()-started}),flush=True)
        return checkpoint

    def calibrate(self, folds, arm):
        predictions=[]
        for fold in folds:
            if {self.rows[v]['group_id'] for v in fold['train']} & {self.rows[v]['group_id'] for v in fold['validation']}:
                raise ValueError('Family leakage')
            predictions.extend(predict(self.train(fold['train'],arm,42),[self.rows[v] for v in fold['validation']],self.device))
        return clip_threshold(predictions),action_thresholds(predictions,self.rows)

    def run(self):
        if (self.output/'complete.json').exists():raise ValueError('Completed experiments are immutable')
        all_predictions={arm:{seed:[] for seed in SEEDS} for arm in ARMS};all_actions={arm:[] for arm in ARMS};all_thresholds={arm:[] for arm in ARMS}
        for number,fold in enumerate(self.plan['folds']):
            report_path=self.output/f'outer-{number}.pt'
            if report_path.exists():
                report=torch.load(report_path,weights_only=True)
            else:
                report={}
                for arm in ARMS:
                    threshold,action_t=self.calibrate(fold['inner'],arm)
                    values={}
                    for seed in SEEDS:
                        p=predict(self.train(fold['train'],arm,seed),[self.rows[v] for v in fold['validation']],self.device)
                        values[seed]=[{**r,'threshold':threshold} for r in p]
                    report[arm]={'predictions':values,'action_thresholds':action_t}
                atomic_checkpoint(report_path,report)
            for arm in ARMS:
                for seed in SEEDS:all_predictions[arm][seed].extend(report[arm]['predictions'][seed])
                all_actions[arm].extend(report[arm]['predictions'][42])
                all_thresholds[arm].append({'ids':fold['validation'],'thresholds':report[arm]['action_thresholds']})
            print(json.dumps({'outer_complete':number}),flush=True)
        summary={}
        for arm in ARMS:
            per_seed={str(seed):summarize(all_predictions[arm][seed]) for seed in SEEDS}
            mean={k:float(np.mean([m[k] for m in per_seed.values()])) for k in ('accuracy','balanced_accuracy','macro_f1')}
            # Every outer prediction keeps its own train-only calibrated thresholds.
            adjusted=[]
            for record in all_thresholds[arm]:
                for r in all_actions[arm]:
                    if r['video_id'] in record['ids']:
                        adjusted.append({**r,'fine':r['fine']/torch.tensor(record['thresholds']).clamp_min(.001)})
            summary[arm]={'seeds':per_seed,'mean':mean,'actions':action_report(adjusted,self.rows,[1.]*len(TAXONOMY))}
        control=self.plan['control'];candidate=summary['temporal_actions']['mean']
        promoted=all(candidate[k]>=control[k] for k in control) and summary['temporal_actions']['actions']['macro_f1_all_classes']>=.35
        result={'version':VERSION,'protocol_sha256':self.plan['protocol_sha256'],'results':summary,
                'promoted_clip_model':promoted,'production_ready':False,'independent_external_test':False}
        atomic_json(self.output/'cv_report.json',result)
        threshold,action_t=self.calibrate(self.plan['final_inner'],'temporal_actions')
        final=self.train(self.plan['development_ids'],'temporal_actions',42)
        final={**final,'threshold':threshold,'action_thresholds':action_t,'protocol_sha256':self.plan['protocol_sha256']}
        atomic_checkpoint(self.output/'final.pt',final)
        atomic_json(self.output/'complete.json',{'report_sha256':file_sha256(self.output/'cv_report.json'),'fit_sha256':file_sha256(self.output/'final.pt'),
                                               'promoted_clip_model':promoted,'production_ready':False})
        print(json.dumps(result),flush=True)


def main():
    parser=argparse.ArgumentParser(description=__doc__);sub=parser.add_subparsers(dest='command',required=True)
    p=sub.add_parser('prepare');p.add_argument('--root',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    p=sub.add_parser('run');p.add_argument('--output',type=Path,required=True);p.add_argument('--device',default='cuda')
    args=parser.parse_args();torch.set_num_threads(4);torch.use_deterministic_algorithms(True)
    if args.command=='prepare':prepare(args.root,args.output)
    else:Experiment(args.output,args.device).run()


if __name__=='__main__':main()
