@echo off
echo =======================================================
echo   Kokoro TTS Windows-Safe Training Pipeline Launcher
echo =======================================================
echo.
echo Step 1: Processing Dataset (This will take hours for 20 hours of MP3s)
echo -------------------------------------------------------
python training\prep_dataset.py --input "C:\Users\cogni\Downloads\kokoro - hindi-dataset" --output "C:\Users\cogni\Downloads\kokoro-processed"
if %errorlevel% neq 0 exit /b %errorlevel%

echo.
echo Step 2: Patching Training Configuration
echo -------------------------------------------------------
python training\patch_config.py "C:\Users\cogni\Downloads\kokoro-deutsch\Configs\config.yml" "C:\Users\cogni\Downloads\kokoro-processed"
if %errorlevel% neq 0 exit /b %errorlevel%

echo.
echo Step 3: Launching Stage 1 Training (Decoder & Aligner)
echo -------------------------------------------------------
echo WARNING: This will take a very long time. Do not close this window.
python training\train_windows.py first --repo-dir "C:\Users\cogni\Downloads\kokoro-deutsch" --config "C:\Users\cogni\Downloads\kokoro-deutsch\Configs\config.yml"
if %errorlevel% neq 0 exit /b %errorlevel%

echo.
echo Step 4: Launching Stage 2 Training (Prosody Predictor)
echo -------------------------------------------------------
python training\train_windows.py second --repo-dir "C:\Users\cogni\Downloads\kokoro-deutsch" --config "C:\Users\cogni\Downloads\kokoro-deutsch\Configs\config.yml"

echo.
echo =======================================================
echo   TRAINING COMPLETE!
echo =======================================================
pause
