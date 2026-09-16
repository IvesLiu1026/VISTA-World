"""Create a silent, English-captioned technical review from real sensor frames.

Uses only the first repeat of each explicitly labeled trial. The two views are
fixed cameras from the same run, not a human avatar or a learned-agent demo.
"""
import argparse
import json
from pathlib import Path
import subprocess

from PIL import Image, ImageDraw, ImageFont

p = argparse.ArgumentParser()
p.add_argument("--data", type=Path, required=True)
p.add_argument("--output", type=Path, required=True)
args = p.parse_args()
args.output.mkdir(parents=True, exist_ok=False)
result = json.loads((args.data/"results.json").read_text())
if not result["checks"]["sensor_streams_valid"]:
    raise RuntimeError("Review requires valid native sensor evidence")
font_path = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
font = ImageFont.truetype(font_path, 23)
small = ImageFont.truetype(font_path, 18)
phases = ["Approach object", "Lower gripper", "Settle", "Close gripper", "Lift object",
          "Carry to target", "Lower object", "Open gripper", "Retract", "Finish", "Verify physical outcome"]
titles = {"normal": "NORMAL PICK AND PLACE", "pause_resume": "PAUSE FOR 2 SECONDS, THEN RESUME",
          "gripper_disabled": "FAULT TEST: GRIPPER HELD OPEN"}
command = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-f", "rawvideo",
           "-pixel_format", "rgb24", "-video_size", "1280x492", "-framerate", "15",
           "-i", "pipe:0", "-an", "-c:v", "libx264", "-preset", "fast", "-crf", "20",
           "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(args.output/"isaac-pilot-demo.mp4")]
frames = 0
with subprocess.Popen(command, stdin=subprocess.PIPE) as encoder:
    try:
        for item in result["trials"]:
            if item["repeat"] != 0:
                continue
            trial = args.data/item['trial']
            stream = [json.loads(x) for x in (trial/"observations/stream.jsonl").read_text().splitlines()]
            trace = {r['step']:r for r in json.loads((trial/"evaluation/trace.json").read_text())}
            for index, obs in enumerate(stream):
                ev = trace[obs['step']]
                image = Image.new("RGB", (1280,492), (15,21,29))
                image.paste(Image.open(trial/"observations"/obs['images']['observer']['rgb']), (0,68))
                image.paste(Image.open(trial/"observations"/obs['images']['ego']['rgb']), (640,68))
                draw = ImageDraw.Draw(image)
                draw.text((18,8), titles[item['condition']], font=font, fill="white")
                draw.text((18,40), "FIXED ROOM CAMERA", font=small, fill=(164,185,205))
                draw.text((658,40), "FIXED EGO-HEIGHT CAMERA (NO HUMAN AVATAR)", font=small, fill=(164,185,205))
                phase = "PAUSED - physics and sensors continue" if ev['paused'] and ev['controller_event'] < 10 else phases[min(ev['controller_event'],10)]
                draw.text((18,436), f"t = {obs['clock_s']:05.2f} s  |  {phase}", font=small, fill="white")
                line = "Scripted RMPflow controller; real PhysX contact; no learned planning."
                color = (173,190,206)
                if ev['controller_event'] >= 10:
                    verdict = "SUCCESS" if item['physical_success'] else "FAILED"
                    line = f"Controller: DONE  |  Physical result: {verdict}  |  Final target error: {item['target_xy_error_m']*1000:.1f} mm"
                    color = (103,221,158) if item['physical_success'] else (255,171,119)
                    if item['condition'] == 'pause_resume' and item['minimum_carried_height_during_pause_m'] <= .9:
                        line = "Final placement: SUCCESS | Pause clearance criterion: FAILED (controller paused too early)"
                        color = (255,171,119)
                draw.text((18,464), line, font=small, fill=color)
                encoder.stdin.write(image.tobytes())
                frames += 1
                if index in (0, len(stream)//2, len(stream)-1):
                    image.save(args.output/f"{item['condition']}-{index:04d}.png")
            # Preserve a readable outcome without inventing further simulation.
            for _ in range(15):
                encoder.stdin.write(image.tobytes())
                frames += 1
        encoder.stdin.close()
        if encoder.wait(timeout=60):
            raise RuntimeError("ffmpeg failed")
    finally:
        if encoder.poll() is None:
            encoder.kill()
            encoder.wait()
(args.output/"media-receipt.json").write_text(json.dumps({
    "source":str(args.data.resolve()),"source_kind":"native Isaac RGB sensor frames",
    "frames":frames,"fps":15,"duration_s":frames/15,"audio":False,
    "edits":"English labels; paired fixed cameras; three separately reset trials; one-second outcome holds",
    "note":"Not photorealism, human locomotion, image-based planning or synchronized UE/Isaac replay",
    "experiment_checks":result['checks'],
},indent=2)+"\n")
print(args.output/"isaac-pilot-demo.mp4")
