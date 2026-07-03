"""Hardware profiler for Auralynq ModelFit Index.

Detects CPU, RAM, GPU, VRAM, backend support, Ollama, HF cache, and disk.
All detection is read-only and purely local — no network calls, no telemetry.
"""

from __future__ import annotations

import os
import platform
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class GPUInfo:
    vendor: str  # "nvidia" | "apple" | "amd" | "intel" | "unknown"
    name: str
    vram_gb: float
    backend: str  # "cuda" | "metal" | "rocm" | "cpu"
    device_index: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "vendor": self.vendor,
            "name": self.name,
            "vram_gb": self.vram_gb,
            "backend": self.backend,
            "device_index": self.device_index,
        }


@dataclass
class HardwareProfile:
    os_name: str = ""
    os_version: str = ""
    python_version: str = ""
    cpu_model: str = ""
    cpu_cores_physical: int = 0
    cpu_cores_logical: int = 0
    ram_gb: float = 0.0
    gpus: list[GPUInfo] = field(default_factory=list)
    disk_free_gb: float = 0.0
    ollama_available: bool = False
    ollama_version: str | None = None
    hf_available: bool = False
    hf_cache_path: str | None = None
    in_container: bool = False
    cuda_available: bool = False
    cuda_version: str | None = None
    metal_available: bool = False
    rocm_available: bool = False
    warnings: list[str] = field(default_factory=list)

    @property
    def best_backend(self) -> str:
        if self.cuda_available:
            return "cuda"
        if self.metal_available:
            return "metal"
        if self.rocm_available:
            return "rocm"
        return "cpu"

    @property
    def total_vram_gb(self) -> float:
        return sum(g.vram_gb for g in self.gpus)

    def to_dict(self) -> dict[str, Any]:
        return {
            "os": {"name": self.os_name, "version": self.os_version},
            "python_version": self.python_version,
            "cpu": {
                "model": self.cpu_model,
                "cores_physical": self.cpu_cores_physical,
                "cores_logical": self.cpu_cores_logical,
            },
            "ram_gb": round(self.ram_gb, 1),
            "gpus": [g.to_dict() for g in self.gpus],
            "total_vram_gb": round(self.total_vram_gb, 1),
            "disk_free_gb": round(self.disk_free_gb, 1),
            "best_backend": self.best_backend,
            "cuda_available": self.cuda_available,
            "cuda_version": self.cuda_version,
            "metal_available": self.metal_available,
            "rocm_available": self.rocm_available,
            "ollama_available": self.ollama_available,
            "ollama_version": self.ollama_version,
            "hf_available": self.hf_available,
            "hf_cache_path": self.hf_cache_path,
            "in_container": self.in_container,
            "warnings": self.warnings,
        }


def _detect_cpu() -> tuple[str, int, int]:
    """Return (model, physical_cores, logical_cores)."""
    model = platform.processor() or "unknown"
    logical = os.cpu_count() or 1
    physical = logical

    try:
        import psutil  # optional

        physical = psutil.cpu_count(logical=False) or logical
    except ImportError:
        # Fallback: parse /proc/cpuinfo on Linux
        if platform.system() == "Linux":
            try:
                with open("/proc/cpuinfo") as f:
                    content = f.read()
                models = [
                    line.split(":", 1)[1].strip()
                    for line in content.splitlines()
                    if line.startswith("model name")
                ]
                if models:
                    model = models[0]
                cores = set()
                for line in content.splitlines():
                    if line.startswith("core id"):
                        cores.add(line.split(":", 1)[1].strip())
                physical = len(cores) if cores else logical
            except OSError:
                pass

    return model, physical, logical


def _detect_ram_gb() -> float:
    try:
        import psutil

        return psutil.virtual_memory().total / (1024**3)
    except ImportError:
        pass
    if platform.system() == "Linux":
        try:
            with open("/proc/meminfo") as f:
                for line in f:
                    if line.startswith("MemTotal:"):
                        kb = int(line.split()[1])
                        return round(kb / (1024**2), 1)
        except OSError:
            pass
    return 0.0


def _detect_nvidia_gpus() -> list[GPUInfo]:
    gpus: list[GPUInfo] = []
    try:
        result = subprocess.run(
            [
                "nvidia-smi",
                "--query-gpu=name,memory.total",
                "--format=csv,noheader,nounits",
            ],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode == 0:
            for i, line in enumerate(result.stdout.strip().splitlines()):
                parts = line.split(",")
                if len(parts) == 2:
                    name = parts[0].strip()
                    vram_mb = float(parts[1].strip())
                    gpus.append(
                        GPUInfo(
                            vendor="nvidia",
                            name=name,
                            vram_gb=round(vram_mb / 1024, 1),
                            backend="cuda",
                            device_index=i,
                        )
                    )
    except (FileNotFoundError, subprocess.TimeoutExpired, ValueError):
        pass
    return gpus


def _detect_apple_silicon() -> list[GPUInfo]:
    if platform.system() != "Darwin":
        return []
    try:
        result = subprocess.run(
            ["system_profiler", "SPDisplaysDataType"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode == 0:
            # Apple Silicon shares RAM; estimate from total
            ram_gb = _detect_ram_gb()
            gpu_name = platform.processor() or "Apple Silicon"
            # Heuristic: Apple unified memory — GPU can use up to ~75% RAM
            vram_est = round(ram_gb * 0.75, 1)
            return [
                GPUInfo(
                    vendor="apple",
                    name=gpu_name,
                    vram_gb=vram_est,
                    backend="metal",
                    device_index=0,
                )
            ]
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass
    return []


def _detect_amd_gpus() -> list[GPUInfo]:
    gpus: list[GPUInfo] = []
    try:
        result = subprocess.run(
            ["rocm-smi", "--showmeminfo", "vram", "--csv"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode == 0:
            lines = result.stdout.strip().splitlines()
            for i, line in enumerate(lines[1:], 0):
                parts = line.split(",")
                if len(parts) >= 2:
                    try:
                        vram_bytes = int(parts[1].strip())
                        gpus.append(
                            GPUInfo(
                                vendor="amd",
                                name=f"AMD GPU {i}",
                                vram_gb=round(vram_bytes / (1024**3), 1),
                                backend="rocm",
                                device_index=i,
                            )
                        )
                    except ValueError:
                        pass
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass
    return gpus


def _detect_gpus() -> tuple[list[GPUInfo], bool, str | None, bool, bool]:
    """Return (gpus, cuda_avail, cuda_version, metal_avail, rocm_avail)."""
    cuda_available = False
    cuda_version: str | None = None
    metal_available = False
    rocm_available = False

    nvidia = _detect_nvidia_gpus()
    if nvidia:
        cuda_available = True
        try:
            r = subprocess.run(["nvcc", "--version"], capture_output=True, text=True, timeout=5)
            for line in r.stdout.splitlines():
                if "release" in line.lower():
                    cuda_version = line.strip()
                    break
        except (FileNotFoundError, subprocess.TimeoutExpired):
            cuda_version = "detected (version unknown)"
        return nvidia, cuda_available, cuda_version, metal_available, rocm_available

    # Apple Metal
    if platform.system() == "Darwin":
        apple = _detect_apple_silicon()
        if apple:
            metal_available = True
            return apple, cuda_available, cuda_version, metal_available, rocm_available

    # AMD ROCm
    amd = _detect_amd_gpus()
    if amd:
        rocm_available = True
        return amd, cuda_available, cuda_version, metal_available, rocm_available

    # Try torch as last resort
    try:
        import torch

        if torch.cuda.is_available():
            cuda_available = True
            cuda_version = torch.version.cuda
            count = torch.cuda.device_count()
            gpus: list[GPUInfo] = []
            for i in range(count):
                props = torch.cuda.get_device_properties(i)
                gpus.append(
                    GPUInfo(
                        vendor="nvidia",
                        name=props.name,
                        vram_gb=round(props.total_memory / (1024**3), 1),
                        backend="cuda",
                        device_index=i,
                    )
                )
            return gpus, cuda_available, cuda_version, metal_available, rocm_available
        if hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
            metal_available = True
            ram_gb = _detect_ram_gb()
            return (
                [GPUInfo("apple", "Apple MPS", round(ram_gb * 0.75, 1), "metal", 0)],
                cuda_available,
                cuda_version,
                metal_available,
                rocm_available,
            )
    except ImportError:
        pass

    return [], cuda_available, cuda_version, metal_available, rocm_available


def _detect_ollama() -> tuple[bool, str | None]:
    if not shutil.which("ollama"):
        return False, None
    try:
        r = subprocess.run(["ollama", "--version"], capture_output=True, text=True, timeout=5)
        version = r.stdout.strip() or r.stderr.strip() or "unknown"
        return True, version
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False, None


def _detect_hf() -> tuple[bool, str | None]:
    cache_env = os.environ.get("HF_HOME") or os.environ.get("HUGGINGFACE_HUB_CACHE")
    default = Path.home() / ".cache" / "huggingface"
    cache_path = Path(cache_env) if cache_env else default
    available = cache_path.exists()
    return available, str(cache_path) if available else None


def _detect_disk_free_gb() -> float:
    try:
        usage = shutil.disk_usage(Path.home())
        return round(usage.free / (1024**3), 1)
    except OSError:
        return 0.0


def _in_container() -> bool:
    return (
        Path("/.dockerenv").exists()
        or os.environ.get("CONTAINER") == "podman"
        or "KUBERNETES_SERVICE_HOST" in os.environ
    )


def probe_hardware() -> HardwareProfile:
    """Collect a full hardware profile. Never raises — missing data → 0/empty."""
    warnings: list[str] = []

    cpu_model, cpu_physical, cpu_logical = _detect_cpu()
    ram_gb = _detect_ram_gb()
    if ram_gb == 0.0:
        warnings.append("Could not detect RAM size.")

    gpus, cuda_avail, cuda_ver, metal_avail, rocm_avail = _detect_gpus()
    if not gpus:
        warnings.append("No GPU detected — inference will use CPU only.")

    disk_free = _detect_disk_free_gb()
    if disk_free < 10:
        warnings.append(f"Low disk space: {disk_free:.1f} GB free.")

    ollama_avail, ollama_ver = _detect_ollama()
    hf_avail, hf_path = _detect_hf()

    return HardwareProfile(
        os_name=platform.system(),
        os_version=platform.version(),
        python_version=sys.version.split()[0],
        cpu_model=cpu_model,
        cpu_cores_physical=cpu_physical,
        cpu_cores_logical=cpu_logical,
        ram_gb=round(ram_gb, 1),
        gpus=gpus,
        disk_free_gb=disk_free,
        ollama_available=ollama_avail,
        ollama_version=ollama_ver,
        hf_available=hf_avail,
        hf_cache_path=hf_path,
        in_container=_in_container(),
        cuda_available=cuda_avail,
        cuda_version=cuda_ver,
        metal_available=metal_avail,
        rocm_available=rocm_avail,
        warnings=warnings,
    )
