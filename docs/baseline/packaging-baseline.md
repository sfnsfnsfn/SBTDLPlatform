# Packaging Baseline — Phase 0 Freeze

> Captured: 2026-06-07 | Branch: feat/dataset-scan-service | Commit: 663523d

## Environment

| Variable | Value |
|----------|-------|
| Python | 3.12.13 |
| Platform | Windows 11 Pro (10.0.26200) |
| PyInstaller | (project dependency) |

## Spec Files

| File | Target | Size |
|------|--------|------|
| `packaging/pyinstaller/specs/x-anylabeling-win-cpu.spec` | Windows CPU | 197 lines |
| `packaging/pyinstaller/specs/x-anylabeling-win-gpu.spec` | Windows GPU | ~200 lines |
| `packaging/pyinstaller/specs/x-anylabeling-linux-cpu.spec` | Linux CPU | ~200 lines |
| `packaging/pyinstaller/specs/x-anylabeling-linux-gpu.spec` | Linux GPU (CUDA) | ~200 lines |
| `packaging/pyinstaller/specs/x-anylabeling-macos.spec` | macOS | ~200 lines |

## Key Configuration (win-cpu.spec)

- **Entry point**: `anylabeling/app.py`
- **Name pattern**: `X-AnyLabeling-v{version}-CPU`
- **Console**: `False` (windowed app)
- **MSVC runtime DLLs**: Bundled automatically (msvcp140, vcruntime140, etc.)
- **ONNX Runtime**: DLLs collected from installed package
- **matplotlib**: Data files + hidden imports (backend_agg, font_manager, mathtext)
- **Runtime hook**: `packaging/pyinstaller/runtime_hooks/ort_dll_bootstrap.py`
- **UPX**: Disabled
- **Debug**: Disabled
- **Strip**: Disabled

## Trial Build Command

```bash
# Windows CPU
pyinstaller packaging/pyinstaller/specs/x-anylabeling-win-cpu.spec

# Windows GPU
pyinstaller packaging/pyinstaller/specs/x-anylabeling-win-gpu.spec
```

## Build Verification Steps

1. Run PyInstaller with the spec file
2. Locate executable in `dist/`
3. Launch executable and verify:
   - Window opens without errors
   - Navigation bar renders (8 steps)
   - Can create/open a project
4. Record hash of resulting `.exe`

## Notes

- PyInstaller build NOT executed during Phase 0 (freeze phase — capture config only)
- Actual build verification deferred to release pipeline
- ONNX Runtime DLL path detection depends on the installed `onnxruntime` package
