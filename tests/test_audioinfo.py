"""Tests for audio info extraction."""



from absorg.audioinfo import AudioInfo, extract_audio_info, format_duration, format_quality


class TestExtractAudioInfo:
    def test_mp3_basic(self, make_mp3):
        path = make_mp3("test.mp3", artist="Test", album="Album")
        ai = extract_audio_info(path)
        assert ai.codec == "mp3"
        assert ai.bitrate > 0
        assert ai.duration > 0
        assert ai.sample_rate == 44100
        assert ai.channels >= 1

    def test_mp3_bitrate(self, make_mp3):
        path = make_mp3("test.mp3")
        ai = extract_audio_info(path)
        # Our fixture creates 128kbps MP3 frames
        assert ai.bitrate == 128000

    def test_nonexistent_file(self):
        ai = extract_audio_info("/nonexistent/file.mp3")
        assert ai == AudioInfo()

    def test_non_audio_file(self, tmp_path):
        txt = tmp_path / "readme.txt"
        txt.write_text("not audio")
        ai = extract_audio_info(str(txt))
        assert ai == AudioInfo()

    def test_empty_file(self, tmp_path):
        empty = tmp_path / "empty.mp3"
        empty.write_bytes(b"")
        ai = extract_audio_info(str(empty))
        assert ai == AudioInfo()


class TestFormatDuration:
    def test_zero(self):
        assert format_duration(0) == "0s"

    def test_seconds(self):
        assert format_duration(45) == "45s"

    def test_minutes(self):
        assert format_duration(125) == "2m05s"

    def test_hours(self):
        assert format_duration(3661) == "1h01m01s"

    def test_large(self):
        assert format_duration(45000) == "12h30m00s"

    def test_negative(self):
        assert format_duration(-5) == "0s"


class TestFormatQuality:
    def test_full_info(self):
        ai = AudioInfo(bitrate=128000, duration=3600, codec="mp3",
                       sample_rate=44100, channels=2)
        result = format_quality(ai)
        assert "MP3" in result
        assert "128kbps" in result
        assert "44.1kHz" in result
        assert "stereo" in result
        assert "1h00m00s" in result

    def test_mono(self):
        ai = AudioInfo(bitrate=64000, duration=60, codec="aac",
                       sample_rate=22050, channels=1)
        result = format_quality(ai)
        assert "mono" in result

    def test_empty_info(self):
        ai = AudioInfo()
        result = format_quality(ai)
        assert result == "0s"
