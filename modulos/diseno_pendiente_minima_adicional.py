# -*- coding: utf-8 -*-
from qgis.core import (
    QgsProject, QgsVectorLayer, QgsFeature,
    QgsGeometry, QgsPointXY, QgsField,
    QgsWkbTypes, QgsLineString, QgsPoint
)
from qgis.PyQt.QtCore import Qt, QVariant
from qgis.PyQt.QtWidgets import (
    QMessageBox, QDialog, QVBoxLayout, QLabel,
    QPushButton, QComboBox, QProgressBar, QFileDialog,
    QDoubleSpinBox, QGroupBox, QFormLayout, QHBoxLayout,
    QLineEdit, QCheckBox, QTabWidget, QWidget, QTableWidget,
    QTableWidgetItem, QHeaderView, QInputDialog
)
import math
import os


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


class DisenoPendienteMinimaAdicional:
    def __init__(self, iface):
        self.iface = iface
        self.capa_tuberias = None
        self.capa_camaras = None
        self.capa_diametros = None
        self.diametros_disponibles = []
        self.pendientes_minimas = {}  # Diccionario: diametro -> pendiente_minima (%)
        self.camaras_dict = {}
        self.tuberias_dict = {}
        self.max_iteraciones = 200

        # Parámetros de diseño
        self.tractiva_min = 1.0  # Pa
        self.n_manning = 0.013
        self.profundidad_min = 1.3  # m
        self.hD_max = 0.7
        self.diametro_min = 150  # mm
        self.q_rel_inicial = 0.15

        # Constantes
        self.g = 9.81
        self.gamma_agua = 9810

        # Control de depuración
        self.debug = False

    def mostrar_dialogo(self):
        """Muestra el diálogo de configuración del diseño"""
        dialog = QDialog(self.iface.mainWindow())
        dialog.setWindowTitle('GLC - Diseño por Pendiente Mínima (con tabla)')
        dialog.setMinimumWidth(850)
        dialog.setMinimumHeight(650)

        layout = QVBoxLayout()

        label_titulo = QLabel(
            '<b>Diseño Hidráulico por Pendiente Mínima (con tabla de pendientes)</b>'
        )
        label_titulo.setStyleSheet('font-size: 14pt; color: #2C3E50; padding: 5px;')
        layout.addWidget(label_titulo)

        tabs = QTabWidget()

        # Pestaña 1: Capas
        tab_capas = QWidget()
        layout_capas = QVBoxLayout()

        grupo_capas = QGroupBox('Selección de capas')
        form_capas = QFormLayout()

        self.combo_tuberias = QComboBox()
        self.combo_tuberias.addItem('-- Seleccionar --', '')
        for layer in QgsProject.instance().mapLayers().values():
            if isinstance(layer, QgsVectorLayer):
                if layer.geometryType() == QgsWkbTypes.LineGeometry:
                    if 'GLC_Tuberias' in layer.name() or \
                       'tuberia' in layer.name().lower():
                        self.combo_tuberias.addItem(f"⭐ {layer.name()}", layer.id())
                    else:
                        self.combo_tuberias.addItem(layer.name(), layer.id())
        form_capas.addRow('Tuberías:', self.combo_tuberias)

        self.combo_camaras = QComboBox()
        self.combo_camaras.addItem('-- Seleccionar --', '')
        for layer in QgsProject.instance().mapLayers().values():
            if isinstance(layer, QgsVectorLayer):
                if layer.geometryType() == QgsWkbTypes.PointGeometry:
                    if 'GLC_Camaras' in layer.name() or \
                       'camara' in layer.name().lower():
                        self.combo_camaras.addItem(f"⭐ {layer.name()}", layer.id())
                    else:
                        self.combo_camaras.addItem(layer.name(), layer.id())
        form_capas.addRow('Cámaras:', self.combo_camaras)

        self.combo_diametros = QComboBox()
        self.combo_diametros.addItem('-- Seleccionar --', '')
        for layer in QgsProject.instance().mapLayers().values():
            if isinstance(layer, QgsVectorLayer):
                nombre = layer.name().lower()
                if ('diam' in nombre or 'd_mm' in nombre or 'planilla' in nombre):
                    self.combo_diametros.addItem(f"⭐ {layer.name()}", layer.id())
                elif layer.geometryType() == QgsWkbTypes.NullGeometry:
                    self.combo_diametros.addItem(layer.name(), layer.id())
        form_capas.addRow('Diámetros (capa):', self.combo_diametros)

        btn_cargar_diametros = QPushButton(
            'Cargar diámetros y pendientes desde capa seleccionada'
        )
        btn_cargar_diametros.setStyleSheet('background-color: #3498DB; color: white;')
        btn_cargar_diametros.clicked.connect(
            self.cargar_diametros_y_pendientes_desde_capa
        )
        form_capas.addRow('', btn_cargar_diametros)

        self.lbl_diametros = QLabel('Diámetros cargados: Ninguno')
        self.lbl_diametros.setStyleSheet('color: #666; font-style: italic;')
        form_capas.addRow('Estado:', self.lbl_diametros)

        grupo_capas.setLayout(form_capas)
        layout_capas.addWidget(grupo_capas)

        grupo_preview = QGroupBox('Vista previa de diámetros y pendientes')
        layout_preview = QVBoxLayout()

        self.tabla_diametros = QTableWidget()
        self.tabla_diametros.setColumnCount(2)
        self.tabla_diametros.setHorizontalHeaderLabels(
            ['Diámetro (mm)', 'Pendiente mínima (%)']
        )
        self.tabla_diametros.horizontalHeader().setSectionResizeMode(
            1, QHeaderView.Stretch
        )
        self.tabla_diametros.setMaximumHeight(200)
        layout_preview.addWidget(self.tabla_diametros)

        grupo_preview.setLayout(layout_preview)
        layout_capas.addWidget(grupo_preview)

        layout_capas.addStretch()
        tab_capas.setLayout(layout_capas)
        tabs.addTab(tab_capas, 'Capas y Datos')

        # Pestaña 2: Parámetros
        tab_parametros = QWidget()
        layout_parametros = QVBoxLayout()

        grupo_parametros = QGroupBox('Parámetros hidráulicos')
        form_param = QFormLayout()

        # Tensión tractiva
        self.spin_tractiva = QDoubleSpinBox()
        self.spin_tractiva.setRange(0.1, 10.0)
        self.spin_tractiva.setDecimals(2)
        self.spin_tractiva.setSingleStep(0.1)
        self.spin_tractiva.setSuffix(' Pa')
        self.spin_tractiva.setValue(self.tractiva_min)
        form_param.addRow('Tensión tractiva mínima:', self.spin_tractiva)

        # Manning
        self.spin_manning = QDoubleSpinBox()
        self.spin_manning.setRange(0.001, 0.1)
        self.spin_manning.setDecimals(4)
        self.spin_manning.setSingleStep(0.001)
        self.spin_manning.setValue(self.n_manning)
        form_param.addRow('Coeficiente de Manning (n):', self.spin_manning)

        # Profundidad mínima
        self.spin_profundidad = QDoubleSpinBox()
        self.spin_profundidad.setRange(0.1, 10.0)
        self.spin_profundidad.setDecimals(2)
        self.spin_profundidad.setSingleStep(0.1)
        self.spin_profundidad.setSuffix(' m')
        self.spin_profundidad.setValue(self.profundidad_min)
        form_param.addRow('Profundidad mínima:', self.spin_profundidad)

        # Relación h/D máxima
        self.spin_hD = QDoubleSpinBox()
        self.spin_hD.setRange(0.1, 0.95)
        self.spin_hD.setDecimals(2)
        self.spin_hD.setSingleStep(0.05)
        self.spin_hD.setValue(self.hD_max)
        form_param.addRow('Relación h/D máxima:', self.spin_hD)

        # Diámetro mínimo
        self.spin_diametro_min = QDoubleSpinBox()
        self.spin_diametro_min.setRange(100, 2000)
        self.spin_diametro_min.setDecimals(0)
        self.spin_diametro_min.setSingleStep(50)
        self.spin_diametro_min.setSuffix(' mm')
        self.spin_diametro_min.setValue(self.diametro_min)
        form_param.addRow('Diámetro mínimo:', self.spin_diametro_min)

        # q/Q inicial
        self.spin_q_rel = QDoubleSpinBox()
        self.spin_q_rel.setRange(0.01, 0.5)
        self.spin_q_rel.setDecimals(2)
        self.spin_q_rel.setSingleStep(0.01)
        self.spin_q_rel.setValue(self.q_rel_inicial)
        form_param.addRow('q/Q inicial (estimación):', self.spin_q_rel)

        grupo_parametros.setLayout(form_param)
        layout_parametros.addWidget(grupo_parametros)

        grupo_avanzado = QGroupBox('Opciones avanzadas')
        form_avanzado = QFormLayout()

        # Máx iteraciones
        self.spin_iteraciones = QDoubleSpinBox()
        self.spin_iteraciones.setRange(50, 5000)
        self.spin_iteraciones.setDecimals(0)
        self.spin_iteraciones.setSingleStep(100)
        self.spin_iteraciones.setValue(self.max_iteraciones)
        form_avanzado.addRow('Máx. iteraciones:', self.spin_iteraciones)

        self.chk_debug = QCheckBox('Mostrar mensajes de depuración (consola)')
        self.chk_debug.setChecked(self.debug)
        form_avanzado.addRow('', self.chk_debug)

        grupo_avanzado.setLayout(form_avanzado)
        layout_parametros.addWidget(grupo_avanzado)

        layout_parametros.addStretch()
        tab_parametros.setLayout(layout_parametros)
        tabs.addTab(tab_parametros, 'Parámetros')

        layout.addWidget(tabs)

        self.progress = QProgressBar()
        self.progress.setValue(0)
        layout.addWidget(self.progress)

        hbox_botones = QHBoxLayout()

        btn_disenar = QPushButton('Diseñar Red')
        btn_disenar.setStyleSheet(
            'background-color: #27AE60; color: white; font-weight: bold; '
            'padding: 10px; font-size: 12pt;'
        )
        btn_disenar.clicked.connect(lambda: self.ejecutar_diseno(dialog))
        hbox_botones.addWidget(btn_disenar)

        btn_cancelar = QPushButton('Cancelar')
        btn_cancelar.clicked.connect(dialog.reject)
        hbox_botones.addWidget(btn_cancelar)

        layout.addLayout(hbox_botones)

        dialog.setLayout(layout)
        self.combo_diametros.currentIndexChanged.connect(
            self.on_capa_diametros_cambiada
        )

        dialog.exec_()

    def on_capa_diametros_cambiada(self):
        self.lbl_diametros.setText('Diámetros cargados: Ninguno')
        self.lbl_diametros.setStyleSheet('color: #666; font-style: italic;')
        self.tabla_diametros.setRowCount(0)
        self.diametros_disponibles = []
        self.pendientes_minimas = {}

    def cargar_diametros_y_pendientes_desde_capa(self):
        """Carga los diámetros y sus pendientes mínimas desde la capa seleccionada en QGIS"""
        diametros_id = self.combo_diametros.currentData()

        if not diametros_id:
            QMessageBox.warning(
                self.iface.mainWindow(),
                'Advertencia',
                'Debe seleccionar una capa de diámetros'
            )
            return

        layer = QgsProject.instance().mapLayer(diametros_id)
        if not layer:
            QMessageBox.warning(
                self.iface.mainWindow(),
                'Error',
                'No se encontró la capa seleccionada'
            )
            return

        if not isinstance(layer, QgsVectorLayer):
            QMessageBox.warning(
                self.iface.mainWindow(),
                'Error',
                'La capa seleccionada no es una capa vectorial'
            )
            return

        campos = [field.name() for field in layer.fields()]
        campo_diametro = None
        campo_pendiente = None

        posibles_campos_diam = ['d_mm', 'diametro', 'diam', 'D_mm', 'D',
                                'diametro_mm', 'diam_mm']
        for campo in posibles_campos_diam:
            if campo in campos:
                campo_diametro = campo
                break

        posibles_campos_pend = ['p_por', 'pendiente', 'pend_min', 'S_min', 's_min']
        for campo in posibles_campos_pend:
            if campo in campos:
                campo_pendiente = campo
                break

        if not campo_diametro:
            campo_diametro, ok = QInputDialog.getItem(
                self.iface.mainWindow(),
                'Seleccionar campo de diámetros',
                'Seleccione el campo que contiene los diámetros:',
                campos,
                0,
                False
            )
            if not ok:
                return

        if not campo_pendiente:
            campo_pendiente, ok = QInputDialog.getItem(
                self.iface.mainWindow(),
                'Seleccionar campo de pendiente mínima',
                'Seleccione el campo que contiene las pendientes mínimas:',
                campos,
                0,
                False
            )
            if not ok:
                return

        self.diametros_disponibles = []
        self.pendientes_minimas = {}

        idx_diam = layer.fields().indexFromName(campo_diametro)
        idx_pend = layer.fields().indexFromName(campo_pendiente)

        if idx_diam == -1:
            QMessageBox.warning(
                self.iface.mainWindow(),
                'Error',
                f'No se encontró el campo "{campo_diametro}"'
            )
            return

        if idx_pend == -1:
            QMessageBox.warning(
                self.iface.mainWindow(),
                'Error',
                f'No se encontró el campo "{campo_pendiente}"'
            )
            return

        for feature in layer.getFeatures():
            valor_diam = feature.attribute(idx_diam)
            valor_pend = feature.attribute(idx_pend)

            if valor_diam is not None and valor_pend is not None:
                try:
                    diam = float(valor_diam)
                    pend = float(valor_pend)
                    if diam > 0 and diam < 10000 and pend > 0:
                        self.diametros_disponibles.append(diam)
                        self.pendientes_minimas[diam] = pend
                except Exception:
                    pass

        if not self.diametros_disponibles:
            QMessageBox.warning(
                self.iface.mainWindow(),
                'Advertencia',
                f'No se encontraron diámetros válidos con sus pendientes mínimas'
            )
            return

        self.diametros_disponibles = sorted(set(self.diametros_disponibles))

        self.tabla_diametros.setRowCount(len(self.diametros_disponibles))
        for i, diam in enumerate(self.diametros_disponibles):
            self.tabla_diametros.setItem(i, 0, QTableWidgetItem(f"{diam:.0f}"))
            pend = self.pendientes_minimas.get(diam, 0)
            self.tabla_diametros.setItem(i, 1, QTableWidgetItem(f"{pend:.3f}"))

        self.lbl_diametros.setText(
            f'✅ Cargados: {len(self.diametros_disponibles)} diámetros '
            f'con pendientes mínimas'
        )
        self.lbl_diametros.setStyleSheet('color: #27AE60; font-weight: bold;')

        QMessageBox.information(
            self.iface.mainWindow(),
            'Éxito',
            f'Se cargaron {len(self.diametros_disponibles)} diámetros con sus pendientes mínimas\n'
            f'Rango diámetros: {min(self.diametros_disponibles):.0f} - '
            f'{max(self.diametros_disponibles):.0f} mm'
        )

    def ejecutar_diseno(self, dialog):
        """Ejecuta el diseño de la red por orden topológico con iteraciones de corrección"""

        if not self.diametros_disponibles:
            QMessageBox.warning(
                self.iface.mainWindow(),
                'Error',
                'Debe cargar una capa de diámetros válida con sus pendientes mínimas'
            )
            return

        self.tractiva_min = self.spin_tractiva.value()
        self.n_manning = self.spin_manning.value()
        self.profundidad_min = self.spin_profundidad.value()
        self.hD_max = self.spin_hD.value()
        self.diametro_min = self.spin_diametro_min.value()
        self.q_rel_inicial = self.spin_q_rel.value()
        self.max_iteraciones = int(self.spin_iteraciones.value())
        self.debug = self.chk_debug.isChecked()

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
            QMessageBox.warning(self.iface.mainWindow(), 'Error',
                                'No se encontraron las capas seleccionadas')
            return

        self.crear_campo_zs1()

        campos_requeridos = ['ID_O', 'Ci', 'Cf', 'L', 'cab_ata', 'qdise']
        for campo in campos_requeridos:
            if self.capa_tuberias.fields().indexFromName(campo) == -1:
                QMessageBox.warning(
                    self.iface.mainWindow(),
                    'Error',
                    f'La capa de tuberías no tiene el campo "{campo}"\n'
                    f'Ejecute primero el módulo de Cálculo de Caudales.'
                )
                return

        self.progress.setValue(5)
        self.construir_diccionarios()
        self.progress.setValue(10)

        # Identificar tuberías de arranque
        tuberias_arranque = []
        for id_t, t_data in self.tuberias_dict.items():
            if t_data['cab_ata'] == 'Arranque':
                tuberias_arranque.append(id_t)

        if not tuberias_arranque:
            QMessageBox.warning(
                self.iface.mainWindow(),
                'Error',
                'No se encontraron tuberías de arranque'
            )
            return

        if self.debug:
            print("\n" + "=" * 60)
            print("DISEÑO POR PENDIENTE MÍNIMA CON TABLA E ITERACIONES")
            print("=" * 60)
            print(f"📌 Arranques: {len(tuberias_arranque)}")
            print(f"📌 Tuberías: {len(self.tuberias_dict)}")
            print("=" * 60)

        # ================================================================
        # ===== PASO 1: PRIMER DISEÑO TOPOLÓGICO INICIAL =====
        # ================================================================
        if self.debug:
            print("\n" + "=" * 60)
            print("PASO 1: PRIMER DISEÑO TOPOLÓGICO INICIAL")
            print("=" * 60)

        self.disenar_red_topologicamente(tuberias_arranque)

        # ================================================================
        # ===== PASO 2: ASIGNAR Zs MÍNIMAS A CÁMARAS =====
        # ================================================================
        if self.debug:
            print("\n" + "=" * 60)
            print("PASO 2: ASIGNAR Zs MÍNIMAS A CÁMARAS")
            print("=" * 60)

        self.asignar_cota_minima_a_camaras()

        # ================================================================
        # ===== PASO 3: ITERACIONES DE CORRECCIÓN CON TOPOLÓGICO =====
        # ================================================================
        MAX_ITER = 20
        iteracion = 0
        cambios_realizados = True

        while cambios_realizados and iteracion < MAX_ITER:
            cambios_realizados = False
            iteracion += 1

            if self.debug:
                print("\n" + "=" * 60)
                print(f"PASO 3: ITERACIÓN DE CORRECCIÓN {iteracion}")
                print("=" * 60)

            # Obtener orden topológico
            tuberias_ordenadas = self.ordenar_tuberias(tuberias_arranque)

            # Recorrer en orden topológico
            for id_t in tuberias_ordenadas:
                t = self.tuberias_dict[id_t]

                # Saltar tuberías de arranque
                if t['cab_ata'] == 'Arranque':
                    continue

                if t['diseno'] is None or t['Zs_i'] is None:
                    continue

                ci = t['ci']
                if ci is None:
                    continue

                # Obtener Zs de la cámara (actualizada)
                zs_camara = self.obtener_zs_camara(ci)

                if zs_camara is None:
                    continue

                # Verificar si Zs_i > Zs_camara
                if t['Zs_i'] > zs_camara + 0.001:
                    if self.debug:
                        print(f"\n⚠️ Tubería {id_t}: Zs_i={t['Zs_i']:.3f} > "
                              f"Zs_camara={zs_camara:.3f}")
                        print(f"   Rediseñando desde esta tubería...")

                    # ===== REDISEÑAR ESTA TUBERÍA Y PROPAGAR =====
                    self.redisenar_y_propagar(id_t, zs_camara)
                    cambios_realizados = True

                    # ===== RECALCULAR PARÁMETROS HIDRÁULICOS DESPUÉS DEL REDISEÑO =====
                    self.recalcular_parametros_tuberias_modificadas()

                    # ===== ACTUALIZAR Zs DE CÁMARAS DESPUÉS DEL REDISEÑO =====
                    self.asignar_cota_minima_a_camaras()

        if self.debug:
            print(f"\n✅ Corrección completada en {iteracion} iteraciones")

        # ================================================================
        # ===== RECALCULAR PARÁMETROS HIDRÁULICOS FINALES =====
        # ================================================================
        self.progress.setValue(92)
        self.recalcular_parametros_tuberias_modificadas()

        self.progress.setValue(97)
        self.actualizar_campos_tuberias()

        # ================================================================
        # ===== ACTUALIZAR Zs EN CÁMARAS FINAL =====
        # ================================================================
        self.asignar_cota_minima_a_camaras()

        self.progress.setValue(100)

        if self.debug:
            print("\nDISEÑO COMPLETADO")
            print("=" * 60)

        dialog.accept()

        total = sum(1 for d in self.tuberias_dict.values()
                    if d.get('diseno') is not None)

        QMessageBox.information(
            self.iface.mainWindow(),
            'Diseño Completado',
            f'✅ Diseño completado\n\n'
            f'📊 Tuberías diseñadas: {total} de {len(self.tuberias_dict)}'
        )

    def recalcular_parametros_tuberias_modificadas(self):
        """
        Recalcula los parámetros hidráulicos de todas las tuberías.
        """
        for id_t, t in self.tuberias_dict.items():
            if t['diseno'] is None or t['Zs_i'] is None:
                continue

            d = t['diseno']
            D_m = d['D_mm'] / 1000
            L = t['l']

            # Calcular pendiente real
            S_real = (t['Zs_i'] - t['Zs_f']) / L if L > 0 else 0
            S_real_porc = S_real * 100
            S_real_porc = self.redondear_pendiente(S_real_porc)
            d['S_diseno'] = S_real_porc

            Qd_lps = d['Q_real']
            Qd_m3s = Qd_lps / 1000

            Q_lleno = self.calcular_Q_lleno(D_m, S_real_porc, self.n_manning) * 1000
            V_lleno = self.calcular_V_lleno(D_m, S_real_porc, self.n_manning)
            Rh_lleno = self.calcular_Rh_lleno(D_m)

            if Q_lleno > 0 and Qd_m3s > 0:
                q_rel = Qd_m3s / (Q_lleno / 1000)
                if q_rel > 1.0:
                    q_rel = 1.0

                theta = self.resolver_angulo(q_rel)
                hD, V_rel, Q_rel, Rh_rel = self.calcular_parametros_parcial(theta)
                Rh_parcial = Rh_rel * Rh_lleno
                tractiva = self.calcular_tractiva(Rh_parcial, S_real_porc)
                V_real = V_rel * V_lleno
            else:
                theta = 180
                hD = 0.5
                V_rel = 0
                Rh_parcial = Rh_lleno * 0.5
                tractiva = self.calcular_tractiva(Rh_parcial, S_real_porc)
                V_real = 0
                q_rel = 0

            d['theta'] = theta
            d['hD'] = hD
            d['V_rel'] = V_rel
            d['Rh_parcial'] = Rh_parcial
            d['tractiva'] = tractiva
            d['V_real'] = V_real
            d['q_rel'] = q_rel
            d['Q_lleno'] = Q_lleno
            d['V_lleno'] = V_lleno

    def disenar_red_topologicamente(self, tuberias_arranque):
        """
        Diseña toda la red siguiendo el orden topológico.
        """

        # Orden topológico de las tuberías
        tuberias_ordenadas = self.ordenar_tuberias(tuberias_arranque)

        # Diccionarios para almacenar información de cámaras
        diametros_camaras = {}
        cotas_salida_camaras = {}

        # Inicializar diccionarios
        for id_camara in self.camaras_dict.keys():
            cotas_salida_camaras[id_camara] = None

        total_tuberias = len(tuberias_ordenadas)

        for idx, id_t in enumerate(tuberias_ordenadas):
            t = self.tuberias_dict[id_t]

            if self.debug:
                print(f"\n📍 Procesando tubería {id_t}")
                print(f"   Ci={t['ci']}, Cf={t['cf']}")
                print(f"   Qd={t['qdise_lps']:.3f} L/s")

            # ===== DETERMINAR DIÁMETRO MÍNIMO =====
            if t['cab_ata'] == 'Arranque':
                d_min = self.diametro_min
                if self.debug:
                    print(f"   Arranque: diámetro mínimo = {d_min} mm")
            else:
                d_min = self.diametro_min
                if t['ci'] in diametros_camaras:
                    d_min = max(d_min, diametros_camaras[t['ci']])
                    if self.debug:
                        print(f"   Diámetro máximo en cámara {t['ci']}: {d_min} mm")

            # ===== DISEÑAR LA TUBERÍA =====
            resultado = self.disenar_tuberia(t, d_min)
            if resultado is None:
                if self.debug:
                    print(f"   ❌ Error en diseño de {id_t}")
                continue

            t['diseno'] = resultado
            D_mm = resultado['D_mm']
            D_m = D_mm / 1000
            L = t['l']
            S_porc = resultado['S_diseno']
            S_dec = S_porc / 100

            # ===== CALCULAR COTA SOLERA INICIAL (Zs_i) =====
            es_arranque = (t['cab_ata'] == 'Arranque')

            if es_arranque:
                Zs_i = t['zi'] - self.profundidad_min - D_m
                if self.debug:
                    print(f"   Arranque: Zs_i={Zs_i:.3f}")
            else:
                if t['ci'] in cotas_salida_camaras and \
                   cotas_salida_camaras[t['ci']] is not None:
                    Zs_i = cotas_salida_camaras[t['ci']]
                    if self.debug:
                        print(f"   Cámara {t['ci']} (salida): Zs_i={Zs_i:.3f}")
                else:
                    Zs_i = t['zi'] - self.profundidad_min - D_m
                    if self.debug:
                        print(f"   Sin cota en cámara {t['ci']}, "
                              f"usando prof mínima: Zs_i={Zs_i:.3f}")

            # Verificar profundidad en el inicio
            Hclave_i = t['zi'] - Zs_i - D_m
            if Hclave_i < self.profundidad_min:
                Zs_i = t['zi'] - self.profundidad_min - D_m
                if self.debug:
                    print(f"   Ajustando Zs_i por prof mínima: {Zs_i:.3f}")

            # ===== CALCULAR COTA SOLERA FINAL (Zs_f) =====
            Zs_f = Zs_i - (S_dec * L)

            # Verificar profundidad en el final
            Hclave_f = t['zf'] - Zs_f - D_m
            if Hclave_f < self.profundidad_min:
                Zs_f = t['zf'] - self.profundidad_min - D_m
                if self.debug:
                    print(f"   Ajustando Zs_f por prof mínima: {Zs_f:.3f}")

            # Guardar cotas en la tubería
            t['Zs_i'] = Zs_i
            t['Zs_f'] = Zs_f

            # ===== ACTUALIZAR DIÁMETRO EN CÁMARA DESTINO =====
            cf = t['cf']
            if cf in diametros_camaras:
                diametros_camaras[cf] = max(diametros_camaras[cf], D_mm)
            else:
                diametros_camaras[cf] = D_mm

            # ===== ACTUALIZAR COTA DE SALIDA EN LA CÁMARA DESTINO =====
            if cf in cotas_salida_camaras:
                if cotas_salida_camaras[cf] is None or \
                   Zs_f < cotas_salida_camaras[cf]:
                    cotas_salida_camaras[cf] = Zs_f
                    if self.debug:
                        print(f"   Cámara {cf} (salida mínima): Zs_i={Zs_f:.3f}")

            if self.debug:
                print(f"   ✅ D={D_mm}mm, S={S_porc:.2f}%")
                print(f"      Zs_i={Zs_i:.3f}, Zs_f={Zs_f:.3f}")
                print(f"      Hclave_i={Hclave_i:.3f}, Hclave_f={Hclave_f:.3f}")

            progreso = 20 + ((idx + 1) / total_tuberias) * 70
            self.progress.setValue(int(progreso))

        # Recalcular parámetros hidráulicos después del diseño inicial
        self.recalcular_parametros_tuberias_modificadas()

    def obtener_diametro_minimo_para_tuberia(self, t):
        """
        Obtiene el diámetro mínimo para una tubería.
        Si es arranque, usa el diámetro mínimo general.
        Si no, busca el máximo de las tuberías que llegan a su cámara de inicio.
        """
        if t['cab_ata'] == 'Arranque':
            return self.diametro_min
        else:
            d_min = self.diametro_min
            ci = t['ci']
            for id_t2, t2 in self.tuberias_dict.items():
                if t2['cf'] == ci and t2['diseno'] is not None:
                    d_min = max(d_min, t2['diseno']['D_mm'])
            return d_min

    def redisenar_y_propagar(self, id_t_inicio, nueva_Zs_i):
        """
        Rediseña una tubería y propaga los cambios hacia las tuberías aguas abajo.
        """

        # ===== REDISEÑAR LA TUBERÍA DE INICIO =====
        t = self.tuberias_dict[id_t_inicio]

        # Obtener diámetro mínimo para esta tubería
        d_min = self.obtener_diametro_minimo_para_tuberia(t)

        if self.debug:
            print(f"   Diámetro mínimo para {id_t_inicio}: {d_min} mm")
            print(f"   Nueva Zs_i = {nueva_Zs_i:.3f}")

        # Buscar diseño que cumpla condiciones
        resultado = self.buscar_diseno_cumpliendo_condiciones(t, d_min)
        if resultado is None:
            if self.debug:
                print(f"   ❌ No se encontró diseño para {id_t_inicio}")
            return

        t['diseno'] = resultado
        D_mm = resultado['D_mm']
        D_m = D_mm / 1000
        L = t['l']
        S_porc = resultado['S_diseno']
        S_dec = S_porc / 100

        # Asignar nueva Zs_i
        Zs_i = nueva_Zs_i

        # Verificar profundidad en el inicio
        Hclave_i = t['zi'] - Zs_i - D_m
        if Hclave_i < self.profundidad_min:
            Zs_i = t['zi'] - self.profundidad_min - D_m
            if self.debug:
                print(f"   Ajustando Zs_i por prof mínima: {Zs_i:.3f}")

        # Calcular Zs_f
        Zs_f = Zs_i - (S_dec * L)

        # Verificar profundidad en el final
        Hclave_f = t['zf'] - Zs_f - D_m
        if Hclave_f < self.profundidad_min:
            Zs_f = t['zf'] - self.profundidad_min - D_m
            if self.debug:
                print(f"   Ajustando Zs_f por prof mínima: {Zs_f:.3f}")

        t['Zs_i'] = Zs_i
        t['Zs_f'] = Zs_f

        if self.debug:
            print(f"   ✅ Tubería {id_t_inicio} rediseñada:")
            print(f"      D={D_mm}mm, S={S_porc:.2f}%")
            print(f"      Zs_i={Zs_i:.3f}, Zs_f={Zs_f:.3f}")

        # ===== ACTUALIZAR Zs DE LA CÁMARA DESTINO =====
        cf = t['cf']
        zs_camara_destino = self.obtener_zs_camara(cf)

        if zs_camara_destino is not None:
            if Zs_f < zs_camara_destino:
                if self.debug:
                    print(f"   → Nueva Zs_f={Zs_f:.3f} < "
                          f"Zs_camara_destino={zs_camara_destino:.3f}")
                    print(f"   → Actualizando cámara {cf}")
                self.actualizar_zs_camara(cf, Zs_f)
            else:
                if self.debug:
                    print(f"   → Nueva Zs_f={Zs_f:.3f} >= "
                          f"Zs_camara_destino={zs_camara_destino:.3f}")
                    print(f"   → No se actualiza, fin del trayecto")
                return

        # ===== PROPAGAR HACIA AGUAS ABAJO =====
        self.propagar_hacia_abajo(cf)

    def propagar_hacia_abajo(self, id_camara):
        """
        Propaga las cotas hacia las tuberías que salen de una cámara.
        """
        # Buscar tuberías que salen de esta cámara
        for id_t, t in self.tuberias_dict.items():
            if t['ci'] == id_camara and t['cab_ata'] != 'Arranque' and \
               t['diseno'] is not None:
                if self.debug:
                    print(f"\n   📍 Propagando a tubería {id_t}")

                # Obtener Zs actualizada de la cámara
                zs_camara = self.obtener_zs_camara(id_camara)
                if zs_camara is None:
                    continue

                # Obtener diámetro mínimo para esta tubería
                d_min = self.obtener_diametro_minimo_para_tuberia(t)

                # Verificar si la tubería necesita re-diseño
                if t['Zs_i'] > zs_camara + 0.001:
                    # Rediseñar esta tubería con la nueva cota
                    self.redisenar_y_propagar(id_t, zs_camara)
                else:
                    # Si no necesita re-diseño, solo propagar la cota
                    t['Zs_i'] = zs_camara
                    D_m = t['diseno']['D_mm'] / 1000
                    L = t['l']
                    S_dec = t['diseno']['S_diseno'] / 100

                    # Recalcular Zs_f
                    Zs_f = t['Zs_i'] - (S_dec * L)

                    # Verificar profundidad en el final
                    Hclave_f = t['zf'] - Zs_f - D_m
                    if Hclave_f < self.profundidad_min:
                        Zs_f = t['zf'] - self.profundidad_min - D_m

                    t['Zs_f'] = Zs_f

                    if self.debug:
                        print(f"      → Actualizando Zs_i={t['Zs_i']:.3f}, "
                              f"Zs_f={t['Zs_f']:.3f}")

                    # Actualizar cámara destino
                    cf = t['cf']
                    zs_camara_destino = self.obtener_zs_camara(cf)
                    if zs_camara_destino is not None and Zs_f < zs_camara_destino:
                        self.actualizar_zs_camara(cf, Zs_f)
                        # Propagar recursivamente
                        self.propagar_hacia_abajo(cf)

    def buscar_diseno_cumpliendo_condiciones(self, t, d_min):
        """
        Busca un diseño que cumpla con tractiva mínima y h/D máximo.
        Usa la tabla de pendientes mínimas por diámetro.
        Si Q_lleno <= Qd, automáticamente prueba el siguiente diámetro.
        """
        Qd_m3s = t['qdise']
        Qd_lps = Qd_m3s * 1000

        if Qd_m3s <= 0:
            D_mm = self.obtener_diametro_disponible(max(d_min, self.diametro_min))
            S_min = self.pendientes_minimas.get(D_mm, 0.50)
            return {
                'D_mm': D_mm, 'S_diseno': S_min, 'theta': 0, 'hD': 0,
                'V_lleno': 0.5, 'V_real': 0, 'Q_lleno': 0, 'Q_real': Qd_lps,
                'Rh_lleno': D_mm / 4000, 'Rh_parcial': 0, 'tractiva': 0,
                'q_rel': 0, 'V_rel': 0
            }

        # Probar diámetros desde el mínimo requerido
        for D_mm in sorted(self.diametros_disponibles):
            if D_mm < d_min:
                continue

            if self.debug:
                print(f"   🔧 Probando diámetro: {D_mm} mm")

            D_m = D_mm / 1000

            # Obtener pendiente mínima de la tabla
            S_porc = self.pendientes_minimas.get(D_mm, 0.50)

            if self.debug:
                print(f"      S_tabla: {S_porc:.3f}%")

            # Verificar capacidad
            Q_lleno = self.calcular_Q_lleno(D_m, S_porc, self.n_manning)

            # Si Q_lleno <= Qd, el diámetro es insuficiente, probar el siguiente
            if Q_lleno <= Qd_m3s:
                if self.debug:
                    print(f"      ⚠️ Q_lleno ({Q_lleno:.4f}) <= Qd ({Qd_m3s:.4f}) - "
                          f"probando siguiente diámetro")
                continue

            q_rel = Qd_m3s / Q_lleno
            theta = self.resolver_angulo(q_rel)
            hD, V_rel, Q_rel, Rh_rel = self.calcular_parametros_parcial(theta)

            Rh_lleno = self.calcular_Rh_lleno(D_m)
            Rh_parcial = Rh_rel * Rh_lleno
            tractiva = self.calcular_tractiva(Rh_parcial, S_porc)

            # Si no cumple tractiva, aumentar pendiente
            S_actual = S_porc
            iteraciones = 0
            while tractiva < self.tractiva_min - 0.001 and \
                  iteraciones < self.max_iteraciones:
                S_actual = S_actual + 0.01
                Q_lleno = self.calcular_Q_lleno(D_m, S_actual, self.n_manning)
                if Q_lleno <= Qd_m3s:
                    # Si al aumentar pendiente el caudal a tubo lleno es insuficiente,
                    # salir del bucle y probar el siguiente diámetro
                    break
                q_rel = Qd_m3s / Q_lleno
                theta = self.resolver_angulo(q_rel)
                hD, V_rel, Q_rel, Rh_rel = self.calcular_parametros_parcial(theta)
                Rh_parcial = Rh_rel * Rh_lleno
                tractiva = self.calcular_tractiva(Rh_parcial, S_actual)
                iteraciones += 1

            # Si salió del bucle porque Q_lleno <= Qd_m3s, probar el siguiente diámetro
            if Q_lleno <= Qd_m3s and iteraciones > 0:
                if self.debug:
                    print(f"      ⚠️ Q_lleno ({Q_lleno:.4f}) <= Qd ({Qd_m3s:.4f}) - "
                          f"probando siguiente diámetro")
                continue

            if self.debug:
                print(f"      Tractiva: {tractiva:.3f} Pa "
                      f"(mín: {self.tractiva_min} Pa)")
                print(f"      S final: {S_actual:.3f}%")
                print(f"      h/D: {hD:.3f} (máx: {self.hD_max})")

            if tractiva >= self.tractiva_min and hD <= self.hD_max:
                S_final = self.redondear_pendiente(S_actual)
                Q_lleno_f = self.calcular_Q_lleno(D_m, S_final, self.n_manning)
                q_rel_f = Qd_m3s / Q_lleno_f if Q_lleno_f > 0 else 0
                theta_f = self.resolver_angulo(q_rel_f)
                hD_f, V_rel_f, Q_rel_f, Rh_rel_f = \
                    self.calcular_parametros_parcial(theta_f)
                Rh_parcial_f = Rh_rel_f * Rh_lleno
                tractiva_f = self.calcular_tractiva(Rh_parcial_f, S_final)
                V_lleno_f = self.calcular_V_lleno(D_m, S_final, self.n_manning)
                V_real_f = V_rel_f * V_lleno_f

                if self.debug:
                    print(f"   ✅ Diámetro {D_mm} mm seleccionado, "
                          f"S={S_final:.3f}%")

                return {
                    'D_mm': D_mm, 'S_diseno': S_final, 'theta': theta_f,
                    'hD': hD_f, 'V_lleno': V_lleno_f, 'V_real': V_real_f,
                    'Q_lleno': Q_lleno_f * 1000, 'Q_real': Qd_lps,
                    'Rh_lleno': Rh_lleno, 'Rh_parcial': Rh_parcial_f,
                    'tractiva': tractiva_f, 'q_rel': q_rel_f, 'V_rel': V_rel_f
                }
            else:
                if self.debug:
                    if tractiva < self.tractiva_min:
                        print(f"      ⚠️ Tractiva {tractiva:.3f} < "
                              f"{self.tractiva_min}")
                    if hD > self.hD_max:
                        print(f"      ⚠️ h/D={hD:.3f} > {self.hD_max}")
                    print(f"      → Probando siguiente diámetro")
                continue

        # Si ningún diámetro cumple, usar el máximo disponible
        D_mm = max(self.diametros_disponibles)
        S_min = self.pendientes_minimas.get(D_mm, 0.50)

        if self.debug:
            print(f"   ⚠️ Ningún diámetro cumple, usando máximo: {D_mm} mm")

        D_m = D_mm / 1000
        S_min = self.redondear_pendiente(S_min)

        return {
            'D_mm': D_mm, 'S_diseno': S_min, 'theta': 180, 'hD': 0.5,
            'V_lleno': self.calcular_V_lleno(D_m, S_min, self.n_manning),
            'V_real': 0,
            'Q_lleno': self.calcular_Q_lleno(D_m, S_min, self.n_manning) * 1000,
            'Q_real': Qd_lps, 'Rh_lleno': D_m / 4, 'Rh_parcial': D_m / 4 * 0.5,
            'tractiva': self.calcular_tractiva(D_m / 4 * 0.5, S_min),
            'q_rel': 0, 'V_rel': 0
        }

    def actualizar_zs_camara(self, id_camara, nuevo_zs):
        """
        Actualiza el valor Zs de una cámara en el shapefile.
        """
        idx_zs = self.capa_camaras.fields().indexFromName('Zs')
        if idx_zs == -1:
            return

        self.capa_camaras.startEditing()

        for f in self.capa_camaras.getFeatures():
            id_o = f.attribute('ID_O')
            if id_o == id_camara:
                try:
                    self.capa_camaras.changeAttributeValue(
                        f.id(), idx_zs, round(nuevo_zs, 3)
                    )
                    if self.debug:
                        print(f"      ✅ Cámara {id_camara}: "
                              f"Zs actualizada a {nuevo_zs:.3f}")
                except Exception as e:
                    if self.debug:
                        print(f"      ❌ Error actualizando cámara {id_camara}: {e}")
                break

        self.capa_camaras.commitChanges()

    def crear_campo_zs1(self):
        provider = self.capa_camaras.dataProvider()
        if 'Zs1' not in [f.name() for f in provider.fields()]:
            provider.addAttributes([_campo('Zs1', 'double')])
            self.capa_camaras.updateFields()

    def guardar_zs1_en_camaras(self, cotas):
        idx = self.capa_camaras.fields().indexFromName('Zs1')
        if idx == -1:
            return
        self.capa_camaras.startEditing()
        for f in self.capa_camaras.getFeatures():
            id_o = f.attribute('ID_O')
            if id_o in cotas and cotas[id_o] is not None:
                self.capa_camaras.changeAttributeValue(
                    f.id(), idx, round(float(cotas[id_o]), 3)
                )
        self.capa_camaras.commitChanges()

    def asignar_cota_minima_a_camaras(self):
        """
        Crea el campo Zs en la capa de cámaras y asigna la cota solera MÍNIMA
        de todas las tuberías conectadas a cada cámara (tanto como inicio como final)
        """

        # ===== CREAR EL CAMPO Zs EN CÁMARAS SI NO EXISTE =====
        provider = self.capa_camaras.dataProvider()
        campos_existentes = [field.name() for field in provider.fields()]

        if 'Zs' not in campos_existentes:
            provider.addAttributes([_campo('Zs', 'double')])
            self.capa_camaras.updateFields()
            if self.debug:
                print("✅ Campo 'Zs' creado en la capa de cámaras")

        # ===== RECOPILAR TODAS LAS COTAS SOLERAS DE CADA CÁMARA =====
        cotas_por_camara = {}

        # Inicializar diccionario con todas las cámaras
        for id_camara in self.camaras_dict.keys():
            cotas_por_camara[id_camara] = []

        # Recorrer todas las tuberías
        for id_t, t in self.tuberias_dict.items():
            if t['diseno'] is None:
                continue

            ci = t['ci']
            cf = t['cf']
            Zs_i = t['Zs_i']
            Zs_f = t['Zs_f']

            # Si la cámara es INICIO, agregar Zs_i
            if ci is not None and Zs_i is not None:
                if ci in cotas_por_camara:
                    cotas_por_camara[ci].append(Zs_i)

            # Si la cámara es FINAL, agregar Zs_f
            if cf is not None and Zs_f is not None:
                if cf in cotas_por_camara:
                    cotas_por_camara[cf].append(Zs_f)

        # ===== CALCULAR LA COTA MÍNIMA PARA CADA CÁMARA =====
        zs_minima_por_camara = {}

        for id_camara, lista_cotas in cotas_por_camara.items():
            if lista_cotas:
                zs_min = min(lista_cotas)
                zs_minima_por_camara[id_camara] = zs_min
                if self.debug:
                    print(f"   🏷️ Cámara {id_camara}: Zs mínima = {zs_min:.3f}")
            else:
                zs_minima_por_camara[id_camara] = None

        # ===== ASIGNAR LA COTA MÍNIMA A CADA CÁMARA =====
        idx_zs = self.capa_camaras.fields().indexFromName('Zs')
        if idx_zs == -1:
            if self.debug:
                print("❌ No se encontró el campo 'Zs' en cámaras")
            return

        self.capa_camaras.startEditing()

        for f in self.capa_camaras.getFeatures():
            id_o = f.attribute('ID_O')
            if id_o in zs_minima_por_camara and \
               zs_minima_por_camara[id_o] is not None:
                try:
                    self.capa_camaras.changeAttributeValue(
                        f.id(),
                        idx_zs,
                        round(zs_minima_por_camara[id_o], 3)
                    )
                except Exception as e:
                    if self.debug:
                        print(f"   ❌ Error en cámara {id_o}: {e}")

        self.capa_camaras.commitChanges()

        if self.debug:
            print(f"\n✅ Campo 'Zs' actualizado en cámaras con la cota solera mínima")

    def obtener_zs_camara(self, id_camara):
        """
        Obtiene el valor Zs de una cámara desde el shapefile de cámaras.
        """
        idx_zs = self.capa_camaras.fields().indexFromName('Zs')
        if idx_zs == -1:
            return None

        for f in self.capa_camaras.getFeatures():
            id_o = f.attribute('ID_O')
            if id_o == id_camara:
                zs = f.attribute(idx_zs)
                if zs is not None:
                    return float(zs)
                return None

        return None

    def ordenar_tuberias(self, arranques):
        """Ordena las tuberías por orden topológico (BFS)"""
        niveles = {id_t: 0 for id_t in arranques}
        cambios = True
        it = 0

        while cambios and it < 100:
            cambios = False
            it += 1
            for id_t, t in self.tuberias_dict.items():
                ci = t['ci']
                if ci is not None:
                    nmax = -1
                    for id_t2, t2 in self.tuberias_dict.items():
                        if t2['cf'] == ci and id_t2 in niveles:
                            nmax = max(nmax, niveles[id_t2])
                    nv = nmax + 1
                    if id_t not in niveles or niveles[id_t] < nv:
                        niveles[id_t] = nv
                        cambios = True

        por_nivel = {}
        for id_t, n in niveles.items():
            por_nivel.setdefault(n, []).append(id_t)

        orden = []
        for n in sorted(por_nivel.keys()):
            orden.extend(por_nivel[n])
        for id_t in self.tuberias_dict.keys():
            if id_t not in orden:
                orden.append(id_t)
        return orden

    def construir_diccionarios(self):
        """Construye diccionarios para acceso rápido"""
        self.tuberias_dict = {}
        for f in self.capa_tuberias.getFeatures():
            id_o = f.attribute('ID_O')
            if id_o is None:
                continue

            geom = f.geometry()
            if geom:
                try:
                    if geom.isMultipart():
                        line = geom.asMultiPolyline()[0]
                    else:
                        line = geom.asPolyline()
                    if len(line) >= 2:
                        zi = line[0].z() if hasattr(line[0], 'z') and \
                             line[0].z() is not None else f.attribute('Zi') or 0
                        zf = line[-1].z() if hasattr(line[-1], 'z') and \
                             line[-1].z() is not None else f.attribute('Zf') or 0
                    else:
                        zi = f.attribute('Zi') or 0
                        zf = f.attribute('Zf') or 0
                except Exception:
                    zi = f.attribute('Zi') or 0
                    zf = f.attribute('Zf') or 0
            else:
                zi = f.attribute('Zi') or 0
                zf = f.attribute('Zf') or 0

            qdise_lps = f.attribute('qdise') or 0.0
            cab = f.attribute('cab_ata') or ''
            if cab.lower() in ['comienzo', 'arranque']:
                cab = 'Arranque'

            self.tuberias_dict[id_o] = {
                'id_o': id_o,
                'ci': f.attribute('Ci'),
                'cf': f.attribute('Cf'),
                'l': f.attribute('L') or 0.0,
                'cab_ata': cab,
                'zi': float(zi),
                'zf': float(zf),
                'qdise_lps': qdise_lps,
                'qdise': qdise_lps / 1000.0,
                'feature': f,
                'diseno': None,
                'Zs_i': None,
                'Zs_f': None
            }

        self.camaras_dict = {}
        for f in self.capa_camaras.getFeatures():
            id_o = f.attribute('ID_O')
            if id_o is None:
                continue
            geom = f.geometry()
            z = 0
            if geom:
                try:
                    if geom.isMultipart():
                        p = geom.asMultiPoint()[0]
                    else:
                        p = geom.asPoint()
                    z = p.z() if hasattr(p, 'z') and p.z() is not None \
                        else f.attribute('Z') or 0
                except Exception:
                    z = f.attribute('Z') or 0
            self.camaras_dict[id_o] = {'id_o': id_o, 'z': float(z), 'feature': f}

    # ===== FUNCIONES HIDRÁULICAS =====
    def resolver_angulo(self, q_rel):
        if q_rel <= 0:
            return 0
        if q_rel >= 1:
            return 360
        theta_min, theta_max = 0.1, 359.9
        for _ in range(1000):
            tm = (theta_min + theta_max) / 2
            tr = math.radians(tm)
            try:
                Q = (tm / 360 - math.sin(tr) / (2 * math.pi)) * \
                    (1 - (360 * math.sin(tr)) / (2 * math.pi * tm)) ** (2 / 3)
            except Exception:
                Q = 0
            if abs(Q - q_rel) < 0.0001:
                return tm
            if Q < q_rel:
                theta_min = tm
            else:
                theta_max = tm
        return (theta_min + theta_max) / 2

    def calcular_parametros_parcial(self, theta):
        if theta <= 0:
            return 0, 0, 0, 0
        if theta >= 360:
            return 1, 1, 1, 1
        tr = math.radians(theta)
        hD = 0.5 * (1 - math.cos(tr / 2))
        try:
            V_rel = (1 - (360 * math.sin(tr)) / (2 * math.pi * theta)) ** (2 / 3)
        except Exception:
            V_rel = 0
        Q_rel = (theta / 360 - math.sin(tr) / (2 * math.pi)) * V_rel
        try:
            Rh_rel = 1 - (360 * math.sin(tr)) / (2 * math.pi * theta)
        except Exception:
            Rh_rel = 0
        return hD, V_rel, Q_rel, Rh_rel

    def calcular_Rh_lleno(self, D_m):
        return D_m / 4

    def calcular_V_lleno(self, D_m, S_porc, n):
        return (1 / n) * (D_m / 4) ** (2 / 3) * (S_porc / 100) ** 0.5

    def calcular_Q_lleno(self, D_m, S_porc, n):
        A = math.pi * (D_m ** 2) / 4
        return A * self.calcular_V_lleno(D_m, S_porc, n)

    def calcular_tractiva(self, Rh_m, S_porc):
        return self.gamma_agua * Rh_m * (S_porc / 100)

    def obtener_diametro_disponible(self, D_mm):
        if not self.diametros_disponibles:
            return D_mm
        for d in sorted(self.diametros_disponibles):
            if d >= D_mm:
                return d
        return max(self.diametros_disponibles)

    def obtener_diametro_superior(self, D_mm):
        if not self.diametros_disponibles:
            return D_mm + 50
        for d in sorted(self.diametros_disponibles):
            if d > D_mm + 0.001:
                return d
        return D_mm

    def redondear_pendiente(self, S_porc):
        if S_porc <= 0:
            return 0.01
        return math.ceil(S_porc * 100) / 100

    def disenar_tuberia(self, t, d_min):
        """
        Diseña una tubería usando la tabla de pendientes mínimas por diámetro.
        Prueba diámetros desde el mínimo requerido hacia arriba.
        Si Q_lleno <= Qd, automáticamente prueba el siguiente diámetro.
        """
        Qd_m3s = t['qdise']
        Qd_lps = Qd_m3s * 1000

        if Qd_m3s <= 0:
            D_mm = self.obtener_diametro_disponible(max(d_min, self.diametro_min))
            S_min = self.pendientes_minimas.get(D_mm, 0.50)
            return {
                'D_mm': D_mm, 'S_diseno': S_min, 'theta': 0, 'hD': 0,
                'V_lleno': 0.5, 'V_real': 0, 'Q_lleno': 0, 'Q_real': Qd_lps,
                'Rh_lleno': D_mm / 4000, 'Rh_parcial': 0, 'tractiva': 0,
                'q_rel': 0, 'V_rel': 0
            }

        # Probar diámetros desde el mínimo requerido
        for D_mm in sorted(self.diametros_disponibles):
            if D_mm < d_min:
                continue

            if self.debug:
                print(f"   🔧 Probando diámetro: {D_mm} mm")

            D_m = D_mm / 1000

            # Obtener pendiente mínima de la tabla
            S_porc = self.pendientes_minimas.get(D_mm, 0.50)

            if self.debug:
                print(f"      S_tabla: {S_porc:.3f}%")

            # Verificar capacidad
            Q_lleno = self.calcular_Q_lleno(D_m, S_porc, self.n_manning)

            # Si Q_lleno <= Qd, el diámetro es insuficiente, probar el siguiente
            if Q_lleno <= Qd_m3s:
                if self.debug:
                    print(f"      ⚠️ Q_lleno ({Q_lleno:.4f}) <= Qd ({Qd_m3s:.4f}) - "
                          f"probando siguiente diámetro")
                continue

            q_rel = Qd_m3s / Q_lleno
            theta = self.resolver_angulo(q_rel)
            hD, V_rel, Q_rel, Rh_rel = self.calcular_parametros_parcial(theta)

            Rh_lleno = self.calcular_Rh_lleno(D_m)
            Rh_parcial = Rh_rel * Rh_lleno
            tractiva = self.calcular_tractiva(Rh_parcial, S_porc)

            # Si no cumple tractiva, aumentar pendiente
            S_actual = S_porc
            iteraciones = 0
            while tractiva < self.tractiva_min - 0.001 and \
                  iteraciones < self.max_iteraciones:
                S_actual = S_actual + 0.01
                Q_lleno = self.calcular_Q_lleno(D_m, S_actual, self.n_manning)
                if Q_lleno <= Qd_m3s:
                    # Si al aumentar pendiente el caudal a tubo lleno es insuficiente,
                    # salir del bucle y probar el siguiente diámetro
                    if self.debug:
                        print(f"      ⚠️ Q_lleno ({Q_lleno:.4f}) <= "
                              f"Qd ({Qd_m3s:.4f}) - probando siguiente diámetro")
                    break
                q_rel = Qd_m3s / Q_lleno
                theta = self.resolver_angulo(q_rel)
                hD, V_rel, Q_rel, Rh_rel = self.calcular_parametros_parcial(theta)
                Rh_parcial = Rh_rel * Rh_lleno
                tractiva = self.calcular_tractiva(Rh_parcial, S_actual)
                iteraciones += 1

            # Si salió del bucle porque Q_lleno <= Qd_m3s, probar el siguiente diámetro
            if Q_lleno <= Qd_m3s and iteraciones > 0:
                continue

            if self.debug:
                print(f"      Tractiva: {tractiva:.3f} Pa "
                      f"(mín: {self.tractiva_min} Pa)")
                print(f"      S final: {S_actual:.3f}%")
                print(f"      h/D: {hD:.3f} (máx: {self.hD_max})")

            if tractiva >= self.tractiva_min and hD <= self.hD_max:
                S_final = self.redondear_pendiente(S_actual)
                Q_lleno_f = self.calcular_Q_lleno(D_m, S_final, self.n_manning)
                q_rel_f = Qd_m3s / Q_lleno_f if Q_lleno_f > 0 else 0
                theta_f = self.resolver_angulo(q_rel_f)
                hD_f, V_rel_f, Q_rel_f, Rh_rel_f = \
                    self.calcular_parametros_parcial(theta_f)
                Rh_parcial_f = Rh_rel_f * Rh_lleno
                tractiva_f = self.calcular_tractiva(Rh_parcial_f, S_final)
                V_lleno_f = self.calcular_V_lleno(D_m, S_final, self.n_manning)
                V_real_f = V_rel_f * V_lleno_f

                if self.debug:
                    print(f"   ✅ Diámetro {D_mm} mm seleccionado, "
                          f"S={S_final:.3f}%")

                return {
                    'D_mm': D_mm, 'S_diseno': S_final, 'theta': theta_f,
                    'hD': hD_f, 'V_lleno': V_lleno_f, 'V_real': V_real_f,
                    'Q_lleno': Q_lleno_f * 1000, 'Q_real': Qd_lps,
                    'Rh_lleno': Rh_lleno, 'Rh_parcial': Rh_parcial_f,
                    'tractiva': tractiva_f, 'q_rel': q_rel_f, 'V_rel': V_rel_f
                }
            else:
                if self.debug:
                    if tractiva < self.tractiva_min:
                        print(f"      ⚠️ Tractiva {tractiva:.3f} < "
                              f"{self.tractiva_min}")
                    if hD > self.hD_max:
                        print(f"      ⚠️ h/D={hD:.3f} > {self.hD_max}")
                    print(f"      → Probando siguiente diámetro")
                continue

        # Si ningún diámetro cumple, usar el máximo disponible
        D_mm = max(self.diametros_disponibles)
        S_min = self.pendientes_minimas.get(D_mm, 0.50)

        if self.debug:
            print(f"   ⚠️ Ningún diámetro cumple, usando máximo: {D_mm} mm")

        D_m = D_mm / 1000
        S_min = self.redondear_pendiente(S_min)

        return {
            'D_mm': D_mm, 'S_diseno': S_min, 'theta': 180, 'hD': 0.5,
            'V_lleno': self.calcular_V_lleno(D_m, S_min, self.n_manning),
            'V_real': 0,
            'Q_lleno': self.calcular_Q_lleno(D_m, S_min, self.n_manning) * 1000,
            'Q_real': Qd_lps, 'Rh_lleno': D_m / 4, 'Rh_parcial': D_m / 4 * 0.5,
            'tractiva': self.calcular_tractiva(D_m / 4 * 0.5, S_min),
            'q_rel': 0, 'V_rel': 0
        }

    def actualizar_campos_tuberias(self):
        """Actualiza la capa de tuberías con los resultados del diseño"""
        campos = [
            ('D_mm', 'double'), ('S_diseno', 'double'),
            ('Zs_i', 'double'), ('Zs_f', 'double'),
            ('Hexc_i', 'double'), ('Hexc_f', 'double'),
            ('Q_lleno', 'double'), ('V_lleno', 'double'),
            ('Rh_lleno', 'double'), ('q_Q', 'double'),
            ('v_V', 'double'), ('h_D', 'double'),
            ('rh_Rh', 'double'), ('v_real', 'double'),
            ('h_real', 'double'), ('rh_real', 'double'),
            ('angulo', 'double'), ('tractiva', 'double'),
            ('vc', 'double')
        ]

        provider = self.capa_tuberias.dataProvider()
        existentes = [f.name() for f in provider.fields()]
        for n, t in campos:
            if n not in existentes:
                provider.addAttributes([_campo(n, t)])
        self.capa_tuberias.updateFields()

        idx = {n: provider.fields().indexFromName(n) for n, _ in campos}
        self.capa_tuberias.startEditing()

        for id_o, d in self.tuberias_dict.items():
            if d['diseno'] is None:
                continue

            f = d['feature']
            if not f.isValid():
                continue

            dis = d['diseno']
            D_m = dis['D_mm'] / 1000

            hexc_i = d['zi'] - d['Zs_i'] if d['Zs_i'] is not None else 0
            hexc_f = d['zf'] - d['Zs_f'] if d['Zs_f'] is not None else 0

            h_real = dis['hD'] * D_m
            vc = 6 * (self.g * dis['Rh_parcial']) ** 0.5 \
                if dis['Rh_parcial'] > 0 else 0

            try:
                self.capa_tuberias.changeAttributeValue(
                    f.id(), idx['D_mm'], float(dis['D_mm'])
                )
                self.capa_tuberias.changeAttributeValue(
                    f.id(), idx['S_diseno'], round(float(dis['S_diseno']), 3)
                )
                self.capa_tuberias.changeAttributeValue(
                    f.id(), idx['Zs_i'], round(float(d['Zs_i']), 3)
                )
                self.capa_tuberias.changeAttributeValue(
                    f.id(), idx['Zs_f'], round(float(d['Zs_f']), 3)
                )
                self.capa_tuberias.changeAttributeValue(
                    f.id(), idx['Hexc_i'], round(float(hexc_i), 3)
                )
                self.capa_tuberias.changeAttributeValue(
                    f.id(), idx['Hexc_f'], round(float(hexc_f), 3)
                )
                self.capa_tuberias.changeAttributeValue(
                    f.id(), idx['Q_lleno'], round(float(dis['Q_lleno']), 3)
                )
                self.capa_tuberias.changeAttributeValue(
                    f.id(), idx['V_lleno'], round(float(dis['V_lleno']), 3)
                )
                self.capa_tuberias.changeAttributeValue(
                    f.id(), idx['Rh_lleno'], round(float(dis['Rh_lleno']), 3)
                )
                self.capa_tuberias.changeAttributeValue(
                    f.id(), idx['q_Q'], round(float(dis['q_rel']), 4)
                )
                self.capa_tuberias.changeAttributeValue(
                    f.id(), idx['v_V'], round(float(dis['V_rel']), 4)
                )
                self.capa_tuberias.changeAttributeValue(
                    f.id(), idx['h_D'], round(float(dis['hD']), 4)
                )
                rh_rel = dis['Rh_parcial'] / dis['Rh_lleno'] \
                    if dis['Rh_lleno'] > 0 else 0
                self.capa_tuberias.changeAttributeValue(
                    f.id(), idx['rh_Rh'], round(float(rh_rel), 4)
                )
                self.capa_tuberias.changeAttributeValue(
                    f.id(), idx['v_real'], round(float(dis['V_real']), 3)
                )
                self.capa_tuberias.changeAttributeValue(
                    f.id(), idx['h_real'], round(float(h_real), 3)
                )
                self.capa_tuberias.changeAttributeValue(
                    f.id(), idx['rh_real'], round(float(dis['Rh_parcial']), 3)
                )
                self.capa_tuberias.changeAttributeValue(
                    f.id(), idx['angulo'], round(float(dis['theta']), 2)
                )
                self.capa_tuberias.changeAttributeValue(
                    f.id(), idx['tractiva'], round(float(dis['tractiva']), 3)
                )
                self.capa_tuberias.changeAttributeValue(
                    f.id(), idx['vc'], round(float(vc), 3)
                )
            except Exception as e:
                if self.debug:
                    print(f"Error {id_o}: {e}")

        self.capa_tuberias.commitChanges()