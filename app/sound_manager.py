import wave
import struct
import math
import os
import tempfile
import logging

try:
    from PySide6.QtMultimedia import QSoundEffect
    from PySide6.QtCore import QUrl
    HAS_QT_MULTIMEDIA = True
except ImportError:
    QSoundEffect = None
    QUrl = None
    HAS_QT_MULTIMEDIA = False

logger = logging.getLogger(__name__)


def _synthesize_wav(filepath: str, frequency: float, duration: float,
                    volume: float = 0.3, sample_rate: int = 22050):
    """Generate a simple sine-wave WAV file."""
    n_samples = int(sample_rate * duration)
    data = []
    for i in range(n_samples):
        t = i / sample_rate
        # Simple sine with a short fade-in/out to avoid clicks.
        envelope = 1.0
        fade = int(sample_rate * 0.01)  # 10 ms fade
        if i < fade:
            envelope = i / fade
        elif i > n_samples - fade:
            envelope = (n_samples - i) / fade
        sample = int(volume * envelope * 32767 * math.sin(2 * math.pi * frequency * t))
        data.append(struct.pack('<h', sample))
    with wave.open(filepath, 'w') as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(b''.join(data))


class SoundManager:
    """Manages short sound effects for milestones and achievements.

    Sounds are synthesized at startup as WAV files in a temp directory
    so no external audio files need to be bundled.
    """

    def __init__(self):
        self._enabled = True
        self._sounds: dict = {}
        self._temp_dir: str | None = None
        self._init_sounds()

    def _init_sounds(self):
        try:
            self._temp_dir = tempfile.mkdtemp(prefix="lm_sounds_")

            # Milestone chime: pleasant two-tone ascending.
            path1 = os.path.join(self._temp_dir, "milestone.wav")
            self._synthesize_chime(path1, [(523, 0.12), (659, 0.12), (784, 0.2)])
            self._sounds["milestone"] = self._load(path1)

            # Bonus: short bright note.
            path2 = os.path.join(self._temp_dir, "bonus.wav")
            _synthesize_wav(path2, 880, 0.15, volume=0.25)
            self._sounds["bonus"] = self._load(path2)

            # Achievement: longer triumphant chord.
            path3 = os.path.join(self._temp_dir, "achievement.wav")
            self._synthesize_chime(path3, [(392, 0.08), (523, 0.08), (659, 0.08),
                                           (784, 0.3)], overlap=True)
            self._sounds["achievement"] = self._load(path3)

        except Exception as exc:
            logger.warning("Could not initialize sounds: %s", exc)

    def _synthesize_chime(self, filepath: str, notes: list[tuple[float, float]],
                          overlap: bool = False):
        """Synthesize a multi-note chime."""
        import struct, math
        sample_rate = 22050
        if overlap:
            # Play all notes simultaneously (chord).
            total_duration = max(d for _, d in notes)
            n_samples = int(sample_rate * total_duration)
            data = []
            for i in range(n_samples):
                t = i / sample_rate
                sample = 0.0
                for freq, dur in notes:
                    if t <= dur:
                        env = 1.0
                        fade = int(sample_rate * 0.005)
                        if i < fade:
                            env = i / fade
                        elif i > n_samples - fade:
                            env = (n_samples - i) / fade
                        sample += 0.2 * env * math.sin(2 * math.pi * freq * t)
                sample = max(-1.0, min(1.0, sample))
                data.append(struct.pack('<h', int(sample * 32767 * 0.3)))
        else:
            # Play notes sequentially.
            data = []
            for freq, dur in notes:
                n = int(sample_rate * dur)
                fade = int(sample_rate * 0.008)
                for i in range(n):
                    t = i / sample_rate
                    env = 1.0
                    if i < fade:
                        env = i / fade
                    elif i > n - fade:
                        env = (n - i) / fade
                    sample = int(0.3 * env * 32767 * math.sin(2 * math.pi * freq * t))
                    data.append(struct.pack('<h', sample))
        with wave.open(filepath, 'w') as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(sample_rate)
            wf.writeframes(b''.join(data))

    def _load(self, path: str):
        if not HAS_QT_MULTIMEDIA:
            return None
        try:
            effect = QSoundEffect()
            effect.setSource(QUrl.fromLocalFile(path))
            effect.setVolume(0.5)
            return effect
        except Exception as exc:
            logger.debug("Could not load sound %s: %s", path, exc)
            return None

    @property
    def enabled(self) -> bool:
        return self._enabled

    def set_enabled(self, enabled: bool):
        self._enabled = enabled

    def play(self, kind: str):
        if not self._enabled:
            return
        effect = self._sounds.get(kind)
        if effect is not None:
            try:
                effect.play()
            except Exception as exc:
                logger.debug("Sound play failed: %s", exc)

    def play_milestone(self):
        self.play("milestone")

    def play_bonus(self):
        self.play("bonus")

    def play_achievement(self):
        self.play("achievement")

    def cleanup(self):
        """Remove temporary sound files."""
        if self._temp_dir and os.path.isdir(self._temp_dir):
            try:
                import shutil
                shutil.rmtree(self._temp_dir, ignore_errors=True)
            except Exception:
                pass
