from flask import Flask, render_template, request, redirect, url_for, session, flash, send_from_directory
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps
import os
from itertools import combinations
import random
from collections import defaultdict
from datetime import datetime, timedelta
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.secret_key = os.urandom(24).hex()
app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv('DATABASE_URL')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['UPLOAD_FOLDER'] = 'static/logos'
app.config['ALLOWED_EXTENSIONS'] = {'png', 'jpg', 'jpeg', 'gif'}
db = SQLAlchemy(app)

# Asegurar que la carpeta de logos existe
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

# Modelos de la base de datos
class Torneo(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(100), nullable=False, default="Torneo Principal")
    formato_liga = db.Column(db.String(20), default="ida_vuelta")
    categorias = db.relationship('Categoria', backref='torneo', lazy=True)

class Categoria(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(50), nullable=False)
    tiene_grupos = db.Column(db.Boolean, default=False)
    num_grupos = db.Column(db.Integer, default=1)
    torneo_id = db.Column(db.Integer, db.ForeignKey('torneo.id'), nullable=False)
    equipos = db.relationship('Equipo', backref='categoria', lazy=True)
    partidos = db.relationship('Partido', backref='categoria', lazy=True)
    grupos = db.relationship('Grupo', backref='categoria', lazy=True)

class Grupo(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(50), nullable=False)
    categoria_id = db.Column(db.Integer, db.ForeignKey('categoria.id'), nullable=False)
    equipos = db.relationship('Equipo', backref='grupo', lazy=True)
    partidos = db.relationship('Partido', backref='grupo', lazy=True)

class Equipo(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(50), nullable=False)
    categoria_id = db.Column(db.Integer, db.ForeignKey('categoria.id'), nullable=False)
    grupo_id = db.Column(db.Integer, db.ForeignKey('grupo.id'), nullable=True)
    puntos = db.Column(db.Integer, default=0)
    goles_favor = db.Column(db.Integer, default=0)
    goles_contra = db.Column(db.Integer, default=0)
    diferencia_goles = db.Column(db.Integer, default=0)
    partidos_jugados = db.Column(db.Integer, default=0)
    logo = db.Column(db.String(100), nullable=True)

class Partido(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    jornada = db.Column(db.Integer, nullable=False)
    fecha = db.Column(db.DateTime, nullable=True)
    hora = db.Column(db.String(10), nullable=True)
    categoria_id = db.Column(db.Integer, db.ForeignKey('categoria.id'), nullable=False)
    grupo_id = db.Column(db.Integer, db.ForeignKey('grupo.id'), nullable=True)
    equipo_local = db.Column(db.String(50), nullable=True)
    equipo_visitante = db.Column(db.String(50), nullable=True)
    goles_local = db.Column(db.Integer)
    goles_visitante = db.Column(db.Integer)
    jugado = db.Column(db.Boolean, default=False)
    es_descanso = db.Column(db.Boolean, default=False)
    equipo_descansa = db.Column(db.String(50))

class Goleador(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(50), nullable=False)
    equipo = db.Column(db.String(50), nullable=False)
    categoria_id = db.Column(db.Integer, db.ForeignKey('categoria.id'), nullable=False)
    categoria = db.relationship('Categoria', backref='goleadores')
    total_goles = db.Column(db.Integer, default=0)
    goles_por_jornada = db.Column(db.JSON, default=lambda: {})

# Funciones auxiliares
def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in app.config['ALLOWED_EXTENSIONS']

def get_logo_path(equipo):
    if equipo.logo and os.path.exists(os.path.join(app.config['UPLOAD_FOLDER'], equipo.logo)):
        return url_for('static', filename=f'logos/{equipo.logo}')
    return url_for('static', filename='logos/default.png')

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

# Funciones de lógica del torneo
def calcular_progreso(partidos):
    partidos_jugados = sum(1 for p in partidos if p.jugado and not p.es_descanso)
    total_partidos = sum(1 for p in partidos if not p.es_descanso)
    return partidos_jugados, total_partidos

def crear_calendario_liga(equipos, categoria_id, grupo_id=None, formato_liga="ida_vuelta"):
    n = len(equipos)
    if n < 2:
        flash('Se necesitan al menos 2 equipos para crear una liga', 'danger')
        return

    tiene_descanso = n % 2 != 0
    equipos_originales = equipos.copy()

    if tiene_descanso:
        equipos_originales.append(None)

    num_jornadas = len(equipos_originales) - 1
    jornadas = []

    for i in range(num_jornadas):
        jornada = []
        descanso = equipos_originales[0]
        for j in range(len(equipos_originales) // 2):
            if i % 2 == 0:
                local = equipos_originales[j]
                visitante = equipos_originales[-(j + 1)]
            else:
                local = equipos_originales[-(j + 1)]
                visitante = equipos_originales[j]
            if local and visitante and local != visitante:
                jornada.append((local, visitante))
        jornadas.append((descanso, jornada))
        equipos_originales = [equipos_originales[0]] + equipos_originales[-1:] + equipos_originales[1:-1]

    if formato_liga == "ida_vuelta":
        jornadas_vuelta = []
        for descanso, jornada in jornadas:
            jornada_vuelta = [(visitante, local) for local, visitante in jornada]
            jornadas_vuelta.append((descanso, jornada_vuelta))
        jornadas.extend(jornadas_vuelta)

    for i, (descanso, jornada) in enumerate(jornadas, 1):
        if descanso:
            partido_descanso = Partido(
                jornada=i,
                categoria_id=categoria_id,
                grupo_id=grupo_id,
                es_descanso=True,
                equipo_descansa=descanso
            )
            db.session.add(partido_descanso)

        for local, visitante in jornada:
            if local is None or visitante is None:
                continue
            partido = Partido(
                jornada=i,
                categoria_id=categoria_id,
                grupo_id=grupo_id,
                equipo_local=local,
                equipo_visitante=visitante
            )
            db.session.add(partido)

    db.session.commit()

def crear_grupos_liga(equipos, categoria_id, num_grupos=1, formato_liga="ida_vuelta"):
    if num_grupos < 1:
        return []
        
    random.shuffle(equipos)
    equipos_por_grupo = len(equipos) // num_grupos
    grupos = []
    
    for i in range(num_grupos):
        grupo = Grupo(
            nombre=f"Grupo {chr(65+i)}",
            categoria_id=categoria_id)
        db.session.add(grupo)
        db.session.flush()
        
        grupo_equipos = equipos[i*equipos_por_grupo:(i+1)*equipos_por_grupo]
        for equipo_nombre in grupo_equipos:
            equipo = Equipo(
                nombre=equipo_nombre,
                categoria_id=categoria_id,
                grupo_id=grupo.id)
            db.session.add(equipo)
        
        crear_calendario_liga(grupo_equipos, categoria_id, grupo.id, formato_liga)
        grupos.append(grupo)
    
    return grupos

def revertir_estadisticas(partido):
    if partido.es_descanso:
        return
        
    equipo_local = Equipo.query.filter_by(
        nombre=partido.equipo_local, 
        categoria_id=partido.categoria_id,
        grupo_id=partido.grupo_id).first()
    equipo_visitante = Equipo.query.filter_by(
        nombre=partido.equipo_visitante,
        categoria_id=partido.categoria_id,
        grupo_id=partido.grupo_id).first()
    
    if equipo_local and equipo_visitante:
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

def actualizar_estadisticas(partido, es_nuevo=True):
    if partido.es_descanso:
        return
        
    equipo_local = Equipo.query.filter_by(
        nombre=partido.equipo_local,
        categoria_id=partido.categoria_id,
        grupo_id=partido.grupo_id).first()
    equipo_visitante = Equipo.query.filter_by(
        nombre=partido.equipo_visitante,
        categoria_id=partido.categoria_id,
        grupo_id=partido.grupo_id).first()
    
    if equipo_local and equipo_visitante:
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

def calcular_estadisticas_equipo(equipo):
    partidos = Partido.query.filter(
        ((Partido.equipo_local == equipo.nombre) | 
         (Partido.equipo_visitante == equipo.nombre)) & 
        (Partido.jugado == True) &
        (Partido.categoria_id == equipo.categoria_id) &
        ((Partido.grupo_id == equipo.grupo_id) | (Partido.grupo_id.is_(None))) &
        (Partido.es_descanso == False)).all()
    
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

@app.context_processor
def utility_processor():
    return dict(calcular_estadisticas_equipo=calcular_estadisticas_equipo,
               get_logo_path=get_logo_path)

# Inicialización de la base de datos
with app.app_context():
    db.create_all()
    if not Torneo.query.first():
        torneo = Torneo(nombre="Torneo Principal", formato_liga="ida_vuelta")
        db.session.add(torneo)
        db.session.commit()

# Rutas principales
@app.route('/')
def index():
    return redirect(url_for('modo_invitado'))

@app.route('/goleadores')
def ver_goleadores():
    goleadores = Goleador.query.order_by(Goleador.total_goles.desc()).limit(20).all()
    return render_template('goleadores.html', goleadores=goleadores)

@app.route('/modo-invitado')
def modo_invitado():
    torneo = Torneo.query.first()
    today = datetime.now().date()

    if not torneo:
        return render_template('modo_invitado.html', datos_ligas=[], today=today)

    categorias = Categoria.query.filter_by(torneo_id=torneo.id).all()
    datos_ligas = []

    for categoria in categorias:
        equipos_categoria = Equipo.query.filter_by(categoria_id=categoria.id).all()
        equipos_con_logo = [{'nombre': e.nombre, 'logo': get_logo_path(e)} for e in equipos_categoria]

        categoria_data = {
            'categoria': categoria,
            'tiene_grupos': categoria.tiene_grupos,
            'goleadores': Goleador.query.filter_by(categoria_id=categoria.id).order_by(Goleador.total_goles.desc()).all(),
            'equipos_con_logo': equipos_con_logo
        }

        if categoria.tiene_grupos:
            grupos_data = []
            grupos = Grupo.query.filter_by(categoria_id=categoria.id).all()

            for grupo in grupos:
                equipos = Equipo.query.filter_by(grupo_id=grupo.id).order_by(
                    Equipo.puntos.desc(),
                    Equipo.diferencia_goles.desc(),
                    Equipo.goles_favor.desc()).all()

                partidos = Partido.query.filter_by(grupo_id=grupo.id).order_by(Partido.jornada, Partido.fecha, Partido.hora).all()

                jornadas_dict = defaultdict(list)
                descansos_dict = defaultdict(list)

                for partido in partidos:
                    partido_dict = {
                        'id': partido.id,
                        'jornada': partido.jornada,
                        'fecha': partido.fecha,
                        'hora': partido.hora,
                        'equipo_local': partido.equipo_local,
                        'equipo_visitante': partido.equipo_visitante,
                        'goles_local': partido.goles_local,
                        'goles_visitante': partido.goles_visitante,
                        'jugado': partido.jugado,
                        'es_descanso': partido.es_descanso,
                        'equipo_descansa': partido.equipo_descansa
                    }

                    if partido.es_descanso:
                        descansos_dict[partido.jornada].append(partido.equipo_descansa)
                    else:
                        jornadas_dict[partido.jornada].append(partido_dict)

                jornadas_ordenadas = sorted(jornadas_dict.items(), key=lambda x: x[0])

                grupo_data = {
                    'grupo': grupo,
                    'tabla': equipos,
                    'jornadas': jornadas_ordenadas,
                    'descansos': dict(descansos_dict),
                    'total_partidos': len([p for p in partidos if not p.es_descanso]),
                    'partidos_jugados': len([p for p in partidos if p.jugado and not p.es_descanso]),
                    'total_equipos': len(equipos),
                    'stats_equipos': {e.nombre: calcular_estadisticas_equipo(e) for e in equipos},
                    'tiene_descanso': len(equipos) % 2 != 0
                }

                grupos_data.append(grupo_data)

            categoria_data['grupos'] = grupos_data
        else:
            equipos = Equipo.query.filter_by(categoria_id=categoria.id).order_by(
                Equipo.puntos.desc(),
                Equipo.diferencia_goles.desc(),
                Equipo.goles_favor.desc()).all()

            partidos = Partido.query.filter_by(categoria_id=categoria.id).order_by(Partido.jornada, Partido.fecha, Partido.hora).all()

            jornadas_dict = defaultdict(list)
            descansos_dict = defaultdict(list)

            for partido in partidos:
                partido_dict = {
                    'id': partido.id,
                    'jornada': partido.jornada,
                    'fecha': partido.fecha,
                    'hora': partido.hora,
                    'equipo_local': partido.equipo_local,
                    'equipo_visitante': partido.equipo_visitante,
                    'goles_local': partido.goles_local,
                    'goles_visitante': partido.goles_visitante,
                    'jugado': partido.jugado,
                    'es_descanso': partido.es_descanso,
                    'equipo_descansa': partido.equipo_descansa
                }

                if partido.es_descanso:
                    descansos_dict[partido.jornada].append(partido.equipo_descansa)
                else:
                    jornadas_dict[partido.jornada].append(partido_dict)

            jornadas_ordenadas = sorted(jornadas_dict.items(), key=lambda x: x[0])

            categoria_data.update({
                'tabla': equipos,
                'jornadas': jornadas_ordenadas,
                'descansos': dict(descansos_dict),
                'total_partidos': len([p for p in partidos if not p.es_descanso]),
                'partidos_jugados': len([p for p in partidos if p.jugado and not p.es_descanso]),
                'total_equipos': len(equipos),
                'stats_equipos': {e.nombre: calcular_estadisticas_equipo(e) for e in equipos},
                'tiene_descanso': len(equipos) % 2 != 0
            })

        datos_ligas.append(categoria_data)
        
    equipos_por_categoria = {}
    for categoria in categorias:
        equipos = Equipo.query.filter_by(categoria_id=categoria.id).all()
        equipos_por_categoria[categoria.id] = [{
            'nombre': equipo.nombre,
            'logo': get_logo_path(equipo)
        } for equipo in equipos]

    return render_template('modo_invitado.html',
                         torneo=torneo,
                         datos_ligas=datos_ligas,
                         today=today,
                         equipos_por_categoria=equipos_por_categoria)

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

    categorias = Categoria.query.filter_by(torneo_id=torneo.id).all()
    datos_ligas = []

    for categoria in categorias:
        if categoria.tiene_grupos:
            grupos = Grupo.query.filter_by(categoria_id=categoria.id).all()
            datos_grupos = []

            for grupo in grupos:
                equipos = Equipo.query.filter_by(grupo_id=grupo.id).order_by(
                    Equipo.puntos.desc(),
                    Equipo.diferencia_goles.desc(),
                    Equipo.goles_favor.desc()).all()
                
                partidos = Partido.query.filter_by(grupo_id=grupo.id).order_by(Partido.jornada, Partido.fecha, Partido.hora).all()
                
                partidos_jugados, total_partidos = calcular_progreso(partidos)

                jornadas = defaultdict(list)
                for partido in partidos:
                    if not partido.es_descanso:
                        jornadas[partido.jornada].append({
                            'equipo_local': partido.equipo_local,
                            'equipo_visitante': partido.equipo_visitante,
                            'goles_local': partido.goles_local,
                            'goles_visitante': partido.goles_visitante,
                            'jugado': partido.jugado,
                            'id': partido.id,
                            'fecha': partido.fecha,
                            'hora': partido.hora
                        })

                jornadas_ordenadas = sorted(jornadas.items(), key=lambda x: x[0])

                datos_grupos.append({
                    'grupo': grupo,
                    'tabla': equipos,
                    'jornadas': jornadas_ordenadas,
                    'total_partidos': total_partidos,
                    'partidos_jugados': partidos_jugados,
                    'total_equipos': len(equipos)
                })

            datos_ligas.append({
                'categoria': categoria,
                'tiene_grupos': True,
                'grupos': datos_grupos
            })
        else:
            equipos = Equipo.query.filter_by(categoria_id=categoria.id).order_by(
                Equipo.puntos.desc(),
                Equipo.diferencia_goles.desc(),
                Equipo.goles_favor.desc()).all()
            
            partidos = Partido.query.filter_by(categoria_id=categoria.id).order_by(Partido.jornada, Partido.fecha, Partido.hora).all()
            
            partidos_jugados, total_partidos = calcular_progreso(partidos)

            jornadas = defaultdict(list)
            for partido in partidos:
                if not partido.es_descanso:
                    jornadas[partido.jornada].append({
                        'equipo_local': partido.equipo_local,
                        'equipo_visitante': partido.equipo_visitante,
                        'goles_local': partido.goles_local,
                        'goles_visitante': partido.goles_visitante,
                        'jugado': partido.jugado,
                        'id': partido.id,
                        'fecha': partido.fecha,
                        'hora': partido.hora
                    })

            jornadas_ordenadas = sorted(jornadas.items(), key=lambda x: x[0])

            datos_ligas.append({
                'categoria': categoria,
                'tiene_grupos': False,
                'tabla': equipos,
                'jornadas': jornadas_ordenadas,
                'total_partidos': total_partidos,
                'partidos_jugados': partidos_jugados,
                'total_equipos': len(equipos)
            })

    goleadores = Goleador.query.order_by(Goleador.total_goles.desc()).all()

    return render_template('admin_dashboard.html',
                         torneo=torneo,
                         datos_ligas=datos_ligas,
                         goleadores=goleadores)
@app.route('/admin/goleadores', methods=['GET', 'POST'])
@admin_required
def administrar_goleadores():
    if request.method == 'POST':
        try:
            if 'add_goleador' in request.form:
                nombre = request.form['nombre']
                equipo = request.form['equipo']
                categoria_id = int(request.form['categoria_id'])
                
                existente = Goleador.query.filter_by(nombre=nombre, equipo=equipo, categoria_id=categoria_id).first()
                if existente:
                    flash('Este jugador ya está registrado', 'warning')
                else:
                    nuevo_goleador = Goleador(
                        nombre=nombre,
                        equipo=equipo,
                        categoria_id=categoria_id,
                        total_goles=0,
                        goles_por_jornada={}
                    )
                    db.session.add(nuevo_goleador)
                    db.session.commit()
                    flash('Goleador añadido correctamente', 'success')
            
            elif 'update_goles' in request.form:
                goleador_id = int(request.form['goleador_id'])
                jornada = request.form['jornada']  # Mantener como string
                goles = int(request.form['goles'])
                
                goleador = Goleador.query.get(goleador_id)
                if goleador:
                    # Asegurar que goles_por_jornada es un diccionario
                    if goleador.goles_por_jornada is None:
                        goleador.goles_por_jornada = {}
                    
                    # Convertir claves a strings por si acaso
                    goles_por_jornada = {str(k): v for k, v in goleador.goles_por_jornada.items()}
                    
                    # Calcular diferencia
                    goles_anteriores = goles_por_jornada.get(jornada, 0)
                    diferencia = goles - goles_anteriores
                    
                    # Actualizar
                    goles_por_jornada[jornada] = goles
                    goleador.goles_por_jornada = goles_por_jornada
                    goleador.total_goles += diferencia
                    
                    db.session.commit()
                    flash('Goles actualizados correctamente', 'success')
                else:
                    flash('Goleador no encontrado', 'danger')
            
            elif 'delete_goleador' in request.form:
                goleador_id = int(request.form['goleador_id'])
                goleador = Goleador.query.get(goleador_id)
                if goleador:
                    db.session.delete(goleador)
                    db.session.commit()
                    flash('Goleador eliminado correctamente', 'success')
                else:
                    flash('Goleador no encontrado', 'danger')
        
        except ValueError as e:
            db.session.rollback()
            flash('Error en los datos proporcionados: valores numéricos inválidos', 'danger')
        except Exception as e:
            db.session.rollback()
            flash(f'Error al procesar la solicitud: {str(e)}', 'danger')

    # Obtener todas las categorías con sus equipos y partidos
    categorias = Categoria.query.options(
        db.joinedload(Categoria.equipos),
        db.joinedload(Categoria.partidos)
    ).all()
    
    # Obtener goleadores con información de categoría
    goleadores = db.session.query(
        Goleador,
        Categoria.nombre.label('categoria_nombre')
    ).join(Categoria).order_by(Goleador.total_goles.desc()).all()

    # Preparar jornadas únicas por categoría
    jornadas_por_categoria = {}
    for categoria in categorias:
        # Usamos un conjunto para evitar duplicados y luego ordenamos
        jornadas = sorted({p.jornada for p in categoria.partidos}, key=int)
        jornadas_por_categoria[categoria.id] = [str(j) for j in jornadas]  # Convertimos a string para consistencia

    return render_template('admin_goleadores.html',
                        categorias=categorias,
                        goleadores=[{
                            'id': g.id,
                            'nombre': g.nombre,
                            'equipo': g.equipo,
                            'categoria_id': g.categoria_id,
                            'categoria_nombre': cat_nombre,
                            'total_goles': g.total_goles,
                            'goles_por_jornada': g.goles_por_jornada if g.goles_por_jornada else {}
                        } for g, cat_nombre in goleadores],
                        jornadas_por_categoria=jornadas_por_categoria)

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
            db.session.query(Equipo).delete()
            db.session.query(Grupo).delete()
            db.session.query(Categoria).delete()
            db.session.query(Goleador).delete()

            # Crear o actualizar torneo
            torneo = Torneo.query.first()
            if torneo:
                torneo.nombre = nombre_torneo
                torneo.formato_liga = formato_liga
            else:
                torneo = Torneo(
                    nombre=nombre_torneo,
                    formato_liga=formato_liga)
                db.session.add(torneo)
            
            db.session.flush()

            # Procesar cada categoría
            for i in range(1, num_categorias + 1):
                nombre_categoria = request.form.get(f'nombre_categoria_{i}', f'Categoría {i}')
                num_equipos = int(request.form.get(f'num_equipos_categoria_{i}', 0))
                tiene_grupos = request.form.get(f'tiene_grupos_{i}') == 'on'
                num_grupos = int(request.form.get(f'num_grupos_categoria_{i}', 1)) if tiene_grupos else 1

                if num_equipos < 2:
                    flash(f'La categoría {nombre_categoria} debe tener al menos 2 equipos.', 'danger')
                    return redirect(url_for('crear_torneo_admin'))

                if tiene_grupos and (num_equipos < num_grupos * 2 or num_equipos % num_grupos != 0):
                    flash(f'Para grupos en {nombre_categoria}, el número de equipos debe ser divisible entre el número de grupos.', 'danger')
                    return redirect(url_for('crear_torneo_admin'))

                # Crear categoría
                categoria = Categoria(
                    nombre=nombre_categoria,
                    tiene_grupos=tiene_grupos,
                    num_grupos=num_grupos,
                    torneo_id=torneo.id)
                db.session.add(categoria)
                db.session.flush()

                # Obtener nombres de equipos
                nombres_equipos = []
                for j in range(1, num_equipos + 1):
                    nombre_equipo = request.form.get(f'equipo_categoria_{i}_{j}', f'Equipo {j}')
                    nombres_equipos.append(nombre_equipo)

                # Crear equipos y competiciones según configuración
                if tiene_grupos:
                    crear_grupos_liga(nombres_equipos, categoria.id, num_grupos, formato_liga)
                else:
                    for nombre in nombres_equipos:
                        db.session.add(Equipo(
                            nombre=nombre,
                            categoria_id=categoria.id))
                    
                    crear_calendario_liga(nombres_equipos, categoria.id, None, formato_liga)

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
            
            if goles_local < 0 or goles_visitante < 0:
                flash('Los goles no pueden ser negativos', 'danger')
                return redirect(url_for('admin_dashboard'))
            
            if partido.jugado:
                revertir_estadisticas(partido)
            
            partido.goles_local = goles_local
            partido.goles_visitante = goles_visitante
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
    grupo = Grupo.query.get(partido.grupo_id) if partido.grupo_id else None
    return render_template('editar_partido.html', 
                           partido=partido,
                           categoria=categoria,
                           grupo=grupo)

@app.route('/admin/actualizar-tabla', methods=['GET', 'POST'])
@admin_required
def actualizar_tabla():
    try:
        equipos = Equipo.query.all()
        
        for equipo in equipos:
            equipo.puntos = 0
            equipo.goles_favor = 0
            equipo.goles_contra = 0
            equipo.diferencia_goles = 0
            equipo.partidos_jugados = 0
        
        partidos = Partido.query.filter_by(jugado=True).all()
        for partido in partidos:
            if not partido.es_descanso:
                actualizar_estadisticas(partido, es_nuevo=True)
        
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
        db.session.query(Goleador).delete()
        db.session.query(Partido).delete()
        db.session.query(Equipo).delete()
        db.session.query(Grupo).delete()
        db.session.query(Categoria).delete()
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

@app.route('/admin/editar-hora/<int:partido_id>', methods=['GET', 'POST'])
@admin_required
def editar_hora(partido_id):
    partido = Partido.query.get_or_404(partido_id)
    
    if request.method == 'POST':
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
    
    return render_template('editar_hora.html', partido=partido)

@app.route('/admin/subir-logo/<int:equipo_id>', methods=['GET', 'POST'])
@admin_required
def subir_logo(equipo_id):
    equipo = Equipo.query.get_or_404(equipo_id)
    
    if request.method == 'POST':
        if 'logo' not in request.files:
            flash('No se seleccionó ningún archivo', 'danger')
            return redirect(request.url)
        
        file = request.files['logo']
        
        if file.filename == '':
            flash('No se seleccionó ningún archivo', 'danger')
            return redirect(request.url)
        
        if file and allowed_file(file.filename):
            if equipo.logo and os.path.exists(os.path.join(app.config['UPLOAD_FOLDER'], equipo.logo)):
                try:
                    os.remove(os.path.join(app.config['UPLOAD_FOLDER'], equipo.logo))
                except Exception as e:
                    flash(f'Error al eliminar el logo anterior: {str(e)}', 'warning')
            
            filename = secure_filename(f"equipo_{equipo.id}.{file.filename.rsplit('.', 1)[1].lower()}")
            file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
            
            equipo.logo = filename
            db.session.commit()
            
            flash('Logo subido correctamente', 'success')
            return redirect(url_for('admin_dashboard'))
        else:
            flash('Tipo de archivo no permitido. Use PNG, JPG o JPEG', 'danger')
    
    return render_template('subir_logo.html', equipo=equipo)

@app.route('/logout')
def logout():
    session.clear()
    flash('Has cerrado sesión correctamente', 'info')
    return redirect(url_for('modo_invitado'))

if __name__ == '__main__':
    app.run(debug=True)