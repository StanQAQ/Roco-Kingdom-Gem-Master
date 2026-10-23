"""CPU-only rule-scoped inference. No training libraries or remote services."""
from pathlib import Path
import argparse
import hashlib
import json
import sys
import numpy as np
from training.features import FEATURE_VERSION
from training.inference import LocalPolicy

SCENARIOS=('unlimited','10','20','30')
DIFFICULTIES=('hard',)


def scenario_key(max_rounds):
    if max_rounds is None:return 'unlimited'
    if type(max_rounds) is not int or max_rounds not in (10,20,30):raise ValueError('Supported max_rounds: None, 10, 20, 30')
    return str(max_rounds)


class ScenarioPolicy:
    """Loads only the selected model; identical baseline copies reuse one ORT session."""
    def __init__(self, manifest):
        self.manifest=Path(manifest).resolve(); self.root=self.manifest.parent
        self.card=json.loads(self.manifest.read_text(encoding='utf-8'))
        if self.card.get('schema_version')!=1 or self.card.get('feature_version')!=FEATURE_VERSION:
            raise ValueError('Unsupported scenario manifest or feature version')
        entries=self.card.get('scenarios',{})
        if not entries or not set(entries).issubset(SCENARIOS):raise ValueError('Invalid scenarios')
        difficulties=self.card.get('difficulties',{})
        if not set(difficulties).issubset(DIFFICULTIES):raise ValueError('Invalid difficulty routes')
        self.entries=entries; self.difficulty_entries=difficulties; self.paths={};self._active_digest=None;self._policy=None
        for key,entry in entries.items():
            path=(self.root/entry['model']).resolve()
            if not path.is_relative_to(self.root):raise ValueError('Model path must remain inside package')
            if hashlib.sha256(path.read_bytes()).hexdigest()!=entry['sha256']:raise ValueError('Model SHA256 mismatch')
            self.paths[key]=path
        for key,entry in difficulties.items():
            path=(self.root/entry['model']).resolve()
            if not path.is_relative_to(self.root):raise ValueError('Model path must remain inside package')
            if hashlib.sha256(path.read_bytes()).hexdigest()!=entry['sha256']:raise ValueError('Model SHA256 mismatch')
            self.paths[f'difficulty:{key}']=path

    def entry(self,target_score,max_rounds,difficulty=None):
        if type(target_score) is not int or not 15<=target_score<=50:raise ValueError('Supported target scores: 15 through 50')
        if difficulty is not None:
            if difficulty not in self.difficulty_entries:
                raise ValueError(f'Unsupported difficulty: {difficulty}')
            return f'difficulty:{difficulty}',self.difficulty_entries[difficulty]
        key=scenario_key(max_rounds)
        if key not in self.entries:raise ValueError(f'This independent package does not contain scenario {key}')
        return key,self.entries[key]

    def _load(self,key,entry):
        if self._active_digest!=entry['sha256']:
            # Release the prior model before loading another scenario.
            self._policy=None;self._active_digest=None
            self._policy=LocalPolicy(self.paths[key]); self._active_digest=entry['sha256']
        return self._policy

    def scores(self,state,actions,*,target_score,max_rounds,difficulty=None):
        key,entry=self.entry(target_score,max_rounds,difficulty)
        state=np.asarray(state,dtype=np.float32)
        expected=[target_score/50,(max_rounds or 0)/50,float(max_rounds is not None)]
        if state.shape!=(676,) or not np.allclose(state[1:4],expected,rtol=0,atol=1e-6):
            raise ValueError('Encoded rules and selected scenario differ')
        return self._load(key,entry).scores(state,actions)

    def choose_action(self,game,*,difficulty=None):
        key,entry=self.entry(game.target_score,game.max_rounds,difficulty)
        return self._load(key,entry).choose_action(game)


def self_test(policy,target,max_rounds,games,seed,difficulty=None):
    from src.ai import choose_action
    from src.cards import build_decks
    from src.game import Game
    from src.models import Player
    from src.rules import create_state
    rows=[]
    for number in range(games):
        game_seed=seed+number
        state=create_state([Player(str(i)) for i in range(4)],build_decks(game_seed),game_seed)
        state.first_player=state.current_player=game_seed%4
        game=Game(state,target_score=target,max_rounds=max_rounds);seat=number%4
        for _ in range(2000):
            if game.state.finished:break
            game.execute(policy.choose_action(game,difficulty=difficulty) if game.state.current_player==seat else choose_action(game,'hard'))
        if not game.state.finished:raise RuntimeError('Self-test game truncated')
        winners=game.winners(); credit=1/len(winners) if any(p is game.state.players[seat] for p in winners) else 0.
        rows.append({'seed':game_seed,'seat':seat,'finished':True,'scores':[p.score for p in game.state.players],'victory_credit':credit})
    key,entry=policy.entry(target,max_rounds,difficulty)
    return {'route':key,'scenario':None if difficulty else key,'difficulty':difficulty,'target_score':target,'model_sha256':entry['sha256'],'model_status':entry['status'],
            'provider':['CPUExecutionProvider'],'games':rows}


def main():
    root=Path(getattr(sys,'_MEIPASS',Path(__file__).resolve().parents[1]))
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest',type=Path,default=root/'scenarios.json')
    parser.add_argument('--max-rounds',choices=SCENARIOS)
    parser.add_argument('--difficulty',choices=DIFFICULTIES)
    parser.add_argument('--target',type=int,default=20);parser.add_argument('--games',type=int,default=1)
    parser.add_argument('--seed',type=int,default=8_000_001)
    parser.add_argument('--input-json',help='Encoded state/actions and target_score/max_rounds; - reads stdin')
    args=parser.parse_args();policy=ScenarioPolicy(args.manifest)
    if args.input_json:
        data=json.loads(sys.stdin.read() if args.input_json=='-' else Path(args.input_json).read_text(encoding='utf-8'))
        target=data['target_score'];limit=data['max_rounds'];difficulty=data.get('difficulty',args.difficulty);scores=policy.scores(data['state'],data['actions'],target_score=target,max_rounds=limit,difficulty=difficulty)
        key,entry=policy.entry(target,limit,difficulty)
        result={'route':key,'scenario':None if difficulty else key,'difficulty':difficulty,'model_sha256':entry['sha256'],'selected_index':int(scores.argmax()),'scores':scores.tolist(),'provider':['CPUExecutionProvider']}
    else:
        if args.games<1:parser.error('games must be positive')
        key=args.max_rounds or (next(iter(policy.entries)) if len(policy.entries)==1 else 'unlimited')
        limit=None if key=='unlimited' else int(key)
        policy.entry(args.target,limit,args.difficulty)
        result=self_test(policy,args.target,limit,args.games,args.seed,args.difficulty)
    print(json.dumps(result,ensure_ascii=False,indent=2))


if __name__=='__main__':main()
