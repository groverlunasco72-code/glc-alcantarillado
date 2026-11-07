# -*- coding: utf-8 -*-
"""
Módulo: Exportar DXF Completo (Planta + Etiquetas)

Genera UN SOLO archivo DXF con toda la red y sus etiquetas.

CAPAS DEL DXF:
    • TUBERIAS       → POLYLINE (líneas de tuberías)
    • CAMARAS        → CIRCLE de 6 m de diámetro
    • ARRANQUES      → POLYLINE perpendicular en Ci (arranques)
    • DIRECCION      → flechas en V en el punto medio
    • ETIQUETAS      → etiquetas de cámaras (ID, Z, Zs, H)
    • ETIQ_TUBERIAS  → etiquetas de tuberías (ID, D-S%-L, Zs_f, Zs_i)

Todos los parámetros son FIJOS (valores por defecto de cada módulo).

Formato: DXF R12 (AC1009)
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


# ============================================================
# PARÁMETROS FIJOS
# ============================================================

# Cámaras
DIAMETRO_CAMARA = 6.0
RADIO_CAMARA = DIAMETRO_CAMARA / 2.0

# Flechas de dirección
FLECHA_LARGO_BRAZO = 2.0
FLECHA_ANGULO = 30.0

# Etiquetas de cámaras
ETQ_CAM_DESP_X = 7.5
ETQ_CAM_DESP_Y = 7.5
ETQ_CAM_LARGO_LINEA = 14.0
ETQ_CAM_ALTURA_TEXTO = 2.0
ETQ_CAM_DIST = 1.3

# Etiquetas de tuberías
ETQ_TUB_DIST_PERP = 2.5
ETQ_TUB_DIST_ID_EXTRA = 3.0
ETQ_TUB_ALTURA_TEXTO = 2.0
ETQ_TUB_DEC_S = 2
ETQ_TUB_DEC_L = 2
ETQ_TUB_DIST_CF = 10.0
ETQ_TUB_DIST_PERP_CF = 1.0
ETQ_TUB_DEC_ZF = 2


class ExportarCompletoDXF:
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
        dialog.setWindowTitle('GLC - Exportar DXF Completo')
        dialog.setMinimumWidth(650)
        self.dialog = dialog

        layout = QVBoxLayout()

        titulo = QLabel('<b>📐 Exportar DXF Completo (Planta + Etiquetas)</b>')
        titulo.setStyleSheet('font-size: 14pt; font-weight: bold;')
        layout.addWidget(titulo)

        info = QLabel(
            'Genera UN SOLO archivo DXF con:\n\n'
            '• Tuberías, Cámaras, Arranques, Flechas\n'
            '• Etiquetas de cámaras (ID, Z, Zs, H)\n'
            '• Etiquetas de tuberías (ID, D-S%-L, Zs_f, Zs_i)\n\n'
            'Todos los parámetros usan valores por defecto.'
        )
        info.setWordWrap(True)
        layout.addWidget(info)

        layout.addWidget(QLabel('-' * 50))

        # ---- Capas ----
        grupo_capas = QGroupBox('Capas')
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

        # ---- Campos ID ----
        grupo_ids = QGroupBox('Campos para ID')
        layout_ids = QVBoxLayout()

        layout_ids.addWidget(QLabel('Campo ID para Cámaras:'))
        self.combo_id_camaras = QComboBox()
        layout_ids.addWidget(self.combo_id_camaras)
        self.combo_camaras.currentIndexChanged.connect(
            lambda: self._refrescar_campos_id(
                self.combo_camaras, self.combo_id_camaras
            )
        )
        self._refrescar_campos_id(self.combo_camaras, self.combo_id_camaras)

        layout_ids.addWidget(QLabel('Campo ID para Tuberías:'))
        self.combo_id_tuberias = QComboBox()
        layout_ids.addWidget(self.combo_id_tuberias)
        self.combo_tuberias.currentIndexChanged.connect(
            lambda: self._refrescar_campos_id(
                self.combo_tuberias, self.combo_id_tuberias
            )
        )
        self._refrescar_campos_id(self.combo_tuberias, self.combo_id_tuberias)

        grupo_ids.setLayout(layout_ids)
        layout.addWidget(grupo_ids)

        # ---- Secciones a incluir ----
        grupo_secciones = QGroupBox('Secciones a incluir')
        layout_secciones = QVBoxLayout()

        self.chk_tuberias = QCheckBox('Tuberías (líneas)')
        self.chk_tuberias.setChecked(True)
        layout_secciones.addWidget(self.chk_tuberias)

        self.chk_camaras = QCheckBox('Cámaras (círculos)')
        self.chk_camaras.setChecked(True)
        layout_secciones.addWidget(self.chk_camaras)

        self.chk_arranques = QCheckBox('Arranques (perpendiculares en Ci)')
        self.chk_arranques.setChecked(True)
        layout_secciones.addWidget(self.chk_arranques)

        self.chk_direccion = QCheckBox('Flechas de dirección')
        self.chk_direccion.setChecked(True)
        layout_secciones.addWidget(self.chk_direccion)

        self.chk_etq_camaras = QCheckBox('Etiquetas de cámaras')
        self.chk_etq_camaras.setChecked(True)
        layout_secciones.addWidget(self.chk_etq_camaras)

        self.chk_etq_tuberias = QCheckBox('Etiquetas de tuberías')
        self.chk_etq_tuberias.setChecked(True)
        layout_secciones.addWidget(self.chk_etq_tuberias)

        grupo_secciones.setLayout(layout_secciones)
        layout.addWidget(grupo_secciones)

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

        btn_exportar = QPushButton('📤 Generar DXF Completo')
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
    # REFRESCAR CAMPOS ID
    # ============================================================
    def _refrescar_campos_id(self, combo_capa, combo_campo):
        combo_campo.clear()
        capa_id = combo_capa.currentData()
        if not capa_id:
            return
        capa = QgsProject.instance().mapLayer(capa_id)
        if not capa:
            return

        nombres = [campo.name() for campo in capa.fields()]
        combo_campo.addItems(nombres)
        if 'ID_O' in nombres:
            combo_campo.setCurrentText('ID_O')

    # ============================================================
    # SELECCIONAR RUTA DE SALIDA
    # ============================================================
    def _seleccionar_ruta(self):
        ruta, _ = QFileDialog.getSaveFileName(
            self.iface.mainWindow(),
            'Guardar DXF Completo',
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
        ruta = self.txt_ruta.text().strip()
        if not ruta:
            QMessageBox.warning(self.iface.mainWindow(), 'Error',
                                'Selecciona un archivo DXF de salida.')
            return
        if not ruta.lower().endswith('.dxf'):
            ruta += '.dxf'

        if not any([self.chk_tuberias.isChecked(),
                    self.chk_camaras.isChecked(),
                    self.chk_arranques.isChecked(),
                    self.chk_direccion.isChecked(),
                    self.chk_etq_camaras.isChecked(),
                    self.chk_etq_tuberias.isChecked()]):
            QMessageBox.warning(self.iface.mainWindow(), 'Error',
                                'Activa al menos una sección.')
            return

        tuberias_id = self.combo_tuberias.currentData()
        camaras_id = self.combo_camaras.currentData()

        self.capa_tuberias = QgsProject.instance().mapLayer(tuberias_id) \
            if tuberias_id else None
        self.capa_camaras = QgsProject.instance().mapLayer(camaras_id) \
            if camaras_id else None

        if (self.chk_tuberias.isChecked() or
            self.chk_arranques.isChecked() or
            self.chk_direccion.isChecked() or
            self.chk_etq_tuberias.isChecked()) and not self.capa_tuberias:
            QMessageBox.warning(self.iface.mainWindow(), 'Error',
                                'No se encontró la capa de tuberías.')
            return

        if (self.chk_camaras.isChecked() or
            self.chk_etq_camaras.isChecked()) and not self.capa_camaras:
            QMessageBox.warning(self.iface.mainWindow(), 'Error',
                                'No se encontró la capa de cámaras.')
            return

        crs_proyecto = QgsProject.instance().crs()
        if not crs_proyecto.isValid():
            QMessageBox.warning(self.iface.mainWindow(), 'Error',
                                'El proyecto no tiene un CRS válido.')
            return

        # --- Recopilar todo ---
        lineas = []
        circulos = []
        lineas_arranque = []
        flechas = []
        etiquetas_cam = []
        etiquetas_tub = []

        # ---- Tuberías ----
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

        # ---- Cámaras ----
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

        # ---- Arranques ----
        if self.chk_arranques.isChecked() and self.capa_tuberias:
            lineas_arranque = self._calcular_lineas_arranque(self.capa_tuberias)

        # ---- Flechas ----
        if self.chk_direccion.isChecked() and self.capa_tuberias:
            flechas = self._calcular_flechas(self.capa_tuberias)

        # ---- Etiquetas de cámaras ----
        if self.chk_etq_camaras.isChecked() and self.capa_camaras:
            campo_id = self.combo_id_camaras.currentText()
            etiquetas_cam = self._calcular_etiquetas_camaras(
                self.capa_camaras, campo_id, crs_proyecto
            )

        # ---- Etiquetas de tuberías ----
        if self.chk_etq_tuberias.isChecked() and self.capa_tuberias:
            campo_id = self.combo_id_tuberias.currentText()
            etiquetas_tub = self._calcular_etiquetas_tuberias(
                self.capa_tuberias, campo_id
            )

        # --- Extensión ---
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
        for et in etiquetas_cam:
            xs.append(et['x']); ys.append(et['y'])
        for et in etiquetas_tub:
            xs.append(et['x']); ys.append(et['y'])

        if not xs or not ys:
            QMessageBox.warning(self.iface.mainWindow(), 'Error',
                                'No hay geometrías para exportar.')
            return

        margen = 50.0
        ext = (min(xs) - margen, min(ys) - margen,
               max(xs) + margen, max(ys) + margen)

        # --- Generar DXF ---
        try:
            contenido = self._generar_dxf_completo(
                lineas, circulos, lineas_arranque, flechas,
                etiquetas_cam, etiquetas_tub, ext
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
            'DXF Completo generado',
            f'✅ DXF completo exportado.\n\n'
            f'📁 Archivo: {ruta}\n'
            f'📦 Tamaño: {tamano} bytes\n\n'
            f'📏 Tuberías: {len(lineas)}\n'
            f'⭕ Cámaras: {len(circulos)}\n'
            f'🚩 Arranques: {len(lineas_arranque)}\n'
            f'➡️  Flechas: {len(flechas)}\n'
            f'🏷️  Etiquetas cámaras: {len(etiquetas_cam)}\n'
            f'🏷️  Etiquetas tuberías: {len(etiquetas_tub)}\n\n'
            f'📌 Capas: TUBERIAS, CAMARAS, ARRANQUES, DIRECCION,\n'
            f'         ETIQUETAS, ETIQ_TUBERIAS\n\n'
            f'⚠️ Si no ves nada en CAD: ejecuta ZOOM EXTENTS (ZOOM E)'
        )

    # ============================================================
    # CÁLCULO DE ARRANQUES
    # ============================================================
    def _calcular_lineas_arranque(self, capa_tuberias):
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

            medio_x = xi + RADIO_CAMARA * ux
            medio_y = yi + RADIO_CAMARA * uy

            px = -uy
            py = ux

            mitad = RADIO_CAMARA
            p1 = (medio_x + mitad * px, medio_y + mitad * py)
            p2 = (medio_x - mitad * px, medio_y - mitad * py)

            resultado.append([p1, p2])

        return resultado

    # ============================================================
    # CÁLCULO DE FLECHAS
    # ============================================================
    def _calcular_flechas(self, capa_tuberias):
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

            xm = (xi + xf) / 2.0
            ym = (yi + yf) / 2.0

            bx = -ux
            by = -uy

            b1x = bx * cos_a - by * sin_a
            b1y = bx * sin_a + by * cos_a
            b2x = bx * cos_a + by * sin_a
            b2y = -bx * sin_a + by * cos_a

            ax = xm + FLECHA_LARGO_BRAZO * b1x
            ay = ym + FLECHA_LARGO_BRAZO * b1y
            cx = xm + FLECHA_LARGO_BRAZO * b2x
            cy = ym + FLECHA_LARGO_BRAZO * b2y

            resultado.append([
                [(ax, ay), (xm, ym)],
                [(xm, ym), (cx, cy)],
            ])

        return resultado

    # ============================================================
    # CÁLCULO DE ETIQUETAS DE CÁMARAS
    # ============================================================
    def _calcular_etiquetas_camaras(self, capa_camaras, campo_id, crs_proyecto):
        resultado = []

        try:
            transform = QgsCoordinateTransform(
                capa_camaras.crs(), crs_proyecto, QgsProject.instance()
            )
        except Exception:
            transform = None

        campos = capa_camaras.fields()
        idx_id = campos.indexFromName(campo_id) if campo_id else -1
        idx_z = campos.indexFromName('Z')
        idx_zs = campos.indexFromName('Zs')

        if idx_id == -1:
            return resultado

        for feat in capa_camaras.getFeatures():
            geom = feat.geometry()
            if geom is None or geom.isEmpty():
                continue

            punto = self._punto_de_geometria(geom)
            if punto is None:
                continue

            if transform is not None:
                try:
                    punto = transform.transform(punto)
                except Exception:
                    pass

            id_val = feat.attribute(idx_id)
            z = feat.attribute(idx_z) if idx_z != -1 else None
            zs = feat.attribute(idx_zs) if idx_zs != -1 else None

            altura = None
            if z is not None and zs is not None:
                try:
                    altura = float(z) - float(zs)
                except (TypeError, ValueError):
                    altura = None

            resultado.append({
                'x': punto.x(),
                'y': punto.y(),
                'id': str(id_val) if id_val is not None else '',
                'z': float(z) if z is not None else None,
                'zs': float(zs) if zs is not None else None,
                'altura': altura,
            })

        return resultado

    # ============================================================
    # CÁLCULO DE ETIQUETAS DE TUBERÍAS
    # ============================================================
    def _calcular_etiquetas_tuberias(self, capa_tuberias, campo_id):
        resultado = []

        campos = capa_tuberias.fields()
        idx_d = campos.indexFromName('D_mm')
        idx_s = campos.indexFromName('S_diseno')
        idx_l = campos.indexFromName('L')
        idx_zf = campos.indexFromName('Zs_f')
        idx_zi = campos.indexFromName('Zs_i')
        idx_cab = campos.indexFromName('cab_ata')
        idx_id = campos.indexFromName(campo_id) if campo_id else -1

        for feat in capa_tuberias.getFeatures():
            geom = feat.geometry()
            if geom is None or geom.isEmpty():
                continue

            geom_plana = self._aplanar_geometria(geom)
            partes = self._extraer_partes(geom_plana)
            if not partes:
                continue

            puntos = partes[0]
            if len(puntos) < 2:
                continue

            xm, ym = self._punto_medio_polilinea(puntos)
            if xm is None:
                continue

            xin_tub, yin_tub = puntos[0]
            xfin_tub, yfin_tub = puntos[-1]

            x0, y0 = puntos[0]
            x1, y1 = puntos[-1]
            dx = x1 - x0
            dy = y1 - y0
            largo = math.hypot(dx, dy)
            if largo < 1e-9:
                continue

            ux = dx / largo
            uy = dy / largo

            angulo_deg = math.degrees(math.atan2(uy, ux))
            if angulo_deg > 90.0:
                angulo_deg -= 180.0
            elif angulo_deg <= -90.0:
                angulo_deg += 180.0

            ang_rad = math.radians(angulo_deg)
            px = -math.sin(ang_rad)
            py = math.cos(ang_rad)

            altura_texto = ETQ_TUB_ALTURA_TEXTO
            altura_texto_id = altura_texto * 1.25

            # ETIQUETA ID (encima de la central)
            if idx_id != -1:
                id_val = feat.attribute(idx_id)
                if id_val is not None and str(id_val).strip() != '':
                    x_id = xm + (ETQ_TUB_DIST_PERP + ETQ_TUB_DIST_ID_EXTRA) * px
                    y_id = ym + (ETQ_TUB_DIST_PERP + ETQ_TUB_DIST_ID_EXTRA) * py
                    resultado.append({
                        'x': x_id, 'y': y_id,
                        'texto': str(id_val),
                        'angulo': angulo_deg,
                        'altura': altura_texto_id,
                    })

            # ETIQUETA CENTRAL (arriba de la tubería)
            try:
                d_num = float(feat.attribute(idx_d)) if idx_d != -1 and feat.attribute(idx_d) is not None else 0.0
            except (TypeError, ValueError):
                d_num = 0.0
            try:
                s_num = float(feat.attribute(idx_s)) if idx_s != -1 and feat.attribute(idx_s) is not None else 0.0
            except (TypeError, ValueError):
                s_num = 0.0
            try:
                l_num = float(feat.attribute(idx_l)) if idx_l != -1 and feat.attribute(idx_l) is not None else 0.0
            except (TypeError, ValueError):
                l_num = 0.0

            if abs(d_num - int(d_num)) < 1e-6:
                texto_d = f"{int(d_num)}"
            else:
                texto_d = f"{d_num:.2f}"

            texto_central = f"{texto_d} - {s_num:.{ETQ_TUB_DEC_S}f}% - {l_num:.{ETQ_TUB_DEC_L}f}"

            resultado.append({
                'x': xm + ETQ_TUB_DIST_PERP * px,
                'y': ym + ETQ_TUB_DIST_PERP * py,
                'texto': texto_central,
                'angulo': angulo_deg,
                'altura': altura_texto,
            })

            # ETIQUETA FINAL (Zs_f) — DEBAJO de la tubería
            if idx_zf != -1:
                zf_val = feat.attribute(idx_zf)
                try:
                    zf_num = float(zf_val) if zf_val is not None else None
                except (TypeError, ValueError):
                    zf_num = None

                if zf_num is not None:
                    texto_final = f"{zf_num:.{ETQ_TUB_DEC_ZF}f}"
                    dist_total = ETQ_TUB_DIST_CF + RADIO_CAMARA
                    x_cf = xfin_tub - dist_total * ux
                    y_cf = yfin_tub - dist_total * uy
                    resultado.append({
                        'x': x_cf - ETQ_TUB_DIST_PERP_CF * px,
                        'y': y_cf - ETQ_TUB_DIST_PERP_CF * py,
                        'texto': texto_final,
                        'angulo': angulo_deg,
                        'altura': altura_texto,
                    })

            # ETIQUETA INICIAL (Zs_i) — solo arranques, DEBAJO de la tubería
            if idx_zi != -1 and idx_cab != -1:
                cab_val = feat.attribute(idx_cab)
                es_arranque = False
                if cab_val is not None:
                    if str(cab_val).strip().lower() == 'arranque':
                        es_arranque = True

                if es_arranque:
                    zi_val = feat.attribute(idx_zi)
                    try:
                        zi_num = float(zi_val) if zi_val is not None else None
                    except (TypeError, ValueError):
                        zi_num = None

                    if zi_num is not None:
                        texto_inicial = f"{zi_num:.{ETQ_TUB_DEC_ZF}f}"
                        dist_total_i = ETQ_TUB_DIST_CF + RADIO_CAMARA
                        x_ci = xin_tub + dist_total_i * ux
                        y_ci = yin_tub + dist_total_i * uy
                        resultado.append({
                            'x': x_ci - ETQ_TUB_DIST_PERP_CF * px,
                            'y': y_ci - ETQ_TUB_DIST_PERP_CF * py,
                            'texto': texto_inicial,
                            'angulo': angulo_deg,
                            'altura': altura_texto,
                        })

        return resultado

    # ============================================================
    # GENERAR DXF COMPLETO
    # ============================================================
    def _generar_dxf_completo(self, lineas, circulos, lineas_arranque, flechas,
                              etiquetas_cam, etiquetas_tub, ext):
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

        # LAYER (7 capas)
        out.append("0\nTABLE\n2\nLAYER\n70\n7\n")
        out.append("0\nLAYER\n2\n0\n70\n0\n62\n7\n6\nCONTINUOUS\n")
        out.append("0\nLAYER\n2\nTUBERIAS\n70\n0\n62\n7\n6\nCONTINUOUS\n")
        out.append("0\nLAYER\n2\nCAMARAS\n70\n0\n62\n7\n6\nCONTINUOUS\n")
        out.append("0\nLAYER\n2\nARRANQUES\n70\n0\n62\n1\n6\nCONTINUOUS\n")
        out.append("0\nLAYER\n2\nDIRECCION\n70\n0\n62\n3\n6\nCONTINUOUS\n")
        out.append("0\nLAYER\n2\nETIQUETAS\n70\n0\n62\n4\n6\nCONTINUOUS\n")
        out.append("0\nLAYER\n2\nETIQ_TUBERIAS\n70\n0\n62\n5\n6\nCONTINUOUS\n")
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

        # ---- Tuberías ----
        for linea in lineas:
            out.append("0\nPOLYLINE\n8\nTUBERIAS\n66\n1\n70\n0\n")
            for x, y in linea:
                out.append(
                    f"0\nVERTEX\n8\nTUBERIAS\n10\n{x:.6f}\n20\n{y:.6f}\n30\n0.0\n"
                )
            out.append("0\nSEQEND\n8\nTUBERIAS\n")

        # ---- Cámaras ----
        for x, y, r in circulos:
            out.append(
                f"0\nCIRCLE\n8\nCAMARAS\n"
                f"10\n{x:.6f}\n20\n{y:.6f}\n30\n0.0\n40\n{r:.6f}\n"
            )

        # ---- Arranques ----
        for linea in lineas_arranque:
            out.append("0\nPOLYLINE\n8\nARRANQUES\n66\n1\n70\n0\n")
            for x, y in linea:
                out.append(
                    f"0\nVERTEX\n8\nARRANQUES\n10\n{x:.6f}\n20\n{y:.6f}\n30\n0.0\n"
                )
            out.append("0\nSEQEND\n8\nARRANQUES\n")

        # ---- Flechas ----
        for flecha in flechas:
            for segmento in flecha:
                out.append("0\nPOLYLINE\n8\nDIRECCION\n66\n1\n70\n0\n")
                for x, y in segmento:
                    out.append(
                        f"0\nVERTEX\n8\nDIRECCION\n10\n{x:.6f}\n20\n{y:.6f}\n30\n0.0\n"
                    )
                out.append("0\nSEQEND\n8\nDIRECCION\n")

        # ---- Etiquetas de cámaras ----
        for et in etiquetas_cam:
            xc = et['x']
            yc = et['y']

            xfin = xc + ETQ_CAM_DESP_X
            yfin = yc + ETQ_CAM_DESP_Y

            # Línea oblicua
            out.append("0\nPOLYLINE\n8\nETIQUETAS\n66\n1\n70\n0\n")
            for x, y in [(xc, yc), (xfin, yfin)]:
                out.append(
                    f"0\nVERTEX\n8\nETIQUETAS\n10\n{x:.6f}\n20\n{y:.6f}\n30\n0.0\n"
                )
            out.append("0\nSEQEND\n8\nETIQUETAS\n")

            # Línea horizontal
            x_hr = xfin + ETQ_CAM_LARGO_LINEA
            out.append("0\nPOLYLINE\n8\nETIQUETAS\n66\n1\n70\n0\n")
            for x, y in [(xfin, yfin), (x_hr, yfin)]:
                out.append(
                    f"0\nVERTEX\n8\nETIQUETAS\n10\n{x:.6f}\n20\n{y:.6f}\n30\n0.0\n"
                )
            out.append("0\nSEQEND\n8\nETIQUETAS\n")

            altura_texto_id = ETQ_CAM_ALTURA_TEXTO * 1.25

            # ID de cámara (arriba)
            if et['id']:
                self._escribir_texto(
                    out, et['id'],
                    xfin, yfin + ETQ_CAM_DIST + altura_texto_id,
                    altura_texto_id, "ETIQUETAS"
                )

            # Zt (arriba de la línea)
            if et['z'] is not None:
                self._escribir_texto(
                    out, f"{et['z']:.2f}",
                    xfin, yfin + ETQ_CAM_DIST,
                    ETQ_CAM_ALTURA_TEXTO, "ETIQUETAS"
                )

            # Zs (debajo de la línea)
            if et['zs'] is not None:
                self._escribir_texto(
                    out, f"{et['zs']:.2f}",
                    xfin, yfin - ETQ_CAM_DIST - ETQ_CAM_ALTURA_TEXTO,
                    ETQ_CAM_ALTURA_TEXTO, "ETIQUETAS"
                )

            # Altura (al final de la línea horizontal)
            if et['altura'] is not None:
                self._escribir_texto(
                    out, f"{et['altura']:.2f}",
                    x_hr + ETQ_CAM_DIST, yfin - ETQ_CAM_ALTURA_TEXTO / 2.0,
                    ETQ_CAM_ALTURA_TEXTO, "ETIQUETAS"
                )

        # ---- Etiquetas de tuberías ----
        for et in etiquetas_tub:
            self._escribir_texto_rotado(
                out, et['texto'],
                et['x'], et['y'],
                et.get('altura', ETQ_TUB_ALTURA_TEXTO),
                et['angulo'],
                "ETIQ_TUBERIAS"
            )

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

    def _punto_medio_polilinea(self, puntos):
        if not puntos or len(puntos) < 2:
            return None, None

        largo_total = 0.0
        segmentos = []
        for i in range(len(puntos) - 1):
            x1, y1 = puntos[i]
            x2, y2 = puntos[i + 1]
            dx = x2 - x1
            dy = y2 - y1
            l = math.hypot(dx, dy)
            if l > 1e-9:
                segmentos.append((x1, y1, dx, dy, l))
                largo_total += l

        if largo_total < 1e-9:
            return puntos[0]

        mitad = largo_total / 2.0
        acumulado = 0.0

        for (x1, y1, dx, dy, l) in segmentos:
            if acumulado + l >= mitad:
                resta = mitad - acumulado
                t = resta / l
                xm = x1 + dx * t
                ym = y1 + dy * t
                return xm, ym
            acumulado += l

        return puntos[-1]

    def _escribir_texto(self, out, texto, x, y, altura, capa):
        texto_seguro = texto.replace('\n', ' ').replace('\r', '')
        out.append(
            f"0\nTEXT\n8\n{capa}\n"
            f"10\n{x:.6f}\n20\n{y:.6f}\n30\n0.0\n"
            f"40\n{altura:.4f}\n"
            f"1\n{texto_seguro}\n"
        )

    def _escribir_texto_rotado(self, out, texto, x, y, altura, angulo, capa):
        texto_seguro = texto.replace('\n', ' ').replace('\r', '')
        out.append(
            f"0\nTEXT\n8\n{capa}\n"
            f"10\n{x:.6f}\n20\n{y:.6f}\n30\n0.0\n"
            f"40\n{altura:.4f}\n"
            f"1\n{texto_seguro}\n"
            f"50\n{angulo:.4f}\n"
            f"72\n1\n"
            f"73\n2\n"
            f"11\n{x:.6f}\n21\n{y:.6f}\n31\n0.0\n"
        )

    def desactivar(self, mostrar_mensaje=True):
        pass