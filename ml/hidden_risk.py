"""Preregistered risk ablation: only the original 256 GRU state dimensions.

The parent experiment used6016 input dimensions for36 videos. This variant keeps
the exact same objective, folds, normalization and selection while zeroing detail
features before any fit. It neither modifies the completed parent nor its models.
"""
import argparse
import hashlib
from pathlib import Path
import torch
from ml import temporal_risk as parent
from ml.data.annotation_tasks import read_json
from ml.data.deduplicate import stable_hash
from ml.models.encoder import file_sha256
from ml.video_baseline import atomic_json

VERSION='weak-hidden-risk-v1'


def code_hash():
    return stable_hash({'own':hashlib.sha256(Path(__file__).read_text(encoding='utf-8-sig').encode()).hexdigest(),'parent':parent.code_hash()})


def prepare(experiment,destination):
    experiment,destination=Path(experiment),Path(destination)
    plan=read_json(experiment/'protocol.json')
    if plan['code_sha256']!=parent.code_hash():raise ValueError('Parent risk algorithm changed')
    new={k:v for k,v in plan.items() if k!='protocol_sha256'}
    new.update(version=VERSION,code_sha256=code_hash(),parent=str(experiment.resolve()),
               parent_protocol_sha256=plan['protocol_sha256'],feature_ablation='only original GRU hidden256; all detail feature weights zero')
    new['protocol_sha256']=stable_hash(new);destination.mkdir(parents=True,exist_ok=False);atomic_json(destination/'protocol.json',new)


class Experiment(parent.Experiment):
    def __init__(self,directory,device='cuda'):
        directory=Path(directory);plan=read_json(directory/'protocol.json')
        if plan['code_sha256']!=code_hash() or plan['protocol_sha256']!=stable_hash({k:v for k,v in plan.items() if k!='protocol_sha256'}):
            raise ValueError('Hidden risk variant changed')
        # Parent is read only: its representations already have exact fold-specific encoders.
        self.parent=parent.Experiment(plan['parent'],device)
        self.directory=directory;self.plan=plan;self.device=device;self.rows=self.parent.rows
        (directory/'fits').mkdir(exist_ok=True);(directory/'representations').mkdir(exist_ok=True)

    def representations(self,ids,seed):
        values=self.parent.representations(ids,seed)
        return {video:{**row,'features':torch.cat((row['features'][:,:256],torch.zeros(len(row['features']),parent.DIM-256)),1)}
                for video,row in values.items()}


def main():
    parser=argparse.ArgumentParser(description=__doc__);sub=parser.add_subparsers(dest='command',required=True)
    p=sub.add_parser('prepare');p.add_argument('--parent',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    p=sub.add_parser('run');p.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();torch.set_num_threads(4);torch.use_deterministic_algorithms(True)
    if args.command=='prepare':prepare(args.parent,args.output)
    else:Experiment(args.output).run()


if __name__=='__main__':main()
