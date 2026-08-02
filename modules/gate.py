"""
Gate 1: ANPR & Vehicle Counter combined on a single camera feed.
Internally reuses the existing VehicleProcessor and PlateProcessor —
no logic duplicated, just composed together so one physical gate camera
gives both the IN/OUT count AND the plate reading in one video.

Frame-skip: PlateProcessor.process() (YOLO + async OCR submit) runs every
config.PLATE_FRAME_SKIP frames. VehicleProcessor runs every frame as usual
so the IN/OUT counter stays accurate. Between plate-inference frames the
last annotated boxes are kept via PlateProcessor's internal track state —
the video is never blank.
"""
import config
from modules.vehicle import VehicleProcessor
from modules.plate import PlateProcessor


class GateProcessor:
    def __init__(self):
        self.vehicle = VehicleProcessor()
        self.plate = PlateProcessor()
        self._gate_frame_count = 0

    def process(self, frame):
        self._gate_frame_count += 1
        frame = self.vehicle.process(frame)
        vehicle_context = self.vehicle.get_recent_crossing()

        # Run plate YOLO + submit OCR only every PLATE_FRAME_SKIP frames.
        # Between frames: _drain_ocr_results() still runs (picks up finished
        # OCR results) and draws cached track boxes — zero visible lag.
        skip = max(config.PLATE_FRAME_SKIP, 1)
        if self._gate_frame_count % skip == 0:
            frame = self.plate.process(frame, vehicle_context=vehicle_context)
        else:
            # Drain any pending async OCR results and redraw existing tracks
            # without running full YOLO — keeps boxes visible between inferences
            self.plate._drain_ocr_results()

        return frame

    def reset(self):
        self.vehicle.reset()
        self._gate_frame_count = 0

    def manual_entry(self, plate_text, vehicle_type="—", direction="—"):
        self.plate.manual_entry(plate_text, vehicle_type, direction)

    def get_counts(self):
        c = self.vehicle.get_counts()
        c["recent_plates"] = self.plate.get_recent()
        return c

    def get_recent(self):
        return self.plate.get_recent()
