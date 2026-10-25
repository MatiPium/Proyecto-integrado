"""Agregación consistente de metas individuales y resultados colectivos."""
from collections import defaultdict
from .models import MetaFuncionario, Funcionario


def resumen_funcionario(funcionario, metas):
    detalles = []
    for meta in metas:
        objetivo = meta.meta_ajustada
        avance = meta.avance
        cumplimiento = round(min(avance / objetivo * 100, 120), 1) if objetivo else 0
        esperado = meta.avance_esperado
        color = ('sin_meta' if not objetivo else 'verde' if cumplimiento >= esperado else
                 'ambar' if cumplimiento >= esperado * float(meta.periodo.umbral_ambar) / 100 else 'rojo')
        detalles.append(dict(meta=meta, objetivo=objetivo, avance=avance, cumplimiento=cumplimiento,
                             esperado=esperado, semaforo=color, peso=float(meta.item.ponderador)))
    medibles = [d for d in detalles if d['objetivo'] > 0]
    peso = sum(d['peso'] for d in medibles)
    resultado = sum(d['cumplimiento'] * d['peso'] for d in medibles) / peso if peso else None
    esperado = sum(d['esperado'] * d['peso'] for d in medibles) / peso if peso else None
    umbral = float(metas[0].periodo.umbral_ambar) / 100 if metas else .6
    color = ('sin_meta' if resultado is None else 'verde' if resultado >= esperado else
             'ambar' if resultado >= esperado * umbral else 'rojo')
    return dict(funcionario=funcionario, cumplimiento=round(resultado, 1) if resultado is not None else None,
                esperado=round(esperado, 1) if esperado is not None else None, semaforo=color, items=detalles)


def consolidar(nombre, personas):
    medibles = [p for p in personas if p['cumplimiento'] is not None]
    return dict(nombre=nombre, funcionarios=len(personas), evaluados=len(medibles),
                cumplimiento=round(sum(p['cumplimiento'] for p in medibles) / len(medibles), 1) if medibles else None,
                verdes=sum(p['semaforo'] == 'verde' for p in personas),
                ambar=sum(p['semaforo'] == 'ambar' for p in personas),
                rojos=sum(p['semaforo'] == 'rojo' for p in personas),
                sin_meta=len(personas) - len(medibles))


def tablero(periodo, delegaciones):
    usuarios = Funcionario.objects.filter(is_active=True, delegacion__in=delegaciones).select_related('delegacion', 'cargo')
    metas_usuario = defaultdict(list)
    for meta in MetaFuncionario.objects.filter(periodo=periodo, funcionario__in=usuarios).select_related('item', 'periodo', 'funcionario'):
        metas_usuario[meta.funcionario_id].append(meta)
    personas = [resumen_funcionario(u, metas_usuario[u.pk]) for u in usuarios]
    grupos = {clave: defaultdict(list) for clave in ('delegaciones', 'equipos', 'territorios')}
    for p in personas:
        u = p['funcionario']
        grupos['delegaciones'][str(u.delegacion)].append(p)
        grupos['equipos'][f'{u.delegacion} · {u.cargo or "Sin cargo"}'].append(p)
        grupos['territorios'][f'{u.delegacion} · {u.territorio or u.delegacion.sector or "Sin territorio asignado"}'].append(p)
    return dict(individuales=personas, **{clave: [consolidar(nombre, equipo) for nombre, equipo in grupo.items()]
                                        for clave, grupo in grupos.items()})
