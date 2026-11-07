# -*- coding: utf-8 -*-
"""
Módulo: interaccion_epaswmm
Versión: 1.3
Propósito: Integrar los módulos de interacción con EPA SWMM
- Calcular Caudales por Tramo (añade Caudal_Tra y Sumatoria a GLC_Tuberias)
- Crear Tuberías Virtuales (copia con Ci_Virtual)
- Generar Cámaras Virtuales desde Tuberías Virtuales

Cambios v1.3:
    - Eliminados DeprecationWarning de QgsField (uso de QMetaType).
    - Eliminado DeprecationWarning de QgsVectorFileWriter (writeAsVectorFormatV3).
    - Compatible con QGIS 3.x y 4.x.
"""

from qgis.PyQt.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QPushButton,
    QLabel, QComboBox, QMessageBox, QProgressBar,
    QLineEdit, QGroupBox, QGridLayout, QFileDialog
)
from qgis.PyQt.QtCore import Qt, QVariant
from qgis.core import (
    QgsProject, QgsVectorLayer, QgsField, QgsFeature,
    QgsGeometry, QgsWkbTypes, QgsFields,
    QgsVectorFileWriter, QgsPointXY
)
import os

# ============================================================
# COMPATIBILIDAD: QMetaType (QGIS 3.38+ / 4.x) vs QVariant (antiguo)
# ============================================================
try:
    from qgis.PyQt.QtCore import QMetaType
    _USE_QMETATYPE = True
except ImportError:
    _USE_QMETATYPE = False


class InteraccionEPASWMM:
    def __init__(self, iface):
        self.iface = iface
        self.dialog = None
        self.ruta_salida = None
        self.id_final = None

    # ============================================================
    # HELPER: crear QgsField sin DeprecationWarning
    # ============================================================
    @staticmethod
    def _campo(nombre, tipo, longitud=0, precision=0):
        """
        Crea un QgsField evitando el DeprecationWarning en QGIS 3.38+.

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

    # ============================================================
    # DIÁLOGO
    # ============================================================
    def mostrar_dialogo(self):
        """Muestra el diálogo principal"""
        self.dialog = QDialog(self.iface.mainWindow())
        self.dialog.setWindowTitle('GLC - Interacción EPA SWMM')
        self.dialog.setMinimumWidth(750)

        layout = QVBoxLayout()

        # Descripción
        lbl_desc = QLabel(
            '<b>Interacción EPA SWMM</b>\n\n'
            '📌 Proceso integrado en 3 pasos:\n\n'
            '1️⃣ <b>Calcular Caudales por Tramo</b>\n'
            '   • Añade Caudal_Tra y Sumatoria a GLC_Tuberias\n'
            '   • Cámara final se detecta automáticamente (fin=1)\n\n'
            '2️⃣ <b>Crear Tuberías Virtuales</b>\n'
            '   • Copia GLC_Tuberias con columna Ci_Virtual\n'
            '   • Solo modifica Ci en tuberías con cab_ata="Arranque"\n'
            '   • Renombra duplicados con letras (a, b, c...)\n\n'
            '3️⃣ <b>Generar Cámaras Virtuales</b>\n'
            '   • Crea GLC_Camaras_Virtuales desde Tuberías Virtuales\n'
            '   • Nodo final detectado automáticamente de GLC_Camaras (fin=1)'
        )
        lbl_desc.setWordWrap(True)
        layout.addWidget(lbl_desc)

        # Selección de capas
        group_capas = QGroupBox('Capas de entrada')
        grid_capas = QGridLayout()

        grid_capas.addWidget(QLabel('Tuberías (GLC_Tuberias):'), 0, 0)
        self.cmb_tuberias = QComboBox()
        self._cargar_capas_linea()
        grid_capas.addWidget(self.cmb_tuberias, 0, 1)

        grid_capas.addWidget(QLabel('Cámaras (GLC_Camaras):'), 1, 0)
        self.cmb_camaras = QComboBox()
        self._cargar_capas_punto()
        grid_capas.addWidget(self.cmb_camaras, 1, 1)

        # Mostrar la cámara final detectada
        self.label_camara_final = QLabel('🔍 Buscando cámara final...')
        self.label_camara_final.setStyleSheet(
            'background-color: #e3f2fd; padding: 8px; border-radius: 4px;'
        )
        grid_capas.addWidget(self.label_camara_final, 2, 0, 1, 2)

        group_capas.setLayout(grid_capas)
        layout.addWidget(group_capas)

        # Carpeta de salida
        group_salida = QGroupBox('Carpeta de salida')
        grid_salida = QGridLayout()

        self.txt_ruta = QLineEdit()
        self.txt_ruta.setReadOnly(True)
        grid_salida.addWidget(self.txt_ruta, 0, 0)

        btn_ruta = QPushButton('Seleccionar Carpeta...')
        btn_ruta.clicked.connect(self._seleccionar_carpeta)
        grid_salida.addWidget(btn_ruta, 0, 1)

        btn_proyecto = QPushButton('Usar carpeta del proyecto')
        btn_proyecto.clicked.connect(self._usar_carpeta_proyecto)
        grid_salida.addWidget(btn_proyecto, 1, 0, 1, 2)

        group_salida.setLayout(grid_salida)
        layout.addWidget(group_salida)

        # Barra de progreso
        self.progress = QProgressBar()
        layout.addWidget(self.progress)

        # Botones
        btn_layout = QHBoxLayout()
        btn_ejecutar = QPushButton('Ejecutar Proceso Completo')
        btn_ejecutar.setStyleSheet(
            'background-color: #4CAF50; color: white; font-weight: bold;'
        )
        btn_ejecutar.clicked.connect(self.ejecutar)
        btn_cerrar = QPushButton('Cerrar')
        btn_cerrar.clicked.connect(self.dialog.close)
        btn_layout.addStretch()
        btn_layout.addWidget(btn_ejecutar)
        btn_layout.addWidget(btn_cerrar)
        layout.addLayout(btn_layout)

        # Conexiones
        self.cmb_camaras.currentIndexChanged.connect(self._buscar_camara_final)

        self.dialog.setLayout(layout)
        self.dialog.show()

        # Buscar cámara final automáticamente al mostrar
        self._buscar_camara_final()

    # ============================================================
    # CARGA DE CAPAS
    # ============================================================
    def _cargar_capas_linea(self):
        self.cmb_tuberias.clear()
        for layer in QgsProject.instance().mapLayers().values():
            if layer.type() == QgsVectorLayer.VectorLayer and \
               layer.geometryType() == QgsWkbTypes.LineGeometry:
                self.cmb_tuberias.addItem(layer.name(), layer.id())

    def _cargar_capas_punto(self):
        self.cmb_camaras.clear()
        for layer in QgsProject.instance().mapLayers().values():
            if layer.type() == QgsVectorLayer.VectorLayer and \
               layer.geometryType() == QgsWkbTypes.PointGeometry:
                self.cmb_camaras.addItem(layer.name(), layer.id())

    # ============================================================
    # DETECCIÓN DE CÁMARA FINAL
    # ============================================================
    def _buscar_camara_final(self):
        """Buscar la cámara final (fin = 1) en la capa de cámaras"""
        layer_id = self.cmb_camaras.currentData()
        if not layer_id:
            self.label_camara_final.setText('❌ Seleccione una capa de cámaras')
            self.label_camara_final.setStyleSheet(
                'background-color: #ffcdd2; padding: 8px; border-radius: 4px;'
            )
            self.id_final = None
            return

        layer = QgsProject.instance().mapLayer(layer_id)
        if not layer:
            self.label_camara_final.setText('❌ No se encontró la capa')
            self.label_camara_final.setStyleSheet(
                'background-color: #ffcdd2; padding: 8px; border-radius: 4px;'
            )
            self.id_final = None
            return

        idx_fin = layer.fields().indexFromName('fin')
        if idx_fin == -1:
            self.label_camara_final.setText('⚠️ La capa no tiene el campo "fin".')
            self.label_camara_final.setStyleSheet(
                'background-color: #fff3e0; padding: 8px; border-radius: 4px;'
            )
            self.id_final = None
            return

        camara_final = None
        for feature in layer.getFeatures():
            if feature.attribute('fin') == 1:
                camara_final = feature
                break

        if camara_final:
            id_o = camara_final.attribute('ID_O')
            self.id_final = id_o
            geom = camara_final.geometry()
            if geom:
                punto = geom.asPoint()
                self.label_camara_final.setText(
                    f'✅ Cámara final: ID_O={id_o} (X: {punto.x():.2f}, Y: {punto.y():.2f})'
                )
                self.label_camara_final.setStyleSheet(
                    'background-color: #c8e6c9; padding: 8px; border-radius: 4px;'
                )
            else:
                self.label_camara_final.setText(f'✅ Cámara final: ID_O={id_o}')
                self.label_camara_final.setStyleSheet(
                    'background-color: #c8e6c9; padding: 8px; border-radius: 4px;'
                )
        else:
            self.label_camara_final.setText('❌ No hay cámara con fin = 1.')
            self.label_camara_final.setStyleSheet(
                'background-color: #ffcdd2; padding: 8px; border-radius: 4px;'
            )
            self.id_final = None

    # ============================================================
    # CARPETA DE SALIDA
    # ============================================================
    def _seleccionar_carpeta(self):
        carpeta = QFileDialog.getExistingDirectory(
            self.dialog,
            'Seleccionar carpeta de salida',
            '',
            QFileDialog.ShowDirsOnly
        )
        if carpeta:
            self.txt_ruta.setText(carpeta)
            self.ruta_salida = carpeta

    def _usar_carpeta_proyecto(self):
        proyecto = QgsProject.instance()
        ruta = proyecto.fileName()
        if ruta:
            carpeta = os.path.dirname(ruta)
            self.txt_ruta.setText(carpeta)
            self.ruta_salida = carpeta
        else:
            QMessageBox.warning(self.dialog, 'Error', 'Guarde el proyecto primero.')

    # ============================================================
    # GUARDAR SHAPEFILE (API MODERNA)
    # ============================================================
    def _guardar_shapefile(self, capa, nombre):
        """
        Guarda una capa como shapefile usando writeAsVectorFormatV3
        (API moderna, sin DeprecationWarning).
        """
        if not self.ruta_salida:
            return None

        nombre_archivo = os.path.join(self.ruta_salida, f"{nombre}.shp")

        if os.path.exists(nombre_archivo):
            respuesta = QMessageBox.question(
                self.dialog,
                'Archivo existe',
                f'El archivo {nombre}.shp ya existe.\n¿Deseas sobrescribirlo?',
                QMessageBox.Yes | QMessageBox.No
            )
            if respuesta == QMessageBox.No:
                return None

        # ============================================================
        # API moderna: writeAsVectorFormatV3
        # ============================================================
        try:
            options = QgsVectorFileWriter.SaveVectorOptions()
            options.driverName = 'ESRI Shapefile'
            options.fileEncoding = 'utf-8'
            options.layerName = nombre

            # Si el archivo ya existe, permitir sobreescribir
            try:
                options.actionOnExistingFile = \
                    QgsVectorFileWriter.CreateOrOverwriteFile
            except AttributeError:
                pass  # versiones antiguas no tienen este atributo

            transform_context = QgsProject.instance().transformContext()

            resultado = QgsVectorFileWriter.writeAsVectorFormatV3(
                capa,
                nombre_archivo,
                transform_context,
                options
            )

            # writeAsVectorFormatV3 devuelve (err, errString, newFilename, newLayer)
            if isinstance(resultado, tuple):
                err_code = resultado[0]
                err_msg = resultado[1] if len(resultado) > 1 else ''
            else:
                err_code = resultado
                err_msg = ''

            if err_code != QgsVectorFileWriter.NoError:
                QMessageBox.warning(
                    self.dialog, 'Error',
                    f'Error al guardar {nombre}:\n{err_msg or err_code}'
                )
                return None

            return nombre_archivo

        except AttributeError:
            # Fallback (versiones muy antiguas, no debería ocurrir en QGIS 3.10+)
            error = QgsVectorFileWriter.writeAsVectorFormat(
                capa,
                nombre_archivo,
                'utf-8',
                capa.crs(),
                'ESRI Shapefile'
            )
            if error[0] != QgsVectorFileWriter.NoError:
                QMessageBox.warning(self.dialog, 'Error', f'Error al guardar: {error}')
                return None
            return nombre_archivo

    # ============================================================
    # RENOMBRAR DUPLICADOS
    # ============================================================
    def _renombrar_duplicados(self, lista_virtuales):
        """
        Recibe una lista de Ci_Virtual y renombra los duplicados con letras.
        Ejemplo: ['100v', '100v', '200v'] → ['100va', '100vb', '200v']
        """
        conteo = {}
        for valor in lista_virtuales:
            if valor and valor != '':
                if valor not in conteo:
                    conteo[valor] = 0
                conteo[valor] += 1

        duplicados = {k: v for k, v in conteo.items() if v > 1}
        if not duplicados:
            return lista_virtuales

        contadores = {k: 0 for k in duplicados.keys()}
        letras = 'abcdefghijklmnopqrstuvwxyz'
        resultado = []

        for valor in lista_virtuales:
            if valor in duplicados:
                idx = contadores[valor]
                if idx < len(letras):
                    nuevo_valor = f"{valor}{letras[idx]}"
                else:
                    nuevo_valor = f"{valor}_{idx-26+1}"
                contadores[valor] += 1
                resultado.append(nuevo_valor)
            else:
                resultado.append(valor)

        return resultado

    # ============================================================
    # HELPERS DE CONVERSIÓN SEGURA
    # ============================================================
    def _to_float(self, valor):
        if valor is None:
            return 0.0
        try:
            return float(valor)
        except (ValueError, TypeError):
            return 0.0

    def _to_str(self, valor):
        if valor is None:
            return ''
        return str(valor)

    # ============================================================
    # PASO 1: Calcular Caudales por Tramo
    # ============================================================
    def _calcular_caudales_tramo(self, capa_tuberias, capa_camaras, id_final):
        """Calcula caudales por tramo y añade columnas Caudal_Tra y Sumatoria"""

        campo_id_tuberia = 'ID_O'
        campo_ci = 'Ci'
        campo_cf = 'Cf'
        campo_qdiseno = 'qdise'
        campo_cab_ata = 'cab_ata'

        campos_tuberia = [f.name() for f in capa_tuberias.fields()]
        for campo in [campo_id_tuberia, campo_ci, campo_cf, campo_qdiseno, campo_cab_ata]:
            if campo not in campos_tuberia:
                raise Exception(f"El campo '{campo}' no existe en la capa de tuberías")

        campo_id_camara = 'ID_O'
        campo_fin = 'fin'
        campos_camara = [f.name() for f in capa_camaras.fields()]
        if campo_id_camara not in campos_camara:
            raise Exception(f"El campo '{campo_id_camara}' no existe en la capa de cámaras")
        if campo_fin not in campos_camara:
            raise Exception(f"El campo '{campo_fin}' no existe en la capa de cámaras")

        # Diccionario de tuberías
        tuberias_dict = {}
        for feature in capa_tuberias.getFeatures():
            id_o = feature.attribute(campo_id_tuberia)
            if id_o is None:
                continue

            cab_ata_valor = self._to_str(feature.attribute(campo_cab_ata))

            tuberias_dict[id_o] = {
                'id_o': id_o,
                'ci': feature.attribute(campo_ci),
                'cf': feature.attribute(campo_cf),
                'qdiseno': self._to_float(feature.attribute(campo_qdiseno)),
                'cab_ata': cab_ata_valor,
                'feature': feature,
                'procesado': False,
                'caudal_tramo': 0.0,
                'sumatoria': 0.0
            }

        # Cabezas
        cabezas = []
        for id_tuberia, datos in tuberias_dict.items():
            if datos['cab_ata'] == 'Arranque':
                cabezas.append(id_tuberia)

        if not cabezas:
            raise Exception('No se encontraron tuberías con cab_ata="Arranque"')

        for id_cabeza in cabezas:
            if id_cabeza in tuberias_dict:
                tuberia = tuberias_dict[id_cabeza]
                tuberia['caudal_tramo'] = tuberia['qdiseno']
                tuberia['sumatoria'] = tuberia['qdiseno']
                tuberia['procesado'] = True

        # Procesar resto iterativamente
        max_iteraciones = len(tuberias_dict) * 2
        iteracion = 0

        while iteracion < max_iteraciones:
            iteracion += 1
            algo_procesado = False

            for id_tuberia, tuberia in tuberias_dict.items():
                if tuberia['procesado']:
                    continue

                ci = tuberia['ci']
                if ci is None or ci == -1:
                    continue

                todas_llegan_procesadas = True
                sumatoria_total_que_llega = 0.0

                for id_t, datos in tuberias_dict.items():
                    if datos['cf'] == ci:
                        if not datos['procesado']:
                            todas_llegan_procesadas = False
                            break
                        else:
                            sumatoria_total_que_llega += datos['sumatoria']

                if todas_llegan_procesadas:
                    caudal_tramo = tuberia['qdiseno'] - sumatoria_total_que_llega
                    tuberia['caudal_tramo'] = caudal_tramo
                    tuberia['sumatoria'] = sumatoria_total_que_llega + caudal_tramo
                    tuberia['procesado'] = True
                    algo_procesado = True

            if not algo_procesado:
                break

        no_procesadas = sum(1 for d in tuberias_dict.values() if not d['procesado'])
        if no_procesadas > 0:
            print(f"⚠️ Advertencia: {no_procesadas} tuberías no fueron procesadas")

        # Añadir campos con la API moderna
        provider = capa_tuberias.dataProvider()
        idx_caudal_tra = capa_tuberias.fields().indexFromName('Caudal_Tra')
        if idx_caudal_tra == -1:
            provider.addAttributes([self._campo('Caudal_Tra', 'double', 20, 3)])

        idx_sumatoria = capa_tuberias.fields().indexFromName('Sumatoria')
        if idx_sumatoria == -1:
            provider.addAttributes([self._campo('Sumatoria', 'double', 20, 3)])

        capa_tuberias.updateFields()

        # Actualizar valores
        capa_tuberias.startEditing()
        for id_tuberia, datos in tuberias_dict.items():
            feature = datos['feature']
            feature.setAttribute('Caudal_Tra', round(datos['caudal_tramo'], 3))
            feature.setAttribute('Sumatoria', round(datos['sumatoria'], 3))
            capa_tuberias.updateFeature(feature)

        capa_tuberias.commitChanges()

        return {
            'total': len(tuberias_dict),
            'procesadas': sum(1 for d in tuberias_dict.values() if d['procesado']),
            'cabezas': len(cabezas),
            'no_procesadas': no_procesadas
        }

    # ============================================================
    # PASO 2: Crear Tuberías Virtuales
    # ============================================================
    def _crear_tuberias_virtuales(self, capa_tuberias):
        """Crea una copia de las tuberías con la columna Ci_Virtual"""

        campos_tuberia = [f.name() for f in capa_tuberias.fields()]
        for campo in ['ID_O', 'Ci', 'Cf', 'cab_ata']:
            if campo not in campos_tuberia:
                raise Exception(f"El campo '{campo}' no existe en la capa de tuberías")

        crs = capa_tuberias.crs()

        # Copiar campos + añadir Ci_Virtual (sin deprecación)
        campos = QgsFields(capa_tuberias.fields())
        campos.append(self._campo('Ci_Virtual', 'string', 50))

        uri_line = f"LineString?crs={crs.authid()}&index=yes"
        capa_resultado = QgsVectorLayer(uri_line, 'Tuberias_Virtuales', 'memory')
        provider = capa_resultado.dataProvider()
        provider.addAttributes(campos)
        capa_resultado.updateFields()

        total_tuberias = capa_tuberias.featureCount()
        tuberias_modificadas = 0

        lista_virtuales = []
        features_temporales = []

        for feature in capa_tuberias.getFeatures():
            ci_original = feature.attribute('Ci')
            cab_ata = self._to_str(feature.attribute('cab_ata'))

            atributos = list(feature.attributes())

            if cab_ata == 'Arranque' and ci_original is not None:
                ci_virtual = f"{ci_original}v"
                tuberias_modificadas += 1
            else:
                ci_virtual = self._to_str(ci_original)

            lista_virtuales.append(ci_virtual)
            features_temporales.append({
                'atributos': atributos,
                'geometria': feature.geometry(),
                'ci_virtual': ci_virtual
            })

        lista_virtuales_renombrados = self._renombrar_duplicados(lista_virtuales)

        renombrados = 0
        for original, nuevo in zip(lista_virtuales, lista_virtuales_renombrados):
            if original != nuevo and original != '':
                renombrados += 1

        for i, datos in enumerate(features_temporales):
            atributos = datos['atributos']
            ci_virtual_renombrado = lista_virtuales_renombrados[i]
            atributos.append(ci_virtual_renombrado)

            nueva_feature = QgsFeature(campos)
            nueva_feature.setAttributes(atributos)
            nueva_feature.setGeometry(datos['geometria'])
            provider.addFeature(nueva_feature)

        capa_resultado.updateFields()
        capa_resultado.commitChanges()

        return {
            'capa': capa_resultado,
            'total': total_tuberias,
            'modificadas': tuberias_modificadas,
            'renombrados': renombrados
        }

    # ============================================================
    # PASO 3: Generar Cámaras Virtuales
    # ============================================================
    def _generar_camaras_virtuales(self, capa_tuberias_virtuales, id_final):
        """Genera cámaras virtuales desde las tuberías virtuales"""

        campos_tuberia = [f.name() for f in capa_tuberias_virtuales.fields()]
        for campo in ['Ci_Virtual', 'Xi', 'Yi', 'Zi', 'Zs_i',
                      'Caudal_Tra', 'Cf', 'Xf', 'Yf', 'Zf', 'Zs_f']:
            if campo not in campos_tuberia:
                raise Exception(f"El campo '{campo}' no existe en la capa de tuberías virtuales")

        crs = capa_tuberias_virtuales.crs()

        nodos_dict = {}

        # Buscar datos del nodo final
        datos_nodo_final = None
        for feature in capa_tuberias_virtuales.getFeatures():
            cf = feature.attribute('Cf')
            if cf and self._to_str(cf).strip() == self._to_str(id_final):
                datos_nodo_final = {
                    'x': self._to_float(feature.attribute('Xf')),
                    'y': self._to_float(feature.attribute('Yf')),
                    'z': self._to_float(feature.attribute('Zf')),
                    'zs': self._to_float(feature.attribute('Zs_f')),
                }
                break

        if datos_nodo_final is None:
            raise Exception(
                f"No se encontró el nodo final {id_final} en el campo Cf "
                f"de las tuberías virtuales"
            )

        total_tuberias = capa_tuberias_virtuales.featureCount()
        nodos_creados = 0

        for feature in capa_tuberias_virtuales.getFeatures():
            id_ci = feature.attribute('Ci_Virtual')

            if id_ci and self._to_str(id_ci).strip() and self._to_str(id_ci) != '-1':
                id_str = self._to_str(id_ci)

                if id_str not in nodos_dict:
                    xi = self._to_float(feature.attribute('Xi'))
                    yi = self._to_float(feature.attribute('Yi'))
                    zi = self._to_float(feature.attribute('Zi'))
                    zsi = self._to_float(feature.attribute('Zs_i'))
                    qacu = self._to_float(feature.attribute('Caudal_Tra'))

                    nodos_dict[id_str] = {
                        'x': xi,
                        'y': yi,
                        'z': zi,
                        'zs_i': zsi,
                        'qacu': qacu if qacu is not None else 0,
                    }
                    nodos_creados += 1

        # Nodo final
        id_final_str = self._to_str(id_final)
        if id_final_str not in nodos_dict:
            nodos_dict[id_final_str] = {
                'x': datos_nodo_final['x'],
                'y': datos_nodo_final['y'],
                'z': datos_nodo_final['z'],
                'zs_i': datos_nodo_final['zs'],
                'qacu': 0,
            }
            nodos_creados += 1
        else:
            nodos_dict[id_final_str]['x'] = datos_nodo_final['x']
            nodos_dict[id_final_str]['y'] = datos_nodo_final['y']
            nodos_dict[id_final_str]['z'] = datos_nodo_final['z']
            nodos_dict[id_final_str]['zs_i'] = datos_nodo_final['zs']
            nodos_dict[id_final_str]['qacu'] = 0

        # Campos de la capa de nodos (sin deprecación)
        campos = QgsFields()
        campos.append(self._campo('ID_O',     'string', 50))
        campos.append(self._campo('X',        'double', 20, 6))
        campos.append(self._campo('Y',        'double', 20, 6))
        campos.append(self._campo('Z',        'double', 20, 3))
        campos.append(self._campo('Zs_i',     'double', 20, 3))
        campos.append(self._campo('Qacu',     'double', 20, 3))
        campos.append(self._campo('Es_Final', 'string', 3))

        uri = f"Point?crs={crs.authid()}&index=yes"
        capa_resultado = QgsVectorLayer(uri, 'Camaras_Virtuales', 'memory')
        provider = capa_resultado.dataProvider()
        provider.addAttributes(campos)
        capa_resultado.updateFields()

        for id_nodo, datos in nodos_dict.items():
            feature = QgsFeature(campos)

            punto = QgsPointXY(datos['x'], datos['y'])
            geom = QgsGeometry.fromPointXY(punto)

            es_final = 'SI' if id_nodo == id_final_str else 'NO'

            feature.setGeometry(geom)
            feature.setAttributes([
                id_nodo,
                round(datos['x'], 3) if datos['x'] is not None else 0,
                round(datos['y'], 3) if datos['y'] is not None else 0,
                round(datos['z'], 3) if datos['z'] is not None else -9999,
                round(datos['zs_i'], 3) if datos['zs_i'] is not None else -9999,
                round(datos['qacu'], 3) if datos['qacu'] is not None else 0,
                es_final
            ])

            provider.addFeature(feature)

        capa_resultado.updateFields()
        capa_resultado.commitChanges()

        return {
            'capa': capa_resultado,
            'total_nodos': len(nodos_dict),
            'nodo_final': id_final
        }

    # ============================================================
    # EJECUTAR PROCESO COMPLETO
    # ============================================================
    def ejecutar(self):
        """Ejecuta el proceso completo"""
        try:
            if not self.ruta_salida:
                QMessageBox.warning(self.dialog, 'Error', 'Seleccione carpeta de salida')
                return

            tuberias_id = self.cmb_tuberias.currentData()
            camaras_id = self.cmb_camaras.currentData()

            if not tuberias_id or not camaras_id:
                QMessageBox.warning(self.dialog, 'Error', 'Seleccione ambas capas')
                return

            capa_tuberias = QgsProject.instance().mapLayer(tuberias_id)
            capa_camaras = QgsProject.instance().mapLayer(camaras_id)

            if not capa_tuberias or not capa_camaras:
                QMessageBox.warning(self.dialog, 'Error', 'No se encontraron las capas')
                return

            if self.id_final is None:
                QMessageBox.warning(
                    self.dialog, 'Error',
                    'No se encontró una cámara final con fin = 1.\n'
                    'Usa el módulo "Asignar Cámara Final" primero.'
                )
                return

            self.progress.setValue(0)

            # ============================================
            # PASO 1
            # ============================================
            self.progress.setValue(10)
            self.progress.setFormat('Paso 1/3: Calculando caudales...')

            try:
                resultado_caudales = self._calcular_caudales_tramo(
                    capa_tuberias, capa_camaras, self.id_final
                )
            except Exception as e:
                QMessageBox.warning(self.dialog, 'Error',
                                    f'Error en cálculo de caudales: {str(e)}')
                return

            self.progress.setValue(35)

            # ============================================
            # PASO 2
            # ============================================
            self.progress.setFormat('Paso 2/3: Creando tuberías virtuales...')

            try:
                resultado_tuberias_virtuales = self._crear_tuberias_virtuales(capa_tuberias)
            except Exception as e:
                QMessageBox.warning(self.dialog, 'Error',
                                    f'Error al crear tuberías virtuales: {str(e)}')
                return

            ruta_tuberias_virtuales = self._guardar_shapefile(
                resultado_tuberias_virtuales['capa'],
                'GLC_Tuberias_Virtuales'
            )

            if not ruta_tuberias_virtuales:
                QMessageBox.warning(self.dialog, 'Error',
                                    'No se pudo guardar el archivo de tuberías virtuales')
                return

            self.progress.setValue(60)

            capa_tv = QgsVectorLayer(ruta_tuberias_virtuales,
                                     "GLC_Tuberias_Virtuales", "ogr")
            QgsProject.instance().addMapLayer(capa_tv)

            # ============================================
            # PASO 3
            # ============================================
            self.progress.setFormat('Paso 3/3: Generando cámaras virtuales...')

            try:
                resultado_camaras_virtuales = self._generar_camaras_virtuales(
                    capa_tv, self.id_final
                )
            except Exception as e:
                QMessageBox.warning(self.dialog, 'Error',
                                    f'Error al generar cámaras virtuales: {str(e)}')
                return

            ruta_camaras_virtuales = self._guardar_shapefile(
                resultado_camaras_virtuales['capa'],
                'GLC_Camaras_Virtuales'
            )

            if not ruta_camaras_virtuales:
                QMessageBox.warning(self.dialog, 'Error',
                                    'No se pudo guardar el archivo de cámaras virtuales')
                return

            self.progress.setValue(90)

            capa_cv = QgsVectorLayer(ruta_camaras_virtuales,
                                     "GLC_Camaras_Virtuales", "ogr")
            QgsProject.instance().addMapLayer(capa_cv)

            self.progress.setValue(100)
            self.progress.setFormat('Completado')

            # ============================================
            # RESUMEN
            # ============================================
            mensaje = (
                f'✅ PROCESO COMPLETADO\n\n'
                f'📊 Resumen:\n\n'
                f'1️⃣ <b>Caudales por Tramo (GLC_Tuberias):</b>\n'
                f'   • Tuberías procesadas: {resultado_caudales["procesadas"]} '
                f'de {resultado_caudales["total"]}\n'
                f'   • Cabezas (Arranque): {resultado_caudales["cabezas"]}\n'
                f'   • Columnas añadidas: Caudal_Tra, Sumatoria\n'
                f'   • Cámara final: ID_O={self.id_final}\n\n'
                f'2️⃣ <b>Tuberías Virtuales (GLC_Tuberias_Virtuales):</b>\n'
                f'   • Total tuberías: {resultado_tuberias_virtuales["total"]}\n'
                f'   • Modificadas (Arranque): {resultado_tuberias_virtuales["modificadas"]}\n'
                f'   • Ci_Virtual renombrados: {resultado_tuberias_virtuales["renombrados"]}\n\n'
                f'3️⃣ <b>Cámaras Virtuales (GLC_Camaras_Virtuales):</b>\n'
                f'   • Total nodos: {resultado_camaras_virtuales["total_nodos"]}\n'
                f'   • Nodo final: {resultado_camaras_virtuales["nodo_final"]} (Qacu=0)\n\n'
                f'📁 Archivos guardados en:\n'
                f'  📄 {ruta_tuberias_virtuales}\n'
                f'  📄 {ruta_camaras_virtuales}'
            )

            QMessageBox.information(self.dialog, 'Completado', mensaje)
            self.dialog.close()

        except Exception as e:
            QMessageBox.critical(self.dialog, 'Error', f'Error: {str(e)}')
            import traceback
            traceback.print_exc()

    def desactivar(self):
        pass