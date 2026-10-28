import json
import os
import sys
import traceback
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import trimesh

from PySide6.QtCore import Qt, QObject, Signal
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QComboBox, QFileDialog, QFormLayout, QFrame,
    QHBoxLayout, QLabel, QMainWindow, QMessageBox, QPushButton, QSplitter,
    QStatusBar, QVBoxLayout, QWidget, QGroupBox, QPlainTextEdit
)

from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure
from matplotlib.patches import Rectangle

from runtime_bridge import RuntimeBridge


SUPPORTED_HINT = "3D files (*.obj *.stl *.ply *.off *.glb *.gltf *.dae *.3mf);;JSON scene (*.json);;All files (*.*)"


@dataclass
class SceneObject:
    name: str
    bounds: np.ndarray  # shape (2, 3), min/max in x,y,z
    source: str = "mesh"


def box_mesh(bounds, name="BlockoutBox"):
    lo, hi = np.asarray(bounds[0], dtype=float), np.asarray(bounds[1], dtype=float)
    extents = np.maximum(hi - lo, 0.01)
    center = (lo + hi) / 2.0
    mesh = trimesh.creation.box(extents=extents)
    mesh.apply_translation(center)
    mesh.metadata["name"] = name
    return mesh


def scene_objects_from_trimesh(loaded):
    objects = []
    if isinstance(loaded, trimesh.Trimesh):
        if len(loaded.vertices):
            objects.append(SceneObject("Mesh_001", loaded.bounds.copy()))
        return objects

    if isinstance(loaded, trimesh.Scene):
        # scene.dump(concatenate=False) applies scene graph transforms.
        dumped = loaded.dump(concatenate=False)
        for idx, geom in enumerate(dumped):
            if not isinstance(geom, trimesh.Trimesh) or not len(geom.vertices):
                continue
            name = str(geom.metadata.get("name") or f"Mesh_{idx+1:03d}")
            objects.append(SceneObject(name, np.asarray(geom.bounds).copy()))
        # Some loaders may produce a scene with no graph instances but with geometry.
        if not objects:
            for idx, geom in enumerate(loaded.geometry.values()):
                if isinstance(geom, trimesh.Trimesh) and len(geom.vertices):
                    objects.append(SceneObject(f"Mesh_{idx+1:03d}", np.asarray(geom.bounds).copy()))
    return objects


def load_json_scene(path):
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    objs = []
    for idx, item in enumerate(data.get("objects", [])):
        pos = np.asarray(item.get("position", [0, 0, 0]), dtype=float)
        size = np.asarray(item.get("size", [1, 1, 1]), dtype=float)
        if pos.shape != (3,) or size.shape != (3,):
            continue
        size = np.maximum(np.abs(size), 0.01)
        bounds = np.vstack([pos - size / 2, pos + size / 2])
        objs.append(SceneObject(item.get("name", f"Object_{idx+1:03d}"), bounds, item.get("type", "json")))
    return objs, data.get("name", Path(path).stem), data.get("units", "unknown")


def export_obj(meshes, path):
    scene = trimesh.Scene()
    for idx, mesh in enumerate(meshes):
        name = str(mesh.metadata.get("name") or f"Blockout_{idx+1:03d}")
        scene.add_geometry(mesh, node_name=name, geom_name=name)
    # Export a scene to OBJ with separate objects where supported by trimesh.
    exported = scene.export(file_type="obj")
    Path(path).write_text(exported, encoding="utf-8")


class PreviewCanvas(FigureCanvas):
    def __init__(self, parent=None):
        self.figure = Figure(figsize=(7, 6), tight_layout=True)
        self.ax = self.figure.add_subplot(111)
        super().__init__(self.figure)
        self.setParent(parent)
        self.draw_empty()

    def draw_empty(self):
        self.ax.clear()
        self.ax.set_title("Top-down level preview")
        self.ax.set_xlabel("X")
        self.ax.set_ylabel("Y")
        self.ax.grid(True, alpha=0.2)
        self.ax.text(0.5, 0.5, "Open a geometry file to begin", ha="center", va="center",
                     transform=self.ax.transAxes, color="#6b7280")
        self.draw_idle()

    def draw_objects(self, objects, blockout=False):
        self.ax.clear()
        self.ax.set_title("Top-down bounds preview (X / Y)")
        self.ax.set_xlabel("X")
        self.ax.set_ylabel("Y")
        self.ax.set_aspect("equal", adjustable="datalim")
        self.ax.grid(True, alpha=0.22)
        if not objects:
            self.draw_empty()
            return
        for obj in objects:
            (lo, hi) = obj.bounds
            x, y = lo[0], lo[1]
            w, h = max(hi[0] - lo[0], 0.01), max(hi[1] - lo[1], 0.01)
            rect = Rectangle(
                (x, y), w, h, fill=False, linewidth=1.0 if not blockout else 1.3,
                alpha=0.78
            )
            self.ax.add_patch(rect)
        all_bounds = np.array([o.bounds for o in objects])
        lo = all_bounds[:, 0, :].min(axis=0)
        hi = all_bounds[:, 1, :].max(axis=0)
        pad = max(float(max(hi[0]-lo[0], hi[1]-lo[1])) * 0.05, 1.0)
        self.ax.set_xlim(lo[0] - pad, hi[0] + pad)
        self.ax.set_ylim(lo[1] - pad, hi[1] + pad)
        self.draw_idle()



class BridgeSignals(QObject):
    snapshot_received = Signal(object)
    status_received = Signal(str)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Level Archaeologist — Prototype 0.1")
        self.resize(1180, 760)
        self.source_path = None
        self.source_objects = []
        self.blockout_objects = []
        self.level_name = "Untitled"
        self.units = "unknown"
        self.bridge_signals = BridgeSignals(self)
        self.bridge_signals.snapshot_received.connect(self.on_runtime_snapshot)
        self.bridge_signals.status_received.connect(self.on_bridge_status)
        self.runtime_bridge = RuntimeBridge(
            on_snapshot=self.bridge_signals.snapshot_received.emit,
            on_status=self.bridge_signals.status_received.emit,
        )

        root = QWidget()
        root_layout = QVBoxLayout(root)
        root_layout.setContentsMargins(14, 14, 14, 14)
        root_layout.setSpacing(12)

        header = QHBoxLayout()
        title_col = QVBoxLayout()
        title = QLabel("LEVEL ARCHAEOLOGIST")
        title.setObjectName("title")
        subtitle = QLabel("Game-level geometry research · blockout generation · Blender export")
        subtitle.setObjectName("subtitle")
        title_col.addWidget(title)
        title_col.addWidget(subtitle)
        header.addLayout(title_col)
        header.addStretch()
        self.status_label = QLabel("No level loaded")
        self.status_label.setObjectName("statusPill")
        header.addWidget(self.status_label)
        root_layout.addLayout(header)

        splitter = QSplitter(Qt.Horizontal)
        sidebar = QWidget()
        side_layout = QVBoxLayout(sidebar)
        side_layout.setContentsMargins(0, 0, 0, 0)
        side_layout.setSpacing(10)

        input_group = QGroupBox("1 · Source")
        input_layout = QVBoxLayout(input_group)
        self.open_button = QPushButton("Open geometry / scene…")
        self.open_button.clicked.connect(self.open_file)
        input_layout.addWidget(self.open_button)
        self.path_label = QLabel("No file selected")
        self.path_label.setWordWrap(True)
        self.path_label.setObjectName("muted")
        input_layout.addWidget(self.path_label)
        side_layout.addWidget(input_group)

        runtime_group = QGroupBox("Runtime capture")
        runtime_layout = QVBoxLayout(runtime_group)
        self.runtime_button = QPushButton("Start local runtime bridge")
        self.runtime_button.clicked.connect(self.toggle_runtime_bridge)
        runtime_layout.addWidget(self.runtime_button)
        runtime_hint = QLabel("Receives scene snapshots from a game-side mod / debug exporter on 127.0.0.1:47831.")
        runtime_hint.setWordWrap(True)
        runtime_hint.setObjectName("muted")
        runtime_layout.addWidget(runtime_hint)
        side_layout.addWidget(runtime_group)

        settings_group = QGroupBox("2 · Blockout settings")
        settings_layout = QFormLayout(settings_group)
        self.mode_combo = QComboBox()
        self.mode_combo.addItems(["One box per mesh/object", "One box for whole level"])
        settings_layout.addRow("Simplification:", self.mode_combo)
        self.min_size_check = QCheckBox("Clamp zero-thickness dimensions")
        self.min_size_check.setChecked(True)
        settings_layout.addRow(self.min_size_check)
        self.build_button = QPushButton("Build blockout")
        self.build_button.setObjectName("primary")
        self.build_button.clicked.connect(self.build_blockout)
        settings_layout.addRow(self.build_button)
        side_layout.addWidget(settings_group)

        export_group = QGroupBox("3 · Export")
        export_layout = QVBoxLayout(export_group)
        self.export_button = QPushButton("Export OBJ for Blender…")
        self.export_button.clicked.connect(self.export_blockout)
        self.export_button.setEnabled(False)
        export_layout.addWidget(self.export_button)
        self.export_json_button = QPushButton("Export neutral scene JSON…")
        self.export_json_button.clicked.connect(self.export_json)
        self.export_json_button.setEnabled(False)
        export_layout.addWidget(self.export_json_button)
        side_layout.addWidget(export_group)

        stats_group = QGroupBox("Level statistics")
        stats_layout = QVBoxLayout(stats_group)
        self.stats_label = QLabel("Objects: —\nBounds: —\nApprox. dimensions: —")
        self.stats_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        stats_layout.addWidget(self.stats_label)
        side_layout.addWidget(stats_group)

        notes_group = QGroupBox("Notes")
        notes_layout = QVBoxLayout(notes_group)
        self.notes = QPlainTextEdit()
        self.notes.setPlaceholderText("Record observations about the level here…")
        self.notes.setMaximumHeight(105)
        notes_layout.addWidget(self.notes)
        side_layout.addWidget(notes_group)
        side_layout.addStretch()

        preview_frame = QFrame()
        preview_frame.setObjectName("previewFrame")
        preview_layout = QVBoxLayout(preview_frame)
        preview_header = QHBoxLayout()
        preview_header.addWidget(QLabel("LEVEL PLAN"))
        preview_header.addStretch()
        self.preview_mode = QComboBox()
        self.preview_mode.addItems(["Source bounds", "Generated blockout"])
        self.preview_mode.currentIndexChanged.connect(self.refresh_preview)
        preview_header.addWidget(self.preview_mode)
        preview_layout.addLayout(preview_header)
        self.canvas = PreviewCanvas()
        preview_layout.addWidget(self.canvas, 1)

        splitter.addWidget(sidebar)
        splitter.addWidget(preview_frame)
        splitter.setSizes([330, 820])
        root_layout.addWidget(splitter, 1)
        self.setCentralWidget(root)
        self.setStatusBar(QStatusBar())
        self.setStyleSheet("""
            QMainWindow, QWidget { background: #151922; color: #e7eaf0; font-size: 10pt; }
            QLabel#title { font-size: 19pt; font-weight: 700; letter-spacing: 1px; }
            QLabel#subtitle, QLabel#muted { color: #9aa4b5; }
            QLabel#statusPill { background: #263a34; color: #a5f3c5; padding: 7px 11px; border-radius: 10px; }
            QGroupBox { border: 1px solid #343b49; border-radius: 10px; margin-top: 10px; padding: 10px; font-weight: 600; }
            QGroupBox::title { subcontrol-origin: margin; left: 10px; padding: 0 5px; color: #c5ccda; }
            QPushButton { background: #2a303d; border: 1px solid #424b5b; padding: 9px; border-radius: 7px; text-align: left; }
            QPushButton:hover { background: #353e4e; }
            QPushButton:disabled { color: #667080; background: #202530; }
            QPushButton#primary { background: #5b5ce2; border-color: #7778f0; font-weight: 700; }
            QPushButton#primary:hover { background: #6b6cf0; }
            QComboBox, QPlainTextEdit { background: #202530; border: 1px solid #3b4352; border-radius: 6px; padding: 6px; }
            QFrame#previewFrame { border: 1px solid #343b49; border-radius: 10px; }
        """)
        self.statusBar().showMessage("Ready · Start with an authorized geometry file or neutral JSON scene")

    def toggle_runtime_bridge(self):
        if self.runtime_bridge.running:
            self.runtime_bridge.stop()
            self.runtime_button.setText("Start local runtime bridge")
            return
        try:
            self.runtime_bridge.start()
            self.runtime_button.setText("Stop local runtime bridge")
        except OSError as exc:
            QMessageBox.critical(
                self, "Runtime bridge could not start",
                f"{exc}\\n\\nPort 47831 may already be in use."
            )

    def on_bridge_status(self, message):
        self.statusBar().showMessage(message)
        if "listening" in message.lower():
            self.status_label.setText("Waiting for runtime snapshot")
        elif "stopped" in message.lower():
            self.status_label.setText("Runtime bridge stopped")

    def on_runtime_snapshot(self, snapshot):
        try:
            objects = []
            for item in snapshot.get("objects", []):
                pos = np.asarray(item["position"], dtype=float)
                size = np.asarray(item["size"], dtype=float)
                bounds = np.vstack([pos - size / 2.0, pos + size / 2.0])
                objects.append(SceneObject(item["name"], bounds, item.get("type", "runtime")))
            if not objects:
                self.statusBar().showMessage("Runtime snapshot received, but it contains no valid objects")
                return
            self.source_objects = objects
            self.blockout_objects = []
            self.source_path = None
            self.level_name = snapshot.get("name", "Runtime capture")
            self.units = snapshot.get("units", "unknown")
            self.path_label.setText(
                f"Runtime capture · {snapshot.get('source', 'game adapter')} · {len(objects)} objects"
            )
            self.export_button.setEnabled(False)
            self.export_json_button.setEnabled(True)
            self.preview_mode.setCurrentIndex(0)
            self.update_stats(objects)
            self.refresh_preview()
            self.status_label.setText(f"Captured · {len(objects)} objects")
            self.statusBar().showMessage(f"Received runtime snapshot: {len(objects)} objects")
        except Exception as exc:
            self.statusBar().showMessage(f"Could not apply runtime snapshot: {exc}")

    def closeEvent(self, event):
        try:
            self.runtime_bridge.stop()
        finally:
            super().closeEvent(event)

    def open_file(self):
        path, _ = QFileDialog.getOpenFileName(self, "Open level geometry", "", SUPPORTED_HINT)
        if not path:
            return
        try:
            if Path(path).suffix.lower() == ".json":
                objects, name, units = load_json_scene(path)
                self.source_objects = objects
                self.level_name = name
                self.units = units
            else:
                loaded = trimesh.load(path, force=None, process=False)
                self.source_objects = scene_objects_from_trimesh(loaded)
                self.level_name = Path(path).stem
                self.units = "source units (unknown)"
            if not self.source_objects:
                raise ValueError("No mesh/object bounds were found in this file.")
            self.source_path = path
            self.path_label.setText(path)
            self.status_label.setText(f"Loaded · {len(self.source_objects)} objects")
            self.blockout_objects = []
            self.export_button.setEnabled(False)
            self.export_json_button.setEnabled(True)
            self.update_stats(self.source_objects)
            self.refresh_preview()
            self.statusBar().showMessage(f"Loaded {os.path.basename(path)}")
        except Exception as exc:
            QMessageBox.critical(self, "Could not open file", f"{exc}\n\n{traceback.format_exc(limit=3)}")

    def build_blockout(self):
        if not self.source_objects:
            QMessageBox.information(self, "No source", "Open a geometry or neutral JSON scene first.")
            return
        if self.mode_combo.currentIndex() == 1:
            all_b = np.array([o.bounds for o in self.source_objects])
            lo = all_b[:, 0, :].min(axis=0)
            hi = all_b[:, 1, :].max(axis=0)
            self.blockout_objects = [SceneObject("WholeLevel_Blockout", np.vstack([lo, hi]), "aabb")]
        else:
            self.blockout_objects = []
            for obj in self.source_objects:
                b = np.array(obj.bounds, dtype=float).copy()
                if self.min_size_check.isChecked():
                    center = (b[0] + b[1]) / 2
                    size = np.maximum(b[1] - b[0], 0.05)
                    b = np.vstack([center - size/2, center + size/2])
                self.blockout_objects.append(SceneObject(obj.name + "_Blockout", b, "aabb"))
        self.export_button.setEnabled(True)
        self.preview_mode.setCurrentIndex(1)
        self.update_stats(self.blockout_objects)
        self.status_label.setText(f"Blockout · {len(self.blockout_objects)} boxes")
        self.statusBar().showMessage(f"Generated {len(self.blockout_objects)} AABB blockout objects")

    def refresh_preview(self):
        objects = self.blockout_objects if self.preview_mode.currentIndex() == 1 and self.blockout_objects else self.source_objects
        self.canvas.draw_objects(objects, self.preview_mode.currentIndex() == 1)

    def update_stats(self, objects):
        if not objects:
            self.stats_label.setText("Objects: —\nBounds: —\nApprox. dimensions: —")
            return
        all_b = np.array([o.bounds for o in objects])
        lo = all_b[:, 0, :].min(axis=0)
        hi = all_b[:, 1, :].max(axis=0)
        dims = hi - lo
        self.stats_label.setText(
            f"Objects: {len(objects)}\n"
            f"Bounds: X {lo[0]:.2f}…{hi[0]:.2f}, Y {lo[1]:.2f}…{hi[1]:.2f}, Z {lo[2]:.2f}…{hi[2]:.2f}\n"
            f"Approx. dimensions: {dims[0]:.2f} × {dims[1]:.2f} × {dims[2]:.2f}\n"
            f"Units: {self.units}"
        )

    def export_blockout(self):
        if not self.blockout_objects:
            return
        path, _ = QFileDialog.getSaveFileName(self, "Export blockout OBJ", f"{self.level_name}_blockout.obj", "Wavefront OBJ (*.obj)")
        if not path:
            return
        try:
            meshes = [box_mesh(o.bounds, o.name) for o in self.blockout_objects]
            export_obj(meshes, path)
            QMessageBox.information(self, "Export complete", f"Exported {len(meshes)} blockout boxes:\n{path}\n\nIn Blender, use File > Import > Wavefront (.obj).")
            self.statusBar().showMessage(f"Exported OBJ: {path}")
        except Exception as exc:
            QMessageBox.critical(self, "Export failed", f"{exc}\n\n{traceback.format_exc(limit=3)}")

    def export_json(self):
        if not self.source_objects:
            return
        path, _ = QFileDialog.getSaveFileName(self, "Export neutral scene JSON", f"{self.level_name}_scene.json", "JSON (*.json)")
        if not path:
            return
        try:
            objs = []
            for o in self.source_objects:
                lo, hi = o.bounds
                center = (lo + hi) / 2
                size = hi - lo
                objs.append({
                    "name": o.name,
                    "type": o.source,
                    "position": [float(x) for x in center],
                    "size": [float(x) for x in size]
                })
            data = {
                "schema": "level-archaeologist.scene.v1",
                "name": self.level_name,
                "units": self.units,
                "source": os.path.basename(self.source_path or ""),
                "notes": self.notes.toPlainText(),
                "objects": objs
            }
            Path(path).write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
            self.statusBar().showMessage(f"Exported JSON: {path}")
        except Exception as exc:
            QMessageBox.critical(self, "JSON export failed", str(exc))


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("Level Archaeologist")
    win = MainWindow()
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
