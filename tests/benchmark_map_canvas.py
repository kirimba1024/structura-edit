import argparse
import hashlib
import json
from pathlib import Path
import platform
from statistics import median
from time import perf_counter, thread_time

import numpy as np
from PySide6 import __version__ as qt_version
from PySide6.QtGui import QImage
from PySide6.QtWidgets import QApplication

from flight_metrics import distribution
from structura_edit.map_canvas import MapCanvas
from structura_edit.map_projection import VIEWS


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--frames", type=int, default=120)
    args = parser.parse_args()
    if args.frames < 2:
        parser.error("At least two frames are required")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    app = QApplication([])
    canvas = MapCanvas()
    canvas.size_blocks = (256, 256, 256)
    canvas.origin = (-1024, -64, -256)
    canvas.position = (128, 128, 128)
    canvas.layout.reset()
    pixels = np.full((128, 128, 3), (73, 112, 69), np.uint8)
    canvas.set_images(dict.fromkeys(VIEWS, pixels))
    icon = np.full((16, 16, 4), (220, 169, 148, 255), np.uint8)
    positions = np.random.default_rng(4).uniform(0, 256, (512, 3))
    canvas.set_entities([(tuple(position), i % 32 == 0, "Entity", icon) for i, position in enumerate(positions)])
    report = dict(entities=len(positions), frames=args.frames, device_pixel_ratio=2,
                  platform=platform.platform(), python=platform.python_version(), qt=qt_version, stages={})
    try:
        for name, size, focused in (("compact", (288, 192), None), ("large", (1104, 700), "top")):
            canvas.resize(*size)
            canvas.layout.large = name == "large"
            canvas.layout.focused = focused
            image = QImage(size[0] * 2, size[1] * 2, QImage.Format.Format_RGBA8888)
            image.setDevicePixelRatio(2)
            canvas.render(image)
            samples, cpu_samples = [], []
            for frame in range(args.frames):
                canvas.position = (128 + frame / 8, 128, 128)
                canvas.direction = (np.sin(frame / 20), 0, np.cos(frame / 20))
                start, cpu = perf_counter(), thread_time()
                canvas.render(image)
                cpu_samples.append((thread_time() - cpu) * 1000)
                samples.append((perf_counter() - start) * 1000)
            screenshot = args.output.with_name(args.output.stem + f"-{name}.png")
            image.save(str(screenshot))
            report["stages"][name] = dict(median_ms=median(samples), max_ms=max(samples), cpu_median_ms=median(cpu_samples),
                                         cpu_max_ms=max(cpu_samples), pixels_sha256=hashlib.sha256(image.constBits()).hexdigest(),
                                         size=list(size), frame_ms=distribution(samples), cpu_ms=distribution(cpu_samples),
                                         screenshot=str(screenshot), samples_ms=samples, cpu_samples_ms=cpu_samples)
        args.output.write_text(json.dumps(report, indent=2))
        print(json.dumps(report), flush=True)
    finally:
        canvas.close()
        canvas.deleteLater()
        app.processEvents()


if __name__ == "__main__":
    main()
