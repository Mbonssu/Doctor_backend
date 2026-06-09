# DoctoPing — Backend API (FastAPI)

Backend REST API pour l'application mobile DoctoPing, construite avec FastAPI + PostgreSQL.

---

## Structure du projet

```
doctoping-backend/
├── app/
│   ├── main.py                  # Point d'entrée FastAPI
│   ├── core/
│   │   ├── config.py            # Settings (pydantic-settings)
│   │   ├── database.py          # SQLAlchemy async engine
│   │   └── security.py          # JWT, hashing, dépendances auth
│   ├── models/
│   │   └── models.py            # Tous les modèles SQLAlchemy
│   ├── schemas/
│   │   └── schemas.py           # Tous les schémas Pydantic (I/O)
│   ├── repositories/
│   │   └── repositories.py      # Accès BDD (queries)
│   └── api/v1/
│       └── routes.py            # Tous les endpoints REST
├── migrations/                  # Alembic migrations
├── tests/
├── requirements.txt
├── .env.example
└── alembic.ini
```

---

## Installation

```bash
# 1. Cloner et se placer dans le dossier backend
cd doctoping-backend

# 2. Créer un environnement virtuel
python -m venv venv
source venv/bin/activate        # Linux/macOS
# venv\Scripts\activate         # Windows

# 3. Installer les dépendances
pip install -r requirements.txt

# 4. Configurer les variables d'environnement
cp .env.example .env
# Éditer .env avec vos valeurs (DATABASE_URL, SECRET_KEY...)

# 5. Créer la base de données PostgreSQL
createdb doctoping_db

# 6. Démarrer le serveur
uvicorn app.main:app --reload --port 8000
```

---

## Endpoints principaux

| Méthode | Endpoint | Description |
|---------|----------|-------------|
| POST | `/api/v1/auth/login` | Connexion |
| POST | `/api/v1/auth/register` | Inscription |
| POST | `/api/v1/auth/refresh` | Refresh token |
| POST | `/api/v1/auth/logout` | Déconnexion |
| GET | `/api/v1/users/me` | Profil utilisateur |
| PUT | `/api/v1/users/me` | Modifier profil |
| GET | `/api/v1/doctors` | Liste médecins (avec filtres) |
| GET | `/api/v1/doctors/top-rated` | Médecins les mieux notés |
| GET | `/api/v1/doctors/{id}` | Détail médecin |
| PUT | `/api/v1/doctors/me` | Modifier profil médecin |
| GET | `/api/v1/doctors/me/schedule` | Horaires du médecin |
| PUT | `/api/v1/doctors/me/schedule` | Modifier horaires |
| GET | `/api/v1/doctors/me/appointments` | RDV du médecin |
| POST | `/api/v1/appointments` | Prendre un RDV |
| GET | `/api/v1/appointments/my-appointments` | Mes RDV (patient) |
| GET | `/api/v1/appointments/upcoming` | RDV à venir |
| POST | `/api/v1/appointments/check-availability` | Vérifier dispo |
| PUT | `/api/v1/appointments/{id}` | Modifier un RDV |
| POST | `/api/v1/appointments/{id}/cancel` | Annuler un RDV |
| GET | `/api/v1/reviews/doctor/{id}` | Avis d'un médecin |
| POST | `/api/v1/reviews` | Poster un avis |
| GET | `/api/v1/notifications/unread/count` | Notifications non lues |

Documentation Swagger disponible sur : `http://localhost:8000/docs`

---

## Connexion avec le frontend Flutter

Dans `lib/core/config/api_config.dart`, l'URL de dev pointe déjà sur `http://localhost:8000`.

Pour tester depuis un appareil physique Android, remplace `localhost` par l'IP de ta machine :
```dart
ApiConfig.setCustomDevelopmentUrl('http://192.168.x.x:8000');
```

Pour un émulateur Android : utilise `http://10.0.2.2:8000`.

---

## Variables d'environnement

| Variable | Description | Défaut |
|----------|-------------|--------|
| `DATABASE_URL` | URL PostgreSQL async | `postgresql+asyncpg://...` |
| `SECRET_KEY` | Clé secrète JWT | À changer en prod ! |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | Durée access token | `30` |
| `REFRESH_TOKEN_EXPIRE_DAYS` | Durée refresh token | `30` |
| `DEBUG` | Mode debug | `true` |
