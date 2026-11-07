# -*- coding: utf-8 -*-
"""
Módulo: actualizar_camaras_desde_tuberias
Versión: 2.0 - Simplificado
Propósito: Actualizar la capa de cámaras con cotas soleras y profundidades desde tuberías
"""

from qgis.PyQt.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QPushButton, 
    QLabel, QComboBox, QMessageBox, QProgressBar,
    QGroupBox, QGridLayout, QCheckBox
)
from qgis.PyQt.QtCore import Qt, QVariant
from qgis.core import (
    QgsProject, QgsVectorLayer, QgsField,
    QgsWkbTypes
)
import os


class ActualizarCamarasDesdeTuberias:
    def __init__(self, iface):
        self.iface = iface
        self.dialog = None
        self.debug = False

    def mostrar_dialogo(self):
        """Muestra el diálogo principal"""
        self.dialog = QDialog(self.iface.mainWindow())
        self.dialog.setWindowTitle('GLC - Actualizar Cámaras desde Tuberías')
        self.dialog.setMinimumWidth(700)
        
        layout = QVBoxLayout()

        # Descripción
        lbl_desc = QLabel(
            '<b>Actualizar Cámaras con Cotas Soleras y Profundidades</b>\n\n'
            '📌 Este módulo actualiza la capa de cámaras con los datos calculados en el diseño:\n'
            '   • Zs (cota solera) desde la tubería que llega a la cámara\n'
            '   • Hexc (profundidad) = Z - Zs\n\n'
            '📌 Si una cámara recibe varias tuberías, se usa la que tenga mayor profundidad.\n'
            '📌 La cámara final (Es_Final = "SI") obtiene sus datos de la tubería que llega.\n'
            '📌 Cámaras de arranque (sin tuberías que lleguen) usan las tuberías que salen.\n\n'
            '📌 Se agregan los campos Zs y Hexc si no existen.'
        )
        lbl_desc.setWordWrap(True)
        layout.addWidget(lbl_desc)

        layout.addWidget(QLabel('-' * 60))

        # Selección de capas
        group_capas = QGroupBox('Capas')
        grid_capas = QGridLayout()

        grid_capas.addWidget(QLabel('Tuberías (diseñadas):'), 0, 0)
        self.cmb_tuberias = QComboBox()
        self._cargar_capas_linea()
        grid_capas.addWidget(self.cmb_tuberias, 0, 1)

        grid_capas.addWidget(QLabel('Cámaras (actualizar):'), 1, 0)
        self.cmb_camaras = QComboBox()
        self._cargar_capas_punto()
        grid_capas.addWidget(self.cmb_camaras, 1, 1)

        group_capas.setLayout(grid_capas)
        layout.addWidget(group_capas)

        # Opciones
        group_opciones = QGroupBox('Opciones')
        grid_opciones = QGridLayout()

        self.chk_debug = QCheckBox('Mostrar depuración en consola')
        grid_opciones.addWidget(self.chk_debug, 0, 0)

        group_opciones.setLayout(grid_opciones)
        layout.addWidget(group_opciones)

        # Barra de progreso
        self.progress = QProgressBar()
        layout.addWidget(self.progress)

        # Botones
        btn_layout = QHBoxLayout()
        btn_ejecutar = QPushButton('Actualizar Cámaras')
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
                if 'GLC_Tuberias' in layer.name():
                    self.cmb_tuberias.addItem(f"⭐ {layer.name()}", layer.id())
                else:
                    self.cmb_tuberias.addItem(layer.name(), layer.id())

    def _cargar_capas_punto(self):
        self.cmb_camaras.clear()
        for layer in QgsProject.instance().mapLayers().values():
            if layer.type() == QgsVectorLayer.VectorLayer and layer.geometryType() == QgsWkbTypes.PointGeometry:
                if 'GLC_Camaras' in layer.name():
                    self.cmb_camaras.addItem(f"⭐ {layer.name()}", layer.id())
                else:
                    self.cmb_camaras.addItem(layer.name(), layer.id())

    def _agregar_campo_si_no_existe(self, provider, nombre, tipo):
        """Agrega un campo a la capa si no existe"""
        if self.capa_camaras.fields().indexFromName(nombre) == -1:
            field = QgsField(nombre, tipo)
            provider.addAttributes([field])
            if self.debug:
                print(f"✅ Campo '{nombre}' agregado a cámaras")

    def ejecutar(self):
        """Ejecuta el proceso principal"""
        try:
            # Obtener capas
            tuberias_id = self.cmb_tuberias.currentData()
            camaras_id = self.cmb_camaras.currentData()

            if not tuberias_id or not camaras_id:
                QMessageBox.warning(self.dialog, 'Error', 'Seleccione ambas capas')
                return

            self.capa_tuberias = QgsProject.instance().mapLayer(tuberias_id)
            self.capa_camaras = QgsProject.instance().mapLayer(camaras_id)

            if not self.capa_tuberias or not self.capa_camaras:
                QMessageBox.warning(self.dialog, 'Error', 'No se encontraron las capas')
                return

            self.debug = self.chk_debug.isChecked()

            self.progress.setValue(0)

            # ============================================
            # PASO 1: Verificar campos en tuberías
            # ============================================
            
            campos_tuberias = ['ID_O', 'Ci', 'Cf', 'Zi', 'Zf', 'Zs_f', 'Hexc_f']
            for campo in campos_tuberias:
                if self.capa_tuberias.fields().indexFromName(campo) == -1:
                    QMessageBox.warning(
                        self.dialog,
                        'Error',
                        f'La capa de tuberías no tiene el campo "{campo}".\n'
                        f'Ejecute primero el Diseño por Pendiente Mínima.'
                    )
                    return

            self.progress.setValue(10)

            # ============================================
            # PASO 2: Verificar/Agregar campos en cámaras
            # ============================================
            
            self.capa_camaras.startEditing()
            provider = self.capa_camaras.dataProvider()
            
            # Solo Zs y Hexc (una sola cota por cámara)
            self._agregar_campo_si_no_existe(provider, 'Zs', QVariant.Double)
            self._agregar_campo_si_no_existe(provider, 'Hexc', QVariant.Double)
            
            self.capa_camaras.updateFields()
            self.progress.setValue(20)

            # ============================================
            # PASO 3: Construir diccionarios de tuberías
            # ============================================
            
            tuberias_dict = {}
            for feature in self.capa_tuberias.getFeatures():
                id_o = feature.attribute('ID_O')
                if id_o is None:
                    continue
                
                ci = feature.attribute('Ci')
                cf = feature.attribute('Cf')
                
                tuberias_dict[id_o] = {
                    'id_o': id_o,
                    'ci': ci,
                    'cf': cf,
                    'zi': feature.attribute('Zi') or 0,
                    'zf': feature.attribute('Zf') or 0,
                    'zs': feature.attribute('Zs_f') or 0,      # Zs_f es la cota solera en Cf
                    'hexc': feature.attribute('Hexc_f') or 0,  # Hexc_f es la profundidad en Cf
                    'feature': feature
                }

            self.progress.setValue(30)

            if self.debug:
                print(f"\n📌 Tuberías cargadas: {len(tuberias_dict)}")

            # ============================================
            # PASO 4: Identificar cámara final
            # ============================================
            
            idx_es_final = self.capa_camaras.fields().indexFromName('Es_Final')
            id_camara_final = None
            
            for feature in self.capa_camaras.getFeatures():
                if idx_es_final != -1:
                    es_final = feature.attribute('Es_Final')
                    if es_final and str(es_final).strip().upper() == 'SI':
                        id_camara_final = feature.attribute('ID_O')
                        break

            if self.debug:
                print(f"📌 Cámara final: {id_camara_final}")

            self.progress.setValue(40)

            # ============================================
            # PASO 5: Construir diccionario de cámaras
            # ============================================
            
            camaras_dict = {}
            for feature in self.capa_camaras.getFeatures():
                id_o = feature.attribute('ID_O')
                if id_o is None:
                    continue
                
                # Obtener coordenada Z de la cámara
                z = feature.attribute('Z') or 0
                
                # Determinar si es la cámara final
                es_final = (id_o == id_camara_final)
                
                camaras_dict[id_o] = {
                    'id_o': id_o,
                    'z': float(z),
                    'es_final': es_final,
                    'feature': feature,
                    'tuberias_que_llegan': [],  # Cf == id_camara (tuberías que terminan en esta cámara)
                    'tuberias_que_salen': [],   # Ci == id_camara (tuberías que comienzan en esta cámara)
                    'zs': None,
                    'hexc': None
                }

            self.progress.setValue(50)

            # ============================================
            # PASO 6: Conectar tuberías a cámaras
            # ============================================
            
            for id_t, t_data in tuberias_dict.items():
                ci = t_data['ci']
                cf = t_data['cf']
                
                if ci is not None and ci in camaras_dict:
                    camaras_dict[ci]['tuberias_que_salen'].append(id_t)
                
                if cf is not None and cf in camaras_dict:
                    camaras_dict[cf]['tuberias_que_llegan'].append(id_t)

            self.progress.setValue(60)

            if self.debug:
                print(f"\n📌 Conexiones identificadas:")
                for id_c, c_data in camaras_dict.items():
                    print(f"  Cámara {id_c}: llegan {len(c_data['tuberias_que_llegan'])}, salen {len(c_data['tuberias_que_salen'])}")

            # ============================================
            # PASO 7: Calcular Zs y Hexc para cada cámara
            # ============================================
            # REGLA: 
            # 1. Si llegan tuberías a la cámara, usar la que tenga mayor Hexc_f
            # 2. Si no llegan tuberías (cámara de arranque), usar la que sale con mayor Hexc_i
            # 3. Si es la cámara final, forzar a usar la tubería que llega
            
            total_camaras = len(camaras_dict)
            procesadas = 0

            for id_c, c_data in camaras_dict.items():
                z_camara = c_data['z']
                zs_valor = None
                hexc_valor = None
                
                # ===== 1. Buscar en tuberías que llegan a la cámara =====
                for id_t in c_data['tuberias_que_llegan']:
                    if id_t in tuberias_dict:
                        t_data = tuberias_dict[id_t]
                        # Usar Zs_f y Hexc_f de la tubería (es la cota en Cf)
                        zs_tmp = t_data['zs']
                        hexc_tmp = t_data['hexc']
                        
                        if zs_valor is None or hexc_tmp > hexc_valor:
                            zs_valor = zs_tmp
                            hexc_valor = hexc_tmp
                
                # ===== 2. Si no llegan tuberías, buscar en las que salen (cámara de arranque) =====
                if zs_valor is None:
                    for id_t in c_data['tuberias_que_salen']:
                        if id_t in tuberias_dict:
                            t_data = tuberias_dict[id_t]
                            # Usar Zs_i y Hexc_i de la tubería (es la cota en Ci)
                            # Pero solo tenemos Zs_f y Hexc_f guardados
                            # Para la cámara de arranque, necesitamos los datos de inicio
                            # Usamos los datos de la tubería, que son Zs_f y Hexc_f
                            zs_tmp = t_data['zs']
                            hexc_tmp = t_data['hexc']
                            
                            if zs_valor is None or hexc_tmp > hexc_valor:
                                zs_valor = zs_tmp
                                hexc_valor = hexc_tmp
                
                # ===== 3. Si es la cámara final, forzar a usar la tubería que llega =====
                if c_data['es_final']:
                    for id_t in c_data['tuberias_que_llegan']:
                        if id_t in tuberias_dict:
                            t_data = tuberias_dict[id_t]
                            zs_valor = t_data['zs']
                            hexc_valor = t_data['hexc']
                            break
                
                # Guardar valores en el diccionario
                c_data['zs'] = zs_valor if zs_valor is not None else z_camara
                c_data['hexc'] = hexc_valor if hexc_valor is not None else 0
                
                if self.debug:
                    print(f"  Cámara {id_c}: Z={z_camara:.3f}, Zs={c_data['zs']:.3f}, Hexc={c_data['hexc']:.3f}")
                
                procesadas += 1
                progreso = 60 + (procesadas / total_camaras) * 30
                self.progress.setValue(int(progreso))

            self.progress.setValue(90)

            # ============================================
            # PASO 8: Actualizar campos en la capa de cámaras
            # ============================================
            
            idx_zs = self.capa_camaras.fields().indexFromName('Zs')
            idx_hexc = self.capa_camaras.fields().indexFromName('Hexc')

            for id_c, c_data in camaras_dict.items():
                feature = c_data['feature']
                
                self.capa_camaras.changeAttributeValue(
                    feature.id(), 
                    idx_zs, 
                    round(c_data['zs'], 3)
                )
                self.capa_camaras.changeAttributeValue(
                    feature.id(), 
                    idx_hexc, 
                    round(c_data['hexc'], 3)
                )

            self.capa_camaras.commitChanges()
            self.capa_camaras.triggerRepaint()

            self.progress.setValue(100)

            # ============================================
            # PASO 9: Resumen
            # ============================================
            
            con_datos = 0
            for c_data in camaras_dict.values():
                if c_data['zs'] is not None and c_data['zs'] != 0:
                    con_datos += 1

            mensaje = (
                f'✅ ACTUALIZACIÓN COMPLETADA\n\n'
                f'📊 Resumen:\n'
                f'  • Tuberías procesadas: {len(tuberias_dict)}\n'
                f'  • Cámaras actualizadas: {len(camaras_dict)}\n'
                f'  • Cámaras con datos: {con_datos}\n'
                f'  • Cámara final: {id_camara_final}\n\n'
                f'📌 Campos actualizados en GLC_Camaras:\n'
                f'  • Zs (cota solera)\n'
                f'  • Hexc (profundidad = Z - Zs)\n\n'
                f'💡 Regla:\n'
                f'  • Para cada cámara, se busca la tubería que llega (Cf = id_camara)\n'
                f'  • Se usa la que tenga mayor profundidad (Hexc)\n'
                f'  • Si no llegan tuberías (cámara de arranque), se usa la que sale\n'
                f'  • La cámara final siempre usa la tubería que llega'
            )

            QMessageBox.information(self.dialog, 'Actualización Completada', mensaje)

            self.dialog.close()

        except Exception as e:
            QMessageBox.critical(self.dialog, 'Error', f'Error: {str(e)}')
            import traceback
            traceback.print_exc()

    def desactivar(self):
        pass