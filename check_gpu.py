"""Check GPU availability and PyTorch setup."""

import torch

print("=" * 60)
print("GPU AVAILABILITY CHECK")
print("=" * 60)

print(f"\nPyTorch Version: {torch.__version__}")
print(f"CUDA Available: {torch.cuda.is_available()}")

if torch.cuda.is_available():
    print(f"CUDA Version: {torch.version.cuda}")
    print(f"GPU Count: {torch.cuda.device_count()}")
    print(f"GPU Name: {torch.cuda.get_device_name(0)}")
    print(f"GPU Memory: {torch.cuda.get_device_properties(0).total_memory / 1e9:.2f} GB")
    print(f"\n✅ GPU is available and ready!")
else:
    print("\n❌ GPU is NOT available!")
    print("\nPossible causes:")
    print("1. NVIDIA GPU not installed")
    print("2. CUDA not installed")
    print("3. PyTorch CPU version installed (not GPU version)")
    print("4. NVIDIA drivers not installed")
    print("\nTo fix:")
    print("1. Check if you have an NVIDIA GPU: nvidia-smi")
    print("2. Install CUDA Toolkit from NVIDIA")
    print("3. Reinstall PyTorch with GPU support:")
    print("   pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu118")

print("\n" + "=" * 60)

