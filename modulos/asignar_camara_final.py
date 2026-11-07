# -*- coding: utf-8 -*-
"""
Módulo: Asignar Cámara Final

Marca una cámara como final de la red (campo 'fin' = 1).

CORRECCIONES:
    - Reemplazado QgsField('fin', QVariant.Int) por helper _campo() sin
      DeprecationWarning.
    - Manejo de excepciones de map tool más robusto.
    - Verificación de que el campo 'fin' existe antes de aplicar.

Compatible con QGIS 3.x y 4.x.
"""

from qgis.core import (
    QgsProject, QgsVectorLayer, QgsFeature,
    QgsGeometry, QgsField, QgsWkbTypes,
    QgsFeatureRequest
)
from qgis.PyQt.QtCore import QVariant
from qgis.PyQt.QtWidgets import (
    QMessageBox, QDialog, QVBoxLayout, QLabel,
    QPushButton, QComboBox, QCheckBox
)
from qgis.gui import QgsMapToolEmitPoint


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


class AsignarCamaraFinal:
    def __init__(self, iface):
        self.iface = iface
        self.capa_camaras = None
        self.tool_seleccion = None
        self.camara_seleccionada = None
        self.camara_id = None

    def mostrar_dialogo(self):
        dialog = QDialog(self.iface.mainWindow())
        dialog.setWindowTitle('GLC - Asignar Cámara Final')
        dialog.setMinimumWidth(500)

        layout = QVBoxLayout()

        layout.addWidget(QLabel('<b>Asignar Cámara Final de la Red</b>'))
        layout.addWidget(QLabel('-' * 50))

        # Seleccionar capa de cámaras
        layout.addWidget(QLabel('Seleccionar capa GLC_Camaras:'))
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

        layout.addWidget(QLabel('-' * 50))

        # Botón para seleccionar cámara
        self.btn_seleccionar = QPushButton('🎯 Seleccionar Cámara Final (clic en el mapa)')
        self.btn_seleccionar.setStyleSheet(
            'background-color: #FF9800; color: white; font-weight: bold; padding: 8px;'
        )
        self.btn_seleccionar.clicked.connect(
            lambda: self.activar_seleccion(dialog, combo_camaras.currentData())
        )
        layout.addWidget(self.btn_seleccionar)

        # Mostrar cámara seleccionada
        self.label_seleccion = QLabel('Cámara seleccionada: Ninguna')
        self.label_seleccion.setStyleSheet(
            'background-color: #e3f2fd; padding: 8px; border-radius: 4px;'
        )
        layout.addWidget(self.label_seleccion)

        # Opción para limpiar la cámara final
        self.check_limpiar = QCheckBox('Limpiar cámara final (eliminar marca)')
        layout.addWidget(self.check_limpiar)

        layout.addWidget(QLabel('-' * 50))

        # Botón para aplicar
        btn_aplicar = QPushButton('✅ Aplicar Cámara Final')
        btn_aplicar.setStyleSheet(
            'background-color: #4CAF50; color: white; font-weight: bold; padding: 10px;'
        )
        btn_aplicar.clicked.connect(
            lambda: self.aplicar_camara_final(dialog, combo_camaras.currentData())
        )
        layout.addWidget(btn_aplicar)

        layout.addWidget(QLabel('-' * 50))

        # Instrucciones
        instrucciones = QLabel(
            '📌 INSTRUCCIONES:\n'
            '1. Selecciona la capa GLC_Camaras\n'
            '2. Haz clic en "Seleccionar Cámara Final"\n'
            '3. Haz clic en la cámara en el mapa\n'
            '4. Presiona "Aplicar Cámara Final"\n\n'
            '💡 La cámara final será marcada con "1" en la columna "fin"'
        )
        instrucciones.setWordWrap(True)
        instrucciones.setStyleSheet(
            'background-color: #f5f5f5; padding: 10px; border-radius: 5px;'
        )
        layout.addWidget(instrucciones)

        dialog.setLayout(layout)
        dialog.exec_()

    def activar_seleccion(self, dialog, layer_id):
        layer = QgsProject.instance().mapLayer(layer_id)

        if not layer:
            QMessageBox.warning(self.iface.mainWindow(), 'Error',
                                'No se encontró la capa')
            return

        self.capa_camaras = layer

        # Desactivar cualquier tool previo
        if self.tool_seleccion:
            try:
                self.iface.mapCanvas().unsetMapTool(self.tool_seleccion)
            except Exception:
                pass
            self.tool_seleccion = None

        # Crear herramienta de selección con QgsMapToolEmitPoint
        self.tool_seleccion = QgsMapToolEmitPoint(self.iface.mapCanvas())
        self.tool_seleccion.canvasClicked.connect(self.on_canvas_click)

        self.iface.mapCanvas().setMapTool(self.tool_seleccion)

        # Cambiar mensaje del botón
        self.btn_seleccionar.setText('🔴 Seleccionando... haz clic en una cámara')
        self.btn_seleccionar.setStyleSheet(
            'background-color: #f44336; color: white; font-weight: bold; padding: 8px;'
        )
        self.btn_seleccionar.setEnabled(False)

        QMessageBox.information(
            self.iface.mainWindow(),
            'Seleccionar Cámara',
            'Haz clic en la cámara que será la final de la red'
        )

    def on_canvas_click(self, point):
        """Callback cuando se hace clic en el mapa"""
        if not self.capa_camaras:
            return

        # Buscar la cámara más cercana al punto clic
        # Convertir tolerancia (10 px en unidades del mapa)
        tolerancia_mapa = 10.0
        try:
            canvas = self.iface.mapCanvas()
            scale = canvas.mapSettings().scale()
            tolerancia_mapa = 10.0 * scale / 1000.0
        except Exception:
            tolerancia_mapa = 10.0

        feature_seleccionado = None
        dist_minima = tolerancia_mapa

        punto_geom = QgsGeometry.fromPointXY(point)

        for feature in self.capa_camaras.getFeatures():
            geom = feature.geometry()
            if not geom or geom.isEmpty():
                continue

            try:
                dist = geom.distance(punto_geom)
            except Exception:
                continue

            if dist < dist_minima:
                dist_minima = dist
                feature_seleccionado = feature

        if feature_seleccionado:
            self.on_camara_seleccionada(feature_seleccionado)
        else:
            QMessageBox.warning(
                self.iface.mainWindow(),
                'Error',
                'No se encontró ninguna cámara cerca del punto. '
                'Intenta hacer clic más cerca de una cámara.'
            )

    def on_camara_seleccionada(self, feature):
        """Callback cuando se selecciona una cámara"""
        if not feature:
            return

        self.camara_seleccionada = feature
        self.camara_id = feature.id()
        id_o = feature.attribute('ID_O') or f'ID_{self.camara_id}'

        # Mostrar información de la cámara seleccionada
        geom = feature.geometry()
        if geom:
            punto = geom.asPoint()
            self.label_seleccion.setText(
                f'✅ Cámara seleccionada: {id_o} '
                f'(X: {punto.x():.2f}, Y: {punto.y():.2f})'
            )
        else:
            self.label_seleccion.setText(f'✅ Cámara seleccionada: {id_o}')

        self.label_seleccion.setStyleSheet(
            'background-color: #c8e6c9; padding: 8px; border-radius: 4px;'
        )

        # Restaurar botón
        self.btn_seleccionar.setText('🎯 Seleccionar Cámara Final (clic en el mapa)')
        self.btn_seleccionar.setStyleSheet(
            'background-color: #FF9800; color: white; font-weight: bold; padding: 8px;'
        )
        self.btn_seleccionar.setEnabled(True)

        # Desactivar herramienta de selección
        if self.tool_seleccion:
            try:
                self.iface.mapCanvas().unsetMapTool(self.tool_seleccion)
            except Exception:
                pass
            self.tool_seleccion = None

    def aplicar_camara_final(self, dialog, layer_id):
        layer = QgsProject.instance().mapLayer(layer_id)

        if not layer:
            QMessageBox.warning(self.iface.mainWindow(), 'Error',
                                'No se encontró la capa')
            return

        # Verificar si existe el campo 'fin', si no crearlo
        if layer.fields().indexFromName('fin') == -1:
            reply = QMessageBox.question(
                self.iface.mainWindow(),
                'Crear Campo',
                'La capa no tiene el campo "fin". ¿Desea crearlo?',
                QMessageBox.Yes | QMessageBox.No
            )
            if reply == QMessageBox.Yes:
                layer.startEditing()
                layer.addAttribute(_campo('fin', 'int'))
                layer.commitChanges()
                layer.updateFields()  # ⭐ Refrescar campos
                QMessageBox.information(
                    self.iface.mainWindow(),
                    'Campo Creado',
                    'Se creó el campo "fin" en la capa'
                )
            else:
                return

        # Verificar si se va a limpiar
        if self.check_limpiar.isChecked():
            self.limpiar_camara_final(layer)
            self.check_limpiar.setChecked(False)
            self.label_seleccion.setText('Cámara seleccionada: Ninguna')
            self.label_seleccion.setStyleSheet(
                'background-color: #e3f2fd; padding: 8px; border-radius: 4px;'
            )
            QMessageBox.information(
                self.iface.mainWindow(),
                'Limpieza Completa',
                'Se eliminó la marca de cámara final de todas las cámaras'
            )
            return

        # Verificar si hay cámara seleccionada
        if self.camara_seleccionada is None:
            QMessageBox.warning(
                self.iface.mainWindow(),
                'Error',
                'Primero selecciona una cámara usando el botón '
                '"Seleccionar Cámara Final"'
            )
            return

        # Aplicar la cámara final
        self.asignar_camara_final(layer, self.camara_seleccionada)

        id_o = self.camara_seleccionada.attribute('ID_O') or f'ID_{self.camara_id}'
        QMessageBox.information(
            self.iface.mainWindow(),
            'Cámara Final Asignada',
            f'✅ Se asignó la cámara {id_o} como cámara final de la red'
        )

        # Limpiar selección
        self.camara_seleccionada = None
        self.camara_id = None
        self.label_seleccion.setText('Cámara seleccionada: Ninguna')
        self.label_seleccion.setStyleSheet(
            'background-color: #e3f2fd; padding: 8px; border-radius: 4px;'
        )

    def asignar_camara_final(self, layer, feature):
        """Asigna la cámara final marcando con 1 en el campo 'fin'"""
        idx_fin = layer.fields().indexFromName('fin')

        if idx_fin == -1:
            return

        # Primero limpiar todas las cámaras
        layer.startEditing()

        # Poner 0 en todas las cámaras
        for f in layer.getFeatures():
            layer.changeAttributeValue(f.id(), idx_fin, 0)

        # Poner 1 en la cámara seleccionada
        layer.changeAttributeValue(feature.id(), idx_fin, 1)

        layer.commitChanges()
        layer.triggerRepaint()

    def limpiar_camara_final(self, layer):
        """Elimina la marca de cámara final de todas las cámaras"""
        idx_fin = layer.fields().indexFromName('fin')

        if idx_fin == -1:
            return

        layer.startEditing()
        for f in layer.getFeatures():
            layer.changeAttributeValue(f.id(), idx_fin, 0)
        layer.commitChanges()
        layer.triggerRepaint()

    def desactivar(self):
        """Desactivar herramientas activas"""
        if self.tool_seleccion:
            try:
                self.iface.mapCanvas().unsetMapTool(self.tool_seleccion)
            except Exception:
                pass
            self.tool_seleccion = None