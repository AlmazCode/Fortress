import numpy as np
import torch
from ml.action_rare import fit


def test_few_family_fit_counts_actual_families_and_does_not_treat_unknown_as_negative():
    rows=[];values={}
    for name,group,targets in [('bag','positive',[1]*6+[-1]*2),('a','negative_a',[0]*8),('b','negative_b',[0]*8)]:
        coarse=torch.full((8,15),-1.);coarse[:,4]=torch.tensor(targets)
        rows.append({'video_id':name,'group_id':group,'coarse':coarse})
        values[name]=np.full((8,2),1. if name=='bag' else -1.)
    state=fit(rows,values,4,1.)
    assert state['positive_training_families']==1 and state['negative_training_families']==2
    rows[0]['coarse'][:2,4]=-1
    assert fit(rows,values,4,1.) is None


def test_all_negative_frames_do_not_create_a_rare_positive_recognizer():
    row={'video_id':'a','group_id':'family','coarse':torch.zeros(8,15)}
    assert fit([row],{'a':np.zeros((8,2))},4,1.) is None
