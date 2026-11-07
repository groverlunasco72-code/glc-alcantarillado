# -*- coding: utf-8 -*-
"""
Módulo: Etiquetas de Cámaras (DXF)

Genera un DXF independiente SOLO con las etiquetas de las cámaras.

Para cada cámara:
    • Línea oblicua desde el centro hasta (Xc + 5.5, Yc + 5.5)
    • Línea horizontal de 14 unidades desde ese punto
    • Etiquetas (texto horizontal):
        - ID (campo seleccionable) arriba, texto más grande
        - Cota terreno (Z) arriba de la línea (solo número)
        - Cota solera (Zs) abajo de la línea (solo número)
        - Altura = Z - Zs al final de la línea (solo número)

Capa DXF: ETIQUETAS
Formato: DXF R12 (AC1009)
"""

import os
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
# PARÁMETROS POR DEFECTO (configurables desde el diálogo)
# ============================================================
DESPLAZAMIENTO_X = 7.5           # Δx desde el centro
DESPLAZAMIENTO_Y = 7.5           # Δy desde el centro
LARGO_LINEA_HORIZONTAL = 14.0    # unidades
ALTURA_TEXTO = 2.0               # altura del texto (metros)
DISTANCIA_ETIQUETA = 1.3         # distancia del texto a la línea


class EtiquetasCamaras:
    def __init__(self, iface):
        self.iface = iface
        self.ruta_salida = None
        self.capa_camaras = None

    # ============================================================
    # DIÁLOGO
    # ============================================================
    def mostrar_dialogo(self):
        dialog = QDialog(self.iface.mainWindow())
        dialog.setWindowTitle('GLC - Etiquetas de Cámaras (DXF)')
        dialog.setMinimumWidth(620)
        self.dialog = dialog

        layout = QVBoxLayout()

        titulo = QLabel('<b>🏷️  Etiquetas de Cámaras</b>')
        titulo.setStyleSheet('font-size: 14pt; font-weight: bold;')
        layout.addWidget(titulo)

        info = QLabel(
            'Genera un DXF con las etiquetas de cada cámara:\n\n'
            '• Línea oblicua desde el centro hasta (Xc+5.5, Yc+5.5)\n'
            '• Línea horizontal de 14 unidades\n'
            '• Textos horizontales: ID, Z, Zs, Altura\n'
            '  (Z, Zs y Altura solo con el número, sin prefijos)\n\n'
            'El DXF se puede abrir junto al DXF de la red.'
        )
        info.setWordWrap(True)
        layout.addWidget(info)

        layout.addWidget(QLabel('-' * 50))

        # ---- Capa de cámaras ----
        layout.addWidget(QLabel('Capa de Cámaras:'))
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
        layout.addWidget(self.combo_camaras)

        # ---- Campo para el ID ----
        layout.addWidget(QLabel('Campo para el ID:'))
        self.combo_campo_id = QComboBox()
        layout.addWidget(self.combo_campo_id)

        # Conectar el cambio de capa para refrescar la lista de campos
        self.combo_camaras.currentIndexChanged.connect(self._refrescar_campos_id)
        self._refrescar_campos_id()

        layout.addWidget(QLabel('-' * 50))

        # ---- Parámetros configurables ----
        grupo_params = QGroupBox('Parámetros')
        layout_params = QVBoxLayout()

        h1 = QHBoxLayout()
        h1.addWidget(QLabel('Altura del texto (m):'))
        self.spin_altura = QDoubleSpinBox()
        self.spin_altura.setRange(0.5, 20.0)
        self.spin_altura.setSingleStep(0.1)
        self.spin_altura.setDecimals(2)
        self.spin_altura.setValue(ALTURA_TEXTO)
        h1.addWidget(self.spin_altura, 1)
        layout_params.addLayout(h1)

        h2 = QHBoxLayout()
        h2.addWidget(QLabel('Distancia etiqueta-línea (m):'))
        self.spin_dist = QDoubleSpinBox()
        self.spin_dist.setRange(0.1, 10.0)
        self.spin_dist.setSingleStep(0.1)
        self.spin_dist.setDecimals(2)
        self.spin_dist.setValue(DISTANCIA_ETIQUETA)
        h2.addWidget(self.spin_dist, 1)
        layout_params.addLayout(h2)

        h3 = QHBoxLayout()
        h3.addWidget(QLabel('Largo línea horizontal:'))
        self.spin_largo = QDoubleSpinBox()
        self.spin_largo.setRange(5.0, 50.0)
        self.spin_largo.setSingleStep(0.5)
        self.spin_largo.setDecimals(2)
        self.spin_largo.setValue(LARGO_LINEA_HORIZONTAL)
        h3.addWidget(self.spin_largo, 1)
        layout_params.addLayout(h3)

        self.chk_id = QCheckBox('Mostrar ID de cámara')
        self.chk_id.setChecked(True)
        layout_params.addWidget(self.chk_id)

        self.chk_zt = QCheckBox('Mostrar cota terreno (Z)')
        self.chk_zt.setChecked(True)
        layout_params.addWidget(self.chk_zt)

        self.chk_zs = QCheckBox('Mostrar cota solera (Zs)')
        self.chk_zs.setChecked(True)
        layout_params.addWidget(self.chk_zs)

        self.chk_altura = QCheckBox('Mostrar altura (Z - Zs)')
        self.chk_altura.setChecked(True)
        layout_params.addWidget(self.chk_altura)

        grupo_params.setLayout(layout_params)
        layout.addWidget(grupo_params)

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
        """Rellena el combo con los campos de la capa de cámaras seleccionada."""
        self.combo_campo_id.clear()
        capa_id = self.combo_camaras.currentData()
        if not capa_id:
            return
        capa = QgsProject.instance().mapLayer(capa_id)
        if not capa:
            return

        nombres = [campo.name() for campo in capa.fields()]
        self.combo_campo_id.addItems(nombres)

        # Seleccionar ID_O por defecto si existe
        if 'ID_O' in nombres:
            self.combo_campo_id.setCurrentText('ID_O')

    # ============================================================
    # SELECCIONAR RUTA DE SALIDA
    # ============================================================
    def _seleccionar_ruta(self):
        ruta, _ = QFileDialog.getSaveFileName(
            self.iface.mainWindow(),
            'Guardar DXF de Etiquetas',
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

        capa_id = self.combo_camaras.currentData()
        if not capa_id:
            QMessageBox.warning(self.iface.mainWindow(), 'Error',
                                'Selecciona una capa de cámaras.')
            return

        self.capa_camaras = QgsProject.instance().mapLayer(capa_id)
        if not self.capa_camaras:
            QMessageBox.warning(self.iface.mainWindow(), 'Error',
                                'No se encontró la capa de cámaras.')
            return

        crs_proyecto = QgsProject.instance().crs()
        if not crs_proyecto.isValid():
            QMessageBox.warning(self.iface.mainWindow(), 'Error',
                                'El proyecto no tiene un CRS válido.')
            return

        # Campo elegido para el ID
        campo_id_nombre = self.combo_campo_id.currentText()
        if not campo_id_nombre:
            QMessageBox.warning(self.iface.mainWindow(), 'Error',
                                'Selecciona un campo para el ID.')
            return

        altura_texto = self.spin_altura.value()
        altura_texto_id = altura_texto * 1.25
        dist_etiqueta = self.spin_dist.value()
        largo_linea = self.spin_largo.value()

        try:
            transform = QgsCoordinateTransform(
                self.capa_camaras.crs(), crs_proyecto,
                QgsProject.instance()
            )
        except Exception:
            transform = None

        campos = self.capa_camaras.fields()
        idx_id = campos.indexFromName(campo_id_nombre)
        idx_z = campos.indexFromName('Z')
        idx_zs = campos.indexFromName('Zs')

        if idx_id == -1:
            QMessageBox.warning(self.iface.mainWindow(), 'Error',
                                f'La capa no tiene el campo "{campo_id_nombre}".')
            return

        etiquetas = []
        for feat in self.capa_camaras.getFeatures():
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

            etiquetas.append({
                'x': punto.x(),
                'y': punto.y(),
                'id': str(id_val) if id_val is not None else '',
                'z': float(z) if z is not None else None,
                'zs': float(zs) if zs is not None else None,
                'altura': altura,
            })

        if not etiquetas:
            QMessageBox.warning(self.iface.mainWindow(), 'Error',
                                'No hay cámaras para etiquetar.')
            return

        xs, ys = [], []
        for et in etiquetas:
            xs.extend([et['x'], et['x'] + DESPLAZAMIENTO_X + largo_linea])
            ys.extend([et['y'], et['y'] + DESPLAZAMIENTO_Y])
        margen = max(altura_texto * 10, dist_etiqueta * 10)
        ext = (min(xs) - margen, min(ys) - margen,
               max(xs) + margen, max(ys) + margen)

        try:
            contenido = self._generar_dxf(
                etiquetas,
                altura_texto, altura_texto_id, dist_etiqueta,
                largo_linea,
                self.chk_id.isChecked(),
                self.chk_zt.isChecked(),
                self.chk_zs.isChecked(),
                self.chk_altura.isChecked(),
                ext
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
            'Etiquetas generadas',
            f'✅ DXF de etiquetas exportado.\n\n'
            f'📁 Archivo: {ruta}\n'
            f'📦 Tamaño: {tamano} bytes\n'
            f'🏷️  Cámaras etiquetadas: {len(etiquetas)}\n'
            f'🔑 Campo ID usado: {campo_id_nombre}\n\n'
            f'📌 Capa del DXF: ETIQUETAS\n\n'
            f'⚠️ Si no ves nada en CAD: ejecuta ZOOM EXTENTS (ZOOM E)'
        )

    # ============================================================
    # GENERAR CONTENIDO DXF R12
    # ============================================================
    def _generar_dxf(self, etiquetas,
                     altura_texto, altura_texto_id, dist_etiqueta,
                     largo_linea,
                     mostrar_id, mostrar_zt, mostrar_zs, mostrar_altura,
                     ext):
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
        out.append(f"9\n$TEXTSIZE\n40\n{altura_texto:.4f}\n")
        out.append("0\nENDSEC\n")

        # TABLES
        out.append("0\nSECTION\n2\nTABLES\n")
        out.append("0\nTABLE\n2\nLTYPE\n70\n1\n")
        out.append(
            "0\nLTYPE\n2\nCONTINUOUS\n70\n64\n"
            "3\nSolid line\n72\n65\n73\n0\n40\n0.0\n"
        )
        out.append("0\nENDTAB\n")

        out.append("0\nTABLE\n2\nLAYER\n70\n2\n")
        out.append("0\nLAYER\n2\n0\n70\n0\n62\n7\n6\nCONTINUOUS\n")
        out.append("0\nLAYER\n2\nETIQUETAS\n70\n0\n62\n4\n6\nCONTINUOUS\n")
        out.append("0\nENDTAB\n")

        out.append("0\nTABLE\n2\nSTYLE\n70\n1\n")
        out.append(
            "0\nSTYLE\n2\nSTANDARD\n70\n0\n40\n0.0\n"
            f"41\n1.0\n50\n0.0\n71\n0\n42\n{altura_texto:.4f}\n3\ntxt\n4\n\n"
        )
        out.append("0\nENDTAB\n")

        out.append("0\nENDSEC\n")

        # ENTITIES
        out.append("0\nSECTION\n2\nENTITIES\n")

        for et in etiquetas:
            xc = et['x']
            yc = et['y']

            xfin = xc + DESPLAZAMIENTO_X
            yfin = yc + DESPLAZAMIENTO_Y

            # Línea oblicua: del centro al punto final
            self._escribir_linea(out, [(xc, yc), (xfin, yfin)], "ETIQUETAS")

            # Línea horizontal
            x_hr = xfin + largo_linea
            self._escribir_linea(out, [(xfin, yfin), (x_hr, yfin)], "ETIQUETAS")

            # ID de cámara (arriba, texto más grande)
            if mostrar_id and et['id']:
                x_texto = xfin
                y_texto = yfin + dist_etiqueta + altura_texto_id
                self._escribir_texto(
                    out, et['id'], x_texto, y_texto,
                    altura_texto_id, "ETIQUETAS"
                )

            # Cota terreno (Z) — arriba de la línea, solo el número
            if mostrar_zt and et['z'] is not None:
                texto = f"{et['z']:.2f}"
                x_texto = xfin
                y_texto = yfin + dist_etiqueta
                self._escribir_texto(
                    out, texto, x_texto, y_texto,
                    altura_texto, "ETIQUETAS"
                )

            # Cota solera (Zs) — abajo de la línea, solo el número
            if mostrar_zs and et['zs'] is not None:
                texto = f"{et['zs']:.2f}"
                x_texto = xfin
                y_texto = yfin - dist_etiqueta - altura_texto
                self._escribir_texto(
                    out, texto, x_texto, y_texto,
                    altura_texto, "ETIQUETAS"
                )

            # Altura (Z - Zs) — al FINAL de la línea horizontal (lado derecho)
            if mostrar_altura and et['altura'] is not None:
                texto = f"{et['altura']:.2f}"
                # Borde izquierdo del texto a 1.3 del fin de la línea
                x_texto = x_hr + dist_etiqueta
                y_texto = yfin - altura_texto / 2.0
                self._escribir_texto(
                    out, texto, x_texto, y_texto,
                    altura_texto, "ETIQUETAS"
                )

        out.append("0\nENDSEC\n")
        out.append("0\nEOF\n")

        return "".join(out)

    # ============================================================
    # ESCRIBIR UNA LÍNEA (POLYLINE)
    # ============================================================
    def _escribir_linea(self, out, puntos, capa):
        out.append(f"0\nPOLYLINE\n8\n{capa}\n66\n1\n70\n0\n")
        for x, y in puntos:
            out.append(
                f"0\nVERTEX\n8\n{capa}\n10\n{x:.6f}\n20\n{y:.6f}\n30\n0.0\n"
            )
        out.append(f"0\nSEQEND\n8\n{capa}\n")

    # ============================================================
    # ESCRIBIR UN TEXTO (TEXT)
    # ============================================================
    def _escribir_texto(self, out, texto, x, y, altura, capa):
        texto_seguro = texto.replace('\n', ' ').replace('\r', '')
        out.append(
            f"0\nTEXT\n8\n{capa}\n"
            f"10\n{x:.6f}\n20\n{y:.6f}\n30\n0.0\n"
            f"40\n{altura:.4f}\n"
            f"1\n{texto_seguro}\n"
        )

    # ============================================================
    # UTILIDADES
    # ============================================================
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

    # ============================================================
    # DESACTIVAR
    # ============================================================
    def desactivar(self, mostrar_mensaje=True):
        pass