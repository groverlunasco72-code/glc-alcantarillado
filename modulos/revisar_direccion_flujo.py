# -*- coding: utf-8 -*-
from qgis.core import (
    QgsProject, QgsVectorLayer, QgsFeature,
    QgsGeometry, QgsPointXY, QgsField,
    QgsWkbTypes, QgsLineString
)
from qgis.PyQt.QtWidgets import (
    QMessageBox, QDialog, QVBoxLayout, QLabel,
    QPushButton, QComboBox, QProgressBar,
    QTextEdit, QApplication
)


class RevisarDireccionFlujo:
    def __init__(self, iface):
        self.iface = iface

    def mostrar_dialogo(self):
        dialog = QDialog(self.iface.mainWindow())
        dialog.setWindowTitle('GLC - Revisar Dirección de Flujo')
        dialog.setMinimumWidth(600)
        dialog.setMinimumHeight(400)

        layout = QVBoxLayout()

        layout.addWidget(QLabel('<b>Revisar Dirección de Flujo (Zi > Zf)</b>'))
        layout.addWidget(QLabel('Compara las cotas Z (Zi > Zf) y corrige si es necesario'))
        layout.addWidget(QLabel('-' * 50))

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

        self.btn_revisar = QPushButton('Revisar y Corregir')
        self.btn_revisar.clicked.connect(
            lambda: self.revisar(dialog, combo_tuberias.currentData())
        )
        layout.addWidget(self.btn_revisar)

        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        layout.addWidget(self.progress_bar)

        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setStyleSheet('font-family: monospace;')
        layout.addWidget(self.log_text)

        btn_cerrar = QPushButton('Cerrar')
        btn_cerrar.clicked.connect(dialog.accept)
        layout.addWidget(btn_cerrar)

        dialog.setLayout(layout)
        dialog.exec_()

    def revisar(self, dialog, layer_id):
        layer = QgsProject.instance().mapLayer(layer_id)
        
        if not layer:
            QMessageBox.warning(self.iface.mainWindow(), 'Error', 'No se encontró la capa')
            return

        # Verificar campos
        campos = ['Ci', 'Cf', 'Zi', 'Zf', 'Xi', 'Yi', 'Xf', 'Yf', 'dir', 'S']
        for campo in campos:
            if layer.fields().indexFromName(campo) == -1:
                QMessageBox.warning(self.iface.mainWindow(), 'Error', f'Falta el campo "{campo}"')
                return

        self.log_text.clear()
        self.btn_revisar.setEnabled(False)
        self.progress_bar.setVisible(True)

        features = list(layer.getFeatures())
        total = len(features)
        self.progress_bar.setMaximum(total)
        self.progress_bar.setValue(0)

        corregidas = 0
        layer.startEditing()

        self.log_text.append('=' * 60)
        self.log_text.append('REVISANDO DIRECCIÓN DE FLUJO (Zi > Zf)')
        self.log_text.append('=' * 60)

        for i, feature in enumerate(features):
            self.progress_bar.setValue(i + 1)
            QApplication.processEvents()

            id_o = feature.attribute('ID_O') or f'ID_{feature.id()}'
            
            zi = feature.attribute('Zi')
            zf = feature.attribute('Zf')

            # Saltar si no hay cotas válidas
            if zi is None or zf is None or zi == -9999 or zf == -9999:
                self.log_text.append(f'⚠️ {id_o}: Zi={zi}, Zf={zf} (sin cota)')
                continue

            # Si Zi > Zf, está bien (flujo descendente)
            if zi > zf:
                self.log_text.append(f'✅ {id_o}: Zi={zi:.3f} > Zf={zf:.3f} (OK)')
                continue

            # Si Zi < Zf, invertir (flujo ascendente, hay que corregir)
            if zi < zf:
                self.log_text.append(f'🔄 {id_o}: Zi={zi:.3f} < Zf={zf:.3f} (INVIRTIENDO)')
                
                # Invertir
                self.invertir(layer, feature)
                corregidas += 1
                self.log_text.append(f'   ✅ Corregido')

        # Aplicar cambios
        if corregidas > 0:
            layer.commitChanges()
            layer.triggerRepaint()
            self.log_text.append(f'\n✅ Se corrigieron {corregidas} tuberías')
            QMessageBox.information(self.iface.mainWindow(), 'Completado', f'Se corrigieron {corregidas} tuberías')
        else:
            layer.rollBack()
            self.log_text.append('\n✅ Todas las tuberías están correctas')
            QMessageBox.information(self.iface.mainWindow(), 'Completado', 'Todas las tuberías están correctas')

        self.progress_bar.setVisible(False)
        self.btn_revisar.setEnabled(True)

    def invertir(self, layer, feature):
        """Invierte la tubería: intercambia Ci↔Cf, Zi↔Zf, Xi↔Xf, Yi↔Yf y la flecha"""
        id_feature = feature.id()

        # Índices de campos
        idx_ci = layer.fields().indexFromName('Ci')
        idx_cf = layer.fields().indexFromName('Cf')
        idx_zi = layer.fields().indexFromName('Zi')
        idx_zf = layer.fields().indexFromName('Zf')
        idx_xi = layer.fields().indexFromName('Xi')
        idx_yi = layer.fields().indexFromName('Yi')
        idx_xf = layer.fields().indexFromName('Xf')
        idx_yf = layer.fields().indexFromName('Yf')
        idx_dir = layer.fields().indexFromName('dir')
        idx_s = layer.fields().indexFromName('S')

        # Valores actuales
        ci = feature.attribute('Ci')
        cf = feature.attribute('Cf')
        zi = feature.attribute('Zi')
        zf = feature.attribute('Zf')
        xi = feature.attribute('Xi')
        yi = feature.attribute('Yi')
        xf = feature.attribute('Xf')
        yf = feature.attribute('Yf')
        direccion = feature.attribute('dir') or '->'
        longitud = feature.attribute('L')

        # Intercambiar todos los valores
        layer.changeAttributeValue(id_feature, idx_ci, cf)
        layer.changeAttributeValue(id_feature, idx_cf, ci)
        layer.changeAttributeValue(id_feature, idx_zi, zf)
        layer.changeAttributeValue(id_feature, idx_zf, zi)
        layer.changeAttributeValue(id_feature, idx_xi, xf)
        layer.changeAttributeValue(id_feature, idx_yi, yf)
        layer.changeAttributeValue(id_feature, idx_xf, xi)
        layer.changeAttributeValue(id_feature, idx_yf, yi)
        layer.changeAttributeValue(id_feature, idx_dir, '<-' if direccion == '->' else '->')

        # Recalcular pendiente (ahora será positiva porque Zi > Zf)
        if zi is not None and zf is not None and longitud and longitud > 0:
            nueva_s = (zf - zi) / longitud * 100
            layer.changeAttributeValue(id_feature, idx_s, round(nueva_s, 3))

        # Invertir geometría
        geom = feature.geometry()
        if geom and not geom.isEmpty():
            puntos = []
            for vertex in geom.vertices():
                puntos.append(QgsPointXY(vertex))
            puntos.reverse()
            nueva_linea = QgsLineString(puntos)
            layer.changeGeometry(id_feature, QgsGeometry(nueva_linea))