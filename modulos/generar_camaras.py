# -*- coding: utf-8 -*-
"""
Módulo: Generar Cámaras

Genera cámaras permanentes desde la red y DEM.

CORRECCIONES:
    - Reemplazado QgsField(nombre, QVariant.Tipo) por helper con QMetaType.
    - Reemplazado writeAsVectorFormat por writeAsVectorFormatV3.

Compatible con QGIS 3.x y 4.x.
"""

from qgis.core import (
    QgsProject, QgsVectorLayer, QgsFeature,
    QgsGeometry, QgsPoint, QgsPointXY, QgsField,
    QgsWkbTypes, QgsRasterLayer,
    QgsMarkerSymbol, QgsSingleSymbolRenderer,
    QgsVectorFileWriter,
)
from qgis.PyQt.QtCore import Qt, QVariant
from qgis.PyQt.QtWidgets import (
    QMessageBox, QDialog, QVBoxLayout, QLabel,
    QPushButton, QComboBox, QFileDialog
)
from .utils import obtener_vertices_linea, extraer_cota_dem
import os


# ============================================================
# COMPATIBILIDAD: QMetaType (QGIS 3.38+ / 4.x) vs QVariant (antiguo)
# ============================================================
try:
    from qgis.PyQt.QtCore import QMetaType
    _USE_QMETATYPE = True
except ImportError:
    _USE_QMETATYPE = False


def _campo(nombre, tipo='string', longitud=0, precision=0):
    """
    Crea un QgsField evitando DeprecationWarning.

    tipo: 'string' | 'double' | 'int' | 'bool'
    """
    if _USE_QMETATYPE:
        mapa = {
            'string': QMetaType.QString,
            'double': QMetaType.Double,
            'int':    QMetaType.Int,
            'bool':   QMetaType.Bool,
        }
        qtipo = mapa.get(tipo, QMetaType.QString)
        return QgsField(nombre, qtipo, '', longitud, precision)
    else:
        mapa = {
            'string': QVariant.String,
            'double': QVariant.Double,
            'int':    QVariant.Int,
            'bool':   QVariant.Bool,
        }
        qvtipo = mapa.get(tipo, QVariant.String)
        return QgsField(nombre, qvtipo, tipo, longitud, precision)


class GeneradorCamaras:
    def __init__(self, iface):
        self.iface = iface
        self.tolerancia = 0.5
        self.ruta_guardado = None

    def mostrar_dialogo(self):
        dialog = QDialog(self.iface.mainWindow())
        dialog.setWindowTitle('GLC - Generar Camaras')
        dialog.setMinimumWidth(500)

        layout = QVBoxLayout()

        label_titulo = QLabel('<b>Generar Camaras</b>')
        label_titulo.setStyleSheet('font-size: 12pt;')
        layout.addWidget(label_titulo)

        label_info = QLabel('Genera camaras permanentes desde la red y DEM.\n'
                           'Se guardara como Shapefile para mantener todas las columnas.\n\n'
                           '📌 ID_O = Identificador unico (debe existir en la capa de lineas)')
        label_info.setWordWrap(True)
        layout.addWidget(label_info)

        layout.addWidget(QLabel('-' * 40))

        layout.addWidget(QLabel('Seleccionar capa de lineas:'))
        combo_lineas = QComboBox()
        for layer in QgsProject.instance().mapLayers().values():
            if isinstance(layer, QgsVectorLayer):
                if layer.geometryType() == QgsWkbTypes.LineGeometry:
                    combo_lineas.addItem(layer.name(), layer.id())
        layout.addWidget(combo_lineas)

        layout.addWidget(QLabel('Seleccionar DEM (raster):'))
        combo_dem = QComboBox()
        for layer in QgsProject.instance().mapLayers().values():
            if isinstance(layer, QgsRasterLayer):
                combo_dem.addItem(layer.name(), layer.id())
        layout.addWidget(combo_dem)

        layout.addWidget(QLabel('-' * 40))

        # Ruta de guardado
        layout.addWidget(QLabel('Guardar como (Shapefile):'))
        self.ruta_guardado_label = QLabel('Seleccionar carpeta...')
        layout.addWidget(self.ruta_guardado_label)

        btn_ruta = QPushButton('Seleccionar Carpeta')
        btn_ruta.clicked.connect(self.seleccionar_carpeta)
        layout.addWidget(btn_ruta)

        layout.addWidget(QLabel('-' * 40))

        btn_generar = QPushButton('Generar Camaras con Cotas (Permanente)')
        btn_generar.setStyleSheet('background-color: #4CAF50; color: white; font-weight: bold;')
        btn_generar.clicked.connect(lambda: self.generar(
            dialog,
            combo_lineas.currentData(),
            combo_dem.currentData()
        ))
        layout.addWidget(btn_generar)

        dialog.setLayout(layout)
        dialog.exec_()

    def seleccionar_carpeta(self):
        carpeta = QFileDialog.getExistingDirectory(
            self.iface.mainWindow(),
            'Seleccionar Carpeta para guardar Camaras',
            ''
        )
        if carpeta:
            self.ruta_guardado_label.setText(carpeta)

    def asegurar_id_o(self, layer):
        """Asegurar que la capa tenga campo ID_O con valores unicos"""
        if layer.fields().indexFromName('ID_O') == -1:
            layer.dataProvider().addAttributes([_campo('ID_O', 'int')])
            layer.updateFields()

            layer.startEditing()
            idx_id_o = layer.fields().indexFromName('ID_O')
            contador = 1
            for feature in layer.getFeatures():
                layer.changeAttributeValue(feature.id(), idx_id_o, contador)
                contador += 1
            layer.commitChanges()

    def generar(self, dialog, layer_id, dem_id):
        layer_lineas = QgsProject.instance().mapLayer(layer_id)
        layer_dem = QgsProject.instance().mapLayer(dem_id)

        if not layer_lineas or not layer_dem:
            QMessageBox.warning(self.iface.mainWindow(), 'Error', 'No se encontraron las capas')
            return

        if not isinstance(layer_lineas, QgsVectorLayer):
            QMessageBox.warning(self.iface.mainWindow(), 'Error', 'La capa de lineas no es vectorial')
            return

        # Verificar ruta
        carpeta = self.ruta_guardado_label.text()
        if carpeta == 'Seleccionar carpeta...' or not os.path.exists(carpeta):
            QMessageBox.warning(self.iface.mainWindow(), 'Error', 'Selecciona una carpeta valida para guardar')
            return

        # ===== ASEGURAR ID_O EN LA CAPA DE LINEAS =====
        self.asegurar_id_o(layer_lineas)

        # Crear diccionario para obtener ID_O por feature.id()
        id_o_por_feature = {}
        idx_id_o = layer_lineas.fields().indexFromName('ID_O')
        for feature in layer_lineas.getFeatures():
            id_o = feature.attribute(idx_id_o)
            if id_o is None:
                id_o = feature.id()
            id_o_por_feature[feature.id()] = id_o

        # Obtener todos los vertices
        puntos = []
        for feature in layer_lineas.getFeatures():
            geom = feature.geometry()
            if not geom or geom.isEmpty():
                continue

            vertices = obtener_vertices_linea(geom)
            if not vertices or len(vertices) < 2:
                continue

            id_o = id_o_por_feature.get(feature.id(), feature.id())

            for i, punto in enumerate(vertices):
                puntos.append({
                    'id_o': id_o,                # ID_O de la linea
                    'punto': punto,
                    'es_extremo': i == 0 or i == len(vertices) - 1,
                    'indice': i
                })

        if not puntos:
            QMessageBox.warning(self.iface.mainWindow(), 'Error', 'No se encontraron puntos')
            return

        # Agrupar puntos cercanos
        grupos = []
        for item in puntos:
            agregado = False
            for grupo in grupos:
                if grupo[0]['punto'].distance(item['punto']) <= self.tolerancia:
                    grupo.append(item)
                    agregado = True
                    break
            if not agregado:
                grupos.append([item])

        # Crear capa de camaras 3D (memoria)
        crs = layer_lineas.crs()
        uri = f"PointZ?crs={crs.authid()}&index=yes"
        capa_camaras = QgsVectorLayer(uri, "GLC_Camaras_temp", "memory")

        if not capa_camaras.isValid():
            QMessageBox.warning(self.iface.mainWindow(), 'Error', 'No se pudo crear la capa 3D')
            return

        # Campos (sin DeprecationWarning)
        campos = [
            ('ID_O',      'int'),      # Identificador unico
            ('X',         'double'),
            ('Y',         'double'),
            ('Z',         'double'),   # Cota DEM
            ('N_Lineas',  'int'),
            ('Lineas_ID', 'string'),   # IDs O de las lineas conectadas
            ('Tipo',      'string'),
        ]

        for nombre, tipo in campos:
            capa_camaras.dataProvider().addAttributes([_campo(nombre, tipo)])
        capa_camaras.updateFields()

        # Generar features
        features = []
        cotas_exitosas = 0
        cotas_fallidas = 0

        for i, grupo in enumerate(grupos):
            x = sum(item['punto'].x() for item in grupo) / len(grupo)
            y = sum(item['punto'].y() for item in grupo) / len(grupo)

            # Extraer cota del DEM
            cota = extraer_cota_dem(layer_dem, QgsPointXY(x, y))

            if cota is not None:
                cotas_exitosas += 1
                z_valor = float(cota)
            else:
                cotas_fallidas += 1
                z_valor = 0.0

            # Crear punto 3D
            punto_3d = QgsPoint(x, y, z_valor)

            # Obtener IDs_O unicos de las lineas en el grupo
            lineas_unicas = list(set(item['id_o'] for item in grupo))
            es_extremo = any(item['es_extremo'] for item in grupo)

            feature = QgsFeature(capa_camaras.fields())
            feature.setGeometry(QgsGeometry.fromPoint(punto_3d))
            feature.setAttributes([
                i + 1,                       # ID_O
                round(x, 3),                 # X
                round(y, 3),                 # Y
                round(z_valor, 3),           # Z (cota)
                len(lineas_unicas),          # N_Lineas
                ', '.join(str(l) for l in sorted(lineas_unicas)),  # Lineas_ID
                'Extremo' if es_extremo else 'Intermedio'  # Tipo
            ])
            features.append(feature)

        capa_camaras.dataProvider().addFeatures(features)
        capa_camaras.updateExtents()

        # Guardar como Shapefile permanente
        nombre_archivo = os.path.join(carpeta, "GLC_Camaras.shp")

        if os.path.exists(nombre_archivo):
            respuesta = QMessageBox.question(
                self.iface.mainWindow(),
                'Archivo existe',
                f'El archivo {nombre_archivo} ya existe.\n¿Deseas sobrescribirlo?',
                QMessageBox.Yes | QMessageBox.No
            )
            if respuesta == QMessageBox.No:
                return

        # ============================================================
        # API MODERNA: writeAsVectorFormatV3
        # ============================================================
        guardado_ok = False
        err_msg = ''

        try:
            options = QgsVectorFileWriter.SaveVectorOptions()
            options.driverName = 'ESRI Shapefile'
            options.fileEncoding = 'utf-8'
            options.layerName = 'GLC_Camaras'
            try:
                options.actionOnExistingFile = \
                    QgsVectorFileWriter.CreateOrOverwriteFile
            except AttributeError:
                pass

            transform_context = QgsProject.instance().transformContext()

            resultado = QgsVectorFileWriter.writeAsVectorFormatV3(
                capa_camaras,
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
                QMessageBox.warning(
                    self.iface.mainWindow(), 'Error',
                    f'Error al guardar:\n{err_msg or err_code}'
                )
                return
            guardado_ok = True

        except AttributeError:
            # Fallback para versiones muy antiguas (QGIS < 3.10)
            error = QgsVectorFileWriter.writeAsVectorFormat(
                capa_camaras,
                nombre_archivo,
                'utf-8',
                crs,
                'ESRI Shapefile'
            )
            if error[0] != QgsVectorFileWriter.NoError:
                QMessageBox.warning(
                    self.iface.mainWindow(), 'Error',
                    f'Error al guardar: {error}'
                )
                return
            guardado_ok = True

        if not guardado_ok:
            return

        capa_guardada = QgsVectorLayer(nombre_archivo, "GLC_Camaras", "ogr")
        QgsProject.instance().addMapLayer(capa_guardada)

        dialog.accept()

        mensaje = f"=== CAMARAS GENERADAS ===\n\n"
        mensaje += f"Total de camaras generadas: {len(features)}\n"
        mensaje += f"Tolerancia usada: {self.tolerancia} m\n\n"
        mensaje += f"=== EXTRACCION DE COTAS ===\n"
        mensaje += f"Cotas extraidas correctamente: {cotas_exitosas}\n"
        mensaje += f"Cotas fallidas (Z=0): {cotas_fallidas}\n\n"

        mensaje += f"CAMPOS DISPONIBLES:\n"
        mensaje += f"  - ID_O (Identificador unico)\n"
        mensaje += f"  - X, Y, Z (coordenadas y cota)\n"
        mensaje += f"  - N_Lineas\n"
        mensaje += f"  - Lineas_ID (IDs_O de las lineas conectadas)\n"
        mensaje += f"  - Tipo\n\n"

        if cotas_exitosas > 0:
            mensaje += f"✅ Las camaras tienen geometria 3D con la elevacion real\n"
        else:
            mensaje += f"⚠️ No se pudo extraer ninguna cota\n"

        mensaje += f"\n✅ Guardado en: {nombre_archivo}"

        QMessageBox.information(
            self.iface.mainWindow(),
            'Camaras Generadas',
            mensaje
        )

    def aplicar_simbologia(self, layer):
        simbolo = QgsMarkerSymbol.createSimple({
            'name': 'circle',
            'color': '#ff0000',
            'size': '3',
            'outline_color': '#000000',
            'outline_width': '0.5'
        })

        layer.setRenderer(QgsSingleSymbolRenderer(simbolo))
        layer.triggerRepaint()