# -*- coding: utf-8 -*-
"""
Módulo: Calcular Áreas Acumuladas

Calcula las áreas tributarias (At) y acumuladas (Aa) usando orden
topológico (Kahn) desde las cabeceras de la red.

CORRECCIONES:
    - Reemplazado QgsField(nombre, QVariant.Double) por helper con QMetaType.
    - Compatible con QGIS 3.38+ y 4.x (sin DeprecationWarning).

Compatible con QGIS 3.x y 4.x.
"""

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


class CalcularAreasAcumuladas:
    def __init__(self, iface):
        self.iface = iface
        self.capa_tuberias = None
        self.capa_camaras = None
        self.debug = False

    def mostrar_dialogo(self):
        dialog = QDialog(self.iface.mainWindow())
        dialog.setWindowTitle('GLC - Calcular Áreas Acumuladas')
        dialog.setMinimumWidth(500)

        layout = QVBoxLayout()

        label_titulo = QLabel('<b>Calcular Áreas Acumuladas (At y Aa)</b>')
        label_titulo.setStyleSheet('font-size: 12pt;')
        layout.addWidget(label_titulo)

        label_info = QLabel(
            'Calcula las áreas tributarias y acumuladas usando el modelo de acumulados.\n\n'
            '📌 La cámara final se detecta automáticamente con fin = 1\n\n'
            '📌 Regla principal:\n'
            '   • Una tubería pertenece a la red si Cf == id_camara_final\n'
            '   • Si cab_ata="Arranque" → es cabeza, At = 0, Aa = A\n'
            '   • Si cab_ata="" → seguir hacia su Ci\n\n'
            '📌 Campos actualizados: At, Aa\n'
            '   • At = Área tributaria (m²)\n'
            '   • Aa = Área acumulada (m²) = A + At'
        )
        label_info.setWordWrap(True)
        layout.addWidget(label_info)

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
        self.label_camara_final.setStyleSheet(
            'background-color: #e3f2fd; padding: 8px; border-radius: 4px;'
        )
        layout.addWidget(self.label_camara_final)

        layout.addWidget(QLabel('-' * 40))

        # Barra de progreso
        self.progress = QProgressBar()
        layout.addWidget(self.progress)

        btn_calcular = QPushButton('Calcular Áreas Acumuladas')
        btn_calcular.setStyleSheet(
            'background-color: #4CAF50; color: white; font-weight: bold;'
        )
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
            self.label_camara_final.setStyleSheet(
                'background-color: #ffcdd2; padding: 8px; border-radius: 4px;'
            )
            return None

        # Verificar si existe el campo 'fin'
        idx_fin = layer.fields().indexFromName('fin')
        if idx_fin == -1:
            self.label_camara_final.setText(
                '⚠️ La capa no tiene el campo "fin". '
                'Usa "Asignar Cámara Final" primero.'
            )
            self.label_camara_final.setStyleSheet(
                'background-color: #fff3e0; padding: 8px; border-radius: 4px;'
            )
            return None

        # Buscar la cámara con fin = 1
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
                    f'✅ Cámara final: ID_O={id_o} '
                    f'(X: {punto.x():.2f}, Y: {punto.y():.2f})'
                )
                self.label_camara_final.setStyleSheet(
                    'background-color: #c8e6c9; padding: 8px; border-radius: 4px;'
                )
            else:
                self.label_camara_final.setText(f'✅ Cámara final: ID_O={id_o}')
                self.label_camara_final.setStyleSheet(
                    'background-color: #c8e6c9; padding: 8px; border-radius: 4px;'
                )
            return id_o
        else:
            self.label_camara_final.setText(
                '❌ No hay cámara con fin = 1. '
                'Usa "Asignar Cámara Final" primero.'
            )
            self.label_camara_final.setStyleSheet(
                'background-color: #ffcdd2; padding: 8px; border-radius: 4px;'
            )
            return None

    def calcular(self, dialog, tuberias_id, camaras_id):
        """Calcula áreas acumuladas usando orden topológico (desde cabeceras)"""

        self.capa_tuberias = QgsProject.instance().mapLayer(tuberias_id)
        self.capa_camaras = QgsProject.instance().mapLayer(camaras_id)

        if not self.capa_tuberias or not self.capa_camaras:
            QMessageBox.warning(self.iface.mainWindow(), 'Error',
                                'No se encontraron las capas')
            return

        # Verificar campos
        for campo in ['ID_O', 'Ci', 'Cf', 'cab_ata']:
            if self.capa_tuberias.fields().indexFromName(campo) == -1:
                QMessageBox.warning(
                    self.iface.mainWindow(),
                    'Error',
                    f'La capa de tuberías no tiene el campo "{campo}"'
                )
                return

        # Verificar que existe el campo A
        if self.capa_tuberias.fields().indexFromName('A') == -1:
            QMessageBox.warning(
                self.iface.mainWindow(),
                'Error',
                'La capa de tuberías no tiene el campo "A".\n'
                'Ejecuta primero "Calcular Áreas Propias" para generar A.'
            )
            return

        for campo in ['ID_O', 'Lineas_ID', 'fin']:
            if self.capa_camaras.fields().indexFromName(campo) == -1:
                QMessageBox.warning(
                    self.iface.mainWindow(),
                    'Error',
                    f'La capa de cámaras no tiene el campo "{campo}"'
                )
                return

        # Buscar la cámara final automáticamente
        id_final = self.buscar_camara_final(camaras_id)

        if id_final is None:
            QMessageBox.warning(
                self.iface.mainWindow(),
                'Error',
                'No se encontró una cámara final.\n'
                'Usa el módulo "Asignar Cámara Final" primero.'
            )
            return

        # Agregar At y Aa si no existen (sin DeprecationWarning)
        if self.capa_tuberias.fields().indexFromName('At') == -1:
            self.capa_tuberias.dataProvider().addAttributes(
                [_campo('At', 'double')]
            )
            self.capa_tuberias.updateFields()

        if self.capa_tuberias.fields().indexFromName('Aa') == -1:
            self.capa_tuberias.dataProvider().addAttributes(
                [_campo('Aa', 'double')]
            )
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

            cab_ata_valor = feature.attribute('cab_ata') or ''

            tuberias_dict[id_o] = {
                'id_o': id_o,
                'ci': feature.attribute('Ci'),
                'cf': feature.attribute('Cf'),
                'a': feature.attribute('A') or 0.0,
                'cab_ata': cab_ata_valor,
                'feature': feature,
                'at': 0.0,
                'aa': 0.0,
                'procesado': False
            }

        self.progress.setValue(20)

        # ============================================
        # PASO 2: Orden topológico (Kahn)
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
                    dependencias_pendientes = [
                        d for d in dependencias.get(id_o, [])
                        if d not in procesados
                    ]
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

        # Diccionario para acumular sumas de áreas por cámara
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
                data['at'] = 0.0
                data['aa'] = data['a']
                data['procesado'] = True

                # Agregar esta tubería a la suma de su Cf
                cf = data['cf']
                if cf in sumas_por_camara:
                    sumas_por_camara[cf] += data['aa']

                continue

            # ===== SI ES VACIO (tubería normal) =====
            ci = data['ci']

            # Obtener la suma que llega a esta cámara
            sum_at = sumas_por_camara.get(ci, 0.0)

            data['at'] = sum_at
            data['aa'] = data['a'] + sum_at
            data['procesado'] = True

            # Agregar esta tubería a la suma de su Cf
            cf = data['cf']
            if cf in sumas_por_camara:
                sumas_por_camara[cf] += data['aa']

            # Actualizar progreso
            progreso = 50 + (i / total) * 40
            self.progress.setValue(int(progreso))

        self.progress.setValue(90)

        # ============================================
        # PASO 4: Actualizar campos en la capa
        # ============================================

        self.capa_tuberias.startEditing()
        idx_at = self.capa_tuberias.fields().indexFromName('At')
        idx_aa = self.capa_tuberias.fields().indexFromName('Aa')

        for id_o, data in tuberias_dict.items():
            feature = data['feature']

            # Si no fue procesada, asignar valores por defecto
            if not data['procesado']:
                data['at'] = 0.0
                data['aa'] = data['a']

            self.capa_tuberias.changeAttributeValue(
                feature.id(), idx_at, round(data['at'], 3)
            )
            self.capa_tuberias.changeAttributeValue(
                feature.id(), idx_aa, round(data['aa'], 3)
            )

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
            f'  • At (Área tributaria)\n'
            f'  • Aa (Área acumulada = A + At)'
        )

        QMessageBox.information(
            self.iface.mainWindow(),
            'Áreas Acumuladas Calculadas',
            mensaje
        )

        dialog.accept()