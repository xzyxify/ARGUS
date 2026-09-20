import asyncio
import io
import logging
import time
from contextlib import asynccontextmanager
from threading import Lock

import numpy as np
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from PIL import Image, ImageOps, UnidentifiedImageError
from starlette.concurrency import run_in_threadpool
from recognition import ROOT, MEDICINES, Router
# Preserve Pillow's decoder before Ultralytics adds optional HEIF auto-install hooks.
decode_image = Image.open
from ultralytics import YOLO

class Engine:
    def __init__(self):
        self.lock = Lock()
        self.router = Router()
        self.models = {key: YOLO(ROOT / 'models' / (key + '.pt')) for key in MEDICINES}
        self.device = self.router.features.device
        for model in self.models.values():
            model.predict(np.zeros((480, 640, 3), dtype=np.uint8), imgsz=640, device=self.device, verbose=False)

    def inspect(self, image):
        if not self.lock.acquire(blocking=False):
            raise HTTPException(429, 'ระบบกำลังตรวจภาพ กรุณาลองอีกครั้ง')
        start = time.perf_counter()
        try:
            route = self.router.predict(image)
            response = {'route': route, 'medicine': None, 'status': 'uncertain', 'detections': [], 'qc_confidence': None}
            if route['accepted']:
                key = route['medicine']
                result = self.models[key].predict(image, conf=.45, imgsz=640, device=self.device, verbose=False)[0]
                detections = []
                masks = result.masks.xyn if result.masks is not None else []
                for i, box in enumerate(result.boxes):
                    label = result.names[int(box.cls.item())]
                    detections.append({'label': label, 'confidence': float(box.conf.item()),
                                       'box': box.xyxyn[0].tolist(), 'polygon': masks[i][::max(1, len(masks[i]) // 120)].tolist() if i < len(masks) else [],
                                       'normal': label.lower() == 'normal' or label.lower().endswith('_normal')})
                response['medicine'] = key
                response['detections'] = detections
                if detections:
                    response['status'] = 'damaged' if any(not d['normal'] for d in detections) else 'normal'
                    response['qc_confidence'] = max(d['confidence'] for d in detections)
            response['elapsed_ms'] = round((time.perf_counter() - start) * 1000)
            return response
        finally:
            self.lock.release()

engine = None
load_error = None

async def initialize():
    global engine, load_error
    try:
        engine = await run_in_threadpool(Engine)
    except Exception:
        logging.exception('Model initialization failed')
        load_error = 'โหลดโมเดลไม่สำเร็จ โปรดตรวจไฟล์โมเดลและบันทึกข้อผิดพลาด'

@asynccontextmanager
async def lifespan(app):
    task = asyncio.create_task(initialize())
    yield
    await task

app = FastAPI(title='ARGUS', lifespan=lifespan)

@app.middleware('http')
async def local_only(request: Request, call_next):
    # Camera frames stay on localhost; refuse cross-origin browser submissions.
    origin = request.headers.get('origin')
    allowed = {'http://127.0.0.1:8000', 'http://localhost:8000'}
    if origin and origin not in allowed:
        from fastapi.responses import JSONResponse
        return JSONResponse({'detail': 'Origin not allowed'}, status_code=403)
    response = await call_next(request)
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['Cache-Control'] = 'no-store'
    return response

@app.get('/api/health')
def health():
    return {'ready': engine is not None, 'error': load_error, 'device': engine.device if engine else None,
            'models': [{'id': key, 'name': value, 'loaded': engine is not None,
                        'classes': list(engine.models[key].names.values()) if engine else []} for key, value in MEDICINES.items()]}

@app.post('/api/inspect')
async def inspect(request: Request):
    if engine is None:
        raise HTTPException(503, load_error or 'กำลังเตรียมโมเดล')
    data = bytearray()
    async for chunk in request.stream():
        data.extend(chunk)
        if len(data) > 5 * 1024 * 1024:
            raise HTTPException(413, 'ภาพใหญ่เกิน 5 MB')
    try:
        image = decode_image(io.BytesIO(data))
        if image.width * image.height > 16_000_000:
            raise HTTPException(413, 'ภาพมีความละเอียดสูงเกินไป')
        image = ImageOps.exif_transpose(image).convert('RGB')
        image.thumbnail((1280, 1280))
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError):
        raise HTTPException(400, 'อ่านภาพไม่ได้')
    return await run_in_threadpool(engine.inspect, image)

@app.get('/')
def index():
    return FileResponse(ROOT / 'web/index.html')

app.mount('/static', StaticFiles(directory=ROOT / 'web'), name='static')
