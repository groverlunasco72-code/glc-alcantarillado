# -*- coding: utf-8 -*-
"""
Módulo: Verificar Ángulos de Conexión en Cámaras

Para cada cámara con tubería de SALIDA (continuación, cab_ata != 'Arranque'),
verifica el ángulo en XY entre cada tubería que LLEGA (entrada, no-Arranque)
y la tubería de salida.

CONVENCIÓN DE VECTORES (misma para entrada y salida):
    Ambos vectores apuntan DESDE la cámara hacia el otro extremo de su
    respectiva tubería. Por tanto:
        - Ángulo 180° → entrada y salida en direcciones opuestas desde C
                       → el agua entra por un lado y sale por el opuesto → IDEAL
        - Ángulo > 90° → correcto
        - Ángulo ≤ 90° → PROBLEMA (el agua entra muy de lado o contra la salida)

Reporte: lista de TUBERÍAS DE ENTRADA que incumplen el ángulo mínimo,
         ordenadas de menor a mayor ángulo (las más críticas primero).

NOTAS:
    - Las tuberías Arranque NO se consideran (son de otra red/subred).
    - Esta verificación NO modifica la red. Solo reporta.

Compatible con QGIS 3.x y preparado para 4.x.
"""

from qgis.core import (
    QgsProject, QgsVectorLayer,
    QgsWkbTypes, QgsPointXY,
)
from qgis.PyQt.QtWidgets import (
    QMessageBox, QDialog, QVBoxLayout, QLabel,
    QPushButton, QComboBox, QProgressBar,
    QTextEdit, QHBoxLayout, QGroupBox,
    QCheckBox, QTabWidget, QWidget, QTableWidget,
    QTableWidgetItem, QHeaderView, QSpinBox,
)
from qgis.PyQt.QtCore import Qt
import math


try:
    _MSG_YES = QMessageBox.StandardButton.Yes
    _MSG_NO = QMessageBox.StandardButton.No
except AttributeError:
    _MSG_YES = QMessageBox.Yes
    _MSG_NO = QMessageBox.No


def _enum_value(x):
    return getattr(x, 'value', x)


class VerificarAngulosCamaras:

    CAMPO_ID_TUBERIA = 'ID_O'
    CAMPO_CI = 'Ci'
    CAMPO_CF = 'Cf'
    CAMPO_ID_CAMARA = 'ID_O'
    CAMPO_CAB_ATA = 'cab_ata'

    def __init__(self, iface):
        self.iface = iface
        self.capa_tuberias = None
        self.capa_camaras = None
        self.debug = False

    # ============================================================
    # HELPERS
    # ============================================================
    @staticmethod
    def _attr(feat, nombre):
        try:
            return feat.attribute(nombre)
        except Exception:
            try:
                return feat[nombre]
            except Exception:
                return None

    @staticmethod
    def _idx(layer, nombre):
        try:
            return layer.fields().indexFromName(nombre)
        except Exception:
            return -1

    @staticmethod
    def _msg(parent, icono, titulo, texto):
        try:
            box = QMessageBox(parent)
            box.setIcon(icono)
            box.setWindowTitle(titulo)
            box.setText(texto)
            box.exec_()
        except Exception:
            if icono == QMessageBox.Warning:
                QMessageBox.warning(parent, titulo, texto)
            elif icono == QMessageBox.Critical:
                QMessageBox.critical(parent, titulo, texto)
            else:
                QMessageBox.information(parent, titulo, texto)

    # ============================================================
    # DIÁLOGO
    # ============================================================
    def mostrar_dialogo(self):
        dialog = QDialog(self.iface.mainWindow())
        dialog.setWindowTitle('GLC - Verificar Ángulos en Cámaras')
        dialog.setMinimumWidth(950)
        dialog.setMinimumHeight(650)
        self.dialog = dialog

        layout = QVBoxLayout()

        lbl = QLabel('<b>📐 Verificar Ángulos en Cámaras</b>')
        lbl.setStyleSheet('font-size: 14pt; color: #2c3e50;')
        layout.addWidget(lbl)

        desc = QLabel(
            'Detecta las TUBERÍAS DE ENTRADA que forman un ángulo MENOR al mínimo\n'
            'con la tubería de SALIDA de su cámara, vista en el plano XY.\n\n'
            '📌 Ángulo 180° = entrada y salida en direcciones opuestas desde la cámara (ideal)\n'
            '📌 Ángulo > mínimo = correcto\n'
            '📌 Ángulo ≤ mínimo = ⚠️ tubería a corregir\n\n'
            '⚠️ Las tuberías Arranque NO se verifican (son de otra red/subred).\n'
            '⚠️ Solo verifica, no modifica la red.'
        )
        desc.setWordWrap(True)
        desc.setStyleSheet('background-color: #ecf0f1; padding: 8px; border-radius: 4px;')
        layout.addWidget(desc)

        # ---- Capas ----
        box_capas = QGroupBox('Capas de trabajo')
        hb_capas = QHBoxLayout()

        hb_capas.addWidget(QLabel('Tuberías:'))
        self.combo_tuberias = QComboBox()
        for layer in QgsProject.instance().mapLayers().values():
            if isinstance(layer, QgsVectorLayer) and \
               _enum_value(layer.geometryType()) == _enum_value(QgsWkbTypes.LineGeometry):
                nombre = layer.name()
                prefijo = '⭐ ' if 'GLC_Tuberias' in nombre else ''
                self.combo_tuberias.addItem(f'{prefijo}{nombre}', layer.id())
        hb_capas.addWidget(self.combo_tuberias)

        hb_capas.addWidget(QLabel('Cámaras:'))
        self.combo_camaras = QComboBox()
        for layer in QgsProject.instance().mapLayers().values():
            if isinstance(layer, QgsVectorLayer) and \
               _enum_value(layer.geometryType()) == _enum_value(QgsWkbTypes.PointGeometry):
                nombre = layer.name()
                prefijo = '⭐ ' if 'GLC_Camaras' in nombre else ''
                self.combo_camaras.addItem(f'{prefijo}{nombre}', layer.id())
        hb_capas.addWidget(self.combo_camaras)

        box_capas.setLayout(hb_capas)
        layout.addWidget(box_capas)

        # ---- Opciones ----
        box_op = QGroupBox('Opciones')
        hb_op = QHBoxLayout()

        hb_op.addWidget(QLabel('Ángulo mínimo aceptable (°):'))
        self.spin_angulo = QSpinBox()
        self.spin_angulo.setRange(0, 180)
        self.spin_angulo.setValue(90)
        self.spin_angulo.setSuffix(' °')
        self.spin_angulo.setToolTip(
            'Ángulo mínimo entre cada tubería de entrada y la salida.\n'
            'Por defecto 90°. Valores > 90° son más estrictos.'
        )
        hb_op.addWidget(self.spin_angulo)

        self.chk_debug = QCheckBox('Mostrar detalles en consola')
        hb_op.addWidget(self.chk_debug)

        hb_op.addStretch()
        box_op.setLayout(hb_op)
        layout.addWidget(box_op)

        # ---- Botón ----
        btn = QPushButton('📐 Verificar Ángulos')
        btn.setStyleSheet(
            'background-color: #2196f3; color: white; font-weight: bold; padding: 10px;'
        )
        btn.clicked.connect(self._verificar)
        layout.addWidget(btn)

        self.progress = QProgressBar()
        layout.addWidget(self.progress)

        # ---- Tabs ----
        self.tabs = QTabWidget()

        # Tab 1: Resumen
        self.tab_resumen = QWidget()
        lay_r = QVBoxLayout()
        self.text_resumen = QTextEdit()
        self.text_resumen.setReadOnly(True)
        self.text_resumen.setStyleSheet('font-family: monospace;')
        lay_r.addWidget(self.text_resumen)
        self.tab_resumen.setLayout(lay_r)
        self.tabs.addTab(self.tab_resumen, '📊 Resumen')

        # Tab 2: Tuberías con problema
        self.tab_problemas = QWidget()
        lay_p = QVBoxLayout()

        info_p = QLabel(
            '👉 Cada fila es una TUBERÍA DE ENTRADA que incumple el ángulo mínimo.\n'
            '   Ordenadas por ángulo ascendente (las más críticas primero).'
        )
        info_p.setWordWrap(True)
        info_p.setStyleSheet('color: #c0392b; font-weight: bold; padding: 4px;')
        lay_p.addWidget(info_p)

        self.table_problemas = QTableWidget()
        self.table_problemas.setColumnCount(8)
        self.table_problemas.setHorizontalHeaderLabels([
            'Tubería ID_O',
            'Ángulo (°)',
            'Cámara',
            'Ci entrada',
            'Cf entrada',
            'Tubería salida',
            'Longitud L',
            'Estado',
        ])
        self.table_problemas.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.ResizeToContents
        )
        self.table_problemas.horizontalHeader().setSectionResizeMode(
            1, QHeaderView.ResizeToContents
        )
        lay_p.addWidget(self.table_problemas)
        self.tab_problemas.setLayout(lay_p)
        self.tabs.addTab(self.tab_problemas, '❌ Tuberías con problema')

        # Tab 3: Resumen por cámara
        self.tab_todas = QWidget()
        lay_t = QVBoxLayout()
        self.table_todas = QTableWidget()
        self.table_todas.setColumnCount(7)
        self.table_todas.setHorizontalHeaderLabels([
            'Cámara', 'N entradas', 'Tubería salida',
            'Ángulo mín (°)', 'Ángulo máx (°)',
            'Tuberías problemáticas', 'Estado',
        ])
        lay_t.addWidget(self.table_todas)
        self.tab_todas.setLayout(lay_t)
        self.tabs.addTab(self.tab_todas, '🏗️ Resumen por cámara')

        layout.addWidget(self.tabs)

        btn_cerrar = QPushButton('Cerrar')
        btn_cerrar.clicked.connect(dialog.accept)
        layout.addWidget(btn_cerrar)

        dialog.setLayout(layout)
        dialog.exec_()

    # ============================================================
    # MATEMÁTICA
    # ============================================================
    @staticmethod
    def _angulo_entre_vectores(v1, v2):
        """Ángulo en grados [0, 180] entre dos vectores 2D."""
        n1 = math.hypot(v1[0], v1[1])
        n2 = math.hypot(v2[0], v2[1])
        if n1 < 1e-9 or n2 < 1e-9:
            return None
        dot = v1[0] * v2[0] + v1[1] * v2[1]
        cos_a = dot / (n1 * n2)
        cos_a = max(-1.0, min(1.0, cos_a))
        return math.degrees(math.acos(cos_a))

    def _vector_desde_camara(self, tuberia, id_camara):
        """
        Vector DESDE la cámara hacia el otro extremo de la tubería.
        Se usa para ENTRADA y para SALIDA con la misma convención.

        Con esta convención:
            - Ángulo 180° → entrada y salida opuestas desde C → IDEAL
            - Ángulo > 90° → correcto
            - Ángulo ≤ 90° → problema
        """
        ci, cf = tuberia['ci'], tuberia['cf']
        xi, yi = tuberia['xi'], tuberia['yi']
        xf, yf = tuberia['xf'], tuberia['yf']
        if xi is None or yi is None or xf is None or yf is None:
            return None
        if ci == id_camara:
            return (xf - xi, yf - yi)
        elif cf == id_camara:
            return (xi - xf, yi - yf)
        return None

    # Alias explícitos para claridad del código
    def _vector_salida(self, tuberia, id_camara):
        return self._vector_desde_camara(tuberia, id_camara)

    def _vector_entrada(self, tuberia, id_camara):
        return self._vector_desde_camara(tuberia, id_camara)

    # ============================================================
    # VERIFICACIÓN
    # ============================================================
    def _verificar(self):
        tub_id = self.combo_tuberias.currentData()
        cam_id = self.combo_camaras.currentData()

        if not tub_id or not cam_id:
            self._msg(self.iface.mainWindow(), QMessageBox.Warning, 'Error',
                      'Debe seleccionar las capas de tuberías y cámaras')
            return

        self.capa_tuberias = QgsProject.instance().mapLayer(tub_id)
        self.capa_camaras = QgsProject.instance().mapLayer(cam_id)

        if not self.capa_tuberias or not self.capa_camaras:
            self._msg(self.iface.mainWindow(), QMessageBox.Warning, 'Error',
                      'No se encontraron las capas seleccionadas')
            return

        for campo in (self.CAMPO_CI, self.CAMPO_CF, 'Xi', 'Yi', 'Xf', 'Yf'):
            if self._idx(self.capa_tuberias, campo) == -1:
                self._msg(self.iface.mainWindow(), QMessageBox.Warning, 'Error',
                          f'La capa de tuberías no tiene el campo "{campo}"')
                return

        self.debug = self.chk_debug.isChecked()
        angulo_min = self.spin_angulo.value()

        self.progress.setValue(0)
        self.text_resumen.clear()
        self.table_problemas.setRowCount(0)
        self.table_todas.setRowCount(0)

        # ============================================
        # PASO 1: Cargar tuberías
        # ============================================
        tuberias = {}
        for f in self.capa_tuberias.getFeatures():
            id_t = self._attr(f, self.CAMPO_ID_TUBERIA)
            if id_t is None:
                continue
            tuberias[id_t] = {
                'id': id_t,
                'ci': self._attr(f, self.CAMPO_CI),
                'cf': self._attr(f, self.CAMPO_CF),
                'xi': self._attr(f, 'Xi'),
                'yi': self._attr(f, 'Yi'),
                'xf': self._attr(f, 'Xf'),
                'yf': self._attr(f, 'Yf'),
                'L': self._attr(f, 'L'),
                'cab_ata': self._attr(f, self.CAMPO_CAB_ATA) or '',
            }

        self.progress.setValue(30)

        # ============================================
        # PASO 2: Cargar cámaras
        # ============================================
        camaras = {}
        for f in self.capa_camaras.getFeatures():
            id_c = self._attr(f, self.CAMPO_ID_CAMARA)
            if id_c is None:
                continue
            camaras[id_c] = {
                'id': id_c,
                'entradas': [],
                'salidas': [],
            }

        for id_t, t in tuberias.items():
            ci, cf = t['ci'], t['cf']
            if ci in camaras:
                camaras[ci]['salidas'].append(id_t)
            if cf in camaras:
                camaras[cf]['entradas'].append(id_t)

        self.progress.setValue(60)

        # ============================================
        # PASO 3: Verificar ángulos — reporte por TUBERÍA
        # ============================================
        problemas = []
        resultados_camaras = []

        total_camaras = len(camaras)
        for i, (id_c, c) in enumerate(camaras.items()):
            self.progress.setValue(60 + int(35 * i / max(1, total_camaras)))

            # Tubería de SALIDA = continuación (no-Arranque)
            salidas_continuacion = [
                id_t for id_t in c['salidas']
                if tuberias[id_t]['cab_ata'] != 'Arranque'
            ]

            if len(salidas_continuacion) == 0:
                resultados_camaras.append({
                    'id': id_c,
                    'n_entradas': len(c['entradas']),
                    'salida': None,
                    'ang_min': None,
                    'ang_max': None,
                    'problemas': [],
                    'estado': '— Sin continuación',
                })
                continue

            id_t_salida = salidas_continuacion[0]
            t_salida = tuberias[id_t_salida]
            v_salida = self._vector_salida(t_salida, id_c)

            if v_salida is None:
                resultados_camaras.append({
                    'id': id_c,
                    'n_entradas': len(c['entradas']),
                    'salida': id_t_salida,
                    'ang_min': None,
                    'ang_max': None,
                    'problemas': [],
                    'estado': '— Salida sin geometría',
                })
                continue

            # Entradas a verificar: NO-Arranque
            entradas_a_verificar = [
                id_t for id_t in c['entradas']
                if tuberias[id_t]['cab_ata'] != 'Arranque'
            ]

            angulos = []
            problemas_de_esta_camara = []

            for id_t_ent in entradas_a_verificar:
                t_ent = tuberias[id_t_ent]
                v_ent = self._vector_entrada(t_ent, id_c)
                if v_ent is None:
                    continue

                ang = self._angulo_entre_vectores(v_ent, v_salida)
                if ang is None:
                    continue

                angulos.append(ang)

                if ang <= angulo_min:
                    problemas.append({
                        'tuberia': id_t_ent,
                        'angulo': round(ang, 2),
                        'camara': id_c,
                        'ci': t_ent['ci'],
                        'cf': t_ent['cf'],
                        'salida': id_t_salida,
                        'L': t_ent['L'],
                        'estado': f'⚠️ ≤ {angulo_min}°',
                    })
                    problemas_de_esta_camara.append(id_t_ent)

            if angulos:
                estado = '❌ Revisar' if problemas_de_esta_camara else '✅ OK'
                resultados_camaras.append({
                    'id': id_c,
                    'n_entradas': len(entradas_a_verificar),
                    'salida': id_t_salida,
                    'ang_min': round(min(angulos), 2),
                    'ang_max': round(max(angulos), 2),
                    'problemas': problemas_de_esta_camara,
                    'estado': estado,
                })
            else:
                resultados_camaras.append({
                    'id': id_c,
                    'n_entradas': len(entradas_a_verificar),
                    'salida': id_t_salida,
                    'ang_min': None,
                    'ang_max': None,
                    'problemas': [],
                    'estado': '— Sin entradas válidas',
                })

        problemas.sort(key=lambda p: p['angulo'])

        self.progress.setValue(95)

        self._mostrar_resumen(tuberias, camaras, problemas,
                              resultados_camaras, angulo_min)
        self._mostrar_problemas(problemas)
        self._mostrar_todas(resultados_camaras)

        self.progress.setValue(100)

        if problemas:
            self._msg(self.iface.mainWindow(), QMessageBox.Warning,
                      'Verificación completada',
                      f'Se encontraron {len(problemas)} TUBERÍA(S) de entrada con '
                      f'ángulo ≤ {angulo_min}°.\n\n'
                      f'Revisa la pestaña "❌ Tuberías con problema" para ver el '
                      f'listado con sus ID_O.\n\n'
                      '⚠️ Se excluyeron las tuberías Arranque.')
        else:
            self._msg(self.iface.mainWindow(), QMessageBox.Information,
                      'Verificación completada',
                      f'✅ No se encontraron problemas de ángulos.\n'
                      f'Todas las tuberías de entrada (no-Arranque) forman más de '
                      f'{angulo_min}° con su salida.')

    # ============================================================
    # MOSTRAR RESULTADOS
    # ============================================================
    def _mostrar_resumen(self, tuberias, camaras, problemas,
                         resultados, angulo_min):
        total_tub = len(tuberias)
        total_cam = len(camaras)
        cam_con_salida = sum(1 for r in resultados if r['salida'] is not None)
        cam_con_entradas = sum(1 for r in resultados if r['n_entradas'] > 0)
        cam_ok = sum(1 for r in resultados if r['estado'] == '✅ OK')
        cam_revisar = sum(1 for r in resultados if r['estado'] == '❌ Revisar')

        texto = f"""
╔══════════════════════════════════════════════════════════════════════════════╗
║                   VERIFICACIÓN DE ÁNGULOS EN CÁMARAS                         ║
╠══════════════════════════════════════════════════════════════════════════════╣
║                                                                              ║
║  📊 ESTADÍSTICAS                                                             ║
║  ──────────────────────────────────────────────────────────────────────────  ║
║  • Total de tuberías:                  {total_tub:>6}                        ║
║  • Total de cámaras:                   {total_cam:>6}                        ║
║  • Cámaras con tubería de salida:      {cam_con_salida:>6}                        ║
║  • Cámaras con entradas válidas:       {cam_con_entradas:>6}                        ║
║                                                                              ║
║  📋 RESULTADOS                                                               ║
║  ──────────────────────────────────────────────────────────────────────────  ║
║  • Ángulo mínimo aceptable:            {angulo_min:>6} °                      ║
║  • Cámaras OK (todas > {angulo_min}°):       {cam_ok:>6}                        ║
║  • Cámaras con problemas:              {cam_revisar:>6}                        ║
║  • TUBERÍAS con problema:              {len(problemas):>6}   ← a corregir    ║
║                                                                              ║
║  📌 CONVENCIÓN: Ángulo 180° = entrada y salida opuestas desde la cámara.      ║
║  📌 REGLA: Cada entrada (no-Arranque) debe formar > {angulo_min}° con la salida.║
║  ⚠️ Las tuberías Arranque NO se verifican (son de otra red/subred).           ║
║                                                                              ║
╚══════════════════════════════════════════════════════════════════════════════╝
"""
        self.text_resumen.setText(texto)
        if self.debug:
            print(texto)

    def _mostrar_problemas(self, problemas):
        self.table_problemas.setRowCount(len(problemas))

        for row, p in enumerate(problemas):
            item_id = QTableWidgetItem(str(p['tuberia']))
            try:
                item_id.setBackground(Qt.red)
                item_id.setForeground(Qt.white)
            except Exception:
                pass
            self.table_problemas.setItem(row, 0, item_id)

            item_ang = QTableWidgetItem(f"{p['angulo']:.2f}")
            try:
                item_ang.setForeground(Qt.darkRed)
            except Exception:
                pass
            self.table_problemas.setItem(row, 1, item_ang)

            self.table_problemas.setItem(row, 2, QTableWidgetItem(str(p['camara'])))
            self.table_problemas.setItem(row, 3, QTableWidgetItem(str(p['ci'])))
            self.table_problemas.setItem(row, 4, QTableWidgetItem(str(p['cf'])))
            self.table_problemas.setItem(row, 5, QTableWidgetItem(str(p['salida'])))

            L = p['L']
            self.table_problemas.setItem(
                row, 6,
                QTableWidgetItem(f"{L:.3f}" if isinstance(L, (int, float)) else '—')
            )
            self.table_problemas.setItem(row, 7, QTableWidgetItem(p['estado']))

        self.table_problemas.resizeColumnsToContents()

    def _mostrar_todas(self, resultados):
        self.table_todas.setRowCount(len(resultados))

        for row, r in enumerate(resultados):
            self.table_todas.setItem(row, 0, QTableWidgetItem(str(r['id'])))
            self.table_todas.setItem(row, 1, QTableWidgetItem(str(r['n_entradas'])))
            self.table_todas.setItem(row, 2, QTableWidgetItem(
                str(r['salida']) if r['salida'] is not None else '—'
            ))
            self.table_todas.setItem(row, 3, QTableWidgetItem(
                str(r['ang_min']) if r['ang_min'] is not None else '—'
            ))
            self.table_todas.setItem(row, 4, QTableWidgetItem(
                str(r['ang_max']) if r['ang_max'] is not None else '—'
            ))
            probs = r.get('problemas', [])
            txt_probs = ', '.join(str(x) for x in probs[:5])
            if len(probs) > 5:
                txt_probs += f' … (+{len(probs) - 5})'
            self.table_todas.setItem(row, 5, QTableWidgetItem(txt_probs or '—'))
            self.table_todas.setItem(row, 6, QTableWidgetItem(r['estado']))

        self.table_todas.resizeColumnsToContents()

    def desactivar(self):
        pass