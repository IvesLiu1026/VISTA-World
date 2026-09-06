"""Copy an accepted home and CC0 character into an isolated interaction project."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil


def record(path):
    return {"path": str(path.resolve()), "bytes": path.stat().st_size,
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--home", type=Path, required=True)
    p.add_argument("--character", type=Path, required=True)
    p.add_argument("--out", type=Path, required=True)
    a = p.parse_args()
    if a.out.exists():
        raise SystemExit("Use a fresh project directory")
    home = a.home / "PhotorealHome.uproject"
    character = a.character / "Content/VISTA/MakeHumanCC0/R6"
    if not home.is_file() or not (character / "SK_VISTA_CC0_Hero_R6.uasset").is_file():
        raise SystemExit("Accepted home or character is missing")
    shutil.copytree(a.home, a.out, ignore=shutil.ignore_patterns(
        "Saved", "Intermediate", "DerivedDataCache", ".git"))
    shutil.copytree(character, a.out / "Content/VISTA/MakeHumanCC0/R6")
    config = a.out / "Config/DefaultEngine.ini"
    text = config.read_text()
    text = text.replace("GlobalDefaultGameMode=/Script/VistaPhotorealReview.PhotorealReviewGameMode",
                        "GlobalDefaultGameMode=/Script/VistaPhotorealReview.EmbodiedReviewGameMode")
    text += "\n[/Script/Engine.PhysicsSettings]\nbSubstepping=True\nMaxSubstepDeltaTime=0.008333\nMaxSubsteps=8\n\n[/Script/Engine.Engine]\nNearClipPlane=2.0\n"
    config.write_text(text)
    receipt = {"schema": "vista.embodied-project-copy/v1", "home": record(home),
               "character_inputs": [record(x) for x in sorted(character.glob("*.uasset"))],
               "project": str((a.out / home.name).resolve()), "status": "copied_for_authoring"}
    (a.out.parent / (a.out.name + "-copy.json")).write_text(json.dumps(receipt, indent=2) + "\n")
    print(receipt["project"])


if __name__ == "__main__":
    main()
