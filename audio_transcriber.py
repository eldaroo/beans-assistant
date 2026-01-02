"""
Audio transcription module using OpenAI Whisper (local).

Handles downloading and transcribing audio files from WhatsApp.
"""
import os
import tempfile
import requests
from typing import Optional
import whisper


class AudioTranscriber:
    """Transcribe audio files using Whisper model."""

    def __init__(self, model_name: str = "base"):
        """
        Initialize Whisper transcriber.

        Args:
            model_name: Whisper model size (tiny, base, small, medium, large)
                       - tiny: fastest, least accurate (~1GB RAM)
                       - base: good balance (~1GB RAM) - RECOMMENDED
                       - small: better accuracy (~2GB RAM)
                       - medium: very good (~5GB RAM)
                       - large: best accuracy (~10GB RAM)
        """
        print(f"Loading Whisper model '{model_name}'...")
        self.model = whisper.load_model(model_name)
        print(f"Whisper model '{model_name}' loaded successfully")

    def download_audio_file(self, url: str, output_path: str) -> bool:
        """
        Download audio file from URL.

        Args:
            url: Audio file URL
            output_path: Path to save the audio file

        Returns:
            True if downloaded successfully
        """
        try:
            print(f"[AUDIO] Downloading from URL: {url[:100]}...")
            response = requests.get(url, timeout=30)
            response.raise_for_status()

            file_size = len(response.content)
            print(f"[AUDIO] Download complete. File size: {file_size} bytes")

            with open(output_path, 'wb') as f:
                f.write(response.content)

            print(f"[AUDIO] Saved to: {output_path}")
            return True

        except requests.exceptions.RequestException as e:
            print(f"[AUDIO ERROR] Download failed: {e}")
            import traceback
            traceback.print_exc()
            return False

    def transcribe_audio_file(self, audio_path: str, language: str = "es") -> Optional[str]:
        """
        Transcribe audio file to text.

        Args:
            audio_path: Path to audio file
            language: Language code (es for Spanish, en for English, etc.)

        Returns:
            Transcribed text or None if failed
        """
        try:
            import os
            file_size = os.path.getsize(audio_path)
            print(f"[AUDIO] Starting transcription...")
            print(f"[AUDIO] File: {audio_path}")
            print(f"[AUDIO] Size: {file_size} bytes")
            print(f"[AUDIO] Language: {language}")

            # Transcribe with Whisper
            import time
            start_time = time.time()

            result = self.model.transcribe(
                audio_path,
                language=language,
                fp16=False  # Use FP32 for better CPU compatibility
            )

            duration = time.time() - start_time
            transcription = result["text"].strip()

            print(f"[AUDIO] Transcription complete in {duration:.2f}s")
            print(f"[AUDIO] Result: \"{transcription}\"")

            return transcription

        except Exception as e:
            print(f"[AUDIO ERROR] Transcription failed: {e}")
            import traceback
            traceback.print_exc()
            return None

    def transcribe_from_url(self, url: str, language: str = "es") -> Optional[str]:
        """
        Download and transcribe audio from URL.

        Args:
            url: Audio file URL
            language: Language code (es for Spanish)

        Returns:
            Transcribed text or None if failed
        """
        print(f"\n{'='*60}")
        print(f"[AUDIO] Starting audio transcription workflow")
        print(f"{'='*60}")

        # Create temporary file
        with tempfile.NamedTemporaryFile(suffix=".ogg", delete=False) as temp_file:
            temp_path = temp_file.name

        print(f"[AUDIO] Temp file created: {temp_path}")

        try:
            # Download audio
            print(f"[AUDIO] Step 1: Downloading audio...")
            if not self.download_audio_file(url, temp_path):
                print(f"[AUDIO ERROR] Download step failed")
                return None

            # Transcribe
            print(f"[AUDIO] Step 2: Transcribing audio...")
            transcription = self.transcribe_audio_file(temp_path, language)

            if transcription:
                print(f"[AUDIO] ✓ Transcription successful")
                print(f"{'='*60}\n")
            else:
                print(f"[AUDIO ERROR] Transcription step failed")
                print(f"{'='*60}\n")

            return transcription

        except Exception as e:
            print(f"[AUDIO ERROR] Unexpected error in transcription workflow: {e}")
            import traceback
            traceback.print_exc()
            print(f"{'='*60}\n")
            return None

        finally:
            # Clean up temporary file
            if os.path.exists(temp_path):
                os.remove(temp_path)
                print(f"[AUDIO] Temp file cleaned up")


# Global instance (lazy loaded)
_transcriber: Optional[AudioTranscriber] = None


def get_transcriber(model_name: str = "base") -> AudioTranscriber:
    """
    Get or create global AudioTranscriber instance.

    Args:
        model_name: Whisper model size

    Returns:
        AudioTranscriber instance
    """
    global _transcriber
    if _transcriber is None:
        _transcriber = AudioTranscriber(model_name)
    return _transcriber


def transcribe_audio_from_url(url: str, language: str = "es") -> Optional[str]:
    """
    Convenience function to transcribe audio from URL.

    Args:
        url: Audio file URL
        language: Language code

    Returns:
        Transcribed text or None if failed
    """
    transcriber = get_transcriber()
    return transcriber.transcribe_from_url(url, language)
