import torch
import torch.nn as nn


VOCABULARY = " abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789.,!?-'\":;()/<>{}[]|~₹@#$%^&*+="
BLANK_INDEX = len(VOCABULARY)


def char_to_index(c: str) -> int:
    idx = VOCABULARY.find(c)
    return idx if idx >= 0 else BLANK_INDEX


def index_to_char(idx: int) -> str:
    if 0 <= idx < len(VOCABULARY):
        return VOCABULARY[idx]
    return ""


class CustomOCRModel(nn.Module):
    """CNN + BiLSTM + CTC for handwriting recognition from scratch."""

    def __init__(self, num_chars: int = len(VOCABULARY) + 1, lstm_hidden: int = 256):
        super().__init__()
        self.num_chars = num_chars  # includes CTC blank

        self.cnn = nn.Sequential(
            nn.Conv2d(1, 64, 3, padding=1),
            nn.ReLU(),
            nn.MaxPool2d(2, 2),

            nn.Conv2d(64, 128, 3, padding=1),
            nn.BatchNorm2d(128),
            nn.ReLU(),
            nn.MaxPool2d(2, 2),

            nn.Conv2d(128, 256, 3, padding=1),
            nn.BatchNorm2d(256),
            nn.ReLU(),
            nn.MaxPool2d(2, 2),

            nn.Conv2d(256, 256, 3, padding=1),
            nn.BatchNorm2d(256),
            nn.ReLU(),
            nn.MaxPool2d((2, 1)),

            nn.Conv2d(256, 256, 3, padding=1),
            nn.BatchNorm2d(256),
            nn.ReLU(),
            nn.MaxPool2d((2, 1)),
        )

        self.lstm = nn.LSTM(
            input_size=256,
            hidden_size=lstm_hidden,
            num_layers=1,
            bidirectional=True,
            batch_first=True,
        )

        self.fc = nn.Linear(lstm_hidden * 2, num_chars)
        self.softmax = nn.LogSoftmax(dim=2)

    def forward(self, x):
        x = self.cnn(x)
        b, c, h, w = x.size()
        x = x.permute(0, 3, 1, 2)
        x = x.reshape(b, w, c * h)

        x, _ = self.lstm(x)
        x = self.fc(x)
        x = self.softmax(x)
        return x

    @staticmethod
    def ctc_greedy_decode(output: torch.Tensor) -> list[list[int]]:
        preds = output.argmax(dim=2)
        results = []
        for batch in preds:
            prev = -1
            indices = []
            for idx in batch.tolist():
                if idx != prev and idx != BLANK_INDEX:
                    indices.append(idx)
                prev = idx
            results.append(indices)
        return results

    @staticmethod
    def indices_to_text(indices: list[int]) -> str:
        return "".join(index_to_char(i) for i in indices)


def count_parameters(model: nn.Module) -> int:
    return sum(p.numel() for p in model.parameters() if p.requires_grad)
