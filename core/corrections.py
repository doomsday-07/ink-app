import os
import csv
import json
import shutil
from datetime import datetime
from pathlib import Path
from PIL import Image
from PyQt6.QtGui import QImage


class CorrectionStore:
    """Stores handwriting corrections (image + correct text) for later training.

    Dataset structure:
        dataset/
        ├── images/
        │   ├── img_000001.png
        │   ├── img_000002.png
        │   └── ...
        └── labels.csv
            (columns: image, text, original_prediction, timestamp, language)
    """

    def __init__(self, dataset_dir: str = None):
        if dataset_dir is None:
            dataset_dir = os.path.join(os.path.expanduser("~"), "ink-app-dataset")
        self._dataset_dir = dataset_dir
        self._images_dir = os.path.join(dataset_dir, "images")
        self._labels_file = os.path.join(dataset_dir, "labels.csv")
        self._ensure_dirs()

    def _ensure_dirs(self):
        os.makedirs(self._images_dir, exist_ok=True)
        if not os.path.exists(self._labels_file):
            with open(self._labels_file, "w", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                writer.writerow(["image", "text", "original_prediction", "timestamp", "language"])

    def get_dataset_dir(self) -> str:
        return self._dataset_dir

    def get_count(self) -> int:
        if not os.path.exists(self._labels_file):
            return 0
        with open(self._labels_file, "r", encoding="utf-8") as f:
            return sum(1 for _ in csv.DictReader(f))

    def _next_image_name(self) -> str:
        max_id = 0
        if os.path.exists(self._images_dir):
            for fname in os.listdir(self._images_dir):
                if fname.startswith("img_") and fname.endswith(".png"):
                    try:
                        num = int(fname[4:10])
                        max_id = max(max_id, num)
                    except (ValueError, IndexError):
                        pass
        return f"img_{max_id + 1:06d}.png"

    def save_correction(
        self,
        image: QImage,
        corrected_text: str,
        original_prediction: str = "",
        language: str = "en",
    ) -> str:
        image_name = self._next_image_name()
        image_path = os.path.join(self._images_dir, image_name)

        image.save(image_path, "PNG")

        with open(self._labels_file, "a", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow([
                image_name,
                corrected_text,
                original_prediction,
                datetime.now().isoformat(),
                language,
            ])

        return image_path

    def save_correction_from_pil(
        self,
        pil_image: Image.Image,
        corrected_text: str,
        original_prediction: str = "",
        language: str = "en",
    ) -> str:
        image_name = self._next_image_name()
        image_path = os.path.join(self._images_dir, image_name)

        pil_image.save(image_path, "PNG")

        with open(self._labels_file, "a", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow([
                image_name,
                corrected_text,
                original_prediction,
                datetime.now().isoformat(),
                language,
            ])

        return image_path

    def get_all_corrections(self) -> list[dict]:
        """Load all corrections from the dataset."""
        if not os.path.exists(self._labels_file):
            return []
        corrections = []
        with open(self._labels_file, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                row["image_path"] = os.path.join(self._images_dir, row["image"])
                corrections.append(row)
        return corrections

    def export_for_training(self, output_dir: str) -> str:
        """Export dataset in Thulium training format.

        Creates:
            output_dir/
            ├── train/
            │   ├── img_000001.png
            │   └── ...
            └── train.csv
                (columns: name, text)
        """
        os.makedirs(os.path.join(output_dir, "train"), exist_ok=True)

        corrections = self.get_all_corrections()
        csv_path = os.path.join(output_dir, "train.csv")

        with open(csv_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(["name", "text"])
            for c in corrections:
                src = c["image_path"]
                dst = os.path.join(output_dir, "train", c["image"])
                if os.path.exists(src):
                    shutil.copy2(src, dst)
                writer.writerow([c["image"], c["text"]])

        return csv_path

    def delete_correction(self, image_name: str):
        """Delete a specific correction from the dataset."""
        image_path = os.path.join(self._images_dir, image_name)
        if os.path.exists(image_path):
            os.remove(image_path)

        corrections = self.get_all_corrections()
        with open(self._labels_file, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(["image", "text", "original_prediction", "timestamp", "language"])
            for c in corrections:
                if c["image"] != image_name:
                    writer.writerow([c["image"], c["text"], c["original_prediction"],
                                     c["timestamp"], c["language"]])

    def clear(self):
        """Clear all corrections from the dataset."""
        shutil.rmtree(self._images_dir, ignore_errors=True)
        os.makedirs(self._images_dir, exist_ok=True)
        with open(self._labels_file, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(["image", "text", "original_prediction", "timestamp", "language"])
