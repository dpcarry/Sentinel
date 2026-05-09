# Models

This directory is the runtime location for local model files.

Required for the default Raspberry Pi pipeline:

```text
lost_items_yolo_models/best.onnx
lost_items_yolo_models/metadata.yaml
xiao_classifier/classifier.json
```

Optional for local speech-to-text:

```text
vosk-model-small-en-us-0.15/
```

Large downloaded model directories and alternate training exports are ignored by git. Keep only the selected runtime model files in version control.
