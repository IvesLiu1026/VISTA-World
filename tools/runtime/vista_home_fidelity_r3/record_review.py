"""Reuse native R2 episode capture with opaque R3 candidate directories."""
from pathlib import Path
import sys
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'vista_home_actions_r2'))
import record_events
from export_review import export
from run_native_checks import CheckedSequences


def opaque_export(video, turns, bridge, output, capture, timed=False):
    # The legacy driver supplies an event-named destination. Keep source IDs
    # in privileged evidence and use an opaque directory for the review bundle.
    destination = Path(output).parent / uuid.uuid4().hex
    return export(video, turns, bridge, destination, capture, timed=timed)


if __name__ == '__main__':
    record_events.export = opaque_export
    record_events.Sequences = CheckedSequences
    record_events.main()
