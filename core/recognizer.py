import os
import tempfile
from pathlib import Path
from PyQt6.QtGui import QImage


CUSTOM_MODEL_DIR = Path(__file__).parent.parent / "custom_model"


class HandwritingRecognizer:
    """Handwriting-to-text recognizer with multiple engine support.

    Engines:
    - 'vision': macOS Vision framework (default, fast, English-focused)
    - 'easyocr': EasyOCR (multilingual, 80+ languages)
    - 'custom': Your own CNN+BiLSTM+CTC model (requires training first)
    """

    def __init__(self, engine: str = "vision"):
        self._engine = engine
        self._easyocr_reader = None
        self._custom_model = None
        self._custom_vocab = None

    def set_engine(self, engine: str):
        if engine not in ("vision", "easyocr", "custom"):
            raise ValueError(f"Unknown engine: {engine}")
        self._engine = engine

    def get_engine(self) -> str:
        return self._engine

    @staticmethod
    def is_easyocr_available() -> bool:
        try:
            import easyocr
            return True
        except ImportError:
            return False

    @staticmethod
    def is_custom_model_available() -> bool:
        return (CUSTOM_MODEL_DIR / "model.pt").exists()

    @staticmethod
    def has_training_deps() -> bool:
        try:
            import torch
            return True
        except ImportError:
            return False

    def _get_easyocr_reader(self, language: str = "en"):
        if self._easyocr_reader is None:
            import easyocr
            self._easyocr_reader = easyocr.Reader([language], gpu=False)
        return self._easyocr_reader

    def _load_custom_model(self):
        import torch
        if self._custom_model is not None:
            return
        from core.ocr_model import CustomOCRModel, VOCABULARY

        checkpoint = torch.load(
            CUSTOM_MODEL_DIR / "model.pt",
            map_location="cpu",
            weights_only=False,
        )
        self._custom_model = CustomOCRModel()
        self._custom_model.load_state_dict(checkpoint["model_state_dict"])
        self._custom_model.eval()
        self._custom_vocab = checkpoint.get("vocabulary", VOCABULARY)

    def is_loaded(self) -> bool:
        return True

    def _preprocess_custom(self, pil_image) -> "torch.Tensor":
        import numpy as np
        import torch
        from PIL import Image
        img = pil_image.convert("L")
        arr = np.array(img, dtype=np.float32)

        # Binarize to match training preprocessing
        threshold = np.mean(arr) * 0.6
        binary = (arr < threshold).astype(np.float32) * 255.0

        # Find ink bounding box and crop
        rows = np.any(binary > 0, axis=1)
        cols = np.any(binary > 0, axis=0)
        if rows.any() and cols.any():
            rmin, rmax = np.where(rows)[0][[0, -1]]
            cmin, cmax = np.where(cols)[0][[0, -1]]
            margin = 4
            rmin = max(0, rmin - margin)
            rmax = min(binary.shape[0] - 1, rmax + margin)
            cmin = max(0, cmin - margin)
            cmax = min(binary.shape[1] - 1, cmax + margin)
            binary = binary[rmin:rmax + 1, cmin:cmax + 1]

        img = Image.fromarray(binary.astype(np.uint8), "L")
        w, h = img.size
        new_w = max(1, int(w * (32 / h)))
        img = img.resize((new_w, 32), Image.Resampling.LANCZOS)
        tensor = torch.tensor(list(img.getdata()), dtype=torch.float32).view(1, 32, new_w)
        return tensor.unsqueeze(0) / 255.0

    def _preprocess(self, pil_image):
        from PIL import Image
        img = pil_image.convert("RGB")
        w, h = img.size
        if h > 0 and h < 50:
            scale = 50 / h
            img = img.resize((int(w * scale), int(h * scale)), Image.Resampling.LANCZOS)
        return img

    def _recognize_with_vision(self, pil_image) -> str:
        import Vision
        import Quartz

        tmp_path = tempfile.mktemp(suffix=".tiff")
        try:
            pil_image.save(tmp_path, "TIFF")
            image_url = Quartz.CFURLCreateFromFileSystemRepresentation(
                None, tmp_path.encode("utf-8"), len(tmp_path.encode("utf-8")), False
            )
            source = Quartz.CGImageSourceCreateWithURL(image_url, None)
            cg_image = Quartz.CGImageSourceCreateImageAtIndex(source, 0, None)

            request_handler = Vision.VNImageRequestHandler.alloc().initWithCGImage_options_(
                cg_image, {}
            )

            request = Vision.VNRecognizeTextRequest.alloc().init()
            request.setRecognitionLevel_(Vision.VNRequestTextRecognitionLevelAccurate)
            request.setUsesLanguageCorrection_(True)

            success = request_handler.performRequests_error_([request], None)
            if not success[0]:
                return ""

            results = request.results()
            if not results:
                return ""

            texts = []
            for observation in results:
                candidate = observation.topCandidates_(1)
                if candidate:
                    texts.append(candidate[0].string())

            return " ".join(texts)
        finally:
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)

    def _recognize_with_easyocr(self, pil_image, language: str = "en") -> str:
        import numpy as np

        reader = self._get_easyocr_reader(language)
        img_array = np.array(pil_image)
        results = reader.readtext(img_array, detail=0)
        return " ".join(results)

    def _recognize_with_custom(self, pil_image) -> str:
        import torch
        self._load_custom_model()
        tensor = self._preprocess_custom(pil_image)
        with torch.no_grad():
            output = self._custom_model(tensor)
        from core.ocr_model import CustomOCRModel, BLANK_INDEX
        preds = output.argmax(dim=2)
        indices = []
        prev = -1
        for idx in preds[0].tolist():
            if idx != prev and idx != BLANK_INDEX:
                indices.append(idx)
            prev = idx
        return CustomOCRModel.indices_to_text(indices)

    def recognize_from_image(self, pil_image, language: str = "en") -> str:
        if self._engine == "custom":
            return self._recognize_with_custom(pil_image)
        processed = self._preprocess(pil_image)
        if self._engine == "easyocr":
            return self._recognize_with_easyocr(processed, language)
        return self._recognize_with_vision(processed)

    def recognize_from_qimage(self, qimage: QImage, language: str = "en") -> str:
        from PIL import Image
        tmp_path = tempfile.mktemp(suffix=".png")
        try:
            qimage.save(tmp_path, "PNG")
            pil_image = Image.open(tmp_path).convert("RGB")
            return self.recognize_from_image(pil_image, language)
        finally:
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)

    def recognize_from_file(self, filepath: str, language: str = "en") -> str:
        from PIL import Image
        pil_image = Image.open(filepath).convert("RGB")
        return self.recognize_from_image(pil_image, language)
