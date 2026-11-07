# -*- coding: utf-8 -*-
"""
Módulo: crear_camaras_virtuales
Versión: 1.0
Propósito: Crear shapefile de TUBERÍAS con IDs virtuales para EPA SWMM
SOLO cambia Ci en tuberías con cab_ata = "Arranque"
Y renombra Ci_Virtual duplicados con letras únicas (a, b, c, ...)
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
    QgsVectorFileWriter, QgsCoordinateReferenceSystem
)
import os

class CrearCamarasVirtuales:
    def __init__(self, iface):
        self.iface = iface
        self.dialog = None
        self.ruta_salida = None

    def mostrar_dialogo(self):
        """Muestra el diálogo principal"""
        self.dialog = QDialog(self.iface.mainWindow())
        self.dialog.setWindowTitle('Crear Cámaras Virtuales para SWMM')
        self.dialog.setMinimumWidth(600)
        
        layout = QVBoxLayout()

        # Descripción
        lbl_desc = QLabel(
            '<b>Crear Cámaras Virtuales para EPA SWMM</b>\n\n'
            '📌 REGLA:\n'
            '   • Busca tuberías con cab_ata = "Arranque"\n'
            '   • Cambia su Ci por Ci + "v" (ej: 100 → 100v)\n'
            '   • Si hay Ci_Virtual duplicados, los renombra con letras\n'
            '   • Ejemplo: 100v, 100v → 100va, 100vb\n\n'
            '📌 Se crea UN SOLO shapefile: Tuberias_Virtuales.shp'
        )
        lbl_desc.setWordWrap(True)
        layout.addWidget(lbl_desc)

        # Selección de capas
        group_capas = QGroupBox('Capas de entrada')
        grid_capas = QGridLayout()

        grid_capas.addWidget(QLabel('Tuberías:'), 0, 0)
        self.cmb_tuberias = QComboBox()
        self._cargar_capas_linea()
        grid_capas.addWidget(self.cmb_tuberias, 0, 1)

        group_capas.setLayout(grid_capas)
        layout.addWidget(group_capas)

        # Selección de campos
        group_campos = QGroupBox('Campos')
        grid_campos = QGridLayout()

        grid_campos.addWidget(QLabel('Campo ID Tubería:'), 0, 0)
        self.cmb_id_tuberia = QComboBox()
        grid_campos.addWidget(self.cmb_id_tuberia, 0, 1)

        grid_campos.addWidget(QLabel('Campo Ci:'), 1, 0)
        self.cmb_ci = QComboBox()
        grid_campos.addWidget(self.cmb_ci, 1, 1)

        grid_campos.addWidget(QLabel('Campo Cf:'), 2, 0)
        self.cmb_cf = QComboBox()
        grid_campos.addWidget(self.cmb_cf, 2, 1)

        grid_campos.addWidget(QLabel('Campo cab_ata:'), 3, 0)
        self.cmb_cab_ata = QComboBox()
        grid_campos.addWidget(self.cmb_cab_ata, 3, 1)

        group_campos.setLayout(grid_campos)
        layout.addWidget(group_campos)

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
        self.cmb_id_tuberia.clear()
        self.cmb_ci.clear()
        self.cmb_cf.clear()
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
        self.cmb_cab_ata.addItems(fields)

        if 'ID_O' in fields:
            self.cmb_id_tuberia.setCurrentIndex(fields.index('ID_O'))
        if 'Ci' in fields:
            self.cmb_ci.setCurrentIndex(fields.index('Ci'))
        if 'Cf' in fields:
            self.cmb_cf.setCurrentIndex(fields.index('Cf'))
        if 'cab_ata' in fields:
            self.cmb_cab_ata.setCurrentIndex(fields.index('cab_ata'))

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
        """Guarda una capa como shapefile (método de copiar_red.py)"""
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

    def _renombrar_duplicados(self, lista_virtuales):
        """
        Recibe una lista de Ci_Virtual y renombra los duplicados con letras
        Ejemplo: ['100v', '100v', '200v'] → ['100va', '100vb', '200v']
        """
        # Contar ocurrencias de cada valor
        conteo = {}
        for valor in lista_virtuales:
            if valor and valor != '':
                if valor not in conteo:
                    conteo[valor] = 0
                conteo[valor] += 1
        
        # Si no hay duplicados, retornar la lista original
        duplicados = {k: v for k, v in conteo.items() if v > 1}
        if not duplicados:
            return lista_virtuales
        
        # Renombrar duplicados
        contadores = {k: 0 for k in duplicados.keys()}
        letras = 'abcdefghijklmnopqrstuvwxyz'
        resultado = []
        
        for valor in lista_virtuales:
            if valor in duplicados:
                # Asignar letra
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
            campo_id = self.cmb_id_tuberia.currentText()
            campo_ci = self.cmb_ci.currentText()
            campo_cf = self.cmb_cf.currentText()
            campo_cab_ata = self.cmb_cab_ata.currentText()

            if not all([campo_id, campo_ci, campo_cf, campo_cab_ata]):
                QMessageBox.warning(self.dialog, 'Error', 'Seleccione todos los campos')
                return

            self.progress.setValue(0)

            # ============================================
            # PASO 1: Preparar nueva capa (MEMORIA)
            # ============================================
            
            crs = capa_tuberias.crs()
            
            # Crear campos (copiar originales + agregar Ci_Virtual)
            campos = QgsFields(capa_tuberias.fields())
            campos.append(QgsField('Ci_Virtual', QVariant.String, len=50))

            uri_line = f"LineString?crs={crs.authid()}&index=yes"
            capa_resultado = QgsVectorLayer(uri_line, 'Tuberias_Virtuales', 'memory')
            provider = capa_resultado.dataProvider()
            provider.addAttributes(campos)
            capa_resultado.updateFields()

            self.progress.setValue(20)

            # ============================================
            # PASO 2: Recorrer tuberías y recolectar Ci_Virtual
            # ============================================
            
            total_tuberias = capa_tuberias.featureCount()
            tuberias_procesadas = 0
            tuberias_modificadas = 0
            
            # Lista para almacenar Ci_Virtual temporalmente
            lista_virtuales = []
            # Lista para almacenar features temporalmente
            features_temporales = []

            for feature in capa_tuberias.getFeatures():
                id_tuberia = feature.attribute(campo_id)
                ci_original = feature.attribute(campo_ci)
                cab_ata = feature.attribute(campo_cab_ata) or ''
                
                # Copiar atributos originales
                atributos = list(feature.attributes())
                
                # Determinar Ci_Virtual
                if cab_ata == 'Arranque' and ci_original is not None:
                    ci_virtual = f"{ci_original}v"
                    tuberias_modificadas += 1
                else:
                    ci_virtual = str(ci_original) if ci_original is not None else ''
                
                # Guardar para procesar después
                lista_virtuales.append(ci_virtual)
                features_temporales.append({
                    'atributos': atributos,
                    'geometria': feature.geometry(),
                    'ci_virtual': ci_virtual
                })
                
                tuberias_procesadas += 1
                
                if tuberias_procesadas % 100 == 0:
                    self.progress.setValue(int(20 + (tuberias_procesadas / total_tuberias) * 40))

            self.progress.setValue(60)

            # ============================================
            # PASO 3: Renombrar duplicados
            # ============================================
            
            lista_virtuales_renombrados = self._renombrar_duplicados(lista_virtuales)
            
            # Contar cuántos fueron renombrados
            renombrados = 0
            for i, (original, nuevo) in enumerate(zip(lista_virtuales, lista_virtuales_renombrados)):
                if original != nuevo and original != '':
                    renombrados += 1

            self.progress.setValue(70)

            # ============================================
            # PASO 4: Crear features con los nuevos nombres
            # ============================================
            
            for i, datos in enumerate(features_temporales):
                atributos = datos['atributos']
                ci_virtual_renombrado = lista_virtuales_renombrados[i]
                
                # Agregar Ci_Virtual renombrado al final
                atributos.append(ci_virtual_renombrado)
                
                # Crear nueva feature
                nueva_feature = QgsFeature(campos)
                nueva_feature.setAttributes(atributos)
                nueva_feature.setGeometry(datos['geometria'])
                provider.addFeature(nueva_feature)

            capa_resultado.updateFields()
            capa_resultado.commitChanges()

            self.progress.setValue(80)

            # ============================================
            # PASO 5: GUARDAR SHAPEFILE
            # ============================================
            
            ruta = self._guardar_shapefile(capa_resultado, 'Tuberias_Virtuales')

            if not ruta:
                QMessageBox.warning(self.dialog, 'Error', 'No se pudo guardar el archivo')
                return

            self.progress.setValue(100)

            # Agregar capa al proyecto (cargar desde el archivo guardado)
            capa_guardada = QgsVectorLayer(ruta, "Tuberias_Virtuales", "ogr")
            QgsProject.instance().addMapLayer(capa_guardada)

            # ============================================
            # RESUMEN
            # ============================================
            
            mensaje = (
                f'✅ PROCESO COMPLETADO\n\n'
                f'📊 Resumen:\n'
                f'  • Tuberías procesadas: {tuberias_procesadas}\n'
                f'  • Tuberías modificadas (cab_ata="Arranque"): {tuberias_modificadas}\n'
                f'  • Ci_Virtual renombrados (duplicados): {renombrados}\n\n'
                f'📌 REGLA:\n'
                f'  • Si cab_ata = "Arranque" → Ci se convierte en Ci + "v"\n'
                f'  • Ejemplo: 100 → 100v\n'
                f'  • Si hay duplicados: 100v, 100v → 100va, 100vb\n'
                f'  • Si NO es "Arranque" → mantiene su Ci original\n\n'
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