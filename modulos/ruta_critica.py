# -*- coding: utf-8 -*-
from qgis.core import (
    QgsProject, QgsVectorLayer, QgsFeature,
    QgsGeometry, QgsPointXY, QgsField,
    QgsWkbTypes, QgsLineString
)
from qgis.PyQt.QtCore import Qt, QVariant
from qgis.PyQt.QtWidgets import (
    QMessageBox, QDialog, QVBoxLayout, QLabel,
    QPushButton, QComboBox, QProgressBar,
    QTextEdit, QHBoxLayout, QGroupBox,
    QCheckBox, QTabWidget, QWidget, QTableWidget,
    QTableWidgetItem, QHeaderView, QFormLayout
)


class RutaCritica:
    def __init__(self, iface):
        self.iface = iface
        self.capa_tuberias = None
        self.capa_camaras = None
        self.debug = False
        self.tuberias_dict = {}
        self.camaras_dict = {}
    
    def mostrar_dialogo(self):
        """Muestra el diálogo principal"""
        dialog = QDialog(self.iface.mainWindow())
        dialog.setWindowTitle('GLC - Encontrar Ruta Crítica')
        dialog.setMinimumWidth(900)
        dialog.setMinimumHeight(650)
        
        layout = QVBoxLayout()
        
        label_titulo = QLabel('<b>🔍 Encontrar Ruta Crítica de la Red</b>')
        label_titulo.setStyleSheet('font-size: 14pt; color: #2c3e50;')
        layout.addWidget(label_titulo)
        
        label_desc = QLabel(
            'La ruta crítica es la <b>subred</b> que tiene el <b>MAYOR PUNTAJE</b>.\n\n'
            '📌 Se toma CADA tubería con cab_ata="Arranque" y se sigue su flujo hasta el final.\n'
            '📌 El puntaje considera: Profundidad Máxima, Promedio, Cámaras > 3.0m y Longitud.\n'
            '📌 Puntaje = (Prof_Max × 1.5 + Prof_Prom × 1.0 + Prof_Altas × 0.5) × (1 + Longitud/1000)\n\n'
            '📌 Las cámaras en la ruta crítica NO pueden modificarse a menor profundidad.'
        )
        label_desc.setWordWrap(True)
        label_desc.setStyleSheet('background-color: #ecf0f1; padding: 10px; border-radius: 4px;')
        layout.addWidget(label_desc)
        
        layout.addWidget(QLabel('-' * 60))
        
        # Capas
        group_capas = QGroupBox('Capas')
        form_capas = QFormLayout()
        
        self.combo_tuberias = QComboBox()
        for layer in QgsProject.instance().mapLayers().values():
            if isinstance(layer, QgsVectorLayer):
                if layer.geometryType() == QgsWkbTypes.LineGeometry:
                    self.combo_tuberias.addItem(layer.name(), layer.id())
        form_capas.addRow('Tuberías:', self.combo_tuberias)
        
        self.combo_camaras = QComboBox()
        for layer in QgsProject.instance().mapLayers().values():
            if isinstance(layer, QgsVectorLayer):
                if layer.geometryType() == QgsWkbTypes.PointGeometry:
                    self.combo_camaras.addItem(layer.name(), layer.id())
        form_capas.addRow('Cámaras:', self.combo_camaras)
        
        group_capas.setLayout(form_capas)
        layout.addWidget(group_capas)
        
        # Opciones
        self.chk_debug = QCheckBox('Mostrar depuración en consola')
        layout.addWidget(self.chk_debug)
        
        # Botones
        hbox_botones = QHBoxLayout()
        btn_encontrar = QPushButton('🔍 Encontrar Ruta Crítica')
        btn_encontrar.setStyleSheet('background-color: #2196f3; color: white; font-weight: bold; padding: 10px;')
        btn_encontrar.clicked.connect(lambda: self.encontrar(dialog))
        hbox_botones.addWidget(btn_encontrar)
        hbox_botones.addStretch()
        
        btn_cerrar = QPushButton('Cerrar')
        btn_cerrar.clicked.connect(dialog.accept)
        hbox_botones.addWidget(btn_cerrar)
        
        layout.addLayout(hbox_botones)
        
        # Barra de progreso
        self.progress = QProgressBar()
        layout.addWidget(self.progress)
        
        # Pestañas
        tabs = QTabWidget()
        
        self.tab_resumen = QWidget()
        layout_resumen = QVBoxLayout()
        self.text_resumen = QTextEdit()
        self.text_resumen.setReadOnly(True)
        self.text_resumen.setStyleSheet('font-family: monospace; font-size: 10pt;')
        layout_resumen.addWidget(self.text_resumen)
        self.tab_resumen.setLayout(layout_resumen)
        tabs.addTab(self.tab_resumen, '📊 Resumen')
        
        self.tab_rutas = QWidget()
        layout_rutas = QVBoxLayout()
        self.table_rutas = QTableWidget()
        self.table_rutas.setColumnCount(7)
        self.table_rutas.setHorizontalHeaderLabels([
            '#', 'Ruta (Cámaras)', 'Prof. Max', 'Prof. Prom', 'Prof. >3.0m', 'Longitud', 'Puntaje'
        ])
        self.table_rutas.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        layout_rutas.addWidget(self.table_rutas)
        self.tab_rutas.setLayout(layout_rutas)
        tabs.addTab(self.tab_rutas, '🗺️ Subredes')
        
        layout.addWidget(tabs)
        
        dialog.setLayout(layout)
        dialog.exec_()
    
    def encontrar(self, dialog):
        """Encuentra la ruta crítica de la red"""
        
        tuberias_id = self.combo_tuberias.currentData()
        camaras_id = self.combo_camaras.currentData()
        self.debug = self.chk_debug.isChecked()
        
        if not tuberias_id or not camaras_id:
            QMessageBox.warning(self.iface.mainWindow(), 'Error', 'Seleccione ambas capas')
            return
        
        self.capa_tuberias = QgsProject.instance().mapLayer(tuberias_id)
        self.capa_camaras = QgsProject.instance().mapLayer(camaras_id)
        
        if not self.capa_tuberias or not self.capa_camaras:
            QMessageBox.warning(self.iface.mainWindow(), 'Error', 'No se encontraron las capas')
            return
        
        self.progress.setValue(10)
        self.text_resumen.clear()
        self.table_rutas.setRowCount(0)
        
        self.construir_diccionarios()
        
        self.progress.setValue(30)
        
        subredes = self.encontrar_subredes()
        
        self.progress.setValue(60)
        
        if not subredes:
            self.text_resumen.setText('❌ No se encontraron subredes.\nVerifique que haya tuberías con cab_ata="Arranque".')
            QMessageBox.warning(self.iface.mainWindow(), 'Error', 'No se encontraron subredes')
            self.progress.setValue(100)
            return
        
        subredes_ordenadas = sorted(subredes, key=lambda x: x['puntaje'], reverse=True)
        ruta_critica = subredes_ordenadas[0] if subredes_ordenadas else None
        
        self.progress.setValue(80)
        
        self.mostrar_resultados(subredes_ordenadas, ruta_critica)
        
        self.progress.setValue(100)
        
        if ruta_critica:
            QMessageBox.information(
                self.iface.mainWindow(),
                'Ruta Crítica Encontrada',
                f'✅ RUTA CRÍTICA\n\n'
                f'📌 Cámaras: {len(ruta_critica["camaras"])}\n'
                f'📌 Ruta: {" → ".join(str(c) for c in ruta_critica["camaras"])}\n'
                f'📊 Prof. Máxima: {ruta_critica["prof_max"]:.3f} m\n'
                f'📊 Prof. Promedio: {ruta_critica["prof_prom"]:.3f} m\n'
                f'📊 Prof. > 3.0m: {ruta_critica["prof_altas"]}\n'
                f'📊 Longitud: {ruta_critica["longitud"]:.2f} m\n'
                f'📊 Puntaje: {ruta_critica["puntaje"]:.2f}'
            )
    
    def construir_diccionarios(self):
        """Construye diccionarios de tuberías y cámaras"""
        
        # ===== DICCIONARIO DE TUBERÍAS =====
        self.tuberias_dict = {}
        for feature in self.capa_tuberias.getFeatures():
            id_o = feature.attribute('ID_O')
            if id_o is None:
                continue
            
            self.tuberias_dict[id_o] = {
                'id_o': id_o,
                'ci': feature.attribute('Ci'),
                'cf': feature.attribute('Cf'),
                'cab_ata': feature.attribute('cab_ata') or '',
                'longitud': feature.attribute('L') or 0.0,
                'feature': feature
            }
        
        # ===== DICCIONARIO DE CÁMARAS =====
        self.camaras_dict = {}
        for feature in self.capa_camaras.getFeatures():
            id_o = feature.attribute('ID_O')
            if id_o is None:
                continue
            
            # Leer la profundidad de la cámara (es la que le corresponde por diseño)
            hexc = feature.attribute('Hexc') or 0.0
            
            self.camaras_dict[id_o] = {
                'id_o': id_o,
                'hexc': float(hexc),
                'feature': feature,
                'tuberias_que_llegan': [],
                'tuberias_que_salen': []
            }
        
        # ===== IDENTIFICAR CONEXIONES =====
        for id_t, t_data in self.tuberias_dict.items():
            ci = t_data['ci']
            cf = t_data['cf']
            
            if ci is not None and ci in self.camaras_dict:
                self.camaras_dict[ci]['tuberias_que_salen'].append(id_t)
            if cf is not None and cf in self.camaras_dict:
                self.camaras_dict[cf]['tuberias_que_llegan'].append(id_t)
        
        # ===== SI UNA CÁMARA NO TIENE Hexc, CALCULAR DESDE TUBERÍAS =====
        for id_c, c_data in self.camaras_dict.items():
            if c_data['hexc'] == 0.0:
                max_hexc = 0.0
                
                for id_t in c_data['tuberias_que_llegan']:
                    if id_t in self.tuberias_dict:
                        hexc = self.tuberias_dict[id_t]['feature'].attribute('Hexc_f') or 0.0
                        if hexc > max_hexc:
                            max_hexc = hexc
                
                if max_hexc == 0.0:
                    for id_t in c_data['tuberias_que_salen']:
                        if id_t in self.tuberias_dict:
                            hexc = self.tuberias_dict[id_t]['feature'].attribute('Hexc_i') or 0.0
                            if hexc > max_hexc:
                                max_hexc = hexc
                
                c_data['hexc'] = max_hexc
        
        if self.debug:
            print("\n" + "="*60)
            print("DICCIONARIOS CONSTRUIDOS")
            print("="*60)
            print(f"Tuberías: {len(self.tuberias_dict)}")
            print(f"Cámaras: {len(self.camaras_dict)}")
    
    def encontrar_subredes(self):
        """
        Encuentra todas las subredes.
        
        SOLO: Para CADA tubería con cab_ata="Arranque", seguir su flujo.
        """
        
        # 1. Identificar tuberías de arranque
        tuberias_arranque = []
        for id_t, t_data in self.tuberias_dict.items():
            if t_data['cab_ata'] == 'Arranque':
                tuberias_arranque.append(id_t)
        
        if self.debug:
            print(f"\n🔍 Tuberías con cab_ata='Arranque': {tuberias_arranque}")
        
        if not tuberias_arranque:
            return None
        
        subredes = []
        
        # 2. Para CADA tubería de arranque
        for id_t_arranque in tuberias_arranque:
            
            # La primera cámara es el Ci de esta tubería
            inicio = self.tuberias_dict[id_t_arranque]['ci']
            
            if inicio is None or inicio not in self.camaras_dict:
                continue
            
            # Iniciar el camino
            camino_camaras = [inicio]
            camino_tuberias = [id_t_arranque]
            profundidades = [self.camaras_dict[inicio]['hexc']]
            longitud_total = self.tuberias_dict[id_t_arranque]['longitud']
            
            if self.debug:
                print(f"\n📌 Subred desde tubería {id_t_arranque} (Ci={inicio})")
            
            # La siguiente cámara es el Cf de esta tubería
            actual = self.tuberias_dict[id_t_arranque]['cf']
            
            if actual is None or actual not in self.camaras_dict:
                continue
            
            # Agregar la primera cámara destino
            camino_camaras.append(actual)
            profundidades.append(self.camaras_dict[actual]['hexc'])
            
            if self.debug:
                print(f"  → Cámara {actual}")
            
            # 3. Seguir el flujo
            for i in range(1000):
                # Buscar la tubería que SALE de la cámara actual
                salidas = self.camaras_dict[actual]['tuberias_que_salen']
                
                if self.debug:
                    print(f"    Cámara {actual}: salidas={salidas}")
                
                if not salidas:
                    # No hay salidas → fin de subred
                    if self.debug:
                        print(f"    Fin de subred en {actual}")
                    break
                
                # Tomar la PRIMERA salida que NO es Arranque
                id_t_salida = None
                for id_t in salidas:
                    if self.tuberias_dict[id_t]['cab_ata'] != 'Arranque':
                        id_t_salida = id_t
                        break
                
                if id_t_salida is None:
                    # Todas las salidas son Arranque → fin de subred
                    if self.debug:
                        print(f"    Todas las salidas son Arranque, fin de subred")
                    break
                
                cf = self.tuberias_dict[id_t_salida]['cf']
                
                if cf is None or cf not in self.camaras_dict:
                    break
                
                # Evitar ciclos
                if cf in camino_camaras:
                    if self.debug:
                        print(f"    ⚠️ Ciclo en {cf}, deteniendo")
                    break
                
                # Agregar al camino
                camino_tuberias.append(id_t_salida)
                camino_camaras.append(cf)
                profundidades.append(self.camaras_dict[cf]['hexc'])
                longitud_total += self.tuberias_dict[id_t_salida]['longitud']
                
                if self.debug:
                    print(f"    → Tubería {id_t_salida} → Cámara {cf}")
                
                actual = cf
            
            # 4. Guardar la subred
            if len(camino_camaras) > 1:
                prof_max = max(profundidades)
                prof_prom = sum(profundidades) / len(profundidades)
                prof_altas = sum(1 for p in profundidades if p > 3.0)
                
                # Puntaje: considera profundidad máxima, promedio, altas y longitud
                # Factor longitud: 1 + (longitud / 1000) para dar peso a subredes más largas
                factor_longitud = 1 + (longitud_total / 1000)
                puntaje = (prof_max * 1.5 + prof_prom * 1.0 + prof_altas * 0.5) * factor_longitud
                
                subredes.append({
                    'inicio': inicio,
                    'final': actual,
                    'camaras': camino_camaras,
                    'tuberias': camino_tuberias,
                    'prof_max': prof_max,
                    'prof_prom': prof_prom,
                    'prof_altas': prof_altas,
                    'longitud': longitud_total,
                    'puntaje': puntaje,
                    'profundidades': profundidades
                })
                
                if self.debug:
                    print(f"  ✅ Subred: {' → '.join(str(c) for c in camino_camaras)}")
                    print(f"     Prof Max: {prof_max:.3f}, Longitud: {longitud_total:.2f}, Puntaje: {puntaje:.2f}")
        
        if self.debug:
            print("\n" + "="*60)
            print("📊 SUBREDES ENCONTRADAS:")
            for i, sub in enumerate(subredes):
                print(f"  {i+1}. {sub['inicio']} → {sub['final']}: "
                      f"{len(sub['camaras'])} cámaras, "
                      f"prof_max={sub['prof_max']:.3f}, "
                      f"longitud={sub['longitud']:.2f}, "
                      f"puntaje={sub['puntaje']:.2f}")
                print(f"     Ruta: {' → '.join(str(c) for c in sub['camaras'])}")
            print("="*60)
        
        return subredes
    
    def mostrar_resultados(self, subredes, ruta_critica):
        """Muestra los resultados en la interfaz"""
        
        resumen = f"""
╔══════════════════════════════════════════════════════════════════════════════╗
║                              RUTA CRÍTICA DE LA RED                          ║
╠══════════════════════════════════════════════════════════════════════════════╣
║                                                                              ║
║  📊 ESTADÍSTICAS                                                             ║
║  ──────────────────────────────────────────────────────────────────────────  ║
║  • Total de cámaras:               {len(self.camaras_dict):>6}                            ║
║  • Total de tuberías:              {len(self.tuberias_dict):>6}                            ║
║  • Subredes encontradas:           {len(subredes):>6}                            ║
║                                                                              ║
║  🏆 RUTA CRÍTICA                                                             ║
║  ──────────────────────────────────────────────────────────────────────────  ║
║  • Ruta: {' → '.join(str(c) for c in ruta_critica['camaras']) if ruta_critica else 'N/A'}                         ║
║  • Cámaras: {len(ruta_critica['camaras']) if ruta_critica else 0}                            ║
║  • Prof. Máxima: {ruta_critica['prof_max'] if ruta_critica else 0:>6.3f} m  ║
║  • Prof. Promedio: {ruta_critica['prof_prom'] if ruta_critica else 0:>6.3f} m  ║
║  • Prof. > 3.0m: {ruta_critica['prof_altas'] if ruta_critica else 0}                            ║
║  • Longitud: {ruta_critica['longitud'] if ruta_critica else 0:>6.2f} m  ║
║  • Puntaje: {ruta_critica['puntaje'] if ruta_critica else 0:>6.2f}                            ║
║                                                                              ║
║  📌 DETALLE DE SUBREDES                                                     ║
║  ──────────────────────────────────────────────────────────────────────────  ║
"""
        
        for i, sub in enumerate(subredes):
            es_critica = "🏆 CRÍTICA" if sub == ruta_critica else ""
            resumen += f"""
  {i+1}. {sub['inicio']} → {sub['final']} {es_critica}
      • Ruta: {' → '.join(str(c) for c in sub['camaras'])}
      • Cámaras: {len(sub['camaras'])}
      • Prof. Máx: {sub['prof_max']:.3f} m
      • Prof. Prom: {sub['prof_prom']:.3f} m
      • Prof. > 3.0m: {sub['prof_altas']}
      • Longitud: {sub['longitud']:.2f} m
      • Puntaje: {sub['puntaje']:.2f}
"""
        
        resumen += """
╚══════════════════════════════════════════════════════════════════════════════╝
"""
        
        self.text_resumen.setText(resumen)
        
        # ===== Tabla de subredes =====
        self.table_rutas.setRowCount(len(subredes))
        
        for i, sub in enumerate(subredes):
            self.table_rutas.setItem(i, 0, QTableWidgetItem(str(i + 1)))
            cam_str = ' → '.join(str(c) for c in sub['camaras'])
            self.table_rutas.setItem(i, 1, QTableWidgetItem(cam_str))
            self.table_rutas.setItem(i, 2, QTableWidgetItem(f"{sub['prof_max']:.3f}"))
            self.table_rutas.setItem(i, 3, QTableWidgetItem(f"{sub['prof_prom']:.3f}"))
            self.table_rutas.setItem(i, 4, QTableWidgetItem(str(sub['prof_altas'])))
            self.table_rutas.setItem(i, 5, QTableWidgetItem(f"{sub['longitud']:.2f}"))
            self.table_rutas.setItem(i, 6, QTableWidgetItem(f"{sub['puntaje']:.2f}"))
            
            if sub == ruta_critica:
                for col in range(7):
                    item = self.table_rutas.item(i, col)
                    if item:
                        item.setBackground(Qt.green)
                        item.setForeground(Qt.black)
        
        self.table_rutas.resizeColumnsToContents()
    
    def desactivar(self):
        """Desactivar herramientas activas"""
        pass