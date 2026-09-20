# ARGUS — USB camera prototype

ดับเบิลคลิก **Start ARGUS.cmd** แล้วเปิด http://127.0.0.1:8000 หากเบราว์เซอร์ไม่เปิดอัตโนมัติ
รอโมเดลพร้อม 5/5 เลือกกล้อง USB กดเปิดกล้อง และอนุญาตการใช้กล้อง
วางยาทีละชิ้นให้เห็นทั้งบรรจุภัณฑ์ในกรอบกลาง ภาพในกรอบจะส่งไปตรวจบนเครื่องนี้
ผลยืนยันหลังพบชนิดยาและผล QC เดิม 3 ภาพต่อเนื่อง ผลภาพและเส้น segmentation แสดงในช่องผลตรวจเพื่อไม่ให้ทับผิดตำแหน่งบนภาพสดที่มีความหน่วง
หยุดด้วยปุ่มหยุดกล้อง ปิดหน้าต่างเซิร์ฟเวอร์เมื่อเลิกใช้งาน

## How it works

- Browser getUserMedia selects a USB camera, crops the visible 70% inspection region and sends one JPEG at a time. It does not request microphone access or store frames.
- A frozen ImageNet MobileNetV3-small backbone with logistic regression, fitted to the supplied training images, routes to one of five QC models. Confidence >= 0.80, margin >= 0.25 and nearest training-feature cosine similarity >= 0.72 are required. These are initial prototype gates, not calibrated probabilities or a guarantee of unknown-object rejection.
- The selected original Ultralytics model performs segmentation at imgsz=640 and confidence >= 0.45. A detected class `normal` or ending in `_normal` is normal; other observed model classes are treated as defects. No detections means uncertain, never pass.
- Only matching medicine and QC status in three consecutive requests produces a confirmed display. This is temporal smoothing, not independent statistical confirmation. One item per frame is an operator constraint, not automatically enforced.
- The app binds to localhost; no cloud endpoint or upload service is used. Models and router weights stay local. Camera permission is granted in the browser.

## Limitations before presenting

The router report evaluates the dataset's provided validation/test partitions, after excluding exact-byte and source-name duplicates against earlier splits. Similar adjacent frames may remain. It does not establish performance on a new USB camera, conveyor, lighting setup or unrelated objects. Capture held-out images from the presentation camera and verify all five medicines and defect types before claiming live accuracy. ImageNet features are pretrained; only the linear router is trained here. No retraining of the five supplied QC models is performed. No production release/reject mechanism or reliable physical piece counting is included.

## Reproduce

This repository contains application source only. Datasets, trained model weights, generated reports, local environments and runtime files are excluded from Git. On another computer, obtain the five QC weights separately and place them in `models/`. Also copy `router_features.pt` and `router.npz` into `models/`, or recreate them with `train_router.py` using the original dataset ZIP files under `Med/`.

Python 3.14 is used on this machine. Install requirements into `.venv`. Run `.venv/Scripts/python.exe train_router.py` to regenerate the router from the five ZIP archives listed in the script. The initial run downloads public MobileNetV3 weights; normal app use is offline.

Run `.venv/Scripts/python.exe -m uvicorn app:app --host 127.0.0.1 --port 8000` to serve without opening a browser. Run `.venv/Scripts/python.exe test_argus.py` for the backend smoke tests.

Reports are in `reports/`. Dependencies are pinned in `requirements.txt` (transitive versions in `requirements-lock.txt`). Keep the original `.pt` model files named antacil, betadine, fahtalaijone, gaviscon and yoki in `models/`.
