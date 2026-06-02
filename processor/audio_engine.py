"""
StreamClipper — Audio Engine
Handles voice normalization, looping background music overlay, sidechain audio ducking,
and context-aware sound effects (SFX) injection at highlight climax points.
"""

import logging
import random
from pathlib import Path
from typing import Optional, Tuple

import config

logger = logging.getLogger("streamclipper.audio_engine")


class AudioEngine:
    """Constructs complex FFmpeg audio filtergraphs for mixing voice, background music, and sound effects."""

    def __init__(self):
        self.assets_dir = config.BASE_DIR / "assets"
        self.music_dir = self.assets_dir / "music"
        self.sfx_dir = self.assets_dir / "sfx"

        # Auto-create assets directories
        self.music_dir.mkdir(parents=True, exist_ok=True)
        self.sfx_dir.mkdir(parents=True, exist_ok=True)

        # Populate sample placeholder logs if empty
        self._check_assets_presence()

    def _check_assets_presence(self):
        music_files = list(self.music_dir.glob("*.mp3")) + list(self.music_dir.glob("*.wav"))
        sfx_files = list(self.sfx_dir.glob("*.mp3")) + list(self.sfx_dir.glob("*.wav"))

        if not music_files:
            logger.warning("No background music tracks (.mp3/.wav) found in %s", self.music_dir)
        else:
            logger.info("Found %d background music tracks.", len(music_files))

        if not sfx_files:
            logger.warning("No sound effects (.mp3/.wav) found in %s", self.sfx_dir)
        else:
            logger.info("Found %d sound effect files.", len(sfx_files))

    def get_random_music_track(self) -> Optional[Path]:
        """Select a random background music track from the music directory."""
        tracks = list(self.music_dir.glob("*.mp3")) + list(self.music_dir.glob("*.wav"))
        return random.choice(tracks) if tracks else None

    def get_sfx_track(self, name: str = "vine_boom") -> Optional[Path]:
        """Find a sound effect file matching a specific name/keyword."""
        sfxs = list(self.sfx_dir.glob("*.mp3")) + list(self.sfx_dir.glob("*.wav"))
        for s in sfxs:
            if name.lower() in s.name.lower():
                return s
        return sfxs[0] if sfxs else None

    def build_audio_filter(
        self,
        duration: float,
        has_sfx: bool = False,
        sfx_name: str = "vine_boom",
        sfx_offset_sec: float = 0.0,
    ) -> Tuple[str, list[str]]:
        """
        Builds the audio filter complex and input arguments.
        Returns:
            - filter_string: The FFmpeg audio filter string.
            - extra_args: Additional command line arguments (extra inputs).
        """
        extra_args = []
        filter_parts = []

        # Current input index tracking
        # Input 0: Main Video
        next_input_idx = 1

        # 1. Voice Normalization (loudnorm) on the source audio [0:a]
        filter_parts.append("[0:a]loudnorm=I=-16:TP=-1.5:LRA=11[voice_norm]")
        voice_label = "[voice_norm]"

        music_track = self.get_random_music_track()
        music_input_label = None

        if music_track:
            # Loop the music infinitely to match the clip duration
            extra_args.extend(["-stream_loop", "-1", "-i", str(music_track)])
            music_input_label = f"[{next_input_idx}:a]"
            next_input_idx += 1

            # Adjust music input volume to be quiet by default (-18dB)
            filter_parts.append(f"{music_input_label}volume=volume=0.12[bg_music]")
            
            # Apply sidechain compression (ducking): duck the [bg_music] when [voice_norm] is active
            filter_parts.append(
                f"[voice_norm][bg_music]sidechaincompress=threshold=0.18:ratio=4:attack=150:release=800[bg_ducked]"
            )
            
            # Mix voice and ducked music
            filter_parts.append(f"{voice_label}[bg_ducked]amix=inputs=2:duration=first:dropout_transition=2[mixed_audio]")
            voice_label = "[mixed_audio]"

        sfx_track = self.get_sfx_track(sfx_name) if has_sfx else None
        
        if sfx_track:
            extra_args.extend(["-i", str(sfx_track)])
            sfx_input_label = f"[{next_input_idx}:a]"
            next_input_idx += 1

            # Sound effects volume adjust
            filter_parts.append(f"{sfx_input_label}volume=volume=0.6[sfx_vol]")
            
            # Delay the sound effect to the target timestamp (climax offset in ms)
            delay_ms = int(sfx_offset_sec * 1000)
            # FFmpeg adelay takes delays for each channel separated by '|'
            filter_parts.append(f"[sfx_vol]adelay={delay_ms}|{delay_ms}[sfx_delayed]")
            
            # Mix with the current audio mix
            filter_parts.append(f"{voice_label}[sfx_delayed]amix=inputs=2:duration=first[final_audio]")
            voice_label = "[final_audio]"

        # Ensure the final audio output is mapped to [a_out]
        filter_parts.append(f"{voice_label}anull[a_out]")
        filter_string = ";".join(filter_parts)

        return filter_string, extra_args
