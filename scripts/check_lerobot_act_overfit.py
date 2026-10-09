#!/usr/bin/env python3
"""Interface and one-episode teacher/action-chunk alignment check."""
from __future__ import annotations
import argparse,json
from pathlib import Path
import numpy as np
def main():
 ap=argparse.ArgumentParser();ap.add_argument('--dataset',required=True);ap.add_argument('--episode',type=int,default=0);a=ap.parse_args();p=Path(a.dataset)/'data'/f'episode_{a.episode:04d}.npz';d=np.load(p,allow_pickle=True);st=d['observation_state'];ac=d['action'];ch=d['action_chunk'];assert st.shape[0]==ac.shape[0] and ac.shape[1]==7 and ch.shape[1:]==(4,7);recon=np.stack([ch[i,0] for i in range(len(ch))]);err=float(np.max(np.abs(recon-ac[:len(recon)]))); result={'episode':a.episode,'frames':len(ac),'obs_dim':int(st.shape[1]),'action_shape':list(ac.shape),'chunk_shape':list(ch.shape),'max_first_action_error':err,'teacher_action_reproduced':bool(err==0.0),'timestamp_dt':float(np.diff(d['timestamp']).mean()),'phase_start':str(d['phase'][0]),'phase_trace':list(dict.fromkeys(map(str,d['phase']))),'normalization_exists':(Path(a.dataset)/'normalization.npz').exists()};print(json.dumps(result,indent=2));
if __name__=='__main__':main()
