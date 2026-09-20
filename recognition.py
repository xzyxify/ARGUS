"""Local medicine router: frozen ImageNet features + a trained linear classifier."""
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent
(ROOT / '.runtime' / 'yolo' / 'Ultralytics').mkdir(parents=True, exist_ok=True)
os.environ.setdefault('TORCH_HOME', str(ROOT / '.runtime' / 'torch'))
os.environ.setdefault('YOLO_CONFIG_DIR', str(ROOT / '.runtime' / 'yolo'))
import numpy as np
import torch
from PIL import Image, ImageOps
from torchvision.models import mobilenet_v3_small, MobileNet_V3_Small_Weights

MEDICINES = {'antacil': 'Antacil', 'betadine': 'Betadine', 'fahtalaijone': 'ฟ้าทะลายโจร', 'gaviscon': 'Gaviscon', 'yoki': 'Yoki'}
torch.set_num_threads(4)

class Features:
    def __init__(self, download=False):
        self.device = 'cuda' if torch.cuda.is_available() else 'cpu'
        weights = MobileNet_V3_Small_Weights.DEFAULT
        self.net = mobilenet_v3_small(weights=weights if download else None)
        if not download:
            self.net.load_state_dict(torch.load(ROOT / 'models' / 'router_features.pt', map_location='cpu', weights_only=True))
        self.net.classifier = torch.nn.Identity()
        self.net.to(self.device).eval()
        self.transform = weights.transforms()

    def encode(self, images):
        batch = torch.stack([self.transform(ImageOps.exif_transpose(im).convert('RGB')) for im in images]).to(self.device)
        with torch.inference_mode():
            values = self.net(batch).cpu().numpy()
        return values / np.maximum(np.linalg.norm(values, axis=1, keepdims=True), 1e-8)

class Router:
    def __init__(self):
        self.features = Features()
        data = np.load(ROOT / 'models' / 'router.npz', allow_pickle=False)
        self.classes = data['classes']
        self.coef, self.intercept = data['coef'], data['intercept']
        self.references, self.labels = data['references'], data['labels']

    def predict(self, image):
        vector = self.features.encode([image])[0]
        logits = self.coef @ vector + self.intercept
        probabilities = np.exp(logits - logits.max())
        probabilities /= probabilities.sum()
        order = np.argsort(probabilities)[::-1]
        index = order[0]
        similarity = float((self.references[self.labels == self.classes[index]] @ vector).max())
        confidence = float(probabilities[index])
        margin = float(probabilities[index] - probabilities[order[1]])
        return {'medicine': str(self.classes[index]), 'confidence': confidence, 'similarity': similarity,
                'accepted': confidence >= .80 and margin >= .25 and similarity >= .72}
