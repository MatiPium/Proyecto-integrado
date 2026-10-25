"""Días laborables municipales: lunes a viernes, sin feriados públicos de Chile."""
from datetime import timedelta
from functools import lru_cache
import holidays


@lru_cache(maxsize=32)
def feriados(anio):
    # CO = Región de Coquimbo; excluye feriados exclusivamente bancarios.
    return holidays.country_holidays('CL', subdiv='CO', years=[anio], categories=holidays.PUBLIC)


def dias_habiles(inicio, fin):
    return {dia for n in range(max(0, (fin - inicio).days + 1))
            if (dia := inicio + timedelta(days=n)).weekday() < 5 and dia not in feriados(dia.year)}
