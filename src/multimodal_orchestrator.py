import argparse
import json
import os
import time
from pathlib import Path

from openai import OpenAI

from action_executor import execute_safe_action, recommend_safe_action
from activity_service import ActivityService, ActivityServiceConfig
from audio_service import AudioService, AudioServiceConfig
from calibration import CalibrationManager
from camera_service import CameraService, CameraServiceConfig
from context_fusion import fuse_signals
from local_orchestrator import Toolbox, load_text, run_agent_task
from multimodal_types import to_payload


def build_prompt(task: str, fused: dict, vision: dict, audio: dict, activity: dict) -> str:
    return (
        f"Task: {task}\n\n"
        "Use this multimodal state to assist the user without over-claiming certainty. "
        "Treat signals as probabilistic and propose reversible actions.\n\n"
        f"FUSED_STATE:\n{json.dumps(fused, ensure_ascii=True)}\n\n"
        f"VISION_SIGNAL:\n{json.dumps(vision, ensure_ascii=True)}\n\n"
        f"AUDIO_SIGNAL:\n{json.dumps(audio, ensure_ascii=True)}\n\n"
        f"ACTIVITY_SIGNAL:\n{json.dumps(activity, ensure_ascii=True)}"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Multimodal Local Orchestrator")
    parser.add_argument("--task", required=True, help="User-facing objective")
    parser.add_argument("--workspace-root", default=os.getenv("AGENT_WORKSPACE_ROOT", "."))
    parser.add_argument("--system-dna", default=os.getenv("AGENT_SYSTEM_DNA", "system_dna.md"))
    parser.add_argument("--model", default=os.getenv("LLM_MODEL", "local-model"))
    parser.add_argument("--base-url", default=os.getenv("LLM_BASE_URL", "http://localhost:1234/v1"))
    parser.add_argument("--api-key", default=os.getenv("LLM_API_KEY", "lm-studio"))
    parser.add_argument("--allow-tools", action="store_true")
    parser.add_argument("--max-tool-steps", type=int, default=int(os.getenv("AGENT_MAX_TOOL_STEPS", "4")))
    parser.add_argument("--enable-camera", action="store_true")
    parser.add_argument("--enable-audio", action="store_true")
    parser.add_argument("--enable-transcription", action="store_true")
    parser.add_argument("--transcription-model", default="base")
    parser.add_argument("--transcription-compute-type", default="int8")
    parser.add_argument("--transcription-device", default="auto")
    parser.add_argument("--model-cache-dir", default="memory/models")
    parser.add_argument("--activity-note", default="")
    parser.add_argument("--activity-context-file", default="")
    parser.add_argument("--propose-safe-action", action="store_true")
    parser.add_argument("--approve-action", action="store_true")
    parser.add_argument("--record-calibration-label", default="")
    parser.add_argument("--compute-calibration", action="store_true")
    parser.add_argument("--interval", type=float, default=3.0)
    parser.add_argument("--iterations", type=int, default=1)
    parser.add_argument(
        "--consent",
        default="",
        help='Required when camera/audio are enabled. Pass exactly: "I AGREE"',
    )
    args = parser.parse_args()

    if (args.enable_camera or args.enable_audio) and args.consent != "I AGREE":
        raise SystemExit('Sensor capture blocked. Re-run with --consent "I AGREE".')

    workspace_root = Path(args.workspace_root).resolve()
    calibration = CalibrationManager(workspace_root)
    thresholds = calibration.load_profile()
    if args.compute_calibration:
        thresholds = calibration.compute_profile()

    system_dna_path = Path(args.system_dna)
    if not system_dna_path.is_absolute():
        system_dna_path = workspace_root / system_dna_path
    system_dna = load_text(system_dna_path)

    camera = CameraService(CameraServiceConfig(enabled=args.enable_camera), thresholds=thresholds)
    audio = AudioService(
        AudioServiceConfig(
            enabled=args.enable_audio,
            enable_transcription=args.enable_transcription,
            transcription_model=args.transcription_model,
            transcription_compute_type=args.transcription_compute_type,
            transcription_device=args.transcription_device,
            model_cache_dir=args.model_cache_dir,
        ),
        thresholds=thresholds,
    )
    activity = ActivityService(
        workspace_root=workspace_root,
        config=ActivityServiceConfig(
            enabled=True,
            note=args.activity_note,
            context_file=args.activity_context_file,
        ),
    )

    client = OpenAI(base_url=args.base_url, api_key=args.api_key)
    toolbox = Toolbox(workspace_root=workspace_root)

    for i in range(max(1, args.iterations)):
        vision_signal = camera.sample()
        audio_signal = audio.sample()
        activity_signal = activity.sample()
        fused_state = fuse_signals(vision_signal, audio_signal, activity_signal, thresholds=thresholds)

        if args.record_calibration_label:
            calibration.record_sample(
                {
                    "label": args.record_calibration_label,
                    "audio_energy_rms": audio_signal.energy_rms,
                    "vision_motion_level": vision_signal.motion_level,
                    "vision_eye_open_ratio": vision_signal.eye_open_ratio,
                    "audio_sentiment": audio_signal.sentiment,
                    "audio_sentiment_confidence": audio_signal.sentiment_confidence,
                }
            )

        task_with_state = build_prompt(
            task=args.task,
            fused=to_payload(fused_state),
            vision=to_payload(vision_signal),
            audio=to_payload(audio_signal),
            activity=to_payload(activity_signal),
        )

        output = run_agent_task(
            client=client,
            model=args.model,
            system_dna=system_dna,
            task_description=task_with_state,
            workspace_context="",
            toolbox=toolbox,
            allow_tools=args.allow_tools,
            max_tool_steps=args.max_tool_steps,
        )

        print(f"\n=== Iteration {i + 1} ===")
        print(json.dumps({"fused_state": to_payload(fused_state)}, ensure_ascii=True, indent=2))

        if args.propose_safe_action:
            action = recommend_safe_action(fused_state)
            action_result = execute_safe_action(
                toolbox=toolbox,
                action=action,
                approved=args.approve_action,
            )
            print("\nSAFE_ACTION:\n")
            print(json.dumps(action_result, ensure_ascii=True, indent=2))

        print("\nAGENT_OUTPUT:\n")
        print(output)

        if i + 1 < args.iterations:
            time.sleep(max(0.1, args.interval))


if __name__ == "__main__":
    main()
