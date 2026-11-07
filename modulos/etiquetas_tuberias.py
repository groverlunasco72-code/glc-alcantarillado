# -*- coding: utf-8 -*-
"""
Módulo: Etiquetas de Tuberías (DXF)

Genera un DXF independiente SOLO con las etiquetas de las tuberías.

Para cada tubería:
    • Etiqueta ID: campo seleccionable, encima de la etiqueta central
    • Etiqueta central: "D_mm - S_diseno% - L"
    • Etiqueta final: "Zs_f"
    • Etiqueta inicial: "Zs_i" (SOLO en tuberías de arranque)
      (usa los MISMOS parámetros que la etiqueta final)

Capa DXF: ETIQ_TUBERIAS
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
    QFileDialog, QLineEdit, QGroupBox, QDoubleSpinBox,
    QCheckBox
)


# ============================================================
# PARÁMETROS POR DEFECTO
# ============================================================
DISTANCIA_PERP = 2.5            # distancia perpendicular etiqueta central (m)
DISTANCIA_ID_EXTRA = 3          # distancia adicional del ID sobre la central (m)
ALTURA_TEXTO = 2.0              # altura del texto (m)
DECIMALES_S = 2                 # decimales para la pendiente
DECIMALES_L = 2                 # decimales para la longitud

# Etiquetas en extremos (Zs_f y Zs_i comparten estos parámetros)
DISTANCIA_LARGO_CF = 10         # distancia desde extremo (m)
DISTANCIA_PERP_CF = 1.0         # distancia perpendicular (m)
DECIMALES_ZF = 2                # decimales

# Radio de la cámara
DIAMETRO_CAMARA = 6.0
RADIO_CAMARA = DIAMETRO_CAMARA / 2.0


class EtiquetasTuberias:
    def __init__(self, iface):
        self.iface = iface
        self.ruta_salida = None
        self.capa_tuberias = None

    # ============================================================
    # DIÁLOGO
    # ============================================================
    def mostrar_dialogo(self):
        dialog = QDialog(self.iface.mainWindow())
        dialog.setWindowTitle('GLC - Etiquetas de Tuberías (DXF)')
        dialog.setMinimumWidth(650)
        self.dialog = dialog

        layout = QVBoxLayout()

        titulo = QLabel('<b>🏷️  Etiquetas Tuberías</b>')
        titulo.setStyleSheet('font-size: 14pt; font-weight: bold;')
        layout.addWidget(titulo)

        layout.addWidget(QLabel('-' * 50))

        # ---- Capa de tuberías ----
        layout.addWidget(QLabel('Capa de Tuberías:'))
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
        layout.addWidget(self.combo_tuberias)

        # ---- Campo para el ID ----
        layout.addWidget(QLabel('Campo para el ID de tubería:'))
        self.combo_campo_id = QComboBox()
        layout.addWidget(self.combo_campo_id)
        self.combo_tuberias.currentIndexChanged.connect(self._refrescar_campos_id)
        self._refrescar_campos_id()

        layout.addWidget(QLabel('-' * 50))

        # ---- Parámetros generales ----
        grupo_params = QGroupBox('Parámetros generales')
        layout_params = QVBoxLayout()

        h2 = QHBoxLayout()
        h2.addWidget(QLabel('Altura del texto (m):'))
        self.spin_altura = QDoubleSpinBox()
        self.spin_altura.setRange(0.5, 20.0)
        self.spin_altura.setSingleStep(0.1)
        self.spin_altura.setDecimals(2)
        self.spin_altura.setValue(ALTURA_TEXTO)
        h2.addWidget(self.spin_altura, 1)
        layout_params.addLayout(h2)

        h3 = QHBoxLayout()
        h3.addWidget(QLabel('Decimales pendiente (S):'))
        self.spin_dec_s = QDoubleSpinBox()
        self.spin_dec_s.setRange(0, 6)
        self.spin_dec_s.setSingleStep(1)
        self.spin_dec_s.setDecimals(0)
        self.spin_dec_s.setValue(DECIMALES_S)
        h3.addWidget(self.spin_dec_s, 1)
        layout_params.addLayout(h3)

        h4 = QHBoxLayout()
        h4.addWidget(QLabel('Decimales longitud (L):'))
        self.spin_dec_l = QDoubleSpinBox()
        self.spin_dec_l.setRange(0, 6)
        self.spin_dec_l.setSingleStep(1)
        self.spin_dec_l.setDecimals(0)
        self.spin_dec_l.setValue(DECIMALES_L)
        h4.addWidget(self.spin_dec_l, 1)
        layout_params.addLayout(h4)

        grupo_params.setLayout(layout_params)
        layout.addWidget(grupo_params)

        # ---- Etiqueta central + ID ----
        grupo_central = QGroupBox('Etiqueta central (D - S% - L) + ID')
        layout_central = QVBoxLayout()

        hc1 = QHBoxLayout()
        hc1.addWidget(QLabel('Distancia perpendicular central (m):'))
        self.spin_dist = QDoubleSpinBox()
        self.spin_dist.setRange(0.1, 20.0)
        self.spin_dist.setSingleStep(0.1)
        self.spin_dist.setDecimals(2)
        self.spin_dist.setValue(DISTANCIA_PERP)
        hc1.addWidget(self.spin_dist, 1)
        layout_central.addLayout(hc1)

        hc2 = QHBoxLayout()
        hc2.addWidget(QLabel('Distancia ID sobre central (m):'))
        self.spin_dist_id = QDoubleSpinBox()
        self.spin_dist_id.setRange(0.1, 20.0)
        self.spin_dist_id.setSingleStep(0.1)
        self.spin_dist_id.setDecimals(2)
        self.spin_dist_id.setValue(DISTANCIA_ID_EXTRA)
        hc2.addWidget(self.spin_dist_id, 1)
        layout_central.addLayout(hc2)

        self.chk_mostrar_id = QCheckBox('Mostrar ID de tubería')
        self.chk_mostrar_id.setChecked(True)
        layout_central.addWidget(self.chk_mostrar_id)

        self.chk_mostrar_central = QCheckBox('Mostrar etiqueta central (D - S% - L)')
        self.chk_mostrar_central.setChecked(True)
        layout_central.addWidget(self.chk_mostrar_central)

        grupo_central.setLayout(layout_central)
        layout.addWidget(grupo_central)

        # ---- Etiquetas en extremos ----
        grupo_final = QGroupBox('Etiquetas en extremos (Zs_f y Zs_i)')
        layout_final = QVBoxLayout()

        hf1 = QHBoxLayout()
        hf1.addWidget(QLabel('Distancia desde extremo (m):'))
        self.spin_dist_cf = QDoubleSpinBox()
        self.spin_dist_cf.setRange(0.1, 50.0)
        self.spin_dist_cf.setSingleStep(0.5)
        self.spin_dist_cf.setDecimals(2)
        self.spin_dist_cf.setValue(DISTANCIA_LARGO_CF)
        hf1.addWidget(self.spin_dist_cf, 1)
        layout_final.addLayout(hf1)

        hf2 = QHBoxLayout()
        hf2.addWidget(QLabel('Distancia perpendicular (m):'))
        self.spin_dist_perp_cf = QDoubleSpinBox()
        self.spin_dist_perp_cf.setRange(0.1, 20.0)
        self.spin_dist_perp_cf.setSingleStep(0.1)
        self.spin_dist_perp_cf.setDecimals(2)
        self.spin_dist_perp_cf.setValue(DISTANCIA_PERP_CF)
        hf2.addWidget(self.spin_dist_perp_cf, 1)
        layout_final.addLayout(hf2)

        hf3 = QHBoxLayout()
        hf3.addWidget(QLabel('Decimales Zs:'))
        self.spin_dec_zf = QDoubleSpinBox()
        self.spin_dec_zf.setRange(0, 6)
        self.spin_dec_zf.setSingleStep(1)
        self.spin_dec_zf.setDecimals(0)
        self.spin_dec_zf.setValue(DECIMALES_ZF)
        hf3.addWidget(self.spin_dec_zf, 1)
        layout_final.addLayout(hf3)

        self.chk_mostrar_final = QCheckBox('Mostrar etiqueta final (Zs_f)')
        self.chk_mostrar_final.setChecked(True)
        layout_final.addWidget(self.chk_mostrar_final)

        self.chk_mostrar_inicial = QCheckBox('Mostrar etiqueta inicial (Zs_i) en arranques')
        self.chk_mostrar_inicial.setChecked(True)
        layout_final.addWidget(self.chk_mostrar_inicial)

        grupo_final.setLayout(layout_final)
        layout.addWidget(grupo_final)

        # ---- Filtros ----
        self.chk_solo_con_diam = QCheckBox('Solo tuberías con D_mm > 0')
        self.chk_solo_con_diam.setChecked(False)
        layout.addWidget(self.chk_solo_con_diam)

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

        btn_exportar = QPushButton('📤 Generar DXF de Etiquetas')
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
    # REFRESCAR LISTA DE CAMPOS DE ID
    # ============================================================
    def _refrescar_campos_id(self):
        self.combo_campo_id.clear()
        capa_id = self.combo_tuberias.currentData()
        if not capa_id:
            return
        capa = QgsProject.instance().mapLayer(capa_id)
        if not capa:
            return

        nombres = [campo.name() for campo in capa.fields()]
        self.combo_campo_id.addItems(nombres)

        if 'ID_O' in nombres:
            self.combo_campo_id.setCurrentText('ID_O')

    # ============================================================
    # SELECCIONAR RUTA DE SALIDA
    # ============================================================
    def _seleccionar_ruta(self):
        ruta, _ = QFileDialog.getSaveFileName(
            self.iface.mainWindow(),
            'Guardar DXF de Etiquetas de Tuberías',
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

        capa_id = self.combo_tuberias.currentData()
        if not capa_id:
            QMessageBox.warning(self.iface.mainWindow(), 'Error',
                                'Selecciona una capa de tuberías.')
            return

        self.capa_tuberias = QgsProject.instance().mapLayer(capa_id)
        if not self.capa_tuberias:
            QMessageBox.warning(self.iface.mainWindow(), 'Error',
                                'No se encontró la capa de tuberías.')
            return

        crs_proyecto = QgsProject.instance().crs()
        if not crs_proyecto.isValid():
            QMessageBox.warning(self.iface.mainWindow(), 'Error',
                                'El proyecto no tiene un CRS válido.')
            return

        campo_id_nombre = self.combo_campo_id.currentText()

        dist_perp = self.spin_dist.value()
        dist_id_extra = self.spin_dist_id.value()
        altura_texto = self.spin_altura.value()
        altura_texto_id = altura_texto * 1.25
        dec_s = int(self.spin_dec_s.value())
        dec_l = int(self.spin_dec_l.value())
        solo_con_diam = self.chk_solo_con_diam.isChecked()

        dist_cf = self.spin_dist_cf.value()
        dist_perp_cf = self.spin_dist_perp_cf.value()
        dec_zf = int(self.spin_dec_zf.value())

        # La etiqueta inicial usa los MISMOS parámetros que la final
        dist_ci = dist_cf
        dist_perp_ci = dist_perp_cf
        dec_zi = dec_zf

        mostrar_inicial = self.chk_mostrar_inicial.isChecked()
        mostrar_id = self.chk_mostrar_id.isChecked()
        mostrar_central = self.chk_mostrar_central.isChecked()
        mostrar_final = self.chk_mostrar_final.isChecked()

        if not mostrar_id and not mostrar_central \
                and not mostrar_final and not mostrar_inicial:
            QMessageBox.warning(self.iface.mainWindow(), 'Error',
                                'Activa al menos una etiqueta.')
            return

        try:
            transform = QgsCoordinateTransform(
                self.capa_tuberias.crs(), crs_proyecto,
                QgsProject.instance()
            )
        except Exception:
            transform = None

        campos = self.capa_tuberias.fields()
        idx_d = campos.indexFromName('D_mm')
        idx_s = campos.indexFromName('S_diseno')
        idx_l = campos.indexFromName('L')
        idx_zf = campos.indexFromName('Zs_f')
        idx_zi = campos.indexFromName('Zs_i')
        idx_cab = campos.indexFromName('cab_ata')
        idx_id = campos.indexFromName(campo_id_nombre) if campo_id_nombre else -1

        if mostrar_central and (idx_d == -1 or idx_s == -1 or idx_l == -1):
            QMessageBox.warning(
                self.iface.mainWindow(), 'Error',
                'La capa no tiene los campos D_mm, S_diseno o L.'
            )
            return

        if mostrar_id and idx_id == -1:
            QMessageBox.warning(
                self.iface.mainWindow(), 'Error',
                f'La capa no tiene el campo "{campo_id_nombre}".'
            )
            return

        etiquetas = []
        for feat in self.capa_tuberias.getFeatures():
            geom = feat.geometry()
            if geom is None or geom.isEmpty():
                continue

            d_mm = feat.attribute(idx_d) if idx_d != -1 else None

            if solo_con_diam:
                try:
                    if d_mm is None or float(d_mm) <= 0:
                        continue
                except (TypeError, ValueError):
                    continue

            geom_plana = self._aplanar_geometria(geom)
            if transform is not None:
                try:
                    geom_plana.transform(transform)
                except Exception:
                    pass

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

            # ============================================================
            # ETIQUETA ID
            # ============================================================
            if mostrar_id:
                id_val = feat.attribute(idx_id)
                if id_val is not None and str(id_val).strip() != '':
                    x_id = xm + (dist_perp + dist_id_extra) * px
                    y_id = ym + (dist_perp + dist_id_extra) * py
                    etiquetas.append({
                        'x': x_id,
                        'y': y_id,
                        'texto': str(id_val),
                        'angulo': angulo_deg,
                        'altura': altura_texto_id,
                    })

            # ============================================================
            # ETIQUETA CENTRAL
            # ============================================================
            if mostrar_central:
                try:
                    d_num = float(d_mm) if d_mm is not None else 0.0
                except (TypeError, ValueError):
                    d_num = 0.0
                s_dis = feat.attribute(idx_s)
                l_val = feat.attribute(idx_l)
                try:
                    s_num = float(s_dis) if s_dis is not None else 0.0
                except (TypeError, ValueError):
                    s_num = 0.0
                try:
                    l_num = float(l_val) if l_val is not None else 0.0
                except (TypeError, ValueError):
                    l_num = 0.0

                if abs(d_num - int(d_num)) < 1e-6:
                    texto_d = f"{int(d_num)}"
                else:
                    texto_d = f"{d_num:.2f}"

                texto_s = f"{s_num:.{dec_s}f}"
                texto_l = f"{l_num:.{dec_l}f}"
                texto_central = f"{texto_d} - {texto_s}% - {texto_l}"

                etiquetas.append({
                    'x': xm + dist_perp * px,
                    'y': ym + dist_perp * py,
                    'texto': texto_central,
                    'angulo': angulo_deg,
                    'altura': altura_texto,
                })

            # ============================================================
            # ETIQUETA FINAL (Zs_f)
            # ============================================================
            if mostrar_final and idx_zf != -1:
                zf_val = feat.attribute(idx_zf)
                try:
                    zf_num = float(zf_val) if zf_val is not None else None
                except (TypeError, ValueError):
                    zf_num = None

                if zf_num is not None:
                    texto_final = f"{zf_num:.{dec_zf}f}"
                    dist_total = dist_cf + RADIO_CAMARA
                    x_cf = xfin_tub - dist_total * ux
                    y_cf = yfin_tub - dist_total * uy
                    etiquetas.append({
                        'x': x_cf + dist_perp_cf * px,
                        'y': y_cf + dist_perp_cf * py,
                        'texto': texto_final,
                        'angulo': angulo_deg,
                        'altura': altura_texto,
                    })

            # ============================================================
            # ETIQUETA INICIAL (Zs_i) — solo arranques
            # ============================================================
            if mostrar_inicial and idx_zi != -1 and idx_cab != -1:
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
                        texto_inicial = f"{zi_num:.{dec_zi}f}"
                        dist_total_i = dist_ci + RADIO_CAMARA
                        x_ci = xin_tub + dist_total_i * ux
                        y_ci = yin_tub + dist_total_i * uy
                        etiquetas.append({
                            'x': x_ci + dist_perp_ci * px,
                            'y': y_ci + dist_perp_ci * py,
                            'texto': texto_inicial,
                            'angulo': angulo_deg,
                            'altura': altura_texto,
                        })

        if not etiquetas:
            QMessageBox.warning(self.iface.mainWindow(), 'Error',
                                'No hay tuberías para etiquetar.')
            return

        # --- Extensión ---
        xs, ys = [], []
        for et in etiquetas:
            xs.append(et['x'])
            ys.append(et['y'])
        margen = max(altura_texto * 20, 10.0)
        ext = (min(xs) - margen, min(ys) - margen,
               max(xs) + margen, max(ys) + margen)

        try:
            contenido = self._generar_dxf(etiquetas, ext)
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
            'Etiquetas generadas',
            f'✅ DXF de etiquetas de tuberías exportado.\n\n'
            f'📁 Archivo: {ruta}\n'
            f'📦 Tamaño: {tamano} bytes\n'
            f'🏷️  Etiquetas dibujadas: {len(etiquetas)}\n'
            f'🔑 Campo ID usado: {campo_id_nombre}\n\n'
            f'📌 Capa del DXF: ETIQ_TUBERIAS\n\n'
            f'⚠️ Si no ves nada en CAD: ejecuta ZOOM EXTENTS (ZOOM E)'
        )

    # ============================================================
    # GENERAR CONTENIDO DXF R12
    # ============================================================
    def _generar_dxf(self, etiquetas, ext):
        emin_x, emin_y, emax_x, emax_y = ext
        out = []

        altura_def = ALTURA_TEXTO

        out.append("0\nSECTION\n2\nHEADER\n")
        out.append("9\n$ACADVER\n1\nAC1009\n")
        out.append("9\n$INSUNITS\n70\n6\n")
        out.append(f"9\n$EXTMIN\n10\n{emin_x:.6f}\n20\n{emin_y:.6f}\n30\n0.0\n")
        out.append(f"9\n$EXTMAX\n10\n{emax_x:.6f}\n20\n{emax_y:.6f}\n30\n0.0\n")
        out.append("9\n$LIMMIN\n10\n0.0\n20\n0.0\n")
        out.append("9\n$LIMMAX\n10\n420.0\n20\n297.0\n")
        out.append("9\n$LTSCALE\n40\n1.0\n")
        out.append(f"9\n$TEXTSIZE\n40\n{altura_def:.4f}\n")
        out.append("0\nENDSEC\n")

        out.append("0\nSECTION\n2\nTABLES\n")
        out.append("0\nTABLE\n2\nLTYPE\n70\n1\n")
        out.append(
            "0\nLTYPE\n2\nCONTINUOUS\n70\n64\n"
            "3\nSolid line\n72\n65\n73\n0\n40\n0.0\n"
        )
        out.append("0\nENDTAB\n")

        out.append("0\nTABLE\n2\nLAYER\n70\n2\n")
        out.append("0\nLAYER\n2\n0\n70\n0\n62\n7\n6\nCONTINUOUS\n")
        out.append("0\nLAYER\n2\nETIQ_TUBERIAS\n70\n0\n62\n5\n6\nCONTINUOUS\n")
        out.append("0\nENDTAB\n")

        out.append("0\nTABLE\n2\nSTYLE\n70\n1\n")
        out.append(
            "0\nSTYLE\n2\nSTANDARD\n70\n0\n40\n0.0\n"
            f"41\n1.0\n50\n0.0\n71\n0\n42\n{altura_def:.4f}\n3\ntxt\n4\n\n"
        )
        out.append("0\nENDTAB\n")

        out.append("0\nENDSEC\n")

        out.append("0\nSECTION\n2\nENTITIES\n")

        for et in etiquetas:
            self._escribir_texto_rotado(
                out, et['texto'],
                et['x'], et['y'],
                et.get('altura', altura_def),
                et['angulo'],
                "ETIQ_TUBERIAS"
            )

        out.append("0\nENDSEC\n")
        out.append("0\nEOF\n")

        return "".join(out)

    # ============================================================
    # ESCRIBIR TEXTO ROTADO
    # ============================================================
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

    # ============================================================
    # PUNTO MEDIO SOBRE UNA POLILÍNEA
    # ============================================================
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

    # ============================================================
    # EXTRAER PARTES DE UNA GEOMETRÍA
    # ============================================================
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

    # ============================================================
    # APLANAR GEOMETRÍA
    # ============================================================
    def _aplanar_geometria(self, geom):
        try:
            if QgsWkbTypes.hasZ(geom.wkbType()):
                geom_sin_z = QgsGeometry(geom)
                geom_sin_z.get().dropZValue()
                return geom_sin_z
        except Exception:
            pass
        return geom

    # ============================================================
    # DESACTIVAR
    # ============================================================
    def desactivar(self, mostrar_mensaje=True):
        pass