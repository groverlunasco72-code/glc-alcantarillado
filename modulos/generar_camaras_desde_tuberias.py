# -*- coding: utf-8 -*-
"""
Módulo: generar_camaras_desde_tuberias
Versión: 1.0
Propósito: Generar shapefile de cámaras (nodos) a partir de las tuberías virtuales
SOLO usa Ci_Virtual para crear nodos. El nodo final se busca automáticamente en Cf.
Copia el campo Qacu a cada cámara. El nodo final siempre tiene Qacu = 0.
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

class GenerarCamarasDesdeTuberias:
    def __init__(self, iface):
        self.iface = iface
        self.dialog = None
        self.ruta_salida = None

    def mostrar_dialogo(self):
        """Muestra el diálogo principal"""
        self.dialog = QDialog(self.iface.mainWindow())
        self.dialog.setWindowTitle('GLC - Generar Cámaras desde Tuberías')
        self.dialog.setMinimumWidth(700)
        
        layout = QVBoxLayout()

        # Descripción
        lbl_desc = QLabel(
            '<b>Generar Cámaras (Nodos) desde Tuberías Virtuales</b>\n\n'
            '📌 REGLA:\n'
            '   • Toma Ci_Virtual como ID de los nodos\n'
            '   • Usa las coordenadas Xi, Yi, Zi, Zs_i y Qacu\n'
            '   • Si hay duplicados, se agrupan en una sola cámara\n'
            '   • Ingresa el ID del nodo final y se busca automáticamente en Cf\n'
            '   • El nodo final siempre tiene Qacu = 0\n\n'
            '📌 Se crea UN SOLO shapefile: Camaras.shp'
        )
        lbl_desc.setWordWrap(True)
        layout.addWidget(lbl_desc)

        # Selección de capas
        group_capas = QGroupBox('Capas de entrada')
        grid_capas = QGridLayout()

        grid_capas.addWidget(QLabel('Tuberías Virtuales:'), 0, 0)
        self.cmb_tuberias = QComboBox()
        self._cargar_capas_linea()
        grid_capas.addWidget(self.cmb_tuberias, 0, 1)

        group_capas.setLayout(grid_capas)
        layout.addWidget(group_capas)

        # Selección de campos
        group_campos = QGroupBox('Campos')
        grid_campos = QGridLayout()

        grid_campos.addWidget(QLabel('Campo Ci_Virtual (ID nodo):'), 0, 0)
        self.cmb_ci_virtual = QComboBox()
        grid_campos.addWidget(self.cmb_ci_virtual, 0, 1)

        grid_campos.addWidget(QLabel('Campo Cf (ID nodo final):'), 1, 0)
        self.cmb_cf = QComboBox()
        grid_campos.addWidget(self.cmb_cf, 1, 1)

        grid_campos.addWidget(QLabel('Campo Xi (X inicio):'), 2, 0)
        self.cmb_xi = QComboBox()
        grid_campos.addWidget(self.cmb_xi, 2, 1)

        grid_campos.addWidget(QLabel('Campo Yi (Y inicio):'), 3, 0)
        self.cmb_yi = QComboBox()
        grid_campos.addWidget(self.cmb_yi, 3, 1)

        grid_campos.addWidget(QLabel('Campo Zi (cota inicio):'), 4, 0)
        self.cmb_zi = QComboBox()
        grid_campos.addWidget(self.cmb_zi, 4, 1)

        grid_campos.addWidget(QLabel('Campo Zs_i (cota solera inicio):'), 5, 0)
        self.cmb_zsi = QComboBox()
        grid_campos.addWidget(self.cmb_zsi, 5, 1)

        grid_campos.addWidget(QLabel('Campo Qacu (caudal acumulado):'), 6, 0)
        self.cmb_qacu = QComboBox()
        grid_campos.addWidget(self.cmb_qacu, 6, 1)

        grid_campos.addWidget(QLabel('Campo Xf (X final):'), 7, 0)
        self.cmb_xf = QComboBox()
        grid_campos.addWidget(self.cmb_xf, 7, 1)

        grid_campos.addWidget(QLabel('Campo Yf (Y final):'), 8, 0)
        self.cmb_yf = QComboBox()
        grid_campos.addWidget(self.cmb_yf, 8, 1)

        grid_campos.addWidget(QLabel('Campo Zf (cota final):'), 9, 0)
        self.cmb_zf = QComboBox()
        grid_campos.addWidget(self.cmb_zf, 9, 1)

        grid_campos.addWidget(QLabel('Campo Zs_f (cota solera final):'), 10, 0)
        self.cmb_zsf = QComboBox()
        grid_campos.addWidget(self.cmb_zsf, 10, 1)

        group_campos.setLayout(grid_campos)
        layout.addWidget(group_campos)

        # Nodo final (cámara final de la red)
        group_final = QGroupBox('Nodo Final de la Red')
        grid_final = QGridLayout()

        grid_final.addWidget(QLabel('ID del nodo final (Cf):'), 0, 0)
        self.txt_nodo_final = QLineEdit()
        self.txt_nodo_final.setPlaceholderText('Ej: 200')
        grid_final.addWidget(self.txt_nodo_final, 0, 1)

        btn_buscar = QPushButton('Buscar datos del nodo final')
        btn_buscar.clicked.connect(self._buscar_nodo_final)
        grid_final.addWidget(btn_buscar, 1, 0, 1, 2)

        # Mostrar datos encontrados
        self.lbl_datos_final = QLabel('Datos del nodo final: (pendiente de búsqueda)')
        self.lbl_datos_final.setWordWrap(True)
        self.lbl_datos_final.setStyleSheet('background-color: #f0f0f0; padding: 5px;')
        grid_final.addWidget(self.lbl_datos_final, 2, 0, 1, 2)

        group_final.setLayout(grid_final)
        layout.addWidget(group_final)

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

        # Conexiones
        self.cmb_tuberias.currentIndexChanged.connect(self._actualizar_campos)

        self._actualizar_campos()

        # Progreso
        self.progress = QProgressBar()
        layout.addWidget(self.progress)

        # Botones
        btn_layout = QHBoxLayout()
        btn_ejecutar = QPushButton('Ejecutar')
        btn_ejecutar.setStyleSheet('background-color: #4CAF50; color: white; font-weight: bold;')
        btn_ejecutar.clicked.connect(self.ejecutar)
        btn_cerrar = QPushButton('Cerrar')
        btn_cerrar.clicked.connect(self.dialog.close)
        btn_layout.addStretch()
        btn_layout.addWidget(btn_ejecutar)
        btn_layout.addWidget(btn_cerrar)
        layout.addLayout(btn_layout)

        self.dialog.setLayout(layout)
        self.dialog.show()

    def _cargar_capas_linea(self):
        self.cmb_tuberias.clear()
        for layer in QgsProject.instance().mapLayers().values():
            if layer.type() == QgsVectorLayer.VectorLayer and layer.geometryType() == QgsWkbTypes.LineGeometry:
                self.cmb_tuberias.addItem(layer.name(), layer.id())

    def _actualizar_campos(self):
        self.cmb_ci_virtual.clear()
        self.cmb_cf.clear()
        self.cmb_xi.clear()
        self.cmb_yi.clear()
        self.cmb_zi.clear()
        self.cmb_zsi.clear()
        self.cmb_qacu.clear()
        self.cmb_xf.clear()
        self.cmb_yf.clear()
        self.cmb_zf.clear()
        self.cmb_zsf.clear()

        layer_id = self.cmb_tuberias.currentData()
        if not layer_id:
            return

        layer = QgsProject.instance().mapLayer(layer_id)
        if not layer:
            return

        fields = [f.name() for f in layer.fields()]
        self.cmb_ci_virtual.addItems(fields)
        self.cmb_cf.addItems(fields)
        self.cmb_xi.addItems(fields)
        self.cmb_yi.addItems(fields)
        self.cmb_zi.addItems(fields)
        self.cmb_zsi.addItems(fields)
        self.cmb_qacu.addItems(fields)
        self.cmb_xf.addItems(fields)
        self.cmb_yf.addItems(fields)
        self.cmb_zf.addItems(fields)
        self.cmb_zsf.addItems(fields)

        if 'Ci_Virtual' in fields:
            self.cmb_ci_virtual.setCurrentIndex(fields.index('Ci_Virtual'))
        if 'Cf' in fields:
            self.cmb_cf.setCurrentIndex(fields.index('Cf'))
        if 'Xi' in fields:
            self.cmb_xi.setCurrentIndex(fields.index('Xi'))
        if 'Yi' in fields:
            self.cmb_yi.setCurrentIndex(fields.index('Yi'))
        if 'Zi' in fields:
            self.cmb_zi.setCurrentIndex(fields.index('Zi'))
        if 'Zs_i' in fields:
            self.cmb_zsi.setCurrentIndex(fields.index('Zs_i'))
        if 'Qacu' in fields:
            self.cmb_qacu.setCurrentIndex(fields.index('Qacu'))
        if 'Xf' in fields:
            self.cmb_xf.setCurrentIndex(fields.index('Xf'))
        if 'Yf' in fields:
            self.cmb_yf.setCurrentIndex(fields.index('Yf'))
        if 'Zf' in fields:
            self.cmb_zf.setCurrentIndex(fields.index('Zf'))
        if 'Zs_f' in fields:
            self.cmb_zsf.setCurrentIndex(fields.index('Zs_f'))

    def _buscar_nodo_final(self):
        """Busca el nodo final en el campo Cf de las tuberías"""
        layer_id = self.cmb_tuberias.currentData()
        if not layer_id:
            QMessageBox.warning(self.dialog, 'Error', 'Seleccione la capa de tuberías')
            return

        capa_tuberias = QgsProject.instance().mapLayer(layer_id)
        if not capa_tuberias:
            QMessageBox.warning(self.dialog, 'Error', 'No se encontró la capa')
            return

        nodo_final_id = self.txt_nodo_final.text().strip()
        if not nodo_final_id:
            QMessageBox.warning(self.dialog, 'Error', 'Ingrese el ID del nodo final')
            return

        # Obtener campos
        campo_cf = self.cmb_cf.currentText()
        campo_xf = self.cmb_xf.currentText()
        campo_yf = self.cmb_yf.currentText()
        campo_zf = self.cmb_zf.currentText()
        campo_zsf = self.cmb_zsf.currentText()

        # Buscar el nodo en Cf
        encontrado = False
        for feature in capa_tuberias.getFeatures():
            cf = feature.attribute(campo_cf)
            if cf and str(cf).strip() == nodo_final_id:
                xf = feature.attribute(campo_xf)
                yf = feature.attribute(campo_yf)
                zf = feature.attribute(campo_zf)
                zsf = feature.attribute(campo_zsf)
                
                self.datos_nodo_final = {
                    'x': xf,
                    'y': yf,
                    'z': zf,
                    'zs': zsf,
                    'id_tuberia': feature.attribute('ID_O')
                }
                
                # Mostrar datos
                mensaje = (
                    f'✅ Nodo final encontrado en tubería ID_O={feature.attribute("ID_O")}\n'
                    f'  • Xf: {xf}\n'
                    f'  • Yf: {yf}\n'
                    f'  • Zf: {zf}\n'
                    f'  • Zs_f: {zsf}\n'
                    f'  • Qacu: 0 (nodo final - siempre cero)'
                )
                self.lbl_datos_final.setText(mensaje)
                encontrado = True
                break

        if not encontrado:
            self.lbl_datos_final.setText(f'❌ No se encontró el nodo "{nodo_final_id}" en el campo Cf')
            self.datos_nodo_final = None
            QMessageBox.warning(self.dialog, 'Error', f'No se encontró el nodo "{nodo_final_id}" en el campo Cf')

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

    def _guardar_shapefile(self, capa, nombre):
        """Guarda una capa como shapefile"""
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

    def ejecutar(self):
        """Ejecuta el proceso principal"""
        try:
            # Validar carpeta
            if not self.ruta_salida:
                QMessageBox.warning(self.dialog, 'Error', 'Seleccione carpeta de salida')
                return

            # Obtener capa
            tuberias_id = self.cmb_tuberias.currentData()
            if not tuberias_id:
                QMessageBox.warning(self.dialog, 'Error', 'Seleccione la capa de tuberías')
                return

            capa_tuberias = QgsProject.instance().mapLayer(tuberias_id)
            if not capa_tuberias:
                QMessageBox.warning(self.dialog, 'Error', 'No se encontró la capa')
                return

            # Obtener campos
            campo_ci_virtual = self.cmb_ci_virtual.currentText()
            campo_xi = self.cmb_xi.currentText()
            campo_yi = self.cmb_yi.currentText()
            campo_zi = self.cmb_zi.currentText()
            campo_zsi = self.cmb_zsi.currentText()
            campo_qacu = self.cmb_qacu.currentText()

            if not all([campo_ci_virtual, campo_xi, campo_yi, campo_zi, campo_zsi, campo_qacu]):
                QMessageBox.warning(self.dialog, 'Error', 'Seleccione todos los campos')
                return

            # Obtener nodo final
            nodo_final_id = self.txt_nodo_final.text().strip()
            if not nodo_final_id:
                QMessageBox.warning(self.dialog, 'Error', 'Ingrese el ID del nodo final')
                return

            # Verificar que el nodo final fue encontrado
            if not hasattr(self, 'datos_nodo_final') or self.datos_nodo_final is None:
                QMessageBox.warning(self.dialog, 'Error', 'Primero busque el nodo final con el botón "Buscar datos del nodo final"')
                return

            self.progress.setValue(0)

            # ============================================
            # PASO 1: Recorrer tuberías y recolectar nodos
            # ============================================
            
            # Diccionario para almacenar nodos únicos
            nodos_dict = {}
            
            total_tuberias = capa_tuberias.featureCount()
            tuberias_procesadas = 0
            nodos_creados = 0

            for feature in capa_tuberias.getFeatures():
                # Nodo INICIO (Ci_Virtual)
                id_ci = feature.attribute(campo_ci_virtual)
                
                # Solo procesar si tiene Ci_Virtual válido
                if id_ci and str(id_ci).strip() and str(id_ci) != '-1':
                    id_str = str(id_ci)
                    
                    # Si el nodo ya existe, no sobrescribir
                    if id_str not in nodos_dict:
                        xi = feature.attribute(campo_xi)
                        yi = feature.attribute(campo_yi)
                        zi = feature.attribute(campo_zi)
                        zsi = feature.attribute(campo_zsi)
                        qacu = feature.attribute(campo_qacu)
                        
                        nodos_dict[id_str] = {
                            'x': xi,
                            'y': yi,
                            'z': zi,
                            'zs_i': zsi,
                            'qacu': qacu if qacu is not None else 0,
                            'id_tuberia': feature.attribute('ID_O')
                        }
                        nodos_creados += 1
                
                tuberias_procesadas += 1
                
                if tuberias_procesadas % 100 == 0:
                    self.progress.setValue(int((tuberias_procesadas / total_tuberias) * 60))

            self.progress.setValue(60)

            # ============================================
            # PASO 2: Agregar nodo final con datos encontrados
            # ============================================
            
            datos_final = self.datos_nodo_final
            
            if nodo_final_id not in nodos_dict:
                nodos_dict[nodo_final_id] = {
                    'x': datos_final['x'],
                    'y': datos_final['y'],
                    'z': datos_final['z'],
                    'zs_i': datos_final['zs'],
                    'qacu': 0,  # Nodo final siempre Qacu = 0
                    'id_tuberia': datos_final['id_tuberia']
                }
                nodos_creados += 1
            else:
                # Si el nodo final ya existe, actualizar con los datos encontrados
                nodos_dict[nodo_final_id]['x'] = datos_final['x']
                nodos_dict[nodo_final_id]['y'] = datos_final['y']
                nodos_dict[nodo_final_id]['z'] = datos_final['z']
                nodos_dict[nodo_final_id]['zs_i'] = datos_final['zs']
                nodos_dict[nodo_final_id]['qacu'] = 0  # Nodo final siempre Qacu = 0

            self.progress.setValue(70)

            # ============================================
            # PASO 3: Crear capa de nodos
            # ============================================
            
            crs = capa_tuberias.crs()
            
            # Crear campos
            campos = QgsFields()
            campos.append(QgsField('ID_O', QVariant.String, len=50))
            campos.append(QgsField('X', QVariant.Double))
            campos.append(QgsField('Y', QVariant.Double))
            campos.append(QgsField('Z', QVariant.Double))
            campos.append(QgsField('Zs_i', QVariant.Double))
            campos.append(QgsField('Qacu', QVariant.Double))
            campos.append(QgsField('ID_Tuberia', QVariant.Int))
            campos.append(QgsField('Es_Final', QVariant.String, len=3))

            uri = f"Point?crs={crs.authid()}&index=yes"
            capa_resultado = QgsVectorLayer(uri, 'Camaras', 'memory')
            provider = capa_resultado.dataProvider()
            provider.addAttributes(campos)
            capa_resultado.updateFields()

            nodos_agregados = 0
            for id_nodo, datos in nodos_dict.items():
                feature = QgsFeature(campos)
                
                # Crear punto
                punto = QgsPointXY(datos['x'], datos['y'])
                geom = QgsGeometry.fromPointXY(punto)
                
                es_final = 'SI' if id_nodo == nodo_final_id else 'NO'
                
                feature.setGeometry(geom)
                feature.setAttributes([
                    id_nodo,
                    round(datos['x'], 3) if datos['x'] is not None else 0,
                    round(datos['y'], 3) if datos['y'] is not None else 0,
                    round(datos['z'], 3) if datos['z'] is not None else -9999,
                    round(datos['zs_i'], 3) if datos['zs_i'] is not None else -9999,
                    round(datos['qacu'], 3) if datos['qacu'] is not None else 0,
                    datos['id_tuberia'] if datos['id_tuberia'] is not None else 0,
                    es_final
                ])
                
                provider.addFeature(feature)
                nodos_agregados += 1

            capa_resultado.updateFields()
            capa_resultado.commitChanges()

            self.progress.setValue(85)

            # ============================================
            # PASO 4: GUARDAR SHAPEFILE
            # ============================================
            
            ruta = self._guardar_shapefile(capa_resultado, 'Camaras')

            if not ruta:
                QMessageBox.warning(self.dialog, 'Error', 'No se pudo guardar el archivo')
                return

            self.progress.setValue(100)

            # Agregar capa al proyecto
            capa_guardada = QgsVectorLayer(ruta, "Camaras", "ogr")
            QgsProject.instance().addMapLayer(capa_guardada)

            # ============================================
            # RESUMEN
            # ============================================
            
            mensaje = (
                f'✅ PROCESO COMPLETADO\n\n'
                f'📊 Resumen:\n'
                f'  • Tuberías procesadas: {tuberias_procesadas}\n'
                f'  • Nodos generados desde Ci_Virtual: {nodos_agregados - 1}\n'
                f'  • Nodo final: {nodo_final_id} (Qacu = 0)\n'
                f'  • Total nodos: {nodos_agregados}\n\n'
                f'📌 Campos generados:\n'
                f'  • ID_O: Identificador del nodo (Ci_Virtual)\n'
                f'  • X, Y: Coordenadas del punto\n'
                f'  • Z: Cota del nodo\n'
                f'  • Zs_i: Cota solera del nodo\n'
                f'  • Qacu: Caudal acumulado (0 para nodo final)\n'
                f'  • ID_Tuberia: ID de la tubería origen\n'
                f'  • Es_Final: "SI" si es el nodo final\n\n'
                f'📁 Archivo guardado en:\n'
                f'  {ruta}'
            )

            QMessageBox.information(self.dialog, 'Completado', mensaje)

            self.dialog.close()

        except Exception as e:
            QMessageBox.critical(self.dialog, 'Error', f'Error: {str(e)}')
            import traceback
            traceback.print_exc()

    def desactivar(self):
        pass