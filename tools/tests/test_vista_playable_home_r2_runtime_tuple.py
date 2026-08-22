from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.runtime.vista_playable_home import runtime
from tools.ue.vista_playable_home import capture_review_views
from tools.ue.vista_playable_home import package_receipt


def test_r2_runtime_tuple_matches_the_vista_world_demo_endpoint() -> None:
    assert runtime.R2_DISPLAY == ":117"
    assert package_receipt.R2_DISPLAY == ":117"
    assert capture_review_views.R2_DISPLAY == ":117"
    assert runtime.R2_VISTA_WORLD_PORT == 55620
    assert package_receipt.R2_VISTA_WORLD_PORT == 55620
    assert runtime.R2_GPU == package_receipt.R2_GPU == 0
    assert runtime.R2_WIDTH == package_receipt.R2_WIDTH == 1920
    assert runtime.R2_HEIGHT == package_receipt.R2_HEIGHT == 1080
    assert runtime.R2_FPS == package_receipt.R2_FPS == 60
