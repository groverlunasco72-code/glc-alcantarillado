# -*- coding: utf-8 -*-
"""
Módulo: Planilla de Diámetros

Crea una planilla editable con diámetros y anchos de zanja.
Se exporta como CSV (recomendado) o GeoPackage (tabla sin geometría).

CORRECCIONES:
    - Eliminado el uso de QgsField(nombre, QVariant.Tipo).
    - Eliminado writeAsVectorFormat (deprecado).
    - Ahora exporta CSV o GeoPackage (no más puntos ficticios).

Compatible con QGIS 3.x y 4.x.
"""

from qgis.core import (
    QgsProject, QgsVectorLayer, QgsFeature,
    QgsGeometry, QgsPointXY, QgsField,
    QgsWkbTypes, QgsVectorFileWriter,
    QgsFields,
)
from qgis.PyQt.QtCore import Qt, QVariant
from qgis.PyQt.QtWidgets import (
    QMessageBox, QDialog, QVBoxLayout, QLabel,
    QPushButton, QHBoxLayout, QFileDialog,
    QTableWidget, QTableWidgetItem, QHeaderView,
    QTabWidget, QWidget, QRadioButton, QButtonGroup,
    QGroupBox,
)
import os
import csv


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


class PlanillaDiametros:
    def __init__(self, iface):
        self.iface = iface
        self.capa_planilla = None
        self.formato_salida = 'csv'   # 'csv' o 'gpkg'

    def mostrar_dialogo(self):
        dialog = QDialog(self.iface.mainWindow())
        dialog.setWindowTitle('GLC - Planilla de Diámetros')
        dialog.setMinimumWidth(900)
        dialog.setMinimumHeight(500)

        layout = QVBoxLayout()

        label_titulo = QLabel('<b>Planilla de Diámetros y Anchos de Zanja</b>')
        label_titulo.setStyleSheet('font-size: 14pt; font-weight: bold;')
        layout.addWidget(label_titulo)

        # ===== TABS =====
        tabs = QTabWidget()

        # ---------- TAB 1: VISTA PREVIA ----------
        tab_vista = QWidget()
        layout_vista = QVBoxLayout()

        label_info = QLabel(
            '📌 ESTRUCTURA DE LA TABLA:\n'
            '   • d_mm   = Diámetro (mm)\n'
            '   • p_por  = Pendiente (%)\n'
            '   • b1     = 0-0 m sin entibado\n'
            '   • b1_    = 0-0 m con entibado\n'
            '   • b2     = 2-2 m sin entibado\n'
            '   • b2_    = 2-2 m con entibado\n'
            '   • b3     = 4-4 m sin entibado\n'
            '   • b3_    = 4-4 m con entibado\n\n'
            '🟩 Primera fila = Límites de profundidad\n'
            '💡 Puedes editar esta tabla desde Excel o desde la tabla de atributos'
        )
        label_info.setWordWrap(True)
        layout_vista.addWidget(label_info)

        # Tabla de vista previa
        self.table_preview = QTableWidget()
        self.table_preview.setColumnCount(8)
        self.table_preview.setHorizontalHeaderLabels(
            ['d_mm', 'p_por', 'b1', 'b1_', 'b2', 'b2_', 'b3', 'b3_']
        )
        self.table_preview.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)

        datos_preview = [
            ['0', '0', '0', '2', '2', '4', '4', '5'],
            ['150', '0.4452', '0.60', '0.70', '0.70', '0.80', '0.80', '1.00'],
            ['200', '0.3339', '0.65', '0.75', '0.75', '0.85', '0.85', '1.05'],
            ['250', '0.2671', '0.70', '0.80', '0.80', '0.90', '0.90', '1.10'],
            ['300', '0.2226', '0.80', '0.90', '0.90', '1.00', '1.00', '1.20'],
            ['400', '0.1670', '0.90', '1.00', '1.00', '1.10', '1.10', '1.30'],
            ['450', '0.1484', '0.95', '1.05', '1.05', '1.15', '1.15', '1.35'],
            ['500', '0.1336', '1.00', '1.10', '1.10', '1.20', '1.20', '1.40'],
            ['550', '0.1214', '1.10', '1.20', '1.20', '1.30', '1.30', '1.50'],
            ['600', '0.1113', '1.15', '1.25', '1.25', '1.40', '1.35', '1.60'],
            ['700', '0.0954', '1.25', '1.35', '1.35', '1.50', '1.45', '1.70'],
            ['800', '0.0835', '1.35', '1.45', '1.45', '1.60', '1.55', '1.80'],
            ['900', '0.0742', '1.50', '1.60', '1.60', '1.75', '1.70', '1.95'],
            ['1000', '0.0668', '1.60', '1.70', '1.70', '1.85', '1.80', '2.05'],
            ['1100', '0.0607', '1.80', '1.90', '1.90', '2.05', '2.00', '2.25'],
        ]

        self.table_preview.setRowCount(len(datos_preview))
        for row, fila in enumerate(datos_preview):
            for col, valor in enumerate(fila):
                item = QTableWidgetItem(valor)
                if row == 0:
                    item.setBackground(Qt.green)
                    item.setForeground(Qt.white)
                self.table_preview.setItem(row, col, item)

        layout_vista.addWidget(self.table_preview)

        label_leyenda = QLabel('🟩 Primera fila = Límites de profundidad')
        label_leyenda.setStyleSheet('padding: 5px;')
        layout_vista.addWidget(label_leyenda)

        tab_vista.setLayout(layout_vista)
        tabs.addTab(tab_vista, 'Vista Previa')

        # ---------- TAB 2: CREAR PLANILLA ----------
        tab_crear = QWidget()
        layout_crear = QVBoxLayout()

        # Formato de salida
        box_formato = QGroupBox('Formato de salida')
        lay_formato = QVBoxLayout()

        self.radio_csv = QRadioButton('📄 CSV (editable en Excel) — recomendado')
        self.radio_csv.setChecked(True)
        self.radio_gpkg = QRadioButton('🗂️ GeoPackage (tabla sin geometría)')

        grupo = QButtonGroup(dialog)
        grupo.addButton(self.radio_csv)
        grupo.addButton(self.radio_gpkg)

        lay_formato.addWidget(self.radio_csv)
        lay_formato.addWidget(self.radio_gpkg)
        box_formato.setLayout(lay_formato)
        layout_crear.addWidget(box_formato)

        layout_crear.addWidget(QLabel('-' * 40))

        layout_crear.addWidget(QLabel('Carpeta de guardado:'))
        self.ruta_label = QLabel('Seleccionar carpeta...')
        self.ruta_label.setStyleSheet('background-color: #f5f5f5; padding: 5px;')
        layout_crear.addWidget(self.ruta_label)

        btn_ruta = QPushButton('Seleccionar Carpeta')
        btn_ruta.clicked.connect(self.seleccionar_carpeta)
        layout_crear.addWidget(btn_ruta)

        layout_crear.addWidget(QLabel('-' * 40))

        btn_crear = QPushButton('Crear Planilla de Diámetros')
        btn_crear.setStyleSheet(
            'background-color: #4CAF50; color: white; font-weight: bold; font-size: 12pt;'
        )
        btn_crear.clicked.connect(self.crear_planilla)
        layout_crear.addWidget(btn_crear)

        layout_crear.addWidget(QLabel('-' * 40))

        label_ayuda = QLabel(
            '📌 DESPUÉS DE CREAR LA PLANILLA:\n'
            '   • CSV: ábrelo en Excel, edita la tabla y guarda como CSV\n'
            '   • GeoPackage: se abrirá en QGIS como tabla sin geometría\n'
            '     y podrás editarla desde la tabla de atributos\n\n'
            '💡 Para agregar un nuevo rango:\n'
            '   • Agrega 2 columnas nuevas (bN y bN_)\n'
            '   • Completa los valores para cada diámetro\n'
            '   • Actualiza la primera fila con los nuevos límites'
        )
        label_ayuda.setWordWrap(True)
        label_ayuda.setStyleSheet(
            'background-color: #f5f5f5; padding: 10px; border-radius: 5px;'
        )
        layout_crear.addWidget(label_ayuda)

        tab_crear.setLayout(layout_crear)
        tabs.addTab(tab_crear, 'Crear Planilla')

        layout.addWidget(tabs)

        btn_cerrar = QPushButton('Cerrar')
        btn_cerrar.setStyleSheet('background-color: #f44336; color: white;')
        btn_cerrar.clicked.connect(dialog.accept)
        layout.addWidget(btn_cerrar)

        dialog.setLayout(layout)
        dialog.exec_()

    def seleccionar_carpeta(self):
        carpeta = QFileDialog.getExistingDirectory(
            self.iface.mainWindow(),
            'Seleccionar Carpeta para guardar Planilla',
            ''
        )
        if carpeta:
            self.ruta_label.setText(carpeta)

    def crear_planilla(self):
        carpeta = self.ruta_label.text()

        if carpeta == 'Seleccionar carpeta...' or not os.path.exists(carpeta):
            QMessageBox.warning(
                self.iface.mainWindow(),
                'Error',
                'Selecciona una carpeta válida para guardar'
            )
            return

        # Determinar formato elegido
        if self.radio_gpkg.isChecked():
            self.formato_salida = 'gpkg'
        else:
            self.formato_salida = 'csv'

        # Datos (encabezados + filas)
        headers = ['d_mm', 'p_por', 'b1', 'b1_', 'b2', 'b2_', 'b3', 'b3_']

        # Primera fila: límites
        limites = [0, 0, 0, 2, 2, 4, 4, 5]

        datos = [
            [150, 0.4452, 0.60, 0.70, 0.70, 0.80, 0.80, 1.00],
            [200, 0.3339, 0.65, 0.75, 0.75, 0.85, 0.85, 1.05],
            [250, 0.2671, 0.70, 0.80, 0.80, 0.90, 0.90, 1.10],
            [300, 0.2226, 0.80, 0.90, 0.90, 1.00, 1.00, 1.20],
            [400, 0.1670, 0.90, 1.00, 1.00, 1.10, 1.10, 1.30],
            [450, 0.1484, 0.95, 1.05, 1.05, 1.15, 1.15, 1.35],
            [500, 0.1336, 1.00, 1.10, 1.10, 1.20, 1.20, 1.40],
            [550, 0.1214, 1.10, 1.20, 1.20, 1.30, 1.30, 1.50],
            [600, 0.1113, 1.15, 1.25, 1.25, 1.40, 1.35, 1.60],
            [700, 0.0954, 1.25, 1.35, 1.35, 1.50, 1.45, 1.70],
            [800, 0.0835, 1.35, 1.45, 1.45, 1.60, 1.55, 1.80],
            [900, 0.0742, 1.50, 1.60, 1.60, 1.75, 1.70, 1.95],
            [1000, 0.0668, 1.60, 1.70, 1.70, 1.85, 1.80, 2.05],
            [1100, 0.0607, 1.80, 1.90, 1.90, 2.05, 2.00, 2.25],
        ]

        filas = [limites] + datos

        # ============================================================
        # GUARDAR CSV
        # ============================================================
        if self.formato_salida == 'csv':
            nombre_archivo = os.path.join(carpeta, "GLC_Planilla_Diametros.csv")

            if os.path.exists(nombre_archivo):
                respuesta = QMessageBox.question(
                    self.iface.mainWindow(),
                    'Archivo existe',
                    f'El archivo ya existe.\n¿Deseas sobrescribirlo?',
                    QMessageBox.Yes | QMessageBox.No
                )
                if respuesta == QMessageBox.No:
                    return

            try:
                # Encoding utf-8-sig para que Excel muestre bien las tildes
                with open(nombre_archivo, 'w', newline='', encoding='utf-8-sig') as f:
                    writer = csv.writer(f, delimiter=';')
                    writer.writerow(headers)
                    for fila in filas:
                        writer.writerow(fila)

                self._mostrar_resumen_csv(nombre_archivo, len(datos))
            except Exception as e:
                QMessageBox.warning(
                    self.iface.mainWindow(), 'Error',
                    f'No se pudo guardar el CSV:\n{e}'
                )
                return

        # ============================================================
        # GUARDAR GEOPACKAGE (tabla sin geometría)
        # ============================================================
        else:
            nombre_archivo = os.path.join(carpeta, "GLC_Planilla_Diametros.gpkg")

            if os.path.exists(nombre_archivo):
                respuesta = QMessageBox.question(
                    self.iface.mainWindow(),
                    'Archivo existe',
                    f'El archivo ya existe.\n¿Deseas sobrescribirlo?',
                    QMessageBox.Yes | QMessageBox.No
                )
                if respuesta == QMessageBox.No:
                    return
                # Borrar para sobrescribir
                try:
                    os.remove(nombre_archivo)
                except Exception:
                    pass

            # Crear capa sin geometría
            uri = f"None?field=d_mm:double&field=p_por:double" \
                  f"&field=b1:double&field=b1_:double" \
                  f"&field=b2:double&field=b2_:double" \
                  f"&field=b3:double&field=b3_:double"

            capa = QgsVectorLayer(uri, "GLC_Planilla_Diametros", "memory")

            if not capa.isValid():
                QMessageBox.warning(self.iface.mainWindow(), 'Error',
                                    'No se pudo crear la capa sin geometría')
                return

            features = []
            for fila in filas:
                feature = QgsFeature(capa.fields())
                feature.setAttributes(fila)
                features.append(feature)

            capa.dataProvider().addFeatures(features)
            capa.updateExtents()

            # Guardar como GeoPackage (API moderna)
            try:
                options = QgsVectorFileWriter.SaveVectorOptions()
                options.driverName = 'GPKG'
                options.layerName = 'GLC_Planilla_Diametros'
                try:
                    options.actionOnExistingFile = \
                        QgsVectorFileWriter.CreateOrOverwriteFile
                except AttributeError:
                    pass

                transform_context = QgsProject.instance().transformContext()

                resultado = QgsVectorFileWriter.writeAsVectorFormatV3(
                    capa,
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
            except Exception as e:
                QMessageBox.warning(
                    self.iface.mainWindow(), 'Error',
                    f'Error al guardar el GeoPackage:\n{e}'
                )
                return

            # Cargar en el proyecto
            capa_guardada = QgsVectorLayer(
                f"{nombre_archivo}|layername=GLC_Planilla_Diametros",
                "GLC_Planilla_Diametros", "ogr"
            )
            QgsProject.instance().addMapLayer(capa_guardada)
            self.capa_planilla = capa_guardada
            self.iface.showAttributeTable(capa_guardada)

            self._mostrar_resumen_gpkg(nombre_archivo, len(datos))

    def _mostrar_resumen_csv(self, nombre_archivo, n_datos):
        mensaje = (
            f'✅ Planilla creada exitosamente (CSV)\n\n'
            f'📁 {nombre_archivo}\n'
            f'📊 {n_datos} diámetros + 1 fila de límites\n'
            f'📄 Separador: ; (punto y coma)\n'
            f'📄 Codificación: UTF-8 con BOM (compatible con Excel)\n\n'
            f'📌 PRIMERA FILA (límites):\n'
            f'   b1=0, b1_=2  → Rango 0-0\n'
            f'   b2=2, b2_=4  → Rango 2-2\n'
            f'   b3=4, b3_=5  → Rango 4-4\n\n'
            f'📌 b1, b2, b3 = Sin Entibado\n'
            f'📌 b1_, b2_, b3_ = Con Entibado\n\n'
            f'💡 Abre el archivo en Excel para editarlo.'
        )
        QMessageBox.information(self.iface.mainWindow(), 'Planilla Creada', mensaje)

    def _mostrar_resumen_gpkg(self, nombre_archivo, n_datos):
        mensaje = (
            f'✅ Planilla creada exitosamente (GeoPackage)\n\n'
            f'📁 {nombre_archivo}\n'
            f'📊 {n_datos} diámetros + 1 fila de límites\n'
            f'🗂️ Tabla sin geometría (solo atributos)\n\n'
            f'📌 PRIMERA FILA (límites):\n'
            f'   b1=0, b1_=2  → Rango 0-0\n'
            f'   b2=2, b2_=4  → Rango 2-2\n'
            f'   b3=4, b3_=5  → Rango 4-4\n\n'
            f'📌 b1, b2, b3 = Sin Entibado\n'
            f'📌 b1_, b2_, b3_ = Con Entibado\n\n'
            f'💡 La tabla se ha abierto en QGIS. Actívala en modo edición '
            f'para modificarla.'
        )
        QMessageBox.information(self.iface.mainWindow(), 'Planilla Creada', mensaje)