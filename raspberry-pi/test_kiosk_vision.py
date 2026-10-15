"""Camera failure/cleanup checks without Pi hardware or native camera imports."""
import queue
import threading
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch
from kiosk_vision import camera_worker


class CameraLifecycleTests(unittest.TestCase):
    def run_camera(self, factory, stop):
        output = queue.Queue()
        modules = {'picamera2': SimpleNamespace(Picamera2=factory),
                   'cv2': SimpleNamespace(), 'numpy': SimpleNamespace()}
        with patch.dict('sys.modules', modules), patch('kiosk_vision.signal.signal'):
            camera_worker(output, 640, 360, 15, stop)
        return output

    def test_busy_camera_reports_error_instead_of_uncaught_constructor_traceback(self):
        output = self.run_camera(Mock(side_effect=RuntimeError('Device or resource busy')),
                                 threading.Event())
        kind, _, message = output.get_nowait()
        self.assertEqual(kind, 'error')
        self.assertIn('busy', message)

    def test_stop_request_closes_camera_without_capturing(self):
        camera = Mock()
        stop = threading.Event()
        stop.set()
        self.run_camera(Mock(return_value=camera), stop)
        camera.capture_array.assert_not_called()
        camera.stop.assert_called_once()
        camera.close.assert_called_once()

    def test_capture_failure_closes_camera_even_if_stop_raises(self):
        camera = Mock()
        camera.capture_array.side_effect = RuntimeError('capture failed')
        camera.stop.side_effect = RuntimeError('already stopped')
        output = self.run_camera(Mock(return_value=camera), threading.Event())
        self.assertEqual(output.get_nowait()[2], 'capture failed')
        camera.close.assert_called_once()


if __name__ == '__main__':
    unittest.main()
