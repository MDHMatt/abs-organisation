"""Audio stream information extraction via mutagen."""

from __future__ import annotations

import logging
from dataclasses import dataclass

import mutagen
import mutagen.asf
import mutagen.flac
import mutagen.mp3
import mutagen.mp4
import mutagen.oggopus
import mutagen.oggvorbis

logger = logging.getLogger(__name__)


@dataclass
class AudioInfo:
    """Stream-level properties of an audio file."""

    bitrate: int = 0          # bits per second (e.g. 128000)
    duration: float = 0.0     # seconds
    codec: str = ""           # "mp3", "aac", "flac", "vorbis", "opus", "wma"
    sample_rate: int = 0      # Hz (e.g. 44100)
    channels: int = 0         # 1=mono, 2=stereo


# Map mutagen info types to codec names.
_INFO_CODEC_MAP: dict[type, str] = {
    mutagen.mp3.MPEGInfo: "mp3",
    mutagen.mp4.MP4Info: "aac",
    mutagen.flac.StreamInfo: "flac",
    mutagen.oggvorbis.OggVorbisInfo: "vorbis",
    mutagen.oggopus.OggOpusInfo: "opus",
    mutagen.asf.ASFInfo: "wma",
}


def extract_audio_info(filepath: str) -> AudioInfo:
    """Open *filepath* with mutagen and return stream-level :class:`AudioInfo`.

    Returns a default (all-zero) result on any failure.
    """
    try:
        audio = mutagen.File(filepath, easy=False)
    except Exception:
        logger.debug("mutagen could not open: %s", filepath)
        return AudioInfo()

    if audio is None or audio.info is None:
        return AudioInfo()

    info = audio.info
    codec = _INFO_CODEC_MAP.get(type(info), "")

    return AudioInfo(
        bitrate=getattr(info, "bitrate", 0) or 0,
        duration=getattr(info, "length", 0.0) or 0.0,
        codec=codec,
        sample_rate=getattr(info, "sample_rate", 0) or 0,
        channels=getattr(info, "channels", 0) or 0,
    )


def format_duration(seconds: float) -> str:
    """Format *seconds* as a human-readable duration string."""
    if seconds <= 0:
        return "0s"
    total = int(seconds)
    h, remainder = divmod(total, 3600)
    m, s = divmod(remainder, 60)
    if h:
        return f"{h}h{m:02d}m{s:02d}s"
    if m:
        return f"{m}m{s:02d}s"
    return f"{s}s"


def format_quality(ai: AudioInfo) -> str:
    """Format an :class:`AudioInfo` as a single-line quality summary."""
    parts: list[str] = []
    if ai.codec:
        parts.append(ai.codec.upper())
    if ai.bitrate:
        parts.append(f"{ai.bitrate // 1000}kbps")
    if ai.sample_rate:
        sr = ai.sample_rate / 1000
        parts.append(f"{sr:g}kHz")
    if ai.channels:
        parts.append("stereo" if ai.channels >= 2 else "mono")
    dur = format_duration(ai.duration)
    if parts:
        return f"{' '.join(parts)}, {dur}"
    return dur
