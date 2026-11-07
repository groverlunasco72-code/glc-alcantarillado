# -*- coding: utf-8 -*-
from qgis.core import (
    QgsProject, QgsVectorLayer, QgsFeature, 
    QgsGeometry, QgsPointXY, QgsField,
    QgsWkbTypes, QgsLineString
)
from qgis.PyQt.QtCore import Qt, QVariant
from qgis.PyQt.QtWidgets import (
    QMessageBox, QDialog, QVBoxLayout, QLabel, 
    QPushButton, QComboBox, QProgressBar, QSpinBox,
    QTabWidget, QWidget, QHBoxLayout, QLineEdit,
    QGroupBox, QRadioButton
)

class Renumerar:
    def __init__(self, iface):
        self.iface = iface
        self.capa_tuberias = None
        self.capa_camaras = None
        self.camaras_visitadas = set()
        self.contador = 1
        self.debug = False
    
    def mostrar_dialogo(self):
        dialog = QDialog(self.iface.mainWindow())
        dialog.setWindowTitle('GLC - Renumerar Red')
        dialog.setMinimumWidth(750)
        dialog.setMinimumHeight(550)
        
        layout = QVBoxLayout()
        
        label_titulo = QLabel('<b>Renumerar Red de Alcantarillado</b>')
        label_titulo.setStyleSheet('font-size: 14pt; font-weight: bold;')
        layout.addWidget(label_titulo)
        
        # ===== TABS =====
        tabs = QTabWidget()
        
        # ---------- TAB 1: RENUMERAR TUBERIAS ----------
        tab_tuberias = QWidget()
        layout_tub = QVBoxLayout()
        
        label_tub_info = QLabel(
            'Renumera las tuberias siguiendo el flujo de la red.\n'
            'Se selecciona la camara final y se recorre hacia atras.\n\n'
            '📌 Actualiza: ID_O en tuberias (orden de recorrido)\n'
            '📌 Actualiza: Lineas_ID en camaras\n'
            '⚠️ Ci y Cf NO se modifican (son IDs de camaras)'
        )
        label_tub_info.setWordWrap(True)
        layout_tub.addWidget(label_tub_info)
        
        layout_tub.addWidget(QLabel('-' * 40))
        
        # Seleccionar capas
        layout_tub.addWidget(QLabel('Seleccionar capa GLC_Tuberias:'))
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
        layout_tub.addWidget(combo_tuberias)
        
        layout_tub.addWidget(QLabel('Seleccionar capa de Camaras:'))
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
        layout_tub.addWidget(combo_camaras)
        
        layout_tub.addWidget(QLabel('-' * 40))
        
        # Seleccionar camara final
        layout_tub.addWidget(QLabel('Seleccionar la camara final (ID_O):'))
        combo_final_tub = QComboBox()
        combo_final_tub.setEditable(True)
        combo_final_tub.addItem('-- Seleccionar --')
        combo_camaras.currentIndexChanged.connect(lambda: self.cargar_camaras_final(combo_camaras, combo_final_tub))
        layout_tub.addWidget(combo_final_tub)
        
        layout_tub.addWidget(QLabel('-' * 40))
        
        # Configuracion de numeracion
        group_tub = QGroupBox('Configuracion de numeracion')
        group_layout = QVBoxLayout()
        
        hbox_inicio = QHBoxLayout()
        hbox_inicio.addWidget(QLabel('Comenzar desde:'))
        spin_inicio_tub = QSpinBox()
        spin_inicio_tub.setRange(1, 999999)
        spin_inicio_tub.setValue(1)
        hbox_inicio.addWidget(spin_inicio_tub)
        group_layout.addLayout(hbox_inicio)
        
        hbox_paso = QHBoxLayout()
        hbox_paso.addWidget(QLabel('Paso:'))
        spin_paso_tub = QSpinBox()
        spin_paso_tub.setRange(1, 100)
        spin_paso_tub.setValue(1)
        hbox_paso.addWidget(spin_paso_tub)
        group_layout.addLayout(hbox_paso)
        
        radio_asc_tub = QRadioButton('Ascendente (1, 2, 3...)')
        radio_asc_tub.setChecked(True)
        radio_desc_tub = QRadioButton('Descendente (N, N-1, N-2...)')
        group_layout.addWidget(radio_asc_tub)
        group_layout.addWidget(radio_desc_tub)
        
        group_tub.setLayout(group_layout)
        layout_tub.addWidget(group_tub)
        
        layout_tub.addWidget(QLabel('-' * 40))
        
        # Barra de progreso
        progress_tub = QProgressBar()
        layout_tub.addWidget(progress_tub)
        
        btn_renumerar_tub = QPushButton('Renumerar Tuberias (por red)')
        btn_renumerar_tub.setStyleSheet('background-color: #4CAF50; color: white; font-weight: bold;')
        btn_renumerar_tub.clicked.connect(lambda: self.renumerar_tuberias_por_red(
            dialog,
            combo_tuberias.currentData(),
            combo_camaras.currentData(),
            combo_final_tub.currentText(),
            spin_inicio_tub.value(),
            spin_paso_tub.value(),
            radio_asc_tub.isChecked(),
            progress_tub
        ))
        layout_tub.addWidget(btn_renumerar_tub)
        
        tab_tuberias.setLayout(layout_tub)
        tabs.addTab(tab_tuberias, '1. Renumerar Tuberias')
        
        # ---------- TAB 2: RENUMERAR CAMARAS ----------
        tab_camaras = QWidget()
        layout_cam = QVBoxLayout()
        
        label_cam_info = QLabel(
            'Renumera las camaras siguiendo el flujo de la red.\n'
            'Se selecciona la camara final y se recorre hacia atras.\n\n'
            '📌 Actualiza: ID_O en camaras (orden de recorrido)\n'
            '📌 Actualiza: Ci y Cf en tuberias\n'
            '⚠️ Lineas_ID en camaras NO se modifica'
        )
        label_cam_info.setWordWrap(True)
        layout_cam.addWidget(label_cam_info)
        
        layout_cam.addWidget(QLabel('-' * 40))
        
        # Seleccionar capas
        layout_cam.addWidget(QLabel('Seleccionar capa GLC_Tuberias:'))
        combo_tuberias2 = QComboBox()
        for layer in QgsProject.instance().mapLayers().values():
            if isinstance(layer, QgsVectorLayer):
                if layer.geometryType() == QgsWkbTypes.LineGeometry:
                    if 'GLC_Tuberias' in layer.name():
                        combo_tuberias2.addItem(layer.name(), layer.id())
        if combo_tuberias2.count() == 0:
            for layer in QgsProject.instance().mapLayers().values():
                if isinstance(layer, QgsVectorLayer):
                    if layer.geometryType() == QgsWkbTypes.LineGeometry:
                        combo_tuberias2.addItem(layer.name(), layer.id())
        layout_cam.addWidget(combo_tuberias2)
        
        layout_cam.addWidget(QLabel('Seleccionar capa de Camaras:'))
        combo_camaras2 = QComboBox()
        for layer in QgsProject.instance().mapLayers().values():
            if isinstance(layer, QgsVectorLayer):
                if layer.geometryType() == QgsWkbTypes.PointGeometry:
                    if 'GLC_Camaras' in layer.name():
                        combo_camaras2.addItem(layer.name(), layer.id())
        if combo_camaras2.count() == 0:
            for layer in QgsProject.instance().mapLayers().values():
                if isinstance(layer, QgsVectorLayer):
                    if layer.geometryType() == QgsWkbTypes.PointGeometry:
                        combo_camaras2.addItem(layer.name(), layer.id())
        layout_cam.addWidget(combo_camaras2)
        
        layout_cam.addWidget(QLabel('-' * 40))
        
        # Seleccionar camara final
        layout_cam.addWidget(QLabel('Seleccionar la camara final (ID_O):'))
        combo_final_cam = QComboBox()
        combo_final_cam.setEditable(True)
        combo_final_cam.addItem('-- Seleccionar --')
        combo_camaras2.currentIndexChanged.connect(lambda: self.cargar_camaras_final(combo_camaras2, combo_final_cam))
        layout_cam.addWidget(combo_final_cam)
        
        layout_cam.addWidget(QLabel('-' * 40))
        
        # Configuracion de numeracion
        group_cam = QGroupBox('Configuracion de numeracion')
        group_layout_cam = QVBoxLayout()
        
        hbox_inicio_cam = QHBoxLayout()
        hbox_inicio_cam.addWidget(QLabel('Comenzar desde:'))
        spin_inicio_cam = QSpinBox()
        spin_inicio_cam.setRange(1, 999999)
        spin_inicio_cam.setValue(1)
        hbox_inicio_cam.addWidget(spin_inicio_cam)
        group_layout_cam.addLayout(hbox_inicio_cam)
        
        hbox_paso_cam = QHBoxLayout()
        hbox_paso_cam.addWidget(QLabel('Paso:'))
        spin_paso_cam = QSpinBox()
        spin_paso_cam.setRange(1, 100)
        spin_paso_cam.setValue(1)
        hbox_paso_cam.addWidget(spin_paso_cam)
        group_layout_cam.addLayout(hbox_paso_cam)
        
        radio_asc_cam = QRadioButton('Ascendente (1, 2, 3...)')
        radio_asc_cam.setChecked(True)
        radio_desc_cam = QRadioButton('Descendente (N, N-1, N-2...)')
        group_layout_cam.addWidget(radio_asc_cam)
        group_layout_cam.addWidget(radio_desc_cam)
        
        group_cam.setLayout(group_layout_cam)
        layout_cam.addWidget(group_cam)
        
        layout_cam.addWidget(QLabel('-' * 40))
        
        # Barra de progreso
        progress_cam = QProgressBar()
        layout_cam.addWidget(progress_cam)
        
        btn_renumerar_cam = QPushButton('Renumerar Camaras (por red)')
        btn_renumerar_cam.setStyleSheet('background-color: #4CAF50; color: white; font-weight: bold;')
        btn_renumerar_cam.clicked.connect(lambda: self.renumerar_camaras_por_red(
            dialog,
            combo_tuberias2.currentData(),
            combo_camaras2.currentData(),
            combo_final_cam.currentText(),
            spin_inicio_cam.value(),
            spin_paso_cam.value(),
            radio_asc_cam.isChecked(),
            progress_cam
        ))
        layout_cam.addWidget(btn_renumerar_cam)
        
        tab_camaras.setLayout(layout_cam)
        tabs.addTab(tab_camaras, '2. Renumerar Camaras')
        
        # ---------- TAB 3: RENUMERAR MANUAL ----------
        tab_manual = QWidget()
        layout_man = QVBoxLayout()
        
        label_man_info = QLabel(
            'Renumera UNA tuberia o camara especifica y actualiza todos los rastros.\n'
            'Verifica que el nuevo ID no exista antes de asignarlo.'
        )
        label_man_info.setWordWrap(True)
        layout_man.addWidget(label_man_info)
        
        layout_man.addWidget(QLabel('-' * 40))
        
        # Seleccionar tipo
        layout_man.addWidget(QLabel('Seleccionar tipo:'))
        combo_tipo = QComboBox()
        combo_tipo.addItem('Tuberia', 'tuberia')
        combo_tipo.addItem('Camara', 'camara')
        layout_man.addWidget(combo_tipo)
        
        # Seleccionar capa
        layout_man.addWidget(QLabel('Seleccionar capa:'))
        combo_capa_man = QComboBox()
        layout_man.addWidget(combo_capa_man)
        
        # Cargar capas segun tipo
        combo_tipo.currentIndexChanged.connect(lambda: self.cargar_capas_manual(combo_tipo, combo_capa_man))
        self.cargar_capas_manual(combo_tipo, combo_capa_man)
        
        layout_man.addWidget(QLabel('-' * 40))
        
        # ID antiguo y nuevo
        hbox_antiguo = QHBoxLayout()
        hbox_antiguo.addWidget(QLabel('ID antiguo:'))
        txt_antiguo = QLineEdit()
        txt_antiguo.setPlaceholderText('Ej: 5')
        hbox_antiguo.addWidget(txt_antiguo)
        layout_man.addLayout(hbox_antiguo)
        
        hbox_nuevo = QHBoxLayout()
        hbox_nuevo.addWidget(QLabel('ID nuevo:'))
        txt_nuevo = QLineEdit()
        txt_nuevo.setPlaceholderText('Ej: 10')
        hbox_nuevo.addWidget(txt_nuevo)
        layout_man.addLayout(hbox_nuevo)
        
        layout_man.addWidget(QLabel('-' * 40))
        
        btn_renumerar_man = QPushButton('Renumerar Manualmente')
        btn_renumerar_man.setStyleSheet('background-color: #FF9800; color: white; font-weight: bold;')
        btn_renumerar_man.clicked.connect(lambda: self.renumerar_manual(
            dialog,
            combo_tipo.currentData(),
            combo_capa_man.currentData(),
            txt_antiguo.text(),
            txt_nuevo.text()
        ))
        layout_man.addWidget(btn_renumerar_man)
        
        tab_manual.setLayout(layout_man)
        tabs.addTab(tab_manual, '3. Renumerar Manual')
        
        layout.addWidget(tabs)
        
        # Boton cerrar
        btn_cerrar = QPushButton('Cerrar')
        btn_cerrar.setStyleSheet('background-color: #f44336; color: white;')
        btn_cerrar.clicked.connect(dialog.accept)
        layout.addWidget(btn_cerrar)
        
        dialog.setLayout(layout)
        dialog.exec_()
    
    def cargar_camaras_final(self, combo_camaras, combo_final):
        """Cargar IDs de camaras para seleccionar la camara final"""
        combo_final.clear()
        combo_final.addItem('-- Seleccionar --')
        
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
                combo_final.addItem(str(id_o))
    
    def cargar_capas_manual(self, combo_tipo, combo_capa):
        """Cargar capas segun el tipo seleccionado"""
        combo_capa.clear()
        tipo = combo_tipo.currentData()
        
        if tipo == 'tuberia':
            for layer in QgsProject.instance().mapLayers().values():
                if isinstance(layer, QgsVectorLayer):
                    if layer.geometryType() == QgsWkbTypes.LineGeometry:
                        if 'GLC_Tuberias' in layer.name():
                            combo_capa.addItem(layer.name(), layer.id())
            if combo_capa.count() == 0:
                for layer in QgsProject.instance().mapLayers().values():
                    if isinstance(layer, QgsVectorLayer):
                        if layer.geometryType() == QgsWkbTypes.LineGeometry:
                            combo_capa.addItem(layer.name(), layer.id())
        else:  # camara
            for layer in QgsProject.instance().mapLayers().values():
                if isinstance(layer, QgsVectorLayer):
                    if layer.geometryType() == QgsWkbTypes.PointGeometry:
                        if 'GLC_Camaras' in layer.name():
                            combo_capa.addItem(layer.name(), layer.id())
            if combo_capa.count() == 0:
                for layer in QgsProject.instance().mapLayers().values():
                    if isinstance(layer, QgsVectorLayer):
                        if layer.geometryType() == QgsWkbTypes.PointGeometry:
                            combo_capa.addItem(layer.name(), layer.id())
    
    def verificar_id_existe(self, layer, id_o):
        """Verificar si un ID_O ya existe en la capa"""
        idx = layer.fields().indexFromName('ID_O')
        if idx == -1:
            return False
        for feature in layer.getFeatures():
            if feature.attribute('ID_O') == id_o:
                return True
        return False
    
    # ===== RENUMERAR TUBERIAS POR RED =====
    def renumerar_tuberias_por_red(self, dialog, tuberias_id, camaras_id, final_id_str, inicio, paso, ascendente, progress):
        """Renumerar tuberias siguiendo el recorrido de la red"""
        
        self.capa_tuberias = QgsProject.instance().mapLayer(tuberias_id)
        self.capa_camaras = QgsProject.instance().mapLayer(camaras_id)
        
        if not self.capa_tuberias or not self.capa_camaras:
            QMessageBox.warning(self.iface.mainWindow(), 'Error', 'No se encontraron las capas')
            return
        
        try:
            id_final = int(final_id_str)
        except:
            QMessageBox.warning(self.iface.mainWindow(), 'Error', 'Selecciona un ID_O de camara final valido')
            return
        
        # Verificar campos
        if self.capa_tuberias.fields().indexFromName('ID_O') == -1:
            QMessageBox.warning(self.iface.mainWindow(), 'Error', 'La capa de tuberias no tiene campo "ID_O"')
            return
        
        if self.capa_camaras.fields().indexFromName('Lineas_ID') == -1:
            QMessageBox.warning(self.iface.mainWindow(), 'Error', 'La capa de camaras no tiene campo "Lineas_ID"')
            return
        
        progress.setValue(10)
        
        # Construir diccionarios
        self.construir_diccionarios()
        
        if id_final not in self.camaras_dict:
            QMessageBox.warning(self.iface.mainWindow(), 'Error', f'No se encontro la camara ID_O={id_final}')
            return
        
        progress.setValue(20)
        
        # ===== RECORRER LA RED DESDE LA CAMARA FINAL =====
        self.camaras_visitadas = set()
        self.contador = inicio
        orden_recorrido = []  # Lista de IDs en orden de recorrido
        
        self.recorrer_red_tuberias(id_final, orden_recorrido)
        
        progress.setValue(50)
        
        if not orden_recorrido:
            QMessageBox.warning(self.iface.mainWindow(), 'Error', 'No se encontraron tuberias en la red')
            return
        
        # Invertir si es descendente
        if not ascendente:
            orden_recorrido.reverse()
        
        progress.setValue(60)
        
        # ===== CREAR MAPEO DE IDs =====
        mapeo_ids = {}
        contador = inicio
        for id_viejo in orden_recorrido:
            mapeo_ids[id_viejo] = contador
            contador += paso
        
        progress.setValue(70)
        
        # ===== ACTUALIZAR TUBERIAS (SOLO ID_O) =====
        self.capa_tuberias.startEditing()
        idx_id_o = self.capa_tuberias.fields().indexFromName('ID_O')
        
        for feature in self.capa_tuberias.getFeatures():
            id_viejo = feature.attribute('ID_O')
            if id_viejo in mapeo_ids:
                self.capa_tuberias.changeAttributeValue(feature.id(), idx_id_o, mapeo_ids[id_viejo])
        
        self.capa_tuberias.commitChanges()
        
        progress.setValue(85)
        
        # ===== ACTUALIZAR CAMARAS (Lineas_ID) =====
        self.capa_camaras.startEditing()
        idx_lineas_id = self.capa_camaras.fields().indexFromName('Lineas_ID')
        
        for feature in self.capa_camaras.getFeatures():
            lineas_id_str = feature.attribute('Lineas_ID') or ''
            if lineas_id_str:
                try:
                    parts = lineas_id_str.split(',')
                    nuevos_ids = []
                    for p in parts:
                        p_clean = p.strip()
                        if p_clean and p_clean.isdigit():
                            id_old = int(p_clean)
                            if id_old in mapeo_ids:
                                nuevos_ids.append(str(mapeo_ids[id_old]))
                            else:
                                nuevos_ids.append(str(id_old))
                    nueva_lineas_id = ', '.join(nuevos_ids)
                    self.capa_camaras.changeAttributeValue(feature.id(), idx_lineas_id, nueva_lineas_id)
                except:
                    pass
        
        self.capa_camaras.commitChanges()
        
        progress.setValue(100)
        
        dialog.accept()
        
        QMessageBox.information(
            self.iface.mainWindow(),
            'Renumeracion Completada',
            f'✅ Tuberias renumeradas: {len(mapeo_ids)}\n'
            f'📊 Desde: {inicio}\n'
            f'📊 Paso: {paso}\n'
            f'📊 Orden: {"Ascendente" if ascendente else "Descendente"}\n'
            f'📊 Camara final: {id_final}\n\n'
            f'⚠️ Ci y Cf NO se modificaron (son IDs de camaras)'
        )
    
    def recorrer_red_tuberias(self, id_camara, orden_recorrido):
        """Recorrer la red desde una camara y guardar el orden de tuberias"""
        
        if id_camara not in self.camaras_dict:
            return
        
        if id_camara in self.camaras_visitadas:
            return
        self.camaras_visitadas.add(id_camara)
        
        camara = self.camaras_dict[id_camara]
        
        # Para cada tuberia conectada a esta camara
        for id_tuberia in camara['lineas']:
            if id_tuberia not in self.tuberias_dict:
                continue
            
            tuberia = self.tuberias_dict[id_tuberia]
            
            # Solo considerar tuberias que LLEGAN a la camara (Cf == id_camara)
            if tuberia['cf'] != id_camara:
                continue
            
            # Agregar al orden de recorrido
            if id_tuberia not in orden_recorrido:
                orden_recorrido.append(id_tuberia)
            
            # Seguir hacia su Ci (camara de inicio)
            id_camara_inicio = tuberia['ci']
            if id_camara_inicio is not None and id_camara_inicio != -1:
                self.recorrer_red_tuberias(id_camara_inicio, orden_recorrido)
    
    # ===== RENUMERAR CAMARAS POR RED =====
    def renumerar_camaras_por_red(self, dialog, tuberias_id, camaras_id, final_id_str, inicio, paso, ascendente, progress):
        """Renumerar camaras siguiendo el recorrido de la red"""
        
        self.capa_tuberias = QgsProject.instance().mapLayer(tuberias_id)
        self.capa_camaras = QgsProject.instance().mapLayer(camaras_id)
        
        if not self.capa_tuberias or not self.capa_camaras:
            QMessageBox.warning(self.iface.mainWindow(), 'Error', 'No se encontraron las capas')
            return
        
        try:
            id_final = int(final_id_str)
        except:
            QMessageBox.warning(self.iface.mainWindow(), 'Error', 'Selecciona un ID_O de camara final valido')
            return
        
        # Verificar campos
        if self.capa_camaras.fields().indexFromName('ID_O') == -1:
            QMessageBox.warning(self.iface.mainWindow(), 'Error', 'La capa de camaras no tiene campo "ID_O"')
            return
        
        for campo in ['Ci', 'Cf']:
            if self.capa_tuberias.fields().indexFromName(campo) == -1:
                QMessageBox.warning(
                    self.iface.mainWindow(),
                    'Error',
                    f'La capa de tuberias no tiene el campo "{campo}"'
                )
                return
        
        progress.setValue(10)
        
        # Construir diccionarios
        self.construir_diccionarios()
        
        if id_final not in self.camaras_dict:
            QMessageBox.warning(self.iface.mainWindow(), 'Error', f'No se encontro la camara ID_O={id_final}')
            return
        
        progress.setValue(20)
        
        # ===== RECORRER LA RED DESDE LA CAMARA FINAL =====
        self.camaras_visitadas = set()
        orden_recorrido = []  # Lista de IDs de camaras en orden de recorrido
        
        self.recorrer_red_camaras(id_final, orden_recorrido)
        
        progress.setValue(50)
        
        if not orden_recorrido:
            QMessageBox.warning(self.iface.mainWindow(), 'Error', 'No se encontraron camaras en la red')
            return
        
        # Invertir si es descendente
        if not ascendente:
            orden_recorrido.reverse()
        
        progress.setValue(60)
        
        # ===== CREAR MAPEO DE IDs =====
        mapeo_ids = {}
        contador = inicio
        for id_viejo in orden_recorrido:
            mapeo_ids[id_viejo] = contador
            contador += paso
        
        progress.setValue(70)
        
        # ===== ACTUALIZAR CAMARAS (SOLO ID_O) =====
        self.capa_camaras.startEditing()
        idx_id_o = self.capa_camaras.fields().indexFromName('ID_O')
        
        for feature in self.capa_camaras.getFeatures():
            id_viejo = feature.attribute('ID_O')
            if id_viejo in mapeo_ids:
                self.capa_camaras.changeAttributeValue(feature.id(), idx_id_o, mapeo_ids[id_viejo])
        
        self.capa_camaras.commitChanges()
        
        progress.setValue(85)
        
        # ===== ACTUALIZAR TUBERIAS (Ci y Cf) =====
        self.capa_tuberias.startEditing()
        idx_ci = self.capa_tuberias.fields().indexFromName('Ci')
        idx_cf = self.capa_tuberias.fields().indexFromName('Cf')
        
        for feature in self.capa_tuberias.getFeatures():
            ci_actual = feature.attribute('Ci')
            if ci_actual in mapeo_ids:
                self.capa_tuberias.changeAttributeValue(feature.id(), idx_ci, mapeo_ids[ci_actual])
            
            cf_actual = feature.attribute('Cf')
            if cf_actual in mapeo_ids:
                self.capa_tuberias.changeAttributeValue(feature.id(), idx_cf, mapeo_ids[cf_actual])
        
        self.capa_tuberias.commitChanges()
        
        progress.setValue(100)
        
        dialog.accept()
        
        QMessageBox.information(
            self.iface.mainWindow(),
            'Renumeracion Completada',
            f'✅ Camaras renumeradas: {len(mapeo_ids)}\n'
            f'📊 Desde: {inicio}\n'
            f'📊 Paso: {paso}\n'
            f'📊 Orden: {"Ascendente" if ascendente else "Descendente"}\n'
            f'📊 Camara final: {id_final}\n\n'
            f'⚠️ Lineas_ID en camaras NO se modifico'
        )
    
    def recorrer_red_camaras(self, id_camara, orden_recorrido):
        """Recorrer la red desde una camara y guardar el orden de camaras"""
        
        if id_camara not in self.camaras_dict:
            return
        
        if id_camara in self.camaras_visitadas:
            return
        self.camaras_visitadas.add(id_camara)
        
        # Agregar la camara al orden
        if id_camara not in orden_recorrido:
            orden_recorrido.append(id_camara)
        
        camara = self.camaras_dict[id_camara]
        
        # Para cada tuberia conectada a esta camara
        for id_tuberia in camara['lineas']:
            if id_tuberia not in self.tuberias_dict:
                continue
            
            tuberia = self.tuberias_dict[id_tuberia]
            
            # Solo considerar tuberias que LLEGAN a la camara (Cf == id_camara)
            if tuberia['cf'] != id_camara:
                continue
            
            # Seguir hacia su Ci (camara de inicio)
            id_camara_inicio = tuberia['ci']
            if id_camara_inicio is not None and id_camara_inicio != -1:
                self.recorrer_red_camaras(id_camara_inicio, orden_recorrido)
    
    # ===== FUNCIONES DE CONSTRUCCION DE DICCIONARIOS =====
    def construir_diccionarios(self):
        """Construir diccionarios para acceso rapido"""
        
        self.tuberias_dict = {}
        for feature in self.capa_tuberias.getFeatures():
            id_o = feature.attribute('ID_O')
            if id_o is None:
                continue
            
            self.tuberias_dict[id_o] = {
                'id_o': id_o,
                'ci': feature.attribute('Ci'),
                'cf': feature.attribute('Cf'),
                'feature': feature
            }
        
        self.camaras_dict = {}
        for feature in self.capa_camaras.getFeatures():
            id_o = feature.attribute('ID_O')
            if id_o is None:
                continue
            
            lineas_id_str = feature.attribute('Lineas_ID') or ''
            lineas_list = []
            if lineas_id_str:
                try:
                    parts = str(lineas_id_str).split(',')
                    for p in parts:
                        p_clean = p.strip()
                        if p_clean and p_clean.isdigit():
                            lineas_list.append(int(p_clean))
                except:
                    pass
            
            self.camaras_dict[id_o] = {
                'id_o': id_o,
                'lineas': lineas_list,
                'feature': feature
            }
    
    # ===== RENUMERAR MANUAL =====
    def renumerar_manual(self, dialog, tipo, capa_id, id_antiguo_str, id_nuevo_str):
        """Renumerar UNA tuberia o camara manualmente"""
        
        if not id_antiguo_str or not id_nuevo_str:
            QMessageBox.warning(self.iface.mainWindow(), 'Error', 'Ingresa ID antiguo y nuevo')
            return
        
        try:
            id_antiguo = int(id_antiguo_str)
            id_nuevo = int(id_nuevo_str)
        except:
            QMessageBox.warning(self.iface.mainWindow(), 'Error', 'Los IDs deben ser numeros enteros')
            return
        
        if id_antiguo == id_nuevo:
            QMessageBox.warning(self.iface.mainWindow(), 'Error', 'El ID antiguo y nuevo son iguales')
            return
        
        capa = QgsProject.instance().mapLayer(capa_id)
        if not capa:
            QMessageBox.warning(self.iface.mainWindow(), 'Error', 'No se encontro la capa')
            return
        
        # Verificar que el ID antiguo existe
        idx_id_o = capa.fields().indexFromName('ID_O')
        if idx_id_o == -1:
            QMessageBox.warning(self.iface.mainWindow(), 'Error', 'La capa no tiene campo ID_O')
            return
        
        feature_antigua = None
        for feature in capa.getFeatures():
            if feature.attribute('ID_O') == id_antiguo:
                feature_antigua = feature
                break
        
        if feature_antigua is None:
            QMessageBox.warning(self.iface.mainWindow(), 'Error', f'No se encontro ID_O={id_antiguo}')
            return
        
        # Verificar que el ID nuevo no exista
        if self.verificar_id_existe(capa, id_nuevo):
            QMessageBox.warning(
                self.iface.mainWindow(),
                'Error',
                f'El ID_O={id_nuevo} ya existe en la capa.\nElige otro numero.'
            )
            return
        
        # Crear mapeo
        mapeo = {id_antiguo: id_nuevo}
        
        # ===== ACTUALIZAR LA CAPA SELECCIONADA =====
        capa.start