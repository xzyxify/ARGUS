"""Keep the provided train/valid/test split; exclude source-name and byte duplicates."""
import hashlib
import io
import json
import zipfile
from collections import Counter
import numpy as np
import torch
from PIL import Image
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import classification_report, confusion_matrix
from recognition import ROOT, Features

SOURCES = {
    'antacil': 'Med/antacil/Hospital phasse 3.v3-all_antacil.yolov8.zip',
    'betadine': 'Med/Betadine/Betadine.v1i.yolov8.zip',
    'fahtalaijone': 'Med/Fah/Fahtalaijone.v1-fah.yolov8.zip',
    'gaviscon': 'Med/Garviscon/Graviscon.v1-gaviscon.yolov8.zip',
    'yoki': 'Med/Yoki/Yoki.v1i.yolov8.zip',
}

def main():
    features = Features(download=True)
    # Save the complete backbone before removing its classifier for inference.
    from torchvision.models import mobilenet_v3_small, MobileNet_V3_Small_Weights
    torch.save(mobilenet_v3_small(weights=MobileNet_V3_Small_Weights.DEFAULT).state_dict(), ROOT / 'models/router_features.pt')
    records = {'train': [], 'valid': [], 'test': []}
    excluded = Counter()
    for medicine, path in SOURCES.items():
        seen_names, seen_bytes = set(), set()
        with zipfile.ZipFile(ROOT / path) as archive:
            for split in records:
                names = sorted(n for n in archive.namelist() if n.startswith(split + '/images/') and n.lower().endswith(('.jpg', '.png', '.jpeg')))
                pending = []
                for name in names:
                    raw = archive.read(name)
                    source = name.rsplit('/', 1)[-1].split('.rf.')[0]
                    digest = hashlib.sha256(raw).hexdigest()
                    if source in seen_names or digest in seen_bytes:
                        excluded[split] += 1
                        continue
                    seen_names.add(source)
                    seen_bytes.add(digest)
                    pending.append((Image.open(io.BytesIO(raw)).convert('RGB'), name))
                    if len(pending) == 32:
                        vectors = features.encode([p[0] for p in pending])
                        records[split].extend((v, medicine, path, p[1]) for v, p in zip(vectors, pending))
                        pending = []
                if pending:
                    vectors = features.encode([p[0] for p in pending])
                    records[split].extend((v, medicine, path, p[1]) for v, p in zip(vectors, pending))
                print(medicine, split, len(records[split]), flush=True)
    x = np.array([r[0] for r in records['train']])
    y = np.array([r[1] for r in records['train']])
    model = LogisticRegression(C=20, max_iter=2000, class_weight='balanced').fit(x, y)
    np.savez_compressed(ROOT / 'models/router.npz', coef=model.coef_, intercept=model.intercept_, classes=model.classes_, references=x, labels=y)
    report = {'method': 'ImageNet MobileNetV3-small frozen features + logistic regression; full images',
              'limitations': 'Dataset split evaluation only, not USB camera validation. Similar frames may remain across splits. No labeled unknown-object test set.',
              'excluded_duplicates': dict(excluded), 'train_counts': dict(Counter(y))}
    for split in ('valid', 'test'):
        rows = records[split]
        values, expected = np.array([r[0] for r in rows]), [r[1] for r in rows]
        pred = model.predict(values)
        probs = model.predict_proba(values)
        sorted_probs = np.sort(probs, axis=1)
        sim = np.array([max(x[y == label] @ v) for label, v in zip(pred, values)])
        accepted = (sorted_probs[:, -1] >= .8) & ((sorted_probs[:, -1] - sorted_probs[:, -2]) >= .25) & (sim >= .72)
        report[split] = {'count': len(rows), 'classification': classification_report(expected, pred, output_dict=True, zero_division=0),
                         'confusion_matrix': confusion_matrix(expected, pred, labels=model.classes_).tolist(),
                         'class_order': model.classes_.tolist(), 'accepted_count': int(accepted.sum()),
                         'accepted_accuracy': float(np.mean(pred[accepted] == np.array(expected)[accepted])) if accepted.any() else None}
    (ROOT / 'reports').mkdir(exist_ok=True)
    (ROOT / 'reports/router-evaluation.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    (ROOT / 'reports/test-manifest.json').write_text(json.dumps([{'medicine': r[1], 'archive': r[2], 'image': r[3]} for r in records['test']], ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(report, ensure_ascii=True, indent=2), flush=True)

if __name__ == '__main__':
    main()
