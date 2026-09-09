"""Run inherited native scenarios with verified, collision-free test fixtures."""
import argparse
import importlib
import math
from pathlib import Path
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'vista_home_actions_r2'))
from probe_sequences import Sequences


class CheckedSequences(Sequences):
    def fixture(self, position, target):
        if target == 'living_door':
            position = (-269, 203, 86, -90)
        if target == 'kitchen_door':
            # Approach from the handle side of the open leaf. The original
            # northern fixture can trap the closing path beside the shoe bench.
            position = (70, 88, 86, 90)
        if target == 'bed':
            position = (-318, -258, 86, 180)
        if target == 'shoe_bench':
            position = (59, 299, 86, 0)
        super().fixture(position, target)
        time.sleep(.4)
        state = self.h.state()
        if math.dist(position[:2], state['player_cm'][:2]) > 3 or abs(position[2] - state['player_cm'][2]) > 4:
            raise RuntimeError('Test fixture was displaced by collision: ' + target + ' ' + str(state['player_cm']))


def main():
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument('--suite', choices=['sequences', 'details'], required=True)
    args, remaining = parser.parse_known_args()
    module = importlib.import_module('probe_' + args.suite)
    module.Sequences = CheckedSequences
    sys.argv = [sys.argv[0], *remaining]
    module.main()


if __name__ == '__main__':
    main()
