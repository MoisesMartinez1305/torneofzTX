from flask import Flask, render_template, request, redirect, url_for, session, flash, send_from_directory
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps
import os
from itertools import combinations, zip_longest
import random
from collections import defaultdict
from datetime import datetime, timedelta

app = Flask(__name__)
app.secret_key = os.urandom(24).hex()
app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv('DATABASE_URL')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

# Modelos de la base de datos
class Torneo(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(100), nullable=False, default="Torneo Principal")
    formato_liga = db.Column(db.String(20), default="ida_vuelta")  # 'ida_vuelta', 'solo_ida'
    categorias = db.relationship('Categoria', backref='torneo', lazy=True)
    grupos_copa = db.relationship('GrupoCopa', backref='torneo', lazy=True)

class Categoria(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(50), nullable=False)
    tiene_liga = db.Column(db.Boolean, default=True)
    tiene_copa = db.Column(db.Boolean, default=False)
    num_grupos_copa = db.Column(db.Integer, default=0)
    torneo_id = db.Column(db.Integer, db.ForeignKey('torneo.id'), nullable=False)
    equipos = db.relationship('Equipo', backref='categoria', lazy=True)
    partidos = db.relationship('Partido', backref='categoria', lazy=True)

class GrupoCopa(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(50), nullable=False)
    categoria_id = db.Column(db.Integer, db.ForeignKey('categoria.id'), nullable=False)
    torneo_id = db.Column(db.Integer, db.ForeignKey('torneo.id'), nullable=False)
    equipos = db.relationship('EquipoCopa', backref='grupo', lazy=True)
    partidos = db.relationship('PartidoCopa', backref='grupo', lazy=True)

class Equipo(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(50), nullable=False)
    categoria_id = db.Column(db.Integer, db.ForeignKey('categoria.id'), nullable=False)
    puntos = db.Column(db.Integer, default=0)
    goles_favor = db.Column(db.Integer, default=0)
    goles_contra = db.Column(db.Integer, default=0)
    diferencia_goles = db.Column(db.Integer, default=0)
    partidos_jugados = db.Column(db.Integer, default=0)

class EquipoCopa(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(50), nullable=False)
    grupo_id = db.Column(db.Integer, db.ForeignKey('grupo_copa.id'), nullable=False)
    categoria_id = db.Column(db.Integer, db.ForeignKey('categoria.id'), nullable=False)
    puntos = db.Column(db.Integer, default=0)
    goles_favor = db.Column(db.Integer, default=0)
    goles_contra = db.Column(db.Integer, default=0)
    diferencia_goles = db.Column(db.Integer, default=0)
    partidos_jugados = db.Column(db.Integer, default=0)

class Partido(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    jornada = db.Column(db.Integer, nullable=False)
    fecha = db.Column(db.DateTime)
    categoria_id = db.Column(db.Integer, db.ForeignKey('categoria.id'), nullable=False)
    equipo_local = db.Column(db.String(50), nullable=False)
    equipo_visitante = db.Column(db.String(50), nullable=False)
    goles_local = db.Column(db.Integer)
    goles_visitante = db.Column(db.Integer)
    jugado = db.Column(db.Boolean, default=False)
    es_descanso = db.Column(db.Boolean, default=False)  # Nuevo campo para identificar descansos
    equipo_descansa = db.Column(db.String(50))  # Nuevo campo para guardar qué equipo descansa

class PartidoCopa(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    fase = db.Column(db.String(20), nullable=False)  # 'grupos', 'octavos', 'cuartos', 'semifinal', 'final'
    grupo_id = db.Column(db.Integer, db.ForeignKey('grupo_copa.id'), nullable=True)
    categoria_id = db.Column(db.Integer, db.ForeignKey('categoria.id'), nullable=False)
    fecha = db.Column(db.DateTime)
    equipo_local = db.Column(db.String(50), nullable=False)
    equipo_visitante = db.Column(db.String(50), nullable=False)
    goles_local = db.Column(db.Integer)
    goles_visitante = db.Column(db.Integer)
    jugado = db.Column(db.Boolean, default=False)

# Usuario administrador
ADMIN_USER = {
    "username": "Moy",
    "password": generate_password_hash("5de8619a2f")
}

# Decorador para rutas de administrador
def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'admin_logged_in' not in session:
            flash('Acceso denegado: Se requieren credenciales de administrador', 'danger')
            return redirect(url_for('admin_login'))
        return f(*args, **kwargs)
    return decorated_function

# Funciones auxiliares mejoradas
def crear_calendario_liga(equipos, categoria_id, formato_liga="ida_vuelta"):
    n = len(equipos)
    if n < 2:
        flash('Se necesitan al menos 2 equipos para crear una liga', 'danger')
        return

    # Si el número de equipos es impar, agregar un equipo ficticio "Descanso"
    tiene_descanso = n % 2 != 0
    if tiene_descanso:
        equipos.append("Descanso")
        n += 1

    fecha_inicio = datetime.now()
    jornadas = defaultdict(list)
    descansos = defaultdict(list)  # Almacenar los equipos en descanso
    jornada_actual = 1

    # Generar el calendario usando el algoritmo de round-robin
    for i in range(n - 1):  # n-1 jornadas para "solo ida"
        for j in range(n // 2):
            local = equipos[j]
            visitante = equipos[-(j + 1)]

            # Si uno de los equipos es "Descanso", registrar el descanso
            if local == "Descanso" or visitante == "Descanso":
                equipo_descansa = visitante if local == "Descanso" else local
                descansos[jornada_actual].append(equipo_descansa)
            else:
                # Alternar local y visitante para que sea equitativo
                if jornada_actual % 2 == 0:
                    local, visitante = visitante, local

                partido = Partido(
                    jornada=jornada_actual,
                    categoria_id=categoria_id,
                    equipo_local=local,
                    equipo_visitante=visitante,
                    fecha=fecha_inicio + timedelta(days=(jornada_actual - 1) * 7)
                )
                db.session.add(partido)
                jornadas[jornada_actual].append(partido)

        # Rotar los equipos para la siguiente jornada (excepto el primero)
        equipos = [equipos[0]] + [equipos[-1]] + equipos[1:-1]
        jornada_actual += 1

    # Crear partidos de vuelta solo si es ida y vuelta
    if formato_liga == "ida_vuelta":
        num_jornadas_ida = jornada_actual - 1
        for j in range(1, num_jornadas_ida + 1):
            for partido in jornadas[j]:
                fecha_partido = fecha_inicio + timedelta(days=(j + num_jornadas_ida - 1) * 7)
                partido_vuelta = Partido(
                    jornada=j + num_jornadas_ida,
                    categoria_id=categoria_id,
                    equipo_local=partido.equipo_visitante,
                    equipo_visitante=partido.equipo_local,
                    fecha=fecha_partido
                )
                db.session.add(partido_vuelta)

    # Guardar los cambios en la base de datos
    db.session.commit()

    # Mostrar los descansos en la parte superior de cada jornada
    for jornada, equipos_descansan in descansos.items():
        print(f"Jornada {jornada}: Equipos en descanso: {', '.join(equipos_descansan)}")

def crear_fase_grupos_copa(equipos, categoria_id, num_grupos=4):
    fecha_inicio = datetime.now()
    random.shuffle(equipos)
    equipos_por_grupo = len(equipos) // num_grupos
    categoria = Categoria.query.get(categoria_id)
    grupos = []
    
    for i in range(num_grupos):
        grupo = GrupoCopa(
            nombre=f"Grupo {chr(65+i)}",
            categoria_id=categoria_id,
            torneo_id=categoria.torneo_id
        )
        db.session.add(grupo)
        db.session.flush()
        
        grupo_equipos = equipos[i*equipos_por_grupo:(i+1)*equipos_por_grupo]
        for equipo in grupo_equipos:
            db.session.add(EquipoCopa(
                nombre=equipo,
                grupo_id=grupo.id,
                categoria_id=categoria_id
            ))
        
        # Crear partidos de ida
        fecha_actual = fecha_inicio
        for local, visitante in combinations(grupo_equipos, 2):
            db.session.add(PartidoCopa(
                fase="grupos",
                grupo_id=grupo.id,
                categoria_id=categoria_id,
                equipo_local=local,
                equipo_visitante=visitante,
                fecha=fecha_actual
            ))
            fecha_actual += timedelta(days=7)  # 1 semana entre partidos
        
        # Crear partidos de vuelta
        fecha_actual = fecha_inicio + timedelta(days=len(list(combinations(grupo_equipos, 2))) * 7)
        for visitante, local in combinations(grupo_equipos, 2):
            db.session.add(PartidoCopa(
                fase="grupos",
                grupo_id=grupo.id,
                categoria_id=categoria_id,
                equipo_local=local,
                equipo_visitante=visitante,
                fecha=fecha_actual
            ))
            fecha_actual += timedelta(days=7)  # Incrementar la fecha para el siguiente partido
        
        grupos.append(grupo)
    
    return grupos

def crear_fase_eliminatoria(categoria_id, equipos_clasificados):
    """Crea la fase eliminatoria de la copa (cuartos, semifinal, final)"""
    if len(equipos_clasificados) < 2:
        return
    
    categoria = Categoria.query.get(categoria_id)
    num_partidos = len(equipos_clasificados) // 2
    fases = {
        8: "cuartos",
        4: "semifinal",
        2: "final"
    }
    
    fase_actual = fases.get(len(equipos_clasificados), "eliminatoria")
    fecha_inicio = datetime.now() + timedelta(days=7)
    
    # Emparejar equipos (1° vs último, 2° vs penúltimo, etc.)
    emparejamientos = list(zip_longest(
        equipos_clasificados[:num_partidos],
        reversed(equipos_clasificados[num_partidos:]),
        fillvalue=None
    ))
    
    for i, (local, visitante) in enumerate(emparejamientos):
        if local and visitante:
            db.session.add(PartidoCopa(
                fase=fase_actual,
                categoria_id=categoria_id,
                equipo_local=local,
                equipo_visitante=visitante,
                fecha=fecha_inicio + timedelta(days=i*7)
            ))

def revertir_estadisticas(partido, es_copa=False):
    if es_copa:
        equipo_local = EquipoCopa.query.filter_by(
            nombre=partido.equipo_local, 
            categoria_id=partido.categoria_id
        ).first()
        equipo_visitante = EquipoCopa.query.filter_by(
            nombre=partido.equipo_visitante,
            categoria_id=partido.categoria_id
        ).first()
    else:
        equipo_local = Equipo.query.filter_by(
            nombre=partido.equipo_local, 
            categoria_id=partido.categoria_id
        ).first()
        equipo_visitante = Equipo.query.filter_by(
            nombre=partido.equipo_visitante,
            categoria_id=partido.categoria_id
        ).first()
    
    if equipo_local and equipo_visitante and not partido.es_descanso:
        equipo_local.goles_favor -= partido.goles_local or 0
        equipo_local.goles_contra -= partido.goles_visitante or 0
        equipo_visitante.goles_favor -= partido.goles_visitante or 0
        equipo_visitante.goles_contra -= partido.goles_local or 0
        
        if (partido.goles_local or 0) > (partido.goles_visitante or 0):
            equipo_local.puntos -= 3
        elif (partido.goles_local or 0) < (partido.goles_visitante or 0):
            equipo_visitante.puntos -= 3
        else:
            equipo_local.puntos -= 1
            equipo_visitante.puntos -= 1
        
        equipo_local.diferencia_goles = equipo_local.goles_favor - equipo_local.goles_contra
        equipo_visitante.diferencia_goles = equipo_visitante.goles_favor - equipo_visitante.goles_contra
        equipo_local.partidos_jugados -= 1
        equipo_visitante.partidos_jugados -= 1

def actualizar_estadisticas(partido, es_nuevo=True, es_copa=False):
    if es_copa:
        equipo_local = EquipoCopa.query.filter_by(
            nombre=partido.equipo_local,
            categoria_id=partido.categoria_id
        ).first()
        equipo_visitante = EquipoCopa.query.filter_by(
            nombre=partido.equipo_visitante,
            categoria_id=partido.categoria_id
        ).first()
    else:
        equipo_local = Equipo.query.filter_by(
            nombre=partido.equipo_local,
            categoria_id=partido.categoria_id
        ).first()
        equipo_visitante = Equipo.query.filter_by(
            nombre=partido.equipo_visitante,
            categoria_id=partido.categoria_id
        ).first()
    
    if equipo_local and equipo_visitante and not partido.es_descanso:
        if es_nuevo:
            equipo_local.partidos_jugados += 1
            equipo_visitante.partidos_jugados += 1
        
        equipo_local.goles_favor += partido.goles_local or 0
        equipo_local.goles_contra += partido.goles_visitante or 0
        equipo_local.diferencia_goles = equipo_local.goles_favor - equipo_local.goles_contra
        
        equipo_visitante.goles_favor += partido.goles_visitante or 0
        equipo_visitante.goles_contra += partido.goles_local or 0
        equipo_visitante.diferencia_goles = equipo_visitante.goles_favor - equipo_visitante.goles_contra
        
        if es_nuevo:
            if (partido.goles_local or 0) > (partido.goles_visitante or 0):
                equipo_local.puntos += 3
            elif (partido.goles_local or 0) < (partido.goles_visitante or 0):
                equipo_visitante.puntos += 3
            else:
                equipo_local.puntos += 1
                equipo_visitante.puntos += 1

def calcular_estadisticas_equipo(equipo, es_copa=False):
    if es_copa:
        partidos = PartidoCopa.query.filter(
            ((PartidoCopa.equipo_local == equipo.nombre) | 
             (PartidoCopa.equipo_visitante == equipo.nombre)) & 
            (PartidoCopa.jugado == True) &
            (PartidoCopa.categoria_id == equipo.categoria_id)
        ).all()
    else:
        partidos = Partido.query.filter(
            ((Partido.equipo_local == equipo.nombre) | 
             (Partido.equipo_visitante == equipo.nombre)) & 
            (Partido.jugado == True) &
            (Partido.categoria_id == equipo.categoria_id) &
            (Partido.es_descanso == False)  # Excluir partidos de descanso
        ).all()
    
    stats = {'ganados': 0, 'empatados': 0, 'perdidos': 0}
    
    for partido in partidos:
        if partido.equipo_local == equipo.nombre:
            goles_favor = partido.goles_local or 0
            goles_contra = partido.goles_visitante or 0
        else:
            goles_favor = partido.goles_visitante or 0
            goles_contra = partido.goles_local or 0
        
        if goles_favor > goles_contra:
            stats['ganados'] += 1
        elif goles_favor < goles_contra:
            stats['perdidos'] += 1
        else:
            stats['empatados'] += 1
    
    return stats

def calcular_stats_para_tabla(tabla, es_copa=False):
    return {equipo.nombre: calcular_estadisticas_equipo(equipo, es_copa) for equipo in tabla}

def obtener_tabla_general_copa(categoria_id):
    grupos = GrupoCopa.query.filter_by(categoria_id=categoria_id).all()
    todos_equipos = []
    
    for grupo in grupos:
        equipos = EquipoCopa.query.filter_by(grupo_id=grupo.id).order_by(
            EquipoCopa.puntos.desc(),
            EquipoCopa.diferencia_goles.desc(),
            EquipoCopa.goles_favor.desc()
        ).all()
        todos_equipos.extend(equipos)
    
    tabla_general = sorted(todos_equipos, key=lambda e: (-e.puntos, -e.diferencia_goles, -e.goles_favor))
    
    return tabla_general

def obtener_clasificados_copa(categoria_id, num_clasificados=8):
    tabla_general = obtener_tabla_general_copa(categoria_id)
    return [equipo.nombre for equipo in tabla_general[:num_clasificados]]

# Crear tablas automáticamente al iniciar la aplicación
with app.app_context():
    db.create_all()
    if not Torneo.query.first():
        torneo = Torneo(nombre="Torneo Principal", formato_liga="ida_vuelta")
        db.session.add(torneo)
        db.session.commit()

# Manejador para favicon.ico
@app.route('/favicon.ico')
def favicon():
    return send_from_directory(os.path.join(app.root_path, 'static'), 'favicon.ico', mimetype='image/vnd.microsoft.icon')

# Rutas principales
@app.route('/')
def index():
    return redirect(url_for('modo_invitado'))

@app.route('/modo-invitado')
def modo_invitado():
    # Obtener el torneo principal
    torneo = Torneo.query.first()
    if not torneo:
        flash('No hay torneos creados aún', 'info')
        return render_template('modo_invitado.html', datos_ligas=[], datos_grupos_copa=[])

    # Obtener todas las categorías del torneo
    categorias = Categoria.query.filter_by(torneo_id=torneo.id).all()

    datos_ligas = []
    for categoria in categorias:
        # Obtener los equipos y partidos de la categoría
        equipos = Equipo.query.filter_by(categoria_id=categoria.id).order_by(
            Equipo.puntos.desc(),
            Equipo.diferencia_goles.desc(),
            Equipo.goles_favor.desc()
        ).all()
        partidos = Partido.query.filter_by(categoria_id=categoria.id).all()

        # Organizar los partidos por jornada
        jornadas = defaultdict(list)
        descansos = defaultdict(list)  # Almacenar los equipos en descanso
        for partido in partidos:
            if partido.es_descanso:
                descansos[partido.jornada].append(partido.equipo_descansa)
            else:
                jornadas[partido.jornada].append(partido)
        jornadas_ordenadas = sorted(jornadas.items())

        # Calcular estadísticas de los equipos
        stats_equipos = {}
        for equipo in equipos:
            stats_equipos[equipo.nombre] = calcular_estadisticas_equipo(equipo)

        # Agregar los datos de la categoría
        datos_ligas.append({
            'categoria': categoria,
            'tabla': equipos,
            'jornadas': jornadas_ordenadas,
            'descansos': descansos,  # Incluir los descansos
            'total_partidos': len(partidos),
            'partidos_jugados': sum(1 for p in partidos if p.jugado),
            'total_equipos': len(equipos),
            'stats_equipos': stats_equipos,
            'tiene_descanso': any(p.es_descanso for p in partidos)  # Indicar si hay descansos
        })

    return render_template('modo_invitado.html', torneo=torneo, datos_ligas=datos_ligas, datos_grupos_copa=[])

# Rutas de administración
@app.route('/admin/login', methods=['GET', 'POST'])
def admin_login():
    if 'admin_logged_in' in session:
        return redirect(url_for('admin_dashboard'))
    
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        if username == ADMIN_USER['username'] and check_password_hash(ADMIN_USER['password'], password):
            session['admin_logged_in'] = True
            flash('Has iniciado sesión correctamente', 'success')
            return redirect(url_for('admin_dashboard'))
        flash('Credenciales incorrectas', 'danger')
    return render_template('admin_login.html')

@app.route('/admin/dashboard')
@admin_required
def admin_dashboard():
    torneo = Torneo.query.first()
    if not torneo:
        return redirect(url_for('crear_torneo_admin'))
    
    datos_ligas = []
    datos_grupos_copa = []
    
    categorias = Categoria.query.filter_by(torneo_id=torneo.id).all()
    for categoria in categorias:
        if categoria.tiene_liga:
            equipos = Equipo.query.filter_by(categoria_id=categoria.id).all()
            partidos = Partido.query.filter_by(categoria_id=categoria.id).all()
            
            jornadas = {}
            for partido in partidos:
                if partido.jornada not in jornadas:
                    jornadas[partido.jornada] = []
                jornadas[partido.jornada].append(partido)
            
            jornadas_ordenadas = sorted(jornadas.items())
            
            tabla = Equipo.query.filter_by(categoria_id=categoria.id).order_by(
                Equipo.puntos.desc(),
                Equipo.diferencia_goles.desc(),
                Equipo.goles_favor.desc()
            ).all()
            
            total_equipos = len(equipos)
            partidos_jugados = sum(1 for p in partidos if p.jugado)
            total_partidos = len(partidos)
            total_jornadas = max([j[0] for j in jornadas_ordenadas]) if jornadas_ordenadas else 0
            
            stats_equipos = calcular_stats_para_tabla(tabla)
            
            datos_ligas.append({
                'categoria': categoria,
                'jornadas': jornadas_ordenadas,
                'tabla': tabla,
                'stats_equipos': stats_equipos,
                'total_equipos': total_equipos,
                'partidos_jugados': partidos_jugados,
                'total_partidos': total_partidos,
                'total_jornadas': total_jornadas,
                'tiene_descanso': any(p.es_descanso for p in partidos)
            })
        
        if categoria.tiene_copa:
            grupos = GrupoCopa.query.filter_by(categoria_id=categoria.id).all()
            for grupo in grupos:
                equipos = EquipoCopa.query.filter_by(grupo_id=grupo.id).all()
                partidos = PartidoCopa.query.filter_by(grupo_id=grupo.id).order_by(PartidoCopa.id).all()
                
                tabla = EquipoCopa.query.filter_by(grupo_id=grupo.id).order_by(
                    EquipoCopa.puntos.desc(),
                    EquipoCopa.diferencia_goles.desc(),
                    EquipoCopa.goles_favor.desc()
                ).all()
                
                partidos_jugados = sum(1 for p in partidos if p.jugado)
                
                stats_equipos = calcular_stats_para_tabla(tabla, es_copa=True)
                
                datos_grupos_copa.append({
                    'categoria': categoria,
                    'grupo': grupo,
                    'partidos': partidos,
                    'tabla': tabla,
                    'stats_equipos': stats_equipos,
                    'partidos_jugados': partidos_jugados
                })
    
    # Obtener datos de fase eliminatoria si existe
    partidos_eliminatoria = PartidoCopa.query.filter(
        PartidoCopa.categoria_id.in_([c.id for c in categorias]),
        PartidoCopa.fase.in_(['cuartos', 'semifinal', 'final'])
    ).order_by(PartidoCopa.fase, PartidoCopa.id).all()
    
    return render_template('admin_dashboard.html', 
                         torneo=torneo,
                         datos_ligas=datos_ligas,
                         datos_grupos_copa=datos_grupos_copa,
                         partidos_eliminatoria=partidos_eliminatoria)

@app.route('/admin/crear-torneo', methods=['GET', 'POST'])
@admin_required
def crear_torneo_admin():
    if request.method == 'POST':
        if 'cancelar' in request.form:
            return redirect(url_for('admin_dashboard'))
            
        try:
            nombre_torneo = request.form.get('nombre_torneo', 'Torneo Principal')
            formato_liga = request.form.get('formato_liga', 'ida_vuelta')
            num_categorias = int(request.form.get('num_categorias', 0))

            if num_categorias < 1 or num_categorias > 6:
                flash('El número de categorías debe estar entre 1 y 6.', 'danger')
                return redirect(url_for('crear_torneo_admin'))

            # Limpiar datos anteriores
            db.session.query(Partido).delete()
            db.session.query(PartidoCopa).delete()
            db.session.query(Equipo).delete()
            db.session.query(EquipoCopa).delete()
            db.session.query(GrupoCopa).delete()
            db.session.query(Categoria).delete()

            # Crear o actualizar torneo
            torneo = Torneo.query.first()
            if torneo:
                torneo.nombre = nombre_torneo
                torneo.formato_liga = formato_liga
            else:
                torneo = Torneo(
                    nombre=nombre_torneo,
                    formato_liga=formato_liga
                )
                db.session.add(torneo)
            
            db.session.flush()

            # Procesar cada categoría
            for i in range(1, num_categorias + 1):
                nombre_categoria = request.form.get(f'nombre_categoria_{i}', f'Categoría {i}')
                num_equipos = int(request.form.get(f'num_equipos_categoria_{i}', 0))
                tiene_liga = request.form.get(f'tiene_liga_{i}') == 'on'
                tiene_copa = request.form.get(f'tiene_copa_{i}') == 'on'
                num_grupos_copa = int(request.form.get(f'num_grupos_categoria_{i}', 0)) if tiene_copa else 0

                if num_equipos < 2:
                    flash(f'La categoría {nombre_categoria} debe tener al menos 2 equipos.', 'danger')
                    return redirect(url_for('crear_torneo_admin'))

                if tiene_copa and (num_equipos < 4 or num_equipos % num_grupos_copa != 0):
                    flash(f'Para la copa en {nombre_categoria}, el número de equipos debe ser divisible entre el número de grupos.', 'danger')
                    return redirect(url_for('crear_torneo_admin'))

                # Crear categoría
                categoria = Categoria(
                    nombre=nombre_categoria,
                    tiene_liga=tiene_liga,
                    tiene_copa=tiene_copa,
                    num_grupos_copa=num_grupos_copa,
                    torneo_id=torneo.id
                )
                db.session.add(categoria)
                db.session.flush()

                # Obtener nombres de equipos
                nombres_equipos = []
                for j in range(1, num_equipos + 1):
                    nombre_equipo = request.form.get(f'equipo_categoria_{i}_{j}', f'Equipo {j}')
                    nombres_equipos.append(nombre_equipo)

                # Crear equipos y competiciones según configuración
                if tiene_liga:
                    for nombre in nombres_equipos:
                        db.session.add(Equipo(
                            nombre=nombre,
                            categoria_id=categoria.id
                        ))
                    
                    # Crear calendario de liga con el formato seleccionado
                    crear_calendario_liga(nombres_equipos, categoria.id, formato_liga)

                if tiene_copa:
                    # Crear fase de grupos de copa
                    crear_fase_grupos_copa(nombres_equipos, categoria.id, num_grupos_copa)

            db.session.commit()
            flash('Torneo creado exitosamente.', 'success')
            return redirect(url_for('admin_dashboard'))

        except Exception as e:
            db.session.rollback()
            flash(f'Error al crear el torneo: {str(e)}', 'danger')

    return render_template('crear_torneo.html', max_categorias=6)

@app.route('/admin/actualizar-resultado/<int:partido_id>', methods=['GET', 'POST'])
@admin_required
def actualizar_resultado(partido_id):
    partido = Partido.query.get_or_404(partido_id)
    
    if partido.es_descanso:
        flash('No se pueden actualizar resultados de partidos de descanso', 'warning')
        return redirect(url_for('admin_dashboard'))
    
    if request.method == 'POST':
        try:
            goles_local = int(request.form.get('goles_local', 0))
            goles_visitante = int(request.form.get('goles_visitante', 0))
            hora = request.form.get('hora', '19:00')
            
            if goles_local < 0 or goles_visitante < 0:
                flash('Los goles no pueden ser negativos', 'danger')
                return redirect(url_for('admin_dashboard'))
            
            if partido.jugado:
                revertir_estadisticas(partido)
            
            partido.goles_local = goles_local
            partido.goles_visitante = goles_visitante
            partido.hora = hora
            partido.jugado = True
            
            actualizar_estadisticas(partido, es_nuevo=not partido.jugado)
            
            db.session.commit()
            flash('Resultado actualizado correctamente', 'success')
        except ValueError:
            db.session.rollback()
            flash('Los goles deben ser números enteros positivos', 'danger')
        except Exception as e:
            db.session.rollback()
            flash(f'Error al actualizar resultado: {str(e)}', 'danger')
        
        return redirect(url_for('admin_dashboard'))
    
    categoria = Categoria.query.get(partido.categoria_id)
    return render_template('editar_partido.html', 
                         partido=partido,
                         categoria=categoria)

@app.route('/admin/actualizar-resultado-copa/<int:partido_id>', methods=['GET', 'POST'])
@admin_required
def actualizar_resultado_copa(partido_id):
    partido = PartidoCopa.query.get_or_404(partido_id)
    
    if request.method == 'POST':
        try:
            goles_local = int(request.form.get('goles_local', 0))
            goles_visitante = int(request.form.get('goles_visitante', 0))
            hora = request.form.get('hora', '19:00')
            
            if goles_local < 0 or goles_visitante < 0:
                flash('Los goles no pueden ser negativos', 'danger')
                return redirect(url_for('admin_dashboard'))
            
            if partido.jugado:
                revertir_estadisticas(partido, es_copa=True)
            
            partido.goles_local = goles_local
            partido.goles_visitante = goles_visitante
            partido.hora = hora
            partido.jugado = True
            
            actualizar_estadisticas(partido, es_nuevo=not partido.jugado, es_copa=True)
            
            # Si es el último partido de grupos y se está actualizando, crear fase eliminatoria
            if partido.fase == "grupos":
                grupo = GrupoCopa.query.get(partido.grupo_id)
                partidos_grupo = PartidoCopa.query.filter_by(grupo_id=grupo.id, fase="grupos").all()
                
                if all(p.jugado for p in partidos_grupo):
                    equipos_clasificados = obtener_clasificados_copa(grupo.categoria_id)
                    crear_fase_eliminatoria(grupo.categoria_id, equipos_clasificados)
            
            db.session.commit()
            flash('Resultado actualizado correctamente', 'success')
        except ValueError:
            db.session.rollback()
            flash('Los goles deben ser números enteros positivos', 'danger')
        except Exception as e:
            db.session.rollback()
            flash(f'Error al actualizar resultado: {str(e)}', 'danger')
        
        return redirect(url_for('admin_dashboard'))
    
    grupo = GrupoCopa.query.get(partido.grupo_id) if partido.grupo_id else None
    categoria = Categoria.query.get(partido.categoria_id)
    return render_template('editar_partido_copa.html', 
                         partido=partido,
                         grupo=grupo,
                         categoria=categoria)

@app.route('/admin/actualizar-tabla', methods=['GET', 'POST'])
@admin_required
def actualizar_tabla():
    try:
        equipos = Equipo.query.all()
        equipos_copa = EquipoCopa.query.all()
        
        for equipo in equipos:
            equipo.puntos = 0
            equipo.goles_favor = 0
            equipo.goles_contra = 0
            equipo.diferencia_goles = 0
            equipo.partidos_jugados = 0
        
        for equipo in equipos_copa:
            equipo.puntos = 0
            equipo.goles_favor = 0
            equipo.goles_contra = 0
            equipo.diferencia_goles = 0
            equipo.partidos_jugados = 0
        
        partidos = Partido.query.filter_by(jugado=True).all()
        for partido in partidos:
            if not partido.es_descanso:  # Ignorar partidos de descanso
                actualizar_estadisticas(partido, es_nuevo=True)
        
        partidos_copa = PartidoCopa.query.filter_by(jugado=True).all()
        for partido in partidos_copa:
            actualizar_estadisticas(partido, es_nuevo=True, es_copa=True)
        
        db.session.commit()
        flash('Tablas de posiciones actualizadas correctamente', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error al actualizar las tablas: {str(e)}', 'danger')
    
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/reiniciar-torneo', methods=['POST'])
@admin_required
def reiniciar_torneo():
    try:
        db.session.query(Partido).delete()
        db.session.query(PartidoCopa).delete()
        db.session.query(Equipo).delete()
        db.session.query(EquipoCopa).delete()
        db.session.query(Categoria).delete()
        db.session.query(GrupoCopa).delete()
        torneo = Torneo.query.first()
        if torneo:
            torneo.nombre = "Torneo Principal"
            torneo.formato_liga = "ida_vuelta"
        db.session.commit()
        flash('Torneo reiniciado correctamente', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error al reiniciar torneo: {str(e)}', 'danger')
    
    return redirect(url_for('crear_torneo_admin'))

@app.route('/admin/editar-hora/<int:partido_id>', methods=['POST'])
@admin_required
def editar_hora(partido_id):
    partido = Partido.query.get_or_404(partido_id)
    
    try:
        nueva_hora = request.form.get('hora')
        nueva_fecha = request.form.get('fecha')
        
        if nueva_hora:
            partido.hora = nueva_hora
        
        if nueva_fecha:
            partido.fecha = datetime.strptime(nueva_fecha, '%Y-%m-%d')
        
        db.session.commit()
        flash('Fecha y hora actualizadas correctamente', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error al actualizar: {str(e)}', 'danger')
    
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/editar-hora-copa/<int:partido_id>', methods=['POST'])
@admin_required
def editar_hora_copa(partido_id):
    partido = PartidoCopa.query.get_or_404(partido_id)
    
    try:
        nueva_hora = request.form.get('hora')
        nueva_fecha = request.form.get('fecha')
        
        if nueva_hora:
            partido.hora = nueva_hora
        
        if nueva_fecha:
            partido.fecha = datetime.strptime(nueva_fecha, '%Y-%m-%d')
        
        db.session.commit()
        flash('Fecha y hora actualizadas correctamente', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error al actualizar: {str(e)}', 'danger')
    
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/avanzar-fase-copa/<int:categoria_id>', methods=['POST'])
@admin_required
def avanzar_fase_copa(categoria_id):
    try:
        categoria = Categoria.query.get_or_404(categoria_id)
        
        # Obtener los equipos clasificados de la fase anterior
        equipos_clasificados = obtener_clasificados_copa(categoria_id)
        
        # Crear la siguiente fase
        crear_fase_eliminatoria(categoria_id, equipos_clasificados)
        
        db.session.commit()
        flash('Fase eliminatoria creada correctamente', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error al avanzar fase: {str(e)}', 'danger')
    
    return redirect(url_for('admin_dashboard'))

@app.route('/logout')
def logout():
    session.clear()
    flash('Has cerrado sesión correctamente', 'info')
    return redirect(url_for('modo_invitado'))

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
        if not Torneo.query.first():
            torneo = Torneo(nombre="Torneo Principal", formato_liga="ida_vuelta")
            db.session.add(torneo)
            db.session.commit()
    app.run(debug=True)