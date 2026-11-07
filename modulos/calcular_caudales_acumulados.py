# -*- coding: utf-8 -*-
from qgis.core import (
    QgsProject, QgsVectorLayer, QgsFeature, 
    QgsGeometry, QgsPointXY, QgsField,
    QgsWkbTypes, QgsLineString
)
from qgis.PyQt.QtCore import Qt, QVariant
from qgis.PyQt.QtWidgets import (
    QMessageBox, QDialog, QVBoxLayout, QLabel, 
    QPushButton, QComboBox, QProgressBar,
    QDoubleSpinBox, QGroupBox, QFormLayout, QCheckBox
)

class CalcularCaudalesAcumulados:
    def __init__(self, iface):
        self.iface = iface
        self.capa_tuberias = None
        self.capa_camaras = None
        self.debug = False
        self.caudal_minimo = 1.5
    
    def mostrar_dialogo(self):
        dialog = QDialog(self.iface.mainWindow())
        dialog.setWindowTitle('GLC - Calcular Caudales Acumulados')
        dialog.setMinimumWidth(550)
        
        layout = QVBoxLayout()
        
        label_titulo = QLabel('<b>Calcular Caudales Acumulados (qacu y qdise)</b>')
        label_titulo.setStyleSheet('font-size: 12pt;')
        layout.addWidget(label_titulo)
        
        label_info = QLabel(
            'Calcula los caudales acumulados usando el modelo de acumulados.\n\n'
            '📌 La cámara final se detecta automáticamente con fin = 1\n\n'
            '📌 Regla principal:\n'
            '   • qp se acumula desde cabeceras hacia el final\n'
            '   • qacu = qmaxh + qinf + qce + qp_propio + qp_acumulado\n'
            '   • qdise = max(qacu, caudal_mínimo)\n\n'
            '📌 Campos actualizados: qacu, qdise'
        )
        label_info.setWordWrap(True)
        layout.addWidget(label_info)
        
        layout.addWidget(QLabel('-' * 40))
        
        # Parámetros
        group_param = QGroupBox('Parámetros')
        form_param = QFormLayout()
        
        self.spin_caudal_min = QDoubleSpinBox()
        self.spin_caudal_min.setRange(0.1, 100.0)
        self.spin_caudal_min.setValue(self.caudal_minimo)
        self.spin_caudal_min.setSingleStep(0.1)
        self.spin_caudal_min.setDecimals(2)
        self.spin_caudal_min.setSuffix(' L/s')
        form_param.addRow('Caudal mínimo:', self.spin_caudal_min)
        
        self.chk_debug = QCheckBox('Mostrar depuración en consola')
        form_param.addRow('', self.chk_debug)
        
        group_param.setLayout(form_param)
        layout.addWidget(group_param)
        
        layout.addWidget(QLabel('-' * 40))
        
        # Capa de tuberías
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
        
        # Capa de cámaras
        layout.addWidget(QLabel('Seleccionar capa de Cámaras:'))
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
        
        btn_calcular = QPushButton('Calcular Caudales Acumulados')
        btn_calcular.setStyleSheet('background-color: #4CAF50; color: white; font-weight: bold;')
        btn_calcular.clicked.connect(lambda: self.calcular(
            dialog,
            combo_tuberias.currentData(),
            combo_camaras.currentData()
        ))
        layout.addWidget(btn_calcular)
        
        dialog.setLayout(layout)
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
        
        for feature in layer.getFeatures():
            if feature.attribute('fin') == 1:
                id_o = feature.attribute('ID_O')
                geom = feature.geometry()
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
        
        self.label_camara_final.setText('❌ No hay cámara con fin = 1. Usa "Asignar Cámara Final" primero.')
        self.label_camara_final.setStyleSheet('background-color: #ffcdd2; padding: 8px; border-radius: 4px;')
        return None
    
    def calcular(self, dialog, tuberias_id, camaras_id):
        """Calcula caudales acumulados usando orden topológico (desde cabeceras)"""
        
        self.caudal_minimo = self.spin_caudal_min.value()
        self.debug = self.chk_debug.isChecked()
        
        self.capa_tuberias = QgsProject.instance().mapLayer(tuberias_id)
        self.capa_camaras = QgsProject.instance().mapLayer(camaras_id)
        
        if not self.capa_tuberias or not self.capa_camaras:
            QMessageBox.warning(self.iface.mainWindow(), 'Error', 'No se encontraron las capas')
            return
        
        # Verificar campos
        for campo in ['ID_O', 'Ci', 'Cf', 'cab_ata', 'qmaxh', 'qinf', 'qce']:
            if self.capa_tuberias.fields().indexFromName(campo) == -1:
                QMessageBox.warning(self.iface.mainWindow(), 'Error', f'La capa no tiene el campo "{campo}"')
                return
        
        # Crear campos si no existen
        for campo in ['qp', 'qacu', 'qdise']:
            if self.capa_tuberias.fields().indexFromName(campo) == -1:
                self.capa_tuberias.dataProvider().addAttributes([QgsField(campo, QVariant.Double)])
                self.capa_tuberias.updateFields()
                if campo == 'qp':
                    self.capa_tuberias.startEditing()
                    idx = self.capa_tuberias.fields().indexFromName('qp')
                    for feature in self.capa_tuberias.getFeatures():
                        self.capa_tuberias.changeAttributeValue(feature.id(), idx, 0.0)
                    self.capa_tuberias.commitChanges()
        
        for campo in ['ID_O', 'Lineas_ID', 'fin']:
            if self.capa_camaras.fields().indexFromName(campo) == -1:
                QMessageBox.warning(self.iface.mainWindow(), 'Error', f'La capa de cámaras no tiene el campo "{campo}"')
                return
        
        id_final = self.buscar_camara_final(camaras_id)
        if id_final is None:
            QMessageBox.warning(self.iface.mainWindow(), 'Error', 'No se encontró una cámara final.')
            return
        
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
                'cab_ata': feature.attribute('cab_ata') or '',
                'feature': feature,
                'qmaxh': feature.attribute('qmaxh') or 0.0,
                'qinf': feature.attribute('qinf') or 0.0,
                'qce': feature.attribute('qce') or 0.0,
                'qp': feature.attribute('qp') or 0.0,
                'qacu': 0.0,
                'qdise': 0.0,
                'procesado': False
            }
        
        self.progress.setValue(20)
        
        # ============================================
        # PASO 2: Orden topológico
        # ============================================
        
        dependencias = {}
        for id_o, data in tuberias_dict.items():
            ci = data['ci']
            if ci is not None:
                dependencias[id_o] = []
                for id_t, d in tuberias_dict.items():
                    if d['cf'] == ci and id_t != id_o:
                        dependencias[id_o].append(id_t)
            else:
                dependencias[id_o] = []
        
        cabeceras = []
        for id_o, data in tuberias_dict.items():
            if data['cab_ata'] == 'Arranque':
                cabeceras.append(id_o)
            elif not dependencias.get(id_o, []):
                cabeceras.append(id_o)
        
        if not cabeceras:
            QMessageBox.warning(self.iface.mainWindow(), 'Error', 'No se encontraron tuberías con cab_ata="Arranque"')
            return
        
        self.progress.setValue(30)
        
        orden = []
        cola = list(set(cabeceras))
        procesados = set()
        
        while cola:
            id_actual = cola.pop(0)
            if id_actual in procesados:
                continue
            procesados.add(id_actual)
            orden.append(id_actual)
            
            cf_actual = tuberias_dict[id_actual]['cf']
            for id_o, data in tuberias_dict.items():
                if id_o not in procesados and data['ci'] == cf_actual:
                    dependencias_pendientes = [d for d in dependencias.get(id_o, []) if d not in procesados]
                    if not dependencias_pendientes:
                        cola.append(id_o)
        
        for id_o in tuberias_dict.keys():
            if id_o not in orden:
                orden.append(id_o)
        
        self.progress.setValue(40)
        
        if self.debug:
            print("\n" + "="*70)
            print("ORDEN TOPOLÓGICO:")
            for i, id_o in enumerate(orden):
                data = tuberias_dict[id_o]
                print(f"  {i+1}. ID_O={id_o} | Ci={data['ci']} | Cf={data['cf']} | qp={data['qp']}")
            print("="*70 + "\n")
        
        # ============================================
        # PASO 3: Procesar en orden topológico
        # ============================================
        
        # Diccionario para acumular qp por cámara
        qp_por_camara = {}
        
        # Inicializar todas las cámaras con 0
        for id_o, data in tuberias_dict.items():
            ci = data['ci']
            cf = data['cf']
            if ci is not None and ci not in qp_por_camara:
                qp_por_camara[ci] = 0.0
            if cf is not None and cf not in qp_por_camara:
                qp_por_camara[cf] = 0.0
        
        self.progress.setValue(50)
        
        if self.debug:
            print("PROCESANDO TUBERÍAS:")
            print("  ID_O | qp_propio | qp_acumulado | qacu | qdise | qp_a_trasladar")
            print("-"*70)
        
        total = len(orden)
        for i, id_tuberia in enumerate(orden):
            data = tuberias_dict[id_tuberia]
            
            # Obtener qp acumulado que llega a esta tubería (desde su Ci)
            ci = data['ci']
            qp_acumulado = qp_por_camara.get(ci, 0.0)
            
            # ===== CALCULAR qacu =====
            # qacu = qmaxh + qinf + qce + qp_propio + qp_acumulado
            qacu = data['qmaxh'] + data['qinf'] + data['qce'] + data['qp'] + qp_acumulado
            data['qacu'] = qacu
            data['qdise'] = max(qacu, self.caudal_minimo)
            data['procesado'] = True
            
            # ===== ACUMULAR TODO EL QP HACIA ABAJO =====
            # Se debe trasladar: qp_propio + qp_acumulado (TODO el caudal que llega)
            qp_a_trasladar = data['qp'] + qp_acumulado
            
            cf = data['cf']
            if cf is not None:
                if cf not in qp_por_camara:
                    qp_por_camara[cf] = 0.0
                qp_por_camara[cf] += qp_a_trasladar
                
                if self.debug:
                    print(f"  {id_tuberia:>5} | {data['qp']:>9.2f} | {qp_acumulado:>12.2f} | {qacu:>7.2f} | {data['qdise']:>7.2f} | {qp_a_trasladar:>12.2f}")
                    print(f"         → qp_por_camara[{cf}] = {qp_por_camara[cf]:.2f}")
            else:
                if self.debug:
                    print(f"  {id_tuberia:>5} | {data['qp']:>9.2f} | {qp_acumulado:>12.2f} | {qacu:>7.2f} | {data['qdise']:>7.2f} | {qp_a_trasladar:>12.2f}")
            
            # Actualizar progreso
            progreso = 50 + (i / total) * 40
            self.progress.setValue(int(progreso))
        
        if self.debug:
            print("\n" + "="*70)
            print("RESUMEN FINAL qp_por_camara:")
            for camara, valor in sorted(qp_por_camara.items()):
                print(f"  Cámara {camara}: {valor:.2f}")
            print("="*70 + "\n")
        
        self.progress.setValue(90)
        
        # ============================================
        # PASO 4: Actualizar campos
        # ============================================
        
        self.capa_tuberias.startEditing()
        idx_qacu = self.capa_tuberias.fields().indexFromName('qacu')
        idx_qdise = self.capa_tuberias.fields().indexFromName('qdise')
        
        for id_o, data in tuberias_dict.items():
            feature = data['feature']
            if not data['procesado']:
                data['qacu'] = data['qmaxh'] + data['qinf'] + data['qce'] + data['qp']
                data['qdise'] = max(data['qacu'], self.caudal_minimo)
            
            self.capa_tuberias.changeAttributeValue(feature.id(), idx_qacu, round(data['qacu'], 3))
            self.capa_tuberias.changeAttributeValue(feature.id(), idx_qdise, round(data['qdise'], 3))
        
        self.capa_tuberias.commitChanges()
        self.progress.setValue(100)
        
        # ============================================
        # PASO 5: Resumen
        # ============================================
        
        procesadas = 0
        qdise_max = 0
        qdise_min = float('inf')
        qdise_sum = 0
        qp_total = 0
        
        for data in tuberias_dict.values():
            if data['procesado']:
                procesadas += 1
                qdise = data['qdise']
                qdise_sum += qdise
                qdise_max = max(qdise_max, qdise)
                qdise_min = min(qdise_min, qdise)
                qp_total += data['qp']
        
        if qdise_min == float('inf'):
            qdise_min = 0
        
        mensaje = (
            f'✅ CÁLCULO COMPLETADO\n\n'
            f'📊 Tuberías procesadas: {procesadas} de {len(tuberias_dict)}\n'
            f'📊 Cámara final: ID_O={id_final}\n'
            f'📊 Caudal mínimo: {self.caudal_minimo:.2f} L/s\n'
            f'📊 qp total: {qp_total:.3f} L/s\n\n'
            f'📊 qdise:\n'
            f'  • Mínimo: {qdise_min:.3f} L/s\n'
            f'  • Máximo: {qdise_max:.3f} L/s\n'
            f'  • Suma: {qdise_sum:.3f} L/s'
        )
        
        QMessageBox.information(self.iface.mainWindow(), 'Caudales Acumulados Calculados', mensaje)
        dialog.accept()