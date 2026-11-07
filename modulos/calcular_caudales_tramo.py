# -*- coding: utf-8 -*-
"""
Módulo: calcular_caudales_tramo
Versión: 1.1
Propósito: Calcular caudales por tramo y crear nuevo shapefile con la columna añadida
"""

from qgis.PyQt.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QPushButton, 
    QLabel, QComboBox, QMessageBox, QProgressBar,
    QLineEdit, QGroupBox, QGridLayout, QCheckBox,
    QFileDialog
)
from qgis.PyQt.QtCore import Qt, QVariant
from qgis.core import (
    QgsProject, QgsVectorLayer, QgsField, QgsFeature,
    QgsGeometry, QgsWkbTypes, QgsFields,
    QgsVectorFileWriter
)
import os

class CalcularCaudalesTramo:
    def __init__(self, iface):
        self.iface = iface
        self.dialog = None
        self.debug = False
        self.ruta_salida = None

    def mostrar_dialogo(self):
        """Muestra el diálogo principal"""
        self.dialog = QDialog(self.iface.mainWindow())
        self.dialog.setWindowTitle('GLC - Calcular Caudales por Tramo')
        self.dialog.setMinimumWidth(700)
        
        layout = QVBoxLayout()

        # Descripción
        lbl_desc = QLabel(
            '<b>Calcular Caudales por Tramo</b>\n\n'
            '📌 Crea un nuevo shapefile con las columnas:\n'
            '   • Caudal_Tramo: Caudal que circula por el tramo (LPS)\n'
            '   • Sumatoria: Caudal acumulado que sale del tramo (LPS)\n\n'
            '📌 La cámara final se detecta automáticamente con fin = 1\n\n'
            '📌 REGLA:\n'
            '   • Cabeza (Arranque) → Caudal_Tramo = Qdiseno, Sumatoria = Qdiseno\n'
            '   • Tramo siguiente → Sumatoria_Que_Llega = SUMA(Sumatorias de tuberías que llegan al nodo)\n'
            '   • Caudal_Tramo = Qdiseno - Sumatoria_Que_Llega\n'
            '   • Sumatoria = Sumatoria_Que_Llega + Caudal_Tramo'
        )
        lbl_desc.setWordWrap(True)
        layout.addWidget(lbl_desc)

        # Selección de capas
        group_capas = QGroupBox('Capas de entrada')
        grid_capas = QGridLayout()

        grid_capas.addWidget(QLabel('Tuberías (GLC_Tuberias o Virtuales):'), 0, 0)
        self.cmb_tuberias = QComboBox()
        self._cargar_capas_linea()
        grid_capas.addWidget(self.cmb_tuberias, 0, 1)

        grid_capas.addWidget(QLabel('Cámaras (GLC_Camaras):'), 1, 0)
        self.cmb_camaras = QComboBox()
        self._cargar_capas_punto()
        grid_capas.addWidget(self.cmb_camaras, 1, 1)

        # Mostrar la cámara final detectada
        self.label_camara_final = QLabel('🔍 Buscando cámara final...')
        self.label_camara_final.setStyleSheet('background-color: #e3f2fd; padding: 8px; border-radius: 4px;')
        grid_capas.addWidget(self.label_camara_final, 2, 0, 1, 2)

        group_capas.setLayout(grid_capas)
        layout.addWidget(group_capas)

        # Selección de campos - Tuberías
        group_campos_tuberias = QGroupBox('Campos en Tuberías')
        grid_tuberias = QGridLayout()

        grid_tuberias.addWidget(QLabel('ID_O:'), 0, 0)
        self.cmb_id_tuberia = QComboBox()
        grid_tuberias.addWidget(self.cmb_id_tuberia, 0, 1)

        grid_tuberias.addWidget(QLabel('Ci (nodo inicio):'), 1, 0)
        self.cmb_ci = QComboBox()
        grid_tuberias.addWidget(self.cmb_ci, 1, 1)

        grid_tuberias.addWidget(QLabel('Cf (nodo final):'), 2, 0)
        self.cmb_cf = QComboBox()
        grid_tuberias.addWidget(self.cmb_cf, 2, 1)

        grid_tuberias.addWidget(QLabel('Qdiseno (caudal de diseño):'), 3, 0)
        self.cmb_qdiseno = QComboBox()
        grid_tuberias.addWidget(self.cmb_qdiseno, 3, 1)

        grid_tuberias.addWidget(QLabel('cab_ata:'), 4, 0)
        self.cmb_cab_ata = QComboBox()
        grid_tuberias.addWidget(self.cmb_cab_ata, 4, 1)

        group_campos_tuberias.setLayout(grid_tuberias)
        layout.addWidget(group_campos_tuberias)

        # Selección de campos - Cámaras
        group_campos_camaras = QGroupBox('Campos en Cámaras')
        grid_camaras = QGridLayout()

        grid_camaras.addWidget(QLabel('ID_O:'), 0, 0)
        self.cmb_id_camara = QComboBox()
        grid_camaras.addWidget(self.cmb_id_camara, 0, 1)

        grid_camaras.addWidget(QLabel('Lineas_ID:'), 1, 0)
        self.cmb_lineas_id = QComboBox()
        grid_camaras.addWidget(self.cmb_lineas_id, 1, 1)

        grid_camaras.addWidget(QLabel('fin (cámara final):'), 2, 0)
        self.cmb_fin = QComboBox()
        grid_camaras.addWidget(self.cmb_fin, 2, 1)

        group_campos_camaras.setLayout(grid_camaras)
        layout.addWidget(group_campos_camaras)

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

        # Opciones
        group_opciones = QGroupBox('Opciones')
        grid_opciones = QGridLayout()

        self.chk_debug = QCheckBox('Modo Debug (mostrar mensajes)')
        grid_opciones.addWidget(self.chk_debug, 0, 0)

        group_opciones.setLayout(grid_opciones)
        layout.addWidget(group_opciones)

        # Barra de progreso
        self.progress = QProgressBar()
        layout.addWidget(self.progress)

        # Botones
        btn_layout = QHBoxLayout()
        btn_ejecutar = QPushButton('Calcular Caudales')
        btn_ejecutar.setStyleSheet('background-color: #4CAF50; color: white; font-weight: bold;')
        btn_ejecutar.clicked.connect(self.ejecutar)
        btn_cerrar = QPushButton('Cerrar')
        btn_cerrar.clicked.connect(self.dialog.close)
        btn_layout.addStretch()
        btn_layout.addWidget(btn_ejecutar)
        btn_layout.addWidget(btn_cerrar)
        layout.addLayout(btn_layout)

        # Conexiones
        self.cmb_tuberias.currentIndexChanged.connect(self._actualizar_campos_tuberias)
        self.cmb_camaras.currentIndexChanged.connect(self._actualizar_campos_camaras)
        self.cmb_camaras.currentIndexChanged.connect(self._buscar_camara_final)

        self._actualizar_campos_tuberias()
        self._actualizar_campos_camaras()

        self.dialog.setLayout(layout)
        self.dialog.show()
        
        # Buscar cámara final automáticamente al mostrar
        self._buscar_camara_final()

    def _cargar_capas_linea(self):
        self.cmb_tuberias.clear()
        for layer in QgsProject.instance().mapLayers().values():
            if layer.type() == QgsVectorLayer.VectorLayer and layer.geometryType() == QgsWkbTypes.LineGeometry:
                self.cmb_tuberias.addItem(layer.name(), layer.id())

    def _cargar_capas_punto(self):
        self.cmb_camaras.clear()
        for layer in QgsProject.instance().mapLayers().values():
            if layer.type() == QgsVectorLayer.VectorLayer and layer.geometryType() == QgsWkbTypes.PointGeometry:
                self.cmb_camaras.addItem(layer.name(), layer.id())

    def _buscar_camara_final(self):
        """Buscar la cámara final (fin = 1) en la capa de cámaras"""
        layer_id = self.cmb_camaras.currentData()
        if not layer_id:
            self.label_camara_final.setText('❌ Seleccione una capa de cámaras')
            self.label_camara_final.setStyleSheet('background-color: #ffcdd2; padding: 8px; border-radius: 4px;')
            self.id_final = None
            return

        layer = QgsProject.instance().mapLayer(layer_id)
        if not layer:
            self.label_camara_final.setText('❌ No se encontró la capa')
            self.label_camara_final.setStyleSheet('background-color: #ffcdd2; padding: 8px; border-radius: 4px;')
            self.id_final = None
            return

        # Verificar si existe el campo 'fin'
        idx_fin = layer.fields().indexFromName('fin')
        if idx_fin == -1:
            self.label_camara_final.setText('⚠️ La capa no tiene el campo "fin". Usa "Asignar Cámara Final" primero.')
            self.label_camara_final.setStyleSheet('background-color: #fff3e0; padding: 8px; border-radius: 4px;')
            self.id_final = None
            return

        # Buscar la cámara con fin = 1
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
                self.label_camara_final.setStyleSheet('background-color: #c8e6c9; padding: 8px; border-radius: 4px;')
            else:
                self.label_camara_final.setText(f'✅ Cámara final: ID_O={id_o}')
                self.label_camara_final.setStyleSheet('background-color: #c8e6c9; padding: 8px; border-radius: 4px;')
        else:
            self.label_camara_final.setText('❌ No hay cámara con fin = 1. Usa "Asignar Cámara Final" primero.')
            self.label_camara_final.setStyleSheet('background-color: #ffcdd2; padding: 8px; border-radius: 4px;')
            self.id_final = None

    def _actualizar_campos_tuberias(self):
        self.cmb_id_tuberia.clear()
        self.cmb_ci.clear()
        self.cmb_cf.clear()
        self.cmb_qdiseno.clear()
        self.cmb_cab_ata.clear()

        layer_id = self.cmb_tuberias.currentData()
        if not layer_id:
            return

        layer = QgsProject.instance().mapLayer(layer_id)
        if not layer:
            return

        fields = [f.name() for f in layer.fields()]
        self.cmb_id_tuberia.addItems(fields)
        self.cmb_ci.addItems(fields)
        self.cmb_cf.addItems(fields)
        self.cmb_qdiseno.addItems(fields)
        self.cmb_cab_ata.addItems(fields)

        if 'ID_O' in fields:
            self.cmb_id_tuberia.setCurrentIndex(fields.index('ID_O'))
        if 'Ci' in fields:
            self.cmb_ci.setCurrentIndex(fields.index('Ci'))
        if 'Cf' in fields:
            self.cmb_cf.setCurrentIndex(fields.index('Cf'))
        if 'Qdiseno' in fields:
            self.cmb_qdiseno.setCurrentIndex(fields.index('Qdiseno'))
        if 'cab_ata' in fields:
            self.cmb_cab_ata.setCurrentIndex(fields.index('cab_ata'))

    def _actualizar_campos_camaras(self):
        self.cmb_id_camara.clear()
        self.cmb_lineas_id.clear()
        self.cmb_fin.clear()

        layer_id = self.cmb_camaras.currentData()
        if not layer_id:
            return

        layer = QgsProject.instance().mapLayer(layer_id)
        if not layer:
            return

        fields = [f.name() for f in layer.fields()]
        self.cmb_id_camara.addItems(fields)
        self.cmb_lineas_id.addItems(fields)
        self.cmb_fin.addItems(fields)

        if 'ID_O' in fields:
            self.cmb_id_camara.setCurrentIndex(fields.index('ID_O'))
        if 'Lineas_ID' in fields:
            self.cmb_lineas_id.setCurrentIndex(fields.index('Lineas_ID'))
        if 'fin' in fields:
            self.cmb_fin.setCurrentIndex(fields.index('fin'))

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
        """Ejecuta el cálculo de caudales por tramo"""
        try:
            # Validar carpeta
            if not self.ruta_salida:
                QMessageBox.warning(self.dialog, 'Error', 'Seleccione carpeta de salida')
                return

            # Obtener capas
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

            # Obtener cámara final automática
            id_final = self.id_final
            
            if id_final is None:
                QMessageBox.warning(
                    self.dialog,
                    'Error',
                    'No se encontró una cámara final con fin = 1.\n'
                    'Usa el módulo "Asignar Cámara Final" primero.'
                )
                return

            # Obtener campos
            campo_id_tuberia = self.cmb_id_tuberia.currentText()
            campo_ci = self.cmb_ci.currentText()
            campo_cf = self.cmb_cf.currentText()
            campo_qdiseno = self.cmb_qdiseno.currentText()
            campo_cab_ata = self.cmb_cab_ata.currentText()

            campo_id_camara = self.cmb_id_camara.currentText()
            campo_lineas_id = self.cmb_lineas_id.currentText()

            if not all([campo_id_tuberia, campo_ci, campo_cf, campo_qdiseno, campo_cab_ata]):
                QMessageBox.warning(self.dialog, 'Error', 'Seleccione todos los campos de tuberías')
                return

            if not all([campo_id_camara, campo_lineas_id]):
                QMessageBox.warning(self.dialog, 'Error', 'Seleccione todos los campos de cámaras')
                return

            self.debug = self.chk_debug.isChecked()

            self.progress.setValue(0)

            # ============================================
            # PASO 1: Construir diccionarios
            # ============================================
            
            tuberias_dict = {}
            for feature in capa_tuberias.getFeatures():
                id_o = feature.attribute(campo_id_tuberia)
                if id_o is None:
                    continue
                
                cab_ata_valor = feature.attribute(campo_cab_ata) or ''
                
                tuberias_dict[id_o] = {
                    'id_o': id_o,
                    'ci': feature.attribute(campo_ci),
                    'cf': feature.attribute(campo_cf),
                    'qdiseno': feature.attribute(campo_qdiseno) or 0,
                    'cab_ata': cab_ata_valor,
                    'feature': feature,
                    'procesado': False,
                    'caudal_tramo': 0.0,
                    'sumatoria': 0.0
                }

            self.progress.setValue(20)

            # Diccionario de cámaras
            camaras_dict = {}
            for feature in capa_camaras.getFeatures():
                id_o = feature.attribute(campo_id_camara)
                if id_o is None:
                    continue
                
                lineas_id_str = feature.attribute(campo_lineas_id) or ''
                lineas_list = []
                if lineas_id_str:
                    try:
                        parts = str(lineas_id_str).split(',')
                        for p in parts:
                            p_clean = p.strip()
                            if p_clean and p_clean.isdigit():
                                lineas_list.append(int(p_clean))
                    except:
                        pass
                
                camaras_dict[id_o] = {
                    'id_o': id_o,
                    'lineas': lineas_list,
                    'feature': feature
                }

            self.progress.setValue(30)

            if id_final not in camaras_dict:
                QMessageBox.warning(self.dialog, 'Error', f'No se encontró la cámara {id_final}')
                return

            self.progress.setValue(40)

            # ============================================
            # PASO 2: Encontrar cabezas (Arranque)
            # ============================================
            
            cabezas = []
            for id_tuberia, datos in tuberias_dict.items():
                if datos['cab_ata'] == 'Arranque':
                    cabezas.append(id_tuberia)

            if not cabezas:
                QMessageBox.warning(self.dialog, 'Error', 'No se encontraron tuberías con cab_ata="Arranque"')
                return

            if self.debug:
                print("\n" + "="*60)
                print("CABEZAS ENCONTRADAS:")
                for c in cabezas:
                    print(f"  • Tubería {c}")

            self.progress.setValue(50)

            # ============================================
            # PASO 3: Procesar todas las tuberías (iterativo)
            # ============================================
            
            # Primero, procesar todas las cabezas
            for id_cabeza in cabezas:
                if id_cabeza in tuberias_dict:
                    tuberia = tuberias_dict[id_cabeza]
                    tuberia['caudal_tramo'] = tuberia['qdiseno']
                    tuberia['sumatoria'] = tuberia['qdiseno']
                    tuberia['procesado'] = True
                    
                    if self.debug:
                        print(f"\n🔹 CABEZA: Tubería {id_cabeza}")
                        print(f"   Qdiseno: {tuberia['qdiseno']:.3f} LPS")
                        print(f"   Caudal_Tramo: {tuberia['caudal_tramo']:.3f} LPS")
                        print(f"   Sumatoria: {tuberia['sumatoria']:.3f} LPS")

            self.progress.setValue(60)

            # Luego, procesar iterativamente las tuberías restantes
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
                    sumatoria_total_que_llega = 0
                    
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
                        
                        if self.debug:
                            print(f"\n📌 Tubería {id_tuberia}")
                            print(f"   Ci: {ci}")
                            print(f"   Qdiseno: {tuberia['qdiseno']:.3f} LPS")
                            print(f"   Sumatoria total que llega: {sumatoria_total_que_llega:.3f} LPS")
                            print(f"   Caudal_Tramo: {caudal_tramo:.3f} LPS")
                            print(f"   Sumatoria: {tuberia['sumatoria']:.3f} LPS")
                
                if not algo_procesado:
                    break

            self.progress.setValue(80)

            # ============================================
            # PASO 4: Crear nueva capa
            # ============================================
            
            crs = capa_tuberias.crs()
            
            campos = QgsFields(capa_tuberias.fields())
            campos.append(QgsField('Caudal_Tramo', QVariant.Double))
            campos.append(QgsField('Sumatoria', QVariant.Double))

            uri_line = f"LineString?crs={crs.authid()}&index=yes"
            capa_resultado = QgsVectorLayer(uri_line, 'Tuberias_Caudales', 'memory')
            provider = capa_resultado.dataProvider()
            provider.addAttributes(campos)
            capa_resultado.updateFields()

            tuberias_procesadas = 0

            for id_tuberia, datos in tuberias_dict.items():
                feature = datos['feature']
                
                nueva_feature = QgsFeature(campos)
                atributos = list(feature.attributes())
                atributos.append(round(datos['caudal_tramo'], 3))
                atributos.append(round(datos['sumatoria'], 3))
                
                nueva_feature.setAttributes(atributos)
                nueva_feature.setGeometry(feature.geometry())
                provider.addFeature(nueva_feature)
                tuberias_procesadas += 1

            capa_resultado.updateFields()
            capa_resultado.commitChanges()

            self.progress.setValue(90)

            # ============================================
            # PASO 5: GUARDAR
            # ============================================
            
            nombre_base = capa_tuberias.name()
            nombre_salida = f"{nombre_base}_Caudales"
            
            ruta = self._guardar_shapefile(capa_resultado, nombre_salida)

            if not ruta:
                QMessageBox.warning(self.dialog, 'Error', 'No se pudo guardar el archivo')
                return

            self.progress.setValue(100)

            capa_guardada = QgsVectorLayer(ruta, nombre_salida, "ogr")
            QgsProject.instance().addMapLayer(capa_guardada)

            # ============================================
            # RESUMEN
            # ============================================
            
            procesadas = sum(1 for d in tuberias_dict.values() if d['procesado'])
            
            mensaje = (
                f'✅ PROCESO COMPLETADO\n\n'
                f'📊 Resumen:\n'
                f'  • Tuberías procesadas: {procesadas} de {tuberias_procesadas}\n'
                f'  • Cabezas de atarjea (Arranque): {len(cabezas)}\n'
                f'  • Cámara final (automática): ID_O={id_final}\n\n'
                f'📌 Columnas añadidas:\n'
                f'  • Caudal_Tramo: Caudal que circula por el tramo (LPS)\n'
                f'  • Sumatoria: Caudal acumulado que sale del tramo (LPS)\n\n'
                f'📌 REGLA:\n'
                f'  • Cabeza (Arranque) → Caudal_Tramo = Qdiseno, Sumatoria = Qdiseno\n'
                f'  • Siguiente → Sumatoria_Que_Llega = SUMA(Sumatorias de tuberías que llegan al nodo)\n'
                f'  • Caudal_Tramo = Qdiseno - Sumatoria_Que_Llega\n'
                f'  • Sumatoria = Sumatoria_Que_Llega + Caudal_Tramo\n\n'
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