"""CPU-only portable inference. Does not import torch or training entrypoints."""
from pathlib import Path
import argparse
import json

import numpy as np
import onnxruntime as ort

from training.features import FEATURE_VERSION, candidates, encode


class LocalPolicy:
    def __init__(self, path):
        options = ort.SessionOptions()
        options.intra_op_num_threads = 1
        options.inter_op_num_threads = 1
        self.session = ort.InferenceSession(str(path), sess_options=options,
                                            providers=['CPUExecutionProvider'])
        if self.session.get_modelmeta().custom_metadata_map.get('feature_version') != FEATURE_VERSION:
            raise ValueError('Model and encoder feature versions differ')

    def scores(self, state, actions):
        state, actions = np.asarray(state, dtype=np.float32), np.asarray(actions, dtype=np.float32)
        if state.ndim != 1 or actions.ndim != 2 or not len(actions):
            raise ValueError('Expected one state vector and at least one candidate')
        result = self.session.run(None, {'state': state[None], 'actions': actions[None]})[0][0]
        if not np.isfinite(result).all():
            raise ValueError('Non-finite policy output')
        return result

    def choose_action(self, game):
        options = candidates(game)
        state, actions = encode(game, options)
        return options[int(self.scores(state, actions).argmax())]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--model', type=Path, default=Path(__file__).resolve().parents[1] / 'model.onnx')
    parser.add_argument('--seed', type=int, default=8_000_001)
    parser.add_argument('--games', type=int, default=1)
    args = parser.parse_args()
    from src.ai import choose_action
    from src.cards import build_decks
    from src.game import Game
    from src.models import Player
    from src.rules import create_state
    model = LocalPolicy(args.model)
    results = []
    for number in range(args.games):
        seed = args.seed + number
        game = Game(create_state([Player(str(i)) for i in range(4)], build_decks(seed), seed))
        seat = number % 4
        for step in range(2000):
            if game.state.finished:
                break
            game.execute(model.choose_action(game) if game.state.current_player == seat else choose_action(game, 'hard'))
        if not game.state.finished:
            raise RuntimeError('Self-test game truncated')
        winners = game.winners()
        results.append({'seed': seed, 'model_seat': seat, 'finished': True,
                        'scores': [p.score for p in game.state.players],
                        'victory_credit': 1 / len(winners) if any(p is game.state.players[seat] for p in winners) else 0.})
    print(json.dumps({'provider': model.session.get_providers(), 'games': results}, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
