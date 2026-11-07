# -*- coding: utf-8 -*-
"""
Módulo Dividir Tubería.

CORRECCIONES APLICADAS:
- actualizar_lineas_id: localiza la cámara por ID_O, no por FID guardado.
- deleteFeature: re-localiza la tubería original por ID_O + Ci + Cf
  justo antes de borrar, evitando borrar otra tubería si el FID cambió.

Compatible con QGIS 3.x y preparado para 4.x.
"""

from qgis.core import (
    QgsProject, QgsVectorLayer, QgsFeature,
    QgsGeometry, QgsPointXY, QgsField,
    QgsWkbTypes, QgsLineString,
    QgsRasterLayer,
    QgsPoint
)
from qgis.PyQt.QtCore import Qt, QVariant
from qgis.PyQt.QtWidgets import (
    QMessageBox, QDialog, QVBoxLayout, QLabel,
    QPushButton, QComboBox, QHBoxLayout, QLineEdit
)
from qgis.gui import QgsMapToolEmitPoint
from .utils import obtener_vertices_linea, extraer_cota_dem


class DividirTuberia:
    def __init__(self, iface):
        self.iface = iface
        self.capa_tuberias = None
        self.capa_camaras = None
        self.capa_dem = None
        self.tool_seleccion = None
        self.modo_edicion = False
        self.id_sugerido = ""
        self.dialog = None

    # ============================================================
    # DIÁLOGO
    # ============================================================
    def mostrar_dialogo(self):
        dialog = QDialog(self.iface.mainWindow())
        dialog.setWindowTitle('GLC - Dividir Tuberia')
        dialog.setMinimumWidth(500)
        self.dialog = dialog

        layout = QVBoxLayout()

        label_titulo = QLabel('<b>Dividir Tuberia</b>')
        label_titulo.setStyleSheet('font-size: 12pt; font-weight: bold;')
        layout.addWidget(label_titulo)

        label_info = QLabel(
            'Divide una tuberia existente en dos, creando una camara en el punto de division.\n'
            'Haz clic en la tuberia para seleccionar el punto de division.\n\n'
            '📌 Se crean DOS nuevas tuberias con IDs consecutivos (max+1, max+2)\n'
            '📌 La tuberia original se elimina\n'
            '📌 Se crea una nueva camara en el punto de division'
        )
        label_info.setWordWrap(True)
        layout.addWidget(label_info)

        layout.addWidget(QLabel('-' * 40))

        # Seleccionar capas
        layout.addWidget(QLabel('Seleccionar capa GLC_Tuberias:'))
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
        layout.addWidget(combo_tuberias)

        layout.addWidget(QLabel('Seleccionar capa de Camaras:'))
        combo_camaras = QComboBox()
        for layer in QgsProject.instance().mapLayers().values():
            if isinstance(layer, QgsVectorLayer):
                if layer.geometryType() == QgsWkbTypes.PointGeometry:
                    if 'GLC_Camaras' in layer.name():
                        combo_camaras.addItem(layer.name(), layer.id())
        if combo_camaras.count() == 0:
            for layer in QgsProject.instance().mapLayers().values():
                if isinstance(layer, QgsVectorLayer):
                    if layer.geometryType() == QgsWkbTypes.PointGeometry:
                        combo_camaras.addItem(layer.name(), layer.id())
        layout.addWidget(combo_camaras)

        layout.addWidget(QLabel('Seleccionar DEM (para cota Z):'))
        combo_dem = QComboBox()
        for layer in QgsProject.instance().mapLayers().values():
            if isinstance(layer, QgsRasterLayer):
                combo_dem.addItem(layer.name(), layer.id())
        layout.addWidget(combo_dem)

        layout.addWidget(QLabel('-' * 40))

        # ID de la nueva camara
        hbox_id = QHBoxLayout()
        hbox_id.addWidget(QLabel('ID_O de la nueva camara (opcional):'))
        txt_id = QLineEdit()
        txt_id.setPlaceholderText('Auto (dejar vacio) o escribir numero')
        hbox_id.addWidget(txt_id)
        layout.addLayout(hbox_id)

        layout.addWidget(QLabel('-' * 40))

        btn_dividir = QPushButton('Dividir Tuberia (Click en la tuberia)')
        btn_dividir.setStyleSheet('background-color: #9C27B0; color: white; font-weight: bold;')
        btn_dividir.clicked.connect(lambda: self.activar_dividir(
            combo_tuberias.currentData(),
            combo_camaras.currentData(),
            combo_dem.currentData(),
            txt_id.text()
        ))
        layout.addWidget(btn_dividir)

        btn_cancelar = QPushButton('Cancelar')
        btn_cancelar.setStyleSheet('background-color: #f44336; color: white;')
        btn_cancelar.clicked.connect(dialog.reject)
        layout.addWidget(btn_cancelar)

        dialog.setLayout(layout)
        dialog.exec_()

    # ============================================================
    # HELPERS DE IDs
    # ============================================================
    def obtener_maximo_id(self, layer):
        max_id = 0
        for feature in layer.getFeatures():
            id_o = feature.attribute('ID_O')
            if id_o is not None and id_o > max_id:
                max_id = id_o
        return max_id

    def obtener_nuevo_id(self, layer, id_sugerido=None):
        max_id = self.obtener_maximo_id(layer)
        if id_sugerido and id_sugerido.isdigit():
            id_int = int(id_sugerido)
            if id_int > max_id:
                return id_int
            else:
                return max_id + 1
        else:
            return max_id + 1

    def obtener_dos_nuevos_ids(self, layer, id_sugerido=None):
        max_id = self.obtener_maximo_id(layer)
        if id_sugerido and id_sugerido.isdigit():
            id_int = int(id_sugerido)
            if id_int > max_id:
                return id_int, id_int + 1
            else:
                return max_id + 1, max_id + 2
        else:
            return max_id + 1, max_id + 2

    # ============================================================
    # BÚSQUEDA ROBUSTA POR ID_O
    # ============================================================
    def _buscar_camara_por_id_o(self, id_camara):
        """
        Busca la cámara por ID_O y devuelve el feature (o None).
        Se usa para no depender de FIDs guardados.
        """
        for feature in self.capa_camaras.getFeatures():
            if feature.attribute('ID_O') == id_camara:
                return feature
        return None

    def _buscar_tuberia_por_id_o(self, id_o, ci=None, cf=None):
        """
        Busca una tubería por ID_O (y Ci/Cf si se dan) y devuelve el feature.
        Se usa para re-localizar JUSTO ANTES de eliminar.
        """
        candidatos = []
        for f in self.capa_tuberias.getFeatures():
            if f.attribute('ID_O') != id_o:
                continue
            if ci is not None and f.attribute('Ci') != ci:
                continue
            if cf is not None and f.attribute('Cf') != cf:
                continue
            candidatos.append(f)
        return candidatos[0] if candidatos else None

    def obtener_cota_camara(self, id_camara):
        camara = self._buscar_camara_por_id_o(id_camara)
        return camara.attribute('Z') if camara else None

    # ============================================================
    # ACTUALIZAR LINEAS_ID (por ID_O)
    # ============================================================
    def actualizar_lineas_id(self, id_camara, id_tuberia, accion):
        """
        Actualiza Lineas_ID y N_Lineas de la cámara con ID_O == id_camara.

        - La cámara se localiza por ID_O (no por FID guardado).
        - El FID solo se usa como argumento puntual de changeAttributeValue.
        """
        idx_lineas_id = self.capa_camaras.fields().indexFromName('Lineas_ID')
        if idx_lineas_id == -1:
            return

        # 1) Localizar la cámara por ID_O
        camara = self._buscar_camara_por_id_o(id_camara)
        if camara is None:
            return

        # 2) Recalcular Lineas_ID
        lineas_id_str = camara.attribute('Lineas_ID') or ''
        lineas_list = []
        if lineas_id_str:
            lineas_list = [int(x.strip()) for x in lineas_id_str.split(',')
                           if x.strip().isdigit()]

        if accion == 'añadir' and id_tuberia not in lineas_list:
            lineas_list.append(id_tuberia)
        elif accion == 'quitar' and id_tuberia in lineas_list:
            lineas_list.remove(id_tuberia)

        lineas_list = sorted(set(lineas_list))
        nueva_lineas_id = ', '.join(str(x) for x in lineas_list) if lineas_list else ''

        # 3) Aplicar cambios (FID puntual)
        fid = camara.id()
        idx_n_lineas = self.capa_camaras.fields().indexFromName('N_Lineas')

        self.capa_camaras.startEditing()
        self.capa_camaras.changeAttributeValue(fid, idx_lineas_id, nueva_lineas_id)
        if idx_n_lineas != -1:
            self.capa_camaras.changeAttributeValue(fid, idx_n_lineas, len(lineas_list))
        self.capa_camaras.commitChanges()

    # ============================================================
    # ACTIVAR HERRAMIENTA
    # ============================================================
    def activar_dividir(self, tuberias_id, camaras_id, dem_id, id_sugerido):
        self.capa_tuberias = QgsProject.instance().mapLayer(tuberias_id)
        self.capa_camaras = QgsProject.instance().mapLayer(camaras_id)
        self.capa_dem = QgsProject.instance().mapLayer(dem_id)

        if not self.capa_tuberias or not self.capa_camaras:
            QMessageBox.warning(self.iface.mainWindow(), 'Error', 'No se encontraron las capas')
            return

        if not self.capa_dem:
            QMessageBox.warning(self.iface.mainWindow(), 'Error', 'No se encontró el DEM')
            return

        self.id_sugerido = id_sugerido

        self.tool_seleccion = QgsMapToolEmitPoint(self.iface.mapCanvas())
        self.tool_seleccion.canvasClicked.connect(self.on_canvas_click)
        self.iface.mapCanvas().setMapTool(self.tool_seleccion)
        self.modo_edicion = True

        if self.dialog:
            self.dialog.accept()

        QMessageBox.information(
            self.iface.mainWindow(),
            'Modo Dividir Tuberia',
            '🔹 Haz clic en una tuberia para seleccionar el punto de division\n'
            '🔹 Se creara una nueva camara en ese punto\n'
            '🔹 La tuberia original se eliminara y se crearan DOS nuevas\n'
            '🔹 Presiona ESC para cancelar'
        )

    # ============================================================
    # CLICK EN EL MAPA
    # ============================================================
    def on_canvas_click(self, point):
        # Buscar la tuberia mas cercana al punto
        tolerancia = 10.0
        tuberia_cercana = None
        dist_minima = tolerancia

        punto_geom = QgsGeometry.fromPointXY(point)

        for feature in self.capa_tuberias.getFeatures():
            geom = feature.geometry()
            if not geom or geom.isEmpty():
                continue

            dist = geom.distance(punto_geom)
            if dist < dist_minima:
                dist_minima = dist
                tuberia_cercana = feature

        if tuberia_cercana is None:
            QMessageBox.warning(self.iface.mainWindow(), 'Error',
                                'No se encontro ninguna tuberia cerca del punto')
            return

        geom = tuberia_cercana.geometry()
        vertices = obtener_vertices_linea(geom)
        if not vertices or len(vertices) < 2:
            QMessageBox.warning(self.iface.mainWindow(), 'Error',
                                'La tuberia no tiene vertices validos')
            return

        punto_proyectado = geom.nearestPoint(punto_geom).asPoint()

        # ⭐ Guardamos SOLO claves de negocio (ID_O + Ci + Cf).
        # NUNCA guardamos el feature ni el FID para operaciones posteriores.
        id_o_original = tuberia_cercana.attribute('ID_O')
        ci_original = tuberia_cercana.attribute('Ci')
        cf_original = tuberia_cercana.attribute('Cf')
        cab_ata_original = tuberia_cercana.attribute('cab_ata') or ''

        punto_inicio = vertices[0]
        punto_fin = vertices[-1]

        # ===== OBTENER DOS NUEVOS IDs PARA LAS TUBERIAS =====
        id_tuberia1, id_tuberia2 = self.obtener_dos_nuevos_ids(
            self.capa_tuberias, self.id_sugerido
        )

        # ===== PASO 1: CREAR NUEVA CAMARA =====
        nuevo_id_camara = self.obtener_nuevo_id(self.capa_camaras, self.id_sugerido)
        cota_nueva = extraer_cota_dem(
            self.capa_dem,
            QgsPointXY(punto_proyectado.x(), punto_proyectado.y())
        )

        self.capa_camaras.startEditing()
        new_camara = QgsFeature(self.capa_camaras.fields())
        new_camara.setGeometry(
            QgsGeometry.fromPointXY(QgsPointXY(punto_proyectado.x(), punto_proyectado.y()))
        )

        campos_camara = {}
        for field in self.capa_camaras.fields():
            campos_camara[field.name()] = None

        campos_camara['ID_O'] = nuevo_id_camara
        campos_camara['X'] = round(punto_proyectado.x(), 3)
        campos_camara['Y'] = round(punto_proyectado.y(), 3)
        campos_camara['Z'] = round(cota_nueva, 3) if cota_nueva is not None else -9999.0
        campos_camara['N_Lineas'] = 2
        campos_camara['Lineas_ID'] = ''
        campos_camara['Tipo'] = 'Intermedio'

        new_camara.setAttributes(
            [campos_camara[f.name()] for f in self.capa_camaras.fields()]
        )
        self.capa_camaras.addFeature(new_camara)
        self.capa_camaras.commitChanges()

        # ===== PASO 2: OBTENER COTAS =====
        cota_ci = self.obtener_cota_camara(ci_original)
        cota_cf = self.obtener_cota_camara(cf_original)
        cota_nueva = self.obtener_cota_camara(nuevo_id_camara)

        # ===== PASO 3: CREAR SEGMENTO 1 (Ci → nueva camara) =====
        linea1 = QgsLineString([
            QgsPoint(punto_inicio.x(), punto_inicio.y()),
            QgsPoint(punto_proyectado.x(), punto_proyectado.y())
        ])
        geom1 = QgsGeometry(linea1)
        longitud1 = geom1.length()

        pendiente1 = 0.0
        if cota_ci is not None and cota_nueva is not None and longitud1 > 0:
            pendiente1 = (cota_ci - cota_nueva) / longitud1 * 100

        if punto_proyectado.x() > punto_inicio.x():
            dir1 = '->'
        elif punto_proyectado.x() < punto_inicio.x():
            dir1 = '<-'
        else:
            dir1 = '->' if punto_proyectado.y() > punto_inicio.y() else '<-'

        # ===== PASO 4: CREAR SEGMENTO 2 (nueva camara → Cf) =====
        linea2 = QgsLineString([
            QgsPoint(punto_proyectado.x(), punto_proyectado.y()),
            QgsPoint(punto_fin.x(), punto_fin.y())
        ])
        geom2 = QgsGeometry(linea2)
        longitud2 = geom2.length()

        pendiente2 = 0.0
        if cota_nueva is not None and cota_cf is not None and longitud2 > 0:
            pendiente2 = (cota_nueva - cota_cf) / longitud2 * 100

        if punto_fin.x() > punto_proyectado.x():
            dir2 = '->'
        elif punto_fin.x() < punto_proyectado.x():
            dir2 = '<-'
        else:
            dir2 = '->' if punto_fin.y() > punto_proyectado.y() else '<-'

        # ===== PASO 5: ACTUALIZAR CAMARA DE INICIO (ci_original) =====
        self.actualizar_lineas_id(ci_original, id_o_original, 'quitar')

        # ===== PASO 6: ELIMINAR LA TUBERIA ORIGINAL =====
        # ⭐ Re-localizar por ID_O + Ci + Cf justo antes de borrar.
        tuberia_a_borrar = self._buscar_tuberia_por_id_o(
            id_o_original, ci_original, cf_original
        )

        if tuberia_a_borrar is None:
            QMessageBox.warning(
                self.iface.mainWindow(), 'Error',
                f'No se encontró la tubería original ID_O={id_o_original} '
                f'(Ci={ci_original}, Cf={cf_original}) para eliminar.\n'
                'Puede que el ID_O haya cambiado o la tubería ya no exista.'
            )
            return

        self.capa_tuberias.startEditing()
        self.capa_tuberias.deleteFeature(tuberia_a_borrar.id())
        self.capa_tuberias.commitChanges()

        # ===== PASO 7: CREAR SEGMENTO 1 =====
        campos_tuberia = {}
        for field in self.capa_tuberias.fields():
            campos_tuberia[field.name()] = None

        campos_tuberia['ID_O'] = id_tuberia1
        campos_tuberia['Ci'] = ci_original
        campos_tuberia['Cf'] = nuevo_id_camara
        campos_tuberia['Xi'] = round(punto_inicio.x(), 3)
        campos_tuberia['Yi'] = round(punto_inicio.y(), 3)
        campos_tuberia['Zi'] = round(cota_ci, 3) if cota_ci is not None else -9999.0
        campos_tuberia['Xf'] = round(punto_proyectado.x(), 3)
        campos_tuberia['Yf'] = round(punto_proyectado.y(), 3)
        campos_tuberia['Zf'] = round(cota_nueva, 3) if cota_nueva is not None else -9999.0
        campos_tuberia['L'] = round(longitud1, 3)
        campos_tuberia['S'] = round(pendiente1, 3)
        campos_tuberia['dir'] = dir1
        campos_tuberia['cab_ata'] = cab_ata_original

        self.capa_tuberias.startEditing()
        new_tuberia1 = QgsFeature(self.capa_tuberias.fields())
        new_tuberia1.setGeometry(geom1)
        new_tuberia1.setAttributes(
            [campos_tuberia[f.name()] for f in self.capa_tuberias.fields()]
        )
        self.capa_tuberias.addFeature(new_tuberia1)
        self.capa_tuberias.commitChanges()

        # ===== PASO 8: CREAR SEGMENTO 2 =====
        for key in campos_tuberia:
            campos_tuberia[key] = None

        campos_tuberia['ID_O'] = id_tuberia2
        campos_tuberia['Ci'] = nuevo_id_camara
        campos_tuberia['Cf'] = cf_original
        campos_tuberia['Xi'] = round(punto_proyectado.x(), 3)
        campos_tuberia['Yi'] = round(punto_proyectado.y(), 3)
        campos_tuberia['Zi'] = round(cota_nueva, 3) if cota_nueva is not None else -9999.0
        campos_tuberia['Xf'] = round(punto_fin.x(), 3)
        campos_tuberia['Yf'] = round(punto_fin.y(), 3)
        campos_tuberia['Zf'] = round(cota_cf, 3) if cota_cf is not None else -9999.0
        campos_tuberia['L'] = round(longitud2, 3)
        campos_tuberia['S'] = round(pendiente2, 3)
        campos_tuberia['dir'] = dir2
        campos_tuberia['cab_ata'] = ''

        self.capa_tuberias.startEditing()
        new_tuberia2 = QgsFeature(self.capa_tuberias.fields())
        new_tuberia2.setGeometry(geom2)
        new_tuberia2.setAttributes(
            [campos_tuberia[f.name()] for f in self.capa_tuberias.fields()]
        )
        self.capa_tuberias.addFeature(new_tuberia2)
        self.capa_tuberias.commitChanges()

        # ===== PASO 9: ACTUALIZAR CAMPOS DE CAMARAS =====
        # Nueva cámara: recibe los dos segmentos
        self.actualizar_lineas_id(nuevo_id_camara, id_tuberia1, 'añadir')
        self.actualizar_lineas_id(nuevo_id_camara, id_tuberia2, 'añadir')

        # Cámara final: quitar la tubería original, añadir la nueva
        self.actualizar_lineas_id(cf_original, id_o_original, 'quitar')
        self.actualizar_lineas_id(cf_original, id_tuberia2, 'añadir')

        # Cámara de inicio: el quitar ya se hizo en Paso 5, ahora añadimos la nueva
        self.actualizar_lineas_id(ci_original, id_tuberia1, 'añadir')

        # Desactivar herramienta
        self.iface.mapCanvas().unsetMapTool(self.tool_seleccion)
        self.tool_seleccion = None
        self.modo_edicion = False

        # ===== PASO 10: MOSTRAR RESULTADOS =====
        mensaje = f"=== TUBERIA DIVIDIDA EXITOSAMENTE ===\n\n"
        mensaje += f"📌 Tuberia original eliminada: ID_O={id_o_original}\n\n"
        mensaje += f"📌 Nueva tuberia 1: ID_O={id_tuberia1}\n"
        mensaje += f"   Ci={ci_original} → Cf={nuevo_id_camara}\n"
        mensaje += f"   Longitud: {round(longitud1, 3)} m\n\n"
        mensaje += f"📌 Nueva tuberia 2: ID_O={id_tuberia2}\n"
        mensaje += f"   Ci={nuevo_id_camara} → Cf={cf_original}\n"
        mensaje += f"   Longitud: {round(longitud2, 3)} m\n\n"
        mensaje += f"📌 Nueva camara: ID_O={nuevo_id_camara}\n"
        mensaje += f"   📍 X={round(punto_proyectado.x(), 3)}, Y={round(punto_proyectado.y(), 3)}\n"
        mensaje += f"   📐 Z={round(cota_nueva, 3) if cota_nueva is not None else 'N/A'}\n"
        mensaje += f"   🔗 Lineas conectadas: {id_tuberia1}, {id_tuberia2}\n\n"
        mensaje += f"✅ Longitud total: {round(longitud1 + longitud2, 3)} m"

        QMessageBox.information(
            self.iface.mainWindow(),
            'Tuberia Dividida',
            mensaje
        )