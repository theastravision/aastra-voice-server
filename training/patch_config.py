"""
Auto-patch the Kokoro/StyleTTS2 config.yml with our dataset paths.
"""
import sys
from pathlib import Path
import yaml

def patch_config(config_path: str, data_dir: str):
    p = Path(config_path)
    if not p.exists():
        print(f"Error: Config not found at {config_path}")
        sys.exit(1)
        
    with open(p, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)
        
    # Update paths
    dataset_path = Path(data_dir)
    config["train_data"] = str((dataset_path / "metadata.csv").absolute()).replace("\\", "/")
    config["val_data"] = str((dataset_path / "metadata.csv").absolute()).replace("\\", "/")
    config["root_dir"] = str((dataset_path / "wavs").absolute()).replace("\\", "/")
    
    # Optional: reduce batch size for safety on Windows (prevents OOM on 24GB VRAM)
    if "batch_size" in config:
        config["batch_size"] = min(config.get("batch_size", 8), 4)
        
    with open(p, "w", encoding="utf-8") as f:
        yaml.dump(config, f, default_flow_style=False)
        
    print(f"Successfully patched {config_path} with dataset paths.")

if __name__ == "__main__":
    patch_config(sys.argv[1], sys.argv[2])
