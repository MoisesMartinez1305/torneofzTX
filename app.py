from flask import Flask, render_template, request, redirect, url_for, session, flash
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps
import os
from itertools import zip_longest

app = Flask(__name__)
app.secret_key = os.urandom(24).hex()
app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv('DATABASE_URL')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

# Modelos de la base de datos
class Liga(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(50), nullable=False)
    torneo_id = db.Column(db.Integer, db.ForeignKey('torneo.id'), nullable=False)

class Torneo(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(100), nullable=False, default="Torneo Principal")
    ligas = db.relationship('Liga', backref='torneo', lazy=True)

class Equipo(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(50), nullable=False)
    liga_id = db.Column(db.Integer, db.ForeignKey('liga.id'), nullable=False)
    puntos = db.Column(db.Integer, default=0)
    goles_favor = db.Column(db.Integer, default=0)
    goles_contra = db.Column(db.Integer, default=0)
    diferencia_goles = db.Column(db.Integer, default=0)
    partidos_jugados = db.Column(db.Integer, default=0)

class Partido(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    jornada = db.Column(db.Integer, nullable=False)
    liga_id = db.Column(db.Integer, db.ForeignKey('liga.id'), nullable=False)
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

# Funciones auxiliares
def crear_calendario(equipos, liga_id):
    """Crea un calendario de partidos para los equipos proporcionados en una liga específica"""
    n = len(equipos)
    if n < 2:
        flash('Se necesitan al menos 2 equipos para crear una liga', 'danger')
        return
    
    # Determinar número de jornadas
    jornadas = n if n % 2 != 0 else n - 1
    
    # Si es impar, añadimos un equipo "Descanso" para rotaciones
    equipos_calendario = equipos.copy()
    if n % 2 != 0:
        equipos_calendario.append("Descanso")
    
    # Ida
    for j in range(1, jornadas + 1):
        for i in range(len(equipos_calendario) // 2):
            local = equipos_calendario[i]
            visitante = equipos_calendario[len(equipos_calendario) - 1 - i]
            
            # Solo crear partido si no es contra el equipo "Descanso"
            if local != "Descanso" and visitante != "Descanso":
                partido = Partido(
                    jornada=j,
                    liga_id=liga_id,
                    equipo_local=local,
                    equipo_visitante=visitante,
                )
                db.session.add(partido)
        
        # Rotar equipos (excepto el primero)
        equipos_calendario = [equipos_calendario[0]] + [equipos_calendario[-1]] + equipos_calendario[1:-1]
    
    # Vuelta (solo si es par)
    if n % 2 == 0:
        for j in range(jornadas + 1, 2 * jornadas + 1):
            for i in range(len(equipos_calendario) // 2):
                visitante = equipos_calendario[i]
                local = equipos_calendario[len(equipos_calendario) - 1 - i]
                
                if local != "Descanso" and visitante != "Descanso":
                    partido = Partido(
                        jornada=j,
                        liga_id=liga_id,
                        equipo_local=local,
                        equipo_visitante=visitante,
                    )
                    db.session.add(partido)
            
            # Rotar equipos (excepto el primero)
            equipos_calendario = [equipos_calendario[0]] + [equipos_calendario[-1]] + equipos_calendario[1:-1]

def revertir_estadisticas(partido):
    """Reverte las estadísticas de un partido ya jugado"""
    equipo_local = Equipo.query.filter_by(nombre=partido.equipo_local, liga_id=partido.liga_id).first()
    equipo_visitante = Equipo.query.filter_by(nombre=partido.equipo_visitante, liga_id=partido.liga_id).first()
    
    if equipo_local and equipo_visitante:
        # Restar goles
        equipo_local.goles_favor -= partido.goles_local
        equipo_local.goles_contra -= partido.goles_visitante
        equipo_visitante.goles_favor -= partido.goles_visitante
        equipo_visitante.goles_contra -= partido.goles_local
        
        # Restar puntos según el resultado anterior
        if partido.goles_local > partido.goles_visitante:
            equipo_local.puntos -= 3  # Local ganó
        elif partido.goles_local < partido.goles_visitante:
            equipo_visitante.puntos -= 3  # Visitante ganó
        else:
            equipo_local.puntos -= 1  # Empate
            equipo_visitante.puntos -= 1  # Empate
        
        # Actualizar diferencias
        equipo_local.diferencia_goles = equipo_local.goles_favor - equipo_local.goles_contra
        equipo_visitante.diferencia_goles = equipo_visitante.goles_favor - equipo_visitante.goles_contra
        equipo_local.partidos_jugados -= 1
        equipo_visitante.partidos_jugados -= 1

def actualizar_estadisticas(partido, es_nuevo=True):
    """Actualiza las estadísticas de los equipos después de un partido"""
    equipo_local = Equipo.query.filter_by(nombre=partido.equipo_local, liga_id=partido.liga_id).first()
    equipo_visitante = Equipo.query.filter_by(nombre=partido.equipo_visitante, liga_id=partido.liga_id).first()
    
    if equipo_local and equipo_visitante:
        # Solo incrementar partidos jugados si es un nuevo resultado
        if es_nuevo:
            equipo_local.partidos_jugados += 1
            equipo_visitante.partidos_jugados += 1
        
        # Actualizar goles
        equipo_local.goles_favor += partido.goles_local
        equipo_local.goles_contra += partido.goles_visitante
        equipo_local.diferencia_goles = equipo_local.goles_favor - equipo_local.goles_contra
        
        equipo_visitante.goles_favor += partido.goles_visitante
        equipo_visitante.goles_contra += partido.goles_local
        equipo_visitante.diferencia_goles = equipo_visitante.goles_favor - equipo_visitante.goles_contra
        
        # Asignar puntos (solo si es un nuevo resultado)
        if es_nuevo:
            if partido.goles_local > partido.goles_visitante:
                equipo_local.puntos += 3  # Local gana
            elif partido.goles_local < partido.goles_visitante:
                equipo_visitante.puntos += 3  # Visitante gana
            else:
                equipo_local.puntos += 1  # Empate
                equipo_visitante.puntos += 1  # Empate

def calcular_estadisticas_equipo(equipo):
    """Calcula los partidos ganados, empatados y perdidos para un equipo"""
    partidos = Partido.query.filter(
        ((Partido.equipo_local == equipo.nombre) | 
         (Partido.equipo_visitante == equipo.nombre)) & 
        (Partido.jugado == True) &
        (Partido.liga_id == equipo.liga_id)
    ).all()
    
    stats = {'ganados': 0, 'empatados': 0, 'perdidos': 0}
    
    for partido in partidos:
        if partido.equipo_local == equipo.nombre:
            goles_favor = partido.goles_local
            goles_contra = partido.goles_visitante
        else:
            goles_favor = partido.goles_visitante
            goles_contra = partido.goles_local
        
        if goles_favor > goles_contra:
            stats['ganados'] += 1
        elif goles_favor < goles_contra:
            stats['perdidos'] += 1
        else:
            stats['empatados'] += 1
    
    return stats

def calcular_stats_para_tabla(tabla):
    """Precalcula las estadísticas para todos los equipos en la tabla"""
    return {equipo.nombre: calcular_estadisticas_equipo(equipo) for equipo in tabla}

# Crear tablas automáticamente al iniciar la aplicación
with app.app_context():
    db.create_all()
    # Crear un torneo por defecto si no existe
    if not Torneo.query.first():
        torneo = Torneo(nombre="Torneo Principal")
        db.session.add(torneo)
        db.session.commit()

# Rutas principales
@app.route('/')
def index():
    return redirect(url_for('modo_invitado'))

@app.route('/invitado')
def modo_invitado():
    torneo = Torneo.query.first()
    if not torneo:
        flash('No hay torneos creados aún', 'info')
        return render_template('modo_invitado.html')
    
    ligas = Liga.query.filter_by(torneo_id=torneo.id).all()
    if not ligas:
        flash('No hay ligas creadas aún', 'info')
        return render_template('modo_invitado.html')
    
    # Obtener datos de todas las ligas
    datos_ligas = []
    for liga in ligas:
        partidos = Partido.query.filter_by(liga_id=liga.id).order_by(Partido.jornada).all()
        
        # Obtener jornadas agrupadas
        jornadas = {}
        for partido in partidos:
            if partido.jornada not in jornadas:
                jornadas[partido.jornada] = []
            jornadas[partido.jornada].append(partido)
        
        jornadas_ordenadas = sorted(jornadas.items())
        
        # Obtener tabla de posiciones
        tabla = Equipo.query.filter_by(liga_id=liga.id).order_by(
            Equipo.puntos.desc(),
            Equipo.diferencia_goles.desc(),
            Equipo.goles_favor.desc()
        ).all()
        
        # Calcular estadísticas
        total_equipos = len(tabla)
        partidos_jugados = sum(1 for p in partidos if p.jugado)
        total_partidos = len(partidos)
        total_jornadas = max([j[0] for j in jornadas_ordenadas]) if jornadas_ordenadas else 0
        
        # Precalcular estadísticas para la tabla
        stats_equipos = calcular_stats_para_tabla(tabla)
        
        datos_ligas.append({
            'liga': liga,
            'jornadas': jornadas_ordenadas,
            'tabla': tabla,
            'stats_equipos': stats_equipos,
            'total_equipos': total_equipos,
            'partidos_jugados': partidos_jugados,
            'total_partidos': total_partidos,
            'total_jornadas': total_jornadas
        })
    
    admin_logged_in = 'admin_logged_in' in session
    
    return render_template('modo_invitado.html', 
                         torneo=torneo,
                         datos_ligas=datos_ligas,
                         admin_logged_in=admin_logged_in)

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
        return redirect(url_for('crear_torneo'))
    
    ligas = Liga.query.filter_by(torneo_id=torneo.id).all()
    if not ligas:
        return redirect(url_for('crear_torneo'))
    
    # Obtener datos de todas las ligas
    datos_ligas = []
    for liga in ligas:
        equipos = Equipo.query.filter_by(liga_id=liga.id).all()
        partidos = Partido.query.filter_by(liga_id=liga.id).order_by(Partido.jornada).all()
        
        # Obtener jornadas agrupadas
        jornadas = {}
        for partido in partidos:
            if partido.jornada not in jornadas:
                jornadas[partido.jornada] = []
            jornadas[partido.jornada].append(partido)
        
        jornadas_ordenadas = sorted(jornadas.items())
        
        # Obtener tabla de posiciones
        tabla = Equipo.query.filter_by(liga_id=liga.id).order_by(
            Equipo.puntos.desc(),
            Equipo.diferencia_goles.desc(),
            Equipo.goles_favor.desc()
        ).all()
        
        # Calcular estadísticas
        total_equipos = len(equipos)
        partidos_jugados = sum(1 for p in partidos if p.jugado)
        total_partidos = len(partidos)
        total_jornadas = max([j[0] for j in jornadas_ordenadas]) if jornadas_ordenadas else 0
        
        # Precalcular estadísticas para la tabla
        stats_equipos = calcular_stats_para_tabla(tabla)
        
        datos_ligas.append({
            'liga': liga,
            'jornadas': jornadas_ordenadas,
            'tabla': tabla,
            'stats_equipos': stats_equipos,
            'total_equipos': total_equipos,
            'partidos_jugados': partidos_jugados,
            'total_partidos': total_partidos,
            'total_jornadas': total_jornadas
        })
    
    return render_template('admin_dashboard.html', 
                         torneo=torneo,
                         datos_ligas=datos_ligas)

@app.route('/admin/crear-torneo', methods=['GET', 'POST'])
@admin_required
def crear_torneo():
    torneo = Torneo.query.first()
    if not torneo:
        torneo = Torneo(nombre="Torneo Principal")
        db.session.add(torneo)
        db.session.commit()
    
    if request.method == 'POST':
        try:
            # Obtener número de ligas (máximo 6)
            num_ligas = min(int(request.form.get('num_ligas', 1)), 6)
            if num_ligas < 1:
                flash('Debe haber al menos 1 liga', 'danger')
                return redirect(url_for('crear_torneo'))
            
            # Eliminar datos existentes
            db.session.query(Partido).delete()
            db.session.query(Equipo).delete()
            db.session.query(Liga).delete()
            
            # Crear ligas
            for i in range(1, num_ligas + 1):
                nombre_liga = request.form.get(f'nombre_liga_{i}', f'Liga {i}').strip()
                num_equipos = int(request.form.get(f'num_equipos_{i}', 0))
                
                if num_equipos < 2:
                    flash(f'La liga {nombre_liga} debe tener al menos 2 equipos', 'danger')
                    return redirect(url_for('crear_torneo'))
                
                # Crear la liga
                liga = Liga(nombre=nombre_liga, torneo_id=torneo.id)
                db.session.add(liga)
                db.session.flush()  # Para obtener el ID de la liga
                
                # Crear equipos para esta liga
                nombres_equipos = []
                for j in range(1, num_equipos + 1):
                    nombre_equipo = request.form.get(f'equipo_{i}_{j}').strip()
                    if not nombre_equipo:
                        flash(f'Todos los equipos en la liga {nombre_liga} deben tener un nombre', 'danger')
                        return redirect(url_for('crear_torneo'))
                    
                    nombres_equipos.append(nombre_equipo)
                    db.session.add(Equipo(nombre=nombre_equipo, liga_id=liga.id))
                
                # Crear calendario para esta liga
                crear_calendario(nombres_equipos, liga.id)
            
            db.session.commit()
            flash('Torneo creado exitosamente con múltiples ligas', 'success')
            return redirect(url_for('admin_dashboard'))
        
        except Exception as e:
            db.session.rollback()
            flash(f'Error al crear torneo: {str(e)}', 'danger')
    
    return render_template('crear_torneo.html', max_ligas=6)

@app.route('/admin/actualizar-resultado/<int:partido_id>', methods=['GET', 'POST'])
@admin_required
def actualizar_resultado(partido_id):
    partido = Partido.query.get_or_404(partido_id)
    
    if request.method == 'POST':
        try:
            # Obtener valores del formulario
            goles_local = int(request.form.get('goles_local', 0))
            goles_visitante = int(request.form.get('goles_visitante', 0))
            hora = request.form.get('hora', '19:00')
            
            # Validar valores
            if goles_local < 0 or goles_visitante < 0:
                flash('Los goles no pueden ser negativos', 'danger')
                return redirect(url_for('admin_dashboard'))
            
            # Revertir estadísticas anteriores si el partido ya estaba jugado
            if partido.jugado:
                revertir_estadisticas(partido)
            
            # Actualizar el partido con los nuevos valores
            partido.goles_local = goles_local
            partido.goles_visitante = goles_visitante
            partido.hora = hora
            partido.jugado = True
            
            # Actualizar estadísticas con los nuevos valores
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
    
    # Si es GET, mostrar formulario de edición
    liga = Liga.query.get(partido.liga_id)
    return render_template('editar_partido.html', 
                         partido=partido,
                         liga=liga)

@app.route('/admin/actualizar-tabla', methods=['GET', 'POST'])
@admin_required
def actualizar_tabla():
    try:
        # Resetear estadísticas de todos los equipos
        equipos = Equipo.query.all()
        for equipo in equipos:
            equipo.puntos = 0
            equipo.goles_favor = 0
            equipo.goles_contra = 0
            equipo.diferencia_goles = 0
            equipo.partidos_jugados = 0
        
        # Recalcular estadísticas para cada partido jugado
        partidos = Partido.query.filter_by(jugado=True).all()
        for partido in partidos:
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
        db.session.query(Partido).delete()
        db.session.query(Equipo).delete()
        db.session.query(Liga).delete()
        torneo = Torneo.query.first()
        if torneo:
            torneo.nombre = "Torneo Principal"
        db.session.commit()
        flash('Torneo reiniciado correctamente', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error al reiniciar torneo: {str(e)}', 'danger')
    
    return redirect(url_for('crear_torneo'))

@app.route('/admin/editar-hora/<int:partido_id>', methods=['POST'])
@admin_required
def editar_hora(partido_id):
    partido = Partido.query.get_or_404(partido_id)
    
    try:
        nueva_hora = request.form.get('hora')
        if nueva_hora:
            partido.hora = nueva_hora
            db.session.commit()
            flash('Hora actualizada correctamente', 'success')
        else:
            flash('La hora no puede estar vacía', 'danger')
    except Exception as e:
        db.session.rollback()
        flash(f'Error al actualizar la hora: {str(e)}', 'danger')
    
    return redirect(url_for('admin_dashboard'))

@app.route('/logout')
def logout():
    session.clear()
    flash('Has cerrado sesión correctamente', 'info')
    return redirect(url_for('modo_invitado'))

# Manejo de errores
@app.errorhandler(404)
def page_not_found(e):
    return render_template('404.html'), 404

@app.errorhandler(500)
def internal_server_error(e):
    db.session.rollback()
    return render_template('500.html'), 500

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
        # Crear un torneo por defecto si no existe
        if not Torneo.query.first():
            torneo = Torneo(nombre="Torneo Principal")
            db.session.add(torneo)
            db.session.commit()
    app.run(debug=True, port=8000)