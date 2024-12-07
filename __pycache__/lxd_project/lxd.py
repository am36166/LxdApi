from flask import (
    Flask, jsonify, render_template, request, redirect, url_for, flash, session
)
from flask_cors import CORS
from functions import (
    getClient, create_instance, get_db_connection , all_instances , get_instance_stats , Running_vms
)
import os

app = Flask(__name__, template_folder='C:\\Users\\lenovo\\Desktop\\lxd_project\\templates')
CORS(app)
app.config['SECRET_KEY'] = 'admin_secret'

# Page de base
@app.route('/')
def landing_page():
    return render_template('base.html', active_page='base')

@app.route('/login' , methods=['GET', 'POST'])
def login():
    if request.method == 'GET':
         return render_template('login.html')
    elif request.method == 'POST':
      username = request.form.get('username')
      password = request.form.get('password')

    # Connexion à la base de données
      conn = get_db_connection()
      cursor = conn.cursor()

    # Exécution de la requête avec paramètres (évite l'injection SQL)
      cursor.execute("SELECT * FROM users WHERE username = %s", (username,))
      user = cursor.fetchone()

      if user:
        stored_password = user[2]  # Supposons que le mot de passe est dans la 3ème colonne
        role_id = user[4]  # Supposons que le rôle est dans la 4ème colonne
        print(role_id)

        # Vérifier si le mot de passe est correct (utilisation de check_password_hash si haché)
        if stored_password ==  password:
            # Créer une session pour l'utilisateur et stocker son rôle
            session['username'] = username
            session['role'] = role_id

            flash("Connexion réussie", 'success')

            return redirect(url_for('dashboard'))
        else:
            flash("Mot de passe incorrect.", 'error')
      else:
        flash("Nom d'utilisateur introuvable.", 'error')

      return redirect(url_for('register'))

@app.route('/register')
def register():
    if request.method == 'GET':
        return render_template('registration.html')


# Page Dashboard
@app.route('/dashboard')
def dashboard():
    if 'username' in session:
        return render_template('dashboard.html', active_page='dashboard')
    flash("Veuillez vous connecter pour accéder au tableau de bord.", 'error')
    return redirect(url_for('landing_page'))

# Création d'une nouvelle instance
@app.route('/create-instance', methods=['POST', 'GET'])
def create_new_instance():
    if request.method == 'POST':
        # Vérifier que l'utilisateur est authentifié
        if 'username' not in session:
            return jsonify({'message': "Accès refusé. Veuillez vous connecter.", 'status': 'error'}), 403

        # Récupération des données du formulaire
        name = request.form.get('name')
        alias = request.form.get('alias')
        cpu = request.form.get('cpu')
        memory = request.form.get('memory')

        conn = get_db_connection()
        cursor = conn.cursor()

        username = session.get('username')

        try:
            # Récupérer l'ID utilisateur
            cursor.execute("SELECT id FROM users WHERE username = %s", (username,))
            user_data = cursor.fetchone()

            if user_data:
                user_id = user_data[0]
                instance_name = f"{name}-{username}"

                # Création de l'instance
                instance = create_instance(instance_name, alias, cpu, memory)
                cursor.execute(
                    "INSERT INTO instances (user_id, instance_name) VALUES (%s, %s)",
                    (user_id, instance_name)
                )
                conn.commit()

                flash(f"Instance {instance_name} créée avec succès.", 'success')
                return redirect(url_for('dashboard'))
            else:
                flash("Utilisateur introuvable.", 'error')
        except Exception as e:
            conn.rollback()
            flash(f"Erreur : {str(e)}", 'error')
        finally:
            cursor.close()
            conn.close()

    return render_template('create_instance.html', active_page='create_instance')




@app.route('/instances', methods=['GET'])
def get_all_instances():
    conn = get_db_connection()
    username = session.get('username')
    role = session.get('role')

    if username and role:
        cursor = conn.cursor()

        # Récupère toutes les instances disponibles
        instances_info = all_instances()  # Vous devez vous assurer que cette fonction renvoie les bonnes données

        if role == 2:
            cursor.execute("SELECT id FROM users WHERE username = %s", (username,))
            user_data = cursor.fetchone()
            if user_data:
                user_id = user_data[0]
                cursor.execute("SELECT instance_name FROM instances WHERE user_id = %s", (user_id,))
                user_instances_names = cursor.fetchall()
                user_instances = [instance[0] for instance in user_instances_names]

                user_instance_to_retrieve = [instance for instance in instances_info if instance['name'] in user_instances]

                conn.close()  # Fermer la connexion après utilisation
                return render_template('containers.html', instances=user_instance_to_retrieve)
            else:
                conn.close()
                return jsonify({"error": "Utilisateur non trouvé."}), 404

        elif role == 1:
            conn.close()  # Fermer la connexion après utilisation
            return render_template('containers.html', instances=instances_info)

    else:
        return redirect(url_for('login'))
    
@app.route('/start_instance/<name>', methods=['POST', 'GET'])
def start_instance(name):
    client = getClient()
    if 'username' in session:
        # Vérifier si le nom d'utilisateur est dans le nom de l'instance
        if session.get('username') in name.split('-'):
            try:
                instance = client.instances.get(name)
                instance.start()
                flash(f"Instance {instance.name} démarrée.", 'success')
                return render_template('containers.html')  # Rediriger vers containers.html

            except Exception as e:
                flash(f"Erreur : {str(e)}", 'danger')
                return render_template('containers.html')
        # Si l'utilisateur a un rôle administrateur (role == 1)
        elif session.get('role') == 1:
            try:
                instance = client.instances.get(name)
                instance.start()
                flash(f"Instance {instance.name} démarrée par un administrateur.", 'success')
                return render_template('containers.html')
            except Exception as e:
                flash(f"Erreur : {str(e)}", 'danger')
                return render_template('containers.html')
    else:
        flash('Accès non autorisé', 'danger')
        return redirect(url_for('containers'))
    

@app.route('/stop_instance/<name>', methods=['POST' , 'GET'])
def stop_instance(name):
    client = getClient()
    if 'username' in session:
        # Vérifier si le nom d'utilisateur est dans le nom de l'instance
        if session.get('username') in name.split('-'):
            try:
                instance = client.instances.get(name)
                instance.stop()
                flash(f"Instance {instance.name} arretée.", 'success')
                return render_template('containers.html')
            except Exception as e:
                 flash(f"Erreur : {str(e)}", 'danger')
                 return render_template('containers.html')
        # Si l'utilisateur a un rôle administrateur (role == 1)
        elif session.get('role') == 1:
            try:
                instance = client.instances.get(name)
                instance.stop()
                flash(f"Instance {instance.name} arretée par un administrateur.", 'success')
                return render_template('containers.html')
            except Exception as e:
                flash(f"Erreur : {str(e)}", 'danger')
                return render_template('containers.html')
    else:
        # Si l'utilisateur n'est pas authentifié
        flash('Accès non autorisé', 'danger')
        return render_template('containers.html') 

@app.route('/delete_instance/<name>', methods=['POST', 'GET'])
def delete_instance(name):
    client = getClient()

    if 'username' in session:
        conn = get_db_connection()
        try:
            # Vérifier si l'utilisateur est associé à l'instance
            if session.get('username') in name.split('-'):
                username = session.get('username')
                instance = client.instances.get(name) 
                # Créer un curseur pour exécuter les requêtes SQL
                cursor = conn.cursor()
                
                # Supprimer l'instance associée à cet utilisateur dans la base de données
                cursor.execute("DELETE FROM instances WHERE instance_name = %s", (name,))
                conn.commit()  # Appliquer les changements à la base de données
                
                # Supprimer l'instance elle-même
                instance.delete(wait=True)
                
                flash(f"Instance {instance.name} supprimée.", 'success')
                return render_template('containers.html')
            
            # Si l'utilisateur a un rôle administrateur (role == 1)
            elif session.get('role') == 1:
                instance = client.instances.get(name)
                
                # Supprimer l'instance de la base de données
                cursor = conn.cursor()
                cursor.execute("DELETE FROM instances WHERE name = %s", (name,))
                conn.commit()
                
                # Supprimer l'instance elle-même
                instance.delete(wait=True)
                
                flash(f"Instance {instance.name} supprimée par un administrateur.", 'success')
                return render_template('containers.html')
            
        except Exception as e:
             flash(f"Erreur : {str(e)}", 'danger')
             return render_template('containers.html')
        finally:
            cursor.close()
            conn.close()
    else:
        # Si l'utilisateur n'est pas authentifié
        flash(f"Erreur : {str(e)}", 'danger')
        return render_template('containers.html')


@app.route('/monitoring', methods=['GET', 'POST'])
def monitoring():
    
    # Récupérer tous les containers en état running
    containers = Running_vms()
    stats = None
    if request.method == 'POST':
        # Récupérer le nom du container sélectionné
        container_name = request.form.get('container_name')

        if container_name:
            try:
                # Récupérer les statistiques du container sélectionné
                stats = get_instance_stats(container_name)
            except Exception as e:
                # Gérer les erreurs de récupération des stats
                stats = {"error": str(e)}

    return render_template('monitoring.html', containers=containers, stats=stats)



if __name__ == '__main__':
    app.run(debug=True)
