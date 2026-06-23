# ONNX Self-Test Baseline

## 1. Prerequisites

| Dependency | Minimum Version | Check Command |
|---|---|---|
| Python | 3.11+ | `python --version` |
| ultralytics | 8.x | `python -c "import ultralytics; print(ultralytics.__version__)"` |
| onnx | 1.16+ | `python -c "import onnx; print(onnx.__version__)"` |
| onnxruntime | 1.18+ | `python -c "import onnxruntime; print(onnxruntime.__version__)"` |
| PyTorch | 2.x | `python -c "import torch; print(torch.__version__)"` |

## 2. Manual Procedure

### 2.1 Export Model to ONNX

```bash
python -c "
from ultralytics import YOLO
model = YOLO('yolo11n.pt')
model.export(format='onnx', imgsz=640)
"
```

### 2.2 Load and Inspect ONNX Model

```bash
python -c "
import onnx
model = onnx.load('yolo11n.onnx')
onnx.checker.check_model(model)
print('Inputs:', [(i.name, str(i.type)) for i in model.graph.input])
print('Outputs:', [(o.name, str(o.type)) for o in model.graph.output])
"
```

### 2.3 Create ONNX Runtime Session

```bash
python -c "
import onnxruntime as ort
session = ort.InferenceSession('yolo11n.onnx')
print('Providers:', session.get_providers())
inp = session.get_inputs()[0]
print(f'Input: {inp.name} shape={inp.shape}')
for out in session.get_outputs():
    print(f'Output: {out.name} shape={out.shape}')
"
```

### 2.4 Dummy Inference Shape Check

```bash
python -c "
import numpy as np
import onnxruntime as ort
session = ort.InferenceSession('yolo11n.onnx')
inp = session.get_inputs()[0]
dummy = np.random.randn(1, 3, 640, 640).astype(np.float32)
outputs = session.run(None, {inp.name: dummy})
for o in session.get_outputs():
    print(f'{o.name}: shape={outputs[0].shape}')
"
```

## 3. Known Limitations (Phase 1c)

- **No inference consistency check**: Phase 1c only verifies ONNX model loadability and session creation. Pixel-level output comparison with PyTorch source model belongs to Phase 4.
- **No dynamic batch size**: Export defaults to fixed batch=1.
- **No INT8/FP16 quantization**: Full-precision FP32 only.
- **No checksum verification**: Hash-based integrity checks deferred to Phase 4.

## 4. Pass / Fail Criteria

| Stage | Pass Condition | Fail Indicator |
|---|---|---|
| Export | `.onnx` file exists, size > 0 | File missing or 0 bytes |
| Load | `onnx.load()` + `onnx.checker.check_model()` succeed | `ValidationError` |
| Session | `ort.InferenceSession()` succeeds | `RuntimeError` |
| Shape | Input `[1, 3, 640, 640]`, valid detection output | Unexpected rank/channels |

### Automated Test

```bash
python -m pytest tests/platform/application/test_export_service.py -v -k "onnx"
```

Expected: 3 tests pass or skip gracefully when onnxruntime is unavailable.
