# -*- coding: utf-8 -*-
import math
from qgis.core import (
    QgsProject, QgsVectorLayer, QgsFeature,
    QgsGeometry, QgsPointXY, QgsField,
    QgsWkbTypes, QgsLineString
)
from qgis.PyQt.QtCore import Qt, QVariant
from qgis.PyQt.QtWidgets import (
    QMessageBox, QDialog, QVBoxLayout, QLabel,
    QPushButton, QComboBox, QHBoxLayout,
    QDoubleSpinBox, QSpinBox, QGroupBox,
    QProgressBar, QRadioButton, QButtonGroup,
    QTabWidget, QWidget, QLineEdit
)


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


class CalcularCaudales:
    def __init__(self, iface):
        self.iface = iface
        self.capa_tuberias = None

    def mostrar_dialogo(self):
        dialog = QDialog(self.iface.mainWindow())
        dialog.setWindowTitle('GLC - Calcular Caudales')
        dialog.setMinimumWidth(700)
        dialog.setMinimumHeight(600)

        layout = QVBoxLayout()

        label_titulo = QLabel('<b>Calcular Caudales de Diseño</b>')
        label_titulo.setStyleSheet('font-size: 14pt; font-weight: bold;')
        layout.addWidget(label_titulo)

        # ===== TABS =====
        tabs = QTabWidget()

        # ---------- TAB 1: PARAMETROS GENERALES ----------
        tab_general = QWidget()
        layout_gen = QVBoxLayout()

        # Seleccionar capa
        layout_gen.addWidget(QLabel('Seleccionar capa GLC_Tuberias:'))
        combo_tuberias = QComboBox()
        for layer in QgsProject.instance().mapLayers().values():
            if isinstance(layer, QgsVectorLayer):
                if layer.geometryType() == QgsWkbTypes.LineGeometry:
                    if 'GLC_Tuberias' in layer.name():
                        combo_tuberias.addItem(layer.name(), layer.id())
        if combo_tuberias.count() == 0:
            for layer in QgsProject.instance().mapLayers().values():
                if isinstance(layer, QgsVectorLayer):
                    if layer.geometryType() == QgsWkbTypes.LineGeometry:
                        combo_tuberias.addItem(layer.name(), layer.id())
        layout_gen.addWidget(combo_tuberias)

        layout_gen.addWidget(QLabel('-' * 40))

        # Método de cálculo de población
        group_metodo = QGroupBox('Método de cálculo de población')
        metodo_layout = QVBoxLayout()

        self.radio_longitudes = QRadioButton('Por longitudes (L y Lt)')
        self.radio_longitudes.setChecked(True)
        self.radio_areas = QRadioButton('Por áreas (A y At)')
        self.radio_areas.setEnabled(True)

        metodo_layout.addWidget(self.radio_longitudes)
        metodo_layout.addWidget(self.radio_areas)
        group_metodo.setLayout(metodo_layout)
        layout_gen.addWidget(group_metodo)

        layout_gen.addWidget(QLabel('-' * 40))

        # Parámetros básicos
        group_params = QGroupBox('Parámetros de diseño')
        params_layout = QVBoxLayout()

        # Densidad poblacional
        hbox_densidad = QHBoxLayout()
        hbox_densidad.addWidget(QLabel('Densidad poblacional:'))
        spin_densidad = QDoubleSpinBox()
        spin_densidad.setRange(0, 10000)
        spin_densidad.setDecimals(4)
        spin_densidad.setSingleStep(1)
        spin_densidad.setValue(100)
        hbox_densidad.addWidget(spin_densidad)

        self.label_unidad_densidad = QLabel('hab/m')
        hbox_densidad.addWidget(self.label_unidad_densidad)

        self.radio_longitudes.toggled.connect(
            lambda: self.actualizar_unidad_densidad()
        )
        self.radio_areas.toggled.connect(
            lambda: self.actualizar_unidad_densidad()
        )

        params_layout.addLayout(hbox_densidad)

        # Dotación
        hbox_dotacion = QHBoxLayout()
        hbox_dotacion.addWidget(QLabel('Dotación (L/hab/día):'))
        spin_dotacion = QDoubleSpinBox()
        spin_dotacion.setRange(0, 1000)
        spin_dotacion.setDecimals(1)
        spin_dotacion.setSingleStep(10)
        spin_dotacion.setValue(180)
        hbox_dotacion.addWidget(spin_dotacion)
        params_layout.addLayout(hbox_dotacion)

        # Coeficiente de retorno
        hbox_retorno = QHBoxLayout()
        hbox_retorno.addWidget(QLabel('Coeficiente de retorno (0.7 - 0.8):'))
        spin_retorno = QDoubleSpinBox()
        spin_retorno.setRange(0.5, 1.0)
        spin_retorno.setDecimals(3)
        spin_retorno.setSingleStep(0.01)
        spin_retorno.setValue(0.8)
        hbox_retorno.addWidget(spin_retorno)
        params_layout.addLayout(hbox_retorno)

        # Coeficiente de infiltración (ahora en L/s/km)
        hbox_infiltracion = QHBoxLayout()
        hbox_infiltracion.addWidget(QLabel('Coef. infiltración (L/s/km):'))
        spin_infiltracion = QDoubleSpinBox()
        spin_infiltracion.setRange(0, 100)
        spin_infiltracion.setDecimals(4)
        spin_infiltracion.setSingleStep(0.1)
        spin_infiltracion.setValue(0.5)          # ← DEFAULT 0.5 L/s/km
        spin_infiltracion.setSuffix(' L/s/km')
        hbox_infiltracion.addWidget(spin_infiltracion)
        params_layout.addLayout(hbox_infiltracion)

        # Porcentaje de conexiones erradas
        hbox_ce = QHBoxLayout()
        hbox_ce.addWidget(QLabel('Conexiones erradas (% del QmaxH):'))
        spin_ce = QDoubleSpinBox()
        spin_ce.setRange(0, 100)
        spin_ce.setDecimals(1)
        spin_ce.setSingleStep(1)
        spin_ce.setValue(10)
        spin_ce.setSuffix(' %')
        hbox_ce.addWidget(spin_ce)
        params_layout.addLayout(hbox_ce)

        # Caudal mínimo
        hbox_minimo = QHBoxLayout()
        hbox_minimo.addWidget(QLabel('Caudal mínimo (L/s) - norma: '))
        spin_minimo = QDoubleSpinBox()
        spin_minimo.setRange(0, 100)
        spin_minimo.setDecimals(2)
        spin_minimo.setSingleStep(0.5)
        spin_minimo.setValue(1.5)
        hbox_minimo.addWidget(spin_minimo)
        params_layout.addLayout(hbox_minimo)

        group_params.setLayout(params_layout)
        layout_gen.addWidget(group_params)

        tab_general.setLayout(layout_gen)
        tabs.addTab(tab_general, '1. Parámetros Generales')

        # ---------- TAB 2: COEFICIENTE DE MAYORACION ----------
        tab_mayoracion = QWidget()
        layout_may = QVBoxLayout()

        label_may_info = QLabel(
            'Selecciona el método para calcular el coeficiente de mayoración (M).\n'
            'Este coeficiente multiplica al caudal máximo horario.\n\n'
            '📌 QmaxH = (Dotación × Población × Retorno × M) / 86400\n'
            '📌 Población = Población propia + Población tributaria'
        )
        label_may_info.setWordWrap(True)
        layout_may.addWidget(label_may_info)

        layout_may.addWidget(QLabel('-' * 40))

        # Grupo de métodos
        group_mayoracion = QGroupBox('Método de coeficiente de mayoración')
        may_layout = QVBoxLayout()

        self.radio_harmon = QRadioButton('Harmon: M = 1 + 14/(4 + √P)')
        self.radio_harmon.setChecked(True)
        self.radio_babbit = QRadioButton('Babbit: M = 5 / P^0.20')
        self.radio_flores = QRadioButton('Flores: M = 3.5 / P^0.10')
        self.radio_popel = QRadioButton('Pópel (según tabla)')
        self.radio_manual = QRadioButton('Manual (K1 × K2)')

        may_layout.addWidget(self.radio_harmon)
        may_layout.addWidget(self.radio_babbit)
        may_layout.addWidget(self.radio_flores)
        may_layout.addWidget(self.radio_popel)
        may_layout.addWidget(self.radio_manual)

        group_mayoracion.setLayout(may_layout)
        layout_may.addWidget(group_mayoracion)

        # ===== VALORES MANUALES K1 Y K2 =====
        group_manual = QGroupBox('Valores manuales (K1 × K2)')
        manual_layout = QHBoxLayout()

        manual_layout.addWidget(QLabel('K1:'))
        spin_k1 = QDoubleSpinBox()
        spin_k1.setRange(0, 10)
        spin_k1.setDecimals(2)
        spin_k1.setSingleStep(0.1)
        spin_k1.setValue(1.0)
        manual_layout.addWidget(spin_k1)

        manual_layout.addWidget(QLabel('K2:'))
        spin_k2 = QDoubleSpinBox()
        spin_k2.setRange(0, 10)
        spin_k2.setDecimals(2)
        spin_k2.setSingleStep(0.1)
        spin_k2.setValue(1.0)
        manual_layout.addWidget(spin_k2)

        group_manual.setLayout(manual_layout)
        layout_may.addWidget(group_manual)

        # Información de restricciones
        label_restricciones = QLabel(
            '📌 RESTRICCIONES:\n'
            '   • Harmon: P < 1000 hab → M = 3.8 | P > 100000 hab → M = 2.0\n'
            '   • Babbit: P en miles de habitantes\n'
            '   • Flores: P en miles de habitantes\n'
            '   • Pópel: Según tabla de valores'
        )
        label_restricciones.setWordWrap(True)
        label_restricciones.setStyleSheet(
            'background-color: #f5f5f5; padding: 10px; border-radius: 5px;'
        )
        layout_may.addWidget(label_restricciones)

        tab_mayoracion.setLayout(layout_may)
        tabs.addTab(tab_mayoracion, '2. Coef. Mayoración')

        layout.addWidget(tabs)

        layout.addWidget(QLabel('-' * 40))

        # Barra de progreso
        progress = QProgressBar()
        layout.addWidget(progress)

        btn_calcular = QPushButton('Calcular Caudales')
        btn_calcular.setStyleSheet(
            'background-color: #4CAF50; color: white; font-weight: bold; font-size: 12pt;'
        )
        btn_calcular.clicked.connect(lambda: self.calcular(
            dialog,
            combo_tuberias.currentData(),
            spin_densidad.value(),
            spin_dotacion.value(),
            spin_retorno.value(),
            spin_infiltracion.value(),   # ← ahora es L/s/km
            spin_ce.value(),
            spin_minimo.value(),
            spin_k1.value(),
            spin_k2.value(),
            progress
        ))
        layout.addWidget(btn_calcular)

        btn_cerrar = QPushButton('Cerrar')
        btn_cerrar.setStyleSheet('background-color: #f44336; color: white;')
        btn_cerrar.clicked.connect(dialog.accept)
        layout.addWidget(btn_cerrar)

        dialog.setLayout(layout)
        dialog.exec_()

    def actualizar_unidad_densidad(self):
        """Actualizar la unidad de densidad según el método seleccionado"""
        if self.radio_areas.isChecked():
            self.label_unidad_densidad.setText('(hab/ha)')
        else:
            self.label_unidad_densidad.setText('(hab/m)')

    def verificar_campos_existentes(self, layer, usar_areas):
        """Verificar que la capa tenga los campos necesarios según el método"""

        if usar_areas:
            campos_necesarios = ['A', 'At', 'La']
            nombre_campos = ['A (área propia)', 'At (área tributaria)',
                             'La (longitud acumulada)']
        else:
            campos_necesarios = ['L', 'Lt', 'La']
            nombre_campos = ['L (longitud propia)', 'Lt (longitud tributaria)',
                             'La (longitud acumulada)']

        campos_faltantes = []
        for i, campo in enumerate(campos_necesarios):
            if layer.fields().indexFromName(campo) == -1:
                campos_faltantes.append(nombre_campos[i])

        if campos_faltantes:
            metodo = 'áreas' if usar_areas else 'longitudes'
            QMessageBox.warning(
                self.iface.mainWindow(),
                'Error',
                f'La capa no tiene los campos necesarios para el método de {metodo}:\n'
                f'{", ".join(campos_faltantes)}\n\n'
                f'Para longitudes: ejecuta "Calcular Acumulados"\n'
                f'Para áreas: ejecuta "Calcular Áreas Propias" y '
                f'"Calcular Áreas Acumuladas"'
            )
            return False

        return True

    def asegurar_campos(self, layer):
        """Asegurar que todos los campos necesarios existan (sin DeprecationWarning)"""

        campos = [
            ('pobla_prop', 'double'),   # Población propia
            ('pobla_trib', 'double'),   # Población tributaria
            ('pobla_tot',  'double'),   # Población total
            ('coef_m',     'double'),   # Coeficiente de mayoración
            ('qmaxh',      'double'),   # Caudal máximo horario
            ('qinf',       'double'),   # Caudal de infiltración
            ('qce',        'double'),   # Caudal conexiones erradas
            ('qp',         'double'),   # Caudales puntuales
            ('qacu',       'double'),   # Caudal acumulado
            ('qdise',      'double')    # Caudal de diseño
        ]

        for nombre, tipo in campos:
            if layer.fields().indexFromName(nombre) == -1:
                layer.dataProvider().addAttributes([_campo(nombre, tipo)])

        layer.updateFields()

    def obtener_valor_numerico(self, valor):
        """Convertir QVariant o cualquier valor a float"""
        if valor is None:
            return 0.0
        try:
            if hasattr(valor, 'isNull'):
                if valor.isNull():
                    return 0.0
            return float(valor)
        except (ValueError, TypeError):
            return 0.0

    def calcular_coeficiente_mayoracion(self, poblacion_total_hab):
        """
        Calcula el coeficiente de mayoración según el método seleccionado
        """
        P = poblacion_total_hab / 1000.0
        P_hab = poblacion_total_hab

        if self.radio_harmon.isChecked():
            if P_hab < 1000:
                return 3.8
            elif P_hab > 100000:
                return 2.0
            else:
                if P > 0:
                    return 1 + 14 / (4 + math.sqrt(P))
                else:
                    return 3.8

        elif self.radio_babbit.isChecked():
            if P > 0:
                return 5 / (P ** 0.20)
            else:
                return 5.0

        elif self.radio_flores.isChecked():
            if P > 0:
                return 3.5 / (P ** 0.10)
            else:
                return 3.5

        elif self.radio_popel.isChecked():
            if P_hab < 5000:
                return 2.20
            elif P_hab < 10000:
                return 1.92
            elif P_hab < 50000:
                return 1.72
            elif P_hab < 250000:
                return 1.46
            else:
                return 1.33

        else:  # Manual (K1 × K2)
            k1 = self.k1_value if hasattr(self, 'k1_value') else 1.0
            k2 = self.k2_value if hasattr(self, 'k2_value') else 1.0
            return k1 * k2

    def calcular(self, dialog, tuberias_id, densidad_input, dotacion, retorno,
                 coef_infiltracion_lskm, pct_ce, caudal_minimo, k1, k2, progress):
        """Calcular todos los caudales"""

        self.k1_value = k1
        self.k2_value = k2

        self.capa_tuberias = QgsProject.instance().mapLayer(tuberias_id)

        if not self.capa_tuberias:
            QMessageBox.warning(self.iface.mainWindow(), 'Error',
                                'No se encontró la capa')
            return

        usar_areas = self.radio_areas.isChecked()

        # ===== DENSIDAD SEGÚN MÉTODO =====
        if usar_areas:
            # Áreas: usuario ingresa en hab/ha → convertir a hab/m² (/10000)
            densidad = densidad_input / 10000.0
            unidad_entrada = 'hab/ha'
            unidad_calculo = 'hab/m²'
        else:
            # Longitudes: usuario ingresa en hab/m (directo)
            densidad = densidad_input
            unidad_entrada = 'hab/m'
            unidad_calculo = 'hab/m'

        # ===== CONVERSIÓN DE INFILTRACIÓN: L/s/km → L/s/m =====
        # El usuario ingresa en L/s/km; para el cálculo se necesita L/s/m
        coef_infiltracion = coef_infiltracion_lskm / 1000.0

        # Verificar campos existentes según el método
        if not self.verificar_campos_existentes(self.capa_tuberias, usar_areas):
            return

        progress.setValue(10)

        # Asegurar campos de resultados
        self.asegurar_campos(self.capa_tuberias)

        progress.setValue(20)

        # ===== CONVERTIR PARAMETROS =====
        pct_ce_decimal = pct_ce / 100.0

        # ===== CALCULAR PARA CADA TUBERIA =====
        self.capa_tuberias.startEditing()

        idx_pobla_prop = self.capa_tuberias.fields().indexFromName('pobla_prop')
        idx_pobla_trib = self.capa_tuberias.fields().indexFromName('pobla_trib')
        idx_pobla_tot = self.capa_tuberias.fields().indexFromName('pobla_tot')
        idx_coef_m = self.capa_tuberias.fields().indexFromName('coef_m')
        idx_qmaxh = self.capa_tuberias.fields().indexFromName('qmaxh')
        idx_qinf = self.capa_tuberias.fields().indexFromName('qinf')
        idx_qce = self.capa_tuberias.fields().indexFromName('qce')
        idx_qp = self.capa_tuberias.fields().indexFromName('qp')
        idx_qacu = self.capa_tuberias.fields().indexFromName('qacu')
        idx_qdise = self.capa_tuberias.fields().indexFromName('qdise')

        total_features = sum(1 for _ in self.capa_tuberias.getFeatures())
        procesados = 0

        SEGUNDOS_DIA = 86400.0

        for feature in self.capa_tuberias.getFeatures():

            # ===== OBTENER VALORES SEGÚN MÉTODO =====
            if usar_areas:
                # Método por áreas: usa A (propia) y At (tributaria)
                c_pob_p = self.obtener_valor_numerico(feature.attribute('A'))
                c_pob_trib = self.obtener_valor_numerico(feature.attribute('At'))
                La = self.obtener_valor_numerico(feature.attribute('La'))
            else:
                # Método por longitudes: usa L (propia) y Lt (tributaria)
                c_pob_p = self.obtener_valor_numerico(feature.attribute('L'))
                c_pob_trib = self.obtener_valor_numerico(feature.attribute('Lt'))
                La = self.obtener_valor_numerico(feature.attribute('La'))

            # ==========================================
            # PASO 1: POBLACION
            # ==========================================
            pobla_propia = densidad * c_pob_p
            pobla_tributaria = densidad * c_pob_trib
            poblacion_total = pobla_propia + pobla_tributaria

            self.capa_tuberias.changeAttributeValue(
                feature.id(), idx_pobla_prop, round(pobla_propia, 4)
            )
            self.capa_tuberias.changeAttributeValue(
                feature.id(), idx_pobla_trib, round(pobla_tributaria, 4)
            )
            self.capa_tuberias.changeAttributeValue(
                feature.id(), idx_pobla_tot, round(poblacion_total, 4)
            )

            # ==========================================
            # PASO 2: COEFICIENTE DE MAYORACION (M)
            # ==========================================
            coef_m = self.calcular_coeficiente_mayoracion(poblacion_total)
            self.capa_tuberias.changeAttributeValue(
                feature.id(), idx_coef_m, round(coef_m, 4)
            )

            # ==========================================
            # PASO 3: QmaxH
            # ==========================================
            qmaxh = (dotacion * poblacion_total * retorno * coef_m) / SEGUNDOS_DIA
            self.capa_tuberias.changeAttributeValue(
                feature.id(), idx_qmaxh, round(qmaxh, 6)
            )

            # ==========================================
            # PASO 4: Qinf (usa La - longitud acumulada)
            # coef_infiltracion está en L/s/m (ya convertido)
            # ==========================================
            qinf = coef_infiltracion * La
            self.capa_tuberias.changeAttributeValue(
                feature.id(), idx_qinf, round(qinf, 6)
            )

            # ==========================================
            # PASO 5: Qce
            # ==========================================
            qce = pct_ce_decimal * qmaxh
            self.capa_tuberias.changeAttributeValue(
                feature.id(), idx_qce, round(qce, 6)
            )

            # ==========================================
            # PASO 6: Qp (Caudales puntuales - editables)
            # ==========================================
            qp_existente = feature.attribute('qp')
            qp = self.obtener_valor_numerico(qp_existente)
            self.capa_tuberias.changeAttributeValue(
                feature.id(), idx_qp, round(qp, 6)
            )

            # ==========================================
            # PASO 7: Qacu
            # ==========================================
            qacu = qmaxh + qinf + qce + qp
            self.capa_tuberias.changeAttributeValue(
                feature.id(), idx_qacu, round(qacu, 6)
            )

            # ==========================================
            # PASO 8: Qdise
            # ==========================================
            qdise = max(qacu, caudal_minimo)
            self.capa_tuberias.changeAttributeValue(
                feature.id(), idx_qdise, round(qdise, 6)
            )

            procesados += 1

            if procesados % 10 == 0 or procesados == total_features:
                pct = 20 + (procesados / total_features) * 70
                progress.setValue(int(pct))

        progress.setValue(95)
        self.capa_tuberias.commitChanges()
        progress.setValue(100)

        dialog.accept()

        # ===== DETERMINAR METODO USADO =====
        if self.radio_harmon.isChecked():
            metodo_m = 'Harmon'
        elif self.radio_babbit.isChecked():
            metodo_m = 'Babbit'
        elif self.radio_flores.isChecked():
            metodo_m = 'Flores'
        elif self.radio_popel.isChecked():
            metodo_m = 'Pópel'
        else:
            metodo_m = f'Manual (K1={k1}, K2={k2})'

        metodo_pob = 'Áreas (A y At)' if usar_areas else 'Longitudes (L y Lt)'

        # ===== MOSTRAR RESULTADOS =====
        mensaje = "=== CALCULO DE CAUDALES COMPLETADO ===\n\n"
        mensaje += f"📊 Tuberías procesadas: {procesados}\n\n"
        mensaje += "📌 PARÁMETROS UTILIZADOS:\n"
        mensaje += f"   - Método población: {metodo_pob}\n"
        mensaje += f"   - Densidad: {densidad_input} {unidad_entrada}"
        if usar_areas:
            mensaje += f" → {densidad:.8f} {unidad_calculo}\n"
        else:
            mensaje += f" → {densidad} {unidad_calculo}\n"
        mensaje += f"   - Dotación: {dotacion} L/hab/día\n"
        mensaje += f"   - Coef. retorno: {retorno}\n"
        mensaje += f"   - Coef. mayoración: {metodo_m}\n"
        mensaje += f"   - Coef. infiltración: {coef_infiltracion_lskm} L/s/km "
        mensaje += f"→ {coef_infiltracion:.6f} L/s/m\n"
        mensaje += f"   - Conexiones erradas: {pct_ce}%\n"
        mensaje += f"   - Caudal mínimo: {caudal_minimo} L/s\n\n"
        mensaje += "📌 CAMPOS ACTUALIZADOS:\n"
        mensaje += "   1. pobla_prop  → Población propia (hab)\n"
        mensaje += "   2. pobla_trib  → Población tributaria (hab)\n"
        mensaje += "   3. pobla_tot   → Población TOTAL (propia + tributaria)\n"
        mensaje += "   4. coef_m      → Coeficiente de mayoración\n"
        mensaje += "   5. qmaxh       → Caudal máximo horario (L/s)\n"
        mensaje += "   6. qinf        → Caudal de infiltración (L/s)\n"
        mensaje += "   7. qce         → Conexiones erradas (L/s)\n"
        mensaje += "   8. qp          → Caudales puntuales (L/s) - ¡EDITABLE!\n"
        mensaje += "   9. qacu        → Caudal acumulado (L/s)\n"
        mensaje += "  10. qdise       → Caudal de diseño (L/s)\n\n"
        mensaje += "💡 FÓRMULA QmaxH:\n"
        mensaje += "   QmaxH = (Dotación × Población_total × Retorno × M) / 86400\n"
        mensaje += f"   Donde Población_total = Densidad ({unidad_calculo}) × "
        mensaje += f"{'At' if usar_areas else 'Lt'}\n\n"
        mensaje += "💡 FÓRMULA Qinf:\n"
        mensaje += "   Qinf = Coef_infiltración (L/s/m) × La (m)\n"
        mensaje += f"   Equivalente a: Coef (L/s/km) × La (m) / 1000"

        QMessageBox.information(
            self.iface.mainWindow(),
            'Caudales Calculados',
            mensaje
        )