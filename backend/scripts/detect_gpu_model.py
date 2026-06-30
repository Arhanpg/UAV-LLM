"""VRAM-tier → recommended Ollama model (Section 4)."""

import subprocess
import sys


def detect_vram_gb() -> float | None:
    try:
        out = subprocess.check_output(
            ["nvidia-smi", "--query-gpu=memory.total", "--format=csv,noheader,nounits"],
            text=True,
            stderr=subprocess.DEVNULL,
        )
        mb = float(out.strip().split("\n")[0])
        return mb / 1024.0
    except (FileNotFoundError, subprocess.CalledProcessError, ValueError, IndexError):
        return None


def recommend_model(vram_gb: float | None) -> str:
    if vram_gb is None:
        return "phi4-mini"
    if vram_gb < 5.5:
        return "qwen3:4b"
    if vram_gb < 7.5:
        return "qwen3:8b"
    return "qwen3:8b"


if __name__ == "__main__":
    vram = detect_vram_gb()
    model = recommend_model(vram)
    print(f"Detected VRAM: {vram:.1f} GB" if vram else "No NVIDIA GPU detected")
    print(f"Recommended OLLAMA_MODEL={model}")
    sys.exit(0)
