# -*- coding: utf-8 -*-
"""
Módulo Copiar Red → GLC_Tuberias

Crea la capa GLC_Tuberias con TODAS las columnas necesarias para el
flujo completo de diseño (áreas, caudales, diseño hidráulico, SWMM, etc.)
en blanco (0.0). Los demás módulos solo RELLENAN los valores.

Compatible con QGIS 3.x y 4.x.
"""
from qgis.core import (
    QgsProject, QgsVectorLayer, QgsFeature,
    QgsGeometry, QgsPointXY, QgsField,
    QgsWkbTypes, QgsLineString,
    QgsSpatialIndex
)
from qgis.PyQt.QtCore import Qt, QVariant
from qgis.PyQt.QtWidgets import (
    QMessageBox, QDialog, QVBoxLayout, QLabel,
    QPushButton, QComboBox, QFileDialog
)
from .utils import obtener_vertices_linea
import os

# Compatibilidad Qt6
try:
    from qgis.PyQt.QtCore import QMetaType
    _QT6 = True
except ImportError:
    _QT6 = False


class CopiarRed:
    def __init__(self, iface):
        self.iface = iface
        self.ruta_guardado = None

    # ============================================================
    # DIÁLOGO
    # ============================================================
    def mostrar_dialogo(self):
        dialog = QDialog(self.iface.mainWindow())
        dialog.setWindowTitle('GLC - Copiar Red a GLC_Tuberias')
        dialog.setMinimumWidth(500)

        layout = QVBoxLayout()

        label_titulo = QLabel('<b>Copiar Red a GLC_Tuberias</b>')
        label_titulo.setStyleSheet('font-size: 12pt;')
        layout.addWidget(label_titulo)

        label_info = QLabel(
            'Crea una copia permanente de la red con TODAS las columnas\n'
            'necesarias para el flujo completo de diseño.\n\n'
            '📌 Se crea automaticamente ID_O en la capa original\n'
            '📌 Ci = Camara en el primer vertice\n'
            '📌 Cf = Camara en el ultimo vertice\n'
            '📌 Las columnas de cálculo se crean en 0.0 (en blanco)'
        )
        label_info.setWordWrap(True)
        layout.addWidget(label_info)

        layout.addWidget(QLabel('-' * 40))

        layout.addWidget(QLabel('Seleccionar capa de lineas (red):'))
        combo_lineas = QComboBox()
        for layer in QgsProject.instance().mapLayers().values():
            if isinstance(layer, QgsVectorLayer):
                if layer.geometryType() == QgsWkbTypes.LineGeometry:
                    combo_lineas.addItem(layer.name(), layer.id())
        layout.addWidget(combo_lineas)

        layout.addWidget(QLabel('Seleccionar capa de camaras:'))
        combo_camaras = QComboBox()
        for layer in QgsProject.instance().mapLayers().values():
            if isinstance(layer, QgsVectorLayer):
                if layer.geometryType() == QgsWkbTypes.PointGeometry:
                    combo_camaras.addItem(layer.name(), layer.id())
        layout.addWidget(combo_camaras)

        layout.addWidget(QLabel('-' * 40))

        layout.addWidget(QLabel('Guardar como (Shapefile):'))
        self.ruta_guardado_label = QLabel('Seleccionar carpeta...')
        layout.addWidget(self.ruta_guardado_label)

        btn_ruta = QPushButton('Seleccionar Carpeta')
        btn_ruta.clicked.connect(self.seleccionar_carpeta)
        layout.addWidget(btn_ruta)

        layout.addWidget(QLabel('-' * 40))

        btn_copiar = QPushButton('Crear GLC_Tuberias (Permanente)')
        btn_copiar.setStyleSheet(
            'background-color: #4CAF50; color: white; font-weight: bold;'
        )
        btn_copiar.clicked.connect(lambda: self.copiar_red(
            dialog,
            combo_lineas.currentData(),
            combo_camaras.currentData()
        ))
        layout.addWidget(btn_copiar)

        dialog.setLayout(layout)
        dialog.exec_()

    def seleccionar_carpeta(self):
        carpeta = QFileDialog.getExistingDirectory(
            self.iface.mainWindow(),
            'Seleccionar Carpeta para guardar GLC_Tuberias',
            ''
        )
        if carpeta:
            self.ruta_guardado_label.setText(carpeta)

    # ============================================================
    # ASEGURAR ID_O
    # ============================================================
    def asegurar_id_o(self, layer):
        """Asegurar que la capa tenga campo ID_O con valores unicos"""
        if layer.fields().indexFromName('ID_O') == -1:
            if _QT6:
                layer.dataProvider().addAttributes(
                    [QgsField('ID_O', QMetaType.Int)]
                )
            else:
                layer.dataProvider().addAttributes(
                    [QgsField('ID_O', QVariant.Int)]
                )
            layer.updateFields()

            layer.startEditing()
            idx_id_o = layer.fields().indexFromName('ID_O')
            contador = 1
            for feature in layer.getFeatures():
                layer.changeAttributeValue(feature.id(), idx_id_o, contador)
                contador += 1
            layer.commitChanges()

    # ============================================================
    # COPIAR RED
    # ============================================================
    def copiar_red(self, dialog, layer_id, camaras_id):
        """Copiar la red con todos los campos necesarios"""

        layer_original = QgsProject.instance().mapLayer(layer_id)
        layer_camaras = QgsProject.instance().mapLayer(camaras_id)

        if not layer_original or not layer_camaras:
            QMessageBox.warning(self.iface.mainWindow(), 'Error',
                                'No se encontraron las capas')
            return

        if not isinstance(layer_original, QgsVectorLayer):
            QMessageBox.warning(self.iface.mainWindow(), 'Error',
                                'La capa de lineas no es vectorial')
            return

        carpeta = self.ruta_guardado_label.text()
        if carpeta == 'Seleccionar carpeta...' or not os.path.exists(carpeta):
            QMessageBox.warning(self.iface.mainWindow(), 'Error',
                                'Selecciona una carpeta valida para guardar')
            return

        # Asegurar ID_O en ambas capas
        self.asegurar_id_o(layer_original)
        self.asegurar_id_o(layer_camaras)

        # Índice espacial de cámaras
        index_camaras = QgsSpatialIndex()
        camaras_info = {}

        for feature in layer_camaras.getFeatures():
            geom = feature.geometry()
            if geom and not geom.isEmpty():
                index_camaras.addFeature(feature)
                camaras_info[feature.id()] = {
                    'id_o': feature.attribute('ID_O'),
                    'cota': feature.attribute('Z'),
                    'geom': geom
                }

        # Crear capa GLC_Tuberias (memoria)
        crs = layer_original.crs()
        uri = f"LineString?crs={crs.authid()}&index=yes"
        capa_tuberias = QgsVectorLayer(uri, "GLC_Tuberias_temp", "memory")

        # ============================================================
        # ESQUEMA COMPLETO DE GLC_Tuberias
        # ============================================================
        campos = [
            # --- CREACIÓN BÁSICA ---
            ('ID_O',        QVariant.Int),
            ('Ci',          QVariant.Int),
            ('Cf',          QVariant.Int),
            ('Xi',          QVariant.Double),
            ('Yi',          QVariant.Double),
            ('Zi',          QVariant.Double),
            ('Xf',          QVariant.Double),
            ('Yf',          QVariant.Double),
            ('Zf',          QVariant.Double),
            ('L',           QVariant.Double),
            ('S',           QVariant.Double),
            ('dir',         QVariant.String),
            ('cab_ata',     QVariant.String),
            # --- LONGITUD ACUMULADA ---
            ('Lt',          QVariant.Double),
            ('La',          QVariant.Double),
            # --- ÁREAS / POBLACIÓN ---
            ('pobla_prop',  QVariant.Double),
            ('pobla_trib',  QVariant.Double),
            ('pobla_tot',   QVariant.Double),
            # --- CAUDALES ---
            ('coef_m',      QVariant.Double),
            ('qmaxh',       QVariant.Double),
            ('qinf',        QVariant.Double),
            ('qce',         QVariant.Double),
            ('qp',          QVariant.Double),
            # --- CAUDALES ACUMULADOS ---
            ('qacu',        QVariant.Double),
            ('qdise',       QVariant.Double),
            # --- DISEÑO HIDRÁULICO ---
            ('D_mm',        QVariant.Double),
            ('S_diseno',    QVariant.Double),
            ('Zs_i',        QVariant.Double),
            ('Zs_f',        QVariant.Double),
            ('Hexc_i',      QVariant.Double),
            ('Hexc_f',      QVariant.Double),
            ('Q_lleno',     QVariant.Double),
            ('V_lleno',     QVariant.Double),
            ('Rh_lleno',    QVariant.Double),
            ('q_Q',         QVariant.Double),
            ('v_V',         QVariant.Double),
            ('h_D',         QVariant.Double),
            ('rh_Rh',       QVariant.Double),
            ('v_real',      QVariant.Double),
            ('h_real',      QVariant.Double),
            ('rh_real',     QVariant.Double),
            # --- VERIFICACIONES ---
            ('angulo',      QVariant.Double),
            ('tractiva',    QVariant.Double),
            ('vc',          QVariant.Double),
            # --- INTERACCIÓN EPA SWMM ---
            ('Caudal_Tra',  QVariant.Double),
            ('Sumatoria',   QVariant.Double),
        ]

        for nombre, tipo in campos:
            if _QT6:
                if tipo == QVariant.Int:
                    qtipo = QMetaType.Int
                elif tipo == QVariant.Double:
                    qtipo = QMetaType.Double
                else:
                    qtipo = QMetaType.QString
                capa_tuberias.dataProvider().addAttributes(
                    [QgsField(nombre, qtipo)]
                )
            else:
                capa_tuberias.dataProvider().addAttributes(
                    [QgsField(nombre, tipo)]
                )
        capa_tuberias.updateFields()

        # Copiar features
        features = []
        tuberias_ok = 0
        tuberias_sin_cota = 0
        tolerancia_busqueda = 1.0

        for feature in layer_original.getFeatures():
            geom = feature.geometry()
            if not geom or geom.isEmpty():
                continue

            id_o = feature.attribute('ID_O')
            if id_o is None:
                id_o = feature.id()

            try:
                geom_copia = geom.copy()
            except Exception:
                geom_copia = QgsGeometry(geom)

            vertices = obtener_vertices_linea(geom)
            if not vertices or len(vertices) < 2:
                continue

            punto_primero = vertices[0]
            punto_ultimo = vertices[-1]

            cota_ci, id_camara_ci = self.buscar_camara_cercana(
                punto_primero, index_camaras, layer_camaras,
                camaras_info, tolerancia_busqueda
            )
            cota_cf, id_camara_cf = self.buscar_camara_cercana(
                punto_ultimo, index_camaras, layer_camaras,
                camaras_info, tolerancia_busqueda
            )

            xi = punto_primero.x()
            yi = punto_primero.y()
            xf = punto_ultimo.x()
            yf = punto_ultimo.y()

            if xf > xi:
                dir_flujo = '->'
            elif xf < xi:
                dir_flujo = '<-'
            else:
                dir_flujo = '->' if yf > yi else '<-'

            longitud = geom.length()

            pendiente = 0.0
            if cota_ci is not None and cota_cf is not None and longitud > 0:
                pendiente = (cota_ci - cota_cf) / longitud * 100

            new_feature = QgsFeature(capa_tuberias.fields())
            new_feature.setGeometry(geom_copia)

            new_feature.setAttributes([
                # --- CREACIÓN BÁSICA ---
                id_o,
                id_camara_ci if id_camara_ci is not None else -1,
                id_camara_cf if id_camara_cf is not None else -1,
                round(punto_primero.x(), 3),
                round(punto_primero.y(), 3),
                cota_ci if cota_ci is not None else -9999.0,
                round(punto_ultimo.x(), 3),
                round(punto_ultimo.y(), 3),
                cota_cf if cota_cf is not None else -9999.0,
                round(longitud, 3),
                round(pendiente, 3),
                dir_flujo,
                '',
                # --- En blanco (los rellenan otros módulos) ---
                0.0,  # Lt
                0.0,  # La
                0.0,  # pobla_prop
                0.0,  # pobla_trib
                0.0,  # pobla_tot
                0.0,  # coef_m
                0.0,  # qmaxh
                0.0,  # qinf
                0.0,  # qce
                0.0,  # qp
                0.0,  # qacu
                0.0,  # qdise
                0.0,  # D_mm
                0.0,  # S_diseno
                0.0,  # Zs_i
                0.0,  # Zs_f
                0.0,  # Hexc_i
                0.0,  # Hexc_f
                0.0,  # Q_lleno
                0.0,  # V_lleno
                0.0,  # Rh_lleno
                0.0,  # q_Q
                0.0,  # v_V
                0.0,  # h_D
                0.0,  # rh_Rh
                0.0,  # v_real
                0.0,  # h_real
                0.0,  # rh_real
                0.0,  # angulo
                0.0,  # tractiva
                0.0,  # vc
                0.0,  # Caudal_Tra
                0.0,  # Sumatoria
            ])

            features.append(new_feature)

            if cota_ci is not None and cota_cf is not None:
                tuberias_ok += 1
            else:
                tuberias_sin_cota += 1

        capa_tuberias.dataProvider().addFeatures(features)
        capa_tuberias.updateExtents()

        # Guardar Shapefile
        nombre_archivo = os.path.join(carpeta, "GLC_Tuberias.shp")

        if os.path.exists(nombre_archivo):
            respuesta = QMessageBox.question(
                self.iface.mainWindow(),
                'Archivo existe',
                f'El archivo {nombre_archivo} ya existe.\n¿Deseas sobrescribirlo?',
                QMessageBox.Yes | QMessageBox.No
            )
            if respuesta == QMessageBox.No:
                return

        from qgis.core import QgsVectorFileWriter
        try:
            options = QgsVectorFileWriter.SaveVectorOptions()
            options.driverName = 'ESRI Shapefile'
            options.fileEncoding = 'utf-8'
            options.layerName = 'GLC_Tuberias'
            try:
                options.actionOnExistingFile = \
                    QgsVectorFileWriter.CreateOrOverwriteFile
            except AttributeError:
                pass

            transform_context = QgsProject.instance().transformContext()
            resultado = QgsVectorFileWriter.writeAsVectorFormatV3(
                capa_tuberias,
                nombre_archivo,
                transform_context,
                options
            )
            if isinstance(resultado, tuple):
                err_code = resultado[0]
                err_msg = resultado[1] if len(resultado) > 1 else ''
            else:
                err_code = resultado
                err_msg = ''

            if err_code != QgsVectorFileWriter.NoError:
                QMessageBox.warning(self.iface.mainWindow(), 'Error',
                                    f'Error al guardar: {err_msg or err_code}')
                return
        except AttributeError:
            error = QgsVectorFileWriter.writeAsVectorFormat(
                capa_tuberias,
                nombre_archivo,
                'utf-8',
                crs,
                'ESRI Shapefile'
            )
            if error[0] != QgsVectorFileWriter.NoError:
                QMessageBox.warning(self.iface.mainWindow(), 'Error',
                                    f'Error al guardar: {error}')
                return

        capa_guardada = QgsVectorLayer(nombre_archivo, "GLC_Tuberias", "ogr")
        QgsProject.instance().addMapLayer(capa_guardada)

        dialog.accept()

        # ============================================================
        # MENSAJE FINAL
        # ============================================================
        mensaje = f"=== RED COPIADA A GLC_Tuberias ===\n\n"
        mensaje += f"Total de tuberías: {len(features)}\n"
        mensaje += f"Con cotas completas: {tuberias_ok}\n"
        mensaje += f"Sin cotas (-9999): {tuberias_sin_cota}\n\n"
        mensaje += f"ESQUEMA CREADO ({len(campos)} columnas):\n"
        mensaje += f"  ▸ Básicas:      ID_O, Ci, Cf, Xi..Zf, L, S, dir, cab_ata\n"
        mensaje += f"  ▸ Acumulados:   Lt, La\n"
        mensaje += f"  ▸ Población:    pobla_prop, pobla_trib, pobla_tot\n"
        mensaje += f"  ▸ Caudales:     coef_m, qmaxh, qinf, qce, qp\n"
        mensaje += f"  ▸ Acumulados:   qacu, qdise\n"
        mensaje += f"  ▸ Diseño:       D_mm, S_diseno, Zs_i, Zs_f, Hexc_i, Hexc_f\n"
        mensaje += f"                  Q_lleno, V_lleno, Rh_lleno\n"
        mensaje += f"                  q_Q, v_V, h_D, rh_Rh\n"
        mensaje += f"                  v_real, h_real, rh_real\n"
        mensaje += f"  ▸ Verificación: angulo, tractiva, vc\n"
        mensaje += f"  ▸ SWMM:         Caudal_Tra, Sumatoria\n\n"
        mensaje += f"📌 Columnas de cálculo en blanco (0.0).\n"
        mensaje += f"📌 Cada módulo rellenará las que le correspondan.\n\n"
        mensaje += f"✅ Guardado en:\n   {nombre_archivo}"

        QMessageBox.information(
            self.iface.mainWindow(),
            'Red Copiada',
            mensaje
        )

    # ============================================================
    # BUSCAR CÁMARA CERCANA
    # ============================================================
    def buscar_camara_cercana(self, punto, index, layer, camaras_info, tolerancia):
        """Buscar la camara mas cercana a un punto"""
        try:
            punto_geom = QgsGeometry.fromPointXY(punto)
            buffer = punto_geom.buffer(tolerancia, 8)
            ids = index.intersects(buffer.boundingBox())

            for id_camara in ids:
                feature = layer.getFeature(id_camara)
                if not feature:
                    continue
                geom = feature.geometry()
                if not geom:
                    continue
                dist = geom.distance(punto_geom)
                if dist <= tolerancia:
                    cota = feature.attribute('Z')
                    id_o = feature.attribute('ID_O')
                    if cota is not None and cota != -9999:
                        return float(cota), id_o

            return None, None
        except Exception:
            return None, None