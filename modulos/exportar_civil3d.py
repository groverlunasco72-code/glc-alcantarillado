# -*- coding: utf-8 -*-
"""
Módulo: Exportar Red a Storm Sewers (.stm)

Genera un archivo .stm compatible con:
  • Storm Sewers
  • Storm Sewers for AutoCAD Civil 3D
  • Storm and Sanitary Analysis (SSA)

CÁMARAS: Cilíndricas concéntricas con dimensiones
  "Structure Shape = ","Circ"
  "Structure Length = ",1.20
  "Structure Width = ",1.20

TUBERÍAS: Circulares con diámetro y cotas soleras
  "Line Type = ","Cir"
  "Rise = ",D
  "Invert Elev Up = ",Zs_i
  "Invert Elev Dn = ",Zs_f

CAMPOS LEÍDOS:
  CÁMARAS:
    • ID_O       → nombre de la cámara (Inlet ID)
    • X, Y       → coordenadas
    • Z          → cota terreno
    • Zs_i       → cota solera

  TUBERÍAS:
    • ID_O       → nombre de la tubería (Line ID)
    • Ci_Virtual → cámara inicio (preferido)
    • Ci         → alternativa
    • Cf         → cámara fin
    • Xi,Yi,Zi   → coords y cota terreno inicio
    • Xf,Yf,Zf   → coords y cota terreno fin
    • Zs_i, Zs_f → cotas solera (POR TUBERÍA)
    • D_mm       → diámetro en mm
    • L          → longitud
    • S_diseno   → pendiente
"""

import os
import math

from qgis.core import (
    QgsProject, QgsVectorLayer, QgsWkbTypes,
    QgsCoordinateTransform, QgsApplication
)
from qgis.PyQt.QtWidgets import (
    QMessageBox, QDialog, QVBoxLayout, QLabel, QPushButton,
    QComboBox, QHBoxLayout, QFileDialog, QLineEdit, QGroupBox,
    QDoubleSpinBox, QSpinBox, QFormLayout
)


# ============================================================
# PARÁMETROS POR DEFECTO
# ============================================================
DIAMETRO_CAMARA_DEF = 1.2
DIAMETRO_TUBO_DEF = 200
N_MANNING_DEF = 0.013

CAMPOS_INICIO_PREFERIDOS = ['Ci_Virtual', 'Ci']
CAMPOS_FIN_PREFERIDOS = ['Cf']


class ExportarCivil3D:

    def __init__(self, iface):
        self.iface = iface
        self.capa_tuberias = None
        self.capa_camaras = None
        self._ultima_exportacion = {}

    # ============================================================
    # DIÁLOGO PRINCIPAL
    # ============================================================
    def mostrar_dialogo(self):
        dialog = QDialog(self.iface.mainWindow())
        dialog.setWindowTitle('GLC - Exportar a Storm Sewers')
        dialog.setMinimumWidth(720)
        self.dialog = dialog

        layout = QVBoxLayout()
        titulo = QLabel('<b>🌊 Exportar Red a Storm Sewers (.stm)</b>')
        titulo.setStyleSheet('font-size: 14pt; font-weight: bold;')
        layout.addWidget(titulo)

        info = QLabel(
            'Genera un archivo .stm compatible con:\n'
            '  • Storm Sewers\n'
            '  • Civil 3D (Insert → Import → Storm Sewers)\n'
            '  • Storm and Sanitary Analysis (SSA)\n\n'
            'Cámaras: cilíndricas concéntricas con dimensiones.'
        )
        info.setWordWrap(True)
        layout.addWidget(info)
        layout.addWidget(QLabel('-' * 60))

        # ---- Capas de entrada ----
        grupo_capas = QGroupBox('Capas de entrada')
        form_capas = QFormLayout()

        self.combo_tuberias = QComboBox()
        for layer in QgsProject.instance().mapLayers().values():
            if isinstance(layer, QgsVectorLayer) and \
               layer.geometryType() == QgsWkbTypes.LineGeometry:
                self.combo_tuberias.addItem(layer.name(), layer.id())
        form_capas.addRow('Tuberías:', self.combo_tuberias)

        self.combo_camaras = QComboBox()
        for layer in QgsProject.instance().mapLayers().values():
            if isinstance(layer, QgsVectorLayer) and \
               layer.geometryType() == QgsWkbTypes.PointGeometry:
                self.combo_camaras.addItem(layer.name(), layer.id())
        form_capas.addRow('Cámaras:', self.combo_camaras)

        grupo_capas.setLayout(form_capas)
        layout.addWidget(grupo_capas)

        # ---- Campos de referencia ----
        grupo_ids = QGroupBox('Campos de referencia')
        form_ids = QFormLayout()

        self.combo_id_cam = QComboBox()
        form_ids.addRow('ID cámaras:', self.combo_id_cam)

        self.combo_id_tub = QComboBox()
        form_ids.addRow('ID tuberías:', self.combo_id_tub)

        self.combo_campo_inicio = QComboBox()
        form_ids.addRow('Campo inicio tubería:', self.combo_campo_inicio)

        self.combo_campo_fin = QComboBox()
        form_ids.addRow('Campo fin tubería:', self.combo_campo_fin)

        self.combo_campo_diam = QComboBox()
        form_ids.addRow('Campo diámetro:', self.combo_campo_diam)

        self.combo_camaras.currentIndexChanged.connect(
            lambda: self._refrescar_campos(
                self.combo_camaras, self.combo_id_cam, 'ID_O'
            )
        )
        self.combo_tuberias.currentIndexChanged.connect(
            lambda: self._refrescar_campos_tuberias(
                self.combo_tuberias, self.combo_id_tub,
                self.combo_campo_inicio, self.combo_campo_fin,
                self.combo_campo_diam
            )
        )
        self._refrescar_campos(self.combo_camaras, self.combo_id_cam, 'ID_O')
        self._refrescar_campos_tuberias(
            self.combo_tuberias, self.combo_id_tub,
            self.combo_campo_inicio, self.combo_campo_fin,
            self.combo_campo_diam
        )

        grupo_ids.setLayout(form_ids)
        layout.addWidget(grupo_ids)

        # ---- Parámetros ----
        grupo_geom = QGroupBox('Parámetros de estructuras')
        form_geom = QFormLayout()

        self.spin_diam_cam = QDoubleSpinBox()
        self.spin_diam_cam.setRange(0.5, 30.0)
        self.spin_diam_cam.setValue(DIAMETRO_CAMARA_DEF)
        self.spin_diam_cam.setSuffix(' m')
        self.spin_diam_cam.setDecimals(2)
        self.spin_diam_cam.setSingleStep(0.1)
        self.spin_diam_cam.setToolTip(
            'Diámetro de la cámara cilíndrica.\n'
            'Valores típicos:\n'
            '  • 1.20 m (tuberías Ø200-500 mm)\n'
            '  • 1.50 m (tuberías Ø500-750 mm)\n'
            '  • 1.80 m (tuberías Ø750-900 mm)'
        )
        form_geom.addRow('Ø cámara:', self.spin_diam_cam)

        self.spin_diam_tubo = QSpinBox()
        self.spin_diam_tubo.setRange(100, 3000)
        self.spin_diam_tubo.setValue(DIAMETRO_TUBO_DEF)
        self.spin_diam_tubo.setSuffix(' mm')
        self.spin_diam_tubo.setSingleStep(50)
        form_geom.addRow('Ø por defecto:', self.spin_diam_tubo)

        self.spin_n = QDoubleSpinBox()
        self.spin_n.setRange(0.001, 0.1)
        self.spin_n.setValue(N_MANNING_DEF)
        self.spin_n.setDecimals(4)
        self.spin_n.setSingleStep(0.001)
        form_geom.addRow('Coef. Manning (n):', self.spin_n)

        grupo_geom.setLayout(form_geom)
        layout.addWidget(grupo_geom)

        # ---- Ruta de salida ----
        layout.addWidget(QLabel('-' * 60))
        layout.addWidget(QLabel('Archivo STM de salida:'))
        hbox = QHBoxLayout()
        self.txt_ruta = QLineEdit()
        self.txt_ruta.setPlaceholderText('C:/proyectos/red.stm')
        hbox.addWidget(self.txt_ruta, 1)
        btn = QPushButton('...')
        btn.setMaximumWidth(40)
        btn.clicked.connect(self._seleccionar_ruta)
        hbox.addWidget(btn)
        layout.addLayout(hbox)

        layout.addWidget(QLabel('-' * 60))

        btn_exportar = QPushButton('📤 Generar archivo .stm')
        btn_exportar.setStyleSheet(
            'background-color: #4CAF50; color: white; font-weight: bold; '
            'font-size: 12pt; padding: 8px;'
        )
        btn_exportar.clicked.connect(self._exportar)
        layout.addWidget(btn_exportar)

        btn_cerrar = QPushButton('Cerrar')
        btn_cerrar.setStyleSheet('background-color: #f44336; color: white;')
        btn_cerrar.clicked.connect(dialog.accept)
        layout.addWidget(btn_cerrar)

        dialog.setLayout(layout)
        dialog.exec_()

    # ============================================================
    # REFRESCAR COMBOS
    # ============================================================
    def _refrescar_campos(self, combo_capa, combo_campo, campo_pref):
        combo_campo.clear()
        capa_id = combo_capa.currentData()
        if not capa_id:
            return
        capa = QgsProject.instance().mapLayer(capa_id)
        if not capa:
            return
        nombres = [f.name() for f in capa.fields()]
        combo_campo.addItems(nombres)
        if campo_pref in nombres:
            combo_campo.setCurrentText(campo_pref)

    def _refrescar_campos_tuberias(self, combo_capa, combo_id,
                                    combo_inicio, combo_fin, combo_diam):
        combo_id.clear()
        combo_inicio.clear()
        combo_fin.clear()
        combo_diam.clear()

        capa_id = combo_capa.currentData()
        if not capa_id:
            return
        capa = QgsProject.instance().mapLayer(capa_id)
        if not capa:
            return

        nombres = [f.name() for f in capa.fields()]

        combo_id.addItems(nombres)
        if 'ID_O' in nombres:
            combo_id.setCurrentText('ID_O')

        cand_i = []
        for p in CAMPOS_INICIO_PREFERIDOS:
            if p in nombres:
                cand_i.append(p)
        for n in nombres:
            if n not in cand_i:
                cand_i.append(n)
        combo_inicio.addItems(cand_i)
        if 'Ci_Virtual' in nombres:
            combo_inicio.setCurrentText('Ci_Virtual')
        elif 'Ci' in nombres:
            combo_inicio.setCurrentText('Ci')

        cand_f = []
        for p in CAMPOS_FIN_PREFERIDOS:
            if p in nombres:
                cand_f.append(p)
        for n in nombres:
            if n not in cand_f:
                cand_f.append(n)
        combo_fin.addItems(cand_f)
        if 'Cf' in nombres:
            combo_fin.setCurrentText('Cf')

        combo_diam.addItems(nombres)
        if 'D_mm' in nombres:
            combo_diam.setCurrentText('D_mm')

    # ============================================================
    # RUTA DE SALIDA
    # ============================================================
    def _seleccionar_ruta(self):
        ruta, _ = QFileDialog.getSaveFileName(
            self.iface.mainWindow(), 'Guardar STM', '',
            'Storm Sewers (*.stm)'
        )
        if ruta:
            if not ruta.lower().endswith('.stm'):
                ruta += '.stm'
            self.txt_ruta.setText(ruta)

    # ============================================================
    # UTILIDADES
    # ============================================================
    @staticmethod
    def _to_float(v):
        if v is None:
            return None
        try:
            return float(v)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _safe_id(s):
        """Limpia un ID para que no rompa el parser de Civil 3D."""
        if s is None:
            return ''
        return str(s).replace('"', '').replace('\n', '') \
                     .replace('\r', '').strip()

    # ============================================================
    # LECTURA DE CÁMARAS
    # ============================================================
    def _leer_camaras(self):
        capa = self.capa_camaras
        crs = QgsProject.instance().crs()
        try:
            tr = QgsCoordinateTransform(capa.crs(), crs, QgsProject.instance())
        except Exception:
            tr = None

        campos = capa.fields()
        campo_id = self.combo_id_cam.currentText()
        idx_id = campos.indexFromName(campo_id) if campo_id else -1
        if idx_id == -1:
            idx_id = campos.indexFromName('ID_O')

        idx_x = campos.indexFromName('X')
        idx_y = campos.indexFromName('Y')
        idx_z = campos.indexFromName('Z')
        idx_zs = campos.indexFromName('Zs_i')
        if idx_zs == -1:
            idx_zs = campos.indexFromName('Zs')

        resultado = {}
        for feat in capa.getFeatures():
            geom = feat.geometry()
            if geom is None or geom.isEmpty():
                continue
            pt = geom.asPoint()
            if tr is not None:
                try:
                    pt = tr.transform(pt)
                except Exception:
                    pass

            if idx_x != -1 and idx_y != -1:
                xv = self._to_float(feat.attribute(idx_x))
                yv = self._to_float(feat.attribute(idx_y))
                x, y = (xv, yv) if (xv is not None and yv is not None) \
                       else (pt.x(), pt.y())
            else:
                x, y = pt.x(), pt.y()

            z_t = self._to_float(feat.attribute(idx_z)) if idx_z != -1 else None
            z_s = self._to_float(feat.attribute(idx_zs)) if idx_zs != -1 else None

            if z_t is None and z_s is not None:
                z_t = z_s + 1.5
            if z_s is None and z_t is not None:
                z_s = z_t - 1.5
            if z_t is None and z_s is None:
                continue

            id_val = feat.attribute(idx_id) if idx_id != -1 else None
            id_str = self._safe_id(id_val)
            if not id_str:
                continue

            resultado[id_str] = {
                'id': id_str,
                'x': x, 'y': y,
                'z_terreno': z_t,
                'z_solera': z_s,
            }

        return resultado

    # ============================================================
    # LECTURA DE TUBERÍAS
    # ============================================================
    def _leer_tuberias(self):
        capa = self.capa_tuberias
        crs = QgsProject.instance().crs()
        try:
            tr = QgsCoordinateTransform(capa.crs(), crs, QgsProject.instance())
        except Exception:
            tr = None

        campos = capa.fields()

        campo_id_tub = self.combo_id_tub.currentText()
        idx_id = campos.indexFromName(campo_id_tub) if campo_id_tub else -1
        if idx_id == -1:
            idx_id = campos.indexFromName('ID_O')

        campo_inicio = self.combo_campo_inicio.currentText()
        idx_ci = campos.indexFromName(campo_inicio) if campo_inicio else -1

        campo_fin = self.combo_campo_fin.currentText()
        idx_cf = campos.indexFromName(campo_fin) if campo_fin else -1

        campo_diam = self.combo_campo_diam.currentText()
        idx_d = campos.indexFromName(campo_diam) if campo_diam else -1

        idx_xi = campos.indexFromName('Xi')
        idx_yi = campos.indexFromName('Yi')
        idx_xf = campos.indexFromName('Xf')
        idx_yf = campos.indexFromName('Yf')
        idx_zsi = campos.indexFromName('Zs_i')
        idx_zsf = campos.indexFromName('Zs_f')
        idx_zi = campos.indexFromName('Zi')
        idx_zf = campos.indexFromName('Zf')
        idx_l = campos.indexFromName('L')
        idx_s = campos.indexFromName('S_diseno')

        resultado = []
        for feat in capa.getFeatures():
            try:
                xi = float(feat.attribute(idx_xi))
                yi = float(feat.attribute(idx_yi))
                xf = float(feat.attribute(idx_xf))
                yf = float(feat.attribute(idx_yf))
            except (TypeError, ValueError):
                geom = feat.geometry()
                if geom is None or geom.isEmpty():
                    continue
                linea = geom.asPolyline()
                if not linea or len(linea) < 2:
                    continue
                p0, p1 = linea[0], linea[-1]
                if tr is not None:
                    try:
                        p0 = tr.transform(p0)
                        p1 = tr.transform(p1)
                    except Exception:
                        pass
                xi, yi = p0.x(), p0.y()
                xf, yf = p1.x(), p1.y()

            zsi = self._to_float(feat.attribute(idx_zsi)) if idx_zsi != -1 else None
            zsf = self._to_float(feat.attribute(idx_zsf)) if idx_zsf != -1 else None

            zi = self._to_float(feat.attribute(idx_zi)) if idx_zi != -1 else None
            zf = self._to_float(feat.attribute(idx_zf)) if idx_zf != -1 else None

            if zsi is None and zi is not None:
                zsi = zi - 1.5
            if zsf is None and zf is not None:
                zsf = zf - 1.5
            if zi is None and zsi is not None:
                zi = zsi + 1.5
            if zf is None and zsf is not None:
                zf = zsf + 1.5

            if zsi is None or zsf is None:
                continue

            d_raw = self._to_float(feat.attribute(idx_d)) if idx_d != -1 else None
            d_mm = None
            if d_raw is not None:
                if d_raw > 20:
                    d_mm = d_raw
                elif d_raw > 0:
                    d_mm = d_raw * 1000.0
            if d_mm is None or d_mm <= 0:
                d_mm = float(self.spin_diam_tubo.value())
            if abs(d_mm - round(d_mm)) < 0.5:
                d_mm = float(round(d_mm))
            d_m = d_mm / 1000.0

            L = self._to_float(feat.attribute(idx_l)) if idx_l != -1 else None
            if L is None or L <= 0:
                L = math.hypot(xf - xi, yf - yi)
            if L < 1e-6:
                continue

            s = self._to_float(feat.attribute(idx_s)) if idx_s != -1 else None
            if s is None:
                s = (zsi - zsf) / L

            ci = None
            if idx_ci != -1:
                ci = feat.attribute(idx_ci)
                if (ci is None or str(ci).strip() == '') and campo_inicio != 'Ci':
                    idx_ci_alt = campos.indexFromName('Ci')
                    if idx_ci_alt != -1:
                        ci_alt = feat.attribute(idx_ci_alt)
                        if ci_alt is not None:
                            ci = ci_alt

            cf = None
            if idx_cf != -1:
                cf = feat.attribute(idx_cf)

            id_val = feat.attribute(idx_id) if idx_id != -1 else None
            id_str = self._safe_id(id_val)
            if not id_str:
                id_str = f'TUB_{len(resultado)}'

            resultado.append({
                'id': id_str,
                'ci': self._safe_id(ci),
                'cf': self._safe_id(cf),
                'xi': xi, 'yi': yi, 'zi': zi, 'zsi': zsi,
                'xf': xf, 'yf': yf, 'zf': zf, 'zsf': zsf,
                'diametro_mm': d_mm, 'd_m': d_m,
                'longitud': L, 'pendiente': s,
            })

        return resultado

    # ============================================================
    # EXPORTAR
    # ============================================================
    def _exportar(self):
        ruta = self.txt_ruta.text().strip()
        if not ruta:
            QMessageBox.warning(self.iface.mainWindow(), 'Error',
                                'Selecciona una ruta de salida.')
            return
        if not ruta.lower().endswith('.stm'):
            ruta += '.stm'

        tub_id = self.combo_tuberias.currentData()
        cam_id = self.combo_camaras.currentData()

        self.capa_tuberias = QgsProject.instance().mapLayer(tub_id) if tub_id else None
        self.capa_camaras = QgsProject.instance().mapLayer(cam_id) if cam_id else None

        if not self.capa_tuberias:
            QMessageBox.warning(self.iface.mainWindow(), 'Error',
                                'Selecciona la capa de tuberías.')
            return

        try:
            camaras = self._leer_camaras() if self.capa_camaras else {}
            tuberias = self._leer_tuberias()
        except Exception as e:
            QMessageBox.critical(self.iface.mainWindow(), 'Error',
                                 f'Error leyendo datos:\n{e}')
            return

        if not tuberias:
            QMessageBox.warning(self.iface.mainWindow(), 'Error',
                                'No hay tuberías para exportar.')
            return

        # Inferir cámaras faltantes desde tuberías
        for t in tuberias:
            for id_c, x, y, z_sol, z_terr in [
                (t['ci'], t['xi'], t['yi'], t['zsi'], t['zi']),
                (t['cf'], t['xf'], t['yf'], t['zsf'], t['zf'])
            ]:
                if not id_c:
                    continue
                if id_c not in camaras:
                    camaras[id_c] = {
                        'id': id_c, 'x': x, 'y': y,
                        'z_terreno': z_terr if z_terr is not None else z_sol + 1.5,
                        'z_solera': z_sol,
                    }

        try:
            contenido = self._generar_stm(
                camaras, tuberias,
                self.spin_diam_cam.value(),
                self.spin_n.value()
            )
            # Storm Sewers / Civil 3D espera codificación ANSI (cp1252)
            with open(ruta, 'w', encoding='cp1252', newline='\r\n') as f:
                f.write(contenido)
        except Exception as e:
            QMessageBox.critical(self.iface.mainWindow(), 'Error',
                                 f'No se pudo escribir:\n{e}')
            return

        if not os.path.exists(ruta):
            QMessageBox.warning(self.iface.mainWindow(), 'Error',
                                f'El archivo no se creó:\n{ruta}')
            return

        diametros = {}
        for t in tuberias:
            d = round(t['diametro_mm'], 1)
            diametros[d] = diametros.get(d, 0) + 1

        msg = (f'✅ Archivo STM generado\n\n'
               f'📁 {ruta}\n'
               f'📦 {os.path.getsize(ruta):,} bytes\n\n'
               f'📊 Cámaras: {len(camaras)}\n'
               f'📊 Tuberías: {len(tuberias)}\n\n'
               f'📏 Diámetros usados:\n')
        for d in sorted(diametros.keys()):
            msg += f'   • Ø{int(d) if d == int(d) else d} mm → {diametros[d]}\n'

        msg += (f'\n🔵 Cámaras cilíndricas:\n'
                f'   Shape = Circ\n'
                f'   Ø = {self.spin_diam_cam.value():.2f} m\n\n'
                f'📌 Importar en:\n'
                f'   • Storm Sewers\n'
                f'   • Civil 3D → Insert → Import → Storm Sewers\n'
                f'   • Storm and Sanitary Analysis (SSA)')

        QMessageBox.information(self.iface.mainWindow(),
                                'STM generado', msg)

    # ============================================================
    # GENERAR .STM
    # ============================================================
    def _generar_stm(self, camaras, tuberias, diam_camara, n_manning):
        """Genera el contenido del archivo .stm para Storm Sewers."""
        out = []
        W = out.append

        # ---- Cabecera ----
        W('"Storm Sewers for AutoCAD Civil 3D 2018"')
        W('"Project Name = ","GLC Export"')
        W('"SI Units? = ",#TRUE#')
        W(f'"Total No. Lines = ",{len(tuberias)}')
        W('"Starting HGL = ",0')
        W('"Return Period Index = ",2')
        W('"Min Cover = ",1')
        W('"Zero Min Cover at outfalls = ",#FALSE#')
        W('"Design Vel = ",3')
        W('"Min Slope = ",0')
        W('"Max Slope = ",10')
        W('"Min Pipe Size = ",150')
        W('"Max Pipe Size = ",2000')
        W(f'"Default Pipe n-value = ",{n_manning}')
        W('"Omit 21-inch pipes = ",#FALSE#')
        W('"Omit 27-inch pipes = ",#FALSE#')
        W('"Omit 33-inch pipes = ",#FALSE#')
        W('"Design Alignment = ",0')
        W('"Allow smaller downstream pipe sizes = ",#FALSE#')
        W('"N-Value of Inlets = ",0.016')
        W('"Grate Design Depth = ",0.299')
        W('"Composite C1 = ",0.2')
        W('"Composite C2 = ",0.5')
        W('"Composite C3 = ",0.9')
        W('"Min. Starting Depth = ","Normal"')
        W('"Accumulate Known Qs = ",#TRUE#')
        W('"Use Inlet Captured Flows in System = ",#FALSE#')
        W('"Auto Compute Junct. Loss Coeff. = ",#TRUE#')
        W('"Supress Pipe Travel Time = ",#FALSE#')
        W('"Minimum Tc used to calc Intensity",5')
        W('"Check for Inlet Control? = ",#FALSE#')
        W('"Correct for EGL discrepancy = ",#FALSE#')
        W('"Using HDS-5 Method? = ",#FALSE#')
        W('"Curb Opening = ","Horiz"')
        W('"LINE DATA ============================="')
        W('"Network Name = ","Network-1"')

        # Mapa: cámara inicio → número de línea (downstream line)
        line_no_by_cam = {}
        for i, t in enumerate(tuberias, start=1):
            if t['ci']:
                line_no_by_cam[t['ci']] = i

        # Valor entero o decimal para Structure Length/Width
        if abs(diam_camara - round(diam_camara)) < 1e-6:
            diam_cam_str = str(int(round(diam_camara)))
        else:
            diam_cam_str = f'{diam_camara:.2f}'

        # ---- Cada línea (tubería) ----
        for i, t in enumerate(tuberias, start=1):
            down_line = line_no_by_cam.get(t['cf'], 0)

            ci_id = self._safe_id(t['ci']) if t['ci'] else f'C{i}'
            cf_id = self._safe_id(t['cf']) if t['cf'] else f'C{i+1}'
            line_id = self._safe_id(t['id']) if t['id'] else f'L{i}'

            # ═══════════════════════════════════════════════════════
            # CADA TUBERÍA USA SU PROPIA Zs_i / Zs_f
            # (del shapefile de tuberías). La cámara solo se usa
            # como fallback si la tubería no tuviera valor.
            # ═══════════════════════════════════════════════════════
            cam_ci = camaras.get(ci_id, {})
            cam_cf = camaras.get(cf_id, {})

            z_sol_up = t['zsi'] if t['zsi'] is not None else cam_ci.get('z_solera')
            z_sol_dn = t['zsf'] if t['zsf'] is not None else cam_cf.get('z_solera')

            z_terr_up = t['zi'] if t['zi'] is not None else cam_ci.get('z_terreno')
            z_terr_dn = t['zf'] if t['zf'] is not None else cam_cf.get('z_terreno')

            # Seguridad: si algo quedó None, evitar crash
            if z_sol_up is None:
                z_sol_up = z_terr_up if z_terr_up is not None else 0.0
            if z_sol_dn is None:
                z_sol_dn = z_terr_dn if z_terr_dn is not None else 0.0
            if z_terr_up is None:
                z_terr_up = z_sol_up + 1.5
            if z_terr_dn is None:
                z_terr_dn = z_sol_dn + 1.5

            d_m = t['d_m']

            W(f'"Line No. = ",{i}')
            W(f'"Line ID = ","{line_id}"')
            W(f'"Downstream Line No. = ",{down_line}')
            W(f'"X,Y Coord Dn = ",{t["xf"]:.2f},{t["yf"]:.2f}')
            W(f'"X,Y Coord Up = ",{t["xi"]:.2f},{t["yi"]:.2f}')
            W('"Deflection Angle = ",0')
            W('"Bearing = ",0')
            W('"Known Q = ",0')
            W('"Sub Drainage Area 1 = ",0')
            W('"Sub Drainage Area 2 = ",0')
            W('"Sub Drainage Area 3 = ",0')
            W('"Drainage Area = ",0')
            W('"Runoff Coeff. = ",0')
            W('"Inlet Time = ",0')
            W(f'"Line Length = ",{t["longitud"]:.2f}')
            W(f'"Invert Elev Dn = ",{z_sol_dn:.3f}')
            W(f'"Line Slope = ",{abs(t["pendiente"]):.4f}')
            W(f'"Invert Elev Up = ",{z_sol_up:.3f}')
            W(f'"Rise = ",{d_m:.3f}')
            W('"Span = ",0')
            W('"No. Barrels = ",1')
            W(f'"N-Value = ",{n_manning}')
            W('"Line Type = ","Cir"')
            W('"Line Part ID = ",""')
            W('"Line Part Description = ",""')
            W('"Junction Loss Coeff = ",0.75')
            W(f'"Ground / Rim Elev Dn = ",{z_terr_dn:.3f}')
            W(f'"Ground / Rim Elev Up = ",{z_terr_up:.3f}')
            W('"Junction Type = ",0')
            W('"Junction Part ID = ",""')
            W('"Junction Part Description = ",""')
            W('"User def. Sta = ",0,0')

            # Bloque USER — patrón EXACTO de Civil 3D (35 líneas)
            W('"User"')
            for _ in range(6):
                W('0')
            W('""')
            for _ in range(9):
                W('0')
            W('""')
            for _ in range(11):
                W('0')
            W('""')
            for _ in range(5):
                W('0')

            # HGL / EGL (EGL = HGL)
            hgl_dn = z_sol_dn + d_m * 0.8
            hgl_up = z_sol_up + d_m * 0.8
            W(f'"HGL Down = ",{hgl_dn:.2f}')
            W(f'"HGL Up = ",{hgl_up:.2f}')
            W(f'"HGL Junct = ",{hgl_up:.2f}')
            W(f'"EGL Down = ",{hgl_dn:.2f}')
            W(f'"EGL Up = ",{hgl_up:.2f}')
            W(f'"EGL Junct = ",{hgl_up:.2f}')
            W('"Velocity Down = ",0')
            W('"Velocity Up = ",0')
            W('"Downstream Inlet No. = ",0')
            W('"Inlet Length = ",0')
            W('"Inlet throat height = ",0')
            W('"Grate Opening Area = ",0')
            W('"Grate Width = ",0')
            W('"Grate Length = ",0')
            W('"Known Capacity = ",0')
            W('"Gutter Width = ",0')
            W('"Gutter Slope = ",0')
            W('"Inlet Cross Slope Sw = ",0')
            W('"Inlet Cross Slope Sx = ",0')
            W('"Inlet Sag = ",0')
            W(f'"Inlet ID = ","{ci_id}"')
            W('"Local Inlet Depression = ",0')
            W(f'"Gutter N-Value = ",{n_manning}')

            # CÁMARA
            W('"Structure Shape = ","Circ"')
            W(f'"Structure Length = ",{diam_cam_str}')
            W(f'"Structure Width = ",{diam_cam_str}')
            W('"---------------------------------------"')

        # ---- Pie: IDF Curves ----
        W('0')
        W('"IDF Curves"')
        W('"FHA"')
        W('13.452,11.042,12.04,11.821,11.872,13.484,13.061,11.616')
        W('-6.0715,-2.3933,-2.741,-2.2976,-1.7455,-1.8356,-0.9752,2.1634')
        W('1.3028,-0.0252,0.0441,-0.0711,-0.2616,-0.3336,-0.5518,-2.005')
        W('-0.124,0.0229,0.0161,0.0243,0.042,0.049,0.0643,0.263')
        W('6.54,4.31,3.01,1.95')
        W('7.22,4.83,3.41,2.31')
        W('7.71,5.26,3.76,2.66')
        W('8.24,5.86,4.14,2.89')
        W('8.86,6.36,4.56,3.22')
        W('9.57,7.04,5.11,3.74')
        W('10.33,7.65,5.61,4.23')
        W('11,8.22,6.12,4.8')
        W('sampleFHA.IDF')
        W('#FALSE#,"",""')
        W('1,0,1,0')
        W('#FALSE#,"",""')
        W('"Number of Parcel lines = ",0')
        W('"Number of Parcel circles = ",0')
        W('1,0,1,0')
        W('  END OF FILE')

        return '\n'.join(out) + '\n'

    def desactivar(self, mostrar_mensaje=True):
        pass