# -*- coding: utf-8 -*-
"""
Módulo: generar_caudales_estocasticos
Versión: 2.0 (Simplificada)
Propósito: Distribuir pulsos estocásticos de 1.5 LPS en las tuberías
"""

from qgis.PyQt.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QPushButton, 
    QLabel, QComboBox, QMessageBox, QProgressBar,
    QLineEdit, QGroupBox, QGridLayout, QFileDialog,
    QSpinBox, QDoubleSpinBox, QCheckBox
)
from qgis.PyQt.QtCore import Qt, QVariant
from qgis.core import (
    QgsProject, QgsVectorLayer, QgsField, QgsFeature,
    QgsGeometry, QgsWkbTypes, QgsFields,
    QgsVectorFileWriter
)
import os
import random

class GenerarCaudalesEstocasticos:
    def __init__(self, iface):
        self.iface = iface
        self.dialog = None
        self.ruta_salida = None
        self.debug = False

    def mostrar_dialogo(self):
        """Muestra el diálogo principal"""
        self.dialog = QDialog(self.iface.mainWindow())
        self.dialog.setWindowTitle('GLC - Generar Caudales Estocásticos (Pulsos)')
        self.dialog.setMinimumWidth(650)
        
        layout = QVBoxLayout()

        # Descripción
        lbl_desc = QLabel(
            '<b>Generar Caudales Estocásticos (Pulsos Instantáneos)</b>\n\n'
            '📌 Distribuye pulsos de 1.5 LPS en las tuberías de forma estocástica:\n'
            '   • Cada tubería tiene una probabilidad de recibir un pulso\n'
            '   • Los pulsos se distribuyen aleatoriamente\n'
            '   • Las tuberías con Qbase = 0 pueden recibir pulsos\n\n'
            '📌 Salida: Shapefile con columna "Q_estocastico"'
        )
        lbl_desc.setWordWrap(True)
        layout.addWidget(lbl_desc)

        # Selección de capas
        group_capas = QGroupBox('Capas de entrada')
        grid_capas = QGridLayout()

        grid_capas.addWidget(QLabel('Tuberías (con Qacu):'), 0, 0)
        self.cmb_tuberias = QComboBox()
        self._cargar_capas_linea()
        grid_capas.addWidget(self.cmb_tuberias, 0, 1)

        group_capas.setLayout(grid_capas)
        layout.addWidget(group_capas)

        # Parámetros estocásticos
        group_parametros = QGroupBox('Parámetros de Distribución')
        grid_parametros = QGridLayout()

        # Caudal del pulso
        grid_parametros.addWidget(QLabel('Caudal del pulso (LPS):'), 0, 0)
        self.spin_qpulso = QDoubleSpinBox()
        self.spin_qpulso.setRange(0.1, 10.0)
        self.spin_qpulso.setValue(1.5)
        self.spin_qpulso.setSingleStep(0.1)
        grid_parametros.addWidget(self.spin_qpulso, 0, 1)

        # Probabilidad de recibir pulso (%)
        grid_parametros.addWidget(QLabel('Probabilidad de recibir pulso (%):'), 1, 0)
        self.spin_probabilidad = QSpinBox()
        self.spin_probabilidad.setRange(0, 100)
        self.spin_probabilidad.setValue(30)
        grid_parametros.addWidget(self.spin_probabilidad, 1, 1)

        # Número mínimo de pulsos
        grid_parametros.addWidget(QLabel('Número mínimo de pulsos:'), 2, 0)
        self.spin_min_pulsos = QSpinBox()
        self.spin_min_pulsos.setRange(0, 100)
        self.spin_min_pulsos.setValue(0)
        grid_parametros.addWidget(self.spin_min_pulsos, 2, 1)

        # Número máximo de pulsos
        grid_parametros.addWidget(QLabel('Número máximo de pulsos:'), 3, 0)
        self.spin_max_pulsos = QSpinBox()
        self.spin_max_pulsos.setRange(0, 1000)
        self.spin_max_pulsos.setValue(50)
        grid_parametros.addWidget(self.spin_max_pulsos, 3, 1)

        # Modo de distribución
        grid_parametros.addWidget(QLabel('Modo de distribución:'), 4, 0)
        self.cmb_modo = QComboBox()
        self.cmb_modo.addItems(['Uniforme', 'Poisson', 'Binomial'])
        grid_parametros.addWidget(self.cmb_modo, 4, 1)

        # Semilla aleatoria
        grid_parametros.addWidget(QLabel('Semilla aleatoria (0 = aleatorio):'), 5, 0)
        self.spin_semilla = QSpinBox()
        self.spin_semilla.setRange(0, 9999)
        self.spin_semilla.setValue(0)
        grid_parametros.addWidget(self.spin_semilla, 5, 1)

        group_parametros.setLayout(grid_parametros)
        layout.addWidget(group_parametros)

        # Opciones de salida
        group_salida = QGroupBox('Opciones de Salida')
        grid_salida_opciones = QGridLayout()

        self.chk_agregar_qbase = QCheckBox('Sumar Qbase + Qpulso (si no, solo Qpulso)')
        self.chk_agregar_qbase.setChecked(True)
        grid_salida_opciones.addWidget(self.chk_agregar_qbase, 0, 0)

        self.chk_guardar_copia = QCheckBox('Guardar como nueva capa (no modificar original)')
        self.chk_guardar_copia.setChecked(True)
        grid_salida_opciones.addWidget(self.chk_guardar_copia, 0, 1)

        self.chk_debug = QCheckBox('Modo Debug')
        grid_salida_opciones.addWidget(self.chk_debug, 1, 0, 1, 2)

        group_salida.setLayout(grid_salida_opciones)
        layout.addWidget(group_salida)

        # Carpeta de salida
        group_archivo = QGroupBox('Carpeta de salida')
        grid_archivo = QGridLayout()

        self.txt_ruta = QLineEdit()
        self.txt_ruta.setReadOnly(True)
        grid_archivo.addWidget(self.txt_ruta, 0, 0)

        btn_ruta = QPushButton('Seleccionar Carpeta...')
        btn_ruta.clicked.connect(self._seleccionar_carpeta)
        grid_archivo.addWidget(btn_ruta, 0, 1)

        btn_proyecto = QPushButton('Usar carpeta del proyecto')
        btn_proyecto.clicked.connect(self._usar_carpeta_proyecto)
        grid_archivo.addWidget(btn_proyecto, 1, 0, 1, 2)

        group_archivo.setLayout(grid_archivo)
        layout.addWidget(group_archivo)

        # Barra de progreso
        self.progress = QProgressBar()
        layout.addWidget(self.progress)

        # Botones
        btn_layout = QHBoxLayout()
        btn_ejecutar = QPushButton('Generar Pulsos Estocásticos')
        btn_ejecutar.setStyleSheet('background-color: #4CAF50; color: white; font-weight: bold;')
        btn_ejecutar.clicked.connect(self.ejecutar)
        btn_cerrar = QPushButton('Cerrar')
        btn_cerrar.clicked.connect(self.dialog.close)
        btn_layout.addStretch()
        btn_layout.addWidget(btn_ejecutar)
        btn_layout.addWidget(btn_cerrar)
        layout.addLayout(btn_layout)

        # Conexiones
        self.cmb_tuberias.currentIndexChanged.connect(self._actualizar_campos)

        self._actualizar_campos()

        self.dialog.setLayout(layout)
        self.dialog.show()

    def _cargar_capas_linea(self):
        self.cmb_tuberias.clear()
        for layer in QgsProject.instance().mapLayers().values():
            if layer.type() == QgsVectorLayer.VectorLayer and layer.geometryType() == QgsWkbTypes.LineGeometry:
                self.cmb_tuberias.addItem(layer.name(), layer.id())

    def _actualizar_campos(self):
        # No es necesario para este módulo
        pass

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

    def _poisson(self, lam):
        """Genera un número aleatorio de Poisson (método de Knuth)"""
        if lam <= 0:
            return 0
        import math
        L = math.exp(-lam)
        k = 0
        p = 1.0
        while p > L:
            k += 1
            p *= random.random()
        return k - 1

    def _distribuir_pulsos(self, total_tuberias, probabilidad, min_pulsos, max_pulsos, modo, semilla):
        """
        Distribuye pulsos entre las tuberías según el modo seleccionado
        Retorna: lista booleana de True/False para cada tubería
        """
        # Configurar semilla
        if semilla > 0:
            random.seed(semilla)
        
        # Calcular número total de pulsos
        if modo == 'Uniforme':
            # Distribución uniforme: cada tubería tiene probabilidad%
            pulsos = [random.random() < (probabilidad / 100.0) for _ in range(total_tuberias)]
            
        elif modo == 'Poisson':
            # Distribución Poisson: lambda = probabilidad * total_tuberias / 100
            lam = (probabilidad / 100.0) * total_tuberias
            n_pulsos = self._poisson(lam)
            
            # Limitar entre min y max
            if n_pulsos < min_pulsos:
                n_pulsos = min_pulsos
            elif n_pulsos > max_pulsos:
                n_pulsos = max_pulsos
            
            # Seleccionar aleatoriamente qué tuberías reciben pulso
            indices = list(range(total_tuberias))
            random.shuffle(indices)
            seleccionados = indices[:n_pulsos]
            pulsos = [i in seleccionados for i in range(total_tuberias)]
            
        else:  # Binomial
            # Distribución binomial: n = total_tuberias, p = probabilidad/100
            n_pulsos = 0
            for _ in range(total_tuberias):
                if random.random() < (probabilidad / 100.0):
                    n_pulsos += 1
            
            # Limitar entre min y max
            if n_pulsos < min_pulsos:
                n_pulsos = min_pulsos
            elif n_pulsos > max_pulsos:
                n_pulsos = max_pulsos
            
            # Seleccionar aleatoriamente qué tuberías reciben pulso
            indices = list(range(total_tuberias))
            random.shuffle(indices)
            seleccionados = indices[:n_pulsos]
            pulsos = [i in seleccionados for i in range(total_tuberias)]
        
        return pulsos

    def _guardar_shapefile(self, capa, nombre):
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
        """Ejecuta la distribución de pulsos estocásticos"""
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

            # Obtener parámetros
            qpulso = self.spin_qpulso.value()
            probabilidad = self.spin_probabilidad.value()
            min_pulsos = self.spin_min_pulsos.value()
            max_pulsos = self.spin_max_pulsos.value()
            modo = self.cmb_modo.currentText()
            semilla = self.spin_semilla.value()
            agregar_qbase = self.chk_agregar_qbase.isChecked()
            guardar_copia = self.chk_guardar_copia.isChecked()

            self.debug = self.chk_debug.isChecked()

            self.progress.setValue(0)

            # ============================================
            # PASO 1: Leer tuberías y sus Qacu
            # ============================================
            
            tuberias_lista = []
            for feature in capa_tuberias.getFeatures():
                id_o = feature.attribute('ID_O')
                qacu = feature.attribute('Qacu') or 0
                
                if id_o is not None:
                    tuberias_lista.append({
                        'id_o': id_o,
                        'qacu': qacu,
                        'feature': feature,
                        'tiene_pulso': False,
                        'q_estocastico': 0.0
                    })

            total_tuberias = len(tuberias_lista)

            if total_tuberias == 0:
                QMessageBox.warning(self.dialog, 'Error', 'No se encontraron tuberías con ID_O')
                return

            self.progress.setValue(20)

            # ============================================
            # PASO 2: Distribuir pulsos
            # ============================================
            
            if self.debug:
                print(f"\n{'='*60}")
                print("DISTRIBUCIÓN DE PULSOS ESTOCÁSTICOS")
                print(f"{'='*60}")
                print(f"Total tuberías: {total_tuberias}")
                print(f"Probabilidad: {probabilidad}%")
                print(f"Modo: {modo}")
                print(f"Mínimo pulsos: {min_pulsos}")
                print(f"Máximo pulsos: {max_pulsos}")
                print(f"Qpulso: {qpulso} LPS")
                print(f"Agregar Qbase: {agregar_qbase}")
                print(f"{'='*60}")

            # Distribuir pulsos
            pulsos = self._distribuir_pulsos(total_tuberias, probabilidad, min_pulsos, max_pulsos, modo, semilla)
            
            # Asignar pulsos a las tuberías
            pulsos_asignados = 0
            for i, tuberia in enumerate(tuberias_lista):
                if i < len(pulsos) and pulsos[i]:
                    tuberia['tiene_pulso'] = True
                    pulsos_asignados += 1

            self.progress.setValue(50)

            if self.debug:
                print(f"\n📊 Pulsos asignados: {pulsos_asignados} de {total_tuberias}")
                print(f"   Porcentaje: {pulsos_asignados/total_tuberias*100:.1f}%")

            # ============================================
            # PASO 3: Calcular caudales estocásticos
            # ============================================
            
            for tuberia in tuberias_lista:
                if tuberia['tiene_pulso']:
                    if agregar_qbase:
                        tuberia['q_estocastico'] = tuberia['qacu'] + qpulso
                    else:
                        tuberia['q_estocastico'] = qpulso
                else:
                    if agregar_qbase:
                        tuberia['q_estocastico'] = tuberia['qacu']
                    else:
                        tuberia['q_estocastico'] = 0

            self.progress.setValue(70)

            # ============================================
            # PASO 4: Crear nueva capa o modificar existente
            # ============================================
            
            if guardar_copia:
                # Crear nueva capa
                campos = QgsFields(capa_tuberias.fields())
                campos.append(QgsField('Q_estocastico', QVariant.Double))
                campos.append(QgsField('Tiene_pulso', QVariant.String, len=3))

                uri = f"LineString?crs={capa_tuberias.crs().authid()}&index=yes"
                capa_resultado = QgsVectorLayer(uri, 'Tuberias_Estocasticas', 'memory')
                provider = capa_resultado.dataProvider()
                provider.addAttributes(campos)
                capa_resultado.updateFields()

                for tuberia in tuberias_lista:
                    feature = tuberia['feature']
                    nueva_feature = QgsFeature(campos)
                    atributos = list(feature.attributes())
                    atributos.append(round(tuberia['q_estocastico'], 3))
                    atributos.append('SI' if tuberia['tiene_pulso'] else 'NO')
                    
                    nueva_feature.setAttributes(atributos)
                    nueva_feature.setGeometry(feature.geometry())
                    provider.addFeature(nueva_feature)

                capa_resultado.updateFields()
                capa_resultado.commitChanges()
                
                ruta = self._guardar_shapefile(capa_resultado, 'Tuberias_Estocasticas')
                if ruta:
                    capa_guardada = QgsVectorLayer(ruta, 'Tuberias_Estocasticas', 'ogr')
                    QgsProject.instance().addMapLayer(capa_guardada)
            else:
                # Modificar capa existente (agregar columna)
                if capa_tuberias.fields().indexFromName('Q_estocastico') == -1:
                    capa_tuberias.startEditing()
                    capa_tuberias.dataProvider().addAttributes([QgsField('Q_estocastico', QVariant.Double)])
                    capa_tuberias.updateFields()
                
                idx_q = capa_tuberias.fields().indexFromName('Q_estocastico')
                
                for tuberia in tuberias_lista:
                    feature = tuberia['feature']
                    capa_tuberias.changeAttributeValue(feature.id(), idx_q, round(tuberia['q_estocastico'], 3))
                
                capa_tuberias.commitChanges()

            self.progress.setValue(100)

            # ============================================
            # RESUMEN
            # ============================================
            
            mensaje = (
                f'✅ PROCESO COMPLETADO\n\n'
                f'📊 Resumen:\n'
                f'  • Tuberías procesadas: {total_tuberias}\n'
                f'  • Pulsos asignados: {pulsos_asignados}\n'
                f'  • Porcentaje: {pulsos_asignados/total_tuberias*100:.1f}%\n\n'
                f'📌 PARÁMETROS:\n'
                f'  • Qpulso: {qpulso} LPS\n'
                f'  • Probabilidad: {probabilidad}%\n'
                f'  • Modo: {modo}\n'
                f'  • Agregar Qbase: {"SI" if agregar_qbase else "NO"}\n\n'
                f'📁 Archivo generado:\n'
                f'  • {"Tuberias_Estocasticas.shp" if guardar_copia else "Capa original actualizada"}'
            )

            QMessageBox.information(self.dialog, 'Completado', mensaje)

            self.dialog.close()

        except Exception as e:
            QMessageBox.critical(self.dialog, 'Error', f'Error: {str(e)}')
            import traceback
            traceback.print_exc()

    def desactivar(self):
        pass