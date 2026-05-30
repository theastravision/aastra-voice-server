"""
Windows-Safe Kokoro Training Launcher

PyTorch multiprocessing on Windows using DataLoader is notorious for deadlocks 
and freezes because Windows lacks the fork() system call. 
If you try to run the community Kokoro/StyleTTS2 training scripts natively on Windows, 
your machine will hang indefinitely.

This script acts as a safe wrapper:
1. It injects torch.multiprocessing.freeze_support() (Required for Windows).
2. It monkey-patches torch.utils.data.DataLoader to FORCE num_workers=0, 
   ensuring data is loaded on the main thread, which completely eliminates the hanging bug.
"""

import sys
import os
import argparse
from pathlib import Path

def patch_dataloader():
    """Monkey-patch PyTorch DataLoader to force num_workers=0."""
    import torch
    from torch.utils.data import DataLoader
    
    original_init = DataLoader.__init__
    
    def safe_init(self, *args, **kwargs):
        if 'num_workers' in kwargs and kwargs['num_workers'] > 0:
            print(f"  [WINDOWS PATCH] Intercepted DataLoader creation. Forcing num_workers=0 (was {kwargs['num_workers']}) to prevent freezing.")
            kwargs['num_workers'] = 0
        original_init(self, *args, **kwargs)
        
    DataLoader.__init__ = safe_init

def main():
    parser = argparse.ArgumentParser(description="Windows-safe Kokoro Training Launcher")
    parser.add_argument("stage", choices=["first", "second"], help="Which training stage to run (first or second)")
    parser.add_argument("--repo-dir", type=str, required=True, help="Path to the cloned kokoro-deutsch repository")
    parser.add_argument("--config", type=str, required=True, help="Path to the config.yml file")
    
    args, unknown = parser.parse_known_args()
    
    repo_path = Path(args.repo_dir).resolve()
    if not repo_path.exists() or not (repo_path / "train_first.py").exists():
        print(f"ERROR: Cannot find training scripts in {repo_path}")
        print("Please clone the repository first: git clone --recurse-submodules https://github.com/semidark/kokoro-deutsch")
        sys.exit(1)
        
    # Add repo to python path so we can import its modules
    sys.path.insert(0, str(repo_path))
    
    # 1. Apply Windows safety patches
    patch_dataloader()
    
    # 2. Re-route sys.argv so the target script parses the right arguments
    sys.argv = [f"train_{args.stage}.py", "--config_path", args.config] + unknown
    
    print(f"\n========================================================")
    print(f" Launching Kokoro Stage '{args.stage}' Training (Windows Safe)")
    print(f"========================================================")
    
    if args.stage == "first":
        import train_first
        # The script usually runs when imported if it's at the global level, 
        # or we might need to call its main() function. 
        # In StyleTTS2/Kokoro repos, execution usually happens under if __name__ == "__main__":
        # So we manually trigger the global execution or call main()
        if hasattr(train_first, 'main'):
            train_first.main()
        else:
            print("WARNING: train_first.py does not have a main() function. It may need to be run directly.")
    else:
        import train_second
        if hasattr(train_second, 'main'):
            train_second.main()
        else:
            print("WARNING: train_second.py does not have a main() function. It may need to be run directly.")

if __name__ == "__main__":
    # REQUIRED FOR WINDOWS
    import torch
    torch.multiprocessing.freeze_support()
    main()
