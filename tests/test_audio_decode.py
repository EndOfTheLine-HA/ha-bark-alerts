"""Decode generated media with real FFmpeg; no household audio is used."""

import asyncio
import wave

import pytest

from custom_components.bark_alerts.history import MAX_AUDIO, HistoryError, extract_audio


@pytest.mark.parametrize("with_audio", [True, False])
async def test_real_audio_extraction(tmp_path, with_audio):
    imageio_ffmpeg = pytest.importorskip("imageio_ffmpeg")
    binary = imageio_ffmpeg.get_ffmpeg_exe()
    source, target = tmp_path / "input.mp4", tmp_path / "output.wav"
    generator = (
        ["-f", "lavfi", "-i", "sine=frequency=440:duration=10", "-c:a", "aac"]
        if with_audio
        else ["-f", "lavfi", "-i", "color=c=black:s=16x16:d=1", "-an", "-c:v", "mpeg4"]
    )
    process = await asyncio.create_subprocess_exec(
        binary,
        "-nostdin",
        "-v",
        "error",
        "-y",
        *generator,
        str(source),
        stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.PIPE,
    )
    async with asyncio.timeout(30):
        _, error = await process.communicate()
    assert process.returncode == 0, error.decode()
    if not with_audio:
        with pytest.raises(HistoryError, match="audio_unavailable"):
            await extract_audio(source, target, binary)
        return
    await extract_audio(source, target, binary)
    assert 44 < target.stat().st_size <= MAX_AUDIO
    with wave.open(str(target), "rb") as clip:
        assert clip.getnchannels() == 1
        assert clip.getframerate() == 16000
        assert clip.getsampwidth() == 2
        assert 9.9 <= clip.getnframes() / clip.getframerate() <= 10
