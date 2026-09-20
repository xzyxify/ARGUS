import io
import json
import time
import zipfile
from PIL import Image
from fastapi.testclient import TestClient
from recognition import ROOT
from app import app

def main():
    results = []
    with TestClient(app) as client:
        for _ in range(180):
            health = client.get('/api/health').json()
            if health['ready'] or health['error']:
                break
            time.sleep(1)
        assert health['ready'], health
        assert len(health['models']) == 5
        assert client.get('/').status_code == 200
        assert client.post('/api/inspect', content=b'bad').status_code == 400
        assert client.post('/api/inspect', content=b'x' * (5 * 1024 * 1024 + 1)).status_code == 413
        assert client.post('/api/inspect', content=b'x', headers={'Origin': 'https://example.com'}).status_code == 403
        manifest = json.loads((ROOT / 'reports/test-manifest.json').read_text(encoding='utf-8'))
        for key in ['antacil', 'betadine', 'fahtalaijone', 'gaviscon', 'yoki']:
            candidates = [row for row in manifest if row['medicine'] == key]
            samples = candidates[:2]
            covered = set()
            for row in candidates:
                with zipfile.ZipFile(ROOT / row['archive']) as archive:
                    label_path = row['image'].replace('/images/', '/labels/').rsplit('.', 1)[0] + '.txt'
                    labels = {int(line.split()[0]) for line in archive.read(label_path).decode().splitlines() if line.strip()}
                if labels - covered:
                    if row not in samples:
                        samples.append(row)
                    covered.update(labels)
            assert samples
            for row in samples:
                with zipfile.ZipFile(ROOT / row['archive']) as archive:
                    raw = archive.read(row['image'])
                response = client.post('/api/inspect', content=raw, headers={'Content-Type': 'image/jpeg'})
                assert response.status_code == 200, response.text
                result = response.json()
                assert result['status'] in ['normal','damaged','uncertain']
                if result['status'] != 'uncertain':
                    assert result['detections']
                for d in result['detections']:
                    if d['label'].lower() == 'normal':
                        assert d['normal'], 'Antacil normal must not be marked damaged'
                results.append({'expected_medicine': key, 'image': row['image'], **result})
                print(key, result['medicine'], result['status'], result['elapsed_ms'], flush=True)
        for color in ['white', 'black', 'gray']:
            buffer=io.BytesIO();Image.new('RGB',(640,480),color).save(buffer,format='JPEG')
            response=client.post('/api/inspect',content=buffer.getvalue())
            assert response.status_code==200
            result=response.json()
            assert result['status']=='uncertain', (color,result)
        (ROOT / 'reports/pipeline-smoke.json').write_text(json.dumps({'device':health['device'],'checks':'HTTP validation, origin rejection, blank-frame rejection, held-out images covering available annotation classes','results':results},ensure_ascii=False,indent=2),encoding='utf-8')
    print('All backend smoke checks passed.',flush=True)

if __name__ == '__main__':
    main()
