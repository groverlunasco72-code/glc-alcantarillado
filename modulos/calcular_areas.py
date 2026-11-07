# -*- coding: utf-8 -*-
"""
Módulo: Calcular Áreas Propias

Calcula las áreas propias (A) de cada tubería.

Dos modos:
    🎯 Automático: A partir de triángulos de influencia en polígonos cerrados.
    ✏️ Manual:     Dibujando polígonos sobre el mapa y sumando sus áreas
                   a la tubería seleccionada.

CORRECCIONES:
    - Reemplazado QgsField(nombre, QVariant.Tipo) por helper con QMetaType.
    - Reemplazado writeAsVectorFormat por writeAsVectorFormatV3.
    - Modo Manual: los polígonos dibujados se guardan en GLC_Areas.shp
    - Modo Manual: al guardar un área, la edición finaliza automáticamente.

Compatible con QGIS 3.x y 4.x.
"""

from qgis.core import (
    QgsProject, QgsVectorLayer, QgsFeature,
    QgsGeometry, QgsPointXY, QgsField,
    QgsWkbTypes, QgsLineString, QgsPolygon,
    QgsVectorFileWriter, QgsSpatialIndex,
    QgsCoordinateTransform
)
from qgis.PyQt.QtCore import Qt, QVariant
from qgis.PyQt.QtWidgets import (
    QMessageBox, QDialog, QVBoxLayout, QLabel,
    QPushButton, QComboBox, QHBoxLayout,
    QDoubleSpinBox, QGroupBox, QProgressBar,
    QRadioButton, QButtonGroup, QTabWidget,
    QWidget, QCheckBox, QFileDialog, QLineEdit
)
from qgis.PyQt.QtGui import QColor
from qgis.gui import QgsMapToolEmitPoint, QgsRubberBand
import math
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


class CalcularAreas:
    def __init__(self, iface):
        self.iface = iface
        self.capa_tuberias = None
        self.capa_camaras = None
        self.ruta_guardado = None
        self.debug = False

        # ===== Estado para dibujo manual =====
        self.tool_seleccion = None
        self.rubber_band = None
        self.puntos_dibujo = []          # Lista de QgsPointXY del polígono actual
        self.dibujando = False
        self.id_tuberia_destino = None
        self.capa_tuberias_dibujo = None

        # ===== Capa de áreas para modo manual =====
        self.capa_areas_manual = None
        self.contador_id_manual = 1

    # ============================================================
    # DIÁLOGO PRINCIPAL
    # ============================================================
    def mostrar_dialogo(self):
        dialog = QDialog(self.iface.mainWindow())
        dialog.setWindowTitle('GLC - Calcular Áreas Propias')
        dialog.setMinimumWidth(720)
        dialog.setMinimumHeight(560)
        self.dialog = dialog

        layout = QVBoxLayout()

        label_titulo = QLabel('<b>Calcular Áreas Propias (A)</b>')
        label_titulo.setStyleSheet('font-size: 14pt; font-weight: bold;')
        layout.addWidget(label_titulo)

        # ===== TABS =====
        tabs = QTabWidget()

        # ---------- TAB 1: AUTOMÁTICO ----------
        tab_auto = QWidget()
        layout_auto = QVBoxLayout()

        label_info = QLabel(
            '📌 GENERACIÓN AUTOMÁTICA DE ÁREAS PROPIAS:\n'
            '   1. Selecciona las capas de tuberías y cámaras\n'
            '   2. Selecciona la carpeta donde guardar el Shapefile\n'
            '   3. Haz clic en "Calcular Áreas Propias"\n\n'
            '📌 RESULTADO:\n'
            '   • Se crea GLC_Areas.shp con los triángulos de influencia\n'
            '   • Se actualiza GLC_Tuberias con A (área propia)'
        )
        label_info.setWordWrap(True)
        layout_auto.addWidget(label_info)

        layout_auto.addWidget(QLabel('-' * 40))

        # Capa de tuberías
        layout_auto.addWidget(QLabel('Seleccionar capa GLC_Tuberias:'))
        combo_tuberias = QComboBox()
        for layer in QgsProject.instance().mapLayers().values():
            if isinstance(layer, QgsVectorLayer):
                if layer.geometryType() == QgsWkbTypes.LineGeometry:
                    if 'GLC_Tuberias' in layer.name():
                        combo_tuberias.addItem(layer.name(), layer.id())
        if combo_tuberias.count() == 0:
            for layer in QgsProject.instance().mapLayers().values():
                if isinstance(layer, QgsVectorLayer):
                    if layer.geometryType() == QgsWkbTypes.LineGeometry:
                        combo_tuberias.addItem(layer.name(), layer.id())
        layout_auto.addWidget(combo_tuberias)

        # Capa de cámaras
        layout_auto.addWidget(QLabel('Seleccionar capa de Cámaras:'))
        combo_camaras = QComboBox()
        for layer in QgsProject.instance().mapLayers().values():
            if isinstance(layer, QgsVectorLayer):
                if layer.geometryType() == QgsWkbTypes.PointGeometry:
                    if 'GLC_Camaras' in layer.name():
                        combo_camaras.addItem(layer.name(), layer.id())
        if combo_camaras.count() == 0:
            for layer in QgsProject.instance().mapLayers().values():
                if isinstance(layer, QgsVectorLayer):
                    if layer.geometryType() == QgsWkbTypes.PointGeometry:
                        combo_camaras.addItem(layer.name(), layer.id())
        layout_auto.addWidget(combo_camaras)

        layout_auto.addWidget(QLabel('-' * 40))

        # Ruta de guardado
        layout_auto.addWidget(QLabel('Guardar Shapefile de áreas:'))
        self.ruta_label = QLabel('Seleccionar carpeta...')
        self.ruta_label.setStyleSheet('background-color: #f5f5f5; padding: 5px;')
        layout_auto.addWidget(self.ruta_label)

        btn_ruta = QPushButton('Seleccionar Carpeta')
        btn_ruta.clicked.connect(self.seleccionar_carpeta)
        layout_auto.addWidget(btn_ruta)

        layout_auto.addWidget(QLabel('-' * 40))

        # Barra de progreso
        self.progress = QProgressBar()
        layout_auto.addWidget(self.progress)

        # Botón calcular
        btn_calcular = QPushButton('📊 Calcular Áreas Propias (A)')
        btn_calcular.setStyleSheet(
            'background-color: #4CAF50; color: white; font-weight: bold; font-size: 12pt;'
        )
        btn_calcular.clicked.connect(lambda: self.calcular_areas(
            dialog,
            combo_tuberias.currentData(),
            combo_camaras.currentData()
        ))
        layout_auto.addWidget(btn_calcular)

        layout_auto.addWidget(QLabel('-' * 40))

        # Estado
        self.label_estado = QLabel('🟡 Estado: Esperando cálculo...')
        self.label_estado.setStyleSheet(
            'background-color: #f5f5f5; padding: 10px; border-radius: 5px;'
        )
        layout_auto.addWidget(self.label_estado)

        tab_auto.setLayout(layout_auto)
        tabs.addTab(tab_auto, '🎯 Automático')

        # ---------- TAB 2: MANUAL ----------
        tab_manual = QWidget()
        layout_manual = QVBoxLayout()

        label_manual_info = QLabel(
            '📌 DIBUJO MANUAL DE ÁREAS:\n'
            '   1. Selecciona la capa de tuberías y la tubería destino\n'
            '   2. Pulsa "Dibujar Área Manual"\n'
            '   3. Haz clic en el mapa para crear los vértices del polígono\n'
            '   4. Doble clic (o clic derecho) para cerrar el polígono\n\n'
            '📌 RESULTADO:\n'
            '   • El área se SUMA al valor actual del campo A\n'
            '   • El polígono se GUARDA en GLC_Areas.shp\n'
            '   • La edición finaliza automáticamente al guardar\n'
            '   • Para dibujar otra área, vuelve a pulsar el botón'
        )
        label_manual_info.setWordWrap(True)
        layout_manual.addWidget(label_manual_info)

        layout_manual.addWidget(QLabel('-' * 40))

        # Capa de tuberías
        layout_manual.addWidget(QLabel('Seleccionar capa GLC_Tuberias:'))
        self.combo_tuberias_manual = QComboBox()
        for layer in QgsProject.instance().mapLayers().values():
            if isinstance(layer, QgsVectorLayer):
                if layer.geometryType() == QgsWkbTypes.LineGeometry:
                    if 'GLC_Tuberias' in layer.name():
                        self.combo_tuberias_manual.addItem(layer.name(), layer.id())
        if self.combo_tuberias_manual.count() == 0:
            for layer in QgsProject.instance().mapLayers().values():
                if isinstance(layer, QgsVectorLayer):
                    if layer.geometryType() == QgsWkbTypes.LineGeometry:
                        self.combo_tuberias_manual.addItem(layer.name(), layer.id())
        layout_manual.addWidget(self.combo_tuberias_manual)

        # Selección de tubería destino
        hbox_id = QHBoxLayout()
        hbox_id.addWidget(QLabel('ID_O de la tubería destino:'))
        self.txt_id_tuberia = QLineEdit()
        self.txt_id_tuberia.setPlaceholderText('Ej: 15')
        hbox_id.addWidget(self.txt_id_tuberia, 1)
        layout_manual.addLayout(hbox_id)

        # Información de área actual de la tubería
        self.lbl_area_actual = QLabel('Área actual de la tubería: —')
        self.lbl_area_actual.setStyleSheet(
            'background-color: #e3f2fd; padding: 8px; border-radius: 4px; '
            'font-family: monospace;'
        )
        layout_manual.addWidget(self.lbl_area_actual)

        # Conectar cambio de ID para consultar área
        self.txt_id_tuberia.textChanged.connect(self._consultar_area_actual)

        layout_manual.addWidget(QLabel('-' * 40))

        # Botón dibujar
        btn_dibujar = QPushButton('✏️ Dibujar Área Manual (clic en el mapa)')
        btn_dibujar.setStyleSheet(
            'background-color: #FF9800; color: white; font-weight: bold; '
            'font-size: 12pt; padding: 8px;'
        )
        btn_dibujar.clicked.connect(self._iniciar_dibujo_manual)
        layout_manual.addWidget(btn_dibujar)

        layout_manual.addWidget(QLabel('-' * 40))

        # Log de dibujos realizados
        layout_manual.addWidget(QLabel('Registro de dibujos:'))
        self.text_log_manual = QLabel('Sin dibujos aún.')
        self.text_log_manual.setStyleSheet(
            'background-color: #f5f5f5; padding: 8px; border-radius: 4px; '
            'font-family: monospace; font-size: 9pt; min-height: 60px;'
        )
        self.text_log_manual.setWordWrap(True)
        layout_manual.addWidget(self.text_log_manual)

        tab_manual.setLayout(layout_manual)
        tabs.addTab(tab_manual, '✏️ Manual')

        layout.addWidget(tabs)

        btn_cerrar = QPushButton('Cerrar')
        btn_cerrar.setStyleSheet('background-color: #f44336; color: white;')
        btn_cerrar.clicked.connect(dialog.accept)
        layout.addWidget(btn_cerrar)

        dialog.setLayout(layout)
        dialog.exec_()

    # ============================================================
    # SELECCIONAR CARPETA
    # ============================================================
    def seleccionar_carpeta(self):
        carpeta = QFileDialog.getExistingDirectory(
            self.iface.mainWindow(),
            'Seleccionar Carpeta para guardar Shapefile',
            ''
        )
        if carpeta:
            self.ruta_label.setText(carpeta)
            self.ruta_guardado = carpeta

    # ============================================================
    # MODO AUTOMÁTICO
    # ============================================================
    def calcular_areas(self, dialog, tuberias_id, camaras_id):

        self.capa_tuberias = QgsProject.instance().mapLayer(tuberias_id)
        if not self.capa_tuberias:
            QMessageBox.warning(self.iface.mainWindow(), 'Error',
                                'No se encontró la capa de tuberías')
            return

        self.capa_camaras = QgsProject.instance().mapLayer(camaras_id)
        if not self.capa_camaras:
            QMessageBox.warning(self.iface.mainWindow(), 'Error',
                                'No se encontró la capa de cámaras')
            return

        # Verificar carpeta
        if not self.ruta_guardado or not os.path.exists(self.ruta_guardado):
            QMessageBox.warning(
                self.iface.mainWindow(),
                'Error',
                'Selecciona una carpeta válida para guardar el Shapefile'
            )
            return

        # Verificar campos
        campos = ['ID_O', 'Ci', 'Cf']
        for campo in campos:
            if self.capa_tuberias.fields().indexFromName(campo) == -1:
                QMessageBox.warning(
                    self.iface.mainWindow(),
                    'Error',
                    f'La capa de tuberías no tiene el campo "{campo}"'
                )
                return

        if self.capa_camaras.fields().indexFromName('ID_O') == -1:
            QMessageBox.warning(
                self.iface.mainWindow(),
                'Error',
                'La capa de cámaras no tiene el campo "ID_O"'
            )
            return

        # Asegurar campo A (sin DeprecationWarning)
        if self.capa_tuberias.fields().indexFromName('A') == -1:
            self.capa_tuberias.dataProvider().addAttributes(
                [_campo('A', 'double')]
            )
            self.capa_tuberias.updateFields()

        self.progress.setValue(10)
        self.label_estado.setText('🟡 Estado: Construyendo red...')

        # ===== CONSTRUIR RED =====
        nodos = {}
        for feature in self.capa_camaras.getFeatures():
            id_o = feature.attribute('ID_O')
            geom = feature.geometry()
            if geom and not geom.isEmpty() and id_o is not None:
                punto = geom.asPoint()
                nodos[id_o] = {
                    'id': id_o,
                    'punto': punto,
                    'geom': geom
                }

        if len(nodos) < 3:
            QMessageBox.warning(
                self.iface.mainWindow(),
                'Error',
                'Se necesitan al menos 3 cámaras para generar áreas'
            )
            return

        self.progress.setValue(20)

        # ===== CREAR CONEXIONES =====
        conexiones = {}
        tuberias_info = {}

        for feature in self.capa_tuberias.getFeatures():
            ci = feature.attribute('Ci')
            cf = feature.attribute('Cf')
            id_o = feature.attribute('ID_O')

            if ci is not None and cf is not None and id_o is not None:
                if ci not in conexiones:
                    conexiones[ci] = []
                if cf not in conexiones:
                    conexiones[cf] = []
                conexiones[ci].append(cf)
                conexiones[cf].append(ci)
                tuberias_info[id_o] = {
                    'ci': ci,
                    'cf': cf,
                    'feature': feature
                }

        self.progress.setValue(30)
        self.label_estado.setText('🟡 Estado: Encontrando polígonos...')

        # ===== ENCONTRAR TODAS LAS CARAS (POLÍGONOS) =====
        poligonos = self.encontrar_todas_las_caras(nodos, conexiones)

        if not poligonos:
            QMessageBox.warning(
                self.iface.mainWindow(),
                'Error',
                'No se encontraron polígonos cerrados en la red.\n'
                'Asegúrate de que la red tenga circuitos cerrados (manzanos).'
            )
            return

        self.progress.setValue(50)
        self.label_estado.setText(
            f'🟡 Estado: {len(poligonos)} polígonos encontrados. Generando triángulos...'
        )

        # ===== CREAR TRIÁNGULOS Y ASIGNAR ÁREAS =====
        crs = self.capa_tuberias.crs()
        nombre_archivo = os.path.join(self.ruta_guardado, "GLC_Areas.shp")

        # Crear capa de triángulos con campos sin DeprecationWarning
        uri = f"Polygon?crs={crs.authid()}&index=yes"
        capa_triangulos = QgsVectorLayer(uri, "GLC_Areas", "memory")
        capa_triangulos.dataProvider().addAttributes([
            _campo('ID',          'int'),
            _campo('Area_m2',     'double'),
            _campo('ID_Tuberia',  'int'),
            _campo('Nodo1',       'int'),
            _campo('Nodo2',       'int'),
            _campo('Nodo_Centro', 'int'),
            _campo('ID_Poligono', 'int'),
        ])
        capa_triangulos.updateFields()

        features_triangulos = []
        idx_triangulo = 1
        idx_poligono = 1

        idx_A = self.capa_tuberias.fields().indexFromName('A')
        areas_por_tuberia = {}

        for poligono in poligonos:
            nodos_poligono = poligono['nodos']
            poligono_geom = poligono['geom']

            centroide = poligono_geom.centroid()
            if centroide and not centroide.isEmpty():
                punto_centro = centroide.asPoint()

                for i in range(len(nodos_poligono)):
                    j = (i + 1) % len(nodos_poligono)

                    nodo1 = nodos_poligono[i]
                    nodo2 = nodos_poligono[j]

                    if nodo1 not in nodos or nodo2 not in nodos:
                        continue

                    p1 = QgsPointXY(nodos[nodo1]['punto'].x(), nodos[nodo1]['punto'].y())
                    p2 = QgsPointXY(nodos[nodo2]['punto'].x(), nodos[nodo2]['punto'].y())
                    p3 = QgsPointXY(punto_centro.x(), punto_centro.y())

                    triangulo_puntos = [p1, p2, p3, p1]
                    triangulo_geom = QgsGeometry.fromPolygonXY([triangulo_puntos])

                    if triangulo_geom and not triangulo_geom.isEmpty() and \
                       triangulo_geom.isGeosValid():
                        id_tuberia = None
                        for id_o, info in tuberias_info.items():
                            ci = info['ci']
                            cf = info['cf']
                            if (ci == nodo1 and cf == nodo2) or \
                               (ci == nodo2 and cf == nodo1):
                                id_tuberia = id_o
                                break

                        feature_tri = QgsFeature(capa_triangulos.fields())
                        feature_tri.setGeometry(triangulo_geom)
                        feature_tri.setAttributes([
                            idx_triangulo,
                            triangulo_geom.area(),
                            id_tuberia if id_tuberia else -1,
                            nodo1,
                            nodo2,
                            -1,
                            idx_poligono
                        ])
                        features_triangulos.append(feature_tri)
                        idx_triangulo += 1

                        if id_tuberia:
                            if id_tuberia not in areas_por_tuberia:
                                areas_por_tuberia[id_tuberia] = 0.0
                            areas_por_tuberia[id_tuberia] += triangulo_geom.area()

            idx_poligono += 1

        self.progress.setValue(70)
        self.label_estado.setText('🟡 Estado: Asignando áreas propias (A)...')

        # ===== ASIGNAR ÁREAS PROPIAS (A) =====
        self.capa_tuberias.startEditing()

        for feature in self.capa_tuberias.getFeatures():
            id_o = feature.attribute('ID_O')
            area = areas_por_tuberia.get(id_o, 0.0)
            self.capa_tuberias.changeAttributeValue(
                feature.id(), idx_A, round(area, 3)
            )

        self.capa_tuberias.commitChanges()

        self.progress.setValue(90)
        self.label_estado.setText('🟡 Estado: Guardando Shapefile...')

        # ===== GUARDAR SHAPEFILE =====
        capa_triangulos.dataProvider().addFeatures(features_triangulos)
        capa_triangulos.updateExtents()

        if os.path.exists(nombre_archivo):
            respuesta = QMessageBox.question(
                self.iface.mainWindow(),
                'Archivo existe',
                f'El archivo ya existe.\n¿Deseas sobrescribirlo?',
                QMessageBox.Yes | QMessageBox.No
            )
            if respuesta == QMessageBox.No:
                return

        # ============================================================
        # API MODERNA: writeAsVectorFormatV3
        # ============================================================
        guardado_ok = False
        try:
            options = QgsVectorFileWriter.SaveVectorOptions()
            options.driverName = 'ESRI Shapefile'
            options.fileEncoding = 'utf-8'
            options.layerName = 'GLC_Areas'
            try:
                options.actionOnExistingFile = \
                    QgsVectorFileWriter.CreateOrOverwriteFile
            except AttributeError:
                pass

            transform_context = QgsProject.instance().transformContext()

            resultado = QgsVectorFileWriter.writeAsVectorFormatV3(
                capa_triangulos,
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
            # Fallback para versiones muy antiguas
            error = QgsVectorFileWriter.writeAsVectorFormat(
                capa_triangulos,
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

        capa_guardada = QgsVectorLayer(nombre_archivo, "GLC_Areas", "ogr")
        QgsProject.instance().addMapLayer(capa_guardada)

        self.progress.setValue(100)
        self.label_estado.setText('✅ Estado: Cálculo completado')

        dialog.accept()

        mensaje = "=== ÁREAS PROPIAS CALCULADAS ===\n\n"
        mensaje += f"📊 Polígonos encontrados: {len(poligonos)}\n"
        mensaje += f"📊 Triángulos generados: {len(features_triangulos)}\n"
        mensaje += f"📊 Tuberías con área propia: {len(areas_por_tuberia)}\n"
        mensaje += f"📊 Tuberías totales: {self.capa_tuberias.featureCount()}\n\n"
        mensaje += f"📁 Archivo guardado: {nombre_archivo}\n\n"
        mensaje += "📌 ESTRUCTURA DEL SHAPEFILE GLC_Areas:\n"
        mensaje += "   • ID: Identificador del triángulo\n"
        mensaje += "   • Area_m2: Área del triángulo (m²)\n"
        mensaje += "   • ID_Tuberia: ID de la tubería asociada\n"
        mensaje += "   • Nodo1, Nodo2: Nodos que forman el triángulo\n"
        mensaje += "   • ID_Poligono: Polígono original al que pertenece\n\n"
        mensaje += "📌 CAMPO ACTUALIZADO EN GLC_Tuberias:\n"
        mensaje += "   • A = Área propia (m²)\n\n"
        mensaje += "💡 Para calcular áreas tributarias (At) y acumuladas (Aa),\n"
        mensaje += "   ejecuta el módulo 'Calcular Áreas Acumuladas'."

        QMessageBox.information(
            self.iface.mainWindow(),
            'Cálculo Completado',
            mensaje
        )

    # ============================================================
    # MODO MANUAL — ASEGURAR CAPA DE ÁREAS (GLC_Areas.shp)
    # ============================================================
    def _asegurar_capa_areas_manual(self, crs):
        """
        Carga GLC_Areas.shp si existe, o lo crea si no.
        Lo deja accesible en self.capa_areas_manual y lo añade al proyecto
        si aún no está.
        """
        # 1) Buscar si ya está cargada en el proyecto
        for lyr in QgsProject.instance().mapLayers().values():
            if isinstance(lyr, QgsVectorLayer) and lyr.name() == "GLC_Areas":
                if lyr.geometryType() == QgsWkbTypes.PolygonGeometry:
                    self.capa_areas_manual = lyr
                    self._actualizar_contador_id_areas()
                    return

        # 2) Si hay ruta de guardado, intentar cargar el .shp
        ruta_shp = None
        if self.ruta_guardado and os.path.isdir(self.ruta_guardado):
            posible = os.path.join(self.ruta_guardado, "GLC_Areas.shp")
            if os.path.exists(posible):
                ruta_shp = posible

        if ruta_shp:
            capa = QgsVectorLayer(ruta_shp, "GLC_Areas", "ogr")
            if capa.isValid():
                self._asegurar_campos_areas(capa)
                QgsProject.instance().addMapLayer(capa)
                self.capa_areas_manual = capa
                self._actualizar_contador_id_areas()
                return

        # 3) Si no existe, crear capa en memoria
        uri = f"Polygon?crs={crs.authid()}&index=yes"
        capa = QgsVectorLayer(uri, "GLC_Areas", "memory")
        capa.dataProvider().addAttributes([
            _campo('ID',          'int'),
            _campo('Area_m2',     'double'),
            _campo('ID_Tuberia',  'int'),
            _campo('Nodo1',       'int'),
            _campo('Nodo2',       'int'),
            _campo('Nodo_Centro', 'int'),
            _campo('ID_Poligono', 'int'),
        ])
        capa.updateFields()
        QgsProject.instance().addMapLayer(capa)
        self.capa_areas_manual = capa
        self.contador_id_manual = 1

    def _asegurar_campos_areas(self, capa):
        """Añade los campos que falten en una capa GLC_Areas ya existente."""
        requeridos = [
            ('ID',          'int'),
            ('Area_m2',     'double'),
            ('ID_Tuberia',  'int'),
            ('Nodo1',       'int'),
            ('Nodo2',       'int'),
            ('Nodo_Centro', 'int'),
            ('ID_Poligono', 'int'),
        ]
        faltan = []
        for nombre, tipo in requeridos:
            if capa.fields().indexFromName(nombre) == -1:
                faltan.append(_campo(nombre, tipo))
        if faltan:
            capa.dataProvider().addAttributes(faltan)
            capa.updateFields()

    def _actualizar_contador_id_areas(self):
        """Calcula el siguiente ID disponible en la capa de áreas."""
        if not self.capa_areas_manual:
            self.contador_id_manual = 1
            return
        idx_id = self.capa_areas_manual.fields().indexFromName('ID')
        max_id = 0
        if idx_id != -1:
            for feat in self.capa_areas_manual.getFeatures():
                val = feat.attribute(idx_id)
                if val is not None:
                    try:
                        max_id = max(max_id, int(val))
                    except (ValueError, TypeError):
                        pass
        self.contador_id_manual = max_id + 1

    # ============================================================
    # MODO MANUAL — CONSULTAR ÁREA ACTUAL
    # ============================================================
    def _consultar_area_actual(self):
        """Consulta el área actual de la tubería introducida"""
        if not hasattr(self, 'txt_id_tuberia'):
            return

        texto = self.txt_id_tuberia.text().strip()
        if not texto:
            self.lbl_area_actual.setText('Área actual de la tubería: —')
            return

        try:
            id_tuberia = int(texto)
        except ValueError:
            self.lbl_area_actual.setText('⚠️ ID_O inválido (debe ser número entero)')
            self.lbl_area_actual.setStyleSheet(
                'background-color: #ffcdd2; padding: 8px; border-radius: 4px; '
                'font-family: monospace;'
            )
            return

        layer_id = self.combo_tuberias_manual.currentData()
        if not layer_id:
            self.lbl_area_actual.setText('⚠️ Selecciona una capa primero')
            return

        layer = QgsProject.instance().mapLayer(layer_id)
        if not layer:
            self.lbl_area_actual.setText('⚠️ No se encontró la capa')
            return

        idx_A = layer.fields().indexFromName('A')
        idx_id = layer.fields().indexFromName('ID_O')
        if idx_A == -1 or idx_id == -1:
            self.lbl_area_actual.setText('⚠️ Falta campo A o ID_O en la capa')
            return

        for feat in layer.getFeatures():
            if feat.attribute(idx_id) == id_tuberia:
                area = feat.attribute(idx_A)
                area_str = f'{float(area):.3f}' if area is not None else '0.000'
                self.lbl_area_actual.setText(
                    f'✅ Área actual de la tubería ID_O={id_tuberia}: {area_str} m²'
                )
                self.lbl_area_actual.setStyleSheet(
                    'background-color: #c8e6c9; padding: 8px; border-radius: 4px; '
                    'font-family: monospace;'
                )
                return

        self.lbl_area_actual.setText(
            f'⚠️ No existe la tubería con ID_O={id_tuberia}'
        )
        self.lbl_area_actual.setStyleSheet(
            'background-color: #ffcdd2; padding: 8px; border-radius: 4px; '
            'font-family: monospace;'
        )

    # ============================================================
    # MODO MANUAL — INICIAR DIBUJO
    # ============================================================
    def _iniciar_dibujo_manual(self):
        """Activa el modo de dibujo manual en el mapa"""

        # Validar entrada
        texto = self.txt_id_tuberia.text().strip()
        if not texto:
            QMessageBox.warning(
                self.iface.mainWindow(), 'Error',
                'Introduce el ID_O de la tubería destino antes de dibujar'
            )
            return

        try:
            id_tuberia = int(texto)
        except ValueError:
            QMessageBox.warning(
                self.iface.mainWindow(), 'Error',
                'El ID_O debe ser un número entero'
            )
            return

        layer_id = self.combo_tuberias_manual.currentData()
        if not layer_id:
            QMessageBox.warning(
                self.iface.mainWindow(), 'Error',
                'Selecciona una capa de tuberías primero'
            )
            return

        layer = QgsProject.instance().mapLayer(layer_id)
        if not layer:
            QMessageBox.warning(
                self.iface.mainWindow(), 'Error',
                'No se encontró la capa seleccionada'
            )
            return

        # Verificar que la tubería exista
        idx_id = layer.fields().indexFromName('ID_O')
        if idx_id == -1:
            QMessageBox.warning(
                self.iface.mainWindow(), 'Error',
                'La capa no tiene el campo ID_O'
            )
            return

        existe = False
        for feat in layer.getFeatures():
            if feat.attribute(idx_id) == id_tuberia:
                existe = True
                break

        if not existe:
            QMessageBox.warning(
                self.iface.mainWindow(), 'Error',
                f'No existe ninguna tubería con ID_O={id_tuberia}'
            )
            return

        # Asegurar que exista el campo A
        if layer.fields().indexFromName('A') == -1:
            layer.dataProvider().addAttributes([_campo('A', 'double')])
            layer.updateFields()

        # ============================================================
        # Cargar o crear el shapefile GLC_Areas.shp para guardar los polígonos manuales
        # ============================================================
        self._asegurar_capa_areas_manual(crs=layer.crs())

        # Guardar referencias
        self.id_tuberia_destino = id_tuberia
        self.capa_tuberias_dibujo = layer

        # Limpiar estado anterior
        self.puntos_dibujo = []
        self.dibujando = True

        # Ocultar diálogo
        if self.dialog:
            try:
                self.dialog.hide()
            except RuntimeError:
                pass

        # Crear rubber band para feedback visual
        try:
            self.rubber_band = QgsRubberBand(
                self.iface.mapCanvas(), QgsWkbTypes.PolygonGeometry
            )
            self.rubber_band.setColor(QColor(255, 152, 0, 100))       # naranja translúcido
            self.rubber_band.setWidth(2)
            self.rubber_band.setFillColor(QColor(255, 152, 0, 60))
        except Exception:
            self.rubber_band = None

        # Crear tool de captura de clics
        self.tool_seleccion = QgsMapToolEmitPoint(self.iface.mapCanvas())
        self.tool_seleccion.canvasClicked.connect(self._on_click_dibujo)
        self.iface.mapCanvas().setMapTool(self.tool_seleccion)

        # Instrucciones
        QMessageBox.information(
            self.iface.mainWindow(),
            'Modo Dibujo Manual',
            f'📌 Dibujando área para la tubería ID_O={id_tuberia}\n\n'
            '🔹 Haz clic en el mapa para añadir vértices\n'
            '🔹 Doble clic (o clic derecho) para cerrar el polígono\n'
            '🔹 Presiona ESC para cancelar'
        )

    # ============================================================
    # MODO MANUAL — CLICK EN EL MAPA
    # ============================================================
    def _on_click_dibujo(self, point, button):
        """Captura cada clic del usuario durante el dibujo"""

        if not self.dibujando:
            return

        # Botón derecho = cerrar polígono
        try:
            if button == Qt.RightButton:
                self._cerrar_poligono()
                return
        except Exception:
            pass

        # Añadir punto
        self.puntos_dibujo.append(QgsPointXY(point.x(), point.y()))

        # Actualizar rubber band
        if self.rubber_band is not None:
            try:
                self.rubber_band.reset(QgsWkbTypes.PolygonGeometry)
                for p in self.puntos_dibujo:
                    self.rubber_band.addPoint(p, False)
                # Cerrar visualmente
                if len(self.puntos_dibujo) >= 3:
                    self.rubber_band.addPoint(self.puntos_dibujo[0], True)
            except Exception:
                pass

        # Feedback en barra de estado
        try:
            self.iface.statusBarIface().showMessage(
                f'📍 Vértices: {len(self.puntos_dibujo)} '
                f'(doble clic o clic derecho para cerrar)',
                4000
            )
        except Exception:
            pass

        # Detectar doble clic (aproximado: si el mismo punto llega 2 veces seguidas)
        if len(self.puntos_dibujo) >= 2:
            p1 = self.puntos_dibujo[-1]
            p2 = self.puntos_dibujo[-2]
            if p1.distance(p2) < 0.001:
                # Fue un doble clic → cerrar
                self.puntos_dibujo.pop()  # quitar el duplicado
                self._cerrar_poligono()

    # ============================================================
    # MODO MANUAL — CERRAR POLÍGONO
    # ============================================================
    def _cerrar_poligono(self):
        """Cierra el polígono, calcula el área y la suma a la tubería"""

        if len(self.puntos_dibujo) < 3:
            QMessageBox.warning(
                self.iface.mainWindow(), 'Error',
                f'Se necesitan al menos 3 vértices para formar un polígono.\n'
                f'Actuales: {len(self.puntos_dibujo)}'
            )
            return

        # Crear geometría del polígono
        puntos_cerrados = list(self.puntos_dibujo)
        puntos_cerrados.append(self.puntos_dibujo[0])

        try:
            poligono = QgsGeometry.fromPolygonXY([puntos_cerrados])
        except Exception as e:
            QMessageBox.warning(
                self.iface.mainWindow(), 'Error',
                f'No se pudo crear el polígono: {e}'
            )
            return

        if poligono.isEmpty() or not poligono.isGeosValid():
            QMessageBox.warning(
                self.iface.mainWindow(), 'Error',
                'El polígono dibujado no es válido. Intenta de nuevo.'
            )
            return

        area_dibujada = poligono.area()

        # Confirmar antes de sumar
        resp = QMessageBox.question(
            self.iface.mainWindow(),
            'Confirmar área dibujada',
            f'📐 Área calculada: {area_dibujada:.3f} m²\n\n'
            f'¿Sumar esta área al campo A de la tubería '
            f'ID_O={self.id_tuberia_destino}?\n\n'
            '(Puedes dibujar más áreas después)',
            QMessageBox.Yes | QMessageBox.No
        )

        if resp != QMessageBox.Yes:
            # Cancelar: limpiar sin guardar
            self.puntos_dibujo = []
            if self.rubber_band:
                try:
                    self.rubber_band.reset(QgsWkbTypes.PolygonGeometry)
                except Exception:
                    pass
            return

        # Sumar el área a la tubería
        layer = self.capa_tuberias_dibujo
        idx_A = layer.fields().indexFromName('A')
        idx_id = layer.fields().indexFromName('ID_O')

        exito = False
        area_actual = 0.0
        area_nueva = area_dibujada

        try:
            layer.startEditing()
            for feat in layer.getFeatures():
                if feat.attribute(idx_id) == self.id_tuberia_destino:
                    area_actual = feat.attribute(idx_A)
                    if area_actual is None:
                        area_actual = 0.0
                    area_actual = float(area_actual)
                    area_nueva = area_actual + area_dibujada
                    layer.changeAttributeValue(
                        feat.id(), idx_A, round(area_nueva, 3)
                    )
                    exito = True
                    break
            layer.commitChanges()
        except Exception as e:
            try:
                layer.rollBack()
            except Exception:
                pass
            QMessageBox.critical(
                self.iface.mainWindow(), 'Error',
                f'No se pudo sumar el área: {e}'
            )
            return

        if not exito:
            QMessageBox.warning(
                self.iface.mainWindow(), 'Error',
                f'No se encontró la tubería ID_O={self.id_tuberia_destino}'
            )
            return

        # Refrescar mapa
        try:
            self.iface.mapCanvas().refresh()
        except Exception:
            pass

        # ============================================================
        # GUARDAR EL POLÍGONO DIBUJADO EN GLC_Areas
        # ============================================================
        self._guardar_poligono_en_areas(
            poligono=poligono,
            area=area_dibujada,
            id_tuberia=self.id_tuberia_destino
        )

        # Actualizar label de área actual
        self._consultar_area_actual()

        # Actualizar log
        self._agregar_log_manual(
            f'✅ Tubería ID_O={self.id_tuberia_destino}: '
            f'+{area_dibujada:.3f} m² → total {area_nueva:.3f} m²'
        )

        # Limpiar rubber band y puntos
        self.puntos_dibujo = []
        if self.rubber_band:
            try:
                self.rubber_band.reset(QgsWkbTypes.PolygonGeometry)
            except Exception:
                pass

        # ============================================================
        # FINALIZAR DIBUJO AUTOMÁTICAMENTE
        # ============================================================
        # Mostrar solo mensaje informativo y terminar la edición
        QMessageBox.information(
            self.iface.mainWindow(),
            'Área guardada',
            f'✅ Área agregada correctamente.\n\n'
            f'📌 Tubería ID_O={self.id_tuberia_destino}\n'
            f'📐 Área sumada: {area_dibujada:.3f} m²\n'
            f'📊 Área total ahora: {area_nueva:.3f} m²\n\n'
            f'✔️ Edición finalizada para esta tubería.'
        )

        # Terminar: desactivar tool y volver al diálogo
        self._finalizar_dibujo_manual()

    # ============================================================
    # MODO MANUAL — GUARDAR POLÍGONO EN GLC_Areas
    # ============================================================
    def _guardar_poligono_en_areas(self, poligono, area, id_tuberia):
        """
        Guarda el polígono dibujado como una feature en GLC_Areas.
        Intenta completar Nodo1 y Nodo2 a partir de Ci/Cf de la tubería.
        """
        if self.capa_areas_manual is None:
            return

        # Intentar obtener Ci/Cf de la tubería destino
        nodo1 = -1
        nodo2 = -1
        try:
            layer_tub = self.capa_tuberias_dibujo
            if layer_tub is not None:
                idx_id = layer_tub.fields().indexFromName('ID_O')
                idx_ci = layer_tub.fields().indexFromName('Ci')
                idx_cf = layer_tub.fields().indexFromName('Cf')
                if idx_id != -1:
                    for feat in layer_tub.getFeatures():
                        if feat.attribute(idx_id) == id_tuberia:
                            if idx_ci != -1:
                                v = feat.attribute(idx_ci)
                                if v is not None:
                                    try:
                                        nodo1 = int(v)
                                    except (ValueError, TypeError):
                                        pass
                            if idx_cf != -1:
                                v = feat.attribute(idx_cf)
                                if v is not None:
                                    try:
                                        nodo2 = int(v)
                                    except (ValueError, TypeError):
                                        pass
                            break
        except Exception:
            pass

        # Crear feature
        try:
            feat = QgsFeature(self.capa_areas_manual.fields())
            feat.setGeometry(poligono)

            # Siguiente ID
            nuevo_id = self.contador_id_manual
            self.contador_id_manual += 1

            # Asignar atributos por nombre (más robusto)
            campos = self.capa_areas_manual.fields()
            valores = {
                'ID':          nuevo_id,
                'Area_m2':     round(area, 3),
                'ID_Tuberia':  int(id_tuberia),
                'Nodo1':       nodo1,
                'Nodo2':       nodo2,
                'Nodo_Centro': -1,
                'ID_Poligono': -1,
            }
            for nombre, valor in valores.items():
                idx = campos.indexFromName(nombre)
                if idx != -1:
                    feat.setAttribute(idx, valor)

            self.capa_areas_manual.startEditing()
            self.capa_areas_manual.addFeature(feat)
            self.capa_areas_manual.commitChanges()

            # Refrescar mapa
            try:
                self.capa_areas_manual.triggerRepaint()
            except Exception:
                pass

        except Exception as e:
            try:
                self.capa_areas_manual.rollBack()
            except Exception:
                pass
            QMessageBox.warning(
                self.iface.mainWindow(),
                'Aviso',
                f'El área se sumó a la tubería, pero no se pudo guardar '
                f'el polígono en GLC_Areas:\n{e}'
            )

    # ============================================================
    # MODO MANUAL — FINALIZAR DIBUJO
    # ============================================================
    def _finalizar_dibujo_manual(self):
        """Desactiva el tool y vuelve a mostrar el diálogo"""
        self.dibujando = False

        if self.tool_seleccion:
            try:
                self.iface.mapCanvas().unsetMapTool(self.tool_seleccion)
            except Exception:
                pass
            self.tool_seleccion = None

        if self.rubber_band:
            try:
                self.rubber_band.reset(QgsWkbTypes.PolygonGeometry)
            except Exception:
                pass

        self.puntos_dibujo = []

        if self.dialog:
            try:
                self.dialog.show()
                self.dialog.raise_()
                self.dialog.activateWindow()
            except RuntimeError:
                pass

    # ============================================================
    # MODO MANUAL — AÑADIR AL LOG
    # ============================================================
    def _agregar_log_manual(self, texto):
        """Añade una línea al log de dibujos"""
        if not hasattr(self, 'text_log_manual'):
            return

        try:
            actual = self.text_log_manual.text()
            if actual == 'Sin dibujos aún.':
                actual = ''
            nueva = (actual + '\n' + texto).strip()
            self.text_log_manual.setText(nueva)
        except Exception:
            pass

    # ============================================================
    # ENCONTRAR CARAS (MODO AUTOMÁTICO)
    # ============================================================
    def encontrar_todas_las_caras(self, nodos, conexiones):
        """Encuentra todas las caras (polígonos) del grafo"""
        if len(nodos) < 3:
            return []

        aristas_por_nodo = {}

        for nodo_id, vecinos in conexiones.items():
            if nodo_id not in nodos:
                continue

            aristas_por_nodo[nodo_id] = []
            for vecino in vecinos:
                if vecino not in nodos:
                    continue
                punto_actual = nodos[nodo_id]['punto']
                punto_vecino = nodos[vecino]['punto']
                angulo = math.atan2(
                    punto_vecino.y() - punto_actual.y(),
                    punto_vecino.x() - punto_actual.x()
                )
                aristas_por_nodo[nodo_id].append({
                    'vecino': vecino,
                    'angulo': angulo
                })

            aristas_por_nodo[nodo_id].sort(key=lambda x: x['angulo'])

        caras = []
        aristas_visitadas = set()

        for nodo_inicio in aristas_por_nodo.keys():
            for arista in aristas_por_nodo[nodo_inicio]:
                arista_key = (nodo_inicio, arista['vecino'])
                if arista_key in aristas_visitadas:
                    continue

                cara = []
                nodo_actual = nodo_inicio
                nodo_siguiente = arista['vecino']

                while True:
                    arista_actual = (nodo_actual, nodo_siguiente)
                    if arista_actual in aristas_visitadas:
                        break

                    aristas_visitadas.add(arista_actual)
                    cara.append(nodo_actual)

                    if nodo_siguiente not in aristas_por_nodo:
                        break

                    vecinos_ordenados = aristas_por_nodo[nodo_siguiente]
                    indice = None
                    for i, v in enumerate(vecinos_ordenados):
                        if v['vecino'] == nodo_actual:
                            indice = i
                            break

                    if indice is None:
                        break

                    nuevo_indice = (indice - 1) % len(vecinos_ordenados)
                    nodo_anterior = nodo_actual
                    nodo_actual = nodo_siguiente
                    nodo_siguiente = vecinos_ordenados[nuevo_indice]['vecino']

                if len(cara) >= 3:
                    caras.append(cara)

        caras_unicas = []
        for cara in caras:
            if len(cara) < 3:
                continue

            existe = False
            for c in caras_unicas:
                if set(cara) == set(c):
                    existe = True
                    break
            if not existe:
                puntos = []
                for nodo_id in cara:
                    if nodo_id in nodos:
                        punto = nodos[nodo_id]['punto']
                        puntos.append(QgsPointXY(punto.x(), punto.y()))

                if len(puntos) >= 3:
                    puntos_cerrados = puntos.copy()
                    puntos_cerrados.append(puntos[0])
                    poligono = QgsGeometry.fromPolygonXY([puntos_cerrados])
                    if poligono and not poligono.isEmpty() and poligono.isGeosValid():
                        caras_unicas.append({
                            'nodos': cara,
                            'geom': poligono,
                            'area': poligono.area()
                        })

        caras_unicas.sort(key=lambda x: x['area'])
        return caras_unicas

    # ============================================================
    # DESACTIVAR
    # ============================================================
    def desactivar(self, mostrar_mensaje=True):
        """Limpieza al descargar el plugin"""
        try:
            self._finalizar_dibujo_manual()
        except Exception:
            pass
        if self.rubber_band:
            try:
                self.rubber_band.reset(QgsWkbTypes.PolygonGeometry)
            except Exception:
                pass
        self.rubber_band = None