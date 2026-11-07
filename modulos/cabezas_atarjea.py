# -*- coding: utf-8 -*-
from qgis.core import (
    QgsProject, QgsVectorLayer, QgsFeature, 
    QgsGeometry, QgsPointXY, QgsField,
    QgsWkbTypes, QgsLineString
)
from qgis.PyQt.QtCore import Qt, QVariant
from qgis.PyQt.QtWidgets import (
    QMessageBox, QDialog, QVBoxLayout, QLabel, 
    QPushButton, QComboBox
)
from qgis.gui import QgsMapToolEmitPoint

class CabezasAtarjea:
    def __init__(self, iface):
        self.iface = iface
        self.capa_tuberias = None
        self.modo_edicion = False
        self.modo_asignacion = None
        self.tool_seleccion = None
    
    def mostrar_dialogo(self):
        dialog = QDialog(self.iface.mainWindow())
        dialog.setWindowTitle('GLC - Cabezas de Atarjea')
        dialog.setMinimumWidth(500)
        
        layout = QVBoxLayout()
        
        label_titulo = QLabel('<b>Cabezas de Atarjea</b>')
        label_titulo.setStyleSheet('font-size: 12pt;')
        layout.addWidget(label_titulo)
        
        label_info = QLabel('Asigna o quita cabezas de atarjea en las tuberias.\n'
                           'Una cabeza de atarjea marca el INICIO de la red.\n\n'
                           '💡 El campo "cab_ata" se crea automaticamente\n'
                           '💡 Valores: "Arranque" = cabeza de atarjea, vacio = normal')
        label_info.setWordWrap(True)
        layout.addWidget(label_info)
        
        layout.addWidget(QLabel('-' * 40))
        
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
        
        layout.addWidget(QLabel('-' * 40))
        
        btn_asignar = QPushButton('Marcar como ARRANQUE (Click en tuberia)')
        btn_asignar.setStyleSheet('background-color: #4CAF50; color: white; font-weight: bold;')
        btn_asignar.clicked.connect(lambda: self.activar_asignar(dialog, combo_tuberias.currentData()))
        layout.addWidget(btn_asignar)
        
        btn_quitar = QPushButton('Quitar ARRANQUE (Click en tuberia)')
        btn_quitar.setStyleSheet('background-color: #FF9800; color: white; font-weight: bold;')
        btn_quitar.clicked.connect(lambda: self.activar_quitar(dialog, combo_tuberias.currentData()))
        layout.addWidget(btn_quitar)
        
        btn_salir = QPushButton('Salir del Modo Edicion')
        btn_salir.setStyleSheet('background-color: #f44336; color: white;')
        btn_salir.clicked.connect(self.salir_edicion)
        layout.addWidget(btn_salir)
        
        layout.addWidget(QLabel('-' * 40))
        
        label_ayuda = QLabel(
            '📌 COMO FUNCIONA:\n'
            '1. Haz clic en "Marcar como ARRANQUE"\n'
            '2. Haz clic en una tuberia → escribe "Arranque" en cab_ata\n'
            '3. O "Quitar ARRANQUE" → deja el campo vacio\n'
            '4. Usa "Salir del Modo Edicion" para terminar\n\n'
            '📌 CAMPO: cab_ata ("Arranque" o vacio)'
        )
        label_ayuda.setWordWrap(True)
        label_ayuda.setStyleSheet('background-color: #f5f5f5; padding: 10px; border-radius: 5px;')
        layout.addWidget(label_ayuda)
        
        dialog.setLayout(layout)
        dialog.exec_()
    
    def activar_asignar(self, dialog, layer_id):
        self.activar_edicion(layer_id, 'asignar', dialog)
    
    def activar_quitar(self, dialog, layer_id):
        self.activar_edicion(layer_id, 'quitar', dialog)
    
    def activar_edicion(self, layer_id, modo, dialog):
        layer = QgsProject.instance().mapLayer(layer_id)
        
        if not layer:
            QMessageBox.warning(self.iface.mainWindow(), 'Error', 'No se encontro la capa')
            return
        
        self.capa_tuberias = layer
        
        if layer.fields().indexFromName('cab_ata') == -1:
            QMessageBox.warning(
                self.iface.mainWindow(),
                'Error',
                'La capa no tiene el campo "cab_ata"\n'
                'Regenera GLC_Tuberias para crearlo automaticamente'
            )
            return
        
        self.modo_edicion = True
        self.modo_asignacion = modo
        
        self.tool_seleccion = QgsMapToolEmitPoint(self.iface.mapCanvas())
        self.tool_seleccion.canvasClicked.connect(self.on_canvas_click)
        
        self.iface.mapCanvas().setMapTool(self.tool_seleccion)
        
        dialog.accept()
        
        mensaje = '🔹 Haz clic en cualquier tuberia para marcar ARRANQUE' if modo == 'asignar' else '🔹 Haz clic en cualquier tuberia para quitar ARRANQUE'
        
        QMessageBox.information(
            self.iface.mainWindow(),
            f'Modo {modo.upper()}',
            f'{mensaje}\n'
            '🔹 El campo "cab_ata" se actualizara\n'
            '🔹 Usa "Salir del Modo Edicion" para terminar'
        )
    
    def on_canvas_click(self, point):
        if not self.capa_tuberias or not self.modo_edicion:
            return
        
        tolerancia = 5.0
        feature_seleccionado = None
        dist_minima = tolerancia
        
        punto_geom = QgsGeometry.fromPointXY(point)
        
        for feature in self.capa_tuberias.getFeatures():
            geom = feature.geometry()
            if not geom or geom.isEmpty():
                continue
            
            dist = geom.distance(punto_geom)
            if dist < dist_minima:
                dist_minima = dist
                feature_seleccionado = feature
        
        if feature_seleccionado:
            if self.modo_asignacion == 'asignar':
                self.asignar_cabeza(feature_seleccionado)
            else:
                self.quitar_cabeza(feature_seleccionado)
        else:
            self.iface.messageBar().pushMessage(
                'Info',
                'No se encontro ninguna tuberia cerca del punto',
                level=1,
                duration=3
            )
    
    def asignar_cabeza(self, feature):
        idx = self.capa_tuberias.fields().indexFromName('cab_ata')
        
        self.capa_tuberias.startEditing()
        self.capa_tuberias.changeAttributeValue(feature.id(), idx, 'Arranque')
        self.capa_tuberias.commitChanges()
        
        self.capa_tuberias.triggerRepaint()
        
        id_o = feature.attribute('ID_O')
        self.iface.messageBar().pushMessage(
            'Cabeza Asignada',
            f'✅ Tuberia ID_O={id_o} marcada como ARRANQUE (cab_ata="Arranque")',
            level=0,
            duration=3
        )
    
    def quitar_cabeza(self, feature):
        idx = self.capa_tuberias.fields().indexFromName('cab_ata')
        
        self.capa_tuberias.startEditing()
        self.capa_tuberias.changeAttributeValue(feature.id(), idx, '')
        self.capa_tuberias.commitChanges()
        
        self.capa_tuberias.triggerRepaint()
        
        id_o = feature.attribute('ID_O')
        self.iface.messageBar().pushMessage(
            'Cabeza Quitada',
            f'✅ Tuberia ID_O={id_o} ya NO tiene ARRANQUE (cab_ata="")',
            level=0,
            duration=3
        )
    
    def salir_edicion(self):
        self.desactivar_edicion(mostrar_mensaje=True)
    
    def desactivar_edicion(self, mostrar_mensaje=False):
        if self.tool_seleccion:
            try:
                canvas = self.iface.mapCanvas()
                if canvas:
                    canvas.unsetMapTool(self.tool_seleccion)
            except:
                pass
            self.tool_seleccion = None
        
        self.modo_edicion = False
        self.modo_asignacion = None
        self.capa_tuberias = None
        
        if mostrar_mensaje:
            try:
                if self.iface.mainWindow():
                    QMessageBox.information(
                        self.iface.mainWindow(),
                        'Modo Desactivado',
                        '✅ Modo de edicion de cabezas de atarjea desactivado'
                    )
            except:
                pass