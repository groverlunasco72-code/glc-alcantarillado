# -*- coding: utf-8 -*-
"""
Módulo Eliminar Tubería.

2 modos de uso:
    1. 🎯 Clic en el mapa (como eliminar_camara)
    2. ✍️ Entrada manual de ID_O (uno o varios separados por comas)

REGLA DE ORO:
    NUNCA usar feat.id() (FID interno) como identidad.
    SIEMPRE identificar features por ID_O (clave de negocio).
    Re-localizar por ID_O justo antes de eliminar/actualizar.

Compatible con QGIS 3.x y preparado para 4.x.
"""

from qgis.core import (
    QgsProject,
    QgsVectorLayer,
    QgsGeometry,
    QgsWkbTypes,
)
from qgis.PyQt.QtWidgets import (
    QMessageBox, QDialog, QVBoxLayout, QLabel,
    QPushButton, QComboBox, QHBoxLayout,
    QGroupBox, QLineEdit,
)
from qgis.PyQt.QtCore import Qt
from qgis.gui import QgsMapToolEmitPoint


# ============================================================
# COMPATIBILIDAD PyQt5 / PyQt6
# ============================================================
try:
    _MSG_YES = QMessageBox.StandardButton.Yes
    _MSG_NO = QMessageBox.StandardButton.No
except AttributeError:
    _MSG_YES = QMessageBox.Yes
    _MSG_NO = QMessageBox.No


def _enum_value(x):
    return getattr(x, 'value', x)


def _nombre_capa(layer):
    try:
        return layer.name() or ''
    except Exception:
        return ''


# ============================================================
# CLASE PRINCIPAL
# ============================================================
class EliminarTuberia:

    CAMPO_ID_TUBERIA = 'ID_O'
    CAMPO_CI = 'Ci'
    CAMPO_CF = 'Cf'
    CAMPO_ID_CAMARA = 'ID_O'
    CAMPO_LINEAS_ID = 'Lineas_ID'
    CAMPO_N_LINEAS = 'N_Lineas'

    def __init__(self, iface):
        self.iface = iface
        self.capa_tuberias = None
        self.capa_camaras = None
        self.dialog = None
        self.tool_seleccion = None
        self.modo_edicion = False

    # ============================================================
    # HELPERS
    # ============================================================
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
    def _idx_campo(layer, nombre):
        try:
            return layer.fields().indexFromName(nombre)
        except Exception:
            return -1

    @staticmethod
    def _tiene_campo(layer, nombre):
        return EliminarTuberia._idx_campo(layer, nombre) != -1

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
    def _editar_capa(layer, callback):
        try:
            layer.startEditing()
            ok = callback()
            if ok is False:
                layer.rollBack()
                return False
            if not layer.commitChanges():
                layer.rollBack()
                return False
            return True
        except Exception:
            try:
                layer.rollBack()
            except Exception:
                pass
            return False

    # ============================================================
    # BÚSQUEDA ROBUSTA POR ID_O
    # ============================================================
    def _buscar_feature_tuberia(self, id_o, ci=None, cf=None):
        candidatos = []
        try:
            for f in self.capa_tuberias.getFeatures():
                if self._attr(f, self.CAMPO_ID_TUBERIA) != id_o:
                    continue
                if ci is not None and self._attr(f, self.CAMPO_CI) != ci:
                    continue
                if cf is not None and self._attr(f, self.CAMPO_CF) != cf:
                    continue
                candidatos.append(f)
        except Exception:
            return None
        return candidatos[0] if candidatos else None

    def _buscar_feature_camara(self, id_camara):
        try:
            for f in self.capa_camaras.getFeatures():
                if self._attr(f, self.CAMPO_ID_CAMARA) == id_camara:
                    return f
        except Exception:
            return None
        return None

    # ============================================================
    # DIÁLOGO PRINCIPAL
    # ============================================================
    def mostrar_dialogo(self):
        dialog = QDialog(self.iface.mainWindow())
        dialog.setWindowTitle('GLC - Eliminar Tubería')
        dialog.setMinimumWidth(600)
        self.dialog = dialog

        layout = QVBoxLayout()

        lbl = QLabel('<b>🗑️ Eliminar Tubería</b>')
        lbl.setStyleSheet('font-size: 13pt; font-weight: bold;')
        layout.addWidget(lbl)

        info = QLabel(
            'Elimina tuberías y limpia TODAS sus referencias en cámaras.\n'
            'Al eliminar una tubería se quita su ID_O de Lineas_ID en las cámaras Ci y Cf,\n'
            'y se actualiza N_Lineas en ambas.\n\n'
            'Elige el modo que prefieras:'
        )
        info.setWordWrap(True)
        layout.addWidget(info)

        # ---- Capas ----
        box_capas = QGroupBox('1. Capas de trabajo')
        lay_capas = QVBoxLayout()
        lay_capas.addWidget(QLabel('Capa GLC_Tuberias:'))
        self.combo_tuberias = QComboBox()
        self._llenar_combo(self.combo_tuberias,
                           _enum_value(QgsWkbTypes.LineGeometry),
                           'GLC_Tuberias')
        lay_capas.addWidget(self.combo_tuberias)

        lay_capas.addWidget(QLabel('Capa de Cámaras:'))
        self.combo_camaras = QComboBox()
        self._llenar_combo(self.combo_camaras,
                           _enum_value(QgsWkbTypes.PointGeometry),
                           'GLC_Camaras')
        lay_capas.addWidget(self.combo_camaras)
        box_capas.setLayout(lay_capas)
        layout.addWidget(box_capas)

        # ---- OPCIÓN A: clic en el mapa ----
        box_mapa = QGroupBox('2. Opción A — 🎯 Eliminar con clic en el mapa (recomendado)')
        lay_mapa = QVBoxLayout()
        lay_mapa.addWidget(QLabel(
            '👉 Pulsa el botón, luego haz clic sobre una tubería en el mapa.\n'
            '   Se te pedirá confirmación mostrando su ID_O, Ci y Cf.\n'
            '   Al terminar, la herramienta se desactiva sola.'
        ))
        btn_mapa = QPushButton('🎯 Eliminar Tubería (Click en el mapa)')
        btn_mapa.setStyleSheet(
            'background-color: #f44336; color: white; font-weight: bold; padding: 8px;'
        )
        btn_mapa.clicked.connect(self._activar_modo_mapa)
        lay_mapa.addWidget(btn_mapa)
        box_mapa.setLayout(lay_mapa)
        layout.addWidget(box_mapa)

        # ---- OPCIÓN B: entrada manual por ID_O ----
        box_manual = QGroupBox('3. Opción B — ✍️ Eliminar por ID_O (manual)')
        lay_manual = QVBoxLayout()
        lay_manual.addWidget(QLabel(
            '👉 Escribe el ID_O de la tubería a eliminar.\n'
            '   Para varias tuberías, sepáralas por comas (ej: 12, 15, 23).'
        ))
        hb_manual = QHBoxLayout()
        hb_manual.addWidget(QLabel('ID_O:'))
        self.txt_ids = QLineEdit()
        self.txt_ids.setPlaceholderText('Ej: 12    o    12, 15, 23')
        self.txt_ids.returnPressed.connect(self._eliminar_por_ids_manual)
        hb_manual.addWidget(self.txt_ids, 1)
        lay_manual.addLayout(hb_manual)

        hb_botones_manual = QHBoxLayout()
        btn_manual = QPushButton('🗑️ Eliminar por ID_O')
        btn_manual.setStyleSheet(
            'background-color: #D32F2F; color: white; font-weight: bold; padding: 6px;'
        )
        btn_manual.clicked.connect(self._eliminar_por_ids_manual)
        hb_botones_manual.addWidget(btn_manual)

        btn_limpiar_txt = QPushButton('🧹 Limpiar')
        btn_limpiar_txt.clicked.connect(lambda: self.txt_ids.clear())
        hb_botones_manual.addWidget(btn_limpiar_txt)
        lay_manual.addLayout(hb_botones_manual)

        box_manual.setLayout(lay_manual)
        layout.addWidget(box_manual)

        # ---- Cerrar ----
        btn_cerrar = QPushButton('Cerrar')
        btn_cerrar.setStyleSheet('background-color: #9E9E9E; color: white;')
        btn_cerrar.clicked.connect(dialog.reject)
        layout.addWidget(btn_cerrar)

        dialog.setLayout(layout)
        dialog.exec_()

    # ============================================================
    # COMBOS Y CAPAS
    # ============================================================
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
                if _enum_value(layer.geometryType()) != geom_value:
                    continue
            except Exception:
                continue
            nombre = _nombre_capa(layer)
            (preferidos if nombre_preferido in nombre else otros).append(layer)
        for layer in (preferidos or otros):
            combo.addItem(_nombre_capa(layer), layer.id())

    def _resolver_capas(self, mostrar_error=True):
        tub_id = self.combo_tuberias.currentData() if hasattr(self, 'combo_tuberias') else None
        cam_id = self.combo_camaras.currentData() if hasattr(self, 'combo_camaras') else None

        try:
            self.capa_tuberias = QgsProject.instance().mapLayer(tub_id) if tub_id else None
            self.capa_camaras = QgsProject.instance().mapLayer(cam_id) if cam_id else None
        except Exception:
            self.capa_tuberias = None
            self.capa_camaras = None

        if not isinstance(self.capa_tuberias, QgsVectorLayer) or \
           not isinstance(self.capa_camaras, QgsVectorLayer):
            if mostrar_error:
                self._msg(self.iface.mainWindow(), QMessageBox.Warning, 'Error',
                          'Selecciona capas válidas de tuberías y cámaras')
            return False

        if not self._tiene_campo(self.capa_tuberias, self.CAMPO_ID_TUBERIA):
            if mostrar_error:
                self._msg(self.iface.mainWindow(), QMessageBox.Warning, 'Error',
                          f'La capa de tuberías no tiene el campo {self.CAMPO_ID_TUBERIA}')
            return False

        if not self._tiene_campo(self.capa_camaras, self.CAMPO_LINEAS_ID):
            if mostrar_error:
                self._msg(self.iface.mainWindow(), QMessageBox.Warning, 'Error',
                          f'La capa de cámaras no tiene {self.CAMPO_LINEAS_ID}')
            return False

        return True

    # ============================================================
    # MODO MAPA — 🎯 clic sobre tubería
    # ============================================================
    def _activar_modo_mapa(self):
        if not self._resolver_capas():
            return

        self.tool_seleccion = QgsMapToolEmitPoint(self.iface.mapCanvas())
        self.tool_seleccion.canvasClicked.connect(self._on_canvas_click)
        self.iface.mapCanvas().setMapTool(self.tool_seleccion)
        self.modo_edicion = True

        if self.dialog:
            self.dialog.accept()

        self._msg(self.iface.mainWindow(), QMessageBox.Information,
                  'Modo Eliminar Tubería',
                  '🔹 Haz clic sobre una tubería en el mapa para eliminarla\n'
                  '🔹 Se te pedirá confirmación con su ID_O, Ci y Cf\n'
                  '🔹 Se limpiarán las referencias en las cámaras\n'
                  '🔹 Presiona ESC para cancelar')

    def _on_canvas_click(self, point):
        """Detecta la tubería más cercana al clic y pide confirmación."""
        punto_geom = QgsGeometry.fromPointXY(point)

        # Tolerancia adaptada a la escala (aprox 10 px en unidades del mapa)
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

        if tuberia_cercana is None or (dist_minima is not None and dist_minima > tolerancia_mapa):
            self._msg(self.iface.mainWindow(), QMessageBox.Warning,
                      'Sin selección',
                      'No se encontró ninguna tubería cerca del clic.\n'
                      'Acércate más a una tubería e inténtalo de nuevo.')
            return

        # Extraer claves por ID_O (nunca FID)
        id_o = self._attr(tuberia_cercana, self.CAMPO_ID_TUBERIA)
        ci = self._attr(tuberia_cercana, self.CAMPO_CI)
        cf = self._attr(tuberia_cercana, self.CAMPO_CF)

        if not self._preguntar(
            self.iface.mainWindow(),
            'Confirmar eliminación',
            f'¿Eliminar esta tubería?\n\n'
            f'   ID_O = {id_o}\n'
            f'   Ci = {ci}  →  Cf = {cf}\n\n'
            f'Se limpiará su ID_O de Lineas_ID en las cámaras Ci y Cf,\n'
            f'y se actualizará N_Lineas en ambas.'
        ):
            return

        eliminadas, errores = self._eliminar_por_claves([(id_o, ci, cf)])

        self._desactivar_tool()

        if eliminadas:
            self._msg(self.iface.mainWindow(), QMessageBox.Information,
                      'Tubería eliminada',
                      f'✅ Tubería ID_O={eliminadas[0]} eliminada.\n'
                      '✅ Referencias actualizadas en Lineas_ID y N_Lineas.')
        elif errores:
            self._msg(self.iface.mainWindow(), QMessageBox.Critical,
                      'Error',
                      'No se pudo eliminar:\n' + '\n'.join(str(e) for e in errores))

    # ============================================================
    # MODO MANUAL — ✍️ escribir ID_O
    # ============================================================
    def _eliminar_por_ids_manual(self):
        if not self._resolver_capas():
            return

        texto = self.txt_ids.text().strip()
        if not texto:
            self._msg(self.iface.mainWindow(), QMessageBox.Warning,
                      'Sin datos',
                      'Escribe al menos un ID_O.\n'
                      'Puedes escribir varios separados por comas: 12, 15, 23')
            return

        # Parsear: acepta "12", "12, 15, 23", "12;15;23", "12 15 23"
        texto_norm = texto.replace(';', ',').replace(' ', ',')
        ids = []
        invalidos = []
        for parte in texto_norm.split(','):
            parte = parte.strip()
            if not parte:
                continue
            try:
                ids.append(int(parte))
            except ValueError:
                invalidos.append(parte)

        if invalidos:
            self._msg(self.iface.mainWindow(), QMessageBox.Warning,
                      'Valores inválidos',
                      'No se pudieron interpretar como números:\n   ' +
                      ', '.join(invalidos))
            return

        if not ids:
            self._msg(self.iface.mainWindow(), QMessageBox.Warning,
                      'Sin IDs válidos',
                      'No se detectó ningún ID_O válido en el texto.')
            return

        # Deduplicar manteniendo orden
        vistos = set()
        ids_unicos = []
        for i in ids:
            if i not in vistos:
                vistos.add(i)
                ids_unicos.append(i)

        # Buscar las tuberías por ID_O para mostrar resumen
        encontradas = []
        no_encontradas = []
        for id_o in ids_unicos:
            feat = self._buscar_feature_tuberia(id_o)
            if feat is None:
                no_encontradas.append(id_o)
            else:
                encontradas.append((
                    id_o,
                    self._attr(feat, self.CAMPO_CI),
                    self._attr(feat, self.CAMPO_CF),
                ))

        if not encontradas:
            self._msg(self.iface.mainWindow(), QMessageBox.Warning,
                      'No encontradas',
                      f'Ninguna de las tuberías indicadas existe:\n'
                      f'   {", ".join(str(i) for i in ids_unicos)}')
            return

        # Resumen para confirmar
        lineas = []
        for id_o, ci, cf in encontradas[:30]:
            lineas.append(f'  • ID_O={id_o}  (Ci={ci} → Cf={cf})')
        resumen = '\n'.join(lineas)
        if len(encontradas) > 30:
            resumen += f'\n  ... y {len(encontradas) - 30} más'

        aviso_extra = ''
        if no_encontradas:
            aviso_extra = (f'\n\n⚠️ No encontradas (se ignorarán): '
                           f'{", ".join(str(i) for i in no_encontradas)}')

        if not self._preguntar(
            self.iface.mainWindow(),
            'Confirmar eliminación',
            f'¿Eliminar {len(encontradas)} tubería(s)?\n\n{resumen}{aviso_extra}'
        ):
            return

        eliminadas, errores = self._eliminar_por_claves(encontradas)

        ids_eliminados = set(eliminadas)
        no_encontradas_finales = [i for i in ids_unicos if i not in ids_eliminados]
        ids_error = {e[0] for e in errores if isinstance(e, tuple)}
        no_encontradas_finales = [i for i in no_encontradas_finales
                                  if i not in ids_error]

        # Limpiar el campo de texto tras el intento
        self.txt_ids.clear()
        self._mostrar_resumen(eliminadas, no_encontradas_finales, errores)

    # ============================================================
    # LÓGICA CENTRAL — ELIMINAR POR CLAVES (id_o, ci, cf)
    # ============================================================
    def _eliminar_por_claves(self, claves):
        eliminadas = []
        errores = []

        vistas = set()
        claves_unicas = []
        for c in claves:
            if c in vistas:
                continue
            vistas.add(c)
            claves_unicas.append(c)

        for id_o, ci, cf in claves_unicas:
            try:
                # 1) Localizar la tubería AHORA por ID_O
                feat = self._buscar_feature_tuberia(id_o, ci, cf)
                if feat is None:
                    errores.append((id_o, 'No encontrada (ID_O no existe o cambió)'))
                    continue

                # 2) Limpiar Lineas_ID de las cámaras Ci y Cf
                if ci is not None:
                    self._quitar_id_de_camara(ci, id_o)
                if cf is not None and cf != ci:
                    self._quitar_id_de_camara(cf, id_o)

                # 3) Eliminar el feature (FID recién leído)
                fid_real = feat.id()

                def _do_delete(fid=fid_real):
                    return self.capa_tuberias.deleteFeature(fid)

                if not self._editar_capa(self.capa_tuberias, _do_delete):
                    errores.append((id_o, 'deleteFeature devolvió False'))
                    continue

                eliminadas.append(id_o)
            except Exception as e:
                errores.append((id_o, str(e)))

        try:
            self.capa_tuberias.removeSelection()
        except Exception:
            pass
        try:
            self.iface.mapCanvas().refresh()
        except Exception:
            pass

        return eliminadas, errores

    # ============================================================
    # QUITAR ID DE CÁMARA (por ID_O)
    # ============================================================
    def _quitar_id_de_camara(self, id_camara, id_tuberia):
        idx_lineas = self._idx_campo(self.capa_camaras, self.CAMPO_LINEAS_ID)
        idx_n = self._idx_campo(self.capa_camaras, self.CAMPO_N_LINEAS)
        if idx_lineas == -1:
            return

        camara = self._buscar_feature_camara(id_camara)
        if camara is None:
            return

        lineas_str = self._attr(camara, self.CAMPO_LINEAS_ID) or ''
        lineas_list = []
        if lineas_str:
            for x in str(lineas_str).split(','):
                x = x.strip()
                if x.isdigit():
                    try:
                        lineas_list.append(int(x))
                    except Exception:
                        pass

        if id_tuberia in lineas_list:
            lineas_list.remove(id_tuberia)

        lineas_list = sorted(set(lineas_list))
        nueva = ', '.join(str(x) for x in lineas_list) if lineas_list else ''

        fid_cam = camara.id()

        def _do_update():
            self.capa_camaras.changeAttributeValue(fid_cam, idx_lineas, nueva)
            if idx_n != -1:
                self.capa_camaras.changeAttributeValue(fid_cam, idx_n, len(lineas_list))
            return True

        self._editar_capa(self.capa_camaras, _do_update)

    # ============================================================
    # RESUMEN
    # ============================================================
    def _mostrar_resumen(self, eliminadas, no_encontradas, errores):
        partes = ['=== RESUMEN ===', '']
        partes.append(f'✅ Eliminadas: {len(eliminadas)}')
        if eliminadas:
            txt = ', '.join(str(x) for x in eliminadas[:40])
            if len(eliminadas) > 40:
                txt += f' ... (+{len(eliminadas) - 40})'
            partes.append(f'   IDs: {txt}')
        if no_encontradas:
            partes.append(f'\n⚠️ No encontradas: {len(no_encontradas)}')
            partes.append('   IDs: ' + ', '.join(str(x) for x in no_encontradas))
        if errores:
            partes.append(f'\n❌ Errores: {len(errores)}')
            for e in errores:
                partes.append(f'   {e}')
        partes.append('\n✅ Referencias actualizadas en Lineas_ID y N_Lineas.')

        self._msg(self.iface.mainWindow(), QMessageBox.Information,
                  'Eliminación completada', '\n'.join(partes))

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
        self.modo_edicion = False

    def desactivar(self, mostrar_mensaje=True):
        self._desactivar_tool()
        if mostrar_mensaje:
            try:
                self.iface.mapCanvas().refresh()
            except Exception:
                pass