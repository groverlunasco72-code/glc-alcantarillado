# -*- coding: utf-8 -*-
from qgis.core import (
    QgsProject, QgsVectorLayer, QgsFeature, 
    QgsGeometry, QgsPointXY, QgsField,
    QgsWkbTypes, QgsLineString
)
from qgis.PyQt.QtCore import Qt, QVariant
from qgis.PyQt.QtWidgets import (
    QMessageBox, QDialog, QVBoxLayout, QLabel, 
    QPushButton, QComboBox, QProgressBar
)

class Acumulados:
    def __init__(self, iface):
        self.iface = iface
        self.capa_tuberias = None
        self.capa_camaras = None
        self.debug = False
    
    def mostrar_dialogo(self):
        dialog = QDialog(self.iface.mainWindow())
        dialog.setWindowTitle('GLC - Calcular Longitudes Acumuladas')
        dialog.setMinimumWidth(500)
        
        layout = QVBoxLayout()
        
        label_titulo = QLabel('<b>Calcular Longitudes Acumuladas</b>')
        label_titulo.setStyleSheet('font-size: 12pt;')
        layout.addWidget(label_titulo)
        
        label_info = QLabel(
            'Calcula las longitudes acumuladas usando la cámara final.\n\n'
            '📌 La cámara final se detecta automáticamente con fin = 1\n\n'
            '📌 Regla principal:\n'
            '   • Una tuberia pertenece a la red si Cf == id_camara_comando\n'
            '   • Si cab_ata="Arranque" → es cabeza, sumar L y terminar\n'
            '   • Si cab_ata="" → seguir hacia su Ci\n\n'
            '📌 Campos actualizados: Lt, La'
        )
        label_info.setWordWrap(True)
        layout.addWidget(label_info)
        
        layout.addWidget(QLabel('-' * 40))
        
        # Capa de tuberias
        layout.addWidget(QLabel('Seleccionar capa GLC_Tuberias:'))
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
        layout.addWidget(combo_tuberias)
        
        # Capa de camaras
        layout.addWidget(QLabel('Seleccionar capa de Camaras:'))
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
        layout.addWidget(combo_camaras)
        
        layout.addWidget(QLabel('-' * 40))
        
        # Mostrar la cámara final detectada
        self.label_camara_final = QLabel('🔍 Buscando cámara final...')
        self.label_camara_final.setStyleSheet('background-color: #e3f2fd; padding: 8px; border-radius: 4px;')
        layout.addWidget(self.label_camara_final)
        
        layout.addWidget(QLabel('-' * 40))
        
        # Barra de progreso
        self.progress = QProgressBar()
        layout.addWidget(self.progress)
        
        btn_calcular = QPushButton('Calcular Acumulados')
        btn_calcular.setStyleSheet('background-color: #4CAF50; color: white; font-weight: bold;')
        btn_calcular.clicked.connect(lambda: self.calcular(
            dialog,
            combo_tuberias.currentData(),
            combo_camaras.currentData()
        ))
        layout.addWidget(btn_calcular)
        
        dialog.setLayout(layout)
        
        # Buscar automáticamente al mostrar el diálogo
        self.buscar_camara_final(combo_camaras.currentData())
        
        dialog.exec_()
    
    def buscar_camara_final(self, camaras_id):
        """Buscar la cámara final (fin = 1) en la capa de cámaras"""
        layer = QgsProject.instance().mapLayer(camaras_id)
        
        if not layer:
            self.label_camara_final.setText('❌ No se encontró la capa de cámaras')
            self.label_camara_final.setStyleSheet('background-color: #ffcdd2; padding: 8px; border-radius: 4px;')
            return None
        
        idx_fin = layer.fields().indexFromName('fin')
        if idx_fin == -1:
            self.label_camara_final.setText('⚠️ La capa no tiene el campo "fin". Usa "Asignar Cámara Final" primero.')
            self.label_camara_final.setStyleSheet('background-color: #fff3e0; padding: 8px; border-radius: 4px;')
            return None
        
        camara_final = None
        for feature in layer.getFeatures():
            if feature.attribute('fin') == 1:
                camara_final = feature
                break
        
        if camara_final:
            id_o = camara_final.attribute('ID_O')
            geom = camara_final.geometry()
            if geom:
                punto = geom.asPoint()
                self.label_camara_final.setText(
                    f'✅ Cámara final: ID_O={id_o} (X: {punto.x():.2f}, Y: {punto.y():.2f})'
                )
                self.label_camara_final.setStyleSheet('background-color: #c8e6c9; padding: 8px; border-radius: 4px;')
            else:
                self.label_camara_final.setText(f'✅ Cámara final: ID_O={id_o}')
                self.label_camara_final.setStyleSheet('background-color: #c8e6c9; padding: 8px; border-radius: 4px;')
            return id_o
        else:
            self.label_camara_final.setText('❌ No hay cámara con fin = 1. Usa "Asignar Cámara Final" primero.')
            self.label_camara_final.setStyleSheet('background-color: #ffcdd2; padding: 8px; border-radius: 4px;')
            return None
    
    def calcular(self, dialog, tuberias_id, camaras_id):
        """Calcula longitudes acumuladas usando orden topológico (desde cabeceras)"""
        
        self.capa_tuberias = QgsProject.instance().mapLayer(tuberias_id)
        self.capa_camaras = QgsProject.instance().mapLayer(camaras_id)
        
        if not self.capa_tuberias or not self.capa_camaras:
            QMessageBox.warning(self.iface.mainWindow(), 'Error', 'No se encontraron las capas')
            return
        
        # Verificar campos
        for campo in ['ID_O', 'Ci', 'Cf', 'L', 'cab_ata']:
            if self.capa_tuberias.fields().indexFromName(campo) == -1:
                QMessageBox.warning(
                    self.iface.mainWindow(),
                    'Error',
                    f'La capa de tuberias no tiene el campo "{campo}"'
                )
                return
        
        for campo in ['ID_O', 'Lineas_ID', 'fin']:
            if self.capa_camaras.fields().indexFromName(campo) == -1:
                QMessageBox.warning(
                    self.iface.mainWindow(),
                    'Error',
                    f'La capa de camaras no tiene el campo "{campo}"'
                )
                return
        
        # Buscar cámara final
        id_final = self.buscar_camara_final(camaras_id)
        if id_final is None:
            QMessageBox.warning(
                self.iface.mainWindow(),
                'Error',
                'No se encontró una cámara final.\n'
                'Usa el módulo "Asignar Cámara Final" primero.'
            )
            return
        
        # Agregar campos
        if self.capa_tuberias.fields().indexFromName('Lt') == -1:
            self.capa_tuberias.dataProvider().addAttributes([QgsField('Lt', QVariant.Double)])
            self.capa_tuberias.updateFields()
        
        if self.capa_tuberias.fields().indexFromName('La') == -1:
            self.capa_tuberias.dataProvider().addAttributes([QgsField('La', QVariant.Double)])
            self.capa_tuberias.updateFields()
        
        self.progress.setValue(10)
        
        # ============================================
        # PASO 1: Construir diccionarios
        # ============================================
        
        tuberias_dict = {}
        for feature in self.capa_tuberias.getFeatures():
            id_o = feature.attribute('ID_O')
            if id_o is None:
                continue
            
            tuberias_dict[id_o] = {
                'id_o': id_o,
                'ci': feature.attribute('Ci'),
                'cf': feature.attribute('Cf'),
                'l': feature.attribute('L') or 0.0,
                'cab_ata': feature.attribute('cab_ata') or '',
                'feature': feature,
                'la': 0.0,
                'lt': 0.0,
                'procesado': False
            }
        
        self.progress.setValue(20)
        
        # ============================================
        # PASO 2: Orden topológico (Kahn) - igual que en diseño
        # ============================================
        
        # Construir grafo de dependencias
        dependencias = {}
        for id_o, data in tuberias_dict.items():
            ci = data['ci']
            if ci is not None:
                dependencias[id_o] = []
                # Buscar todas las tuberías que llegan a esta cámara (Cf = ci)
                for id_t, d in tuberias_dict.items():
                    if d['cf'] == ci and id_t != id_o:
                        dependencias[id_o].append(id_t)
            else:
                dependencias[id_o] = []
        
        # Identificar cabeceras (cab_ata = Arranque o sin dependencias)
        cabeceras = []
        for id_o, data in tuberias_dict.items():
            if data['cab_ata'] == 'Arranque':
                cabeceras.append(id_o)
            elif not dependencias.get(id_o, []):
                cabeceras.append(id_o)
        
        if not cabeceras:
            QMessageBox.warning(
                self.iface.mainWindow(),
                'Error',
                'No se encontraron tuberías con cab_ata="Arranque"'
            )
            return
        
        self.progress.setValue(30)
        
        # Orden topológico (Kahn)
        orden = []
        cola = list(set(cabeceras))
        procesados = set()
        
        while cola:
            id_actual = cola.pop(0)
            if id_actual in procesados:
                continue
            procesados.add(id_actual)
            orden.append(id_actual)
            
            # Buscar tuberías que tienen como Ci al Cf de esta
            cf_actual = tuberias_dict[id_actual]['cf']
            for id_o, data in tuberias_dict.items():
                if id_o not in procesados and data['ci'] == cf_actual:
                    # Verificar si todas sus dependencias ya están procesadas
                    dependencias_pendientes = [d for d in dependencias.get(id_o, []) if d not in procesados]
                    if not dependencias_pendientes:
                        cola.append(id_o)
        
        # Agregar las que no se procesaron (por si acaso)
        for id_o in tuberias_dict.keys():
            if id_o not in orden:
                if self.debug:
                    print(f"⚠️ Tubería {id_o} no procesada en orden topológico")
                orden.append(id_o)
        
        self.progress.setValue(40)
        
        if self.debug:
            print(f"\n📌 Orden topológico ({len(orden)} tuberías):")
            for i, id_o in enumerate(orden[:20]):
                print(f"   {i+1}. {id_o}")
        
        # ============================================
        # PASO 3: Procesar en orden topológico
        # ============================================
        
        # Diccionario para acumular sumas por cámara
        sumas_por_camara = {}
        
        # Inicializar sumas para todas las cámaras
        for id_o, data in tuberias_dict.items():
            ci = data['ci']
            if ci is not None:
                if ci not in sumas_por_camara:
                    sumas_por_camara[ci] = 0.0
        
        self.progress.setValue(50)
        
        total = len(orden)
        for i, id_tuberia in enumerate(orden):
            data = tuberias_dict[id_tuberia]
            
            # ===== SI ES ARRANQUE =====
            if data['cab_ata'] == 'Arranque':
                data['lt'] = 0.0
                data['la'] = data['l']
                data['procesado'] = True
                
                # Agregar esta tubería a la suma de su Cf (para que las siguientes la sumen)
                cf = data['cf']
                if cf in sumas_por_camara:
                    sumas_por_camara[cf] += data['la']
                
                continue
            
            # ===== SI ES VACIO (tubería normal) =====
            ci = data['ci']
            
            # Obtener la suma que llega a esta cámara
            sum_lt = sumas_por_camara.get(ci, 0.0)
            
            data['lt'] = sum_lt
            data['la'] = data['l'] + sum_lt
            data['procesado'] = True
            
            # Agregar esta tubería a la suma de su Cf (para que las siguientes la sumen)
            cf = data['cf']
            if cf in sumas_por_camara:
                sumas_por_camara[cf] += data['la']
            
            # Actualizar progreso
            progreso = 50 + (i / total) * 40
            self.progress.setValue(int(progreso))
        
        self.progress.setValue(90)
        
        # ============================================
        # PASO 4: Actualizar campos en la capa
        # ============================================
        
        self.capa_tuberias.startEditing()
        idx_lt = self.capa_tuberias.fields().indexFromName('Lt')
        idx_la = self.capa_tuberias.fields().indexFromName('La')
        
        for id_o, data in tuberias_dict.items():
            feature = data['feature']
            
            # Si no fue procesada, asignar valores por defecto
            if not data['procesado']:
                data['lt'] = 0.0
                data['la'] = data['l']
            
            self.capa_tuberias.changeAttributeValue(feature.id(), idx_lt, round(data['lt'], 3))
            self.capa_tuberias.changeAttributeValue(feature.id(), idx_la, round(data['la'], 3))
        
        self.capa_tuberias.commitChanges()
        
        self.progress.setValue(100)
        
        # ============================================
        # PASO 5: Mostrar resumen
        # ============================================
        
        procesadas = sum(1 for d in tuberias_dict.values() if d['procesado'])
        
        mensaje = (
            f'✅ CÁLCULO COMPLETADO\n\n'
            f'📊 Método: Orden topológico (Kahn) desde cabeceras\n'
            f'📊 Tuberías procesadas: {procesadas} de {len(tuberias_dict)}\n'
            f'📊 Cámara final: ID_O={id_final}\n\n'
            f'📌 Campos actualizados:\n'
            f'  • Lt (Longitud tributaria)\n'
            f'  • La (Longitud acumulada)'
        )
        
        QMessageBox.information(
            self.iface.mainWindow(),
            'Acumulados Calculados',
            mensaje
        )
        
        dialog.accept()