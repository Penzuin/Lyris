@echo off
rem Opens the Lyris project in Unreal Engine 5.8 (no .uproject file association needed).
start "" "C:\Program Files\Epic Games\UE_5.8\Engine\Binaries\Win64\UnrealEditor.exe" "%~dp0Lyris.uproject"
