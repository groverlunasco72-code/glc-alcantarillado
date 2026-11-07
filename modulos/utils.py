# -*- coding: utf-8 -*-
from qgis.core import QgsPointXY, QgsLineString, QgsRasterDataProvider

def obtener_vertices_linea(geometria):
    """Obtener los vertices de una linea"""
    vertices = []
    try:
        if geometria.isMultipart():
            for part in geometria.parts():
                if isinstance(part, QgsLineString):
                    for i in range(part.numPoints()):
                        vertices.append(QgsPointXY(part.pointN(i)))
        else:
            if isinstance(geometria, QgsLineString):
                for i in range(geometria.numPoints()):
                    vertices.append(QgsPointXY(geometria.pointN(i)))
            else:
                const_get = geometria.constGet()
                if isinstance(const_get, QgsLineString):
                    for i in range(const_get.numPoints()):
                        vertices.append(QgsPointXY(const_get.pointN(i)))
    except:
        pass
    return vertices

def extraer_cota_dem(layer_dem, punto):
    """Extraer cota del DEM - CORREGIDO para manejar tupla"""
    try:
        provider = layer_dem.dataProvider()
        
        # Usar sample
        try:
            resultado = provider.sample(punto, 1)
            if resultado is not None:
                # resultado es una tupla (valor, ok)
                if isinstance(resultado, tuple) and len(resultado) >= 2:
                    valor = resultado[0]
                    ok = resultado[1]
                    if ok and valor is not None:
                        try:
                            valor_num = float(valor)
                            # Verificar que no sea NoData
                            if valor_num > -9999 and valor_num < 999999:
                                return valor_num
                        except:
                            pass
        except:
            pass
        
        # Fallback con identify
        try:
            resultado = provider.identify(punto, QgsRasterDataProvider.IdentifyFormatValue)
            if resultado.isValid():
                results = resultado.results()
                for key, value in results.items():
                    if value is not None:
                        try:
                            valor_num = float(value)
                            if valor_num > -9999 and valor_num < 999999:
                                return valor_num
                        except:
                            pass
        except:
            pass
        
        return None
        
    except Exception as e:
        print(f"Error al extraer cota: {e}")
        return None