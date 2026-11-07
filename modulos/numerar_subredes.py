# -*- coding: utf-8 -*-
"""
Módulo: Numerar Subredes (v21)

Modo 1er NIVEL:
    Seleccionas rutas → numeración 1, 2, 3, ...

Modo 2do NIVEL:
    Haces clic sobre una tubería de la subred.
    El módulo detecta la cámara principal y asigna k.N ÚNICO.

Modo RESTANTES:
    Numera TODAS las cámaras y tuberías sin número usando los vecinos
    ya numerados como referencia (en olas sucesivas).

Reglas:
    - La numeración de CÁMARAS y TUBERÍAS es INDEPENDIENTE.
    - Los IDs guardados llevan prefijo:
        · Cámaras:   C1, C5, C5.1, C10.3, ...
        · Tuberías:  T1, T5, T5.1, T10.3, ...
    - Ci_Num y Cf_Num también llevan prefijo C (referencian cámaras).

Campos creados:
    - GLC_Camaras:  ID_Num (String)
    - GLC_Tuberias: ID_tub (String), Ci_Num (String), Cf_Num (String)

Compatible con QGIS 3.x y 4.x.
"""

from qgis.core import (
    QgsProject, QgsVectorLayer, QgsField, QgsFeature,
    QgsGeometry, QgsWkbTypes,
)
from qgis.PyQt.QtCore import Qt, QVariant
from qgis.PyQt.QtWidgets import (
    QMessageBox, QDialog, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QComboBox, QProgressBar, QGroupBox,
    QRadioButton, QButtonGroup, QListWidget, QListWidgetItem,
    QTextEdit, QAbstractItemView, QScrollArea, QWidget,
    QLineEdit,
)
from qgis.gui import QgsMapToolEmitPoint


# ============================================================
# COMPATIBILIDAD
# ============================================================
try:
    from qgis.PyQt.QtCore import QMetaType
    _USE_QMETATYPE = True
except ImportError:
    _USE_QMETATYPE = False

try:
    _MSG_YES = QMessageBox.StandardButton.Yes
    _MSG_NO = QMessageBox.StandardButton.No
except AttributeError:
    _MSG_YES = QMessageBox.Yes
    _MSG_NO = QMessageBox.No

try:
    _USER_ROLE = int(Qt.UserRole)
except (TypeError, AttributeError):
    _USER_ROLE = 0x0100


def _enum_value(x):
    return getattr(x, 'value', x)


class NumerarSubredes:

    CAMPO_ID_CAMARA = 'ID_O'
    CAMPO_ID_TUBERIA = 'ID_O'
    CAMPO_CI = 'Ci'
    CAMPO_CF = 'Cf'
    CAMPO_CAB_ATA = 'cab_ata'
    CAMPO_FIN = 'fin'

    CAMPO_ID_NUM = 'ID_Num'
    CAMPO_ID_TUB = 'ID_tub'
    CAMPO_CI_NUM = 'Ci_Num'
    CAMPO_CF_NUM = 'Cf_Num'

    # ⭐ Prefijos para distinguir cámaras y tuberías al exportar a Excel
    PREFIJO_CAMARA = 'C'
    PREFIJO_TUBERIA = 'T'

    def __init__(self, iface):
        self.iface = iface
        self.capa_tuberias = None
        self.capa_camaras = None
        self.tool_seleccion = None
        self.modo_mapa = False
        self.dialog = None
        self.lista_rutas = None
        self.rutas_seleccionadas = []

        self.tuberias = {}
        self.camaras = {}

        self.asignacion_camaras = {}
        self.asignacion_tuberias = {}

        self._esperando_clic_subred = False
        self._tuberias_usadas = set()
        self._contador_subredes = 0

        # Pendientes para Ci_Num/Cf_Num
        self._pendientes_ci_cf = {}

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

    @staticmethod
    def _preguntar(parent, titulo, texto):
        try:
            return QMessageBox.question(
                parent, titulo, texto, _MSG_YES | _MSG_NO
            ) == _MSG_YES
        except Exception:
            return False

    @staticmethod
    def _campo(nombre, tipo='string', longitud=0):
        if _USE_QMETATYPE:
            mapa = {
                'string': QMetaType.QString,
                'double': QMetaType.Double,
                'int':    QMetaType.Int,
            }
            return QgsField(nombre, mapa.get(tipo, QMetaType.QString), '', longitud, 0)
        else:
            mapa = {
                'string': QVariant.String,
                'double': QVariant.Double,
                'int':    QVariant.Int,
            }
            return QgsField(nombre, mapa.get(tipo, QVariant.String), tipo, longitud, 0)

    @staticmethod
    def _sin_prefijo(num_str, prefijo):
        """Quita el prefijo (C o T) de un ID_Num o ID_tub."""
        if isinstance(num_str, str) and num_str.startswith(prefijo):
            return num_str[len(prefijo):]
        return num_str

    @staticmethod
    def _max_n_con_prefijo(asignaciones, prefijo, prefijo_id=''):
        """
        Devuelve el máximo N cuyo valor sea <prefijo_id><prefijo>.N...
        Ej: si prefijo_id='C' y prefijo='10', busca 'C10.1', 'C10.2', etc.
        """
        if prefijo_id:
            prefijo_dot = f"{prefijo_id}{prefijo}."
        else:
            prefijo_dot = f"{prefijo}."

        n_max = 0
        for num in asignaciones.values():
            if not isinstance(num, str):
                continue
            if not num.startswith(prefijo_dot):
                continue
            resto = num[len(prefijo_dot):]
            primera = resto.split('.')[0]
            try:
                n = int(primera)
                if n > n_max:
                    n_max = n
            except (ValueError, IndexError):
                pass
        return n_max

    # ============================================================
    # DIÁLOGO
    # ============================================================
    def mostrar_dialogo(self):
        if self.dialog is not None:
            try:
                self.dialog.show()
                self.dialog.raise_()
                self.dialog.activateWindow()
                self._refrescar_lista_rutas()
                return
            except RuntimeError:
                self.dialog = None
                self.lista_rutas = None

        self._desactivar_tool()

        dialog = QDialog(self.iface.mainWindow())
        dialog.setWindowTitle('GLC - Numerar Subredes')
        dialog.setMinimumWidth(620)
        dialog.setMinimumHeight(500)

        try:
            screen = dialog.screen() or self.iface.mainWindow().screen()
            if screen:
                avail = screen.availableGeometry()
                dialog.resize(
                    min(760, int(avail.width() * 0.75)),
                    min(640, int(avail.height() * 0.80))
                )
        except Exception:
            dialog.resize(720, 560)

        self.dialog = dialog

        def _on_key_press(event):
            if event.key() == Qt.Key_Escape:
                if getattr(self, '_esperando_clic_subred', False):
                    self._esperando_clic_subred = False
                    self._desactivar_tool()
                    self._finalizar_segundo_nivel()
                    return
                if self.modo_mapa:
                    self._desactivar_tool()
                    if self.dialog is not None:
                        try:
                            self.dialog.show()
                            self.dialog.raise_()
                            self.dialog.activateWindow()
                            self._refrescar_lista_rutas()
                        except RuntimeError:
                            pass
                else:
                    dialog.reject()
            else:
                QDialog.keyPressEvent(dialog, event)

        dialog.keyPressEvent = _on_key_press

        def _on_finished(result):
            self._desactivar_tool()
            self.dialog = None
            self.lista_rutas = None

        dialog.finished.connect(_on_finished)

        main_layout = QVBoxLayout(dialog)
        main_layout.setContentsMargins(6, 6, 6, 6)
        main_layout.setSpacing(6)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.NoFrame)

        contenido = QWidget()
        layout = QVBoxLayout(contenido)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(8)

        lbl = QLabel('<b>🔢 Numerar Subredes</b>')
        lbl.setStyleSheet('font-size: 13pt; color: #2c3e50;')
        layout.addWidget(lbl)

        desc = QLabel(
            '📌 <b>1er NIVEL</b>: rutas principales → C1, C2, ... / T1, T2, ...\n'
            '📌 <b>2do NIVEL</b>: subredes tributarias → C5.1, C5.2 / T5.1, T5.2\n'
            '📌 <b>RESTANTES</b>: numera lo que falta usando vecinos numerados\n'
            '📌 <b>ACTUALIZAR</b>: refresca Ci_Num/Cf_Num de todas las tuberías\n'
            'ℹ️ Prefijos: C = cámara, T = tubería'
        )
        desc.setWordWrap(True)
        desc.setStyleSheet(
            'background-color: #ecf0f1; padding: 6px; border-radius: 4px; '
            'font-size: 9pt;'
        )
        layout.addWidget(desc)

        # ---- Capas ----
        box_capas = QGroupBox('Capas de trabajo')
        lay_capas = QVBoxLayout()
        lay_capas.setSpacing(4)

        hb_tub = QHBoxLayout()
        lbl_tub = QLabel('Tuberías:')
        lbl_tub.setFixedWidth(70)
        hb_tub.addWidget(lbl_tub)
        self.combo_tuberias = QComboBox()
        self._llenar_combo(self.combo_tuberias, QgsWkbTypes.LineGeometry, 'GLC_Tuberias')
        hb_tub.addWidget(self.combo_tuberias, 1)
        lay_capas.addLayout(hb_tub)

        hb_cam = QHBoxLayout()
        lbl_cam = QLabel('Cámaras:')
        lbl_cam.setFixedWidth(70)
        hb_cam.addWidget(lbl_cam)
        self.combo_camaras = QComboBox()
        self._llenar_combo(self.combo_camaras, QgsWkbTypes.PointGeometry, 'GLC_Camaras')
        hb_cam.addWidget(self.combo_camaras, 1)
        lay_capas.addLayout(hb_cam)

        box_capas.setLayout(lay_capas)
        layout.addWidget(box_capas)

        # ---- Dirección ----
        box_dir = QGroupBox('Dirección (1er nivel)')
        lay_dir = QHBoxLayout()
        lay_dir.setSpacing(12)

        self.radio_asc = QRadioButton('Ascendente (Arranque → Final)')
        self.radio_desc = QRadioButton('Descendente (Final → Arranque)')
        self.radio_asc.setChecked(True)

        grupo = QButtonGroup(dialog)
        grupo.addButton(self.radio_asc)
        grupo.addButton(self.radio_desc)

        lay_dir.addWidget(self.radio_asc)
        lay_dir.addWidget(self.radio_desc)
        lay_dir.addStretch()
        box_dir.setLayout(lay_dir)
        layout.addWidget(box_dir)

        # ---- Selección de rutas ----
        box_sel = QGroupBox('Rutas (por orden de selección)')
        lay_sel = QVBoxLayout()
        lay_sel.setSpacing(4)

        info_sel = QLabel(
            '👉 Haz clic en el mapa sobre CUALQUIER tubería de cada ruta.'
        )
        info_sel.setWordWrap(True)
        info_sel.setStyleSheet('font-size: 9pt; color: #555;')
        lay_sel.addWidget(info_sel)

        hb_btn = QHBoxLayout()
        hb_btn.setSpacing(4)

        btn_activar = QPushButton('🎯 Seleccionar en mapa')
        btn_activar.setStyleSheet(
            'background-color: #2196f3; color: white; font-weight: bold; padding: 4px;'
        )
        btn_activar.clicked.connect(self._activar_modo_mapa)
        hb_btn.addWidget(btn_activar)

        btn_subir = QPushButton('⬆ Subir')
        btn_subir.clicked.connect(self._subir_seleccionada)
        hb_btn.addWidget(btn_subir)

        btn_bajar = QPushButton('⬇ Bajar')
        btn_bajar.clicked.connect(self._bajar_seleccionada)
        hb_btn.addWidget(btn_bajar)

        lay_sel.addLayout(hb_btn)

        hb_btn2 = QHBoxLayout()
        hb_btn2.setSpacing(4)

        btn_quitar = QPushButton('❌ Quitar')
        btn_quitar.clicked.connect(self._quitar_seleccionada)
        hb_btn2.addWidget(btn_quitar)

        btn_limpiar = QPushButton('🧹 Limpiar')
        btn_limpiar.clicked.connect(self._limpiar_lista)
        hb_btn2.addWidget(btn_limpiar)

        lay_sel.addLayout(hb_btn2)

        self.lista_rutas = QListWidget()
        self.lista_rutas.setMinimumHeight(90)
        self.lista_rutas.setMaximumHeight(140)
        try:
            self.lista_rutas.setSelectionMode(
                QAbstractItemView.SelectionMode.ExtendedSelection
            )
        except AttributeError:
            self.lista_rutas.setSelectionMode(
                QAbstractItemView.ExtendedSelection
            )
        lay_sel.addWidget(self.lista_rutas)

        box_sel.setLayout(lay_sel)
        layout.addWidget(box_sel)

        self.progress = QProgressBar()
        self.progress.setMaximumHeight(18)
        layout.addWidget(self.progress)

        lbl_log = QLabel('Registro:')
        lbl_log.setStyleSheet('font-size: 9pt; color: #555;')
        layout.addWidget(lbl_log)

        self.text_log = QTextEdit()
        self.text_log.setReadOnly(True)
        self.text_log.setStyleSheet('font-family: monospace; font-size: 9pt;')
        self.text_log.setMinimumHeight(80)
        self.text_log.setMaximumHeight(120)
        layout.addWidget(self.text_log)

        scroll.setWidget(contenido)
        main_layout.addWidget(scroll, 1)

        # ---- Barra inferior fija ----
        barra_inferior = QHBoxLayout()
        barra_inferior.setSpacing(4)

        btn_ejecutar = QPushButton('🔢 1er NIVEL')
        btn_ejecutar.setToolTip('Numerar rutas principales')
        btn_ejecutar.setStyleSheet(
            'background-color: #4CAF50; color: white; font-weight: bold; '
            'padding: 8px 6px; font-size: 9pt;'
        )
        btn_ejecutar.clicked.connect(self._ejecutar_numeracion)
        barra_inferior.addWidget(btn_ejecutar, 1)

        btn_nivel2 = QPushButton('🔢 2do NIVEL')
        btn_nivel2.setToolTip('Numerar subred tributaria (clic en el mapa)')
        btn_nivel2.setStyleSheet(
            'background-color: #FF9800; color: white; font-weight: bold; '
            'padding: 8px 6px; font-size: 9pt;'
        )
        btn_nivel2.clicked.connect(self._ejecutar_segundo_nivel)
        barra_inferior.addWidget(btn_nivel2, 1)

        btn_restantes = QPushButton('🔢 RESTANTES')
        btn_restantes.setToolTip(
            'Numerar todas las cámaras/tuberías sin número usando los vecinos'
        )
        btn_restantes.setStyleSheet(
            'background-color: #9C27B0; color: white; font-weight: bold; '
            'padding: 8px 6px; font-size: 9pt;'
        )
        btn_restantes.clicked.connect(self._numerar_restantes)
        barra_inferior.addWidget(btn_restantes, 1)

        btn_actualizar = QPushButton('🔄 ACTUALIZAR')
        btn_actualizar.setToolTip('Actualizar Ci_Num y Cf_Num de todas las tuberías')
        btn_actualizar.setStyleSheet(
            'background-color: #2196f3; color: white; font-weight: bold; '
            'padding: 8px 6px; font-size: 9pt;'
        )
        btn_actualizar.clicked.connect(self._actualizar_ci_cf_num)
        barra_inferior.addWidget(btn_actualizar, 1)

        btn_cerrar = QPushButton('Cerrar')
        btn_cerrar.setStyleSheet(
            'background-color: #f44336; color: white; padding: 8px 6px; font-size: 9pt;'
        )
        btn_cerrar.clicked.connect(dialog.reject)
        barra_inferior.addWidget(btn_cerrar)

        main_layout.addLayout(barra_inferior)

        dialog.setLayout(main_layout)

        self._refrescar_lista_rutas()

        dialog.show()

    def _llenar_combo(self, combo, geom_value, nombre_preferido):
        combo.clear()
        preferidos, otros = [], []
        try:
            capas = list(QgsProject.instance().mapLayers().values())
        except Exception:
            capas = []
        for layer in capas:
            if not isinstance(layer, QgsVectorLayer):
                continue
            try:
                if _enum_value(layer.geometryType()) != _enum_value(geom_value):
                    continue
            except Exception:
                continue
            nombre = layer.name() or ''
            (preferidos if nombre_preferido in nombre else otros).append(layer)
        for layer in (preferidos or otros):
            combo.addItem(layer.name(), layer.id())

    def _resolver_capas(self):
        tub_id = self.combo_tuberias.currentData()
        cam_id = self.combo_camaras.currentData()

        self.capa_tuberias = QgsProject.instance().mapLayer(tub_id) if tub_id else None
        self.capa_camaras = QgsProject.instance().mapLayer(cam_id) if cam_id else None

        if not isinstance(self.capa_tuberias, QgsVectorLayer) or \
           not isinstance(self.capa_camaras, QgsVectorLayer):
            self._msg(self.iface.mainWindow(), QMessageBox.Warning, 'Error',
                      'Selecciona capas válidas de tuberías y cámaras')
            return False
        return True

    # ============================================================
    # MODO MAPA (1er nivel)
    # ============================================================
    def _activar_modo_mapa(self):
        if not self._resolver_capas():
            return

        self._desactivar_tool()

        self.tool_seleccion = QgsMapToolEmitPoint(self.iface.mapCanvas())
        self.tool_seleccion.canvasClicked.connect(self._on_canvas_click)
        self.iface.mapCanvas().setMapTool(self.tool_seleccion)
        self.modo_mapa = True

        if self.dialog is not None:
            try:
                self.dialog.hide()
            except RuntimeError:
                self.dialog = None
                self.lista_rutas = None

        try:
            self.iface.statusBarIface().showMessage(
                '🎯 Haz clic sobre CUALQUIER tubería de cada ruta. '
                'Presiona ESC para volver al diálogo.', 8000
            )
        except Exception:
            pass

    def _on_canvas_click(self, point):
        punto_geom = QgsGeometry.fromPointXY(point)

        tolerancia_mapa = 10.0
        try:
            canvas = self.iface.mapCanvas()
            scale = canvas.mapSettings().scale()
            tolerancia_mapa = 10.0 * scale / 1000.0
        except Exception:
            pass

        tuberia_cercana = None
        dist_minima = None

        for feat in self.capa_tuberias.getFeatures():
            geom = feat.geometry()
            if not geom or geom.isEmpty():
                continue
            try:
                dist = geom.distance(punto_geom)
            except Exception:
                continue
            if dist_minima is None or dist < dist_minima:
                dist_minima = dist
                tuberia_cercana = feat

        if tuberia_cercana is None or \
           (dist_minima is not None and dist_minima > tolerancia_mapa):
            try:
                self.iface.statusBarIface().showMessage(
                    '⚠️ No se encontró tubería cerca del clic', 3000
                )
            except Exception:
                pass
            return

        id_o = self._attr(tuberia_cercana, self.CAMPO_ID_TUBERIA)
        ci = self._attr(tuberia_cercana, self.CAMPO_CI)
        cf = self._attr(tuberia_cercana, self.CAMPO_CF)

        for r in self.rutas_seleccionadas:
            if r['id_o'] == id_o:
                try:
                    self.iface.statusBarIface().showMessage(
                        f'⚠️ Tubería ID_O={id_o} ya está en la lista', 3000
                    )
                except Exception:
                    pass
                return

        self.rutas_seleccionadas.append({
            'id_o': id_o,
            'ci': ci,
            'cf': cf,
        })

        try:
            self.iface.statusBarIface().showMessage(
                f'✅ Añadida tubería ID_O={id_o} '
                f'(Ci={ci} → Cf={cf}). Total: {len(self.rutas_seleccionadas)}',
                4000
            )
        except Exception:
            pass

    def _quitar_seleccionada(self):
        if self.lista_rutas is None:
            return
        try:
            indices = sorted(
                [self.lista_rutas.row(it) for it in self.lista_rutas.selectedItems()],
                reverse=True
            )
            for idx in indices:
                if 0 <= idx < len(self.rutas_seleccionadas):
                    self.rutas_seleccionadas.pop(idx)
                self.lista_rutas.takeItem(idx)
            self._refrescar_lista_rutas()
        except RuntimeError:
            self.lista_rutas = None

    def _subir_seleccionada(self):
        if self.lista_rutas is None:
            return
        try:
            items = self.lista_rutas.selectedItems()
            if not items:
                return
            idx = self.lista_rutas.row(items[0])
            if idx <= 0:
                return
            self.rutas_seleccionadas[idx - 1], self.rutas_seleccionadas[idx] = \
                self.rutas_seleccionadas[idx], self.rutas_seleccionadas[idx - 1]
            self._refrescar_lista_rutas()
            try:
                self.lista_rutas.setCurrentRow(idx - 1)
            except Exception:
                pass
        except RuntimeError:
            self.lista_rutas = None

    def _bajar_seleccionada(self):
        if self.lista_rutas is None:
            return
        try:
            items = self.lista_rutas.selectedItems()
            if not items:
                return
            idx = self.lista_rutas.row(items[0])
            if idx >= len(self.rutas_seleccionadas) - 1:
                return
            self.rutas_seleccionadas[idx + 1], self.rutas_seleccionadas[idx] = \
                self.rutas_seleccionadas[idx], self.rutas_seleccionadas[idx + 1]
            self._refrescar_lista_rutas()
            try:
                self.lista_rutas.setCurrentRow(idx + 1)
            except Exception:
                pass
        except RuntimeError:
            self.lista_rutas = None

    def _limpiar_lista(self):
        self.rutas_seleccionadas = []
        self._refrescar_lista_rutas()

    def _refrescar_lista_rutas(self):
        if self.lista_rutas is None:
            return
        try:
            self.lista_rutas.clear()
            for i, r in enumerate(self.rutas_seleccionadas):
                item = QListWidgetItem(
                    f"{i+1}. ID_O={r['id_o']}  (Ci={r['ci']} → Cf={r['cf']})"
                )
                try:
                    item.setData(_USER_ROLE, r['id_o'])
                except Exception:
                    pass
                self.lista_rutas.addItem(item)
        except RuntimeError:
            self.lista_rutas = None

    # ============================================================
    # DICCIONARIOS
    # ============================================================
    def _construir_diccionarios(self):
        self.tuberias = {}
        for feat in self.capa_tuberias.getFeatures():
            id_o = self._attr(feat, self.CAMPO_ID_TUBERIA)
            if id_o is None:
                continue
            self.tuberias[id_o] = {
                'id_o': id_o,
                'ci': self._attr(feat, self.CAMPO_CI),
                'cf': self._attr(feat, self.CAMPO_CF),
                'cab_ata': (self._attr(feat, self.CAMPO_CAB_ATA) or '').strip(),
                'feature': feat,
            }

        self.camaras = {}
        for feat in self.capa_camaras.getFeatures():
            id_o = self._attr(feat, self.CAMPO_ID_CAMARA)
            if id_o is None:
                continue
            fin = self._attr(feat, self.CAMPO_FIN)
            es_final = (fin == 1) or (str(fin).strip() == '1')
            self.camaras[id_o] = {
                'id_o': id_o,
                'es_final': es_final,
                'feature': feat,
                'tuberias_que_llegan': [],
                'tuberias_que_salen': [],
            }

        for id_t, t in self.tuberias.items():
            ci = t['ci']
            cf = t['cf']
            if ci in self.camaras:
                self.camaras[ci]['tuberias_que_salen'].append(id_t)
            if cf in self.camaras:
                self.camaras[cf]['tuberias_que_llegan'].append(id_t)

    # ============================================================
    # RASTREO BIDIRECCIONAL (1er nivel)
    # ============================================================
    def _rastrear_ruta_completa(self, id_tuberia_inicial):
        if id_tuberia_inicial not in self.tuberias:
            return None

        hacia_atras = [id_tuberia_inicial]
        actual = id_tuberia_inicial
        visitados_atras = {id_tuberia_inicial}

        for _ in range(10000):
            t = self.tuberias.get(actual)
            if t is None:
                break

            if t['cab_ata'] == 'Arranque':
                break

            ci = t['ci']
            if ci is None or ci not in self.camaras:
                break

            camara_ci = self.camaras[ci]

            continuacion = None
            for id_t in camara_ci['tuberias_que_llegan']:
                if id_t in visitados_atras:
                    continue
                t_ent = self.tuberias.get(id_t)
                if t_ent is None:
                    continue
                if t_ent['cab_ata'] != 'Arranque':
                    continuacion = id_t
                    break

            if continuacion is not None:
                hacia_atras.append(continuacion)
                visitados_atras.add(continuacion)
                actual = continuacion
                continue

            arranque = None
            for id_t in camara_ci['tuberias_que_salen']:
                if id_t in visitados_atras:
                    continue
                t_arr = self.tuberias.get(id_t)
                if t_arr is None:
                    continue
                if t_arr['cab_ata'] == 'Arranque':
                    arranque = id_t
                    break

            if arranque is not None:
                hacia_atras.append(arranque)
                visitados_atras.add(arranque)
                break

            break

        hacia_atras.reverse()

        hacia_adelante = []
        actual = id_tuberia_inicial
        visitados_adelante = {id_tuberia_inicial}

        for _ in range(10000):
            t = self.tuberias.get(actual)
            if t is None:
                break

            cf = t['cf']
            if cf is None or cf not in self.camaras:
                break

            camara_cf = self.camaras[cf]

            if camara_cf['es_final']:
                break

            siguiente = None
            for id_t in camara_cf['tuberias_que_salen']:
                if id_t in visitados_adelante:
                    continue
                t_sal = self.tuberias.get(id_t)
                if t_sal is None:
                    continue
                if t_sal['cab_ata'] != 'Arranque':
                    siguiente = id_t
                    break

            if siguiente is None:
                break

            hacia_adelante.append(siguiente)
            visitados_adelante.add(siguiente)
            actual = siguiente

        ruta_completa = hacia_atras + hacia_adelante
        return ruta_completa

    def _camaras_de_ruta(self, ruta_tuberias):
        if not ruta_tuberias:
            return []
        camaras = []
        t1 = self.tuberias.get(ruta_tuberias[0])
        if t1 is None:
            return []
        camaras.append(t1['ci'])
        for id_t in ruta_tuberias:
            t = self.tuberias.get(id_t)
            if t is None:
                continue
            camaras.append(t['cf'])
        return camaras

    # ============================================================
    # 1er NIVEL
    # ============================================================
    def _ejecutar_numeracion(self):
        if not self._resolver_capas():
            return

        if not self.rutas_seleccionadas:
            self._msg(self.iface.mainWindow(), QMessageBox.Warning,
                      'Sin rutas',
                      'Debes seleccionar al menos una tubería.')
            return

        if not self._preguntar(
            self.iface.mainWindow(),
            'Confirmar numeración 1er nivel',
            f'Se van a numerar {len(self.rutas_seleccionadas)} ruta(s) '
            f'en orden de selección.\n\n'
            f'📌 Numeración cámaras: C1, C2, C3, ...\n'
            f'📌 Numeración tuberías: T1, T2, T3, ...\n'
            f'📌 Cámaras y tuberías se numeran por separado.\n\n'
            f'⚠️ Los valores previos serán SOBREESCRITOS.\n'
            f'⚠️ Al terminar, la lista de rutas se vaciará.\n\n'
            f'¿Continuar?'
        ):
            return

        if self.text_log is not None:
            try:
                self.text_log.clear()
            except RuntimeError:
                pass
        if self.progress is not None:
            try:
                self.progress.setValue(0)
            except RuntimeError:
                pass

        ascendente = self.radio_asc.isChecked()

        self._construir_diccionarios()

        def _log(msg):
            if self.text_log is not None:
                try:
                    self.text_log.append(msg)
                except RuntimeError:
                    pass

        _log(f"📊 Tuberías: {len(self.tuberias)}  |  Cámaras: {len(self.camaras)}")

        self._crear_campos()

        self.asignacion_camaras = {}
        self.asignacion_tuberias = {}

        camaras_ya_numeradas = set()
        tuberias_ya_numeradas = set()

        contador_camaras = 0
        contador_tuberias = 0

        for idx_ruta, ruta_info in enumerate(self.rutas_seleccionadas):
            id_t_inicial = ruta_info['id_o']

            ruta = self._rastrear_ruta_completa(id_t_inicial)
            if not ruta:
                _log(
                    f"\n⚠️ Ruta #{idx_ruta + 1}: no se pudo rastrear "
                    f"(ID_O={id_t_inicial})"
                )
                continue

            camaras_ruta = self._camaras_de_ruta(ruta)

            _log(
                f"\n🎯 RUTA #{idx_ruta + 1} (tubería inicial ID_O={id_t_inicial})"
            )
            _log(
                f"   Tuberías ({len(ruta)}): {' → '.join(str(x) for x in ruta)}"
            )
            _log(
                f"   Cámaras ({len(camaras_ruta)}): "
                f"{' → '.join(str(x) for x in camaras_ruta)}"
            )

            camaras_a_numerar = list(camaras_ruta)
            if not ascendente:
                camaras_a_numerar = list(reversed(camaras_a_numerar))

            camaras_nuevas = 0
            for id_c in camaras_a_numerar:
                if id_c in camaras_ya_numeradas:
                    continue
                contador_camaras += 1
                id_num_asignado = f"{self.PREFIJO_CAMARA}{contador_camaras}"
                self.asignacion_camaras[id_c] = id_num_asignado
                self._pendientes_ci_cf[id_c] = id_num_asignado
                camaras_ya_numeradas.add(id_c)
                camaras_nuevas += 1

            tuberias_a_numerar = list(ruta)
            if not ascendente:
                tuberias_a_numerar = list(reversed(tuberias_a_numerar))

            tuberias_nuevas = 0
            for id_t in tuberias_a_numerar:
                if id_t in tuberias_ya_numeradas:
                    continue
                contador_tuberias += 1
                self.asignacion_tuberias[id_t] = \
                    f"{self.PREFIJO_TUBERIA}{contador_tuberias}"
                tuberias_ya_numeradas.add(id_t)
                tuberias_nuevas += 1

            _log(
                f"   ✅ Cámaras nuevas: {camaras_nuevas}  |  "
                f"Tuberías nuevas: {tuberias_nuevas}"
            )

        if self.progress is not None:
            try:
                self.progress.setValue(80)
            except RuntimeError:
                pass

        _log(f"\n💾 Guardando en las capas...")
        self._aplicar_a_capas()

        aplicadas = self._aplicar_pendientes_ci_cf()
        _log(f"   Ci_Num/Cf_Num actualizados en {aplicadas} tuberías")

        if self.progress is not None:
            try:
                self.progress.setValue(100)
            except RuntimeError:
                pass

        _log(f"\n{'='*60}")
        _log(f"✅ NUMERACIÓN 1er NIVEL COMPLETADA")
        _log(f"{'='*60}")
        _log(f"📌 Cámaras numeradas: {len(self.asignacion_camaras)}")
        _log(f"📌 Tuberías numeradas: {len(self.asignacion_tuberias)}")

        self._msg(self.iface.mainWindow(), QMessageBox.Information,
                  '1er nivel completado',
                  f'✅ Completado\n\n'
                  f'📌 Cámaras numeradas: {len(self.asignacion_camaras)}\n'
                  f'📌 Tuberías numeradas: {len(self.asignacion_tuberias)}\n'
                  f'📌 Ci_Num/Cf_Num actualizados: {aplicadas}\n'
                  f'📌 Rango cámaras: C1 ... C{contador_camaras}\n'
                  f'📌 Rango tuberías: T1 ... T{contador_tuberias}\n\n'
                  f'Ahora pulsa "2do NIVEL" o "RESTANTES".')

        self.rutas_seleccionadas = []
        self._refrescar_lista_rutas()

    # ============================================================
    # 2do NIVEL
    # ============================================================
    def _ejecutar_segundo_nivel(self):
        if not self._resolver_capas():
            return

        if not self._preguntar(
            self.iface.mainWindow(),
            'Numerar 2do nivel',
            'Vas a numerar subredes tributarias manualmente.\n\n'
            '📌 En cada paso:\n'
            '   1. Haz clic sobre cualquier tubería de la subred.\n'
            '   2. El módulo detecta la cámara principal REAL.\n'
            '   3. Se numera la subred con Ck.N / Tk.N ÚNICO.\n\n'
            '📌 Presiona ESC durante el clic para terminar.\n\n'
            '¿Continuar?'
        ):
            return

        if self.text_log is not None:
            try:
                self.text_log.clear()
            except RuntimeError:
                pass

        def _log(msg):
            if self.text_log is not None:
                try:
                    self.text_log.append(msg)
                except RuntimeError:
                    pass

        self._construir_diccionarios()
        _log(f"📊 Tuberías: {len(self.tuberias)}  |  Cámaras: {len(self.camaras)}")

        self._crear_campos()

        self._releer_asignaciones_desde_capas()

        if not self.asignacion_camaras:
            self._msg(self.iface.mainWindow(), QMessageBox.Warning,
                      'Sin numeración previa',
                      'Primero ejecuta la numeración del 1er nivel.')
            return

        self._contador_subredes = 0

        if self.dialog is not None:
            try:
                self.dialog.hide()
            except RuntimeError:
                pass

        self._iniciar_seleccion_subred()

    def _releer_asignaciones_desde_capas(self):
        self.asignacion_camaras = {}
        self.asignacion_tuberias = {}

        idx_id_num = self._idx(self.capa_camaras, self.CAMPO_ID_NUM)
        if idx_id_num != -1:
            for feat in self.capa_camaras.getFeatures():
                id_o = self._attr(feat, self.CAMPO_ID_CAMARA)
                num = self._attr(feat, self.CAMPO_ID_NUM)
                if id_o is not None and num:
                    self.asignacion_camaras[id_o] = str(num)

        idx_id_tub = self._idx(self.capa_tuberias, self.CAMPO_ID_TUB)
        if idx_id_tub != -1:
            for feat in self.capa_tuberias.getFeatures():
                id_o = self._attr(feat, self.CAMPO_ID_TUBERIA)
                num = self._attr(feat, self.CAMPO_ID_TUB)
                if id_o is not None and num:
                    self.asignacion_tuberias[id_o] = str(num)

        self._tuberias_usadas = set(self.asignacion_tuberias.keys())

    def _iniciar_seleccion_subred(self):
        self._desactivar_tool()

        self._esperando_clic_subred = True

        self.tool_seleccion = QgsMapToolEmitPoint(self.iface.mapCanvas())
        self.tool_seleccion.canvasClicked.connect(self._on_click_subred)
        self.iface.mapCanvas().setMapTool(self.tool_seleccion)
        self.modo_mapa = True

        try:
            self.iface.statusBarIface().showMessage(
                '🎯 Haz clic sobre CUALQUIER tubería de la subred a numerar. '
                'Presiona ESC para terminar.', 15000
            )
        except Exception:
            pass

    def _on_click_subred(self, point):
        if not getattr(self, '_esperando_clic_subred', False):
            return

        punto_geom = QgsGeometry.fromPointXY(point)

        tolerancia_mapa = 10.0
        try:
            scale = self.iface.mapCanvas().mapSettings().scale()
            tolerancia_mapa = 10.0 * scale / 1000.0
        except Exception:
            pass

        tuberia_cercana = None
        dist_minima = None

        for feat in self.capa_tuberias.getFeatures():
            geom = feat.geometry()
            if not geom or geom.isEmpty():
                continue
            try:
                dist = geom.distance(punto_geom)
            except Exception:
                continue
            if dist_minima is None or dist < dist_minima:
                dist_minima = dist
                tuberia_cercana = feat

        if tuberia_cercana is None or \
           (dist_minima is not None and dist_minima > tolerancia_mapa):
            try:
                self.iface.statusBarIface().showMessage(
                    '⚠️ No se encontró tubería cerca del clic. Intenta de nuevo.', 3000
                )
            except Exception:
                pass
            return

        self._esperando_clic_subred = False
        id_t_inicial = self._attr(tuberia_cercana, self.CAMPO_ID_TUBERIA)

        self._desactivar_tool()

        self._procesar_subred_capturada(id_t_inicial)

    def _detectar_y_rastrear_subred(self, id_tuberia_inicial):
        if id_tuberia_inicial not in self.tuberias:
            return None, None, None

        id_c_principal = None
        id_num_principal = None
        tuberias_hacia_adelante = []

        t_actual = self.tuberias.get(id_tuberia_inicial)
        if t_actual is None:
            return None, None, None

        id_c_actual = t_actual['cf']
        visitados_adelante = {id_tuberia_inicial}

        for _ in range(10000):
            if id_c_actual is None:
                break

            num = self.asignacion_camaras.get(id_c_actual, '')
            # ⭐ Limpiar prefijo C
            num_puro = self._sin_prefijo(num, self.PREFIJO_CAMARA)

            if num_puro and '.' not in num_puro:
                id_c_principal = id_c_actual
                id_num_principal = num_puro
                break

            if num_puro and '.' in num_puro:
                partes = num_puro.split('.')
                if partes and partes[0]:
                    id_c_principal = id_c_actual
                    id_num_principal = partes[0]
                    break
                break

            camara_data = self.camaras.get(id_c_actual)
            if camara_data is None:
                break

            siguiente = None
            for id_t in camara_data['tuberias_que_salen']:
                if id_t in visitados_adelante:
                    continue
                t_sal = self.tuberias.get(id_t)
                if t_sal is None:
                    continue
                if t_sal['cab_ata'] != 'Arranque':
                    siguiente = id_t
                    break

            if siguiente is None:
                break

            tuberias_hacia_adelante.append(siguiente)
            visitados_adelante.add(siguiente)
            t_sal = self.tuberias.get(siguiente)
            if t_sal is None:
                break
            id_c_actual = t_sal['cf']

        if id_c_principal is None:
            return None, None, None

        tuberias_hacia_atras = []
        actual = id_tuberia_inicial
        visitados_atras = {id_tuberia_inicial}

        for _ in range(10000):
            t = self.tuberias.get(actual)
            if t is None:
                break

            if t['cab_ata'] == 'Arranque':
                break

            ci = t['ci']
            if ci is None or ci not in self.camaras:
                break

            if ci == id_c_principal:
                break

            num_ci = self.asignacion_camaras.get(ci, '')
            if num_ci:
                break

            camara_ci = self.camaras[ci]

            continuacion = None
            for id_t in camara_ci['tuberias_que_llegan']:
                if id_t in visitados_atras:
                    continue
                t_ent = self.tuberias.get(id_t)
                if t_ent is None:
                    continue
                if t_ent['cab_ata'] != 'Arranque':
                    continuacion = id_t
                    break

            if continuacion is not None:
                tuberias_hacia_atras.append(continuacion)
                visitados_atras.add(continuacion)
                actual = continuacion
                continue

            arranque = None
            for id_t in camara_ci['tuberias_que_salen']:
                if id_t in visitados_atras:
                    continue
                t_arr = self.tuberias.get(id_t)
                if t_arr is None:
                    continue
                if t_arr['cab_ata'] == 'Arranque':
                    arranque = id_t
                    break

            if arranque is not None:
                tuberias_hacia_atras.append(arranque)
                visitados_atras.add(arranque)
                break

            break

        tuberias_hacia_atras.reverse()

        ruta_sub = tuberias_hacia_atras + [id_tuberia_inicial] + tuberias_hacia_adelante
        return ruta_sub, id_c_principal, id_num_principal

    def _procesar_subred_capturada(self, id_t_inicial):
        def _log(msg):
            if self.text_log is not None:
                try:
                    self.text_log.append(msg)
                except RuntimeError:
                    pass

        self._releer_asignaciones_desde_capas()

        if id_t_inicial not in self.tuberias:
            self._msg(self.iface.mainWindow(), QMessageBox.Warning,
                      'Error', f'Tubería ID_O={id_t_inicial} no encontrada')
            self._preguntar_continuar_subredes()
            return

        ruta_sub, id_c_principal, id_num_principal = \
            self._detectar_y_rastrear_subred(id_t_inicial)

        _log(f"\n🔍 Subred desde ID_O={id_t_inicial}")
        if ruta_sub:
            _log(f"   Ruta: {' → '.join(str(x) for x in ruta_sub)}")

        if id_c_principal is None or ruta_sub is None:
            t_ini = self.tuberias.get(id_t_inicial)
            if t_ini:
                cf_ini = t_ini['cf']
                num_cf_ini = self.asignacion_camaras.get(cf_ini, '(vacío)')
                _log(f"   Diagnóstico:")
                _log(f"   • Cf inicial: {cf_ini}")
                _log(f"   • ID_Num de Cf: '{num_cf_ini}'")
                _log(f"   • cab_ata: '{t_ini['cab_ata']}'")

            self._msg(self.iface.mainWindow(), QMessageBox.Warning,
                      'No se pudo detectar',
                      'No se pudo detectar la cámara principal.\n\n'
                      'Revisa el registro para más detalle.')
            self._preguntar_continuar_subredes()
            return

        _log(f"   Cámara principal: ID_O={id_c_principal} → "
             f"ID_Num={self.PREFIJO_CAMARA}{id_num_principal}")

        ruta_nueva = []
        for id_t in ruta_sub:
            if id_t in self._tuberias_usadas:
                continue
            ruta_nueva.append(id_t)

        if not ruta_nueva:
            self._msg(self.iface.mainWindow(), QMessageBox.Information,
                      'Sin tramos nuevos',
                      f'La subred ya está numerada.')
            self._preguntar_continuar_subredes()
            return

        camaras_sub = self._camaras_de_ruta(ruta_nueva)
        camaras_nuevas = [
            c for c in camaras_sub
            if c not in self.asignacion_camaras
            and c != id_c_principal
        ]

        # ---- Contadores INDEPENDIENTES (con prefijo) ----
        n_max_camaras = self._max_n_con_prefijo(
            self.asignacion_camaras, id_num_principal, self.PREFIJO_CAMARA
        )
        n_max_tuberias = self._max_n_con_prefijo(
            self.asignacion_tuberias, id_num_principal, self.PREFIJO_TUBERIA
        )

        contador_n_camaras = n_max_camaras
        contador_n_tuberias = n_max_tuberias

        _log(f"   Prefijo: {self.PREFIJO_CAMARA}{id_num_principal}. y "
             f"{self.PREFIJO_TUBERIA}{id_num_principal}.")
        _log(f"   N máx cámaras: {n_max_camaras} | N máx tuberías: {n_max_tuberias}")

        # Cámaras: contador propio
        for id_c_sub in camaras_nuevas:
            contador_n_camaras += 1
            id_num_asignado = \
                f"{self.PREFIJO_CAMARA}{id_num_principal}.{contador_n_camaras}"
            self.asignacion_camaras[id_c_sub] = id_num_asignado
            self._pendientes_ci_cf[id_c_sub] = id_num_asignado

        # Tuberías: contador propio
        tuberias_nuevas = 0
        for id_t_sub in ruta_nueva:
            if id_t_sub in self._tuberias_usadas:
                continue
            contador_n_tuberias += 1
            self.asignacion_tuberias[id_t_sub] = \
                f"{self.PREFIJO_TUBERIA}{id_num_principal}.{contador_n_tuberias}"
            self._tuberias_usadas.add(id_t_sub)
            tuberias_nuevas += 1

        _log(f"   ✅ Cámaras nuevas: {len(camaras_nuevas)} "
             f"(N:{n_max_camaras}→{contador_n_camaras})")
        _log(f"   ✅ Tuberías nuevas: {tuberias_nuevas} "
             f"(N:{n_max_tuberias}→{contador_n_tuberias})")

        self._aplicar_a_capas()
        self._contador_subredes += 1

        try:
            self.iface.statusBarIface().showMessage(
                f'✅ Subred C{id_num_principal}.* / T{id_num_principal}.* asignada. '
                f'({len(camaras_nuevas)} cámaras, {tuberias_nuevas} tuberías)',
                5000
            )
        except Exception:
            pass

        self._preguntar_continuar_subredes()

    def _preguntar_continuar_subredes(self):
        if self._preguntar(
            self.iface.mainWindow(),
            '¿Otra subred?',
            f'✅ Subredes asignadas hasta ahora: {self._contador_subredes}\n\n'
            f'¿Quieres numerar otra subred?\n\n'
            f'(Si pulsas Sí, se ocultará el diálogo y podrás hacer otro clic)'
        ):
            if self.dialog is not None:
                try:
                    self.dialog.hide()
                except RuntimeError:
                    pass
            self._iniciar_seleccion_subred()
        else:
            self._finalizar_segundo_nivel()

    def _finalizar_segundo_nivel(self):
        aplicadas = self._aplicar_pendientes_ci_cf()

        if self.dialog is not None:
            try:
                self.dialog.show()
                self.dialog.raise_()
                self.dialog.activateWindow()
            except RuntimeError:
                pass

        self._msg(self.iface.mainWindow(), QMessageBox.Information,
                  '2do nivel completado',
                  f'✅ Completado\n\n'
                  f'📌 Subredes asignadas: {self._contador_subredes}\n'
                  f'📌 Cámaras totales: {len(self.asignacion_camaras)}\n'
                  f'📌 Tuberías totales: {len(self.asignacion_tuberias)}\n'
                  f'📌 Ci_Num/Cf_Num actualizados: {aplicadas} tuberías')

    # ============================================================
    # NUMERAR RESTANTES
    # ============================================================
    def _numerar_restantes(self):
        if not self._resolver_capas():
            return

        if not self._preguntar(
            self.iface.mainWindow(),
            'Numerar restantes',
            'Se van a numerar TODAS las cámaras y tuberías sin número\n'
            'usando los vecinos ya numerados como referencia.\n\n'
            '📌 Cámaras: reciben C<ID_Num_vecino>.<N>\n'
            '📌 Tuberías: reciben T<ID_Num_cámara_adyacente>.<N>\n'
            '📌 Se ejecuta en olas hasta agotar todas las posibilidades.\n\n'
            '⚠️ Las cámaras sin camino a ningún vecino numerado quedarán sin número.\n\n'
            '¿Continuar?'
        ):
            return

        if self.text_log is not None:
            try:
                self.text_log.clear()
            except RuntimeError:
                pass

        def _log(msg):
            if self.text_log is not None:
                try:
                    self.text_log.append(msg)
                except RuntimeError:
                    pass

        self._construir_diccionarios()
        self._crear_campos()
        self._releer_asignaciones_desde_capas()

        _log(f"📊 Tuberías: {len(self.tuberias)}  |  Cámaras: {len(self.camaras)}")
        _log(f"🔎 Cámaras ya numeradas: {len(self.asignacion_camaras)}")
        _log(f"🔎 Tuberías ya numeradas: {len(self.asignacion_tuberias)}")

        contador_camaras = self._numerar_camaras_en_olas(_log)
        _log(f"\n✅ Cámaras numeradas en esta pasada: {contador_camaras}")
        self._aplicar_a_capas()

        self._releer_asignaciones_desde_capas()
        contador_tuberias = self._numerar_tuberias_en_olas(_log)
        _log(f"\n✅ Tuberías numeradas en esta pasada: {contador_tuberias}")
        self._aplicar_a_capas()

        aplicadas = self._aplicar_pendientes_ci_cf()
        _log(f"💾 Ci_Num/Cf_Num actualizados en {aplicadas} tuberías")

        camaras_sin = sum(
            1 for id_c in self.camaras
            if id_c not in self.asignacion_camaras
        )
        tuberias_sin = sum(
            1 for id_t in self.tuberias
            if id_t not in self.asignacion_tuberias
        )

        _log(f"\n{'='*60}")
        _log(f"✅ NUMERACIÓN DE RESTANTES COMPLETADA")
        _log(f"{'='*60}")
        _log(f"📌 Cámaras totales: {len(self.asignacion_camaras)}")
        _log(f"📌 Cámaras SIN número: {camaras_sin}")
        _log(f"📌 Tuberías totales: {len(self.asignacion_tuberias)}")
        _log(f"📌 Tuberías SIN número: {tuberias_sin}")

        self._msg(self.iface.mainWindow(), QMessageBox.Information,
                  'Restantes numeradas',
                  f'✅ Completado\n\n'
                  f'📌 Cámaras numeradas en esta pasada: {contador_camaras}\n'
                  f'📌 Tuberías numeradas en esta pasada: {contador_tuberias}\n\n'
                  f'📌 Cámaras sin número: {camaras_sin}\n'
                  f'📌 Tuberías sin número: {tuberias_sin}\n\n'
                  f'(Las sin número no tienen camino a ningún vecino numerado)')

    def _numerar_camaras_en_olas(self, _log):
        contador_total = 0

        for ola in range(100):
            candidatas = []

            for id_c in self.camaras:
                if id_c in self.asignacion_camaras:
                    continue

                vecinas_numeradas = []
                cam_data = self.camaras[id_c]

                for id_t in cam_data['tuberias_que_llegan']:
                    t = self.tuberias.get(id_t)
                    if t is None:
                        continue
                    ci = t['ci']
                    num_ci = self.asignacion_camaras.get(ci, '')
                    num_puro = self._sin_prefijo(num_ci, self.PREFIJO_CAMARA)
                    if num_puro and '.' not in num_puro:
                        vecinas_numeradas.append(num_puro)
                    elif num_puro:
                        vecinas_numeradas.append(num_puro.split('.')[0])

                for id_t in cam_data['tuberias_que_salen']:
                    t = self.tuberias.get(id_t)
                    if t is None:
                        continue
                    cf = t['cf']
                    num_cf = self.asignacion_camaras.get(cf, '')
                    num_puro = self._sin_prefijo(num_cf, self.PREFIJO_CAMARA)
                    if num_puro and '.' not in num_puro:
                        vecinas_numeradas.append(num_puro)
                    elif num_puro:
                        vecinas_numeradas.append(num_puro.split('.')[0])

                if vecinas_numeradas:
                    try:
                        prefijo = str(min(int(p) for p in vecinas_numeradas))
                    except Exception:
                        prefijo = vecinas_numeradas[0]
                    candidatas.append((id_c, prefijo))

            if not candidatas:
                break

            _log(f"\n🌊 Ola {ola + 1}: {len(candidatas)} cámaras")

            for id_c, prefijo in candidatas:
                # Contador SOLO entre cámaras (con prefijo C)
                n_max = self._max_n_con_prefijo(
                    self.asignacion_camaras, prefijo, self.PREFIJO_CAMARA
                )
                n_siguiente = n_max + 1
                etiqueta = f"{self.PREFIJO_CAMARA}{prefijo}.{n_siguiente}"
                self.asignacion_camaras[id_c] = etiqueta
                self._pendientes_ci_cf[id_c] = etiqueta
                contador_total += 1

        return contador_total

    def _numerar_tuberias_en_olas(self, _log):
        contador_total = 0

        for ola in range(100):
            candidatas = []

            for id_t, t in self.tuberias.items():
                if id_t in self.asignacion_tuberias:
                    continue

                ci = t['ci']
                cf = t['cf']

                num_ci = self.asignacion_camaras.get(ci, '')
                num_cf = self.asignacion_camaras.get(cf, '')

                candidatos = []
                if num_ci:
                    num_puro = self._sin_prefijo(num_ci, self.PREFIJO_CAMARA)
                    if num_puro and '.' not in num_puro:
                        candidatos.append(num_puro)
                    elif num_puro:
                        candidatos.append(num_puro.split('.')[0])
                if num_cf:
                    num_puro = self._sin_prefijo(num_cf, self.PREFIJO_CAMARA)
                    if num_puro and '.' not in num_puro:
                        candidatos.append(num_puro)
                    elif num_puro:
                        candidatos.append(num_puro.split('.')[0])

                if candidatos:
                    try:
                        prefijo = str(min(int(p) for p in candidatos))
                    except Exception:
                        prefijo = candidatos[0]
                    candidatas.append((id_t, prefijo))

            if not candidatas:
                break

            _log(f"\n🌊 Ola {ola + 1} (tuberías): {len(candidatas)}")

            for id_t, prefijo in candidatas:
                # Contador SOLO entre tuberías (con prefijo T)
                n_max = self._max_n_con_prefijo(
                    self.asignacion_tuberias, prefijo, self.PREFIJO_TUBERIA
                )
                n_siguiente = n_max + 1
                self.asignacion_tuberias[id_t] = \
                    f"{self.PREFIJO_TUBERIA}{prefijo}.{n_siguiente}"
                self._tuberias_usadas.add(id_t)
                contador_total += 1

        return contador_total

    # ============================================================
    # APLICAR PENDIENTES DE Ci_Num/Cf_Num
    # ============================================================
    def _aplicar_pendientes_ci_cf(self):
        if not self._pendientes_ci_cf:
            return 0

        idx_ci_num = self._idx(self.capa_tuberias, self.CAMPO_CI_NUM)
        idx_cf_num = self._idx(self.capa_tuberias, self.CAMPO_CF_NUM)
        if idx_ci_num == -1 or idx_cf_num == -1:
            return 0

        aplicadas = 0
        self.capa_tuberias.startEditing()
        for feat in self.capa_tuberias.getFeatures():
            ci = self._attr(feat, self.CAMPO_CI)
            cf = self._attr(feat, self.CAMPO_CF)

            if ci in self._pendientes_ci_cf:
                self.capa_tuberias.changeAttributeValue(
                    feat.id(), idx_ci_num, self._pendientes_ci_cf[ci]
                )
                aplicadas += 1
            if cf in self._pendientes_ci_cf:
                self.capa_tuberias.changeAttributeValue(
                    feat.id(), idx_cf_num, self._pendientes_ci_cf[cf]
                )
        self.capa_tuberias.commitChanges()

        self._pendientes_ci_cf = {}
        return aplicadas

    # ============================================================
    # ACTUALIZAR Ci_Num Y Cf_Num (BOTÓN)
    # ============================================================
    def _actualizar_ci_cf_num(self):
        if not self._resolver_capas():
            return

        self._crear_campos()

        idx_ci_num = self._idx(self.capa_tuberias, self.CAMPO_CI_NUM)
        idx_cf_num = self._idx(self.capa_tuberias, self.CAMPO_CF_NUM)
        if idx_ci_num == -1 or idx_cf_num == -1:
            self._msg(self.iface.mainWindow(), QMessageBox.Warning,
                      'Error',
                      'No se pudieron crear los campos Ci_Num y/o Cf_Num.')
            return

        if not self._preguntar(
            self.iface.mainWindow(),
            'Actualizar Ci_Num y Cf_Num',
            'Se van a actualizar los campos Ci_Num y Cf_Num de TODAS las '
            'tuberías a partir de los ID_Num actuales de las cámaras.\n\n'
            '📌 Recorre la capa UNA SOLA VEZ (muy rápido).\n\n'
            '¿Continuar?'
        ):
            return

        mapa_num_camaras = {}
        idx_id_num = self._idx(self.capa_camaras, self.CAMPO_ID_NUM)
        if idx_id_num != -1:
            for feat in self.capa_camaras.getFeatures():
                id_o = self._attr(feat, self.CAMPO_ID_CAMARA)
                num = self._attr(feat, self.CAMPO_ID_NUM)
                if id_o is not None:
                    mapa_num_camaras[id_o] = str(num) if num else ''

        self.capa_tuberias.startEditing()
        actualizadas = 0
        for feat in self.capa_tuberias.getFeatures():
            ci = self._attr(feat, self.CAMPO_CI)
            cf = self._attr(feat, self.CAMPO_CF)

            ci_num = mapa_num_camaras.get(ci, '') if ci is not None else ''
            cf_num = mapa_num_camaras.get(cf, '') if cf is not None else ''

            self.capa_tuberias.changeAttributeValue(
                feat.id(), idx_ci_num, ci_num
            )
            self.capa_tuberias.changeAttributeValue(
                feat.id(), idx_cf_num, cf_num
            )
            actualizadas += 1

        self.capa_tuberias.commitChanges()

        try:
            self.iface.mapCanvas().refresh()
        except Exception:
            pass

        self._msg(self.iface.mainWindow(), QMessageBox.Information,
                  'Actualización completada',
                  f'✅ Ci_Num y Cf_Num actualizados.\n\n'
                  f'📌 Tuberías procesadas: {actualizadas}')

    # ============================================================
    # CREAR CAMPOS
    # ============================================================
    def _crear_campos(self):
        if self._idx(self.capa_camaras, self.CAMPO_ID_NUM) == -1:
            self.capa_camaras.dataProvider().addAttributes(
                [self._campo(self.CAMPO_ID_NUM, 'string', 50)]
            )
            self.capa_camaras.updateFields()

        if self._idx(self.capa_tuberias, self.CAMPO_ID_TUB) == -1:
            self.capa_tuberias.dataProvider().addAttributes(
                [self._campo(self.CAMPO_ID_TUB, 'string', 50)]
            )
            self.capa_tuberias.updateFields()

        if self._idx(self.capa_tuberias, self.CAMPO_CI_NUM) == -1:
            self.capa_tuberias.dataProvider().addAttributes(
                [self._campo(self.CAMPO_CI_NUM, 'string', 50)]
            )
            self.capa_tuberias.updateFields()

        if self._idx(self.capa_tuberias, self.CAMPO_CF_NUM) == -1:
            self.capa_tuberias.dataProvider().addAttributes(
                [self._campo(self.CAMPO_CF_NUM, 'string', 50)]
            )
            self.capa_tuberias.updateFields()

    # ============================================================
    # APLICAR A CAPAS
    # ============================================================
    def _aplicar_a_capas(self):
        idx_id_num = self._idx(self.capa_camaras, self.CAMPO_ID_NUM)
        if idx_id_num != -1:
            self.capa_camaras.startEditing()
            for feat in self.capa_camaras.getFeatures():
                id_o = self._attr(feat, self.CAMPO_ID_CAMARA)
                if id_o is None:
                    continue
                nuevo_num = self.asignacion_camaras.get(id_o, '')
                self.capa_camaras.changeAttributeValue(
                    feat.id(), idx_id_num, nuevo_num
                )
            self.capa_camaras.commitChanges()

        idx_id_tub = self._idx(self.capa_tuberias, self.CAMPO_ID_TUB)
        if idx_id_tub != -1:
            self.capa_tuberias.startEditing()
            for feat in self.capa_tuberias.getFeatures():
                id_o = self._attr(feat, self.CAMPO_ID_TUBERIA)
                if id_o is None:
                    continue
                nuevo_tub = self.asignacion_tuberias.get(id_o, '')
                self.capa_tuberias.changeAttributeValue(
                    feat.id(), idx_id_tub, nuevo_tub
                )
            self.capa_tuberias.commitChanges()

        try:
            self.iface.mapCanvas().refresh()
        except Exception:
            pass

    # ============================================================
    # DESACTIVAR
    # ============================================================
    def _desactivar_tool(self):
        if self.tool_seleccion:
            try:
                self.iface.mapCanvas().unsetMapTool(self.tool_seleccion)
            except Exception:
                pass
            self.tool_seleccion = None
        self.modo_mapa = False
        try:
            self.iface.mapCanvas().setCursor(Qt.ArrowCursor)
        except Exception:
            pass

    def desactivar(self, mostrar_mensaje=True):
        self._desactivar_tool()
        self._esperando_clic_subred = False
        if self.dialog is not None:
            try:
                self.dialog.close()
            except Exception:
                pass
        self.dialog = None
        self.lista_rutas = None
        if mostrar_mensaje:
            try:
                self.iface.mapCanvas().refresh()
            except Exception:
                pass