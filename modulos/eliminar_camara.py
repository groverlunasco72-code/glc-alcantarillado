# -*- coding: utf-8 -*-
"""
Módulo Eliminar Cámara - Elimina una cámara y TODAS las tuberías conectadas.
Actualiza Lineas_ID y N_Lineas en las cámaras del otro extremo.

REGLA DE ORO:
    NUNCA usar feat.id() (FID interno de QGIS) para identificar features.
    SIEMPRE identificar por ID_O (clave de negocio).
    Re-localizar cada feature por ID_O JUSTO ANTES de eliminar/actualizar.

Compatible con QGIS 3.x y preparado para 4.x.
"""

from qgis.core import (
    QgsProject,
    QgsVectorLayer,
    QgsGeometry,
    QgsPointXY,
    QgsWkbTypes,
)
from qgis.PyQt.QtWidgets import (
    QMessageBox, QDialog, QVBoxLayout, QLabel,
    QPushButton, QComboBox, QHBoxLayout,
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


class EliminarCamara:
    """
    Elimina una cámara y, en cascada, todas las tuberías conectadas a ella.
    Limpia Lineas_ID y N_Lineas en las cámaras del otro extremo.

    Toda la lógica se apoya en ID_O. El FID interno solo se usa de forma
    puntual como argumento de deleteFeature / changeAttributeValue,
    nunca como fuente de identidad.
    """

    # Nombres de campos (centralizados)
    CAMPO_ID = 'ID_O'
    CAMPO_CI = 'Ci'
    CAMPO_CF = 'Cf'
    CAMPO_LINEAS_ID = 'Lineas_ID'
    CAMPO_N_LINEAS = 'N_Lineas'

    def __init__(self, iface):
        self.iface = iface
        self.capa_tuberias = None
        self.capa_camaras = None
        self.tool_seleccion = None
        self.modo_edicion = False
        self.dialog = None

    # ============================================================
    # HELPERS DE COMPATIBILIDAD
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
            try:
                return QMessageBox.question(
                    parent, titulo, texto,
                    QMessageBox.Yes | QMessageBox.No
                ) == QMessageBox.Yes
            except Exception:
                return False

    @staticmethod
    def _idx_campo(layer, nombre):
        try:
            return layer.fields().indexFromName(nombre)
        except Exception:
            return -1

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
        """startEditing/commit/rollback seguro."""
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
    # ⭐ BÚSQUEDA ROBUSTA POR ID_O
    # ============================================================
    def _buscar_tuberia_por_id_o(self, id_o, ci=None, cf=None):
        """
        Busca una tubería por ID_O (y opcionalmente Ci/Cf para desambiguar).
        Devuelve el feature o None.
        """
        candidatos = []
        try:
            for f in self.capa_tuberias.getFeatures():
                if self._attr(f, self.CAMPO_ID) != id_o:
                    continue
                if ci is not None and self._attr(f, self.CAMPO_CI) != ci:
                    continue
                if cf is not None and self._attr(f, self.CAMPO_CF) != cf:
                    continue
                candidatos.append(f)
        except Exception:
            return None
        return candidatos[0] if candidatos else None

    def _buscar_camara_por_id_o(self, id_camara):
        """Busca una cámara por ID_O. Devuelve el feature o None."""
        try:
            for f in self.capa_camaras.getFeatures():
                if self._attr(f, self.CAMPO_ID) == id_camara:
                    return f
        except Exception:
            return None
        return None

    # ============================================================
    # DIÁLOGO
    # ============================================================
    def mostrar_dialogo(self):
        dialog = QDialog(self.iface.mainWindow())
        dialog.setWindowTitle('GLC - Eliminar Cámara')
        dialog.setMinimumWidth(560)
        self.dialog = dialog

        layout = QVBoxLayout()

        lbl = QLabel('<b>🗑️ Eliminar Cámara</b>')
        lbl.setStyleSheet('font-size: 13pt; font-weight: bold;')
        layout.addWidget(lbl)

        info = QLabel(
            'Elimina una cámara y TODAS las tuberías conectadas a ella.\n\n'
            '📌 Al eliminar la cámara se eliminan también sus tuberías Ci y Cf\n'
            '📌 Se limpia el ID_O de esas tuberías en Lineas_ID de las cámaras\n'
            '   del otro extremo, y se actualiza su N_Lineas\n'
            '📌 Toda la lógica trabaja con ID_O (nunca con el FID interno)\n\n'
            '⚠️ Esta acción es en cascada: revisa bien antes de confirmar.'
        )
        info.setWordWrap(True)
        layout.addWidget(info)

        layout.addWidget(QLabel('-' * 40))

        # Capas
        layout.addWidget(QLabel('Capa GLC_Tuberias:'))
        self.combo_tuberias = QComboBox()
        self._llenar_combo(self.combo_tuberias,
                           _enum_value(QgsWkbTypes.LineGeometry),
                           'GLC_Tuberias')
        layout.addWidget(self.combo_tuberias)

        layout.addWidget(QLabel('Capa GLC_Camaras:'))
        self.combo_camaras = QComboBox()
        self._llenar_combo(self.combo_camaras,
                           _enum_value(QgsWkbTypes.PointGeometry),
                           'GLC_Camaras')
        layout.addWidget(self.combo_camaras)

        layout.addWidget(QLabel('-' * 40))

        btn = QPushButton('🗑️ Eliminar Cámara (Click en el mapa)')
        btn.setStyleSheet(
            'background-color: #f44336; color: white; font-weight: bold; padding: 6px;'
        )
        btn.clicked.connect(self._activar)
        layout.addWidget(btn)

        btn_cancelar = QPushButton('Cancelar')
        btn_cancelar.setStyleSheet('background-color: #9E9E9E; color: white;')
        btn_cancelar.clicked.connect(dialog.reject)
        layout.addWidget(btn_cancelar)

        dialog.setLayout(layout)
        dialog.exec_()

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

    # ============================================================
    # ACTIVAR HERRAMIENTA
    # ============================================================
    def _activar(self):
        tub_id = self.combo_tuberias.currentData()
        cam_id = self.combo_camaras.currentData()

        self.capa_tuberias = QgsProject.instance().mapLayer(tub_id) if tub_id else None
        self.capa_camaras = QgsProject.instance().mapLayer(cam_id) if cam_id else None

        if not isinstance(self.capa_tuberias, QgsVectorLayer) or \
           not isinstance(self.capa_camaras, QgsVectorLayer):
            self._msg(self.iface.mainWindow(), QMessageBox.Warning, 'Error',
                      'Selecciona capas válidas de tuberías y cámaras')
            return

        if self._idx_campo(self.capa_tuberias, self.CAMPO_CI) == -1 or \
           self._idx_campo(self.capa_tuberias, self.CAMPO_CF) == -1:
            self._msg(self.iface.mainWindow(), QMessageBox.Warning, 'Error',
                      'La capa de tuberías debe tener los campos Ci y Cf')
            return

        if self._idx_campo(self.capa_camaras, self.CAMPO_ID) == -1:
            self._msg(self.iface.mainWindow(), QMessageBox.Warning, 'Error',
                      f'La capa de cámaras no tiene el campo {self.CAMPO_ID}')
            return

        self.tool_seleccion = QgsMapToolEmitPoint(self.iface.mapCanvas())
        self.tool_seleccion.canvasClicked.connect(self._on_canvas_click)
        self.iface.mapCanvas().setMapTool(self.tool_seleccion)
        self.modo_edicion = True

        if self.dialog:
            self.dialog.accept()

        self._msg(self.iface.mainWindow(), QMessageBox.Information,
                  'Modo Eliminar Cámara',
                  '🔹 Haz clic sobre una cámara para eliminarla\n'
                  '🔹 Se eliminarán también sus tuberías conectadas\n'
                  '🔹 Las cámaras del otro extremo se actualizarán\n'
                  '🔹 Presiona ESC para cancelar')

    # ============================================================
    # CLICK EN EL MAPA
    # ============================================================
    def _on_canvas_click(self, point):
        punto_geom = QgsGeometry.fromPointXY(point)
        camara_cercana = None

        # 1) Buscar cámara que CONTENGA el punto
        for feat in self.capa_camaras.getFeatures():
            geom = feat.geometry()
            if not geom or geom.isEmpty():
                continue
            if geom.contains(punto_geom):
                camara_cercana = feat
                break

        # 2) Si no hay, buscar la más cercana dentro de tolerancia
        if camara_cercana is None:
            tolerancia_mapa = 10.0
            try:
                canvas = self.iface.mapCanvas()
                scale = canvas.mapSettings().scale()
                tolerancia_mapa = 10.0 * scale / 1000.0
            except Exception:
                pass

            dist_min = tolerancia_mapa
            for feat in self.capa_camaras.getFeatures():
                geom = feat.geometry()
                if not geom or geom.isEmpty():
                    continue
                try:
                    dist = geom.distance(punto_geom)
                except Exception:
                    continue
                if dist < dist_min:
                    dist_min = dist
                    camara_cercana = feat

        if camara_cercana is None:
            self._msg(self.iface.mainWindow(), QMessageBox.Warning, 'Sin selección',
                      'No se encontró ninguna cámara cerca del clic')
            return

        # ⭐ Guardamos ID_O, no el FID
        id_camara = self._attr(camara_cercana, self.CAMPO_ID)

        # Buscar tuberías conectadas por ID_O
        # Guardamos SOLO claves (id_o, ci, cf). Nada de features ni FIDs.
        claves_tuberias = []
        try:
            for feat in self.capa_tuberias.getFeatures():
                ci = self._attr(feat, self.CAMPO_CI)
                cf = self._attr(feat, self.CAMPO_CF)
                if ci == id_camara or cf == id_camara:
                    claves_tuberias.append((
                        self._attr(feat, self.CAMPO_ID),
                        ci,
                        cf,
                    ))
        except Exception:
            pass

        # Resumen para confirmación
        n_tub = len(claves_tuberias)
        resumen = f'🗑️ Cámara a eliminar: ID_O = {id_camara}\n\n'
        if n_tub == 0:
            resumen += '✅ Esta cámara no tiene tuberías conectadas.'
        else:
            resumen += f'⚠️ Se eliminarán TAMBIÉN {n_tub} tubería(s) conectada(s):\n'
            for id_t, ci, cf in claves_tuberias[:20]:
                resumen += f'   • ID_O={id_t}  (Ci={ci} → Cf={cf})\n'
            if n_tub > 20:
                resumen += f'   ... y {n_tub - 20} más\n'
            resumen += '\nSe actualizarán las cámaras del otro extremo.'

        if not self._preguntar(self.iface.mainWindow(),
                               'Confirmar eliminación en cascada',
                               resumen + '\n\n¿Continuar?'):
            return

        # Ejecutar eliminación en cascada usando ID_O
        ok, msg_resumen = self._eliminar_camara_y_tuberias(id_camara, claves_tuberias)

        # Desactivar herramienta
        self._desactivar_tool()

        if ok:
            self._msg(self.iface.mainWindow(), QMessageBox.Information,
                      'Cámara eliminada', msg_resumen)
        else:
            self._msg(self.iface.mainWindow(), QMessageBox.Critical,
                      'Error', msg_resumen)

    # ============================================================
    # ⭐ LÓGICA DE ELIMINACIÓN EN CASCADA (todo por ID_O)
    # ============================================================
    def _eliminar_camara_y_tuberias(self, id_camara, claves_tuberias):
        """
        claves_tuberias: lista de (id_o_tuberia, ci, cf)

        Pasos:
          1) Para cada tubería:
             a) localizarla AHORA por ID_O (+ Ci/Cf)
             b) limpiar Lineas_ID del OTRO extremo (re-localizado por ID_O)
             c) eliminar la tubería
          2) Eliminar la cámara re-localizándola por ID_O.
        """
        eliminadas = []
        errores = []

        # Deduplicar claves por si acaso
        vistas = set()
        claves_unicas = []
        for c in claves_tuberias:
            if c in vistas:
                continue
            vistas.add(c)
            claves_unicas.append(c)

        # ----- PASO 1: eliminar tuberías conectadas -----
        for id_t, ci, cf in claves_unicas:
            try:
                # a) Localizar la tubería AHORA por ID_O
                feat_t = self._buscar_tuberia_por_id_o(id_t, ci, cf)
                if feat_t is None:
                    errores.append((id_t, 'No encontrada al re-localizar por ID_O'))
                    continue

                # b) Identificar el OTRO extremo
                if ci == id_camara and cf != id_camara:
                    otro = cf
                elif cf == id_camara and ci != id_camara:
                    otro = ci
                else:
                    otro = None  # lazo a sí misma o caso degenerado

                if otro is not None:
                    self._quitar_id_de_camara(otro, id_t)

                # c) Eliminar la tubería (FID solo se usa aquí, al instante)
                fid_real = feat_t.id()

                def _do_delete(fid=fid_real):
                    return self.capa_tuberias.deleteFeature(fid)

                if not self._editar_capa(self.capa_tuberias, _do_delete):
                    errores.append((id_t, 'No se pudo eliminar la tubería'))
                    continue

                eliminadas.append(id_t)
            except Exception as e:
                errores.append((id_t, str(e)))

        # ----- PASO 2: eliminar la cámara re-localizada por ID_O -----
        feat_cam = self._buscar_camara_por_id_o(id_camara)
        if feat_cam is None:
            errores.append((id_camara, 'Cámara no encontrada al re-localizar'))
            return False, self._formar_resumen(id_camara, eliminadas, errores)

        fid_cam = feat_cam.id()

        def _do_delete_cam(fid=fid_cam):
            return self.capa_camaras.deleteFeature(fid)

        if not self._editar_capa(self.capa_camaras, _do_delete_cam):
            errores.append((id_camara, 'No se pudo eliminar la cámara'))
            return False, self._formar_resumen(id_camara, eliminadas, errores)

        # Refrescar canvas
        try:
            self.iface.mapCanvas().refresh()
        except Exception:
            pass

        return True, self._formar_resumen(id_camara, eliminadas, errores)

    # ============================================================
    # ⭐ QUITAR ID DE CÁMARA (re-localizando por ID_O)
    # ============================================================
    def _quitar_id_de_camara(self, id_camara, id_tuberia):
        """
        Quita id_tuberia de Lineas_ID en la cámara con ID_O == id_camara.
        La cámara se re-localiza por ID_O (nunca se usa un FID guardado).
        """
        idx_lineas = self._idx_campo(self.capa_camaras, self.CAMPO_LINEAS_ID)
        idx_n = self._idx_campo(self.capa_camaras, self.CAMPO_N_LINEAS)
        if idx_lineas == -1:
            return

        # ⭐ Re-localización por ID_O
        feat_cam = self._buscar_camara_por_id_o(id_camara)
        if feat_cam is None:
            return

        lineas_str = self._attr(feat_cam, self.CAMPO_LINEAS_ID) or ''
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

        # FID solo como argumento puntual de changeAttributeValue
        fid_cam = feat_cam.id()

        def _do_update():
            self.capa_camaras.changeAttributeValue(fid_cam, idx_lineas, nueva)
            if idx_n != -1:
                self.capa_camaras.changeAttributeValue(fid_cam, idx_n, len(lineas_list))
            return True

        self._editar_capa(self.capa_camaras, _do_update)

    # ============================================================
    # RESUMEN
    # ============================================================
    def _formar_resumen(self, id_camara, eliminadas, errores):
        msg = '=== ELIMINACIÓN EN CASCADA ===\n\n'
        msg += f'🗑️ Cámara eliminada: ID_O = {id_camara}\n\n'
        msg += f'✅ Tuberías eliminadas: {len(eliminadas)}\n'
        if eliminadas:
            txt = ', '.join(str(x) for x in eliminadas[:30])
            if len(eliminadas) > 30:
                txt += f' ... (+{len(eliminadas) - 30})'
            msg += f'   IDs: {txt}\n'
        if errores:
            msg += f'\n❌ Errores: {len(errores)}\n'
            for e in errores:
                msg += f'   {e}\n'
        msg += '\n✅ Lineas_ID y N_Lineas actualizados en las cámaras del otro extremo.'
        return msg

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