"""Isolate camera and native AI calls so a stall can be terminated and recovered."""
import os
import queue
import time
import signal
from contextlib import suppress


def put_latest(target, value):
    try:
        target.put_nowait(value)
    except queue.Full:
        try:
            target.get_nowait()
        except queue.Empty:
            pass
        try:
            target.put_nowait(value)
        except queue.Full:
            pass


def camera_worker(output, width, height, fps, stop_event=None):
    # Terminal Ctrl+C is handled by the parent, which requests orderly shutdown.
    signal.signal(signal.SIGINT, signal.SIG_IGN)
    os.environ['LIBCAMERA_LOG_LEVELS']='*:ERROR'
    from picamera2 import Picamera2
    import cv2
    import numpy as np
    camera = None
    try:
        camera=Picamera2()
        camera.configure(camera.create_preview_configuration(main={'format':'RGB888','size':(width,height)},
                                                               controls={'FrameRate':fps},buffer_count=4))
        camera.start()
        while stop_event is None or not stop_event.is_set():
            frame=camera.capture_array()
            frame=cv2.rotate(frame[:,:,::-1],cv2.ROTATE_90_CLOCKWISE)
            frame=cv2.flip(frame,1)
            put_latest(output,('frame',time.monotonic(),np.ascontiguousarray(frame)))
    except Exception as exc:
        put_latest(output,('error',time.monotonic(),str(exc)))
    finally:
        if camera is not None:
            try:
                with suppress(Exception):
                    camera.stop()
            finally:
                camera.close()


def inference_worker(incoming, output, stop_event=None):
    signal.signal(signal.SIGINT, signal.SIG_IGN)
    # Limits native inference contention with capture and rendering on the Pi.
    os.environ.setdefault('OMP_NUM_THREADS','2')
    os.environ.setdefault('OPENBLAS_NUM_THREADS','2')
    import cv2
    import onnxruntime as ort
    from insightface.app import FaceAnalysis
    options=ort.SessionOptions()
    options.intra_op_num_threads=2
    options.inter_op_num_threads=1
    app=FaceAnalysis(name='buffalo_s',providers=['CPUExecutionProvider'],
                     allowed_modules=['detection','recognition'],sess_options=options)
    app.prepare(ctx_id=-1,det_size=(320,320))
    put_latest(output,('ready',None,[]))
    while stop_event is None or not stop_event.is_set():
        try:
            sequence,frame=incoming.get(timeout=.2)
        except queue.Empty:
            continue
        try:
            faces=app.get(cv2.cvtColor(frame,cv2.COLOR_RGB2BGR))
            result=[{'bbox':f.bbox,'embedding':f.embedding,'det_score':float(f.det_score)} for f in faces]
            put_latest(output,('result',sequence,result))
        except Exception as exc:
            put_latest(output,('error',sequence,str(exc)))
