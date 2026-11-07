# -*- coding: utf-8 -*-
"""
Módulo: exportar_swmm
Versión: 1.0
Propósito: Exportar a formato .inp para EPA SWMM
"""

from qgis.PyQt.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QPushButton, 
    QLabel, QComboBox, QMessageBox, QProgressBar,
    QLineEdit, QGroupBox, QGridLayout, QFileDialog
)
from qgis.PyQt.QtCore import Qt
from qgis.core import QgsProject, QgsVectorLayer, QgsWkbTypes
import os

class ExportarSWMM:
    def __init__(self, iface):
        self.iface = iface
        self.dialog = None
        self.ruta_salida = None

    def mostrar_dialogo(self):
        """Muestra el diálogo principal"""
        self.dialog = QDialog(self.iface.mainWindow())
        self.dialog.setWindowTitle('GLC - Exportar a EPA SWMM (.inp)')
        self.dialog.setMinimumWidth(700)
        
        layout = QVBoxLayout()

        # Descripción
        lbl_desc = QLabel(
            '<b>Exportar a EPA SWMM (.inp)</b>\n\n'
            '📌 Genera el archivo .inp a partir de las capas:\n'
            '   • Tuberías Virtuales (Ci_Virtual, Cf, L, D_mm, Zs_i, Zs_f)\n'
            '   • Cámaras (ID_O, Zs_i, Z, Qacu)\n\n'
            '📌 OutOffset = Zs_f (tubería) - Zs_i (cámara)\n'
            '   (siempre positivo, representa el desnivel de entrada)'
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

        grid_capas.addWidget(QLabel('Cámaras:'), 1, 0)
        self.cmb_camaras = QComboBox()
        self._cargar_capas_punto()
        grid_capas.addWidget(self.cmb_camaras, 1, 1)

        group_capas.setLayout(grid_capas)
        layout.addWidget(group_capas)

        # Selección de campos - Tuberías
        group_campos_tuberias = QGroupBox('Campos en Tuberías')
        grid_tuberias = QGridLayout()

        grid_tuberias.addWidget(QLabel('ID_O:'), 0, 0)
        self.cmb_id_tuberia = QComboBox()
        grid_tuberias.addWidget(self.cmb_id_tuberia, 0, 1)

        grid_tuberias.addWidget(QLabel('Ci_Virtual (From Node):'), 1, 0)
        self.cmb_ci_virtual = QComboBox()
        grid_tuberias.addWidget(self.cmb_ci_virtual, 1, 1)

        grid_tuberias.addWidget(QLabel('Cf (To Node):'), 2, 0)
        self.cmb_cf = QComboBox()
        grid_tuberias.addWidget(self.cmb_cf, 2, 1)

        grid_tuberias.addWidget(QLabel('L (Longitud):'), 3, 0)
        self.cmb_l = QComboBox()
        grid_tuberias.addWidget(self.cmb_l, 3, 1)

        grid_tuberias.addWidget(QLabel('D_mm (Diámetro en mm):'), 4, 0)
        self.cmb_d = QComboBox()
        grid_tuberias.addWidget(self.cmb_d, 4, 1)

        grid_tuberias.addWidget(QLabel('Zs_i (Cota solera inicio):'), 5, 0)
        self.cmb_zsi = QComboBox()
        grid_tuberias.addWidget(self.cmb_zsi, 5, 1)

        grid_tuberias.addWidget(QLabel('Zs_f (Cota solera final):'), 6, 0)
        self.cmb_zsf = QComboBox()
        grid_tuberias.addWidget(self.cmb_zsf, 6, 1)

        group_campos_tuberias.setLayout(grid_tuberias)
        layout.addWidget(group_campos_tuberias)

        # Selección de campos - Cámaras
        group_campos_camaras = QGroupBox('Campos en Cámaras')
        grid_camaras = QGridLayout()

        grid_camaras.addWidget(QLabel('ID_O:'), 0, 0)
        self.cmb_id_camara = QComboBox()
        grid_camaras.addWidget(self.cmb_id_camara, 0, 1)

        grid_camaras.addWidget(QLabel('Zs_i (Cota solera):'), 1, 0)
        self.cmb_zs_camara = QComboBox()
        grid_camaras.addWidget(self.cmb_zs_camara, 1, 1)

        grid_camaras.addWidget(QLabel('Z (Cota terreno):'), 2, 0)
        self.cmb_z_camara = QComboBox()
        grid_camaras.addWidget(self.cmb_z_camara, 2, 1)

        grid_camaras.addWidget(QLabel('Qacu (Caudal):'), 3, 0)
        self.cmb_qacu = QComboBox()
        grid_camaras.addWidget(self.cmb_qacu, 3, 1)

        grid_camaras.addWidget(QLabel('X (Coordenada X):'), 4, 0)
        self.cmb_x = QComboBox()
        grid_camaras.addWidget(self.cmb_x, 4, 1)

        grid_camaras.addWidget(QLabel('Y (Coordenada Y):'), 5, 0)
        self.cmb_y = QComboBox()
        grid_camaras.addWidget(self.cmb_y, 5, 1)

        grid_camaras.addWidget(QLabel('Es_Final (SI/NO):'), 6, 0)
        self.cmb_es_final = QComboBox()
        grid_camaras.addWidget(self.cmb_es_final, 6, 1)

        group_campos_camaras.setLayout(grid_camaras)
        layout.addWidget(group_campos_camaras)

        # Parámetros adicionales
        group_parametros = QGroupBox('Parámetros')
        grid_parametros = QGridLayout()

        grid_parametros.addWidget(QLabel('Rugosidad (Manning):'), 0, 0)
        self.txt_rugosidad = QLineEdit('0.013')
        grid_parametros.addWidget(self.txt_rugosidad, 0, 1)

        grid_parametros.addWidget(QLabel('Nombre del proyecto:'), 1, 0)
        self.txt_proyecto = QLineEdit('Proyecto Alcantarillado')
        grid_parametros.addWidget(self.txt_proyecto, 1, 1)

        group_parametros.setLayout(grid_parametros)
        layout.addWidget(group_parametros)

        # Carpeta de salida
        group_salida = QGroupBox('Archivo de salida')
        grid_salida = QGridLayout()

        self.txt_ruta = QLineEdit()
        self.txt_ruta.setReadOnly(True)
        grid_salida.addWidget(self.txt_ruta, 0, 0)

        btn_ruta = QPushButton('Seleccionar Archivo...')
        btn_ruta.clicked.connect(self._seleccionar_archivo)
        grid_salida.addWidget(btn_ruta, 0, 1)

        group_salida.setLayout(grid_salida)
        layout.addWidget(group_salida)

        # Conexiones
        self.cmb_tuberias.currentIndexChanged.connect(self._actualizar_campos_tuberias)
        self.cmb_camaras.currentIndexChanged.connect(self._actualizar_campos_camaras)

        self._actualizar_campos_tuberias()
        self._actualizar_campos_camaras()

        # Progreso
        self.progress = QProgressBar()
        layout.addWidget(self.progress)

        # Botones
        btn_layout = QHBoxLayout()
        btn_ejecutar = QPushButton('Exportar a .inp')
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

    def _cargar_capas_punto(self):
        self.cmb_camaras.clear()
        for layer in QgsProject.instance().mapLayers().values():
            if layer.type() == QgsVectorLayer.VectorLayer and layer.geometryType() == QgsWkbTypes.PointGeometry:
                self.cmb_camaras.addItem(layer.name(), layer.id())

    def _actualizar_campos_tuberias(self):
        self.cmb_id_tuberia.clear()
        self.cmb_ci_virtual.clear()
        self.cmb_cf.clear()
        self.cmb_l.clear()
        self.cmb_d.clear()
        self.cmb_zsi.clear()
        self.cmb_zsf.clear()

        layer_id = self.cmb_tuberias.currentData()
        if not layer_id:
            return

        layer = QgsProject.instance().mapLayer(layer_id)
        if not layer:
            return

        fields = [f.name() for f in layer.fields()]
        self.cmb_id_tuberia.addItems(fields)
        self.cmb_ci_virtual.addItems(fields)
        self.cmb_cf.addItems(fields)
        self.cmb_l.addItems(fields)
        self.cmb_d.addItems(fields)
        self.cmb_zsi.addItems(fields)
        self.cmb_zsf.addItems(fields)

        if 'ID_O' in fields:
            self.cmb_id_tuberia.setCurrentIndex(fields.index('ID_O'))
        if 'Ci_Virtual' in fields:
            self.cmb_ci_virtual.setCurrentIndex(fields.index('Ci_Virtual'))
        if 'Cf' in fields:
            self.cmb_cf.setCurrentIndex(fields.index('Cf'))
        if 'L' in fields:
            self.cmb_l.setCurrentIndex(fields.index('L'))
        if 'D_mm' in fields:
            self.cmb_d.setCurrentIndex(fields.index('D_mm'))
        if 'Zs_i' in fields:
            self.cmb_zsi.setCurrentIndex(fields.index('Zs_i'))
        if 'Zs_f' in fields:
            self.cmb_zsf.setCurrentIndex(fields.index('Zs_f'))

    def _actualizar_campos_camaras(self):
        self.cmb_id_camara.clear()
        self.cmb_zs_camara.clear()
        self.cmb_z_camara.clear()
        self.cmb_qacu.clear()
        self.cmb_x.clear()
        self.cmb_y.clear()
        self.cmb_es_final.clear()

        layer_id = self.cmb_camaras.currentData()
        if not layer_id:
            return

        layer = QgsProject.instance().mapLayer(layer_id)
        if not layer:
            return

        fields = [f.name() for f in layer.fields()]
        self.cmb_id_camara.addItems(fields)
        self.cmb_zs_camara.addItems(fields)
        self.cmb_z_camara.addItems(fields)
        self.cmb_qacu.addItems(fields)
        self.cmb_x.addItems(fields)
        self.cmb_y.addItems(fields)
        self.cmb_es_final.addItems(fields)

        if 'ID_O' in fields:
            self.cmb_id_camara.setCurrentIndex(fields.index('ID_O'))
        if 'Zs_i' in fields:
            self.cmb_zs_camara.setCurrentIndex(fields.index('Zs_i'))
        if 'Z' in fields:
            self.cmb_z_camara.setCurrentIndex(fields.index('Z'))
        if 'Qacu' in fields:
            self.cmb_qacu.setCurrentIndex(fields.index('Qacu'))
        if 'X' in fields:
            self.cmb_x.setCurrentIndex(fields.index('X'))
        if 'Y' in fields:
            self.cmb_y.setCurrentIndex(fields.index('Y'))
        if 'Es_Final' in fields:
            self.cmb_es_final.setCurrentIndex(fields.index('Es_Final'))

    def _seleccionar_archivo(self):
        archivo, _ = QFileDialog.getSaveFileName(
            self.dialog,
            'Guardar archivo .inp',
            '',
            'Archivos INP (*.inp)'
        )
        if archivo:
            if not archivo.endswith('.inp'):
                archivo += '.inp'
            self.txt_ruta.setText(archivo)
            self.ruta_salida = archivo

    def _calcular_max_depth(self, z, zs_i):
        """Calcula MaxDepth = Z - Zs_i"""
        try:
            return round(float(z) - float(zs_i), 3)
        except:
            return 0

    def _calcular_outoffset(self, zs_f_tuberia, zs_i_camara):
        """
        Calcula OutOffset = Zs_f (tubería) - Zs_i (cámara)
        Siempre positivo (desnivel de entrada)
        """
        try:
            # Si alguno es None, retornar 0
            if zs_f_tuberia is None or zs_i_camara is None:
                return 0
            
            resultado = float(zs_f_tuberia) - float(zs_i_camara)
            # Si es negativo, usar valor absoluto
            if resultado < 0:
                resultado = abs(resultado)
            return round(resultado, 3)
        except:
            return 0

    def ejecutar(self):
        """Ejecuta la exportación a .inp"""
        try:
            # Validar archivo de salida
            if not self.ruta_salida:
                QMessageBox.warning(self.dialog, 'Error', 'Seleccione el archivo de salida')
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

            # Obtener campos
            campo_id_tuberia = self.cmb_id_tuberia.currentText()
            campo_ci_virtual = self.cmb_ci_virtual.currentText()
            campo_cf = self.cmb_cf.currentText()
            campo_l = self.cmb_l.currentText()
            campo_d = self.cmb_d.currentText()
            campo_zsi = self.cmb_zsi.currentText()
            campo_zsf = self.cmb_zsf.currentText()

            campo_id_camara = self.cmb_id_camara.currentText()
            campo_zs_camara = self.cmb_zs_camara.currentText()
            campo_z_camara = self.cmb_z_camara.currentText()
            campo_qacu = self.cmb_qacu.currentText()
            campo_x = self.cmb_x.currentText()
            campo_y = self.cmb_y.currentText()
            campo_es_final = self.cmb_es_final.currentText()

            rugosidad = self.txt_rugosidad.text()
            nombre_proyecto = self.txt_proyecto.text()

            self.progress.setValue(0)

            # ============================================
            # PASO 1: Leer datos de cámaras
            # ============================================
            
            camaras_dict = {}
            camara_final = None
            
            for feature in capa_camaras.getFeatures():
                id_o = str(feature.attribute(campo_id_camara))
                zs = feature.attribute(campo_zs_camara)
                z = feature.attribute(campo_z_camara)
                qacu = feature.attribute(campo_qacu)
                x = feature.attribute(campo_x)
                y = feature.attribute(campo_y)
                es_final = feature.attribute(campo_es_final) or 'NO'
                
                camaras_dict[id_o] = {
                    'zs': zs,
                    'z': z,
                    'qacu': qacu if qacu is not None else 0,
                    'x': x,
                    'y': y,
                    'es_final': es_final
                }
                
                if es_final == 'SI':
                    camara_final = id_o

            self.progress.setValue(20)

            # ============================================
            # PASO 2: Leer datos de tuberías
            # ============================================
            
            tuberias_list = []
            
            for feature in capa_tuberias.getFeatures():
                id_o = str(feature.attribute(campo_id_tuberia))
                ci_virtual = str(feature.attribute(campo_ci_virtual))
                cf = str(feature.attribute(campo_cf))
                longitud = feature.attribute(campo_l)
                diametro_mm = feature.attribute(campo_d)
                zs_i = feature.attribute(campo_zsi)
                zs_f = feature.attribute(campo_zsf)
                
                # Convertir diámetro de mm a metros
                diametro_m = diametro_mm / 1000.0 if diametro_mm else 0.15
                
                tuberias_list.append({
                    'id': id_o,
                    'from_node': ci_virtual,
                    'to_node': cf,
                    'length': longitud,
                    'diametro': diametro_m,
                    'zs_i': zs_i,
                    'zs_f': zs_f
                })

            self.progress.setValue(40)

            # ============================================
            # PASO 3: Generar archivo .inp
            # ============================================
            
            with open(self.ruta_salida, 'w', encoding='utf-8') as f:
                # TITLE
                f.write('[TITLE]\n')
                f.write(f';;{nombre_proyecto}\n\n')
                
                # OPTIONS
                f.write('[OPTIONS]\n')
                f.write(';;Option             Value\n')
                f.write('FLOW_UNITS           LPS\n')
                f.write('INFILTRATION         HORTON\n')
                f.write('FLOW_ROUTING         STEADY\n')
                f.write('LINK_OFFSETS         DEPTH\n')
                f.write('MIN_SLOPE            0\n')
                f.write('ALLOW_PONDING        NO\n')
                f.write('SKIP_STEADY_STATE    NO\n')
                f.write('\n')
                f.write('START_DATE           05/16/2023\n')
                f.write('START_TIME           00:00:00\n')
                f.write('REPORT_START_DATE    05/16/2023\n')
                f.write('REPORT_START_TIME    00:00:00\n')
                f.write('END_DATE             05/16/2023\n')
                f.write('END_TIME             06:00:00\n')
                f.write('SWEEP_START          1/1\n')
                f.write('SWEEP_END            12/31\n')
                f.write('DRY_DAYS             0\n')
                f.write('REPORT_STEP          00:15:00\n')
                f.write('WET_STEP             00:05:00\n')
                f.write('DRY_STEP             01:00:00\n')
                f.write('ROUTING_STEP         0:00:20 \n')
                f.write('RULE_STEP            00:00:00\n')
                f.write('\n')
                f.write('INERTIAL_DAMPING     PARTIAL\n')
                f.write('NORMAL_FLOW_LIMITED  BOTH\n')
                f.write('FORCE_MAIN_EQUATION  H-W\n')
                f.write('VARIABLE_STEP        0.75\n')
                f.write('LENGTHENING_STEP     0\n')
                f.write('MIN_SURFAREA         0\n')
                f.write('MAX_TRIALS           0\n')
                f.write('HEAD_TOLERANCE       0\n')
                f.write('SYS_FLOW_TOL         5\n')
                f.write('LAT_FLOW_TOL         5\n')
                f.write('MINIMUM_STEP         0.5\n')
                f.write('THREADS              1\n\n')
                
                # EVAPORATION
                f.write('[EVAPORATION]\n')
                f.write(';;Data Source    Parameters\n')
                f.write(';;-------------- ----------------\n')
                f.write('CONSTANT         0.0\n')
                f.write('DRY_ONLY         NO\n\n')
                
                # JUNCTIONS
                f.write('[JUNCTIONS]\n')
                f.write(';;Name           Elevation  MaxDepth   InitDepth  SurDepth   Aponded   \n')
                f.write(';;-------------- ---------- ---------- ---------- ---------- ----------\n')
                
                for id_o, datos in camaras_dict.items():
                    if datos['es_final'] == 'SI':
                        continue
                    elevacion = datos['zs'] if datos['zs'] is not None else -9999
                    max_depth = self._calcular_max_depth(datos['z'], datos['zs'])
                    f.write(f'{id_o:<15} {elevacion:>10.3f} {max_depth:>10.3f} 0          0          0         \n')
                
                f.write('\n')
                
                # OUTFALLS
                f.write('[OUTFALLS]\n')
                f.write(';;Name           Elevation  Type       Stage Data       Gated    Route To        \n')
                f.write(';;-------------- ---------- ---------- ---------------- -------- ----------------\n')
                
                if camara_final and camara_final in camaras_dict:
                    elevacion = camaras_dict[camara_final]['zs'] if camaras_dict[camara_final]['zs'] is not None else -9999
                    f.write(f'{camara_final:<15} {elevacion:>10.3f} FREE                        NO                       \n')
                else:
                    # Si no hay cámara final, usar la última cámara
                    ultima_camara = list(camaras_dict.keys())[-1] if camaras_dict else '1'
                    elevacion = camaras_dict[ultima_camara]['zs'] if camaras_dict[ultima_camara]['zs'] is not None else -9999
                    f.write(f'{ultima_camara:<15} {elevacion:>10.3f} FREE                        NO                       \n')
                
                f.write('\n')
                
                # CONDUITS
                f.write('[CONDUITS]\n')
                f.write(';;Name           From Node        To Node          Length     Roughness  InOffset   OutOffset  InitFlow   MaxFlow   \n')
                f.write(';;-------------- ---------------- ---------------- ---------- ---------- ---------- ---------- ---------- ----------\n')
                
                for tuberia in tuberias_list:
                    # OutOffset = Zs_f (tubería) - Zs_i (cámara)
                    zs_i_camara = camaras_dict.get(tuberia['to_node'], {}).get('zs', 0)
                    out_offset = self._calcular_outoffset(tuberia['zs_f'], zs_i_camara)
                    
                    f.write(f'{tuberia["id"]:<15} {tuberia["from_node"]:<16} {tuberia["to_node"]:<16} {tuberia["length"]:>10.2f} {rugosidad:>10} 0          {out_offset:>10.3f} 0          0         \n')
                
                f.write('\n')
                
                # XSECTIONS
                f.write('[XSECTIONS]\n')
                f.write(';;Link           Shape        Geom1            Geom2      Geom3      Geom4      Barrels    Culvert   \n')
                f.write(';;-------------- ------------ ---------------- ---------- ---------- ---------- ---------- ----------\n')
                
                for tuberia in tuberias_list:
                    f.write(f'{tuberia["id"]:<15} CIRCULAR     {tuberia["diametro"]:>16.3f} 0          0          0          1                    \n')
                
                f.write('\n')
                
                # DWF
                f.write('[DWF]\n')
                f.write(';;Node           Constituent      Baseline   Patterns  \n')
                f.write(';;-------------- ---------------- ---------- ----------\n')
                
                for id_o, datos in camaras_dict.items():
                    if datos['es_final'] == 'SI':
                        continue
                    qacu = datos['qacu'] if datos['qacu'] is not None else 0
                    f.write(f'{id_o:<15} FLOW             {qacu:>10.3f} "" "" ""\n')
                
                f.write('\n')
                
                # REPORT
                f.write('[REPORT]\n')
                f.write(';;Reporting Options\n')
                f.write('SUBCATCHMENTS ALL\n')
                f.write('NODES ALL\n')
                f.write('LINKS ALL\n\n')
                
                # TAGS
                f.write('[TAGS]\n\n')
                
                # MAP
                # Calcular dimensiones del mapa a partir de las coordenadas
                xs = [datos['x'] for datos in camaras_dict.values() if datos['x'] is not None]
                ys = [datos['y'] for datos in camaras_dict.values() if datos['y'] is not None]
                
                if xs and ys:
                    min_x = min(xs)
                    max_x = max(xs)
                    min_y = min(ys)
                    max_y = max(ys)
                    
                    # Añadir margen
                    margen_x = (max_x - min_x) * 0.1 if (max_x - min_x) > 0 else 10
                    margen_y = (max_y - min_y) * 0.1 if (max_y - min_y) > 0 else 10
                    
                    f.write('[MAP]\n')
                    f.write(f'DIMENSIONS {min_x - margen_x:.3f} {min_y - margen_y:.3f} {max_x + margen_x:.3f} {max_y + margen_y:.3f}\n')
                    f.write('Units      None\n\n')
                
                # COORDINATES
                f.write('[COORDINATES]\n')
                f.write(';;Node           X-Coord            Y-Coord           \n')
                f.write(';;-------------- ------------------ ------------------\n')
                
                for id_o, datos in camaras_dict.items():
                    x = datos['x'] if datos['x'] is not None else 0
                    y = datos['y'] if datos['y'] is not None else 0
                    f.write(f'{id_o:<15} {x:>18.3f} {y:>18.3f}       \n')
                
                f.write('\n')
                
                # VERTICES
                f.write('[VERTICES]\n')
                f.write(';;Link           X-Coord            Y-Coord           \n')
                f.write(';;-------------- ------------------ ------------------\n\n')
                
                # Polygons
                f.write('[Polygons]\n')

            self.progress.setValue(100)

            QMessageBox.information(self.dialog, 'Completado',
                f'✅ ARCHIVO .inp GENERADO EXITOSAMENTE\n\n'
                f'📊 Resumen:\n'
                f'  • Nodos (Junctions): {len([k for k, v in camaras_dict.items() if v["es_final"] != "SI"])}\n'
                f'  • Nodo final (Outfall): {camara_final}\n'
                f'  • Tuberías (Conduits): {len(tuberias_list)}\n\n'
                f'📌 OutOffset = Zs_f (tubería) - Zs_i (cámara)\n'
                f'   (siempre positivo)\n\n'
                f'📁 Archivo guardado en:\n'
                f'  {self.ruta_salida}')

            self.dialog.close()

        except Exception as e:
            QMessageBox.critical(self.dialog, 'Error', f'Error: {str(e)}')
            import traceback
            traceback.print_exc()

    def desactivar(self):
        pass