from datetime import datetime, timedelta
from threading import Lock, Thread
import time
from flask import (
    Flask, jsonify, render_template, request, redirect, url_for, flash, session , Response
)

from flask_cors import CORS
import matplotlib
import requests
from functions import (
    getClient, create_instance, get_db_connection , all_instances , get_instance_stats , Running_vms , update_instance_resources
)
import os
import pandas as pd
import matplotlib.pyplot as plt
import io
matplotlib.use('Agg')  # UI conflict 


app = Flask(__name__, template_folder='C:\\Users\\lenovo\\Desktop\\lxd_project\\templates')
CORS(app)
app.config['SECRET_KEY'] = 'admin_secret'

ALIAS_LIST = ["ubuntu", "centos", "debian", "alpine"]

# Page de base
@app.route('/', methods=['GET'])
def homepage():
    return render_template('landingpage.html')

@app.route('/landingpage')
def landing_page():
    if 'username' in session and session.get('role')==2:
     return  redirect(url_for('get_all_instances'))
    elif 'username' in session and session.get('role')==1:
        return redirect(url_for('users_roles'))
    return url_for('register')

@app.route('/login' , methods=['GET', 'POST'])
def login():
    if request.method == 'GET':
         return render_template('login.html')
    elif request.method == 'POST':
      username = request.form.get('username')
      password = request.form.get('password')

      conn = get_db_connection()
      cursor = conn.cursor()

    
      cursor.execute("SELECT * FROM users WHERE username = %s", (username,))
      user = cursor.fetchone()

      if user:
        stored_password = user[2]  
        role_id = user[4]  
        print(role_id)

        if stored_password ==  password:
            session['username'] = username
            session['role'] = role_id

            flash("Connexion réussie", 'success')

            return redirect(url_for('landing_page'))
        else:
            flash("Mot de passe incorrect.", 'error')
      else:
        flash("Nom d'utilisateur introuvable.", 'error')

      return redirect(url_for('register'))

@app.route('/register',methods=['GET','POST'])
def register():
    if request.method == 'GET':
        return render_template('registration.html')
    
    username = request.form.get('username')
    email = request.form.get('email')
    password = request.form.get('password')
    confirm_password = request.form.get('confirm_password')
    
    if password != confirm_password:
        flash('Les mots de passe ne correspondent pas.', 'error')
        return redirect(url_for('register'))

    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM users WHERE email = %s OR username = %s", (email, username))
    existing_user = cursor.fetchone()

    if existing_user:
        flash('L\'utilisateur avec cet email ou nom d\'utilisateur existe déjà.', 'error')
        cursor.close()
        conn.close()
        return redirect(url_for('register'))

    cursor.execute("SELECT id FROM roles WHERE name = 'user'")
    role_id = cursor.fetchone()[0]

    cursor.execute(
        "INSERT INTO users (username, email, password, role_id) VALUES (%s, %s, %s, %s)",
        (username, email, password, role_id)
    )

    conn.commit()

    cursor.close()
    conn.close()

    flash('Inscription réussie ! Vous pouvez desormais acceder a votre compte.', 'success')
    return redirect(url_for('register'))

@app.route('/dashboard')
def dashboard():
    if 'username' in session and session.get('role')==2:
        return render_template('dashboard.html', active_page='dashboard')
    flash("Veuillez vous connecter pour accéder au tableau de bord.", 'error')
    return redirect(url_for('landing_page'))


@app.route('/create-instance', methods=['POST', 'GET'])
def create_new_instance():
    if request.method == 'POST':

        if 'username' not in session:
            flash("Accès refusé. Veuillez vous connecter.", 'error')
            render_template('login.html')

        name = request.form.get('name')
        alias = request.form.get('alias')
        cpu = request.form.get('cpu', type=int)
        memory = request.form.get('memory', type=int)
        instance_type = request.form.get('type')
        conn = get_db_connection()
        cursor = conn.cursor()

        username = session.get('username')

        try:
            cursor.execute("SELECT id FROM users WHERE username = %s", (username,))
            user_data = cursor.fetchone()

            if user_data:
                user_id = user_data[0]
                instance_name = f"{name}-{username}"

                # Création de l'instance
                instance = create_instance(instance_name, alias, cpu, memory , instance_type)
                cursor.execute(
                    "INSERT INTO instances (user_id, instance_name) VALUES (%s, %s)",
                    (user_id, instance_name)
                )
                conn.commit()

                flash(f"Instance {instance_name} créée avec succès.", 'success')
                return redirect(url_for('get_all_instances'))
            else:
                flash("Utilisateur introuvable.", 'error')
        except Exception as e:
            conn.rollback()
            flash(f"Erreur : {str(e)}", 'error')
        finally:
            cursor.close()
            conn.close() 

    return render_template('create_instance.html', alias_list=ALIAS_LIST)




@app.route('/instances', methods=['GET'])
def get_all_instances():
    conn = get_db_connection()
    username = session.get('username')
    role = session.get('role')

    if username and role:
        cursor = conn.cursor()

        instances_info = all_instances()  

        if role == 2:
            cursor.execute("SELECT id FROM users WHERE username = %s", (username,))
            user_data = cursor.fetchone()
            if user_data:
                user_id = user_data[0]
                cursor.execute("SELECT instance_name FROM instances WHERE user_id = %s", (user_id,))
                user_instances_names = cursor.fetchall()
                user_instances = [instance[0] for instance in user_instances_names]

                user_instance_to_retrieve = [instance for instance in instances_info if instance['name'] in user_instances]

                conn.close()  
                return render_template('containers.html', instances=user_instance_to_retrieve)
            else:
                conn.close()
                return jsonify({"error": "Utilisateur non trouvé."}), 404

        elif role == 1:
           cursor.execute("SELECT username FROM users")
           results = cursor.fetchall()

           usernames = {result[0] for result in results}

           for instance in instances_info:
             instance_name = instance.get('name')  # Récupérer le nom de l'instance
             if isinstance(instance_name, str):   # Vérifier que c'est une chaîne valide
                 parts = instance_name.split('-')
                 owner = next((user for user in parts if user in usernames), None)
                 if owner:
                    instance['owner'] = owner  

        conn.close()  
        return render_template('admin-visibility-containers.html', instances=instances_info)

    else:
        return redirect(url_for('login'))
    
@app.route('/start_instance/<name>', methods=['POST', 'GET'])
def start_instance(name):
    client = getClient()
    if 'username' in session:

        if session.get('username') in name.split('-'):
            try:
                instance = client.instances.get(name)
                instance.start()
                flash(f"Instance {instance.name} démarrée.", 'success')
                return redirect(url_for('get_all_instances')) 

            except Exception as e:
                flash(f"Erreur : {str(e)}", 'danger')
                return redirect(url_for('get_all_instances'))

        elif session.get('role') == 1:
            try:
                instance = client.instances.get(name)
                instance.start()
                flash(f"Instance {instance.name} démarrée par un administrateur.", 'success')
                return redirect(url_for('get_all_instances'))
            except Exception as e:
                flash(f"Erreur : {str(e)}", 'danger')
                return redirect(url_for('get_all_instances'))
    else:
        flash('Accès non autorisé', 'danger')
        return redirect(url_for('get_all_instances'))
    

@app.route('/stop_instance/<name>', methods=['POST' , 'GET'])
def stop_instance(name):
    client = getClient()
    if 'username' in session:

        if session.get('username') in name.split('-'):
            try:
                instance = client.instances.get(name)
                instance.stop()
                flash(f"Instance {instance.name} arretée.", 'success')
                return redirect(url_for('get_all_instances'))
            except Exception as e:
                 flash(f"Erreur : {str(e)}", 'danger')
                 return redirect(url_for('get_all_instances'))

        elif session.get('role') == 1:
            try:
                instance = client.instances.get(name)
                instance.stop()
                flash(f"Instance {instance.name} arretée par un administrateur.", 'success')
                return render_template('admin-visibility-containers.html')
            except Exception as e:
                flash(f"Erreur : {str(e)}", 'danger')
                return redirect(url_for('get_all_instances'))
    else:

        flash('Accès non autorisé', 'danger')
        return redirect(url_for('get_all_instances')) 

@app.route('/delete_instance/<name>', methods=['POST', 'GET'])
def delete_instance(name):
    client = getClient()

    if 'username' in session:
        conn = get_db_connection()
        try:

            if session.get('username') in name.split('-'):
                username = session.get('username')
                instance = client.instances.get(name) 

                cursor = conn.cursor()
                
                cursor.execute("DELETE FROM instances WHERE instance_name = %s", (name,))
                conn.commit()  
                
                instance.delete(wait=True)
                
                flash(f"Instance {instance.name} supprimée.", 'success')
                return redirect(url_for('get_all_instances'))
            
            elif session.get('role') == 1:
                instance = client.instances.get(name)
                
                cursor = conn.cursor()
                cursor.execute("DELETE FROM instances WHERE name = %s", (name,))
                conn.commit()
                
                instance.delete(wait=True)
                
                flash(f"Instance {instance.name} supprimée par un administrateur.", 'success')
                return redirect(url_for('get_all_instances'))
            
        except Exception as e:
             flash(f"Erreur : {str(e)}", 'danger')
             return redirect(url_for('get_all_instances'))
        finally:
            cursor.close()
            conn.close()
    else:

        flash(f"Erreur : {str(e)}", 'danger')
        return redirect(url_for('get_all_instances'))


@app.route('/monitoring', methods=['GET', 'POST'])
def monitoring():
    
    # instances in a running state
    containers = Running_vms()
    stats = None
    if request.method == 'POST':
        
        container_name = request.form.get('container_name')

        if container_name:
            try:

                stats = get_instance_stats(container_name)
            except Exception as e:
                stats = {"error": str(e)}

    return render_template('monitoring.html', containers=containers, stats=stats)

@app.route('/update_instance_resources', methods=['GET', 'POST'])
def update_resources():
    if 'username' not in session:
        flash("Veuillez vous connecter pour accéder à cette fonctionnalité.", 'danger')
        return redirect(url_for('login'))

    if request.method == 'GET':
        return render_template('update_resources.html')

    try:
        name = request.form.get('name')
        name_without_space = name.replace("","")
        cpu = request.form.get('cpu')
        memory = request.form.get('memory')

        res_split = name.split('-')

        # verifing that the user attembting to update resources that its the owner
        if session.get('username') not in name_without_space.split('-'):
            print(session.get('username'))
            print(name)
            print(res_split)
            flash("Vous n'êtes pas autorisé à modifier ce conteneur.", 'danger')
            return render_template('update_resources.html')

        # data validation
        if not cpu.isdigit() or not memory.isdigit():
            flash("Veuillez entrer des valeurs numériques valides pour le CPU et la mémoire.", 'danger')
            return render_template('update_resources.html')

        # iinvoque update function
        updated_config = update_instance_resources(name_without_space, cpu, memory)

        flash(f"Ressources de l'instance {name} ont ete bien mise a jour", 'success')
        return render_template('update_resources.html', updated_config=updated_config)

    except Exception as e:
        flash(f"Erreur : {str(e)}", 'danger')
        return render_template('update_resources.html')

@app.route('/logout' , methods=['POST' , 'GET'])
def logout():
    session.pop('username', None)  
    return redirect(url_for('homepage'))


# Page principale
@app.route("/mon")
def index():
    """Page principale avec des liens pour les graphiques"""
    return render_template("dashboard.html")

@app.route("/users")
def users_roles():
    if 'username' in session and session.get('role') == 1:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT username, email, role_id FROM users')
        users = cursor.fetchall()

        # Transformation des rôles : on remplace les role_id par les noms correspondants
        users_transformed = []
        for user in users:
            user_dict = {
                'username': user[0],
                'email': user[1],
                'role': "Administrateur" if user[2] == 1 else "Utilisateur"
            }
            users_transformed.append(user_dict)
        
        return render_template('users.html', users=users_transformed)
    else:
        return redirect('/login')
@app.route("/add_user" , methods=["POST"])
def add_user():
    data = request.json
    new_user = {
        "username": data['username'],
        "email": data['email'],
        "role": 'user',
        "password": data['password']
    }
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO users (username, email, password, role_id) VALUES (%s, %s, %s, %s)",
        (new_user['username'], new_user['email'], new_user['password'], 2)
    )
    
    conn.commit()
    cursor.close()
    conn.close()
    return redirect(url_for('users_roles'))

@app.route('/delete_user/<name>', methods=['POST'])
def delete_user(name):
    if 'username' in session and session.get('role') == 1:
        try:
            conn = get_db_connection()
            cursor = conn.cursor()

            cursor.execute('SELECT id FROM users WHERE username = %s', (name,))
            user = cursor.fetchone()
            
            if user:
                user_id = user[0]
                
                cursor.execute('SELECT * FROM instances WHERE user_id = %s', (user_id))
                instances = cursor.fetchall()
                if instances:
                    cursor.execute('DELETE FROM instances WHERE user_id = %s', (user_id,))
                    cursor.execute('DELETE FROM users WHERE id = %s', (user_id,))
                    conn.commit()
                
                cursor.execute('DELETE FROM users WHERE id = %s', (user_id,))
                conn.commit()
                flash(f"Utilisateur {name} a été bien supprimé", 'success')
            else:
                flash(f"L'utilisateur {name} n'existe pas", 'error')

            cursor.close()
            conn.close()

        except Exception as e:
            flash(f"Une erreur est survenue : {str(e)}", 'error')
            return redirect(url_for('users_roles'))

        return redirect(url_for('users_roles'))

    flash('Vous n\'avez pas les droits nécessaires pour effectuer cette action', 'error')
    return redirect(url_for('login')) 


@app.route('/edit_user', methods=['POST'])
def update_user():
    data = request.json
    updated_user = {
        "username": data['username'],
        "email": data['email'],
        "role": 'user',
        "password": data['password']
    }
    # Vérifier si l'utilisateur a les droits pour effectuer cette action
    if 'username' not in session or session.get('role') != 1:
        return jsonify({'error': 'Permission refusée'}), 403

    # Valider les champs requis
    if not all(key in data for key in ('username', 'email', 'password')):
        return jsonify({'error': 'Champs manquants'}), 400

    # Effectuer la mise à jour
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                     'UPDATE Users SET email = %s , password = %s WHERE username = %s',
                            (data['email'],data['password'], data['username'])
                     )
            conn.commit()
            flash(f"Utilisateur {data['username']} a été bien modifié", 'success')
    except Exception as e:
        return jsonify({'error': 'Erreur lors de la mise à jour : {}'.format(str(e))}), 500

    return jsonify({'message': 'Utilisateur mis à jour avec succès'})

 
 # URL de Prometheus
PROMETHEUS_URL = 'http://192.168.0.189:9090/api/v1/query_range'

# Répertoire pour stocker les images de graphiques
GRAPH_FOLDER = "static/graphs"
os.makedirs(GRAPH_FOLDER, exist_ok=True)

# Fonction pour récupérer les métriques depuis Prometheus
def fetch_metric(container_name, query, label):
    end_time = datetime.utcnow()
    start_time = end_time - timedelta(hours=2)

    params = {
        'query': query.format(container_name=container_name),
        'start': start_time.strftime('%Y-%m-%dT%H:%M:%SZ'),
        'end': end_time.strftime('%Y-%m-%dT%H:%M:%SZ'),
        'step': '15s'
    }

    try:
        response = requests.get(PROMETHEUS_URL, params=params)
        response.raise_for_status()
        data = response.json().get('data', {}).get('result', [])
        if not data:
            print(f"Aucune donnée trouvée pour la requête : {query}")
            return None

        timestamps = []
        values = []
        for result in data:
            for value in result['values']:
                timestamps.append(datetime.utcfromtimestamp(float(value[0])))
                values.append(float(value[1]))

        return pd.DataFrame({'timestamp': timestamps, label: values})
    
    except requests.exceptions.RequestException as e:
        print(f"Erreur lors de la requête pour {query}: {e}")
        return None

# Fonction pour tracer et enregistrer un graphique
def plot_metric_updated(container_name, df, label):
    if df is not None and not df.empty:
        plt.figure(figsize=(10, 6))
        plt.plot(df['timestamp'], df[label], label=label, color='b')
        plt.xlabel('Temps')
        plt.ylabel(label)
        plt.title(f'{label} Over Time for {container_name}')
        plt.xticks(rotation=45)
        plt.tight_layout()
        plt.legend()
        graph_path = os.path.join(GRAPH_FOLDER, f"{container_name}_{label.replace(' ', '_')}.png")
        plt.savefig(graph_path)
        plt.close()
        return graph_path
    return None

# Vue principale
@app.route('/monitoring_updated', methods=['GET', 'POST'])
def monitoring_updated():
    if request.method == 'POST':
        container_name = request.form.get('container_name')
        if not container_name:
            return render_template('index.html', error="Veuillez entrer un nom de conteneur.")

        # Récupérer et tracer les métriques
        metrics = {
            'CPU Usage': 'lxd_cpu_seconds_total{{mode="user", name="{container_name}"}}',
            'Memory Usage (Bytes)': 'lxd_memory_Active_bytes{{name="{container_name}"}}',
            'Network Transmit (Bytes)': 'lxd_network_transmit_bytes_total{{name="{container_name}"}}',
            'Network Receive (Bytes)': 'lxd_network_receive_bytes_total{{name="{container_name}"}}'
        }
        graphs = []
        for label, query in metrics.items():
            df = fetch_metric(container_name, query, label)
            graph_path = plot_metric_updated(container_name, df, label)
            if graph_path:
                graphs.append(graph_path)

        return render_template('index.html', container_name=container_name, graphs=graphs)

    return render_template('index.html')
if __name__ == '__main__':
    app.run(debug=True)
