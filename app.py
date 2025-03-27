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
class Equipo(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(50), unique=True, nullable=False)
    puntos = db.Column(db.Integer, default=0)
    goles_favor = db.Column(db.Integer, default=0)
    goles_contra = db.Column(db.Integer, default=0)
    diferencia_goles = db.Column(db.Integer, default=0)
    partidos_jugados = db.Column(db.Integer, default=0)

class Partido(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    jornada = db.Column(db.Integer, nullable=False)
    equipo_local = db.Column(db.String(50), nullable=False)
    equipo_visitante = db.Column(db.String(50), nullable=False)
    goles_local = db.Column(db.Integer)
    goles_visitante = db.Column(db.Integer)
    jugado = db.Column(db.Boolean, default=False)

# Usuario administrador
ADMIN_USER = {
    "username": "admin",
    "password": generate_password_hash("admin123")
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
def crear_calendario(equipos):
    """Crea un calendario de partidos para los equipos proporcionados, manejando descansos para impares"""
    n = len(equipos)
    if n < 2:
        flash('Se necesitan al menos 2 equipos para crear un torneo', 'danger')
        return
    
    # Determinar número de jornadas
    jornadas = n if n % 2 != 0 else n - 1
    
    # Si es impar, añadimos un equipo "Descanso" para rotaciones
    equipos_calendario = equipos.copy()
    if n % 2 != 0:
        equipos_calendario.append("Descanso")
    
    # Crear lista para almacenar los descansos por jornada
    descansos_por_jornada = {}
    
    # Ida
    for j in range(1, jornadas + 1):
        # Determinar qué equipo descansa en esta jornada
        equipo_descanso = None
        for i in range(len(equipos_calendario) // 2):
            local = equipos_calendario[i]
            visitante = equipos_calendario[len(equipos_calendario) - 1 - i]
            
            if local == "Descanso":
                equipo_descanso = visitante
            elif visitante == "Descanso":
                equipo_descanso = local
            
            # Solo crear partido si no es contra el equipo "Descanso"
            if local != "Descanso" and visitante != "Descanso":
                partido = Partido(
                    jornada=j,
                    equipo_local=local,
                    equipo_visitante=visitante
                )
                db.session.add(partido)
        
        # Registrar equipo que descansa (si aplica)
        if equipo_descanso:
            descansos_por_jornada[j] = equipo_descanso
        
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
                        equipo_local=local,
                        equipo_visitante=visitante
                    )
                    db.session.add(partido)
            
            # Rotar equipos (excepto el primero)
            equipos_calendario = [equipos_calendario[0]] + [equipos_calendario[-1]] + equipos_calendario[1:-1]
    
    return descansos_por_jornada

def actualizar_estadisticas(partido):
    """Actualiza las estadísticas de los equipos después de un partido"""
    equipo_local = Equipo.query.filter_by(nombre=partido.equipo_local).first()
    equipo_visitante = Equipo.query.filter_by(nombre=partido.equipo_visitante).first()
    
    if equipo_local and equipo_visitante:
        # Actualizar partidos jugados
        equipo_local.partidos_jugados += 1
        equipo_visitante.partidos_jugados += 1
        
        # Actualizar goles
        equipo_local.goles_favor += partido.goles_local
        equipo_local.goles_contra += partido.goles_visitante
        equipo_local.diferencia_goles = equipo_local.goles_favor - equipo_local.goles_contra
        
        equipo_visitante.goles_favor += partido.goles_visitante
        equipo_visitante.goles_contra += partido.goles_local
        equipo_visitante.diferencia_goles = equipo_visitante.goles_favor - equipo_visitante.goles_contra
        
        # Asignar puntos
        if partido.goles_local > partido.goles_visitante:
            equipo_local.puntos += 3
        elif partido.goles_local < partido.goles_visitante:
            equipo_visitante.puntos += 3
        else:
            equipo_local.puntos += 1
            equipo_visitante.puntos += 1
with app.app_context():
	db.create_all()

# Rutas principales
@app.route('/')
def index():
    return render_template('seleccion_modo.html')

@app.route('/invitado')
def modo_invitado():
    # Obtener todos los partidos (no solo por jornada)
    todos_los_partidos = Partido.query.order_by(Partido.jornada).all()
    
    # Obtener jornadas agrupadas
    jornadas = {}
    for partido in todos_los_partidos:
        if partido.jornada not in jornadas:
            jornadas[partido.jornada] = []
        jornadas[partido.jornada].append(partido)
    
    # Convertir a lista ordenada de tuplas
    jornadas_ordenadas = sorted(jornadas.items())
    
    # Obtener tabla de posiciones
    tabla = Equipo.query.order_by(
        Equipo.puntos.desc(),
        Equipo.diferencia_goles.desc(),
        Equipo.goles_favor.desc()
    ).all()
    
    # Calcular estadísticas para el dashboard
    total_equipos = len(tabla)
    partidos_jugados = sum(1 for p in todos_los_partidos if p.jugado)  # Esto es el conteo
    total_jornadas = max([j[0] for j in jornadas_ordenadas]) if jornadas_ordenadas else 0
    
    return render_template('modo_invitado.html', 
                         jornadas=jornadas_ordenadas,
                         tabla=tabla,
                         total_equipos=total_equipos,
                         partidos_jugados=partidos_jugados,  # El conteo
                         todos_los_partidos=todos_los_partidos,  # La lista completa
                         total_jornadas=total_jornadas)

# Agrega esta ruta junto con las demás rutas de administración
@app.route('/admin/actualizar-tabla', methods=['POST'])
@admin_required
def actualizar_tabla():
    """Actualiza la tabla de posiciones recalculando todas las estadísticas"""
    try:
        # Obtener todos los partidos jugados
        partidos = Partido.query.filter_by(jugado=True).all()
        
        # Resetear estadísticas de todos los equipos
        equipos = Equipo.query.all()
        for equipo in equipos:
            equipo.puntos = 0
            equipo.goles_favor = 0
            equipo.goles_contra = 0
            equipo.diferencia_goles = 0
            equipo.partidos_jugados = 0
        
        # Recalcular estadísticas para cada partido jugado
        for partido in partidos:
            actualizar_estadisticas(partido)
        
        db.session.commit()
        flash('Tabla de posiciones actualizada correctamente', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error al actualizar la tabla: {str(e)}', 'danger')
    
    return redirect(url_for('admin_dashboard'))


# Rutas de administración
@app.route('/admin/login', methods=['GET', 'POST'])
def admin_login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        if username == ADMIN_USER['username'] and check_password_hash(ADMIN_USER['password'], password):
            session['admin_logged_in'] = True
            return redirect(url_for('admin_dashboard'))
        flash('Credenciales incorrectas', 'danger')
    return render_template('admin_login.html')

@app.route('/admin/dashboard')
@admin_required
def admin_dashboard():
    equipos = Equipo.query.all()
    
    # Obtener jornadas agrupadas
    partidos = Partido.query.order_by(Partido.jornada).all()
    jornadas = {}
    for partido in partidos:
        if partido.jornada not in jornadas:
            jornadas[partido.jornada] = []
        jornadas[partido.jornada].append(partido)
    
    # Convertir a lista ordenada de tuplas
    jornadas_ordenadas = sorted(jornadas.items())
    
    # Obtener tabla de posiciones
    tabla = Equipo.query.order_by(
        Equipo.puntos.desc(),
        Equipo.diferencia_goles.desc(),
        Equipo.goles_favor.desc()
    ).all()
    
    # Calcular estadísticas
    total_equipos = len(equipos)
    partidos_jugados = sum(1 for p in partidos if p.jugado)
    total_jornadas = max([j[0] for j in jornadas_ordenadas]) if jornadas_ordenadas else 0
    
    return render_template('admin_dashboard.html', 
                         jornadas=jornadas_ordenadas,
                         tabla=tabla,
                         total_equipos=total_equipos,
                         partidos_jugados=partidos_jugados,
                         total_jornadas=total_jornadas)

@app.route('/admin/crear-torneo', methods=['GET', 'POST'])
@admin_required
def crear_torneo():
    if request.method == 'POST':
        try:
            # Validar número de equipos
            num_equipos = int(request.form.get('num_equipos'))
            if num_equipos < 2:
                flash('Debe haber al menos 2 equipos', 'danger')
                return redirect(url_for('crear_torneo'))
            
            # Eliminar datos existentes
            db.session.query(Partido).delete()
            db.session.query(Equipo).delete()
            
            # Crear equipos
            nombres_equipos = []
            for i in range(1, num_equipos + 1):
                nombre = request.form.get(f'equipo_{i}').strip()
                if not nombre:
                    flash('Todos los equipos deben tener un nombre', 'danger')
                    return redirect(url_for('crear_torneo'))
                
                nombres_equipos.append(nombre)
                db.session.add(Equipo(nombre=nombre))
            
            # Crear calendario
            crear_calendario(nombres_equipos)
            db.session.commit()
            
            flash('Torneo creado exitosamente', 'success')
            return redirect(url_for('admin_dashboard'))
        
        except Exception as e:
            db.session.rollback()
            flash(f'Error al crear torneo: {str(e)}', 'danger')
    
    return render_template('crear_torneo.html')

@app.route('/admin/actualizar-resultado/<int:partido_id>', methods=['POST'])
@admin_required
def actualizar_resultado(partido_id):
    partido = Partido.query.get_or_404(partido_id)
    
    try:
        goles_local = int(request.form.get('goles_local', 0))
        goles_visitante = int(request.form.get('goles_visitante', 0))
        
        # Revertir estadísticas anteriores si el partido ya estaba jugado
        if partido.jugado:
            partido.goles_local = 0
            partido.goles_visitante = 0
            actualizar_estadisticas(partido)
        
        # Actualizar el partido
        partido.goles_local = goles_local
        partido.goles_visitante = goles_visitante
        partido.jugado = True
        
        # Actualizar estadísticas
        actualizar_estadisticas(partido)
        db.session.commit()
        
        flash('Resultado actualizado correctamente', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error al actualizar resultado: {str(e)}', 'danger')
    
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/reiniciar-torneo', methods=['POST'])
@admin_required
def reiniciar_torneo():
    try:
        db.session.query(Partido).delete()
        db.session.query(Equipo).delete()
        db.session.commit()
        flash('Torneo reiniciado correctamente', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error al reiniciar torneo: {str(e)}', 'danger')
    
    return redirect(url_for('crear_torneo'))

@app.route('/logout')
def logout():
    session.clear()
    flash('Has cerrado sesión correctamente', 'info')
    return redirect(url_for('index'))

# Inicialización de la aplicación
with app.app_context():
    db.create_all()

if __name__ == '__main__':
    app.run(debug=True)