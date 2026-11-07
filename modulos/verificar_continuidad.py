# -*- coding: utf-8 -*-
"""
Módulo: Verificar Continuidad de la Red
Propósito: Revisa la conectividad de la red de alcantarillado
"""

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
    QTableWidgetItem, QHeaderView
)


class VerificarContinuidad:
    def __init__(self, iface):
        self.iface = iface
        self.capa_tuberias = None
        self.capa_camaras = None
        self.debug = False

    def mostrar_dialogo(self):
        """Muestra el diálogo principal"""
        dialog = QDialog(self.iface.mainWindow())
        dialog.setWindowTitle('GLC - Verificar Continuidad de la Red')
        dialog.setMinimumWidth(800)
        dialog.setMinimumHeight(600)

        layout = QVBoxLayout()

        # Título
        label_titulo = QLabel('<b>🔍 Verificar Continuidad de la Red</b>')
        label_titulo.setStyleSheet('font-size: 14pt; color: #2c3e50;')
        layout.addWidget(label_titulo)

        label_desc = QLabel(
            'Este módulo verifica la conectividad de la red y detecta problemas:\n'
            '• Cámaras con múltiples continuaciones (más de 1 salida no-Arranque)\n'
            '• Tuberías que no llegan a ninguna cámara\n'
            '• Tuberías que no salen de ninguna cámara\n'
            '• Ciclos en la red\n'
            '• Cámaras aisladas\n'
            '• Múltiples cámaras finales\n\n'
            '📌 REGLA: Una cámara puede tener múltiples Arranques, pero solo 0 o 1 continuación (no-Arranque)'
        )
        label_desc.setWordWrap(True)
        label_desc.setStyleSheet('background-color: #ecf0f1; padding: 8px; border-radius: 4px;')
        layout.addWidget(label_desc)

        layout.addWidget(QLabel('-' * 60))

        # Selección de capas
        group_capas = QGroupBox('Capas')
        grid_capas = QHBoxLayout()

        # Capa de tuberías
        grid_capas.addWidget(QLabel('Tuberías:'))
        self.combo_tuberias = QComboBox()
        for layer in QgsProject.instance().mapLayers().values():
            if isinstance(layer, QgsVectorLayer):
                if layer.geometryType() == QgsWkbTypes.LineGeometry:
                    if 'GLC_Tuberias' in layer.name():
                        self.combo_tuberias.addItem(f"⭐ {layer.name()}", layer.id())
                    else:
                        self.combo_tuberias.addItem(layer.name(), layer.id())
        grid_capas.addWidget(self.combo_tuberias)

        # Capa de cámaras
        grid_capas.addWidget(QLabel('Cámaras:'))
        self.combo_camaras = QComboBox()
        for layer in QgsProject.instance().mapLayers().values():
            if isinstance(layer, QgsVectorLayer):
                if layer.geometryType() == QgsWkbTypes.PointGeometry:
                    if 'GLC_Camaras' in layer.name():
                        self.combo_camaras.addItem(f"⭐ {layer.name()}", layer.id())
                    else:
                        self.combo_camaras.addItem(layer.name(), layer.id())
        grid_capas.addWidget(self.combo_camaras)

        group_capas.setLayout(grid_capas)
        layout.addWidget(group_capas)

        # Opciones
        group_opciones = QGroupBox('Opciones')
        grid_opciones = QHBoxLayout()

        self.chk_debug = QCheckBox('Mostrar detalles en consola')
        grid_opciones.addWidget(self.chk_debug)

        group_opciones.setLayout(grid_opciones)
        layout.addWidget(group_opciones)

        # Botón de verificación
        btn_verificar = QPushButton('🔍 Verificar Continuidad')
        btn_verificar.setStyleSheet(
            'background-color: #2196f3; color: white; font-weight: bold; padding: 10px;'
        )
        btn_verificar.clicked.connect(lambda: self.verificar(dialog))
        layout.addWidget(btn_verificar)

        # Barra de progreso
        self.progress = QProgressBar()
        layout.addWidget(self.progress)

        # Pestañas para resultados
        self.tabs = QTabWidget()

        # Pestaña: Resumen
        self.tab_resumen = QWidget()
        layout_resumen = QVBoxLayout()
        self.text_resumen = QTextEdit()
        self.text_resumen.setReadOnly(True)
        self.text_resumen.setStyleSheet('font-family: monospace;')
        layout_resumen.addWidget(self.text_resumen)
        self.tab_resumen.setLayout(layout_resumen)
        self.tabs.addTab(self.tab_resumen, '📊 Resumen')

        # Pestaña: Errores
        self.tab_errores = QWidget()
        layout_errores = QVBoxLayout()
        self.table_errores = QTableWidget()
        self.table_errores.setColumnCount(4)
        self.table_errores.setHorizontalHeaderLabels(['ID', 'Tipo', 'Descripción', 'Severidad'])
        self.table_errores.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        layout_errores.addWidget(self.table_errores)
        self.tab_errores.setLayout(layout_errores)
        self.tabs.addTab(self.tab_errores, '❌ Errores y Advertencias')

        # Pestaña: Detalle de cámaras
        self.tab_camaras = QWidget()
        layout_camaras = QVBoxLayout()
        self.table_camaras = QTableWidget()
        self.table_camaras.setColumnCount(7)
        self.table_camaras.setHorizontalHeaderLabels(['ID_O', 'Llegan', 'Salen', 'Arranques', 'Continuaciones', 'Es Final', 'Estado'])
        self.table_camaras.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        layout_camaras.addWidget(self.table_camaras)
        self.tab_camaras.setLayout(layout_camaras)
        self.tabs.addTab(self.tab_camaras, '🏗️ Cámaras')

        layout.addWidget(self.tabs)

        # Botón cerrar
        btn_cerrar = QPushButton('Cerrar')
        btn_cerrar.clicked.connect(dialog.accept)
        layout.addWidget(btn_cerrar)

        dialog.setLayout(layout)
        dialog.exec_()

    def verificar(self, dialog):
        """Ejecuta la verificación de continuidad"""
        
        tuberias_id = self.combo_tuberias.currentData()
        camaras_id = self.combo_camaras.currentData()

        if not tuberias_id or not camaras_id:
            QMessageBox.warning(
                self.iface.mainWindow(),
                'Error',
                'Debe seleccionar las capas de tuberías y cámaras'
            )
            return

        self.capa_tuberias = QgsProject.instance().mapLayer(tuberias_id)
        self.capa_camaras = QgsProject.instance().mapLayer(camaras_id)

        if not self.capa_tuberias or not self.capa_camaras:
            QMessageBox.warning(
                self.iface.mainWindow(),
                'Error',
                'No se encontraron las capas seleccionadas'
            )
            return

        self.debug = self.chk_debug.isChecked()

        self.progress.setValue(0)
        self.text_resumen.clear()
        self.table_errores.setRowCount(0)
        self.table_camaras.setRowCount(0)

        self.progress.setValue(10)

        # ============================================
        # PASO 1: Construir diccionarios
        # ============================================

        tuberias_dict = {}
        for feature in self.capa_tuberias.getFeatures():
            id_o = feature.attribute('ID_O')
            if id_o is None:
                continue

            tuberias_dict[id_o] = {
                'id_o': id_o,
                'ci': feature.attribute('Ci'),
                'cf': feature.attribute('Cf'),
                'cab_ata': feature.attribute('cab_ata') or '',
                'feature': feature
            }

        self.progress.setValue(20)

        camaras_dict = {}
        for feature in self.capa_camaras.getFeatures():
            id_o = feature.attribute('ID_O')
            if id_o is None:
                continue

            # Obtener Lineas_ID
            lineas_id_str = feature.attribute('Lineas_ID') or ''
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

            # Verificar si tiene fin = 1
            es_final = feature.attribute('fin') == 1

            camaras_dict[id_o] = {
                'id_o': id_o,
                'lineas': lineas_list,
                'es_final': es_final,
                'feature': feature,
                'tuberias_que_llegan': [],
                'tuberias_que_salen': []
            }

        self.progress.setValue(30)

        # ============================================
        # PASO 2: Verificar conexiones
        # ============================================

        errores = []
        advertencias = []

        # 2a. Verificar qué tuberías llegan a cada cámara (Cf)
        for id_t, t_data in tuberias_dict.items():
            cf = t_data['cf']
            if cf is not None and cf in camaras_dict:
                camaras_dict[cf]['tuberias_que_llegan'].append(id_t)
            elif cf is not None and cf not in camaras_dict:
                errores.append({
                    'id': id_t,
                    'tipo': 'Tubería sin cámara destino',
                    'desc': f'Cf={cf} no existe en la capa de cámaras',
                    'severidad': 'Error'
                })

        # 2b. Verificar qué tuberías salen de cada cámara (Ci)
        for id_t, t_data in tuberias_dict.items():
            ci = t_data['ci']
            if ci is not None and ci in camaras_dict:
                camaras_dict[ci]['tuberias_que_salen'].append(id_t)
            elif ci is not None and ci not in camaras_dict:
                errores.append({
                    'id': id_t,
                    'tipo': 'Tubería sin cámara origen',
                    'desc': f'Ci={ci} no existe en la capa de cámaras',
                    'severidad': 'Error'
                })

        self.progress.setValue(50)

        # 2c. Verificar que ningún Ci sea igual a Cf en la misma tubería (bucle de 1)
        for id_t, t_data in tuberias_dict.items():
            if t_data['ci'] is not None and t_data['cf'] is not None:
                if t_data['ci'] == t_data['cf']:
                    errores.append({
                        'id': id_t,
                        'tipo': 'Bucle de 1 (Ci = Cf)',
                        'desc': f'La tubería {id_t} comienza y termina en la misma cámara',
                        'severidad': 'Error'
                    })

        # 2d. Verificar cámaras con salidas
        for id_c, c_data in camaras_dict.items():
            salidas = c_data['tuberias_que_salen']
            n_salidas = len(salidas)
            
            if n_salidas == 0:
                # Cámara sin salidas → es final, OK si tiene fin=1
                continue
                
            # Contar cuántas salidas son Arranque y cuántas NO son Arranque
            arranques = []
            continuaciones = []
            for id_t in salidas:
                if tuberias_dict.get(id_t, {}).get('cab_ata') == 'Arranque':
                    arranques.append(id_t)
                else:
                    continuaciones.append(id_t)
            
            n_arranques = len(arranques)
            n_continuaciones = len(continuaciones)
            
            # ===== REGLA: Solo 0 o 1 continuaciones permitidas =====
            if n_continuaciones > 1:
                errores.append({
                    'id': id_c,
                    'tipo': 'Múltiples continuaciones',
                    'desc': f'Cámara {id_c} tiene {n_salidas} salidas: {n_arranques} Arranque(s) y {n_continuaciones} continuaciones. Solo se permite 1 continuación.',
                    'severidad': 'Error'
                })

        self.progress.setValue(60)

        # 2e. Identificar cámaras finales (sin salidas)
        camaras_finales = []
        for id_c, c_data in camaras_dict.items():
            if len(c_data['tuberias_que_salen']) == 0:
                camaras_finales.append(id_c)

        if len(camaras_finales) == 0:
            errores.append({
                'id': 'SISTEMA',
                'tipo': 'Sin cámara final',
                'desc': 'No se encontró ninguna cámara sin salidas (cámara final)',
                'severidad': 'Error'
            })
        elif len(camaras_finales) > 1:
            # Verificar cuántas tienen fin=1
            finales_marcadas = [c for c in camaras_finales if camaras_dict[c]['es_final']]
            if len(finales_marcadas) == 0:
                errores.append({
                    'id': 'SISTEMA',
                    'tipo': 'Múltiples cámaras finales sin marcar',
                    'desc': f'Hay {len(camaras_finales)} cámaras sin salidas y ninguna tiene fin=1: {camaras_finales}',
                    'severidad': 'Error'
                })
            elif len(finales_marcadas) > 1:
                errores.append({
                    'id': 'SISTEMA',
                    'tipo': 'Múltiples cámaras finales marcadas',
                    'desc': f'Hay {len(finales_marcadas)} cámaras con fin=1: {finales_marcadas}',
                    'severidad': 'Error'
                })
            else:
                # Una está marcada, las otras no → advertencia
                otras_finales = [c for c in camaras_finales if not camaras_dict[c]['es_final']]
                if otras_finales:
                    advertencias.append({
                        'id': 'SISTEMA',
                        'tipo': 'Cámaras finales sin marcar',
                        'desc': f'Hay {len(otras_finales)} cámaras sin salidas que no tienen fin=1: {otras_finales}',
                        'severidad': 'Advertencia'
                    })

        self.progress.setValue(70)

        # 2f. Detectar ciclos (DFS)
        ciclos = self.detectar_ciclos(tuberias_dict, camaras_dict)
        for ciclo in ciclos:
            errores.append({
                'id': 'SISTEMA',
                'tipo': 'Ciclo detectado',
                'desc': f'Ciclo: {" → ".join(str(c) for c in ciclo[:5])}{"..." if len(ciclo) > 5 else ""}',
                'severidad': 'Error'
            })

        self.progress.setValue(80)

        # 2g. Verificar cámaras aisladas (sin tuberías que lleguen ni salgan)
        camaras_aisladas = []
        for id_c, c_data in camaras_dict.items():
            if len(c_data['tuberias_que_llegan']) == 0 and len(c_data['tuberias_que_salen']) == 0:
                # Si no es una cámara final marcada
                if not c_data['es_final']:
                    camaras_aisladas.append(id_c)

        if camaras_aisladas:
            errores.append({
                'id': 'SISTEMA',
                'tipo': 'Cámaras aisladas',
                'desc': f'{len(camaras_aisladas)} cámaras no tienen tuberías que lleguen ni salgan: {camaras_aisladas[:5]}{"..." if len(camaras_aisladas) > 5 else ""}',
                'severidad': 'Error'
            })

        self.progress.setValue(90)

        # ============================================
        # PASO 3: Mostrar resultados
        # ============================================

        # Resumen
        self.mostrar_resumen(tuberias_dict, camaras_dict, errores, advertencias, ciclos)

        # Tabla de errores
        self.mostrar_errores(errores, advertencias)

        # Tabla de cámaras
        self.mostrar_camaras(camaras_dict, tuberias_dict)

        self.progress.setValue(100)

        # Mensaje final
        if errores:
            QMessageBox.warning(
                self.iface.mainWindow(),
                'Verificación Completada',
                f'Se encontraron {len(errores)} errores y {len(advertencias)} advertencias.\n'
                'Revisa los detalles en las pestañas.\n\n'
                '⚠️ TODOS los errores deben corregirse manualmente.'
            )
        elif advertencias:
            QMessageBox.information(
                self.iface.mainWindow(),
                'Verificación Completada',
                f'Se encontraron {len(advertencias)} advertencias.\n'
                'La red es funcional pero tiene aspectos a mejorar.\n\n'
                'Revisa los detalles en la pestaña de errores.'
            )
        else:
            QMessageBox.information(
                self.iface.mainWindow(),
                'Verificación Completada',
                '✅ ¡La red está perfectamente conectada!\n'
                'No se encontraron errores ni advertencias.'
            )

    def detectar_ciclos(self, tuberias_dict, camaras_dict):
        """Detecta ciclos en la red usando DFS"""
        ciclos = []
        visitados = set()
        pila = []

        # Construir grafo: cámara -> [cámaras destino] (solo continuaciones, no Arranques)
        grafo = {}
        for id_c, c_data in camaras_dict.items():
            grafo[id_c] = []
            for id_t in c_data['tuberias_que_salen']:
                # Solo seguir continuaciones (NO Arranques) para detectar ciclos
                if tuberias_dict.get(id_t, {}).get('cab_ata') != 'Arranque':
                    cf = tuberias_dict.get(id_t, {}).get('cf')
                    if cf is not None and cf in camaras_dict:
                        grafo[id_c].append(cf)

        def dfs(nodo, camino):
            if nodo in pila:
                # Encontrado ciclo
                idx = pila.index(nodo)
                ciclo = pila[idx:] + [nodo]
                if len(ciclo) > 2:  # Ignorar ciclos de 1 (ya detectados)
                    ciclos.append(ciclo)
                return
            if nodo in visitados:
                return

            visitados.add(nodo)
            pila.append(nodo)

            for vecino in grafo.get(nodo, []):
                dfs(vecino, camino + [nodo])

            pila.pop()

        # Ejecutar DFS desde cada nodo
        for nodo in grafo:
            if nodo not in visitados:
                dfs(nodo, [])

        return ciclos

    def mostrar_resumen(self, tuberias_dict, camaras_dict, errores, advertencias, ciclos):
        """Muestra el resumen en la pestaña correspondiente"""
        
        total_tuberias = len(tuberias_dict)
        total_camaras = len(camaras_dict)

        # Contar cabeceras
        cabeceras = [id_t for id_t, t_data in tuberias_dict.items() if t_data['cab_ata'] == 'Arranque']

        # Contar cámaras finales
        finales = [id_c for id_c, c_data in camaras_dict.items() if len(c_data['tuberias_que_salen']) == 0]
        finales_marcadas = [id_c for id_c in finales if camaras_dict[id_c]['es_final']]

        # Contar conexiones válidas
        conexiones = sum(1 for t_data in tuberias_dict.values() 
                        if t_data['ci'] is not None and t_data['cf'] is not None
                        and t_data['ci'] in camaras_dict and t_data['cf'] in camaras_dict)

        resumen = f"""
╔══════════════════════════════════════════════════════════════════════════════╗
║                              RESUMEN DE LA RED                               ║
╠══════════════════════════════════════════════════════════════════════════════╣
║                                                                              ║
║  📊 ESTADÍSTICAS GENERALES                                                   ║
║  ──────────────────────────────────────────────────────────────────────────  ║
║  • Total de tuberías:              {total_tuberias:>6}                            ║
║  • Total de cámaras:               {total_camaras:>6}                            ║
║  • Conexiones válidas:             {conexiones:>6}                            ║
║  • Cabeceras (Arranque):           {len(cabeceras):>6}                            ║
║  • Cámaras finales (sin salida):   {len(finales):>6}                            ║
║  • Cámaras finales (fin=1):        {len(finales_marcadas):>6}                            ║
║                                                                              ║
║  📋 RESULTADOS DE LA VERIFICACIÓN                                             ║
║  ──────────────────────────────────────────────────────────────────────────  ║
║  • Errores encontrados:            {len(errores):>6}                            ║
║  • Advertencias:                   {len(advertencias):>6}                            ║
║  • Ciclos detectados:              {len(ciclos):>6}                            ║
║                                                                              ║
║  📌 ESTADO:                                                                  ║
║  {'✅ RED CORRECTA' if len(errores) == 0 and len(advertencias) == 0 else '⚠️ REVISAR - Se encontraron problemas'}                    ║
║                                                                              ║
║  ⚠️ NOTA: Todos los errores deben corregirse manualmente                      ║
║                                                                              ║
╚══════════════════════════════════════════════════════════════════════════════╝
"""

        self.text_resumen.setText(resumen)

        if self.debug:
            print(resumen)

    def mostrar_errores(self, errores, advertencias):
        """Muestra la tabla de errores y advertencias"""
        
        self.table_errores.setRowCount(len(errores) + len(advertencias))
        
        row = 0
        for error in errores:
            self.table_errores.setItem(row, 0, QTableWidgetItem(str(error['id'])))
            self.table_errores.setItem(row, 1, QTableWidgetItem(error['tipo']))
            self.table_errores.setItem(row, 2, QTableWidgetItem(error['desc']))
            item_sev = QTableWidgetItem('❌ ' + error['severidad'])
            item_sev.setBackground(Qt.red)
            item_sev.setForeground(Qt.white)
            self.table_errores.setItem(row, 3, item_sev)
            row += 1

        for adv in advertencias:
            self.table_errores.setItem(row, 0, QTableWidgetItem(str(adv['id'])))
            self.table_errores.setItem(row, 1, QTableWidgetItem(adv['tipo']))
            self.table_errores.setItem(row, 2, QTableWidgetItem(adv['desc']))
            item_sev = QTableWidgetItem('⚠️ ' + adv['severidad'])
            item_sev.setBackground(Qt.yellow)
            self.table_errores.setItem(row, 3, item_sev)
            row += 1

        self.table_errores.resizeColumnsToContents()

    def mostrar_camaras(self, camaras_dict, tuberias_dict):
        """Muestra el detalle de cámaras"""
        
        self.table_camaras.setRowCount(len(camaras_dict))
        
        row = 0
        for id_c, c_data in sorted(camaras_dict.items()):
            self.table_camaras.setItem(row, 0, QTableWidgetItem(str(id_c)))
            
            llegan = ', '.join(str(t) for t in c_data['tuberias_que_llegan'][:5])
            if len(c_data['tuberias_que_llegan']) > 5:
                llegan += f'... (+{len(c_data["tuberias_que_llegan"]) - 5})'
            self.table_camaras.setItem(row, 1, QTableWidgetItem(llegan or '—'))
            
            salen = ', '.join(str(t) for t in c_data['tuberias_que_salen'][:5])
            if len(c_data['tuberias_que_salen']) > 5:
                salen += f'... (+{len(c_data["tuberias_que_salen"]) - 5})'
            self.table_camaras.setItem(row, 2, QTableWidgetItem(salen or '—'))
            
            # Contar Arranques y Continuaciones
            arranques = []
            continuaciones = []
            for id_t in c_data['tuberias_que_salen']:
                if tuberias_dict.get(id_t, {}).get('cab_ata') == 'Arranque':
                    arranques.append(id_t)
                else:
                    continuaciones.append(id_t)
            
            arranques_str = ', '.join(str(a) for a in arranques)
            continuaciones_str = ', '.join(str(c) for c in continuaciones)
            
            self.table_camaras.setItem(row, 3, QTableWidgetItem(arranques_str or '—'))
            self.table_camaras.setItem(row, 4, QTableWidgetItem(continuaciones_str or '—'))
            self.table_camaras.setItem(row, 5, QTableWidgetItem('✅' if c_data['es_final'] else ''))
            
            # Estado de la cámara
            n_continuaciones = len(continuaciones)
            
            if n_continuaciones == 0:
                estado = '✅ FINAL (0 continuaciones)'
            elif n_continuaciones == 1:
                estado = '✅ OK (1 continuación)'
            else:
                estado = f'❌ ERROR ({n_continuaciones} continuaciones)'
            
            self.table_camaras.setItem(row, 6, QTableWidgetItem(estado))
            
            row += 1
        
        self.table_camaras.resizeColumnsToContents()

    def desactivar(self):
        """Desactivar herramientas activas"""
        pass