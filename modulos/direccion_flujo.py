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

class DireccionFlujo:
    def __init__(self, iface):
        self.iface = iface
        self.capa_tuberias = None
        self.modo_edicion = False
        self.tool_seleccion = None
    
    def mostrar_dialogo(self):
        dialog = QDialog(self.iface.mainWindow())
        dialog.setWindowTitle('GLC - Direccion de Flujo')
        dialog.setMinimumWidth(500)
        
        layout = QVBoxLayout()
        
        label_titulo = QLabel('<b>Direccion de Flujo en Tuberias</b>')
        label_titulo.setStyleSheet('font-size: 12pt;')
        layout.addWidget(label_titulo)
        
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
        
        btn_cambiar = QPushButton('Cambiar Direccion (Click en tuberia)')
        btn_cambiar.setStyleSheet('background-color: #FF9800; color: white; font-weight: bold;')
        btn_cambiar.clicked.connect(lambda: self.activar_cambio_direccion(dialog, combo_tuberias.currentData()))
        layout.addWidget(btn_cambiar)
        
        btn_salir = QPushButton('Salir del Modo Edicion')
        btn_salir.setStyleSheet('background-color: #f44336; color: white;')
        btn_salir.clicked.connect(self.salir_edicion)
        layout.addWidget(btn_salir)
        
        layout.addWidget(QLabel('-' * 40))
        
        label_ayuda = QLabel(
            '📌 AL CAMBIAR DIRECCION SE ACTUALIZA:\n'
            '  - Ci ↔ Cf (camaras intercambiadas)\n'
            '  - Xi ↔ Xf, Yi ↔ Yf, Zi ↔ Zf\n'
            '  - dir: "->" ↔ "<-"\n'
            '  - S (pendiente recalculada)\n\n'
        )
        label_ayuda.setWordWrap(True)
        label_ayuda.setStyleSheet('background-color: #f5f5f5; padding: 10px; border-radius: 5px;')
        layout.addWidget(label_ayuda)
        
        dialog.setLayout(layout)
        dialog.exec_()
    
    def activar_cambio_direccion(self, dialog, layer_id):
        layer = QgsProject.instance().mapLayer(layer_id)
        
        if not layer:
            QMessageBox.warning(self.iface.mainWindow(), 'Error', 'No se encontro la capa')
            return
        
        self.capa_tuberias = layer
        
        # Verificar campos necesarios
        campos = ['dir', 'Ci', 'Cf', 'Zi', 'Zf', 'L', 'S', 'Xi', 'Yi', 'Xf', 'Yf']
        for campo in campos:
            if layer.fields().indexFromName(campo) == -1:
                QMessageBox.warning(
                    self.iface.mainWindow(),
                    'Error',
                    f'La capa no tiene el campo "{campo}"\nRegenera GLC_Tuberias'
                )
                return
        
        self.tool_seleccion = QgsMapToolEmitPoint(self.iface.mapCanvas())
        self.tool_seleccion.canvasClicked.connect(self.on_canvas_click)
        
        self.iface.mapCanvas().setMapTool(self.tool_seleccion)
        self.modo_edicion = True
        
        dialog.accept()
        
        QMessageBox.information(
            self.iface.mainWindow(),
            'Modo Cambio de Direccion',
            '🔹 Haz clic en cualquier tuberia para invertir su direccion\n'
            '🔹 Se intercambiaran Ci↔Cf, Xi↔Xf, Yi↔Yf, Zi↔Zf\n'
            '🔹 La pendiente se recalculara automaticamente\n'
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
            self.cambiar_direccion_feature(feature_seleccionado)
        else:
            self.iface.messageBar().pushMessage(
                'Info',
                'No se encontro ninguna tuberia cerca del punto',
                level=1,
                duration=3
            )
    
    def cambiar_direccion_feature(self, feature):
        if not self.capa_tuberias:
            return
        
        id_feature = feature.id()
        
        # Obtener direccion actual
        idx_dir = self.capa_tuberias.fields().indexFromName('dir')
        direccion_actual = feature.attribute('dir') or '->'
        
        # CAMBIO: usar -> y <-
        nueva_direccion = '<-' if direccion_actual == '->' else '->'
        
        # Invertir geometria
        geom = feature.geometry()
        if geom and not geom.isEmpty():
            # Obtener vertices y revertir
            puntos = []
            for vertex in geom.vertices():
                puntos.append(QgsPointXY(vertex))
            puntos.reverse()
            nueva_linea = QgsLineString(puntos)
            geom_invertida = QgsGeometry(nueva_linea)
            
            # Obtener nuevos puntos inicio/fin
            punto_inicio = puntos[0]
            punto_fin = puntos[-1]
            
            # Obtener indices de campos
            idx_ci = self.capa_tuberias.fields().indexFromName('Ci')
            idx_cf = self.capa_tuberias.fields().indexFromName('Cf')
            idx_zi = self.capa_tuberias.fields().indexFromName('Zi')
            idx_zf = self.capa_tuberias.fields().indexFromName('Zf')
            idx_xi = self.capa_tuberias.fields().indexFromName('Xi')
            idx_yi = self.capa_tuberias.fields().indexFromName('Yi')
            idx_xf = self.capa_tuberias.fields().indexFromName('Xf')
            idx_yf = self.capa_tuberias.fields().indexFromName('Yf')
            idx_s = self.capa_tuberias.fields().indexFromName('S')
            idx_l = self.capa_tuberias.fields().indexFromName('L')
            
            # Obtener valores actuales
            ci = feature.attribute('Ci')
            cf = feature.attribute('Cf')
            zi = feature.attribute('Zi')
            zf = feature.attribute('Zf')
            xi = feature.attribute('Xi')
            yi = feature.attribute('Yi')
            xf = feature.attribute('Xf')
            yf = feature.attribute('Yf')
            longitud = feature.attribute('L')
            
            # Intercambiar
            nuevo_ci = cf
            nuevo_cf = ci
            nuevo_zi = zf
            nuevo_zf = zi
            nuevo_xi = round(punto_inicio.x(), 3)
            nuevo_yi = round(punto_inicio.y(), 3)
            nuevo_xf = round(punto_fin.x(), 3)
            nuevo_yf = round(punto_fin.y(), 3)
            
            # Recalcular pendiente
            nueva_s = 0.0
            if nuevo_zi is not None and nuevo_zf is not None and longitud > 0:
                if nuevo_zi != -9999 and nuevo_zf != -9999:
                    nueva_s = (nuevo_zi - nuevo_zf) / longitud * 100
            
            # Editar la capa
            self.capa_tuberias.startEditing()
            
            # Actualizar geometria
            self.capa_tuberias.changeGeometry(id_feature, geom_invertida)
            
            # Actualizar atributos
            self.capa_tuberias.changeAttributeValue(id_feature, idx_dir, nueva_direccion)
            self.capa_tuberias.changeAttributeValue(id_feature, idx_ci, nuevo_ci if nuevo_ci is not None else -1)
            self.capa_tuberias.changeAttributeValue(id_feature, idx_cf, nuevo_cf if nuevo_cf is not None else -1)
            self.capa_tuberias.changeAttributeValue(id_feature, idx_zi, round(nuevo_zi, 3) if nuevo_zi is not None else -9999.0)
            self.capa_tuberias.changeAttributeValue(id_feature, idx_zf, round(nuevo_zf, 3) if nuevo_zf is not None else -9999.0)
            self.capa_tuberias.changeAttributeValue(id_feature, idx_xi, nuevo_xi)
            self.capa_tuberias.changeAttributeValue(id_feature, idx_yi, nuevo_yi)
            self.capa_tuberias.changeAttributeValue(id_feature, idx_xf, nuevo_xf)
            self.capa_tuberias.changeAttributeValue(id_feature, idx_yf, nuevo_yf)
            self.capa_tuberias.changeAttributeValue(id_feature, idx_s, round(nueva_s, 3))
            
            self.capa_tuberias.commitChanges()
            
            # Actualizar visualizacion
            self.capa_tuberias.triggerRepaint()
            
            id_o = feature.attribute('ID_O')
            self.iface.messageBar().pushMessage(
                'Direccion Cambiada',
                f'✅ Tuberia ID_O={id_o} invertida. Nuevo sentido: {nueva_direccion}',
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
        self.capa_tuberias = None
        
        if mostrar_mensaje:
            try:
                if self.iface.mainWindow():
                    QMessageBox.information(
                        self.iface.mainWindow(),
                        'Modo Desactivado',
                        '✅ Modo de edicion de direccion desactivado'
                    )
            except:
                pass