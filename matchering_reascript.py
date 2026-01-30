"""
Matchering ReaScript for REAPER
-------------------------------
How to use:
1. Place a TARGET item (your song) on one track
2. Place a REFERENCE item (the sound you want) on another track
3. Select BOTH items
4. Run this script from Actions

You'll get a choice:
  - Analyze + Plugin: creates a real-time JSFX you can tweak
  - Process Offline: full matchering render (original behavior)
"""

from __future__ import print_function
import sys
import traceback

print("=== Matchering ReaScript loading ===", file=sys.stderr)

try:
    import subprocess
    import os

    SCRIPT_DIR = "/home/bryan/PLUGIN"
    VENV_PYTHON = os.path.join(SCRIPT_DIR, "venv", "bin", "python3")
    PROCESSOR = os.path.join(SCRIPT_DIR, "matchering_process.py")
    ANALYZER = os.path.join(SCRIPT_DIR, "matchering_analyzer.py")
    JSFX_GEN = os.path.join(SCRIPT_DIR, "jsfx_generator.py")
    EFFECTS_DIR = os.path.expanduser("~/.config/REAPER/Effects")
    JSFX_OUTPUT = os.path.join(EFFECTS_DIR, "matchering_realtime.jsfx")
    PARAMS_JSON = os.path.join(SCRIPT_DIR, "matchering_params.json")


    def get_item_source_file(item):
        take = RPR_GetActiveTake(item)
        if not take:
            return None
        source = RPR_GetMediaItemTake_Source(take)
        if not source:
            return None
        filenamebuf = " " * 1024
        result = RPR_GetMediaSourceFileName(source, filenamebuf, 1024)
        return result[1].strip() if result[1].strip() else None


    def msg(text):
        RPR_ShowMessageBox(str(text), "Matchering", 0)


    def get_selected_files():
        num_selected = RPR_CountSelectedMediaItems(0)
        if num_selected != 2:
            msg(
                f"Select exactly 2 items:\n"
                f"- First = TARGET (your song)\n"
                f"- Second = REFERENCE (desired sound)\n\n"
                f"Currently selected: {num_selected}"
            )
            return None, None

        target_item = RPR_GetSelectedMediaItem(0, 0)
        ref_item = RPR_GetSelectedMediaItem(0, 1)

        target_file = get_item_source_file(target_item)
        ref_file = get_item_source_file(ref_item)

        if not target_file or not os.path.isfile(target_file):
            msg(f"Could not find target audio file:\n{target_file}")
            return None, None
        if not ref_file or not os.path.isfile(ref_file):
            msg(f"Could not find reference audio file:\n{ref_file}")
            return None, None

        return target_file, ref_file


    def run_subprocess(args, label):
        RPR_ShowConsoleMsg(f"Matchering: {label}...\n")
        print(f"Running: {' '.join(args)}", file=sys.stderr)

        try:
            result = subprocess.run(args, capture_output=True, text=True, timeout=300)
        except subprocess.TimeoutExpired:
            msg(f"{label} timed out after 5 minutes.")
            return None
        except Exception as e:
            msg(f"Error: {e}")
            traceback.print_exc(file=sys.stderr)
            return None

        print(f"Return code: {result.returncode}", file=sys.stderr)
        if result.stdout:
            print(f"STDOUT: {result.stdout}", file=sys.stderr)
        if result.stderr:
            print(f"STDERR: {result.stderr}", file=sys.stderr)

        if result.returncode != 0:
            msg(f"{label} failed:\n{result.stderr[:500]}")
            RPR_ShowConsoleMsg(f"STDERR:\n{result.stderr}\n")
            return None

        RPR_ShowConsoleMsg(result.stdout + "\n")
        return result


    def do_analyze(target_file, ref_file):
        """Analyze and generate real-time JSFX plugin."""
        # Ask for a profile name
        result = RPR_GetUserInputs(
            "Matchering Profile", 1,
            "Profile name (e.g. Rock Ref, Steely Dan):",
            "", 256
        )

        if not result[0]:
            return  # User cancelled

        profile_name = result[4].strip()

        # Determine output filenames based on profile
        if profile_name:
            safe_name = profile_name.replace(" ", "_").lower()
            jsfx_output = os.path.join(EFFECTS_DIR, f"matchering_{safe_name}.jsfx")
            jsfx_filename = f"matchering_{safe_name}.jsfx"
        else:
            jsfx_output = JSFX_OUTPUT
            jsfx_filename = "matchering_realtime.jsfx"

        RPR_ShowConsoleMsg(f"Target: {target_file}\nReference: {ref_file}\n")
        if profile_name:
            RPR_ShowConsoleMsg(f"Profile: {profile_name}\n")

        # Step 1: Run analyzer
        result = run_subprocess(
            [VENV_PYTHON, ANALYZER, target_file, ref_file, PARAMS_JSON],
            "Analyzing"
        )
        if not result:
            return

        # Step 2: Generate JSFX
        gen_args = [VENV_PYTHON, JSFX_GEN, PARAMS_JSON, jsfx_output]
        if profile_name:
            gen_args.append(profile_name)
        result = run_subprocess(gen_args, "Generating JSFX")
        if not result:
            return

        # Step 3: Add JSFX to the target's track
        target_item = RPR_GetSelectedMediaItem(0, 0)
        track = RPR_GetMediaItem_Track(target_item)

        # Add the JSFX as an FX on the track
        fx_idx = RPR_TrackFX_AddByName(track, jsfx_output, 0, -1)
        if fx_idx < 0:
            fx_idx = RPR_TrackFX_AddByName(track, jsfx_filename, 0, -1)

        display = profile_name if profile_name else "default"
        if fx_idx >= 0:
            RPR_TrackFX_SetOpen(track, fx_idx, True)
            msg(
                f"Real-time mastering plugin loaded!\n"
                f"Profile: {display}\n\n"
                f"FIR convolution - exact matchering EQ curve.\n"
                f"Latency: ~93ms (auto-compensated by REAPER PDC)\n\n"
                f"Sliders:\n"
                f"- Input Gain: RMS loudness match\n"
                f"- Low/Mid/High Tweak: post-EQ seasoning\n"
                f"- 42069 Compressor: FET compression\n"
                f"- Dry/Wet: blend with original\n"
                f"- Limiter: brickwall protection"
            )
        else:
            msg(
                f"JSFX generated but couldn't auto-load it.\n"
                f"Add it manually: FX > JS > {jsfx_filename}\n\n"
                f"File: {jsfx_output}"
            )


    def do_offline(target_file, ref_file):
        """Full offline matchering render."""
        target_dir = os.path.dirname(target_file)
        target_name = os.path.splitext(os.path.basename(target_file))[0]
        output_file = os.path.join(target_dir, f"{target_name}_mastered.wav")

        RPR_ShowConsoleMsg(f"Target: {target_file}\nReference: {ref_file}\n")

        result = run_subprocess(
            [VENV_PYTHON, PROCESSOR, target_file, ref_file, output_file],
            "Processing"
        )
        if not result:
            return

        if not os.path.isfile(output_file):
            msg("Matchering ran but output file was not created.")
            return

        num_tracks = RPR_CountTracks(0)
        RPR_InsertTrackAtIndex(num_tracks, True)
        new_track = RPR_GetTrack(0, num_tracks)
        RPR_GetSetMediaTrackInfo_String(new_track, "P_NAME", "Mastered", True)
        RPR_SetOnlyTrackSelected(new_track)
        RPR_InsertMedia(output_file, 0)
        RPR_UpdateArrange()

        msg(f"Done! Mastered file placed on new track.\n\nOutput: {output_file}")


    def main():
        print("=== Matchering main() called ===", file=sys.stderr)

        if not os.path.isfile(VENV_PYTHON):
            msg(f"Venv Python not found at:\n{VENV_PYTHON}")
            return

        target_file, ref_file = get_selected_files()
        if not target_file:
            return

        # Ask the user what they want to do
        choice = RPR_ShowMessageBox(
            "What do you want to do?\n\n"
            "YES = Analyze + Real-time Plugin (JSFX)\n"
            "   Analyzes your tracks and creates a tweakable plugin\n\n"
            "NO = Process Offline (full render)\n"
            "   Runs full matchering and creates a mastered file",
            "Matchering",
            3,  # Yes/No/Cancel
        )

        if choice == 6:  # Yes
            do_analyze(target_file, ref_file)
        elif choice == 7:  # No
            do_offline(target_file, ref_file)
        # Cancel = do nothing

    main()

except Exception as e:
    print(f"=== Matchering ReaScript FATAL ERROR ===", file=sys.stderr)
    traceback.print_exc(file=sys.stderr)
    try:
        RPR_ShowMessageBox(f"Script error:\n{e}", "Matchering Error", 0)
    except:
        pass
