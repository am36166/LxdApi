
from pylxd import Client
import time
import pymysql



def get_db_connection():
    return pymysql.connect(
         host="localhost",
         user="root",
         password="",
         database="gestion_instances"
)

def getClient():
    client = Client(
        endpoint="https://controller:8443",
         cert=('C:/Users/lenovo/.config/lxc/client.crt', 'C:/Users/lenovo/.config/lxc/client.key')
         )
    return client

def create_instance(name, alias, cpu, memory):
    
    config = {
        'name': name,  # Utilisation du nom passé en paramètre
        'source': {
            'type': 'image',  # La source est une image
            'alias': alias,  # Utilisation de l'alias passé en paramètre
            'mode': 'pull',  # Utilisation du mode passé en paramètre
            'server': 'https://cloud-images.ubuntu.com/daily',  # Serveur d'images Ubuntu
            'protocol': 'simplestreams',  # Protocole simplestreams
        },
        'config': {
            'limits.cpu': str(cpu),
            'limits.memory': f"{memory}MB",
        },
        'type': 'container',  # Type d'instance : conteneur
        'profiles': ['default'],  # Profils à appliquer (profil par défaut)
    }
    
    client = getClient()
    instance = client.instances.create(config, wait=True)
    instance.start()
    time.sleep(10)
    status = instance.state()  # Utilisez state() au lieu de status()
    
    return instance

def get_instance_ip_address_if_running(name):

    # Vérification de l'état de l'instance
    state = name.state().status
    if state != 'Running':
        return f""

    try:
        # Récupération des informations réseau
        network_info = name.state().network  # Toutes les interfaces réseau
        
        # Parcourir toutes les interfaces réseau
        for interface, interface_info in network_info.items():
            # Chercher une adresse IPv4 dans cette interface
            for address in interface_info['addresses']:
                if address['family'] == 'inet':  # Chercher une adresse IPv4
                    return address['address']  # Retourner l'adresse IPv4 trouvée
        
        return "Aucune adresse IP IPv4 trouvée."
    except Exception as e:
        return f"Erreur : {e}"

def get_instance_config(instance):
    # Récupérer les détails de configuration de l'instance
    config = instance.config
    cpu_limit = config.get('limits.cpu', 'Non spécifié')
    memory_limit = config.get('limits.memory', 'Non spécifié')
    description = config.get('image.description' , 'Non spécifié')
    ip = get_instance_ip_address_if_running(instance)

    return cpu_limit, memory_limit, description ,ip


# Fonction pour afficher toutes les instances
def all_instances():
    client = getClient()
    instances = client.instances.all()
    instances_info = []
    for instance in instances:
        cpu_limit, memory_limit , description ,ip = get_instance_config(instance)
        status = instance.state().status

        instances_info.append({
            'name': instance.name,
            'status': status,
            'cpu': cpu_limit,
            'memory': memory_limit,
            'description' : description,
            'ip': ip
        })
    return instances_info

def update_instance_resources(name, cpu=None, memory=None):
    try:
        client = getClient()

        # Récupérer l'instance par son nom
        instance = client.instances.get(name)
        
        # Si CPU est spécifié, mettre à jour
        if cpu is not None:
            instance.config['limits.cpu'] = str(cpu)
        
        # Si Mémoire est spécifiée, mettre à jour
        if memory is not None:
            instance.config['limits.memory'] = f"{memory}MB"
        
        # Sauvegarder les modifications
        instance.save()
        
        # Retourner les nouvelles configurations
        return instance.config
    
    except Exception as e:
        return str(e)

def get_instance_stats(vm):
    
    client = getClient()

    # Récupérer l'état de l'instance
    instance = client.instances.get(vm)
    state = instance.state()
    
    # Utilisation de la mémoire
    memory_usage = state.memory['usage']
    memory_usage_peak = state.memory['usage_peak']
    
    # Utilisation du réseau (interface eth0)
    eth0 = state.network['eth0']
    eth0_ip = eth0['addresses'][0]['address']
    eth0_received_bytes = eth0['counters']['bytes_received']
    eth0_sent_bytes = eth0['counters']['bytes_sent']
    eth0_received_packets = eth0['counters']['packets_received']
    eth0_sent_packets = eth0['counters']['packets_sent']
    
    # Utilisation du réseau (interface loopback)
    lo = state.network['lo']
    lo_ip = lo['addresses'][0]['address']
    lo_received_bytes = lo['counters']['bytes_received']
    lo_sent_bytes = lo['counters']['bytes_sent']
    lo_received_packets = lo['counters']['packets_received']
    lo_sent_packets = lo['counters']['packets_sent']
    
    # Utilisation du CPU
    cpu_usage = state.cpu['usage']
    cpu_usage_percentage = (cpu_usage / 1e9) * 100  # Conversion en pourcentage
    
    # Préparation des données pour l'API (au format dictionnaire)
    stats = {
        "memory": {
            "usage": memory_usage,
            "usage_peak": memory_usage_peak
        },
        "network": {
            "eth0": {
                "ip": eth0_ip,
                "bytes_received": eth0_received_bytes,
                "bytes_sent": eth0_sent_bytes,
                "packets_received": eth0_received_packets,
                "packets_sent": eth0_sent_packets
            },
            "lo": {
                "ip": lo_ip,
                "bytes_received": lo_received_bytes,
                "bytes_sent": lo_sent_bytes,
                "packets_received": lo_received_packets,
                "packets_sent": lo_sent_packets
            }
        },
        "cpu": {
            "usage_percentage": f"{cpu_usage_percentage:.2f}",
            "cpu_time_seconds": f"{cpu_usage / 1e9:.2f}"
        }
    }
    
    return stats
# Routes Flask

def Running_vms():
    client = getClient()

    instances = client.instances.all()
    up_vms = []
    for instance in instances:
        state = instance.state().status
        if state == "Running":
            up_vms.append(instance.name)
    return up_vms