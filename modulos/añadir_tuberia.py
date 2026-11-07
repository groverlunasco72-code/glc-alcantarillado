# -*- coding: utf-8 -*-
"""
Módulo Añadir Tubería.

CORRECCIONES APLICADAS:
- actualizar_lineas_id: localiza la cámara por ID_O (no por FID dentro del bucle).
- on_canvas_click_nueva: elimina la 3ª llamada duplicada a actualizar_lineas_id
  (nuevo_id_camara es siempre igual a ci o cf).

Compatible con QGIS 3.x y preparado para 4.x.
"""

from qgis.core import (
    QgsProject, QgsVectorLayer, QgsFeature,
    QgsGeometry, QgsPointXY, QgsField,
    QgsWkbTypes, QgsLineString,
    QgsRasterLayer,
    QgsPoint
)
from qgis.PyQt.QtCore import Qt, QVariant
from qgis.PyQt.QtWidgets import (
    QMessageBox, QDialog, QVBoxLayout, QLabel,
    QPushButton, QComboBox, QHBoxLayout, QLineEdit,
    QRadioButton, QButtonGroup, QTabWidget, QWidget
)
from qgis.gui import QgsMapToolEmitPoint
from .utils import obtener_vertices_linea, extraer_cota_dem


class AnadirTuberia:
    def __init__(self, iface):
        self.iface = iface
        self.capa_tuberias = None
        self.capa_camaras = None
        self.capa_dem = None
        self.tool_seleccion = None
        self.modo_edicion = False
        self.id_sugerido = ""
        self.dialog = None
        self.camara_existente_seleccionada = None
        self.punto_creado = None

    # ============================================================
    # DIÁLOGO
    # ============================================================
    def mostrar_dialogo(self):
        dialog = QDialog(self.iface.mainWindow())
        dialog.setWindowTitle('GLC - Añadir Tuberia')
        dialog.setMinimumWidth(600)
        self.dialog = dialog

        layout = QVBoxLayout()

        label_titulo = QLabel('<b>Añadir Tuberia</b>')
        label_titulo.setStyleSheet('font-size: 12pt; font-weight: bold;')
        layout.addWidget(label_titulo)

        # ===== TABS =====
        tabs = QTabWidget()

        # ---------- TAB 1: AÑADIR CON NUEVA CAMARA ----------
        tab_nueva = QWidget()
        layout_nueva = QVBoxLayout()

        label_info_nueva = QLabel(
            'Añade una nueva tuberia conectando una camara existente con una NUEVA camara.\n'
            'PASO 1: Selecciona la camara existente\n'
            'PASO 2: Haz clic en el mapa para crear la nueva camara\n\n'
            '📌 Se crea una nueva camara y una nueva tuberia'
        )
        label_info_nueva.setWordWrap(True)
        layout_nueva.addWidget(label_info_nueva)

        layout_nueva.addWidget(QLabel('-' * 40))

        # Seleccionar capas
        layout_nueva.addWidget(QLabel('Seleccionar capa GLC_Tuberias:'))
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
        layout_nueva.addWidget(combo_tuberias)

        layout_nueva.addWidget(QLabel('Seleccionar capa de Camaras:'))
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
        layout_nueva.addWidget(combo_camaras)

        layout_nueva.addWidget(QLabel('Seleccionar DEM (para cota Z - opcional):'))
        combo_dem = QComboBox()
        combo_dem.addItem('-- Ninguno --', None)
        for layer in QgsProject.instance().mapLayers().values():
            if isinstance(layer, QgsRasterLayer):
                combo_dem.addItem(layer.name(), layer.id())
        layout_nueva.addWidget(combo_dem)

        layout_nueva.addWidget(QLabel('-' * 40))

        # Seleccionar camara existente
        layout_nueva.addWidget(QLabel('Seleccionar camara existente (ID_O):'))
        combo_camara_existente = QComboBox()
        combo_camara_existente.setEditable(True)
        combo_camara_existente.addItem('-- Seleccionar --')
        combo_camaras.currentIndexChanged.connect(
            lambda: self.cargar_camaras(combo_camaras, combo_camara_existente)
        )
        self.cargar_camaras(combo_camaras, combo_camara_existente)
        layout_nueva.addWidget(combo_camara_existente)

        layout_nueva.addWidget(QLabel('-' * 40))

        # Direccion de la tuberia
        layout_nueva.addWidget(QLabel('Direccion de la tuberia:'))
        radio_group = QButtonGroup()
        radio_ci_nueva = QRadioButton('Camara existente → Nueva camara')
        radio_ci_nueva.setChecked(True)
        radio_nueva_ci = QRadioButton('Nueva camara → Camara existente')
        radio_group.addButton(radio_ci_nueva)
        radio_group.addButton(radio_nueva_ci)
        layout_nueva.addWidget(radio_ci_nueva)
        layout_nueva.addWidget(radio_nueva_ci)

        layout_nueva.addWidget(QLabel('-' * 40))

        # ID de la nueva camara y tuberia
        hbox_id_cam = QHBoxLayout()
        hbox_id_cam.addWidget(QLabel('ID_O nueva camara:'))
        txt_id_cam = QLineEdit()
        txt_id_cam.setPlaceholderText('Auto')
        hbox_id_cam.addWidget(txt_id_cam)
        layout_nueva.addLayout(hbox_id_cam)

        hbox_id_tub = QHBoxLayout()
        hbox_id_tub.addWidget(QLabel('ID_O nueva tuberia:'))
        txt_id_tub = QLineEdit()
        txt_id_tub.setPlaceholderText('Auto')
        hbox_id_tub.addWidget(txt_id_tub)
        layout_nueva.addLayout(hbox_id_tub)

        layout_nueva.addWidget(QLabel('-' * 40))

        btn_anadir_nueva = QPushButton('Añadir Tuberia (Click en el mapa)')
        btn_anadir_nueva.setStyleSheet(
            'background-color: #4CAF50; color: white; font-weight: bold;'
        )
        btn_anadir_nueva.clicked.connect(lambda: self.activar_anadir_nueva(
            combo_tuberias.currentData(),
            combo_camaras.currentData(),
            combo_dem.currentData(),
            combo_camara_existente.currentText(),
            radio_ci_nueva.isChecked(),
            txt_id_cam.text(),
            txt_id_tub.text()
        ))
        layout_nueva.addWidget(btn_anadir_nueva)

        tab_nueva.setLayout(layout_nueva)
        tabs.addTab(tab_nueva, '1. Nueva Camara')

        # ---------- TAB 2: UNIR CAMARAS EXISTENTES ----------
        tab_unir = QWidget()
        layout_unir = QVBoxLayout()

        label_info_unir = QLabel(
            'Une dos camaras existentes con una nueva tuberia.\n'
            'PASO 1: Selecciona la camara de inicio (Ci)\n'
            'PASO 2: Selecciona la camara final (Cf)\n\n'
            '📌 Solo se crea la tuberia (no se crean nuevas camaras)\n'
            '📌 Se actualiza Lineas_ID en ambas camaras'
        )
        label_info_unir.setWordWrap(True)
        layout_unir.addWidget(label_info_unir)

        layout_unir.addWidget(QLabel('-' * 40))

        # Seleccionar capas
        layout_unir.addWidget(QLabel('Seleccionar capa GLC_Tuberias:'))
        combo_tuberias_unir = QComboBox()
        for layer in QgsProject.instance().mapLayers().values():
            if isinstance(layer, QgsVectorLayer):
                if layer.geometryType() == QgsWkbTypes.LineGeometry:
                    if 'GLC_Tuberias' in layer.name():
                        combo_tuberias_unir.addItem(layer.name(), layer.id())
        if combo_tuberias_unir.count() == 0:
            for layer in QgsProject.instance().mapLayers().values():
                if isinstance(layer, QgsVectorLayer):
                    if layer.geometryType() == QgsWkbTypes.LineGeometry:
                        combo_tuberias_unir.addItem(layer.name(), layer.id())
        layout_unir.addWidget(combo_tuberias_unir)

        layout_unir.addWidget(QLabel('Seleccionar capa de Camaras:'))
        combo_camaras_unir = QComboBox()
        for layer in QgsProject.instance().mapLayers().values():
            if isinstance(layer, QgsVectorLayer):
                if layer.geometryType() == QgsWkbTypes.PointGeometry:
                    if 'GLC_Camaras' in layer.name():
                        combo_camaras_unir.addItem(layer.name(), layer.id())
        if combo_camaras_unir.count() == 0:
            for layer in QgsProject.instance().mapLayers().values():
                if isinstance(layer, QgsVectorLayer):
                    if layer.geometryType() == QgsWkbTypes.PointGeometry:
                        combo_camaras_unir.addItem(layer.name(), layer.id())
        layout_unir.addWidget(combo_camaras_unir)

        layout_unir.addWidget(QLabel('-' * 40))

        # Seleccionar camara inicio
        layout_unir.addWidget(QLabel('Camara de inicio (Ci):'))
        combo_ci_unir = QComboBox()
        combo_ci_unir.setEditable(True)
        combo_ci_unir.addItem('-- Seleccionar --')
        combo_camaras_unir.currentIndexChanged.connect(
            lambda: self.cargar_camaras(combo_camaras_unir, combo_ci_unir)
        )
        self.cargar_camaras(combo_camaras_unir, combo_ci_unir)
        layout_unir.addWidget(combo_ci_unir)

        # Seleccionar camara final
        layout_unir.addWidget(QLabel('Camara final (Cf):'))
        combo_cf_unir = QComboBox()
        combo_cf_unir.setEditable(True)
        combo_cf_unir.addItem('-- Seleccionar --')
        combo_camaras_unir.currentIndexChanged.connect(
            lambda: self.cargar_camaras(combo_camaras_unir, combo_cf_unir)
        )
        self.cargar_camaras(combo_camaras_unir, combo_cf_unir)
        layout_unir.addWidget(combo_cf_unir)

        layout_unir.addWidget(QLabel('-' * 40))

        # ID de la nueva tuberia
        hbox_id_tub_unir = QHBoxLayout()
        hbox_id_tub_unir.addWidget(QLabel('ID_O nueva tuberia:'))
        txt_id_tub_unir = QLineEdit()
        txt_id_tub_unir.setPlaceholderText('Auto')
        hbox_id_tub_unir.addWidget(txt_id_tub_unir)
        layout_unir.addLayout(hbox_id_tub_unir)

        layout_unir.addWidget(QLabel('-' * 40))

        # Direccion de la tuberia (segun seleccion de camaras)
        layout_unir.addWidget(QLabel('Direccion de flujo:'))
        radio_group_unir = QButtonGroup()
        radio_ci_cf = QRadioButton('Ci → Cf')
        radio_ci_cf.setChecked(True)
        radio_cf_ci = QRadioButton('Cf → Ci')
        radio_group_unir.addButton(radio_ci_cf)
        radio_group_unir.addButton(radio_cf_ci)
        layout_unir.addWidget(radio_ci_cf)
        layout_unir.addWidget(radio_cf_ci)

        layout_unir.addWidget(QLabel('-' * 40))

        btn_unir = QPushButton('Unir Camaras')
        btn_unir.setStyleSheet(
            'background-color: #FF9800; color: white; font-weight: bold;'
        )
        btn_unir.clicked.connect(lambda: self.unir_camaras(
            combo_tuberias_unir.currentData(),
            combo_camaras_unir.currentData(),
            combo_ci_unir.currentText(),
            combo_cf_unir.currentText(),
            radio_ci_cf.isChecked(),
            txt_id_tub_unir.text()
        ))
        layout_unir.addWidget(btn_unir)

        tab_unir.setLayout(layout_unir)
        tabs.addTab(tab_unir, '2. Unir Camaras')

        layout.addWidget(tabs)

        # Boton cancelar
        btn_cancelar = QPushButton('Cancelar')
        btn_cancelar.setStyleSheet('background-color: #f44336; color: white;')
        btn_cancelar.clicked.connect(dialog.reject)
        layout.addWidget(btn_cancelar)

        dialog.setLayout(layout)
        dialog.exec_()

    # ============================================================
    # CARGA DE CÁMARAS EN COMBO
    # ============================================================
    def cargar_camaras(self, combo_camaras, combo_camara_destino):
        """Cargar IDs de camaras en el combo (por ID_O)"""
        combo_camara_destino.clear()
        combo_camara_destino.addItem('-- Seleccionar --')

        layer_id = combo_camaras.currentData()
        if not layer_id:
            return

        layer = QgsProject.instance().mapLayer(layer_id)
        if not layer:
            return

        idx_id = layer.fields().indexFromName('ID_O')
        if idx_id == -1:
            return

        for feature in layer.getFeatures():
            id_o = feature.attribute('ID_O')
            if id_o is not None:
                combo_camara_destino.addItem(str(id_o))

    # ============================================================
    # HELPERS DE IDs
    # ============================================================
    def obtener_maximo_id(self, layer):
        max_id = 0
        for feature in layer.getFeatures():
            id_o = feature.attribute('ID_O')
            if id_o is not None and id_o > max_id:
                max_id = id_o
        return max_id

    def obtener_nuevo_id(self, layer, id_sugerido=None):
        max_id = self.obtener_maximo_id(layer)
        if id_sugerido and id_sugerido.isdigit():
            id_int = int(id_sugerido)
            if id_int > max_id:
                return id_int
            else:
                return max_id + 1
        else:
            return max_id + 1

    # ============================================================
    # BÚSQUEDA ROBUSTA POR ID_O
    # ============================================================
    def _buscar_camara_por_id_o(self, id_camara):
        """Busca una cámara por ID_O y devuelve el feature (o None)."""
        for feature in self.capa_camaras.getFeatures():
            if feature.attribute('ID_O') == id_camara:
                return feature
        return None

    def obtener_cota_camara(self, id_camara):
        camara = self._buscar_camara_por_id_o(id_camara)
        return camara.attribute('Z') if camara else None

    # ============================================================
    # ACTUALIZAR LINEAS_ID (por ID_O)
    # ============================================================
    def actualizar_lineas_id(self, id_camara, id_tuberia, accion):
        """
        Actualiza Lineas_ID y N_Lineas de la cámara con ID_O == id_camara.

        - La cámara se localiza por ID_O (no por FID dentro del bucle).
        - El FID solo se usa como argumento puntual de changeAttributeValue.
        """
        idx_lineas_id = self.capa_camaras.fields().indexFromName('Lineas_ID')
        if idx_lineas_id == -1:
            return

        # 1) Localizar la cámara por ID_O
        camara = self._buscar_camara_por_id_o(id_camara)
        if camara is None:
            return

        # 2) Recalcular Lineas_ID
        lineas_id_str = camara.attribute('Lineas_ID') or ''
        lineas_list = []
        if lineas_id_str:
            lineas_list = [int(x.strip()) for x in lineas_id_str.split(',')
                           if x.strip().isdigit()]

        if accion == 'añadir' and id_tuberia not in lineas_list:
            lineas_list.append(id_tuberia)
        elif accion == 'quitar' and id_tuberia in lineas_list:
            lineas_list.remove(id_tuberia)

        lineas_list = sorted(set(lineas_list))
        nueva_lineas_id = ', '.join(str(x) for x in lineas_list) if lineas_list else ''

        # 3) Aplicar cambios (FID puntual)
        fid = camara.id()
        idx_n_lineas = self.capa_camaras.fields().indexFromName('N_Lineas')

        self.capa_camaras.startEditing()
        self.capa_camaras.changeAttributeValue(fid, idx_lineas_id, nueva_lineas_id)
        if idx_n_lineas != -1:
            self.capa_camaras.changeAttributeValue(fid, idx_n_lineas, len(lineas_list))
        self.capa_camaras.commitChanges()

    # ============================================================
    # TAB 1: AÑADIR CON NUEVA CAMARA
    # ============================================================
    def activar_anadir_nueva(self, tuberias_id, camaras_id, dem_id,
                             camara_existente_str, ci_es_existente,
                             id_cam_sugerido, id_tub_sugerido):
        """Activar herramienta para añadir tuberia con nueva camara"""

        self.capa_tuberias = QgsProject.instance().mapLayer(tuberias_id)
        self.capa_camaras = QgsProject.instance().mapLayer(camaras_id)
        self.capa_dem = QgsProject.instance().mapLayer(dem_id) if dem_id else None

        if not self.capa_tuberias or not self.capa_camaras:
            QMessageBox.warning(self.iface.mainWindow(), 'Error',
                                'No se encontraron las capas')
            return

        try:
            self.camara_existente = int(camara_existente_str)
        except Exception:
            QMessageBox.warning(self.iface.mainWindow(), 'Error',
                                'Selecciona una camara existente valida')
            return

        self.ci_es_existente = ci_es_existente
        self.id_cam_sugerido = id_cam_sugerido
        self.id_tub_sugerido = id_tub_sugerido

        self.tool_seleccion = QgsMapToolEmitPoint(self.iface.mapCanvas())
        self.tool_seleccion.canvasClicked.connect(self.on_canvas_click_nueva)
        self.iface.mapCanvas().setMapTool(self.tool_seleccion)
        self.modo_edicion = True

        if self.dialog:
            self.dialog.accept()

        QMessageBox.information(
            self.iface.mainWindow(),
            'Modo Añadir Tuberia',
            '🔹 Haz clic en el mapa para crear la nueva camara\n'
            '🔹 Se creara una nueva camara y una nueva tuberia\n'
            '🔹 La tuberia conectara la camara existente con la nueva\n'
            '🔹 Presiona ESC para cancelar'
        )

    def on_canvas_click_nueva(self, point):
        """Manejar click para añadir tuberia con nueva camara"""

        punto = point

        cota_nueva = None
        if self.capa_dem:
            cota_nueva = extraer_cota_dem(
                self.capa_dem, QgsPointXY(punto.x(), punto.y())
            )

        if cota_nueva is None:
            cota_nueva = 0.0

        # Obtener informacion de la camara existente (por ID_O)
        camara_existente_feature = self._buscar_camara_por_id_o(self.camara_existente)

        if camara_existente_feature is None:
            QMessageBox.warning(self.iface.mainWindow(), 'Error',
                                'No se encontro la camara existente')
            return

        geom_existente = camara_existente_feature.geometry()
        punto_existente = geom_existente.asPoint()
        cota_existente = camara_existente_feature.attribute('Z') or 0.0

        # Crear nueva camara
        nuevo_id_camara = self.obtener_nuevo_id(self.capa_camaras, self.id_cam_sugerido)

        self.capa_camaras.startEditing()
        new_camara = QgsFeature(self.capa_camaras.fields())
        new_camara.setGeometry(QgsGeometry.fromPointXY(QgsPointXY(punto.x(), punto.y())))

        campos_camara = {}
        for field in self.capa_camaras.fields():
            campos_camara[field.name()] = None

        campos_camara['ID_O'] = nuevo_id_camara
        campos_camara['X'] = round(punto.x(), 3)
        campos_camara['Y'] = round(punto.y(), 3)
        campos_camara['Z'] = round(cota_nueva, 3)
        campos_camara['N_Lineas'] = 1
        campos_camara['Lineas_ID'] = ''
        campos_camara['Tipo'] = 'Nueva'

        new_camara.setAttributes(
            [campos_camara[f.name()] for f in self.capa_camaras.fields()]
        )
        self.capa_camaras.addFeature(new_camara)
        self.capa_camaras.commitChanges()

        # Obtener cotas
        cota_existente = self.obtener_cota_camara(self.camara_existente)
        cota_nueva = self.obtener_cota_camara(nuevo_id_camara)

        if cota_existente is None:
            cota_existente = 0.0
        if cota_nueva is None:
            cota_nueva = 0.0

        # Determinar Ci y Cf
        if self.ci_es_existente:
            ci = self.camara_existente
            cf = nuevo_id_camara
            punto_ci = punto_existente
            punto_cf = punto
            cota_ci = cota_existente
            cota_cf = cota_nueva
        else:
            ci = nuevo_id_camara
            cf = self.camara_existente
            punto_ci = punto
            punto_cf = punto_existente
            cota_ci = cota_nueva
            cota_cf = cota_existente

        # Crear la tuberia
        nuevo_id_tuberia = self.obtener_nuevo_id(self.capa_tuberias, self.id_tub_sugerido)

        linea = QgsLineString([
            QgsPoint(punto_ci.x(), punto_ci.y()),
            QgsPoint(punto_cf.x(), punto_cf.y())
        ])
        geom = QgsGeometry(linea)

        longitud = geom.length()

        pendiente = 0.0
        if cota_ci is not None and cota_cf is not None and longitud > 0:
            pendiente = (cota_ci - cota_cf) / longitud * 100

        if punto_cf.x() > punto_ci.x():
            dir_flujo = '->'
        elif punto_cf.x() < punto_ci.x():
            dir_flujo = '<-'
        else:
            dir_flujo = '->' if punto_cf.y() > punto_ci.y() else '<-'

        campos_tuberia = {}
        for field in self.capa_tuberias.fields():
            campos_tuberia[field.name()] = None

        campos_tuberia['ID_O'] = nuevo_id_tuberia
        campos_tuberia['Ci'] = ci
        campos_tuberia['Cf'] = cf
        campos_tuberia['Xi'] = round(punto_ci.x(), 3)
        campos_tuberia['Yi'] = round(punto_ci.y(), 3)
        campos_tuberia['Zi'] = round(cota_ci, 3)
        campos_tuberia['Xf'] = round(punto_cf.x(), 3)
        campos_tuberia['Yf'] = round(punto_cf.y(), 3)
        campos_tuberia['Zf'] = round(cota_cf, 3)
        campos_tuberia['L'] = round(longitud, 3)
        campos_tuberia['S'] = round(pendiente, 3)
        campos_tuberia['dir'] = dir_flujo
        campos_tuberia['cab_ata'] = ''

        self.capa_tuberias.startEditing()
        new_tuberia = QgsFeature(self.capa_tuberias.fields())
        new_tuberia.setGeometry(geom)
        new_tuberia.setAttributes(
            [campos_tuberia[f.name()] for f in self.capa_tuberias.fields()]
        )
        self.capa_tuberias.addFeature(new_tuberia)
        self.capa_tuberias.commitChanges()

        # ===== Actualizar Lineas_ID en las DOS cámaras involucradas (ci y cf) =====
        # Nota: nuevo_id_camara es siempre igual a ci o a cf, no hace falta
        # una tercera llamada.
        self.actualizar_lineas_id(ci, nuevo_id_tuberia, 'añadir')
        self.actualizar_lineas_id(cf, nuevo_id_tuberia, 'añadir')

        # Desactivar herramienta
        self.iface.mapCanvas().unsetMapTool(self.tool_seleccion)
        self.tool_seleccion = None
        self.modo_edicion = False

        mensaje = f"=== TUBERIA AÑADIDA ===\n\n"
        mensaje += f"📌 Nueva camara: ID_O={nuevo_id_camara}\n"
        mensaje += f"   📍 X={round(punto.x(), 3)}, Y={round(punto.y(), 3)}\n"
        mensaje += f"   📐 Z={round(cota_nueva, 3)}\n\n"
        mensaje += f"📌 Nueva tuberia: ID_O={nuevo_id_tuberia}\n"
        mensaje += f"   Ci={ci} → Cf={cf}\n"
        mensaje += f"   Longitud: {round(longitud, 3)} m\n"
        mensaje += f"   Pendiente: {round(pendiente, 3)}%\n"
        mensaje += f"   Direccion: {dir_flujo}"

        QMessageBox.information(
            self.iface.mainWindow(),
            'Tuberia Añadida',
            mensaje
        )

    # ============================================================
    # TAB 2: UNIR CAMARAS EXISTENTES
    # ============================================================
    def unir_camaras(self, tuberias_id, camaras_id, ci_str, cf_str,
                     ci_es_ci, id_tub_sugerido):
        """Unir dos camaras existentes con una nueva tuberia"""

        self.capa_tuberias = QgsProject.instance().mapLayer(tuberias_id)
        self.capa_camaras = QgsProject.instance().mapLayer(camaras_id)

        if not self.capa_tuberias or not self.capa_camaras:
            QMessageBox.warning(self.iface.mainWindow(), 'Error',
                                'No se encontraron las capas')
            return

        try:
            ci = int(ci_str)
            cf = int(cf_str)
        except Exception:
            QMessageBox.warning(self.iface.mainWindow(), 'Error',
                                'Selecciona IDs de camaras validos')
            return

        if ci == cf:
            QMessageBox.warning(self.iface.mainWindow(), 'Error',
                                'La camara de inicio y final no pueden ser iguales')
            return

        # Obtener geometrias de las camaras (por ID_O)
        punto_ci = None
        punto_cf = None
        cota_ci = None
        cota_cf = None

        for feature in self.capa_camaras.getFeatures():
            id_o = feature.attribute('ID_O')
            if id_o == ci:
                geom = feature.geometry()
                if geom:
                    punto_ci = geom.asPoint()
                    cota_ci = feature.attribute('Z') or 0.0
            if id_o == cf:
                geom = feature.geometry()
                if geom:
                    punto_cf = geom.asPoint()
                    cota_cf = feature.attribute('Z') or 0.0

        if punto_ci is None or punto_cf is None:
            QMessageBox.warning(self.iface.mainWindow(), 'Error',
                                'No se encontraron las camaras seleccionadas')
            return

        # Determinar direccion segun seleccion del usuario
        if ci_es_ci:
            punto_inicio = punto_ci
            punto_fin = punto_cf
            ci_final = ci
            cf_final = cf
            cota_inicio = cota_ci
            cota_fin = cota_cf
        else:
            punto_inicio = punto_cf
            punto_fin = punto_ci
            ci_final = cf
            cf_final = ci
            cota_inicio = cota_cf
            cota_fin = cota_ci

        # Obtener nuevo ID para la tuberia
        nuevo_id = self.obtener_nuevo_id(self.capa_tuberias, id_tub_sugerido)

        # Crear geometria de la linea
        linea = QgsLineString([
            QgsPoint(punto_inicio.x(), punto_inicio.y()),
            QgsPoint(punto_fin.x(), punto_fin.y())
        ])
        geom = QgsGeometry(linea)

        longitud = geom.length()

        pendiente = 0.0
        if cota_inicio is not None and cota_fin is not None and longitud > 0:
            pendiente = (cota_inicio - cota_fin) / longitud * 100

        if punto_fin.x() > punto_inicio.x():
            dir_flujo = '->'
        elif punto_fin.x() < punto_inicio.x():
            dir_flujo = '<-'
        else:
            dir_flujo = '->' if punto_fin.y() > punto_inicio.y() else '<-'

        # Crear feature
        self.capa_tuberias.startEditing()
        new_feature = QgsFeature(self.capa_tuberias.fields())
        new_feature.setGeometry(geom)

        campos_tuberia = {}
        for field in self.capa_tuberias.fields():
            campos_tuberia[field.name()] = None

        campos_tuberia['ID_O'] = nuevo_id
        campos_tuberia['Ci'] = ci_final
        campos_tuberia['Cf'] = cf_final
        campos_tuberia['Xi'] = round(punto_inicio.x(), 3)
        campos_tuberia['Yi'] = round(punto_inicio.y(), 3)
        campos_tuberia['Zi'] = round(cota_inicio, 3)
        campos_tuberia['Xf'] = round(punto_fin.x(), 3)
        campos_tuberia['Yf'] = round(punto_fin.y(), 3)
        campos_tuberia['Zf'] = round(cota_fin, 3)
        campos_tuberia['L'] = round(longitud, 3)
        campos_tuberia['S'] = round(pendiente, 3)
        campos_tuberia['dir'] = dir_flujo
        campos_tuberia['cab_ata'] = ''

        new_feature.setAttributes(
            [campos_tuberia[f.name()] for f in self.capa_tuberias.fields()]
        )
        self.capa_tuberias.addFeature(new_feature)
        self.capa_tuberias.commitChanges()

        # Actualizar Lineas_ID de las camaras (por ID_O)
        self.actualizar_lineas_id(ci_final, nuevo_id, 'añadir')
        self.actualizar_lineas_id(cf_final, nuevo_id, 'añadir')

        mensaje = f"=== CAMARAS UNIDAS ===\n\n"
        mensaje += f"📌 Nueva tuberia: ID_O={nuevo_id}\n"
        mensaje += f"   Ci={ci_final} → Cf={cf_final}\n"
        mensaje += f"   Longitud: {round(longitud, 3)} m\n"
        mensaje += f"   Pendiente: {round(pendiente, 3)}%\n"
        mensaje += f"   Direccion: {dir_flujo}\n\n"
        mensaje += f"✅ Lineas_ID actualizadas en ambas camaras"

        QMessageBox.information(
            self.iface.mainWindow(),
            'Camaras Unidas',
            mensaje
        )