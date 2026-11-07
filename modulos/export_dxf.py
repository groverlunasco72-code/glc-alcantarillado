# -*- coding: utf-8 -*-
"""
Módulo: Exportar DXF (Plano en planta)

Exporta la red de alcantarillado a un archivo DXF en planta (sin Z).

Formato DXF R12 (AC1009) generado como texto para evitar bugs de
QgsDxfExport en Python.

CAPAS DEL DXF:
    • TUBERIAS  → POLYLINE (líneas de tuberías)
    • CAMARAS   → CIRCLE de 6 m de diámetro
    • ARRANQUES → POLYLINE perpendicular en la cámara Ci de cada
                  tubería con cab_ata = 'Arranque'
    • DIRECCION → flechas en V en el punto medio de cada tubería,
                  apuntando en el sentido Ci → Cf
"""

import os
import math
from qgis.core import (
    QgsProject, QgsVectorLayer, QgsGeometry,
    QgsWkbTypes, QgsCoordinateTransform
)
from qgis.PyQt.QtWidgets import (
    QMessageBox, QDialog, QVBoxLayout, QLabel,
    QPushButton, QComboBox, QHBoxLayout,
    QFileDialog, QLineEdit, QGroupBox, QCheckBox
)


# Parámetros de dibujo
DIAMETRO_CAMARA = 6.0
RADIO_CAMARA = DIAMETRO_CAMARA / 2.0

# Parámetros de las flechas de dirección
FLECHA_LARGO_BRAZO = 2.0      # metros
FLECHA_ANGULO = 30.0          # grados


class ExportDXF:
    def __init__(self, iface):
        self.iface = iface
        self.ruta_salida = None
        self.capa_tuberias = None
        self.capa_camaras = None

    # ============================================================
    # DIÁLOGO
    # ============================================================
    def mostrar_dialogo(self):
        dialog = QDialog(self.iface.mainWindow())
        dialog.setWindowTitle('GLC - Exportar DXF (Plano en planta)')
        dialog.setMinimumWidth(650)
        self.dialog = dialog

        layout = QVBoxLayout()

        titulo = QLabel('<b>📐 Exportar Red a DXF (Planta)</b>')
        titulo.setStyleSheet('font-size: 14pt; font-weight: bold;')
        layout.addWidget(titulo)

        info = QLabel(
            'Exporta la red de alcantarillado a un archivo DXF en planta.\n\n'
            '• Tuberías  → líneas (capa TUBERIAS)\n'
            f'• Cámaras   → círculos de {DIAMETRO_CAMARA:.1f} m (capa CAMARAS)\n'
            '• Arranques → perpendicular en Ci (capa ARRANQUES)\n'
            '• Dirección → flechas en V (capa DIRECCION)\n\n'
            'Formato DXF R12 (AC1009). Compatible con AutoCAD, LibreCAD,\n'
            'QCAD, BricsCAD, DraftSight, etc.\n\n'
            '⚠️ Si al abrir el DXF no ves nada, ejecuta ZOOM EXTENTS (ZOOM E).'
        )
        info.setWordWrap(True)
        layout.addWidget(info)

        layout.addWidget(QLabel('-' * 50))

        # ---- Capas ----
        grupo_capas = QGroupBox('Capas a exportar')
        layout_capas = QVBoxLayout()

        layout_capas.addWidget(QLabel('Capa de Tuberías:'))
        self.combo_tuberias = QComboBox()
        for layer in QgsProject.instance().mapLayers().values():
            if isinstance(layer, QgsVectorLayer):
                if layer.geometryType() == QgsWkbTypes.LineGeometry:
                    if 'GLC_Tuberias' in layer.name():
                        self.combo_tuberias.addItem(layer.name(), layer.id())
        if self.combo_tuberias.count() == 0:
            for layer in QgsProject.instance().mapLayers().values():
                if isinstance(layer, QgsVectorLayer):
                    if layer.geometryType() == QgsWkbTypes.LineGeometry:
                        self.combo_tuberias.addItem(layer.name(), layer.id())
        layout_capas.addWidget(self.combo_tuberias)

        layout_capas.addWidget(QLabel('Capa de Cámaras:'))
        self.combo_camaras = QComboBox()
        for layer in QgsProject.instance().mapLayers().values():
            if isinstance(layer, QgsVectorLayer):
                if layer.geometryType() == QgsWkbTypes.PointGeometry:
                    if 'GLC_Camaras' in layer.name():
                        self.combo_camaras.addItem(layer.name(), layer.id())
        if self.combo_camaras.count() == 0:
            for layer in QgsProject.instance().mapLayers().values():
                if isinstance(layer, QgsVectorLayer):
                    if layer.geometryType() == QgsWkbTypes.PointGeometry:
                        self.combo_camaras.addItem(layer.name(), layer.id())
        layout_capas.addWidget(self.combo_camaras)

        grupo_capas.setLayout(layout_capas)
        layout.addWidget(grupo_capas)

        # ---- Opciones ----
        grupo_opciones = QGroupBox('Opciones')
        layout_opciones = QVBoxLayout()

        self.chk_tuberias = QCheckBox('Incluir tuberías')
        self.chk_tuberias.setChecked(True)
        layout_opciones.addWidget(self.chk_tuberias)

        self.chk_camaras = QCheckBox('Incluir cámaras')
        self.chk_camaras.setChecked(True)
        layout_opciones.addWidget(self.chk_camaras)

        self.chk_arranques = QCheckBox(
            'Marcar arranques (perpendicular en Ci)'
        )
        self.chk_arranques.setChecked(True)
        layout_opciones.addWidget(self.chk_arranques)

        self.chk_direccion = QCheckBox('Marcar dirección de flujo (flechas)')
        self.chk_direccion.setChecked(True)
        layout_opciones.addWidget(self.chk_direccion)

        grupo_opciones.setLayout(layout_opciones)
        layout.addWidget(grupo_opciones)

        # ---- Ruta de salida ----
        layout.addWidget(QLabel('-' * 50))
        layout.addWidget(QLabel('Archivo DXF de salida:'))
        hbox_ruta = QHBoxLayout()
        self.txt_ruta = QLineEdit()
        self.txt_ruta.setPlaceholderText('Selecciona dónde guardar el DXF...')
        hbox_ruta.addWidget(self.txt_ruta, 1)

        btn_ruta = QPushButton('...')
        btn_ruta.setMaximumWidth(40)
        btn_ruta.clicked.connect(self._seleccionar_ruta)
        hbox_ruta.addWidget(btn_ruta)
        layout.addLayout(hbox_ruta)

        layout.addWidget(QLabel('-' * 50))

        # ---- Botones ----
        btn_exportar = QPushButton('📤 Exportar DXF')
        btn_exportar.setStyleSheet(
            'background-color: #4CAF50; color: white; font-weight: bold; '
            'font-size: 12pt; padding: 8px;'
        )
        btn_exportar.clicked.connect(self._exportar)
        layout.addWidget(btn_exportar)

        btn_cerrar = QPushButton('Cerrar')
        btn_cerrar.setStyleSheet('background-color: #f44336; color: white;')
        btn_cerrar.clicked.connect(dialog.accept)
        layout.addWidget(btn_cerrar)

        dialog.setLayout(layout)
        dialog.exec_()

    # ============================================================
    # SELECCIONAR RUTA DE SALIDA
    # ============================================================
    def _seleccionar_ruta(self):
        ruta, _ = QFileDialog.getSaveFileName(
            self.iface.mainWindow(),
            'Guardar DXF',
            '',
            'Archivos DXF (*.dxf)'
        )
        if ruta:
            if not ruta.lower().endswith('.dxf'):
                ruta += '.dxf'
            self.txt_ruta.setText(ruta)
            self.ruta_salida = ruta

    # ============================================================
    # EXPORTAR
    # ============================================================
    def _exportar(self):
        # --- Validaciones ---
        ruta = self.txt_ruta.text().strip()
        if not ruta:
            QMessageBox.warning(self.iface.mainWindow(), 'Error',
                                'Selecciona un archivo DXF de salida.')
            return
        if not ruta.lower().endswith('.dxf'):
            ruta += '.dxf'

        if not self.chk_tuberias.isChecked() \
                and not self.chk_camaras.isChecked() \
                and not self.chk_arranques.isChecked() \
                and not self.chk_direccion.isChecked():
            QMessageBox.warning(self.iface.mainWindow(), 'Error',
                                'Debes seleccionar al menos una opción.')
            return

        tuberias_id = self.combo_tuberias.currentData()
        camaras_id = self.combo_camaras.currentData()
        self.capa_tuberias = QgsProject.instance().mapLayer(tuberias_id) \
            if tuberias_id else None
        self.capa_camaras = QgsProject.instance().mapLayer(camaras_id) \
            if camaras_id else None

        if self.chk_tuberias.isChecked() and not self.capa_tuberias:
            QMessageBox.warning(self.iface.mainWindow(), 'Error',
                                'No se encontró la capa de tuberías.')
            return
        if self.chk_camaras.isChecked() and not self.capa_camaras:
            QMessageBox.warning(self.iface.mainWindow(), 'Error',
                                'No se encontró la capa de cámaras.')
            return

        crs_proyecto = QgsProject.instance().crs()
        if not crs_proyecto.isValid():
            QMessageBox.warning(self.iface.mainWindow(), 'Error',
                                'El proyecto no tiene un CRS válido.')
            return

        # --- Recopilar geometrías ---
        lineas = []
        circulos = []
        lineas_arranque = []
        flechas = []

        # Tuberías
        if self.chk_tuberias.isChecked() and self.capa_tuberias:
            transform_t = self._crear_transform(self.capa_tuberias, crs_proyecto)
            for feat in self.capa_tuberias.getFeatures():
                geom = feat.geometry()
                if geom is None or geom.isEmpty():
                    continue
                geom = self._aplanar_geometria(geom)
                if transform_t is not None:
                    try:
                        geom.transform(transform_t)
                    except Exception:
                        pass
                for parte in self._extraer_partes(geom):
                    if len(parte) >= 2:
                        lineas.append(parte)

        # Cámaras
        if self.chk_camaras.isChecked() and self.capa_camaras:
            transform_c = self._crear_transform(self.capa_camaras, crs_proyecto)
            for feat in self.capa_camaras.getFeatures():
                geom = feat.geometry()
                if geom is None or geom.isEmpty():
                    continue
                punto = self._punto_de_geometria(geom)
                if punto is None:
                    continue
                if transform_c is not None:
                    try:
                        punto = transform_c.transform(punto)
                    except Exception:
                        pass
                circulos.append((punto.x(), punto.y(), RADIO_CAMARA))

        # Arranques
        if self.chk_arranques.isChecked() and self.capa_tuberias:
            lineas_arranque = self._calcular_lineas_arranque(self.capa_tuberias)

        # Flechas de dirección
        if self.chk_direccion.isChecked() and self.capa_tuberias:
            flechas = self._calcular_flechas(self.capa_tuberias)

        if not lineas and not circulos and not lineas_arranque and not flechas:
            QMessageBox.warning(self.iface.mainWindow(), 'Error',
                                'No hay geometrías para exportar.')
            return

        # --- Extensión total ---
        xs, ys = [], []
        for linea in lineas:
            for x, y in linea:
                xs.append(x); ys.append(y)
        for x, y, r in circulos:
            xs.extend([x - r, x + r])
            ys.extend([y - r, y + r])
        for linea in lineas_arranque:
            for x, y in linea:
                xs.append(x); ys.append(y)
        for flecha in flechas:
            for segmento in flecha:
                for x, y in segmento:
                    xs.append(x); ys.append(y)

        ext = (min(xs), min(ys), max(xs), max(ys))

        # --- Generar DXF ---
        try:
            contenido = self._generar_dxf(
                lineas, circulos, lineas_arranque, flechas, ext
            )
            with open(ruta, 'w', encoding='utf-8', newline='\r\n') as f:
                f.write(contenido)
        except Exception as e:
            QMessageBox.critical(self.iface.mainWindow(), 'Error',
                                 f'No se pudo escribir el DXF:\n{e}')
            return

        if not os.path.exists(ruta):
            QMessageBox.warning(self.iface.mainWindow(), 'Error',
                                f'El archivo no se creó:\n{ruta}')
            return

        tamano = os.path.getsize(ruta)

        QMessageBox.information(
            self.iface.mainWindow(),
            'Exportación completada',
            f'✅ DXF exportado correctamente.\n\n'
            f'📁 Archivo: {ruta}\n'
            f'📦 Tamaño: {tamano} bytes\n'
            f'📏 Tuberías: {len(lineas)}\n'
            f'⭕ Cámaras: {len(circulos)}\n'
            f'🚩 Arranques: {len(lineas_arranque)}\n'
            f'➡️  Flechas: {len(flechas)}\n\n'
            f'📌 Capas del DXF: TUBERIAS, CAMARAS, ARRANQUES, DIRECCION\n\n'
            f'⚠️ Si no ves nada en CAD: ejecuta ZOOM EXTENTS (ZOOM E)'
        )

    # ============================================================
    # LÍNEAS DE ARRANQUE
    # ============================================================
    def _calcular_lineas_arranque(self, capa_tuberias):
        """
        Para cada tubería con cab_ata == 'Arranque', genera una línea
        perpendicular a la tubería cuyo punto medio está en el borde
        del círculo de la cámara Ci (a distancia = radio desde Ci),
        con longitud total = diámetro de la cámara (6 m).

        Devuelve lista de líneas, cada una como [(x1,y1), (x2,y2)].
        """
        resultado = []

        idx_xi = capa_tuberias.fields().indexFromName('Xi')
        idx_yi = capa_tuberias.fields().indexFromName('Yi')
        idx_xf = capa_tuberias.fields().indexFromName('Xf')
        idx_yf = capa_tuberias.fields().indexFromName('Yf')
        idx_cab = capa_tuberias.fields().indexFromName('cab_ata')

        if min(idx_xi, idx_yi, idx_xf, idx_yf, idx_cab) == -1:
            return resultado

        for feat in capa_tuberias.getFeatures():
            cab = feat.attribute(idx_cab)
            if cab is None:
                continue
            if str(cab).strip().lower() != 'arranque':
                continue

            try:
                xi = float(feat.attribute(idx_xi))
                yi = float(feat.attribute(idx_yi))
                xf = float(feat.attribute(idx_xf))
                yf = float(feat.attribute(idx_yf))
            except (TypeError, ValueError):
                continue

            dx = xf - xi
            dy = yf - yi
            largo = math.hypot(dx, dy)
            if largo < 1e-9:
                continue
            ux = dx / largo
            uy = dy / largo

            # Punto medio: borde del círculo Ci en dirección Ci → Cf
            medio_x = xi + RADIO_CAMARA * ux
            medio_y = yi + RADIO_CAMARA * uy

            # Perpendicular
            px = -uy
            py = ux

            mitad = RADIO_CAMARA
            p1 = (medio_x + mitad * px, medio_y + mitad * py)
            p2 = (medio_x - mitad * px, medio_y - mitad * py)

            resultado.append([p1, p2])

        return resultado

    # ============================================================
    # FLECHAS DE DIRECCIÓN DE FLUJO
    # ============================================================
    def _calcular_flechas(self, capa_tuberias):
        """
        Para cada tubería, genera una flecha en V (2 segmentos) con el
        vértice en el punto medio de la tubería, apuntando en el sentido
        Ci → Cf.

        Cada flecha se devuelve como lista de 2 segmentos:
            [[(ax,ay),(xm,ym)], [(xm,ym),(bx,by)]]
        """
        resultado = []

        idx_xi = capa_tuberias.fields().indexFromName('Xi')
        idx_yi = capa_tuberias.fields().indexFromName('Yi')
        idx_xf = capa_tuberias.fields().indexFromName('Xf')
        idx_yf = capa_tuberias.fields().indexFromName('Yf')

        if min(idx_xi, idx_yi, idx_xf, idx_yf) == -1:
            return resultado

        ang = math.radians(FLECHA_ANGULO)
        cos_a = math.cos(ang)
        sin_a = math.sin(ang)

        for feat in capa_tuberias.getFeatures():
            try:
                xi = float(feat.attribute(idx_xi))
                yi = float(feat.attribute(idx_yi))
                xf = float(feat.attribute(idx_xf))
                yf = float(feat.attribute(idx_yf))
            except (TypeError, ValueError):
                continue

            dx = xf - xi
            dy = yf - yi
            largo = math.hypot(dx, dy)
            if largo < 1e-9:
                continue
            ux = dx / largo
            uy = dy / largo

            # Punto medio (vértice de la flecha)
            xm = (xi + xf) / 2.0
            ym = (yi + yf) / 2.0

            # Dirección atrás
            bx = -ux
            by = -uy

            # Brazo 1: rotar +30°
            b1x = bx * cos_a - by * sin_a
            b1y = bx * sin_a + by * cos_a

            # Brazo 2: rotar -30°
            b2x = bx * cos_a + by * sin_a
            b2y = -bx * sin_a + by * cos_a

            ax = xm + FLECHA_LARGO_BRAZO * b1x
            ay = ym + FLECHA_LARGO_BRAZO * b1y
            cx = xm + FLECHA_LARGO_BRAZO * b2x
            cy = ym + FLECHA_LARGO_BRAZO * b2y

            segmentos = [
                [(ax, ay), (xm, ym)],
                [(xm, ym), (cx, cy)],
            ]
            resultado.append(segmentos)

        return resultado

    # ============================================================
    # GENERAR CONTENIDO DXF R12
    # ============================================================
    def _generar_dxf(self, lineas, circulos, lineas_arranque, flechas, ext):
        """
        Genera el texto DXF en formato R12 (AC1009).
        ext = (min_x, min_y, max_x, max_y)
        """
        emin_x, emin_y, emax_x, emax_y = ext
        out = []

        # HEADER
        out.append("0\nSECTION\n2\nHEADER\n")
        out.append("9\n$ACADVER\n1\nAC1009\n")
        out.append("9\n$INSUNITS\n70\n6\n")
        out.append(f"9\n$EXTMIN\n10\n{emin_x:.6f}\n20\n{emin_y:.6f}\n30\n0.0\n")
        out.append(f"9\n$EXTMAX\n10\n{emax_x:.6f}\n20\n{emax_y:.6f}\n30\n0.0\n")
        out.append("9\n$LIMMIN\n10\n0.0\n20\n0.0\n")
        out.append("9\n$LIMMAX\n10\n420.0\n20\n297.0\n")
        out.append("9\n$LTSCALE\n40\n1.0\n")
        out.append("9\n$TEXTSIZE\n40\n2.5\n")
        out.append("0\nENDSEC\n")

        # TABLES
        out.append("0\nSECTION\n2\nTABLES\n")

        # LTYPE
        out.append("0\nTABLE\n2\nLTYPE\n70\n1\n")
        out.append(
            "0\nLTYPE\n2\nCONTINUOUS\n70\n64\n"
            "3\nSolid line\n72\n65\n73\n0\n40\n0.0\n"
        )
        out.append("0\nENDTAB\n")

        # LAYER (5 capas: 0, TUBERIAS, CAMARAS, ARRANQUES, DIRECCION)
        out.append("0\nTABLE\n2\nLAYER\n70\n5\n")
        out.append("0\nLAYER\n2\n0\n70\n0\n62\n7\n6\nCONTINUOUS\n")
        out.append("0\nLAYER\n2\nTUBERIAS\n70\n0\n62\n7\n6\nCONTINUOUS\n")
        out.append("0\nLAYER\n2\nCAMARAS\n70\n0\n62\n7\n6\nCONTINUOUS\n")
        out.append("0\nLAYER\n2\nARRANQUES\n70\n0\n62\n1\n6\nCONTINUOUS\n")
        out.append("0\nLAYER\n2\nDIRECCION\n70\n0\n62\n3\n6\nCONTINUOUS\n")
        out.append("0\nENDTAB\n")

        # STYLE
        out.append("0\nTABLE\n2\nSTYLE\n70\n1\n")
        out.append(
            "0\nSTYLE\n2\nSTANDARD\n70\n0\n40\n0.0\n"
            "41\n1.0\n50\n0.0\n71\n0\n42\n2.5\n3\ntxt\n4\n\n"
        )
        out.append("0\nENDTAB\n")

        out.append("0\nENDSEC\n")

        # ENTITIES
        out.append("0\nSECTION\n2\nENTITIES\n")

        # Tuberías
        for linea in lineas:
            out.append("0\nPOLYLINE\n8\nTUBERIAS\n66\n1\n70\n0\n")
            for x, y in linea:
                out.append(
                    f"0\nVERTEX\n8\nTUBERIAS\n10\n{x:.6f}\n20\n{y:.6f}\n30\n0.0\n"
                )
            out.append("0\nSEQEND\n8\nTUBERIAS\n")

        # Cámaras
        for x, y, r in circulos:
            out.append(
                f"0\nCIRCLE\n8\nCAMARAS\n"
                f"10\n{x:.6f}\n20\n{y:.6f}\n30\n0.0\n40\n{r:.6f}\n"
            )

        # Arranques
        for linea in lineas_arranque:
            out.append("0\nPOLYLINE\n8\nARRANQUES\n66\n1\n70\n0\n")
            for x, y in linea:
                out.append(
                    f"0\nVERTEX\n8\nARRANQUES\n10\n{x:.6f}\n20\n{y:.6f}\n30\n0.0\n"
                )
            out.append("0\nSEQEND\n8\nARRANQUES\n")

        # Flechas de dirección
        for flecha in flechas:
            for segmento in flecha:
                out.append("0\nPOLYLINE\n8\nDIRECCION\n66\n1\n70\n0\n")
                for x, y in segmento:
                    out.append(
                        f"0\nVERTEX\n8\nDIRECCION\n10\n{x:.6f}\n20\n{y:.6f}\n30\n0.0\n"
                    )
                out.append("0\nSEQEND\n8\nDIRECCION\n")

        out.append("0\nENDSEC\n")
        out.append("0\nEOF\n")

        return "".join(out)

    # ============================================================
    # UTILIDADES
    # ============================================================
    def _crear_transform(self, capa, crs_destino):
        try:
            return QgsCoordinateTransform(
                capa.crs(), crs_destino, QgsProject.instance()
            )
        except Exception:
            return None

    def _extraer_partes(self, geom):
        partes = []
        try:
            if geom.isMultipart():
                for parte in geom.asMultiPolyline():
                    if parte and len(parte) >= 2:
                        partes.append([(p.x(), p.y()) for p in parte])
            else:
                parte = geom.asPolyline()
                if parte and len(parte) >= 2:
                    partes.append([(p.x(), p.y()) for p in parte])
        except Exception:
            pass
        return partes

    def _punto_de_geometria(self, geom):
        try:
            return geom.asPoint()
        except Exception:
            try:
                multi = geom.asMultiPoint()
                if multi:
                    return multi[0]
            except Exception:
                pass
        return None

    def _aplanar_geometria(self, geom):
        try:
            if QgsWkbTypes.hasZ(geom.wkbType()):
                geom_sin_z = QgsGeometry(geom)
                geom_sin_z.get().dropZValue()
                return geom_sin_z
        except Exception:
            pass
        return geom

    def desactivar(self, mostrar_mensaje=True):
        pass